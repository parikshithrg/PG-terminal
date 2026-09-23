"""Local PG-terminal server with an in-memory Kite Connect handshake."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from zoneinfo import ZoneInfo


TOKEN_URL = "https://api.kite.trade/session/token"
PROFILE_URL = "https://api.kite.trade/user/profile"
OHLC_URL = "https://api.kite.trade/quote/ohlc"
NSE_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NSE"
NIFTY500_CONSTITUENTS_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
NIFTY_INDICES_PUBLIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HISTORICAL_URL_TEMPLATE = "https://api.kite.trade/instruments/historical/{instrument_token}/day"
BASE_INDEX = ("Nifty 50", "NSE:NIFTY 50")
DASHBOARD_EOD_INDICES = ("Nifty 50", "Nifty Bank", "Nifty IT", "Nifty Energy")
OFFICIAL_SECTORAL_INDICES = (
    "Nifty Auto",
    "Nifty Bank",
    "Nifty Capital Goods",
    "Nifty Cement",
    "Nifty Chemicals",
    "Nifty Commercial & Transport Services",
    "Nifty Construction",
    "Nifty Consumer Durables",
    "Nifty Consumer Services",
    "Nifty Financial Services",
    "Nifty Financial Services 25/50",
    "Nifty Financial Services Ex Bank",
    "Nifty FMCG",
    "Nifty Healthcare",
    "Nifty Hospitals",
    "Nifty Housing Finance",
    "Nifty Insurance",
    "Nifty IT",
    "Nifty Media",
    "Nifty Metal",
    "Nifty NBFC",
    "Nifty Oil and Gas",
    "Nifty Pharma",
    "Nifty Power",
    "Nifty Private Bank",
    "Nifty PSU Bank",
    "Nifty Realty",
    "Nifty REITs & Realty",
    "Nifty Retail",
    "Nifty Telecommunications",
    "Nifty500 Healthcare",
    "Nifty MidSmall Financial Services",
    "Nifty MidSmall Healthcare",
    "Nifty MidSmall IT & Telecom",
)
INDEX_NAME_ALIASES = {
    "Nifty Consumer Durables": ("NIFTY CONSR DURBL",),
    "Nifty Financial Services": ("NIFTY FIN SERVICE",),
    "Nifty Financial Services Ex Bank": ("NIFTY FINSRV EX-BANK",),
    "Nifty Private Bank": ("NIFTY PVT BANK",),
    "Nifty Telecommunications": ("NIFTY TELECOM",),
    "Nifty MidSmall Financial Services": ("NIFTY MIDSML FIN SERV",),
    "Nifty MidSmall Healthcare": ("NIFTY MIDSML HEALTHCARE",),
    "Nifty MidSmall IT & Telecom": ("NIFTY MIDSML IT & TELECOM",),
}
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_INSTRUMENT_BYTES = 8 * 1024 * 1024
MAX_CONSTITUENT_BYTES = 128 * 1024
REQUEST_TIMEOUT_SECONDS = 10
BREADTH_CACHE_SECONDS = 15 * 60
HISTORICAL_LOOKBACK_DAYS = 420
HISTORICAL_REQUEST_INTERVAL_SECONDS = 0.36
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")

_ACTIVE_KITE_SESSION: dict[str, str] = {}
_ACTIVE_INDEX_TARGETS: list[tuple[str, str, str]] = []
_ACTIVE_DASHBOARD_INDEX_TOKENS: dict[str, str] = {}
_ACTIVE_EQUITY_TOKENS: dict[str, str] = {}
_KITE_DIAGNOSTICS: dict[str, str | None] = {"last_error": None}
_BREADTH_CACHE: dict[str, object] = {}
_SESSION_LOCK = threading.Lock()
_BREADTH_BUILD_LOCK = threading.Lock()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_PROVIDER_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def extract_request_token(value: str) -> str:
    """Accept a raw request token or the full registered redirect URL."""
    candidate = value.strip()
    if not candidate:
        return ""
    if "://" not in candidate and "request_token=" not in candidate:
        return candidate

    parsed = urllib.parse.urlparse(candidate if "://" in candidate else f"https://local/?{candidate}")
    values = urllib.parse.parse_qs(parsed.query).get("request_token", [])
    return values[0].strip() if len(values) == 1 else ""


def build_checksum(api_key: str, request_token: str, api_secret: str) -> str:
    return hashlib.sha256(f"{api_key}{request_token}{api_secret}".encode("utf-8")).hexdigest()


def classify_network_error(error: BaseException) -> str:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "provider_timeout"
    if isinstance(reason, ssl.SSLError):
        return "provider_tls_failure"
    if isinstance(reason, socket.gaierror):
        return "provider_dns_failure"
    if isinstance(reason, PermissionError) or getattr(reason, "winerror", None) == 10013:
        return "provider_network_blocked"
    return "provider_connection_failed"


def parse_nifty500_constituents(csv_payload: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_constituent_file")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in reader:
        symbol = (row.get("Symbol") or "").strip().upper()
        industry = (row.get("Industry") or "").strip()
        series = (row.get("Series") or "").strip().upper()
        if not symbol or not industry or series not in {"EQ", "BE"} or symbol in seen:
            raise ValueError("invalid_constituent_file")
        seen.add(symbol)
        rows.append({"symbol": symbol, "sector": industry})
    # NIFTY 500 is a 500-company index. Its official constituent file can
    # contain 501 securities when a constituent is represented by an
    # additional eligible series, so preserve the official file as published.
    if len(rows) not in {500, 501}:
        raise ValueError("unexpected_constituent_count")
    return rows


def parse_equity_tokens(csv_payload: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"instrument_token", "tradingsymbol", "instrument_type", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")
    tokens: dict[str, str] = {}
    for row in reader:
        if (
            row.get("exchange") != "NSE"
            or row.get("segment") != "NSE"
            or row.get("instrument_type") != "EQ"
        ):
            continue
        symbol = (row.get("tradingsymbol") or "").strip().upper()
        token = (row.get("instrument_token") or "").strip()
        if symbol and token.isdigit():
            tokens.setdefault(symbol, token)
    if not tokens:
        raise ValueError("invalid_instrument_master")
    return tokens


def parse_dashboard_index_tokens(csv_payload: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"instrument_token", "tradingsymbol", "name", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")
    inventory: dict[str, str] = {}
    for row in reader:
        if row.get("exchange") != "NSE" or row.get("segment") != "INDICES":
            continue
        token = (row.get("instrument_token") or "").strip()
        if not token.isdigit():
            continue
        for candidate in ((row.get("tradingsymbol") or ""), (row.get("name") or "")):
            if candidate.strip():
                inventory.setdefault(normalize_index_name(candidate), token)
    result: dict[str, str] = {}
    for display_name in DASHBOARD_EOD_INDICES:
        candidates = (display_name, *INDEX_NAME_ALIASES.get(display_name, ()))
        token = next(
            (
                inventory[normalize_index_name(candidate)]
                for candidate in candidates
                if normalize_index_name(candidate) in inventory
            ),
            None,
        )
        if token is None:
            raise ValueError("dashboard_index_not_available")
        result[display_name] = token
    return result


def parse_daily_closes(
    provider_payload: dict[str, object],
    *,
    today: date,
    now_time: datetime_time,
) -> list[tuple[date, float]]:
    data = provider_payload.get("data")
    candles = data.get("candles") if isinstance(data, dict) else None
    if provider_payload.get("status") != "success" or not isinstance(candles, list):
        raise ValueError("invalid_provider_response")
    allow_today = now_time >= datetime_time(15, 40)
    parsed: list[tuple[date, float]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 5 or not isinstance(candle[0], str):
            raise ValueError("invalid_provider_response")
        close = candle[4]
        if not isinstance(close, (int, float)) or isinstance(close, bool) or not math.isfinite(float(close)):
            raise ValueError("invalid_provider_response")
        try:
            candle_date = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).date()
        except ValueError as error:
            raise ValueError("invalid_provider_response") from error
        if candle_date < today or allow_today:
            parsed.append((candle_date, float(close)))
    parsed.sort(key=lambda item: item[0])
    return parsed


def calculate_index_ytd(
    display_name: str, history: list[tuple[date, float]]
) -> dict[str, object]:
    if not history:
        raise ValueError("no_completed_historical_data")
    latest_date, latest_close = history[-1]
    prior_year_rows = [item for item in history if item[0].year < latest_date.year]
    if not prior_year_rows:
        raise ValueError("prior_year_close_unavailable")
    prior_date, prior_close = prior_year_rows[-1]
    if prior_close <= 0:
        raise ValueError("invalid_provider_response")
    return {
        "display_name": display_name,
        "as_of_date": latest_date.isoformat(),
        "close": round(latest_close, 2),
        "prior_year_close_date": prior_date.isoformat(),
        "ytd_pct": round(((latest_close / prior_close) - 1) * 100, 2),
    }


def calculate_market_breadth(
    constituents: list[dict[str, str]],
    histories: dict[str, list[tuple[date, float]]],
) -> tuple[list[dict[str, object]], date, int]:
    latest_dates = [history[-1][0] for history in histories.values() if history]
    if not latest_dates:
        raise ValueError("no_completed_historical_data")
    as_of = max(latest_dates)
    sectors: dict[str, list[list[float]]] = {}
    for constituent in constituents:
        history = histories.get(constituent["symbol"], [])
        closes = [close for candle_date, close in history if candle_date <= as_of]
        if not history or history[-1][0] != as_of or len(closes) < 201:
            continue
        sectors.setdefault(constituent["sector"], []).append(closes)

    rows: list[dict[str, object]] = []
    evaluated = 0
    all_sectors = sorted({item["sector"] for item in constituents})
    for sector in all_sectors:
        total = sum(1 for item in constituents if item["sector"] == sector)
        series = sectors.get(sector, [])
        evaluated += len(series)
        if not series:
            rows.append(
                {
                    "sector": sector,
                    "stocks": total,
                    "evaluated": 0,
                    "above_20dma_pct": None,
                    "above_50dma_pct": None,
                    "above_200dma_pct": None,
                    "one_day_change_pt": None,
                }
            )
            continue

        def percentage_above(window: int, offset: int = 0) -> int:
            count = 0
            for closes in series:
                end = len(closes) - offset
                moving_average = sum(closes[end - window:end]) / window
                count += closes[end - 1] > moving_average
            return round(100 * count / len(series))

        current_20 = percentage_above(20)
        previous_20 = percentage_above(20, offset=1)
        rows.append(
            {
                "sector": sector,
                "stocks": total,
                "evaluated": len(series),
                "above_20dma_pct": current_20,
                "above_50dma_pct": percentage_above(50),
                "above_200dma_pct": percentage_above(200),
                "one_day_change_pt": current_20 - previous_20,
            }
        )
    return rows, as_of, evaluated


def normalize_index_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("&", "AND"))


def discover_sectoral_indices(csv_payload: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Bind the official sector list only to index symbols present in Kite's current NSE master."""
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"tradingsymbol", "name", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")

    inventory: dict[str, str] = {}
    for row in reader:
        if row.get("exchange") != "NSE" or row.get("segment") != "INDICES":
            continue
        symbol = (row.get("tradingsymbol") or "").strip()
        name = (row.get("name") or "").strip()
        if not symbol:
            continue
        for candidate in (symbol, name):
            if candidate:
                inventory.setdefault(normalize_index_name(candidate), symbol)

    targets: list[tuple[str, str, str]] = [(BASE_INDEX[0], BASE_INDEX[1], "broad_market")]
    missing: list[str] = []
    for display_name in OFFICIAL_SECTORAL_INDICES:
        candidates = (display_name, *INDEX_NAME_ALIASES.get(display_name, ()))
        symbol = next(
            (inventory[normalize_index_name(candidate)] for candidate in candidates
             if normalize_index_name(candidate) in inventory),
            None,
        )
        if symbol is None:
            missing.append(display_name)
            continue
        targets.append((display_name, f"NSE:{symbol}", "sectoral"))
    return targets, missing


