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
import zipfile
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from eod_store import (
    CandleConflictError,
    ConfirmedFpiConflictError,
    EODStore,
    FuturesSnapshotConflictError,
    GlobalRiskConflictError,
    InstitutionalFlowConflictError,
    MacroSnapshotConflictError,
)


TOKEN_URL = "https://api.kite.trade/session/token"
PROFILE_URL = "https://api.kite.trade/user/profile"
OHLC_URL = "https://api.kite.trade/quote/ohlc"
NSE_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NSE"
NFO_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NFO"
FULL_QUOTE_URL = "https://api.kite.trade/quote"
NIFTY500_CONSTITUENTS_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_FII_DII_SOURCE = "NSE FII/FPI & DII combined-exchange cash-market report"
NSDL_FPI_MONTHLY_URL = "https://www.fpi.nsdl.co.in/web/Reports/Monthly.aspx"
NSDL_FPI_SOURCE = "NSDL custodian-confirmed daily FPI investment report"
FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_GLOBAL_SOURCE = "Federal Reserve Bank of St. Louis FRED daily series"
FRED_GLOBAL_SERIES = {
    "SP500": ("sp500", "Index", "S&P 500"),
    "VIXCLS": ("us_vix", "Index", "CBOE VIX"),
    "DEXJPUS": ("usd_jpy", "JPY per USD", "USD/JPY"),
    "DTWEXBGS": ("broad_usd", "Index Jan 2006=100", "Broad U.S. dollar index"),
    "DCOILBRENTEU": ("brent_crude", "USD per barrel", "Brent crude spot"),
}
SENTIMENT_EVIDENCE_MODEL_VERSION = "market-sentiment-evidence-v1"
REGIME_RULE_VERSION = "market-regime-candidate-v1"
REGIME_BAND_VALUES = {"constructive": 1.0, "mixed": 0.0, "defensive": -1.0}
REGIME_CLUSTER_WEIGHTS = {
    "domestic_trend": 0.25,
    "participation_and_strength": 0.20,
    "volatility_and_stress": 0.15,
    "institutional_flows": 0.15,
    "currency_and_rates": 0.10,
    "global_risk": 0.15,
}
REGIME_MINIMUM_AVAILABLE_WEIGHT = 0.60
REGIME_MINIMUM_STOCK_COVERAGE_PCT = 80.0
REGIME_VALIDATION_TRAILING_SESSIONS = 252
REGIME_VALIDATION_DEFAULT_HORIZONS = (5, 20, 60)
REGIME_EXTERNAL_HISTORY_SESSIONS = 252
REGIME_EXTERNAL_WALK_FORWARD_SESSIONS = 312
REGIME_RECOVERY_MINIMUM_RISK_SESSIONS = 5
REGIME_RECOVERY_MAXIMUM_SESSIONS = 20
REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS = 60
REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT = 1.0
REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT = 60.0
REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT = 0.5
REGIME_LONG_HORIZON_SESSIONS = 20
REGIME_SHORT_HORIZON_SESSIONS = 5
REGIME_RISK_TAIL_PERCENTILE = 10.0
REGIME_ADVERSE_DISTANCE_LEVELS_PCT = (2.0, 3.0, 5.0)
REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT = 5
REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT = 50.0
REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT = 55.0
REGIME_RECOVERY_INCREMENTAL_RETURN_PCT = 0.5
REGIME_RECOVERY_INCREMENTAL_POSITIVE_RATE_PCT = 5.0
REGIME_RECOVERY_DRAWDOWN_TOLERANCE_PCT = 2.0
REGIME_VALIDATION_EVENTS = (
    {
        "key": "india_nbfc_stress_2018",
        "label": "India NBFC liquidity stress",
        "start": date(2018, 9, 4),
        "end": date(2018, 10, 31),
    },
    {
        "key": "covid_shock_2020",
        "label": "COVID-19 market shock",
        "start": date(2020, 2, 20),
        "end": date(2020, 5, 29),
    },
    {
        "key": "global_inflation_ukraine_2022",
        "label": "Global inflation and Ukraine shock",
        "start": date(2022, 2, 24),
        "end": date(2022, 6, 17),
    },
    {
        "key": "india_election_result_2024",
        "label": "India general-election result shock",
        "start": date(2024, 6, 3),
        "end": date(2024, 6, 10),
    },
)
REGIME_LABEL_THRESHOLDS = {
    "positive_market": 0.55,
    "cautiously_positive": 0.20,
    "weak_market": -0.20,
    "high_risk_market": -0.55,
}
RBI_HOME_URL = "https://www.rbi.org.in/"
RBI_MACRO_SOURCE = "Reserve Bank of India current rates; FX source FBIL"
KITE_FUTURES_SOURCE = "Kite Connect NFO completed daily price and open interest"
NIFTY_INDICES_PUBLIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HISTORICAL_URL_TEMPLATE = "https://api.kite.trade/instruments/historical/{instrument_token}/day"
BASE_INDEX = ("Nifty 50", "NSE:NIFTY 50")
DASHBOARD_EOD_INDICES = ("Nifty 50", "Nifty Bank", "Nifty IT", "Nifty Energy", "India VIX")
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
NSDL_MAX_RESPONSE_BYTES = 512 * 1024
FRED_MAX_RESPONSE_BYTES = 512 * 1024
RBI_MAX_RESPONSE_BYTES = 1024 * 1024
MAX_HISTORICAL_RESPONSE_BYTES = 512 * 1024
MAX_INSTRUMENT_BYTES = 8 * 1024 * 1024
MAX_NFO_INSTRUMENT_BYTES = 32 * 1024 * 1024
MAX_QUOTE_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CONSTITUENT_BYTES = 128 * 1024
REQUEST_TIMEOUT_SECONDS = 10
BREADTH_CACHE_SECONDS = 15 * 60
SEASONALITY_CACHE_SECONDS = 15 * 60
HISTORICAL_LOOKBACK_DAYS = 420
SEASONALITY_LOOKBACK_YEARS = 10
SEASONALITY_HISTORY_CHUNK_DAYS = 1800
HISTORICAL_REQUEST_INTERVAL_SECONDS = 0.36
FNO_UNIVERSE_EXPECTED = 210
PRICE_STRENGTH_SERIES_SESSIONS = 126
FUTURES_PRICE_NOISE_PCT = 0.25
FUTURES_OI_NOISE_PCT = 1.0
FUTURES_MAX_COMPARISON_GAP_DAYS = 4
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")

SEASONALITY_INDICES = (
    "Nifty 50",
    "Nifty Auto",
    "Nifty Bank",
    "Nifty Chemicals",
    "Nifty Consumer Durables",
    "Nifty Energy",
    "Nifty Financial Services",
    "Nifty FMCG",
    "Nifty Healthcare",
    "Nifty IT",
    "Nifty Media",
    "Nifty Metal",
    "Nifty Oil and Gas",
    "Nifty Pharma",
    "Nifty Private Bank",
    "Nifty PSU Bank",
    "Nifty Realty",
    "Nifty MidSmall Financial Services",
    "Nifty MidSmall IT & Telecom",
)

_ACTIVE_KITE_SESSION: dict[str, str] = {}
_ACTIVE_INDEX_TARGETS: list[tuple[str, str, str]] = []
_ACTIVE_DASHBOARD_INDEX_TOKENS: dict[str, str] = {}
_ACTIVE_SEASONALITY_INDEX_TOKENS: dict[str, str] = {}
_ACTIVE_EQUITY_TOKENS: dict[str, str] = {}
_KITE_DIAGNOSTICS: dict[str, str | None] = {"last_error": None}
_BREADTH_CACHE: dict[str, object] = {}
_SEASONALITY_CACHE: dict[tuple[str, str], dict[str, object]] = {}
_MONTHLY_EQUITY_RETURNS_CACHE: dict[str, object] = {}
_MONTHLY_LEADERS_CACHE: dict[str, object] = {}
_HISTORICAL_MONTH_LEADERS_CACHE: dict[str, object] = {}
_REGIME_VALIDATION_CACHE: dict[str, object] = {}
_CROSS_INDEX_VALIDATION_CACHE: dict[str, object] = {}
_SESSION_LOCK = threading.Lock()
_BREADTH_BUILD_LOCK = threading.Lock()
_HISTORICAL_MONTH_LEADERS_LOCK = threading.Lock()
_REGIME_VALIDATION_LOCK = threading.Lock()
_CROSS_INDEX_VALIDATION_LOCK = threading.Lock()
_EOD_STORE: EODStore | None = None


def _get_eod_store() -> EODStore:
    global _EOD_STORE
    if _EOD_STORE is None:
        _EOD_STORE = EODStore(Path(__file__).resolve().parent / "data" / "pg_terminal_eod.sqlite3")
    return _EOD_STORE


def load_index_constituent_snapshot() -> dict[str, object]:
    path = Path(__file__).resolve().parent / "data" / "index_constituents.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("index_constituent_snapshot_unavailable") from error
    indices = payload.get("indices") if isinstance(payload, dict) else None
    if not isinstance(indices, dict):
        raise ValueError("index_constituent_snapshot_unavailable")
    normalized: dict[str, list[str]] = {}
    for index_name, symbols in indices.items():
        if index_name not in SEASONALITY_INDICES or not isinstance(symbols, list):
            continue
        clean_symbols = sorted(
            {
                str(symbol).strip()
                for symbol in symbols
                if isinstance(symbol, str) and str(symbol).strip()
            }
        )
        if clean_symbols:
            normalized[str(index_name)] = clean_symbols
    normalized_history: dict[str, list[dict[str, object]]] = {}
    raw_history = payload.get("history") if isinstance(payload, dict) else None
    if isinstance(raw_history, dict):
        for index_name, snapshots in raw_history.items():
            if index_name not in SEASONALITY_INDICES or not isinstance(snapshots, list):
                continue
            clean_snapshots: list[dict[str, object]] = []
            for snapshot in snapshots:
                if not isinstance(snapshot, dict) or not isinstance(snapshot.get("symbols"), list):
                    continue
                try:
                    effective_from = date.fromisoformat(str(snapshot.get("effective_from")))
                    effective_to = (
                        date.fromisoformat(str(snapshot.get("effective_to")))
                        if snapshot.get("effective_to") else None
                    )
                except ValueError:
                    continue
                if effective_to is not None and effective_to < effective_from:
                    continue
                symbols = sorted(
                    {
                        str(symbol).strip()
                        for symbol in snapshot["symbols"]
                        if isinstance(symbol, str) and str(symbol).strip()
                    }
                )
                if symbols:
                    clean_snapshots.append(
                        {
                            "effective_from": effective_from,
                            "effective_to": effective_to,
                            "symbols": symbols,
                        }
                    )
            if clean_snapshots:
                normalized_history[str(index_name)] = sorted(
                    clean_snapshots, key=lambda item: item["effective_from"]
                )
    return {
        "as_of": payload.get("as_of"),
        "source": payload.get("source"),
        "membership_type": payload.get("membership_type"),
        "indices": normalized,
        "history": normalized_history,
    }


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


def parse_near_month_stock_futures(
    csv_payload: str,
    symbols: tuple[str, ...],
    *,
    as_of: date,
) -> tuple[list[dict[str, object]], list[str]]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {
        "instrument_token", "tradingsymbol", "name", "expiry", "lot_size",
        "instrument_type", "segment", "exchange",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_nfo_instrument_master")
    requested = set(symbols)
    candidates: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in symbols}
    for row in reader:
        if (
            row.get("exchange") != "NFO"
            or row.get("segment") != "NFO-FUT"
            or row.get("instrument_type") != "FUT"
        ):
            continue
        underlying = (row.get("name") or "").strip().upper()
        if underlying not in requested:
            continue
        token = (row.get("instrument_token") or "").strip()
        tradingsymbol = (row.get("tradingsymbol") or "").strip().upper()
        try:
            expiry = date.fromisoformat((row.get("expiry") or "").strip())
            lot_size = int((row.get("lot_size") or "").strip())
        except ValueError:
            continue
        if not token.isdigit() or not tradingsymbol or expiry < as_of or lot_size <= 0:
            continue
        candidates[underlying].append(
            {
                "underlying": underlying,
                "tradingsymbol": tradingsymbol,
                "exchange": "NFO",
                "instrument_token": token,
                "expiry": expiry,
                "lot_size": lot_size,
            }
        )
    selected = [
        min(candidates[symbol], key=lambda item: (item["expiry"], item["tradingsymbol"]))
        for symbol in symbols
        if candidates[symbol]
    ]
    selected.sort(key=lambda item: item["underlying"])
    missing = [symbol for symbol in symbols if not candidates[symbol]]
    return selected, missing


def normalize_futures_eod_quotes(
    provider_payload: dict[str, object],
    contracts: list[dict[str, object]],
    *,
    now: datetime,
) -> tuple[list[dict[str, object]], list[str]]:
    local_now = now.astimezone(INDIA_TIMEZONE)
    if local_now.time().replace(tzinfo=None) < datetime_time(15, 40):
        raise ValueError("futures_eod_not_due")
    data = provider_payload.get("data")
    if provider_payload.get("status") != "success" or not isinstance(data, dict):
        raise ValueError("invalid_futures_quote_response")
    snapshots: list[dict[str, object]] = []
    missing: list[str] = []
    for contract in contracts:
        key = f"NFO:{contract['tradingsymbol']}"
        quote = data.get(key)
        if not isinstance(quote, dict):
            missing.append(str(contract["underlying"]))
            continue
        ohlc = quote.get("ohlc")
        timestamp = quote.get("timestamp") or quote.get("last_trade_time")
        raw_values = (
            ohlc.get("open") if isinstance(ohlc, dict) else None,
            ohlc.get("high") if isinstance(ohlc, dict) else None,
            ohlc.get("low") if isinstance(ohlc, dict) else None,
            quote.get("last_price"),
        )
        volume = quote.get("volume")
        open_interest = quote.get("oi")
        try:
            session_date = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).date()
        except ValueError:
            missing.append(str(contract["underlying"]))
            continue
        if (
            not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0
                for value in raw_values
            )
            or not isinstance(volume, (int, float))
            or isinstance(volume, bool)
            or int(volume) < 0
            or float(volume) != int(volume)
            or not isinstance(open_interest, (int, float))
            or isinstance(open_interest, bool)
            or int(open_interest) < 0
            or float(open_interest) != int(open_interest)
            or session_date != local_now.date()
        ):
            missing.append(str(contract["underlying"]))
            continue
        open_price, high, low, close = (float(value) for value in raw_values)
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            missing.append(str(contract["underlying"]))
            continue
        snapshots.append(
            {
                "contract_key": key,
                "date": session_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": int(volume),
                "open_interest": int(open_interest),
            }
        )
    return snapshots, missing


def parse_futures_daily_snapshot(
    provider_payload: dict[str, object],
    contract: dict[str, object],
    *,
    completed_through: date,
) -> dict[str, object] | None:
    data = provider_payload.get("data")
    candles = data.get("candles") if isinstance(data, dict) else None
    if provider_payload.get("status") != "success" or not isinstance(candles, list):
        raise ValueError("invalid_futures_history_response")
    parsed: list[dict[str, object]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 7 or not isinstance(candle[0], str):
            raise ValueError("invalid_futures_history_response")
        try:
            session_date = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).date()
        except ValueError as error:
            raise ValueError("invalid_futures_history_response") from error
        if session_date > completed_through:
            continue
        raw_prices = candle[1:5]
        volume = candle[5]
        open_interest = candle[6]
        if (
            not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0
                for value in raw_prices
            )
            or not isinstance(volume, (int, float))
            or isinstance(volume, bool)
            or float(volume) != int(volume)
            or int(volume) < 0
            or not isinstance(open_interest, (int, float))
            or isinstance(open_interest, bool)
            or float(open_interest) != int(open_interest)
            or int(open_interest) < 0
        ):
            raise ValueError("invalid_futures_history_response")
        open_price, high, low, close = (float(value) for value in raw_prices)
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise ValueError("invalid_futures_history_response")
        parsed.append(
            {
                "contract_key": f"NFO:{contract['tradingsymbol']}",
                "date": session_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": int(volume),
                "open_interest": int(open_interest),
            }
        )
    return max(parsed, key=lambda item: item["date"]) if parsed else None


def calculate_futures_oi_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "available": False,
            "reason": "Run EOD update after market close to establish the near-month futures baseline.",
        }
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["underlying"]), []).append(row)
    latest_date = max(row["date"] for row in rows)
    comparable = 0
    baseline_only = 0
    rollover_baseline = 0
    latest_rows = 0
    eligible = 0
    stale_gap_count = 0
    liquidity_excluded_count = 0
    states: list[dict[str, object]] = []
    state_counts = {
        "long_build_up": 0,
        "short_build_up": 0,
        "long_unwinding": 0,
        "short_covering": 0,
        "no_clear_signal": 0,
    }
    for underlying_rows in grouped.values():
        ordered = sorted(underlying_rows, key=lambda item: (item["date"], item["expiry"]))
        latest = ordered[-1]
        if latest["date"] != latest_date:
            continue
        latest_rows += 1
        prior = next((item for item in reversed(ordered[:-1]) if item["date"] < latest_date), None)
        if prior is None:
            baseline_only += 1
        elif prior["contract_key"] != latest["contract_key"]:
            rollover_baseline += 1
        else:
            comparable += 1
            prior_close = float(prior["close"])
            prior_oi = int(prior["open_interest"])
            current_close = float(latest["close"])
            current_oi = int(latest["open_interest"])
            gap_days = (latest["date"] - prior["date"]).days
            if gap_days > FUTURES_MAX_COMPARISON_GAP_DAYS:
                stale_gap_count += 1
                continue
            if prior_oi <= 0 or current_oi <= 0 or int(latest["volume"]) <= 0:
                liquidity_excluded_count += 1
                continue
            eligible += 1
            price_change = (current_close / prior_close - 1) * 100
            oi_change = (current_oi / prior_oi - 1) * 100
            if abs(price_change) < FUTURES_PRICE_NOISE_PCT or abs(oi_change) < FUTURES_OI_NOISE_PCT:
                state = "no_clear_signal"
            elif price_change > 0 and oi_change > 0:
                state = "long_build_up"
            elif price_change < 0 and oi_change > 0:
                state = "short_build_up"
            elif price_change < 0 and oi_change < 0:
                state = "long_unwinding"
            elif price_change > 0 and oi_change < 0:
                state = "short_covering"
            else:
                state = "no_clear_signal"
            state_counts[state] += 1
            states.append(
                {
                    "underlying": latest["underlying"],
                    "tradingsymbol": latest["tradingsymbol"],
                    "expiry": latest["expiry"].isoformat(),
                    "from_date": prior["date"].isoformat(),
                    "to_date": latest["date"].isoformat(),
                    "calendar_gap_days": gap_days,
                    "price_change_pct": round(price_change, 2),
                    "oi_change_pct": round(oi_change, 2),
                    "volume": int(latest["volume"]),
                    "open_interest": current_oi,
                    "state": state,
                }
            )
    states.sort(key=lambda item: (-abs(float(item["oi_change_pct"])), str(item["underlying"])))
    return {
        "available": True,
        "as_of_date": latest_date.isoformat(),
        "stored_underlyings": len(grouped),
        "expected_universe": FNO_UNIVERSE_EXPECTED,
        "latest_coverage": latest_rows,
        "latest_coverage_pct": round(100 * latest_rows / FNO_UNIVERSE_EXPECTED, 1),
        "latest_missing_count": max(0, FNO_UNIVERSE_EXPECTED - latest_rows),
        "comparable_count": comparable,
        "eligible_count": eligible,
        "baseline_only_count": baseline_only,
        "rollover_baseline_count": rollover_baseline,
        "stale_gap_count": stale_gap_count,
        "liquidity_excluded_count": liquidity_excluded_count,
        "classification_status": "descriptive_only" if eligible else "withheld",
        "state_counts": state_counts,
        "states": states,
        "safeguards": {
            "minimum_absolute_price_change_pct": FUTURES_PRICE_NOISE_PCT,
            "minimum_absolute_oi_change_pct": FUTURES_OI_NOISE_PCT,
            "maximum_calendar_gap_days": FUTURES_MAX_COMPARISON_GAP_DAYS,
            "requires_positive_volume_and_oi": True,
            "regime_score_enabled": False,
        },
        "definition": "Price and OI direction between two eligible stored observations of the same contract; descriptive only.",
        "reason": (
            "Same-contract price/OI quadrants are visible as descriptive evidence and do not affect the regime score."
            if eligible
            else "Contract-specific price and OI are stored; a second same-contract observation is required."
        ),
    }


def build_index_futures_confirmation(
    constituent_symbols: list[str],
    *,
    fno_constituent_count: int,
    futures_summary: dict[str, object],
    history_ready: bool,
    current_state_date: str | None,
) -> dict[str, object]:
    """Gate short research with mature history and same-session bearish F&O breadth."""
    states = futures_summary.get("states")
    states = states if isinstance(states, list) else []
    constituents = set(constituent_symbols)
    selected = [
        item
        for item in states
        if isinstance(item, dict) and str(item.get("underlying") or "") in constituents
    ]
    clear_states = [item for item in selected if item.get("state") != "no_clear_signal"]
    bearish_states = [
        item
        for item in clear_states
        if item.get("state") in {"short_build_up", "long_unwinding"}
    ]
    bullish_states = [
        item
        for item in clear_states
        if item.get("state") in {"long_build_up", "short_covering"}
    ]
    denominator = max(1, int(fno_constituent_count))
    coverage_pct = 100 * len(selected) / denominator
    bearish_share_pct = (
        100 * len(bearish_states) / len(clear_states) if clear_states else 0.0
    )
    same_session = bool(
        current_state_date
        and futures_summary.get("as_of_date") == current_state_date
    )
    current_confirmation_ready = bool(
        same_session
        and len(clear_states) >= REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT
        and coverage_pct >= REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT
    )
    bearish_confirmation = bool(
        current_confirmation_ready
        and bearish_share_pct >= REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT
    )
    if not history_ready:
        status = "history_accumulating"
    elif not current_confirmation_ready:
        status = "current_confirmation_unavailable"
    elif bearish_confirmation:
        status = "bearish_confirmation_present"
    else:
        status = "bearish_confirmation_absent"
    return {
        "history_ready": bool(history_ready),
        "current_confirmation_ready": current_confirmation_ready,
        "bearish_confirmation": bearish_confirmation,
        "short_gate_passed": bool(history_ready and bearish_confirmation),
        "status": status,
        "as_of_date": futures_summary.get("as_of_date"),
        "same_session_as_current_state": same_session,
        "eligible_constituent_states": len(selected),
        "clear_directional_states": len(clear_states),
        "bearish_states": len(bearish_states),
        "bullish_states": len(bullish_states),
        "coverage_pct": round(coverage_pct, 1),
        "bearish_share_pct": round(bearish_share_pct, 1),
        "contract": {
            "minimum_history_sessions": REGIME_EXTERNAL_HISTORY_SESSIONS,
            "minimum_clear_constituent_states": REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT,
            "minimum_constituent_coverage_pct": REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT,
            "minimum_bearish_share_pct": REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT,
            "bearish_states": ["short_build_up", "long_unwinding"],
            "status": "confirmation_gate_not_trading_signal",
        },
    }


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


