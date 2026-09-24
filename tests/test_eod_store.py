import tempfile
import unittest
from datetime import date
from pathlib import Path

from eod_store import CandleConflictError, EODStore
from server import incremental_history_ranges


class EODStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = EODStore(Path(self.temporary_directory.name) / "eod.sqlite3")

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def candle(session_date, close=102.0):
        return {
            "date": session_date,
            "open": 100.0,
            "high": 104.0,
            "low": 99.0,
            "close": close,
        }

    def test_append_is_idempotent_and_preserves_validated_candles(self):
        candles = [
            self.candle(date(2026, 9, 21), 101.0),
            self.candle(date(2026, 9, 22), 102.0),
        ]
        first = self.store.append_candles(
            kind="index", display_name="Nifty 50", provider_token="256265", candles=candles
        )
        second = self.store.append_candles(
            kind="index", display_name="Nifty 50", provider_token="256265", candles=candles
        )

        self.assertEqual(first, {"inserted": 2, "duplicates": 0, "source_duplicates": 0})
        self.assertEqual(second, {"inserted": 0, "duplicates": 2, "source_duplicates": 0})
        self.assertEqual(self.store.coverage(kind="index", display_name="Nifty 50")["session_count"], 2)
        self.assertEqual(
            [row["date"] for row in self.store.load_candles(kind="index", display_name="Nifty 50")],
            [date(2026, 9, 21), date(2026, 9, 22)],
        )

    def test_existing_session_cannot_be_silently_overwritten(self):
        self.store.append_candles(
            kind="stock", display_name="INFY", provider_token="408065",
            candles=[self.candle(date(2026, 9, 22), 102.0)],
        )
        with self.assertRaises(CandleConflictError):
            self.store.append_candles(
                kind="stock", display_name="INFY", provider_token="408065",
                candles=[self.candle(date(2026, 9, 22), 103.0)],
            )
        loaded = self.store.load_candles(kind="stock", display_name="INFY")
        self.assertEqual(loaded[0]["close"], 102.0)

    def test_duplicate_dates_in_one_provider_snapshot_are_consolidated(self):
        result = self.store.append_candles(
            kind="index",
            display_name="Nifty Auto",
            provider_token="426265",
            candles=[
                self.candle(date(2026, 9, 22), 101.0),
                self.candle(date(2026, 9, 22), 102.0),
            ],
        )
        self.assertEqual(result, {"inserted": 1, "duplicates": 0, "source_duplicates": 1})
        loaded = self.store.load_candles(kind="index", display_name="Nifty Auto")
        self.assertEqual(loaded[0]["close"], 102.0)

    def test_incremental_ranges_resume_after_latest_stored_session(self):
        self.assertEqual(
            incremental_history_ranges(
                date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 6), chunk_days=2
            ),
            [(date(2026, 1, 7), date(2026, 1, 8)), (date(2026, 1, 9), date(2026, 1, 10))],
        )
        self.assertEqual(
            incremental_history_ranges(date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 10)),
            [],
        )

    def test_invalid_ohlc_is_rejected_before_storage(self):
        bad = self.candle(date(2026, 9, 22))
        bad["high"] = 98.0
        with self.assertRaisesRegex(ValueError, "invalid_candle"):
            self.store.append_candles(
                kind="index", display_name="Nifty 50", provider_token="256265", candles=[bad]
            )

    def test_list_instruments_returns_coverage_by_kind(self):
        self.store.append_candles(
            kind="stock",
            display_name="INFY",
            provider_token="408065",
            candles=[self.candle(date(2026, 9, 22), 102.0)],
        )
        self.store.append_candles(
            kind="index",
            display_name="Nifty 50",
            provider_token="256265",
            candles=[self.candle(date(2026, 9, 22), 101.0)],
        )
        stocks = self.store.list_instruments(kind="stock")
        self.assertEqual(len(stocks), 1)
        self.assertEqual(stocks[0]["display_name"], "INFY")
        self.assertEqual(stocks[0]["session_count"], 1)
        self.assertEqual(stocks[0]["last_session"], date(2026, 9, 22))


if __name__ == "__main__":
    unittest.main()
