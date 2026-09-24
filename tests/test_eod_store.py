import tempfile
import unittest
from datetime import date
from pathlib import Path

from eod_store import (
    CandleConflictError,
    EODStore,
    FuturesSnapshotConflictError,
    InstitutionalFlowConflictError,
    MacroSnapshotConflictError,
)
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

    def test_institutional_flows_are_append_only_and_idempotent(self):
        rows = [
            {"date": date(2026, 9, 23), "category": "DII", "buy_crore": 14404.90, "sell_crore": 12063.44, "net_crore": 2341.46},
            {"date": date(2026, 9, 23), "category": "FII/FPI", "buy_crore": 13580.40, "sell_crore": 11962.95, "net_crore": 1617.45},
        ]
        first = self.store.append_institutional_flows(rows, source="NSE official report")
        second = self.store.append_institutional_flows(rows, source="NSE official report")
        self.assertEqual(first, {"inserted": 2, "duplicates": 0})
        self.assertEqual(second, {"inserted": 0, "duplicates": 2})
        loaded = self.store.load_institutional_flows()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[1]["category"], "FII/FPI")
        self.assertEqual(loaded[1]["net_crore"], 1617.45)

        changed = [dict(row) for row in rows]
        changed[0].update({"buy_crore": 14405.90, "net_crore": 2342.46})
        with self.assertRaises(InstitutionalFlowConflictError):
            self.store.append_institutional_flows(changed, source="NSE official report")

    def test_macro_snapshots_are_append_only_and_preserve_instrument_label(self):
        rows = [
            {"date": date(2026, 9, 24), "metric_key": "usd_inr", "value": 95.9099, "unit": "INR per USD", "instrument_label": "USD/INR"},
            {"date": date(2026, 9, 24), "metric_key": "gbp_inr", "value": 127.0295, "unit": "INR per GBP", "instrument_label": "GBP/INR"},
            {"date": date(2026, 9, 24), "metric_key": "eur_inr", "value": 109.1912, "unit": "INR per EUR", "instrument_label": "EUR/INR"},
            {"date": date(2026, 9, 24), "metric_key": "jpy_100_inr", "value": 60.62, "unit": "INR per 100 JPY", "instrument_label": "JPY/INR (100 JPY)"},
            {"date": date(2026, 9, 23), "metric_key": "india_10y_gsec_yield", "value": 7.0408, "unit": "percent yield", "instrument_label": "6.94% GS 2036 (approx. 10-year; matures 2036)"},
        ]
        self.assertEqual(
            self.store.append_macro_snapshots(rows, source="RBI current rates"),
            {"inserted": 5, "duplicates": 0},
        )
        self.assertEqual(
            self.store.append_macro_snapshots(rows, source="RBI current rates"),
            {"inserted": 0, "duplicates": 5},
        )
        loaded = self.store.load_macro_snapshots()
        self.assertEqual(len(loaded), 5)
        gsec = next(row for row in loaded if row["metric_key"] == "india_10y_gsec_yield")
        self.assertIn("GS 2036", gsec["instrument_label"])

        changed = [dict(row) for row in rows]
        changed[0]["value"] = 96.0
        with self.assertRaises(MacroSnapshotConflictError):
            self.store.append_macro_snapshots(changed, source="RBI current rates")

    def test_futures_snapshots_are_keyed_by_contract_and_session(self):
        contracts = [
            {
                "underlying": "AAA", "tradingsymbol": "AAA26SEPFUT", "exchange": "NFO",
                "instrument_token": "101", "expiry": date(2026, 9, 24), "lot_size": 500,
            }
        ]
        snapshots = [
            {
                "contract_key": "NFO:AAA26SEPFUT", "date": date(2026, 9, 23),
                "open": 100.0, "high": 108.0, "low": 98.0, "close": 105.0,
                "volume": 125000, "open_interest": 750000,
            }
        ]
        self.assertEqual(
            self.store.append_futures_eod_snapshots(contracts, snapshots, source="Kite NFO"),
            {"inserted": 1, "duplicates": 0},
        )
        self.assertEqual(
            self.store.append_futures_eod_snapshots(contracts, snapshots, source="Kite NFO"),
            {"inserted": 0, "duplicates": 1},
        )
        loaded = self.store.load_futures_eod_snapshots()
        self.assertEqual(loaded[0]["contract_key"], "NFO:AAA26SEPFUT")
        self.assertEqual(loaded[0]["open_interest"], 750000)

        changed = [dict(snapshots[0])]
        changed[0]["open_interest"] = 750001
        with self.assertRaises(FuturesSnapshotConflictError):
            self.store.append_futures_eod_snapshots(contracts, changed, source="Kite NFO")


if __name__ == "__main__":
    unittest.main()
