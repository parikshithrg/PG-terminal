import unittest
import socket
import urllib.error
import io
import zipfile
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from server import (
    NIFTY_INDICES_PUBLIC_USER_AGENT,
    OFFICIAL_SECTORAL_INDICES,
    build_checksum,
    calculate_seasonality,
    calculate_seasonality_validation,
    calculate_month_to_date_returns,
    calculate_index_ytd,
    classify_network_error,
    completed_history_date,
    calculate_market_breadth,
    calculate_candidate_regime,
    calculate_domestic_sentiment_core,
    calculate_regime_walk_forward_validation,
    build_dashboard_market_sentiment_summary,
    build_dashboard_fno_summary,
    build_dashboard_seasonality_summary,
    build_index_futures_confirmation,
    build_regime_external_cluster_readiness,
    apply_recovering_market_state,
    build_regime_validation_universe,
    load_index_constituent_snapshot,
    calculate_institutional_flow_summary,
    calculate_confirmed_fpi_summary,
    calculate_macro_context_summary,
    calculate_futures_oi_summary,
    calculate_global_risk_summary,
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
    parse_dashboard_index_tokens,
    parse_equity_tokens,
    parse_nifty500_constituents,
    parse_institutional_flows,
    parse_nsdl_confirmed_fpi,
    parse_futures_daily_snapshot,
    parse_fred_global_csv,
    parse_fred_global_zip,
    parse_rbi_macro_snapshot,
    parse_near_month_stock_futures,
    parse_seasonality_index_tokens,
    rank_historical_month_averages,
)


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
        self.assertEqual(rows[0], {"symbol": "SYM0", "sector": "Sector 0"})
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
        invalid = {
            "status": "success",
            "data": {"candles": [["2026-09-22T00:00:00+0530", 100, 90, 95, 105, 100]]},
        }
        with self.assertRaisesRegex(ValueError, "invalid_provider_response"):
            parse_daily_candles(invalid, today=date(2026, 9, 23), now_time=time(10, 0))

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


if __name__ == "__main__":
    unittest.main()