def parse_seasonality_index_tokens(csv_payload: str) -> dict[str, str]:
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
    for display_name in SEASONALITY_INDICES:
        candidates = (display_name, *INDEX_NAME_ALIASES.get(display_name, ()))
        token = next(
            (
                inventory[normalize_index_name(candidate)]
                for candidate in candidates
                if normalize_index_name(candidate) in inventory
            ),
            None,
        )
        if token is not None:
            result[display_name] = token
    if "Nifty 50" not in result:
        raise ValueError("invalid_instrument_master")
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


def parse_daily_candles(
    provider_payload: dict[str, object],
    *,
    today: date,
    now_time: datetime_time,
) -> list[dict[str, object]]:
    data = provider_payload.get("data")
    candles = data.get("candles") if isinstance(data, dict) else None
    if provider_payload.get("status") != "success" or not isinstance(candles, list):
        raise ValueError("invalid_provider_response")
    allow_today = now_time >= datetime_time(15, 40)
    parsed: list[dict[str, object]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 5 or not isinstance(candle[0], str):
            raise ValueError("invalid_provider_response")
        try:
            candle_date = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).date()
        except ValueError as error:
            raise ValueError("invalid_provider_response") from error
        values = candle[1:5]
        numeric_values = all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in values
        )
        if not numeric_values:
            raise ValueError("invalid_provider_response")
        if all(float(value) == 0 for value in values):
            continue
        if not all(float(value) > 0 for value in values):
            raise ValueError("invalid_provider_response")
        open_price, high, low, close = (float(value) for value in values)
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            raise ValueError("invalid_provider_response")
        if candle_date < today or allow_today:
            parsed.append(
                {
                    "date": candle_date,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                }
            )
    parsed.sort(key=lambda item: item["date"])
    return parsed


def historical_date_ranges(
    start: date,
    end: date,
    *,
    chunk_days: int = SEASONALITY_HISTORY_CHUNK_DAYS,
) -> list[tuple[date, date]]:
    if chunk_days < 1 or start > end:
        raise ValueError("invalid_history_range")
    ranges: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges


def historical_lookback_start(as_of: date, *, years: int = SEASONALITY_LOOKBACK_YEARS) -> date:
    if years < 1:
        raise ValueError("invalid_history_range")
    try:
        return as_of.replace(year=as_of.year - years)
    except ValueError:
        return as_of.replace(year=as_of.year - years, day=28)


def incremental_history_ranges(
    history_start: date,
    end: date,
    last_stored: date | None,
    *,
    chunk_days: int = SEASONALITY_HISTORY_CHUNK_DAYS,
) -> list[tuple[date, date]]:
    start = max(history_start, last_stored + timedelta(days=1)) if last_stored else history_start
    if start > end:
        return []
    return historical_date_ranges(start, end, chunk_days=chunk_days)


def completed_history_date(now: datetime) -> date:
    """Return the latest date that may contain a completed daily candle."""
    local_now = now.astimezone(INDIA_TIMEZONE)
    if local_now.time().replace(tzinfo=None) < datetime_time(15, 40):
        return local_now.date() - timedelta(days=1)
    return local_now.date()


def is_complete_seasonality_payload(payload: object) -> bool:
    """Keep ranking-only cache entries out of full seasonality responses."""
    return (
        isinstance(payload, dict)
        and payload.get("ok") is True
        and isinstance(payload.get("month_rows"), list)
        and isinstance(payload.get("weekday_rows"), list)
        and isinstance(payload.get("validation"), dict)
    )