def normalize_index_snapshot(
    provider_payload: dict[str, object],
    targets: list[tuple[str, str, str]],
) -> tuple[list[dict[str, object]], list[str]]:
    data = provider_payload.get("data")
    if provider_payload.get("status") != "success" or not isinstance(data, dict):
        raise ValueError("invalid_provider_response")

    rows: list[dict[str, object]] = []
    missing: list[str] = []
    for display_name, instrument, category in targets:
        quote = data.get(instrument)
        ohlc = quote.get("ohlc") if isinstance(quote, dict) else None
        values = {
            "open": ohlc.get("open") if isinstance(ohlc, dict) else None,
            "high": ohlc.get("high") if isinstance(ohlc, dict) else None,
            "low": ohlc.get("low") if isinstance(ohlc, dict) else None,
            "previous_close": ohlc.get("close") if isinstance(ohlc, dict) else None,
            "last_price": quote.get("last_price") if isinstance(quote, dict) else None,
        }
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in values.values()
        ):
            missing.append(display_name)
            continue
        rows.append(
            {
                "display_name": display_name,
                "instrument": instrument,
                "category": category,
                **values,
            }
        )
    return rows, missing


class PGTerminalHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, static_directory: str, **kwargs):
        super().__init__(*args, directory=static_directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/kite/status":
            with _SESSION_LOCK:
                connected = bool(_ACTIVE_KITE_SESSION)
                last_error = _KITE_DIAGNOSTICS["last_error"]
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "connected": connected, "last_error": last_error},
            )
            return
        if path == "/api/kite/indices/ohlc":
            self._send_index_snapshot()
            return
        if path == "/api/kite/indices/eod-summary":
            self._send_index_eod_summary()
            return
        if path == "/api/kite/market-breadth":
            self._send_market_breadth()
            return
        super().do_GET()

    def _send_index_snapshot(self) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "reason": "kite_not_connected"},
            )
            return

        try:
            targets, inventory_missing = self._current_index_targets(api_key, access_token)
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": str(error)})
            return

        query = urllib.parse.urlencode([("i", instrument) for _, instrument, _ in targets])
        request = urllib.request.Request(
            f"{OHLC_URL}?{query}",
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "application/json",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        provider_payload, reason = self._request_provider_json(request, exchange=False)
        if reason is not None:
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return

        try:
            rows, quote_missing = normalize_index_snapshot(provider_payload or {}, targets)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_provider_response"},
            )
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
                "missing": [*inventory_missing, *quote_missing],
                "official_sector_count": len(OFFICIAL_SECTORAL_INDICES),
                "available_sector_count": sum(
                    1 for row in rows if row.get("category") == "sectoral"
                ),
            },
        )

    def _send_index_eod_summary(self) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return
        try:
            self._current_index_targets(api_key, access_token)
            with _SESSION_LOCK:
                tokens = dict(_ACTIVE_DASHBOARD_INDEX_TOKENS)
            if set(tokens) != set(DASHBOARD_EOD_INDICES):
                raise ValueError("dashboard_index_not_available")

            now = datetime.now(INDIA_TIMEZONE)
            from_date = date(now.year - 1, 12, 1)
            rows: list[dict[str, object]] = []
            for index, display_name in enumerate(DASHBOARD_EOD_INDICES):
                if index:
                    time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                query = urllib.parse.urlencode(
                    {"from": from_date.isoformat(), "to": now.date().isoformat(), "continuous": "0", "oi": "0"}
                )
                request = urllib.request.Request(
                    f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=tokens[display_name])}?{query}",
                    headers={
                        "Authorization": f"token {api_key}:{access_token}",
                        "X-Kite-Version": "3",
                        "Accept": "application/json",
                        "User-Agent": "PG-terminal-local/0.1",
                    },
                    method="GET",
                )
                provider_payload, reason = self._request_provider_json(request, exchange=False)
                if reason is not None:
                    raise ValueError(reason)
                history = parse_daily_closes(
                    provider_payload or {}, today=now.date(), now_time=now.time().replace(tzinfo=None)
                )
                rows.append(calculate_index_ytd(display_name, history))
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return

        self._send_json(
            HTTPStatus.OK,
            {"ok": True, "retrieved_at": datetime.now(timezone.utc).isoformat(), "rows": rows},
        )

    def _current_index_targets(
        self, api_key: str, access_token: str
    ) -> tuple[list[tuple[str, str, str]], list[str]]:
        with _SESSION_LOCK:
            cached = list(_ACTIVE_INDEX_TARGETS)
        if cached:
            available_names = {target[0] for target in cached if target[2] == "sectoral"}
            return cached, [name for name in OFFICIAL_SECTORAL_INDICES if name not in available_names]

        request = urllib.request.Request(
            NSE_INSTRUMENTS_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        csv_payload, reason = self._request_provider_text(request, MAX_INSTRUMENT_BYTES)
        if reason is not None:
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            raise ValueError(reason)
        try:
            targets, missing = discover_sectoral_indices(csv_payload or "")
            equity_tokens = parse_equity_tokens(csv_payload or "")
            dashboard_index_tokens = parse_dashboard_index_tokens(csv_payload or "")
        except ValueError as error:
            raise ValueError(str(error)) from error
        with _SESSION_LOCK:
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_INDEX_TARGETS.extend(targets)
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.update(dashboard_index_tokens)
            _ACTIVE_EQUITY_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.update(equity_tokens)
        return targets, missing

    def _send_market_breadth(self) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
            cached_payload = _BREADTH_CACHE.get("payload")
            cached_at = _BREADTH_CACHE.get("created_at")
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return
        if (
            isinstance(cached_payload, dict)
            and isinstance(cached_at, (int, float))
            and time.monotonic() - float(cached_at) < BREADTH_CACHE_SECONDS
        ):
            self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
            return
        if not _BREADTH_BUILD_LOCK.acquire(blocking=False):
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "breadth_refresh_in_progress"},
            )
            return

        try:
            payload = self._build_market_breadth(api_key, access_token)
            with _SESSION_LOCK:
                _BREADTH_CACHE.clear()
                _BREADTH_CACHE.update({"payload": payload, "created_at": time.monotonic()})
            self._send_json(HTTPStatus.OK, {**payload, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
        finally:
            _BREADTH_BUILD_LOCK.release()

    def _build_market_breadth(self, api_key: str, access_token: str) -> dict[str, object]:
        constituent_request = urllib.request.Request(
            NIFTY500_CONSTITUENTS_URL,
            headers={
                "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
                # The public download endpoint serves its website shell to
                # unknown application user agents. Use an ordinary browser
                # identity, without cookies or access-control workarounds.
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        constituent_csv, reason = self._request_provider_text(
            constituent_request, MAX_CONSTITUENT_BYTES
        )
        if reason is not None:
            raise ValueError(f"constituent_source_{reason}")
        constituents = parse_nifty500_constituents(constituent_csv or "")
        tokens = self._current_equity_tokens(api_key, access_token)
        missing_symbols = [item["symbol"] for item in constituents if item["symbol"] not in tokens]

        now = datetime.now(INDIA_TIMEZONE)
        from_date = now.date() - timedelta(days=HISTORICAL_LOOKBACK_DAYS)
        histories: dict[str, list[tuple[date, float]]] = {}
        requested = 0
        for constituent in constituents:
            symbol = constituent["symbol"]
            token = tokens.get(symbol)
            if token is None:
                continue
            if requested:
                time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
            query = urllib.parse.urlencode(
                {"from": from_date.isoformat(), "to": now.date().isoformat(), "continuous": "0", "oi": "0"}
            )
            request = urllib.request.Request(
                f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=token)}?{query}",
                headers={
                    "Authorization": f"token {api_key}:{access_token}",
                    "X-Kite-Version": "3",
                    "Accept": "application/json",
                    "User-Agent": "PG-terminal-local/0.1",
                },
                method="GET",
            )
            provider_payload, reason = self._request_provider_json(request, exchange=False)
            requested += 1
            if reason is not None:
                raise ValueError(reason)
            histories[symbol] = parse_daily_closes(
                provider_payload or {}, today=now.date(), now_time=now.time().replace(tzinfo=None)
            )

        rows, as_of, evaluated = calculate_market_breadth(constituents, histories)
        return {
            "ok": True,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "as_of_date": as_of.isoformat(),
            "universe": "NIFTY 500",
            "universe_count": len(constituents),
            "evaluated_count": evaluated,
            "missing_count": len(constituents) - evaluated,
            "unmatched_instrument_count": len(missing_symbols),
            "historical_requests": requested,
            "rows": rows,
            "one_day_change_definition": "percentage-point change in share above 20DMA",
            "universe_source": NIFTY500_CONSTITUENTS_URL,
            "price_source": "Kite Connect historical daily candles",
        }

    def _current_equity_tokens(self, api_key: str, access_token: str) -> dict[str, str]:
        with _SESSION_LOCK:
            cached = dict(_ACTIVE_EQUITY_TOKENS)
        if cached:
            return cached
        request = urllib.request.Request(
            NSE_INSTRUMENTS_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        csv_payload, reason = self._request_provider_text(request, MAX_INSTRUMENT_BYTES)
        if reason is not None:
            raise ValueError(reason)
        tokens = parse_equity_tokens(csv_payload or "")
        with _SESSION_LOCK:
            _ACTIVE_EQUITY_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.update(tokens)
        return tokens

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        if self.path == "/api/kite/disconnect":
            payload = self._read_json_payload()
            if payload is None:
                return
            with _SESSION_LOCK:
                _ACTIVE_KITE_SESSION.clear()
                _ACTIVE_INDEX_TARGETS.clear()
                _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
                _ACTIVE_EQUITY_TOKENS.clear()
                _BREADTH_CACHE.clear()
                _KITE_DIAGNOSTICS["last_error"] = None
            print("Kite session state: disconnected", flush=True)
            self._send_json(HTTPStatus.OK, {"ok": True, "connected": False})
            return

        if self.path not in {"/api/kite/session", "/api/kite/validate"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        if self.path == "/api/kite/session":
            self._exchange_and_connect(payload)
        else:
            self._validate_existing_token(payload)

    def _exchange_and_connect(self, payload: dict[str, object]) -> None:
        api_key = payload.get("api_key")
        api_secret = payload.get("api_secret")
        request_token_input = payload.get("request_token")
        if (
            not self._valid_credential(api_key, 256)
            or not self._valid_credential(api_secret, 512)
            or not self._valid_credential(request_token_input, 4096)
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "missing_or_invalid_credentials"},
            )
            return

        request_token = extract_request_token(request_token_input)
        if not self._valid_credential(request_token, 2048):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "request_token_not_found"},
            )
            return

        form_body = urllib.parse.urlencode(
            {
                "api_key": api_key,
                "request_token": request_token,
                "checksum": build_checksum(api_key, request_token, api_secret),
            }
        ).encode("ascii")
        request = urllib.request.Request(
            TOKEN_URL,
            data=form_body,
            headers={
                "X-Kite-Version": "3",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="POST",
        )

        provider_payload, reason = self._request_provider_json(request, exchange=True)
        if reason is not None:
            self._clear_session()
            self._set_last_error(reason)
            print(f"Kite token exchange: {reason}", flush=True)
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": reason})
            return

        data = provider_payload.get("data") if isinstance(provider_payload, dict) else None
        access_token = data.get("access_token") if isinstance(data, dict) else None
        if not self._valid_credential(access_token, 2048):
            self._clear_session()
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "access_token_missing_from_provider"},
            )
            return

        profile_reason = self._profile_failure_reason(api_key, access_token)
        if profile_reason is not None:
            self._clear_session()
            self._set_last_error(profile_reason)
            print(f"Kite profile verification: {profile_reason}", flush=True)
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "reason": profile_reason},
            )
            return

        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_KITE_SESSION.update({"api_key": api_key, "access_token": access_token})
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _KITE_DIAGNOSTICS["last_error"] = None
        print("Kite session state: authenticated", flush=True)
        self._send_json(HTTPStatus.OK, {"ok": True, "connected": True})

    def _validate_existing_token(self, payload: dict[str, object]) -> None:
        api_key = payload.get("api_key")
        access_token = payload.get("access_token")
        if not self._valid_credential(api_key, 256) or not self._valid_credential(access_token, 2048):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "missing_or_invalid_credentials"},
            )
            return

        reason = self._profile_failure_reason(api_key, access_token)
        if reason is not None:
            self._clear_session()
            self._set_last_error(reason)
            print(f"Kite profile verification: {reason}", flush=True)
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": reason})
            return

        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_KITE_SESSION.update({"api_key": api_key, "access_token": access_token})
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _KITE_DIAGNOSTICS["last_error"] = None
        print("Kite session state: authenticated", flush=True)
        self._send_json(HTTPStatus.OK, {"ok": True, "connected": True})

    def _profile_failure_reason(self, api_key: str, access_token: str) -> str | None:
        request = urllib.request.Request(
            PROFILE_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "application/json",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        payload, reason = self._request_provider_json(request, exchange=False)
        if reason is not None:
            return reason
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "success"
            or not isinstance(payload.get("data"), dict)
        ):
            return "invalid_provider_response"
        return None

    def _request_provider_json(
        self,
        request: urllib.request.Request,
        *,
        exchange: bool,
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            with _PROVIDER_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    return None, "provider_response_too_large"
                payload = json.loads(body.decode("utf-8"))
                if response.status != HTTPStatus.OK or not isinstance(payload, dict):
                    return None, "invalid_provider_response"
                return payload, None
        except urllib.error.HTTPError as error:
            return None, self._classify_provider_error(error, exchange=exchange)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            return None, classify_network_error(error)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None, "invalid_provider_response"

    def _request_provider_text(
        self,
        request: urllib.request.Request,
        maximum_bytes: int,
    ) -> tuple[str | None, str | None]:
        try:
            with _PROVIDER_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
                    return None, "provider_response_too_large"
                if response.status != HTTPStatus.OK:
                    return None, "invalid_provider_response"
                return body.decode("utf-8-sig"), None
        except urllib.error.HTTPError as error:
            return None, self._classify_provider_error(error, exchange=False)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            return None, classify_network_error(error)
        except (UnicodeDecodeError, ValueError):
            return None, "invalid_provider_response"

    @staticmethod
    def _classify_provider_error(error: urllib.error.HTTPError, *, exchange: bool) -> str:
        error_type = ""
        try:
            body = error.read(MAX_RESPONSE_BYTES + 1)
            if len(body) <= MAX_RESPONSE_BYTES:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, dict):
                    error_type = str(payload.get("error_type", ""))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass

        if error_type == "TokenException":
            return "request_token_invalid_expired_or_used" if exchange else "access_token_invalid_or_expired"
        if error_type == "InputException":
            return "token_exchange_input_rejected" if exchange else "provider_input_rejected"
        if error_type == "PermissionException":
            return "profile_access_denied"
        if error.code in (401, 403):
            return "authentication_failed"
        return "provider_rejected_request"

    def _read_json_payload(self) -> dict[str, object] | None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"ok": False, "reason": "invalid_content_type"},
            )
            return None

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_request_size"},
            )
            return None

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_json"})
            return None
        return payload

    @staticmethod
    def _valid_credential(value: object, maximum_length: int) -> bool:
        return (
            isinstance(value, str)
            and 0 < len(value) <= maximum_length
            and value.strip() == value
            and all(character.isprintable() for character in value)
        )

    @staticmethod
    def _clear_session() -> None:
        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()

    @staticmethod
    def _set_last_error(reason: str) -> None:
        with _SESSION_LOCK:
            _KITE_DIAGNOSTICS["last_error"] = reason

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Never log POST request lines, bodies, or headers.
        if self.command == "GET" and not self.path.startswith("/api/"):
            super().log_message(format, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local PG-terminal server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8510, type=int)
    args = parser.parse_args()

    static_directory = str(Path(__file__).resolve().parent / "dist")

    def handler(*handler_args, **handler_kwargs):
        return PGTerminalHandler(
            *handler_args,
            static_directory=static_directory,
            **handler_kwargs,
        )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"PG-terminal available at http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
