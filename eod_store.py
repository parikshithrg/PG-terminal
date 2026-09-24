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