def _seasonality_summary(values: list[tuple[float, float]]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "average_return_pct": None,
            "average_range_pct": None,
            "highest_return_pct": None,
            "lowest_return_pct": None,
        }
    returns = [item[0] for item in values]
    ranges = [item[1] for item in values]
    return {
        "count": len(values),
        "average_return_pct": round(sum(returns) / len(returns), 2),
        "average_range_pct": round(sum(ranges) / len(ranges), 2),
        "highest_return_pct": round(max(returns), 2),
        "lowest_return_pct": round(min(returns), 2),
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sample_variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    average = sum(values) / len(values)
    return sum((value - average) ** 2 for value in values) / (len(values) - 1)


def _percentile(values: list[float], percentile: float) -> float:
    if not values or not 0 <= percentile <= 100:
        raise ValueError("invalid_percentile_input")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_regime_risk_profile(
    observations: list[dict[str, object]],
    *,
    horizon_sessions: int,
    orientation: str,
) -> dict[str, object]:
    """Summarize outcome tails and entry-relative adverse distance without sizing advice."""
    if horizon_sessions <= 0 or orientation not in {"long", "short"}:
        raise ValueError("invalid_regime_risk_profile_contract")
    key = str(horizon_sessions)
    return_key = "forward_returns_pct"
    adverse_key = (
        "forward_long_adverse_excursions_pct"
        if orientation == "long"
        else "forward_short_adverse_excursions_pct"
    )
    position_returns: list[float] = []
    adverse_distances: list[float] = []
    for observation in observations:
        raw_returns = observation.get(return_key)
        raw_adverse = observation.get(adverse_key)
        if not isinstance(raw_returns, dict) or not isinstance(raw_adverse, dict):
            continue
        outcome = raw_returns.get(key)
        adverse = raw_adverse.get(key)
        if not isinstance(outcome, (int, float)) or not isinstance(adverse, (int, float)):
            continue
        position_returns.append(float(outcome) if orientation == "long" else -float(outcome))
        adverse_distances.append(float(adverse))
    if not position_returns:
        return {
            "available": False,
            "orientation": orientation,
            "horizon_sessions": horizon_sessions,
            "observations": 0,
        }
    breach_rates = {
        f"{distance:g}": round(
            100 * sum(value >= distance for value in adverse_distances) / len(adverse_distances),
            1,
        )
        for distance in REGIME_ADVERSE_DISTANCE_LEVELS_PCT
    }
    return {
        "available": True,
        "orientation": orientation,
        "horizon_sessions": horizon_sessions,
        "observations": len(position_returns),
        "tail_percentile": REGIME_RISK_TAIL_PERCENTILE,
        "tail_position_return_pct": round(
            _percentile(position_returns, REGIME_RISK_TAIL_PERCENTILE), 2
        ),
        "median_position_return_pct": round(median(position_returns), 2),
        "worst_position_return_pct": round(min(position_returns), 2),
        "median_adverse_excursion_pct": round(median(adverse_distances), 2),
        "tail_adverse_excursion_pct": round(
            _percentile(adverse_distances, 100 - REGIME_RISK_TAIL_PERCENTILE), 2
        ),
        "worst_adverse_excursion_pct": round(max(adverse_distances), 2),
        "adverse_distance_breach_rates_pct": breach_rates,
        "distance_levels_pct": list(REGIME_ADVERSE_DISTANCE_LEVELS_PCT),
        "status": "historical_risk_evidence_not_stop_recommendation",
    }


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 200
    epsilon = 3e-14
    minimum = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < minimum:
        d = minimum
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        twice = 2 * iteration
        coefficient = iteration * (b - iteration) * x / ((qam + twice) * (a + twice))
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        result *= d * c
        coefficient = -(a + iteration) * (qab + iteration) * x / ((a + twice) * (qap + twice))
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return result


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _welch_test(first: list[float], second: list[float]) -> tuple[float | None, float | None]:
    first_variance = _sample_variance(first)
    second_variance = _sample_variance(second)
    if first_variance is None or second_variance is None:
        return None, None
    first_term = first_variance / len(first)
    second_term = second_variance / len(second)
    denominator = first_term + second_term
    if denominator <= 0:
        return None, None
    t_statistic = ((_mean(first) or 0.0) - (_mean(second) or 0.0)) / math.sqrt(denominator)
    degrees_of_freedom_denominator = (
        (first_term * first_term) / (len(first) - 1)
        + (second_term * second_term) / (len(second) - 1)
    )
    if degrees_of_freedom_denominator <= 0:
        return None, None
    degrees_of_freedom = denominator * denominator / degrees_of_freedom_denominator
    probability = _regularized_incomplete_beta(
        degrees_of_freedom / 2.0,
        0.5,
        degrees_of_freedom / (degrees_of_freedom + t_statistic * t_statistic),
    )
    return t_statistic, max(0.0, min(1.0, probability))


def _benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    valid = sorted(
        ((value, index) for index, value in enumerate(p_values) if value is not None),
        key=lambda item: item[0],
    )
    adjusted: list[float | None] = [None] * len(p_values)
    running = 1.0
    total = len(valid)
    for rank in range(total, 0, -1):
        value, index = valid[rank - 1]
        running = min(running, value * total / rank)
        adjusted[index] = max(0.0, min(1.0, running))
    return adjusted


def _turn_of_month_analysis(candles: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(candles, key=lambda item: item["date"])
    daily: list[dict[str, object]] = []
    for previous, current in zip(ordered, ordered[1:]):
        daily.append(
            {
                "date": current["date"],
                "return_pct": ((float(current["close"]) / float(previous["close"])) - 1) * 100,
                "in_window": False,
            }
        )
    month_groups: list[list[dict[str, object]]] = []
    for row in daily:
        key = (row["date"].year, row["date"].month)
        if not month_groups or (month_groups[-1][0]["date"].year, month_groups[-1][0]["date"].month) != key:
            month_groups.append([])
        month_groups[-1].append(row)
    for index, group in enumerate(month_groups):
        for row in group[-3:]:
            row["in_window"] = True
        if index + 1 < len(month_groups):
            for row in month_groups[index + 1][:3]:
                row["in_window"] = True

    turn_values = [float(row["return_pct"]) for row in daily if row["in_window"]]
    rest_values = [float(row["return_pct"]) for row in daily if not row["in_window"]]

    def summary(label: str, values: list[float]) -> dict[str, object]:
        ordered_values = sorted(values)
        middle = len(ordered_values) // 2
        median = None
        if ordered_values:
            median = (
                ordered_values[middle]
                if len(ordered_values) % 2
                else (ordered_values[middle - 1] + ordered_values[middle]) / 2
            )
        return {
            "window": label,
            "count": len(values),
            "average_return_pct": round(_mean(values), 2) if values else None,
            "median_return_pct": round(median, 2) if median is not None else None,
            "positive_sessions_pct": round(sum(value > 0 for value in values) / len(values) * 100, 2) if values else None,
        }

    t_statistic, p_value = _welch_test(turn_values, rest_values)
    turn_mean = _mean(turn_values)
    rest_mean = _mean(rest_values)
    return {
        "rows": [summary("Turn of month", turn_values), summary("Rest of month", rest_values)],
        "edge_pct": round(turn_mean - rest_mean, 2) if turn_mean is not None and rest_mean is not None else None,
        "t_statistic": round(t_statistic, 3) if t_statistic is not None else None,
        "p_value": round(p_value, 4) if p_value is not None else None,
    }


def calculate_seasonality_validation(
    candles: list[dict[str, object]],
    *,
    today: date,
) -> dict[str, object]:
    ordered = sorted(candles, key=lambda item: item["date"])
    monthly_buckets: dict[tuple[int, int], list[dict[str, object]]] = {}
    for candle in ordered:
        candle_date = candle["date"]
        monthly_buckets.setdefault((candle_date.year, candle_date.month), []).append(candle)
    completed = [
        (key, rows)
        for key, rows in sorted(monthly_buckets.items())
        if key != (today.year, today.month)
    ]
    monthly_returns: list[dict[str, object]] = []
    previous_close: float | None = None
    for (_year, month), rows in completed:
        month_close = float(rows[-1]["close"])
        if previous_close is not None:
            monthly_returns.append(
                {
                    "date": rows[-1]["date"],
                    "month": month,
                    "return_pct": ((month_close / previous_close) - 1) * 100,
                }
            )
        previous_close = month_close
    if len(monthly_returns) < 4:
        raise ValueError("no_completed_historical_data")

    split_index = len(monthly_returns) // 2
    train = monthly_returns[:split_index]
    test = monthly_returns[split_index:]
    split_date = test[0]["date"].replace(day=1)
    month_names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    intermediate: list[dict[str, object]] = []
    train_p_values: list[float | None] = []
    for month in range(1, 13):
        train_values = [float(row["return_pct"]) for row in train if row["month"] == month]
        train_others = [float(row["return_pct"]) for row in train if row["month"] != month]
        test_values = [float(row["return_pct"]) for row in test if row["month"] == month]
        test_others = [float(row["return_pct"]) for row in test if row["month"] != month]
        _train_t, train_p = _welch_test(train_values, train_others)
        _test_t, test_p = _welch_test(test_values, test_others)
        train_excess = (
            (_mean(train_values) or 0.0) - (_mean(train_others) or 0.0)
            if train_values and train_others else None
        )
        test_excess = (
            (_mean(test_values) or 0.0) - (_mean(test_others) or 0.0)
            if test_values and test_others else None
        )
        train_p_values.append(train_p)
        intermediate.append(
            {
                "period": month_names[month - 1],
                "train_count": len(train_values),
                "train_excess_pct": train_excess,
                "train_p_value": train_p,
                "test_count": len(test_values),
                "test_excess_pct": test_excess,
                "test_p_value": test_p,
                "same_direction": (
                    train_excess is not None and test_excess is not None
                    and train_excess != 0 and test_excess != 0
                    and (train_excess > 0) == (test_excess > 0)
                ),
            }
        )
    train_q_values = _benjamini_hochberg(train_p_values)
    held_out_rows: list[dict[str, object]] = []
    for row, q_value in zip(intermediate, train_q_values):
        train_significant = q_value is not None and q_value < 0.10
        survived = (
            train_significant
            and row["same_direction"]
            and row["test_p_value"] is not None
            and row["test_p_value"] < 0.05
        )
        held_out_rows.append(
            {
                "period": row["period"],
                "train_count": row["train_count"],
                "train_excess_pct": round(row["train_excess_pct"], 2) if row["train_excess_pct"] is not None else None,
                "train_significant": train_significant,
                "test_count": row["test_count"],
                "test_excess_pct": round(row["test_excess_pct"], 2) if row["test_excess_pct"] is not None else None,
                "same_direction": row["same_direction"],
                "survived": survived,
            }
        )

    turn = _turn_of_month_analysis(ordered)
    turn_held_out_rows: list[dict[str, object]] = []
    for label, subset in (
        ("Train", [row for row in ordered if row["date"] < split_date]),
        ("Test", [row for row in ordered if row["date"] >= split_date]),
    ):
        result = _turn_of_month_analysis(subset)
        p_value = result["p_value"]
        turn_held_out_rows.append(
            {
                "period": label,
                "from_date": subset[0]["date"].isoformat() if subset else None,
                "to_date": subset[-1]["date"].isoformat() if subset else None,
                "edge_pct": result["edge_pct"],
                "p_value": p_value,
                "significant": p_value is not None and p_value < 0.05,
            }
        )
    return {
        "turn_rows": turn["rows"],
        "turn_edge_pct": turn["edge_pct"],
        "turn_t_statistic": turn["t_statistic"],
        "turn_p_value": turn["p_value"],
        "holdout_split_date": split_date.isoformat(),
        "held_out_rows": held_out_rows,
        "held_out_summary": {
            "same_direction": sum(bool(row["same_direction"]) for row in held_out_rows),
            "train_significant": sum(bool(row["train_significant"]) for row in held_out_rows),
            "survived": sum(bool(row["survived"]) for row in held_out_rows),
        },
        "turn_held_out_rows": turn_held_out_rows,
    }


def calculate_seasonality(
    candles: list[dict[str, object]],
    *,
    today: date,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if len(candles) < 2:
        raise ValueError("no_completed_historical_data")
    ordered = sorted(candles, key=lambda item: item["date"])
    weekday_values: dict[int, list[tuple[float, float]]] = {index: [] for index in range(5)}
    for previous, current in zip(ordered, ordered[1:]):
        previous_close = float(previous["close"])
        low = float(current["low"])
        daily_return = ((float(current["close"]) / previous_close) - 1) * 100
        daily_range = ((float(current["high"]) - low) / low) * 100
        weekday = current["date"].weekday()
        if weekday in weekday_values:
            weekday_values[weekday].append((daily_return, daily_range))

    monthly_buckets: dict[tuple[int, int], list[dict[str, object]]] = {}
    for candle in ordered:
        candle_date = candle["date"]
        monthly_buckets.setdefault((candle_date.year, candle_date.month), []).append(candle)
    completed_months = [
        (key, rows)
        for key, rows in sorted(monthly_buckets.items())
        if key != (today.year, today.month)
    ]
    month_values: dict[int, list[tuple[float, float]]] = {month: [] for month in range(1, 13)}
    previous_month_close: float | None = None
    for (year, month), rows in completed_months:
        month_close = float(rows[-1]["close"])
        month_low = min(float(row["low"]) for row in rows)
        month_high = max(float(row["high"]) for row in rows)
        if previous_month_close is not None:
            monthly_return = ((month_close / previous_month_close) - 1) * 100
            monthly_range = ((month_high - month_low) / month_low) * 100
            month_values[month].append((monthly_return, monthly_range))
        previous_month_close = month_close

    month_names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    weekday_names = ("Mon", "Tue", "Wed", "Thu", "Fri")
    month_rows = [
        {"period": month_names[month - 1], **_seasonality_summary(month_values[month])}
        for month in range(1, 13)
    ]
    weekday_rows = [
        {"period": weekday_names[weekday], **_seasonality_summary(weekday_values[weekday])}
        for weekday in range(5)
    ]
    return month_rows, weekday_rows


def calculate_month_to_date_returns(
    histories: dict[str, list[tuple[date, float]]],
    *,
    as_of: date,
) -> dict[str, float]:
    month_start = date(as_of.year, as_of.month, 1)
    returns: dict[str, float] = {}
    for instrument, history in histories.items():
        completed = sorted((row for row in history if row[0] <= as_of), key=lambda row: row[0])
        prior_rows = [row for row in completed if row[0] < month_start]
        current_rows = [row for row in completed if month_start <= row[0] <= as_of]
        if not prior_rows or not current_rows or current_rows[-1][0] != as_of:
            continue
        prior_close = float(prior_rows[-1][1])
        latest_close = float(current_rows[-1][1])
        if prior_close <= 0 or not math.isfinite(prior_close) or not math.isfinite(latest_close):
            continue
        returns[instrument] = round(((latest_close / prior_close) - 1) * 100, 2)
    return returns


def rank_historical_month_averages(
    averages: dict[str, tuple[float, int]],
) -> dict[str, object]:
    eligible: list[tuple[str, float, int]] = []
    for instrument, value in averages.items():
        average_return, observations = value
        average_return = float(average_return)
        if observations < 1 or not math.isfinite(average_return):
            continue
        eligible.append((instrument, average_return, observations))
    if not eligible:
        raise ValueError("historical_month_data_unavailable")
    leader = max(eligible, key=lambda item: (item[1], item[0]))
    lagger = min(eligible, key=lambda item: (item[1], item[0]))
    return {
        "leader": {
            "instrument": leader[0],
            "average_return_pct": round(leader[1], 2),
            "observations": leader[2],
        },
        "lagger": {
            "instrument": lagger[0],
            "average_return_pct": round(lagger[1], 2),
            "observations": lagger[2],
        },
        "evaluated": len(eligible),
    }


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


def parse_institutional_flows(payload: object, *, today: date) -> list[dict[str, object]]:
    """Validate NSE's combined-exchange provisional FII/FPI and DII cash rows."""
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("invalid_institutional_flow_response")

    def number(value: object) -> float:
        if isinstance(value, bool):
            raise ValueError("invalid_institutional_flow_response")
        try:
            parsed = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError) as error:
            raise ValueError("invalid_institutional_flow_response") from error
        if not math.isfinite(parsed):
            raise ValueError("invalid_institutional_flow_response")
        return parsed

    rows: list[dict[str, object]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("invalid_institutional_flow_response")
        category = str(raw.get("category", "")).strip()
        try:
            session_date = datetime.strptime(str(raw.get("date", "")).strip(), "%d-%b-%Y").date()
        except ValueError as error:
            raise ValueError("invalid_institutional_flow_response") from error
        buy = number(raw.get("buyValue"))
        sell = number(raw.get("sellValue"))
        net = number(raw.get("netValue"))
        if (
            category not in {"FII/FPI", "DII"}
            or session_date > today
            or buy < 0
            or sell < 0
            or abs((buy - sell) - net) > 0.11
        ):
            raise ValueError("invalid_institutional_flow_response")
        rows.append(
            {
                "date": session_date,
                "category": category,
                "buy_crore": buy,
                "sell_crore": sell,
                "net_crore": net,
            }
        )
    if {row["category"] for row in rows} != {"FII/FPI", "DII"} or len({row["date"] for row in rows}) != 1:
        raise ValueError("invalid_institutional_flow_response")
    return sorted(rows, key=lambda row: str(row["category"]))


def calculate_institutional_flow_summary(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    """Summarise append-only provisional cash flows without inventing a signal threshold."""
    sessions: dict[date, dict[str, dict[str, object]]] = {}
    for row in rows:
        session_date = row.get("date")
        category = row.get("category")
        if isinstance(session_date, date) and category in {"FII/FPI", "DII"}:
            sessions.setdefault(session_date, {})[str(category)] = row
    complete_dates = sorted(
        session_date
        for session_date, categories in sessions.items()
        if set(categories) == {"FII/FPI", "DII"}
    )
    if not complete_dates:
        return {
            "available": False,
            "publication_status": "provisional",
            "reason": "Run EOD update to retrieve the official NSE institutional-flow report.",
        }

    latest_date = complete_dates[-1]
    latest = sessions[latest_date]

    def category_values(category: str) -> dict[str, float]:
        row = latest[category]
        return {
            "buy_crore": round(float(row["buy_crore"]), 2),
            "sell_crore": round(float(row["sell_crore"]), 2),
            "net_crore": round(float(row["net_crore"]), 2),
        }

    def cumulative(window: int) -> dict[str, float] | None:
        if len(complete_dates) < window:
            return None
        selected = complete_dates[-window:]
        fii = sum(float(sessions[item]["FII/FPI"]["net_crore"]) for item in selected)
        dii = sum(float(sessions[item]["DII"]["net_crore"]) for item in selected)
        return {
            "fii_fpi_net_crore": round(fii, 2),
            "dii_net_crore": round(dii, 2),
            "combined_net_crore": round(fii + dii, 2),
        }

    latest_fii = category_values("FII/FPI")
    latest_dii = category_values("DII")
    series = [
        {
            "date": session_date.isoformat(),
            "fii_fpi_net_crore": round(float(sessions[session_date]["FII/FPI"]["net_crore"]), 2),
            "dii_net_crore": round(float(sessions[session_date]["DII"]["net_crore"]), 2),
            "combined_net_crore": round(
                float(sessions[session_date]["FII/FPI"]["net_crore"])
                + float(sessions[session_date]["DII"]["net_crore"]),
                2,
            ),
        }
        for session_date in complete_dates
    ]
    return {
        "available": True,
        "as_of_date": latest_date.isoformat(),
        "publication_status": "provisional",
        "market_scope": "NSE, BSE and MSEI combined cash market",
        "source": NSE_FII_DII_SOURCE,
        "session_count": len(complete_dates),
        "latest": {
            "fii_fpi": latest_fii,
            "dii": latest_dii,
            "combined_net_crore": round(latest_fii["net_crore"] + latest_dii["net_crore"], 2),
        },
        "five_session": cumulative(5),
        "twenty_session": cumulative(20),
        "series": series,
        "band": "unranked",
        "reason": "Official provisional cash flows are visible; directional thresholds are not yet validated.",
        "confirmed_reconciliation": "not_loaded",
    }


def parse_nsdl_confirmed_fpi(html_payload: str, *, today: date) -> list[dict[str, object]]:
    """Extract confirmed equity investment routes from NSDL's current-month report."""
    if not isinstance(html_payload, str) or not html_payload.strip():
        raise ValueError("invalid_confirmed_fpi_response")
    investment_start = html_payload.find("Daily Trends in FPI Investments")
    derivative_start = html_payload.find("Daily Trends in FPI Derivative Trades")
    if investment_start < 0 or derivative_start <= investment_start:
        raise ValueError("invalid_confirmed_fpi_response")
    section = html_payload[investment_start:derivative_start]

    import html as html_module

    def cell_text(value: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html_module.unescape(without_tags).replace("\xa0", " ")).strip()

    def number(value: str) -> float:
        cleaned = value.replace(",", "").strip()
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        if negative:
            cleaned = cleaned[1:-1].strip()
        try:
            parsed = float(cleaned)
        except ValueError as error:
            raise ValueError("invalid_confirmed_fpi_response") from error
        if not math.isfinite(parsed):
            raise ValueError("invalid_confirmed_fpi_response")
        return -parsed if negative else parsed

    routes = {"Stock Exchange", "Primary market & others", "Sub-total"}
    parsed_rows: list[dict[str, object]] = []
    current_date: date | None = None
    current_asset = ""
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, flags=re.IGNORECASE | re.DOTALL):
        cells = [
            cell_text(cell)
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", raw_row, flags=re.IGNORECASE | re.DOTALL)
        ]
        if not cells:
            continue
        try:
            row_date = datetime.strptime(cells[0], "%d-%b-%Y").date()
        except ValueError:
            row_date = None
        if row_date is not None:
            if len(cells) < 6 or row_date > today:
                raise ValueError("invalid_confirmed_fpi_response")
            current_date = row_date
            current_asset = cells[1]
            route = cells[2]
            values = cells[3:6]
        elif cells[0] in routes:
            route = cells[0]
            values = cells[1:4]
        else:
            if len(cells) < 5:
                continue
            current_asset = cells[0]
            route = cells[1]
            values = cells[2:5]
        if current_date is None or current_asset != "Equity" or route not in routes:
            continue
        if len(values) != 3:
            raise ValueError("invalid_confirmed_fpi_response")
        purchases, sales, net = (number(value) for value in values)
        if purchases < 0 or sales < 0 or abs((purchases - sales) - net) > 0.11:
            raise ValueError("invalid_confirmed_fpi_response")
        parsed_rows.append(
            {
                "date": current_date,
                "asset_class": "Equity",
                "investment_route": route,
                "gross_purchases_crore": purchases,
                "gross_sales_crore": sales,
                "net_investment_crore": net,
            }
        )
    routes_by_date: dict[date, set[str]] = {}
    for row in parsed_rows:
        routes_by_date.setdefault(row["date"], set()).add(str(row["investment_route"]))
    if not parsed_rows or any(found != routes for found in routes_by_date.values()):
        raise ValueError("invalid_confirmed_fpi_response")
    return parsed_rows


def calculate_confirmed_fpi_summary(
    rows: list[dict[str, object]], *, today: date | None = None
) -> dict[str, object]:
    """Summarise custodian-confirmed FPI equity data without blending NSE provisional flows."""
    sessions: dict[date, dict[str, dict[str, object]]] = {}
    required_routes = {"Stock Exchange", "Primary market & others", "Sub-total"}
    for row in rows:
        reporting_date = row.get("date")
        route = row.get("investment_route")
        if isinstance(reporting_date, date) and route in required_routes:
            sessions.setdefault(reporting_date, {})[str(route)] = row
    complete_dates = sorted(
        reporting_date
        for reporting_date, route_rows in sessions.items()
        if set(route_rows) == required_routes
    )
    if not complete_dates:
        return {
            "available": False,
            "publication_status": "confirmed_custodian",
            "reason": "Run EOD update to retrieve the official NSDL custodian-confirmed FPI report.",
        }

    latest_date = complete_dates[-1]
    latest_routes = sessions[latest_date]

    def values(route: str) -> dict[str, float]:
        row = latest_routes[route]
        return {
            "gross_purchases_crore": round(float(row["gross_purchases_crore"]), 2),
            "gross_sales_crore": round(float(row["gross_sales_crore"]), 2),
            "net_investment_crore": round(float(row["net_investment_crore"]), 2),
        }

    def cumulative(window: int) -> float | None:
        if len(complete_dates) < window:
            return None
        return round(
            sum(
                float(sessions[item]["Sub-total"]["net_investment_crore"])
                for item in complete_dates[-window:]
            ),
            2,
        )

    reference_date = today or datetime.now(INDIA_TIMEZONE).date()
    return {
        "available": True,
        "as_of_date": latest_date.isoformat(),
        "publication_status": "confirmed_custodian",
        "asset_class": "Equity",
        "source": NSDL_FPI_SOURCE,
        "session_count": len(complete_dates),
        "reporting_lag_calendar_days": max(0, (reference_date - latest_date).days),
        "latest": {
            "stock_exchange": values("Stock Exchange"),
            "primary_market_and_others": values("Primary market & others"),
            "subtotal": values("Sub-total"),
        },
        "five_session_net_crore": cumulative(5),
        "twenty_session_net_crore": cumulative(20),
        "series": [
            {
                "date": reporting_date.isoformat(),
                "net_investment_crore": round(
                    float(sessions[reporting_date]["Sub-total"]["net_investment_crore"]), 2
                ),
            }
            for reporting_date in complete_dates
        ],
        "comparison_note": (
            "Custodian-confirmed FPI investment is shown separately from NSE provisional "
            "FII/FPI cash activity because publication timing and coverage differ."
        ),
    }


def parse_rbi_macro_snapshot(html_payload: str) -> list[dict[str, object]]:
    """Extract the current official FBIL FX references and approximate 10-year G-Sec."""
    if not isinstance(html_payload, str) or not html_payload.strip():
        raise ValueError("invalid_rbi_macro_response")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_payload, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    import html as html_module

    text = html_module.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()

    fx_date_match = re.search(
        r"As\s+at\s+1\.00\s*pm\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    gsec_heading = re.search(r"Government\s+Securities\s+Market", text, flags=re.IGNORECASE)
    preceding_dates = (
        re.findall(
            r"as\s+on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text[: gsec_heading.start()] if gsec_heading else "",
            flags=re.IGNORECASE,
        )
        if gsec_heading
        else []
    )
    following_dates = (
        re.findall(
            r"as\s+on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text[gsec_heading.end() : gsec_heading.end() + 1000] if gsec_heading else "",
            flags=re.IGNORECASE,
        )
        if gsec_heading
        else []
    )
    if (
        fx_date_match is None
        or not (preceding_dates or following_dates)
        or re.search(r"Source\s*:\s*FBIL", text, flags=re.IGNORECASE) is None
    ):
        raise ValueError("invalid_rbi_macro_response")
    try:
        fx_date = datetime.strptime(fx_date_match.group(1), "%B %d, %Y").date()
        gsec_date_text = preceding_dates[-1] if preceding_dates else following_dates[0]
        gsec_date = datetime.strptime(gsec_date_text, "%B %d, %Y").date()
    except ValueError as error:
        raise ValueError("invalid_rbi_macro_response") from error

    fx_specs = (
        ("usd_inr", r"INR\s*/\s*1\s*USD", "INR per USD", "USD/INR"),
        ("gbp_inr", r"INR\s*/\s*1\s*GBP", "INR per GBP", "GBP/INR"),
        ("eur_inr", r"INR\s*/\s*1\s*EUR", "INR per EUR", "EUR/INR"),
        ("jpy_100_inr", r"INR\s*/\s*100\s*JPY", "INR per 100 JPY", "JPY/INR (100 JPY)"),
    )
    rows: list[dict[str, object]] = []
    for metric_key, label_pattern, unit, instrument_label in fx_specs:
        match = re.search(rf"{label_pattern}\s*:?\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
        if match is None:
            raise ValueError("invalid_rbi_macro_response")
        value = float(match.group(1))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid_rbi_macro_response")
        rows.append(
            {
                "date": fx_date,
                "metric_key": metric_key,
                "value": value,
                "unit": unit,
                "instrument_label": instrument_label,
            }
        )

    gsec_candidates: list[tuple[int, float, str]] = []
    for match in re.finditer(
        r"((?:[0-9]+(?:\.[0-9]+)?)%\s+GS\s+(\d{4}))\s*:?\s*([0-9]+(?:\.[0-9]+)?)%",
        text,
        flags=re.IGNORECASE,
    ):
        label, maturity_text, yield_text = match.groups()
        maturity = int(maturity_text)
        yield_value = float(yield_text)
        if maturity >= gsec_date.year and 0 < yield_value < 25:
            gsec_candidates.append((maturity, yield_value, re.sub(r"\s+", " ", label).upper()))
    if not gsec_candidates:
        raise ValueError("invalid_rbi_macro_response")
    maturity, yield_value, label = min(
        gsec_candidates,
        key=lambda item: (abs(item[0] - (gsec_date.year + 10)), item[0]),
    )
    rows.append(
        {
            "date": gsec_date,
            "metric_key": "india_10y_gsec_yield",
            "value": yield_value,
            "unit": "percent yield",
            "instrument_label": f"{label} (approx. 10-year; matures {maturity})",
        }
    )
    return rows


def calculate_macro_context_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    metric_labels = {
        "usd_inr": "USD/INR",
        "gbp_inr": "GBP/INR",
        "eur_inr": "EUR/INR",
        "jpy_100_inr": "JPY/INR (100 JPY)",
        "india_10y_gsec_yield": "India approx. 10-year G-Sec",
    }
    grouped: dict[str, list[dict[str, object]]] = {key: [] for key in metric_labels}
    for row in rows:
        key = row.get("metric_key")
        if key in grouped and isinstance(row.get("date"), date):
            grouped[str(key)].append(row)
    if any(not values for values in grouped.values()):
        return {
            "available": False,
            "band": "unavailable",
            "reason": "Run EOD update to retrieve official RBI/FBIL currency and sovereign-rate data.",
        }

    def change(values: list[dict[str, object]], sessions: int, *, yield_metric: bool) -> float | None:
        if len(values) <= sessions:
            return None
        current = float(values[-1]["value"])
        previous = float(values[-(sessions + 1)]["value"])
        if yield_metric:
            return round((current - previous) * 100, 2)
        return round((current / previous - 1) * 100, 2)

    metrics: dict[str, dict[str, object]] = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda item: item["date"])
        latest = ordered[-1]
        is_yield = key == "india_10y_gsec_yield"
        metrics[key] = {
            "label": metric_labels[key],
            "level": round(float(latest["value"]), 4),
            "unit": latest["unit"],
            "instrument_label": latest["instrument_label"],
            "as_of_date": latest["date"].isoformat(),
            "five_session_change": change(ordered, 5, yield_metric=is_yield),
            "twenty_session_change": change(ordered, 20, yield_metric=is_yield),
            "change_unit": "basis points" if is_yield else "percent",
            "stored_observations": len(ordered),
        }
    latest_dates = [date.fromisoformat(item["as_of_date"]) for item in metrics.values()]
    return {
        "available": True,
        "band": "unranked",
        "reason": "Official levels are visible; directional thresholds are not yet validated.",
        "as_of_date": max(latest_dates).isoformat(),
        "oldest_component_date": min(latest_dates).isoformat(),
        "source": RBI_MACRO_SOURCE,
        "metrics": metrics,
    }


def parse_fred_global_csv(
    csv_payload: str, *, series_id: str, today: date, earliest: date
) -> list[dict[str, object]]:
    if series_id not in FRED_GLOBAL_SERIES or not isinstance(csv_payload, str):
        raise ValueError("invalid_fred_global_response")
    metric_key, unit, _label = FRED_GLOBAL_SERIES[series_id]
    reader = csv.DictReader(io.StringIO(csv_payload))
    if reader.fieldnames != ["observation_date", series_id]:
        raise ValueError("invalid_fred_global_response")
    rows: list[dict[str, object]] = []
    seen: set[date] = set()
    for raw in reader:
        raw_date = str(raw.get("observation_date", "")).strip()
        raw_value = str(raw.get(series_id, "")).strip()
        if raw_value in {"", "."}:
            continue
        try:
            observation_date = date.fromisoformat(raw_date)
            value = float(raw_value)
        except ValueError as error:
            raise ValueError("invalid_fred_global_response") from error
        if observation_date < earliest:
            continue
        if (
            observation_date > today
            or observation_date in seen
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("invalid_fred_global_response")
        seen.add(observation_date)
        rows.append(
            {
                "date": observation_date,
                "metric_key": metric_key,
                "value": value,
                "unit": unit,
                "source_series": series_id,
            }
        )
    if not rows:
        raise ValueError("invalid_fred_global_response")
    return rows


def parse_fred_global_zip(
    zip_payload: bytes, *, today: date, earliest: date
) -> list[dict[str, object]]:
    if not isinstance(zip_payload, bytes) or not zip_payload.startswith(b"PK"):
        raise ValueError("invalid_fred_global_response")
    collected: list[dict[str, object]] = []
    found_series: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                text = archive.read(name).decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text))
                fieldnames = reader.fieldnames or []
                if not fieldnames or fieldnames[0] != "observation_date":
                    raise ValueError("invalid_fred_global_response")
                series_ids = [item for item in fieldnames[1:] if item in FRED_GLOBAL_SERIES]
                if not series_ids:
                    continue
                table_rows = list(reader)
                for series_id in series_ids:
                    single_csv = io.StringIO()
                    writer = csv.writer(single_csv, lineterminator="\n")
                    writer.writerow(["observation_date", series_id])
                    writer.writerows(
                        [raw.get("observation_date", ""), raw.get(series_id, "")]
                        for raw in table_rows
                    )
                    parsed = parse_fred_global_csv(
                        single_csv.getvalue(),
                        series_id=series_id,
                        today=today,
                        earliest=earliest,
                    )
                    collected.extend(parsed)
                    found_series.add(series_id)
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise ValueError("invalid_fred_global_response") from error
    if found_series != set(FRED_GLOBAL_SERIES):
        raise ValueError("invalid_fred_global_response")
    return collected


def calculate_global_risk_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    series_specs = {
        metric_key: {"series_id": series_id, "label": label}
        for series_id, (metric_key, _unit, label) in FRED_GLOBAL_SERIES.items()
    }
    grouped: dict[str, list[dict[str, object]]] = {key: [] for key in series_specs}
    for row in rows:
        key = row.get("metric_key")
        if key in grouped and isinstance(row.get("date"), date):
            grouped[str(key)].append(row)
    if any(not values for values in grouped.values()):
        return {
            "available": False,
            "band": "unavailable",
            "reason": "Run EOD update to retrieve the permitted FRED global-risk series.",
        }

    def percent_change(values: list[dict[str, object]], sessions: int) -> float | None:
        if len(values) <= sessions:
            return None
        current = float(values[-1]["value"])
        previous = float(values[-(sessions + 1)]["value"])
        return round((current / previous - 1) * 100, 2)

    metrics: dict[str, dict[str, object]] = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda item: item["date"])
        latest = ordered[-1]
        metrics[key] = {
            "label": series_specs[key]["label"],
            "source_series": series_specs[key]["series_id"],
            "level": round(float(latest["value"]), 4),
            "unit": latest["unit"],
            "as_of_date": latest["date"].isoformat(),
            "five_session_change_pct": percent_change(ordered, 5),
            "twenty_session_change_pct": percent_change(ordered, 20),
            "stored_observations": len(ordered),
        }

    sp_values = sorted(grouped["sp500"], key=lambda item: item["date"])
    sp_latest = float(sp_values[-1]["value"])
    for window in (20, 50, 200):
        moving_average = (
            sum(float(item["value"]) for item in sp_values[-window:]) / window
            if len(sp_values) >= window
            else None
        )
        metrics["sp500"][f"vs_{window}dma_pct"] = (
            round((sp_latest / moving_average - 1) * 100, 2)
            if moving_average is not None
            else None
        )

    vix_values = sorted(grouped["us_vix"], key=lambda item: item["date"])[-252:]
    vix_latest = float(vix_values[-1]["value"])
    metrics["us_vix"]["one_year_percentile"] = round(
        100 * sum(float(item["value"]) <= vix_latest for item in vix_values) / len(vix_values),
        1,
    )
    latest_dates = [date.fromisoformat(metric["as_of_date"]) for metric in metrics.values()]
    return {
        "available": True,
        "band": "unranked",
        "reason": "Global EOD context is visible; regime thresholds are not yet validated.",
        "source": FRED_GLOBAL_SOURCE,
        "as_of_date": max(latest_dates).isoformat(),
        "oldest_component_date": min(latest_dates).isoformat(),
        "metrics": metrics,
        "scoring_enabled": False,
    }


def calculate_candidate_regime(evidence: dict[str, object]) -> dict[str, object]:
    """Apply the frozen validation-only regime rule to one EOD evidence snapshot."""

    def band_value(candidate: object) -> float | None:
        if not isinstance(candidate, dict):
            return None
        band = candidate.get("band")
        return REGIME_BAND_VALUES.get(str(band))

    trend_score = band_value(evidence.get("trend"))
    breadth_score = band_value(evidence.get("breadth"))
    price_strength_score = band_value(evidence.get("price_strength"))
    participation_parts = [
        score for score in (breadth_score, price_strength_score) if score is not None
    ]
    participation_score = (
        sum(participation_parts) / len(participation_parts)
        if len(participation_parts) == 2
        else None
    )

    volatility = evidence.get("volatility")
    realised_volatility_score = band_value(volatility)
    india_vix_score = None
    if isinstance(volatility, dict):
        india_vix = volatility.get("india_vix")
        if isinstance(india_vix, dict) and india_vix.get("available") is True:
            india_vix_score = band_value(india_vix)
    volatility_parts = [
        score for score in (realised_volatility_score, india_vix_score) if score is not None
    ]
    volatility_score = (
        sum(volatility_parts) / len(volatility_parts) if volatility_parts else None
    )

    cluster_scores = {
        "domestic_trend": trend_score,
        "participation_and_strength": participation_score,
        "volatility_and_stress": volatility_score,
        "institutional_flows": band_value(evidence.get("institutional_flows")),
        "currency_and_rates": band_value(evidence.get("macro_context")),
        "global_risk": band_value(evidence.get("global_risk")),
    }
    clusters = {
        key: {
            "weight": weight,
            "available": cluster_scores[key] is not None,
            "score": cluster_scores[key],
        }
        for key, weight in REGIME_CLUSTER_WEIGHTS.items()
    }
    available_weight = sum(
        REGIME_CLUSTER_WEIGHTS[key]
        for key, score in cluster_scores.items()
        if score is not None
    )
    weighted_total = sum(
        REGIME_CLUSTER_WEIGHTS[key] * float(score)
        for key, score in cluster_scores.items()
        if score is not None
    )
    normalized_score = weighted_total / available_weight if available_weight else None

    freshness = evidence.get("freshness")
    freshness_state = freshness.get("state") if isinstance(freshness, dict) else None
    breadth = evidence.get("breadth")
    raw_coverage = breadth.get("coverage_pct") if isinstance(breadth, dict) else None
    stock_coverage_pct = (
        float(raw_coverage)
        if isinstance(raw_coverage, (int, float)) and not isinstance(raw_coverage, bool)
        else 0.0
    )
    gate_failures: list[str] = []
    if freshness_state != "fresh":
        gate_failures.append("fresh_eod_data_required")
    if stock_coverage_pct < REGIME_MINIMUM_STOCK_COVERAGE_PCT:
        gate_failures.append("stock_coverage_below_80_pct")
    if available_weight < REGIME_MINIMUM_AVAILABLE_WEIGHT:
        gate_failures.append("weighted_evidence_below_60_pct")

    classification_eligible = not gate_failures and normalized_score is not None
    if not classification_eligible:
        label_key = "not_enough_reliable_data"
        confidence = "insufficient"
    else:
        if available_weight >= 0.90 and stock_coverage_pct >= 95.0:
            confidence = "high"
        elif available_weight >= 0.75 and stock_coverage_pct >= 90.0:
            confidence = "medium"
        else:
            confidence = "low"
        if normalized_score >= REGIME_LABEL_THRESHOLDS["positive_market"]:
            label_key = "positive_market"
        elif normalized_score >= REGIME_LABEL_THRESHOLDS["cautiously_positive"]:
            label_key = "cautiously_positive"
        elif normalized_score > REGIME_LABEL_THRESHOLDS["weak_market"]:
            label_key = "uncertain_market"
        elif normalized_score > REGIME_LABEL_THRESHOLDS["high_risk_market"]:
            label_key = "weak_market"
        else:
            label_key = "high_risk_market"

    investor_labels = {
        "positive_market": "Positive market",
        "cautiously_positive": "Cautiously positive",
        "uncertain_market": "Uncertain market",
        "weak_market": "Weak market",
        "high_risk_market": "High-risk market",
        "not_enough_reliable_data": "Not enough reliable data",
    }
    return {
        "rule_version": REGIME_RULE_VERSION,
        "validation_status": "candidate_unvalidated",
        "classification_eligible": classification_eligible,
        "label_key": label_key,
        "label": investor_labels[label_key],
        "score": round(normalized_score * 100, 1) if normalized_score is not None else None,
        "confidence": confidence,
        "available_weight_pct": round(available_weight * 100, 1),
        "stock_coverage_pct": round(stock_coverage_pct, 1),
        "freshness_state": freshness_state or "unavailable",
        "gate_failures": gate_failures,
        "missing_clusters": [
            key for key, score in cluster_scores.items() if score is None
        ],
        "clusters": clusters,
        "contract": {
            "band_values": dict(REGIME_BAND_VALUES),
            "cluster_weights": dict(REGIME_CLUSTER_WEIGHTS),
            "minimum_available_weight_pct": REGIME_MINIMUM_AVAILABLE_WEIGHT * 100,
            "minimum_stock_coverage_pct": REGIME_MINIMUM_STOCK_COVERAGE_PCT,
            "label_thresholds": dict(REGIME_LABEL_THRESHOLDS),
            "confirmation_sessions": 2,
            "recovering_label_requires_transition_history": True,
            "missing_evidence_policy": "exclude_and_reduce_confidence",
        },
    }


def build_regime_external_cluster_readiness(
    *,
    institutional_flow_rows: list[dict[str, object]] | None = None,
    confirmed_fpi_rows: list[dict[str, object]] | None = None,
    macro_snapshot_rows: list[dict[str, object]] | None = None,
    global_risk_rows: list[dict[str, object]] | None = None,
    futures_snapshot_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Audit dated external evidence before it can enter walk-forward scoring."""

    def complete_dates(
        rows: list[dict[str, object]],
        *,
        group_key: str,
        required_values: set[str],
    ) -> list[date]:
        found: defaultdict[date, set[str]] = defaultdict(set)
        for row in rows:
            row_date = row.get("date")
            value = row.get(group_key)
            if isinstance(row_date, date) and isinstance(value, str):
                found[row_date].add(value)
        return sorted(row_date for row_date, values in found.items() if required_values <= values)

    provisional_dates = complete_dates(
        institutional_flow_rows or [],
        group_key="category",
        required_values={"FII/FPI", "DII"},
    )
    confirmed_dates = complete_dates(
        confirmed_fpi_rows or [],
        group_key="investment_route",
        required_values={"Stock Exchange", "Primary market & others", "Sub-total"},
    )
    macro_dates = complete_dates(
        macro_snapshot_rows or [],
        group_key="metric_key",
        required_values={
            "usd_inr",
            "gbp_inr",
            "eur_inr",
            "jpy_100_inr",
            "india_10y_gsec_yield",
        },
    )
    global_dates = complete_dates(
        global_risk_rows or [],
        group_key="metric_key",
        required_values=set(value[0] for value in FRED_GLOBAL_SERIES.values()),
    )
    futures_by_date: defaultdict[date, set[str]] = defaultdict(set)
    for row in futures_snapshot_rows or []:
        row_date = row.get("date")
        underlying = row.get("underlying")
        if isinstance(row_date, date) and isinstance(underlying, str):
            futures_by_date[row_date].add(underlying)
    futures_dates = sorted(
        row_date
        for row_date, underlyings in futures_by_date.items()
        if len(underlyings) >= math.ceil(FNO_UNIVERSE_EXPECTED * 0.80)
    )

    def readiness_row(
        key: str,
        label: str,
        cluster: str,
        weight_pct: float | None,
        dates: list[date],
        source: str,
    ) -> dict[str, object]:
        stored_sessions = len(dates)
        history_ready = stored_sessions >= REGIME_EXTERNAL_HISTORY_SESSIONS
        walk_forward_ready = stored_sessions >= REGIME_EXTERNAL_WALK_FORWARD_SESSIONS
        return {
            "key": key,
            "label": label,
            "cluster": cluster,
            "candidate_weight_pct": weight_pct,
            "stored_sessions": stored_sessions,
            "first_session": dates[0].isoformat() if dates else None,
            "last_session": dates[-1].isoformat() if dates else None,
            "history_sessions_required": REGIME_EXTERNAL_HISTORY_SESSIONS,
            "walk_forward_sessions_required": REGIME_EXTERNAL_WALK_FORWARD_SESSIONS,
            "sessions_until_history_ready": max(
                0, REGIME_EXTERNAL_HISTORY_SESSIONS - stored_sessions
            ),
            "sessions_until_walk_forward_ready": max(
                0, REGIME_EXTERNAL_WALK_FORWARD_SESSIONS - stored_sessions
            ),
            "history_ready": history_ready,
            "walk_forward_ready": walk_forward_ready,
            "scoring_ready": False,
            "source": source,
            "status": (
                "threshold_validation_pending"
                if walk_forward_ready else "accumulating_history"
            ),
        }

    rows = [
        readiness_row(
            "nse_provisional_institutional_flows",
            "NSE provisional FII/FPI and DII cash flows",
            "Institutional flows",
            15.0,
            provisional_dates,
            NSE_FII_DII_SOURCE,
        ),
        readiness_row(
            "nsdl_confirmed_fpi",
            "NSDL confirmed FPI equity investment",
            "Institutional-flow cross-check",
            None,
            confirmed_dates,
            NSDL_FPI_SOURCE,
        ),
        readiness_row(
            "rbi_currency_and_rates",
            "RBI/FBIL currency and sovereign rates",
            "Currency and rates",
            10.0,
            macro_dates,
            RBI_MACRO_SOURCE,
        ),
        readiness_row(
            "fred_global_risk",
            "Permitted FRED global-risk series",
            "Global risk",
            15.0,
            global_dates,
            FRED_GLOBAL_SOURCE,
        ),
        readiness_row(
            "kite_futures_oi",
            "Kite F&O price and open-interest snapshots",
            "F&O confirmation layer",
            None,
            futures_dates,
            KITE_FUTURES_SOURCE,
        ),
    ]
    return {
        "minimum_history_sessions": REGIME_EXTERNAL_HISTORY_SESSIONS,
        "minimum_walk_forward_sessions": REGIME_EXTERNAL_WALK_FORWARD_SESSIONS,
        "rows": rows,
        "candidate_weight_ready_pct": sum(
            float(row["candidate_weight_pct"] or 0)
            for row in rows
            if row["scoring_ready"]
        ),
        "note": (
            "Coverage readiness does not activate scoring. Every external cluster "
            "still requires frozen directional thresholds and out-of-sample review."
        ),
    }


def apply_recovering_market_state(
    observations: list[dict[str, object]],
    *,
    minimum_risk_sessions: int = REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
    maximum_recovery_sessions: int = REGIME_RECOVERY_MAXIMUM_SESSIONS,
) -> dict[str, object]:
    """Apply an outcome-blind transition state after sustained risk episodes."""
    if minimum_risk_sessions <= 0 or maximum_recovery_sessions <= 0:
        raise ValueError("invalid_recovery_state_contract")
    risk_labels = {"weak_market", "high_risk_market"}
    recovery_entry_labels = {"uncertain_market", "cautiously_positive"}
    risk_run = 0
    risk_run_start: date | None = None
    last_risk_label: str | None = None
    active_episode: dict[str, object] | None = None
    episodes: list[dict[str, object]] = []

    def close_episode(exit_reason: str, exit_date: date | None) -> None:
        nonlocal active_episode
        if active_episode is None:
            return
        active_episode["exit_reason"] = exit_reason
        active_episode["exit_date"] = exit_date.isoformat() if exit_date else None
        episodes.append(active_episode)
        active_episode = None

    for position, observation in enumerate(observations):
        label = observation.get("confirmed_label_key")
        session_date = observation.get("date")
        if not isinstance(label, str) or not isinstance(session_date, date):
            observation["transition_label_key"] = None
            continue

        if active_episode is not None:
            if label in risk_labels:
                close_episode("relapsed_to_risk", session_date)
                observation["transition_label_key"] = label
                risk_run = 1
                risk_run_start = session_date
                last_risk_label = label
                continue
            if label == "positive_market":
                close_episode("positive_market_confirmed", session_date)
                observation["transition_label_key"] = label
                risk_run = 0
                risk_run_start = None
                last_risk_label = None
                continue
            if int(active_episode["recovery_sessions"]) < maximum_recovery_sessions:
                active_episode["recovery_sessions"] = int(active_episode["recovery_sessions"]) + 1
                observation["transition_label_key"] = "recovering_market"
                continue
            previous_date = observations[position - 1].get("date") if position else None
            close_episode(
                "maximum_window_reached",
                previous_date if isinstance(previous_date, date) else session_date,
            )
            observation["transition_label_key"] = label
            risk_run = 0
            risk_run_start = None
            last_risk_label = None
            continue

        if label in risk_labels:
            if risk_run == 0:
                risk_run_start = session_date
            risk_run += 1
            last_risk_label = label
            observation["transition_label_key"] = label
            continue

        if risk_run >= minimum_risk_sessions and label in recovery_entry_labels:
            active_episode = {
                "entry_date": session_date.isoformat(),
                "entry_base_regime": label,
                "prior_risk_regime": last_risk_label,
                "prior_risk_start": risk_run_start.isoformat() if risk_run_start else None,
                "prior_risk_sessions": risk_run,
                "recovery_sessions": 1,
                "exit_date": None,
                "exit_reason": "still_open",
            }
            observation["transition_label_key"] = "recovering_market"
        else:
            observation["transition_label_key"] = label
        risk_run = 0
        risk_run_start = None
        last_risk_label = None

    if active_episode is not None:
        close_episode("still_open", None)

    exit_counts = {
        reason: sum(episode["exit_reason"] == reason for episode in episodes)
        for reason in (
            "positive_market_confirmed",
            "relapsed_to_risk",
            "maximum_window_reached",
            "still_open",
        )
    }
    return {
        "status": "validation_only_outcome_blind_rule",
        "minimum_prior_risk_sessions": minimum_risk_sessions,
        "maximum_recovery_sessions": maximum_recovery_sessions,
        "entry_base_regimes": sorted(recovery_entry_labels),
        "positive_market_exits_immediately": True,
        "episodes": episodes,
        "episode_count": len(episodes),
        "exit_counts": exit_counts,
        "method": (
            "After at least five consecutive confirmed weak/high-risk sessions, "
            "an improvement to uncertain or cautiously positive is labelled Recovering "
            "market for at most 20 sessions. Positive confirmation or renewed risk ends it."
        ),
    }


def build_regime_validation_universe(
    instruments: list[dict[str, object]],
    *,
    stock_names: set[str] | None = None,
    constituent_snapshot: dict[str, object] | None = None,
    supported_indices: tuple[str, ...] = SEASONALITY_INDICES,
    trailing_sessions: int = REGIME_VALIDATION_TRAILING_SESSIONS,
    maximum_horizon: int = max(REGIME_VALIDATION_DEFAULT_HORIZONS),
) -> dict[str, object]:
    """Describe validation readiness without treating short history as an error."""
    by_name = {
        str(item["display_name"]): item
        for item in instruments
        if item.get("display_name") in supported_indices
    }
    rows: list[dict[str, object]] = []
    constituent_indices = (
        constituent_snapshot.get("indices", {})
        if isinstance(constituent_snapshot, dict) else {}
    )
    for display_name in supported_indices:
        item = by_name.get(display_name, {})
        session_count = int(item.get("session_count") or 0)
        current_regime_ready = session_count >= trailing_sessions
        walk_forward_ready = session_count >= trailing_sessions + maximum_horizon
        symbols = constituent_indices.get(display_name, []) if isinstance(constituent_indices, dict) else []
        official_constituent_count = len(symbols) if isinstance(symbols, list) else 0
        fno_constituent_count = (
            len(set(symbols) & stock_names)
            if isinstance(symbols, list) and stock_names is not None else None
        )
        constituent_breadth_ready = (
            fno_constituent_count >= 5
            if fno_constituent_count is not None else True
        )
        rows.append(
            {
                "display_name": display_name,
                "session_count": session_count,
                "first_session": (
                    item["first_session"].isoformat()
                    if isinstance(item.get("first_session"), date)
                    else None
                ),
                "last_session": (
                    item["last_session"].isoformat()
                    if isinstance(item.get("last_session"), date)
                    else None
                ),
                "current_regime_ready": current_regime_ready,
                "walk_forward_ready": walk_forward_ready,
                "constituent_breadth_ready": constituent_breadth_ready,
                "validation_ready": walk_forward_ready and constituent_breadth_ready,
                "official_constituent_count": official_constituent_count or None,
                "fno_constituent_count": fno_constituent_count,
                "sessions_until_current_regime": max(0, trailing_sessions - session_count),
                "sessions_until_walk_forward": max(
                    0, trailing_sessions + maximum_horizon - session_count
                ),
            }
        )
    return {
        "ok": True,
        "trailing_sessions_required": trailing_sessions,
        "maximum_forward_horizon": maximum_horizon,
        "walk_forward_sessions_required": trailing_sessions + maximum_horizon,
        "benchmark": "Nifty 50",
        "constituent_snapshot_as_of": (
            constituent_snapshot.get("as_of")
            if isinstance(constituent_snapshot, dict) else None
        ),
        "indices": rows,
    }


def calculate_regime_walk_forward_validation(
    index_candles: list[dict[str, object]],
    stock_histories: dict[str, list[dict[str, object]]],
    *,
    india_vix_candles: list[dict[str, object]] | None = None,
    target_index: str = "Nifty 50",
    benchmark_candles: list[dict[str, object]] | None = None,
    benchmark_index: str | None = None,
    constituent_symbols: list[str] | None = None,
    constituent_membership_history: list[dict[str, object]] | None = None,
    constituent_snapshot_as_of: str | None = None,
    institutional_flow_rows: list[dict[str, object]] | None = None,
    confirmed_fpi_rows: list[dict[str, object]] | None = None,
    macro_snapshot_rows: list[dict[str, object]] | None = None,
    global_risk_rows: list[dict[str, object]] | None = None,
    futures_snapshot_rows: list[dict[str, object]] | None = None,
    event_windows: tuple[dict[str, object], ...] = REGIME_VALIDATION_EVENTS,
    horizons: tuple[int, ...] = REGIME_VALIDATION_DEFAULT_HORIZONS,
) -> dict[str, object]:
    """Evaluate the frozen candidate using only evidence known at each historical EOD."""
    if not horizons or any(not isinstance(item, int) or item <= 0 for item in horizons):
        raise ValueError("invalid_regime_validation_horizons")
    ordered_index = sorted(index_candles, key=lambda item: item["date"])
    maximum_horizon = max(horizons)
    if len(ordered_index) < 252 + maximum_horizon:
        raise ValueError("regime_validation_history_unavailable")
    index_dates = [item["date"] for item in ordered_index]
    index_closes = [float(item["close"]) for item in ordered_index]
    benchmark_by_date = {
        item["date"]: float(item["close"])
        for item in sorted(benchmark_candles or [], key=lambda item: item["date"])
    }
    use_benchmark = bool(
        benchmark_index
        and benchmark_index != target_index
        and benchmark_by_date
    )
    index_prefix = [0.0]
    for close in index_closes:
        index_prefix.append(index_prefix[-1] + close)

    def window_average(prefix: list[float], end: int, length: int) -> float:
        return (prefix[end + 1] - prefix[end + 1 - length]) / length

    daily_log_returns = [
        math.log(current / previous)
        for previous, current in zip(index_closes, index_closes[1:])
    ]
    realised_volatility: list[float | None] = [None] * len(index_closes)
    for position in range(20, len(index_closes)):
        variance = _sample_variance(daily_log_returns[position - 20 : position])
        if variance is not None:
            realised_volatility[position] = math.sqrt(variance * 252) * 100

    vix_bands: dict[date, str] = {}
    ordered_vix = sorted(india_vix_candles or [], key=lambda item: item["date"])
    vix_closes = [float(item["close"]) for item in ordered_vix]
    for position in range(251, len(ordered_vix)):
        current = vix_closes[position]
        window = vix_closes[position - 251 : position + 1]
        percentile = 100 * sum(value <= current for value in window) / len(window)
        vix_bands[ordered_vix[position]["date"]] = (
            "defensive" if percentile >= 85 else "mixed" if percentile >= 60 else "constructive"
        )

    official_constituents = sorted(set(constituent_symbols or []))
    membership_history: list[dict[str, object]] = []
    for snapshot in constituent_membership_history or []:
        effective_from = snapshot.get("effective_from")
        effective_to = snapshot.get("effective_to")
        symbols = snapshot.get("symbols")
        if (
            isinstance(effective_from, date)
            and (effective_to is None or isinstance(effective_to, date))
            and isinstance(symbols, list)
        ):
            membership_history.append(
                {
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "symbols": sorted({str(symbol) for symbol in symbols if str(symbol)}),
                }
            )
    membership_history.sort(key=lambda item: item["effective_from"])
    historical_constituents = sorted(
        {
            symbol
            for snapshot in membership_history
            for symbol in snapshot["symbols"]
        }
    )
    selected_constituents = historical_constituents or official_constituents
    selected_stock_histories = (
        {
            symbol: stock_histories[symbol]
            for symbol in selected_constituents
            if symbol in stock_histories
        }
        if selected_constituents else stock_histories
    )
    if len(selected_stock_histories) < 5:
        raise ValueError("regime_validation_constituent_coverage_unavailable")

    metrics_by_date: defaultdict[date, list[tuple[str, bool, bool, bool, int, bool, bool]]] = defaultdict(list)
    for symbol, history in selected_stock_histories.items():
        ordered = sorted(history, key=lambda item: item["date"])
        if len(ordered) < 252:
            continue
        closes = [float(item["close"]) for item in ordered]
        prefix = [0.0]
        for close in closes:
            prefix.append(prefix[-1] + close)
        maximums: deque[int] = deque()
        minimums: deque[int] = deque()
        for position, close in enumerate(closes):
            while maximums and closes[maximums[-1]] <= close:
                maximums.pop()
            maximums.append(position)
            while minimums and closes[minimums[-1]] >= close:
                minimums.pop()
            minimums.append(position)
            cutoff = position - 251
            while maximums and maximums[0] < cutoff:
                maximums.popleft()
            while minimums and minimums[0] < cutoff:
                minimums.popleft()
            if position < 251:
                continue
            advance_state = 1 if close > closes[position - 1] else -1 if close < closes[position - 1] else 0
            metrics_by_date[ordered[position]["date"]].append(
                (
                    symbol,
                    close > window_average(prefix, position, 20),
                    close > window_average(prefix, position, 50),
                    close > window_average(prefix, position, 200),
                    advance_state,
                    close >= closes[maximums[0]] * 0.95,
                    close <= closes[minimums[0]] * 1.05,
                )
            )

    universe_total = len(selected_stock_histories)
    if universe_total == 0:
        raise ValueError("regime_validation_stock_history_unavailable")

    observations: list[dict[str, object]] = []
    state_observations: list[dict[str, object]] = []
    skipped_for_coverage = 0

    def membership_for_date(session_date: date) -> set[str] | None:
        for snapshot in reversed(membership_history):
            if snapshot["effective_from"] <= session_date and (
                snapshot["effective_to"] is None
                or session_date <= snapshot["effective_to"]
            ):
                return set(snapshot["symbols"])
        return set(official_constituents) if not membership_history and official_constituents else None

    for position in range(251, len(index_closes)):
        session_date = index_dates[position]
        session_membership = membership_for_date(session_date)
        if membership_history and session_membership is None:
            skipped_for_coverage += 1
            continue
        stock_metrics = [
            item
            for item in metrics_by_date.get(session_date, [])
            if session_membership is None or item[0] in session_membership
        ]
        session_universe_total = (
            len(session_membership.intersection(stock_histories))
            if session_membership is not None else universe_total
        )
        if session_universe_total < 5:
            skipped_for_coverage += 1
            continue
        coverage_pct = 100 * len(stock_metrics) / session_universe_total
        if coverage_pct < REGIME_MINIMUM_STOCK_COVERAGE_PCT:
            skipped_for_coverage += 1
            continue

        close = index_closes[position]
        sma50 = window_average(index_prefix, position, 50)
        sma200 = window_average(index_prefix, position, 200)
        prior_sma50 = (
            index_prefix[position - 19] - index_prefix[position - 69]
        ) / 50
        sma50_slope = (sma50 / prior_sma50 - 1) * 100
        if close > sma50 > sma200 and sma50_slope > 0:
            trend_band = "constructive"
        elif close < sma50 < sma200 and sma50_slope < 0:
            trend_band = "defensive"
        else:
            trend_band = "mixed"

        evaluated = len(stock_metrics)
        above50 = 100 * sum(item[2] for item in stock_metrics) / evaluated
        above200 = 100 * sum(item[3] for item in stock_metrics) / evaluated
        advances = sum(item[4] > 0 for item in stock_metrics)
        declines = sum(item[4] < 0 for item in stock_metrics)
        if above50 >= 55 and above200 >= 55 and advances > declines:
            breadth_band = "constructive"
        elif (above50 < 40 and above200 < 40) or (declines and advances / declines < 0.67):
            breadth_band = "defensive"
        else:
            breadth_band = "mixed"

        near_high_pct = 100 * sum(item[5] for item in stock_metrics) / evaluated
        near_low_pct = 100 * sum(item[6] for item in stock_metrics) / evaluated
        net_strength = near_high_pct - near_low_pct
        price_strength_band = (
            "constructive" if net_strength >= 10 else "defensive" if net_strength <= -10 else "mixed"
        )

        current_volatility = realised_volatility[position]
        historical_volatility = [
            value
            for value in realised_volatility[max(20, position - 251) : position + 1]
            if value is not None
        ]
        if current_volatility is None or not historical_volatility:
            continue
        volatility_percentile = (
            100
            * sum(value <= current_volatility for value in historical_volatility)
            / len(historical_volatility)
        )
        volatility_band = (
            "defensive"
            if volatility_percentile >= 85
            else "mixed"
            if volatility_percentile >= 60
            else "constructive"
        )
        vix_band = vix_bands.get(session_date)
        evidence = {
            "trend": {"band": trend_band},
            "breadth": {"band": breadth_band, "coverage_pct": coverage_pct},
            "price_strength": {"band": price_strength_band},
            "volatility": {
                "band": volatility_band,
                "india_vix": {
                    "available": vix_band is not None,
                    "band": vix_band or "unranked",
                },
            },
            "institutional_flows": {"band": "unranked"},
            "macro_context": {"band": "unranked"},
            "global_risk": {"band": "unranked"},
            "freshness": {"state": "fresh"},
        }
        candidate = calculate_candidate_regime(evidence)
        if not candidate["classification_eligible"]:
            continue

        state_observation: dict[str, object] = {
            "date": session_date,
            "raw_label_key": candidate["label_key"],
            "score": float(candidate["score"]),
            "coverage_pct": coverage_pct,
            "baseline_key": "above_200dma" if close > sma200 else "below_200dma",
            "close": close,
            "trend_band": trend_band,
            "breadth_band": breadth_band,
            "price_strength_band": price_strength_band,
            "volatility_band": volatility_band,
            "india_vix_band": vix_band,
            "above_50dma_pct": round(above50, 1),
            "above_200dma_pct": round(above200, 1),
            "net_strength_pct": round(net_strength, 1),
            "realised_volatility_percentile": round(volatility_percentile, 1),
        }
        state_observations.append(state_observation)
        if position + maximum_horizon >= len(index_closes):
            continue

        forward_returns: dict[str, float] = {}
        forward_drawdowns: dict[str, float] = {}
        forward_long_adverse_excursions: dict[str, float] = {}
        forward_short_adverse_excursions: dict[str, float] = {}
        forward_excess_returns: dict[str, float | None] = {}
        forward_relative_drawdowns: dict[str, float | None] = {}
        for horizon in horizons:
            future_path = index_closes[position : position + horizon + 1]
            forward_returns[str(horizon)] = (future_path[-1] / close - 1) * 100
            entry_relative_path = [
                (future_close / close - 1) * 100 for future_close in future_path[1:]
            ]
            forward_long_adverse_excursions[str(horizon)] = max(
                0.0, -min(entry_relative_path, default=0.0)
            )
            forward_short_adverse_excursions[str(horizon)] = max(
                0.0, max(entry_relative_path, default=0.0)
            )
            peak = future_path[0]
            worst_drawdown = 0.0
            for future_close in future_path[1:]:
                peak = max(peak, future_close)
                worst_drawdown = min(worst_drawdown, (future_close / peak - 1) * 100)
            forward_drawdowns[str(horizon)] = worst_drawdown
            benchmark_path = [benchmark_by_date.get(item) for item in index_dates[position : position + horizon + 1]]
            if use_benchmark and all(value is not None for value in benchmark_path):
                aligned_benchmark = [float(value) for value in benchmark_path if value is not None]
                benchmark_return = (aligned_benchmark[-1] / aligned_benchmark[0] - 1) * 100
                forward_excess_returns[str(horizon)] = forward_returns[str(horizon)] - benchmark_return
                relative_path = [
                    (target_value / future_path[0]) / (benchmark_value / aligned_benchmark[0])
                    for target_value, benchmark_value in zip(future_path, aligned_benchmark)
                ]
                relative_peak = relative_path[0]
                relative_drawdown = 0.0
                for relative_value in relative_path[1:]:
                    relative_peak = max(relative_peak, relative_value)
                    relative_drawdown = min(
                        relative_drawdown,
                        (relative_value / relative_peak - 1) * 100,
                    )
                forward_relative_drawdowns[str(horizon)] = relative_drawdown
            else:
                forward_excess_returns[str(horizon)] = None
                forward_relative_drawdowns[str(horizon)] = None
        state_observation.update(
            {
                "forward_returns_pct": forward_returns,
                "forward_drawdowns_pct": forward_drawdowns,
                "forward_long_adverse_excursions_pct": forward_long_adverse_excursions,
                "forward_short_adverse_excursions_pct": forward_short_adverse_excursions,
                "forward_excess_returns_pct": forward_excess_returns,
                "forward_relative_drawdowns_pct": forward_relative_drawdowns,
            }
        )
        observations.append(state_observation)

    if len(observations) < 2:
        raise ValueError("regime_validation_coverage_unavailable")

    pending_label: str | None = None
    pending_count = 0
    confirmed_label: str | None = None
    for observation in state_observations:
        raw_label = str(observation["raw_label_key"])
        if raw_label == pending_label:
            pending_count += 1
        else:
            pending_label = raw_label
            pending_count = 1
        if pending_count >= 2:
            confirmed_label = raw_label
        observation["confirmed_label_key"] = confirmed_label

    current_transition_analysis = apply_recovering_market_state(state_observations)
    transition_analysis = {
        key: value
        for key, value in current_transition_analysis.items()
        if key not in {"episodes", "episode_count", "exit_counts"}
    }
    historical_transition = apply_recovering_market_state(observations)
    transition_analysis.update(
        {
            "episodes": historical_transition["episodes"],
            "episode_count": historical_transition["episode_count"],
            "exit_counts": historical_transition["exit_counts"],
        }
    )

    def aggregate(group: list[dict[str, object]]) -> dict[str, object]:
        summary: dict[str, object] = {
            "sessions": len(group),
            "average_score": round(sum(float(item["score"]) for item in group) / len(group), 1),
            "average_stock_coverage_pct": round(
                sum(float(item["coverage_pct"]) for item in group) / len(group), 1
            ),
            "horizons": {},
        }
        for horizon in horizons:
            key = str(horizon)
            returns = [float(item["forward_returns_pct"][key]) for item in group]
            drawdowns = [float(item["forward_drawdowns_pct"][key]) for item in group]
            variance = _sample_variance(returns)
            summary["horizons"][key] = {
                "mean_return_pct": round(sum(returns) / len(returns), 2),
                "median_return_pct": round(median(returns), 2),
                "positive_rate_pct": round(100 * sum(value > 0 for value in returns) / len(returns), 1),
                "return_stddev_pct": round(math.sqrt(variance), 2) if variance is not None else 0.0,
                "worst_return_pct": round(min(returns), 2),
                "mean_max_drawdown_pct": round(sum(drawdowns) / len(drawdowns), 2),
                "worst_max_drawdown_pct": round(min(drawdowns), 2),
            }
            excess_returns = [
                float(value)
                for item in group
                if (value := item["forward_excess_returns_pct"][key]) is not None
            ]
            relative_drawdowns = [
                float(value)
                for item in group
                if (value := item["forward_relative_drawdowns_pct"][key]) is not None
            ]
            summary["horizons"][key].update(
                {
                    "benchmark_observations": len(excess_returns),
                    "mean_excess_return_pct": (
                        round(sum(excess_returns) / len(excess_returns), 2)
                        if excess_returns else None
                    ),
                    "median_excess_return_pct": (
                        round(median(excess_returns), 2) if excess_returns else None
                    ),
                    "outperformance_rate_pct": (
                        round(
                            100 * sum(value > 0 for value in excess_returns) / len(excess_returns),
                            1,
                        )
                        if excess_returns else None
                    ),
                    "worst_relative_drawdown_pct": (
                        round(min(relative_drawdowns), 2) if relative_drawdowns else None
                    ),
                }
            )
        return summary

    label_names = {
        "positive_market": "Positive market",
        "cautiously_positive": "Cautiously positive",
        "uncertain_market": "Uncertain market",
        "weak_market": "Weak market",
        "high_risk_market": "High-risk market",
    }
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    baseline_grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for observation in observations:
        confirmed = observation.get("confirmed_label_key")
        if isinstance(confirmed, str):
            grouped[confirmed].append(observation)
        baseline_grouped[str(observation["baseline_key"])].append(observation)

    ordered_labels = [
        "positive_market",
        "cautiously_positive",
        "uncertain_market",
        "weak_market",
        "high_risk_market",
    ]
    by_regime = [
        {"label_key": key, "label": label_names[key], **aggregate(grouped[key])}
        for key in ordered_labels
        if grouped[key]
    ]
    baseline_names = {
        "above_200dma": f"{target_index} above 200DMA",
        "below_200dma": f"{target_index} at or below 200DMA",
    }
    baseline = [
        {"baseline_key": key, "label": baseline_names[key], **aggregate(baseline_grouped[key])}
        for key in ("above_200dma", "below_200dma")
        if baseline_grouped[key]
    ]
    confirmed_observations = [
        item
        for item in observations
        if isinstance(item.get("confirmed_label_key"), str)
    ]
    overall = aggregate(confirmed_observations)
    transition_grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for observation in observations:
        transition_label = observation.get("transition_label_key")
        if isinstance(transition_label, str):
            transition_grouped[transition_label].append(observation)
    transition_order = [
        "positive_market",
        "cautiously_positive",
        "recovering_market",
        "uncertain_market",
        "weak_market",
        "high_risk_market",
    ]
    transition_label_names = {
        **label_names,
        "recovering_market": "Recovering market",
    }
    transition_analysis["by_state"] = [
        {
            "label_key": key,
            "label": transition_label_names[key],
            **aggregate(transition_grouped[key]),
        }
        for key in transition_order
        if transition_grouped[key]
    ]
    directional_evidence: list[dict[str, object]] = []
    for state in transition_analysis["by_state"]:
        state_key = str(state["label_key"])
        state_group = transition_grouped[state_key]
        long_metrics = state["horizons"][str(REGIME_LONG_HORIZON_SESSIONS)]
        short_metrics = state["horizons"][str(REGIME_SHORT_HORIZON_SESSIONS)]
        sessions = int(state["sessions"])
        sample_ready = sessions >= REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS
        long_median_excess = long_metrics.get("median_excess_return_pct")
        long_outperformance_rate = long_metrics.get("outperformance_rate_pct")
        short_median_excess = short_metrics.get("median_excess_return_pct")
        short_outperformance_rate = short_metrics.get("outperformance_rate_pct")
        relative_long_ready = (
            not use_benchmark
            or (
                long_median_excess is not None
                and float(long_median_excess) >= REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT
                and long_outperformance_rate is not None
                and float(long_outperformance_rate) >= 55.0
            )
        )
        relative_short_ready = (
            not use_benchmark
            or (
                short_median_excess is not None
                and float(short_median_excess) <= -REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT
                and short_outperformance_rate is not None
                and float(short_outperformance_rate) <= 45.0
            )
        )
        long_state_eligible = state_key in {
            "positive_market",
            "cautiously_positive",
            "recovering_market",
        }
        short_state_eligible = state_key in {
            "weak_market",
            "high_risk_market",
        }
        long_case_passed = bool(
            sample_ready
            and float(long_metrics["median_return_pct"])
            >= REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT
            and float(long_metrics["positive_rate_pct"])
            >= REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT
            and relative_long_ready
        )
        short_case_passed = bool(
            sample_ready
            and float(short_metrics["median_return_pct"])
            <= -REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT
            and float(short_metrics["positive_rate_pct"])
            <= 100 - REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT
            and relative_short_ready
        )
        if long_case_passed:
            if long_state_eligible:
                research_bias = "long_research_candidate"
            elif short_state_eligible:
                research_bias = "countertrend_rebound_study"
            else:
                research_bias = "tactical_rebound_study"
        elif short_case_passed:
            research_bias = (
                "short_research_candidate"
                if short_state_eligible else "reversal_short_study"
            )
        elif not sample_ready:
            research_bias = "insufficient_sample"
        else:
            research_bias = "no_consistent_edge"
        selected_orientation = (
            "short"
            if research_bias in {"short_research_candidate", "reversal_short_study"}
            or (
                research_bias in {"insufficient_sample", "no_consistent_edge"}
                and short_state_eligible
            )
            else "long"
        )
        selected_horizon = (
            REGIME_SHORT_HORIZON_SESSIONS
            if selected_orientation == "short" else REGIME_LONG_HORIZON_SESSIONS
        )
        metrics = short_metrics if selected_orientation == "short" else long_metrics
        median_excess = metrics.get("median_excess_return_pct")
        outperformance_rate = metrics.get("outperformance_rate_pct")
        long_risk = build_regime_risk_profile(
            state_group,
            horizon_sessions=REGIME_LONG_HORIZON_SESSIONS,
            orientation="long",
        )
        short_risk = build_regime_risk_profile(
            state_group,
            horizon_sessions=REGIME_SHORT_HORIZON_SESSIONS,
            orientation="short",
        )
        selected_risk = short_risk if selected_orientation == "short" else long_risk
        directional_evidence.append(
            {
                "label_key": state_key,
                "label": state["label"],
                "sessions": sessions,
                "sample_ready": sample_ready,
                "research_bias": research_bias,
                "orientation": selected_orientation,
                "horizon_sessions": selected_horizon,
                "median_return_pct": metrics["median_return_pct"],
                "positive_rate_pct": metrics["positive_rate_pct"],
                "median_excess_return_pct": median_excess,
                "outperformance_rate_pct": outperformance_rate,
                "worst_return_pct": metrics["worst_return_pct"],
                "worst_max_drawdown_pct": metrics["worst_max_drawdown_pct"],
                "risk_profile": selected_risk,
                "long_case": {
                    "horizon_sessions": REGIME_LONG_HORIZON_SESSIONS,
                    "passed": long_case_passed,
                    "median_return_pct": long_metrics["median_return_pct"],
                    "positive_rate_pct": long_metrics["positive_rate_pct"],
                    "median_excess_return_pct": long_median_excess,
                    "outperformance_rate_pct": long_outperformance_rate,
                    "risk_profile": long_risk,
                },
                "short_case": {
                    "horizon_sessions": REGIME_SHORT_HORIZON_SESSIONS,
                    "passed": short_case_passed,
                    "median_return_pct": short_metrics["median_return_pct"],
                    "positive_rate_pct": short_metrics["positive_rate_pct"],
                    "median_excess_return_pct": short_median_excess,
                    "outperformance_rate_pct": short_outperformance_rate,
                    "risk_profile": short_risk,
                },
            }
        )
    transition_analysis["directional_state_evidence"] = directional_evidence
    transition_analysis["directional_contract"] = {
        "minimum_state_sessions": REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
        "absolute_median_return_threshold_pct": REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
        "positive_rate_long_threshold_pct": REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
        "positive_rate_short_threshold_pct": 100
        - REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
        "relative_median_excess_threshold_pct": REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
        "relative_outperformance_long_threshold_pct": 55.0,
        "relative_outperformance_short_threshold_pct": 45.0,
        "long_horizon_sessions": REGIME_LONG_HORIZON_SESSIONS,
        "short_horizon_sessions": REGIME_SHORT_HORIZON_SESSIONS,
        "tail_percentile": REGIME_RISK_TAIL_PERCENTILE,
        "adverse_distance_levels_pct": list(REGIME_ADVERSE_DISTANCE_LEVELS_PCT),
        "status": "historical_research_only",
    }

    recovery_group = transition_grouped.get("recovering_market", [])
    base_comparison_group = (
        transition_grouped.get("uncertain_market", [])
        + transition_grouped.get("cautiously_positive", [])
    )
    recovery_incremental: dict[str, object] = {
        "status": "insufficient_sample",
        "recovery_sessions": len(recovery_group),
        "comparable_base_sessions": len(base_comparison_group),
        "minimum_recovery_episodes": 5,
        "minimum_state_sessions": REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
    }
    if recovery_group and base_comparison_group:
        recovery_summary = aggregate(recovery_group)
        base_summary = aggregate(base_comparison_group)
        recovery_metrics = recovery_summary["horizons"]["20"]
        base_metrics = base_summary["horizons"]["20"]
        delta_return = round(
            float(recovery_metrics["median_return_pct"])
            - float(base_metrics["median_return_pct"]),
            2,
        )
        delta_positive = round(
            float(recovery_metrics["positive_rate_pct"])
            - float(base_metrics["positive_rate_pct"]),
            1,
        )
        delta_drawdown = round(
            float(recovery_metrics["worst_max_drawdown_pct"])
            - float(base_metrics["worst_max_drawdown_pct"]),
            2,
        )
        recovery_excess = recovery_metrics.get("median_excess_return_pct")
        base_excess = base_metrics.get("median_excess_return_pct")
        delta_excess = (
            round(float(recovery_excess) - float(base_excess), 2)
            if recovery_excess is not None and base_excess is not None else None
        )
        sample_ready = (
            len(recovery_group) >= REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS
            and len(base_comparison_group) >= REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS
            and int(transition_analysis["episode_count"]) >= 5
        )
        positive_relative_gate = not use_benchmark or (
            delta_excess is not None and delta_excess >= 0
        )
        negative_relative_gate = not use_benchmark or (
            delta_excess is not None and delta_excess <= 0
        )
        if not sample_ready:
            status = "insufficient_sample"
        elif (
            delta_return >= REGIME_RECOVERY_INCREMENTAL_RETURN_PCT
            and delta_positive >= REGIME_RECOVERY_INCREMENTAL_POSITIVE_RATE_PCT
            and delta_drawdown >= -REGIME_RECOVERY_DRAWDOWN_TOLERANCE_PCT
            and positive_relative_gate
        ):
            status = "recovery_long_thesis_supported"
        elif (
            delta_return <= -REGIME_RECOVERY_INCREMENTAL_RETURN_PCT
            and delta_positive <= -REGIME_RECOVERY_INCREMENTAL_POSITIVE_RATE_PCT
            and negative_relative_gate
        ):
            status = "recovery_long_thesis_contradicted"
        else:
            status = "mixed_incremental_evidence"
        recovery_incremental.update(
            {
                "status": status,
                "sample_ready": sample_ready,
                "recovery_20d": recovery_metrics,
                "comparable_base_20d": base_metrics,
                "delta_median_return_pct": delta_return,
                "delta_positive_rate_pct": delta_positive,
                "delta_worst_drawdown_pct": delta_drawdown,
                "delta_median_excess_return_pct": delta_excess,
            }
        )
    transition_analysis["recovery_incremental_evidence"] = recovery_incremental
    observations_by_date = {
        item["date"].isoformat(): item
        for item in observations
        if isinstance(item.get("date"), date)
    }
    for episode in transition_analysis["episodes"]:
        entry_observation = observations_by_date.get(str(episode["entry_date"]))
        if not isinstance(entry_observation, dict):
            continue
        episode["entry_score"] = round(float(entry_observation["score"]), 1)
        episode["forward_outcomes"] = {
            key: {
                "return_pct": entry_observation["forward_returns_pct"].get(key),
                "maximum_drawdown_pct": entry_observation["forward_drawdowns_pct"].get(key),
                "excess_return_pct": entry_observation["forward_excess_returns_pct"].get(key),
            }
            for key in ("5", "20", "60")
            if key in entry_observation["forward_returns_pct"]
        }

    latest_state = state_observations[-1]
    latest_state_date = latest_state["date"]
    latest_state_position = index_dates.index(latest_state_date)
    current_session_lag = len(index_dates) - 1 - latest_state_position
    current_base_key = latest_state.get("confirmed_label_key")
    current_transition_key = latest_state.get("transition_label_key")
    current_state = {
        "as_of_date": latest_state_date.isoformat(),
        "latest_index_session": index_dates[-1].isoformat(),
        "session_lag": current_session_lag,
        "fresh": current_session_lag == 0,
        "classification_ready": (
            current_session_lag == 0
            and isinstance(current_base_key, str)
            and isinstance(current_transition_key, str)
        ),
        "base_label_key": current_base_key,
        "base_label": (
            transition_label_names.get(str(current_base_key))
            if isinstance(current_base_key, str) else None
        ),
        "transition_label_key": current_transition_key,
        "transition_label": (
            transition_label_names.get(str(current_transition_key))
            if isinstance(current_transition_key, str) else None
        ),
        "score": round(float(latest_state["score"]), 1),
        "stock_coverage_pct": round(float(latest_state["coverage_pct"]), 1),
        "close": round(float(latest_state["close"]), 2),
        "evidence": {
            "trend_band": latest_state["trend_band"],
            "breadth_band": latest_state["breadth_band"],
            "price_strength_band": latest_state["price_strength_band"],
            "volatility_band": latest_state["volatility_band"],
            "india_vix_band": latest_state["india_vix_band"],
            "above_50dma_pct": latest_state["above_50dma_pct"],
            "above_200dma_pct": latest_state["above_200dma_pct"],
            "net_strength_pct": latest_state["net_strength_pct"],
            "realised_volatility_percentile": latest_state[
                "realised_volatility_percentile"
            ],
        },
    }

    confirmed_sequence = [
        str(item["confirmed_label_key"])
        for item in observations
        if isinstance(item.get("confirmed_label_key"), str)
    ]
    raw_transitions = sum(
        current != previous
        for previous, current in zip(
            [str(item["raw_label_key"]) for item in observations],
            [str(item["raw_label_key"]) for item in observations][1:],
        )
    )
    confirmed_transitions = sum(
        current != previous
        for previous, current in zip(confirmed_sequence, confirmed_sequence[1:])
    )
    durations: defaultdict[str, list[int]] = defaultdict(list)
    if confirmed_sequence:
        run_label = confirmed_sequence[0]
        run_length = 1
        for label in confirmed_sequence[1:]:
            if label == run_label:
                run_length += 1
            else:
                durations[run_label].append(run_length)
                run_label = label
                run_length = 1
        durations[run_label].append(run_length)
    duration_summary = [
        {
            "label_key": key,
            "label": label_names[key],
            "episodes": len(values),
            "average_sessions": round(sum(values) / len(values), 1),
            "median_sessions": round(float(median(values)), 1),
            "maximum_sessions": max(values),
        }
        for key in ordered_labels
        if (values := durations.get(key))
    ]

    event_results: list[dict[str, object]] = []
    risk_labels = {"weak_market", "high_risk_market"}
    close_by_date = dict(zip(index_dates, index_closes))
    named_event_ranges = [
        (event.get("start"), event.get("end"))
        for event in event_windows
        if isinstance(event.get("start"), date)
        and isinstance(event.get("end"), date)
        and event["end"] >= event["start"]
    ]

    def overlaps_named_event(group: list[dict[str, object]]) -> bool:
        return any(
            event_start <= item["date"] <= event_end
            for item in group
            for event_start, event_end in named_event_ranges
        )

    def normal_control_distribution(session_count: int) -> list[dict[str, float]]:
        if session_count < 2:
            return []
        controls: list[dict[str, float]] = []
        for start in range(0, len(confirmed_observations) - session_count + 1, session_count):
            group = confirmed_observations[start : start + session_count]
            if overlaps_named_event(group):
                continue
            closes = [close_by_date[item["date"]] for item in group]
            control_return = (closes[-1] / closes[0] - 1) * 100
            peak = closes[0]
            control_drawdown = 0.0
            for close in closes[1:]:
                peak = max(peak, close)
                control_drawdown = min(control_drawdown, (close / peak - 1) * 100)
            labels = [str(item["confirmed_label_key"]) for item in group]
            transition_labels = [str(item.get("transition_label_key")) for item in group]
            controls.append(
                {
                    "return_pct": control_return,
                    "maximum_drawdown_pct": control_drawdown,
                    "weak_or_high_risk_sessions_pct": (
                        100 * sum(label in risk_labels for label in labels) / len(labels)
                    ),
                    "recovering_sessions_pct": (
                        100
                        * sum(label == "recovering_market" for label in transition_labels)
                        / len(transition_labels)
                    ),
                }
            )
        return controls

    def empirical_percentile(value: float, controls: list[float]) -> float | None:
        if not controls:
            return None
        lower = sum(item < value for item in controls)
        equal = sum(math.isclose(item, value, abs_tol=1e-9) for item in controls)
        return round(100 * (lower + 0.5 * equal) / len(controls), 1)

    for event in event_windows:
        event_start = event.get("start")
        event_end = event.get("end")
        if not isinstance(event_start, date) or not isinstance(event_end, date) or event_end < event_start:
            continue
        event_path = [
            (session_date, close)
            for session_date, close in zip(index_dates, index_closes)
            if event_start <= session_date <= event_end
        ]
        event_observations = [
            item
            for item in observations
            if event_start <= item["date"] <= event_end
            and isinstance(item.get("confirmed_label_key"), str)
        ]
        if len(event_path) < 2 or not event_observations:
            continue
        event_return = (event_path[-1][1] / event_path[0][1] - 1) * 100
        peak = event_path[0][1]
        event_drawdown = 0.0
        for _, close in event_path[1:]:
            peak = max(peak, close)
            event_drawdown = min(event_drawdown, (close / peak - 1) * 100)
        event_labels = [str(item["confirmed_label_key"]) for item in event_observations]
        regime_counts = {
            key: event_labels.count(key)
            for key in ordered_labels
            if key in event_labels
        }
        dominant_key = max(regime_counts, key=regime_counts.get)
        risk_positions = [
            index
            for index, label in enumerate(event_labels)
            if label in risk_labels
        ]
        benchmark_return: float | None = None
        excess_return: float | None = None
        relative_drawdown: float | None = None
        benchmark_path = [benchmark_by_date.get(session_date) for session_date, _ in event_path]
        if use_benchmark and all(value is not None for value in benchmark_path):
            aligned_benchmark = [float(value) for value in benchmark_path if value is not None]
            benchmark_return = (aligned_benchmark[-1] / aligned_benchmark[0] - 1) * 100
            excess_return = event_return - benchmark_return
            relative_path = [
                (target_close / event_path[0][1]) / (benchmark_close / aligned_benchmark[0])
                for (_, target_close), benchmark_close in zip(event_path, aligned_benchmark)
            ]
            relative_peak = relative_path[0]
            relative_drawdown = 0.0
            for relative_value in relative_path[1:]:
                relative_peak = max(relative_peak, relative_value)
                relative_drawdown = min(
                    relative_drawdown,
                    (relative_value / relative_peak - 1) * 100,
                )
        event_stress_share = (
            100 * sum(label in risk_labels for label in event_labels) / len(event_labels)
        )
        event_recovery_share = (
            100
            * sum(
                item.get("transition_label_key") == "recovering_market"
                for item in event_observations
            )
            / len(event_observations)
        )
        normal_controls = normal_control_distribution(len(event_observations))
        control_returns = [item["return_pct"] for item in normal_controls]
        control_drawdowns = [item["maximum_drawdown_pct"] for item in normal_controls]
        control_stress_shares = [
            item["weak_or_high_risk_sessions_pct"] for item in normal_controls
        ]
        control_recovery_shares = [
            item["recovering_sessions_pct"] for item in normal_controls
        ]
        event_results.append(
            {
                "key": str(event.get("key") or "event"),
                "label": str(event.get("label") or "Event review"),
                "window_start": event_path[0][0].isoformat(),
                "window_end": event_path[-1][0].isoformat(),
                "sessions": len(event_observations),
                "index_return_pct": round(event_return, 2),
                "maximum_drawdown_pct": round(event_drawdown, 2),
                "benchmark_return_pct": round(benchmark_return, 2) if benchmark_return is not None else None,
                "excess_return_pct": round(excess_return, 2) if excess_return is not None else None,
                "relative_drawdown_pct": round(relative_drawdown, 2) if relative_drawdown is not None else None,
                "entry_regime": label_names[event_labels[0]],
                "exit_regime": label_names[event_labels[-1]],
                "dominant_regime": label_names[dominant_key],
                "weak_or_high_risk_sessions_pct": round(event_stress_share, 1),
                "recovering_sessions_pct": round(event_recovery_share, 1),
                "first_weak_or_high_risk_date": (
                    event_observations[risk_positions[0]]["date"].isoformat()
                    if risk_positions else None
                ),
                "sessions_to_first_weak_or_high_risk": risk_positions[0] if risk_positions else None,
                "minimum_candidate_score": round(
                    min(float(item["score"]) for item in event_observations), 1
                ),
                "regime_session_counts": regime_counts,
                "normal_period_control": {
                    "method": "non_overlapping_same_length_windows_excluding_named_events",
                    "window_count": len(normal_controls),
                    "median_return_pct": (
                        round(float(median(control_returns)), 2) if control_returns else None
                    ),
                    "median_maximum_drawdown_pct": (
                        round(float(median(control_drawdowns)), 2) if control_drawdowns else None
                    ),
                    "median_weak_or_high_risk_sessions_pct": (
                        round(float(median(control_stress_shares)), 1)
                        if control_stress_shares else None
                    ),
                    "median_recovering_sessions_pct": (
                        round(float(median(control_recovery_shares)), 1)
                        if control_recovery_shares else None
                    ),
                    "event_return_percentile_pct": (
                        empirical_percentile(event_return, control_returns)
                    ),
                    "event_drawdown_severity_percentile_pct": (
                        empirical_percentile(
                            -event_drawdown,
                            [-value for value in control_drawdowns],
                        )
                    ),
                    "event_stress_share_percentile_pct": (
                        empirical_percentile(event_stress_share, control_stress_shares)
                    ),
                    "event_recovery_share_percentile_pct": (
                        empirical_percentile(event_recovery_share, control_recovery_shares)
                    ),
                },
            }
        )

    return {
        "ok": True,
        "target_index": target_index,
        "benchmark_index": benchmark_index if use_benchmark else None,
        "evidence_scope": {
            "target_specific": [
                "trend",
                "realised_volatility",
                "forward_outcomes",
                "current-constituent F&O breadth",
                "current-constituent F&O price strength",
            ],
            "broad_market_context": ["main Market Sentiment regime remains separate"],
        },
        "rule_version": REGIME_RULE_VERSION,
        "validation_status": "historical_walk_forward_exploratory",
        "method": "Each session uses trailing data only; outcomes begin after classification.",
        "confirmation_sessions": 2,
        "evaluation_start": observations[0]["date"].isoformat(),
        "evaluation_end": observations[-1]["date"].isoformat(),
        "index_history_start": index_dates[0].isoformat(),
        "index_history_end": index_dates[-1].isoformat(),
        "sessions_evaluated": len(observations),
        "sessions_skipped_for_coverage": skipped_for_coverage,
        "stock_universe_size": universe_total,
        "breadth_universe": {
            "method": (
                "point_in_time_index_constituents_intersected_with_fno_universe"
                if membership_history
                else "current_index_constituents_intersected_with_fno_universe"
                if official_constituents
                else "broad_fno_universe"
            ),
            "membership_history_available": bool(membership_history),
            "membership_snapshot_count": len(membership_history),
            "constituent_snapshot_as_of": constituent_snapshot_as_of,
            "official_constituent_count": (
                len(official_constituents) if official_constituents else None
            ),
            "fno_constituent_count": universe_total,
            "constituents_outside_fno_universe": (
                [symbol for symbol in official_constituents if symbol not in stock_histories]
                if official_constituents else []
            ),
        },
        "horizons": list(horizons),
        "raw_transitions": raw_transitions,
        "confirmed_transitions": confirmed_transitions,
        "transition_reduction_pct": round(
            100 * (raw_transitions - confirmed_transitions) / raw_transitions, 1
        ) if raw_transitions else 0.0,
        "by_regime": by_regime,
        "overall": overall,
        "duration_summary": duration_summary,
        "current_state": current_state,
        "transition_analysis": transition_analysis,
        "event_validation": event_results,
        "external_cluster_readiness": build_regime_external_cluster_readiness(
            institutional_flow_rows=institutional_flow_rows,
            confirmed_fpi_rows=confirmed_fpi_rows,
            macro_snapshot_rows=macro_snapshot_rows,
            global_risk_rows=global_risk_rows,
            futures_snapshot_rows=futures_snapshot_rows,
        ),
        "baseline": baseline,
        "limitations": [
            (
                "Historical breadth uses dated index-membership snapshots intersected with the available F&O histories."
                if membership_history
                else "Historical breadth uses today’s index constituents intersected with the current F&O universe and is subject to survivorship and membership bias."
            ),
            "Constituent stocks enter only after 252 stored sessions; each evaluated date must meet the 80% coverage gate.",
            "Institutional-flow, currency/rates, and global-risk clusters remain unranked, leaving 60% candidate weight available.",
            "Thresholds were frozen before this report but have not been statistically fitted or approved for decisions.",
            "Overlapping forward-return windows are descriptive and not independent observations.",
            "Named event windows are retrospective stress reviews selected with hindsight and are not independent test samples.",
            "Normal-period controls are non-overlapping same-length historical windows outside the named events; they are descriptive controls, not causal counterfactuals.",
            "The Recovering market state is an outcome-blind transition rule under validation; it is not displayed as a current signal.",
        ],
    }


def calculate_domestic_sentiment_core(
    index_candles: list[dict[str, object]],
    stock_histories: dict[str, list[dict[str, object]]],
    *,
    india_vix_candles: list[dict[str, object]] | None = None,
    institutional_flow_rows: list[dict[str, object]] | None = None,
    confirmed_fpi_rows: list[dict[str, object]] | None = None,
    macro_snapshot_rows: list[dict[str, object]] | None = None,
    global_risk_rows: list[dict[str, object]] | None = None,
    futures_snapshot_rows: list[dict[str, object]] | None = None,
    retrieved_at: datetime | None = None,
) -> dict[str, object]:
    """Calculate transparent EOD domestic-tape evidence from local candles."""
    retrieved_at = (retrieved_at or datetime.now(INDIA_TIMEZONE)).astimezone(INDIA_TIMEZONE)
    ordered_index = sorted(index_candles, key=lambda item: item["date"])
    if len(ordered_index) < 252:
        raise ValueError("domestic_core_history_unavailable")
    as_of = ordered_index[-1]["date"]
    closes = [float(row["close"]) for row in ordered_index]

    def average(values: list[float]) -> float:
        return sum(values) / len(values)

    def relative_pct(value: float, reference: float) -> float:
        return ((value / reference) - 1) * 100

    latest_close = closes[-1]
    sma20 = average(closes[-20:])
    sma50 = average(closes[-50:])
    sma200 = average(closes[-200:])
    prior_sma50 = average(closes[-70:-20])
    sma50_slope = relative_pct(sma50, prior_sma50)
    drawdown = relative_pct(latest_close, max(closes[-252:]))
    momentum20 = relative_pct(latest_close, closes[-21])

    if latest_close > sma50 > sma200 and sma50_slope > 0:
        trend_band = "constructive"
        trend_reason = "Price is above aligned rising 50- and 200-session averages."
    elif latest_close < sma50 < sma200 and sma50_slope < 0:
        trend_band = "defensive"
        trend_reason = "Price is below aligned falling 50- and 200-session averages."
    else:
        trend_band = "mixed"
        trend_reason = "Price and moving-average evidence is not fully aligned."

    daily_returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:])]

    def annualised_volatility(returns: list[float]) -> float:
        variance = _sample_variance(returns)
        if variance is None:
            raise ValueError("domestic_core_history_unavailable")
        return math.sqrt(variance * 252) * 100

    current_vol = annualised_volatility(daily_returns[-20:])
    rolling_vols = [
        annualised_volatility(daily_returns[end - 20:end])
        for end in range(max(20, len(daily_returns) - 251), len(daily_returns) + 1)
    ]
    previous_vol = rolling_vols[-6] if len(rolling_vols) >= 6 else rolling_vols[0]
    vol_percentile = 100 * sum(value <= current_vol for value in rolling_vols) / len(rolling_vols)
    if vol_percentile >= 85:
        volatility_band = "defensive"
        volatility_reason = "Realised volatility is in the top 15% of its one-year range."
    elif vol_percentile >= 60:
        volatility_band = "mixed"
        volatility_reason = "Realised volatility is elevated relative to the past year."
    else:
        volatility_band = "constructive"
        volatility_reason = "Realised volatility is below its elevated-risk range."

    ordered_vix = [
        row
        for row in sorted(india_vix_candles or [], key=lambda item: item["date"])
        if row["date"] <= as_of
    ]
    if len(ordered_vix) >= 252 and ordered_vix[-1]["date"] == as_of:
        vix_closes = [float(row["close"]) for row in ordered_vix]
        vix_level = vix_closes[-1]
        vix_percentile = 100 * sum(value <= vix_level for value in vix_closes[-252:]) / 252
        vix_five_day_change = vix_level - vix_closes[-6]
        if vix_percentile >= 85:
            vix_band = "defensive"
            vix_reason = "India VIX is in the top 15% of its one-year range."
        elif vix_percentile >= 60:
            vix_band = "mixed"
            vix_reason = "India VIX is elevated relative to its one-year range."
        else:
            vix_band = "constructive"
            vix_reason = "India VIX is below its elevated-risk range."
        india_vix = {
            "available": True,
            "as_of_date": ordered_vix[-1]["date"].isoformat(),
            "level": round(vix_level, 2),
            "five_day_change_pt": round(vix_five_day_change, 2),
            "one_year_percentile": round(vix_percentile, 1),
            "implied_realised_gap_pt": round(vix_level - current_vol, 2),
            "band": vix_band,
            "reason": vix_reason,
        }
    else:
        india_vix = {
            "available": False,
            "as_of_date": ordered_vix[-1]["date"].isoformat() if ordered_vix else None,
            "reason": "India VIX needs 252 aligned completed sessions from the EOD update.",
        }

    eligible: list[list[float]] = []
    eligible_by_date: list[dict[date, float]] = []
    missing_stocks: list[dict[str, object]] = []
    for stock_name, history in sorted(stock_histories.items()):
        ordered = sorted(history, key=lambda item: item["date"])
        last_session = ordered[-1]["date"] if ordered else None
        if not ordered:
            reason = "no_history"
        elif len(ordered) < 252:
            reason = "insufficient_history"
        elif last_session != as_of:
            reason = "latest_session_mismatch"
        else:
            reason = None
        if reason is not None:
            missing_stocks.append(
                {
                    "stock": stock_name,
                    "reason": reason,
                    "sessions": len(ordered),
                    "last_session": last_session.isoformat() if last_session else None,
                }
            )
            continue
        eligible.append([float(row["close"]) for row in ordered])
        eligible_by_date.append({row["date"]: float(row["close"]) for row in ordered})
    if not eligible:
        raise ValueError("domestic_breadth_unavailable")

    def percent_above(window: int) -> float:
        return 100 * sum(series[-1] > average(series[-window:]) for series in eligible) / len(eligible)

    advances = sum(series[-1] > series[-2] for series in eligible)
    declines = sum(series[-1] < series[-2] for series in eligible)
    unchanged = len(eligible) - advances - declines
    advance_decline_ratio = advances / declines if declines else None
    common_dates = sorted(
        set.intersection(*(set(series) for series in eligible_by_date))
    )
    price_strength_series: list[dict[str, object]] = []
    if len(common_dates) >= 252:
        first_evaluation = max(251, len(common_dates) - PRICE_STRENGTH_SERIES_SESSIONS)
        for position in range(first_evaluation, len(common_dates)):
            window_dates = common_dates[position - 251 : position + 1]
            evaluation_date = common_dates[position]
            near_high_count = 0
            near_low_count = 0
            for history in eligible_by_date:
                window = [history[session] for session in window_dates]
                latest = window[-1]
                near_high_count += latest >= max(window) * 0.95
                near_low_count += latest <= min(window) * 1.05
            high_pct = 100 * near_high_count / len(eligible_by_date)
            low_pct = 100 * near_low_count / len(eligible_by_date)
            price_strength_series.append(
                {
                    "date": evaluation_date.isoformat(),
                    "near_52w_high_pct": round(high_pct, 1),
                    "near_52w_low_pct": round(low_pct, 1),
                    "net_strength_pct": round(high_pct - low_pct, 1),
                }
            )
    if price_strength_series:
        latest_strength = price_strength_series[-1]
        near_high_pct = float(latest_strength["near_52w_high_pct"])
        near_low_pct = float(latest_strength["near_52w_low_pct"])
        price_strength = float(latest_strength["net_strength_pct"])
    else:
        near_high = sum(series[-1] >= max(series[-252:]) * 0.95 for series in eligible)
        near_low = sum(series[-1] <= min(series[-252:]) * 1.05 for series in eligible)
        near_high_pct = 100 * near_high / len(eligible)
        near_low_pct = 100 * near_low / len(eligible)
        price_strength = near_high_pct - near_low_pct
    above20 = percent_above(20)
    above50 = percent_above(50)
    above200 = percent_above(200)
    if above50 >= 55 and above200 >= 55 and advances > declines:
        breadth_band = "constructive"
        breadth_reason = "A majority is above medium- and long-term averages with positive daily breadth."
    elif (above50 < 40 and above200 < 40) or (declines and advances / declines < 0.67):
        breadth_band = "defensive"
        breadth_reason = "Participation is weak across moving averages or daily breadth."
    else:
        breadth_band = "mixed"
        breadth_reason = "Participation is neither broadly strong nor broadly weak."

    if price_strength >= 10:
        price_strength_band = "constructive"
        price_strength_reason = "More stocks are clustered near 52-week highs than lows."
    elif price_strength <= -10:
        price_strength_band = "defensive"
        price_strength_reason = "More stocks are clustered near 52-week lows than highs."
    else:
        price_strength_band = "mixed"
        price_strength_reason = "The balance near 52-week extremes is inconclusive."

    bands = [trend_band, breadth_band, price_strength_band, volatility_band]
    constructive = bands.count("constructive")
    defensive = bands.count("defensive")
    if constructive >= 3 and defensive == 0:
        domestic_tape = "Constructive"
    elif defensive >= 2:
        domestic_tape = "Defensive"
    else:
        domestic_tape = "Mixed"

    expected_through = completed_history_date(retrieved_at)
    while expected_through.weekday() >= 5:
        expected_through -= timedelta(days=1)
    freshness_lag_days = max(0, (expected_through - as_of).days)
    if as_of >= expected_through:
        freshness_state = "fresh"
    elif freshness_lag_days == 1:
        freshness_state = "pending"
    else:
        freshness_state = "stale"
    universe_total = len(stock_histories)
    coverage_pct = 100 * len(eligible) / universe_total if universe_total else 0.0
    institutional_flows = calculate_institutional_flow_summary(institutional_flow_rows or [])
    confirmed_fpi = calculate_confirmed_fpi_summary(confirmed_fpi_rows or [])
    macro_context = calculate_macro_context_summary(macro_snapshot_rows or [])
    global_risk = calculate_global_risk_summary(global_risk_rows or [])
    futures_oi = calculate_futures_oi_summary(futures_snapshot_rows or [])

    payload = {
        "ok": True,
        "as_of_date": as_of.isoformat(),
        "overall_regime": "Pending full model",
        "domestic_tape": domestic_tape,
        "confidence": "Partial",
        "available_clusters": (
            3
            + int(institutional_flows["available"])
            + int(macro_context["available"])
            + int(global_risk["available"])
        ),
        "total_clusters": 6,
        "trend": {
            "band": trend_band,
            "reason": trend_reason,
            "close": round(latest_close, 2),
            "vs_20dma_pct": round(relative_pct(latest_close, sma20), 2),
            "vs_50dma_pct": round(relative_pct(latest_close, sma50), 2),
            "vs_200dma_pct": round(relative_pct(latest_close, sma200), 2),
            "sma50_slope_20d_pct": round(sma50_slope, 2),
            "momentum_20d_pct": round(momentum20, 2),
            "drawdown_52w_pct": round(drawdown, 2),
        },
        "breadth": {
            "band": breadth_band,
            "reason": breadth_reason,
            "universe": "Locally stored NSE F&O equities",
            "evaluated": len(eligible),
            "above_20dma_pct": round(above20, 1),
            "above_50dma_pct": round(above50, 1),
            "above_200dma_pct": round(above200, 1),
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "advance_decline_ratio": round(advance_decline_ratio, 2) if advance_decline_ratio is not None else None,
            "universe_total": universe_total,
            "coverage_pct": round(coverage_pct, 1),
            "missing_count": len(missing_stocks),
            "missing_stocks": missing_stocks,
        },
        "price_strength": {
            "band": price_strength_band,
            "reason": price_strength_reason,
            "near_52w_high_pct": round(near_high_pct, 1),
            "near_52w_low_pct": round(near_low_pct, 1),
            "net_strength_pct": round(price_strength, 1),
            "series": price_strength_series,
            "series_window_sessions": PRICE_STRENGTH_SERIES_SESSIONS,
        },
        "volatility": {
            "band": volatility_band,
            "reason": volatility_reason,
            "realised_20d_pct": round(current_vol, 2),
            "five_day_change_pt": round(current_vol - previous_vol, 2),
            "one_year_percentile": round(vol_percentile, 1),
            "india_vix": india_vix,
        },
        "institutional_flows": institutional_flows,
        "confirmed_fpi": confirmed_fpi,
        "macro_context": macro_context,
        "global_risk": global_risk,
        "futures_oi": futures_oi,
        "source": "Validated local Kite EOD candles",
        "freshness": {
            "state": freshness_state,
            "expected_through": expected_through.isoformat(),
            "latest_session": as_of.isoformat(),
            "lag_days": freshness_lag_days,
            "retrieved_at": retrieved_at.isoformat(timespec="seconds"),
        },
    }
    payload["candidate_regime"] = calculate_candidate_regime(payload)
    return payload


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
        if path == "/api/kite/seasonality":
            self._send_seasonality(urllib.parse.urlsplit(self.path).query)
            return
        if path == "/api/market-sentiment/domestic-core":
            self._send_domestic_sentiment_core()
            return
        if path == "/api/market-sentiment/regime-validation":
            self._send_regime_validation(urllib.parse.urlsplit(self.path).query)
            return
        if path == "/api/market-sentiment/regime-validation-universe":
            self._send_regime_validation_universe()
            return
        if path == "/api/market-sentiment/cross-index-validation":
            self._send_cross_index_validation()
            return
        super().do_GET()

    def _send_domestic_sentiment_core(self) -> None:
        try:
            payload = self._calculate_sentiment_payload()
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": str(error)})

    def _send_regime_validation(self, query: str) -> None:
        try:
            parameters = urllib.parse.parse_qs(query, keep_blank_values=True)
            target_index = parameters.get("index", ["Nifty 50"])[0]
            benchmark_value = parameters.get("benchmark", ["Nifty 50"])[0]
            if target_index not in SEASONALITY_INDICES or benchmark_value not in {"Nifty 50", "none"}:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "reason": "invalid_regime_validation_selection"},
                )
                return
            benchmark_index = None if benchmark_value == "none" or benchmark_value == target_index else benchmark_value
            payload = self._calculate_regime_validation_payload(
                target_index=target_index,
                benchmark_index=benchmark_index,
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": str(error)})

    def _send_regime_validation_universe(self) -> None:
        store = _get_eod_store()
        stock_names = {
            str(item["display_name"])
            for item in store.list_instruments(kind="stock")
        }
        payload = build_regime_validation_universe(
            store.list_instruments(kind="index"),
            stock_names=stock_names,
            constituent_snapshot=load_index_constituent_snapshot(),
        )
        self._send_json(HTTPStatus.OK, payload)

    def _send_cross_index_validation(self) -> None:
        try:
            payload = self._calculate_cross_index_validation_payload()
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": str(error)})

    @staticmethod
    def _calculate_cross_index_validation_payload() -> dict[str, object]:
        store = _get_eod_store()
        index_inventory = store.list_instruments(kind="index")
        stock_inventory = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock", display_name=str(item["display_name"])
            )
            for item in stock_inventory
        }
        constituent_snapshot = load_index_constituent_snapshot()
        readiness = build_regime_validation_universe(
            index_inventory,
            stock_names=set(stock_histories),
            constituent_snapshot=constituent_snapshot,
        )
        histories = {
            name: store.load_candles(kind="index", display_name=name)
            for name in SEASONALITY_INDICES
        }
        india_vix_candles = store.load_candles(kind="index", display_name="India VIX")
        nifty50_candles = histories.get("Nifty 50", [])
        institutional_flow_rows = store.load_institutional_flows()
        confirmed_fpi_rows = store.load_confirmed_fpi_investments()
        macro_snapshot_rows = store.load_macro_snapshots()
        global_risk_rows = store.load_global_risk_observations()
        futures_snapshot_rows = store.load_futures_eod_snapshots()
        external_rows = {
            "institutional": institutional_flow_rows,
            "confirmed_fpi": confirmed_fpi_rows,
            "macro": macro_snapshot_rows,
            "global": global_risk_rows,
            "futures": futures_snapshot_rows,
        }
        external_readiness = build_regime_external_cluster_readiness(
            institutional_flow_rows=institutional_flow_rows,
            confirmed_fpi_rows=confirmed_fpi_rows,
            macro_snapshot_rows=macro_snapshot_rows,
            global_risk_rows=global_risk_rows,
            futures_snapshot_rows=futures_snapshot_rows,
        )
        futures_history_row = next(
            (
                item
                for item in external_readiness["rows"]
                if item["key"] == "kite_futures_oi"
            ),
            {},
        )
        futures_oi_summary = calculate_futures_oi_summary(futures_snapshot_rows)
        cache_contract = {
            "rule_version": REGIME_RULE_VERSION,
            "recovery_contract": (
                REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
                REGIME_RECOVERY_MAXIMUM_SESSIONS,
            ),
            "directional_contract": (
                REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
                REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
                REGIME_LONG_HORIZON_SESSIONS,
                REGIME_SHORT_HORIZON_SESSIONS,
                REGIME_RISK_TAIL_PERCENTILE,
                REGIME_ADVERSE_DISTANCE_LEVELS_PCT,
                REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT,
                REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT,
                REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT,
            ),
            "constituent_snapshot_as_of": constituent_snapshot.get("as_of"),
            "constituent_membership_history": {
                name: [
                    (
                        item["effective_from"].isoformat(),
                        item["effective_to"].isoformat() if item["effective_to"] else None,
                        item["symbols"],
                    )
                    for item in snapshots
                ]
                for name, snapshots in constituent_snapshot.get("history", {}).items()
            },
            "indices": [
                (
                    name,
                    len(history),
                    history[-1]["date"].isoformat() if history else None,
                )
                for name, history in sorted(histories.items())
            ],
            "stocks": [
                (
                    name,
                    len(history),
                    history[-1]["date"].isoformat() if history else None,
                )
                for name, history in sorted(stock_histories.items())
            ],
            "external_history": {
                key: (
                    len(rows),
                    max(
                        (item["date"].isoformat() for item in rows if isinstance(item.get("date"), date)),
                        default=None,
                    ),
                )
                for key, rows in external_rows.items()
            },
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with _CROSS_INDEX_VALIDATION_LOCK:
            if _CROSS_INDEX_VALIDATION_CACHE.get("key") == cache_key:
                cached = _CROSS_INDEX_VALIDATION_CACHE.get("payload")
                if isinstance(cached, dict):
                    payload = json.loads(json.dumps(cached))
                    payload["cache_hit"] = True
                    return payload

            rows: list[dict[str, object]] = []
            excluded: list[dict[str, object]] = []
            constituent_indices = constituent_snapshot["indices"]
            constituent_history = constituent_snapshot.get("history", {})
            for state in readiness["indices"]:
                name = str(state["display_name"])
                if not state["validation_ready"]:
                    reason = (
                        "insufficient_history"
                        if not state["walk_forward_ready"]
                        else "insufficient_fno_constituent_breadth"
                    )
                    excluded.append({"index": name, "reason": reason})
                    continue
                validation = calculate_regime_walk_forward_validation(
                    histories[name],
                    stock_histories,
                    india_vix_candles=india_vix_candles,
                    target_index=name,
                    benchmark_candles=nifty50_candles,
                    benchmark_index="Nifty 50" if name != "Nifty 50" else None,
                    constituent_symbols=constituent_indices[name],
                    constituent_membership_history=constituent_history.get(name, []),
                    constituent_snapshot_as_of=str(constituent_snapshot.get("as_of") or ""),
                    institutional_flow_rows=institutional_flow_rows,
                    confirmed_fpi_rows=confirmed_fpi_rows,
                    macro_snapshot_rows=macro_snapshot_rows,
                    global_risk_rows=global_risk_rows,
                    futures_snapshot_rows=futures_snapshot_rows,
                )
                metrics = validation["overall"]["horizons"]["20"]
                transition = validation.get("transition_analysis", {})
                recovery_state = next(
                    (
                        row
                        for row in transition.get("by_state", [])
                        if row.get("label_key") == "recovering_market"
                    ),
                    None,
                )
                recovery_metrics = (
                    recovery_state.get("horizons", {}).get("20", {})
                    if isinstance(recovery_state, dict) else {}
                )
                recovery_exits = transition.get("exit_counts", {})
                directional_states = transition.get("directional_state_evidence", [])
                long_states = [
                    item
                    for item in directional_states
                    if item.get("research_bias") == "long_research_candidate"
                ]
                short_states = [
                    item
                    for item in directional_states
                    if item.get("research_bias") == "short_research_candidate"
                ]
                long_state = max(
                    long_states,
                    key=lambda item: (
                        float(item["median_excess_return_pct"])
                        if item.get("median_excess_return_pct") is not None
                        else float(item["median_return_pct"])
                    ),
                    default=None,
                )
                short_state = min(
                    short_states,
                    key=lambda item: (
                        float(item["median_excess_return_pct"])
                        if item.get("median_excess_return_pct") is not None
                        else float(item["median_return_pct"])
                    ),
                    default=None,
                )
                recovery_incremental = transition.get(
                    "recovery_incremental_evidence", {}
                )
                current_state = validation.get("current_state", {})
                current_transition_key = current_state.get("transition_label_key")
                matched_state_evidence = next(
                    (
                        item
                        for item in directional_states
                        if item.get("label_key") == current_transition_key
                    ),
                    None,
                )
                futures_confirmation = build_index_futures_confirmation(
                    constituent_indices[name],
                    fno_constituent_count=int(
                        validation["breadth_universe"]["fno_constituent_count"]
                    ),
                    futures_summary=futures_oi_summary,
                    history_ready=bool(futures_history_row.get("history_ready")),
                    current_state_date=(
                        str(current_state.get("as_of_date"))
                        if current_state.get("as_of_date") else None
                    ),
                )
                is_benchmark = name == "Nifty 50"
                if is_benchmark:
                    current_decision = "market_context_only"
                elif not current_state.get("classification_ready"):
                    current_decision = "insufficient_evidence"
                elif not isinstance(matched_state_evidence, dict):
                    current_decision = "insufficient_evidence"
                elif matched_state_evidence.get("research_bias") == "long_research_candidate":
                    current_decision = "long_candidate"
                elif matched_state_evidence.get("research_bias") == "short_research_candidate":
                    if futures_confirmation["short_gate_passed"]:
                        current_decision = "short_candidate"
                    elif not futures_confirmation["history_ready"]:
                        current_decision = "short_watch_history_building"
                    elif not futures_confirmation["current_confirmation_ready"]:
                        current_decision = "short_watch_unconfirmed"
                    else:
                        current_decision = "avoid_no_short_confirmation"
                elif matched_state_evidence.get("research_bias") == "countertrend_rebound_study":
                    current_decision = "countertrend_watch"
                elif matched_state_evidence.get("research_bias") == "tactical_rebound_study":
                    current_decision = "tactical_watch"
                elif matched_state_evidence.get("research_bias") == "reversal_short_study":
                    current_decision = "reversal_watch"
                elif matched_state_evidence.get("research_bias") == "insufficient_sample":
                    current_decision = "insufficient_evidence"
                else:
                    current_decision = "avoid_no_validated_edge"
                rows.append(
                    {
                        "index": name,
                        "is_benchmark": is_benchmark,
                        "sessions": validation["overall"]["sessions"],
                        "median_return_pct": metrics["median_return_pct"],
                        "positive_rate_pct": metrics["positive_rate_pct"],
                        "median_excess_return_pct": 0.0 if is_benchmark else metrics["median_excess_return_pct"],
                        "outperformance_rate_pct": None if is_benchmark else metrics["outperformance_rate_pct"],
                        "worst_max_drawdown_pct": metrics["worst_max_drawdown_pct"],
                        "worst_relative_drawdown_pct": 0.0 if is_benchmark else metrics["worst_relative_drawdown_pct"],
                        "official_constituent_count": validation["breadth_universe"]["official_constituent_count"],
                        "fno_constituent_count": validation["breadth_universe"]["fno_constituent_count"],
                        "evaluation_start": validation["evaluation_start"],
                        "evaluation_end": validation["evaluation_end"],
                        "recovery_episode_count": int(transition.get("episode_count") or 0),
                        "recovery_sessions": int(
                            recovery_state.get("sessions") or 0
                            if isinstance(recovery_state, dict) else 0
                        ),
                        "recovery_positive_exit_count": int(
                            recovery_exits.get("positive_market_confirmed") or 0
                        ),
                        "recovery_relapse_count": int(
                            recovery_exits.get("relapsed_to_risk") or 0
                        ),
                        "recovery_timeout_count": int(
                            recovery_exits.get("maximum_window_reached") or 0
                        ),
                        "recovery_open_count": int(recovery_exits.get("still_open") or 0),
                        "recovery_20d_median_return_pct": recovery_metrics.get(
                            "median_return_pct"
                        ),
                        "recovery_20d_positive_rate_pct": recovery_metrics.get(
                            "positive_rate_pct"
                        ),
                        "recovery_20d_worst_return_pct": recovery_metrics.get(
                            "worst_return_pct"
                        ),
                        "recovery_20d_worst_drawdown_pct": recovery_metrics.get(
                            "worst_max_drawdown_pct"
                        ),
                        "recovery_20d_median_excess_return_pct": (
                            0.0
                            if is_benchmark and recovery_metrics
                            else recovery_metrics.get("median_excess_return_pct")
                        ),
                        "recovery_20d_outperformance_rate_pct": (
                            None
                            if is_benchmark else recovery_metrics.get("outperformance_rate_pct")
                        ),
                        "recovery_comparable_base_sessions": int(
                            recovery_incremental.get("comparable_base_sessions") or 0
                        ),
                        "recovery_base_20d_median_return_pct": (
                            recovery_incremental.get("comparable_base_20d", {}).get(
                                "median_return_pct"
                            )
                        ),
                        "recovery_incremental_median_return_pct": recovery_incremental.get(
                            "delta_median_return_pct"
                        ),
                        "recovery_incremental_positive_rate_pct": recovery_incremental.get(
                            "delta_positive_rate_pct"
                        ),
                        "recovery_incremental_status": recovery_incremental.get("status"),
                        "historical_long_state": long_state,
                        "historical_short_state": short_state,
                        "current_state": current_state,
                        "current_state_historical_evidence": matched_state_evidence,
                        "futures_short_confirmation": futures_confirmation,
                        "current_decision": current_decision,
                    }
                )
            rows.sort(
                key=lambda row: (
                    -float(row["median_excess_return_pct"])
                    if row["median_excess_return_pct"] is not None else math.inf,
                    str(row["index"]),
                )
            )
            for rank, row in enumerate(rows, start=1):
                row["rank"] = rank
            decision_priority = {
                "long_candidate": 0,
                "short_candidate": 1,
                "short_watch_unconfirmed": 2,
                "short_watch_history_building": 3,
                "countertrend_watch": 4,
                "tactical_watch": 5,
                "reversal_watch": 6,
                "avoid_no_short_confirmation": 7,
                "avoid_no_validated_edge": 8,
                "insufficient_evidence": 9,
                "market_context_only": 10,
            }
            decision_rows = sorted(
                rows,
                key=lambda row: (
                    decision_priority.get(str(row["current_decision"]), 9),
                    -float(
                        (row.get("current_state_historical_evidence") or {}).get(
                            "median_excess_return_pct"
                        )
                        or (row.get("current_state_historical_evidence") or {}).get(
                            "median_return_pct"
                        )
                        or 0
                    )
                    if row["current_decision"] == "long_candidate"
                    else float(
                        (row.get("current_state_historical_evidence") or {}).get(
                            "median_excess_return_pct"
                        )
                        or (row.get("current_state_historical_evidence") or {}).get(
                            "median_return_pct"
                        )
                        or 0
                    )
                    if row["current_decision"] == "short_candidate"
                    else 0,
                    str(row["index"]),
                ),
            )
            for rank, row in enumerate(decision_rows, start=1):
                row["decision_rank"] = rank
            payload = {
                "ok": True,
                "status": "historical_exploratory_comparison",
                "horizon_sessions": 20,
                "benchmark": "Nifty 50",
                "constituent_snapshot_as_of": constituent_snapshot.get("as_of"),
                "rows": rows,
                "current_decision_rows": decision_rows,
                "recovery_state_contract": {
                    "minimum_prior_risk_sessions": REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
                    "maximum_recovery_sessions": REGIME_RECOVERY_MAXIMUM_SESSIONS,
                    "status": "validation_only_outcome_blind_rule",
                    "eligible_indices": sum(
                        int(row["recovery_episode_count"] > 0) for row in rows
                    ),
                },
                "directional_research_contract": {
                    "minimum_state_sessions": REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
                    "absolute_median_return_threshold_pct": REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
                    "positive_rate_long_threshold_pct": REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                    "positive_rate_short_threshold_pct": 100
                    - REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                    "relative_median_excess_threshold_pct": REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
                    "long_horizon_sessions": REGIME_LONG_HORIZON_SESSIONS,
                    "short_horizon_sessions": REGIME_SHORT_HORIZON_SESSIONS,
                    "tail_percentile": REGIME_RISK_TAIL_PERCENTILE,
                    "adverse_distance_levels_pct": list(REGIME_ADVERSE_DISTANCE_LEVELS_PCT),
                    "status": "historical_research_only_not_live_signal",
                },
                "futures_short_confirmation_contract": {
                    "history_sessions_required": REGIME_EXTERNAL_HISTORY_SESSIONS,
                    "stored_history_sessions": int(
                        futures_history_row.get("stored_sessions") or 0
                    ),
                    "history_ready": bool(futures_history_row.get("history_ready")),
                    "minimum_clear_constituent_states": REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT,
                    "minimum_constituent_coverage_pct": REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT,
                    "minimum_bearish_share_pct": REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT,
                    "status": "confirmation_gate_not_trading_signal",
                },
                "excluded": excluded,
                "limitations": [
                    "Long research uses 20-session outcomes; downside-continuation research uses 5-session outcomes. Neither is a trade signal.",
                    "Tail loss, adverse excursion, and distance-breach rates are historical risk evidence, not stop or position-size recommendations.",
                    "Breadth uses current constituents within the current liquid F&O universe and carries survivorship bias.",
                    "Overlapping forward windows are descriptive rather than independent observations.",
                ],
                "cache_hit": False,
            }
            _CROSS_INDEX_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.update({"key": cache_key, "payload": payload})
            return payload

    @staticmethod
    def _calculate_regime_validation_payload(
        *,
        target_index: str = "Nifty 50",
        benchmark_index: str | None = None,
    ) -> dict[str, object]:
        store = _get_eod_store()
        index_candles = store.load_candles(kind="index", display_name=target_index)
        benchmark_candles = (
            store.load_candles(kind="index", display_name=benchmark_index)
            if benchmark_index else []
        )
        india_vix_candles = store.load_candles(kind="index", display_name="India VIX")
        instruments = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock", display_name=str(item["display_name"])
            )
            for item in instruments
        }
        constituent_snapshot = load_index_constituent_snapshot()
        institutional_flow_rows = store.load_institutional_flows()
        confirmed_fpi_rows = store.load_confirmed_fpi_investments()
        macro_snapshot_rows = store.load_macro_snapshots()
        global_risk_rows = store.load_global_risk_observations()
        futures_snapshot_rows = store.load_futures_eod_snapshots()
        external_rows = {
            "institutional": institutional_flow_rows,
            "confirmed_fpi": confirmed_fpi_rows,
            "macro": macro_snapshot_rows,
            "global": global_risk_rows,
            "futures": futures_snapshot_rows,
        }
        constituent_indices = constituent_snapshot["indices"]
        constituent_symbols = constituent_indices.get(target_index, [])
        if not constituent_symbols:
            raise ValueError("index_constituent_snapshot_unavailable")
        cache_contract = {
            "rule_version": REGIME_RULE_VERSION,
            "recovery_contract": (
                REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
                REGIME_RECOVERY_MAXIMUM_SESSIONS,
            ),
            "directional_contract": (
                REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
                REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
                REGIME_LONG_HORIZON_SESSIONS,
                REGIME_SHORT_HORIZON_SESSIONS,
                REGIME_RISK_TAIL_PERCENTILE,
                REGIME_ADVERSE_DISTANCE_LEVELS_PCT,
            ),
            "target_index": target_index,
            "benchmark_index": benchmark_index,
            "index_sessions": len(index_candles),
            "index_latest": index_candles[-1]["date"].isoformat() if index_candles else None,
            "vix_sessions": len(india_vix_candles),
            "vix_latest": india_vix_candles[-1]["date"].isoformat() if india_vix_candles else None,
            "benchmark_sessions": len(benchmark_candles),
            "benchmark_latest": benchmark_candles[-1]["date"].isoformat() if benchmark_candles else None,
            "constituent_snapshot_as_of": constituent_snapshot.get("as_of"),
            "constituent_symbols": constituent_symbols,
            "constituent_membership_history": [
                (
                    item["effective_from"].isoformat(),
                    item["effective_to"].isoformat() if item["effective_to"] else None,
                    item["symbols"],
                )
                for item in constituent_snapshot.get("history", {}).get(target_index, [])
            ],
            "stocks": [
                (
                    name,
                    len(history),
                    history[-1]["date"].isoformat() if history else None,
                )
                for name, history in sorted(stock_histories.items())
            ],
            "external_history": {
                key: (
                    len(rows),
                    max(
                        (item["date"].isoformat() for item in rows if isinstance(item.get("date"), date)),
                        default=None,
                    ),
                )
                for key, rows in external_rows.items()
            },
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with _REGIME_VALIDATION_LOCK:
            if _REGIME_VALIDATION_CACHE.get("key") == cache_key:
                cached = _REGIME_VALIDATION_CACHE.get("payload")
                if isinstance(cached, dict):
                    payload = json.loads(json.dumps(cached))
                    payload["cache_hit"] = True
                    return payload
            payload = calculate_regime_walk_forward_validation(
                index_candles,
                stock_histories,
                india_vix_candles=india_vix_candles,
                target_index=target_index,
                benchmark_candles=benchmark_candles,
                benchmark_index=benchmark_index,
                constituent_symbols=constituent_symbols,
                constituent_membership_history=constituent_snapshot.get("history", {}).get(
                    target_index, []
                ),
                constituent_snapshot_as_of=str(constituent_snapshot.get("as_of") or ""),
                institutional_flow_rows=institutional_flow_rows,
                confirmed_fpi_rows=confirmed_fpi_rows,
                macro_snapshot_rows=macro_snapshot_rows,
                global_risk_rows=global_risk_rows,
                futures_snapshot_rows=futures_snapshot_rows,
            )
            payload["cache_hit"] = False
            _REGIME_VALIDATION_CACHE.clear()
            _REGIME_VALIDATION_CACHE.update({"key": cache_key, "payload": payload})
            return payload

    @staticmethod
    def _calculate_sentiment_payload() -> dict[str, object]:
        store = _get_eod_store()
        index_candles = store.load_candles(kind="index", display_name="Nifty 50")
        india_vix_candles = store.load_candles(kind="index", display_name="India VIX")
        institutional_flow_rows = store.load_institutional_flows()
        confirmed_fpi_rows = store.load_confirmed_fpi_investments()
        macro_snapshot_rows = store.load_macro_snapshots()
        global_risk_rows = store.load_global_risk_observations()
        futures_snapshot_rows = store.load_futures_eod_snapshots()
        instruments = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock", display_name=str(item["display_name"])
            )
            for item in instruments
        }
        return calculate_domestic_sentiment_core(
            index_candles,
            stock_histories,
            india_vix_candles=india_vix_candles,
            institutional_flow_rows=institutional_flow_rows,
            confirmed_fpi_rows=confirmed_fpi_rows,
            macro_snapshot_rows=macro_snapshot_rows,
            global_risk_rows=global_risk_rows,
            futures_snapshot_rows=futures_snapshot_rows,
        )

    def _send_sentiment_factor_snapshot(self) -> None:
        try:
            payload = self._calculate_sentiment_payload()
            evidence = json.loads(json.dumps(payload, allow_nan=False))
            candidate_regime = evidence.pop("candidate_regime", None)
            freshness = evidence.get("freshness")
            if isinstance(freshness, dict):
                freshness.pop("retrieved_at", None)
            as_of_date = date.fromisoformat(str(payload["as_of_date"]))
            write_result = _get_eod_store().append_sentiment_factor_snapshot(
                as_of_date=as_of_date,
                model_version=SENTIMENT_EVIDENCE_MODEL_VERSION,
                evidence=evidence,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "as_of_date": as_of_date.isoformat(),
                    "model_version": SENTIMENT_EVIDENCE_MODEL_VERSION,
                    "candidate_rule_version": (
                        candidate_regime.get("rule_version")
                        if isinstance(candidate_regime, dict)
                        else REGIME_RULE_VERSION
                    ),
                    "write_result": write_result,
                },
            )
        except (KeyError, TypeError, ValueError) as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error) or "sentiment_factor_snapshot_unavailable"},
            )

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
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
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
            from_date = now.date() - timedelta(days=400)
            store = _get_eod_store()
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
                candles = parse_daily_candles(
                    provider_payload or {}, today=now.date(), now_time=now.time().replace(tzinfo=None)
                )
                history = [(row["date"], float(row["close"])) for row in candles]
                if display_name == "India VIX":
                    try:
                        store.append_candles(
                            kind="index",
                            display_name=display_name,
                            provider_token=tokens[display_name],
                            candles=candles,
                            retrieved_at=datetime.now(timezone.utc).isoformat(),
                        )
                    except CandleConflictError as error:
                        raise ValueError("stored_candle_conflict") from error
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
            seasonality_tokens = dict(_ACTIVE_SEASONALITY_INDEX_TOKENS)
        if cached and seasonality_tokens:
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
            seasonality_index_tokens = parse_seasonality_index_tokens(csv_payload or "")
        except ValueError as error:
            raise ValueError(str(error)) from error
        with _SESSION_LOCK:
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_INDEX_TARGETS.extend(targets)
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.update(dashboard_index_tokens)
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_SEASONALITY_INDEX_TOKENS.update(seasonality_index_tokens)
            _ACTIVE_EQUITY_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.update(equity_tokens)
        return targets, missing

    def _send_seasonality(self, raw_query: str) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        query = urllib.parse.parse_qs(raw_query, keep_blank_values=True)
        kinds = query.get("kind", [])
        instruments = query.get("instrument", [])
        if len(kinds) != 1 or len(instruments) != 1:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_seasonality_request"})
            return
        kind = kinds[0]
        instrument = instruments[0]
        if kind not in {"index", "stock"} or not instrument or len(instrument) > 64 or instrument.strip() != instrument:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_seasonality_request"})
            return

        cache_key = (kind, instrument)
        with _SESSION_LOCK:
            cached = _SEASONALITY_CACHE.get(cache_key)
        if cached and time.monotonic() - float(cached["created_at"]) < SEASONALITY_CACHE_SECONDS:
            cached_payload = cached.get("payload")
            if is_complete_seasonality_payload(cached_payload):
                self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
                return
            with _SESSION_LOCK:
                _SEASONALITY_CACHE.pop(cache_key, None)

        try:
            if kind == "index":
                if instrument not in SEASONALITY_INDICES:
                    raise ValueError("instrument_not_available")
                self._current_index_targets(api_key, access_token)
                with _SESSION_LOCK:
                    token = _ACTIVE_SEASONALITY_INDEX_TOKENS.get(instrument)
            else:
                symbol = instrument.upper()
                if symbol != instrument or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol):
                    raise ValueError("instrument_not_available")
                token = self._current_equity_tokens(api_key, access_token).get(symbol)
            if token is None:
                raise ValueError("instrument_not_available")
            payload = self._build_seasonality(api_key, access_token, token, kind, instrument)
            with _SESSION_LOCK:
                _SEASONALITY_CACHE[cache_key] = {
                    "payload": payload,
                    "created_at": time.monotonic(),
                }
            self._send_json(HTTPStatus.OK, {**payload, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})

    def _build_seasonality(
        self,
        api_key: str,
        access_token: str,
        token: str,
        kind: str,
        instrument: str,
    ) -> dict[str, object]:
        now = datetime.now(INDIA_TIMEZONE)
        completed_through = completed_history_date(now)
        history_start = historical_lookback_start(completed_through)
        store = _get_eod_store()
        coverage_before = store.coverage(kind=kind, display_name=instrument)
        last_stored = coverage_before["last_session"]
        sync_start = max(history_start, last_stored + timedelta(days=1)) if last_stored else history_start
        ranges = incremental_history_ranges(history_start, completed_through, last_stored)
        inserted_sessions = 0
        duplicate_sessions = 0
        for index, (from_date, to_date) in enumerate(ranges):
            if index:
                time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
            query = urllib.parse.urlencode(
                {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                    "continuous": "0",
                    "oi": "0",
                }
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
            provider_payload, reason = self._request_provider_json(
                request,
                exchange=False,
                maximum_bytes=MAX_HISTORICAL_RESPONSE_BYTES,
            )
            if reason is not None:
                raise ValueError(reason)
            parsed_candles = parse_daily_candles(
                provider_payload or {},
                today=now.date(),
                now_time=now.time().replace(tzinfo=None),
            )
            try:
                write_result = store.append_candles(
                    kind=kind,
                    display_name=instrument,
                    provider_token=token,
                    candles=parsed_candles,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                )
            except CandleConflictError as error:
                raise ValueError("stored_candle_conflict") from error
            inserted_sessions += write_result["inserted"]
            duplicate_sessions += write_result["duplicates"]

        candles = store.load_candles(
            kind=kind,
            display_name=instrument,
            start=history_start,
            end=completed_through,
        )
        if len(candles) < 2:
            raise ValueError("no_completed_historical_data")
        month_rows, weekday_rows = calculate_seasonality(candles, today=now.date())
        validation = calculate_seasonality_validation(candles, today=now.date())
        return {
            "ok": True,
            "instrument": instrument,
            "kind": kind,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "from_date": candles[0]["date"].isoformat(),
            "as_of_date": candles[-1]["date"].isoformat(),
            "completed_sessions": len(candles),
            "historical_requests": len(ranges),
            "persistent_store": True,
            "stored_sessions_before_sync": coverage_before["session_count"],
            "new_sessions": inserted_sessions,
            "duplicate_sessions": duplicate_sessions,
            "local_history_reused": coverage_before["session_count"] > 0,
            "sync_from_date": sync_start.isoformat() if ranges else None,
            "month_rows": month_rows,
            "weekday_rows": weekday_rows,
            **validation,
            "return_definition": "close-to-close percentage change",
            "range_definition": "(high - low) / low * 100",
            "price_source": "Kite Connect historical daily candles",
        }

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
        monthly_returns = calculate_month_to_date_returns(histories, as_of=as_of)
        with _SESSION_LOCK:
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.update(
                {"as_of": as_of, "returns": monthly_returns}
            )
            _MONTHLY_LEADERS_CACHE.clear()
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

    def _send_monthly_leaders(self, payload: dict[str, object]) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
            equity_snapshot = dict(_MONTHLY_EQUITY_RETURNS_CACHE)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        raw_symbols = payload.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or not raw_symbols
            or len(raw_symbols) > 250
            or any(
                not isinstance(symbol, str)
                or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
                for symbol in raw_symbols
            )
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_monthly_leader_request"})
            return
        symbols = tuple(sorted(set(raw_symbols)))
        if len(symbols) != len(raw_symbols):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_monthly_leader_request"})
            return

        as_of = equity_snapshot.get("as_of")
        equity_returns = equity_snapshot.get("returns")
        if not isinstance(as_of, date) or not isinstance(equity_returns, dict):
            self._send_json(HTTPStatus.CONFLICT, {"ok": False, "reason": "monthly_stock_data_not_ready"})
            return
        eligible_stock_returns = {
            symbol: float(equity_returns[symbol])
            for symbol in symbols
            if symbol in equity_returns
        }
        if not eligible_stock_returns:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": "monthly_stock_data_unavailable"})
            return

        cache_key = hashlib.sha256("\n".join(symbols).encode("ascii")).hexdigest()
        with _SESSION_LOCK:
            cached_key = _MONTHLY_LEADERS_CACHE.get("key")
            cached_payload = _MONTHLY_LEADERS_CACHE.get("payload")
            cached_at = _MONTHLY_LEADERS_CACHE.get("created_at")
        if (
            cached_key == cache_key
            and isinstance(cached_payload, dict)
            and isinstance(cached_at, (int, float))
            and time.monotonic() - float(cached_at) < SEASONALITY_CACHE_SECONDS
        ):
            self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
            return

        try:
            self._current_index_targets(api_key, access_token)
            with _SESSION_LOCK:
                index_tokens = dict(_ACTIVE_SEASONALITY_INDEX_TOKENS)
            missing = [name for name in SEASONALITY_INDICES if name not in index_tokens]
            if missing:
                raise ValueError("instrument_not_available")
            month_start = date(as_of.year, as_of.month, 1)
            from_date = month_start - timedelta(days=10)
            index_histories: dict[str, list[tuple[date, float]]] = {}
            now = datetime.now(INDIA_TIMEZONE)
            for index, display_name in enumerate(SEASONALITY_INDICES):
                if index:
                    time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                query = urllib.parse.urlencode(
                    {
                        "from": from_date.isoformat(),
                        "to": as_of.isoformat(),
                        "continuous": "0",
                        "oi": "0",
                    }
                )
                request = urllib.request.Request(
                    f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=index_tokens[display_name])}?{query}",
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
                index_histories[display_name] = parse_daily_closes(
                    provider_payload or {},
                    today=now.date(),
                    now_time=now.time().replace(tzinfo=None),
                )
            index_returns = calculate_month_to_date_returns(index_histories, as_of=as_of)
            if "Nifty 50" not in index_returns or not index_returns:
                raise ValueError("monthly_index_data_unavailable")
            best_index = max(index_returns.items(), key=lambda item: (item[1], item[0]))
            best_stock = max(eligible_stock_returns.items(), key=lambda item: (item[1], item[0]))
            result: dict[str, object] = {
                "ok": True,
                "as_of_date": as_of.isoformat(),
                "month": as_of.strftime("%B %Y"),
                "nifty50_mtd_pct": index_returns["Nifty 50"],
                "best_index": {"instrument": best_index[0], "return_pct": best_index[1]},
                "best_stock": {"instrument": best_stock[0], "return_pct": best_stock[1]},
                "indices_evaluated": len(index_returns),
                "fo_stocks_evaluated": len(eligible_stock_returns),
                "return_definition": "last completed close versus previous month final close",
            }
            with _SESSION_LOCK:
                _MONTHLY_LEADERS_CACHE.clear()
                _MONTHLY_LEADERS_CACHE.update(
                    {"key": cache_key, "payload": result, "created_at": time.monotonic()}
                )
            self._send_json(HTTPStatus.OK, {**result, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})

    def _send_historical_month_leaders(self, payload: dict[str, object]) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        raw_symbols = payload.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or not raw_symbols
            or len(raw_symbols) > 250
            or any(
                not isinstance(symbol, str)
                or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
                for symbol in raw_symbols
            )
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_historical_month_leader_request"},
            )
            return
        symbols = tuple(sorted(set(raw_symbols)))
        if len(symbols) != len(raw_symbols):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_historical_month_leader_request"},
            )
            return

        selected_month = payload.get("month")
        if (
            not isinstance(selected_month, int)
            or isinstance(selected_month, bool)
            or selected_month < 1
            or selected_month > 12
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_historical_month_leader_request"},
            )
            return

        now = datetime.now(INDIA_TIMEZONE)
        price_history_through = completed_history_date(now)
        cache_key = hashlib.sha256(
            f"{selected_month}\n{SEASONALITY_LOOKBACK_YEARS}\n".encode("ascii")
            + "\n".join(symbols).encode("ascii")
        ).hexdigest()
        with _SESSION_LOCK:
            cached_key = _HISTORICAL_MONTH_LEADERS_CACHE.get("key")
            cached_payload = _HISTORICAL_MONTH_LEADERS_CACHE.get("payload")
        if (
            cached_key == cache_key
            and isinstance(cached_payload, dict)
            and cached_payload.get("price_history_requested_through")
            == price_history_through.isoformat()
        ):
            self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
            return
        if not _HISTORICAL_MONTH_LEADERS_LOCK.acquire(blocking=False):
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "historical_rank_refresh_in_progress"},
            )
            return

        try:
            self._current_index_targets(api_key, access_token)
            with _SESSION_LOCK:
                index_tokens = dict(_ACTIVE_SEASONALITY_INDEX_TOKENS)
            equity_tokens = self._current_equity_tokens(api_key, access_token)
            if any(name not in index_tokens for name in SEASONALITY_INDICES):
                raise ValueError("instrument_not_available")
            if any(symbol not in equity_tokens for symbol in symbols):
                raise ValueError("instrument_not_available")

            month_index = selected_month - 1
            index_averages: dict[str, tuple[float, int]] = {}
            stock_averages: dict[str, tuple[float, int]] = {}
            total_requests = 0
            history_start = historical_lookback_start(now.date())
            store = _get_eod_store()

            def evaluate(kind: str, instrument: str, token: str) -> tuple[float, int] | None:
                nonlocal total_requests
                coverage = store.coverage(kind=kind, display_name=instrument)
                last_stored = coverage["last_session"]
                needs_sync = last_stored is None or last_stored < price_history_through
                with _SESSION_LOCK:
                    cache_item = _SEASONALITY_CACHE.get((kind, instrument))
                cached = None
                if cache_item and time.monotonic() - float(cache_item["created_at"]) < SEASONALITY_CACHE_SECONDS:
                    cached = cache_item.get("payload")
                if needs_sync:
                    if total_requests:
                        time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                    try:
                        cached = self._build_seasonality(
                            api_key, access_token, token, kind, instrument
                        )
                    except ValueError as error:
                        if str(error) == "no_completed_historical_data":
                            return None
                        raise
                    total_requests += int(cached.get("historical_requests", 0))
                elif not isinstance(cached, dict):
                    stored_candles = store.load_candles(
                        kind=kind,
                        display_name=instrument,
                        start=history_start,
                        end=now.date(),
                    )
                    if len(stored_candles) >= 2:
                        month_rows, _weekday_rows = calculate_seasonality(
                            stored_candles, today=now.date()
                        )
                        cached = {"month_rows": month_rows, "historical_requests": 0}
                    else:
                        if total_requests:
                            time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                        try:
                            cached = self._build_seasonality(
                                api_key, access_token, token, kind, instrument
                            )
                        except ValueError as error:
                            if str(error) == "no_completed_historical_data":
                                return None
                            raise
                        total_requests += int(cached.get("historical_requests", 0))
                    if is_complete_seasonality_payload(cached):
                        with _SESSION_LOCK:
                            _SEASONALITY_CACHE[(kind, instrument)] = {
                                "payload": cached,
                                "created_at": time.monotonic(),
                            }
                month_rows = cached.get("month_rows")
                if not isinstance(month_rows, list) or len(month_rows) != 12:
                    raise ValueError("invalid_provider_response")
                row = month_rows[month_index]
                if not isinstance(row, dict):
                    raise ValueError("invalid_provider_response")
                count = row.get("count")
                average = row.get("average_return_pct")
                if not isinstance(count, int) or count < 1 or not isinstance(average, (int, float)):
                    return None
                return float(average), count

            for instrument in SEASONALITY_INDICES:
                value = evaluate("index", instrument, index_tokens[instrument])
                if value is not None:
                    index_averages[instrument] = value
            for symbol in symbols:
                value = evaluate("stock", symbol, equity_tokens[symbol])
                if value is not None:
                    stock_averages[symbol] = value

            index_rank = rank_historical_month_averages(index_averages)
            stock_rank = rank_historical_month_averages(stock_averages)
            result: dict[str, object] = {
                "ok": True,
                "calendar_month": date(2000, selected_month, 1).strftime("%B"),
                "month": selected_month,
                "completed_year": now.year - 1,
                "history_start": historical_lookback_start(now.date()).isoformat(),
                "lookback_years": SEASONALITY_LOOKBACK_YEARS,
                "completed_through": (date(now.year, now.month, 1) - timedelta(days=1)).isoformat(),
                "index": index_rank,
                "stock": stock_rank,
                "indices_requested": len(SEASONALITY_INDICES),
                "stocks_requested": len(symbols),
                "indices_without_history": len(SEASONALITY_INDICES) - int(index_rank["evaluated"]),
                "stocks_without_history": len(symbols) - int(stock_rank["evaluated"]),
                "historical_requests": total_requests,
                "price_history_requested_through": price_history_through.isoformat(),
                "return_definition": "mean close-to-close return for the selected calendar month across completed years",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
            with _SESSION_LOCK:
                _HISTORICAL_MONTH_LEADERS_CACHE.clear()
                _HISTORICAL_MONTH_LEADERS_CACHE.update({"key": cache_key, "payload": result})
            self._send_json(HTTPStatus.OK, {**result, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
        finally:
            _HISTORICAL_MONTH_LEADERS_LOCK.release()

    def _send_institutional_flow_refresh(self) -> None:
        request = urllib.request.Request(
            NSE_FII_DII_URL,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.nseindia.com/reports/fii-dii",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        text_payload, reason = self._request_provider_text(request, MAX_RESPONSE_BYTES)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "institutional_flow_source_unavailable"},
            )
            return
        try:
            parsed_payload = json.loads(text_payload or "")
            rows = parse_institutional_flows(parsed_payload, today=datetime.now(INDIA_TIMEZONE).date())
            store = _get_eod_store()
            write_result = store.append_institutional_flows(
                rows,
                source=NSE_FII_DII_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_institutional_flow_summary(store.load_institutional_flows())
        except InstitutionalFlowConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_institutional_flow_conflict"},
            )
            return
        except (json.JSONDecodeError, ValueError):
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_institutional_flow_response"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {"ok": True, **summary, "write_result": write_result},
        )

    def _send_confirmed_fpi_refresh(self) -> None:
        request = urllib.request.Request(
            NSDL_FPI_MONTHLY_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://www.fpi.nsdl.co.in/",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        text_payload, reason = self._request_provider_text(request, NSDL_MAX_RESPONSE_BYTES)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "confirmed_fpi_source_unavailable"},
            )
            return
        try:
            now = datetime.now(INDIA_TIMEZONE)
            rows = parse_nsdl_confirmed_fpi(text_payload or "", today=now.date())
            store = _get_eod_store()
            write_result = store.append_confirmed_fpi_investments(
                rows,
                source=NSDL_FPI_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_confirmed_fpi_summary(
                store.load_confirmed_fpi_investments(), today=now.date()
            )
        except ConfirmedFpiConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_confirmed_fpi_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_confirmed_fpi_response"},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True, **summary, "write_result": write_result})

    def _send_macro_context_refresh(self) -> None:
        request = urllib.request.Request(
            RBI_HOME_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        text_payload, reason = self._request_provider_text(request, RBI_MAX_RESPONSE_BYTES)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "rbi_macro_source_unavailable"},
            )
            return
        try:
            rows = parse_rbi_macro_snapshot(text_payload or "")
            store = _get_eod_store()
            write_result = store.append_macro_snapshots(
                rows,
                source=RBI_MACRO_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_macro_context_summary(store.load_macro_snapshots())
        except MacroSnapshotConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_macro_snapshot_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_rbi_macro_response"},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True, **summary, "write_result": write_result})

    def _send_global_risk_refresh(self) -> None:
        today = datetime.now(INDIA_TIMEZONE).date()
        earliest = today - timedelta(days=460)
        query = urllib.parse.urlencode(
            {"id": ",".join(FRED_GLOBAL_SERIES), "cosd": earliest.isoformat()}
        )
        request = urllib.request.Request(
            f"{FRED_GRAPH_CSV_URL}?{query}",
            headers={
                "Accept": "application/zip,text/csv,*/*",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        zip_payload, reason = self._request_fred_export(request)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "global_risk_source_unavailable"},
            )
            return
        try:
            rows = parse_fred_global_zip(zip_payload or b"", today=today, earliest=earliest)
            store = _get_eod_store()
            write_result = store.append_global_risk_observations(
                rows,
                source=FRED_GLOBAL_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_global_risk_summary(store.load_global_risk_observations())
        except GlobalRiskConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_global_risk_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_fred_global_response"},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True, **summary, "write_result": write_result})

    def _send_futures_eod_refresh(self, payload: dict[str, object]) -> None:
        raw_symbols = payload.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or not raw_symbols
            or len(raw_symbols) > 250
            or any(
                not isinstance(symbol, str)
                or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
                for symbol in raw_symbols
            )
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_futures_universe"})
            return
        symbols = tuple(raw_symbols)
        if len(set(symbols)) != len(symbols):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_futures_universe"})
            return
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return
        now = datetime.now(INDIA_TIMEZONE)
        completed_through = completed_history_date(now)
        while completed_through.weekday() >= 5:
            completed_through -= timedelta(days=1)
        instrument_request = urllib.request.Request(
            NFO_INSTRUMENTS_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        csv_payload, reason = self._request_provider_text(instrument_request, MAX_NFO_INSTRUMENT_BYTES)
        if reason is not None:
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return
        try:
            contracts, inventory_missing = parse_near_month_stock_futures(
                csv_payload or "", symbols, as_of=now.date()
            )
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": str(error)})
            return
        if not contracts:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": "futures_contracts_unavailable"})
            return
        try:
            if now.time().replace(tzinfo=None) >= datetime_time(15, 40):
                quote_query = urllib.parse.urlencode(
                    [("i", f"NFO:{contract['tradingsymbol']}") for contract in contracts]
                )
                quote_request = urllib.request.Request(
                    f"{FULL_QUOTE_URL}?{quote_query}",
                    headers={
                        "Authorization": f"token {api_key}:{access_token}",
                        "X-Kite-Version": "3",
                        "Accept": "application/json",
                        "User-Agent": "PG-terminal-local/0.1",
                    },
                    method="GET",
                )
                provider_payload, reason = self._request_provider_json(
                    quote_request, exchange=False, maximum_bytes=MAX_QUOTE_RESPONSE_BYTES
                )
                if reason is not None:
                    raise ValueError(reason)
                snapshots, quote_missing = normalize_futures_eod_quotes(
                    provider_payload or {}, contracts, now=now
                )
                retrieval_mode = "post_close_bulk_quote"
            else:
                snapshots = []
                quote_missing = []
                history_start = completed_through - timedelta(days=10)
                for index, contract in enumerate(contracts):
                    if index:
                        time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                    history_query = urllib.parse.urlencode(
                        {
                            "from": history_start.isoformat(),
                            "to": completed_through.isoformat(),
                            "continuous": "0",
                            "oi": "1",
                        }
                    )
                    history_request = urllib.request.Request(
                        f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=contract['instrument_token'])}?{history_query}",
                        headers={
                            "Authorization": f"token {api_key}:{access_token}",
                            "X-Kite-Version": "3",
                            "Accept": "application/json",
                            "User-Agent": "PG-terminal-local/0.1",
                        },
                        method="GET",
                    )
                    history_payload, reason = self._request_provider_json(
                        history_request,
                        exchange=False,
                        maximum_bytes=MAX_HISTORICAL_RESPONSE_BYTES,
                    )
                    if reason is not None:
                        if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                            raise ValueError(reason)
                        quote_missing.append(str(contract["underlying"]))
                        continue
                    snapshot = parse_futures_daily_snapshot(
                        history_payload or {}, contract, completed_through=completed_through
                    )
                    if snapshot is None:
                        quote_missing.append(str(contract["underlying"]))
                    else:
                        snapshots.append(snapshot)
                retrieval_mode = "latest_completed_history"
            if not snapshots:
                raise ValueError("futures_eod_data_unavailable")
            store = _get_eod_store()
            write_result = store.append_futures_eod_snapshots(
                contracts,
                snapshots,
                source=KITE_FUTURES_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_futures_oi_summary(store.load_futures_eod_snapshots())
        except FuturesSnapshotConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_futures_snapshot_conflict"},
            )
            return
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                **summary,
                "requested_count": len(symbols),
                "contract_count": len(contracts),
                "snapshot_count": len(snapshots),
                "inventory_missing": inventory_missing,
                "quote_missing": quote_missing,
                "retrieval_mode": retrieval_mode,
                "completed_through": completed_through.isoformat(),
                "write_result": write_result,
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        if self.path == "/api/market-sentiment/factor-snapshot":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_sentiment_factor_snapshot()
            return

        if self.path == "/api/market-sentiment/futures-eod/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_futures_eod_refresh(payload)
            return

        if self.path == "/api/market-sentiment/macro-context/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_macro_context_refresh()
            return

        if self.path == "/api/market-sentiment/global-risk/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_global_risk_refresh()
            return

        if self.path == "/api/market-sentiment/institutional-flows/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_institutional_flow_refresh()
            return

        if self.path == "/api/market-sentiment/confirmed-fpi/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_confirmed_fpi_refresh()
            return

        if self.path == "/api/kite/historical-month-leaders":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_historical_month_leaders(payload)
            return

        if self.path == "/api/kite/monthly-leaders":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_monthly_leaders(payload)
            return

        if self.path == "/api/kite/disconnect":
            payload = self._read_json_payload()
            if payload is None:
                return
            with _SESSION_LOCK:
                _ACTIVE_KITE_SESSION.clear()
                _ACTIVE_INDEX_TARGETS.clear()
                _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
                _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
                _ACTIVE_EQUITY_TOKENS.clear()
                _BREADTH_CACHE.clear()
                _SEASONALITY_CACHE.clear()
                _MONTHLY_EQUITY_RETURNS_CACHE.clear()
                _MONTHLY_LEADERS_CACHE.clear()
                _HISTORICAL_MONTH_LEADERS_CACHE.clear()
                _REGIME_VALIDATION_CACHE.clear()
                _CROSS_INDEX_VALIDATION_CACHE.clear()
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
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _SEASONALITY_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_LEADERS_CACHE.clear()
            _HISTORICAL_MONTH_LEADERS_CACHE.clear()
            _REGIME_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.clear()
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
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _SEASONALITY_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_LEADERS_CACHE.clear()
            _HISTORICAL_MONTH_LEADERS_CACHE.clear()
            _REGIME_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.clear()
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
        maximum_bytes: int = MAX_RESPONSE_BYTES,
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            with _PROVIDER_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
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

    def _request_fred_export(
        self, request: urllib.request.Request
    ) -> tuple[bytes | None, str | None]:
        """Fetch the fixed public FRED export, allowing its standard HTTPS redirect handling."""
        last_error: BaseException | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    final_host = (urllib.parse.urlsplit(response.geturl()).hostname or "").lower()
                    if final_host != "fred.stlouisfed.org" or response.status != HTTPStatus.OK:
                        return None, "invalid_provider_response"
                    body = response.read(FRED_MAX_RESPONSE_BYTES + 1)
                    if len(body) > FRED_MAX_RESPONSE_BYTES:
                        return None, "provider_response_too_large"
                    return body, None
            except urllib.error.HTTPError as error:
                return None, self._classify_provider_error(error, exchange=False)
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        return None, classify_network_error(last_error or OSError("fred_request_failed"))

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
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _SEASONALITY_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_LEADERS_CACHE.clear()
            _HISTORICAL_MONTH_LEADERS_CACHE.clear()
            _REGIME_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.clear()

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
