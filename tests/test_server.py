import unittest
import socket
import urllib.error
import io
import json
import math
import tempfile
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from eod_store import EODStore

from server import (
    NIFTY_INDICES_PUBLIC_USER_AGENT,
    OFFICIAL_SECTORAL_INDICES,
    RBI_RELEASE_VINTAGE_SOURCES,
    build_checksum,
    candles_after_last_stored_session,
    calculate_seasonality,
    calculate_seasonality_validation,
    calculate_stock_screener,
    calculate_month_to_date_returns,
    calculate_index_ytd,
    classify_network_error,
    completed_history_date,
    calculate_market_breadth,
    calculate_nifty500_market_context,
    calculate_candidate_regime,
    calculate_domestic_sentiment_core,
    calculate_regime_walk_forward_validation,
    build_dashboard_market_sentiment_summary,
    build_dashboard_market_story,
    build_dashboard_overview,
    build_dashboard_fno_summary,
    build_dashboard_screener_summary,
    build_alpha_research_foundation,
    build_factor_research_foundation,
    build_point_in_time_fundamentals_foundation,
    build_fundamental_coverage_audit,
    build_fundamental_evidence_execution,
    build_financial_sector_factor_model,
    build_composite_factor_validation_contract,
    build_composite_factor_run,
    build_investable_validation,
    build_catalyst_evidence,
    build_portfolio_impact,
    build_candidate_ranking,
    build_research_card_publication,
    build_full_site_story_ux_contract,
    build_production_readiness_contract,
    build_production_health_report,
    build_candidate_overlay_contract,
    build_research_card_contract,
    build_alpha_research_story,
    build_point_in_time_universe_foundation,
    normalize_official_fundamental_export,
    build_dashboard_seasonality_summary,
    build_dashboard_seasonality_universe_summary,
    build_news_events_workspace,
    build_macro_events_calendar,
    build_stock_ytd_table,
    build_earnings_analysis,
    build_index_futures_confirmation,
    build_regime_external_cluster_readiness,
    build_historical_regime_workspace,
    build_historical_series_summary,
    build_historical_episode_stories,
    build_historical_episode_fingerprints,
    build_historical_entry_snapshot_validation,
    build_historical_point_in_time_readiness,
    build_backtests_workspace,
    build_breadth_reversal_model,
    build_stock_backtest_results,
    build_short_term_trade_recommendations,
    build_seasonality_backtest_workspace,
    aggregate_historical_closes,
    apply_recovering_market_state,
    build_regime_validation_universe,
    load_index_constituent_snapshot,
    calculate_institutional_flow_summary,
    calculate_confirmed_fpi_summary,
    calculate_macro_context_summary,
    macro_context_covers_completed_date,
    calculate_futures_oi_summary,
    calculate_global_risk_summary,
    global_risk_covers_completed_date,
    calculate_xirr,
    calculate_cashflow_matched_benchmark_return,
    calculate_portfolio_risk_metrics,
    parse_amfi_nav_history_text,
    resolve_portfolio_amfi_scheme,
    discover_sectoral_indices,
    extract_request_token,
    historical_date_ranges,
    historical_lookback_start,
    incremental_history_ranges,
    is_complete_seasonality_payload,
    normalize_index_snapshot,
    normalize_futures_eod_quotes,
    parse_daily_candles,
    parse_daily_closes,
    parse_rbi_sectoral_credit_catalogue,
    build_rbi_sectoral_credit_archive_post_data,
    parse_rbi_release_vintage,
    parse_dashboard_index_tokens,
    parse_equity_tokens,
    parse_nifty500_constituents,
    parse_institutional_flows,
    parse_nsdl_confirmed_fpi,
    parse_futures_daily_snapshot,
    parse_fred_global_csv,
    parse_fred_global_zip,
    parse_yahoo_global_chart,
    parse_rbi_macro_snapshot,
    parse_rbi_annual_series_table,
    parse_rbi_transposed_annual_growth_table,
    parse_rbi_annual_report_growth_table,
    parse_near_month_stock_futures,
    pending_futures_contracts_for_session,
    parse_nse_announcement_csv,
    parse_earnings_csv,
    parse_expense_file,
    is_supported_expense_import_file_name,
    parse_portfolio_file,
    parse_universal_portfolio_file,
    parse_mutual_fund_file,
    parse_home_loan_tracker_xlsx,
    parse_google_finance_quote_html,
    infer_portfolio_mapping,
    build_portfolio_analysis,
    build_mutual_fund_holdings_analysis,
    build_mutual_fund_performance_comparison,
    build_mutual_fund_catalogue_classification,
    build_mutual_fund_true_diversification,
    match_mutual_fund_scheme_catalogue,
    match_mutual_fund_underlying_scheme_catalogue,
    parse_amfi_scheme_catalogue_text,
    parse_amfi_market_cap_workbook,
    parse_nippon_portfolio_disclosure_links,
    parse_nippon_portfolio_workbook,
    parse_axis_portfolio_document_catalogue,
    parse_axis_portfolio_workbook,
    parse_icici_portfolio_archive,
    parse_sbi_portfolio_disclosure_links,
    parse_sbi_portfolio_workbook,
    parse_whiteoak_portfolio_catalogue,
    parse_whiteoak_portfolio_workbook,
    parse_edelweiss_portfolio_catalogue,
    parse_edelweiss_portfolio_workbook,
    parse_ppfas_portfolio_disclosure_links,
    parse_ppfas_portfolio_workbook,
    parse_motilal_portfolio_page,
    parse_motilal_portfolio_workbook,
    parse_seasonality_index_tokens,
    rank_historical_month_averages,
)


