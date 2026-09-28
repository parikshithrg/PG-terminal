import tempfile
import unittest
import json
from datetime import date
from pathlib import Path

from eod_store import (
    CandleConflictError,
    ConfirmedFpiConflictError,
    EODStore,
    FuturesSnapshotConflictError,
    GlobalRiskConflictError,
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

    def test_confirmed_fpi_routes_are_append_only_and_kept_separate(self):
        rows = [
            {
                "date": date(2026, 9, 24),
                "asset_class": "Equity",
                "investment_route": "Stock Exchange",
                "gross_purchases_crore": 100.0,
                "gross_sales_crore": 120.0,
                "net_investment_crore": -20.0,
            },
            {
                "date": date(2026, 9, 24),
                "asset_class": "Equity",
                "investment_route": "Primary market & others",
                "gross_purchases_crore": 5.0,
                "gross_sales_crore": 0.0,
                "net_investment_crore": 5.0,
            },
            {
                "date": date(2026, 9, 24),
                "asset_class": "Equity",
                "investment_route": "Sub-total",
                "gross_purchases_crore": 105.0,
                "gross_sales_crore": 120.0,
                "net_investment_crore": -15.0,
            },
        ]
        self.assertEqual(
            self.store.append_confirmed_fpi_investments(rows, source="NSDL official report"),
            {"inserted": 3, "duplicates": 0},
        )
        self.assertEqual(
            self.store.append_confirmed_fpi_investments(rows, source="NSDL official report"),
            {"inserted": 0, "duplicates": 3},
        )
        loaded = self.store.load_confirmed_fpi_investments()
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[-1]["investment_route"], "Sub-total")
        self.assertEqual(loaded[-1]["publication_status"], "confirmed_custodian")

        changed = [dict(row) for row in rows]
        changed[-1]["net_investment_crore"] = -14.0
        changed[-1]["gross_purchases_crore"] = 106.0
        with self.assertRaises(ConfirmedFpiConflictError):
            self.store.append_confirmed_fpi_investments(changed, source="NSDL official report")

    def test_global_risk_observations_are_append_only(self):
        rows = [
            {
                "date": date(2026, 9, 25),
                "metric_key": "sp500",
                "value": 7743.41,
                "unit": "Index",
                "source_series": "SP500",
            },
            {
                "date": date(2026, 9, 25),
                "metric_key": "us_vix",
                "value": 14.21,
                "unit": "Index",
                "source_series": "VIXCLS",
            },
        ]
        self.assertEqual(
            self.store.append_global_risk_observations(rows, source="FRED"),
            {"inserted": 2, "duplicates": 0},
        )
        self.assertEqual(
            self.store.append_global_risk_observations(rows, source="FRED"),
            {"inserted": 0, "duplicates": 2},
        )
        self.assertEqual(len(self.store.load_global_risk_observations()), 2)

        changed = [dict(row) for row in rows]
        changed[0]["value"] = 7744.0
        with self.assertRaises(GlobalRiskConflictError):
            self.store.append_global_risk_observations(changed, source="FRED")

    def test_sentiment_factor_snapshots_are_versioned_and_revision_preserving(self):
        evidence = {
            "as_of_date": "2026-09-25",
            "trend": {"band": "constructive", "close": 25000.0},
            "global_risk": {"available": False},
        }
        first = self.store.append_sentiment_factor_snapshot(
            as_of_date=date(2026, 9, 25),
            model_version="market-sentiment-evidence-v1",
            evidence=evidence,
            created_at="2026-09-25T12:00:00+00:00",
        )
        duplicate = self.store.append_sentiment_factor_snapshot(
            as_of_date=date(2026, 9, 25),
            model_version="market-sentiment-evidence-v1",
            evidence=evidence,
            created_at="2026-09-25T12:05:00+00:00",
        )
        revised = json.loads(json.dumps(evidence))
        revised["global_risk"] = {"available": True}
        revision = self.store.append_sentiment_factor_snapshot(
            as_of_date=date(2026, 9, 25),
            model_version="market-sentiment-evidence-v1",
            evidence=revised,
            created_at="2026-09-25T12:10:00+00:00",
        )
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(duplicate["duplicates"], 1)
        self.assertEqual(revision["inserted"], 1)
        loaded = self.store.load_sentiment_factor_snapshots(
            model_version="market-sentiment-evidence-v1"
        )
        self.assertEqual(len(loaded), 2)
        self.assertNotEqual(loaded[0]["evidence_hash"], loaded[1]["evidence_hash"])

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
