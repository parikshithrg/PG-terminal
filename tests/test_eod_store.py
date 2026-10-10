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
    HistoricalSeriesConflictError,
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

    def test_manual_news_import_is_append_only_and_idempotent(self):
        rows = [
            {
                "source_key": "nse_corporate_filings_manual_csv",
                "published_at": "2026-10-05T15:42:10+05:30",
                "symbol": "INFY",
                "company_name": "Infosys Limited",
                "category": "corporate_announcement",
                "headline": "Board meeting outcome",
                "attachment_url": "https://example.test/filing.pdf",
                "raw": {"SYMBOL": "INFY", "SUBJECT": "Board meeting outcome"},
            }
        ]
        first = self.store.append_news_event_records(
            rows,
            source_file_name="nse-announcements.csv",
            imported_at="2026-10-06T10:00:00+00:00",
        )
        duplicate = self.store.append_news_event_records(
            rows,
            source_file_name="nse-announcements.csv",
            imported_at="2026-10-06T10:05:00+00:00",
        )
        revised = [dict(rows[0], headline="Revised board meeting outcome")]
        revision = self.store.append_news_event_records(
            revised,
            source_file_name="nse-announcements-revised.csv",
            imported_at="2026-10-06T10:10:00+00:00",
        )
        self.assertEqual(first, {"inserted": 1, "duplicates": 0})
        self.assertEqual(duplicate, {"inserted": 0, "duplicates": 1})
        self.assertEqual(revision, {"inserted": 1, "duplicates": 0})
        loaded = self.store.load_news_event_records()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["symbol"], "INFY")
        self.assertNotEqual(loaded[0]["event_hash"], loaded[1]["event_hash"])

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

    def test_historical_series_preserve_vintages_and_resolve_latest(self):
        base = {
            "series_key": "bse_sensex_annual_average",
            "date": date(2005, 3, 31),
            "period_label": "2004-05",
            "frequency": "annual",
            "value": 5740.52,
            "unit": "Index average",
            "base_period": "1978-79 = 100",
            "source_title": "RBI Handbook 2006 Table 106",
            "source_url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8656",
            "source_authority": "Reserve Bank of India",
            "vintage_date": date(2006, 9, 18),
            "metadata": {"aggregation": "annual average"},
        }
        latest = dict(
            base,
            value=5740.99,
            source_title="RBI Handbook 2026 Table 85",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=23910",
            vintage_date=date(2026, 7, 31),
        )
        self.assertEqual(
            self.store.append_historical_series_observations([base, latest]),
            {"inserted": 2, "duplicates": 0},
        )
        self.assertEqual(
            self.store.append_historical_series_observations([base, latest]),
            {"inserted": 0, "duplicates": 2},
        )
        self.assertEqual(len(self.store.load_historical_series_observations(latest_only=False)), 2)
        resolved = self.store.load_historical_series_observations()
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["value"], 5740.99)
        self.assertEqual(resolved[0]["vintage_date"], date(2026, 7, 31))

        changed = dict(base, value=6000.0)
        with self.assertRaises(HistoricalSeriesConflictError):
            self.store.append_historical_series_observations([changed])

        contraction = dict(
            base,
            series_key="india_real_gdp_growth_pct",
            date=date(1980, 3, 31),
            period_label="1979-80",
            value=-5.2,
            unit="Per cent annual growth",
            base_period="1993-94",
            source_title="RBI Handbook 2006 Table 237",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=8787",
            metadata={"aggregation": "published annual growth rate", "allows_non_positive": True},
        )
        self.assertEqual(
            self.store.append_historical_series_observations([contraction]),
            {"inserted": 1, "duplicates": 0},
        )
        self.assertEqual(
            self.store.load_historical_series_observations(
                series_key="india_real_gdp_growth_pct"
            )[0]["value"],
            -5.2,
        )

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

    def test_earnings_import_is_append_only_and_preserves_revisions(self):
        row = {
            "symbol": "ABC",
            "company_name": "ABC Limited",
            "sector": "Industrials",
            "basis": "consolidated",
            "fiscal_year": "2026-27",
            "quarter": "Q1",
            "period_end": "2026-06-30",
            "reported_at": "2026-07-20",
            "currency": "INR",
            "unit": "crore",
            "revenue": 120.0,
            "net_profit": 10.0,
            "eps": 2.0,
            "source_url": "https://example.test/abc.pdf",
            "raw": {},
        }
        first = self.store.append_earnings_records([row], source_file_name="earnings.csv")
        duplicate = self.store.append_earnings_records([row], source_file_name="earnings.csv")
        revised = dict(row, revenue=121.0)
        revision = self.store.append_earnings_records([revised], source_file_name="earnings-revised.csv")
        self.assertEqual(first, {"inserted": 1, "duplicates": 0})
        self.assertEqual(duplicate, {"inserted": 0, "duplicates": 1})
        self.assertEqual(revision, {"inserted": 1, "duplicates": 0})
        loaded = self.store.load_earnings_records()
        self.assertEqual(len(loaded), 2)
        self.assertNotEqual(loaded[0]["record_hash"], loaded[1]["record_hash"])

    def test_workspace_snapshot_persists_latest_market_context(self):
        first = {
            "ok": True,
            "as_of_date": "2026-10-07",
            "breadth": {"evaluated": 492, "above_50dma_pct": 24.0},
        }
        second = {
            "ok": True,
            "as_of_date": "2026-10-08",
            "breadth": {"evaluated": 495, "above_50dma_pct": 27.0},
        }
        self.assertEqual(
            self.store.save_workspace_snapshot(
                snapshot_key="nifty500-market-context",
                as_of_date=date(2026, 10, 7),
                payload=first,
            ),
            {"inserted": 1, "duplicates": 0},
        )
        self.assertEqual(
            self.store.save_workspace_snapshot(
                snapshot_key="nifty500-market-context",
                as_of_date=date(2026, 10, 7),
                payload=first,
            ),
            {"inserted": 0, "duplicates": 1},
        )
        self.store.save_workspace_snapshot(
            snapshot_key="nifty500-market-context",
            as_of_date=date(2026, 10, 8),
            payload=second,
        )
        loaded = self.store.load_latest_workspace_snapshot("nifty500-market-context")
        self.assertEqual(loaded["as_of_date"], date(2026, 10, 8))
        self.assertEqual(loaded["payload"], second)


if __name__ == "__main__":
    unittest.main()
