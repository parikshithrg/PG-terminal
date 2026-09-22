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
import threading
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone


TOKEN_URL = "https://api.kite.trade/session/token"
PROFILE_URL = "https://api.kite.trade/user/profile"
OHLC_URL = "https://api.kite.trade/quote/ohlc"
NSE_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NSE"
BASE_INDEX = ("Nifty 50", "NSE:NIFTY 50")
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
REQUEST_TIMEOUT_SECONDS = 10

_ACTIVE_KITE_SESSION: dict[str, str] = {}
_ACTIVE_INDEX_TARGETS: list[tuple[str, str, str]] = []
_SESSION_LOCK = threading.Lock()


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
        if self.path == "/api/kite/status":
            with _SESSION_LOCK:
                connected = bool(_ACTIVE_KITE_SESSION)
            self._send_json(HTTPStatus.OK, {"ok": True, "connected": connected})
            return
        if self.path == "/api/kite/indices/ohlc":
            self._send_index_snapshot()
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
        except ValueError as error:
            raise ValueError(str(error)) from error
        with _SESSION_LOCK:
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_INDEX_TARGETS.extend(targets)
        return targets, missing

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        if self.path == "/api/kite/disconnect":
            payload = self._read_json_payload()
            if payload is None:
                return
            with _SESSION_LOCK:
                _ACTIVE_KITE_SESSION.clear()
                _ACTIVE_INDEX_TARGETS.clear()
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
            print(f"Kite profile verification: {reason}", flush=True)
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": reason})
            return

        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_KITE_SESSION.update({"api_key": api_key, "access_token": access_token})
            _ACTIVE_INDEX_TARGETS.clear()
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
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            return None, "provider_unavailable"
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
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            return None, "provider_unavailable"
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
