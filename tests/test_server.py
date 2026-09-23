import unittest
import socket
import urllib.error
from datetime import date, time, timedelta

from server import (
    NIFTY_INDICES_PUBLIC_USER_AGENT,
    OFFICIAL_SECTORAL_INDICES,
    build_checksum,
    calculate_index_ytd,
    classify_network_error,
    calculate_market_breadth,
    discover_sectoral_indices,
    extract_request_token,
    normalize_index_snapshot,
    parse_daily_closes,
    parse_dashboard_index_tokens,
    parse_equity_tokens,
    parse_nifty500_constituents,
)


class KiteHandshakeHelpersTest(unittest.TestCase):
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

    def test_dashboard_index_tokens_bind_exact_dashboard_indices(self):
        fixture = """instrument_token,tradingsymbol,name,segment,exchange
1,NIFTY 50,NIFTY 50,INDICES,NSE
2,NIFTY BANK,NIFTY BANK,INDICES,NSE
3,NIFTY IT,NIFTY IT,INDICES,NSE
4,NIFTY IT,NIFTY IT,INDICES,BSE
5,NIFTY ENERGY,NIFTY ENERGY,INDICES,NSE
"""
        self.assertEqual(
            parse_dashboard_index_tokens(fixture),
            {"Nifty 50": "1", "Nifty Bank": "2", "Nifty IT": "3", "Nifty Energy": "5"},
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
