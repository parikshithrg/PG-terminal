import unittest
import socket
import urllib.error
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
    calculate_domestic_sentiment_core,
    calculate_institutional_flow_summary,
    calculate_macro_context_summary,
    calculate_futures_oi_summary,
    discover_sectoral_indices,
    extract_request_token,
    historical_date_ranges,
    historical_lookback_start,
    is_complete_seasonality_payload,
    normalize_index_snapshot,
    normalize_futures_eod_quotes,
    parse_daily_candles,
    parse_daily_closes,
    parse_dashboard_index_tokens,
    parse_equity_tokens,
    parse_nifty500_constituents,
    parse_institutional_flows,
    parse_rbi_macro_snapshot,
    parse_near_month_stock_futures,
    parse_seasonality_index_tokens,
    rank_historical_month_averages,
)


class KiteHandshakeHelpersTest(unittest.TestCase):
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

    def test_futures_oi_summary_does_not_compare_across_rollover(self):
        rows = [
            {"date": date(2026, 9, 22), "underlying": "AAA", "contract_key": "NFO:AAA26SEPFUT", "expiry": date(2026, 9, 24)},
            {"date": date(2026, 9, 23), "underlying": "AAA", "contract_key": "NFO:AAA26SEPFUT", "expiry": date(2026, 9, 24)},
            {"date": date(2026, 9, 22), "underlying": "BBB", "contract_key": "NFO:BBB26SEPFUT", "expiry": date(2026, 9, 24)},
            {"date": date(2026, 9, 23), "underlying": "BBB", "contract_key": "NFO:BBB26OCTFUT", "expiry": date(2026, 10, 29)},
        ]
        summary = calculate_futures_oi_summary(rows)
        self.assertEqual(summary["comparable_count"], 1)
        self.assertEqual(summary["rollover_baseline_count"], 1)
        self.assertEqual(summary["classification_status"], "withheld")

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
        self.assertEqual(result["available_clusters"], 3)
        self.assertTrue(result["volatility"]["india_vix"]["available"])
        self.assertEqual(result["volatility"]["india_vix"]["level"], 15.98)
        self.assertEqual(result["volatility"]["india_vix"]["five_day_change_pt"], 0.1)
        self.assertEqual(result["volatility"]["india_vix"]["one_year_percentile"], 100.0)
        self.assertEqual(result["freshness"]["state"], "fresh")
        self.assertEqual(result["freshness"]["expected_through"], "2025-10-27")

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