class AlphaResearchFoundationTest(unittest.TestCase):
    def test_reports_architecture_without_promoting_candidates(self):
        payload = build_alpha_research_foundation(
            {
                "ok": True,
                "coverage": {"total": 210, "ready": 208},
                "freshness": {"state": "fresh"},
            },
            earnings_record_count=24,
        )

        self.assertEqual(payload["contract_version"], "alpha-research-foundation-v1")
        self.assertEqual(payload["summary"]["ranked_ideas"], 0)
        self.assertEqual(payload["policy_history"]["state"], "complete_for_current_scope")
        self.assertEqual(payload["current_focus"]["key"], "terminal_interface_revamp")
        self.assertEqual(
            payload["site_story_ux"]["contract_version"],
            "full-site-story-and-ux-v22",
        )
        self.assertEqual(
            payload["production_readiness"]["contract_version"],
            "production-readiness-v23",
        )
        self.assertEqual(payload["research_story"]["contract_version"], "alpha-research-story-v11")
        factor = next(layer for layer in payload["layers"] if layer["key"] == "factor_core")
        decision = next(layer for layer in payload["layers"] if layer["key"] == "decision")
        self.assertEqual(factor["state"], "partial")
        self.assertIn("208 of 210", factor["summary"])
        self.assertEqual(decision["state"], "blocked")

    def test_keeps_factor_layer_blocked_without_local_universe(self):
        payload = build_alpha_research_foundation(None)

        factor = next(layer for layer in payload["layers"] if layer["key"] == "factor_core")
        catalyst = next(layer for layer in payload["layers"] if layer["key"] == "catalyst")
        self.assertEqual(factor["state"], "blocked")
        self.assertEqual(catalyst["state"], "blocked")

    def test_full_site_story_contract_covers_every_workspace(self):
        result = build_full_site_story_ux_contract()

        self.assertEqual(result["contract_version"], "full-site-story-and-ux-v22")
        self.assertEqual(result["status"], "implemented")
        self.assertEqual(result["workspace_count"], 12)
        self.assertEqual(result["reading_order"][0], "current_situation")
        self.assertEqual(result["reading_order"][-1], "expandable_audit")
        self.assertIn("historical_regimes", result["story_workspaces"])
        self.assertIn("alpha_research", result["existing_story_workspaces"])
        self.assertIn("collapsed_by_default", result["evidence_policy"])

    def test_production_readiness_contract_freezes_retry_and_backup_rules(self):
        result = build_production_readiness_contract()

        self.assertEqual(result["contract_version"], "production-readiness-v23")
        self.assertEqual(result["eod_orchestration"]["stage_count"], 15)
        self.assertEqual(result["eod_orchestration"]["maximum_attempts_per_stage"], 2)
        self.assertEqual(result["database"]["backup_method"], "sqlite_online_backup")
        self.assertEqual(result["database"]["backup_overwrite"], "forbidden")
        self.assertEqual(result["next_milestone"], "release-ready")

    def test_production_health_report_checks_store_and_static_assets(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = EODStore(root / "eod.sqlite3")
            static_root = root / "dist"
            static_root.mkdir()
            for name in build_production_readiness_contract()["required_static_assets"]:
                asset_path = static_root / name
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                asset_path.write_text("ready", encoding="utf-8")

            result = build_production_health_report(store, static_root)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["checks"]["database_integrity"])
        self.assertTrue(result["checks"]["static_assets"])
        self.assertFalse(result["provider_requests_performed"])

    def test_production_health_report_exposes_missing_static_asset(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = EODStore(root / "eod.sqlite3")
            static_root = root / "dist"
            static_root.mkdir()

            result = build_production_health_report(store, static_root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "degraded")
        self.assertIn("index.html", result["failed_assets"])

    def test_candidate_overlay_contract_keeps_missing_evidence_explicit(self):
        overlay = build_candidate_overlay_contract(
            earnings_record_count=0,
            macro_event_count=7,
            reviewed_news_count=0,
        )
        self.assertEqual(overlay["contract_version"], "candidate-overlays-v9")
        self.assertEqual(overlay["summary"]["catalyst_gates_ready"], 1)
        self.assertEqual(overlay["summary"]["trade_recommendations"], 0)
        self.assertEqual(overlay["catalyst_gates"][0]["state"], "ready")
        self.assertEqual(overlay["catalyst_gates"][1]["state"], "blocked")
        self.assertNotIn("portfolio_gates", overlay)
        self.assertEqual(overlay["overlay_rules"]["portfolio_role"], "not applicable; long-term Portfolio Analysis is a separate workspace")
        self.assertEqual(overlay["outputs"]["ranked_candidates"], [])

    def test_candidate_overlay_earnings_gate_uses_frozen_minimum(self):
        overlay = build_candidate_overlay_contract(
            earnings_record_count=20,
            macro_event_count=1,
            reviewed_news_count=3,
        )
        self.assertEqual(overlay["summary"]["catalyst_gates_ready"], 3)
        self.assertEqual(overlay["catalyst_gates"][1]["state"], "ready")
        self.assertEqual(overlay["catalyst_gates"][3]["state"], "blocked")

    def test_research_card_contract_withholds_incomplete_cards(self):
        result = build_research_card_contract({"outputs": {"ranked_candidates": []}})

        self.assertEqual(result["contract_version"], "auditable-research-cards-v10")
        self.assertEqual(result["status"], "publication_blocked")
        self.assertEqual(result["summary"]["required_fields"], 7)
        self.assertEqual(result["summary"]["publication_gates"], 3)
        self.assertEqual(result["summary"]["gates_ready"], 0)
        self.assertEqual(result["cards"], [])

    def test_research_card_candidate_does_not_bypass_remaining_gates(self):
        result = build_research_card_contract(
            {"outputs": {"ranked_candidates": [{"symbol": "TEST"}]}}
        )

        self.assertEqual(result["summary"]["gates_ready"], 1)
        self.assertEqual(result["publication_gates"][0]["state"], "ready")
        self.assertEqual(result["status"], "publication_blocked")
        self.assertEqual(result["cards"], [])

    def test_alpha_research_story_names_first_blocker_without_inventing_an_idea(self):
        layers = [
            {"title": "Validated data", "state": "ready", "summary": "Ready", "next_gate": "Maintain it."},
            {"title": "Factor core", "state": "partial", "summary": "Partial", "next_gate": "Add evidence."},
            {"title": "Ranked research cards", "state": "blocked", "summary": "No candidates.", "next_gate": "Validate a candidate."},
        ]
        cards = build_research_card_contract({"outputs": {"ranked_candidates": []}})
        story = build_alpha_research_story(layers, cards)

        self.assertEqual(story["contract_version"], "alpha-research-story-v11")
        self.assertEqual(story["status"], "evidence_incomplete")
        self.assertEqual(story["summary"]["operational"], 1)
        self.assertEqual(story["story_cards"][1]["title"], "Ranked research cards")
        self.assertEqual(story["summary"]["cards_published"], 0)

    def test_point_in_time_universe_requires_continuous_effective_dated_history(self):
        current = {
            "constituents": [
                {"symbol": "AAA", "company_name": "Alpha", "sector": "Industrials"}
            ]
        }
        incomplete = build_point_in_time_universe_foundation(
            current,
            [],
            as_of=date(2026, 10, 16),
        )
        self.assertEqual(incomplete["contract_version"], "point-in-time-universe-v13")
        self.assertEqual(incomplete["status"], "history_incomplete")
        self.assertEqual(incomplete["summary"]["gates_ready"], 2)

        snapshots = []
        for offset in range(11):
            snapshots.append(
                {
                    "index_name": "Nifty 500",
                    "effective_from": date(2021, 10, 1) + timedelta(days=180 * offset),
                    "constituents": [
                        {"symbol": "AAA", "company_name": "Alpha", "sector": "Industrials"},
                        {"symbol": "BBB", "company_name": "Beta", "sector": "Energy"},
                    ],
                }
            )
        ready = build_point_in_time_universe_foundation(
            current,
            snapshots,
            as_of=date(2026, 10, 16),
        )
        self.assertEqual(ready["status"], "validation_ready")
        self.assertEqual(ready["summary"]["gates_ready"], 5)
        self.assertEqual(ready["coverage"]["maximum_gap_days"], 180)


class FactorResearchFoundationTest(unittest.TestCase):
    @staticmethod
    def _candles(multiplier=1.0):
        start = date(2025, 1, 1)
        return [
            {
                "date": start + timedelta(days=offset),
                "open": multiplier * (100 + offset),
                "high": multiplier * (102 + offset),
                "low": multiplier * (99 + offset),
                "close": multiplier * (101 + offset),
            }
            for offset in range(300)
        ]

    def test_audits_factor_inputs_without_promoting_price_strength_to_a_rank(self):
        benchmark = self._candles()
        as_of = benchmark[-1]["date"]
        result = build_factor_research_foundation(
            {"AAA": self._candles(1.1), "BBB": self._candles(0.9)},
            benchmark,
            expected_through=as_of,
            constituent_snapshot={
                "as_of": as_of.isoformat(),
                "source": "official-test-snapshot",
                "membership_type": "current_snapshot",
                "constituents": [
                    {"symbol": "AAA", "sector": "Industrials"},
                    {"symbol": "BBB", "sector": "Financial Services"},
                ],
            },
        )

        self.assertEqual(result["contract_version"], "factor-research-foundation-v1")
        self.assertEqual(result["coverage"]["price_history_ready"], 2)
        self.assertEqual(result["coverage"]["sector_identity_ready"], 2)
        self.assertEqual(result["coverage"]["research_eligible"], 0)
        self.assertEqual(result["ranked_candidates"], [])
        self.assertEqual(result["ranking_state"], "blocked_until_all_input_gates_pass")
        self.assertIsNotNone(result["rows"][0]["momentum_12_1_pct"])
        states = {gate["key"]: gate["state"] for gate in result["gates"]}
        self.assertEqual(states["universe"], "ready")
        self.assertEqual(states["adjusted_prices"], "blocked")
        self.assertEqual(states["liquidity"], "blocked")

    def test_marks_rows_eligible_only_when_every_input_gate_is_explicit(self):
        benchmark = self._candles()
        as_of = benchmark[-1]["date"]
        result = build_factor_research_foundation(
            {"AAA": self._candles(1.1)},
            benchmark,
            expected_through=as_of,
            constituent_snapshot={
                "as_of": as_of.isoformat(),
                "source": "official-test-snapshot",
                "membership_type": "effective_dated_snapshot",
                "constituents": [{"symbol": "AAA", "sector": "Industrials"}],
            },
            market_data_evidence={
                "AAA": {
                    "adjustment_provenance_ready": True,
                    "liquidity_evidence_ready": True,
                    "positive_volume_coverage_pct": 99.0,
                    "median_daily_turnover_inr": 250_000_000.0,
                }
            },
        )

        self.assertEqual(result["status"], "factor_inputs_ready")
        self.assertEqual(result["coverage"]["research_eligible"], 1)
        self.assertEqual(result["coverage"]["liquidity_evidence_ready"], 1)
        self.assertEqual(result["ranking_state"], "inputs_ready_ranking_not_started")
        self.assertEqual(result["rows"][0]["positive_volume_coverage_pct"], 99.0)
        self.assertEqual(result["ranked_candidates"], [])

    def test_market_data_admission_excludes_failed_rows_without_hiding_them(self):
        benchmark = self._candles()
        as_of = benchmark[-1]["date"]
        histories = {
            f"S{index:02d}": self._candles(1 + index / 100)
            for index in range(20)
        }
        evidence = {
            symbol: {
                "adjustment_provenance_ready": True,
                "liquidity_evidence_ready": symbol != "S19",
                "positive_volume_coverage_pct": 99.0 if symbol != "S19" else 83.33,
                "median_daily_turnover_inr": 250_000_000.0,
            }
            for symbol in histories
        }
        result = build_factor_research_foundation(
            histories,
            benchmark,
            expected_through=as_of,
            constituent_snapshot={
                "as_of": as_of.isoformat(),
                "source": "official-test-snapshot",
                "membership_type": "current_snapshot",
                "constituents": [
                    {"symbol": symbol, "sector": "Industrials"}
                    for symbol in histories
                ],
            },
            market_data_evidence=evidence,
        )

        liquidity_gate = next(
            gate for gate in result["gates"] if gate["key"] == "liquidity"
        )
        excluded = next(row for row in result["rows"] if row["symbol"] == "S19")
        self.assertEqual(result["coverage"]["minimum_market_data_admission"], 19)
        self.assertEqual(result["coverage"]["research_eligible"], 19)
        self.assertEqual(liquidity_gate["state"], "ready")
        self.assertFalse(excluded["research_eligible"])

    def test_builds_sector_neutral_diagnostics_without_promoting_candidates(self):
        benchmark = self._candles()
        as_of = benchmark[-1]["date"]

        def trending_candles(slope):
            start = date(2025, 1, 1)
            return [
                {
                    "date": start + timedelta(days=offset),
                    "open": 100 + slope * offset,
                    "high": 102 + slope * offset,
                    "low": 99 + slope * offset,
                    "close": 101 + slope * offset,
                }
                for offset in range(300)
            ]

        histories = {
            f"S{index}": trending_candles(0.5 + index * 0.2)
            for index in range(5)
        }
        result = build_factor_research_foundation(
            histories,
            benchmark,
            expected_through=as_of,
            constituent_snapshot={
                "as_of": as_of.isoformat(),
                "source": "official-test-snapshot",
                "membership_type": "current_snapshot",
                "constituents": [
                    {"symbol": symbol, "sector": "Industrials"}
                    for symbol in histories
                ],
            },
            market_data_evidence={
                symbol: {
                    "adjustment_provenance_ready": True,
                    "liquidity_evidence_ready": True,
                }
                for symbol in histories
            },
        )

        momentum = result["sector_neutral_momentum"]
        self.assertEqual(momentum["contract_version"], "sector-neutral-momentum-v3")
        self.assertEqual(momentum["coverage"]["sector_neutral_scored"], 5)
        self.assertEqual(momentum["sectors"][0]["state"], "ready")
        self.assertEqual(len(momentum["rows"]), 5)
        self.assertEqual(momentum["ranked_candidates"], [])
        self.assertEqual(momentum["scoring_rule"]["candidate_promotion"], "disabled")
        self.assertGreater(
            momentum["rows"][0]["composite_score"],
            momentum["rows"][-1]["composite_score"],
        )

    def test_fundamentals_use_only_release_known_quarters_and_do_not_rank(self):
        period_ends = [
            "2026-09-30",
            "2026-06-30",
            "2026-03-31",
            "2025-12-31",
            "2025-09-30",
        ]
        filings = []
        for index, period_end in enumerate(period_ends):
            filings.append(
                {
                    "filing_id": f"NSE:AAA:{period_end}:0",
                    "symbol": "AAA",
                    "company_name": "AAA Limited",
                    "sector": "Industrials",
                    "basis": "consolidated",
                    "period_type": "quarterly",
                    "period_end": period_end,
                    "reported_at": (
                        datetime.fromisoformat(period_end)
                        .replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                        + timedelta(days=20)
                    ).isoformat(),
                    "revision_sequence": 0,
                    "currency": "INR",
                    "unit": "absolute",
                    "source_url": "https://nsearchives.nseindia.com/corporate/AAA.xml",
                    "facts": {
                        "revenue": 1_000.0 + index * 10,
                        "ebit": 200.0,
                        "profit_after_tax": 120.0,
                        "total_equity": 2_000.0 - index * 50,
                        "total_debt": 400.0,
                        "cash_and_equivalents": 100.0,
                        "shares_outstanding": 10.0,
                    },
                }
            )
        result = build_point_in_time_fundamentals_foundation(
            filings,
            [
                {
                    "symbol": "AAA",
                    "sector": "Industrials",
                    "factor_input_admitted": True,
                }
            ],
            {"AAA": 100.0},
            known_at=datetime(2026, 10, 31, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

        row = result["rows"][0]
        self.assertEqual(result["contract_version"], "point-in-time-fundamentals-v4")
        self.assertEqual(result["coverage"]["quality_ready"], 1)
        self.assertEqual(result["coverage"]["value_ready"], 1)
        self.assertEqual(row["quarters_known"], 5)
        self.assertIsNotNone(row["return_on_equity_pct"])
        self.assertIsNotNone(row["earnings_yield_pct"])
        self.assertEqual(result["quality_scores"], [])
        self.assertEqual(result["composite_ranks"], [])
        self.assertEqual(result["ranked_candidates"], [])

    def test_official_xbrl_normalizer_uses_period_context_and_preserves_metadata(self):
        payload = b'''<?xml version="1.0" encoding="UTF-8"?>
        <xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
          xmlns:in="https://example.test/indas">
          <xbrli:context id="quarter">
            <xbrli:entity><xbrli:identifier scheme="NSE">AAA</xbrli:identifier></xbrli:entity>
            <xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period>
          </xbrli:context>
          <xbrli:context id="instant">
            <xbrli:entity><xbrli:identifier scheme="NSE">AAA</xbrli:identifier></xbrli:entity>
            <xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period>
          </xbrli:context>
          <in:RevenueFromOperations contextRef="quarter">125</in:RevenueFromOperations>
          <in:ProfitBeforeInterestAndTax contextRef="quarter">25</in:ProfitBeforeInterestAndTax>
          <in:ProfitLossForThePeriod contextRef="quarter">17</in:ProfitLossForThePeriod>
          <in:TotalEquity contextRef="instant">300</in:TotalEquity>
          <in:CashAndCashEquivalents contextRef="instant">20</in:CashAndCashEquivalents>
          <in:TotalBorrowings contextRef="instant">75</in:TotalBorrowings>
          <in:UnmappedDisclosure contextRef="instant">9</in:UnmappedDisclosure>
        </xbrli:xbrl>'''
        result = normalize_official_fundamental_export(
            "AAA-Q2.xbrl",
            payload,
            {
                "symbol": "AAA",
                "company_name": "AAA Limited",
                "sector": "Industrials",
                "basis": "consolidated",
                "period_type": "quarterly",
                "period_end": "2026-09-30",
                "reported_at": "2026-10-20T18:30:00+05:30",
                "revision_sequence": 1,
                "source_url": "https://nsearchives.nseindia.com/corporate/AAA-Q2.xbrl",
                "unit_scale": "lakh",
            },
        )
        filing = result["filing"]
        self.assertEqual(result["contract_version"], "fundamental-xbrl-normalizer-v5")
        self.assertEqual(filing["facts"]["revenue"], 12_500_000.0)
        self.assertEqual(filing["facts"]["total_equity"], 30_000_000.0)
        self.assertEqual(filing["revision_sequence"], 1)
        self.assertEqual(result["audit"]["unmapped_taxonomy_count"], 1)
        self.assertEqual(result["audit"]["metadata_inference"], "disabled")

    def test_official_excel_normalizer_requires_an_unambiguous_value_column(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Financial Results" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>Revenue from operations</t></is></c><c r="B1"><v>80</v></c><c r="C1"><v>120</v></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Profit after tax</t></is></c><c r="B2"><v>9</v></c><c r="C2"><v>15</v></c></row>'
                '</sheetData></worksheet>',
            )
        metadata = {
            "symbol": "AAA",
            "company_name": "AAA Limited",
            "sector": "Industrials",
            "basis": "standalone",
            "period_type": "quarterly",
            "period_end": "2026-09-30",
            "reported_at": "2026-10-20T18:30:00+05:30",
            "revision_sequence": 0,
            "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
            "unit_scale": "crore",
            "value_column": 3,
        }
        result = normalize_official_fundamental_export(
            "AAA-Q2.xlsx", payload.getvalue(), metadata
        )
        self.assertEqual(result["filing"]["facts"]["revenue"], 1_200_000_000.0)
        self.assertEqual(result["filing"]["facts"]["profit_after_tax"], 150_000_000.0)
        self.assertEqual(result["audit"]["value_column"], 3)

    def test_fundamental_coverage_audit_keeps_sector_and_taxonomy_gates_visible(self):
        foundation = {
            "known_at": "2026-10-31T00:00:00+05:30",
            "rows": [
                {
                    "symbol": "AAA",
                    "sector": "Industrials",
                    "quarters_known": 5,
                    "latest_period_end": "2026-09-30",
                    "latest_reported_at": "2026-10-20T18:30:00+05:30",
                    "quality_ready": True,
                    "value_ready": True,
                    "missing_evidence": [],
                },
                {
                    "symbol": "BBB",
                    "sector": "Industrials",
                    "quarters_known": 2,
                    "quality_ready": False,
                    "value_ready": False,
                    "missing_evidence": ["five_release_known_quarters"],
                },
                {
                    "symbol": "BANK",
                    "sector": "Financial Services",
                    "quarters_known": 5,
                    "quality_ready": False,
                    "value_ready": False,
                    "missing_evidence": ["financial_sector_model"],
                },
            ],
        }
        result = build_fundamental_coverage_audit(
            foundation,
            [
                {
                    "symbol": "AAA",
                    "sector": "Industrials",
                    "audit": {
                        "mapped_facts": ["revenue", "profit_after_tax"],
                        "unmapped_taxonomy_count": 1,
                        "ambiguous_facts": [],
                        "missing_model_facts": ["ebit"],
                    },
                }
            ],
        )
        self.assertEqual(result["contract_version"], "fundamental-coverage-audit-v6")
        self.assertEqual(result["summary"]["eligible_nonfinancial_companies"], 2)
        self.assertEqual(result["summary"]["companies_with_five_quarters"], 1)
        self.assertEqual(result["summary"]["five_quarter_coverage_pct"], 50.0)
        self.assertEqual(result["taxonomy_audit"]["unmapped_observations"], 1)
        self.assertFalse(result["admission_gates"]["overall_coverage_gate_passed"])
        self.assertFalse(result["admission_gates"]["taxonomy_review_gate_passed"])
        plan = result["population_plan"]
        self.assertEqual(plan["contract_version"], "fundamental-evidence-population-v7")
        self.assertEqual(plan["sectors_in_queue"], 1)
        self.assertEqual(plan["representatives_ready"], 1)
        self.assertEqual(plan["minimum_official_files_remaining"], 0)
        self.assertEqual(plan["items"][0]["symbol"], "AAA")
        self.assertEqual(result["ranked_candidates"], [])

    def test_fundamental_population_queue_continues_partial_clean_history_first(self):
        foundation = {
            "known_at": "2026-10-31T00:00:00+05:30",
            "rows": [
                {"symbol": "AAA", "sector": "Industrials", "quarters_known": 0},
                {"symbol": "BBB", "sector": "Industrials", "quarters_known": 3},
                {"symbol": "CCC", "sector": "Healthcare", "quarters_known": 1},
                {"symbol": "BANK", "sector": "Financial Services", "quarters_known": 5},
            ],
        }
        result = build_fundamental_coverage_audit(foundation, [])
        plan = result["population_plan"]
        self.assertEqual(plan["sectors_in_queue"], 2)
        self.assertEqual(plan["representatives_ready"], 0)
        self.assertEqual(plan["minimum_official_files_remaining"], 6)
        self.assertEqual(
            [(row["sector"], row["symbol"], row["quarters_remaining"]) for row in plan["items"]],
            [("Healthcare", "CCC", 4), ("Industrials", "BBB", 2)],
        )

        execution = build_fundamental_evidence_execution(result)
        self.assertEqual(execution["contract_version"], "fundamental-evidence-execution-v14")
        self.assertEqual(execution["status"], "official_files_required")
        self.assertEqual(execution["summary"]["next_batch_companies"], 2)
        self.assertEqual(
            [(row["sequence"], row["symbol"], row["quarters_requested"]) for row in execution["next_batch"]],
            [(1, "CCC", 4), (2, "BBB", 2)],
        )
        self.assertEqual(execution["summary"]["gates_ready"], 0)

    def test_financial_sector_model_separates_subsectors_and_withholds_scores(self):
        result = build_financial_sector_factor_model(
            {
                "rows": [
                    {
                        "symbol": "BANK",
                        "sector": "Financial Services",
                        "financial_subsector": "bank",
                        "quarters_known": 5,
                    },
                    {
                        "symbol": "NBFC",
                        "sector": "Financial Services",
                        "financial_subsector": "nbfc",
                        "quarters_known": 2,
                    },
                    {
                        "symbol": "INSURE",
                        "sector": "Financial Services",
                        "quarters_known": 5,
                    },
                    {
                        "symbol": "INDUSTRIAL",
                        "sector": "Capital Goods",
                        "quarters_known": 5,
                    },
                ]
            }
        )

        self.assertEqual(result["contract_version"], "financial-sector-factor-model-v15")
        self.assertEqual(result["summary"]["financial_companies"], 3)
        self.assertEqual(result["summary"]["subsector_classified"], 2)
        self.assertEqual(result["summary"]["five_quarter_ready"], 1)
        self.assertEqual([model["key"] for model in result["models"]], ["bank", "nbfc", "insurer"])
        self.assertEqual(result["summary"]["gates_ready"], 1)
        self.assertEqual(result["outputs"]["quality_scores"], [])
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_composite_validation_contract_stays_empty_until_every_gate_passes(self):
        factor = {
            "gates": [
                {"state": "ready"},
                {"state": "ready"},
                {"state": "blocked"},
            ],
            "sector_snapshot": {
                "state": "ready",
                "membership_type": "current_snapshot",
            },
            "sector_neutral_momentum": {"validation": {"snapshots": 24}},
        }
        coverage = {
            "admission_gates": {
                "overall_coverage_gate_passed": False,
                "taxonomy_review_gate_passed": False,
            }
        }
        result = build_composite_factor_validation_contract(factor, coverage)
        self.assertEqual(result["contract_version"], "composite-factor-validation-v8")
        self.assertEqual(result["status"], "blocked_by_evidence_gates")
        self.assertEqual(result["summary"]["gates"], 5)
        self.assertEqual(result["summary"]["gates_ready"], 0)
        self.assertEqual(result["methodology"]["chronological_split"], "60% discovery, 20% validation, 20% untouched holdout; no random shuffle")
        self.assertEqual(result["methodology"]["one_way_cost_bps"], 20.0)
        self.assertEqual(result["results"]["ranked_candidates"], [])

    def test_composite_validation_contract_can_become_ready_without_creating_ranks(self):
        factor = {
            "gates": [{"state": "ready"}, {"state": "ready"}],
            "sector_snapshot": {
                "state": "ready",
                "membership_type": "effective_dated_snapshot",
            },
            "sector_neutral_momentum": {"validation": {"snapshots": 60}},
        }
        coverage = {
            "admission_gates": {
                "overall_coverage_gate_passed": True,
                "taxonomy_review_gate_passed": True,
            }
        }
        result = build_composite_factor_validation_contract(factor, coverage)
        self.assertEqual(result["status"], "ready_to_run")
        self.assertEqual(result["summary"]["gates_ready"], 5)
        self.assertEqual(result["summary"]["candidate_ranks"], 0)
        self.assertIsNone(result["results"]["holdout"])

    def test_composite_factor_run_stays_empty_while_validation_is_blocked(self):
        result = build_composite_factor_run(
            {
                "status": "blocked_by_evidence_gates",
                "methodology": {
                    "minimum_monthly_snapshots": 60,
                    "one_way_cost_bps": 20.0,
                },
            },
            [],
        )
        self.assertEqual(result["contract_version"], "composite-factor-run-v16")
        self.assertEqual(result["status"], "blocked_by_evidence_gates")
        self.assertEqual(result["summary"]["snapshots_processed"], 0)
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_composite_factor_run_preserves_chronological_splits_and_costs(self):
        snapshots = []
        start = date(2020, 1, 31)
        for month in range(60):
            signal_date = start + timedelta(days=31 * month)
            rows = []
            for index in range(10):
                rotated = (index + month) % 10
                rows.append(
                    {
                        "symbol": f"S{index:02d}",
                        "sector": "Industrials" if index < 5 else "Healthcare",
                        "momentum_z": float(10 - rotated),
                        "quality_z": float(9 - rotated),
                        "value_z": float(8 - rotated),
                        "forward_return_pct": float(5 - rotated / 2),
                    }
                )
            snapshots.append(
                {
                    "as_of_date": signal_date.isoformat(),
                    "forward_date": (signal_date + timedelta(days=21)).isoformat(),
                    "benchmark_return_pct": 1.0,
                    "universe_return_pct": 0.8,
                    "rows": rows,
                }
            )
        result = build_composite_factor_run(
            {
                "status": "ready_to_run",
                "methodology": {
                    "minimum_monthly_snapshots": 60,
                    "one_way_cost_bps": 20.0,
                },
            },
            snapshots,
        )
        self.assertEqual(result["status"], "completed_research_only")
        self.assertEqual(result["outputs"]["discovery"]["months"], 36)
        self.assertEqual(result["outputs"]["validation"]["months"], 12)
        self.assertEqual(result["outputs"]["holdout"]["months"], 12)
        self.assertEqual(result["summary"]["snapshots_processed"], 60)
        self.assertGreater(result["outputs"]["monthly_results"][0]["cost_drag_bps"], 0)
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_investable_validation_stays_empty_until_composite_run_completes(self):
        result = build_investable_validation(
            {
                "status": "blocked_by_evidence_gates",
                "outputs": {"monthly_results": [], "ranked_candidates": []},
            },
            [],
        )
        self.assertEqual(result["contract_version"], "investable-validation-v17")
        self.assertEqual(result["status"], "blocked_by_composite_run")
        self.assertEqual(result["summary"]["gates_ready"], 0)
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_investable_validation_applies_lag_slippage_and_capacity(self):
        monthly = [
            {
                "as_of_date": "2026-01-31",
                "forward_date": "2026-02-28",
                "net_return_pct": 2.0,
            },
            {
                "as_of_date": "2026-02-28",
                "forward_date": "2026-03-31",
                "net_return_pct": -1.0,
            },
        ]
        evidence = [
            {
                "as_of_date": row["as_of_date"],
                "next_session_price_coverage_pct": 100.0,
                "turnover_coverage_pct": 99.0,
                "median_daily_turnover_inr": 100_000_000.0,
                "rebalance_notional_inr": 2_000_000.0,
                "observed_spread_bps": 8.0,
            }
            for row in monthly
        ]
        result = build_investable_validation(
            {
                "status": "completed_research_only",
                "outputs": {"monthly_results": monthly, "ranked_candidates": []},
            },
            evidence,
        )
        self.assertEqual(result["status"], "completed_research_only")
        self.assertEqual(result["summary"]["gates_ready"], 5)
        self.assertEqual(result["summary"]["months_admitted"], 2)
        self.assertEqual(result["summary"]["capacity_breaches"], 0)
        self.assertGreater(result["outputs"]["summary"]["mean_modelled_slippage_bps"], 0)
        self.assertLess(
            result["outputs"]["monthly_results"][0]["investable_net_return_pct"],
            monthly[0]["net_return_pct"],
        )
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_catalyst_evidence_keeps_missing_fields_explicit(self):
        result = build_catalyst_evidence(
            {"status": "blocked_by_composite_run"},
            [{"symbol": "TEST", "reported_at": "2026-01-20", "eps": 3.0}],
            [],
            [],
        )
        self.assertEqual(result["contract_version"], "catalyst-evidence-v18")
        self.assertEqual(result["status"], "blocked_by_catalyst_evidence")
        self.assertEqual(result["summary"]["release_known_events"], 1)
        self.assertEqual(result["summary"]["expectation_ready_events"], 0)
        self.assertEqual(result["summary"]["candidate_ranks"], 0)

    def test_catalyst_evidence_audits_surprise_guidance_news_and_drift(self):
        earnings = []
        drift = []
        for index in range(20):
            reported = datetime(2026, 1, 20, 16, 0) + timedelta(days=index)
            event_key = f"S{index:02d}|{reported.isoformat()}"
            earnings.append(
                {
                    "symbol": f"S{index:02d}",
                    "reported_at": reported.isoformat(),
                    "consensus_captured_at": (reported - timedelta(days=1)).isoformat(),
                    "actual_eps": 11.0,
                    "consensus_eps": 10.0,
                    "guidance_state": "maintained",
                    "guidance_source_url": "https://example.com/filing",
                }
            )
            drift.append(
                {
                    "event_key": event_key,
                    "price_coverage_pct": 100.0,
                    "return_1d_pct": 1.0,
                    "benchmark_return_1d_pct": 0.5,
                    "return_5d_pct": 2.0,
                    "benchmark_return_5d_pct": 1.0,
                    "return_20d_pct": 3.0,
                    "benchmark_return_20d_pct": 1.5,
                }
            )
        result = build_catalyst_evidence(
            {"status": "completed_research_only"},
            earnings,
            [{"event_hash": "news-1", "source_key": "NSE", "published_at": "2026-01-20T10:00:00", "headline": "Reviewed filing"}],
            drift,
            macro_event_count=2,
        )
        self.assertEqual(result["status"], "completed_research_only")
        self.assertEqual(result["summary"]["gates_ready"], 6)
        self.assertEqual(result["summary"]["drift_ready_events"], 20)
        self.assertEqual(result["outputs"]["earnings_surprises"][0]["eps_surprise_pct"], 10.0)
        self.assertEqual(result["outputs"]["post_event_drift"][0]["excess_20d_pct"], 1.5)
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_portfolio_impact_keeps_missing_local_evidence_explicit(self):
        result = build_portfolio_impact({"status": "completed_research_only"})
        self.assertEqual(result["contract_version"], "portfolio-impact-v19")
        self.assertEqual(result["status"], "blocked_by_portfolio_evidence")
        self.assertEqual(result["summary"]["gates_ready"], 1)
        self.assertEqual(result["summary"]["impacts_calculated"], 0)
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_portfolio_impact_calculates_marginal_risk_without_ranking(self):
        daily_dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(252)]
        portfolio_returns = [
            {"date": observed.isoformat(), "return_pct": -0.4 if index % 40 == 0 else 0.12}
            for index, observed in enumerate(daily_dates)
        ]
        candidate_returns = [
            {"date": observed.isoformat(), "return_pct": -0.2 if index % 40 == 0 else 0.10}
            for index, observed in enumerate(daily_dates)
        ]
        snapshot = {
            "as_of_date": "2025-12-31",
            "transaction_history_complete": True,
            "transactions": [
                {"symbol": "AAA", "traded_at": "2024-01-10", "type": "buy"},
                {"symbol": "BBB", "traded_at": "2024-02-10", "type": "buy"},
            ],
            "positions": [
                {"symbol": "AAA", "sector": "Technology", "weight_pct": 60, "beta": 1.2, "factor_exposures": {"momentum": 0.4, "quality": 0.8, "value": -0.2}},
                {"symbol": "BBB", "sector": "Financials", "weight_pct": 40, "beta": 0.7, "factor_exposures": {"momentum": -0.1, "quality": 0.3, "value": 0.5}},
            ],
            "daily_returns": portfolio_returns,
        }
        result = build_portfolio_impact(
            {"status": "completed_research_only"},
            snapshot,
            [{
                "symbol": "CCC", "sector": "Healthcare", "proposed_weight_pct": 5,
                "beta": 0.8,
                "factor_exposures": {"momentum": 0.2, "quality": 0.6, "value": 0.1},
                "daily_returns": candidate_returns,
            }],
        )
        self.assertEqual(result["status"], "completed_research_only")
        self.assertEqual(result["summary"]["gates_ready"], 6)
        self.assertEqual(result["summary"]["impacts_calculated"], 1)
        impact = result["outputs"]["candidate_impacts"][0]
        self.assertEqual(impact["aligned_sessions"], 252)
        self.assertEqual(impact["security_hhi"]["delta"], -0.0482)
        self.assertEqual(impact["beta"]["delta"], -0.01)
        self.assertEqual(impact["guardrail_state"], "within_frozen_limits")
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_candidate_ranking_stays_blocked_without_whole_candidate_evidence(self):
        result = build_candidate_ranking(
            {"status": "completed_research_only"},
            {"status": "blocked_by_catalyst_evidence"},
            {"status": "blocked_by_portfolio_evidence", "outputs": {"candidate_impacts": []}},
        )
        self.assertEqual(result["contract_version"], "candidate-ranking-v20")
        self.assertEqual(result["status"], "blocked_by_candidate_gates")
        self.assertEqual(result["summary"]["research_ranks"], 0)
        self.assertEqual(result["summary"]["recommendations"], 0)
        self.assertEqual(result["outputs"]["ranked_candidates"], [])

    def test_candidate_ranking_rejects_failed_gate_and_orders_admitted_scores(self):
        source_versions = {
            "factor": "composite-factor-run-v16",
            "investable": "investable-validation-v17",
            "catalyst": "catalyst-evidence-v18",
            "portfolio": "portfolio-impact-v19",
        }
        impacts = [
            {
                "symbol": symbol,
                "guardrail_state": "within_frozen_limits",
                "maximum_drawdown_pct": {"delta": drawdown_delta},
                "security_hhi": {"delta": hhi_delta},
            }
            for symbol, drawdown_delta, hhi_delta in (
                ("AAA", -0.1, -0.01),
                ("BBB", -0.2, -0.02),
                ("CCC", 0.1, -0.03),
            )
        ]
        candidates = []
        for symbol, score, liquidity in (("AAA", 80.0, True), ("BBB", 99.0, False), ("CCC", 90.0, True)):
            candidates.append(
                {
                    "symbol": symbol,
                    "as_of_date": "2026-09-30",
                    "composite_score": score,
                    "factor_gate_passed": True,
                    "regime_gate_passed": True,
                    "validation_gate_passed": True,
                    "liquidity_gate_passed": liquidity,
                    "catalyst_reviewed": True,
                    "source_versions": source_versions,
                }
            )
        result = build_candidate_ranking(
            {"status": "completed_research_only"},
            {"status": "completed_research_only"},
            {"status": "completed_research_only", "outputs": {"candidate_impacts": impacts}},
            candidates,
        )
        self.assertEqual(result["status"], "completed_research_only")
        self.assertEqual(result["summary"]["gates_ready"], 6)
        self.assertEqual(result["summary"]["candidates_admitted"], 2)
        self.assertEqual(result["summary"]["candidates_rejected"], 1)
        self.assertEqual(
            [row["symbol"] for row in result["outputs"]["ranked_candidates"]],
            ["CCC", "AAA"],
        )
        self.assertEqual(result["outputs"]["rejected_candidates"][0]["failed_gates"], ["liquidity"])
        self.assertEqual(result["summary"]["recommendations"], 0)

    def test_research_card_publication_withholds_partial_draft(self):
        ranking = {
            "status": "completed_research_only",
            "outputs": {"ranked_candidates": [{"symbol": "AAA", "research_rank": 1}]},
        }
        result = build_research_card_publication(
            ranking,
            [{"symbol": "AAA", "research_rank": 1, "as_of_date": "2026-09-30", "hypothesis": "Incomplete draft."}],
        )
        self.assertEqual(result["contract_version"], "research-card-publication-v21")
        self.assertEqual(result["status"], "publication_blocked")
        self.assertEqual(result["summary"]["cards_published"], 0)
        self.assertIn("evidence", result["withheld_cards"][0]["missing_fields"])
        self.assertEqual(result["cards"], [])

    def test_research_card_publication_hashes_complete_eight_field_card(self):
        ranking = {
            "status": "completed_research_only",
            "outputs": {"ranked_candidates": [{"symbol": "AAA", "research_rank": 1}]},
        }
        draft = {
            "symbol": "AAA",
            "research_rank": 1,
            "as_of_date": "2026-09-30",
            "hypothesis": "Validated relative strength may persist over the stated review window.",
            "evidence": [
                {
                    "claim": "The frozen composite score is in the admitted set.",
                    "as_of_date": "2026-09-30",
                    "source_key": "local-factor-audit",
                    "contract_version": "candidate-ranking-v20",
                }
            ],
            "uncertainty": ["Factor relationships can weaken after the as-of date."],
            "benchmark": {
                "name": "Nifty 50",
                "horizon_sessions": 20,
                "candidate_return_pct": 3.2,
                "benchmark_return_pct": 1.1,
                "as_of_date": "2026-09-30",
                "source_key": "local-eod-store",
                "contract_version": "composite-factor-run-v16",
            },
            "horizon": {"sessions": 20, "review_rule": "Review after 20 completed sessions or an invalidation event."},
            "risk_budget": {
                "maximum_weight_pct": 3.0,
                "regime_cap_pct": 4.0,
                "liquidity_cap_pct": 5.0,
                "portfolio_cap_pct": 3.5,
            },
            "portfolio_impact": {
                "security_hhi_delta": -0.01,
                "beta_delta": 0.02,
                "drawdown_delta_pct": -0.3,
                "source_contract": "portfolio-impact-v19",
            },
            "invalidation": ["Relative strength falls below the frozen exit threshold."],
        }
        result = build_research_card_publication(ranking, [draft])
        self.assertEqual(result["status"], "completed_research_only")
        self.assertEqual(result["summary"]["gates_ready"], 6)
        self.assertEqual(result["summary"]["cards_published"], 1)
        self.assertEqual(result["summary"]["recommendations"], 0)
        self.assertEqual(len(result["cards"][0]["publication_id"]), 64)
        self.assertEqual(result["withheld_cards"], [])


class KiteHandshakeHelpersTest(unittest.TestCase):
    @staticmethod
    def _candidate_evidence(
        band="constructive", *, freshness="fresh", coverage=100.0, external=True
    ):
        external_band = band if external else "unranked"
        return {
            "trend": {"band": band},
            "breadth": {"band": band, "coverage_pct": coverage},
            "price_strength": {"band": band},
            "volatility": {
                "band": band,
                "india_vix": {"available": True, "band": band},
            },
            "institutional_flows": {"band": external_band},
            "macro_context": {"band": external_band},
            "global_risk": {"band": external_band},
            "freshness": {"state": freshness},
        }

    def test_candidate_regime_rule_is_versioned_weighted_and_validation_only(self):
        result = calculate_candidate_regime(self._candidate_evidence())
        self.assertEqual(result["rule_version"], "market-regime-candidate-v1")
        self.assertEqual(result["validation_status"], "candidate_unvalidated")
        self.assertTrue(result["classification_eligible"])
        self.assertEqual(result["label_key"], "positive_market")
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["available_weight_pct"], 100.0)
        self.assertEqual(sum(result["contract"]["cluster_weights"].values()), 1.0)
        self.assertEqual(
            result["contract"]["missing_evidence_policy"],
            "exclude_and_reduce_confidence",
        )

    def test_historical_regime_workspace_separates_price_and_economic_cycles(self):
        closes = []

        def extend(start, end, sessions):
            closes.extend(
                start + (end - start) * position / sessions
                for position in range(1, sessions + 1)
            )

        closes.append(100.0)
        extend(100.0, 135.0, 100)
        extend(135.0, 90.0, 55)
        extend(90.0, 140.0, 90)
        extend(140.0, 122.0, 35)
        extend(122.0, 142.0, 35)
        extend(142.0, 175.0, 190)
        candles = [
            {
                "date": date(2020, 1, 1) + timedelta(days=position),
                "close": close,
            }
            for position, close in enumerate(closes)
        ]

        result = build_historical_regime_workspace(candles)

        self.assertEqual(result["contract_version"], "historical-regimes-v25")
        self.assertEqual(
            result["point_in_time_readiness"]["contract_version"],
            "historical-point-in-time-readiness-v1",
        )
        self.assertGreaterEqual(result["summary"]["bull_markets"]["count"], 2)
        self.assertGreaterEqual(result["summary"]["bear_markets"]["count"], 1)
        self.assertGreaterEqual(result["summary"]["corrections"]["count"], 1)
        self.assertEqual(
            result["economic_cycles"]["recessions"]["status"],
            "macro_history_required",
        )
        self.assertEqual(result["economic_cycles"]["recessions"]["episodes"], [])
        self.assertEqual(result["history"]["analysis_frequency"], "daily")
        self.assertEqual(result["coverage_ladder"][0]["period"], "1875–1978")
        self.assertEqual(result["story_eras"][0]["period"], "1875–1947")
        self.assertEqual(len(result["story_method"]), 4)
        self.assertGreater(
            result["resolution_views"]["daily"]["observations"],
            result["resolution_views"]["monthly"]["observations"],
        )

    def test_rbi_annual_history_parser_preserves_base_breaks_and_excludes_partial_year(self):
        html = """
        <table>
          <tr><th>Year</th><th>BSE Sensex</th></tr>
          <tr><td>(Base : 1978-79 = 100)</td><td></td></tr>
          <tr><td>1979-80</td><td>122.32</td></tr>
          <tr><td>1980-81</td><td>138.87</td></tr>
          <tr><td>2006-07*</td><td>10994.75</td></tr>
        </table>
        """
        rows = parse_rbi_annual_series_table(
            html,
            series_key="bse_sensex_annual_average",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=8656",
            source_title="RBI Handbook 2006 Table 106",
            vintage_date=date(2006, 9, 18),
            value_column=1,
            unit="Index average",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], date(1980, 3, 31))
        self.assertEqual(rows[0]["base_period"], "1978-79 = 100")
        self.assertEqual(rows[-1]["period_label"], "1980-81")

    def test_rbi_release_vintage_parser_preserves_signed_value_and_release_metadata(self):
        source = {
            "release_id": "rbi-bop-q2-2023-24",
            "series_key": "india_current_account_balance_usd_mn",
            "kind": "current_account",
            "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=56991",
            "title": "Developments in India's Balance of Payments during Q2:2023-24",
            "observation_date": date(2023, 9, 30),
            "period_label": "Q2 2023-24",
            "revision_status": "preliminary",
        }
        row = parse_rbi_release_vintage(
            """
            <html><body><div>Date : Dec 26, 2023</div>
            <p>India’s current account deficit (CAD) narrowed to US$ 8.3 billion
            (1.0 per cent of GDP) in Q2:2023-24.</p></body></html>
            """,
            source=source,
        )

        self.assertEqual(row["value"], -8300.0)
        self.assertEqual(row["vintage_date"], date(2023, 12, 26))
        self.assertEqual(row["metadata"]["release_date"], "2023-12-26")
        self.assertEqual(row["metadata"]["revision_status"], "preliminary")
        self.assertTrue(row["metadata"]["allows_non_positive"])

    def test_rbi_release_vintage_parser_reads_external_debt_stock(self):
        source = {
            "release_id": "rbi-external-debt-mar-2021",
            "series_key": "india_external_debt_usd_mn",
            "kind": "external_debt",
            "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=51819",
            "title": "India's External Debt as at the end of March 2021",
            "observation_date": date(2021, 3, 31),
            "period_label": "March 2021",
            "revision_status": "provisional",
        }
        row = parse_rbi_release_vintage(
            """
            <html><body><div>Date : Jun 30, 2021</div>
            <p>At end-March 2021, India’s external debt was placed at
            US$ 570.0 billion.</p></body></html>
            """,
            source=source,
        )

        self.assertEqual(row["value"], 570000.0)
        self.assertEqual(row["metadata"]["release_date"], "2021-06-30")

    def test_rbi_credit_catalogue_discovers_release_dated_months(self):
        rows = parse_rbi_sectoral_credit_catalogue(
            """
            <table>
              <tr><th colspan="4">Apr 30, 2025</th></tr>
              <tr><td><a href=BS_PressReleaseDisplay.aspx?prid=60332>
                Sectoral Deployment of Bank Credit – March 2025
              </a></td></tr>
              <tr><th colspan="4">Mar 28, 2025</th></tr>
              <tr><td><a href="BS_PressReleaseDisplay.aspx?prid=60101">
                Sectoral Deployment of Bank Credit - February 2025
              </a></td></tr>
            </table>
            """,
            expected_year=2025,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["observation_date"], date(2025, 2, 28))
        self.assertEqual(rows[1]["release_id"], "rbi-sectoral-credit-2025-03-60332")
        self.assertEqual(rows[1]["catalogue_release_date"], date(2025, 4, 30))

    def test_rbi_credit_archive_postback_keeps_required_aspnet_state(self):
        payload = build_rbi_sectoral_credit_archive_post_data(
            """
            <input name="__VIEWSTATE" value="state&amp;one" />
            <input name="__VIEWSTATEGENERATOR" value="generator" />
            <input name="__EVENTVALIDATION" value="validation" />
            """,
            year=2024,
        ).decode("utf-8")

        self.assertIn("hdnYear=2024", payload)
        self.assertIn("__VIEWSTATE=state%26one", payload)
        self.assertIn("UsrFontCntr%24btn=", payload)

    def test_rbi_release_vintage_parser_reads_monthly_non_food_credit(self):
        source = {
            "release_id": "rbi-sectoral-credit-2025-03-60332",
            "series_key": "india_non_food_credit_growth_pct",
            "kind": "bank_credit",
            "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=60332",
            "title": "RBI Sectoral Deployment of Bank Credit – March 2025",
            "observation_date": date(2025, 3, 31),
            "period_label": "March 2025",
            "revision_status": "initial",
        }
        row = parse_rbi_release_vintage(
            """
            <html><body><div>Date : Apr 30, 2025</div>
            <p>On a year-on-year basis, non-food bank credit<sup>2</sup>
            as on the fortnight ended March 21, 2025, grew<sup>3</sup>
            by 12.0 per cent.</p></body></html>
            """,
            source=source,
        )

        self.assertEqual(row["date"], date(2025, 3, 21))
        self.assertEqual(row["value"], 12.0)
        self.assertEqual(row["frequency"], "monthly")
        self.assertEqual(row["unit"], "Per cent year-on-year")
        self.assertEqual(
            row["metadata"]["observation_basis"],
            "last reporting Friday stated in release",
        )

    def test_rbi_credit_parser_accepts_growth_remained_wording(self):
        source = {
            "release_id": "rbi-sectoral-credit-2024-08-58785",
            "series_key": "india_non_food_credit_growth_pct",
            "kind": "bank_credit",
            "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=58785",
            "title": "RBI Sectoral Deployment of Bank Credit – August 2024",
            "observation_date": date(2024, 8, 31),
            "period_label": "August 2024",
            "revision_status": "initial",
            "catalogue_release_date": date(2024, 9, 30),
        }
        row = parse_rbi_release_vintage(
            """
            <html><body><div>Date : Sep 30, 2024</div>
            <p>On a year-on-year basis, the growth in non-food bank credit
            in August 2024 remained at 15.0 per cent.</p></body></html>
            """,
            source=source,
        )

        self.assertEqual(row["date"], date(2024, 8, 31))
        self.assertEqual(row["value"], 15.0)
        self.assertEqual(row["metadata"]["observation_basis"], "catalogue month-end")

    def test_rbi_release_vintage_parser_reads_immediate_policy_repo_decision(self):
        source = {
            "release_id": "rbi-policy-repo-2022-09-30",
            "series_key": "india_policy_repo_rate_pct",
            "kind": "policy_repo_rate",
            "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=54465",
            "title": "RBI MPC resolution: 30 September 2022",
            "observation_date": date(2022, 9, 30),
            "period_label": "30 September 2022",
            "revision_status": "initial",
            "expected_value": 5.90,
            "decision": "increase",
            "change_bps": 50,
        }
        row = parse_rbi_release_vintage(
            """
            <html><body><div>Date : Sep 30, 2022</div>
            <p>Increase the policy repo rate under the liquidity adjustment
            facility (LAF) by 50 basis points from 5.40 per cent to 5.90 per
            cent with immediate effect.</p></body></html>
            """,
            source=source,
        )

        self.assertEqual(row["series_key"], "india_policy_repo_rate_pct")
        self.assertEqual(row["date"], date(2022, 9, 30))
        self.assertEqual(row["vintage_date"], date(2022, 9, 30))
        self.assertEqual(row["frequency"], "event")
        self.assertEqual(row["value"], 5.9)
        self.assertEqual(row["metadata"]["decision"], "increase")
        self.assertEqual(row["metadata"]["change_bps"], 50)
        self.assertEqual(
            row["metadata"]["observation_basis"],
            "release date; decision effective immediately",
        )

    def test_rbi_policy_repo_parser_rejects_wrong_registered_rate_or_date(self):
        source = {
            "release_id": "rbi-policy-repo-2022-12-07",
            "series_key": "india_policy_repo_rate_pct",
            "kind": "policy_repo_rate",
            "url": "https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=12419",
            "title": "RBI policy repo-rate decision: 7 December 2022",
            "observation_date": date(2022, 12, 7),
            "period_label": "7 December 2022",
            "revision_status": "initial",
            "expected_value": 6.25,
            "decision": "increase",
            "change_bps": 35,
        }
        wrong_rate = "<div>Date : Dec 07, 2022</div><p>The policy repo rate was increased to 6.50 per cent.</p>"
        with self.assertRaisesRegex(ValueError, "invalid_rbi_release_vintage"):
            parse_rbi_release_vintage(wrong_rate, source=source)

        wrong_date = "<div>Date : Dec 08, 2022</div><p>The policy repo rate was increased to 6.25 per cent.</p>"
        with self.assertRaisesRegex(ValueError, "invalid_rbi_release_vintage"):
            parse_rbi_release_vintage(wrong_date, source=source)

    def test_rbi_policy_repo_parser_preserves_first_post_tightening_hold(self):
        source = {
            "release_id": "rbi-policy-repo-2023-04-06",
            "series_key": "india_policy_repo_rate_pct",
            "kind": "policy_repo_rate",
            "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=55472",
            "title": "RBI MPC resolution: 6 April 2023",
            "observation_date": date(2023, 4, 6),
            "period_label": "6 April 2023",
            "revision_status": "initial",
            "expected_value": 6.50,
            "decision": "hold",
            "change_bps": 0,
        }
        row = parse_rbi_release_vintage(
            """
            <html><body><div>Date : Apr 06, 2023</div>
            <p>Keep the policy repo rate under the liquidity adjustment
            facility (LAF) unchanged at 6.50 per cent.</p></body></html>
            """,
            source=source,
        )

        self.assertEqual(row["date"], date(2023, 4, 6))
        self.assertEqual(row["value"], 6.5)
        self.assertEqual(row["metadata"]["decision"], "hold")
        self.assertEqual(row["metadata"]["change_bps"], 0)
        self.assertEqual(row["metadata"]["revision_status"], "initial")

    def test_rbi_policy_repo_registry_preserves_2021_to_2022_pause_cycle(self):
        expected_meetings = (
            (date(2021, 2, 5), "51077"),
            (date(2021, 4, 7), "51381"),
            (date(2021, 6, 4), "51683"),
            (date(2021, 8, 6), "52011"),
            (date(2021, 10, 8), "52366"),
            (date(2021, 12, 8), "52687"),
            (date(2022, 2, 10), "53247"),
            (date(2022, 4, 8), "53537"),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], 4.00)
            self.assertEqual(source["decision"], "hold")
            self.assertEqual(source["change_bps"], 0)
            self.assertIn(press_release_id, source["url"])

            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided to keep the policy
                repo rate unchanged at 4.00 per cent.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], 4.0)
            self.assertEqual(row["metadata"]["decision"], "hold")
            self.assertEqual(row["metadata"]["change_bps"], 0)

    def test_rbi_policy_repo_registry_preserves_2020_pandemic_cycle(self):
        expected_meetings = (
            (date(2020, 2, 6), "49342", 5.15, "hold", 0),
            (date(2020, 3, 27), "49581", 4.40, "decrease", -75),
            (date(2020, 5, 22), "49843", 4.00, "decrease", -40),
            (date(2020, 8, 6), "50175", 4.00, "hold", 0),
            (date(2020, 10, 9), "50479", 4.00, "hold", 0),
            (date(2020, 12, 4), "50747", 4.00, "hold", 0),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"reduce the policy repo rate by {abs(change_bps)} basis points to {rate:.2f} per cent"
                if decision == "decrease"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_rbi_policy_repo_registry_preserves_2019_easing_cycle(self):
        expected_meetings = (
            (date(2019, 2, 7), "46235", 6.25, "decrease", -25),
            (date(2019, 4, 4), "46722", 6.00, "decrease", -25),
            (date(2019, 6, 6), "47225", 5.75, "decrease", -25),
            (date(2019, 8, 7), "47818", 5.40, "decrease", -35),
            (date(2019, 10, 4), "48319", 5.15, "decrease", -25),
            (date(2019, 12, 5), "48802", 5.15, "hold", 0),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"reduce the policy repo rate by {abs(change_bps)} basis points to {rate:.2f} per cent"
                if decision == "decrease"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_rbi_policy_repo_registry_preserves_2018_tightening_cycle(self):
        expected_meetings = (
            (date(2018, 2, 7), "43078", 6.00, "hold", 0),
            (date(2018, 4, 5), "43573", 6.00, "hold", 0),
            (date(2018, 6, 6), "44125", 6.25, "increase", 25),
            (date(2018, 8, 1), "44636", 6.50, "increase", 25),
            (date(2018, 10, 5), "45152", 6.50, "hold", 0),
            (date(2018, 12, 5), "45656", 6.50, "hold", 0),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"increase the policy repo rate by {change_bps} basis points to {rate:.2f} per cent"
                if decision == "increase"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_rbi_policy_repo_registry_preserves_2017_easing_cycle(self):
        expected_meetings = (
            (date(2017, 2, 8), "39505", 6.25, "hold", 0),
            (date(2017, 4, 6), "40069", 6.25, "hold", 0),
            (date(2017, 6, 7), "40685", 6.25, "hold", 0),
            (date(2017, 8, 2), "41256", 6.00, "decrease", -25),
            (date(2017, 10, 4), "41852", 6.00, "hold", 0),
            (date(2017, 12, 6), "42476", 6.00, "hold", 0),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"reduce the policy repo rate by {abs(change_bps)} basis points to {rate:.2f} per cent"
                if decision == "decrease"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_rbi_policy_repo_registry_preserves_2016_policy_framework_transition(self):
        expected_meetings = (
            (date(2016, 2, 2), "36124", 6.75, "hold", 0),
            (date(2016, 4, 5), "36654", 6.50, "decrease", -25),
            (date(2016, 6, 7), "37151", 6.50, "hold", 0),
            (date(2016, 8, 9), "37734", 6.50, "hold", 0),
            (date(2016, 10, 4), "38224", 6.25, "decrease", -25),
            (date(2016, 12, 7), "38818", 6.25, "hold", 0),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"reduce the policy repo rate by {abs(change_bps)} basis points to {rate:.2f} per cent"
                if decision == "decrease"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Reserve Bank decided to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_rbi_policy_repo_registry_preserves_remaining_2023_hold_meetings(self):
        expected_meetings = (
            (date(2023, 6, 8), "55814"),
            (date(2023, 8, 10), "56173"),
            (date(2023, 10, 6), "56502"),
            (date(2023, 12, 8), "56888"),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], 6.50)
            self.assertEqual(source["decision"], "hold")
            self.assertEqual(source["change_bps"], 0)
            self.assertIn(press_release_id, source["url"])

            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided unanimously to keep
                the policy repo rate unchanged at 6.50 per cent.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], 6.5)
            self.assertEqual(row["metadata"]["decision"], "hold")
            self.assertEqual(row["metadata"]["change_bps"], 0)

    def test_rbi_policy_repo_registry_preserves_all_2024_hold_meetings(self):
        expected_meetings = (
            (date(2024, 2, 8), "57275"),
            (date(2024, 4, 5), "57637"),
            (date(2024, 6, 7), "58050"),
            (date(2024, 8, 8), "58447"),
            (date(2024, 10, 9), "58850"),
            (date(2024, 12, 6), "59244"),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], 6.50)
            self.assertEqual(source["decision"], "hold")
            self.assertEqual(source["change_bps"], 0)
            self.assertIn(press_release_id, source["url"])

            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee decided to keep the policy
                repo rate unchanged at 6.50 per cent.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], 6.5)
            self.assertEqual(row["metadata"]["decision"], "hold")
            self.assertEqual(row["metadata"]["change_bps"], 0)

    def test_rbi_policy_repo_registry_preserves_complete_2025_easing_cycle(self):
        expected_meetings = (
            (date(2025, 2, 7), "59692", 6.25, "decrease", -25),
            (date(2025, 4, 9), "60176", 6.00, "decrease", -25),
            (date(2025, 6, 6), "60604", 5.50, "decrease", -50),
            (date(2025, 8, 6), "60957", 5.50, "hold", 0),
            (date(2025, 10, 1), "61332", 5.50, "hold", 0),
            (date(2025, 12, 5), "61749", 5.25, "decrease", -25),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"reduce the policy repo rate by {abs(change_bps)} basis points to {rate:.2f} per cent"
                if decision == "decrease"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee voted to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_rbi_policy_repo_registry_preserves_completed_2026_meetings(self):
        expected_meetings = (
            (date(2026, 2, 6), "62169", 5.25, "hold", 0),
            (date(2026, 4, 8), "62514", 5.25, "hold", 0),
            (date(2026, 6, 5), "62863", 5.25, "hold", 0),
            (date(2026, 8, 5), "63287", 5.25, "hold", 0),
            (date(2026, 10, 7), "63742", 5.50, "increase", 25),
        )
        policy_sources = {
            source["observation_date"]: source
            for source in RBI_RELEASE_VINTAGE_SOURCES
            if source["kind"] == "policy_repo_rate"
        }

        for meeting_date, press_release_id, rate, decision, change_bps in expected_meetings:
            source = policy_sources[meeting_date]
            self.assertEqual(source["expected_value"], rate)
            self.assertEqual(source["decision"], decision)
            self.assertEqual(source["change_bps"], change_bps)
            self.assertIn(press_release_id, source["url"])

            decision_wording = (
                f"increase the policy repo rate by {change_bps} basis points to {rate:.2f} per cent"
                if decision == "increase"
                else f"keep the policy repo rate unchanged at {rate:.2f} per cent"
            )
            row = parse_rbi_release_vintage(
                f"""
                <html><body><div>Date : {meeting_date.strftime('%b %d, %Y')}</div>
                <p>The Monetary Policy Committee voted to {decision_wording}
                with immediate effect.</p></body></html>
                """,
                source=source,
            )
            self.assertEqual(row["date"], meeting_date)
            self.assertEqual(row["value"], rate)
            self.assertEqual(row["metadata"]["decision"], decision)
            self.assertEqual(row["metadata"]["change_bps"], change_bps)

    def test_historical_series_summary_withholds_wpi_change_across_base_break(self):
        common = {
            "frequency": "annual",
            "unit": "Index average",
            "source_title": "RBI Handbook",
            "source_url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=1",
            "source_authority": "Reserve Bank of India",
            "vintage_date": date(2026, 7, 31),
            "retrieved_at": "2026-10-09T00:00:00+00:00",
            "metadata": {},
        }
        rows = [
            dict(common, series_key="bse_sensex_annual_average", date=date(2024, 3, 31), period_label="2023-24", value=100.0, base_period="1978-79 = 100"),
            dict(common, series_key="bse_sensex_annual_average", date=date(2025, 3, 31), period_label="2024-25", value=110.0, base_period="1978-79 = 100"),
            dict(common, series_key="india_wpi_all_commodities_annual_average", date=date(2024, 3, 31), period_label="2023-24", value=151.4, base_period="2011-12 = 100"),
            dict(common, series_key="india_wpi_all_commodities_annual_average", date=date(2025, 3, 31), period_label="2024-25", value=101.0, base_period="2022-23 = 100"),
        ]
        summary = build_historical_series_summary(rows)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["joined_annual_observations"], 2)
        self.assertEqual(summary["timeline"][-1]["sensex_change_pct"], 10.0)
        self.assertIsNone(summary["timeline"][-1]["wpi_change_pct"])

    def test_rbi_growth_parser_keeps_contractions_and_publication_status(self):
        html = """
        <table>
          <tr><th>Old series (Base : 1993-94)</th></tr>
          <tr><td>1978-79</td><td>5.5</td></tr>
          <tr><td>1979-80</td><td>-5.2</td></tr>
          <tr><td>2004-05 RE</td><td>6.9</td></tr>
        </table>
        """
        rows = parse_rbi_annual_series_table(
            html,
            series_key="india_real_gdp_growth_pct",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=8787",
            source_title="RBI Handbook 2006 Table 237",
            vintage_date=date(2006, 9, 18),
            value_column=1,
            unit="Per cent annual growth",
            aggregation="published annual growth rate",
            allow_non_positive=True,
        )
        self.assertEqual([row["value"] for row in rows], [5.5, -5.2, 6.9])
        self.assertEqual(rows[1]["base_period"], "1993-94")
        self.assertEqual(rows[-1]["period_label"], "2004-05")
        self.assertEqual(rows[-1]["metadata"]["publication_status"], "RE")

    def test_rbi_transposed_growth_parser_preserves_financial_years_and_negative_growth(self):
        html = """
        <table>
          <tr><th>Item/Year</th><th>2018-19</th><th>2019-20</th><th>2020-21</th><th>2021-22</th></tr>
          <tr><td>Annual Growth Rate</td><td></td><td></td><td></td><td></td></tr>
          <tr><td>Gross Domestic Product</td><td>6.45</td><td>3.87</td><td>-5.78</td><td>9.69</td></tr>
        </table>
        """
        rows = parse_rbi_transposed_annual_growth_table(
            html,
            series_key="india_real_gdp_growth_pct",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=22696",
            source_title="RBI Handbook 2024 Table 222",
            vintage_date=date(2024, 9, 13),
            row_label="Gross Domestic Product",
            unit="Per cent annual growth",
            aggregation="published annual growth rate",
            base_period="2011-12",
            allow_non_positive=True,
        )
        self.assertEqual([row["period_label"] for row in rows], ["2018-19", "2019-20", "2020-21", "2021-22"])
        self.assertEqual([row["value"] for row in rows], [6.45, 3.87, -5.78, 9.69])
        self.assertEqual(rows[0]["date"], date(2019, 3, 31))
        self.assertEqual(rows[0]["base_period"], "2011-12")
        self.assertTrue(rows[2]["metadata"]["allows_non_positive"])

    def test_rbi_annual_report_growth_parser_excludes_advance_estimate_and_share_columns(self):
        html = """
        <table>
          <tr><th>Average 2018-19 to 2022-23</th><th>2023-24</th><th>2024-25</th><th>2025-26*</th><th>2023-24</th><th>2024-25</th><th>2025-26*</th></tr>
          <tr><td>8. GDP</td><td>4.4</td><td>7.2</td><td>7.1</td><td>7.6</td><td>100.0</td><td>100.0</td><td>100.0</td></tr>
        </table>
        """
        rows = parse_rbi_annual_report_growth_table(
            html,
            series_key="india_real_gdp_growth_pct",
            source_url="https://rbi.org.in/scripts/AnnualReportPublications.aspx?Id=1475",
            source_title="RBI Annual Report 2025-26 GDP appendix",
            vintage_date=date(2026, 5, 29),
            row_label="8. GDP",
            unit="Per cent annual growth",
            aggregation="published annual growth rate",
            base_period="2022-23",
            allow_non_positive=True,
        )
        self.assertEqual([row["period_label"] for row in rows], ["2023-24", "2024-25"])
        self.assertEqual([row["value"] for row in rows], [7.2, 7.1])
        self.assertEqual(rows[-1]["date"], date(2025, 3, 31))
        self.assertTrue(rows[-1]["metadata"]["advance_estimates_excluded"])

    def test_rbi_fiscal_parser_keeps_first_table_when_page_repeats_years(self):
        html = """
        <table>
          <tr><th>Year</th><th>Gross fiscal deficit</th></tr>
          <tr><td>1984-85</td><td>6.79</td></tr>
          <tr><td>1990-91</td><td>7.61</td></tr>
        </table>
        <table>
          <tr><th>Year</th><th>Revenue expenditure</th></tr>
          <tr><td>1984-85</td><td>10.79</td></tr>
          <tr><td>1990-91</td><td>12.54</td></tr>
        </table>
        """
        rows = parse_rbi_annual_series_table(
            html,
            series_key="central_gross_fiscal_deficit_pct_gdp",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=24062",
            source_title="RBI Handbook 2026 Table 237",
            vintage_date=date(2026, 7, 31),
            value_column=1,
            unit="Per cent of GDP",
            aggregation="financial-year fiscal ratio",
            base_period_override="Not applicable",
            duplicate_resolution="first",
        )
        self.assertEqual([row["value"] for row in rows], [6.79, 7.61])

    def test_rbi_reserve_parser_selects_total_us_dollar_stock(self):
        html = """
        <table>
          <tr><th>Year</th><th>SDR ₹</th><th>SDR USD</th><th>Gold ₹</th><th>Gold USD</th><th>FCA ₹</th><th>FCA USD</th><th>RTP ₹</th><th>RTP USD</th><th>Total ₹</th><th>Total USD</th></tr>
          <tr><td>1997-98</td><td>4</td><td>1</td><td>13394</td><td>3391</td><td>102507</td><td>25975</td><td>-</td><td>-</td><td>115905</td><td>29367</td></tr>
          <tr><td>1998-99</td><td>34</td><td>8</td><td>12559</td><td>2960</td><td>125412</td><td>29522</td><td>-</td><td>-</td><td>138005</td><td>32490</td></tr>
        </table>
        """
        rows = parse_rbi_annual_series_table(
            html,
            series_key="india_foreign_exchange_reserves_usd_mn",
            source_url="https://rbi.org.in/scripts/PublicationsView.aspx?id=22624",
            source_title="RBI Handbook 2024 Table 150",
            vintage_date=date(2024, 9, 13),
            value_column=10,
            unit="US dollar million",
            aggregation="end of financial year stock",
            base_period_override="Not applicable",
        )
        self.assertEqual([row["value"] for row in rows], [29367.0, 32490.0])

    def test_historical_episode_story_joins_crisis_evidence(self):
        common = {
            "frequency": "annual",
            "source_title": "RBI Handbook",
            "source_url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=1",
            "source_authority": "Reserve Bank of India",
            "vintage_date": date(2026, 7, 31),
            "retrieved_at": "2026-10-10T00:00:00+00:00",
            "metadata": {},
        }
        values = {
            "bse_sensex_annual_average": ((1038.66, 1908.85, 2615.37), "Index average", "1978-79 = 100"),
            "india_wpi_all_commodities_annual_average": ((182.7, 207.8, 228.7), "Index average", "1981-82 = 100"),
            "india_real_gdp_growth_pct": ((5.6, 1.3, 5.1), "Per cent annual growth", "1993-94"),
            "india_call_money_rate_annual": ((15.85, 19.57, 14.42), "Per cent per annum", "Base not stated"),
            "inr_usd_annual_average": ((17.9428, 24.4737, 30.6488), "Indian rupees per US dollar", "Base not stated"),
            "central_gross_fiscal_deficit_pct_gdp": ((7.61, 5.39, 5.19), "Per cent of GDP", "Not applicable"),
            "india_foreign_exchange_reserves_usd_mn": ((5834, 9220, 9832), "US dollar million", "Not applicable"),
        }
        rows = []
        periods = (("1990-91", date(1991, 3, 31)), ("1991-92", date(1992, 3, 31)), ("1992-93", date(1993, 3, 31)))
        for key, (series_values, unit, base_period) in values.items():
            for (period, observation_date), value in zip(periods, series_values):
                rows.append(dict(common, series_key=key, date=observation_date, period_label=period, value=value, unit=unit, base_period=base_period))
        summary = build_historical_series_summary(rows)
        episodes = build_historical_episode_stories(summary)
        crisis = next(item for item in episodes if item["key"] == "bop_crisis_1991")
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(crisis["research_state"], "Official annual evidence connected")
        self.assertGreaterEqual(len(crisis["evidence"]), 5)
        self.assertEqual(
            next(item for item in crisis["evidence"] if item["label"] == "Growth low")["period"],
            "1991-92",
        )

    def test_historical_episode_story_extends_through_technology_bust_and_recovery(self):
        periods = (
            ("1999-00", date(2000, 3, 31)),
            ("2000-01", date(2001, 3, 31)),
            ("2001-02", date(2002, 3, 31)),
            ("2002-03", date(2003, 3, 31)),
            ("2003-04", date(2004, 3, 31)),
        )
        series_values = {
            "bse_sensex_annual_average": (4658.63, 4269.69, 3331.95, 3206.29, 4492.19),
            "india_wpi_all_commodities_annual_average": (145.3, 155.7, 161.3, 166.8, 175.9),
            "india_real_gdp_growth_pct": (6.1, 4.4, 5.8, 3.8, 8.5),
            "india_call_money_rate_annual": (8.87, 9.15, 7.16, 5.89, 4.62),
            "inr_usd_annual_average": (43.3327, 45.6844, 47.6919, 48.3953, 45.9516),
            "central_gross_fiscal_deficit_pct_gdp": (5.18, 5.46, 5.98, 5.72, 4.34),
            "india_foreign_exchange_reserves_usd_mn": (38036, 42281, 54106, 76100, 112959),
        }
        units = {
            "bse_sensex_annual_average": "Index average",
            "india_wpi_all_commodities_annual_average": "Index average",
            "india_real_gdp_growth_pct": "Per cent annual growth",
            "india_call_money_rate_annual": "Per cent per annum",
            "inr_usd_annual_average": "Indian rupees per US dollar",
            "central_gross_fiscal_deficit_pct_gdp": "Per cent of GDP",
            "india_foreign_exchange_reserves_usd_mn": "US dollar million",
        }
        rows = []
        for key, values in series_values.items():
            for (period, observation_date), value in zip(periods, values):
                rows.append({
                    "series_key": key,
                    "date": observation_date,
                    "period_label": period,
                    "frequency": "annual",
                    "value": value,
                    "unit": units[key],
                    "base_period": "1993-94 = 100" if "wpi" in key else "Not applicable",
                    "source_title": "RBI Handbook",
                    "source_url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=1",
                    "source_authority": "Reserve Bank of India",
                    "vintage_date": date(2024, 9, 13),
                    "retrieved_at": "2026-10-10T00:00:00+00:00",
                    "metadata": {},
                })
        episodes = build_historical_episode_stories(build_historical_series_summary(rows))
        technology = next(item for item in episodes if item["key"] == "technology_boom_bust_1999")
        self.assertEqual(technology["research_state"], "Official annual evidence connected")
        self.assertEqual(
            next(item for item in technology["evidence"] if item["label"] == "Sensex annual change low")["period"],
            "2001-02",
        )
        self.assertGreater(
            next(item for item in technology["evidence"] if item["label"] == "FX-reserve stock path")["value"],
            190,
        )

    def test_historical_episode_story_extends_through_global_financial_crisis(self):
        periods = (
            ("2003-04", date(2004, 3, 31)),
            ("2004-05", date(2005, 3, 31)),
            ("2005-06", date(2006, 3, 31)),
            ("2006-07", date(2007, 3, 31)),
            ("2007-08", date(2008, 3, 31)),
            ("2008-09", date(2009, 3, 31)),
            ("2009-10", date(2010, 3, 31)),
        )
        series_values = {
            "bse_sensex_annual_average": (4492.19, 5740.99, 8278.55, 10994.75, 16568.89, 12365.55, 15584.17),
            "india_wpi_all_commodities_annual_average": (175.9, 187.3, 195.6, 206.2, 215.9, 233.9, 242.8),
            "india_real_gdp_growth_pct": (8.5, 7.5, 9.5, 9.6, 9.3, 6.7, 8.6),
            "india_call_money_rate_annual": (4.62, 4.71, 5.60, 7.22, 6.07, 7.17, 3.29),
            "inr_usd_annual_average": (45.9516, 44.9315, 44.2735, 45.2849, 40.2410, 45.9170, 47.4179),
            "central_gross_fiscal_deficit_pct_gdp": (4.34, 3.88, 4.01, 3.32, 2.54, 5.99, 6.46),
            "india_foreign_exchange_reserves_usd_mn": (112959, 141514, 151622, 199179, 309723, 251985, 279057),
        }
        units = {
            "bse_sensex_annual_average": "Index average",
            "india_wpi_all_commodities_annual_average": "Index average",
            "india_real_gdp_growth_pct": "Per cent annual growth",
            "india_call_money_rate_annual": "Per cent per annum",
            "inr_usd_annual_average": "Indian rupees per US dollar",
            "central_gross_fiscal_deficit_pct_gdp": "Per cent of GDP",
            "india_foreign_exchange_reserves_usd_mn": "US dollar million",
        }
        rows = []
        for key, values in series_values.items():
            for (period, observation_date), value in zip(periods, values):
                rows.append({
                    "series_key": key,
                    "date": observation_date,
                    "period_label": period,
                    "frequency": "annual",
                    "value": value,
                    "unit": units[key],
                    "base_period": "1993-94 = 100" if "wpi" in key else "Not applicable",
                    "source_title": "RBI Handbook",
                    "source_url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=1",
                    "source_authority": "Reserve Bank of India",
                    "vintage_date": date(2026, 7, 31),
                    "retrieved_at": "2026-10-10T00:00:00+00:00",
                    "metadata": {},
                })
        episodes = build_historical_episode_stories(build_historical_series_summary(rows))
        boom = next(item for item in episodes if item["key"] == "credit_investment_boom_2003")
        crisis = next(item for item in episodes if item["key"] == "global_financial_crisis_2008")
        self.assertEqual(len(episodes), 17)
        self.assertEqual(boom["research_state"], "Official annual evidence connected")
        self.assertEqual(crisis["research_state"], "Official annual evidence connected")
        self.assertEqual(
            next(item for item in crisis["evidence"] if item["label"] == "Sensex annual change low")["period"],
            "2008-09",
        )
        self.assertEqual(
            next(item for item in crisis["evidence"] if item["label"] == "Rupee depreciation high")["period"],
            "2008-09",
        )
        self.assertGreater(
            next(item for item in crisis["evidence"] if item["label"] == "Central fiscal deficit high")["value"],
            6,
        )

    def test_historical_episode_story_extends_through_pre_pandemic_slowdown(self):
        periods = tuple((f"{year}-{str(year + 1)[-2:]}", date(year + 1, 3, 31)) for year in range(2009, 2020))
        series_values = {
            "bse_sensex_annual_average": (15584, 18605, 17646, 18836, 20355, 27212, 26191, 28118, 33170, 36060, 37892),
            "india_wpi_all_commodities_annual_average": (242.8, 265.9, 289.6, 296.2, 305.4, 181.2, 176.7, 183.0, 188.9, 201.1, 210.1),
            "india_real_gdp_growth_pct": (8.6, 8.9, 6.7, 5.4, 6.3, 7.1, 7.2, 8.26, 6.8, 6.45, 3.87),
            "india_call_money_rate_annual": (3.29, 5.89, 8.22, 8.09, 8.28, 7.97, 7.02, 6.44, 6.06, 6.23, 5.37),
            "inr_usd_annual_average": (47.42, 45.58, 47.92, 54.41, 60.50, 61.15, 65.46, 67.07, 64.45, 69.92, 70.90),
            "central_gross_fiscal_deficit_pct_gdp": (6.46, 4.87, 5.91, 4.93, 4.48, 4.10, 3.87, 3.49, 3.46, 3.39, 4.59),
            "india_foreign_exchange_reserves_usd_mn": (279057, 304818, 294398, 292046, 304224, 341638, 360176, 369955, 424545, 412871, 477807),
        }
        units = {
            "bse_sensex_annual_average": "Index average",
            "india_wpi_all_commodities_annual_average": "Index average",
            "india_real_gdp_growth_pct": "Per cent annual growth",
            "india_call_money_rate_annual": "Per cent per annum",
            "inr_usd_annual_average": "Indian rupees per US dollar",
            "central_gross_fiscal_deficit_pct_gdp": "Per cent of GDP",
            "india_foreign_exchange_reserves_usd_mn": "US dollar million",
        }
        rows = []
        for key, values in series_values.items():
            for (period, observation_date), value in zip(periods, values):
                rows.append({
                    "series_key": key,
                    "date": observation_date,
                    "period_label": period,
                    "frequency": "annual",
                    "value": value,
                    "unit": units[key],
                    "base_period": "2011-12" if key == "india_real_gdp_growth_pct" else "Not applicable",
                    "source_title": "RBI Handbook",
                    "source_url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=1",
                    "source_authority": "Reserve Bank of India",
                    "vintage_date": date(2024, 9, 13),
                    "retrieved_at": "2026-10-10T00:00:00+00:00",
                    "metadata": {},
                })
        episodes = build_historical_episode_stories(build_historical_series_summary(rows))
        taper = next(item for item in episodes if item["key"] == "taper_rupee_stress_2012")
        slowdown = next(item for item in episodes if item["key"] == "nbfc_slowdown_2018")
        self.assertEqual(len(episodes), 17)
        self.assertEqual(taper["research_state"], "Official annual evidence connected")
        self.assertEqual(slowdown["research_state"], "Official annual evidence connected")
        self.assertEqual(
            next(item for item in slowdown["evidence"] if item["label"] == "Growth low")["period"],
            "2019-20",
        )
        self.assertEqual(
            next(item for item in taper["evidence"] if item["label"] == "Rupee depreciation high")["period"],
            "2012-13",
        )

    def test_historical_episode_story_extends_through_pandemic_and_disinflation(self):
        periods = tuple((f"{year}-{str(year + 1)[-2:]}", date(year + 1, 3, 31)) for year in range(2019, 2025))
        series_values = {
            "bse_sensex_annual_average": (37892, 40826, 55775, 58308, 66823, 78212),
            "india_wpi_all_commodities_annual_average": (210.1, 212.8, 240.4, 152.5, 99.3, 101.0),
            "india_real_gdp_growth_pct": (3.87, -5.78, 9.69, 6.99, 7.2, 7.1),
            "india_call_money_rate_annual": (5.37, 3.46, 3.26, 5.42, 6.63, 6.51),
            "inr_usd_annual_average": (70.90, 74.22, 74.50, 80.36, 82.79, 84.58),
            "central_gross_fiscal_deficit_pct_gdp": (4.59, 9.16, 6.71, 6.46, 5.49, 4.76),
            "india_foreign_exchange_reserves_usd_mn": (477807, 576984, 607309, 578449, 646419, 668330),
        }
        units = {
            "bse_sensex_annual_average": "Index average",
            "india_wpi_all_commodities_annual_average": "Index average",
            "india_real_gdp_growth_pct": "Per cent annual growth",
            "india_call_money_rate_annual": "Per cent per annum",
            "inr_usd_annual_average": "Indian rupees per US dollar",
            "central_gross_fiscal_deficit_pct_gdp": "Per cent of GDP",
            "india_foreign_exchange_reserves_usd_mn": "US dollar million",
        }
        rows = []
        for key, values in series_values.items():
            for (period, observation_date), value in zip(periods, values):
                rows.append({
                    "series_key": key,
                    "date": observation_date,
                    "period_label": period,
                    "frequency": "annual",
                    "value": value,
                    "unit": units[key],
                    "base_period": "2022-23" if key == "india_real_gdp_growth_pct" else "Not applicable",
                    "source_title": "RBI official history",
                    "source_url": "https://rbi.org.in/scripts/AnnualReportPublications.aspx?Id=1475",
                    "source_authority": "Reserve Bank of India",
                    "vintage_date": date(2026, 5, 29),
                    "retrieved_at": "2026-10-10T00:00:00+00:00",
                    "metadata": {},
                })
        summary = build_historical_series_summary(rows)
        episodes = build_historical_episode_stories(summary)
        by_key = {episode["key"]: episode for episode in episodes}
        self.assertEqual(len(episodes), 17)
        self.assertEqual(by_key["pandemic_shock_2020"]["research_state"], "Official annual evidence connected")
        self.assertEqual(by_key["reopening_liquidity_recovery_2021"]["research_state"], "Official annual evidence connected")
        self.assertEqual(by_key["ukraine_inflation_tightening_2022"]["research_state"], "Official annual evidence connected")
        self.assertEqual(by_key["disinflation_resilience_2023"]["research_state"], "Official annual evidence connected")
        self.assertEqual(
            next(point for point in by_key["pandemic_shock_2020"]["evidence"] if point["label"] == "Growth low")["period"],
            "2020-21",
        )
        self.assertEqual(
            next(point for point in by_key["ukraine_inflation_tightening_2022"]["evidence"] if point["label"] == "Money-market stress high")["period"],
            "2022-23",
        )
        self.assertEqual(summary["timeline"][-1]["real_gdp_growth_pct"], 7.1)

    def test_historical_episode_fingerprints_keep_missing_categories_and_block_classifier_use(self):
        episodes = [
            {"key": "shock", "title": "Shock", "window": {"start_financial_year": 2019, "end_financial_year": 2020}},
            {"key": "recovery", "title": "Recovery", "window": {"start_financial_year": 2020, "end_financial_year": 2021}},
        ]
        timeline = [
            {"period": "2019-20", "real_gdp_growth_pct": 3.9, "wpi_change_pct": 1.7, "call_money_rate_pct": 5.4, "inr_usd_change_pct": 1.4, "central_gfd_pct_gdp": 6.5, "foreign_exchange_reserves_usd_mn": 100.0, "sensex_average": 100.0, "sensex_change_pct": 5.0},
            {"period": "2020-21", "real_gdp_growth_pct": -5.8, "wpi_change_pct": 1.3, "call_money_rate_pct": 3.4, "inr_usd_change_pct": 4.7, "central_gfd_pct_gdp": 9.2, "foreign_exchange_reserves_usd_mn": 110.0, "sensex_average": 90.0, "sensex_change_pct": -10.0},
            {"period": "2021-22", "real_gdp_growth_pct": 9.7, "wpi_change_pct": 13.0, "call_money_rate_pct": 3.3, "inr_usd_change_pct": 0.4, "central_gfd_pct_gdp": 6.7, "foreign_exchange_reserves_usd_mn": 125.0, "sensex_average": 140.0, "sensex_change_pct": 36.0},
        ]
        start = date(2019, 4, 1)
        candles = [
            {"date": start + timedelta(days=index), "close": 100.0 - min(index, 250) * 0.12 + max(index - 250, 0) * 0.10}
            for index in range(1095)
        ]
        global_rows = [
            {"date": date(2020, 3, 20), "metric_key": "us_vix", "value": 66.0},
            {"date": date(2020, 3, 20), "metric_key": "sp500", "value": 2300.0},
            {"date": date(2021, 3, 20), "metric_key": "sp500", "value": 3900.0},
        ]
        comparison = build_historical_episode_fingerprints(
            episodes,
            {"timeline": timeline},
            candles,
            instrument="Nifty 50",
            global_risk_rows=global_rows,
        )
        self.assertEqual(comparison["contract_version"], "historical-episode-fingerprint-v1")
        self.assertEqual(comparison["classifier_admission"], "blocked")
        self.assertEqual(len(episodes[0]["fingerprint"]["categories"]), 10)
        by_category = {item["key"]: item for item in episodes[0]["fingerprint"]["categories"]}
        self.assertEqual(by_category["breadth_participation"]["status"], "unavailable")
        self.assertEqual(by_category["volatility_stress"]["status"], "ready")
        recurring = {item["key"]: item for item in comparison["recurring_traits"]}
        self.assertEqual(recurring["fiscal_expansion"]["episode_count"], 2)
        self.assertEqual(episodes[0]["fingerprint"]["classification_role"], "retrospective_episode_descriptor_only")

    def test_historical_entry_snapshots_separate_prior_evidence_from_forward_outcomes(self):
        episodes = [
            {"key": f"episode-{year}", "title": f"Episode {year}", "period": str(year), "window": {"start_financial_year": year, "end_financial_year": year}}
            for year in (2019, 2020, 2021, 2022)
        ]
        start = date(2017, 1, 1)
        candles = [
            {"date": start + timedelta(days=index), "close": 100.0 + index * 0.05}
            for index in range(2400)
        ]
        comparison = build_historical_entry_snapshot_validation(
            episodes,
            candles,
            instrument="Nifty 50",
        )

        self.assertEqual(comparison["contract_version"], "historical-entry-validation-v1")
        self.assertEqual(comparison["classifier_admission"], "blocked")
        self.assertEqual([row["split"] for row in comparison["snapshots"]], ["discovery", "discovery", "held_out", "held_out"])
        first = comparison["snapshots"][0]
        self.assertEqual(first["status"], "ready")
        self.assertTrue(first["outcome"]["separated_from_entry_snapshot"])
        self.assertEqual(len(first["factors"]), 10)
        self.assertEqual(
            next(item for item in first["factors"] if item["key"] == "macro_growth_inflation")["status"],
            "unavailable",
        )

        changed = [dict(row) for row in candles]
        for row in changed:
            if row["date"] > date(2019, 4, 1):
                row["close"] *= 4
        changed_episodes = [
            {"key": f"episode-{year}", "title": f"Episode {year}", "period": str(year), "window": {"start_financial_year": year, "end_financial_year": year}}
            for year in (2019, 2020, 2021, 2022)
        ]
        changed_comparison = build_historical_entry_snapshot_validation(
            changed_episodes,
            changed,
            instrument="Nifty 50",
        )
        self.assertEqual(first["price_metrics"], changed_comparison["snapshots"][0]["price_metrics"])
        self.assertNotEqual(
            first["outcome"]["windows"]["252"]["return_pct"],
            changed_comparison["snapshots"][0]["outcome"]["windows"]["252"]["return_pct"],
        )

    def test_historical_entry_snapshot_uses_only_releases_known_at_entry(self):
        episodes = [
            {
                "key": "episode-2022",
                "title": "Episode 2022",
                "period": "2022",
                "window": {"start_financial_year": 2022, "end_financial_year": 2022},
            }
        ]
        start = date(2020, 1, 1)
        candles = [
            {"date": start + timedelta(days=index), "close": 100.0 + index * 0.05}
            for index in range(1200)
        ]
        common = {
            "frequency": "quarterly",
            "unit": "US dollar million",
            "base_period": "Not applicable",
            "source_authority": "Reserve Bank of India",
            "vintage_date": date(2022, 1, 1),
        }
        rows = [
            {
                **common,
                "series_key": "india_external_debt_usd_mn",
                "date": date(2021, 3, 31),
                "period_label": "March 2021",
                "value": 570000.0,
                "metadata": {"release_date": "2021-06-30", "revision_status": "provisional"},
            },
            {
                **common,
                "series_key": "india_current_account_balance_usd_mn",
                "date": date(2021, 12, 31),
                "period_label": "Q3 2021-22",
                "value": -9200.0,
                "metadata": {"release_date": "2022-06-30", "revision_status": "preliminary"},
            },
        ]

        comparison = build_historical_entry_snapshot_validation(
            episodes,
            candles,
            instrument="Nifty 50",
            official_history_rows=rows,
        )
        factor = next(
            item
            for item in comparison["snapshots"][0]["factors"]
            if item["key"] == "rates_currency_credit"
        )
        self.assertEqual(factor["status"], "partial")
        self.assertIn("570,000.00", factor["observation"])
        self.assertNotIn("-9,200.00", factor["observation"])
        self.assertIn("1/3 required", factor["limitation"])

    def test_backtests_workspace_reuses_chronological_entry_validation(self):
        entry_validation = {
            "contract_version": "historical-entry-validation-v1",
            "instrument": "Nifty 50",
            "split": {
                "method": "chronological 70/30 split",
                "discovery_episodes": 2,
                "held_out_episodes": 1,
                "excluded_episodes": 0,
                "boundary_episode": "Held-out episode",
                "outcome_horizon_sessions": 252,
            },
            "snapshots": [
                {
                    "snapshot_as_of": "2018-04-01",
                    "split": "discovery",
                    "outcome": {"windows": {"252": {"status": "ready"}}},
                },
                {
                    "snapshot_as_of": "2020-04-01",
                    "split": "discovery",
                    "outcome": {"windows": {"252": {"status": "ready"}}},
                },
                {
                    "snapshot_as_of": "2022-04-01",
                    "split": "held_out",
                    "outcome": {"windows": {"252": {"status": "ready"}}},
                },
            ],
            "trait_validation": [
                {
                    "key": "global_risk_off",
                    "label": "Global risk-off backdrop",
                    "discovery": {"episodes": 2, "median_252_return_pct": 8.0},
                    "held_out": {"episodes": 1, "median_252_return_pct": 5.0},
                    "direction_consistent": True,
                    "reason": "At least three held-out matches are required.",
                }
            ],
        }
        workspace = build_backtests_workspace(entry_validation)
        self.assertEqual(workspace["contract_version"], "backtests-v6")
        self.assertEqual(workspace["summary"]["registered_contracts"], 3)
        self.assertEqual(workspace["summary"]["chronological_tests_completed"], 1)
        self.assertEqual(workspace["summary"]["held_out_tests_passed"], 0)
        self.assertEqual(workspace["registry"][0]["status"], "blocked")
        self.assertFalse(workspace["trait_results"][0]["held_out_gate_passed"])
        self.assertEqual(workspace["validation_split"]["held_out_period"]["from"], "2022-04-01")

    def test_breadth_reversal_model_uses_prior_states_and_reports_walk_forward_scores(self):
        sessions = [date(2020, 1, 1) + timedelta(days=offset) for offset in range(520)]
        index_candles = [
            {"date": session, "close": 100 + (position * 0.04) + (8 * math.sin(position / 17))}
            for position, session in enumerate(sessions)
        ]
        stock_histories = {}
        for stock_number in range(30):
            stock_histories[f"STOCK{stock_number}"] = [
                {
                    "date": session,
                    "close": 50
                    + stock_number
                    + (position * (0.015 + stock_number / 10000))
                    + ((5 + stock_number / 10) * math.sin((position + stock_number) / 15)),
                }
                for position, session in enumerate(sessions)
            ]
        result = build_breadth_reversal_model(
            stock_histories,
            index_candles,
            instrument="Nifty 50",
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["contract_version"], "breadth-reversal-knn-v1")
        self.assertEqual(result["current_breadth"]["eligible_200"], 30)
        self.assertEqual([row["sessions"] for row in result["horizons"]], [5, 20, 60])
        self.assertGreater(result["horizons"][0]["walk_forward_predictions"], 0)
        self.assertIsNotNone(result["horizons"][0]["brier_score"])
        self.assertIn("survivorship", " ".join(result["limitations"]).lower())

    def test_stock_backtest_results_returns_every_selected_stock(self):
        sessions = [date(2020, 1, 1) + timedelta(days=offset) for offset in range(620)]
        histories = {
            f"STOCK{stock_number}": [
                {
                    "date": session,
                    "close": 80
                    + stock_number
                    + position * 0.03
                    + (7 * math.sin((position + stock_number * 3) / 14)),
                }
                for position, session in enumerate(sessions)
            ]
            for stock_number in range(6)
        }
        histories["SHORT"] = [
            {"date": session, "close": 100 + position}
            for position, session in enumerate(sessions[:100])
        ]
        result = build_stock_backtest_results(
            histories,
            universe_label="Test universe",
            universe_key="test",
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["summary"]["selected_stocks"], 7)
        self.assertEqual(result["summary"]["results_returned"], 7)
        self.assertEqual(result["summary"]["calculation_ready"], 6)
        self.assertEqual(result["summary"]["insufficient_history"], 1)
        ready = next(row for row in result["stocks"] if row["symbol"] == "STOCK0")
        self.assertEqual([row["sessions"] for row in ready["horizons"]], [5, 20, 60])
        unavailable = next(row for row in result["stocks"] if row["symbol"] == "SHORT")
        self.assertEqual(unavailable["status"], "insufficient_history")

    def test_stock_backtest_results_blocks_empty_universe(self):
        result = build_stock_backtest_results(
            {},
            universe_label="Empty universe",
            universe_key="empty",
        )
        self.assertEqual(result["status"], "no_eligible_stocks")
        self.assertEqual(result["summary"]["results_returned"], 0)
        self.assertEqual(result["stocks"], [])

    def test_short_term_trade_recommendations_are_portfolio_independent(self):
        stock_results = {
            "as_of_date": "2026-10-28",
            "universe_key": "test",
            "universe_label": "Test universe",
            "stocks": [
                {
                    "symbol": "LONGTEST",
                    "status": "ready",
                    "as_of_date": "2026-10-28",
                    "close": 100.0,
                    "prior_direction": "down",
                    "prior_20_session_return_pct": -8.0,
                    "above_20dma": False,
                    "above_200dma": False,
                    "horizons": [
                        {"sessions": 5, "status": "ready", "probability_pct": 66.0, "observations": 40},
                        {"sessions": 20, "status": "ready", "probability_pct": 60.0, "observations": 20},
                        {"sessions": 60, "status": "low_sample", "probability_pct": 70.0, "observations": 4},
                    ],
                },
                {
                    "symbol": "SHORTTEST",
                    "status": "ready",
                    "as_of_date": "2026-10-28",
                    "close": 200.0,
                    "prior_direction": "up",
                    "prior_20_session_return_pct": 9.0,
                    "above_20dma": True,
                    "above_200dma": True,
                    "horizons": [
                        {"sessions": 5, "status": "ready", "probability_pct": 68.0, "observations": 45},
                        {"sessions": 20, "status": "ready", "probability_pct": 64.0, "observations": 22},
                    ],
                },
            ],
        }
        result = build_short_term_trade_recommendations(stock_results)

        self.assertEqual(result["status"], "recommendations_ready")
        self.assertEqual(result["summary"]["recommendations"], 2)
        self.assertEqual(result["summary"]["long"], 1)
        self.assertEqual(result["summary"]["short"], 1)
        self.assertIn("Portfolio holdings", result["boundary"])
        self.assertTrue(all(row["execution"] == "manual_review_only" for row in result["recommendations"]))

    def test_historical_point_in_time_readiness_excludes_retrospective_rows(self):
        rows = [
            {
                "series_key": "india_real_gdp_growth_pct",
                "date": date(2020, 3, 31),
                "frequency": "annual",
                "vintage_date": date(2026, 8, 29),
                "metadata": {},
            },
            {
                "series_key": "india_wpi_all_commodities_annual_average",
                "date": date(2020, 3, 31),
                "frequency": "annual",
                "vintage_date": date(2026, 8, 29),
                "metadata": {},
            },
        ]
        readiness = build_historical_point_in_time_readiness(rows)
        macro = next(row for row in readiness["categories"] if row["key"] == "macro_growth_inflation")
        self.assertEqual(readiness["contract_version"], "historical-point-in-time-readiness-v1")
        self.assertEqual(readiness["entry_snapshot_admission"], "blocked")
        self.assertEqual(macro["status"], "blocked")
        self.assertEqual(macro["retrospective_only_observations"], 2)
        self.assertEqual(macro["release_dated_observations"], 0)

    def test_historical_point_in_time_readiness_accepts_explicit_release_metadata(self):
        def released(series_key, release_date):
            return {
                "series_key": series_key,
                "date": date(2020, 3, 31),
                "frequency": "annual",
                "vintage_date": date(2020, 8, 31),
                "metadata": {
                    "release_date": release_date,
                    "revision_status": "initial",
                },
            }

        rows = [
            released("india_real_gdp_growth_pct", "2020-05-29"),
            released("india_wpi_all_commodities_annual_average", "2020-06-15"),
            released("india_call_money_rate_annual", "2020-06-01"),
            released("inr_usd_annual_average", "2020-06-01"),
            released("india_bank_credit_growth_pct", "2020-06-01"),
            released("india_current_account_balance_usd_mn", "2020-06-30"),
            released("india_external_debt_usd_mn", "2020-06-30"),
        ]
        membership = [
            {
                "effective_date": date(2020, 3, 27),
                "release_date": date(2020, 3, 13),
                "revision_status": "initial",
                "frequency": "event",
            }
        ]
        readiness = build_historical_point_in_time_readiness(
            rows,
            membership_snapshots=membership,
        )
        self.assertEqual(readiness["entry_snapshot_admission"], "ready")
        self.assertEqual(readiness["summary"]["ready_categories"], 4)
        self.assertEqual(readiness["summary"]["blocked_categories"], 0)

    def test_historical_point_in_time_readiness_counts_release_dated_policy_rate(self):
        readiness = build_historical_point_in_time_readiness(
            [
                {
                    "series_key": "india_policy_repo_rate_pct",
                    "date": date(2022, 5, 4),
                    "frequency": "event",
                    "vintage_date": date(2022, 5, 4),
                    "metadata": {
                        "release_date": "2022-05-04",
                        "revision_status": "initial",
                    },
                }
            ]
        )
        rates = next(
            row for row in readiness["categories"]
            if row["key"] == "rates_currency_credit"
        )
        self.assertEqual(rates["status"], "partial")
        self.assertEqual(rates["release_dated_observations"], 1)
        self.assertEqual(rates["release_dated_series"], 1)
        self.assertEqual(rates["frequency"], "event")

    def test_all_index_seasonality_backtest_keeps_unavailable_indices_visible(self):
        def history(offset: float) -> list[dict[str, object]]:
            rows = []
            close = 100.0 + offset
            for year in range(2015, 2025):
                for month in range(1, 13):
                    monthly_return = 0.025 if month == 4 else (((year + month) % 5) - 2) / 1000
                    close *= 1 + monthly_return
                    rows.append({"date": date(year, month, 20), "close": close})
            return rows

        workspace = build_seasonality_backtest_workspace(
            {"Nifty 50": history(0), "Nifty IT": history(10)},
            today=date(2026, 10, 12),
            supported_indices=("Nifty 50", "Nifty IT", "Nifty Missing"),
        )
        self.assertEqual(workspace["contract_version"], "seasonality-all-indices-backtest-v1")
        self.assertEqual(workspace["summary"]["supported_indices"], 3)
        self.assertEqual(workspace["summary"]["indices_tested"], 2)
        self.assertEqual(workspace["summary"]["indices_unavailable"], 1)
        self.assertEqual(workspace["summary"]["month_tests_evaluated"], 24)
        self.assertIn("family_q_value", workspace["candidates"][0])
        self.assertEqual(workspace["unavailable"][0]["instrument"], "Nifty Missing")

    def test_historical_close_aggregation_uses_period_end_without_interpolation(self):
        observations = [
            {"date": date(2024, 1, 2), "close": 100.0},
            {"date": date(2024, 1, 31), "close": 110.0},
            {"date": date(2024, 2, 5), "close": 108.0},
            {"date": date(2024, 3, 28), "close": 120.0},
            {"date": date(2024, 4, 1), "close": 121.0},
        ]

        monthly = aggregate_historical_closes(observations, frequency="monthly")
        quarterly = aggregate_historical_closes(observations, frequency="quarterly")

        self.assertEqual(
            monthly,
            [
                {"date": date(2024, 1, 31), "close": 110.0},
                {"date": date(2024, 2, 5), "close": 108.0},
                {"date": date(2024, 3, 28), "close": 120.0},
                {"date": date(2024, 4, 1), "close": 121.0},
            ],
        )
        self.assertEqual(
            quarterly,
            [
                {"date": date(2024, 3, 28), "close": 120.0},
                {"date": date(2024, 4, 1), "close": 121.0},
            ],
        )
        with self.assertRaisesRegex(ValueError, "invalid_historical_frequency"):
            aggregate_historical_closes(observations, frequency="hourly")

    def test_historical_regime_workspace_requires_one_year_of_history(self):
        candles = [
            {"date": date(2025, 1, 1) + timedelta(days=position), "close": 100 + position}
            for position in range(251)
        ]
        with self.assertRaisesRegex(
            ValueError, "historical_regime_history_unavailable"
        ):
            build_historical_regime_workspace(candles)

    def test_candidate_regime_excludes_missing_clusters_and_lowers_confidence(self):
        result = calculate_candidate_regime(
            self._candidate_evidence("defensive", external=False)
        )
        self.assertTrue(result["classification_eligible"])
        self.assertEqual(result["available_weight_pct"], 60.0)
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["label_key"], "high_risk_market")
        self.assertEqual(
            result["missing_clusters"],
            ["institutional_flows", "currency_and_rates", "global_risk"],
        )

    def test_candidate_regime_refuses_stale_or_low_coverage_evidence(self):
        stale = calculate_candidate_regime(
            self._candidate_evidence(freshness="stale")
        )
        self.assertFalse(stale["classification_eligible"])
        self.assertEqual(stale["label_key"], "not_enough_reliable_data")
        self.assertIn("fresh_eod_data_required", stale["gate_failures"])

        low_coverage = calculate_candidate_regime(
            self._candidate_evidence(coverage=79.9)
        )
        self.assertFalse(low_coverage["classification_eligible"])
        self.assertIn("stock_coverage_below_80_pct", low_coverage["gate_failures"])

    def test_regime_walk_forward_uses_trailing_evidence_and_future_outcomes(self):
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=index) for index in range(400)]

        def rising(multiplier):
            return [
                {
                    "date": session_date,
                    "open": 100.0 + index * multiplier,
                    "high": 101.0 + index * multiplier,
                    "low": 99.0 + index * multiplier,
                    "close": 100.0 + index * multiplier,
                }
                for index, session_date in enumerate(dates)
            ]

        result = calculate_regime_walk_forward_validation(
            rising(1.0),
            {
                "UP1": rising(1.0),
                "UP2": rising(0.8),
                "UP3": rising(0.6),
                "UP4": rising(0.4),
                "NEW": rising(0.2)[-200:],
            },
            india_vix_candles=rising(0.02),
        )
        self.assertEqual(result["rule_version"], "market-regime-candidate-v1")
        self.assertEqual(result["evaluation_start"], dates[251].isoformat())
        self.assertEqual(result["evaluation_end"], dates[339].isoformat())
        self.assertEqual(result["sessions_evaluated"], 89)
        self.assertEqual(result["confirmation_sessions"], 2)
        positive = next(
            row for row in result["by_regime"] if row["label_key"] == "positive_market"
        )
        self.assertEqual(positive["sessions"], 88)
        self.assertEqual(positive["horizons"]["60"]["positive_rate_pct"], 100.0)
        self.assertEqual(result["overall"]["sessions"], 88)
        self.assertEqual(result["overall"]["horizons"]["20"]["positive_rate_pct"], 100.0)
        self.assertTrue(result["baseline"])
        self.assertIn("survivorship", result["limitations"][0])

    def test_regime_validation_universe_marks_short_history_without_hiding_it(self):
        result = build_regime_validation_universe(
            [
                {
                    "display_name": "Nifty 50",
                    "session_count": 2481,
                    "first_session": date(2016, 9, 26),
                    "last_session": date(2026, 9, 28),
                },
                {
                    "display_name": "Nifty Chemicals",
                    "session_count": 210,
                    "first_session": date(2025, 11, 24),
                    "last_session": date(2026, 9, 28),
                },
            ],
            supported_indices=("Nifty 50", "Nifty Chemicals", "Nifty IT"),
        )
        self.assertEqual(result["walk_forward_sessions_required"], 312)
        by_name = {row["display_name"]: row for row in result["indices"]}
        self.assertTrue(by_name["Nifty 50"]["walk_forward_ready"])
        self.assertFalse(by_name["Nifty Chemicals"]["current_regime_ready"])
        self.assertEqual(by_name["Nifty Chemicals"]["sessions_until_current_regime"], 42)
        self.assertEqual(by_name["Nifty Chemicals"]["sessions_until_walk_forward"], 102)
        self.assertEqual(by_name["Nifty IT"]["session_count"], 0)

    def test_regime_validation_universe_withholds_thin_fno_constituent_breadth(self):
        result = build_regime_validation_universe(
            [
                {
                    "display_name": "Nifty Media",
                    "session_count": 2481,
                    "first_session": date(2016, 9, 26),
                    "last_session": date(2026, 9, 28),
                }
            ],
            stock_names={"A", "B", "C", "D"},
            constituent_snapshot={
                "as_of": "2026-09-29",
                "indices": {"Nifty Media": ["A", "B", "C", "D", "E", "F"]},
            },
            supported_indices=("Nifty Media",),
        )
        row = result["indices"][0]
        self.assertTrue(row["walk_forward_ready"])
        self.assertFalse(row["constituent_breadth_ready"])
        self.assertFalse(row["validation_ready"])
        self.assertEqual(row["fno_constituent_count"], 4)

    def test_regime_walk_forward_reports_selected_index_relative_to_benchmark(self):
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=index) for index in range(400)]

        def rising(multiplier):
            return [
                {
                    "date": session_date,
                    "open": 100.0 + index * multiplier,
                    "high": 101.0 + index * multiplier,
                    "low": 99.0 + index * multiplier,
                    "close": 100.0 + index * multiplier,
                }
                for index, session_date in enumerate(dates)
            ]

        result = calculate_regime_walk_forward_validation(
            rising(1.0),
            {name: rising(0.5) for name in ("A", "B", "C", "D", "E")},
            target_index="Nifty IT",
            benchmark_candles=rising(0.2),
            benchmark_index="Nifty 50",
            event_windows=(
                {
                    "key": "synthetic_rise",
                    "label": "Synthetic rising window",
                    "start": dates[260],
                    "end": dates[270],
                },
            ),
        )
        self.assertEqual(result["target_index"], "Nifty IT")
        self.assertEqual(result["benchmark_index"], "Nifty 50")
        self.assertEqual(result["current_state"]["as_of_date"], dates[-1].isoformat())
        self.assertEqual(result["current_state"]["session_lag"], 0)
        self.assertTrue(result["current_state"]["classification_ready"])
        self.assertEqual(
            result["current_state"]["transition_label_key"], "positive_market"
        )
        positive = next(
            row for row in result["by_regime"] if row["label_key"] == "positive_market"
        )
        metrics = positive["horizons"]["20"]
        self.assertGreater(metrics["median_excess_return_pct"], 0)
        self.assertEqual(metrics["outperformance_rate_pct"], 100.0)
        self.assertEqual(metrics["worst_relative_drawdown_pct"], 0.0)
        event = result["event_validation"][0]
        self.assertEqual(event["key"], "synthetic_rise")
        self.assertGreater(event["index_return_pct"], 0)
        self.assertGreater(event["excess_return_pct"], 0)
        self.assertEqual(event["maximum_drawdown_pct"], 0.0)
        self.assertEqual(event["weak_or_high_risk_sessions_pct"], 0.0)
        control = event["normal_period_control"]
        self.assertGreater(control["window_count"], 0)
        self.assertEqual(control["median_maximum_drawdown_pct"], 0.0)
        self.assertEqual(control["event_drawdown_severity_percentile_pct"], 50.0)
        self.assertEqual(event["recovering_sessions_pct"], 0.0)
        self.assertEqual(control["median_recovering_sessions_pct"], 0.0)
        self.assertEqual(control["event_recovery_share_percentile_pct"], 50.0)
        directional = result["transition_analysis"]["directional_state_evidence"]
        positive_state = next(
            row for row in directional if row["label_key"] == "positive_market"
        )
        self.assertTrue(positive_state["sample_ready"])
        self.assertEqual(positive_state["research_bias"], "long_research_candidate")
        self.assertEqual(positive_state["orientation"], "long")
        self.assertEqual(positive_state["horizon_sessions"], 20)
        self.assertTrue(positive_state["risk_profile"]["available"])
        self.assertGreater(positive_state["risk_profile"]["tail_position_return_pct"], 0)
        self.assertEqual(
            positive_state["risk_profile"]["adverse_distance_breach_rates_pct"]["3"],
            0.0,
        )

    def test_regime_downside_continuation_uses_shorter_horizon_and_short_risk(self):
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=index) for index in range(400)]

        def falling(multiplier):
            return [
                {
                    "date": session_date,
                    "open": 1000.0 - index * multiplier,
                    "high": 1001.0 - index * multiplier,
                    "low": 999.0 - index * multiplier,
                    "close": 1000.0 - index * multiplier,
                }
                for index, session_date in enumerate(dates)
            ]

        result = calculate_regime_walk_forward_validation(
            falling(2.0),
            {name: falling(1.5) for name in ("A", "B", "C", "D", "E")},
        )
        directional = result["transition_analysis"]["directional_state_evidence"]
        risk_state = next(
            row
            for row in directional
            if row["label_key"] in {"weak_market", "high_risk_market"}
        )
        self.assertEqual(risk_state["research_bias"], "short_research_candidate")
        self.assertEqual(risk_state["orientation"], "short")
        self.assertEqual(risk_state["horizon_sessions"], 5)
        self.assertEqual(risk_state["short_case"]["horizon_sessions"], 5)
        self.assertTrue(risk_state["short_case"]["passed"])
        self.assertGreater(risk_state["risk_profile"]["tail_position_return_pct"], 0)

    def test_index_futures_confirmation_requires_history_same_session_and_bearish_breadth(self):
        states = [
            {"underlying": f"S{index}", "state": "short_build_up"}
            for index in range(4)
        ] + [
            {"underlying": "S4", "state": "long_unwinding"},
            {"underlying": "S5", "state": "long_build_up"},
        ]
        summary = {
            "available": True,
            "as_of_date": "2026-10-05",
            "states": states,
        }
        pending = build_index_futures_confirmation(
            [f"S{index}" for index in range(10)],
            fno_constituent_count=10,
            futures_summary=summary,
            history_ready=False,
            current_state_date="2026-10-05",
        )
        self.assertEqual(pending["status"], "history_accumulating")
        self.assertFalse(pending["short_gate_passed"])

        confirmed = build_index_futures_confirmation(
            [f"S{index}" for index in range(10)],
            fno_constituent_count=10,
            futures_summary=summary,
            history_ready=True,
            current_state_date="2026-10-05",
        )
        self.assertTrue(confirmed["current_confirmation_ready"])
        self.assertTrue(confirmed["bearish_confirmation"])
        self.assertTrue(confirmed["short_gate_passed"])
        self.assertEqual(confirmed["coverage_pct"], 60.0)
        self.assertEqual(confirmed["bearish_share_pct"], 83.3)

    def test_dashboard_market_sentiment_summary_is_compact_and_research_only(self):
        domestic = {
            "ok": True,
            "as_of_date": "2026-10-05",
            "domestic_tape": "Defensive",
            "available_clusters": 5,
            "total_clusters": 6,
            "freshness": {
                "state": "fresh",
                "latest_session": "2026-10-05",
                "expected_through": "2026-10-05",
                "lag_days": 0,
            },
        }
        cross_index = {
            "ok": True,
            "current_decision_rows": [
                {
                    "index": "Nifty Bank",
                    "is_benchmark": False,
                    "current_decision": "long_candidate",
                    "current_state": {"as_of_date": "2026-10-05"},
                },
                {
                    "index": "Nifty IT",
                    "is_benchmark": False,
                    "current_decision": "short_watch_history_building",
                    "current_state": {"as_of_date": "2026-10-05"},
                },
                {
                    "index": "Nifty Auto",
                    "is_benchmark": False,
                    "current_decision": "avoid_no_validated_edge",
                    "current_state": {"as_of_date": "2026-10-05"},
                },
                {
                    "index": "Nifty 50",
                    "is_benchmark": True,
                    "current_decision": "market_context_only",
                    "current_state": {"as_of_date": "2026-10-05"},
                },
            ],
            "excluded": [{"index": "Nifty Media", "reason": "thin_breadth"}],
            "futures_short_confirmation_contract": {
                "stored_history_sessions": 2,
                "history_sessions_required": 252,
                "history_ready": False,
            },
        }
        summary = build_dashboard_market_sentiment_summary(domestic, cross_index)
        self.assertEqual(summary["scope"], "cross_sectional_research_only")
        self.assertEqual(summary["status"], "research_candidates_present")
        self.assertEqual(
            summary["decision_counts"],
            {"long": 1, "confirmed_short": 0, "watch": 1, "avoid": 1, "insufficient": 0},
        )
        self.assertEqual(summary["evidence"]["eligible_indices"], 3)
        self.assertEqual(summary["leading_watch"]["index"], "Nifty IT")
        self.assertFalse(summary["futures_short_confirmation"]["history_ready"])

    def test_dashboard_fno_summary_preserves_descriptive_positioning_contract(self):
        summary = build_dashboard_fno_summary(
            {
                "available": True,
                "as_of_date": "2026-10-05",
                "latest_coverage": 208,
                "expected_universe": 210,
                "latest_coverage_pct": 99.0,
                "latest_missing_count": 2,
                "comparable_count": 205,
                "eligible_count": 200,
                "rollover_baseline_count": 1,
                "stale_gap_count": 2,
                "liquidity_excluded_count": 3,
                "state_counts": {
                    "long_build_up": 60,
                    "short_covering": 45,
                    "short_build_up": 35,
                    "long_unwinding": 30,
                    "no_clear_signal": 30,
                },
                "reason": "Descriptive same-contract evidence.",
                "safeguards": {"regime_score_enabled": False},
            },
            stored_history_sessions=2,
        )
        self.assertEqual(summary["scope"], "descriptive_only")
        self.assertEqual(summary["status"], "bullish_tilt")
        self.assertEqual(summary["coverage"]["latest"], 208)
        self.assertEqual(summary["comparisons"]["eligible"], 200)
        self.assertEqual(summary["positioning"]["bullish"], 105)
        self.assertEqual(summary["positioning"]["bearish"], 65)
        self.assertFalse(summary["safeguards"]["regime_score_enabled"])

    def test_dashboard_seasonality_summary_keeps_holdout_and_forecast_boundary(self):
        month_rows = [
            {
                "period": period,
                "count": 8,
                "average_return_pct": float(index - 5),
                "average_range_pct": 4.0,
                "highest_return_pct": 10.0,
                "lowest_return_pct": -8.0,
            }
            for index, period in enumerate(
                ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            )
        ]
        summary = build_dashboard_seasonality_summary(
            {
                "ok": True,
                "instrument": "Nifty 50",
                "kind": "index",
                "from_date": "2017-01-02",
                "as_of_date": "2026-10-05",
                "completed_sessions": 2400,
                "holdout_split_date": "2022-01-01",
                "month_rows": month_rows,
                "held_out_summary": {
                    "same_direction": 7,
                    "train_significant": 2,
                    "survived": 1,
                },
                "turn_held_out_rows": [
                    {"period": "Train", "edge_pct": 0.1, "significant": False},
                    {"period": "Test", "edge_pct": 0.2, "significant": True},
                ],
            }
        )
        self.assertEqual(summary["scope"], "historical_not_forecast")
        self.assertEqual(summary["status"], "historical_evidence_ready")
        self.assertEqual(summary["strongest_month"]["period"], "Dec")
        self.assertEqual(summary["weakest_month"]["period"], "Jan")
        self.assertEqual(summary["holdout"]["survived"], 1)
        self.assertEqual(summary["turn_of_month_test"]["period"], "Test")

    def test_dashboard_seasonality_universe_keeps_partial_and_unavailable_indices(self):
        ready = {
            "ok": True,
            "instrument": "Nifty 50",
            "kind": "index",
            "status": "historical_evidence_ready",
            "completed_sessions": 2400,
        }
        partial = {
            "ok": True,
            "instrument": "Nifty Chemicals",
            "kind": "index",
            "status": "partial_history",
            "completed_sessions": 214,
        }
        result = build_dashboard_seasonality_universe_summary(
            {"Nifty 50": ready, "Nifty Chemicals": partial},
            supported_indices=("Nifty 50", "Nifty Chemicals", "Nifty Bank"),
        )
        self.assertEqual(result["scope"], "all_supported_indices")
        self.assertEqual(result["universe"], {
            "total": 3,
            "available": 2,
            "ready": 1,
            "partial": 1,
            "unavailable": 1,
        })
        self.assertEqual(result["indices"][2]["instrument"], "Nifty Bank")
        self.assertEqual(result["indices"][2]["status"], "history_unavailable")

    def test_local_stock_screener_keeps_ready_partial_stale_and_unavailable_rows(self):
        dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(253)]

        def candles(selected_dates, base, step):
            return [
                {
                    "date": candle_date,
                    "open": base + index * step,
                    "high": base + index * step + 1,
                    "low": base + index * step - 1,
                    "close": base + index * step,
                }
                for index, candle_date in enumerate(selected_dates)
            ]

        result = calculate_stock_screener(
            {
                "READY": candles(dates, 50.0, 1.0),
                "PARTIAL": candles(dates[-100:], 80.0, 0.2),
                "STALE": candles(dates[:-1], 60.0, 0.5),
                "EMPTY": [],
            },
            candles(dates, 100.0, 0.25),
            expected_through=dates[-1],
        )
        self.assertEqual(result["scope"], "locally_stored_nse_fno_equities")
        self.assertEqual(result["coverage"], {
            "total": 4,
            "ready": 1,
            "partial_history": 1,
            "stale": 1,
            "unavailable": 1,
        })
        rows = {row["symbol"]: row for row in result["rows"]}
        self.assertEqual(rows["READY"]["status"], "ready")
        self.assertGreater(rows["READY"]["return_20d_pct"], 0)
        self.assertGreater(rows["READY"]["vs_200dma_pct"], 0)
        self.assertEqual(rows["READY"]["position_52w_pct"], 100.0)
        self.assertEqual(rows["PARTIAL"]["status"], "partial_history")
        self.assertIsNone(rows["PARTIAL"]["vs_200dma_pct"])
        self.assertEqual(rows["STALE"]["status"], "stale")
        self.assertIsNone(rows["STALE"]["excess_20d_vs_nifty_pct"])
        self.assertEqual(rows["EMPTY"]["status"], "unavailable")
        self.assertEqual(result["contract"]["version"], "local-stock-screener-v1")

    def test_dashboard_screener_summary_is_descriptive_and_keeps_readiness(self):
        result = build_dashboard_screener_summary(
            {
                "ok": True,
                "as_of_date": "2026-10-05",
                "benchmark": "Nifty 50",
                "benchmark_return_20d_pct": -2.0,
                "coverage": {
                    "total": 4,
                    "ready": 3,
                    "partial_history": 1,
                    "stale": 0,
                    "unavailable": 0,
                },
                "freshness": {
                    "state": "stale",
                    "latest_session": "2026-10-05",
                    "expected_through": "2026-10-06",
                },
                "contract": {"version": "local-stock-screener-v1"},
                "rows": [
                    {
                        "symbol": "ALPHA",
                        "status": "ready",
                        "return_20d_pct": 8.0,
                        "excess_20d_vs_nifty_pct": 10.0,
                        "vs_200dma_pct": 12.0,
                    },
                    {
                        "symbol": "BETA",
                        "status": "ready",
                        "return_20d_pct": -1.0,
                        "excess_20d_vs_nifty_pct": 1.0,
                        "vs_200dma_pct": -3.0,
                    },
                    {
                        "symbol": "GAMMA",
                        "status": "ready",
                        "return_20d_pct": -9.0,
                        "excess_20d_vs_nifty_pct": -7.0,
                        "vs_200dma_pct": 2.0,
                    },
                    {"symbol": "NEW", "status": "partial_history"},
                ],
            }
        )
        self.assertEqual(result["scope"], "descriptive_local_screen_only")
        self.assertEqual(result["status"], "partial_history")
        self.assertEqual(result["coverage"]["ready"], 3)
        self.assertEqual(result["observations"]["positive_20d"], 1)
        self.assertEqual(result["observations"]["above_200dma"], 2)
        self.assertEqual(result["observations"]["outperforming_nifty_20d"], 2)
        self.assertEqual(
            result["observations"]["highest_20d_excess"]["symbol"], "ALPHA"
        )
        self.assertEqual(
            result["observations"]["lowest_20d_excess"]["symbol"], "GAMMA"
        )
        self.assertEqual(result["contract_version"], "local-stock-screener-v1")

    def test_dashboard_market_story_connects_current_history_and_catalysts(self):
        result = build_dashboard_market_story(
            {
                "ok": True,
                "as_of_date": "2026-10-07",
                "freshness": {"state": "fresh"},
                "evidence": {"available_clusters": 5, "total_clusters": 6},
                "futures_short_confirmation": {
                    "stored_history_sessions": 4,
                    "history_sessions_required": 252,
                    "history_ready": False,
                },
            },
            {
                "ok": True,
                "benchmark_return_20d_pct": -4.95,
                "coverage": {"ready": 210},
                "observations": {"positive_20d": 31},
            },
            {
                "ok": True,
                "stored_history_sessions": 4,
                "positioning": {"bullish": 33, "bearish": 87, "unclear": 90},
            },
            {
                "ok": True,
                "current_state": {
                    "classification_ready": True,
                    "as_of_date": "2026-10-07",
                    "transition_label_key": "weak_market",
                    "transition_label": "Weak market",
                    "score": -50.0,
                    "close": 22603.05,
                    "evidence": {
                        "above_50dma_pct": 14.0,
                        "above_200dma_pct": 14.0,
                        "realised_volatility_percentile": 55.6,
                    },
                },
                "by_state": [
                    {
                        "label_key": "weak_market",
                        "label": "Weak market",
                        "sessions": 154,
                        "horizons": {
                            5: {"mean_return_pct": 0.3, "median_return_pct": 0.34, "positive_rate_pct": 53.9, "worst_return_pct": -6.11, "mean_max_drawdown_pct": -1.57},
                            20: {"mean_return_pct": 1.68, "median_return_pct": 1.48, "positive_rate_pct": 67.5, "worst_return_pct": -5.91, "mean_max_drawdown_pct": -3.81},
                            60: {"mean_return_pct": 3.51, "median_return_pct": 3.35, "positive_rate_pct": 80.5, "worst_return_pct": -11.68, "mean_max_drawdown_pct": -6.07},
                        },
                    }
                ],
            },
            {
                "ok": True,
                "month_rows": [
                    {"period": "Oct", "count": 9, "average_return_pct": 1.2, "median_return_pct": 0.8, "positive_months_pct": 66.7}
                ],
                "held_out_summary": {"survived": 0},
            },
            {
                "ok": True,
                "events": [
                    {
                        "title": "India CPI",
                        "start_at": "2026-10-12",
                        "end_at": None,
                        "days_until": 5,
                        "region": "India",
                        "category": "inflation",
                        "source_label": "MoSPI",
                    }
                ],
            },
            {
                "ok": True,
                "as_of_date": "2026-10-07",
                "breadth": {
                    "official_count": 500,
                    "evaluated": 492,
                    "coverage_pct": 98.4,
                    "above_50dma_pct": 24.0,
                    "above_200dma_pct": 31.0,
                    "positive_20d": 126,
                    "evaluated_20d": 492,
                },
                "relative_strength": {
                    "window_sessions": 20,
                    "benchmark": {"name": "Nifty 50", "return_pct": -4.95},
                    "indices": {
                        "evaluated": 18,
                        "strongest": {"name": "Nifty FMCG", "return_pct": -1.0, "excess_vs_nifty50_pct": 3.95},
                        "weakest": {"name": "Nifty IT", "return_pct": -8.0, "excess_vs_nifty50_pct": -3.05},
                    },
                    "sectors": {
                        "evaluated": 20,
                        "strongest": {"name": "FMCG", "return_pct": -0.5, "excess_vs_nifty50_pct": 4.45, "stocks_evaluated": 25},
                        "weakest": {"name": "Information Technology", "return_pct": -8.5, "excess_vs_nifty50_pct": -3.55, "stocks_evaluated": 32},
                    },
                    "method": "test method",
                },
            },
        )
        self.assertEqual(result["contract_version"], "dashboard-market-story-v1")
        self.assertEqual(result["regime"]["key"], "weak_market")
        self.assertEqual(result["confidence"]["label"], "moderate")
        self.assertEqual(result["historical_analogue"]["sessions_observed"], 154)
        self.assertEqual(len(result["historical_analogue"]["horizons"]), 3)
        self.assertEqual(result["seasonality"]["month"], "Oct")
        self.assertEqual(result["catalysts"][0]["title"], "India CPI")
        self.assertEqual(result["signals"][1]["value"], "24% / 31%")
        self.assertIn("NIFTY 500", result["signals"][1]["detail"])
        self.assertEqual(
            result["market_context"]["relative_strength"]["indices"]["strongest"]["name"],
            "Nifty FMCG",
        )
        self.assertIn("narrow", result["headline"])

    def test_dashboard_overview_keeps_one_consistent_component_contract(self):
        component = {"ok": True, "as_of_date": "2026-10-28"}
        result = build_dashboard_overview(
            market_story={**component, "headline": "Market story"},
            sentiment_summary={**component, "status": "watch_only"},
            fno_summary={**component, "status": "history_building"},
            screener_summary={**component, "status": "partial_history"},
            seasonality_summary={**component, "indices": []},
            events_summary={**component, "events": []},
        )

        self.assertEqual(result["contract_version"], "dashboard-overview-v1")
        self.assertEqual(result["as_of_date"], "2026-10-28")
        self.assertEqual(result["market_story"]["headline"], "Market story")
        self.assertEqual(result["seasonality"]["indices"], [])

    def test_news_events_foundation_keeps_unsourced_live_items_empty(self):
        result = build_news_events_workspace(
            reviewed_on=date(2026, 10, 6),
            sources=(
                {
                    "key": "official_source",
                    "label": "Official source",
                    "category": "regulatory",
                    "authority": "Regulator",
                    "url": "https://example.test/official",
                    "coverage": "Official releases",
                },
            ),
            event_windows=(
                {
                    "key": "past_event",
                    "label": "Past event",
                    "start": date(2020, 1, 1),
                    "end": date(2020, 1, 5),
                },
            ),
        )
        self.assertEqual(result["status"], "manual_import_ready")
        self.assertEqual(result["contract"]["version"], "news-events-foundation-v1")
        self.assertFalse(result["contract"]["live_ingestion_enabled"])
        self.assertTrue(result["contract"]["manual_csv_import_enabled"])
        self.assertEqual(result["coverage"]["official_sources_reviewed"], 1)
        self.assertEqual(result["coverage"]["connected_sources"], 0)
        self.assertEqual(result["live_items"], [])
        self.assertEqual(result["sources"][0]["status"], "not_connected")
        self.assertEqual(
            result["historical_events"][0]["status"],
            "available_in_market_sentiment",
        )

    def test_nse_announcement_csv_parser_accepts_manual_download_and_rejects_bad_rows(self):
        csv_payload = (
            "SYMBOL,COMPANY NAME,SUBJECT,BROADCAST DATE/TIME,ATTACHMENT URL\n"
            "INFY,Infosys Limited,Board meeting outcome,05-Oct-2026 15:42:10,"
            "https://example.test/infosys.pdf\n"
        )
        rows = parse_nse_announcement_csv(csv_payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "INFY")
        self.assertEqual(rows[0]["category"], "corporate_announcement")
        self.assertEqual(rows[0]["published_at"], "2026-10-05T15:42:10+05:30")
        with self.assertRaisesRegex(ValueError, "invalid_nse_announcement_row"):
            parse_nse_announcement_csv(
                "SYMBOL,COMPANY NAME,SUBJECT,BROADCAST DATE/TIME\n"
                "bad symbol,Company,Subject,05-Oct-2026 15:42:10\n"
            )

    def test_earnings_csv_and_analysis_keep_loss_comparisons_explicit(self):
        header = (
            "Symbol,Company Name,Sector,Basis,Fiscal Year,Quarter,Period End,"
            "Reported At,Currency,Unit,Revenue,Net Profit,EPS,Source URL\n"
        )
        payload = header + (
            "ABC,ABC Limited,Industrials,Consolidated,2025-26,Q1,2025-06-30,"
            "2025-07-20,INR,crore,100,-5,-1,https://example.test/abc-old.pdf\n"
            "ABC,ABC Limited,Industrials,Consolidated,2026-27,Q1,2026-06-30,"
            "2026-07-20,INR,crore,120,10,2,https://example.test/abc-new.pdf\n"
        )
        records = parse_earnings_csv(payload)
        result = build_earnings_analysis(records)
        row = result["rows"][0]
        self.assertEqual(row["revenue_yoy_pct"], 20.0)
        self.assertIsNone(row["revenue_qoq_pct"])
        self.assertEqual(row["profit_state"], "turned_profitable")
        self.assertIsNone(row["net_profit_yoy_pct"])
        self.assertEqual(row["net_profit_yoy_change"], 15.0)
        self.assertEqual(result["coverage"]["turnarounds"], 1)

    def test_earnings_csv_rejects_missing_provenance_and_future_reports(self):
        header = (
            "Symbol,Company Name,Sector,Basis,Fiscal Year,Quarter,Period End,"
            "Reported At,Currency,Unit,Revenue,Net Profit,EPS,Source URL\n"
        )
        with self.assertRaisesRegex(ValueError, "invalid_earnings_row"):
            parse_earnings_csv(
                header
                + "ABC,ABC Limited,Industrials,Consolidated,2026-27,Q1,2026-06-30,"
                "2026-07-20,INR,crore,120,10,2,\n"
            )
        with self.assertRaisesRegex(ValueError, "invalid_earnings_date"):
            parse_earnings_csv(
                header
                + "ABC,ABC Limited,Industrials,Consolidated,2027-28,Q1,2027-06-30,"
                "2027-07-20,INR,crore,120,10,2,https://example.test/a.pdf\n"
            )

    def test_earnings_csv_preserves_release_known_catalyst_fields(self):
        payload = (
            "Symbol,Company Name,Sector,Basis,Fiscal Year,Quarter,Period End,"
            "Reported At,Currency,Unit,Revenue,Net Profit,EPS,Source URL,"
            "Consensus EPS,Consensus Captured At,Guidance State,Guidance Source URL\n"
            "ABC,ABC Limited,Industrials,Consolidated,2026-27,Q1,2026-06-30,"
            "2026-07-20,INR,crore,120,10,2,https://example.test/result.pdf,"
            "1.8,2026-07-19T12:00:00+05:30,maintained,https://example.test/guidance.pdf\n"
        )
        row = parse_earnings_csv(payload)[0]

        self.assertEqual(row["actual_eps"], 2.0)
        self.assertEqual(row["consensus_eps"], 1.8)
        self.assertEqual(row["guidance_state"], "maintained")
        self.assertIn("__catalyst__", row["raw"])

    def test_expense_csv_normalizes_historical_months_and_skips_invalid_rows(self):
        result = parse_expense_file(
            "expenses.csv",
            (
                "Date,Category,Description,Payment,Amount\n"
                "05/01/2026,Housing,Monthly rent,Bank transfer,25000\n"
                "2026-02-08,Food,Groceries,UPI,3250.50\n"
                "not-a-date,Other,Ignored,Cash,10\n"
            ).encode("utf-8"),
        )

        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["rejected_count"], 1)
        self.assertEqual(result["rows"][0]["date"], "2026-01-05")
        self.assertEqual(result["rows"][1]["amount"], 3250.5)

    def test_expense_ods_normalizes_historical_rows(self):
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:spreadsheet><table:table table:name="Expenses">
  <table:table-row>
   <table:table-cell office:value-type="string"><text:p>Date</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Category</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Description</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Payment</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Amount</text:p></table:table-cell>
  </table:table-row>
  <table:table-row>
   <table:table-cell office:value-type="date" office:date-value="2026-03-14"><text:p>14/03/2026</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Travel</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Train ticket</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>UPI</text:p></table:table-cell>
   <table:table-cell office:value-type="currency" office:value="1450.75"><text:p>1,450.75</text:p></table:table-cell>
  </table:table-row>
 </table:table></office:spreadsheet></office:body>
