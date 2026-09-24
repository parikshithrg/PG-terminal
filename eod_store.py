"""Append-only local storage for validated completed daily candles."""

from __future__ import annotations

import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
SOURCE_NAME = "Kite Connect historical daily candles"


class CandleConflictError(ValueError):
    """Raised when a provider tries to change an already stored session."""


class InstitutionalFlowConflictError(ValueError):
    """Raised when a published institutional-flow row changes after storage."""


class MacroSnapshotConflictError(ValueError):
    """Raised when an official macro observation changes after storage."""


class FuturesSnapshotConflictError(ValueError):
    """Raised when a stored contract/session snapshot changes."""


class EODStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialise(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS instruments (
                        instrument_id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL CHECK (kind IN ('index', 'stock')),
                        display_name TEXT NOT NULL,
                        provider_token TEXT NOT NULL,
                        source TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS candles (
                        instrument_id TEXT NOT NULL,
                        session_date TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        source TEXT NOT NULL,
                        retrieved_at TEXT NOT NULL,
                        validation_status TEXT NOT NULL CHECK (validation_status = 'validated'),
                        schema_version INTEGER NOT NULL,
                        PRIMARY KEY (instrument_id, session_date),
                        FOREIGN KEY (instrument_id) REFERENCES instruments(instrument_id)
                    );

                    CREATE INDEX IF NOT EXISTS candles_date_idx
                    ON candles(session_date);

                    CREATE TABLE IF NOT EXISTS institutional_flows (
                        session_date TEXT NOT NULL,
                        category TEXT NOT NULL CHECK (category IN ('FII/FPI', 'DII')),
                        buy_crore REAL NOT NULL,
                        sell_crore REAL NOT NULL,
                        net_crore REAL NOT NULL,
                        market_scope TEXT NOT NULL CHECK (market_scope = 'combined_cash_market'),
                        publication_status TEXT NOT NULL CHECK (publication_status IN ('provisional', 'confirmed')),
                        source TEXT NOT NULL,
                        retrieved_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        PRIMARY KEY (session_date, category, market_scope, publication_status)
                    );

                    CREATE INDEX IF NOT EXISTS institutional_flows_date_idx
                    ON institutional_flows(session_date);

                    CREATE TABLE IF NOT EXISTS macro_snapshots (
                        observation_date TEXT NOT NULL,
                        metric_key TEXT NOT NULL CHECK (metric_key IN (
                            'usd_inr', 'gbp_inr', 'eur_inr', 'jpy_100_inr',
                            'india_10y_gsec_yield'
                        )),
                        value REAL NOT NULL,
                        unit TEXT NOT NULL,
                        instrument_label TEXT NOT NULL,
                        source TEXT NOT NULL,
                        retrieved_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        PRIMARY KEY (observation_date, metric_key)
                    );

                    CREATE INDEX IF NOT EXISTS macro_snapshots_date_idx
                    ON macro_snapshots(observation_date);

                    CREATE TABLE IF NOT EXISTS futures_contracts (
                        contract_key TEXT PRIMARY KEY,
                        underlying TEXT NOT NULL,
                        tradingsymbol TEXT NOT NULL,
                        exchange TEXT NOT NULL CHECK (exchange = 'NFO'),
                        provider_token TEXT NOT NULL,
                        expiry_date TEXT NOT NULL,
                        lot_size INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS futures_eod_snapshots (
                        contract_key TEXT NOT NULL,
                        session_date TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume INTEGER NOT NULL,
                        open_interest INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        retrieved_at TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        PRIMARY KEY (contract_key, session_date),
                        FOREIGN KEY (contract_key) REFERENCES futures_contracts(contract_key)
                    );

                    CREATE INDEX IF NOT EXISTS futures_eod_date_idx
                    ON futures_eod_snapshots(session_date);

                    CREATE INDEX IF NOT EXISTS futures_contract_underlying_idx
                    ON futures_contracts(underlying, expiry_date);
                    """
                )

    @staticmethod
    def instrument_id(kind: str, display_name: str) -> str:
        if kind not in {"index", "stock"} or not display_name or display_name.strip() != display_name:
            raise ValueError("invalid_instrument_identity")
        return f"{kind}:{display_name}"

    @staticmethod
    def _validated_values(candle: dict[str, object]) -> tuple[str, float, float, float, float]:
        candle_date = candle.get("date")
        if not isinstance(candle_date, date):
            raise ValueError("invalid_candle")
        raw_values = (candle.get("open"), candle.get("high"), candle.get("low"), candle.get("close"))
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) > 0
            for value in raw_values
        ):
            raise ValueError("invalid_candle")
        open_price, high, low, close = (float(value) for value in raw_values)
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise ValueError("invalid_candle")
        return candle_date.isoformat(), open_price, high, low, close

    def append_candles(
        self,
        *,
        kind: str,
        display_name: str,
        provider_token: str,
        candles: list[dict[str, object]],
        retrieved_at: str | None = None,
    ) -> dict[str, int]:
        identity = self.instrument_id(kind, display_name)
        if not provider_token or not provider_token.isdigit():
            raise ValueError("invalid_instrument_identity")
        timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
        validated_by_date: dict[str, tuple[str, float, float, float, float]] = {}
        source_duplicates = 0
        for candle in candles:
            validated = self._validated_values(candle)
            if validated[0] in validated_by_date:
                source_duplicates += 1
            # A single provider response is one retrieval snapshot. When it
            # repeats a session, the final row is the provider's final value.
            # Existing persisted sessions remain immutable below.
            validated_by_date[validated[0]] = validated
        validated_rows = [validated_by_date[key] for key in sorted(validated_by_date)]
        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO instruments (
                        instrument_id, kind, display_name, provider_token, source, updated_at, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instrument_id) DO UPDATE SET
                        provider_token = excluded.provider_token,
                        updated_at = excluded.updated_at,
                        schema_version = excluded.schema_version
                    """,
                    (identity, kind, display_name, provider_token, SOURCE_NAME, timestamp, SCHEMA_VERSION),
                )
                for session_date, open_price, high, low, close in validated_rows:
                    existing = connection.execute(
                        """
                        SELECT open, high, low, close
                        FROM candles
                        WHERE instrument_id = ? AND session_date = ?
                        """,
                        (identity, session_date),
                    ).fetchone()
                    values = (open_price, high, low, close)
                    if existing is not None:
                        stored = tuple(float(existing[key]) for key in ("open", "high", "low", "close"))
                        if stored != values:
                            raise CandleConflictError(f"stored_candle_conflict:{identity}:{session_date}")
                        duplicates += 1
                        continue
                    connection.execute(
                        """
                        INSERT INTO candles (
                            instrument_id, session_date, open, high, low, close,
                            source, retrieved_at, validation_status, schema_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'validated', ?)
                        """,
                        (
                            identity,
                            session_date,
                            open_price,
                            high,
                            low,
                            close,
                            SOURCE_NAME,
                            timestamp,
                            SCHEMA_VERSION,
                        ),
                    )
                    inserted += 1
        return {
            "inserted": inserted,
            "duplicates": duplicates,
            "source_duplicates": source_duplicates,
        }

    def load_candles(
        self,
        *,
        kind: str,
        display_name: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict[str, object]]:
        identity = self.instrument_id(kind, display_name)
        clauses = ["instrument_id = ?", "validation_status = 'validated'"]
        parameters: list[object] = [identity]
        if start is not None:
            clauses.append("session_date >= ?")
            parameters.append(start.isoformat())
        if end is not None:
            clauses.append("session_date <= ?")
            parameters.append(end.isoformat())
        query = f"""
            SELECT session_date, open, high, low, close
            FROM candles
            WHERE {' AND '.join(clauses)}
            ORDER BY session_date
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "date": date.fromisoformat(row["session_date"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            for row in rows
        ]

    def coverage(self, *, kind: str, display_name: str) -> dict[str, object]:
        identity = self.instrument_id(kind, display_name)
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS session_count,
                       MIN(session_date) AS first_session,
                       MAX(session_date) AS last_session
                FROM candles
                WHERE instrument_id = ? AND validation_status = 'validated'
                """,
                (identity,),
            ).fetchone()
        return {
            "session_count": int(row["session_count"]),
            "first_session": date.fromisoformat(row["first_session"]) if row["first_session"] else None,
            "last_session": date.fromisoformat(row["last_session"]) if row["last_session"] else None,
        }

    def list_instruments(self, *, kind: str | None = None) -> list[dict[str, object]]:
        if kind is not None and kind not in {"index", "stock"}:
            raise ValueError("invalid_instrument_identity")
        where = "WHERE i.kind = ?" if kind is not None else ""
        parameters: tuple[object, ...] = (kind,) if kind is not None else ()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT i.kind, i.display_name, i.provider_token,
                       COUNT(c.session_date) AS session_count,
                       MIN(c.session_date) AS first_session,
                       MAX(c.session_date) AS last_session
                FROM instruments i
                LEFT JOIN candles c
                  ON c.instrument_id = i.instrument_id
                 AND c.validation_status = 'validated'
                {where}
                GROUP BY i.instrument_id
                ORDER BY i.display_name
                """,
                parameters,
            ).fetchall()
        return [
            {
                "kind": row["kind"],
                "display_name": row["display_name"],
                "provider_token": row["provider_token"],
                "session_count": int(row["session_count"]),
                "first_session": date.fromisoformat(row["first_session"]) if row["first_session"] else None,
                "last_session": date.fromisoformat(row["last_session"]) if row["last_session"] else None,
            }
            for row in rows
        ]

    def append_institutional_flows(
        self,
        rows: list[dict[str, object]],
        *,
        source: str,
        market_scope: str = "combined_cash_market",
        publication_status: str = "provisional",
        retrieved_at: str | None = None,
    ) -> dict[str, int]:
        if (
            not source
            or market_scope != "combined_cash_market"
            or publication_status not in {"provisional", "confirmed"}
        ):
            raise ValueError("invalid_institutional_flow")
        timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
        validated: list[tuple[str, str, float, float, float]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            session_date = row.get("date")
            category = row.get("category")
            raw_values = (row.get("buy_crore"), row.get("sell_crore"), row.get("net_crore"))
            if (
                not isinstance(session_date, date)
                or category not in {"FII/FPI", "DII"}
                or not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    for value in raw_values
                )
            ):
                raise ValueError("invalid_institutional_flow")
            buy, sell, net = (float(value) for value in raw_values)
            if buy < 0 or sell < 0 or abs((buy - sell) - net) > 0.11:
                raise ValueError("invalid_institutional_flow")
            identity = (session_date.isoformat(), str(category))
            if identity in seen:
                raise ValueError("invalid_institutional_flow")
            seen.add(identity)
            validated.append((identity[0], identity[1], buy, sell, net))
        if {item[1] for item in validated} != {"FII/FPI", "DII"} or len({item[0] for item in validated}) != 1:
            raise ValueError("invalid_institutional_flow")

        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection:
            with connection:
                for session_date, category, buy, sell, net in validated:
                    existing = connection.execute(
                        """
                        SELECT buy_crore, sell_crore, net_crore
                        FROM institutional_flows
                        WHERE session_date = ? AND category = ?
                          AND market_scope = ? AND publication_status = ?
                        """,
                        (session_date, category, market_scope, publication_status),
                    ).fetchone()
                    values = (buy, sell, net)
                    if existing is not None:
                        stored = tuple(float(existing[key]) for key in ("buy_crore", "sell_crore", "net_crore"))
                        if stored != values:
                            raise InstitutionalFlowConflictError(
                                f"stored_institutional_flow_conflict:{session_date}:{category}"
                            )
                        duplicates += 1
                        continue
                    connection.execute(
                        """
                        INSERT INTO institutional_flows (
                            session_date, category, buy_crore, sell_crore, net_crore,
                            market_scope, publication_status, source, retrieved_at, schema_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_date,
                            category,
                            buy,
                            sell,
                            net,
                            market_scope,
                            publication_status,
                            source,
                            timestamp,
                            SCHEMA_VERSION,
                        ),
                    )
                    inserted += 1
        return {"inserted": inserted, "duplicates": duplicates}

    def load_institutional_flows(
        self,
        *,
        market_scope: str = "combined_cash_market",
        publication_status: str = "provisional",
    ) -> list[dict[str, object]]:
        if market_scope != "combined_cash_market" or publication_status not in {"provisional", "confirmed"}:
            raise ValueError("invalid_institutional_flow")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT session_date, category, buy_crore, sell_crore, net_crore,
                       source, retrieved_at
                FROM institutional_flows
                WHERE market_scope = ? AND publication_status = ?
                ORDER BY session_date, category
                """,
                (market_scope, publication_status),
            ).fetchall()
        return [
            {
                "date": date.fromisoformat(row["session_date"]),
                "category": row["category"],
                "buy_crore": float(row["buy_crore"]),
                "sell_crore": float(row["sell_crore"]),
                "net_crore": float(row["net_crore"]),
                "source": row["source"],
                "retrieved_at": row["retrieved_at"],
                "market_scope": market_scope,
                "publication_status": publication_status,
            }
            for row in rows
        ]

    def append_macro_snapshots(
        self,
        rows: list[dict[str, object]],
        *,
        source: str,
        retrieved_at: str | None = None,
    ) -> dict[str, int]:
        allowed = {
            "usd_inr",
            "gbp_inr",
            "eur_inr",
            "jpy_100_inr",
            "india_10y_gsec_yield",
        }
        if not source:
            raise ValueError("invalid_macro_snapshot")
        timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
        validated: list[tuple[str, str, float, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            observation_date = row.get("date")
            metric_key = row.get("metric_key")
            value = row.get("value")
            unit = row.get("unit")
            instrument_label = row.get("instrument_label")
            if (
                not isinstance(observation_date, date)
                or metric_key not in allowed
                or not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) <= 0
                or not isinstance(unit, str)
                or not unit.strip()
                or not isinstance(instrument_label, str)
                or not instrument_label.strip()
            ):
                raise ValueError("invalid_macro_snapshot")
            identity = (observation_date.isoformat(), str(metric_key))
            if identity in seen:
                raise ValueError("invalid_macro_snapshot")
            seen.add(identity)
            validated.append(
                (identity[0], identity[1], float(value), unit.strip(), instrument_label.strip())
            )
        if {row[1] for row in validated} != allowed:
            raise ValueError("invalid_macro_snapshot")

        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection:
            with connection:
                for observation_date, metric_key, value, unit, instrument_label in validated:
                    existing = connection.execute(
                        """
                        SELECT value, unit, instrument_label
                        FROM macro_snapshots
                        WHERE observation_date = ? AND metric_key = ?
                        """,
                        (observation_date, metric_key),
                    ).fetchone()
                    stored_values = (value, unit, instrument_label)
                    if existing is not None:
                        existing_values = (
                            float(existing["value"]),
                            existing["unit"],
                            existing["instrument_label"],
                        )
                        if existing_values != stored_values:
                            raise MacroSnapshotConflictError(
                                f"stored_macro_snapshot_conflict:{observation_date}:{metric_key}"
                            )
                        duplicates += 1
                        continue
                    connection.execute(
                        """
                        INSERT INTO macro_snapshots (
                            observation_date, metric_key, value, unit, instrument_label,
                            source, retrieved_at, schema_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            observation_date,
                            metric_key,
                            value,
                            unit,
                            instrument_label,
                            source,
                            timestamp,
                            SCHEMA_VERSION,
                        ),
                    )
                    inserted += 1
        return {"inserted": inserted, "duplicates": duplicates}

    def load_macro_snapshots(self) -> list[dict[str, object]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT observation_date, metric_key, value, unit, instrument_label,
                       source, retrieved_at
                FROM macro_snapshots
                ORDER BY observation_date, metric_key
                """
            ).fetchall()
        return [
            {
                "date": date.fromisoformat(row["observation_date"]),
                "metric_key": row["metric_key"],
                "value": float(row["value"]),
                "unit": row["unit"],
                "instrument_label": row["instrument_label"],
                "source": row["source"],
                "retrieved_at": row["retrieved_at"],
            }
            for row in rows
        ]

    def append_futures_eod_snapshots(
        self,
        contracts: list[dict[str, object]],
        snapshots: list[dict[str, object]],
        *,
        source: str,
        retrieved_at: str | None = None,
    ) -> dict[str, int]:
        if not source:
            raise ValueError("invalid_futures_snapshot")
        timestamp = retrieved_at or datetime.now(timezone.utc).isoformat()
        validated_contracts: dict[str, tuple[str, str, str, str, str, int]] = {}
        for contract in contracts:
            underlying = contract.get("underlying")
            tradingsymbol = contract.get("tradingsymbol")
            exchange = contract.get("exchange")
            provider_token = contract.get("instrument_token")
            expiry = contract.get("expiry")
            lot_size = contract.get("lot_size")
            if (
                not isinstance(underlying, str)
                or not underlying.strip()
                or not isinstance(tradingsymbol, str)
                or not tradingsymbol.strip()
                or exchange != "NFO"
                or not isinstance(provider_token, str)
                or not provider_token.isdigit()
                or not isinstance(expiry, date)
                or not isinstance(lot_size, int)
                or isinstance(lot_size, bool)
                or lot_size <= 0
            ):
                raise ValueError("invalid_futures_snapshot")
            contract_key = f"NFO:{tradingsymbol}"
            if contract_key in validated_contracts:
                raise ValueError("invalid_futures_snapshot")
            validated_contracts[contract_key] = (
                underlying,
                tradingsymbol,
                "NFO",
                provider_token,
                expiry.isoformat(),
                lot_size,
            )

        validated_snapshots: list[tuple[str, str, float, float, float, float, int, int]] = []
        seen_snapshots: set[tuple[str, str]] = set()
        for snapshot in snapshots:
            contract_key = snapshot.get("contract_key")
            session_date = snapshot.get("date")
            raw_prices = (snapshot.get("open"), snapshot.get("high"), snapshot.get("low"), snapshot.get("close"))
            volume = snapshot.get("volume")
            open_interest = snapshot.get("open_interest")
            if (
                contract_key not in validated_contracts
                or not isinstance(session_date, date)
                or not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    and float(value) > 0
                    for value in raw_prices
                )
                or not isinstance(volume, int)
                or isinstance(volume, bool)
                or volume < 0
                or not isinstance(open_interest, int)
                or isinstance(open_interest, bool)
                or open_interest < 0
            ):
                raise ValueError("invalid_futures_snapshot")
            open_price, high, low, close = (float(value) for value in raw_prices)
            if high < max(open_price, low, close) or low > min(open_price, high, close):
                raise ValueError("invalid_futures_snapshot")
            identity = (str(contract_key), session_date.isoformat())
            if identity in seen_snapshots:
                raise ValueError("invalid_futures_snapshot")
            seen_snapshots.add(identity)
            validated_snapshots.append(
                (identity[0], identity[1], open_price, high, low, close, volume, open_interest)
            )

        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection:
            with connection:
                for contract_key, values in validated_contracts.items():
                    underlying, tradingsymbol, exchange, provider_token, expiry_date, lot_size = values
                    existing = connection.execute(
                        """
                        SELECT underlying, tradingsymbol, exchange, provider_token, expiry_date, lot_size
                        FROM futures_contracts WHERE contract_key = ?
                        """,
                        (contract_key,),
                    ).fetchone()
                    if existing is not None:
                        stored = (
                            existing["underlying"], existing["tradingsymbol"], existing["exchange"],
                            existing["provider_token"], existing["expiry_date"], int(existing["lot_size"]),
                        )
                        if stored != values:
                            raise FuturesSnapshotConflictError(f"stored_futures_contract_conflict:{contract_key}")
                        connection.execute(
                            "UPDATE futures_contracts SET last_seen_at = ? WHERE contract_key = ?",
                            (timestamp, contract_key),
                        )
                    else:
                        connection.execute(
                            """
                            INSERT INTO futures_contracts (
                                contract_key, underlying, tradingsymbol, exchange, provider_token,
                                expiry_date, lot_size, source, first_seen_at, last_seen_at, schema_version
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                contract_key, underlying, tradingsymbol, exchange, provider_token,
                                expiry_date, lot_size, source, timestamp, timestamp, SCHEMA_VERSION,
                            ),
                        )
                for snapshot in validated_snapshots:
                    contract_key, session_date, open_price, high, low, close, volume, open_interest = snapshot
                    existing = connection.execute(
                        """
                        SELECT open, high, low, close, volume, open_interest
                        FROM futures_eod_snapshots
                        WHERE contract_key = ? AND session_date = ?
                        """,
                        (contract_key, session_date),
                    ).fetchone()
                    values = (open_price, high, low, close, volume, open_interest)
                    if existing is not None:
                        stored = (
                            float(existing["open"]), float(existing["high"]), float(existing["low"]),
                            float(existing["close"]), int(existing["volume"]), int(existing["open_interest"]),
                        )
                        if stored != values:
                            raise FuturesSnapshotConflictError(
                                f"stored_futures_snapshot_conflict:{contract_key}:{session_date}"
                            )
                        duplicates += 1
                        continue
                    connection.execute(
                        """
                        INSERT INTO futures_eod_snapshots (
                            contract_key, session_date, open, high, low, close, volume,
                            open_interest, source, retrieved_at, schema_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            contract_key, session_date, open_price, high, low, close, volume,
                            open_interest, source, timestamp, SCHEMA_VERSION,
                        ),
                    )
                    inserted += 1
        return {"inserted": inserted, "duplicates": duplicates}

    def load_futures_eod_snapshots(self) -> list[dict[str, object]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT s.session_date, s.contract_key, s.open, s.high, s.low, s.close,
                       s.volume, s.open_interest, c.underlying, c.tradingsymbol,
                       c.expiry_date, c.lot_size, s.source, s.retrieved_at
                FROM futures_eod_snapshots s
                JOIN futures_contracts c ON c.contract_key = s.contract_key
                ORDER BY c.underlying, s.session_date, c.expiry_date
                """
            ).fetchall()
        return [
            {
                "date": date.fromisoformat(row["session_date"]),
                "contract_key": row["contract_key"],
                "underlying": row["underlying"],
                "tradingsymbol": row["tradingsymbol"],
                "expiry": date.fromisoformat(row["expiry_date"]),
                "lot_size": int(row["lot_size"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "open_interest": int(row["open_interest"]),
                "source": row["source"],
                "retrieved_at": row["retrieved_at"],
            }
            for row in rows
        ]