</office:document-content>"""
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
            archive.writestr("content.xml", content)

        result = parse_expense_file("history.ods", payload.getvalue())

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["sheets_read"], ["Expenses"])
        self.assertEqual(result["rows"][0]["date"], "2026-03-14")
        self.assertEqual(result["rows"][0]["amount"], 1450.75)

    def test_expense_ods_ignores_libreoffice_empty_padding(self):
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:spreadsheet><table:table table:name="Monthly ledger">
  <table:table-header-rows><table:table-row>
   <table:table-cell office:value-type="string"><text:p>Date</text:p></table:table-cell>
   <table:table-cell office:value-type="string"><text:p>Amount</text:p></table:table-cell>
   <table:table-cell table:number-columns-repeated="1022"/>
  </table:table-row></table:table-header-rows>
  <table:table-row>
   <table:table-cell office:value-type="date" office:date-value="2026-04-02"><text:p>02/04/2026</text:p></table:table-cell>
   <table:table-cell office:value-type="float" office:value="799"><text:p>799</text:p></table:table-cell>
   <table:table-cell table:number-columns-repeated="1022"/>
  </table:table-row>
  <table:table-row table:number-rows-repeated="1048574"><table:table-cell table:number-columns-repeated="1024"/></table:table-row>
 </table:table></office:spreadsheet></office:body>
</office:document-content>"""
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
            archive.writestr("content.xml", content)

        result = parse_expense_file("libreoffice-history.ods", payload.getvalue())

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["rows"][0]["date"], "2026-04-02")
        self.assertEqual(result["rows"][0]["amount"], 799.0)

    def test_expense_upload_boundary_accepts_all_supported_formats(self):
        self.assertTrue(is_supported_expense_import_file_name("history.csv"))
        self.assertTrue(is_supported_expense_import_file_name("history.xlsx"))
        self.assertTrue(is_supported_expense_import_file_name("history.ods"))
        self.assertTrue(is_supported_expense_import_file_name("HISTORY.ODS"))
        self.assertFalse(is_supported_expense_import_file_name("history.pdf"))

    def test_expense_ods_imports_annual_category_matrix_and_split_month_columns(self):
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:spreadsheet><table:table table:name="2024">
  <table:table-row>
   <table:table-cell/><table:table-cell><text:p>January</text:p></table:table-cell>
   <table:table-cell><text:p>February</text:p></table:table-cell><table:table-cell><text:p>March</text:p></table:table-cell>
   <table:table-cell><text:p>April</text:p></table:table-cell><table:table-cell><text:p>May</text:p></table:table-cell>
   <table:table-cell/><table:table-cell><text:p>June</text:p></table:table-cell>
  </table:table-row>
  <table:table-row><table:table-cell><text:p>Income</text:p></table:table-cell></table:table-row>
  <table:table-row><table:table-cell><text:p>Expenses</text:p></table:table-cell></table:table-row>
  <table:table-row><table:table-cell><text:p>Food</text:p></table:table-cell>
   <table:table-cell office:value-type="float" office:value="10"/><table:table-cell office:value-type="float" office:value="20"/>
   <table:table-cell office:value-type="float" office:value="30"/><table:table-cell office:value-type="float" office:value="40"/>
   <table:table-cell office:value-type="float" office:value="0"/><table:table-cell office:value-type="float" office:value="50"/>
   <table:table-cell office:value-type="float" office:value="60"/>
  </table:table-row>
  <table:table-row><table:table-cell><text:p>Total Exp</text:p></table:table-cell>
   <table:table-cell office:value-type="float" office:value="10"/><table:table-cell office:value-type="float" office:value="20"/>
   <table:table-cell office:value-type="float" office:value="30"/><table:table-cell office:value-type="float" office:value="40"/>
   <table:table-cell office:value-type="float" office:value="0"/><table:table-cell office:value-type="float" office:value="50"/>
   <table:table-cell office:value-type="float" office:value="60"/>
  </table:table-row>
 </table:table></office:spreadsheet></office:body>
</office:document-content>"""
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
            archive.writestr("content.xml", content)

        result = parse_expense_file("annual-expenses.ods", payload.getvalue())

        self.assertEqual(result["row_count"], 6)
        self.assertEqual(result["detected_layouts"], ["annual_category_matrix"])
        self.assertEqual([row["amount"] for row in result["rows"]], [10, 20, 30, 40, 50, 60])
        self.assertEqual(result["rejected_count"], 0)

    def test_macro_event_calendar_keeps_verified_events_and_pending_rbi_separate(self):
        result = build_macro_events_calendar(
            today=date(2026, 10, 6),
            sources=(
                {
                    "key": "verified",
                    "label": "Official calendar",
                    "authority": "Authority",
                    "region": "India",
                    "url": "https://example.test/calendar",
                    "status": "verified_snapshot",
                    "note": "Reviewed",
                },
                {
                    "key": "pending",
                    "label": "Pending calendar",
                    "authority": "Central bank",
                    "region": "India",
                    "url": "https://example.test/pending",
                    "status": "date_confirmation_required",
                    "note": "Do not guess",
                },
            ),
            events=(
                {
                    "key": "ongoing_meeting",
                    "title": "Official multi-day meeting",
                    "region": "India",
                    "category": "central_bank",
                    "start_at": "2026-10-05",
                    "end_at": "2026-10-06",
                    "timezone": "Asia/Kolkata",
                    "source_key": "verified",
                },
                {
                    "key": "release",
                    "title": "Official release",
                    "region": "India",
                    "category": "inflation",
                    "start_at": "2026-10-12T08:30:00+05:30",
                    "timezone": "Asia/Kolkata",
                    "source_key": "verified",
                },
                {
                    "key": "old",
                    "title": "Past release",
                    "region": "India",
                    "category": "growth",
                    "start_at": "2026-10-01",
                    "timezone": "Asia/Kolkata",
                    "source_key": "verified",
                },
            ),
        )
        self.assertEqual(result["status"], "official_calendar_snapshot_ready")
        self.assertEqual(result["contract"]["version"], "macro-events-calendar-v1")
        self.assertFalse(result["contract"]["unscheduled_news_enabled"])
        self.assertEqual(result["coverage"]["upcoming_events"], 2)
        self.assertEqual(result["coverage"]["next_7_days"], 2)
        self.assertEqual(result["coverage"]["verified_sources"], 1)
        self.assertEqual(result["coverage"]["pending_sources"], 1)
        self.assertEqual(result["next_event"]["key"], "ongoing_meeting")
        self.assertTrue(result["next_event"]["ongoing"])
        self.assertEqual(result["next_event"]["days_until"], 0)
        self.assertEqual(result["events"][1]["india_time"], "2026-10-12T08:30+05:30")

    def test_external_cluster_readiness_requires_complete_dated_sessions(self):
        dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(252)]
        institutional = [
            {"date": session_date, "category": category}
            for session_date in dates
            for category in ("FII/FPI", "DII")
        ]
        macro = [
            {"date": session_date, "metric_key": metric}
            for session_date in dates
            for metric in (
                "usd_inr",
                "gbp_inr",
                "eur_inr",
                "jpy_100_inr",
                "india_10y_gsec_yield",
            )
        ]
        futures = [
            {"date": dates[-1], "underlying": f"STOCK{index}"}
            for index in range(168)
        ]
        result = build_regime_external_cluster_readiness(
            institutional_flow_rows=institutional,
            macro_snapshot_rows=macro,
            futures_snapshot_rows=futures,
        )
        by_key = {row["key"]: row for row in result["rows"]}
        self.assertTrue(by_key["nse_provisional_institutional_flows"]["history_ready"])
        self.assertFalse(by_key["nse_provisional_institutional_flows"]["walk_forward_ready"])
        self.assertTrue(by_key["rbi_currency_and_rates"]["history_ready"])
        self.assertEqual(by_key["kite_futures_oi"]["stored_sessions"], 1)
        self.assertFalse(any(row["scoring_ready"] for row in result["rows"]))

    def test_recovering_state_uses_prior_regimes_without_outcome_data(self):
        labels = (
            ["weak_market"] * 6
            + ["uncertain_market"] * 3
            + ["positive_market"]
            + ["high_risk_market"] * 5
            + ["cautiously_positive", "high_risk_market"]
        )
        observations = [
            {
                "date": date(2026, 1, 1) + timedelta(days=index),
                "confirmed_label_key": label,
            }
            for index, label in enumerate(labels)
        ]
        result = apply_recovering_market_state(observations)
        self.assertEqual(result["status"], "validation_only_outcome_blind_rule")
        self.assertEqual(result["episode_count"], 2)
        self.assertEqual(result["exit_counts"]["positive_market_confirmed"], 1)
        self.assertEqual(result["exit_counts"]["relapsed_to_risk"], 1)
        self.assertEqual(observations[6]["transition_label_key"], "recovering_market")
        self.assertEqual(observations[9]["transition_label_key"], "positive_market")
        self.assertEqual(observations[-1]["transition_label_key"], "high_risk_market")

    def test_regime_walk_forward_uses_current_constituents_inside_fno_universe(self):
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=index) for index in range(400)]

        def rising(multiplier):
            return [
                {
                    "date": session_date,
                    "open": 100.0 + index * multiplier,
                    "high": 101.0 + index * multiplier,
                    "low": 99.0 + index * multiplier,
                    "close": 100.0 + index * multiplier,
                }
                for index, session_date in enumerate(dates)
            ]

        result = calculate_regime_walk_forward_validation(
            rising(1.0),
            {name: rising(0.5) for name in ("A", "B", "C", "D", "E", "OUTSIDE")},
            target_index="Nifty IT",
            constituent_symbols=["A", "B", "C", "D", "E", "MISSING"],
            constituent_snapshot_as_of="2026-09-29",
        )
        breadth = result["breadth_universe"]
        self.assertEqual(result["stock_universe_size"], 5)
        self.assertEqual(breadth["official_constituent_count"], 6)
        self.assertEqual(breadth["fno_constituent_count"], 5)
        self.assertEqual(breadth["constituents_outside_fno_universe"], ["MISSING"])
        self.assertEqual(breadth["constituent_snapshot_as_of"], "2026-09-29")

    def test_regime_walk_forward_uses_dated_constituent_membership_when_available(self):
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=index) for index in range(400)]

        def rising(multiplier):
            return [
                {
                    "date": session_date,
                    "open": 100.0 + index * multiplier,
                    "high": 101.0 + index * multiplier,
                    "low": 99.0 + index * multiplier,
                    "close": 100.0 + index * multiplier,
                }
                for index, session_date in enumerate(dates)
            ]

        first_members = ["A", "B", "C", "D", "E"]
        second_members = ["F", "G", "H", "I", "J"]
        result = calculate_regime_walk_forward_validation(
            rising(1.0),
            {name: rising(0.5) for name in first_members + second_members},
            target_index="Nifty IT",
            constituent_symbols=["CURRENT"],
            constituent_membership_history=[
                {
                    "effective_from": dates[0],
                    "effective_to": dates[300],
                    "symbols": first_members,
                },
                {
                    "effective_from": dates[301],
                    "effective_to": None,
                    "symbols": second_members,
                },
            ],
        )
        breadth = result["breadth_universe"]
        self.assertEqual(result["stock_universe_size"], 10)
        self.assertTrue(breadth["membership_history_available"])
        self.assertEqual(breadth["membership_snapshot_count"], 2)
        self.assertEqual(
            breadth["method"],
            "point_in_time_index_constituents_intersected_with_fno_universe",
        )

    def test_official_constituent_snapshot_covers_supported_index_universe(self):
        snapshot = load_index_constituent_snapshot()
        self.assertEqual(snapshot["membership_type"], "current_snapshot")
        self.assertEqual(snapshot["history"], {})
        self.assertEqual(len(snapshot["indices"]), 19)
        self.assertEqual(len(snapshot["indices"]["Nifty 50"]), 50)
        self.assertIn("SBIN", snapshot["indices"]["Nifty PSU Bank"])

    def test_completed_history_date_excludes_current_session_before_close(self):
        india = ZoneInfo("Asia/Kolkata")
        self.assertEqual(
            completed_history_date(datetime(2026, 9, 24, 9, 30, tzinfo=india)),
            date(2026, 9, 23),
        )
        self.assertEqual(
            completed_history_date(datetime(2026, 9, 24, 15, 40, tzinfo=india)),
            date(2026, 9, 24),
        )

    def test_full_seasonality_cache_rejects_ranking_only_payload(self):
        self.assertFalse(
            is_complete_seasonality_payload({"month_rows": [], "historical_requests": 0})
        )
        self.assertTrue(
            is_complete_seasonality_payload(
                {
                    "ok": True,
                    "month_rows": [],
                    "weekday_rows": [],
                    "validation": {},
                }
            )
        )

    def test_public_constituent_request_uses_browser_identity_without_credentials(self):
        self.assertTrue(NIFTY_INDICES_PUBLIC_USER_AGENT.startswith("Mozilla/5.0"))
        self.assertNotIn("cookie", NIFTY_INDICES_PUBLIC_USER_AGENT.lower())
        self.assertNotIn("token", NIFTY_INDICES_PUBLIC_USER_AGENT.lower())

    def test_raw_request_token_is_preserved(self):
        self.assertEqual(extract_request_token("request-token-123"), "request-token-123")

    def test_request_token_is_extracted_from_redirect_url(self):
        redirect = "https://example.test/callback?status=success&request_token=abc%2B123&action=login"
        self.assertEqual(extract_request_token(redirect), "abc+123")

    def test_missing_or_ambiguous_request_token_is_rejected(self):
        self.assertEqual(extract_request_token("https://example.test/callback?status=success"), "")
        self.assertEqual(
            extract_request_token(
                "https://example.test/callback?request_token=first&request_token=second"
            ),
            "",
        )

    def test_checksum_uses_kite_documented_field_order(self):
        self.assertEqual(
            build_checksum("key", "token", "secret"),
            "08a03d928417ea4085557933d3b187ff2a3515b039d6054dbd230c95d978a17a",
        )

    def test_network_errors_are_classified_without_sensitive_details(self):
        self.assertEqual(classify_network_error(socket.timeout()), "provider_timeout")
        self.assertEqual(
            classify_network_error(urllib.error.URLError(socket.gaierror())),
            "provider_dns_failure",
        )
        blocked = PermissionError("blocked")
        self.assertEqual(classify_network_error(blocked), "provider_network_blocked")
        self.assertEqual(
            classify_network_error(urllib.error.URLError(ConnectionRefusedError())),
            "provider_connection_failed",
        )

    def test_instrument_master_discovers_only_current_nse_indices(self):
        fixture = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
1,1,NIFTY 50,NIFTY 50,0,,0,0.05,1,EQ,INDICES,NSE
2,2,NIFTY BANK,NIFTY BANK,0,,0,0.05,1,EQ,INDICES,NSE
3,3,NIFTY CONSR DURBL,NIFTY CONSR DURBL,0,,0,0.05,1,EQ,INDICES,NSE
4,4,NIFTY IT,NIFTY IT,0,,0,0.05,1,EQ,INDICES,BSE
5,5,NIFTY PHARMA,NIFTY PHARMA,0,,0,0.05,1,EQ,NSE,NSE
"""
        targets, missing = discover_sectoral_indices(fixture)
        self.assertEqual(
            targets,
            [
                ("Nifty 50", "NSE:NIFTY 50", "broad_market"),
                ("Nifty Bank", "NSE:NIFTY BANK", "sectoral"),
                ("Nifty Consumer Durables", "NSE:NIFTY CONSR DURBL", "sectoral"),
            ],
        )
        self.assertEqual(len(missing), len(OFFICIAL_SECTORAL_INDICES) - 2)
        self.assertNotIn("Nifty Bank", missing)

    def test_invalid_instrument_master_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_instrument_master"):
            discover_sectoral_indices("symbol,name\nNIFTY BANK,NIFTY BANK\n")

    def test_nifty500_constituent_file_accepts_the_official_security_count(self):
        header = "Company Name,Industry,Symbol,Series,ISIN Code\n"
        body = "".join(
            f"Company {index},Sector {index % 3},SYM{index},EQ,ISIN{index}\n"
            for index in range(500)
        )
        rows = parse_nifty500_constituents(header + body)
        self.assertEqual(len(rows), 500)
        self.assertEqual(
            rows[0],
            {"symbol": "SYM0", "name": "Company 0", "sector": "Sector 0"},
        )
        current_official_rows = (
            "".join(
                f"Company {index},Sector {index % 3},SYM{index},EQ,ISIN{index}\n"
                for index in range(498)
            )
            + "Bagmane Prime Office REIT,Realty,BAGMANE,RR,INE2OVN25015\n"
            + "Brookfield India Real Estate Trust,Realty,BIRET,RR,INE0FDU25010\n"
            + "EMBASSY OFFICE PARKS REIT,Realty,EMBASSY,RR,INE041025011\n"
        )
        current_rows = parse_nifty500_constituents(header + current_official_rows)
        self.assertEqual(len(current_rows), 501)
        self.assertEqual(
            current_rows[-1],
            {
                "symbol": "EMBASSY",
                "name": "EMBASSY OFFICE PARKS REIT",
                "sector": "Realty",
            },
        )
        rows_with_be_security = parse_nifty500_constituents(
            header + body + "Company BE,Sector 1,SYMBE,BE,ISINBE\n"
        )
        self.assertEqual(len(rows_with_be_security), 501)
        with self.assertRaisesRegex(ValueError, "unexpected_constituent_count"):
            parse_nifty500_constituents(header + body.rsplit("\n", 2)[0] + "\n")

    def test_nifty500_constituent_file_rejects_unapproved_series(self):
        header = "Company Name,Industry,Symbol,Series,ISIN Code\n"
        body = "".join(
            f"Company {index},Sector,SYM{index},EQ,ISIN{index}\n"
            for index in range(499)
        )
        with self.assertRaisesRegex(ValueError, "invalid_constituent_file"):
            parse_nifty500_constituents(
                header + body + "Company 499,Sector,SYM499,BZ,ISIN499\n"
            )

    def test_stock_ytd_table_ranks_returns_and_preserves_missing_rows(self):
        constituents = [
            {"symbol": "AAA", "name": "Alpha Ltd", "sector": "Industrials"},
            {"symbol": "BBB", "name": "Beta Ltd", "sector": "Financial Services"},
            {"symbol": "MISS", "name": "Missing Ltd", "sector": "Healthcare"},
        ]
        sessions = [date(2023, 12, 29)] + [
            date(2024, 1, 1) + timedelta(days=offset) for offset in range(220)
        ]
        histories = {
            "AAA": list(zip(sessions, [100.0] + [100.0 + offset / 2 for offset in range(1, 221)])),
            "BBB": list(zip(sessions, [100.0] + [100.0 - offset / 10 for offset in range(1, 221)])),
        }

        result = build_stock_ytd_table(
            constituents,
            histories,
            as_of=date(2024, 8, 7),
            year=2024,
        )

        self.assertEqual(result["contract_version"], "nifty500-stock-ytd-v1")
        self.assertEqual(result["price_label"], "Latest completed close")
        self.assertEqual([row["symbol"] for row in result["rows"]], ["AAA", "BBB", "MISS"])
        self.assertEqual([row["rank"] for row in result["rows"]], [1, 2, None])
        self.assertEqual(result["rows"][0]["name"], "Alpha Ltd")
        self.assertGreater(result["rows"][0]["ytd_performance_pct"], 0)
        self.assertLess(result["rows"][1]["ytd_performance_pct"], 0)
        self.assertIsNotNone(result["rows"][0]["from_20dma_pct"])
        self.assertIsNotNone(result["rows"][0]["from_200dma_pct"])
        self.assertEqual(
            result["coverage"],
            {"total": 3, "ready": 2, "partial_history": 0, "unavailable": 1},
        )

    def test_stock_ytd_table_aligns_historical_year_metrics_to_year_end(self):
        constituents = [{"symbol": "AAA", "name": "Alpha Ltd", "sector": "Industrials"}]
        start = date(2022, 12, 30)
        sessions = [start + timedelta(days=offset) for offset in range(800)]
        histories = {"AAA": [(session, 100.0 + offset) for offset, session in enumerate(sessions)]}

        result = build_stock_ytd_table(
            constituents,
            histories,
            as_of=date(2025, 3, 10),
            year=2023,
        )

        row = result["rows"][0]
        self.assertEqual(result["price_label"], "Year-end completed close")
        self.assertEqual(row["price_date"], "2023-12-31")
        self.assertEqual(row["ltp"], 466.0)
        self.assertEqual(row["status"], "ready")

    def test_equity_tokens_accept_only_nse_eq_rows(self):
        fixture = """instrument_token,tradingsymbol,instrument_type,segment,exchange
101,AAA,EQ,NSE,NSE
102,BBB,EQ,BSE,BSE
103,AAAFUT,FUT,NFO-FUT,NFO
"""
        self.assertEqual(parse_equity_tokens(fixture), {"AAA": "101"})

    def test_near_month_futures_inventory_selects_earliest_live_contract(self):
        fixture = """instrument_token,tradingsymbol,name,expiry,lot_size,instrument_type,segment,exchange
101,AAA26SEPFUT,AAA,2026-09-24,500,FUT,NFO-FUT,NFO
102,AAA26OCTFUT,AAA,2026-10-29,500,FUT,NFO-FUT,NFO
103,AAA26SEP100CE,AAA,2026-09-24,500,CE,NFO-OPT,NFO
104,BBB26OCTFUT,BBB,2026-10-29,250,FUT,NFO-FUT,NFO
"""
        contracts, missing = parse_near_month_stock_futures(
            fixture, ("AAA", "BBB", "CCC"), as_of=date(2026, 9, 24)
        )
        self.assertEqual([row["tradingsymbol"] for row in contracts], ["AAA26SEPFUT", "BBB26OCTFUT"])
        self.assertEqual(contracts[0]["lot_size"], 500)
        self.assertEqual(missing, ["CCC"])

    def test_futures_rollover_uses_last_completed_session_before_close(self):
        fixture = """instrument_token,tradingsymbol,name,expiry,lot_size,instrument_type,segment,exchange
101,AAA26OCTFUT,AAA,2026-10-27,500,FUT,NFO-FUT,NFO
102,AAA26NOVFUT,AAA,2026-11-26,500,FUT,NFO-FUT,NFO
"""
        india = ZoneInfo("Asia/Kolkata")
        completed_through = completed_history_date(
            datetime(2026, 10, 28, 14, 0, tzinfo=india)
        )
        contracts, missing = parse_near_month_stock_futures(
            fixture, ("AAA",), as_of=completed_through
        )
        self.assertEqual(completed_through, date(2026, 10, 27))
        self.assertEqual(contracts[0]["tradingsymbol"], "AAA26OCTFUT")
        self.assertEqual(missing, [])

    def test_futures_retry_requests_only_contracts_missing_for_session(self):
        contracts = [
            {"underlying": "AAA", "tradingsymbol": "AAA26OCTFUT"},
            {"underlying": "BBB", "tradingsymbol": "BBB26OCTFUT"},
        ]
        stored = [
            {
                "contract_key": "NFO:AAA26OCTFUT",
                "date": date(2026, 10, 27),
            }
        ]
        pending = pending_futures_contracts_for_session(
            contracts, stored, date(2026, 10, 27)
        )
        self.assertEqual(
            [row["tradingsymbol"] for row in pending], ["BBB26OCTFUT"]
        )

    def test_futures_quote_snapshot_requires_completed_current_session(self):
        contracts = [
            {
                "underlying": "AAA", "tradingsymbol": "AAA26SEPFUT", "exchange": "NFO",
                "instrument_token": "101", "expiry": date(2026, 9, 24), "lot_size": 500,
            }
        ]
        payload = {
            "status": "success",
            "data": {
                "NFO:AAA26SEPFUT": {
                    "timestamp": "2026-09-24 15:30:00",
                    "last_price": 105.0,
                    "volume": 125000,
                    "oi": 750000,
                    "ohlc": {"open": 100.0, "high": 108.0, "low": 98.0, "close": 99.0},
                }
            },
        }
        snapshots, missing = normalize_futures_eod_quotes(
            payload,
            contracts,
            now=datetime(2026, 9, 24, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
        self.assertEqual(missing, [])
        self.assertEqual(snapshots[0]["close"], 105.0)
        self.assertEqual(snapshots[0]["open_interest"], 750000)
        with self.assertRaisesRegex(ValueError, "futures_eod_not_due"):
            normalize_futures_eod_quotes(
                payload,
                contracts,
                now=datetime(2026, 9, 24, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
            )

    def test_futures_history_snapshot_uses_latest_completed_candle_with_oi(self):
        contract = {
            "underlying": "AAA", "tradingsymbol": "AAA26OCTFUT", "exchange": "NFO",
            "instrument_token": "101", "expiry": date(2026, 10, 29), "lot_size": 500,
        }
        payload = {
            "status": "success",
            "data": {
                "candles": [
                    ["malformed", 0, 0, 0, 0, 0],
                    ["2026-09-24T00:00:00+0530", 100, 106, 98, 104, 100000, 700000],
                    ["2026-09-25T00:00:00+0530", 104, 109, 103, 108, 120000, 740000],
                    ["2026-09-28T00:00:00+0530", 108, 112, 106, 111, 40000, 760000],
                ]
            },
        }
        snapshot = parse_futures_daily_snapshot(
            payload, contract, completed_through=date(2026, 9, 25)
        )
        self.assertEqual(snapshot["date"], date(2026, 9, 25))
        self.assertEqual(snapshot["close"], 108.0)
        self.assertEqual(snapshot["open_interest"], 740000)

    def test_futures_oi_summary_does_not_compare_across_rollover(self):
        rows = [
            {"date": date(2026, 9, 22), "underlying": "AAA", "tradingsymbol": "AAA26SEPFUT", "contract_key": "NFO:AAA26SEPFUT", "expiry": date(2026, 9, 24), "close": 100.0, "open_interest": 1000, "volume": 500},
            {"date": date(2026, 9, 23), "underlying": "AAA", "tradingsymbol": "AAA26SEPFUT", "contract_key": "NFO:AAA26SEPFUT", "expiry": date(2026, 9, 24), "close": 102.0, "open_interest": 1100, "volume": 600},
            {"date": date(2026, 9, 22), "underlying": "BBB", "tradingsymbol": "BBB26SEPFUT", "contract_key": "NFO:BBB26SEPFUT", "expiry": date(2026, 9, 24), "close": 200.0, "open_interest": 2000, "volume": 800},
            {"date": date(2026, 9, 23), "underlying": "BBB", "tradingsymbol": "BBB26OCTFUT", "contract_key": "NFO:BBB26OCTFUT", "expiry": date(2026, 10, 29), "close": 198.0, "open_interest": 900, "volume": 700},
        ]
        summary = calculate_futures_oi_summary(rows)
        self.assertEqual(summary["comparable_count"], 1)
        self.assertEqual(summary["rollover_baseline_count"], 1)
        self.assertEqual(summary["classification_status"], "descriptive_only")
        self.assertEqual(summary["state_counts"]["long_build_up"], 1)
        self.assertEqual(summary["states"][0]["price_change_pct"], 2.0)
        self.assertEqual(summary["states"][0]["oi_change_pct"], 10.0)

    def test_futures_oi_summary_filters_noise_stale_gaps_and_zero_liquidity(self):
        def row(symbol, day, close, oi, volume=1000):
            return {
                "date": day,
                "underlying": symbol,
                "tradingsymbol": f"{symbol}26OCTFUT",
                "contract_key": f"NFO:{symbol}26OCTFUT",
                "expiry": date(2026, 10, 29),
                "close": close,
                "open_interest": oi,
                "volume": volume,
            }

        rows = [
            row("NOISE", date(2026, 9, 24), 100.0, 1000),
            row("NOISE", date(2026, 9, 25), 100.1, 1020),
            row("STALE", date(2026, 9, 18), 100.0, 1000),
            row("STALE", date(2026, 9, 25), 102.0, 1100),
            row("ZERO", date(2026, 9, 24), 100.0, 1000),
            row("ZERO", date(2026, 9, 25), 102.0, 1100, volume=0),
        ]
        summary = calculate_futures_oi_summary(rows)
        self.assertEqual(summary["eligible_count"], 1)
        self.assertEqual(summary["state_counts"]["no_clear_signal"], 1)
        self.assertEqual(summary["stale_gap_count"], 1)
        self.assertEqual(summary["liquidity_excluded_count"], 1)
        self.assertFalse(summary["safeguards"]["regime_score_enabled"])

    def test_dashboard_index_tokens_bind_exact_dashboard_indices(self):
        fixture = """instrument_token,tradingsymbol,name,segment,exchange
1,NIFTY 50,NIFTY 50,INDICES,NSE
2,NIFTY BANK,NIFTY BANK,INDICES,NSE
3,NIFTY IT,NIFTY IT,INDICES,NSE
4,NIFTY IT,NIFTY IT,INDICES,BSE
5,NIFTY ENERGY,NIFTY ENERGY,INDICES,NSE
6,INDIA VIX,INDIA VIX,INDICES,NSE
"""
        self.assertEqual(
            parse_dashboard_index_tokens(fixture),
            {
                "Nifty 50": "1",
                "Nifty Bank": "2",
                "Nifty IT": "3",
                "Nifty Energy": "5",
                "India VIX": "6",
            },
        )

    def test_seasonality_index_tokens_accept_only_supported_kite_indices(self):
        fixture = """instrument_token,tradingsymbol,name,segment,exchange
1,NIFTY 50,NIFTY 50,INDICES,NSE
2,NIFTY BANK,NIFTY BANK,INDICES,NSE
3,NIFTY ENERGY,NIFTY ENERGY,INDICES,NSE
4,NIFTY 100,NIFTY 100,INDICES,NSE
5,NIFTY IT,NIFTY IT,INDICES,BSE
"""
        self.assertEqual(
            parse_seasonality_index_tokens(fixture),
            {"Nifty 50": "1", "Nifty Bank": "2", "Nifty Energy": "3"},
        )

    def test_index_ytd_uses_last_prior_year_close_and_latest_completed_close(self):
        row = calculate_index_ytd(
            "Nifty 50",
            [
                (date(2025, 12, 30), 98.0),
                (date(2025, 12, 31), 100.0),
                (date(2026, 9, 22), 112.345),
            ],
        )
        self.assertEqual(row["close"], 112.34)
        self.assertEqual(row["prior_year_close_date"], "2025-12-31")
        self.assertEqual(row["ytd_pct"], 12.35)

    def test_daily_closes_exclude_incomplete_current_day(self):
        payload = {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-09-22T00:00:00+0530", 1, 2, 0.5, 1.5, 100],
                    ["2026-09-23T00:00:00+0530", 1, 2, 0.5, 1.6, 100],
                ]
            },
        }
        morning = parse_daily_closes(payload, today=date(2026, 9, 23), now_time=time(10, 0))
        evening = parse_daily_closes(payload, today=date(2026, 9, 23), now_time=time(16, 0))
        self.assertEqual([item[0] for item in morning], [date(2026, 9, 22)])
        self.assertEqual([item[0] for item in evening], [date(2026, 9, 22), date(2026, 9, 23)])

    def test_daily_candles_validate_ohlc_and_exclude_incomplete_current_day(self):
        payload = {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-09-22T00:00:00+0530", 100, 110, 95, 105, 100],
                    ["2026-09-23T00:00:00+0530", 105, 112, 101, 108, 100],
                ]
            },
        }
        candles = parse_daily_candles(payload, today=date(2026, 9, 23), now_time=time(10, 0))
        self.assertEqual([item["date"] for item in candles], [date(2026, 9, 22)])
        self.assertEqual(candles[0]["volume"], 100)
        invalid = {
            "status": "success",
            "data": {"candles": [["2026-09-22T00:00:00+0530", 100, 90, 95, 105, 100]]},
        }
        with self.assertRaisesRegex(ValueError, "invalid_provider_response"):
            parse_daily_candles(invalid, today=date(2026, 9, 23), now_time=time(10, 0))
        invalid_volume = {
            "status": "success",
            "data": {"candles": [["2026-09-22T00:00:00+0530", 100, 110, 95, 105, -1]]},
        }
        with self.assertRaisesRegex(ValueError, "invalid_provider_response"):
            parse_daily_candles(invalid_volume, today=date(2026, 9, 23), now_time=time(10, 0))

    def test_daily_candles_skip_only_all_zero_pre_inception_placeholders(self):
        payload = {
            "status": "success",
            "data": {
                "candles": [
                    ["2000-01-03T00:00:00+0530", 0, 0, 0, 0, 0],
                    ["2005-01-03T00:00:00+0530", 100, 110, 95, 105, 0],
                ]
            },
        }
        candles = parse_daily_candles(payload, today=date(2026, 9, 23), now_time=time(10, 0))
        self.assertEqual([item["date"] for item in candles], [date(2005, 1, 3)])
        partially_zero = {
            "status": "success",
            "data": {"candles": [["2005-01-03T00:00:00+0530", 0, 110, 95, 105, 0]]},
        }
        with self.assertRaisesRegex(ValueError, "invalid_provider_response"):
            parse_daily_candles(partially_zero, today=date(2026, 9, 23), now_time=time(10, 0))

    def test_historical_ranges_are_contiguous_and_bounded(self):
        self.assertEqual(
            historical_date_ranges(date(2026, 1, 1), date(2026, 1, 5), chunk_days=2),
            [
                (date(2026, 1, 1), date(2026, 1, 2)),
                (date(2026, 1, 3), date(2026, 1, 4)),
                (date(2026, 1, 5), date(2026, 1, 5)),
            ],
        )

    def test_historical_lookback_is_rolling_ten_years_and_leap_safe(self):
        self.assertEqual(
            historical_lookback_start(date(2026, 9, 23)),
            date(2016, 9, 23),
        )
        self.assertEqual(
            historical_lookback_start(date(2024, 2, 29)),
            date(2014, 2, 28),
        )

    def test_incremental_history_sync_requests_only_dates_after_last_stored_session(self):
        self.assertEqual(
            incremental_history_ranges(
                date(2016, 9, 28),
                date(2026, 9, 28),
                date(2026, 9, 23),
            ),
            [(date(2026, 9, 24), date(2026, 9, 28))],
        )
        self.assertEqual(
            incremental_history_ranges(
                date(2016, 9, 28),
                date(2026, 9, 28),
                date(2026, 9, 28),
            ),
            [],
        )

    def test_dashboard_eod_store_filters_replayed_provider_history(self):
        candles = [
            {"date": date(2026, 9, 26), "close": 101.0},
            {"date": date(2026, 9, 28), "close": 102.0},
            {"date": date(2026, 9, 29), "close": 103.0},
            {"date": date(2026, 9, 30), "close": 104.0},
        ]
        self.assertEqual(
            candles_after_last_stored_session(candles, date(2026, 9, 28)),
            candles[2:],
        )
        self.assertEqual(candles_after_last_stored_session(candles, None), candles)

    def test_seasonality_uses_close_returns_and_high_low_ranges(self):
        candles = [
            {"date": date(2024, 12, 31), "open": 98.0, "high": 101.0, "low": 97.0, "close": 100.0},
            {"date": date(2025, 1, 2), "open": 100.0, "high": 111.0, "low": 99.0, "close": 110.0},
            {"date": date(2025, 1, 3), "open": 110.0, "high": 121.0, "low": 108.0, "close": 120.0},
            {"date": date(2025, 2, 3), "open": 120.0, "high": 132.0, "low": 117.0, "close": 130.0},
            {"date": date(2025, 3, 3), "open": 130.0, "high": 145.0, "low": 129.0, "close": 140.0},
        ]
        months, weekdays = calculate_seasonality(candles, today=date(2025, 3, 10))
        january = months[0]
        february = months[1]
        march = months[2]
        self.assertEqual(january["count"], 1)
        self.assertEqual(january["average_return_pct"], 20.0)
        self.assertEqual(january["average_range_pct"], 22.22)
        self.assertEqual(february["average_return_pct"], 8.33)
        self.assertEqual(march["count"], 0)
        monday = weekdays[0]
        self.assertEqual(monday["count"], 2)
        self.assertEqual(monday["highest_return_pct"], 8.33)
        self.assertEqual(monday["lowest_return_pct"], 7.69)

    def test_seasonality_validation_populates_turn_and_holdout_tables(self):
        candles = []
        close = 100.0
        for month in range(1, 7):
            for day in range(1, 9):
                close *= 1.0 + (((month + day) % 5) - 2) / 100
                candles.append(
                    {
                        "date": date(2025, month, day),
                        "open": close,
                        "high": close * 1.01,
                        "low": close * 0.99,
                        "close": close,
                    }
                )

        result = calculate_seasonality_validation(candles, today=date(2025, 7, 15))

        self.assertEqual([row["window"] for row in result["turn_rows"]], ["Turn of month", "Rest of month"])
        self.assertEqual(sum(row["count"] for row in result["turn_rows"]), len(candles) - 1)
        self.assertEqual(len(result["held_out_rows"]), 12)
        self.assertEqual(len(result["turn_held_out_rows"]), 2)
        self.assertEqual(result["holdout_split_date"], "2025-04-01")
        self.assertEqual(
            set(result["held_out_summary"]),
            {"same_direction", "train_significant", "survived"},
        )

    def test_month_to_date_returns_use_previous_month_final_close(self):
        histories = {
            "AAA": [
                (date(2026, 8, 28), 100.0),
                (date(2026, 8, 31), 102.0),
                (date(2026, 9, 1), 103.0),
                (date(2026, 9, 22), 112.2),
            ],
            "STALE": [
                (date(2026, 8, 31), 100.0),
                (date(2026, 9, 21), 105.0),
            ],
            "NEW": [(date(2026, 9, 1), 100.0), (date(2026, 9, 22), 110.0)],
        }
        self.assertEqual(
            calculate_month_to_date_returns(histories, as_of=date(2026, 9, 22)),
            {"AAA": 10.0},
        )

    def test_historical_month_rankings_preserve_observation_counts(self):
        result = rank_historical_month_averages(
            {
                "ALPHA": (2.345, 12),
                "BETA": (-1.234, 8),
                "NO_HISTORY": (99.0, 0),
            }
        )
        self.assertEqual(
            result["leader"],
            {"instrument": "ALPHA", "average_return_pct": 2.35, "observations": 12},
        )
        self.assertEqual(
            result["lagger"],
            {"instrument": "BETA", "average_return_pct": -1.23, "observations": 8},
        )
        self.assertEqual(result["evaluated"], 2)

    def test_historical_month_rankings_refuse_empty_or_nonfinite_data(self):
        with self.assertRaisesRegex(ValueError, "historical_month_data_unavailable"):
            rank_historical_month_averages({"EMPTY": (float("nan"), 10)})

    def test_nifty500_context_extends_breadth_and_ranks_relative_strength(self):
        start = date(2026, 3, 17)
        sessions = [start + timedelta(days=offset) for offset in range(205)]
        constituents = [
            {"symbol": "ALPHA", "name": "Alpha", "sector": "Technology"},
            {"symbol": "BETA", "name": "Beta", "sector": "Banks"},
            {"symbol": "GAMMA", "name": "Gamma", "sector": "Technology"},
        ]
        stock_histories = {
            "ALPHA": [(session, 100 + offset * 1.0) for offset, session in enumerate(sessions)],
            "BETA": [(session, 200 - offset * 0.25) for offset, session in enumerate(sessions)],
            "GAMMA": [(session, 100 + offset * 0.5) for offset, session in enumerate(sessions)],
        }
        index_histories = {
            "Nifty 50": [(session, 100 + offset * 0.2) for offset, session in enumerate(sessions)],
            "Nifty IT": [(session, 100 + offset * 0.5) for offset, session in enumerate(sessions)],
            "Nifty Bank": [(session, 100 + offset * 0.05) for offset, session in enumerate(sessions)],
        }
        result = calculate_nifty500_market_context(
            constituents,
            stock_histories,
            index_histories,
        )
        self.assertEqual(result["breadth"]["official_count"], 3)
        self.assertEqual(result["breadth"]["evaluated"], 3)
        self.assertEqual(result["breadth"]["above_50dma_pct"], 66.7)
        self.assertEqual(result["relative_strength"]["indices"]["strongest"]["name"], "Nifty IT")
        self.assertEqual(result["relative_strength"]["indices"]["weakest"]["name"], "Nifty Bank")
        self.assertEqual(result["relative_strength"]["sectors"]["strongest"]["name"], "Technology")
        self.assertEqual(result["relative_strength"]["sectors"]["weakest"]["name"], "Banks")

    def test_market_breadth_uses_completed_aligned_histories(self):
        start = date(2026, 1, 1)
        dates = [start + timedelta(days=index) for index in range(201)]
        rising = list(zip(dates, [float(index + 1) for index in range(201)]))
        falling = list(zip(dates, [float(401 - index) for index in range(201)]))
        constituents = [
            {"symbol": "AAA", "sector": "Alpha"},
            {"symbol": "BBB", "sector": "Alpha"},
            {"symbol": "CCC", "sector": "Beta"},
            {"symbol": "STALE", "sector": "Beta"},
        ]
        rows, as_of, evaluated = calculate_market_breadth(
            constituents,
            {"AAA": rising, "BBB": falling, "CCC": rising, "STALE": rising[:-1]},
        )
        by_sector = {row["sector"]: row for row in rows}
        self.assertEqual(as_of, dates[-1])
        self.assertEqual(evaluated, 3)
        self.assertEqual(by_sector["Alpha"]["above_20dma_pct"], 50)
        self.assertEqual(by_sector["Alpha"]["above_200dma_pct"], 50)
        self.assertEqual(by_sector["Beta"]["evaluated"], 1)

    def test_domestic_sentiment_core_reports_transparent_local_evidence(self):
        start = date(2025, 1, 1)
        dates = [start + timedelta(days=index) for index in range(300)]

        def candles(multiplier, *, stale=False):
            rows = [
                {
                    "date": candle_date,
                    "open": 100.0 + index * multiplier,
                    "high": 101.0 + index * multiplier,
                    "low": 99.0 + index * multiplier,
                    "close": 100.0 + index * multiplier,
                }
                for index, candle_date in enumerate(dates)
            ]
            return rows[:-1] if stale else rows

        vix_candles = [
            {
                "date": candle_date,
                "open": 10.0 + index * 0.02,
                "high": 10.5 + index * 0.02,
                "low": 9.5 + index * 0.02,
                "close": 10.0 + index * 0.02,
            }
            for index, candle_date in enumerate(dates)
        ]
        # A VIX refresh may be newer than the still-aligned cash universe. The
        # calculation should use the VIX observation matching the cash as-of date.
        vix_candles.append(
            {
                "date": dates[-1] + timedelta(days=1),
                "open": 16.0,
                "high": 16.5,
                "low": 15.5,
                "close": 16.0,
            }
        )
        result = calculate_domestic_sentiment_core(
            candles(1.0),
            {"UP1": candles(1.0), "UP2": candles(0.5), "STALE": candles(0.2, stale=True)},
            india_vix_candles=vix_candles,
            retrieved_at=datetime(2025, 10, 28, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["trend"]["band"], "constructive")
        self.assertEqual(result["breadth"]["evaluated"], 2)
        self.assertEqual(result["breadth"]["universe_total"], 3)
        self.assertEqual(result["breadth"]["coverage_pct"], 66.7)
        self.assertEqual(result["breadth"]["missing_count"], 1)
        self.assertEqual(result["breadth"]["missing_stocks"][0]["stock"], "STALE")
        self.assertEqual(result["breadth"]["missing_stocks"][0]["reason"], "latest_session_mismatch")
        self.assertEqual(result["breadth"]["above_200dma_pct"], 100.0)
        self.assertEqual(result["price_strength"]["near_52w_high_pct"], 100.0)
        self.assertEqual(result["price_strength"]["series"][-1]["date"], dates[-1].isoformat())
        self.assertEqual(len(result["price_strength"]["series"]), 49)
        self.assertEqual(result["available_clusters"], 3)
        self.assertTrue(result["volatility"]["india_vix"]["available"])
        self.assertEqual(result["volatility"]["india_vix"]["level"], 15.98)
        self.assertEqual(result["volatility"]["india_vix"]["five_day_change_pt"], 0.1)
        self.assertEqual(result["volatility"]["india_vix"]["one_year_percentile"], 100.0)
        self.assertEqual(result["freshness"]["state"], "fresh")
        self.assertEqual(result["freshness"]["expected_through"], "2025-10-27")
        self.assertEqual(
            result["candidate_regime"]["rule_version"],
            "market-regime-candidate-v1",
        )
        self.assertFalse(result["candidate_regime"]["classification_eligible"])
        self.assertIn(
            "stock_coverage_below_80_pct",
            result["candidate_regime"]["gate_failures"],
        )

    def test_institutional_flow_parser_and_summary_preserve_provisional_values(self):
        parsed = parse_institutional_flows(
            [
                {"buyValue": "14,404.90", "category": "DII", "date": "23-Sep-2026", "netValue": "2341.46", "sellValue": "12063.44"},
                {"buyValue": "13580.4", "category": "FII/FPI", "date": "23-Sep-2026", "netValue": "1617.45", "sellValue": "11962.95"},
            ],
            today=date(2026, 9, 24),
        )
        self.assertEqual(parsed[0]["category"], "DII")
        self.assertEqual(parsed[1]["net_crore"], 1617.45)
        summary = calculate_institutional_flow_summary(parsed)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["publication_status"], "provisional")
        self.assertEqual(summary["latest"]["combined_net_crore"], 3958.91)
        self.assertEqual(summary["series"][0]["date"], "2026-09-23")
        self.assertEqual(summary["series"][0]["combined_net_crore"], 3958.91)
        self.assertIsNone(summary["five_session"])
        self.assertEqual(summary["band"], "unranked")

    def test_institutional_flow_summary_adds_five_session_totals_only_with_coverage(self):
        rows = []
        for offset in range(5):
            session_date = date(2026, 9, 15) + timedelta(days=offset)
            rows.extend(
                [
                    {"date": session_date, "category": "FII/FPI", "buy_crore": 110.0, "sell_crore": 100.0, "net_crore": 10.0},
                    {"date": session_date, "category": "DII", "buy_crore": 105.0, "sell_crore": 100.0, "net_crore": 5.0},
                ]
            )
        summary = calculate_institutional_flow_summary(rows)
        self.assertEqual(summary["five_session"]["fii_fpi_net_crore"], 50.0)
        self.assertEqual(summary["five_session"]["dii_net_crore"], 25.0)
        self.assertEqual(summary["five_session"]["combined_net_crore"], 75.0)
        self.assertEqual(len(summary["series"]), 5)
        self.assertIsNone(summary["twenty_session"])

    def test_nsdl_confirmed_fpi_parser_preserves_equity_routes_and_parentheses(self):
        payload = """
        <div id="rpt"><table>
          <tr><th colspan="8">Daily Trends in FPI Investments on 25-Sep-2026</th></tr>
          <tr><th>Reporting Date</th><th>Asset</th><th>Route</th><th>Buy</th><th>Sell</th><th>Net</th></tr>
          <tr><td rowspan="25">24-Sep-2026</td><td rowspan="3">Equity</td><td>Stock Exchange</td><td>100.00</td><td>120.00</td><td>(20.00)</td></tr>
          <tr><td>Primary market &amp; others</td><td>5.00</td><td>0.00</td><td>5.00</td></tr>
          <tr><td>Sub-total</td><td>105.00</td><td>120.00</td><td>(15.00)</td></tr>
          <tr><td rowspan="3">Debt-General Limit</td><td>Stock Exchange</td><td>1.00</td><td>0.00</td><td>1.00</td></tr>
        </table><table><tr><th>Daily Trends in FPI Derivative Trades on 25-Sep-2026</th></tr></table></div>
        """
        rows = parse_nsdl_confirmed_fpi(payload, today=date(2026, 9, 25))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["investment_route"], "Stock Exchange")
        self.assertEqual(rows[0]["net_investment_crore"], -20.0)
        self.assertEqual(rows[2]["net_investment_crore"], -15.0)

        summary = calculate_confirmed_fpi_summary(rows, today=date(2026, 9, 27))
        self.assertTrue(summary["available"])
        self.assertEqual(summary["as_of_date"], "2026-09-24")
        self.assertEqual(summary["reporting_lag_calendar_days"], 3)
        self.assertEqual(summary["latest"]["subtotal"]["net_investment_crore"], -15.0)
        self.assertIsNone(summary["five_session_net_crore"])

    def test_fred_global_parser_and_summary_preserve_independent_dates(self):
        parsed = parse_fred_global_csv(
            "observation_date,SP500\n2026-09-23,7706.03\n2026-09-24,.\n2026-09-25,7743.41\n",
            series_id="SP500",
            today=date(2026, 9, 28),
            earliest=date(2026, 9, 1),
        )
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[-1]["metric_key"], "sp500")
        self.assertEqual(parsed[-1]["value"], 7743.41)

        rows = []
        specs = {
            "sp500": (7000.0, "Index", "SP500"),
            "us_vix": (15.0, "Index", "VIXCLS"),
            "usd_jpy": (150.0, "JPY per USD", "DEXJPUS"),
            "broad_usd": (115.0, "Index Jan 2006=100", "DTWEXBGS"),
            "brent_crude": (80.0, "USD per barrel", "DCOILBRENTEU"),
        }
        for offset in range(221):
            observation_date = date(2025, 12, 1) + timedelta(days=offset)
            for key, (base, unit, series_id) in specs.items():
                rows.append(
                    {
                        "date": observation_date,
                        "metric_key": key,
                        "value": base + offset,
                        "unit": unit,
                        "source_series": series_id,
                    }
                )
        summary = calculate_global_risk_summary(rows)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["band"], "unranked")
        self.assertIsNotNone(summary["metrics"]["sp500"]["vs_200dma_pct"])
        self.assertEqual(summary["metrics"]["us_vix"]["one_year_percentile"], 100.0)
        self.assertFalse(summary["scoring_enabled"])
        self.assertTrue(
            global_risk_covers_completed_date(
                summary, date(2026, 7, 9)
            )
        )
        self.assertFalse(
            global_risk_covers_completed_date(
                summary, date(2026, 7, 10)
            )
        )

    def test_fred_global_zip_accepts_frequency_grouped_series(self):
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr(
                "daily,_close.csv",
                "observation_date,SP500,VIXCLS\n2026-09-25,7743.41,14.21\n",
            )
            archive.writestr(
                "daily.csv",
                "observation_date,DEXJPUS,DTWEXBGS,DCOILBRENTEU\n"
                "2026-09-25,156.87,119.51,114.89\n",
            )
        rows = parse_fred_global_zip(
            archive_bytes.getvalue(),
            today=date(2026, 9, 28),
            earliest=date(2026, 9, 1),
        )
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["metric_key"] for row in rows}, {
            "sp500", "us_vix", "usd_jpy", "broad_usd", "brent_crude"
        })

    def test_yahoo_global_parser_accepts_completed_daily_closes(self):
        payload = json.dumps(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {"symbol": "^GSPC", "dataGranularity": "1d"},
                            "timestamp": [1790294400, 1790380800, 1790467200],
                            "indicators": {
                                "quote": [{"close": [7743.41, None, 7750.25]}]
                            },
                        }
                    ],
                    "error": None,
                }
            }
        )
        rows = parse_yahoo_global_chart(
            payload,
            symbol="^GSPC",
            today=date(2026, 9, 28),
            earliest=date(2026, 9, 1),
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["metric_key"], "sp500")
        self.assertEqual(rows[-1]["source_series"], "^GSPC")
        self.assertEqual(rows[-1]["value"], 7750.25)

    def test_rbi_macro_parser_preserves_units_and_selects_nearest_ten_year_security(self):
        fixture = """
        <section>Exchange Rates</section>
        <div>INR / 1 USD</div><div>95.9099</div>
        <div>INR / 1 GBP</div><div>127.0295</div>
        <div>INR / 1 EUR</div><div>109.1912</div>
        <div>INR / 100 JPY</div><div>60.6200</div>
        <p>(As at 1.00pm of September 24, 2026)</p><p>(Source : FBIL)</p>
        <section>Government Securities Market</section><p>as on September 23, 2026</p>
        <div>6.36% GS 2031</div><div>6.7278%</div>
        <div>6.94% GS 2036</div><div>7.0408%</div>
        <div>7.06% GS 2041</div><div>7.1978%</div>
        """
        rows = parse_rbi_macro_snapshot(fixture)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["metric_key"], "usd_inr")
        self.assertEqual(rows[3]["unit"], "INR per 100 JPY")
        gsec = rows[-1]
        self.assertEqual(gsec["date"], date(2026, 9, 23))
        self.assertEqual(gsec["value"], 7.0408)
        self.assertIn("GS 2036", gsec["instrument_label"])

    def test_macro_summary_waits_for_history_before_showing_changes(self):
        keys = {
            "usd_inr": (95.0, "INR per USD", "USD/INR"),
            "gbp_inr": (125.0, "INR per GBP", "GBP/INR"),
            "eur_inr": (110.0, "INR per EUR", "EUR/INR"),
            "jpy_100_inr": (62.0, "INR per 100 JPY", "JPY/INR (100 JPY)"),
            "india_10y_gsec_yield": (7.0, "percent yield", "6.94% GS 2036"),
        }
        rows = []
        for offset in range(6):
            for key, (base, unit, label) in keys.items():
                rows.append(
                    {
                        "date": date(2026, 9, 15) + timedelta(days=offset),
                        "metric_key": key,
                        "value": base + offset,
                        "unit": unit,
                        "instrument_label": label,
                    }
                )
        summary = calculate_macro_context_summary(rows)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["band"], "unranked")
        self.assertEqual(summary["metrics"]["usd_inr"]["five_session_change"], 5.26)
        self.assertEqual(summary["metrics"]["india_10y_gsec_yield"]["five_session_change"], 500.0)
        self.assertIsNone(summary["metrics"]["usd_inr"]["twenty_session_change"])
        self.assertTrue(
            macro_context_covers_completed_date(summary, date(2026, 9, 20))
        )
        self.assertFalse(
            macro_context_covers_completed_date(summary, date(2026, 9, 21))
        )

    def test_index_snapshot_preserves_exact_requested_indices(self):
        targets = [
            ("Nifty 50", "NSE:NIFTY 50", "broad_market"),
            ("Nifty Bank", "NSE:NIFTY BANK", "sectoral"),
        ]
        rows, missing = normalize_index_snapshot(
            {
                "status": "success",
                "data": {
                    "NSE:NIFTY 50": {
                        "last_price": 25123.45,
                        "ohlc": {"open": 25000.0, "high": 25200.0, "low": 24950.0, "close": 24980.0},
                    },
                    "NSE:NIFTY BANK": {
                        "last_price": 55123.4,
                        "ohlc": {"open": 55000.0, "high": 55200.0, "low": 54800.0, "close": 54950.0},
                    },
                    "NSE:UNREQUESTED": {
                        "last_price": 1.0,
                        "ohlc": {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                    },
                },
            },
            targets,
        )
        self.assertEqual([row["instrument"] for row in rows], ["NSE:NIFTY 50", "NSE:NIFTY BANK"])
        self.assertEqual([row["display_name"] for row in rows], ["Nifty 50", "Nifty Bank"])
        self.assertEqual(missing, [])

    def test_index_snapshot_reports_missing_or_invalid_rows(self):
        rows, missing = normalize_index_snapshot(
            {
                "status": "success",
                "data": {
                    "NSE:NIFTY 50": {
                        "last_price": float("nan"),
                        "ohlc": {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                    }
                },
            },
            [
                ("Nifty 50", "NSE:NIFTY 50", "broad_market"),
                ("Nifty Bank", "NSE:NIFTY BANK", "sectoral"),
            ],
        )
        self.assertEqual(rows, [])
        self.assertEqual(missing, ["Nifty 50", "Nifty Bank"])

    def test_portfolio_csv_preview_keeps_rows_in_memory_contract(self):
        preview = parse_portfolio_file(
            "holdings.csv",
            b"Symbol,Quantity,Average Cost\nINFY,10,1400\nTCS,5,3200\n",
        )
        self.assertEqual(preview["headers"], ["Symbol", "Quantity", "Average Cost"])
        self.assertEqual(preview["row_count"], 2)
        self.assertEqual(preview["rows"][0]["Symbol"], "INFY")
        self.assertEqual(
            preview["detected_mapping"],
            {
                "symbol": "Symbol",
                "quantity": "Quantity",
                "weight": None,
                "average_cost": "Average Cost",
                "current_value": None,
                "latest_price": None,
                "entry_date": None,
                "invested_value": None,
                "sector": None,
                "name": None,
            },
        )
        self.assertEqual(preview["persistence"], "browser_memory_only")

    def test_portfolio_mapping_recognizes_common_broker_export_columns(self):
        mapping = infer_portfolio_mapping(
            ["Instrument", "Entry Date", "Qty.", "Avg. cost", "Buy Value", "LTP", "Cur. value", "P&L"],
            [
                {"Instrument": "INFY", "Entry Date": "2025-01-01", "Qty.": 10, "Avg. cost": 1400, "Buy Value": 14000, "LTP": 1500, "Cur. value": 15000, "P&L": 1000},
                {"Instrument": "TCS", "Entry Date": "2025-02-01", "Qty.": 5, "Avg. cost": 3200, "Buy Value": 16000, "LTP": 3000, "Cur. value": 15000, "P&L": -1000},
            ],
        )
        self.assertEqual(mapping["symbol"], "Instrument")
        self.assertEqual(mapping["quantity"], "Qty.")
        self.assertEqual(mapping["average_cost"], "Avg. cost")
        self.assertEqual(mapping["current_value"], "Cur. value")
        self.assertEqual(mapping["latest_price"], "LTP")
        self.assertEqual(mapping["entry_date"], "Entry Date")
        self.assertEqual(mapping["invested_value"], "Buy Value")

    def test_portfolio_mapping_prefers_explicit_symbol_over_instrument_name(self):
        mapping = infer_portfolio_mapping(
            ["Instrument", "Symbol", "Qty.", "Avg. cost", "Cur Value"],
            [{"Instrument": "Infosys", "Symbol": "INFY", "Qty.": 10, "Avg. cost": 1400, "Cur Value": 15000}],
        )
        self.assertEqual(mapping["symbol"], "Symbol")
        self.assertEqual(mapping["name"], "Instrument")

    def test_portfolio_csv_skips_broker_report_preamble_and_finds_header(self):
        preview = parse_portfolio_file(
            "broker-holdings.csv",
            b"Holdings statement\nClient ID,AB1234\nGenerated on,07-10-2026\n\nTrading Symbol,Total Qty,Avg Cost Price,Closing Value\nINFY,10,1400,15000\nTCS,5,3200,15000\n",
        )
        self.assertEqual(preview["headers"], ["Trading Symbol", "Total Qty", "Avg Cost Price", "Closing Value"])
        self.assertEqual(preview["row_count"], 2)
        self.assertEqual(preview["detected_mapping"]["symbol"], "Trading Symbol")
        self.assertEqual(preview["detected_mapping"]["quantity"], "Total Qty")
        self.assertEqual(preview["detected_mapping"]["current_value"], "Closing Value")

    def test_mutual_fund_csv_builds_categories_and_concentration(self):
        parsed = parse_mutual_fund_file(
            "funds.csv",
            b"Fund Name,Current Value\nNippon India Large Cap Fund - Direct Plan - Growth,600000\nICICI Prudential Short Term Fund - Direct Plan - Growth,400000\n",
        )
        result = build_mutual_fund_holdings_analysis(parsed["rows"], parsed["mapping"])
        self.assertEqual(result["diversification"]["fund_count"], 2)
        self.assertEqual(result["categories"][0]["category"], "Equity - Large Cap")
        self.assertEqual(result["categories"][0]["weight_pct"], 60.0)
        self.assertEqual(result["funds"][1]["category"], "Debt - Short Duration")
        self.assertEqual(result["diversification"]["effective_fund_count"], 1.92)
        self.assertEqual(result["improvement_contract_version"], "mutual-fund-improvement-review-v1")
        self.assertEqual(len(result["suggestions"]), 3)
        self.assertEqual(
            [item["priority"] for item in result["suggestions"]],
            ["1 · Simplify", "2 · Diversify", "3 · Return efficiency"],
        )
        self.assertIn("not available", result["suggestions"][1]["detail"])
        self.assertIn("does not guarantee", result["suggestions"][2]["detail"])

    def test_mutual_fund_upload_accepts_broker_fund_and_current_value_headers(self):
        parsed = parse_mutual_fund_file(
            "holdings.csv",
            b"Fund,Category,Current Value\nMotilal Oswal Digital India Fund - Regular Plan - Growth,Equity,30651.7\n",
        )
        self.assertEqual(parsed["mapping"]["scheme"], "Fund")
        self.assertEqual(parsed["mapping"]["current_value"], "Current Value")
        result = build_mutual_fund_holdings_analysis(parsed["rows"], parsed["mapping"])
        self.assertEqual(result["funds"][0]["weight_pct"], 100.0)

    def test_universal_import_routes_mutual_fund_statement_to_comparer(self):
        result = parse_universal_portfolio_file(
            "funds.csv",
            b"Fund Name,Current Value\nNippon India Large Cap Fund - Direct Plan - Growth,600000\nICICI Prudential Short Term Fund - Direct Plan - Growth,400000\n",
        )
        self.assertIsNone(result["stock_preview"])
        self.assertEqual(result["classification"]["stocks"], 0)
        self.assertEqual(result["classification"]["mutual_funds"], 2)
        self.assertEqual(len(result["mutual_fund_analysis"]["funds"]), 2)
        self.assertEqual(result["mutual_fund_analysis"]["input_total"], 1000000.0)
        self.assertEqual(result["combined_preview"]["row_count"], 2)
        self.assertTrue(all(row["Symbol"] == "MF" for row in result["combined_preview"]["rows"]))

    def test_universal_import_splits_stocks_and_funds_in_one_table(self):
        result = parse_universal_portfolio_file(
            "mixed.csv",
            (
                "Instrument,Symbol,Quantity,Current Value\n"
                "Infosys,INFY,10,15000\n"
                "Nippon India Large Cap Fund - Direct Plan - Growth,MF,100,25000\n"
            ).encode("utf-8"),
        )
        self.assertEqual(result["classification"]["stocks"], 1)
        self.assertEqual(result["classification"]["mutual_funds"], 1)
        self.assertEqual(result["stock_preview"]["rows"][0]["Symbol"], "INFY")
        self.assertEqual(result["mutual_fund_analysis"]["funds"][0]["weight_pct"], 100.0)
        self.assertEqual(result["combined_preview"]["row_count"], 2)
        self.assertEqual({row["Symbol"] for row in result["combined_preview"]["rows"]}, {"INFY", "MF"})
        combined = build_portfolio_analysis(
            result["combined_preview"]["rows"],
            result["combined_preview"]["detected_mapping"],
            {},
        )
        self.assertEqual(combined["coverage"]["eligible_positions"], 2)
        self.assertEqual(sum(float(row["current_value"]) for row in combined["positions"]), 40000.0)

    def test_mutual_fund_analysis_calculates_pair_overlap_from_uploaded_holdings(self):
        result = build_mutual_fund_holdings_analysis(
            [
                {"Scheme": "Alpha Large Cap Fund", "Weight %": 50, "Category": "Equity - Large Cap"},
                {"Scheme": "Beta Flexi Cap Fund", "Weight %": 50, "Category": "Equity - Flexi Cap"},
            ],
            {"scheme": "Scheme", "weight": "Weight %", "current_value": None, "invested_value": None, "category": "Category"},
            underlying_rows=[
                {"Scheme": "Alpha Large Cap Fund", "Security": "Reliance", "Weight %": 40},
                {"Scheme": "Alpha Large Cap Fund", "Security": "Infosys", "Weight %": 60},
                {"Scheme": "Beta Flexi Cap Fund", "Security": "Reliance", "Weight %": 30},
                {"Scheme": "Beta Flexi Cap Fund", "Security": "HDFC Bank", "Weight %": 70},
            ],
            underlying_mapping={"scheme": "Scheme", "security": "Security", "weight": "Weight %"},
        )
        self.assertEqual(result["overlaps"][0]["overlap_pct"], 30.0)
        self.assertEqual(result["overlaps"][0]["common_holdings"], 1)
        self.assertEqual(result["overlaps"][0]["status"], "complete")
        reliance = next(item for item in result["top_underlying_holdings"] if item["security"] == "Reliance")
        self.assertEqual(reliance["portfolio_weight_pct"], 35.0)
        self.assertEqual(len(result["suggestions"]), 3)
        self.assertIn("30.00%", result["suggestions"][1]["detail"])
        self.assertIn("Alpha Large Cap Fund", result["suggestions"][1]["detail"])

    def test_mutual_fund_improvement_review_always_returns_three_paths_for_one_fund(self):
        result = build_mutual_fund_holdings_analysis(
            [{"Scheme": "Alpha Equity Fund", "Weight %": 100}],
            {"scheme": "Scheme", "weight": "Weight %", "current_value": None, "invested_value": None, "category": None},
        )
        self.assertEqual(len(result["suggestions"]), 3)
        self.assertIn("already compact", result["suggestions"][0]["detail"])
        self.assertIn("no pairwise redundancy", result["suggestions"][1]["detail"])
        combined = " ".join(item["detail"].lower() for item in result["suggestions"])
        self.assertNotIn("guaranteed return", combined)

    def test_mutual_fund_analysis_uses_the_most_complete_available_weight_basis(self):
        result = build_mutual_fund_holdings_analysis(
            [
                {"Scheme": "Alpha Equity Fund", "Current Value": "", "Weight %": 70},
                {"Scheme": "Beta Debt Fund", "Current Value": 30000, "Weight %": 30},
            ],
            {"scheme": "Scheme", "current_value": "Current Value", "invested_value": None, "weight": "Weight %", "category": None},
        )
        self.assertEqual(result["weight_basis"], "weight")
        self.assertEqual([fund["weight_pct"] for fund in result["funds"]], [70.0, 30.0])

    def test_mutual_fund_performance_uses_one_common_window_for_reviewed_schemes(self):
        sessions = [date(2026, 1, 1) + timedelta(days=index) for index in range(130)]
        result = build_mutual_fund_performance_comparison(
            [
                {"scheme": "Nippon India Large Cap Fund - Direct Plan - Growth", "category": "Equity - Large Cap"},
                {"scheme": "ICICI Prudential Short Term Fund - Direct Plan - Growth", "category": "Debt - Short Duration"},
                {"scheme": "Unreviewed Opportunity Fund", "category": "Equity"},
            ],
            {
                "118632": [
                    {"date": session, "close": 100 + index * (20 / 129)}
                    for index, session in enumerate(sessions)
                ],
                "120754": [
                    {"date": session, "close": 100 + index * (5 / 129)}
                    for index, session in enumerate(sessions)
                ],
            },
        )
        self.assertEqual(result["common_observations"], 130)
        self.assertEqual(result["start_date"], sessions[0].isoformat())
        self.assertEqual(result["end_date"], sessions[-1].isoformat())
        self.assertEqual(result["matched_funds"], 2)
        large_cap = next(row for row in result["rows"] if row.get("scheme_code") == "118632")
        self.assertEqual(large_cap["aligned_return_pct"], 20.0)
        self.assertEqual(large_cap["status"], "ready")
        unreviewed = next(row for row in result["rows"] if row["scheme"] == "Unreviewed Opportunity Fund")
        self.assertEqual(unreviewed["status"], "exact_scheme_not_reviewed")

    def test_mutual_fund_performance_withholds_metrics_without_common_history(self):
        result = build_mutual_fund_performance_comparison(
            [
                {"scheme": "Nippon India Large Cap Fund - Direct Plan - Growth", "category": "Equity - Large Cap"},
                {"scheme": "ICICI Prudential Short Term Fund - Direct Plan - Growth", "category": "Debt - Short Duration"},
            ],
            {
                "118632": [{"date": date(2026, 1, 2), "close": 100.0}],
                "120754": [{"date": date(2026, 1, 3), "close": 100.0}],
            },
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "insufficient_common_history")
        self.assertTrue(all(row["status"] == "insufficient_common_history" for row in result["rows"]))

    def test_amfi_catalogue_keeps_only_current_direct_growth_and_versions_categories(self):
        catalogue = parse_amfi_scheme_catalogue_text("\n".join((
            "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date",
            "",
            "Open Ended Schemes(Equity Scheme - Large Cap Fund)",
            "Nippon India Mutual Fund",
            "118632;INF204K01UN9;-;Nippon India Large Cap Fund;Direct Plan;Growth Option;94.5718;12-Oct-2026",
            "118631;INF204K01UM1;-;Nippon India Large Cap Fund;Regular Plan;Growth Option;80.0000;12-Oct-2026",
            "118630;INF204K01UL3;-;Nippon India Large Cap Fund;Direct Plan;IDCW Option;40.0000;12-Oct-2026",
            "Open Ended Schemes(Debt Scheme - Short Duration Fund)",
            "ICICI Prudential Mutual Fund",
            "120754;INF109K013N3;-;ICICI Prudential Short Term Fund;Direct Plan;Growth;70.6747;12-Oct-2026",
            "999999;INF000000001;-;Old Direct Fund;Direct Plan;Growth;10.0000;01-Jan-2025",
        )))
        self.assertEqual(catalogue["catalogue_as_of"], "2026-10-12")
        self.assertEqual(catalogue["current_direct_growth_schemes"], 2)
        self.assertEqual(catalogue["stale_direct_growth_rows_excluded"], 1)
        self.assertEqual(catalogue["rows"][0]["category_schema_version"], "amfi-category-map-v1")
        categories = {row["scheme_code"]: row["category"] for row in catalogue["rows"]}
        self.assertEqual(categories["118632"], "Equity - Large Cap")
        self.assertEqual(categories["120754"], "Debt - Short Duration")

    def test_amfi_catalogue_matching_rejects_plan_substitution_and_exposes_ambiguity(self):
        rows = [
            {"scheme_code": "1", "scheme_base": "alpha equity fund"},
            {"scheme_code": "2", "scheme_base": "alpha equity fund"},
            {"scheme_code": "3", "scheme_base": "beta debt fund"},
        ]
        self.assertEqual(
            match_mutual_fund_scheme_catalogue("Alpha Equity Fund - Direct Plan - Growth", rows)["status"],
            "ambiguous_direct_growth_match",
        )
        self.assertEqual(
            match_mutual_fund_scheme_catalogue("Beta Debt Fund - Regular Plan - Growth", rows)["status"],
            "non_direct_growth_input",
        )
        match = match_mutual_fund_scheme_catalogue("Beta Debt Fund", rows)
        self.assertEqual(match["status"], "unique_direct_growth_match")
        self.assertEqual(match["match"]["scheme_code"], "3")

    def test_amfi_catalogue_classification_preserves_uploaded_category_and_audit_fields(self):
        catalogue = {
            "category_schema_version": "amfi-category-map-v1",
            "catalogue_as_of": "2026-10-12",
            "current_direct_growth_schemes": 1,
            "stale_direct_growth_rows_excluded": 4,
            "rows": [{
                "scheme_code": "118632",
                "scheme_base": "nippon india large cap fund",
                "official_name": "Nippon India Large Cap Fund - Direct Plan - Growth Option",
                "amc_name": "Nippon India Mutual Fund",
                "plan": "Direct Plan",
                "option": "Growth Option",
                "category": "Equity - Large Cap",
                "category_raw": "Equity Scheme - Large Cap Fund",
                "nav": 94.5718,
                "nav_date": date(2026, 10, 12),
            }],
        }
        result = build_mutual_fund_catalogue_classification(
            [{
                "scheme": "Nippon India Large Cap Fund - Direct Plan - Growth",
                "category": "My Equity Bucket",
                "category_source": "uploaded",
                "weight_pct": 100,
            }],
            catalogue,
        )
        self.assertEqual(result["matched_funds"], 1)
        self.assertEqual(result["rows"][0]["status"], "reviewed_exact_match")
        self.assertEqual(result["rows"][0]["uploaded_category"], "My Equity Bucket")
        self.assertEqual(result["rows"][0]["amfi_category_raw"], "Equity Scheme - Large Cap Fund")
        self.assertEqual(result["category_schema_version"], "amfi-category-map-v1")

    def test_underlying_scheme_matching_accepts_regular_growth_without_changing_nav_contract(self):
        rows = [{
            "scheme_code": "118632",
            "scheme_name": "Nippon India Large Cap Fund",
            "scheme_base": "nippon india large cap fund",
            "amc_name": "Nippon India Mutual Fund",
        }]
        resolved = match_mutual_fund_underlying_scheme_catalogue(
            "Nippon India Large Cap Fund - Regular Plan - Growth Option",
            rows,
        )
        self.assertEqual(resolved["status"], "regular_plan_underlying_match")
        self.assertEqual(resolved["match"]["scheme_code"], "118632")
        self.assertEqual(
            match_mutual_fund_scheme_catalogue(
                "Nippon India Large Cap Fund - Regular Plan - Growth Option",
                rows,
            )["status"],
            "non_direct_growth_input",
        )

    def test_underlying_scheme_matching_collapses_duplicate_plan_rows(self):
        rows = [
            {"scheme_code": "152964", "scheme_name": "Motilal Oswal Digital India Fund", "scheme_base": "motilal oswal digital india fund", "amc_name": "Motilal Oswal Mutual Fund"},
            {"scheme_code": "152965", "scheme_name": "Motilal Oswal Digital India Fund", "scheme_base": "motilal oswal digital india fund", "amc_name": "Motilal Oswal Mutual Fund"},
        ]
        resolved = match_mutual_fund_underlying_scheme_catalogue(
            "Motilal Oswal Digital India Fund - Regular Plan - Growth",
            rows,
        )
        self.assertEqual(resolved["status"], "regular_plan_underlying_match")
        self.assertEqual(resolved["match"]["scheme_code"], "152964")

    def test_nippon_disclosure_link_and_workbook_parser_preserve_isin_sector_and_date(self):
        links = parse_nippon_portfolio_disclosure_links(
            '<a href="/InvestorServices/FactsheetsDocuments/NIMF-MONTHLY-PORTFOLIO-31-Aug-26.xls">old</a>'
            '<a href="/InvestorServices/FactsheetsDocuments/NIMF-MONTHLY-PORTFOLIO-30-Sep-26.xls">new</a>'
        )
        self.assertEqual(links[0]["portfolio_date"], date(2026, 9, 30))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="LC" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>RLMF</t></is></c><c r="B1" t="inlineStr"><is><t>Nippon India Large Cap Fund (An open-ended equity scheme)</t></is></c></row>'
                '<row r="2"><c r="B2" t="inlineStr"><is><t>Monthly Portfolio Statement as on September 30, 2026</t></is></c></row>'
                '<row r="4"><c r="B4" t="inlineStr"><is><t>ISIN</t></is></c><c r="C4" t="inlineStr"><is><t>Name of the Instrument</t></is></c><c r="D4" t="inlineStr"><is><t>Industry / Rating</t></is></c><c r="G4" t="inlineStr"><is><t>% to NAV</t></is></c></row>'
                '<row r="5"><c r="B5" t="inlineStr"><is><t>INE002A01018</t></is></c><c r="C5" t="inlineStr"><is><t>Reliance Industries Limited</t></is></c><c r="D5" t="inlineStr"><is><t>Petroleum Products</t></is></c><c r="G5"><v>0.085</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_nippon_portfolio_workbook(payload.getvalue(), source_url=str(links[0]["url"]))
        scheme = parsed["schemes"][0]
        self.assertEqual(scheme["portfolio_date"], "2026-09-30")
        self.assertEqual(scheme["coverage_pct"], 8.5)
        self.assertEqual(scheme["holdings"][0]["isin"], "INE002A01018")
        self.assertEqual(scheme["holdings"][0]["sector"], "Petroleum Products")

    def test_axis_catalogue_and_consolidated_workbook_preserve_complete_holdings(self):
        links = parse_axis_portfolio_document_catalogue({
            "status": "success",
            "data": {"documentList": [
                {
                    "docuementURL": "https://www.axismf.com/1/5/464/560/monthly-axis-value.xlsx",
                    "documentName": "Monthly Portfolio - Axis Value Fund - 30 September 2026",
                    "documentPostedDate": "2026-09-30",
                },
                {
                    "docuementURL": "https://www.axismf.com/1/5/464/560/Monthly_Portfolio_30_09_2026.xlsx",
                    "documentName": "Monthly Portfolio 30-09-2026",
                    "documentPostedDate": "2026-09-30",
                },
                {
                    "docuementURL": "https://example.com/1/Monthly_Portfolio_31_08_2026.xlsx",
                    "documentName": "Monthly Portfolio 31-08-2026",
                    "documentPostedDate": "2026-08-31",
                },
            ]},
        })
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["portfolio_date"], date(2026, 9, 30))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Index" sheetId="1" r:id="rId1"/><sheet name="AXISVF" sheetId="2" r:id="rId2"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/><Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Sr No.</t></is></c><c r="B1" t="inlineStr"><is><t>Short Name</t></is></c><c r="C1" t="inlineStr"><is><t>Scheme Name</t></is></c></row></sheetData></worksheet>',
            )
            archive.writestr(
                "xl/worksheets/sheet2.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>AXISVF</t></is></c><c r="B1" t="inlineStr"><is><t>Axis Value Fund</t></is></c></row>'
                '<row r="3"><c r="B3" t="inlineStr"><is><t>Monthly Portfolio Statement as on September 30, 2026</t></is></c></row>'
                '<row r="4"><c r="B4" t="inlineStr"><is><t>Name of the Instrument</t></is></c><c r="C4" t="inlineStr"><is><t>ISIN</t></is></c><c r="D4" t="inlineStr"><is><t>Industry</t></is></c><c r="G4" t="inlineStr"><is><t>% to Net Assets</t></is></c></row>'
                '<row r="5"><c r="B5" t="inlineStr"><is><t>ICICI Bank Limited</t></is></c><c r="C5" t="inlineStr"><is><t>INE090A01021</t></is></c><c r="D5" t="inlineStr"><is><t>Banks</t></is></c><c r="G5"><v>0.0514</v></c></row>'
                '<row r="6"><c r="B6" t="inlineStr"><is><t>Reliance Industries Limited</t></is></c><c r="C6" t="inlineStr"><is><t>INE002A01018</t></is></c><c r="D6" t="inlineStr"><is><t>Petroleum Products</t></is></c><c r="G6"><v>0.0338</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_axis_portfolio_workbook(payload.getvalue(), source_url=str(links[0]["url"]))
        scheme = parsed["schemes"][0]
        self.assertEqual(parsed["provider"], "axis_mutual_fund")
        self.assertEqual(scheme["scheme_name"], "Axis Value Fund")
        self.assertEqual(scheme["portfolio_date"], "2026-09-30")
        self.assertEqual(scheme["coverage_pct"], 8.52)
        self.assertEqual(scheme["holdings"][0]["isin"], "INE090A01021")
        self.assertEqual(scheme["holdings"][0]["sector"], "Banks")

    def test_icici_archive_selects_requested_workbooks_and_preserves_nav_weights(self):
        def workbook(scheme_name, isin, security, sector, weight):
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr(
                    "xl/workbook.xml",
                    '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="PORT" sheetId="1" r:id="rId1"/></sheets></workbook>',
                )
                archive.writestr(
                    "xl/_rels/workbook.xml.rels",
                    '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
                )
                archive.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                    '<row r="1"><c r="B1" t="inlineStr"><is><t>ICICI Prudential Mutual Fund</t></is></c></row>'
                    f'<row r="2"><c r="B2" t="inlineStr"><is><t>{scheme_name}</t></is></c></row>'
                    '<row r="3"><c r="B3" t="inlineStr"><is><t>Portfolio as on Sep 30,2026</t></is></c></row>'
                    '<row r="4"><c r="B4" t="inlineStr"><is><t>Company/Issuer/Instrument Name</t></is></c><c r="C4" t="inlineStr"><is><t>ISIN</t></is></c><c r="E4" t="inlineStr"><is><t>Industry/Rating</t></is></c><c r="H4" t="inlineStr"><is><t>% to Nav</t></is></c></row>'
                    f'<row r="5"><c r="B5" t="inlineStr"><is><t>{security}</t></is></c><c r="C5" t="inlineStr"><is><t>{isin}</t></is></c><c r="E5" t="inlineStr"><is><t>{sector}</t></is></c><c r="H5"><v>{weight}</v></c></row>'
                    '</sheetData></worksheet>',
                )
            return payload.getvalue()

        archive_payload = io.BytesIO()
        with zipfile.ZipFile(archive_payload, "w") as archive:
            archive.writestr(
                "ICICI Prudential Active Momentum Fund.xlsx",
                workbook("ICICI Prudential Active Momentum Fund", "INE238A01034", "Axis Bank Ltd.", "Banks", 0.030038),
            )
            archive.writestr(
                "ICICI Prudential Retirement Fund - Pure Equity Plan.xlsx",
                workbook("ICICI Prudential Retirement Fund - Pure Equity Plan", "INE040A01034", "HDFC Bank Ltd.", "Banks", 0.049889),
            )
        parsed = parse_icici_portfolio_archive(
            archive_payload.getvalue(),
            source_name="Monthly-Portfolio-Disclosure-September-2026.zip",
            scheme_names=["ICICI Prudential Active Momentum Fund - Regular Plan - Growth"],
        )
        self.assertEqual(parsed["provider"], "icici_prudential")
        self.assertEqual(parsed["portfolio_date"], "2026-09-30")
        self.assertEqual(parsed["source_archive"], "Monthly-Portfolio-Disclosure-September-2026.zip")
        self.assertEqual(len(parsed["schemes"]), 1)
        scheme = parsed["schemes"][0]
        self.assertEqual(scheme["scheme_name"], "ICICI Prudential Active Momentum Fund")
        self.assertEqual(scheme["coverage_pct"], 3.0)
        self.assertEqual(scheme["holdings"][0]["isin"], "INE238A01034")
        self.assertEqual(scheme["holdings"][0]["sector"], "Banks")

    def test_sbi_disclosure_link_and_workbook_parser_select_requested_scheme(self):
        links = parse_sbi_portfolio_disclosure_links(
            '<a href="/docs/default-source/scheme-portfolios/all-schemes-monthly-portfolio---as-on-31st-august-2026.xlsx?sfvrsn=old">old</a>'
            '<a href="/docs/default-source/scheme-portfolios/all-schemes-monthly-portfolio---as-on-30th-september-2026.xlsx?sfvrsn=new">new</a>'
        )
        self.assertEqual(links[0]["portfolio_date"], date(2026, 9, 30))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Index" sheetId="1" r:id="rId1"/><sheet name="SAOF" sheetId="2" r:id="rId2"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/><Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Index</t></is></c></row></sheetData></worksheet>',
            )
            archive.writestr(
                "xl/worksheets/sheet2.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="3"><c r="C3" t="inlineStr"><is><t>SCHEME NAME :</t></is></c><c r="D3" t="inlineStr"><is><t>SBI Arbitrage Fund (Erstwhile known as SBI Arbitrage Opportunities Fund)</t></is></c></row>'
                '<row r="4"><c r="C4" t="inlineStr"><is><t>PORTFOLIO STATEMENT AS ON :</t></is></c><c r="D4"><v>46295</v></c></row>'
                '<row r="6"><c r="C6" t="inlineStr"><is><t>Name of the Instrument / Issuer</t></is></c><c r="D6" t="inlineStr"><is><t>ISIN</t></is></c><c r="E6" t="inlineStr"><is><t>Rating / Industry^</t></is></c><c r="H6" t="inlineStr"><is><t>% to AUM</t></is></c></row>'
                '<row r="11"><c r="C11" t="inlineStr"><is><t>Reliance Industries Ltd.</t></is></c><c r="D11" t="inlineStr"><is><t>INE002A01018</t></is></c><c r="E11" t="inlineStr"><is><t>Petroleum Products</t></is></c><c r="H11"><v>5.58</v></c></row>'
                '<row r="12"><c r="C12" t="inlineStr"><is><t>NIFTY FUTURES</t></is></c><c r="H12"><v>-4.9</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_sbi_portfolio_workbook(
            payload.getvalue(),
            source_url=str(links[0]["url"]),
            scheme_names=["SBI Arbitrage Fund - Regular Plan - Growth"],
        )
        self.assertEqual(parsed["provider"], "sbi_mutual_fund")
        self.assertEqual(parsed["portfolio_date"], "2026-09-30")
        self.assertEqual(len(parsed["schemes"]), 1)
        scheme = parsed["schemes"][0]
        self.assertEqual(scheme["scheme_name"], "SBI Arbitrage Fund")
        self.assertEqual(scheme["coverage_pct"], 5.58)
        self.assertEqual(scheme["holdings"][0]["isin"], "INE002A01018")
        self.assertEqual(scheme["holdings"][0]["sector"], "Petroleum Products")

    def test_whiteoak_catalogue_and_workbook_parser_capture_positive_isin_holdings(self):
        candidates = parse_whiteoak_portfolio_catalogue({
            "data": [
                {
                    "attributes": {
                        "period": "Monthly",
                        "scheme_name": "WhiteOak Capital Multi Asset Allocation Fund",
                        "doc_name": "WhiteOak Capital Multi Asset Allocation Fund Monthly Portfolio Disclosure - 30th September2026",
                        "doc_file": {"data": {"attributes": {"url": "https://content.whiteoakamc.com/whiteoak-multi-asset-september-2026.xlsx"}}},
                    }
                },
                {
                    "attributes": {
                        "period": "Fortnightly",
                        "scheme_name": "WhiteOak Capital Multi Asset Allocation Fund",
                        "doc_name": "WhiteOak Capital Multi Asset Allocation Fund Portfolio - 15th September2026",
                        "doc_file": {"data": {"attributes": {"url": "https://content.whiteoakamc.com/ignored.xlsx"}}},
                    }
                },
            ]
        })
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["portfolio_date"], date(2026, 9, 30))

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="WOMAF" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>WhiteOak Capital Multi Asset Allocation Fund</t></is></c></row>'
                '<row r="3"><c r="A3" t="inlineStr"><is><t>Monthly Portfolio Statement as on September 30, 2026</t></is></c></row>'
                '<row r="4"><c r="A4" t="inlineStr"><is><t>Name of the Instrument</t></is></c><c r="B4" t="inlineStr"><is><t>ISIN</t></is></c><c r="C4" t="inlineStr"><is><t>Industry / Rating</t></is></c><c r="F4" t="inlineStr"><is><t>% to Net Assets</t></is></c></row>'
                '<row r="5"><c r="A5" t="inlineStr"><is><t>ICICI Bank Limited</t></is></c><c r="B5" t="inlineStr"><is><t>INE090A01021</t></is></c><c r="C5" t="inlineStr"><is><t>Banks</t></is></c><c r="F5"><v>0.0289</v></c></row>'
                '<row r="6"><c r="A6" t="inlineStr"><is><t>Long FUTCOM_GOLD</t></is></c><c r="F6"><v>0.0605</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_whiteoak_portfolio_workbook(
            payload.getvalue(),
            scheme_name_hint="WhiteOak Capital Multi Asset Allocation Fund",
            source_url=str(candidates[0]["url"]),
        )
        self.assertEqual(parsed["portfolio_date"], "2026-09-30")
        self.assertEqual(parsed["coverage_pct"], 2.89)
        self.assertEqual(len(parsed["holdings"]), 1)
        self.assertEqual(parsed["holdings"][0]["isin"], "INE090A01021")
        self.assertEqual(parsed["holdings"][0]["sector"], "Banks")

    def test_edelweiss_catalogue_and_workbook_parser_capture_fund_of_fund_holdings(self):
        candidates = parse_edelweiss_portfolio_catalogue({
            "data": {
                "years": [{
                    "year": 2026,
                    "months": [{
                        "month": "September 2026",
                        "documents": [{
                            "schemeName": "Edelweiss Multi Asset Omni Fund of Fund",
                            "fileUrl": "https://www.edelweissmf.com/Files/MF/Statutory/Portfolio/Edelweiss_Multi_Asset_Omni_30_September_2026.xlsx",
                        }],
                    }],
                }],
            }
        })
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["portfolio_date"], date(2026, 9, 30))

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Omni FoF" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>Edelweiss Multi Asset Omni Fund of Fund</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Monthly Portfolio Statement as on 30 September 2026</t></is></c></row>'
                '<row r="4"><c r="A4" t="inlineStr"><is><t>Name of the Instrument</t></is></c><c r="B4" t="inlineStr"><is><t>ISIN</t></is></c><c r="C4" t="inlineStr"><is><t>Industry / Rating</t></is></c><c r="F4" t="inlineStr"><is><t>% to Net Assets</t></is></c></row>'
                '<row r="5"><c r="A5" t="inlineStr"><is><t>Edelweiss Nifty LargeMidcap 250 ETF</t></is></c><c r="B5" t="inlineStr"><is><t>INF754K01QX0</t></is></c><c r="C5" t="inlineStr"><is><t>Mutual Fund Units</t></is></c><c r="F5"><v>29.9</v></c></row>'
                '<row r="6"><c r="A6" t="inlineStr"><is><t>TREPS</t></is></c><c r="F6"><v>2.1</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_edelweiss_portfolio_workbook(
            payload.getvalue(),
            source_url=str(candidates[0]["url"]),
            scheme_names=["Edelweiss Multi Asset Omni Fund of Fund - Regular Plan - Growth"],
        )
        self.assertEqual(parsed["provider"], "edelweiss_mutual_fund")
        self.assertEqual(parsed["portfolio_date"], "2026-09-30")
        self.assertEqual(parsed["schemes"][0]["coverage_pct"], 29.9)
        self.assertEqual(parsed["schemes"][0]["holdings"][0]["isin"], "INF754K01QX0")
        self.assertEqual(parsed["schemes"][0]["holdings"][0]["sector"], "Mutual Fund Units")

    def test_ppfas_links_and_workbook_parser_capture_positive_isin_holdings(self):
        links = parse_ppfas_portfolio_disclosure_links(
            '<a href="/downloads/portfolio-disclosure/2026/PPFAS_Monthly_Portfolio_Report_September_30_2026.xls?07102026=">Consolidated</a>'
            '<a href="/downloads/portfolio-disclosure/2026/PPTSF_PPFAS_Monthly_Portfolio_Report_September_30_2026.xlsx?07102026=">PPTSF</a>'
            '<a href="https://example.com/PPFAS_Monthly_Portfolio_Report_October_31_2026.xls">Other host</a>'
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["portfolio_date"], date(2026, 9, 30))

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="PPTSF" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="B1" t="inlineStr"><is><t>Parag Parikh ELSS Tax Saver Fund (An open ended equity linked savings scheme)</t></is></c></row>'
                '<row r="3"><c r="B3" t="inlineStr"><is><t>Monthly Portfolio Statement as on September 30, 2026</t></is></c></row>'
                '<row r="4"><c r="B4" t="inlineStr"><is><t>Name of the Instrument</t></is></c><c r="C4" t="inlineStr"><is><t>ISIN</t></is></c><c r="D4" t="inlineStr"><is><t>Industry / Rating</t></is></c><c r="G4" t="inlineStr"><is><t>% to Net Assets</t></is></c></row>'
                '<row r="5"><c r="B5" t="inlineStr"><is><t>HDFC Bank Limited</t></is></c><c r="C5" t="inlineStr"><is><t>INE040A01034</t></is></c><c r="D5" t="inlineStr"><is><t>Banks</t></is></c><c r="G5"><v>0.0757</v></c></row>'
                '<row r="6"><c r="B6" t="inlineStr"><is><t>Cash and cash equivalents</t></is></c><c r="G6"><v>0.02</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_ppfas_portfolio_workbook(
            payload.getvalue(),
            source_url=str(links[0]["url"]),
            scheme_names=["Parag Parikh ELSS Tax Saver Fund - Regular Plan - Growth"],
        )
        self.assertEqual(parsed["provider"], "ppfas_mutual_fund")
        self.assertEqual(parsed["portfolio_date"], "2026-09-30")
        self.assertEqual(len(parsed["schemes"]), 1)
        self.assertEqual(parsed["schemes"][0]["coverage_pct"], 7.57)
        self.assertEqual(parsed["schemes"][0]["holdings"][0]["isin"], "INE040A01034")
        self.assertEqual(parsed["schemes"][0]["holdings"][0]["sector"], "Banks")

    def test_true_diversification_joins_regular_plans_and_reports_repeated_exposure(self):
        catalogue = {
            "rows": [
                {"scheme_code": "1", "scheme_name": "Nippon India Large Cap Fund", "scheme_base": "nippon india large cap fund", "amc_name": "Nippon India Mutual Fund"},
                {"scheme_code": "2", "scheme_name": "Nippon India Growth Mid Cap Fund", "scheme_base": "nippon india growth mid cap fund", "amc_name": "Nippon India Mutual Fund"},
            ]
        }
        package = {
            "provider": "nippon_india",
            "source_url": "https://mf.nipponindiaim.com/example.xls",
            "portfolio_date": "2026-09-30",
            "schemes": [
                {"scheme_name": "Nippon India Large Cap Fund", "scheme_keys": ["nippon india large cap fund", "nippon large cap fund"], "portfolio_date": "2026-09-30", "coverage_pct": 100, "holdings": [
                    {"isin": "INE002A01018", "security": "Reliance Industries", "sector": "Energy", "weight_pct": 60},
                    {"isin": "INE009A01021", "security": "Infosys", "sector": "IT", "weight_pct": 40},
                ]},
                {"scheme_name": "Nippon India Growth Mid Cap Fund", "scheme_keys": ["nippon india mid cap fund", "nippon mid cap fund"], "portfolio_date": "2026-09-30", "coverage_pct": 100, "holdings": [
                    {"isin": "INE002A01018", "security": "Reliance Industries", "sector": "Energy", "weight_pct": 20},
                    {"isin": "INE040A01034", "security": "HDFC Bank", "sector": "Banks", "weight_pct": 80},
                ]},
            ],
        }
        result = build_mutual_fund_true_diversification(
            [
                {"scheme": "Nippon India Large Cap Fund - Regular Plan - Growth", "category": "Equity - Large Cap", "weight_pct": 50},
                {"scheme": "Nippon India Growth Mid Cap Fund - Direct Plan - Growth", "category": "Equity - Mid Cap", "weight_pct": 50},
            ],
            catalogue,
            {"nippon_india": package},
        )
        self.assertEqual(result["holdings_disclosure"]["funds_with_official_holdings"], 2)
        self.assertEqual(result["overlaps"][0]["overlap_pct"], 20.0)
        self.assertEqual(result["repeated_holdings"][0]["isin"], "INE002A01018")
        self.assertEqual(result["repeated_holdings"][0]["fund_count"], 2)
        self.assertEqual(result["diversification"]["repeated_lookthrough_pct"], 40.0)
        self.assertEqual(result["market_cap_allocation"][0]["bucket"], "Large Cap")

    def test_amfi_market_cap_workbook_and_isin_lookthrough_classification(self):
        rows = []
        for rank in range(1, 253):
            category = "Large Cap" if rank <= 100 else "Mid Cap" if rank <= 250 else "Small Cap"
            isin = f"INE{rank:09d}"
            rows.append(
                f'<row r="{rank + 2}"><c r="A{rank + 2}"><v>{rank}</v></c>'
                f'<c r="B{rank + 2}" t="inlineStr"><is><t>Company {rank}</t></is></c>'
                f'<c r="C{rank + 2}" t="inlineStr"><is><t>{isin}</t></is></c>'
                f'<c r="J{rank + 2}"><v>{1000000 - rank}</v></c>'
                f'<c r="K{rank + 2}" t="inlineStr"><is><t>{category}</t></is></c></row>'
            )
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="FINAL" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>Average Market Capitalization of listed companies during the six months ended 30 June 2026</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Sr. No.</t></is></c><c r="B2" t="inlineStr"><is><t>Company name</t></is></c><c r="C2" t="inlineStr"><is><t>ISIN</t></is></c><c r="J2" t="inlineStr"><is><t>Average of All Exchanges (Rs. Cr.)</t></is></c><c r="K2" t="inlineStr"><is><t>Categorization as per SEBI Circular dated Oct 6, 2017</t></is></c></row>'
                + "".join(rows)
                + '</sheetData></worksheet>',
            )
        classification = parse_amfi_market_cap_workbook(payload.getvalue())
        self.assertEqual(classification["companies"], 252)
        self.assertEqual(classification["category_counts"], {"Large Cap": 100, "Mid Cap": 150, "Small Cap": 2})
        result = build_mutual_fund_holdings_analysis(
            [{"Fund": "Example Equity Fund", "Value": 100}],
            {"scheme": "Fund", "current_value": "Value", "invested_value": None, "weight": None, "category": None},
            underlying_rows=[
                {"Scheme": "Example Equity Fund", "Security": "Large", "ISIN": "INE000000001", "Weight": 50},
                {"Scheme": "Example Equity Fund", "Security": "Mid", "ISIN": "INE000000101", "Weight": 30},
                {"Scheme": "Example Equity Fund", "Security": "Unknown", "ISIN": "US0000000001", "Weight": 20},
            ],
            underlying_mapping={"scheme": "Scheme", "security": "Security", "isin": "ISIN", "sector": None, "weight": "Weight"},
            market_cap_classification=classification,
        )
        self.assertEqual(
            [(row["bucket"], row["portfolio_weight_pct"]) for row in result["market_cap_allocation"]],
            [("Large Cap", 50.0), ("Mid Cap", 30.0), ("Unclassified / not captured", 20.0)],
        )
        self.assertEqual(result["market_cap_evidence"]["classified_securities"], 2)
        self.assertEqual(result["market_cap_evidence"]["classified_portfolio_weight_pct"], 80.0)

    def test_motilal_page_and_workbook_parser_preserve_official_holdings(self):
        page_url = "https://www.motilaloswalmf.com/mutual-funds/motilal-oswal-digital-india-fund"
        workbook_url = parse_motilal_portfolio_page(
            '<p><strong>portfolioUrl:</strong> /content/dam/motilal-mf/sheets/fund-csvs/Month_End_Portfolio_September_2026/YO58.xlsx</p>',
            page_url=page_url,
        )
        self.assertEqual(
            workbook_url,
            "https://www.motilaloswalmf.com/content/dam/motilal-mf/sheets/fund-csvs/Month_End_Portfolio_September_2026/YO58.xlsx",
        )
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="YO58" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>MONTHLY PORTFOLIO STATEMENT AS ON SEPTEMBER 30, 2026</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Motilal Oswal Digital India Fund</t></is></c></row>'
                '<row r="3"><c r="A3" t="inlineStr"><is><t>Sr. No.</t></is></c><c r="B3" t="inlineStr"><is><t>Name of the Instrument</t></is></c><c r="C3" t="inlineStr"><is><t>ISIN</t></is></c><c r="D3" t="inlineStr"><is><t>Industry*</t></is></c><c r="G3" t="inlineStr"><is><t>% to Net Assets</t></is></c></row>'
                '<row r="4"><c r="A4"><v>1</v></c><c r="B4" t="inlineStr"><is><t>Eternal Limited</t></is></c><c r="C4" t="inlineStr"><is><t>INE758T01015</t></is></c><c r="D4" t="inlineStr"><is><t>Retailing</t></is></c><c r="G4"><v>6.37</v></c></row>'
                '</sheetData></worksheet>',
            )
        parsed = parse_motilal_portfolio_workbook(
            payload.getvalue(),
            scheme_name="Motilal Oswal Digital India Fund",
            source_url=workbook_url,
            source_page_url=page_url,
        )
        scheme = parsed["schemes"][0]
        self.assertEqual(scheme["portfolio_date"], "2026-09-30")
        self.assertEqual(scheme["coverage_pct"], 6.37)
        self.assertEqual(scheme["holdings"][0]["isin"], "INE758T01015")
        self.assertEqual(scheme["holdings"][0]["sector"], "Retailing")

    def test_mutual_fund_xlsx_reads_optional_underlying_holdings_sheet(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Funds" sheetId="1" r:id="rId1"/><sheet name="Underlying Holdings" sheetId="2" r:id="rId2"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/><Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Scheme</t></is></c><c r="B1" t="inlineStr"><is><t>Current Value</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Alpha Fund</t></is></c><c r="B2"><v>100000</v></c></row></sheetData></worksheet>',
            )
            archive.writestr(
                "xl/worksheets/sheet2.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Scheme</t></is></c><c r="B1" t="inlineStr"><is><t>Security</t></is></c><c r="C1" t="inlineStr"><is><t>Weight %</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Alpha Fund</t></is></c><c r="B2" t="inlineStr"><is><t>Infosys</t></is></c><c r="C2"><v>8.5</v></c></row></sheetData></worksheet>',
            )
        parsed = parse_mutual_fund_file("funds.xlsx", payload.getvalue())
        self.assertEqual(parsed["sheet_name"], "Funds")
        self.assertEqual(parsed["underlying_sheet_name"], "Underlying Holdings")
        self.assertEqual(parsed["underlying_rows"][0]["Security"], "Infosys")

    def test_portfolio_xlsx_preview_reads_first_sheet_without_dependency(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Holdings" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Symbol</t></is></c><c r="B1" t="inlineStr"><is><t>Quantity</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>INFY</t></is></c><c r="B2"><v>12</v></c></row></sheetData></worksheet>',
            )
        preview = parse_portfolio_file("holdings.xlsx", payload.getvalue())
        self.assertEqual(preview["sheet_name"], "Holdings")
        self.assertEqual(preview["rows"], [{"Symbol": "INFY", "Quantity": 12}])

    def test_home_loan_tracker_reads_payments_outstanding_and_rent_totals(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Loan payments" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>Home Loan FY</t></is></c><c r="B1" t="inlineStr"><is><t>Principal</t></is></c><c r="C1" t="inlineStr"><is><t>Interest</t></is></c><c r="D1" t="inlineStr"><is><t>Total</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>2025-26</t></is></c><c r="B2"><v>120000</v></c><c r="C2"><v>80000</v></c><c r="D2"><v>200000</v></c></row>'
                '<row r="3"><c r="A3" t="inlineStr"><is><t>Total</t></is></c><c r="B3"><v>120000</v></c><c r="C3"><v>80000</v></c><c r="D3"><v>200000</v></c><c r="I3" t="inlineStr"><is><t>Total</t></is></c><c r="J3"><v>300000</v></c><c r="K3"><v>50000</v></c><c r="L3"><v>250000</v></c></row>'
                '<row r="4"><c r="A4" t="inlineStr"><is><t>Outstanding(As on Sep 6 2026)</t></is></c><c r="B4"><v>3984073</v></c><c r="C4" t="inlineStr"><is><t>(8.05% p.a.)</t></is></c></row>'
                '</sheetData></worksheet>',
            )
        tracker = parse_home_loan_tracker_xlsx(payload.getvalue())
        self.assertIsNotNone(tracker)
        self.assertEqual(tracker["payment_rows"][0]["payment"], 200000)
        self.assertEqual(tracker["outstanding"], 3984073)
        self.assertEqual(tracker["outstanding_as_of"], "2026-09-06")
        self.assertEqual(tracker["annual_rate_pct"], 8.05)
        self.assertEqual(tracker["suggested_monthly_payment"], 16666.67)
        self.assertEqual(tracker["rent_totals"]["net_rent"], 250000)

    def test_portfolio_xlsx_combines_repeated_holdings_tables_and_skips_summary(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Active" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>Instrument</t></is></c><c r="B1" t="inlineStr"><is><t>Symbol</t></is></c><c r="C1" t="inlineStr"><is><t>Qty.</t></is></c><c r="D1" t="inlineStr"><is><t>Cur Value</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Infosys</t></is></c><c r="B2" t="inlineStr"><is><t>INFY</t></is></c><c r="C2"><v>10</v></c><c r="D2"><v>15000</v></c></row>'
                '<row r="3"/>'
                '<row r="5"><c r="A5" t="inlineStr"><is><t>Instrument</t></is></c><c r="B5" t="inlineStr"><is><t>Symbol</t></is></c><c r="C5" t="inlineStr"><is><t>Qty.</t></is></c><c r="D5" t="inlineStr"><is><t>Cur Value</t></is></c></row>'
                '<row r="6"><c r="A6" t="inlineStr"><is><t>TCS</t></is></c><c r="B6" t="inlineStr"><is><t>TCS</t></is></c><c r="C6"><v>5</v></c><c r="D6"><v>16000</v></c></row>'
                '<row r="7"/>'
                '<row r="9"><c r="A9" t="inlineStr"><is><t>Net worth</t></is></c><c r="B9"><v>500000</v></c></row>'
                '</sheetData></worksheet>',
            )
        preview = parse_portfolio_file("tracker.xlsx", payload.getvalue())
        self.assertEqual(preview["row_count"], 2)
        self.assertEqual([row["Symbol"] for row in preview["rows"]], ["INFY", "TCS"])
        self.assertEqual(preview["detected_mapping"]["symbol"], "Symbol")
        self.assertEqual(preview["detected_mapping"]["name"], "Instrument")

    def test_portfolio_analysis_excludes_duplicates_and_builds_concentration(self):
        histories = {
            "INFY": [{"date": date(2026, 10, 6), "close": 1500.0}],
            "TCS": [{"date": date(2026, 10, 6), "close": 3000.0}],
            "RELIANCE": [{"date": date(2026, 10, 6), "close": 1200.0}],
        }
        result = build_portfolio_analysis(
            [
                {"Symbol": "INFY", "Qty": "10", "Avg": "1400"},
                {"Symbol": "INFY", "Qty": "2", "Avg": "1450"},
                {"Symbol": "TCS", "Qty": "5", "Avg": "3200"},
                {"Symbol": "RELIANCE", "Qty": "10", "Avg": "1000"},
            ],
            {"symbol": "Symbol", "quantity": "Qty", "average_cost": "Avg"},
            histories,
            constituents=[
                {"symbol": "INFY", "name": "Infosys", "sector": "IT"},
                {"symbol": "TCS", "name": "TCS", "sector": "IT"},
                {"symbol": "RELIANCE", "name": "Reliance", "sector": "Energy"},
            ],
            fno_symbols={"INFY", "TCS", "RELIANCE"},
        )
        self.assertEqual(result["coverage"]["eligible_positions"], 2)
        self.assertEqual(result["coverage"]["excluded_rows"], 2)
        self.assertEqual(result["weight_basis"], "quantity_times_latest_close")
        self.assertAlmostEqual(sum(row["weight_pct"] for row in result["positions"] if row["weight_pct"] is not None), 100.0)
        self.assertEqual(result["sectors"][0]["sector"], "IT")
        self.assertTrue(any(issue["reason"] == "duplicate_symbol" for issue in result["issues"]))

    def test_google_finance_quote_parser_reads_last_close_and_latest_price(self):
        record = [
            "/g/example",
            ["BEL", "NSE"],
            "Bharat Electronics Ltd",
            0,
            "INR",
            [378.3, -9.1, -2.35, 2, 2, 2],
            None,
            387.4,
            "#008bc2",
            "IN",
            "/m/example",
            [1791368995],
        ]
        html = (
            '<script class="ds:13">AF_initDataCallback({key: "ds:13", data:'
            f'{json.dumps([[[record]]])}, sideChannel: {{}}}});</script>'
        )
        quote = parse_google_finance_quote_html(html, "BEL")
        self.assertEqual(quote["last_close"], 387.4)
        self.assertEqual(quote["latest_price"], 378.3)
        self.assertEqual(quote["source"], "Google Finance")

    def test_xirr_annualizes_dated_cash_flows(self):
        result = calculate_xirr(
            [
                (date(2025, 1, 1), -100000.0),
                (date(2026, 1, 1), 110000.0),
            ]
        )
        self.assertAlmostEqual(result, 10.0, places=2)

    def test_cashflow_matched_benchmark_uses_each_entry_date(self):
        result = calculate_cashflow_matched_benchmark_return(
            [
                {"entry_date": "2025-01-01", "invested_value": 1000.0},
                {"entry_date": "2025-06-01", "invested_value": 1000.0},
            ],
            [
                {"date": date(2025, 1, 1), "close": 100.0},
                {"date": date(2025, 6, 1), "close": 110.0},
                {"date": date(2026, 1, 1), "close": 121.0},
            ],
            date(2026, 1, 1),
        )
        self.assertEqual(result["covered_positions"], 2)
        self.assertEqual(result["return_pct"], 15.5)

    def test_portfolio_risk_metrics_calculates_aligned_daily_ratios(self):
        sessions = [date(2025, 1, 1) + timedelta(days=index) for index in range(130)]
        closes = [100.0]
        for index in range(1, len(sessions)):
            closes.append(closes[-1] * (1.01 if index % 2 else 0.995))
        history = [
            {"date": session_date, "close": close}
            for session_date, close in zip(sessions, closes)
        ]
        result = calculate_portfolio_risk_metrics(
            [
                {"symbol": "ALPHA", "weight_pct": 60.0},
                {"symbol": "BETA", "weight_pct": 40.0},
            ],
            {"ALPHA": history, "BETA": history},
            history,
        )
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["sessions"], 129)
        self.assertEqual(result["beta"], 1.0)
        self.assertEqual(result["jensen_alpha_pct"], 0.0)
        self.assertEqual(result["tracking_error_pct"], 0.0)
        self.assertEqual(result["correlation"], 1.0)
        self.assertIsNotNone(result["sharpe_ratio"])
        self.assertIsNotNone(result["sortino_ratio"])
        self.assertLess(result["maximum_drawdown_pct"], 0)

    def test_portfolio_risk_metrics_withholds_partial_portfolio_history(self):
        history = [
            {"date": date(2025, 1, 1) + timedelta(days=index), "close": 100 + index}
            for index in range(130)
        ]
        result = calculate_portfolio_risk_metrics(
            [
                {"symbol": "AVAILABLE", "weight_pct": 80.0},
                {"symbol": "MISSING", "weight_pct": 20.0},
            ],
            {"AVAILABLE": history},
            history,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "historical_weight_coverage_below_threshold")
        self.assertEqual(result["coverage"]["historical_positions"], 1)
        self.assertEqual(result["coverage"]["historical_weight_pct"], 80.0)
        self.assertIsNone(result["sharpe_ratio"])

    def test_portfolio_amfi_resolution_and_history_parser_use_exact_scheme(self):
        self.assertEqual(
            resolve_portfolio_amfi_scheme("ICICI Pru short term fund")["scheme_code"],
            "120754",
        )
        self.assertEqual(
            resolve_portfolio_amfi_scheme("Franklin Templeton US opportunities FOF - direct growth")["scheme_code"],
            "118551",
        )
        parsed = parse_amfi_nav_history_text(
            "\n".join((
                "Scheme Code;Scheme Name;Plan;Option;ISIN;;NAV;Date",
                "120754;ICICI Prudential Short Term Fund;Direct Plan;Growth;INF109K013N3;;70.8038;07-Oct-2026",
                "999999;Unrelated Fund;Direct Plan;Growth;INF000000000;;10.0;07-Oct-2026",
                "120754;ICICI Prudential Short Term Fund;Direct Plan;Growth;INF109K013N3;;70.7000;06-Oct-2026",
            )),
            {"120754"},
        )
        self.assertEqual(len(parsed["120754"]), 2)
        self.assertEqual(parsed["120754"][0]["date"], date(2026, 10, 6))
        self.assertEqual(parsed["120754"][-1]["close"], 70.8038)

    def test_portfolio_risk_metrics_excludes_ncd_and_uses_amfi_override(self):
        sessions = [date(2025, 1, 1) + timedelta(days=index) for index in range(130)]
        closes = [100.0]
        for index in range(1, len(sessions)):
            closes.append(closes[-1] * (1.008 if index % 3 else 0.996))
        history = [
            {"date": session_date, "close": close}
            for session_date, close in zip(sessions, closes)
        ]
        result = build_portfolio_analysis(
            [
                {"Instrument": "ICICI Pru short term fund", "Symbol": "MF", "Current": 60},
                {"Instrument": "BEL", "Symbol": "BEL", "Current": 30},
                {"Instrument": "NCD", "Symbol": "SHRIRAM FIN", "Current": 10},
            ],
            {
                "symbol": "Symbol",
                "quantity": None,
                "weight": None,
                "current_value": "Current",
                "name": "Instrument",
            },
            {"BEL": history},
            benchmark_history=history,
            position_history_overrides={
                2: {
                    "history": history,
                    "scheme_code": "120754",
                    "source": "AMFI",
                }
            },
            valuation_date=date(2026, 1, 1),
        )
        metrics = result["risk_metrics"]
        self.assertEqual(metrics["status"], "available")
        self.assertEqual(metrics["coverage"]["required_positions"], 2)
        self.assertEqual(metrics["coverage"]["excluded_positions"], 1)
        self.assertEqual(metrics["coverage"]["excluded_weight_pct"], 10.0)
        self.assertEqual(result["coverage"]["amfi_history_positions"], 1)

    def test_portfolio_analysis_prefers_google_finance_quote_over_local_eod(self):
        result = build_portfolio_analysis(
            [{"Symbol": "BEL", "Qty": "10", "Avg": "350"}],
            {"symbol": "Symbol", "quantity": "Qty", "average_cost": "Avg"},
            {"BEL": [{"date": date(2026, 10, 6), "close": 386.75}]},
            market_quotes={
                "BEL": {
                    "last_close": 387.4,
                    "latest_price": 378.3,
                    "observed_at": "2026-10-07T10:29:55+00:00",
                    "source_url": "https://www.google.com/finance/quote/BEL:NSE?hl=en",
                }
            },
        )
        position = result["positions"][0]
        self.assertEqual(position["last_close"], 387.4)
        self.assertEqual(position["last_close_date"], "2026-10-06")
        self.assertEqual(position["latest_price"], 378.3)
        self.assertEqual(position["price_source"], "google_finance")
        self.assertEqual(result["coverage"]["google_finance_priced"], 1)

    def test_portfolio_eod_refresh_revalues_positions_from_fresh_sources(self):
        result = build_portfolio_analysis(
            [
                {"Instrument": "ICICI Pru short term fund", "Symbol": "MF", "Qty": "100", "LTP": "70", "Current": "7000"},
                {"Instrument": "BEL", "Symbol": "BEL", "Qty": "10", "LTP": "350", "Current": "3500"},
                {"Instrument": "NCD", "Symbol": "SHRIRAM FIN", "Qty": "1", "LTP": "100000", "Current": "100000"},
            ],
            {
                "symbol": "Symbol",
                "quantity": "Qty",
                "weight": None,
                "average_cost": None,
                "current_value": "Current",
                "latest_price": "LTP",
                "entry_date": None,
                "invested_value": None,
                "sector": None,
                "name": "Instrument",
            },
            {"BEL": [{"date": date(2026, 10, 8), "close": 380.0}]},
            position_history_overrides={
                2: {
                    "history": [{"date": date(2026, 10, 8), "close": 71.5}],
                    "scheme_code": "120754",
                    "source": "AMFI",
                }
            },
            valuation_date=date(2026, 10, 8),
            refresh_prices=True,
        )
        positions = {position["company_name"]: position for position in result["positions"]}
        self.assertEqual(result["weight_basis"], "refreshed_price_with_uploaded_value_fallback")
        self.assertEqual(positions["ICICI Pru short term fund"]["latest_price"], 71.5)
        self.assertEqual(positions["ICICI Pru short term fund"]["current_value"], 7150.0)
        self.assertEqual(positions["ICICI Pru short term fund"]["price_source"], "amfi_nav")
        self.assertEqual(positions["BEL"]["latest_price"], 380.0)
        self.assertEqual(positions["BEL"]["current_value"], 3800.0)
        self.assertEqual(positions["BEL"]["price_source"], "local_eod")
        self.assertEqual(positions["NCD"]["current_value"], 100000.0)
        self.assertEqual(positions["NCD"]["price_source"], "uploaded_price_fallback")
        self.assertEqual(result["coverage"]["amfi_nav_priced"], 1)
        self.assertEqual(result["coverage"]["local_eod_priced"], 1)

    def test_portfolio_summary_calculates_returns_benchmark_and_xirr(self):
        result = build_portfolio_analysis(
            [
                {
                    "Symbol": "BEL",
                    "Entry Date": "2025-01-01",
                    "Qty": "10",
                    "Avg": "100",
                    "Current": "1200",
                }
            ],
            {
                "symbol": "Symbol",
                "quantity": "Qty",
                "weight": None,
                "average_cost": "Avg",
                "current_value": "Current",
                "latest_price": None,
                "entry_date": "Entry Date",
                "invested_value": None,
                "sector": None,
                "name": None,
            },
            {},
            benchmark_history=[
                {"date": date(2025, 1, 1), "close": 100.0},
                {"date": date(2026, 1, 1), "close": 110.0},
            ],
            gsec_benchmark_history=[
                {"date": date(2025, 1, 1), "close": 200.0},
                {"date": date(2026, 1, 1), "close": 212.0},
            ],
            valuation_date=date(2026, 1, 1),
        )
        summary = result["portfolio_summary"]
        self.assertEqual(summary["total_invested"], 1000.0)
        self.assertEqual(summary["current_return"], 200.0)
        self.assertEqual(summary["net_return_pct"], 20.0)
        self.assertEqual(summary["portfolio_xirr_pct"], 20.0)
        self.assertEqual(result["benchmark"]["return_pct"], 10.0)
        self.assertEqual(result["gsec_benchmark"]["return_pct"], 6.0)
        self.assertEqual(result["gsec_benchmark"]["name"], "Nifty 10 yr Benchmark G-Sec")

    def test_portfolio_asset_allocation_classifies_and_aggregates_holdings(self):
        result = build_portfolio_analysis(
            [
                {"Instrument": "Large Cap Equity Fund", "Symbol": "EQ FUND", "Current": 400},
                {"Instrument": "Short Term Fund", "Symbol": "DEBT FUND", "Current": 250},
                {"Instrument": "Gold ETF", "Symbol": "GOLDBEES", "Current": 150},
                {"Instrument": "Multi Asset Fund", "Symbol": "HYBRID FUND", "Current": 100},
                {"Instrument": "Bank Balance", "Symbol": "CASH", "Current": 50},
                {"Instrument": "Unmapped Certificate", "Symbol": "MYSTERY", "Current": 50},
            ],
            {
                "symbol": "Symbol",
                "quantity": None,
                "weight": None,
                "average_cost": None,
                "current_value": "Current",
                "latest_price": None,
                "entry_date": None,
                "invested_value": None,
                "sector": None,
                "name": "Instrument",
            },
            {},
        )
        allocation = {row["asset_class"]: row for row in result["asset_allocation"]}
        self.assertEqual(list(allocation), ["Equity", "Debt", "Commodity", "Hybrid", "Cash", "Other"])
        self.assertEqual(allocation["Equity"]["weight_pct"], 40.0)
        self.assertEqual(allocation["Debt"]["current_value"], 250.0)
        self.assertEqual(allocation["Commodity"]["position_count"], 1)
        self.assertEqual(allocation["Other"]["weight_pct"], 5.0)

    def test_portfolio_analysis_accepts_uploaded_weights_without_prices(self):
        result = build_portfolio_analysis(
            [{"Ticker": "AAA", "Weight": "60%"}, {"Ticker": "BBB", "Weight": "40%"}],
            {"symbol": "Ticker", "weight": "Weight"},
            {},
        )
        self.assertEqual(result["coverage"]["eligible_positions"], 2)
        self.assertEqual(result["weight_basis"], "uploaded_weight")
        self.assertEqual(result["concentration"]["largest_position_pct"], 60.0)
        self.assertEqual(result["concentration"]["state"], "high_concentration")

    def test_portfolio_analysis_accepts_current_value_without_quantity(self):
        result = build_portfolio_analysis(
            [{"Stock": "AAA", "Market Value": "75000"}, {"Stock": "BBB", "Market Value": "25000"}],
            {"symbol": "Stock", "quantity": None, "weight": None, "average_cost": None, "current_value": "Market Value", "sector": None, "name": None},
            {},
        )
        self.assertEqual(result["coverage"]["eligible_positions"], 2)
        self.assertEqual(result["weight_basis"], "uploaded_current_value")
        self.assertEqual(result["concentration"]["largest_position_pct"], 75.0)

    def test_portfolio_analysis_uses_uploaded_ltp_when_live_quote_is_off(self):
        result = build_portfolio_analysis(
            [{"Symbol": "MF", "Qty": "10", "Avg": "100", "LTP": "108", "Current": "1080"}],
            {
                "symbol": "Symbol",
                "quantity": "Qty",
                "weight": None,
                "average_cost": "Avg",
                "current_value": "Current",
                "latest_price": "LTP",
                "sector": None,
                "name": None,
            },
            {},
        )
        position = result["positions"][0]
        self.assertEqual(position["latest_price"], 108.0)
        self.assertIsNone(position["last_close"])
        self.assertEqual(position["price_source"], "uploaded_price_fallback")

    def test_portfolio_asset_class_treats_uploaded_traded_stock_as_equity(self):
        result = build_portfolio_analysis(
            [{"Instrument": "Eris Life Sciences", "Symbol": "ERIS", "Qty": 4, "LTP": 1144.2, "Current": 4576.8}],
            {
                "symbol": "Symbol", "quantity": "Qty", "weight": None,
                "average_cost": None, "current_value": "Current", "latest_price": "LTP",
                "entry_date": None, "invested_value": None, "sector": None, "name": "Instrument",
            },
            {},
        )
        self.assertEqual(result["positions"][0]["asset_class"], "Equity")
        self.assertEqual(result["asset_allocation"][0]["asset_class"], "Equity")

    def test_portfolio_analysis_allows_shared_symbol_when_instrument_names_differ(self):
        result = build_portfolio_analysis(
            [
                {"Instrument": "Fund A", "Symbol": "MF", "Qty": "10", "Avg": "100", "Current": "1100"},
                {"Instrument": "Fund B", "Symbol": "MF", "Qty": "20", "Avg": "100", "Current": "1800"},
            ],
            {"symbol": "Symbol", "quantity": "Qty", "average_cost": "Avg", "current_value": "Current", "name": "Instrument"},
            {},
        )
        self.assertEqual(result["coverage"]["eligible_positions"], 2)
        self.assertEqual([row["return_since_average_cost_pct"] for row in result["positions"]], [-10.0, 10.0])

    def test_portfolio_analysis_accepts_descriptive_non_exchange_identifier_with_uploaded_value(self):
        result = build_portfolio_analysis(
            [{"Instrument": "NCD", "Symbol": "SHRIRAM FIN", "Qty": "1", "Avg": "99990", "Current": "104963"}],
            {"symbol": "Symbol", "quantity": "Qty", "average_cost": "Avg", "current_value": "Current", "name": "Instrument"},
            {},
        )
        self.assertEqual(result["coverage"]["eligible_positions"], 1)
        self.assertEqual(result["positions"][0]["return_since_average_cost_pct"], 4.97)

    def test_mutual_funds_comparer_is_a_portfolio_analysis_tab(self):
        page = (Path(__file__).resolve().parents[1] / "dist" / "index.html").read_text(encoding="utf-8")
        portfolio_start = page.index('<section id="portfolioView"')
        next_workspace = page.index('<section id="stockYtdView"', portfolio_start)
        portfolio_markup = page[portfolio_start:next_workspace]

        self.assertNotIn('data-page="Mutual Funds Comparer"', page)
        self.assertIn('id="portfolioMutualFundsTab"', portfolio_markup)
        self.assertIn('id="portfolioMutualFundsPanel"', portfolio_markup)
        self.assertIn('id="combinedPortfolioValue"', portfolio_markup)
        self.assertIn('id="combinedDiversificationScore"', portfolio_markup)
        self.assertIn('id="combinedRedundancyCards"', portfolio_markup)
        self.assertIn('id="combinedImprovementPaths"', portfolio_markup)
        self.assertIn('class="analysis-intro mutual-fund-hero portfolio-clean-hero"', portfolio_markup)
        self.assertIn('class="universe-controls portfolio-upload-card"', portfolio_markup)
        self.assertGreaterEqual(portfolio_markup.count('portfolio-story-section'), 7)
        self.assertIn('01 · OVERVIEW', portfolio_markup)
        self.assertIn('06 · NEXT STEPS', portfolio_markup)
        self.assertIn('class="portfolio-reading-guide"', portfolio_markup)
        self.assertIn('id="portfolioPerformanceSection"', portfolio_markup)
        self.assertIn('id="portfolioRedundancySection"', portfolio_markup)
        self.assertIn("'No stocks found'", page)
        self.assertIn('Highest fund similarities', page)
        self.assertIn('Most repeated underlying holdings', page)
        self.assertIn("document.getElementById('portfolioPerformanceSection').hidden = !performanceHasData", page)
        self.assertIn("document.getElementById('portfolioRedundancySection').hidden = !redundancyCards.length", page)
        self.assertIn('id="portfolioFileGuide"', portfolio_markup)
        self.assertIn('id="portfolioFormatDialog"', portfolio_markup)
        self.assertIn('Example stock holdings table', portfolio_markup)
        self.assertIn('Example mutual fund holdings table', portfolio_markup)
        self.assertIn("portfolioFormatDialog.showModal()", page)
        self.assertIn('id="portfolioLoadProgress"', portfolio_markup)
        self.assertIn('id="portfolioProgressFill"', portfolio_markup)
        self.assertIn("setPortfolioTab('mutual-funds')", page)
        self.assertIn('startPortfolioProgress(file)', page)
        self.assertIn("finishPortfolioProgress('Analysis ready'", page)
        self.assertNotIn("mutualFundsComparerView", page)

    def test_eod_refresh_uses_consolidated_dashboard_and_keeps_failure_reasons(self):
        page = (Path(__file__).resolve().parents[1] / "dist" / "index.html").read_text(encoding="utf-8")
        refresh_start = page.index("async function refreshAllWorkspaceViewsAfterEod()")
        refresh_end = page.index("async function runEodUpdate()", refresh_start)
        refresh_source = page[refresh_start:refresh_end]

        self.assertIn("['Dashboard overview', loadDashboardWorkspace()]", refresh_source)
        self.assertNotIn("loadDashboardMarketStory(false)", refresh_source)
        self.assertIn("workspace_refresh_incomplete", refresh_source)
        self.assertIn("EOD_RUN_STATUS_KEY", page)
        self.assertIn("failedStages.map(formatEodFailure)", page)


if __name__ == "__main__":
    unittest.main()
