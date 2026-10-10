"""Local PG-terminal server with an in-memory Kite Connect handshake."""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import io
import json
import math
import re
import socket
import ssl
import threading
import time
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

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


TOKEN_URL = "https://api.kite.trade/session/token"
PROFILE_URL = "https://api.kite.trade/user/profile"
OHLC_URL = "https://api.kite.trade/quote/ohlc"
NSE_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NSE"
NFO_INSTRUMENTS_URL = "https://api.kite.trade/instruments/NFO"
FULL_QUOTE_URL = "https://api.kite.trade/quote"
NIFTY500_CONSTITUENTS_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
GOOGLE_FINANCE_QUOTE_URL = "https://www.google.com/finance/quote/{symbol}:NSE?hl=en"
NIFTY_GSEC_HISTORY_PAGE_URL = "https://www.niftyindices.com/reports"
NIFTY_GSEC_HISTORY_URL = "https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString"
NIFTY_GSEC_SOURCE_URL = "https://www.niftyindices.com/indices/fixed-income/gsec-indices/nifty-10-yr-benchmark-gsec"
NIFTY_GSEC_INDEX_NAME = "Nifty 10 yr Benchmark G-Sec"
AMFI_NAV_HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
AMFI_NAV_SOURCE_URL = "https://www.amfiindia.com/net-asset-value/nav-download"
AMFI_PORTFOLIO_SCHEMES = (
    {
        "scheme_code": "120754",
        "amc_id": "20",
        "name": "ICICI Prudential Short Term Fund - Direct Plan - Growth",
        "required_terms": ("icici", "short", "term", "fund"),
    },
    {
        "scheme_code": "118632",
        "amc_id": "21",
        "name": "Nippon India Large Cap Fund - Direct Plan - Growth Option",
        "required_terms": ("nippon", "large", "cap"),
    },
    {
        "scheme_code": "120334",
        "amc_id": "20",
        "name": "ICICI Prudential Multi Asset Allocation Fund - Direct Plan - Growth",
        "required_terms": ("icici", "multi", "asset"),
    },
    {
        "scheme_code": "118989",
        "amc_id": "9",
        "name": "HDFC Mid Cap Fund - Direct Plan - Growth Option",
        "required_terms": ("hdfc", "mid", "cap"),
    },
    {
        "scheme_code": "118551",
        "amc_id": "27",
        "name": "Franklin U. S. Opportunities Equity Active Fund of Funds - Direct Plan - Growth",
        "required_terms": ("franklin", "opportunities"),
    },
)
NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_FII_DII_SOURCE = "NSE FII/FPI & DII combined-exchange cash-market report"
NSDL_FPI_MONTHLY_URL = "https://www.fpi.nsdl.co.in/web/Reports/Monthly.aspx"
NSDL_FPI_SOURCE = "NSDL custodian-confirmed daily FPI investment report"
FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_GLOBAL_SOURCE = "Federal Reserve Bank of St. Louis FRED daily series"
FRED_GLOBAL_SERIES = {
    "SP500": ("sp500", "Index", "S&P 500"),
    "VIXCLS": ("us_vix", "Index", "CBOE VIX"),
    "DEXJPUS": ("usd_jpy", "JPY per USD", "USD/JPY"),
    "DTWEXBGS": ("broad_usd", "Index Jan 2006=100", "Broad U.S. dollar index"),
    "DCOILBRENTEU": ("brent_crude", "USD per barrel", "Brent crude spot"),
}
SENTIMENT_EVIDENCE_MODEL_VERSION = "market-sentiment-evidence-v1"
REGIME_RULE_VERSION = "market-regime-candidate-v1"
HISTORICAL_REGIME_CONTRACT_VERSION = "historical-regimes-v5"
HISTORICAL_BULL_BEAR_THRESHOLD_PCT = 20.0
HISTORICAL_CORRECTION_THRESHOLD_PCT = 10.0
HISTORICAL_RAPID_BEAR_SESSIONS = 45
REGIME_BAND_VALUES = {"constructive": 1.0, "mixed": 0.0, "defensive": -1.0}
REGIME_CLUSTER_WEIGHTS = {
    "domestic_trend": 0.25,
    "participation_and_strength": 0.20,
    "volatility_and_stress": 0.15,
    "institutional_flows": 0.15,
    "currency_and_rates": 0.10,
    "global_risk": 0.15,
}
REGIME_MINIMUM_AVAILABLE_WEIGHT = 0.60
REGIME_MINIMUM_STOCK_COVERAGE_PCT = 80.0
REGIME_VALIDATION_TRAILING_SESSIONS = 252
REGIME_VALIDATION_DEFAULT_HORIZONS = (5, 20, 60)
REGIME_EXTERNAL_HISTORY_SESSIONS = 252
REGIME_EXTERNAL_WALK_FORWARD_SESSIONS = 312
REGIME_RECOVERY_MINIMUM_RISK_SESSIONS = 5
REGIME_RECOVERY_MAXIMUM_SESSIONS = 20
REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS = 60
REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT = 1.0
REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT = 60.0
REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT = 0.5
REGIME_LONG_HORIZON_SESSIONS = 20
REGIME_SHORT_HORIZON_SESSIONS = 5
REGIME_RISK_TAIL_PERCENTILE = 10.0
REGIME_ADVERSE_DISTANCE_LEVELS_PCT = (2.0, 3.0, 5.0)
REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT = 5
REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT = 50.0
REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT = 55.0
REGIME_RECOVERY_INCREMENTAL_RETURN_PCT = 0.5
REGIME_RECOVERY_INCREMENTAL_POSITIVE_RATE_PCT = 5.0
REGIME_RECOVERY_DRAWDOWN_TOLERANCE_PCT = 2.0
REGIME_VALIDATION_EVENTS = (
    {
        "key": "india_nbfc_stress_2018",
        "label": "India NBFC liquidity stress",
        "start": date(2018, 9, 4),
        "end": date(2018, 10, 31),
    },
    {
        "key": "covid_shock_2020",
        "label": "COVID-19 market shock",
        "start": date(2020, 2, 20),
        "end": date(2020, 5, 29),
    },
    {
        "key": "global_inflation_ukraine_2022",
        "label": "Global inflation and Ukraine shock",
        "start": date(2022, 2, 24),
        "end": date(2022, 6, 17),
    },
    {
        "key": "india_election_result_2024",
        "label": "India general-election result shock",
        "start": date(2024, 6, 3),
        "end": date(2024, 6, 10),
    },
)
NEWS_EVENT_SOURCES = (
    {
        "key": "nse_corporate_filings",
        "label": "NSE corporate filings",
        "category": "company_disclosures",
        "authority": "National Stock Exchange of India",
        "url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "terms_url": "https://www.nseindia.com/static/nse-terms-of-use",
        "coverage": "Issuer-filed announcements, board meetings, actions, and results",
    },
    {
        "key": "bse_corporate_announcements",
        "label": "BSE corporate announcements",
        "category": "company_disclosures",
        "authority": "BSE India",
        "url": "https://www.bseindia.com/corporates/ann.html",
        "coverage": "Issuer-filed corporate announcements and attachments",
    },
    {
        "key": "sebi_press_releases",
        "label": "SEBI press releases",
        "category": "regulatory",
        "authority": "Securities and Exchange Board of India",
        "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=6&ssid=23",
        "coverage": "Regulatory press releases and market-structure updates",
    },
    {
        "key": "rbi_press_releases",
        "label": "RBI press releases",
        "category": "macro_policy",
        "authority": "Reserve Bank of India",
        "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
        "coverage": "Monetary-policy, liquidity, banking, and sovereign-market releases",
    },
)
MACRO_EVENT_SOURCES = (
    {
        "key": "rbi_mpc_calendar",
        "label": "RBI MPC meeting schedule 2026-27",
        "authority": "Reserve Bank of India",
        "region": "India",
        "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=62422",
        "status": "verified_snapshot",
        "note": "Official schedule published 23-Mar-2026 under Section 45ZI; meeting dates are verified, but release times are not specified.",
    },
    {
        "key": "mospi_release_calendar",
        "label": "MoSPI advance release calendar 2026-27",
        "authority": "Ministry of Statistics and Programme Implementation",
        "region": "India",
        "url": "https://www.mospi.gov.in/uploads/documents/releaseCalender/1779709510470-ADVANCE%20RELEASE%20CALENDAR%202026-27%20Updated%2025.05.2026.pdf",
        "status": "verified_snapshot",
        "note": "Official PDF updated 25-May-2026; dates may change in exigencies or for holidays.",
    },
    {
        "key": "fomc_calendar",
        "label": "Federal Reserve FOMC calendar",
        "authority": "Board of Governors of the Federal Reserve System",
        "region": "United States",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "status": "verified_snapshot",
        "note": "Official 2026 meeting calendar; meeting dates are tentative until confirmed by the preceding meeting.",
    },
    {
        "key": "bls_cpi_schedule",
        "label": "BLS CPI release schedule",
        "authority": "U.S. Bureau of Labor Statistics",
        "region": "United States",
        "url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        "status": "verified_snapshot",
        "note": "Official 2026 CPI schedule; release times are Eastern Time.",
    },
)
MACRO_EVENTS = (
    {
        "key": "rbi_mpc_2026_10",
        "title": "RBI Monetary Policy Committee meeting",
        "region": "India",
        "category": "central_bank",
        "start_at": "2026-10-05",
        "end_at": "2026-10-07",
        "timezone": "Asia/Kolkata",
        "source_key": "rbi_mpc_calendar",
        "note": "Official schedule confirms the meeting dates; it does not specify the policy-decision time.",
    },
    {
        "key": "india_cpi_2026_10",
        "title": "India CPI release",
        "region": "India",
        "category": "inflation",
        "start_at": "2026-10-12",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
    },
    {
        "key": "us_cpi_2026_10",
        "title": "U.S. CPI release — September 2026",
        "region": "United States",
        "category": "inflation",
        "start_at": "2026-10-14T08:30:00-04:00",
        "timezone": "America/New_York",
        "source_key": "bls_cpi_schedule",
    },
    {
        "key": "fomc_2026_10",
        "title": "Federal Reserve FOMC meeting",
        "region": "United States",
        "category": "central_bank",
        "start_at": "2026-10-27",
        "end_at": "2026-10-28",
        "decision_at": "2026-10-28T14:00:00-04:00",
        "timezone": "America/New_York",
        "source_key": "fomc_calendar",
    },
    {
        "key": "india_iip_2026_10",
        "title": "India IIP release",
        "region": "India",
        "category": "growth",
        "start_at": "2026-10-28",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
    },
    {
        "key": "us_cpi_2026_11",
        "title": "U.S. CPI release — October 2026",
        "region": "United States",
        "category": "inflation",
        "start_at": "2026-11-10T08:30:00-05:00",
        "timezone": "America/New_York",
        "source_key": "bls_cpi_schedule",
    },
    {
        "key": "india_cpi_2026_11",
        "title": "India CPI release",
        "region": "India",
        "category": "inflation",
        "start_at": "2026-11-12",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
    },
    {
        "key": "fomc_minutes_2026_11",
        "title": "Federal Reserve FOMC minutes — October meeting",
        "region": "United States",
        "category": "central_bank",
        "start_at": "2026-11-18T14:00:00-05:00",
        "timezone": "America/New_York",
        "source_key": "fomc_calendar",
    },
    {
        "key": "india_iip_2026_11",
        "title": "India IIP release",
        "region": "India",
        "category": "growth",
        "start_at": "2026-11-28",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
        "note": "Falls on a weekend; the official calendar says holiday releases move to the next working day.",
    },
    {
        "key": "india_gdp_2026_q2",
        "title": "India GDP release — Q2 FY 2026-27",
        "region": "India",
        "category": "growth",
        "start_at": "2026-11-30",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
    },
    {
        "key": "rbi_mpc_2026_12",
        "title": "RBI Monetary Policy Committee meeting",
        "region": "India",
        "category": "central_bank",
        "start_at": "2026-12-02",
        "end_at": "2026-12-04",
        "timezone": "Asia/Kolkata",
        "source_key": "rbi_mpc_calendar",
        "note": "Official schedule confirms the meeting dates; it does not specify the policy-decision time.",
    },
    {
        "key": "fomc_2026_12",
        "title": "Federal Reserve FOMC meeting",
        "region": "United States",
        "category": "central_bank",
        "start_at": "2026-12-08",
        "end_at": "2026-12-09",
        "decision_at": "2026-12-09T14:00:00-05:00",
        "timezone": "America/New_York",
        "source_key": "fomc_calendar",
    },
    {
        "key": "us_cpi_2026_12",
        "title": "U.S. CPI release — November 2026",
        "region": "United States",
        "category": "inflation",
        "start_at": "2026-12-10T08:30:00-05:00",
        "timezone": "America/New_York",
        "source_key": "bls_cpi_schedule",
    },
    {
        "key": "india_cpi_2026_12",
        "title": "India CPI release",
        "region": "India",
        "category": "inflation",
        "start_at": "2026-12-12",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
        "note": "Falls on a weekend; the official calendar says holiday releases move to the next working day.",
    },
    {
        "key": "india_iip_2026_12",
        "title": "India IIP release",
        "region": "India",
        "category": "growth",
        "start_at": "2026-12-28",
        "timezone": "Asia/Kolkata",
        "source_key": "mospi_release_calendar",
    },
    {
        "key": "rbi_mpc_2027_02",
        "title": "RBI Monetary Policy Committee meeting",
        "region": "India",
        "category": "central_bank",
        "start_at": "2027-02-03",
        "end_at": "2027-02-05",
        "timezone": "Asia/Kolkata",
        "source_key": "rbi_mpc_calendar",
        "note": "Official schedule confirms the meeting dates; it does not specify the policy-decision time.",
    },
)
REGIME_LABEL_THRESHOLDS = {
    "positive_market": 0.55,
    "cautiously_positive": 0.20,
    "weak_market": -0.20,
    "high_risk_market": -0.55,
}
RBI_HOME_URL = "https://www.rbi.org.in/"
RBI_MACRO_SOURCE = "Reserve Bank of India current rates; FX source FBIL"
RBI_HISTORICAL_SERIES_SOURCES = (
    {
        "series_key": "bse_sensex_annual_average",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8656",
        "title": "RBI Handbook 2006 Table 106: Annual averages of share price indices and market capitalisation",
        "vintage_date": date(2006, 9, 18),
        "value_column": 1,
        "unit": "Index average",
    },
    {
        "series_key": "bse_sensex_annual_average",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=23910",
        "title": "RBI Handbook 2026 Table 85: Annual Averages of Share Price Indices and Market Capitalisation",
        "vintage_date": date(2026, 7, 31),
        "value_column": 1,
        "unit": "Index average",
    },
    {
        "series_key": "india_wpi_all_commodities_annual_average",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=23858",
        "title": "RBI Handbook 2026 Table 33: Wholesale Price Index - Annual Average",
        "vintage_date": date(2026, 7, 31),
        "value_column": 1,
        "unit": "Index average",
    },
    {
        "series_key": "india_real_gdp_growth_pct",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8787",
        "title": "RBI Handbook 2006 Table 237: Select macro-economic aggregates at constant prices",
        "vintage_date": date(2006, 9, 18),
        "value_column": 1,
        "unit": "Per cent annual growth",
        "aggregation": "published annual growth rate",
        "allow_non_positive": True,
    },
    {
        "series_key": "india_call_money_rate_annual",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8624",
        "title": "RBI Handbook 2006 Table 74: Structure of interest rates",
        "vintage_date": date(2006, 9, 18),
        "value_column": 1,
        "unit": "Per cent per annum",
        "aggregation": "financial-year annual rate",
    },
    {
        "series_key": "india_call_money_rate_annual",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=23884",
        "title": "RBI Handbook 2026 Table 59: Structure of interest rates",
        "vintage_date": date(2026, 7, 31),
        "value_column": 1,
        "unit": "Per cent per annum",
        "aggregation": "financial-year annual rate",
        "maximum_end_year": 2026,
    },
    {
        "series_key": "inr_usd_annual_average",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8704",
        "title": "RBI Handbook 2006 Table 154: Financial-year exchange rates",
        "vintage_date": date(2006, 9, 18),
        "value_column": 3,
        "unit": "Indian rupees per US dollar",
    },
    {
        "series_key": "inr_usd_annual_average",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=23958",
        "title": "RBI Handbook 2026 Table 133: Financial-year exchange rates",
        "vintage_date": date(2026, 7, 31),
        "value_column": 3,
        "unit": "Indian rupees per US dollar",
    },
    {
        "series_key": "central_gross_fiscal_deficit_pct_gdp",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=24062",
        "title": "RBI Handbook 2026 Table 237: Central government fiscal indicators as percentage to GDP",
        "vintage_date": date(2026, 7, 31),
        "value_column": 1,
        "unit": "Per cent of GDP",
        "aggregation": "financial-year fiscal ratio",
        "base_period": "Not applicable",
        "maximum_end_year": 2025,
        "duplicate_resolution": "first",
    },
    {
        "series_key": "india_foreign_exchange_reserves_usd_mn",
        "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=22624",
        "title": "RBI Handbook 2024 Table 150: Foreign exchange reserves",
        "vintage_date": date(2024, 9, 13),
        "value_column": 10,
        "unit": "US dollar million",
        "aggregation": "end of financial year stock",
        "base_period": "Not applicable",
        "maximum_end_year": 2024,
    },
)
RBI_HISTORICAL_SERIES_SOURCE = "Reserve Bank of India Handbook of Statistics on Indian Economy"
KITE_FUTURES_SOURCE = "Kite Connect NFO completed daily price and open interest"
NIFTY_INDICES_PUBLIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HISTORICAL_URL_TEMPLATE = "https://api.kite.trade/instruments/historical/{instrument_token}/day"
BASE_INDEX = ("Nifty 50", "NSE:NIFTY 50")
DASHBOARD_EOD_INDICES = ("Nifty 50", "Nifty Bank", "Nifty IT", "Nifty Energy", "India VIX")
OFFICIAL_SECTORAL_INDICES = (
    "Nifty Auto",
    "Nifty Bank",
    "Nifty Capital Goods",
    "Nifty Cement",
    "Nifty Chemicals",
    "Nifty Commercial & Transport Services",
    "Nifty Construction",
    "Nifty Consumer Durables",
    "Nifty Consumer Services",
    "Nifty Financial Services",
    "Nifty Financial Services 25/50",
    "Nifty Financial Services Ex Bank",
    "Nifty FMCG",
    "Nifty Healthcare",
    "Nifty Hospitals",
    "Nifty Housing Finance",
    "Nifty Insurance",
    "Nifty IT",
    "Nifty Media",
    "Nifty Metal",
    "Nifty NBFC",
    "Nifty Oil and Gas",
    "Nifty Pharma",
    "Nifty Power",
    "Nifty Private Bank",
    "Nifty PSU Bank",
    "Nifty Realty",
    "Nifty REITs & Realty",
    "Nifty Retail",
    "Nifty Telecommunications",
    "Nifty500 Healthcare",
    "Nifty MidSmall Financial Services",
    "Nifty MidSmall Healthcare",
    "Nifty MidSmall IT & Telecom",
)
INDEX_NAME_ALIASES = {
    "Nifty Consumer Durables": ("NIFTY CONSR DURBL",),
    "Nifty Financial Services": ("NIFTY FIN SERVICE",),
    "Nifty Financial Services Ex Bank": ("NIFTY FINSRV EX-BANK",),
    "Nifty Private Bank": ("NIFTY PVT BANK",),
    "Nifty Telecommunications": ("NIFTY TELECOM",),
    "Nifty MidSmall Financial Services": ("NIFTY MIDSML FIN SERV",),
    "Nifty MidSmall Healthcare": ("NIFTY MIDSML HEALTHCARE",),
    "Nifty MidSmall IT & Telecom": ("NIFTY MIDSML IT & TELECOM",),
}
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
NSDL_MAX_RESPONSE_BYTES = 512 * 1024
FRED_MAX_RESPONSE_BYTES = 512 * 1024
RBI_MAX_RESPONSE_BYTES = 1024 * 1024
MAX_HISTORICAL_RESPONSE_BYTES = 512 * 1024
MAX_INSTRUMENT_BYTES = 8 * 1024 * 1024
MAX_NFO_INSTRUMENT_BYTES = 32 * 1024 * 1024
MAX_QUOTE_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CONSTITUENT_BYTES = 128 * 1024
MAX_NEWS_IMPORT_BYTES = 2 * 1024 * 1024
MAX_EARNINGS_IMPORT_BYTES = 4 * 1024 * 1024
MAX_PORTFOLIO_IMPORT_BYTES = 12 * 1024 * 1024
MAX_PORTFOLIO_FILE_BYTES = 8 * 1024 * 1024
MAX_PORTFOLIO_ROWS = 5000
MAX_PORTFOLIO_COLUMNS = 100
MAX_GOOGLE_FINANCE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_GOOGLE_FINANCE_SYMBOLS = 100
MAX_NIFTY_GSEC_RESPONSE_BYTES = 512 * 1024
MAX_AMFI_NAV_RESPONSE_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10
BREADTH_CACHE_SECONDS = 15 * 60
SEASONALITY_CACHE_SECONDS = 15 * 60
GOOGLE_FINANCE_CACHE_SECONDS = 5 * 60
NIFTY_GSEC_CACHE_SECONDS = 6 * 60 * 60
AMFI_NAV_CACHE_SECONDS = 6 * 60 * 60
AMFI_NAV_LOOKBACK_DAYS = 300
AMFI_NAV_CHUNK_DAYS = 90
HISTORICAL_LOOKBACK_DAYS = 420
NIFTY500_HISTORY_LOOKBACK_DAYS = 1800
SEASONALITY_LOOKBACK_YEARS = 10
SEASONALITY_HISTORY_CHUNK_DAYS = 1800
HISTORICAL_REQUEST_INTERVAL_SECONDS = 0.36
FNO_UNIVERSE_EXPECTED = 210
SCREENER_READY_SESSIONS = 252
PRICE_STRENGTH_SERIES_SESSIONS = 126
FUTURES_PRICE_NOISE_PCT = 0.25
FUTURES_OI_NOISE_PCT = 1.0
FUTURES_MAX_COMPARISON_GAP_DAYS = 4
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")

SEASONALITY_INDICES = (
    "Nifty 50",
    "Nifty Auto",
    "Nifty Bank",
    "Nifty Chemicals",
    "Nifty Consumer Durables",
    "Nifty Energy",
    "Nifty Financial Services",
    "Nifty FMCG",
    "Nifty Healthcare",
    "Nifty IT",
    "Nifty Media",
    "Nifty Metal",
    "Nifty Oil and Gas",
    "Nifty Pharma",
    "Nifty Private Bank",
    "Nifty PSU Bank",
    "Nifty Realty",
    "Nifty MidSmall Financial Services",
    "Nifty MidSmall IT & Telecom",
)

_ACTIVE_KITE_SESSION: dict[str, str] = {}
_ACTIVE_INDEX_TARGETS: list[tuple[str, str, str]] = []
_ACTIVE_DASHBOARD_INDEX_TOKENS: dict[str, str] = {}
_ACTIVE_SEASONALITY_INDEX_TOKENS: dict[str, str] = {}
_ACTIVE_EQUITY_TOKENS: dict[str, str] = {}
_KITE_DIAGNOSTICS: dict[str, str | None] = {"last_error": None}
_BREADTH_CACHE: dict[str, object] = {}
_SEASONALITY_CACHE: dict[tuple[str, str], dict[str, object]] = {}
_MONTHLY_EQUITY_RETURNS_CACHE: dict[str, object] = {}
_MONTHLY_LEADERS_CACHE: dict[str, object] = {}
_HISTORICAL_MONTH_LEADERS_CACHE: dict[str, object] = {}
_REGIME_VALIDATION_CACHE: dict[str, object] = {}
_CROSS_INDEX_VALIDATION_CACHE: dict[str, object] = {}
_NIFTY_GSEC_HISTORY_CACHE: dict[str, object] = {}
_GOOGLE_FINANCE_QUOTE_CACHE: dict[str, dict[str, object]] = {}
_AMFI_NAV_HISTORY_CACHE: dict[str, object] = {}
_SESSION_LOCK = threading.Lock()
_BREADTH_BUILD_LOCK = threading.Lock()
_HISTORICAL_MONTH_LEADERS_LOCK = threading.Lock()
_REGIME_VALIDATION_LOCK = threading.Lock()
_CROSS_INDEX_VALIDATION_LOCK = threading.Lock()
_EOD_STORE: EODStore | None = None


def _get_eod_store() -> EODStore:
    global _EOD_STORE
    if _EOD_STORE is None:
        _EOD_STORE = EODStore(Path(__file__).resolve().parent / "data" / "pg_terminal_eod.sqlite3")
    return _EOD_STORE


def load_index_constituent_snapshot() -> dict[str, object]:
    path = Path(__file__).resolve().parent / "data" / "index_constituents.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("index_constituent_snapshot_unavailable") from error
    indices = payload.get("indices") if isinstance(payload, dict) else None
    if not isinstance(indices, dict):
        raise ValueError("index_constituent_snapshot_unavailable")
    normalized: dict[str, list[str]] = {}
    for index_name, symbols in indices.items():
        if index_name not in SEASONALITY_INDICES or not isinstance(symbols, list):
            continue
        clean_symbols = sorted(
            {
                str(symbol).strip()
                for symbol in symbols
                if isinstance(symbol, str) and str(symbol).strip()
            }
        )
        if clean_symbols:
            normalized[str(index_name)] = clean_symbols
    normalized_history: dict[str, list[dict[str, object]]] = {}
    raw_history = payload.get("history") if isinstance(payload, dict) else None
    if isinstance(raw_history, dict):
        for index_name, snapshots in raw_history.items():
            if index_name not in SEASONALITY_INDICES or not isinstance(snapshots, list):
                continue
            clean_snapshots: list[dict[str, object]] = []
            for snapshot in snapshots:
                if not isinstance(snapshot, dict) or not isinstance(snapshot.get("symbols"), list):
                    continue
                try:
                    effective_from = date.fromisoformat(str(snapshot.get("effective_from")))
                    effective_to = (
                        date.fromisoformat(str(snapshot.get("effective_to")))
                        if snapshot.get("effective_to") else None
                    )
                except ValueError:
                    continue
                if effective_to is not None and effective_to < effective_from:
                    continue
                symbols = sorted(
                    {
                        str(symbol).strip()
                        for symbol in snapshot["symbols"]
                        if isinstance(symbol, str) and str(symbol).strip()
                    }
                )
                if symbols:
                    clean_snapshots.append(
                        {
                            "effective_from": effective_from,
                            "effective_to": effective_to,
                            "symbols": symbols,
                        }
                    )
            if clean_snapshots:
                normalized_history[str(index_name)] = sorted(
                    clean_snapshots, key=lambda item: item["effective_from"]
                )
    return {
        "as_of": payload.get("as_of"),
        "source": payload.get("source"),
        "membership_type": payload.get("membership_type"),
        "indices": normalized,
        "history": normalized_history,
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_PROVIDER_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def extract_request_token(value: str) -> str:
    """Accept a raw request token or the full registered redirect URL."""
    candidate = value.strip()
    if not candidate:
        return ""
    if "://" not in candidate and "request_token=" not in candidate:
        return candidate

    parsed = urllib.parse.urlparse(candidate if "://" in candidate else f"https://local/?{candidate}")
    values = urllib.parse.parse_qs(parsed.query).get("request_token", [])
    return values[0].strip() if len(values) == 1 else ""


def build_checksum(api_key: str, request_token: str, api_secret: str) -> str:
    return hashlib.sha256(f"{api_key}{request_token}{api_secret}".encode("utf-8")).hexdigest()


def classify_network_error(error: BaseException) -> str:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "provider_timeout"
    if isinstance(reason, ssl.SSLError):
        return "provider_tls_failure"
    if isinstance(reason, socket.gaierror):
        return "provider_dns_failure"
    if isinstance(reason, PermissionError) or getattr(reason, "winerror", None) == 10013:
        return "provider_network_blocked"
    return "provider_connection_failed"


def parse_nifty500_constituents(csv_payload: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_constituent_file")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in reader:
        symbol = (row.get("Symbol") or "").strip().upper()
        company_name = (row.get("Company Name") or "").strip()
        industry = (row.get("Industry") or "").strip()
        series = (row.get("Series") or "").strip().upper()
        # The official NIFTY 500 universe includes listed REIT units in the
        # NSE ``RR`` series in addition to ordinary ``EQ``/``BE`` securities.
        if (
            not symbol
            or not company_name
            or not industry
            or series not in {"EQ", "BE", "RR"}
            or symbol in seen
        ):
            raise ValueError("invalid_constituent_file")
        seen.add(symbol)
        rows.append({"symbol": symbol, "name": company_name, "sector": industry})
    # NIFTY 500 is a 500-company index. Its official constituent file can
    # contain 501 securities when a constituent is represented by an
    # additional eligible series, so preserve the official file as published.
    if len(rows) not in {500, 501}:
        raise ValueError("unexpected_constituent_count")
    return rows


def parse_equity_tokens(csv_payload: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"instrument_token", "tradingsymbol", "instrument_type", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")
    tokens: dict[str, str] = {}
    for row in reader:
        if (
            row.get("exchange") != "NSE"
            or row.get("segment") != "NSE"
            or row.get("instrument_type") != "EQ"
        ):
            continue
        symbol = (row.get("tradingsymbol") or "").strip().upper()
        token = (row.get("instrument_token") or "").strip()
        if symbol and token.isdigit():
            tokens.setdefault(symbol, token)
    if not tokens:
        raise ValueError("invalid_instrument_master")
    return tokens


def parse_near_month_stock_futures(
    csv_payload: str,
    symbols: tuple[str, ...],
    *,
    as_of: date,
) -> tuple[list[dict[str, object]], list[str]]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {
        "instrument_token", "tradingsymbol", "name", "expiry", "lot_size",
        "instrument_type", "segment", "exchange",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_nfo_instrument_master")
    requested = set(symbols)
    candidates: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in symbols}
    for row in reader:
        if (
            row.get("exchange") != "NFO"
            or row.get("segment") != "NFO-FUT"
            or row.get("instrument_type") != "FUT"
        ):
            continue
        underlying = (row.get("name") or "").strip().upper()
        if underlying not in requested:
            continue
        token = (row.get("instrument_token") or "").strip()
        tradingsymbol = (row.get("tradingsymbol") or "").strip().upper()
        try:
            expiry = date.fromisoformat((row.get("expiry") or "").strip())
            lot_size = int((row.get("lot_size") or "").strip())
        except ValueError:
            continue
        if not token.isdigit() or not tradingsymbol or expiry < as_of or lot_size <= 0:
            continue
        candidates[underlying].append(
            {
                "underlying": underlying,
                "tradingsymbol": tradingsymbol,
                "exchange": "NFO",
                "instrument_token": token,
                "expiry": expiry,
                "lot_size": lot_size,
            }
        )
    selected = [
        min(candidates[symbol], key=lambda item: (item["expiry"], item["tradingsymbol"]))
        for symbol in symbols
        if candidates[symbol]
    ]
    selected.sort(key=lambda item: item["underlying"])
    missing = [symbol for symbol in symbols if not candidates[symbol]]
    return selected, missing


def normalize_futures_eod_quotes(
    provider_payload: dict[str, object],
    contracts: list[dict[str, object]],
    *,
    now: datetime,
) -> tuple[list[dict[str, object]], list[str]]:
    local_now = now.astimezone(INDIA_TIMEZONE)
    if local_now.time().replace(tzinfo=None) < datetime_time(15, 40):
        raise ValueError("futures_eod_not_due")
    data = provider_payload.get("data")
    if provider_payload.get("status") != "success" or not isinstance(data, dict):
        raise ValueError("invalid_futures_quote_response")
    snapshots: list[dict[str, object]] = []
    missing: list[str] = []
    for contract in contracts:
        key = f"NFO:{contract['tradingsymbol']}"
        quote = data.get(key)
        if not isinstance(quote, dict):
            missing.append(str(contract["underlying"]))
            continue
        ohlc = quote.get("ohlc")
        timestamp = quote.get("timestamp") or quote.get("last_trade_time")
        raw_values = (
            ohlc.get("open") if isinstance(ohlc, dict) else None,
            ohlc.get("high") if isinstance(ohlc, dict) else None,
            ohlc.get("low") if isinstance(ohlc, dict) else None,
            quote.get("last_price"),
        )
        volume = quote.get("volume")
        open_interest = quote.get("oi")
        try:
            session_date = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).date()
        except ValueError:
            missing.append(str(contract["underlying"]))
            continue
        if (
            not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0
                for value in raw_values
            )
            or not isinstance(volume, (int, float))
            or isinstance(volume, bool)
            or int(volume) < 0
            or float(volume) != int(volume)
            or not isinstance(open_interest, (int, float))
            or isinstance(open_interest, bool)
            or int(open_interest) < 0
            or float(open_interest) != int(open_interest)
            or session_date != local_now.date()
        ):
            missing.append(str(contract["underlying"]))
            continue
        open_price, high, low, close = (float(value) for value in raw_values)
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            missing.append(str(contract["underlying"]))
            continue
        snapshots.append(
            {
                "contract_key": key,
                "date": session_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": int(volume),
                "open_interest": int(open_interest),
            }
        )
    return snapshots, missing


def parse_futures_daily_snapshot(
    provider_payload: dict[str, object],
    contract: dict[str, object],
    *,
    completed_through: date,
) -> dict[str, object] | None:
    data = provider_payload.get("data")
    candles = data.get("candles") if isinstance(data, dict) else None
    if provider_payload.get("status") != "success" or not isinstance(candles, list):
        raise ValueError("invalid_futures_history_response")
    parsed: list[dict[str, object]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 7 or not isinstance(candle[0], str):
            raise ValueError("invalid_futures_history_response")
        try:
            session_date = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).date()
        except ValueError as error:
            raise ValueError("invalid_futures_history_response") from error
        if session_date > completed_through:
            continue
        raw_prices = candle[1:5]
        volume = candle[5]
        open_interest = candle[6]
        if (
            not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0
                for value in raw_prices
            )
            or not isinstance(volume, (int, float))
            or isinstance(volume, bool)
            or float(volume) != int(volume)
            or int(volume) < 0
            or not isinstance(open_interest, (int, float))
            or isinstance(open_interest, bool)
            or float(open_interest) != int(open_interest)
            or int(open_interest) < 0
        ):
            raise ValueError("invalid_futures_history_response")
        open_price, high, low, close = (float(value) for value in raw_prices)
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise ValueError("invalid_futures_history_response")
        parsed.append(
            {
                "contract_key": f"NFO:{contract['tradingsymbol']}",
                "date": session_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": int(volume),
                "open_interest": int(open_interest),
            }
        )
    return max(parsed, key=lambda item: item["date"]) if parsed else None


def calculate_futures_oi_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "available": False,
            "reason": "Run EOD update after market close to establish the near-month futures baseline.",
        }
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["underlying"]), []).append(row)
    latest_date = max(row["date"] for row in rows)
    comparable = 0
    baseline_only = 0
    rollover_baseline = 0
    latest_rows = 0
    eligible = 0
    stale_gap_count = 0
    liquidity_excluded_count = 0
    states: list[dict[str, object]] = []
    state_counts = {
        "long_build_up": 0,
        "short_build_up": 0,
        "long_unwinding": 0,
        "short_covering": 0,
        "no_clear_signal": 0,
    }
    for underlying_rows in grouped.values():
        ordered = sorted(underlying_rows, key=lambda item: (item["date"], item["expiry"]))
        latest = ordered[-1]
        if latest["date"] != latest_date:
            continue
        latest_rows += 1
        prior = next((item for item in reversed(ordered[:-1]) if item["date"] < latest_date), None)
        if prior is None:
            baseline_only += 1
        elif prior["contract_key"] != latest["contract_key"]:
            rollover_baseline += 1
        else:
            comparable += 1
            prior_close = float(prior["close"])
            prior_oi = int(prior["open_interest"])
            current_close = float(latest["close"])
            current_oi = int(latest["open_interest"])
            gap_days = (latest["date"] - prior["date"]).days
            if gap_days > FUTURES_MAX_COMPARISON_GAP_DAYS:
                stale_gap_count += 1
                continue
            if prior_oi <= 0 or current_oi <= 0 or int(latest["volume"]) <= 0:
                liquidity_excluded_count += 1
                continue
            eligible += 1
            price_change = (current_close / prior_close - 1) * 100
            oi_change = (current_oi / prior_oi - 1) * 100
            if abs(price_change) < FUTURES_PRICE_NOISE_PCT or abs(oi_change) < FUTURES_OI_NOISE_PCT:
                state = "no_clear_signal"
            elif price_change > 0 and oi_change > 0:
                state = "long_build_up"
            elif price_change < 0 and oi_change > 0:
                state = "short_build_up"
            elif price_change < 0 and oi_change < 0:
                state = "long_unwinding"
            elif price_change > 0 and oi_change < 0:
                state = "short_covering"
            else:
                state = "no_clear_signal"
            state_counts[state] += 1
            states.append(
                {
                    "underlying": latest["underlying"],
                    "tradingsymbol": latest["tradingsymbol"],
                    "expiry": latest["expiry"].isoformat(),
                    "from_date": prior["date"].isoformat(),
                    "to_date": latest["date"].isoformat(),
                    "calendar_gap_days": gap_days,
                    "price_change_pct": round(price_change, 2),
                    "oi_change_pct": round(oi_change, 2),
                    "volume": int(latest["volume"]),
                    "open_interest": current_oi,
                    "state": state,
                }
            )
    states.sort(key=lambda item: (-abs(float(item["oi_change_pct"])), str(item["underlying"])))
    return {
        "available": True,
        "as_of_date": latest_date.isoformat(),
        "stored_underlyings": len(grouped),
        "expected_universe": FNO_UNIVERSE_EXPECTED,
        "latest_coverage": latest_rows,
        "latest_coverage_pct": round(100 * latest_rows / FNO_UNIVERSE_EXPECTED, 1),
        "latest_missing_count": max(0, FNO_UNIVERSE_EXPECTED - latest_rows),
        "comparable_count": comparable,
        "eligible_count": eligible,
        "baseline_only_count": baseline_only,
        "rollover_baseline_count": rollover_baseline,
        "stale_gap_count": stale_gap_count,
        "liquidity_excluded_count": liquidity_excluded_count,
        "classification_status": "descriptive_only" if eligible else "withheld",
        "state_counts": state_counts,
        "states": states,
        "safeguards": {
            "minimum_absolute_price_change_pct": FUTURES_PRICE_NOISE_PCT,
            "minimum_absolute_oi_change_pct": FUTURES_OI_NOISE_PCT,
            "maximum_calendar_gap_days": FUTURES_MAX_COMPARISON_GAP_DAYS,
            "requires_positive_volume_and_oi": True,
            "regime_score_enabled": False,
        },
        "definition": "Price and OI direction between two eligible stored observations of the same contract; descriptive only.",
        "reason": (
            "Same-contract price/OI quadrants are visible as descriptive evidence and do not affect the regime score."
            if eligible
            else "Contract-specific price and OI are stored; a second same-contract observation is required."
        ),
    }


def build_index_futures_confirmation(
    constituent_symbols: list[str],
    *,
    fno_constituent_count: int,
    futures_summary: dict[str, object],
    history_ready: bool,
    current_state_date: str | None,
) -> dict[str, object]:
    """Gate short research with mature history and same-session bearish F&O breadth."""
    states = futures_summary.get("states")
    states = states if isinstance(states, list) else []
    constituents = set(constituent_symbols)
    selected = [
        item
        for item in states
        if isinstance(item, dict) and str(item.get("underlying") or "") in constituents
    ]
    clear_states = [item for item in selected if item.get("state") != "no_clear_signal"]
    bearish_states = [
        item
        for item in clear_states
        if item.get("state") in {"short_build_up", "long_unwinding"}
    ]
    bullish_states = [
        item
        for item in clear_states
        if item.get("state") in {"long_build_up", "short_covering"}
    ]
    denominator = max(1, int(fno_constituent_count))
    coverage_pct = 100 * len(selected) / denominator
    bearish_share_pct = (
        100 * len(bearish_states) / len(clear_states) if clear_states else 0.0
    )
    same_session = bool(
        current_state_date
        and futures_summary.get("as_of_date") == current_state_date
    )
    current_confirmation_ready = bool(
        same_session
        and len(clear_states) >= REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT
        and coverage_pct >= REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT
    )
    bearish_confirmation = bool(
        current_confirmation_ready
        and bearish_share_pct >= REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT
    )
    if not history_ready:
        status = "history_accumulating"
    elif not current_confirmation_ready:
        status = "current_confirmation_unavailable"
    elif bearish_confirmation:
        status = "bearish_confirmation_present"
    else:
        status = "bearish_confirmation_absent"
    return {
        "history_ready": bool(history_ready),
        "current_confirmation_ready": current_confirmation_ready,
        "bearish_confirmation": bearish_confirmation,
        "short_gate_passed": bool(history_ready and bearish_confirmation),
        "status": status,
        "as_of_date": futures_summary.get("as_of_date"),
        "same_session_as_current_state": same_session,
        "eligible_constituent_states": len(selected),
        "clear_directional_states": len(clear_states),
        "bearish_states": len(bearish_states),
        "bullish_states": len(bullish_states),
        "coverage_pct": round(coverage_pct, 1),
        "bearish_share_pct": round(bearish_share_pct, 1),
        "contract": {
            "minimum_history_sessions": REGIME_EXTERNAL_HISTORY_SESSIONS,
            "minimum_clear_constituent_states": REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT,
            "minimum_constituent_coverage_pct": REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT,
            "minimum_bearish_share_pct": REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT,
            "bearish_states": ["short_build_up", "long_unwinding"],
            "status": "confirmation_gate_not_trading_signal",
        },
    }


def parse_dashboard_index_tokens(csv_payload: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"instrument_token", "tradingsymbol", "name", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")
    inventory: dict[str, str] = {}
    for row in reader:
        if row.get("exchange") != "NSE" or row.get("segment") != "INDICES":
            continue
        token = (row.get("instrument_token") or "").strip()
        if not token.isdigit():
            continue
        for candidate in ((row.get("tradingsymbol") or ""), (row.get("name") or "")):
            if candidate.strip():
                inventory.setdefault(normalize_index_name(candidate), token)
    result: dict[str, str] = {}
    for display_name in DASHBOARD_EOD_INDICES:
        candidates = (display_name, *INDEX_NAME_ALIASES.get(display_name, ()))
        token = next(
            (
                inventory[normalize_index_name(candidate)]
                for candidate in candidates
                if normalize_index_name(candidate) in inventory
            ),
            None,
        )
        if token is None:
            raise ValueError("dashboard_index_not_available")
        result[display_name] = token
    return result


def parse_seasonality_index_tokens(csv_payload: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"instrument_token", "tradingsymbol", "name", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")
    inventory: dict[str, str] = {}
    for row in reader:
        if row.get("exchange") != "NSE" or row.get("segment") != "INDICES":
            continue
        token = (row.get("instrument_token") or "").strip()
        if not token.isdigit():
            continue
        for candidate in ((row.get("tradingsymbol") or ""), (row.get("name") or "")):
            if candidate.strip():
                inventory.setdefault(normalize_index_name(candidate), token)
    result: dict[str, str] = {}
    for display_name in SEASONALITY_INDICES:
        candidates = (display_name, *INDEX_NAME_ALIASES.get(display_name, ()))
        token = next(
            (
                inventory[normalize_index_name(candidate)]
                for candidate in candidates
                if normalize_index_name(candidate) in inventory
            ),
            None,
        )
        if token is not None:
            result[display_name] = token
    if "Nifty 50" not in result:
        raise ValueError("invalid_instrument_master")
    return result


def parse_daily_closes(
    provider_payload: dict[str, object],
    *,
    today: date,
    now_time: datetime_time,
) -> list[tuple[date, float]]:
    data = provider_payload.get("data")
    candles = data.get("candles") if isinstance(data, dict) else None
    if provider_payload.get("status") != "success" or not isinstance(candles, list):
        raise ValueError("invalid_provider_response")
    allow_today = now_time >= datetime_time(15, 40)
    parsed: list[tuple[date, float]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 5 or not isinstance(candle[0], str):
            raise ValueError("invalid_provider_response")
        close = candle[4]
        if not isinstance(close, (int, float)) or isinstance(close, bool) or not math.isfinite(float(close)):
            raise ValueError("invalid_provider_response")
        try:
            candle_date = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).date()
        except ValueError as error:
            raise ValueError("invalid_provider_response") from error
        if candle_date < today or allow_today:
            parsed.append((candle_date, float(close)))
    parsed.sort(key=lambda item: item[0])
    return parsed


def parse_daily_candles(
    provider_payload: dict[str, object],
    *,
    today: date,
    now_time: datetime_time,
) -> list[dict[str, object]]:
    data = provider_payload.get("data")
    candles = data.get("candles") if isinstance(data, dict) else None
    if provider_payload.get("status") != "success" or not isinstance(candles, list):
        raise ValueError("invalid_provider_response")
    allow_today = now_time >= datetime_time(15, 40)
    parsed: list[dict[str, object]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 5 or not isinstance(candle[0], str):
            raise ValueError("invalid_provider_response")
        try:
            candle_date = datetime.fromisoformat(candle[0].replace("Z", "+00:00")).date()
        except ValueError as error:
            raise ValueError("invalid_provider_response") from error
        values = candle[1:5]
        numeric_values = all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in values
        )
        if not numeric_values:
            raise ValueError("invalid_provider_response")
        if all(float(value) == 0 for value in values):
            continue
        if not all(float(value) > 0 for value in values):
            raise ValueError("invalid_provider_response")
        open_price, high, low, close = (float(value) for value in values)
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            raise ValueError("invalid_provider_response")
        if candle_date < today or allow_today:
            parsed.append(
                {
                    "date": candle_date,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                }
            )
    parsed.sort(key=lambda item: item["date"])
    return parsed


def historical_date_ranges(
    start: date,
    end: date,
    *,
    chunk_days: int = SEASONALITY_HISTORY_CHUNK_DAYS,
) -> list[tuple[date, date]]:
    if chunk_days < 1 or start > end:
        raise ValueError("invalid_history_range")
    ranges: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges


def historical_lookback_start(as_of: date, *, years: int = SEASONALITY_LOOKBACK_YEARS) -> date:
    if years < 1:
        raise ValueError("invalid_history_range")
    try:
        return as_of.replace(year=as_of.year - years)
    except ValueError:
        return as_of.replace(year=as_of.year - years, day=28)


def incremental_history_ranges(
    history_start: date,
    end: date,
    last_stored: date | None,
    *,
    chunk_days: int = SEASONALITY_HISTORY_CHUNK_DAYS,
) -> list[tuple[date, date]]:
    start = max(history_start, last_stored + timedelta(days=1)) if last_stored else history_start
    if start > end:
        return []
    return historical_date_ranges(start, end, chunk_days=chunk_days)


def completed_history_date(now: datetime) -> date:
    """Return the latest date that may contain a completed daily candle."""
    local_now = now.astimezone(INDIA_TIMEZONE)
    if local_now.time().replace(tzinfo=None) < datetime_time(15, 40):
        return local_now.date() - timedelta(days=1)
    return local_now.date()


def is_complete_seasonality_payload(payload: object) -> bool:
    """Keep ranking-only cache entries out of full seasonality responses."""
    return (
        isinstance(payload, dict)
        and payload.get("ok") is True
        and isinstance(payload.get("month_rows"), list)
        and isinstance(payload.get("weekday_rows"), list)
        and isinstance(payload.get("validation"), dict)
    )


def _seasonality_summary(values: list[tuple[float, float]]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "average_return_pct": None,
            "average_range_pct": None,
            "highest_return_pct": None,
            "lowest_return_pct": None,
        }
    returns = [item[0] for item in values]
    ranges = [item[1] for item in values]
    return {
        "count": len(values),
        "average_return_pct": round(sum(returns) / len(returns), 2),
        "average_range_pct": round(sum(ranges) / len(ranges), 2),
        "highest_return_pct": round(max(returns), 2),
        "lowest_return_pct": round(min(returns), 2),
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sample_variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    average = sum(values) / len(values)
    return sum((value - average) ** 2 for value in values) / (len(values) - 1)


def _percentile(values: list[float], percentile: float) -> float:
    if not values or not 0 <= percentile <= 100:
        raise ValueError("invalid_percentile_input")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_regime_risk_profile(
    observations: list[dict[str, object]],
    *,
    horizon_sessions: int,
    orientation: str,
) -> dict[str, object]:
    """Summarize outcome tails and entry-relative adverse distance without sizing advice."""
    if horizon_sessions <= 0 or orientation not in {"long", "short"}:
        raise ValueError("invalid_regime_risk_profile_contract")
    key = str(horizon_sessions)
    return_key = "forward_returns_pct"
    adverse_key = (
        "forward_long_adverse_excursions_pct"
        if orientation == "long"
        else "forward_short_adverse_excursions_pct"
    )
    position_returns: list[float] = []
    adverse_distances: list[float] = []
    for observation in observations:
        raw_returns = observation.get(return_key)
        raw_adverse = observation.get(adverse_key)
        if not isinstance(raw_returns, dict) or not isinstance(raw_adverse, dict):
            continue
        outcome = raw_returns.get(key)
        adverse = raw_adverse.get(key)
        if not isinstance(outcome, (int, float)) or not isinstance(adverse, (int, float)):
            continue
        position_returns.append(float(outcome) if orientation == "long" else -float(outcome))
        adverse_distances.append(float(adverse))
    if not position_returns:
        return {
            "available": False,
            "orientation": orientation,
            "horizon_sessions": horizon_sessions,
            "observations": 0,
        }
    breach_rates = {
        f"{distance:g}": round(
            100 * sum(value >= distance for value in adverse_distances) / len(adverse_distances),
            1,
        )
        for distance in REGIME_ADVERSE_DISTANCE_LEVELS_PCT
    }
    return {
        "available": True,
        "orientation": orientation,
        "horizon_sessions": horizon_sessions,
        "observations": len(position_returns),
        "tail_percentile": REGIME_RISK_TAIL_PERCENTILE,
        "tail_position_return_pct": round(
            _percentile(position_returns, REGIME_RISK_TAIL_PERCENTILE), 2
        ),
        "median_position_return_pct": round(median(position_returns), 2),
        "worst_position_return_pct": round(min(position_returns), 2),
        "median_adverse_excursion_pct": round(median(adverse_distances), 2),
        "tail_adverse_excursion_pct": round(
            _percentile(adverse_distances, 100 - REGIME_RISK_TAIL_PERCENTILE), 2
        ),
        "worst_adverse_excursion_pct": round(max(adverse_distances), 2),
        "adverse_distance_breach_rates_pct": breach_rates,
        "distance_levels_pct": list(REGIME_ADVERSE_DISTANCE_LEVELS_PCT),
        "status": "historical_risk_evidence_not_stop_recommendation",
    }


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 200
    epsilon = 3e-14
    minimum = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < minimum:
        d = minimum
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        twice = 2 * iteration
        coefficient = iteration * (b - iteration) * x / ((qam + twice) * (a + twice))
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        result *= d * c
        coefficient = -(a + iteration) * (qab + iteration) * x / ((a + twice) * (qap + twice))
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return result


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _welch_test(first: list[float], second: list[float]) -> tuple[float | None, float | None]:
    first_variance = _sample_variance(first)
    second_variance = _sample_variance(second)
    if first_variance is None or second_variance is None:
        return None, None
    first_term = first_variance / len(first)
    second_term = second_variance / len(second)
    denominator = first_term + second_term
    if denominator <= 0:
        return None, None
    t_statistic = ((_mean(first) or 0.0) - (_mean(second) or 0.0)) / math.sqrt(denominator)
    degrees_of_freedom_denominator = (
        (first_term * first_term) / (len(first) - 1)
        + (second_term * second_term) / (len(second) - 1)
    )
    if degrees_of_freedom_denominator <= 0:
        return None, None
    degrees_of_freedom = denominator * denominator / degrees_of_freedom_denominator
    probability = _regularized_incomplete_beta(
        degrees_of_freedom / 2.0,
        0.5,
        degrees_of_freedom / (degrees_of_freedom + t_statistic * t_statistic),
    )
    return t_statistic, max(0.0, min(1.0, probability))


def _benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    valid = sorted(
        ((value, index) for index, value in enumerate(p_values) if value is not None),
        key=lambda item: item[0],
    )
    adjusted: list[float | None] = [None] * len(p_values)
    running = 1.0
    total = len(valid)
    for rank in range(total, 0, -1):
        value, index = valid[rank - 1]
        running = min(running, value * total / rank)
        adjusted[index] = max(0.0, min(1.0, running))
    return adjusted


def _turn_of_month_analysis(candles: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(candles, key=lambda item: item["date"])
    daily: list[dict[str, object]] = []
    for previous, current in zip(ordered, ordered[1:]):
        daily.append(
            {
                "date": current["date"],
                "return_pct": ((float(current["close"]) / float(previous["close"])) - 1) * 100,
                "in_window": False,
            }
        )
    month_groups: list[list[dict[str, object]]] = []
    for row in daily:
        key = (row["date"].year, row["date"].month)
        if not month_groups or (month_groups[-1][0]["date"].year, month_groups[-1][0]["date"].month) != key:
            month_groups.append([])
        month_groups[-1].append(row)
    for index, group in enumerate(month_groups):
        for row in group[-3:]:
            row["in_window"] = True
        if index + 1 < len(month_groups):
            for row in month_groups[index + 1][:3]:
                row["in_window"] = True

    turn_values = [float(row["return_pct"]) for row in daily if row["in_window"]]
    rest_values = [float(row["return_pct"]) for row in daily if not row["in_window"]]

    def summary(label: str, values: list[float]) -> dict[str, object]:
        ordered_values = sorted(values)
        middle = len(ordered_values) // 2
        median = None
        if ordered_values:
            median = (
                ordered_values[middle]
                if len(ordered_values) % 2
                else (ordered_values[middle - 1] + ordered_values[middle]) / 2
            )
        return {
            "window": label,
            "count": len(values),
            "average_return_pct": round(_mean(values), 2) if values else None,
            "median_return_pct": round(median, 2) if median is not None else None,
            "positive_sessions_pct": round(sum(value > 0 for value in values) / len(values) * 100, 2) if values else None,
        }

    t_statistic, p_value = _welch_test(turn_values, rest_values)
    turn_mean = _mean(turn_values)
    rest_mean = _mean(rest_values)
    return {
        "rows": [summary("Turn of month", turn_values), summary("Rest of month", rest_values)],
        "edge_pct": round(turn_mean - rest_mean, 2) if turn_mean is not None and rest_mean is not None else None,
        "t_statistic": round(t_statistic, 3) if t_statistic is not None else None,
        "p_value": round(p_value, 4) if p_value is not None else None,
    }


def calculate_seasonality_validation(
    candles: list[dict[str, object]],
    *,
    today: date,
) -> dict[str, object]:
    ordered = sorted(candles, key=lambda item: item["date"])
    monthly_buckets: dict[tuple[int, int], list[dict[str, object]]] = {}
    for candle in ordered:
        candle_date = candle["date"]
        monthly_buckets.setdefault((candle_date.year, candle_date.month), []).append(candle)
    completed = [
        (key, rows)
        for key, rows in sorted(monthly_buckets.items())
        if key != (today.year, today.month)
    ]
    monthly_returns: list[dict[str, object]] = []
    previous_close: float | None = None
    for (_year, month), rows in completed:
        month_close = float(rows[-1]["close"])
        if previous_close is not None:
            monthly_returns.append(
                {
                    "date": rows[-1]["date"],
                    "month": month,
                    "return_pct": ((month_close / previous_close) - 1) * 100,
                }
            )
        previous_close = month_close
    if len(monthly_returns) < 4:
        raise ValueError("no_completed_historical_data")

    split_index = len(monthly_returns) // 2
    train = monthly_returns[:split_index]
    test = monthly_returns[split_index:]
    split_date = test[0]["date"].replace(day=1)
    month_names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    intermediate: list[dict[str, object]] = []
    train_p_values: list[float | None] = []
    for month in range(1, 13):
        train_values = [float(row["return_pct"]) for row in train if row["month"] == month]
        train_others = [float(row["return_pct"]) for row in train if row["month"] != month]
        test_values = [float(row["return_pct"]) for row in test if row["month"] == month]
        test_others = [float(row["return_pct"]) for row in test if row["month"] != month]
        _train_t, train_p = _welch_test(train_values, train_others)
        _test_t, test_p = _welch_test(test_values, test_others)
        train_excess = (
            (_mean(train_values) or 0.0) - (_mean(train_others) or 0.0)
            if train_values and train_others else None
        )
        test_excess = (
            (_mean(test_values) or 0.0) - (_mean(test_others) or 0.0)
            if test_values and test_others else None
        )
        train_p_values.append(train_p)
        intermediate.append(
            {
                "period": month_names[month - 1],
                "train_count": len(train_values),
                "train_excess_pct": train_excess,
                "train_p_value": train_p,
                "test_count": len(test_values),
                "test_excess_pct": test_excess,
                "test_p_value": test_p,
                "same_direction": (
                    train_excess is not None and test_excess is not None
                    and train_excess != 0 and test_excess != 0
                    and (train_excess > 0) == (test_excess > 0)
                ),
            }
        )
    train_q_values = _benjamini_hochberg(train_p_values)
    held_out_rows: list[dict[str, object]] = []
    for row, q_value in zip(intermediate, train_q_values):
        train_significant = q_value is not None and q_value < 0.10
        survived = (
            train_significant
            and row["same_direction"]
            and row["test_p_value"] is not None
            and row["test_p_value"] < 0.05
        )
        held_out_rows.append(
            {
                "period": row["period"],
                "train_count": row["train_count"],
                "train_excess_pct": round(row["train_excess_pct"], 2) if row["train_excess_pct"] is not None else None,
                "train_significant": train_significant,
                "test_count": row["test_count"],
                "test_excess_pct": round(row["test_excess_pct"], 2) if row["test_excess_pct"] is not None else None,
                "same_direction": row["same_direction"],
                "survived": survived,
            }
        )

    turn = _turn_of_month_analysis(ordered)
    turn_held_out_rows: list[dict[str, object]] = []
    for label, subset in (
        ("Train", [row for row in ordered if row["date"] < split_date]),
        ("Test", [row for row in ordered if row["date"] >= split_date]),
    ):
        result = _turn_of_month_analysis(subset)
        p_value = result["p_value"]
        turn_held_out_rows.append(
            {
                "period": label,
                "from_date": subset[0]["date"].isoformat() if subset else None,
                "to_date": subset[-1]["date"].isoformat() if subset else None,
                "edge_pct": result["edge_pct"],
                "p_value": p_value,
                "significant": p_value is not None and p_value < 0.05,
            }
        )
    return {
        "turn_rows": turn["rows"],
        "turn_edge_pct": turn["edge_pct"],
        "turn_t_statistic": turn["t_statistic"],
        "turn_p_value": turn["p_value"],
        "holdout_split_date": split_date.isoformat(),
        "held_out_rows": held_out_rows,
        "held_out_summary": {
            "same_direction": sum(bool(row["same_direction"]) for row in held_out_rows),
            "train_significant": sum(bool(row["train_significant"]) for row in held_out_rows),
            "survived": sum(bool(row["survived"]) for row in held_out_rows),
        },
        "turn_held_out_rows": turn_held_out_rows,
    }


def calculate_seasonality(
    candles: list[dict[str, object]],
    *,
    today: date,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if len(candles) < 2:
        raise ValueError("no_completed_historical_data")
    ordered = sorted(candles, key=lambda item: item["date"])
    weekday_values: dict[int, list[tuple[float, float]]] = {index: [] for index in range(5)}
    for previous, current in zip(ordered, ordered[1:]):
        previous_close = float(previous["close"])
        low = float(current["low"])
        daily_return = ((float(current["close"]) / previous_close) - 1) * 100
        daily_range = ((float(current["high"]) - low) / low) * 100
        weekday = current["date"].weekday()
        if weekday in weekday_values:
            weekday_values[weekday].append((daily_return, daily_range))

    monthly_buckets: dict[tuple[int, int], list[dict[str, object]]] = {}
    for candle in ordered:
        candle_date = candle["date"]
        monthly_buckets.setdefault((candle_date.year, candle_date.month), []).append(candle)
    completed_months = [
        (key, rows)
        for key, rows in sorted(monthly_buckets.items())
        if key != (today.year, today.month)
    ]
    month_values: dict[int, list[tuple[float, float]]] = {month: [] for month in range(1, 13)}
    previous_month_close: float | None = None
    for (year, month), rows in completed_months:
        month_close = float(rows[-1]["close"])
        month_low = min(float(row["low"]) for row in rows)
        month_high = max(float(row["high"]) for row in rows)
        if previous_month_close is not None:
            monthly_return = ((month_close / previous_month_close) - 1) * 100
            monthly_range = ((month_high - month_low) / month_low) * 100
            month_values[month].append((monthly_return, monthly_range))
        previous_month_close = month_close

    month_names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    weekday_names = ("Mon", "Tue", "Wed", "Thu", "Fri")
    month_rows = [
        {"period": month_names[month - 1], **_seasonality_summary(month_values[month])}
        for month in range(1, 13)
    ]
    weekday_rows = [
        {"period": weekday_names[weekday], **_seasonality_summary(weekday_values[weekday])}
        for weekday in range(5)
    ]
    return month_rows, weekday_rows


def calculate_month_to_date_returns(
    histories: dict[str, list[tuple[date, float]]],
    *,
    as_of: date,
) -> dict[str, float]:
    month_start = date(as_of.year, as_of.month, 1)
    returns: dict[str, float] = {}
    for instrument, history in histories.items():
        completed = sorted((row for row in history if row[0] <= as_of), key=lambda row: row[0])
        prior_rows = [row for row in completed if row[0] < month_start]
        current_rows = [row for row in completed if month_start <= row[0] <= as_of]
        if not prior_rows or not current_rows or current_rows[-1][0] != as_of:
            continue
        prior_close = float(prior_rows[-1][1])
        latest_close = float(current_rows[-1][1])
        if prior_close <= 0 or not math.isfinite(prior_close) or not math.isfinite(latest_close):
            continue
        returns[instrument] = round(((latest_close / prior_close) - 1) * 100, 2)
    return returns


def rank_historical_month_averages(
    averages: dict[str, tuple[float, int]],
) -> dict[str, object]:
    eligible: list[tuple[str, float, int]] = []
    for instrument, value in averages.items():
        average_return, observations = value
        average_return = float(average_return)
        if observations < 1 or not math.isfinite(average_return):
            continue
        eligible.append((instrument, average_return, observations))
    if not eligible:
        raise ValueError("historical_month_data_unavailable")
    leader = max(eligible, key=lambda item: (item[1], item[0]))
    lagger = min(eligible, key=lambda item: (item[1], item[0]))
    return {
        "leader": {
            "instrument": leader[0],
            "average_return_pct": round(leader[1], 2),
            "observations": leader[2],
        },
        "lagger": {
            "instrument": lagger[0],
            "average_return_pct": round(lagger[1], 2),
            "observations": lagger[2],
        },
        "evaluated": len(eligible),
    }


def calculate_index_ytd(
    display_name: str, history: list[tuple[date, float]]
) -> dict[str, object]:
    if not history:
        raise ValueError("no_completed_historical_data")
    latest_date, latest_close = history[-1]
    prior_year_rows = [item for item in history if item[0].year < latest_date.year]
    if not prior_year_rows:
        raise ValueError("prior_year_close_unavailable")
    prior_date, prior_close = prior_year_rows[-1]
    if prior_close <= 0:
        raise ValueError("invalid_provider_response")
    return {
        "display_name": display_name,
        "as_of_date": latest_date.isoformat(),
        "close": round(latest_close, 2),
        "prior_year_close_date": prior_date.isoformat(),
        "ytd_pct": round(((latest_close / prior_close) - 1) * 100, 2),
    }


def calculate_market_breadth(
    constituents: list[dict[str, str]],
    histories: dict[str, list[tuple[date, float]]],
) -> tuple[list[dict[str, object]], date, int]:
    latest_dates = [history[-1][0] for history in histories.values() if history]
    if not latest_dates:
        raise ValueError("no_completed_historical_data")
    as_of = max(latest_dates)
    sectors: dict[str, list[list[float]]] = {}
    for constituent in constituents:
        history = histories.get(constituent["symbol"], [])
        closes = [close for candle_date, close in history if candle_date <= as_of]
        if not history or history[-1][0] != as_of or len(closes) < 201:
            continue
        sectors.setdefault(constituent["sector"], []).append(closes)

    rows: list[dict[str, object]] = []
    evaluated = 0
    all_sectors = sorted({item["sector"] for item in constituents})
    for sector in all_sectors:
        total = sum(1 for item in constituents if item["sector"] == sector)
        series = sectors.get(sector, [])
        evaluated += len(series)
        if not series:
            rows.append(
                {
                    "sector": sector,
                    "stocks": total,
                    "evaluated": 0,
                    "above_20dma_pct": None,
                    "above_50dma_pct": None,
                    "above_200dma_pct": None,
                    "one_day_change_pt": None,
                }
            )
            continue

        def percentage_above(window: int, offset: int = 0) -> int:
            count = 0
            for closes in series:
                end = len(closes) - offset
                moving_average = sum(closes[end - window:end]) / window
                count += closes[end - 1] > moving_average
            return round(100 * count / len(series))

        current_20 = percentage_above(20)
        previous_20 = percentage_above(20, offset=1)
        rows.append(
            {
                "sector": sector,
                "stocks": total,
                "evaluated": len(series),
                "above_20dma_pct": current_20,
                "above_50dma_pct": percentage_above(50),
                "above_200dma_pct": percentage_above(200),
                "one_day_change_pt": current_20 - previous_20,
            }
        )
    return rows, as_of, evaluated


def calculate_nifty500_market_context(
    constituents: list[dict[str, str]],
    stock_histories: dict[str, list[tuple[date, float]]],
    index_histories: dict[str, list[tuple[date, float]]],
    *,
    window_sessions: int = 20,
) -> dict[str, object]:
    """Summarise full-universe breadth and equal-weight relative strength."""
    if window_sessions < 1 or not constituents:
        raise ValueError("nifty500_market_context_unavailable")

    def clean(history: list[tuple[date, float]]) -> list[tuple[date, float]]:
        by_date = {
            session_date: float(close)
            for session_date, close in history
            if isinstance(session_date, date)
            and isinstance(close, (int, float))
            and not isinstance(close, bool)
            and math.isfinite(float(close))
            and float(close) > 0
        }
        return sorted(by_date.items())

    cleaned_stocks = {
        symbol: clean(history) for symbol, history in stock_histories.items()
    }
    latest_dates = [history[-1][0] for history in cleaned_stocks.values() if history]
    if not latest_dates:
        raise ValueError("nifty500_market_context_unavailable")
    as_of = max(latest_dates)

    evaluated_breadth = 0
    above_50 = 0
    above_200 = 0
    positive_20 = 0
    sector_returns: dict[str, list[float]] = defaultdict(list)
    constituent_by_symbol = {
        str(item.get("symbol") or ""): item for item in constituents if item.get("symbol")
    }
    for symbol, constituent in constituent_by_symbol.items():
        history = cleaned_stocks.get(symbol, [])
        if not history or history[-1][0] != as_of:
            continue
        closes = [close for _, close in history]
        if len(closes) >= 201:
            evaluated_breadth += 1
            above_50 += closes[-1] > sum(closes[-50:]) / 50
            above_200 += closes[-1] > sum(closes[-200:]) / 200
        if len(closes) >= window_sessions + 1:
            stock_return = (closes[-1] / closes[-(window_sessions + 1)] - 1) * 100
            positive_20 += stock_return > 0
            sector_returns[str(constituent.get("sector") or "Unclassified")].append(stock_return)

    benchmark_history = clean(index_histories.get("Nifty 50", []))
    benchmark_history = [item for item in benchmark_history if item[0] <= as_of]
    if (
        len(benchmark_history) < window_sessions + 1
        or benchmark_history[-1][0] != as_of
    ):
        raise ValueError("nifty500_market_context_unavailable")
    benchmark_return = (
        benchmark_history[-1][1] / benchmark_history[-(window_sessions + 1)][1] - 1
    ) * 100

    index_rows: list[dict[str, object]] = []
    for instrument, raw_history in index_histories.items():
        if instrument == "Nifty 50":
            continue
        history = [item for item in clean(raw_history) if item[0] <= as_of]
        if len(history) < window_sessions + 1 or history[-1][0] != as_of:
            continue
        instrument_return = (history[-1][1] / history[-(window_sessions + 1)][1] - 1) * 100
        index_rows.append(
            {
                "name": instrument,
                "return_pct": round(instrument_return, 2),
                "excess_vs_nifty50_pct": round(instrument_return - benchmark_return, 2),
            }
        )

    sector_rows = [
        {
            "name": sector,
            "return_pct": round(sum(returns) / len(returns), 2),
            "excess_vs_nifty50_pct": round(sum(returns) / len(returns) - benchmark_return, 2),
            "stocks_evaluated": len(returns),
        }
        for sector, returns in sector_returns.items()
        if returns
    ]

    def ranked(rows: list[dict[str, object]]) -> dict[str, object]:
        ordered = sorted(
            rows,
            key=lambda item: (float(item["excess_vs_nifty50_pct"]), str(item["name"])),
        )
        return {
            "evaluated": len(ordered),
            "strongest": ordered[-1] if ordered else None,
            "weakest": ordered[0] if ordered else None,
        }

    return {
        "ok": True,
        "contract_version": "nifty500-market-context-v1",
        "as_of_date": as_of.isoformat(),
        "universe": "NIFTY 500",
        "breadth": {
            "official_count": len(constituent_by_symbol),
            "evaluated": evaluated_breadth,
            "coverage_pct": round(100 * evaluated_breadth / len(constituent_by_symbol), 1),
            "above_50dma_pct": round(100 * above_50 / evaluated_breadth, 1) if evaluated_breadth else None,
            "above_200dma_pct": round(100 * above_200 / evaluated_breadth, 1) if evaluated_breadth else None,
            "positive_20d": positive_20,
            "evaluated_20d": sum(len(rows) for rows in sector_returns.values()),
            "positive_20d_pct": round(100 * positive_20 / sum(len(rows) for rows in sector_returns.values()), 1)
            if sector_returns else None,
        },
        "relative_strength": {
            "window_sessions": window_sessions,
            "benchmark": {
                "name": "Nifty 50",
                "return_pct": round(benchmark_return, 2),
            },
            "indices": ranked(index_rows),
            "sectors": ranked(sector_rows),
            "method": "Equal-weight completed-session return minus the Nifty 50 return over the same trailing window.",
        },
        "limitations": [
            "Breadth and sector returns use the current official NIFTY 500 constituents and carry survivorship bias.",
            "Sector returns are equal-weight observations, not official sector-index returns.",
            "Relative strength is a simple return difference, not risk-adjusted alpha.",
        ],
    }


def build_stock_ytd_table(
    constituents: list[dict[str, str]],
    histories: dict[str, list[tuple[date, float]]],
    *,
    as_of: date,
    year: int,
) -> dict[str, object]:
    """Build a point-in-time calendar-year ranking for the current NIFTY 500 universe."""
    if year < 2000 or year > as_of.year:
        raise ValueError("invalid_stock_ytd_year")
    year_start = date(year, 1, 1)
    year_end = min(as_of, date(year, 12, 31))
    rows: list[dict[str, object]] = []
    for constituent in constituents:
        symbol = str(constituent["symbol"])
        history = sorted(
            (
                (session_date, float(close))
                for session_date, close in histories.get(symbol, [])
                if session_date <= year_end and math.isfinite(float(close)) and float(close) > 0
            ),
            key=lambda item: item[0],
        )
        prior_rows = [item for item in history if item[0] < year_start]
        selected_rows = [item for item in history if year_start <= item[0] <= year_end]
        if not selected_rows:
            rows.append(
                {
                    "rank": None,
                    "symbol": symbol,
                    "name": str(constituent.get("name") or symbol),
                    "sector": str(constituent["sector"]),
                    "status": "unavailable",
                    "price_date": None,
                    "ltp": None,
                    "ytd_performance_pct": None,
                    "from_20dma_pct": None,
                    "from_200dma_pct": None,
                }
            )
            continue
        price_date, latest_close = selected_rows[-1]
        prior_close = prior_rows[-1][1] if prior_rows else None
        closes = [close for session_date, close in history if session_date <= price_date]
        average_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        average_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
        ytd_return = (
            ((latest_close / prior_close) - 1) * 100
            if prior_close is not None and prior_close > 0
            else None
        )
        status = "ready" if ytd_return is not None and average_200 is not None else "partial_history"
        rows.append(
            {
                "rank": None,
                "symbol": symbol,
                "name": str(constituent.get("name") or symbol),
                "sector": str(constituent["sector"]),
                "status": status,
                "price_date": price_date.isoformat(),
                "ltp": round(latest_close, 2),
                "ytd_performance_pct": round(ytd_return, 2) if ytd_return is not None else None,
                "from_20dma_pct": (
                    round(((latest_close / average_20) - 1) * 100, 2)
                    if average_20 is not None else None
                ),
                "from_200dma_pct": (
                    round(((latest_close / average_200) - 1) * 100, 2)
                    if average_200 is not None else None
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            row["ytd_performance_pct"] is None,
            -float(row["ytd_performance_pct"]) if row["ytd_performance_pct"] is not None else 0.0,
            str(row["symbol"]),
        )
    )
    rank = 0
    for row in rows:
        if row["ytd_performance_pct"] is not None:
            rank += 1
            row["rank"] = rank
    dated_rows = [row for row in rows if row["price_date"] is not None]
    selected_as_of = max((str(row["price_date"]) for row in dated_rows), default=None)
    ready = sum(row["status"] == "ready" for row in rows)
    partial = sum(row["status"] == "partial_history" for row in rows)
    unavailable = sum(row["status"] == "unavailable" for row in rows)
    return {
        "ok": True,
        "status": "ranking_ready" if ready else "ranking_partial",
        "contract_version": "nifty500-stock-ytd-v1",
        "universe": "NIFTY 500",
        "selected_year": year,
        "as_of_date": selected_as_of,
        "price_label": "Latest completed close" if year == as_of.year else "Year-end completed close",
        "coverage": {
            "total": len(rows),
            "ready": ready,
            "partial_history": partial,
            "unavailable": unavailable,
        },
        "rows": rows,
        "definitions": {
            "ytd_performance_pct": "selected-year close versus the final completed close before that calendar year",
            "from_20dma_pct": "selected-year close percentage above or below its trailing 20-session simple moving average",
            "from_200dma_pct": "selected-year close percentage above or below its trailing 200-session simple moving average",
        },
        "limitations": [
            "The universe is the current official NIFTY 500 constituent snapshot and carries survivorship bias for historical years.",
            "Historical-year prices and moving averages are aligned to that year's final available completed session.",
            "Rows without enough price history remain visible as partial or unavailable.",
            "The ranking is descriptive performance evidence, not a recommendation.",
        ],
    }


def parse_institutional_flows(payload: object, *, today: date) -> list[dict[str, object]]:
    """Validate NSE's combined-exchange provisional FII/FPI and DII cash rows."""
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("invalid_institutional_flow_response")

    def number(value: object) -> float:
        if isinstance(value, bool):
            raise ValueError("invalid_institutional_flow_response")
        try:
            parsed = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError) as error:
            raise ValueError("invalid_institutional_flow_response") from error
        if not math.isfinite(parsed):
            raise ValueError("invalid_institutional_flow_response")
        return parsed

    rows: list[dict[str, object]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("invalid_institutional_flow_response")
        category = str(raw.get("category", "")).strip()
        try:
            session_date = datetime.strptime(str(raw.get("date", "")).strip(), "%d-%b-%Y").date()
        except ValueError as error:
            raise ValueError("invalid_institutional_flow_response") from error
        buy = number(raw.get("buyValue"))
        sell = number(raw.get("sellValue"))
        net = number(raw.get("netValue"))
        if (
            category not in {"FII/FPI", "DII"}
            or session_date > today
            or buy < 0
            or sell < 0
            or abs((buy - sell) - net) > 0.11
        ):
            raise ValueError("invalid_institutional_flow_response")
        rows.append(
            {
                "date": session_date,
                "category": category,
                "buy_crore": buy,
                "sell_crore": sell,
                "net_crore": net,
            }
        )
    if {row["category"] for row in rows} != {"FII/FPI", "DII"} or len({row["date"] for row in rows}) != 1:
        raise ValueError("invalid_institutional_flow_response")
    return sorted(rows, key=lambda row: str(row["category"]))


def calculate_institutional_flow_summary(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    """Summarise append-only provisional cash flows without inventing a signal threshold."""
    sessions: dict[date, dict[str, dict[str, object]]] = {}
    for row in rows:
        session_date = row.get("date")
        category = row.get("category")
        if isinstance(session_date, date) and category in {"FII/FPI", "DII"}:
            sessions.setdefault(session_date, {})[str(category)] = row
    complete_dates = sorted(
        session_date
        for session_date, categories in sessions.items()
        if set(categories) == {"FII/FPI", "DII"}
    )
    if not complete_dates:
        return {
            "available": False,
            "publication_status": "provisional",
            "reason": "Run EOD update to retrieve the official NSE institutional-flow report.",
        }

    latest_date = complete_dates[-1]
    latest = sessions[latest_date]

    def category_values(category: str) -> dict[str, float]:
        row = latest[category]
        return {
            "buy_crore": round(float(row["buy_crore"]), 2),
            "sell_crore": round(float(row["sell_crore"]), 2),
            "net_crore": round(float(row["net_crore"]), 2),
        }

    def cumulative(window: int) -> dict[str, float] | None:
        if len(complete_dates) < window:
            return None
        selected = complete_dates[-window:]
        fii = sum(float(sessions[item]["FII/FPI"]["net_crore"]) for item in selected)
        dii = sum(float(sessions[item]["DII"]["net_crore"]) for item in selected)
        return {
            "fii_fpi_net_crore": round(fii, 2),
            "dii_net_crore": round(dii, 2),
            "combined_net_crore": round(fii + dii, 2),
        }

    latest_fii = category_values("FII/FPI")
    latest_dii = category_values("DII")
    series = [
        {
            "date": session_date.isoformat(),
            "fii_fpi_net_crore": round(float(sessions[session_date]["FII/FPI"]["net_crore"]), 2),
            "dii_net_crore": round(float(sessions[session_date]["DII"]["net_crore"]), 2),
            "combined_net_crore": round(
                float(sessions[session_date]["FII/FPI"]["net_crore"])
                + float(sessions[session_date]["DII"]["net_crore"]),
                2,
            ),
        }
        for session_date in complete_dates
    ]
    return {
        "available": True,
        "as_of_date": latest_date.isoformat(),
        "publication_status": "provisional",
        "market_scope": "NSE, BSE and MSEI combined cash market",
        "source": NSE_FII_DII_SOURCE,
        "session_count": len(complete_dates),
        "latest": {
            "fii_fpi": latest_fii,
            "dii": latest_dii,
            "combined_net_crore": round(latest_fii["net_crore"] + latest_dii["net_crore"], 2),
        },
        "five_session": cumulative(5),
        "twenty_session": cumulative(20),
        "series": series,
        "band": "unranked",
        "reason": "Official provisional cash flows are visible; directional thresholds are not yet validated.",
        "confirmed_reconciliation": "not_loaded",
    }


def parse_nsdl_confirmed_fpi(html_payload: str, *, today: date) -> list[dict[str, object]]:
    """Extract confirmed equity investment routes from NSDL's current-month report."""
    if not isinstance(html_payload, str) or not html_payload.strip():
        raise ValueError("invalid_confirmed_fpi_response")
    investment_start = html_payload.find("Daily Trends in FPI Investments")
    derivative_start = html_payload.find("Daily Trends in FPI Derivative Trades")
    if investment_start < 0 or derivative_start <= investment_start:
        raise ValueError("invalid_confirmed_fpi_response")
    section = html_payload[investment_start:derivative_start]

    import html as html_module

    def cell_text(value: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html_module.unescape(without_tags).replace("\xa0", " ")).strip()

    def number(value: str) -> float:
        cleaned = value.replace(",", "").strip()
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        if negative:
            cleaned = cleaned[1:-1].strip()
        try:
            parsed = float(cleaned)
        except ValueError as error:
            raise ValueError("invalid_confirmed_fpi_response") from error
        if not math.isfinite(parsed):
            raise ValueError("invalid_confirmed_fpi_response")
        return -parsed if negative else parsed

    routes = {"Stock Exchange", "Primary market & others", "Sub-total"}
    parsed_rows: list[dict[str, object]] = []
    current_date: date | None = None
    current_asset = ""
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, flags=re.IGNORECASE | re.DOTALL):
        cells = [
            cell_text(cell)
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", raw_row, flags=re.IGNORECASE | re.DOTALL)
        ]
        if not cells:
            continue
        try:
            row_date = datetime.strptime(cells[0], "%d-%b-%Y").date()
        except ValueError:
            row_date = None
        if row_date is not None:
            if len(cells) < 6 or row_date > today:
                raise ValueError("invalid_confirmed_fpi_response")
            current_date = row_date
            current_asset = cells[1]
            route = cells[2]
            values = cells[3:6]
        elif cells[0] in routes:
            route = cells[0]
            values = cells[1:4]
        else:
            if len(cells) < 5:
                continue
            current_asset = cells[0]
            route = cells[1]
            values = cells[2:5]
        if current_date is None or current_asset != "Equity" or route not in routes:
            continue
        if len(values) != 3:
            raise ValueError("invalid_confirmed_fpi_response")
        purchases, sales, net = (number(value) for value in values)
        if purchases < 0 or sales < 0 or abs((purchases - sales) - net) > 0.11:
            raise ValueError("invalid_confirmed_fpi_response")
        parsed_rows.append(
            {
                "date": current_date,
                "asset_class": "Equity",
                "investment_route": route,
                "gross_purchases_crore": purchases,
                "gross_sales_crore": sales,
                "net_investment_crore": net,
            }
        )
    routes_by_date: dict[date, set[str]] = {}
    for row in parsed_rows:
        routes_by_date.setdefault(row["date"], set()).add(str(row["investment_route"]))
    if not parsed_rows or any(found != routes for found in routes_by_date.values()):
        raise ValueError("invalid_confirmed_fpi_response")
    return parsed_rows


def calculate_confirmed_fpi_summary(
    rows: list[dict[str, object]], *, today: date | None = None
) -> dict[str, object]:
    """Summarise custodian-confirmed FPI equity data without blending NSE provisional flows."""
    sessions: dict[date, dict[str, dict[str, object]]] = {}
    required_routes = {"Stock Exchange", "Primary market & others", "Sub-total"}
    for row in rows:
        reporting_date = row.get("date")
        route = row.get("investment_route")
        if isinstance(reporting_date, date) and route in required_routes:
            sessions.setdefault(reporting_date, {})[str(route)] = row
    complete_dates = sorted(
        reporting_date
        for reporting_date, route_rows in sessions.items()
        if set(route_rows) == required_routes
    )
    if not complete_dates:
        return {
            "available": False,
            "publication_status": "confirmed_custodian",
            "reason": "Run EOD update to retrieve the official NSDL custodian-confirmed FPI report.",
        }

    latest_date = complete_dates[-1]
    latest_routes = sessions[latest_date]

    def values(route: str) -> dict[str, float]:
        row = latest_routes[route]
        return {
            "gross_purchases_crore": round(float(row["gross_purchases_crore"]), 2),
            "gross_sales_crore": round(float(row["gross_sales_crore"]), 2),
            "net_investment_crore": round(float(row["net_investment_crore"]), 2),
        }

    def cumulative(window: int) -> float | None:
        if len(complete_dates) < window:
            return None
        return round(
            sum(
                float(sessions[item]["Sub-total"]["net_investment_crore"])
                for item in complete_dates[-window:]
            ),
            2,
        )

    reference_date = today or datetime.now(INDIA_TIMEZONE).date()
    return {
        "available": True,
        "as_of_date": latest_date.isoformat(),
        "publication_status": "confirmed_custodian",
        "asset_class": "Equity",
        "source": NSDL_FPI_SOURCE,
        "session_count": len(complete_dates),
        "reporting_lag_calendar_days": max(0, (reference_date - latest_date).days),
        "latest": {
            "stock_exchange": values("Stock Exchange"),
            "primary_market_and_others": values("Primary market & others"),
            "subtotal": values("Sub-total"),
        },
        "five_session_net_crore": cumulative(5),
        "twenty_session_net_crore": cumulative(20),
        "series": [
            {
                "date": reporting_date.isoformat(),
                "net_investment_crore": round(
                    float(sessions[reporting_date]["Sub-total"]["net_investment_crore"]), 2
                ),
            }
            for reporting_date in complete_dates
        ],
        "comparison_note": (
            "Custodian-confirmed FPI investment is shown separately from NSE provisional "
            "FII/FPI cash activity because publication timing and coverage differ."
        ),
    }


def parse_rbi_macro_snapshot(html_payload: str) -> list[dict[str, object]]:
    """Extract the current official FBIL FX references and approximate 10-year G-Sec."""
    if not isinstance(html_payload, str) or not html_payload.strip():
        raise ValueError("invalid_rbi_macro_response")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_payload, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    import html as html_module

    text = html_module.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()

    fx_date_match = re.search(
        r"As\s+at\s+1\.00\s*pm\s+of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    gsec_heading = re.search(r"Government\s+Securities\s+Market", text, flags=re.IGNORECASE)
    preceding_dates = (
        re.findall(
            r"as\s+on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text[: gsec_heading.start()] if gsec_heading else "",
            flags=re.IGNORECASE,
        )
        if gsec_heading
        else []
    )
    following_dates = (
        re.findall(
            r"as\s+on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text[gsec_heading.end() : gsec_heading.end() + 1000] if gsec_heading else "",
            flags=re.IGNORECASE,
        )
        if gsec_heading
        else []
    )
    if (
        fx_date_match is None
        or not (preceding_dates or following_dates)
        or re.search(r"Source\s*:\s*FBIL", text, flags=re.IGNORECASE) is None
    ):
        raise ValueError("invalid_rbi_macro_response")
    try:
        fx_date = datetime.strptime(fx_date_match.group(1), "%B %d, %Y").date()
        gsec_date_text = preceding_dates[-1] if preceding_dates else following_dates[0]
        gsec_date = datetime.strptime(gsec_date_text, "%B %d, %Y").date()
    except ValueError as error:
        raise ValueError("invalid_rbi_macro_response") from error

    fx_specs = (
        ("usd_inr", r"INR\s*/\s*1\s*USD", "INR per USD", "USD/INR"),
        ("gbp_inr", r"INR\s*/\s*1\s*GBP", "INR per GBP", "GBP/INR"),
        ("eur_inr", r"INR\s*/\s*1\s*EUR", "INR per EUR", "EUR/INR"),
        ("jpy_100_inr", r"INR\s*/\s*100\s*JPY", "INR per 100 JPY", "JPY/INR (100 JPY)"),
    )
    rows: list[dict[str, object]] = []
    for metric_key, label_pattern, unit, instrument_label in fx_specs:
        match = re.search(rf"{label_pattern}\s*:?\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
        if match is None:
            raise ValueError("invalid_rbi_macro_response")
        value = float(match.group(1))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("invalid_rbi_macro_response")
        rows.append(
            {
                "date": fx_date,
                "metric_key": metric_key,
                "value": value,
                "unit": unit,
                "instrument_label": instrument_label,
            }
        )

    gsec_candidates: list[tuple[int, float, str]] = []
    for match in re.finditer(
        r"((?:[0-9]+(?:\.[0-9]+)?)%\s+GS\s+(\d{4}))\s*:?\s*([0-9]+(?:\.[0-9]+)?)%",
        text,
        flags=re.IGNORECASE,
    ):
        label, maturity_text, yield_text = match.groups()
        maturity = int(maturity_text)
        yield_value = float(yield_text)
        if maturity >= gsec_date.year and 0 < yield_value < 25:
            gsec_candidates.append((maturity, yield_value, re.sub(r"\s+", " ", label).upper()))
    if not gsec_candidates:
        raise ValueError("invalid_rbi_macro_response")
    maturity, yield_value, label = min(
        gsec_candidates,
        key=lambda item: (abs(item[0] - (gsec_date.year + 10)), item[0]),
    )
    rows.append(
        {
            "date": gsec_date,
            "metric_key": "india_10y_gsec_yield",
            "value": yield_value,
            "unit": "percent yield",
            "instrument_label": f"{label} (approx. 10-year; matures {maturity})",
        }
    )
    return rows


class _RbiTableHtmlParser(HTMLParser):
    """Collect text cells from RBI publication tables without browser markup assumptions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self._cell_parts is not None:
            value = re.sub(r"\s+", " ", " ".join(self._cell_parts).replace("\xa0", " ")).strip()
            if self._row is not None:
                self._row.append(value)
            self._cell_parts = None
        elif lowered == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell_parts = None


def parse_rbi_annual_series_table(
    html_payload: str,
    *,
    series_key: str,
    source_url: str,
    source_title: str,
    vintage_date: date,
    value_column: int,
    unit: str,
    aggregation: str = "annual average",
    allow_non_positive: bool = False,
    base_period_override: str | None = None,
    maximum_end_year: int | None = None,
    duplicate_resolution: str = "last",
) -> list[dict[str, object]]:
    """Parse one fiscal-year RBI Handbook series and retain its stated base."""
    if (
        not isinstance(html_payload, str)
        or not html_payload.strip()
        or not source_url.startswith("https://rbi.org.in/")
        or not isinstance(vintage_date, date)
        or not isinstance(value_column, int)
        or value_column < 1
        or not isinstance(aggregation, str)
        or not aggregation.strip()
        or (base_period_override is not None and not base_period_override.strip())
        or (maximum_end_year is not None and maximum_end_year < 1900)
        or duplicate_resolution not in {"first", "last"}
    ):
        raise ValueError("invalid_rbi_historical_series_response")
    parser = _RbiTableHtmlParser()
    try:
        parser.feed(html_payload)
    except (ValueError, TypeError) as error:
        raise ValueError("invalid_rbi_historical_series_response") from error

    base_period = base_period_override or "Base not stated"
    observations: list[dict[str, object]] = []
    fiscal_year_pattern = re.compile(
        r"^(\d{4})\s*[-–]\s*(\d{2,4})(?:\s*(\*+|P|QE|RE|@))?$",
        flags=re.IGNORECASE,
    )
    base_pattern = re.compile(r"Base\s*:?\s*([^\)]+)", flags=re.IGNORECASE)
    for cells in parser.rows:
        joined = " ".join(cells)
        base_match = base_pattern.search(joined)
        if (
            base_period_override is None
            and base_match is not None
            and not fiscal_year_pattern.match(cells[0].strip() if cells else "")
        ):
            base_period = re.sub(r"\s+", " ", base_match.group(1)).strip(" )")
            continue
        if len(cells) <= value_column:
            continue
        period_label = cells[0].strip()
        period_match = fiscal_year_pattern.match(period_label)
        if period_match is None:
            continue
        status_marker = (period_match.group(3) or "").upper()
        if status_marker.startswith("*") or status_marker == "@":
            continue
        start_year = int(period_match.group(1))
        end_text = period_match.group(2)
        end_year = int(end_text) if len(end_text) == 4 else (start_year // 100) * 100 + int(end_text)
        if end_year < start_year:
            end_year += 100
        if maximum_end_year is not None and end_year > maximum_end_year:
            continue
        try:
            value = float(cells[value_column].replace(",", ""))
            observation_date = date(end_year, 3, 31)
        except (ValueError, OverflowError):
            continue
        if not math.isfinite(value) or (value <= 0 and not allow_non_positive):
            continue
        normalized_period = f"{start_year:04d}-{end_text}"
        metadata: dict[str, object] = {
            "period_basis": "Indian financial year",
            "aggregation": aggregation.strip(),
            "partial_period_excluded": True,
        }
        if status_marker:
            metadata["publication_status"] = status_marker
        if allow_non_positive:
            metadata["allows_non_positive"] = True
        observations.append(
            {
                "series_key": series_key,
                "date": observation_date,
                "period_label": normalized_period,
                "frequency": "annual",
                "value": value,
                "unit": unit,
                "base_period": base_period,
                "source_title": source_title,
                "source_url": source_url,
                "source_authority": "Reserve Bank of India",
                "vintage_date": vintage_date,
                "metadata": metadata,
            }
        )
    deduplicated: dict[object, dict[str, object]] = {}
    for row in observations:
        if duplicate_resolution == "last" or row["date"] not in deduplicated:
            deduplicated[row["date"]] = row
    observations = [deduplicated[item] for item in sorted(deduplicated)]
    if len(observations) < 2:
        raise ValueError("invalid_rbi_historical_series_response")
    return observations


def build_historical_series_summary(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    definitions = {
        "bse_sensex_annual_average": {
            "label": "BSE Sensex annual average",
            "comparison": "percent_change",
        },
        "india_wpi_all_commodities_annual_average": {
            "label": "India WPI all commodities annual average",
            "comparison": "percent_change_same_base",
        },
        "india_real_gdp_growth_pct": {
            "label": "India real GDP growth",
            "comparison": "percentage_point_change",
        },
        "india_call_money_rate_annual": {
            "label": "India call money rate",
            "comparison": "percentage_point_change",
        },
        "inr_usd_annual_average": {
            "label": "INR per US dollar annual average",
            "comparison": "percent_change",
        },
        "central_gross_fiscal_deficit_pct_gdp": {
            "label": "Central gross fiscal deficit",
            "comparison": "percentage_point_change",
        },
        "india_foreign_exchange_reserves_usd_mn": {
            "label": "India foreign-exchange reserves",
            "comparison": "percent_change",
        },
    }
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row.get("series_key") in definitions and isinstance(row.get("date"), date):
            grouped[str(row["series_key"])].append(row)

    series: list[dict[str, object]] = []
    for key, definition in definitions.items():
        values = sorted(grouped.get(key, []), key=lambda item: item["date"])
        if not values:
            series.append(
                {
                    "series_key": key,
                    "label": definition["label"],
                    "status": "not_imported",
                    "frequency": "annual",
                    "observations": 0,
                }
            )
            continue
        bases = list(dict.fromkeys(str(item.get("base_period") or "") for item in values))
        vintages = sorted({item["vintage_date"] for item in values if isinstance(item.get("vintage_date"), date)})
        latest_change = None
        latest_delta = None
        if len(values) >= 2:
            same_base = values[-1].get("base_period") == values[-2].get("base_period")
            comparison = definition["comparison"]
            if comparison == "percent_change" or (
                comparison == "percent_change_same_base" and same_base
            ):
                previous = float(values[-2]["value"])
                if previous != 0:
                    latest_change = round(
                        (float(values[-1]["value"]) / previous - 1) * 100,
                        2,
                    )
            elif comparison == "percentage_point_change":
                latest_delta = round(float(values[-1]["value"]) - float(values[-2]["value"]), 2)
        series.append(
            {
                "series_key": key,
                "label": definition["label"],
                "status": "ready",
                "frequency": str(values[-1].get("frequency") or "annual"),
                "observations": len(values),
                "from_date": values[0]["date"].isoformat(),
                "to_date": values[-1]["date"].isoformat(),
                "latest_period": values[-1].get("period_label"),
                "latest_value": round(float(values[-1]["value"]), 2),
                "latest_change_pct": latest_change,
                "latest_delta": latest_delta,
                "comparison": definition["comparison"],
                "unit": values[-1].get("unit"),
                "base_periods": bases,
                "latest_vintage": vintages[-1].isoformat() if vintages else None,
                "source_title": values[-1].get("source_title"),
                "source_url": values[-1].get("source_url"),
            }
        )

    by_series_period = {
        key: {
            str(row.get("period_label")): row
            for row in sorted(grouped.get(key, []), key=lambda item: item["date"])
        }
        for key in definitions
    }
    all_periods: dict[str, date] = {}
    for values in grouped.values():
        for row in values:
            all_periods[str(row.get("period_label"))] = row["date"]
    joined_rows: list[dict[str, object]] = []
    previous_by_key: dict[str, dict[str, object]] = {}
    for period, observation_date in sorted(all_periods.items(), key=lambda item: item[1]):
        sensex = by_series_period["bse_sensex_annual_average"].get(period)
        wpi = by_series_period["india_wpi_all_commodities_annual_average"].get(period)
        growth = by_series_period["india_real_gdp_growth_pct"].get(period)
        call_rate = by_series_period["india_call_money_rate_annual"].get(period)
        usd_inr = by_series_period["inr_usd_annual_average"].get(period)
        fiscal = by_series_period["central_gross_fiscal_deficit_pct_gdp"].get(period)
        reserves = by_series_period["india_foreign_exchange_reserves_usd_mn"].get(period)
        previous_sensex = previous_by_key.get("bse_sensex_annual_average")
        previous_wpi = previous_by_key.get("india_wpi_all_commodities_annual_average")
        previous_usd = previous_by_key.get("inr_usd_annual_average")
        sensex_change = (
            round((float(sensex["value"]) / float(previous_sensex["value"]) - 1) * 100, 2)
            if sensex is not None and previous_sensex is not None else None
        )
        wpi_change = (
            round((float(wpi["value"]) / float(previous_wpi["value"]) - 1) * 100, 2)
            if wpi is not None
            and previous_wpi is not None
            and wpi.get("base_period") == previous_wpi.get("base_period")
            else None
        )
        usd_change = (
            round((float(usd_inr["value"]) / float(previous_usd["value"]) - 1) * 100, 2)
            if usd_inr is not None and previous_usd is not None else None
        )
        joined_rows.append(
            {
                "period": period,
                "date": observation_date.isoformat(),
                "sensex_average": round(float(sensex["value"]), 2) if sensex is not None else None,
                "sensex_change_pct": sensex_change,
                "wpi_average": round(float(wpi["value"]), 2) if wpi is not None else None,
                "wpi_change_pct": wpi_change,
                "wpi_base_period": wpi.get("base_period") if wpi is not None else None,
                "real_gdp_growth_pct": round(float(growth["value"]), 2) if growth is not None else None,
                "real_gdp_base_period": growth.get("base_period") if growth is not None else None,
                "call_money_rate_pct": round(float(call_rate["value"]), 2) if call_rate is not None else None,
                "inr_usd_average": round(float(usd_inr["value"]), 4) if usd_inr is not None else None,
                "inr_usd_change_pct": usd_change,
                "central_gfd_pct_gdp": round(float(fiscal["value"]), 2) if fiscal is not None else None,
                "foreign_exchange_reserves_usd_mn": round(float(reserves["value"]), 2) if reserves is not None else None,
            }
        )
        for key, row in (
            ("bse_sensex_annual_average", sensex),
            ("india_wpi_all_commodities_annual_average", wpi),
            ("inr_usd_annual_average", usd_inr),
        ):
            if row is not None:
                previous_by_key[key] = row
    ready_count = sum(item["status"] == "ready" for item in series)
    return {
        "status": "ready" if ready_count == len(series) else "partial" if ready_count else "not_imported",
        "series": series,
        "joined_annual_observations": len(joined_rows),
        "timeline": joined_rows,
        "method": "Latest RBI publication vintage per financial-year observation; no interpolation. Growth rates and interest/fiscal ratios remain published rates, reserves remain end-financial-year stocks, and WPI changes are withheld across index-base breaks.",
    }


def build_historical_episode_stories(
    official_history: dict[str, object],
) -> list[dict[str, object]]:
    """Build story-first episodes from joined annual evidence and cited anchors."""
    timeline = official_history.get("timeline")
    if not isinstance(timeline, list):
        return []

    def start_year(row: dict[str, object]) -> int:
        try:
            return int(str(row.get("period", ""))[:4])
        except ValueError:
            return -1

    def evidence_for(start: int, end: int) -> list[dict[str, object]]:
        window = [row for row in timeline if isinstance(row, dict) and start <= start_year(row) <= end]
        signals: list[dict[str, object]] = []

        def add_extreme(
            metric: str,
            label: str,
            *,
            maximum: bool,
            suffix: str,
            decimals: int = 2,
        ) -> None:
            available = [row for row in window if isinstance(row.get(metric), (int, float))]
            if not available:
                return
            selected = (max if maximum else min)(available, key=lambda row: float(row[metric]))
            signals.append(
                {
                    "label": label,
                    "period": selected["period"],
                    "value": round(float(selected[metric]), decimals),
                    "suffix": suffix,
                }
            )

        add_extreme("real_gdp_growth_pct", "Growth low", maximum=False, suffix="%")
        add_extreme("wpi_change_pct", "WPI inflation high", maximum=True, suffix="%")
        add_extreme("call_money_rate_pct", "Money-market stress high", maximum=True, suffix="%")
        add_extreme("inr_usd_change_pct", "Rupee depreciation high", maximum=True, suffix="%")
        add_extreme("central_gfd_pct_gdp", "Central fiscal deficit high", maximum=True, suffix="% of GDP")
        add_extreme("sensex_change_pct", "Sensex annual change low", maximum=False, suffix="%")
        sensex_rows = [row for row in window if isinstance(row.get("sensex_average"), (int, float))]
        if len(sensex_rows) >= 2:
            first, last = sensex_rows[0], sensex_rows[-1]
            path = (float(last["sensex_average"]) / float(first["sensex_average"]) - 1) * 100
            signals.append(
                {
                    "label": "Sensex annual-average path",
                    "period": f"{first['period']} to {last['period']}",
                    "value": round(path, 2),
                    "suffix": "%",
                }
            )
        reserve_rows = [
            row
            for row in window
            if isinstance(row.get("foreign_exchange_reserves_usd_mn"), (int, float))
        ]
        if len(reserve_rows) >= 2:
            first, last = reserve_rows[0], reserve_rows[-1]
            path = (
                float(last["foreign_exchange_reserves_usd_mn"])
                / float(first["foreign_exchange_reserves_usd_mn"])
                - 1
            ) * 100
            signals.append(
                {
                    "label": "FX-reserve stock path",
                    "period": f"{first['period']} to {last['period']}",
                    "value": round(path, 2),
                    "suffix": "%",
                }
            )
        return signals

    episodes = [
        {
            "key": "growth_inflation_break_1979",
            "period": "1978-79–1981-82",
            "title": "Growth break, inflation pressure and recovery",
            "family": "Contraction and rebound",
            "start_year": 1978,
            "end_year": 1981,
            "what_happened": "The annual record moves from positive growth into a sharp 1979-80 contraction while wholesale-price pressure rises, followed by a strong real-growth rebound.",
            "how_it_happened": "The evidence layer treats the simultaneous output, inflation and money-market moves as a stress cluster; causal claims remain documentary work rather than being inferred from correlation.",
            "what_came_out": "The episode establishes an early Indian template in which economic stress and the market benchmark do not share one exact turning date.",
            "how_markets_came_out": "Recovery is read as a sequence: real growth turns first in the annual data, while prices, funding conditions and the Sensex path are checked separately.",
            "source_keys": ["rbi_growth", "rbi_wpi", "rbi_rates", "rbi_sensex"],
        },
        {
            "key": "acceleration_fiscal_strain_1984",
            "period": "1984-85–1989-90",
            "title": "Acceleration with accumulating fiscal and funding strain",
            "family": "Expansion and imbalance build-up",
            "start_year": 1984,
            "end_year": 1989,
            "what_happened": "Growth accelerated strongly late in the decade, but the fiscal-deficit and money-market series show that the expansion did not arrive with uniformly easing financial conditions.",
            "how_it_happened": "RBI's historical account describes expansionary fiscal policy and automatic monetisation during the 1980s; the annual data expose the build-up without assigning a daily market trigger.",
            "what_came_out": "A strong-growth reading alone would have missed the policy and external vulnerability carried into the next episode.",
            "how_markets_came_out": "The story remains open until the expansion is joined to higher-frequency market breadth and valuation evidence; annual Sensex averages provide direction, not a precise peak call.",
            "source_keys": ["rbi_bop_history", "rbi_growth", "rbi_rates", "rbi_fiscal"],
        },
        {
            "key": "bop_crisis_1991",
            "period": "1990-91–1992-93",
            "title": "Balance-of-payments crisis, compression and rupee reset",
            "family": "Macro crisis and reform",
            "start_year": 1990,
            "end_year": 1992,
            "what_happened": "Growth slowed sharply in 1991-92 as money-market rates spiked and the annual-average rupee weakened substantially against the US dollar.",
            "how_it_happened": "RBI's official history links accumulated domestic imbalances and a deteriorating external setting to the 1991 balance-of-payments crisis, followed by exchange-rate and structural reforms.",
            "what_came_out": "The rupee regime moved through the 1991 adjustment and the 1992 LERMS transition while fiscal correction and financial-sector reform began.",
            "how_markets_came_out": "The annual evidence shows growth recovering and funding stress easing after the trough; the market story separates that stabilisation from the contemporaneous securities-market disruption.",
            "source_keys": ["rbi_bop_history", "rbi_growth", "rbi_rates", "rbi_fx", "rbi_fiscal"],
        },
        {
            "key": "market_repair_1992",
            "period": "1992-93–1994-95",
            "title": "Reform rebound and securities-market repair",
            "family": "Institutional repair and expansion",
            "start_year": 1992,
            "end_year": 1994,
            "what_happened": "Real growth strengthened through 1994-95 while the rupee's annual average stabilised relative to the crisis break and money-market stress retreated from its 1991-92 peak.",
            "how_it_happened": "Macroeconomic stabilisation overlapped with statutory SEBI powers, removal of administered capital-issue pricing and a programme of settlement and market-infrastructure reform.",
            "what_came_out": "A more market-based exchange-rate and securities-market framework emerged, improving price discovery while regulation and settlement architecture were rebuilt.",
            "how_markets_came_out": "The annual record supports a recovery story led by growth normalisation and lower funding stress; it does not claim that every market consequence of the 1992 crisis had ended by 1995.",
            "source_keys": ["rbi_bop_history", "sebi_reforms_1992_1996", "rbi_growth", "rbi_rates", "rbi_fx"],
        },
        {
            "key": "electronic_market_transition_1995",
            "period": "1995-96–1997-98",
            "title": "Electronic trading, dematerialisation and a new market plumbing",
            "family": "Market-infrastructure transition",
            "start_year": 1995,
            "end_year": 1997,
            "what_happened": "The market entered this period with a weak Sensex annual average and expensive call money even as real growth remained strong, while screen-based trading, the NIFTY 50 and dematerialised settlement became operating infrastructure.",
            "how_it_happened": "NSE's official milestones and SEBI's 1997-98 record show the migration from geographically fragmented floor trading and paper certificates toward electronic access, clearing guarantees, depositories and shorter settlement cycles.",
            "what_came_out": "India acquired a more observable and auditable market: prices travelled nationally, counterparty and settlement risks became more explicit, and index-based comparison became practical.",
            "how_markets_came_out": "This was structural repair rather than a clean price rally. The annual evidence is read alongside institutional milestones because the change in market plumbing altered how later stress and recovery would be transmitted.",
            "source_keys": ["nse_milestones", "sebi_annual_1997_98", "rbi_sensex", "rbi_growth", "rbi_rates"],
        },
        {
            "key": "asian_crisis_1997",
            "period": "1997-98–1998-99",
            "title": "Asian-crisis transmission without a domestic balance-of-payments break",
            "family": "External shock and currency pressure",
            "start_year": 1997,
            "end_year": 1998,
            "what_happened": "Growth slowed in 1997-98; in 1998-99 the rupee's annual average weakened sharply and the Sensex annual average declined, while the end-year foreign-exchange reserve stock continued to rise.",
            "how_it_happened": "RBI's historical assessment treats the Asian crisis as an external financial shock. The Indian evidence shows transmission through growth, currency and equity prices, but not a repeat of the reserve depletion that defined 1991.",
            "what_came_out": "The episode reinforced the value of reserve buffers, managed external exposure and prudential financial regulation while the new electronic market infrastructure was still maturing.",
            "how_markets_came_out": "The annual sequence shows growth rebounding in 1998-99 and reserves increasing even as the Sensex and rupee absorbed stress. Stabilisation across those measures arrived at different times.",
            "source_keys": ["rbi_crisis_growth_review", "rbi_reserves", "rbi_growth", "rbi_fx", "rbi_sensex"],
        },
        {
            "key": "technology_boom_bust_1999",
            "period": "1999-00–2003-04",
            "title": "Technology boom, market break and settlement-system repair",
            "family": "Crowding, correction and institutional repair",
            "start_year": 1999,
            "end_year": 2003,
            "what_happened": "The Sensex annual average surged in 1999-00, then fell for three financial years as the global technology cycle reversed and the domestic market experienced exceptional volatility and manipulation concerns in 2000-01.",
            "how_it_happened": "RBI records the global technology-stock meltdown and weaker world activity, while SEBI's 2001-02 annual report documents its investigation into the March 2001 fall. Concentrated enthusiasm met global repricing and weaknesses in the inherited settlement structure.",
            "what_came_out": "The response accelerated dematerialisation, rolling settlement, risk-based margining and clearing reform: all securities moved to rolling settlement, followed by T+3 in 2002 and T+2 in 2003.",
            "how_markets_came_out": "The annual evidence marks the price trough before the 2003-04 rebound, alongside lower money-market rates and a much larger reserve stock. Recovery therefore joined cheaper funding and stronger buffers with repaired trading infrastructure; it was not just a reversal in sentiment.",
            "source_keys": ["rbi_crisis_growth_review", "sebi_annual_2001_02", "sebi_history", "rbi_reserves", "rbi_sensex", "rbi_rates"],
        },
    ]
    for episode in episodes:
        episode["evidence"] = evidence_for(int(episode.pop("start_year")), int(episode.pop("end_year")))
        episode["research_state"] = (
            "Official annual evidence connected"
            if len(episode["evidence"]) >= 4
            else "Additional official series required"
        )
    return episodes


def calculate_macro_context_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    metric_labels = {
        "usd_inr": "USD/INR",
        "gbp_inr": "GBP/INR",
        "eur_inr": "EUR/INR",
        "jpy_100_inr": "JPY/INR (100 JPY)",
        "india_10y_gsec_yield": "India approx. 10-year G-Sec",
    }
    grouped: dict[str, list[dict[str, object]]] = {key: [] for key in metric_labels}
    for row in rows:
        key = row.get("metric_key")
        if key in grouped and isinstance(row.get("date"), date):
            grouped[str(key)].append(row)
    if any(not values for values in grouped.values()):
        return {
            "available": False,
            "band": "unavailable",
            "reason": "Run EOD update to retrieve official RBI/FBIL currency and sovereign-rate data.",
        }

    def change(values: list[dict[str, object]], sessions: int, *, yield_metric: bool) -> float | None:
        if len(values) <= sessions:
            return None
        current = float(values[-1]["value"])
        previous = float(values[-(sessions + 1)]["value"])
        if yield_metric:
            return round((current - previous) * 100, 2)
        return round((current / previous - 1) * 100, 2)

    metrics: dict[str, dict[str, object]] = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda item: item["date"])
        latest = ordered[-1]
        is_yield = key == "india_10y_gsec_yield"
        metrics[key] = {
            "label": metric_labels[key],
            "level": round(float(latest["value"]), 4),
            "unit": latest["unit"],
            "instrument_label": latest["instrument_label"],
            "as_of_date": latest["date"].isoformat(),
            "five_session_change": change(ordered, 5, yield_metric=is_yield),
            "twenty_session_change": change(ordered, 20, yield_metric=is_yield),
            "change_unit": "basis points" if is_yield else "percent",
            "stored_observations": len(ordered),
        }
    latest_dates = [date.fromisoformat(item["as_of_date"]) for item in metrics.values()]
    return {
        "available": True,
        "band": "unranked",
        "reason": "Official levels are visible; directional thresholds are not yet validated.",
        "as_of_date": max(latest_dates).isoformat(),
        "oldest_component_date": min(latest_dates).isoformat(),
        "source": RBI_MACRO_SOURCE,
        "metrics": metrics,
    }


def parse_fred_global_csv(
    csv_payload: str, *, series_id: str, today: date, earliest: date
) -> list[dict[str, object]]:
    if series_id not in FRED_GLOBAL_SERIES or not isinstance(csv_payload, str):
        raise ValueError("invalid_fred_global_response")
    metric_key, unit, _label = FRED_GLOBAL_SERIES[series_id]
    reader = csv.DictReader(io.StringIO(csv_payload))
    if reader.fieldnames != ["observation_date", series_id]:
        raise ValueError("invalid_fred_global_response")
    rows: list[dict[str, object]] = []
    seen: set[date] = set()
    for raw in reader:
        raw_date = str(raw.get("observation_date", "")).strip()
        raw_value = str(raw.get(series_id, "")).strip()
        if raw_value in {"", "."}:
            continue
        try:
            observation_date = date.fromisoformat(raw_date)
            value = float(raw_value)
        except ValueError as error:
            raise ValueError("invalid_fred_global_response") from error
        if observation_date < earliest:
            continue
        if (
            observation_date > today
            or observation_date in seen
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("invalid_fred_global_response")
        seen.add(observation_date)
        rows.append(
            {
                "date": observation_date,
                "metric_key": metric_key,
                "value": value,
                "unit": unit,
                "source_series": series_id,
            }
        )
    if not rows:
        raise ValueError("invalid_fred_global_response")
    return rows


def parse_fred_global_zip(
    zip_payload: bytes, *, today: date, earliest: date
) -> list[dict[str, object]]:
    if not isinstance(zip_payload, bytes) or not zip_payload.startswith(b"PK"):
        raise ValueError("invalid_fred_global_response")
    collected: list[dict[str, object]] = []
    found_series: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                text = archive.read(name).decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text))
                fieldnames = reader.fieldnames or []
                if not fieldnames or fieldnames[0] != "observation_date":
                    raise ValueError("invalid_fred_global_response")
                series_ids = [item for item in fieldnames[1:] if item in FRED_GLOBAL_SERIES]
                if not series_ids:
                    continue
                table_rows = list(reader)
                for series_id in series_ids:
                    single_csv = io.StringIO()
                    writer = csv.writer(single_csv, lineterminator="\n")
                    writer.writerow(["observation_date", series_id])
                    writer.writerows(
                        [raw.get("observation_date", ""), raw.get(series_id, "")]
                        for raw in table_rows
                    )
                    parsed = parse_fred_global_csv(
                        single_csv.getvalue(),
                        series_id=series_id,
                        today=today,
                        earliest=earliest,
                    )
                    collected.extend(parsed)
                    found_series.add(series_id)
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise ValueError("invalid_fred_global_response") from error
    if found_series != set(FRED_GLOBAL_SERIES):
        raise ValueError("invalid_fred_global_response")
    return collected


def calculate_global_risk_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    series_specs = {
        metric_key: {"series_id": series_id, "label": label}
        for series_id, (metric_key, _unit, label) in FRED_GLOBAL_SERIES.items()
    }
    grouped: dict[str, list[dict[str, object]]] = {key: [] for key in series_specs}
    for row in rows:
        key = row.get("metric_key")
        if key in grouped and isinstance(row.get("date"), date):
            grouped[str(key)].append(row)
    if any(not values for values in grouped.values()):
        return {
            "available": False,
            "band": "unavailable",
            "reason": "Run EOD update to retrieve the permitted FRED global-risk series.",
        }

    def percent_change(values: list[dict[str, object]], sessions: int) -> float | None:
        if len(values) <= sessions:
            return None
        current = float(values[-1]["value"])
        previous = float(values[-(sessions + 1)]["value"])
        return round((current / previous - 1) * 100, 2)

    metrics: dict[str, dict[str, object]] = {}
    for key, values in grouped.items():
        ordered = sorted(values, key=lambda item: item["date"])
        latest = ordered[-1]
        metrics[key] = {
            "label": series_specs[key]["label"],
            "source_series": series_specs[key]["series_id"],
            "level": round(float(latest["value"]), 4),
            "unit": latest["unit"],
            "as_of_date": latest["date"].isoformat(),
            "five_session_change_pct": percent_change(ordered, 5),
            "twenty_session_change_pct": percent_change(ordered, 20),
            "stored_observations": len(ordered),
        }

    sp_values = sorted(grouped["sp500"], key=lambda item: item["date"])
    sp_latest = float(sp_values[-1]["value"])
    for window in (20, 50, 200):
        moving_average = (
            sum(float(item["value"]) for item in sp_values[-window:]) / window
            if len(sp_values) >= window
            else None
        )
        metrics["sp500"][f"vs_{window}dma_pct"] = (
            round((sp_latest / moving_average - 1) * 100, 2)
            if moving_average is not None
            else None
        )

    vix_values = sorted(grouped["us_vix"], key=lambda item: item["date"])[-252:]
    vix_latest = float(vix_values[-1]["value"])
    metrics["us_vix"]["one_year_percentile"] = round(
        100 * sum(float(item["value"]) <= vix_latest for item in vix_values) / len(vix_values),
        1,
    )
    latest_dates = [date.fromisoformat(metric["as_of_date"]) for metric in metrics.values()]
    return {
        "available": True,
        "band": "unranked",
        "reason": "Global EOD context is visible; regime thresholds are not yet validated.",
        "source": FRED_GLOBAL_SOURCE,
        "as_of_date": max(latest_dates).isoformat(),
        "oldest_component_date": min(latest_dates).isoformat(),
        "metrics": metrics,
        "scoring_enabled": False,
    }


def calculate_candidate_regime(evidence: dict[str, object]) -> dict[str, object]:
    """Apply the frozen validation-only regime rule to one EOD evidence snapshot."""

    def band_value(candidate: object) -> float | None:
        if not isinstance(candidate, dict):
            return None
        band = candidate.get("band")
        return REGIME_BAND_VALUES.get(str(band))

    trend_score = band_value(evidence.get("trend"))
    breadth_score = band_value(evidence.get("breadth"))
    price_strength_score = band_value(evidence.get("price_strength"))
    participation_parts = [
        score for score in (breadth_score, price_strength_score) if score is not None
    ]
    participation_score = (
        sum(participation_parts) / len(participation_parts)
        if len(participation_parts) == 2
        else None
    )

    volatility = evidence.get("volatility")
    realised_volatility_score = band_value(volatility)
    india_vix_score = None
    if isinstance(volatility, dict):
        india_vix = volatility.get("india_vix")
        if isinstance(india_vix, dict) and india_vix.get("available") is True:
            india_vix_score = band_value(india_vix)
    volatility_parts = [
        score for score in (realised_volatility_score, india_vix_score) if score is not None
    ]
    volatility_score = (
        sum(volatility_parts) / len(volatility_parts) if volatility_parts else None
    )

    cluster_scores = {
        "domestic_trend": trend_score,
        "participation_and_strength": participation_score,
        "volatility_and_stress": volatility_score,
        "institutional_flows": band_value(evidence.get("institutional_flows")),
        "currency_and_rates": band_value(evidence.get("macro_context")),
        "global_risk": band_value(evidence.get("global_risk")),
    }
    clusters = {
        key: {
            "weight": weight,
            "available": cluster_scores[key] is not None,
            "score": cluster_scores[key],
        }
        for key, weight in REGIME_CLUSTER_WEIGHTS.items()
    }
    available_weight = sum(
        REGIME_CLUSTER_WEIGHTS[key]
        for key, score in cluster_scores.items()
        if score is not None
    )
    weighted_total = sum(
        REGIME_CLUSTER_WEIGHTS[key] * float(score)
        for key, score in cluster_scores.items()
        if score is not None
    )
    normalized_score = weighted_total / available_weight if available_weight else None

    freshness = evidence.get("freshness")
    freshness_state = freshness.get("state") if isinstance(freshness, dict) else None
    breadth = evidence.get("breadth")
    raw_coverage = breadth.get("coverage_pct") if isinstance(breadth, dict) else None
    stock_coverage_pct = (
        float(raw_coverage)
        if isinstance(raw_coverage, (int, float)) and not isinstance(raw_coverage, bool)
        else 0.0
    )
    gate_failures: list[str] = []
    if freshness_state != "fresh":
        gate_failures.append("fresh_eod_data_required")
    if stock_coverage_pct < REGIME_MINIMUM_STOCK_COVERAGE_PCT:
        gate_failures.append("stock_coverage_below_80_pct")
    if available_weight < REGIME_MINIMUM_AVAILABLE_WEIGHT:
        gate_failures.append("weighted_evidence_below_60_pct")

    classification_eligible = not gate_failures and normalized_score is not None
    if not classification_eligible:
        label_key = "not_enough_reliable_data"
        confidence = "insufficient"
    else:
        if available_weight >= 0.90 and stock_coverage_pct >= 95.0:
            confidence = "high"
        elif available_weight >= 0.75 and stock_coverage_pct >= 90.0:
            confidence = "medium"
        else:
            confidence = "low"
        if normalized_score >= REGIME_LABEL_THRESHOLDS["positive_market"]:
            label_key = "positive_market"
        elif normalized_score >= REGIME_LABEL_THRESHOLDS["cautiously_positive"]:
            label_key = "cautiously_positive"
        elif normalized_score > REGIME_LABEL_THRESHOLDS["weak_market"]:
            label_key = "uncertain_market"
        elif normalized_score > REGIME_LABEL_THRESHOLDS["high_risk_market"]:
            label_key = "weak_market"
        else:
            label_key = "high_risk_market"

    investor_labels = {
        "positive_market": "Positive market",
        "cautiously_positive": "Cautiously positive",
        "uncertain_market": "Uncertain market",
        "weak_market": "Weak market",
        "high_risk_market": "High-risk market",
        "not_enough_reliable_data": "Not enough reliable data",
    }
    return {
        "rule_version": REGIME_RULE_VERSION,
        "validation_status": "candidate_unvalidated",
        "classification_eligible": classification_eligible,
        "label_key": label_key,
        "label": investor_labels[label_key],
        "score": round(normalized_score * 100, 1) if normalized_score is not None else None,
        "confidence": confidence,
        "available_weight_pct": round(available_weight * 100, 1),
        "stock_coverage_pct": round(stock_coverage_pct, 1),
        "freshness_state": freshness_state or "unavailable",
        "gate_failures": gate_failures,
        "missing_clusters": [
            key for key, score in cluster_scores.items() if score is None
        ],
        "clusters": clusters,
        "contract": {
            "band_values": dict(REGIME_BAND_VALUES),
            "cluster_weights": dict(REGIME_CLUSTER_WEIGHTS),
            "minimum_available_weight_pct": REGIME_MINIMUM_AVAILABLE_WEIGHT * 100,
            "minimum_stock_coverage_pct": REGIME_MINIMUM_STOCK_COVERAGE_PCT,
            "label_thresholds": dict(REGIME_LABEL_THRESHOLDS),
            "confirmation_sessions": 2,
            "recovering_label_requires_transition_history": True,
            "missing_evidence_policy": "exclude_and_reduce_confidence",
        },
    }


def aggregate_historical_closes(
    observations: list[dict[str, object]],
    *,
    frequency: str,
) -> list[dict[str, object]]:
    """Roll observations to the last available close in each requested period.

    The historical atlas uses this adapter when the source record is not
    consistently daily. It never interpolates a missing price or promotes a
    lower-frequency observation to daily precision.
    """
    supported = {"daily", "weekly", "monthly", "quarterly", "annual"}
    if frequency not in supported:
        raise ValueError("invalid_historical_frequency")

    cleaned: dict[date, float] = {}
    for row in observations:
        observation_date = row.get("date")
        raw_close = row.get("close")
        if (
            isinstance(observation_date, date)
            and isinstance(raw_close, (int, float))
            and not isinstance(raw_close, bool)
            and math.isfinite(float(raw_close))
            and float(raw_close) > 0
        ):
            cleaned[observation_date] = float(raw_close)

    def bucket_key(observation_date: date) -> tuple[int, ...]:
        if frequency == "daily":
            return (observation_date.year, observation_date.month, observation_date.day)
        if frequency == "weekly":
            iso_year, iso_week, _ = observation_date.isocalendar()
            return (iso_year, iso_week)
        if frequency == "monthly":
            return (observation_date.year, observation_date.month)
        if frequency == "quarterly":
            return (observation_date.year, (observation_date.month - 1) // 3 + 1)
        return (observation_date.year,)

    buckets: dict[tuple[int, ...], tuple[date, float]] = {}
    for observation_date, close in sorted(cleaned.items()):
        buckets[bucket_key(observation_date)] = (observation_date, close)
    return [
        {"date": observation_date, "close": close}
        for observation_date, close in buckets.values()
    ]


def build_historical_regime_workspace(
    index_candles: list[dict[str, object]],
    *,
    instrument: str = "Nifty 50",
    official_history_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Identify transparent price-cycle episodes from completed index closes.

    Price cycles and economic cycles deliberately remain separate. Bull, bear,
    correction, and rapid-bear candidates are observable from the index path;
    recession and depression labels require a separately versioned macro data
    contract and are therefore never inferred from price alone.
    """
    by_date: dict[date, float] = {}
    for row in index_candles:
        session_date = row.get("date")
        raw_close = row.get("close")
        if (
            isinstance(session_date, date)
            and isinstance(raw_close, (int, float))
            and not isinstance(raw_close, bool)
            and math.isfinite(float(raw_close))
            and float(raw_close) > 0
        ):
            by_date[session_date] = float(raw_close)
    ordered = sorted(by_date.items())
    if len(ordered) < 252:
        raise ValueError("historical_regime_history_unavailable")

    dates = [item[0] for item in ordered]
    closes = [item[1] for item in ordered]
    last_index = len(ordered) - 1

    def pct_change(start_value: float, end_value: float) -> float:
        return (end_value / start_value - 1) * 100

    def forward_returns(anchor: int) -> dict[str, float | None]:
        results: dict[str, float | None] = {}
        for horizon in (20, 60, 120, 252):
            results[str(horizon)] = (
                round(pct_change(closes[anchor], closes[anchor + horizon]), 2)
                if anchor + horizon <= last_index else None
            )
        return results

    def maximum_drawdown(start: int, end: int) -> float:
        peak = closes[start]
        worst = 0.0
        for value in closes[start : end + 1]:
            peak = max(peak, value)
            worst = min(worst, pct_change(peak, value))
        return round(worst, 2)

    def first_recovery(peak_index: int, trough_index: int) -> int | None:
        peak_value = closes[peak_index]
        return next(
            (
                position
                for position in range(trough_index + 1, len(closes))
                if closes[position] >= peak_value
            ),
            None,
        )

    def phase_record(
        *,
        category: str,
        start: int,
        extreme: int,
        confirmation: int,
        status: str,
    ) -> dict[str, object]:
        observation_end = extreme if status == "completed" else last_index
        move = pct_change(closes[start], closes[extreme])
        record: dict[str, object] = {
            "category": category,
            "status": status,
            "start_date": dates[start].isoformat(),
            "confirmation_date": dates[confirmation].isoformat(),
            "extreme_date": dates[extreme].isoformat(),
            "end_date": dates[observation_end].isoformat(),
            "start_close": round(closes[start], 2),
            "extreme_close": round(closes[extreme], 2),
            "end_close": round(closes[observation_end], 2),
            "move_pct": round(move, 2),
            "current_move_pct": round(pct_change(closes[start], closes[observation_end]), 2),
            "sessions_to_confirmation": confirmation - start,
            "duration_sessions": observation_end - start,
            "duration_calendar_days": (dates[observation_end] - dates[start]).days,
            "forward_from_extreme_pct": forward_returns(extreme),
        }
        if category == "bull_market":
            record["max_drawdown_within_phase_pct"] = maximum_drawdown(start, observation_end)
        else:
            recovery = first_recovery(start, extreme)
            record.update(
                {
                    "rapid_decline": confirmation - start <= HISTORICAL_RAPID_BEAR_SESSIONS,
                    "recovered_previous_peak": recovery is not None,
                    "recovery_date": dates[recovery].isoformat() if recovery is not None else None,
                    "recovery_sessions_from_trough": recovery - extreme if recovery is not None else None,
                    "recovery_calendar_days_from_trough": (
                        (dates[recovery] - dates[extreme]).days if recovery is not None else None
                    ),
                }
            )
        return record

    bull_markets: list[dict[str, object]] = []
    bear_markets: list[dict[str, object]] = []
    direction: str | None = None
    candidate_low = 0
    candidate_high = 0
    phase_start = 0
    phase_extreme = 0
    phase_confirmation = 0
    threshold = HISTORICAL_BULL_BEAR_THRESHOLD_PCT / 100

    for position in range(1, len(closes)):
        value = closes[position]
        if direction is None:
            if value < closes[candidate_low]:
                candidate_low = position
            if value > closes[candidate_high]:
                candidate_high = position
            if value >= closes[candidate_low] * (1 + threshold):
                direction = "bull_market"
                phase_start = candidate_low
                phase_extreme = position
                phase_confirmation = position
            elif value <= closes[candidate_high] * (1 - threshold):
                direction = "bear_market"
                phase_start = candidate_high
                phase_extreme = position
                phase_confirmation = position
            continue

        if direction == "bull_market":
            if value > closes[phase_extreme]:
                phase_extreme = position
            if value <= closes[phase_extreme] * (1 - threshold):
                bull_markets.append(
                    phase_record(
                        category="bull_market",
                        start=phase_start,
                        extreme=phase_extreme,
                        confirmation=phase_confirmation,
                        status="completed",
                    )
                )
                direction = "bear_market"
                phase_start = phase_extreme
                phase_extreme = position
                phase_confirmation = position
        else:
            if value < closes[phase_extreme]:
                phase_extreme = position
            if value >= closes[phase_extreme] * (1 + threshold):
                bear_markets.append(
                    phase_record(
                        category="bear_market",
                        start=phase_start,
                        extreme=phase_extreme,
                        confirmation=phase_confirmation,
                        status="completed",
                    )
                )
                direction = "bull_market"
                phase_start = phase_extreme
                phase_extreme = position
                phase_confirmation = position

    if direction is not None:
        target = bull_markets if direction == "bull_market" else bear_markets
        target.append(
            phase_record(
                category=direction,
                start=phase_start,
                extreme=phase_extreme,
                confirmation=phase_confirmation,
                status="ongoing",
            )
        )

    corrections: list[dict[str, object]] = []
    peak_index = 0
    active_peak: int | None = None
    trough_index: int | None = None
    correction_threshold = HISTORICAL_CORRECTION_THRESHOLD_PCT / 100
    for position in range(1, len(closes)):
        value = closes[position]
        if active_peak is None:
            if value >= closes[peak_index]:
                peak_index = position
                continue
            if value <= closes[peak_index] * (1 - correction_threshold):
                active_peak = peak_index
                trough_index = position
            continue
        if trough_index is not None and value < closes[trough_index]:
            trough_index = position
        if value >= closes[active_peak]:
            drawdown = pct_change(closes[active_peak], closes[trough_index])
            if drawdown > -HISTORICAL_BULL_BEAR_THRESHOLD_PCT:
                corrections.append(
                    {
                        "status": "recovered",
                        "peak_date": dates[active_peak].isoformat(),
                        "trough_date": dates[trough_index].isoformat(),
                        "recovery_date": dates[position].isoformat(),
                        "drawdown_pct": round(drawdown, 2),
                        "decline_sessions": trough_index - active_peak,
                        "recovery_sessions": position - trough_index,
                        "total_sessions": position - active_peak,
                        "calendar_days": (dates[position] - dates[active_peak]).days,
                        "forward_from_trough_pct": forward_returns(trough_index),
                    }
                )
            peak_index = position
            active_peak = None
            trough_index = None
    if active_peak is not None and trough_index is not None:
        drawdown = pct_change(closes[active_peak], closes[trough_index])
        if drawdown > -HISTORICAL_BULL_BEAR_THRESHOLD_PCT:
            corrections.append(
                {
                    "status": "ongoing",
                    "peak_date": dates[active_peak].isoformat(),
                    "trough_date": dates[trough_index].isoformat(),
                    "recovery_date": None,
                    "drawdown_pct": round(drawdown, 2),
                    "decline_sessions": trough_index - active_peak,
                    "recovery_sessions": None,
                    "total_sessions": last_index - active_peak,
                    "calendar_days": (dates[-1] - dates[active_peak]).days,
                    "forward_from_trough_pct": forward_returns(trough_index),
                }
            )

    rapid_bears = [item for item in bear_markets if item.get("rapid_decline")]

    def category_summary(rows: list[dict[str, object]], move_key: str) -> dict[str, object]:
        moves = [float(item[move_key]) for item in rows]
        durations = [int(item["duration_sessions"]) for item in rows if "duration_sessions" in item]
        return {
            "count": len(rows),
            "ongoing": sum(item.get("status") == "ongoing" for item in rows),
            "median_move_pct": round(median(moves), 2) if moves else None,
            "median_duration_sessions": round(median(durations)) if durations else None,
        }

    correction_drawdowns = [float(item["drawdown_pct"]) for item in corrections]
    correction_durations = [int(item["total_sessions"]) for item in corrections]
    resolution_views = {
        frequency: {
            "observations": len(
                aggregate_historical_closes(index_candles, frequency=frequency)
            ),
            "method": "last available close in period; no interpolation",
        }
        for frequency in ("daily", "weekly", "monthly", "quarterly", "annual")
    }
    official_history = build_historical_series_summary(official_history_rows or [])
    official_ready = official_history["status"] == "ready"
    episode_stories = build_historical_episode_stories(official_history)
    coverage_ladder = [
        {
            "period": "1875–1978",
            "preferred_frequency": "Event / annual",
            "evidence_grade": "C",
            "purpose": "Institutional history, structural change and major shock narratives",
            "rule": "Do not infer daily drawdowns, breadth or exact turning points from fragmentary records.",
            "status": "Source registry ready; quantitative series to be connected",
        },
        {
            "period": "1978/79–1990",
            "preferred_frequency": "Monthly / quarterly",
            "evidence_grade": "B",
            "purpose": "Early benchmark cycles joined to RBI macroeconomic history",
            "rule": "Use the coarsest complete series when daily observations are not consistent.",
            "status": (
                "Annual market, growth, inflation, rates and currency evidence connected"
                if official_ready else "Sensex and RBI ingestion queued"
            ),
        },
        {
            "period": "1990–1995",
            "preferred_frequency": "Weekly / monthly",
            "evidence_grade": "B",
            "purpose": "Liberalisation, crisis and market-structure transition stories",
            "rule": "Prefer weekly closes until daily coverage and definitions are auditable.",
            "status": (
                "Annual crisis/reform evidence connected through 2003-04; weekly detail queued"
                if official_ready else "Official index-history ingestion queued"
            ),
        },
        {
            "period": "1995–present",
            "preferred_frequency": "Daily, with weekly and monthly context",
            "evidence_grade": "A when source-complete",
            "purpose": "Price cycles, stress, recovery and increasingly rich regime fingerprints",
            "rule": "Daily analysis is allowed only where completed observations are consistent.",
            "status": "Local daily engine active for the reported stored window",
        },
    ]
    story_eras = [
        {
            "period": "1875–1947",
            "title": "Exchange foundations and globally transmitted shocks",
            "family": "Institutional formation",
            "frequency": "Event / annual",
            "evidence_grade": "C",
            "what_happened": "Organised securities trading took institutional form in Bombay while Indian assets also lived through the First World War, the Great Depression and the Second World War.",
            "how_it_happened": "Trade, commodities, imperial policy, wartime finance and global liquidity transmitted shocks into a still-developing domestic market.",
            "what_came_out": "Exchange institutions and market practice deepened, but surviving price records are too fragmented for a continuous daily regime series.",
            "how_markets_came_out": "Treat each shock as a documented historical episode. Recovery paths will be reconstructed from annual prices, activity records and contemporaneous accounts rather than invented daily curves.",
            "research_state": "Narrative scaffold ready; episode-level verification queued",
        },
        {
            "period": "1947–1978",
            "title": "Nation-building and a controlled capital era",
            "family": "Policy-led structural regime",
            "frequency": "Annual / quarterly",
            "evidence_grade": "C",
            "what_happened": "Independence changed the economic, institutional and ownership setting in which the securities market operated.",
            "how_it_happened": "Industrial policy, capital controls, administered finance and later banking changes shaped capital allocation more than a modern market-price signal alone could explain.",
            "what_came_out": "This period provides structural context for later liberalisation and for why older market behaviour is not directly comparable with the electronic era.",
            "how_markets_came_out": "The story will be measured through long-horizon valuation, issuance, activity and macro series, using quarterly or annual observations where that is the honest resolution.",
            "research_state": "Source discovery and annual-series ingestion queued",
        },
        {
            "period": "1978/79–1991",
            "title": "The benchmark era emerges",
            "family": "Market measurement transition",
            "frequency": "Monthly / quarterly",
            "evidence_grade": "B",
            "what_happened": "The Sensex base period begins in 1978–79 and the index was launched in 1986, creating a durable benchmark for Indian equity-market history.",
            "how_it_happened": "A formal benchmark made broad market advances, declines and recoveries more consistently measurable than the earlier record.",
            "what_came_out": "Market stories can begin to combine a continuous price path with RBI growth, inflation, rates, currency and credit evidence.",
            "how_markets_came_out": "Monthly and quarterly observations will define cycles first; weekly or daily precision will be used only after source coverage is verified.",
            "research_state": "Official Sensex and RBI time-series ingestion queued",
        },
        {
            "period": "1991–1995",
            "title": "Liberalisation and the market-structure reset",
            "family": "Crisis, reform and transition",
            "frequency": "Weekly / monthly",
            "evidence_grade": "B",
            "what_happened": "The balance-of-payments crisis and economic reforms coincided with a profound redesign of securities-market institutions and trading.",
            "how_it_happened": "Macroeconomic pressure, liberalisation, the 1992 securities-market crisis, stronger regulation and the emergence of electronic exchange infrastructure interacted.",
            "what_came_out": "Price discovery, regulation, settlement and participation moved toward the modern market architecture.",
            "how_markets_came_out": "The recovery story must separate economic stabilisation, reform-driven rerating and institutional repair; weekly data is sufficient for the regime path when daily series disagree.",
            "research_state": "Narrative anchors ready; price and macro joins queued",
        },
        {
            "period": "1995–2003",
            "title": "Electronic markets meet global contagion",
            "family": "Modernisation and external shocks",
            "frequency": "Daily / weekly",
            "evidence_grade": "A/B",
            "what_happened": "Electronic trading expanded while the Asian financial crisis and the global technology boom-and-bust tested the new market structure.",
            "how_it_happened": "Cross-border risk appetite, currency stress, technology enthusiasm and changing domestic participation produced alternating advances and drawdowns.",
            "what_came_out": "A more observable market generated richer price, volume and cross-index evidence for comparing fear, crowding and recovery.",
            "how_markets_came_out": "Quantify each shock separately and test whether recovery began through volatility relief, breadth repair, leadership change or macro stabilisation.",
            "research_state": "Daily price-history extension queued",
        },
        {
            "period": "2003–2009",
            "title": "Credit boom to global financial crisis",
            "family": "Bull market, crash and recovery",
            "frequency": "Daily",
            "evidence_grade": "A/B",
            "what_happened": "A powerful expansion in growth, liquidity and participation culminated in the 2008 global financial crisis and a deep equity drawdown.",
            "how_it_happened": "Global credit, capital flows, earnings expectations and risk appetite reinforced the advance, then reversed as the global financial system came under stress.",
            "what_came_out": "The episode offers a high-value test of euphoria, concentration, liquidity withdrawal, capitulation and policy response.",
            "how_markets_came_out": "Measure the sequence from volatility and liquidity relief to breadth, earnings and credit repair instead of treating the rebound as one date.",
            "research_state": "Price, flow, macro and recovery fingerprint queued",
        },
        {
            "period": "2009–2020",
            "title": "Post-crisis liquidity and domestic resets",
            "family": "Expansion with repeated corrections",
            "frequency": "Daily",
            "evidence_grade": "A/B",
            "what_happened": "The post-crisis advance contained multiple global and domestic interruptions rather than one uninterrupted bull market.",
            "how_it_happened": "Global liquidity, domestic growth and policy changes interacted with taper stress, commodity moves, currency pressure and periodic earnings resets.",
            "what_came_out": "This era can reveal which corrections were temporary risk-off events and which carried longer changes in leadership or earnings.",
            "how_markets_came_out": "Compare recovery breadth, sector rotation, foreign and domestic flows, volatility and earnings after each interruption.",
            "research_state": "Episode segmentation and fingerprinting queued",
        },
        {
            "period": "2020–present",
            "title": "Pandemic shock, rapid recovery and inflation reset",
            "family": "Exogenous shock and policy transition",
            "frequency": "Daily",
            "evidence_grade": "A when source-complete",
            "what_happened": "The pandemic produced an unusually fast global shock, followed by a powerful recovery and a later inflation-and-rates transition.",
            "how_it_happened": "Activity shutdowns, extraordinary policy support, reopening, supply disruption, retail participation and later monetary tightening changed the market backdrop in quick succession.",
            "what_came_out": "The period provides detailed evidence for crash speed, policy response, participation, sector rotation and the difference between economic and market recovery.",
            "how_markets_came_out": "Track the hand-off from relief rally to breadth and earnings confirmation, then test which traits survived the inflation and rate reset.",
            "research_state": "Local daily atlas active; external fingerprints to be joined",
        },
    ]
    if official_ready:
        for era in story_eras:
            if era["period"] == "1978/79–1991":
                era["research_state"] = "Official annual market and macro evidence connected; sourced episodes active"
            elif era["period"] in {"1991–1995", "1995–2003"}:
                era["research_state"] = "Official annual market and macro evidence connected; sourced episodes active"
            elif era["period"] in {"2003–2009", "2009–2020"}:
                era["research_state"] = "Official annual market and macro anchors connected; higher-frequency episode joins queued"
    source_registry = [
        {
            "key": "sebi_history",
            "name": "SEBI historical perspective",
            "authority": "SEBI",
            "use": "Exchange formation, regulation and structural milestones",
            "url": "https://www.sebi.gov.in/media/speeches/mar-2004/a-historical-perspective-of-the-securities-market-reforms_2882.html",
        },
        {
            "key": "bse_milestones",
            "name": "BSE milestones",
            "authority": "BSE",
            "use": "Sensex base period, launch and electronic-market milestones",
            "url": "https://www.bseindia.com/downloads1/BSE_Update_Jan_2016.pdf",
        },
        {
            "key": "nifty_methodology",
            "name": "NIFTY 50 official index page",
            "authority": "NSE Indices",
            "use": "Modern benchmark definitions and methodology",
            "url": "https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY-50",
        },
        {
            "key": "rbi_handbook",
            "name": "RBI Handbook and DBIE coverage",
            "authority": "Reserve Bank of India",
            "use": "Growth, inflation, rates, currency, money, credit and financial history",
            "url": "https://www.rbi.org.in/scripts/BS_ViewBulletin.aspx?Id=879",
        },
        {
            "key": "rbi_sensex",
            "name": "RBI Handbook 2026 Table 85",
            "authority": "Reserve Bank of India",
            "use": "BSE Sensex financial-year annual averages",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=23910",
        },
        {
            "key": "rbi_wpi",
            "name": "RBI Handbook 2026 Table 33",
            "authority": "Reserve Bank of India",
            "use": "All-commodities WPI annual averages and published base periods",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=23858",
        },
        {
            "key": "rbi_growth",
            "name": "RBI Handbook 2006 Table 237",
            "authority": "Reserve Bank of India",
            "use": "Historical real GDP growth at stated constant-price bases",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8787",
        },
        {
            "key": "rbi_rates",
            "name": "RBI Handbook 2006 Table 74",
            "authority": "Reserve Bank of India",
            "use": "Historical call/notice money rates",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8624",
        },
        {
            "key": "rbi_fx",
            "name": "RBI Handbook 2006 Table 154",
            "authority": "Reserve Bank of India",
            "use": "Financial-year INR/USD annual averages",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=8704",
        },
        {
            "key": "rbi_fiscal",
            "name": "RBI Handbook 2026 Table 237",
            "authority": "Reserve Bank of India",
            "use": "Central gross fiscal deficit as percentage of GDP",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=24062",
        },
        {
            "key": "rbi_bop_history",
            "name": "RBI history of the 1991 balance-of-payments crisis",
            "authority": "Reserve Bank of India",
            "use": "Crisis transmission, exchange-rate transition and external-sector reform",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?Id=18086",
        },
        {
            "key": "sebi_reforms_1992_1996",
            "name": "SEBI securities-market reforms, 1992–1996",
            "authority": "SEBI",
            "use": "Statutory regulation, capital-issue reform, settlement and market infrastructure",
            "url": "https://www.sebi.gov.in/sebi_data/commondocs/pt01_h.html",
        },
        {
            "key": "nse_milestones",
            "name": "NSE history and milestones",
            "authority": "National Stock Exchange of India",
            "use": "Screen-based trading, NIFTY 50, dematerialised settlement and derivatives milestones",
            "url": "https://www.nseindia.com/static/national-stock-exchange/history-milestones",
        },
        {
            "key": "sebi_annual_1997_98",
            "name": "SEBI Annual Report 1997-98",
            "authority": "SEBI",
            "use": "Clearing guarantees, dematerialisation and the first T+5 rolling-settlement phase",
            "url": "https://www.sebi.gov.in/sebi_data/commondocs/1997-98_p.pdf",
        },
        {
            "key": "sebi_annual_2001_02",
            "name": "SEBI Annual Report 2001-02",
            "authority": "SEBI",
            "use": "Official investigation record for the March 2001 market fall and subsequent reforms",
            "url": "https://www.sebi.gov.in/sebi_data/commondocs/ar01022_p.pdf",
        },
        {
            "key": "rbi_crisis_growth_review",
            "name": "RBI financial-crisis and growth review",
            "authority": "Reserve Bank of India",
            "use": "Asian-crisis and dot-com-bust transmission into Indian output, investment and markets",
            "url": "https://rbi.org.in/scripts/AnnualReportPublications.aspx?Id=896",
        },
        {
            "key": "rbi_reserves",
            "name": "RBI Handbook 2024 Table 150",
            "authority": "Reserve Bank of India",
            "use": "End-financial-year foreign-exchange reserve stock in US dollars",
            "url": "https://rbi.org.in/scripts/PublicationsView.aspx?id=22624",
        },
    ]
    return {
        "ok": True,
        "contract_version": HISTORICAL_REGIME_CONTRACT_VERSION,
        "instrument": instrument,
        "history": {
            "from_date": dates[0].isoformat(),
            "to_date": dates[-1].isoformat(),
            "sessions": len(ordered),
            "source": "Validated local completed EOD candles",
            "analysis_frequency": "daily",
        },
        "resolution_views": resolution_views,
        "official_history": official_history,
        "episode_stories": episode_stories,
        "coverage_ladder": coverage_ladder,
        "story_eras": story_eras,
        "story_method": [
            {
                "question": "What happened?",
                "answer": "Establish the observable market, economic and institutional sequence without hindsight labels.",
            },
            {
                "question": "How did it happen?",
                "answer": "Connect catalysts, transmission channels, positioning, policy and human-behaviour proxies.",
            },
            {
                "question": "What came out of it?",
                "answer": "Record the economic, regulatory, market-structure and portfolio consequences.",
            },
            {
                "question": "How did markets come out?",
                "answer": "Measure the path from stress relief through breadth, leadership, earnings, liquidity and prior-peak recovery.",
            },
        ],
        "source_registry": source_registry,
        "thresholds": {
            "bull_bear_reversal_pct": HISTORICAL_BULL_BEAR_THRESHOLD_PCT,
            "correction_drawdown_pct": HISTORICAL_CORRECTION_THRESHOLD_PCT,
            "rapid_bear_confirmation_sessions": HISTORICAL_RAPID_BEAR_SESSIONS,
        },
        "summary": {
            "bull_markets": category_summary(bull_markets, "move_pct"),
            "bear_markets": category_summary(bear_markets, "move_pct"),
            "corrections": {
                "count": len(corrections),
                "ongoing": sum(item.get("status") == "ongoing" for item in corrections),
                "median_move_pct": round(median(correction_drawdowns), 2) if correction_drawdowns else None,
                "median_duration_sessions": round(median(correction_durations)) if correction_durations else None,
            },
            "rapid_bear_candidates": len(rapid_bears),
        },
        "bull_markets": bull_markets,
        "bear_markets": bear_markets,
        "corrections": corrections,
        "rapid_bear_candidates": rapid_bears,
        "economic_cycles": {
            "recessions": {
                "status": "macro_history_required",
                "episodes": [],
                "definition": "Requires a versioned point-in-time macro rule using real activity, employment, income, credit, and policy evidence; never inferred from an equity drawdown alone.",
            },
            "depressions": {
                "status": "definition_and_macro_history_required",
                "episodes": [],
                "definition": "No universal mechanical depression definition is assumed. A documented severity-and-duration contract and authoritative macro history are required before any label is published.",
            },
        },
        "architecture": {
            "layers": [
                {
                    "name": "Point-in-time evidence store",
                    "purpose": "Preserve the data and constituent membership known at each historical observation without look-ahead, at its honest daily, weekly, monthly, quarterly, annual or event resolution.",
                },
                {
                    "name": "Market-cycle identifier",
                    "purpose": "Detect transparent 20% bull/bear reversals, 10–20% corrections, speed, duration, recovery, and forward paths.",
                },
                {
                    "name": "Multi-factor regime fingerprint",
                    "purpose": "Attach trend, breadth, leadership, volatility, flows, rates/currency, global risk, derivatives, earnings, and macro states to each episode.",
                },
                {
                    "name": "Behavioural hypothesis layer",
                    "purpose": "Test observable proxies for optimism, crowding, fear, capitulation, and recovery; emotion is a hypothesis, not a directly observed variable.",
                },
                {
                    "name": "Outcome and analogue engine",
                    "purpose": "Compare forward returns, drawdowns, recovery time, sector leadership, transition paths, and portfolio sensitivity using held-out periods.",
                },
            ],
            "fingerprint_categories": [
                "Trend and momentum",
                "Breadth and participation",
                "Leadership and concentration",
                "Volatility and stress",
                "Institutional flows and liquidity",
                "Rates, currency, and credit",
                "Global risk backdrop",
                "Derivatives positioning",
                "Earnings and valuation",
                "Macro growth and inflation",
            ],
        },
        "limitations": [
            "The daily episode map is price-path research; the long-history story layer also accepts lower-frequency and documentary evidence without pretending it is daily data.",
            "The available local history begins at the reported start date; an episode already in progress then may be left-censored.",
            "A 20% or 10% threshold is a transparent convention, not a law of markets.",
            "Forward windows overlap and are descriptive rather than independent observations.",
            "Recession and depression labels are withheld until authoritative point-in-time macro histories and definitions are connected.",
        ],
    }


def build_regime_external_cluster_readiness(
    *,
    institutional_flow_rows: list[dict[str, object]] | None = None,
    confirmed_fpi_rows: list[dict[str, object]] | None = None,
    macro_snapshot_rows: list[dict[str, object]] | None = None,
    global_risk_rows: list[dict[str, object]] | None = None,
    futures_snapshot_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Audit dated external evidence before it can enter walk-forward scoring."""

    def complete_dates(
        rows: list[dict[str, object]],
        *,
        group_key: str,
        required_values: set[str],
    ) -> list[date]:
        found: defaultdict[date, set[str]] = defaultdict(set)
        for row in rows:
            row_date = row.get("date")
            value = row.get(group_key)
            if isinstance(row_date, date) and isinstance(value, str):
                found[row_date].add(value)
        return sorted(row_date for row_date, values in found.items() if required_values <= values)

    provisional_dates = complete_dates(
        institutional_flow_rows or [],
        group_key="category",
        required_values={"FII/FPI", "DII"},
    )
    confirmed_dates = complete_dates(
        confirmed_fpi_rows or [],
        group_key="investment_route",
        required_values={"Stock Exchange", "Primary market & others", "Sub-total"},
    )
    macro_dates = complete_dates(
        macro_snapshot_rows or [],
        group_key="metric_key",
        required_values={
            "usd_inr",
            "gbp_inr",
            "eur_inr",
            "jpy_100_inr",
            "india_10y_gsec_yield",
        },
    )
    global_dates = complete_dates(
        global_risk_rows or [],
        group_key="metric_key",
        required_values=set(value[0] for value in FRED_GLOBAL_SERIES.values()),
    )
    futures_by_date: defaultdict[date, set[str]] = defaultdict(set)
    for row in futures_snapshot_rows or []:
        row_date = row.get("date")
        underlying = row.get("underlying")
        if isinstance(row_date, date) and isinstance(underlying, str):
            futures_by_date[row_date].add(underlying)
    futures_dates = sorted(
        row_date
        for row_date, underlyings in futures_by_date.items()
        if len(underlyings) >= math.ceil(FNO_UNIVERSE_EXPECTED * 0.80)
    )

    def readiness_row(
        key: str,
        label: str,
        cluster: str,
        weight_pct: float | None,
        dates: list[date],
        source: str,
    ) -> dict[str, object]:
        stored_sessions = len(dates)
        history_ready = stored_sessions >= REGIME_EXTERNAL_HISTORY_SESSIONS
        walk_forward_ready = stored_sessions >= REGIME_EXTERNAL_WALK_FORWARD_SESSIONS
        return {
            "key": key,
            "label": label,
            "cluster": cluster,
            "candidate_weight_pct": weight_pct,
            "stored_sessions": stored_sessions,
            "first_session": dates[0].isoformat() if dates else None,
            "last_session": dates[-1].isoformat() if dates else None,
            "history_sessions_required": REGIME_EXTERNAL_HISTORY_SESSIONS,
            "walk_forward_sessions_required": REGIME_EXTERNAL_WALK_FORWARD_SESSIONS,
            "sessions_until_history_ready": max(
                0, REGIME_EXTERNAL_HISTORY_SESSIONS - stored_sessions
            ),
            "sessions_until_walk_forward_ready": max(
                0, REGIME_EXTERNAL_WALK_FORWARD_SESSIONS - stored_sessions
            ),
            "history_ready": history_ready,
            "walk_forward_ready": walk_forward_ready,
            "scoring_ready": False,
            "source": source,
            "status": (
                "threshold_validation_pending"
                if walk_forward_ready else "accumulating_history"
            ),
        }

    rows = [
        readiness_row(
            "nse_provisional_institutional_flows",
            "NSE provisional FII/FPI and DII cash flows",
            "Institutional flows",
            15.0,
            provisional_dates,
            NSE_FII_DII_SOURCE,
        ),
        readiness_row(
            "nsdl_confirmed_fpi",
            "NSDL confirmed FPI equity investment",
            "Institutional-flow cross-check",
            None,
            confirmed_dates,
            NSDL_FPI_SOURCE,
        ),
        readiness_row(
            "rbi_currency_and_rates",
            "RBI/FBIL currency and sovereign rates",
            "Currency and rates",
            10.0,
            macro_dates,
            RBI_MACRO_SOURCE,
        ),
        readiness_row(
            "fred_global_risk",
            "Permitted FRED global-risk series",
            "Global risk",
            15.0,
            global_dates,
            FRED_GLOBAL_SOURCE,
        ),
        readiness_row(
            "kite_futures_oi",
            "Kite F&O price and open-interest snapshots",
            "F&O confirmation layer",
            None,
            futures_dates,
            KITE_FUTURES_SOURCE,
        ),
    ]
    return {
        "minimum_history_sessions": REGIME_EXTERNAL_HISTORY_SESSIONS,
        "minimum_walk_forward_sessions": REGIME_EXTERNAL_WALK_FORWARD_SESSIONS,
        "rows": rows,
        "candidate_weight_ready_pct": sum(
            float(row["candidate_weight_pct"] or 0)
            for row in rows
            if row["scoring_ready"]
        ),
        "note": (
            "Coverage readiness does not activate scoring. Every external cluster "
            "still requires frozen directional thresholds and out-of-sample review."
        ),
    }


def apply_recovering_market_state(
    observations: list[dict[str, object]],
    *,
    minimum_risk_sessions: int = REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
    maximum_recovery_sessions: int = REGIME_RECOVERY_MAXIMUM_SESSIONS,
) -> dict[str, object]:
    """Apply an outcome-blind transition state after sustained risk episodes."""
    if minimum_risk_sessions <= 0 or maximum_recovery_sessions <= 0:
        raise ValueError("invalid_recovery_state_contract")
    risk_labels = {"weak_market", "high_risk_market"}
    recovery_entry_labels = {"uncertain_market", "cautiously_positive"}
    risk_run = 0
    risk_run_start: date | None = None
    last_risk_label: str | None = None
    active_episode: dict[str, object] | None = None
    episodes: list[dict[str, object]] = []

    def close_episode(exit_reason: str, exit_date: date | None) -> None:
        nonlocal active_episode
        if active_episode is None:
            return
        active_episode["exit_reason"] = exit_reason
        active_episode["exit_date"] = exit_date.isoformat() if exit_date else None
        episodes.append(active_episode)
        active_episode = None

    for position, observation in enumerate(observations):
        label = observation.get("confirmed_label_key")
        session_date = observation.get("date")
        if not isinstance(label, str) or not isinstance(session_date, date):
            observation["transition_label_key"] = None
            continue

        if active_episode is not None:
            if label in risk_labels:
                close_episode("relapsed_to_risk", session_date)
                observation["transition_label_key"] = label
                risk_run = 1
                risk_run_start = session_date
                last_risk_label = label
                continue
            if label == "positive_market":
                close_episode("positive_market_confirmed", session_date)
                observation["transition_label_key"] = label
                risk_run = 0
                risk_run_start = None
                last_risk_label = None
                continue
            if int(active_episode["recovery_sessions"]) < maximum_recovery_sessions:
                active_episode["recovery_sessions"] = int(active_episode["recovery_sessions"]) + 1
                observation["transition_label_key"] = "recovering_market"
                continue
            previous_date = observations[position - 1].get("date") if position else None
            close_episode(
                "maximum_window_reached",
                previous_date if isinstance(previous_date, date) else session_date,
            )
            observation["transition_label_key"] = label
            risk_run = 0
            risk_run_start = None
            last_risk_label = None
            continue

        if label in risk_labels:
            if risk_run == 0:
                risk_run_start = session_date
            risk_run += 1
            last_risk_label = label
            observation["transition_label_key"] = label
            continue

        if risk_run >= minimum_risk_sessions and label in recovery_entry_labels:
            active_episode = {
                "entry_date": session_date.isoformat(),
                "entry_base_regime": label,
                "prior_risk_regime": last_risk_label,
                "prior_risk_start": risk_run_start.isoformat() if risk_run_start else None,
                "prior_risk_sessions": risk_run,
                "recovery_sessions": 1,
                "exit_date": None,
                "exit_reason": "still_open",
            }
            observation["transition_label_key"] = "recovering_market"
        else:
            observation["transition_label_key"] = label
        risk_run = 0
        risk_run_start = None
        last_risk_label = None

    if active_episode is not None:
        close_episode("still_open", None)

    exit_counts = {
        reason: sum(episode["exit_reason"] == reason for episode in episodes)
        for reason in (
            "positive_market_confirmed",
            "relapsed_to_risk",
            "maximum_window_reached",
            "still_open",
        )
    }
    return {
        "status": "validation_only_outcome_blind_rule",
        "minimum_prior_risk_sessions": minimum_risk_sessions,
        "maximum_recovery_sessions": maximum_recovery_sessions,
        "entry_base_regimes": sorted(recovery_entry_labels),
        "positive_market_exits_immediately": True,
        "episodes": episodes,
        "episode_count": len(episodes),
        "exit_counts": exit_counts,
        "method": (
            "After at least five consecutive confirmed weak/high-risk sessions, "
            "an improvement to uncertain or cautiously positive is labelled Recovering "
            "market for at most 20 sessions. Positive confirmation or renewed risk ends it."
        ),
    }


def build_regime_validation_universe(
    instruments: list[dict[str, object]],
    *,
    stock_names: set[str] | None = None,
    constituent_snapshot: dict[str, object] | None = None,
    supported_indices: tuple[str, ...] = SEASONALITY_INDICES,
    trailing_sessions: int = REGIME_VALIDATION_TRAILING_SESSIONS,
    maximum_horizon: int = max(REGIME_VALIDATION_DEFAULT_HORIZONS),
) -> dict[str, object]:
    """Describe validation readiness without treating short history as an error."""
    by_name = {
        str(item["display_name"]): item
        for item in instruments
        if item.get("display_name") in supported_indices
    }
    rows: list[dict[str, object]] = []
    constituent_indices = (
        constituent_snapshot.get("indices", {})
        if isinstance(constituent_snapshot, dict) else {}
    )
    for display_name in supported_indices:
        item = by_name.get(display_name, {})
        session_count = int(item.get("session_count") or 0)
        current_regime_ready = session_count >= trailing_sessions
        walk_forward_ready = session_count >= trailing_sessions + maximum_horizon
        symbols = constituent_indices.get(display_name, []) if isinstance(constituent_indices, dict) else []
        official_constituent_count = len(symbols) if isinstance(symbols, list) else 0
        fno_constituent_count = (
            len(set(symbols) & stock_names)
            if isinstance(symbols, list) and stock_names is not None else None
        )
        constituent_breadth_ready = (
            fno_constituent_count >= 5
            if fno_constituent_count is not None else True
        )
        rows.append(
            {
                "display_name": display_name,
                "session_count": session_count,
                "first_session": (
                    item["first_session"].isoformat()
                    if isinstance(item.get("first_session"), date)
                    else None
                ),
                "last_session": (
                    item["last_session"].isoformat()
                    if isinstance(item.get("last_session"), date)
                    else None
                ),
                "current_regime_ready": current_regime_ready,
                "walk_forward_ready": walk_forward_ready,
                "constituent_breadth_ready": constituent_breadth_ready,
                "validation_ready": walk_forward_ready and constituent_breadth_ready,
                "official_constituent_count": official_constituent_count or None,
                "fno_constituent_count": fno_constituent_count,
                "sessions_until_current_regime": max(0, trailing_sessions - session_count),
                "sessions_until_walk_forward": max(
                    0, trailing_sessions + maximum_horizon - session_count
                ),
            }
        )
    return {
        "ok": True,
        "trailing_sessions_required": trailing_sessions,
        "maximum_forward_horizon": maximum_horizon,
        "walk_forward_sessions_required": trailing_sessions + maximum_horizon,
        "benchmark": "Nifty 50",
        "constituent_snapshot_as_of": (
            constituent_snapshot.get("as_of")
            if isinstance(constituent_snapshot, dict) else None
        ),
        "indices": rows,
    }


def calculate_regime_walk_forward_validation(
    index_candles: list[dict[str, object]],
    stock_histories: dict[str, list[dict[str, object]]],
    *,
    india_vix_candles: list[dict[str, object]] | None = None,
    target_index: str = "Nifty 50",
    benchmark_candles: list[dict[str, object]] | None = None,
    benchmark_index: str | None = None,
    constituent_symbols: list[str] | None = None,
    constituent_membership_history: list[dict[str, object]] | None = None,
    constituent_snapshot_as_of: str | None = None,
    institutional_flow_rows: list[dict[str, object]] | None = None,
    confirmed_fpi_rows: list[dict[str, object]] | None = None,
    macro_snapshot_rows: list[dict[str, object]] | None = None,
    global_risk_rows: list[dict[str, object]] | None = None,
    futures_snapshot_rows: list[dict[str, object]] | None = None,
    event_windows: tuple[dict[str, object], ...] = REGIME_VALIDATION_EVENTS,
    horizons: tuple[int, ...] = REGIME_VALIDATION_DEFAULT_HORIZONS,
) -> dict[str, object]:
    """Evaluate the frozen candidate using only evidence known at each historical EOD."""
    if not horizons or any(not isinstance(item, int) or item <= 0 for item in horizons):
        raise ValueError("invalid_regime_validation_horizons")
    ordered_index = sorted(index_candles, key=lambda item: item["date"])
    maximum_horizon = max(horizons)
    if len(ordered_index) < 252 + maximum_horizon:
        raise ValueError("regime_validation_history_unavailable")
    index_dates = [item["date"] for item in ordered_index]
    index_closes = [float(item["close"]) for item in ordered_index]
    benchmark_by_date = {
        item["date"]: float(item["close"])
        for item in sorted(benchmark_candles or [], key=lambda item: item["date"])
    }
    use_benchmark = bool(
        benchmark_index
        and benchmark_index != target_index
        and benchmark_by_date
    )
    index_prefix = [0.0]
    for close in index_closes:
        index_prefix.append(index_prefix[-1] + close)

    def window_average(prefix: list[float], end: int, length: int) -> float:
        return (prefix[end + 1] - prefix[end + 1 - length]) / length

    daily_log_returns = [
        math.log(current / previous)
        for previous, current in zip(index_closes, index_closes[1:])
    ]
    realised_volatility: list[float | None] = [None] * len(index_closes)
    for position in range(20, len(index_closes)):
        variance = _sample_variance(daily_log_returns[position - 20 : position])
        if variance is not None:
            realised_volatility[position] = math.sqrt(variance * 252) * 100

    vix_bands: dict[date, str] = {}
    ordered_vix = sorted(india_vix_candles or [], key=lambda item: item["date"])
    vix_closes = [float(item["close"]) for item in ordered_vix]
    for position in range(251, len(ordered_vix)):
        current = vix_closes[position]
        window = vix_closes[position - 251 : position + 1]
        percentile = 100 * sum(value <= current for value in window) / len(window)
        vix_bands[ordered_vix[position]["date"]] = (
            "defensive" if percentile >= 85 else "mixed" if percentile >= 60 else "constructive"
        )

    official_constituents = sorted(set(constituent_symbols or []))
    membership_history: list[dict[str, object]] = []
    for snapshot in constituent_membership_history or []:
        effective_from = snapshot.get("effective_from")
        effective_to = snapshot.get("effective_to")
        symbols = snapshot.get("symbols")
        if (
            isinstance(effective_from, date)
            and (effective_to is None or isinstance(effective_to, date))
            and isinstance(symbols, list)
        ):
            membership_history.append(
                {
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "symbols": sorted({str(symbol) for symbol in symbols if str(symbol)}),
                }
            )
    membership_history.sort(key=lambda item: item["effective_from"])
    historical_constituents = sorted(
        {
            symbol
            for snapshot in membership_history
            for symbol in snapshot["symbols"]
        }
    )
    selected_constituents = historical_constituents or official_constituents
    selected_stock_histories = (
        {
            symbol: stock_histories[symbol]
            for symbol in selected_constituents
            if symbol in stock_histories
        }
        if selected_constituents else stock_histories
    )
    if len(selected_stock_histories) < 5:
        raise ValueError("regime_validation_constituent_coverage_unavailable")

    metrics_by_date: defaultdict[date, list[tuple[str, bool, bool, bool, int, bool, bool]]] = defaultdict(list)
    for symbol, history in selected_stock_histories.items():
        ordered = sorted(history, key=lambda item: item["date"])
        if len(ordered) < 252:
            continue
        closes = [float(item["close"]) for item in ordered]
        prefix = [0.0]
        for close in closes:
            prefix.append(prefix[-1] + close)
        maximums: deque[int] = deque()
        minimums: deque[int] = deque()
        for position, close in enumerate(closes):
            while maximums and closes[maximums[-1]] <= close:
                maximums.pop()
            maximums.append(position)
            while minimums and closes[minimums[-1]] >= close:
                minimums.pop()
            minimums.append(position)
            cutoff = position - 251
            while maximums and maximums[0] < cutoff:
                maximums.popleft()
            while minimums and minimums[0] < cutoff:
                minimums.popleft()
            if position < 251:
                continue
            advance_state = 1 if close > closes[position - 1] else -1 if close < closes[position - 1] else 0
            metrics_by_date[ordered[position]["date"]].append(
                (
                    symbol,
                    close > window_average(prefix, position, 20),
                    close > window_average(prefix, position, 50),
                    close > window_average(prefix, position, 200),
                    advance_state,
                    close >= closes[maximums[0]] * 0.95,
                    close <= closes[minimums[0]] * 1.05,
                )
            )

    universe_total = len(selected_stock_histories)
    if universe_total == 0:
        raise ValueError("regime_validation_stock_history_unavailable")

    observations: list[dict[str, object]] = []
    state_observations: list[dict[str, object]] = []
    skipped_for_coverage = 0

    def membership_for_date(session_date: date) -> set[str] | None:
        for snapshot in reversed(membership_history):
            if snapshot["effective_from"] <= session_date and (
                snapshot["effective_to"] is None
                or session_date <= snapshot["effective_to"]
            ):
                return set(snapshot["symbols"])
        return set(official_constituents) if not membership_history and official_constituents else None

    for position in range(251, len(index_closes)):
        session_date = index_dates[position]
        session_membership = membership_for_date(session_date)
        if membership_history and session_membership is None:
            skipped_for_coverage += 1
            continue
        stock_metrics = [
            item
            for item in metrics_by_date.get(session_date, [])
            if session_membership is None or item[0] in session_membership
        ]
        session_universe_total = (
            len(session_membership.intersection(stock_histories))
            if session_membership is not None else universe_total
        )
        if session_universe_total < 5:
            skipped_for_coverage += 1
            continue
        coverage_pct = 100 * len(stock_metrics) / session_universe_total
        if coverage_pct < REGIME_MINIMUM_STOCK_COVERAGE_PCT:
            skipped_for_coverage += 1
            continue

        close = index_closes[position]
        sma50 = window_average(index_prefix, position, 50)
        sma200 = window_average(index_prefix, position, 200)
        prior_sma50 = (
            index_prefix[position - 19] - index_prefix[position - 69]
        ) / 50
        sma50_slope = (sma50 / prior_sma50 - 1) * 100
        if close > sma50 > sma200 and sma50_slope > 0:
            trend_band = "constructive"
        elif close < sma50 < sma200 and sma50_slope < 0:
            trend_band = "defensive"
        else:
            trend_band = "mixed"

        evaluated = len(stock_metrics)
        above50 = 100 * sum(item[2] for item in stock_metrics) / evaluated
        above200 = 100 * sum(item[3] for item in stock_metrics) / evaluated
        advances = sum(item[4] > 0 for item in stock_metrics)
        declines = sum(item[4] < 0 for item in stock_metrics)
        if above50 >= 55 and above200 >= 55 and advances > declines:
            breadth_band = "constructive"
        elif (above50 < 40 and above200 < 40) or (declines and advances / declines < 0.67):
            breadth_band = "defensive"
        else:
            breadth_band = "mixed"

        near_high_pct = 100 * sum(item[5] for item in stock_metrics) / evaluated
        near_low_pct = 100 * sum(item[6] for item in stock_metrics) / evaluated
        net_strength = near_high_pct - near_low_pct
        price_strength_band = (
            "constructive" if net_strength >= 10 else "defensive" if net_strength <= -10 else "mixed"
        )

        current_volatility = realised_volatility[position]
        historical_volatility = [
            value
            for value in realised_volatility[max(20, position - 251) : position + 1]
            if value is not None
        ]
        if current_volatility is None or not historical_volatility:
            continue
        volatility_percentile = (
            100
            * sum(value <= current_volatility for value in historical_volatility)
            / len(historical_volatility)
        )
        volatility_band = (
            "defensive"
            if volatility_percentile >= 85
            else "mixed"
            if volatility_percentile >= 60
            else "constructive"
        )
        vix_band = vix_bands.get(session_date)
        evidence = {
            "trend": {"band": trend_band},
            "breadth": {"band": breadth_band, "coverage_pct": coverage_pct},
            "price_strength": {"band": price_strength_band},
            "volatility": {
                "band": volatility_band,
                "india_vix": {
                    "available": vix_band is not None,
                    "band": vix_band or "unranked",
                },
            },
            "institutional_flows": {"band": "unranked"},
            "macro_context": {"band": "unranked"},
            "global_risk": {"band": "unranked"},
            "freshness": {"state": "fresh"},
        }
        candidate = calculate_candidate_regime(evidence)
        if not candidate["classification_eligible"]:
            continue

        state_observation: dict[str, object] = {
            "date": session_date,
            "raw_label_key": candidate["label_key"],
            "score": float(candidate["score"]),
            "coverage_pct": coverage_pct,
            "baseline_key": "above_200dma" if close > sma200 else "below_200dma",
            "close": close,
            "trend_band": trend_band,
            "breadth_band": breadth_band,
            "price_strength_band": price_strength_band,
            "volatility_band": volatility_band,
            "india_vix_band": vix_band,
            "above_50dma_pct": round(above50, 1),
            "above_200dma_pct": round(above200, 1),
            "net_strength_pct": round(net_strength, 1),
            "realised_volatility_percentile": round(volatility_percentile, 1),
        }
        state_observations.append(state_observation)
        if position + maximum_horizon >= len(index_closes):
            continue

        forward_returns: dict[str, float] = {}
        forward_drawdowns: dict[str, float] = {}
        forward_long_adverse_excursions: dict[str, float] = {}
        forward_short_adverse_excursions: dict[str, float] = {}
        forward_excess_returns: dict[str, float | None] = {}
        forward_relative_drawdowns: dict[str, float | None] = {}
        for horizon in horizons:
            future_path = index_closes[position : position + horizon + 1]
            forward_returns[str(horizon)] = (future_path[-1] / close - 1) * 100
            entry_relative_path = [
                (future_close / close - 1) * 100 for future_close in future_path[1:]
            ]
            forward_long_adverse_excursions[str(horizon)] = max(
                0.0, -min(entry_relative_path, default=0.0)
            )
            forward_short_adverse_excursions[str(horizon)] = max(
                0.0, max(entry_relative_path, default=0.0)
            )
            peak = future_path[0]
            worst_drawdown = 0.0
            for future_close in future_path[1:]:
                peak = max(peak, future_close)
                worst_drawdown = min(worst_drawdown, (future_close / peak - 1) * 100)
            forward_drawdowns[str(horizon)] = worst_drawdown
            benchmark_path = [benchmark_by_date.get(item) for item in index_dates[position : position + horizon + 1]]
            if use_benchmark and all(value is not None for value in benchmark_path):
                aligned_benchmark = [float(value) for value in benchmark_path if value is not None]
                benchmark_return = (aligned_benchmark[-1] / aligned_benchmark[0] - 1) * 100
                forward_excess_returns[str(horizon)] = forward_returns[str(horizon)] - benchmark_return
                relative_path = [
                    (target_value / future_path[0]) / (benchmark_value / aligned_benchmark[0])
                    for target_value, benchmark_value in zip(future_path, aligned_benchmark)
                ]
                relative_peak = relative_path[0]
                relative_drawdown = 0.0
                for relative_value in relative_path[1:]:
                    relative_peak = max(relative_peak, relative_value)
                    relative_drawdown = min(
                        relative_drawdown,
                        (relative_value / relative_peak - 1) * 100,
                    )
                forward_relative_drawdowns[str(horizon)] = relative_drawdown
            else:
                forward_excess_returns[str(horizon)] = None
                forward_relative_drawdowns[str(horizon)] = None
        state_observation.update(
            {
                "forward_returns_pct": forward_returns,
                "forward_drawdowns_pct": forward_drawdowns,
                "forward_long_adverse_excursions_pct": forward_long_adverse_excursions,
                "forward_short_adverse_excursions_pct": forward_short_adverse_excursions,
                "forward_excess_returns_pct": forward_excess_returns,
                "forward_relative_drawdowns_pct": forward_relative_drawdowns,
            }
        )
        observations.append(state_observation)

    if len(observations) < 2:
        raise ValueError("regime_validation_coverage_unavailable")

    pending_label: str | None = None
    pending_count = 0
    confirmed_label: str | None = None
    for observation in state_observations:
        raw_label = str(observation["raw_label_key"])
        if raw_label == pending_label:
            pending_count += 1
        else:
            pending_label = raw_label
            pending_count = 1
        if pending_count >= 2:
            confirmed_label = raw_label
        observation["confirmed_label_key"] = confirmed_label

    current_transition_analysis = apply_recovering_market_state(state_observations)
    transition_analysis = {
        key: value
        for key, value in current_transition_analysis.items()
        if key not in {"episodes", "episode_count", "exit_counts"}
    }
    historical_transition = apply_recovering_market_state(observations)
    transition_analysis.update(
        {
            "episodes": historical_transition["episodes"],
            "episode_count": historical_transition["episode_count"],
            "exit_counts": historical_transition["exit_counts"],
        }
    )

    def aggregate(group: list[dict[str, object]]) -> dict[str, object]:
        summary: dict[str, object] = {
            "sessions": len(group),
            "average_score": round(sum(float(item["score"]) for item in group) / len(group), 1),
            "average_stock_coverage_pct": round(
                sum(float(item["coverage_pct"]) for item in group) / len(group), 1
            ),
            "horizons": {},
        }
        for horizon in horizons:
            key = str(horizon)
            returns = [float(item["forward_returns_pct"][key]) for item in group]
            drawdowns = [float(item["forward_drawdowns_pct"][key]) for item in group]
            variance = _sample_variance(returns)
            summary["horizons"][key] = {
                "mean_return_pct": round(sum(returns) / len(returns), 2),
                "median_return_pct": round(median(returns), 2),
                "positive_rate_pct": round(100 * sum(value > 0 for value in returns) / len(returns), 1),
                "return_stddev_pct": round(math.sqrt(variance), 2) if variance is not None else 0.0,
                "worst_return_pct": round(min(returns), 2),
                "mean_max_drawdown_pct": round(sum(drawdowns) / len(drawdowns), 2),
                "worst_max_drawdown_pct": round(min(drawdowns), 2),
            }
            excess_returns = [
                float(value)
                for item in group
                if (value := item["forward_excess_returns_pct"][key]) is not None
            ]
            relative_drawdowns = [
                float(value)
                for item in group
                if (value := item["forward_relative_drawdowns_pct"][key]) is not None
            ]
            summary["horizons"][key].update(
                {
                    "benchmark_observations": len(excess_returns),
                    "mean_excess_return_pct": (
                        round(sum(excess_returns) / len(excess_returns), 2)
                        if excess_returns else None
                    ),
                    "median_excess_return_pct": (
                        round(median(excess_returns), 2) if excess_returns else None
                    ),
                    "outperformance_rate_pct": (
                        round(
                            100 * sum(value > 0 for value in excess_returns) / len(excess_returns),
                            1,
                        )
                        if excess_returns else None
                    ),
                    "worst_relative_drawdown_pct": (
                        round(min(relative_drawdowns), 2) if relative_drawdowns else None
                    ),
                }
            )
        return summary

    label_names = {
        "positive_market": "Positive market",
        "cautiously_positive": "Cautiously positive",
        "uncertain_market": "Uncertain market",
        "weak_market": "Weak market",
        "high_risk_market": "High-risk market",
    }
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    baseline_grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for observation in observations:
        confirmed = observation.get("confirmed_label_key")
        if isinstance(confirmed, str):
            grouped[confirmed].append(observation)
        baseline_grouped[str(observation["baseline_key"])].append(observation)

    ordered_labels = [
        "positive_market",
        "cautiously_positive",
        "uncertain_market",
        "weak_market",
        "high_risk_market",
    ]
    by_regime = [
        {"label_key": key, "label": label_names[key], **aggregate(grouped[key])}
        for key in ordered_labels
        if grouped[key]
    ]
    baseline_names = {
        "above_200dma": f"{target_index} above 200DMA",
        "below_200dma": f"{target_index} at or below 200DMA",
    }
    baseline = [
        {"baseline_key": key, "label": baseline_names[key], **aggregate(baseline_grouped[key])}
        for key in ("above_200dma", "below_200dma")
        if baseline_grouped[key]
    ]
    confirmed_observations = [
        item
        for item in observations
        if isinstance(item.get("confirmed_label_key"), str)
    ]
    overall = aggregate(confirmed_observations)
    transition_grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for observation in observations:
        transition_label = observation.get("transition_label_key")
        if isinstance(transition_label, str):
            transition_grouped[transition_label].append(observation)
    transition_order = [
        "positive_market",
        "cautiously_positive",
        "recovering_market",
        "uncertain_market",
        "weak_market",
        "high_risk_market",
    ]
    transition_label_names = {
        **label_names,
        "recovering_market": "Recovering market",
    }
    transition_analysis["by_state"] = [
        {
            "label_key": key,
            "label": transition_label_names[key],
            **aggregate(transition_grouped[key]),
        }
        for key in transition_order
        if transition_grouped[key]
    ]
    directional_evidence: list[dict[str, object]] = []
    for state in transition_analysis["by_state"]:
        state_key = str(state["label_key"])
        state_group = transition_grouped[state_key]
        long_metrics = state["horizons"][str(REGIME_LONG_HORIZON_SESSIONS)]
        short_metrics = state["horizons"][str(REGIME_SHORT_HORIZON_SESSIONS)]
        sessions = int(state["sessions"])
        sample_ready = sessions >= REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS
        long_median_excess = long_metrics.get("median_excess_return_pct")
        long_outperformance_rate = long_metrics.get("outperformance_rate_pct")
        short_median_excess = short_metrics.get("median_excess_return_pct")
        short_outperformance_rate = short_metrics.get("outperformance_rate_pct")
        relative_long_ready = (
            not use_benchmark
            or (
                long_median_excess is not None
                and float(long_median_excess) >= REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT
                and long_outperformance_rate is not None
                and float(long_outperformance_rate) >= 55.0
            )
        )
        relative_short_ready = (
            not use_benchmark
            or (
                short_median_excess is not None
                and float(short_median_excess) <= -REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT
                and short_outperformance_rate is not None
                and float(short_outperformance_rate) <= 45.0
            )
        )
        long_state_eligible = state_key in {
            "positive_market",
            "cautiously_positive",
            "recovering_market",
        }
        short_state_eligible = state_key in {
            "weak_market",
            "high_risk_market",
        }
        long_case_passed = bool(
            sample_ready
            and float(long_metrics["median_return_pct"])
            >= REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT
            and float(long_metrics["positive_rate_pct"])
            >= REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT
            and relative_long_ready
        )
        short_case_passed = bool(
            sample_ready
            and float(short_metrics["median_return_pct"])
            <= -REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT
            and float(short_metrics["positive_rate_pct"])
            <= 100 - REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT
            and relative_short_ready
        )
        if long_case_passed:
            if long_state_eligible:
                research_bias = "long_research_candidate"
            elif short_state_eligible:
                research_bias = "countertrend_rebound_study"
            else:
                research_bias = "tactical_rebound_study"
        elif short_case_passed:
            research_bias = (
                "short_research_candidate"
                if short_state_eligible else "reversal_short_study"
            )
        elif not sample_ready:
            research_bias = "insufficient_sample"
        else:
            research_bias = "no_consistent_edge"
        selected_orientation = (
            "short"
            if research_bias in {"short_research_candidate", "reversal_short_study"}
            or (
                research_bias in {"insufficient_sample", "no_consistent_edge"}
                and short_state_eligible
            )
            else "long"
        )
        selected_horizon = (
            REGIME_SHORT_HORIZON_SESSIONS
            if selected_orientation == "short" else REGIME_LONG_HORIZON_SESSIONS
        )
        metrics = short_metrics if selected_orientation == "short" else long_metrics
        median_excess = metrics.get("median_excess_return_pct")
        outperformance_rate = metrics.get("outperformance_rate_pct")
        long_risk = build_regime_risk_profile(
            state_group,
            horizon_sessions=REGIME_LONG_HORIZON_SESSIONS,
            orientation="long",
        )
        short_risk = build_regime_risk_profile(
            state_group,
            horizon_sessions=REGIME_SHORT_HORIZON_SESSIONS,
            orientation="short",
        )
        selected_risk = short_risk if selected_orientation == "short" else long_risk
        directional_evidence.append(
            {
                "label_key": state_key,
                "label": state["label"],
                "sessions": sessions,
                "sample_ready": sample_ready,
                "research_bias": research_bias,
                "orientation": selected_orientation,
                "horizon_sessions": selected_horizon,
                "median_return_pct": metrics["median_return_pct"],
                "positive_rate_pct": metrics["positive_rate_pct"],
                "median_excess_return_pct": median_excess,
                "outperformance_rate_pct": outperformance_rate,
                "worst_return_pct": metrics["worst_return_pct"],
                "worst_max_drawdown_pct": metrics["worst_max_drawdown_pct"],
                "risk_profile": selected_risk,
                "long_case": {
                    "horizon_sessions": REGIME_LONG_HORIZON_SESSIONS,
                    "passed": long_case_passed,
                    "median_return_pct": long_metrics["median_return_pct"],
                    "positive_rate_pct": long_metrics["positive_rate_pct"],
                    "median_excess_return_pct": long_median_excess,
                    "outperformance_rate_pct": long_outperformance_rate,
                    "risk_profile": long_risk,
                },
                "short_case": {
                    "horizon_sessions": REGIME_SHORT_HORIZON_SESSIONS,
                    "passed": short_case_passed,
                    "median_return_pct": short_metrics["median_return_pct"],
                    "positive_rate_pct": short_metrics["positive_rate_pct"],
                    "median_excess_return_pct": short_median_excess,
                    "outperformance_rate_pct": short_outperformance_rate,
                    "risk_profile": short_risk,
                },
            }
        )
    transition_analysis["directional_state_evidence"] = directional_evidence
    transition_analysis["directional_contract"] = {
        "minimum_state_sessions": REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
        "absolute_median_return_threshold_pct": REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
        "positive_rate_long_threshold_pct": REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
        "positive_rate_short_threshold_pct": 100
        - REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
        "relative_median_excess_threshold_pct": REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
        "relative_outperformance_long_threshold_pct": 55.0,
        "relative_outperformance_short_threshold_pct": 45.0,
        "long_horizon_sessions": REGIME_LONG_HORIZON_SESSIONS,
        "short_horizon_sessions": REGIME_SHORT_HORIZON_SESSIONS,
        "tail_percentile": REGIME_RISK_TAIL_PERCENTILE,
        "adverse_distance_levels_pct": list(REGIME_ADVERSE_DISTANCE_LEVELS_PCT),
        "status": "historical_research_only",
    }

    recovery_group = transition_grouped.get("recovering_market", [])
    base_comparison_group = (
        transition_grouped.get("uncertain_market", [])
        + transition_grouped.get("cautiously_positive", [])
    )
    recovery_incremental: dict[str, object] = {
        "status": "insufficient_sample",
        "recovery_sessions": len(recovery_group),
        "comparable_base_sessions": len(base_comparison_group),
        "minimum_recovery_episodes": 5,
        "minimum_state_sessions": REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
    }
    if recovery_group and base_comparison_group:
        recovery_summary = aggregate(recovery_group)
        base_summary = aggregate(base_comparison_group)
        recovery_metrics = recovery_summary["horizons"]["20"]
        base_metrics = base_summary["horizons"]["20"]
        delta_return = round(
            float(recovery_metrics["median_return_pct"])
            - float(base_metrics["median_return_pct"]),
            2,
        )
        delta_positive = round(
            float(recovery_metrics["positive_rate_pct"])
            - float(base_metrics["positive_rate_pct"]),
            1,
        )
        delta_drawdown = round(
            float(recovery_metrics["worst_max_drawdown_pct"])
            - float(base_metrics["worst_max_drawdown_pct"]),
            2,
        )
        recovery_excess = recovery_metrics.get("median_excess_return_pct")
        base_excess = base_metrics.get("median_excess_return_pct")
        delta_excess = (
            round(float(recovery_excess) - float(base_excess), 2)
            if recovery_excess is not None and base_excess is not None else None
        )
        sample_ready = (
            len(recovery_group) >= REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS
            and len(base_comparison_group) >= REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS
            and int(transition_analysis["episode_count"]) >= 5
        )
        positive_relative_gate = not use_benchmark or (
            delta_excess is not None and delta_excess >= 0
        )
        negative_relative_gate = not use_benchmark or (
            delta_excess is not None and delta_excess <= 0
        )
        if not sample_ready:
            status = "insufficient_sample"
        elif (
            delta_return >= REGIME_RECOVERY_INCREMENTAL_RETURN_PCT
            and delta_positive >= REGIME_RECOVERY_INCREMENTAL_POSITIVE_RATE_PCT
            and delta_drawdown >= -REGIME_RECOVERY_DRAWDOWN_TOLERANCE_PCT
            and positive_relative_gate
        ):
            status = "recovery_long_thesis_supported"
        elif (
            delta_return <= -REGIME_RECOVERY_INCREMENTAL_RETURN_PCT
            and delta_positive <= -REGIME_RECOVERY_INCREMENTAL_POSITIVE_RATE_PCT
            and negative_relative_gate
        ):
            status = "recovery_long_thesis_contradicted"
        else:
            status = "mixed_incremental_evidence"
        recovery_incremental.update(
            {
                "status": status,
                "sample_ready": sample_ready,
                "recovery_20d": recovery_metrics,
                "comparable_base_20d": base_metrics,
                "delta_median_return_pct": delta_return,
                "delta_positive_rate_pct": delta_positive,
                "delta_worst_drawdown_pct": delta_drawdown,
                "delta_median_excess_return_pct": delta_excess,
            }
        )
    transition_analysis["recovery_incremental_evidence"] = recovery_incremental
    observations_by_date = {
        item["date"].isoformat(): item
        for item in observations
        if isinstance(item.get("date"), date)
    }
    for episode in transition_analysis["episodes"]:
        entry_observation = observations_by_date.get(str(episode["entry_date"]))
        if not isinstance(entry_observation, dict):
            continue
        episode["entry_score"] = round(float(entry_observation["score"]), 1)
        episode["forward_outcomes"] = {
            key: {
                "return_pct": entry_observation["forward_returns_pct"].get(key),
                "maximum_drawdown_pct": entry_observation["forward_drawdowns_pct"].get(key),
                "excess_return_pct": entry_observation["forward_excess_returns_pct"].get(key),
            }
            for key in ("5", "20", "60")
            if key in entry_observation["forward_returns_pct"]
        }

    latest_state = state_observations[-1]
    latest_state_date = latest_state["date"]
    latest_state_position = index_dates.index(latest_state_date)
    current_session_lag = len(index_dates) - 1 - latest_state_position
    current_base_key = latest_state.get("confirmed_label_key")
    current_transition_key = latest_state.get("transition_label_key")
    current_state = {
        "as_of_date": latest_state_date.isoformat(),
        "latest_index_session": index_dates[-1].isoformat(),
        "session_lag": current_session_lag,
        "fresh": current_session_lag == 0,
        "classification_ready": (
            current_session_lag == 0
            and isinstance(current_base_key, str)
            and isinstance(current_transition_key, str)
        ),
        "base_label_key": current_base_key,
        "base_label": (
            transition_label_names.get(str(current_base_key))
            if isinstance(current_base_key, str) else None
        ),
        "transition_label_key": current_transition_key,
        "transition_label": (
            transition_label_names.get(str(current_transition_key))
            if isinstance(current_transition_key, str) else None
        ),
        "score": round(float(latest_state["score"]), 1),
        "stock_coverage_pct": round(float(latest_state["coverage_pct"]), 1),
        "close": round(float(latest_state["close"]), 2),
        "evidence": {
            "trend_band": latest_state["trend_band"],
            "breadth_band": latest_state["breadth_band"],
            "price_strength_band": latest_state["price_strength_band"],
            "volatility_band": latest_state["volatility_band"],
            "india_vix_band": latest_state["india_vix_band"],
            "above_50dma_pct": latest_state["above_50dma_pct"],
            "above_200dma_pct": latest_state["above_200dma_pct"],
            "net_strength_pct": latest_state["net_strength_pct"],
            "realised_volatility_percentile": latest_state[
                "realised_volatility_percentile"
            ],
        },
    }

    confirmed_sequence = [
        str(item["confirmed_label_key"])
        for item in observations
        if isinstance(item.get("confirmed_label_key"), str)
    ]
    raw_transitions = sum(
        current != previous
        for previous, current in zip(
            [str(item["raw_label_key"]) for item in observations],
            [str(item["raw_label_key"]) for item in observations][1:],
        )
    )
    confirmed_transitions = sum(
        current != previous
        for previous, current in zip(confirmed_sequence, confirmed_sequence[1:])
    )
    durations: defaultdict[str, list[int]] = defaultdict(list)
    if confirmed_sequence:
        run_label = confirmed_sequence[0]
        run_length = 1
        for label in confirmed_sequence[1:]:
            if label == run_label:
                run_length += 1
            else:
                durations[run_label].append(run_length)
                run_label = label
                run_length = 1
        durations[run_label].append(run_length)
    duration_summary = [
        {
            "label_key": key,
            "label": label_names[key],
            "episodes": len(values),
            "average_sessions": round(sum(values) / len(values), 1),
            "median_sessions": round(float(median(values)), 1),
            "maximum_sessions": max(values),
        }
        for key in ordered_labels
        if (values := durations.get(key))
    ]

    event_results: list[dict[str, object]] = []
    risk_labels = {"weak_market", "high_risk_market"}
    close_by_date = dict(zip(index_dates, index_closes))
    named_event_ranges = [
        (event.get("start"), event.get("end"))
        for event in event_windows
        if isinstance(event.get("start"), date)
        and isinstance(event.get("end"), date)
        and event["end"] >= event["start"]
    ]

    def overlaps_named_event(group: list[dict[str, object]]) -> bool:
        return any(
            event_start <= item["date"] <= event_end
            for item in group
            for event_start, event_end in named_event_ranges
        )

    def normal_control_distribution(session_count: int) -> list[dict[str, float]]:
        if session_count < 2:
            return []
        controls: list[dict[str, float]] = []
        for start in range(0, len(confirmed_observations) - session_count + 1, session_count):
            group = confirmed_observations[start : start + session_count]
            if overlaps_named_event(group):
                continue
            closes = [close_by_date[item["date"]] for item in group]
            control_return = (closes[-1] / closes[0] - 1) * 100
            peak = closes[0]
            control_drawdown = 0.0
            for close in closes[1:]:
                peak = max(peak, close)
                control_drawdown = min(control_drawdown, (close / peak - 1) * 100)
            labels = [str(item["confirmed_label_key"]) for item in group]
            transition_labels = [str(item.get("transition_label_key")) for item in group]
            controls.append(
                {
                    "return_pct": control_return,
                    "maximum_drawdown_pct": control_drawdown,
                    "weak_or_high_risk_sessions_pct": (
                        100 * sum(label in risk_labels for label in labels) / len(labels)
                    ),
                    "recovering_sessions_pct": (
                        100
                        * sum(label == "recovering_market" for label in transition_labels)
                        / len(transition_labels)
                    ),
                }
            )
        return controls

    def empirical_percentile(value: float, controls: list[float]) -> float | None:
        if not controls:
            return None
        lower = sum(item < value for item in controls)
        equal = sum(math.isclose(item, value, abs_tol=1e-9) for item in controls)
        return round(100 * (lower + 0.5 * equal) / len(controls), 1)

    for event in event_windows:
        event_start = event.get("start")
        event_end = event.get("end")
        if not isinstance(event_start, date) or not isinstance(event_end, date) or event_end < event_start:
            continue
        event_path = [
            (session_date, close)
            for session_date, close in zip(index_dates, index_closes)
            if event_start <= session_date <= event_end
        ]
        event_observations = [
            item
            for item in observations
            if event_start <= item["date"] <= event_end
            and isinstance(item.get("confirmed_label_key"), str)
        ]
        if len(event_path) < 2 or not event_observations:
            continue
        event_return = (event_path[-1][1] / event_path[0][1] - 1) * 100
        peak = event_path[0][1]
        event_drawdown = 0.0
        for _, close in event_path[1:]:
            peak = max(peak, close)
            event_drawdown = min(event_drawdown, (close / peak - 1) * 100)
        event_labels = [str(item["confirmed_label_key"]) for item in event_observations]
        regime_counts = {
            key: event_labels.count(key)
            for key in ordered_labels
            if key in event_labels
        }
        dominant_key = max(regime_counts, key=regime_counts.get)
        risk_positions = [
            index
            for index, label in enumerate(event_labels)
            if label in risk_labels
        ]
        benchmark_return: float | None = None
        excess_return: float | None = None
        relative_drawdown: float | None = None
        benchmark_path = [benchmark_by_date.get(session_date) for session_date, _ in event_path]
        if use_benchmark and all(value is not None for value in benchmark_path):
            aligned_benchmark = [float(value) for value in benchmark_path if value is not None]
            benchmark_return = (aligned_benchmark[-1] / aligned_benchmark[0] - 1) * 100
            excess_return = event_return - benchmark_return
            relative_path = [
                (target_close / event_path[0][1]) / (benchmark_close / aligned_benchmark[0])
                for (_, target_close), benchmark_close in zip(event_path, aligned_benchmark)
            ]
            relative_peak = relative_path[0]
            relative_drawdown = 0.0
            for relative_value in relative_path[1:]:
                relative_peak = max(relative_peak, relative_value)
                relative_drawdown = min(
                    relative_drawdown,
                    (relative_value / relative_peak - 1) * 100,
                )
        event_stress_share = (
            100 * sum(label in risk_labels for label in event_labels) / len(event_labels)
        )
        event_recovery_share = (
            100
            * sum(
                item.get("transition_label_key") == "recovering_market"
                for item in event_observations
            )
            / len(event_observations)
        )
        normal_controls = normal_control_distribution(len(event_observations))
        control_returns = [item["return_pct"] for item in normal_controls]
        control_drawdowns = [item["maximum_drawdown_pct"] for item in normal_controls]
        control_stress_shares = [
            item["weak_or_high_risk_sessions_pct"] for item in normal_controls
        ]
        control_recovery_shares = [
            item["recovering_sessions_pct"] for item in normal_controls
        ]
        event_results.append(
            {
                "key": str(event.get("key") or "event"),
                "label": str(event.get("label") or "Event review"),
                "window_start": event_path[0][0].isoformat(),
                "window_end": event_path[-1][0].isoformat(),
                "sessions": len(event_observations),
                "index_return_pct": round(event_return, 2),
                "maximum_drawdown_pct": round(event_drawdown, 2),
                "benchmark_return_pct": round(benchmark_return, 2) if benchmark_return is not None else None,
                "excess_return_pct": round(excess_return, 2) if excess_return is not None else None,
                "relative_drawdown_pct": round(relative_drawdown, 2) if relative_drawdown is not None else None,
                "entry_regime": label_names[event_labels[0]],
                "exit_regime": label_names[event_labels[-1]],
                "dominant_regime": label_names[dominant_key],
                "weak_or_high_risk_sessions_pct": round(event_stress_share, 1),
                "recovering_sessions_pct": round(event_recovery_share, 1),
                "first_weak_or_high_risk_date": (
                    event_observations[risk_positions[0]]["date"].isoformat()
                    if risk_positions else None
                ),
                "sessions_to_first_weak_or_high_risk": risk_positions[0] if risk_positions else None,
                "minimum_candidate_score": round(
                    min(float(item["score"]) for item in event_observations), 1
                ),
                "regime_session_counts": regime_counts,
                "normal_period_control": {
                    "method": "non_overlapping_same_length_windows_excluding_named_events",
                    "window_count": len(normal_controls),
                    "median_return_pct": (
                        round(float(median(control_returns)), 2) if control_returns else None
                    ),
                    "median_maximum_drawdown_pct": (
                        round(float(median(control_drawdowns)), 2) if control_drawdowns else None
                    ),
                    "median_weak_or_high_risk_sessions_pct": (
                        round(float(median(control_stress_shares)), 1)
                        if control_stress_shares else None
                    ),
                    "median_recovering_sessions_pct": (
                        round(float(median(control_recovery_shares)), 1)
                        if control_recovery_shares else None
                    ),
                    "event_return_percentile_pct": (
                        empirical_percentile(event_return, control_returns)
                    ),
                    "event_drawdown_severity_percentile_pct": (
                        empirical_percentile(
                            -event_drawdown,
                            [-value for value in control_drawdowns],
                        )
                    ),
                    "event_stress_share_percentile_pct": (
                        empirical_percentile(event_stress_share, control_stress_shares)
                    ),
                    "event_recovery_share_percentile_pct": (
                        empirical_percentile(event_recovery_share, control_recovery_shares)
                    ),
                },
            }
        )

    return {
        "ok": True,
        "target_index": target_index,
        "benchmark_index": benchmark_index if use_benchmark else None,
        "evidence_scope": {
            "target_specific": [
                "trend",
                "realised_volatility",
                "forward_outcomes",
                "current-constituent F&O breadth",
                "current-constituent F&O price strength",
            ],
            "broad_market_context": ["main Market Sentiment regime remains separate"],
        },
        "rule_version": REGIME_RULE_VERSION,
        "validation_status": "historical_walk_forward_exploratory",
        "method": "Each session uses trailing data only; outcomes begin after classification.",
        "confirmation_sessions": 2,
        "evaluation_start": observations[0]["date"].isoformat(),
        "evaluation_end": observations[-1]["date"].isoformat(),
        "index_history_start": index_dates[0].isoformat(),
        "index_history_end": index_dates[-1].isoformat(),
        "sessions_evaluated": len(observations),
        "sessions_skipped_for_coverage": skipped_for_coverage,
        "stock_universe_size": universe_total,
        "breadth_universe": {
            "method": (
                "point_in_time_index_constituents_intersected_with_fno_universe"
                if membership_history
                else "current_index_constituents_intersected_with_fno_universe"
                if official_constituents
                else "broad_fno_universe"
            ),
            "membership_history_available": bool(membership_history),
            "membership_snapshot_count": len(membership_history),
            "constituent_snapshot_as_of": constituent_snapshot_as_of,
            "official_constituent_count": (
                len(official_constituents) if official_constituents else None
            ),
            "fno_constituent_count": universe_total,
            "constituents_outside_fno_universe": (
                [symbol for symbol in official_constituents if symbol not in stock_histories]
                if official_constituents else []
            ),
        },
        "horizons": list(horizons),
        "raw_transitions": raw_transitions,
        "confirmed_transitions": confirmed_transitions,
        "transition_reduction_pct": round(
            100 * (raw_transitions - confirmed_transitions) / raw_transitions, 1
        ) if raw_transitions else 0.0,
        "by_regime": by_regime,
        "overall": overall,
        "duration_summary": duration_summary,
        "current_state": current_state,
        "transition_analysis": transition_analysis,
        "event_validation": event_results,
        "external_cluster_readiness": build_regime_external_cluster_readiness(
            institutional_flow_rows=institutional_flow_rows,
            confirmed_fpi_rows=confirmed_fpi_rows,
            macro_snapshot_rows=macro_snapshot_rows,
            global_risk_rows=global_risk_rows,
            futures_snapshot_rows=futures_snapshot_rows,
        ),
        "baseline": baseline,
        "limitations": [
            (
                "Historical breadth uses dated index-membership snapshots intersected with the available F&O histories."
                if membership_history
                else "Historical breadth uses today’s index constituents intersected with the current F&O universe and is subject to survivorship and membership bias."
            ),
            "Constituent stocks enter only after 252 stored sessions; each evaluated date must meet the 80% coverage gate.",
            "Institutional-flow, currency/rates, and global-risk clusters remain unranked, leaving 60% candidate weight available.",
            "Thresholds were frozen before this report but have not been statistically fitted or approved for decisions.",
            "Overlapping forward-return windows are descriptive and not independent observations.",
            "Named event windows are retrospective stress reviews selected with hindsight and are not independent test samples.",
            "Normal-period controls are non-overlapping same-length historical windows outside the named events; they are descriptive controls, not causal counterfactuals.",
            "The Recovering market state is an outcome-blind transition rule under validation; it is not displayed as a current signal.",
        ],
    }


def calculate_domestic_sentiment_core(
    index_candles: list[dict[str, object]],
    stock_histories: dict[str, list[dict[str, object]]],
    *,
    india_vix_candles: list[dict[str, object]] | None = None,
    institutional_flow_rows: list[dict[str, object]] | None = None,
    confirmed_fpi_rows: list[dict[str, object]] | None = None,
    macro_snapshot_rows: list[dict[str, object]] | None = None,
    global_risk_rows: list[dict[str, object]] | None = None,
    futures_snapshot_rows: list[dict[str, object]] | None = None,
    retrieved_at: datetime | None = None,
) -> dict[str, object]:
    """Calculate transparent EOD domestic-tape evidence from local candles."""
    retrieved_at = (retrieved_at or datetime.now(INDIA_TIMEZONE)).astimezone(INDIA_TIMEZONE)
    ordered_index = sorted(index_candles, key=lambda item: item["date"])
    if len(ordered_index) < 252:
        raise ValueError("domestic_core_history_unavailable")
    as_of = ordered_index[-1]["date"]
    closes = [float(row["close"]) for row in ordered_index]

    def average(values: list[float]) -> float:
        return sum(values) / len(values)

    def relative_pct(value: float, reference: float) -> float:
        return ((value / reference) - 1) * 100

    latest_close = closes[-1]
    sma20 = average(closes[-20:])
    sma50 = average(closes[-50:])
    sma200 = average(closes[-200:])
    prior_sma50 = average(closes[-70:-20])
    sma50_slope = relative_pct(sma50, prior_sma50)
    drawdown = relative_pct(latest_close, max(closes[-252:]))
    momentum20 = relative_pct(latest_close, closes[-21])

    if latest_close > sma50 > sma200 and sma50_slope > 0:
        trend_band = "constructive"
        trend_reason = "Price is above aligned rising 50- and 200-session averages."
    elif latest_close < sma50 < sma200 and sma50_slope < 0:
        trend_band = "defensive"
        trend_reason = "Price is below aligned falling 50- and 200-session averages."
    else:
        trend_band = "mixed"
        trend_reason = "Price and moving-average evidence is not fully aligned."

    daily_returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:])]

    def annualised_volatility(returns: list[float]) -> float:
        variance = _sample_variance(returns)
        if variance is None:
            raise ValueError("domestic_core_history_unavailable")
        return math.sqrt(variance * 252) * 100

    current_vol = annualised_volatility(daily_returns[-20:])
    rolling_vols = [
        annualised_volatility(daily_returns[end - 20:end])
        for end in range(max(20, len(daily_returns) - 251), len(daily_returns) + 1)
    ]
    previous_vol = rolling_vols[-6] if len(rolling_vols) >= 6 else rolling_vols[0]
    vol_percentile = 100 * sum(value <= current_vol for value in rolling_vols) / len(rolling_vols)
    if vol_percentile >= 85:
        volatility_band = "defensive"
        volatility_reason = "Realised volatility is in the top 15% of its one-year range."
    elif vol_percentile >= 60:
        volatility_band = "mixed"
        volatility_reason = "Realised volatility is elevated relative to the past year."
    else:
        volatility_band = "constructive"
        volatility_reason = "Realised volatility is below its elevated-risk range."

    ordered_vix = [
        row
        for row in sorted(india_vix_candles or [], key=lambda item: item["date"])
        if row["date"] <= as_of
    ]
    if len(ordered_vix) >= 252 and ordered_vix[-1]["date"] == as_of:
        vix_closes = [float(row["close"]) for row in ordered_vix]
        vix_level = vix_closes[-1]
        vix_percentile = 100 * sum(value <= vix_level for value in vix_closes[-252:]) / 252
        vix_five_day_change = vix_level - vix_closes[-6]
        if vix_percentile >= 85:
            vix_band = "defensive"
            vix_reason = "India VIX is in the top 15% of its one-year range."
        elif vix_percentile >= 60:
            vix_band = "mixed"
            vix_reason = "India VIX is elevated relative to its one-year range."
        else:
            vix_band = "constructive"
            vix_reason = "India VIX is below its elevated-risk range."
        india_vix = {
            "available": True,
            "as_of_date": ordered_vix[-1]["date"].isoformat(),
            "level": round(vix_level, 2),
            "five_day_change_pt": round(vix_five_day_change, 2),
            "one_year_percentile": round(vix_percentile, 1),
            "implied_realised_gap_pt": round(vix_level - current_vol, 2),
            "band": vix_band,
            "reason": vix_reason,
        }
    else:
        india_vix = {
            "available": False,
            "as_of_date": ordered_vix[-1]["date"].isoformat() if ordered_vix else None,
            "reason": "India VIX needs 252 aligned completed sessions from the EOD update.",
        }

    eligible: list[list[float]] = []
    eligible_by_date: list[dict[date, float]] = []
    missing_stocks: list[dict[str, object]] = []
    for stock_name, history in sorted(stock_histories.items()):
        ordered = sorted(history, key=lambda item: item["date"])
        last_session = ordered[-1]["date"] if ordered else None
        if not ordered:
            reason = "no_history"
        elif len(ordered) < 252:
            reason = "insufficient_history"
        elif last_session != as_of:
            reason = "latest_session_mismatch"
        else:
            reason = None
        if reason is not None:
            missing_stocks.append(
                {
                    "stock": stock_name,
                    "reason": reason,
                    "sessions": len(ordered),
                    "last_session": last_session.isoformat() if last_session else None,
                }
            )
            continue
        eligible.append([float(row["close"]) for row in ordered])
        eligible_by_date.append({row["date"]: float(row["close"]) for row in ordered})
    if not eligible:
        raise ValueError("domestic_breadth_unavailable")

    def percent_above(window: int) -> float:
        return 100 * sum(series[-1] > average(series[-window:]) for series in eligible) / len(eligible)

    advances = sum(series[-1] > series[-2] for series in eligible)
    declines = sum(series[-1] < series[-2] for series in eligible)
    unchanged = len(eligible) - advances - declines
    advance_decline_ratio = advances / declines if declines else None
    common_dates = sorted(
        set.intersection(*(set(series) for series in eligible_by_date))
    )
    price_strength_series: list[dict[str, object]] = []
    if len(common_dates) >= 252:
        first_evaluation = max(251, len(common_dates) - PRICE_STRENGTH_SERIES_SESSIONS)
        for position in range(first_evaluation, len(common_dates)):
            window_dates = common_dates[position - 251 : position + 1]
            evaluation_date = common_dates[position]
            near_high_count = 0
            near_low_count = 0
            for history in eligible_by_date:
                window = [history[session] for session in window_dates]
                latest = window[-1]
                near_high_count += latest >= max(window) * 0.95
                near_low_count += latest <= min(window) * 1.05
            high_pct = 100 * near_high_count / len(eligible_by_date)
            low_pct = 100 * near_low_count / len(eligible_by_date)
            price_strength_series.append(
                {
                    "date": evaluation_date.isoformat(),
                    "near_52w_high_pct": round(high_pct, 1),
                    "near_52w_low_pct": round(low_pct, 1),
                    "net_strength_pct": round(high_pct - low_pct, 1),
                }
            )
    if price_strength_series:
        latest_strength = price_strength_series[-1]
        near_high_pct = float(latest_strength["near_52w_high_pct"])
        near_low_pct = float(latest_strength["near_52w_low_pct"])
        price_strength = float(latest_strength["net_strength_pct"])
    else:
        near_high = sum(series[-1] >= max(series[-252:]) * 0.95 for series in eligible)
        near_low = sum(series[-1] <= min(series[-252:]) * 1.05 for series in eligible)
        near_high_pct = 100 * near_high / len(eligible)
        near_low_pct = 100 * near_low / len(eligible)
        price_strength = near_high_pct - near_low_pct
    above20 = percent_above(20)
    above50 = percent_above(50)
    above200 = percent_above(200)
    if above50 >= 55 and above200 >= 55 and advances > declines:
        breadth_band = "constructive"
        breadth_reason = "A majority is above medium- and long-term averages with positive daily breadth."
    elif (above50 < 40 and above200 < 40) or (declines and advances / declines < 0.67):
        breadth_band = "defensive"
        breadth_reason = "Participation is weak across moving averages or daily breadth."
    else:
        breadth_band = "mixed"
        breadth_reason = "Participation is neither broadly strong nor broadly weak."

    if price_strength >= 10:
        price_strength_band = "constructive"
        price_strength_reason = "More stocks are clustered near 52-week highs than lows."
    elif price_strength <= -10:
        price_strength_band = "defensive"
        price_strength_reason = "More stocks are clustered near 52-week lows than highs."
    else:
        price_strength_band = "mixed"
        price_strength_reason = "The balance near 52-week extremes is inconclusive."

    bands = [trend_band, breadth_band, price_strength_band, volatility_band]
    constructive = bands.count("constructive")
    defensive = bands.count("defensive")
    if constructive >= 3 and defensive == 0:
        domestic_tape = "Constructive"
    elif defensive >= 2:
        domestic_tape = "Defensive"
    else:
        domestic_tape = "Mixed"

    expected_through = completed_history_date(retrieved_at)
    while expected_through.weekday() >= 5:
        expected_through -= timedelta(days=1)
    freshness_lag_days = max(0, (expected_through - as_of).days)
    if as_of >= expected_through:
        freshness_state = "fresh"
    elif freshness_lag_days == 1:
        freshness_state = "pending"
    else:
        freshness_state = "stale"
    universe_total = len(stock_histories)
    coverage_pct = 100 * len(eligible) / universe_total if universe_total else 0.0
    institutional_flows = calculate_institutional_flow_summary(institutional_flow_rows or [])
    confirmed_fpi = calculate_confirmed_fpi_summary(confirmed_fpi_rows or [])
    macro_context = calculate_macro_context_summary(macro_snapshot_rows or [])
    global_risk = calculate_global_risk_summary(global_risk_rows or [])
    futures_oi = calculate_futures_oi_summary(futures_snapshot_rows or [])

    payload = {
        "ok": True,
        "as_of_date": as_of.isoformat(),
        "overall_regime": "Pending full model",
        "domestic_tape": domestic_tape,
        "confidence": "Partial",
        "available_clusters": (
            3
            + int(institutional_flows["available"])
            + int(macro_context["available"])
            + int(global_risk["available"])
        ),
        "total_clusters": 6,
        "trend": {
            "band": trend_band,
            "reason": trend_reason,
            "close": round(latest_close, 2),
            "vs_20dma_pct": round(relative_pct(latest_close, sma20), 2),
            "vs_50dma_pct": round(relative_pct(latest_close, sma50), 2),
            "vs_200dma_pct": round(relative_pct(latest_close, sma200), 2),
            "sma50_slope_20d_pct": round(sma50_slope, 2),
            "momentum_20d_pct": round(momentum20, 2),
            "drawdown_52w_pct": round(drawdown, 2),
        },
        "breadth": {
            "band": breadth_band,
            "reason": breadth_reason,
            "universe": "Locally stored NSE F&O equities",
            "evaluated": len(eligible),
            "above_20dma_pct": round(above20, 1),
            "above_50dma_pct": round(above50, 1),
            "above_200dma_pct": round(above200, 1),
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "advance_decline_ratio": round(advance_decline_ratio, 2) if advance_decline_ratio is not None else None,
            "universe_total": universe_total,
            "coverage_pct": round(coverage_pct, 1),
            "missing_count": len(missing_stocks),
            "missing_stocks": missing_stocks,
        },
        "price_strength": {
            "band": price_strength_band,
            "reason": price_strength_reason,
            "near_52w_high_pct": round(near_high_pct, 1),
            "near_52w_low_pct": round(near_low_pct, 1),
            "net_strength_pct": round(price_strength, 1),
            "series": price_strength_series,
            "series_window_sessions": PRICE_STRENGTH_SERIES_SESSIONS,
        },
        "volatility": {
            "band": volatility_band,
            "reason": volatility_reason,
            "realised_20d_pct": round(current_vol, 2),
            "five_day_change_pt": round(current_vol - previous_vol, 2),
            "one_year_percentile": round(vol_percentile, 1),
            "india_vix": india_vix,
        },
        "institutional_flows": institutional_flows,
        "confirmed_fpi": confirmed_fpi,
        "macro_context": macro_context,
        "global_risk": global_risk,
        "futures_oi": futures_oi,
        "source": "Validated local Kite EOD candles",
        "freshness": {
            "state": freshness_state,
            "expected_through": expected_through.isoformat(),
            "latest_session": as_of.isoformat(),
            "lag_days": freshness_lag_days,
            "retrieved_at": retrieved_at.isoformat(timespec="seconds"),
        },
    }
    payload["candidate_regime"] = calculate_candidate_regime(payload)
    return payload


def build_dashboard_market_sentiment_summary(
    domestic_payload: dict[str, object],
    cross_index_payload: dict[str, object],
) -> dict[str, object]:
    """Condense validated sentiment evidence into a read-only dashboard contract."""
    if domestic_payload.get("ok") is not True or cross_index_payload.get("ok") is not True:
        raise ValueError("dashboard_market_sentiment_summary_unavailable")
    decision_rows = cross_index_payload.get("current_decision_rows")
    if not isinstance(decision_rows, list):
        raise ValueError("dashboard_market_sentiment_summary_unavailable")

    research_rows = [
        row
        for row in decision_rows
        if isinstance(row, dict) and not bool(row.get("is_benchmark"))
    ]
    watch_decisions = {
        "short_watch_unconfirmed",
        "short_watch_history_building",
        "countertrend_watch",
        "tactical_watch",
        "reversal_watch",
    }
    avoid_decisions = {
        "avoid_no_short_confirmation",
        "avoid_no_validated_edge",
    }

    def count(decisions: set[str]) -> int:
        return sum(str(row.get("current_decision")) in decisions for row in research_rows)

    decision_counts = {
        "long": count({"long_candidate"}),
        "confirmed_short": count({"short_candidate"}),
        "watch": count(watch_decisions),
        "avoid": count(avoid_decisions),
        "insufficient": count({"insufficient_evidence"}),
    }
    candidate_count = decision_counts["long"] + decision_counts["confirmed_short"]
    if candidate_count:
        board_status = "research_candidates_present"
    elif decision_counts["watch"]:
        board_status = "watch_only"
    else:
        board_status = "no_validated_candidates"

    current_dates = [
        str((row.get("current_state") or {}).get("as_of_date"))
        for row in research_rows
        if isinstance(row.get("current_state"), dict)
        and (row.get("current_state") or {}).get("as_of_date")
    ]
    leading_watch = next(
        (
            {
                "index": row.get("index"),
                "decision": row.get("current_decision"),
            }
            for row in research_rows
            if str(row.get("current_decision")) in watch_decisions
        ),
        None,
    )
    freshness = domestic_payload.get("freshness")
    freshness = freshness if isinstance(freshness, dict) else {}
    futures_contract = cross_index_payload.get("futures_short_confirmation_contract")
    futures_contract = futures_contract if isinstance(futures_contract, dict) else {}
    excluded = cross_index_payload.get("excluded")
    excluded = excluded if isinstance(excluded, list) else []
    return {
        "ok": True,
        "status": board_status,
        "scope": "cross_sectional_research_only",
        "as_of_date": max(current_dates, default=domestic_payload.get("as_of_date")),
        "domestic_tape": domestic_payload.get("domestic_tape"),
        "freshness": {
            "state": freshness.get("state"),
            "latest_session": freshness.get("latest_session"),
            "expected_through": freshness.get("expected_through"),
            "lag_days": freshness.get("lag_days"),
        },
        "evidence": {
            "available_clusters": int(domestic_payload.get("available_clusters") or 0),
            "total_clusters": int(domestic_payload.get("total_clusters") or 0),
            "eligible_indices": len(research_rows),
            "excluded_indices": len(excluded),
        },
        "decision_counts": decision_counts,
        "leading_watch": leading_watch,
        "futures_short_confirmation": {
            "stored_history_sessions": int(
                futures_contract.get("stored_history_sessions") or 0
            ),
            "history_sessions_required": int(
                futures_contract.get("history_sessions_required") or 0
            ),
            "history_ready": bool(futures_contract.get("history_ready")),
        },
        "limitations": [
            "Research evidence only; no order, position size, or stop is generated.",
            "Short candidates remain unavailable until the futures/OI history and same-session confirmation gates pass.",
        ],
    }


def build_dashboard_fno_summary(
    futures_summary: dict[str, object],
    *,
    stored_history_sessions: int,
) -> dict[str, object]:
    """Condense descriptive futures/OI state into the Dashboard card contract."""
    if stored_history_sessions < 0:
        raise ValueError("dashboard_fno_summary_unavailable")
    if futures_summary.get("available") is not True:
        return {
            "ok": True,
            "status": "baseline_pending",
            "scope": "descriptive_only",
            "as_of_date": None,
            "stored_history_sessions": stored_history_sessions,
            "coverage": {
                "latest": 0,
                "expected": FNO_UNIVERSE_EXPECTED,
                "pct": 0.0,
                "missing": FNO_UNIVERSE_EXPECTED,
            },
            "comparisons": {
                "comparable": 0,
                "eligible": 0,
                "rollover_baselines": 0,
                "stale_gaps": 0,
                "liquidity_excluded": 0,
            },
            "positioning": {
                "bullish": 0,
                "bearish": 0,
                "unclear": 0,
                "state_counts": {},
            },
            "reason": futures_summary.get("reason"),
            "safeguards": {},
        }

    state_counts = futures_summary.get("state_counts")
    state_counts = state_counts if isinstance(state_counts, dict) else {}
    bullish = int(state_counts.get("long_build_up") or 0) + int(
        state_counts.get("short_covering") or 0
    )
    bearish = int(state_counts.get("short_build_up") or 0) + int(
        state_counts.get("long_unwinding") or 0
    )
    unclear = int(state_counts.get("no_clear_signal") or 0)
    eligible = int(futures_summary.get("eligible_count") or 0)
    if eligible == 0:
        status = "history_building"
    elif bullish > bearish:
        status = "bullish_tilt"
    elif bearish > bullish:
        status = "bearish_tilt"
    else:
        status = "balanced_or_unclear"
    return {
        "ok": True,
        "status": status,
        "scope": "descriptive_only",
        "as_of_date": futures_summary.get("as_of_date"),
        "stored_history_sessions": stored_history_sessions,
        "coverage": {
            "latest": int(futures_summary.get("latest_coverage") or 0),
            "expected": int(
                futures_summary.get("expected_universe") or FNO_UNIVERSE_EXPECTED
            ),
            "pct": float(futures_summary.get("latest_coverage_pct") or 0.0),
            "missing": int(futures_summary.get("latest_missing_count") or 0),
        },
        "comparisons": {
            "comparable": int(futures_summary.get("comparable_count") or 0),
            "eligible": eligible,
            "rollover_baselines": int(
                futures_summary.get("rollover_baseline_count") or 0
            ),
            "stale_gaps": int(futures_summary.get("stale_gap_count") or 0),
            "liquidity_excluded": int(
                futures_summary.get("liquidity_excluded_count") or 0
            ),
        },
        "positioning": {
            "bullish": bullish,
            "bearish": bearish,
            "unclear": unclear,
            "state_counts": state_counts,
        },
        "reason": futures_summary.get("reason"),
        "safeguards": futures_summary.get("safeguards") or {},
    }


def build_dashboard_seasonality_summary(
    seasonality_payload: dict[str, object],
) -> dict[str, object]:
    """Condense historical seasonality and holdout evidence for the Dashboard."""
    if seasonality_payload.get("ok") is not True:
        raise ValueError("dashboard_seasonality_summary_unavailable")
    month_rows = seasonality_payload.get("month_rows")
    if not isinstance(month_rows, list):
        raise ValueError("dashboard_seasonality_summary_unavailable")
    populated = [
        row
        for row in month_rows
        if isinstance(row, dict)
        and int(row.get("count") or 0) > 0
        and isinstance(row.get("average_return_pct"), (int, float))
    ]
    strongest = max(populated, key=lambda row: float(row["average_return_pct"]), default=None)
    weakest = min(populated, key=lambda row: float(row["average_return_pct"]), default=None)
    held_out = seasonality_payload.get("held_out_summary")
    held_out = held_out if isinstance(held_out, dict) else {}
    turn_rows = seasonality_payload.get("turn_held_out_rows")
    turn_rows = turn_rows if isinstance(turn_rows, list) else []
    turn_test = next(
        (row for row in turn_rows if isinstance(row, dict) and row.get("period") == "Test"),
        None,
    )
    validation_ready = bool(seasonality_payload.get("holdout_split_date"))
    status = (
        "historical_evidence_ready"
        if len(populated) == 12 and validation_ready
        else "partial_history"
    )
    return {
        "ok": True,
        "status": status,
        "scope": "historical_not_forecast",
        "instrument": seasonality_payload.get("instrument"),
        "kind": seasonality_payload.get("kind"),
        "from_date": seasonality_payload.get("from_date"),
        "as_of_date": seasonality_payload.get("as_of_date"),
        "completed_sessions": int(seasonality_payload.get("completed_sessions") or 0),
        "populated_months": len(populated),
        "minimum_month_observations": min(
            (int(row.get("count") or 0) for row in populated),
            default=0,
        ),
        "validation_ready": validation_ready,
        "strongest_month": strongest,
        "weakest_month": weakest,
        "holdout": {
            "same_direction": int(held_out.get("same_direction") or 0),
            "train_significant": int(held_out.get("train_significant") or 0),
            "survived": int(held_out.get("survived") or 0),
        },
        "turn_of_month_test": turn_test,
        "limitations": [
            "Historical averages and holdout checks are descriptive, not forecasts.",
            "The current incomplete calendar month is excluded from month-of-year evidence.",
        ],
    }


def build_dashboard_seasonality_universe_summary(
    summaries: dict[str, dict[str, object]],
    *,
    supported_indices: tuple[str, ...] = SEASONALITY_INDICES,
) -> dict[str, object]:
    """Expose every supported index, including honest unavailable states."""
    rows: list[dict[str, object]] = []
    for instrument in supported_indices:
        summary = summaries.get(instrument)
        if summary is None:
            rows.append(
                {
                    "ok": False,
                    "instrument": instrument,
                    "kind": "index",
                    "status": "history_unavailable",
                    "completed_sessions": 0,
                    "populated_months": 0,
                    "minimum_month_observations": 0,
                    "validation_ready": False,
                }
            )
            continue
        rows.append(summary)
    available = [row for row in rows if row.get("ok") is True]
    ready = [
        row
        for row in available
        if row.get("status") == "historical_evidence_ready"
    ]
    return {
        "ok": True,
        "scope": "all_supported_indices",
        "indices": rows,
        "universe": {
            "total": len(rows),
            "available": len(available),
            "ready": len(ready),
            "partial": len(available) - len(ready),
            "unavailable": len(rows) - len(available),
        },
        "limitations": [
            "Each index is calculated independently from its own stored history.",
            "Short-history and unavailable indices remain visible and are not replaced with Nifty 50 evidence.",
            "Historical averages and holdout checks are descriptive, not forecasts.",
        ],
    }


def calculate_stock_screener(
    stock_histories: dict[str, list[dict[str, object]]],
    benchmark_candles: list[dict[str, object]],
    *,
    expected_through: date,
) -> dict[str, object]:
    """Build transparent, descriptive stock factors from validated local EOD data."""
    benchmark = sorted(benchmark_candles, key=lambda item: item["date"])
    if len(benchmark) < 21:
        raise ValueError("screener_benchmark_unavailable")
    as_of = benchmark[-1]["date"]
    benchmark_closes = [float(row["close"]) for row in benchmark]
    benchmark_return_20d = ((benchmark_closes[-1] / benchmark_closes[-21]) - 1) * 100

    def relative_pct(value: float, reference: float) -> float:
        return ((value / reference) - 1) * 100

    rows: list[dict[str, object]] = []
    for symbol, history in sorted(stock_histories.items()):
        ordered = sorted(history, key=lambda item: item["date"])
        sessions = len(ordered)
        latest_session = ordered[-1]["date"] if ordered else None
        if not ordered:
            status = "unavailable"
            reason = "No validated local candles are stored."
        elif latest_session != as_of:
            status = "stale"
            reason = "The latest stored session is not aligned with the benchmark."
        elif sessions < SCREENER_READY_SESSIONS:
            status = "partial_history"
            reason = f"{SCREENER_READY_SESSIONS} aligned sessions are required for full factor coverage."
        else:
            status = "ready"
            reason = "At least 252 aligned completed sessions are available."

        closes = [float(row["close"]) for row in ordered]
        aligned = latest_session == as_of
        latest_close = closes[-1] if closes else None

        def versus_average(window: int) -> float | None:
            if len(closes) < window or latest_close is None:
                return None
            return relative_pct(latest_close, sum(closes[-window:]) / window)

        return_20d = (
            relative_pct(latest_close, closes[-21])
            if latest_close is not None and len(closes) >= 21
            else None
        )
        return_60d = (
            relative_pct(latest_close, closes[-61])
            if latest_close is not None and len(closes) >= 61
            else None
        )
        realised_volatility = None
        if len(closes) >= 21:
            recent_returns = [
                math.log(current / previous)
                for previous, current in zip(closes[-21:-1], closes[-20:])
            ]
            variance = _sample_variance(recent_returns)
            if variance is not None:
                realised_volatility = math.sqrt(variance * 252) * 100
        position_52w = None
        drawdown_52w = None
        if len(closes) >= SCREENER_READY_SESSIONS and latest_close is not None:
            window = closes[-SCREENER_READY_SESSIONS:]
            low = min(window)
            high = max(window)
            position_52w = 100.0 if high == low else 100 * (latest_close - low) / (high - low)
            drawdown_52w = relative_pct(latest_close, high)

        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "reason": reason,
                "sessions": sessions,
                "first_session": ordered[0]["date"].isoformat() if ordered else None,
                "last_session": latest_session.isoformat() if latest_session else None,
                "close": round(latest_close, 2) if latest_close is not None else None,
                "return_20d_pct": round(return_20d, 2) if return_20d is not None else None,
                "return_60d_pct": round(return_60d, 2) if return_60d is not None else None,
                "excess_20d_vs_nifty_pct": (
                    round(return_20d - benchmark_return_20d, 2)
                    if return_20d is not None and aligned else None
                ),
                "vs_20dma_pct": (
                    round(value, 2) if (value := versus_average(20)) is not None else None
                ),
                "vs_50dma_pct": (
                    round(value, 2) if (value := versus_average(50)) is not None else None
                ),
                "vs_200dma_pct": (
                    round(value, 2) if (value := versus_average(200)) is not None else None
                ),
                "position_52w_pct": round(position_52w, 1) if position_52w is not None else None,
                "drawdown_52w_pct": round(drawdown_52w, 2) if drawdown_52w is not None else None,
                "realised_volatility_20d_pct": (
                    round(realised_volatility, 2) if realised_volatility is not None else None
                ),
            }
        )

    counts = {
        state: sum(row["status"] == state for row in rows)
        for state in ("ready", "partial_history", "stale", "unavailable")
    }
    freshness_state = "fresh" if as_of >= expected_through else "stale"
    return {
        "ok": True,
        "scope": "locally_stored_nse_fno_equities",
        "as_of_date": as_of.isoformat(),
        "benchmark": "Nifty 50",
        "benchmark_return_20d_pct": round(benchmark_return_20d, 2),
        "rows": rows,
        "coverage": {"total": len(rows), **counts},
        "freshness": {
            "state": freshness_state,
            "expected_through": expected_through.isoformat(),
            "latest_session": as_of.isoformat(),
        },
        "contract": {
            "version": "local-stock-screener-v1",
            "minimum_ready_sessions": SCREENER_READY_SESSIONS,
            "default_sort": "excess_20d_vs_nifty_pct_desc",
            "formulas": {
                "return_20d_pct": "close / close_20_sessions_ago - 1",
                "return_60d_pct": "close / close_60_sessions_ago - 1",
                "excess_20d_vs_nifty_pct": "stock_20d_return - Nifty_50_20d_return",
                "vs_dma_pct": "close / simple_moving_average - 1",
                "position_52w_pct": "(close - 252_session_low) / (252_session_high - 252_session_low)",
                "drawdown_52w_pct": "close / 252_session_high - 1",
                "realised_volatility_20d_pct": "sample_stddev(log_daily_returns_20d) * sqrt(252)",
            },
            "limitations": [
                "Descriptive EOD evidence only; rows are not buy, sell, or portfolio instructions.",
                "The universe is the locally stored NSE F&O equity list, not the whole cash market.",
                "Current storage has no volume, valuation, quality, earnings, revision, or sector-relative factors.",
                "Relative strength is a return difference versus Nifty 50, not risk-adjusted alpha.",
                "Filters and sorting do not constitute a backtest or validated ranking model.",
            ],
        },
    }


def build_dashboard_screener_summary(
    screener_payload: dict[str, object],
) -> dict[str, object]:
    """Condense transparent local stock factors into a descriptive Dashboard card."""
    if screener_payload.get("ok") is not True:
        raise ValueError("dashboard_screener_summary_unavailable")
    rows = screener_payload.get("rows")
    coverage = screener_payload.get("coverage")
    freshness = screener_payload.get("freshness")
    contract = screener_payload.get("contract")
    if not isinstance(rows, list) or not isinstance(coverage, dict):
        raise ValueError("dashboard_screener_summary_unavailable")
    freshness = freshness if isinstance(freshness, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    ready_rows = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("status") == "ready"
    ]

    def numeric_rows(key: str) -> list[dict[str, object]]:
        return [
            row
            for row in ready_rows
            if isinstance(row.get(key), (int, float))
        ]

    excess_rows = numeric_rows("excess_20d_vs_nifty_pct")
    positive_20d = sum(
        float(row["return_20d_pct"]) > 0
        for row in numeric_rows("return_20d_pct")
    )
    above_200dma = sum(
        float(row["vs_200dma_pct"]) > 0
        for row in numeric_rows("vs_200dma_pct")
    )
    outperforming = sum(
        float(row["excess_20d_vs_nifty_pct"]) > 0
        for row in excess_rows
    )
    highest_excess = max(
        excess_rows,
        key=lambda row: float(row["excess_20d_vs_nifty_pct"]),
        default=None,
    )
    lowest_excess = min(
        excess_rows,
        key=lambda row: float(row["excess_20d_vs_nifty_pct"]),
        default=None,
    )
    total = int(coverage.get("total") or len(rows))
    ready = int(coverage.get("ready") or len(ready_rows))
    freshness_state = str(freshness.get("state") or "unavailable")
    if not ready:
        status = "screen_unavailable"
    elif ready < total:
        status = "partial_history"
    elif freshness_state == "fresh":
        status = "evidence_ready"
    else:
        status = "stale_evidence"

    def observation(row: dict[str, object] | None) -> dict[str, object] | None:
        if row is None:
            return None
        return {
            "symbol": row.get("symbol"),
            "excess_20d_vs_nifty_pct": row.get("excess_20d_vs_nifty_pct"),
            "return_20d_pct": row.get("return_20d_pct"),
        }

    return {
        "ok": True,
        "status": status,
        "scope": "descriptive_local_screen_only",
        "as_of_date": screener_payload.get("as_of_date"),
        "benchmark": screener_payload.get("benchmark"),
        "benchmark_return_20d_pct": screener_payload.get(
            "benchmark_return_20d_pct"
        ),
        "coverage": {
            "total": total,
            "ready": ready,
            "partial_history": int(coverage.get("partial_history") or 0),
            "stale": int(coverage.get("stale") or 0),
            "unavailable": int(coverage.get("unavailable") or 0),
        },
        "freshness": {
            "state": freshness_state,
            "latest_session": freshness.get("latest_session"),
            "expected_through": freshness.get("expected_through"),
        },
        "observations": {
            "positive_20d": positive_20d,
            "above_200dma": above_200dma,
            "outperforming_nifty_20d": outperforming,
            "highest_20d_excess": observation(highest_excess),
            "lowest_20d_excess": observation(lowest_excess),
        },
        "contract_version": contract.get("version"),
        "limitations": [
            "Counts and extremes describe the current local EOD screen; they are not recommendations.",
            "The universe is the locally stored NSE F&O equity list, not the whole cash market.",
            "Twenty-session excess return is a simple difference versus Nifty 50, not risk-adjusted alpha.",
        ],
    }


def build_dashboard_market_story(
    sentiment_summary: dict[str, object],
    screener_summary: dict[str, object],
    fno_summary: dict[str, object],
    regime_validation: dict[str, object],
    seasonality_payload: dict[str, object],
    events_payload: dict[str, object],
    nifty500_context: dict[str, object] | None = None,
) -> dict[str, object]:
    """Connect validated local evidence into a compact, non-prescriptive story."""
    required = (
        sentiment_summary,
        screener_summary,
        fno_summary,
        regime_validation,
        seasonality_payload,
        events_payload,
    )
    if any(payload.get("ok") is not True for payload in required):
        raise ValueError("dashboard_market_story_unavailable")
    current = regime_validation.get("current_state")
    if not isinstance(current, dict) or not current.get("classification_ready"):
        raise ValueError("dashboard_market_story_unavailable")

    evidence = current.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    observations = screener_summary.get("observations")
    observations = observations if isinstance(observations, dict) else {}
    screener_coverage = screener_summary.get("coverage")
    screener_coverage = screener_coverage if isinstance(screener_coverage, dict) else {}
    positioning = fno_summary.get("positioning")
    positioning = positioning if isinstance(positioning, dict) else {}
    sentiment_evidence = sentiment_summary.get("evidence")
    sentiment_evidence = sentiment_evidence if isinstance(sentiment_evidence, dict) else {}
    futures_confirmation = sentiment_summary.get("futures_short_confirmation")
    futures_confirmation = futures_confirmation if isinstance(futures_confirmation, dict) else {}

    regime_key = str(
        current.get("transition_label_key")
        or current.get("base_label_key")
        or "uncertain_market"
    )
    regime_label = str(
        current.get("transition_label")
        or current.get("base_label")
        or "Uncertain market"
    )
    regime_tones = {
        "positive_market": "constructive",
        "cautiously_positive": "cautious",
        "uncertain_market": "mixed",
        "weak_market": "defensive",
        "high_risk_market": "high_risk",
        "recovering_market": "recovering",
    }
    tone = regime_tones.get(regime_key, "mixed")
    score = float(current.get("score") or 0.0)
    nifty50_above_50 = float(evidence.get("above_50dma_pct") or 0.0)
    nifty50_above_200 = float(evidence.get("above_200dma_pct") or 0.0)
    nifty500_context = nifty500_context if isinstance(nifty500_context, dict) else {}
    nifty500_breadth = nifty500_context.get("breadth")
    nifty500_breadth = nifty500_breadth if isinstance(nifty500_breadth, dict) else {}
    nifty500_ready = bool(
        nifty500_context.get("ok") is True
        and nifty500_breadth.get("above_50dma_pct") is not None
        and nifty500_breadth.get("above_200dma_pct") is not None
    )
    above_50 = float(nifty500_breadth.get("above_50dma_pct") or 0.0) if nifty500_ready else nifty50_above_50
    above_200 = float(nifty500_breadth.get("above_200dma_pct") or 0.0) if nifty500_ready else nifty50_above_200
    volatility_percentile = float(evidence.get("realised_volatility_percentile") or 0.0)
    ready_stocks = int(
        nifty500_breadth.get("evaluated_20d")
        if nifty500_ready else screener_coverage.get("ready") or 0
    )
    positive_stocks = int(
        nifty500_breadth.get("positive_20d")
        if nifty500_ready else observations.get("positive_20d") or 0
    )
    positive_share = round(100 * positive_stocks / ready_stocks, 1) if ready_stocks else 0.0
    nifty_20d = float(screener_summary.get("benchmark_return_20d_pct") or 0.0)
    bullish = int(positioning.get("bullish") or 0)
    bearish = int(positioning.get("bearish") or 0)
    unclear = int(positioning.get("unclear") or 0)
    directional = bullish + bearish
    bullish_share = round(100 * bullish / directional, 1) if directional else 50.0

    def signal_state(value: float, positive_at: float, negative_below: float) -> str:
        if value >= positive_at:
            return "positive"
        if value < negative_below:
            return "negative"
        return "mixed"

    signals = [
        {
            "key": "trend",
            "label": "Regime",
            "state": signal_state(score, 25.0, -25.0),
            "value": regime_label,
            "meter_pct": round(max(0.0, min(100.0, (score + 100.0) / 2.0)), 1),
            "detail": f"Validated score {score:+.1f}; trailing inputs only.",
        },
        {
            "key": "breadth",
            "label": "Participation",
            "state": signal_state((above_50 + above_200) / 2.0, 60.0, 33.0) if nifty500_ready else "mixed",
            "value": f"{above_50:.0f}% / {above_200:.0f}%" if nifty500_ready else "EOD update required",
            "meter_pct": round(max(0.0, min(100.0, (above_50 + above_200) / 2.0)), 1) if nifty500_ready else 0.0,
            "detail": (
                f"NIFTY 500 stocks above 50-day / 200-day averages ({int(nifty500_breadth.get('evaluated') or 0)}/{int(nifty500_breadth.get('official_count') or 0)} evaluated)."
                if nifty500_ready else "Run EOD update to build full NIFTY 500 breadth."
            ),
        },
        {
            "key": "momentum",
            "label": "20-session tape",
            "state": "positive" if nifty_20d > 1 else "negative" if nifty_20d < -1 else "mixed",
            "value": f"{nifty_20d:+.2f}%",
            "meter_pct": round(max(0.0, min(100.0, positive_share)), 1),
            "detail": (
                f"{positive_stocks}/{ready_stocks} NIFTY 500 stocks positive over 20 sessions."
                if nifty500_ready else f"{positive_stocks}/{ready_stocks} liquid equities positive over 20 sessions; NIFTY 500 pending."
            ),
        },
        {
            "key": "derivatives",
            "label": "Futures positioning",
            "state": "positive" if bullish > bearish * 1.25 else "negative" if bearish > bullish * 1.25 else "mixed",
            "value": f"{bearish} bearish / {bullish} bullish",
            "meter_pct": bullish_share,
            "detail": f"{unclear} unclear; only {int(fno_summary.get('stored_history_sessions') or 0)} stored sessions.",
        },
        {
            "key": "volatility",
            "label": "Realised volatility",
            "state": "negative" if volatility_percentile >= 80 else "positive" if volatility_percentile <= 30 else "mixed",
            "value": f"{volatility_percentile:.0f}th percentile",
            "meter_pct": round(max(0.0, min(100.0, 100.0 - volatility_percentile)), 1),
            "detail": "Lower meter means a more elevated volatility backdrop.",
        },
    ]

    headline_map = {
        "positive_market": "Broad conditions are constructive, with risk participation in control.",
        "cautiously_positive": "The market is constructive, but confirmation is not broad enough for complacency.",
        "uncertain_market": "Signals disagree; the market lacks a durable directional edge.",
        "weak_market": "Participation is narrow and the derivatives tape leans bearish.",
        "high_risk_market": "Stress is broad; downside and volatility evidence dominate the tape.",
        "recovering_market": "Risk conditions are improving, but recovery confirmation remains incomplete.",
    }
    participation_text = (
        f"Across the NIFTY 500, {above_50:.0f}% of {int(nifty500_breadth.get('evaluated') or 0)} evaluated stocks are above the 50-day average and "
        f"{positive_stocks} of {ready_stocks} are positive over 20 sessions. "
        if nifty500_ready else
        "Full NIFTY 500 participation is pending the next EOD update; the regime remains based on validated Nifty 50 evidence. "
    )
    narrative = (
        f"Nifty 50 is classified as {regime_label.lower()} through {current.get('as_of_date')}. "
        f"{participation_text}"
        f"Futures positioning has {bearish} bearish versus {bullish} bullish quadrants; this is descriptive because its history is still short."
    )

    state_rows = regime_validation.get("by_state")
    state_rows = state_rows if isinstance(state_rows, list) else regime_validation.get("by_regime")
    state_rows = state_rows if isinstance(state_rows, list) else []
    matching_state = next(
        (
            row
            for row in state_rows
            if isinstance(row, dict) and row.get("label_key") == regime_key
        ),
        None,
    )
    if matching_state is None and regime_key == "recovering_market":
        matching_state = next(
            (
                row
                for row in state_rows
                if isinstance(row, dict) and row.get("label_key") == "uncertain_market"
            ),
            None,
        )
    analog_horizons: list[dict[str, object]] = []
    matching_horizons = matching_state.get("horizons") if isinstance(matching_state, dict) else {}
    matching_horizons = matching_horizons if isinstance(matching_horizons, dict) else {}
    for horizon in (5, 20, 60):
        row = matching_horizons.get(horizon) or matching_horizons.get(str(horizon))
        if not isinstance(row, dict):
            continue
        analog_horizons.append(
            {
                "sessions": horizon,
                "mean_return_pct": row.get("mean_return_pct"),
                "median_return_pct": row.get("median_return_pct"),
                "positive_rate_pct": row.get("positive_rate_pct"),
                "worst_return_pct": row.get("worst_return_pct"),
                "mean_max_drawdown_pct": row.get("mean_max_drawdown_pct"),
            }
        )

    as_of_text = str(current.get("as_of_date") or sentiment_summary.get("as_of_date") or "")
    try:
        month_label = date.fromisoformat(as_of_text[:10]).strftime("%b")
    except ValueError:
        month_label = ""
    month_rows = seasonality_payload.get("month_rows")
    month_rows = month_rows if isinstance(month_rows, list) else []
    current_month = next(
        (
            row
            for row in month_rows
            if isinstance(row, dict) and row.get("period") == month_label
        ),
        None,
    )
    events = events_payload.get("events")
    events = events if isinstance(events, list) else []
    catalysts = [
        {
            "title": event.get("title"),
            "start_at": event.get("start_at"),
            "end_at": event.get("end_at"),
            "days_until": event.get("days_until"),
            "region": event.get("region"),
            "category": event.get("category"),
            "source_label": event.get("source_label"),
        }
        for event in events[:3]
        if isinstance(event, dict)
    ]

    available_clusters = int(sentiment_evidence.get("available_clusters") or 0)
    total_clusters = int(sentiment_evidence.get("total_clusters") or 0)
    fresh = str((sentiment_summary.get("freshness") or {}).get("state")) == "fresh"
    history_ready = bool(futures_confirmation.get("history_ready"))
    confidence = "high" if fresh and available_clusters == total_clusters and history_ready else (
        "moderate" if fresh and available_clusters >= max(1, total_clusters - 1) else "limited"
    )
    next_event = catalysts[0] if catalysts else None
    relative_strength = nifty500_context.get("relative_strength")
    relative_strength = relative_strength if isinstance(relative_strength, dict) else {
        "window_sessions": 20,
        "benchmark": {"name": "Nifty 50", "return_pct": None},
        "indices": {"evaluated": 0, "strongest": None, "weakest": None},
        "sectors": {"evaluated": 0, "strongest": None, "weakest": None},
        "method": "Run EOD update to calculate relative strength from aligned completed sessions.",
    }
    watchpoints = [
        {
            "label": "Participation",
            "text": (
                f"NIFTY 500 breadth is {above_50:.0f}% above 50-day and {above_200:.0f}% above 200-day averages. Watch for sustained, broad improvement rather than a one-day bounce."
                if nifty500_ready else "Full NIFTY 500 breadth is not stored yet. Run EOD update before interpreting market participation."
            ),
        },
        {
            "label": "Derivatives confirmation",
            "text": f"Only {int(futures_confirmation.get('stored_history_sessions') or 0)}/{int(futures_confirmation.get('history_sessions_required') or 0)} required futures-history sessions are stored, so no directional confirmation is claimed.",
        },
        {
            "label": "Next catalyst",
            "text": (
                f"{next_event.get('title')} is the next reviewed macro event. Verify its official source before relying on the date or time."
                if next_event else "No future event remains in the reviewed calendar snapshot."
            ),
        },
    ]

    return {
        "ok": True,
        "contract_version": "dashboard-market-story-v1",
        "scope": "connected_evidence_not_forecast",
        "as_of_date": current.get("as_of_date") or sentiment_summary.get("as_of_date"),
        "regime": {
            "key": regime_key,
            "label": regime_label,
            "tone": tone,
            "score": score,
            "close": current.get("close"),
        },
        "headline": headline_map.get(regime_key, headline_map["uncertain_market"]),
        "narrative": narrative,
        "confidence": {
            "label": confidence,
            "fresh": fresh,
            "available_clusters": available_clusters,
            "total_clusters": total_clusters,
            "futures_history_ready": history_ready,
        },
        "signals": signals,
        "historical_analogue": {
            "label": matching_state.get("label") if isinstance(matching_state, dict) else regime_label,
            "sessions_observed": int(matching_state.get("sessions") or 0) if isinstance(matching_state, dict) else 0,
            "horizons": analog_horizons,
            "method": "Trailing-only regime classifications with overlapping forward windows.",
        },
        "seasonality": {
            "month": month_label,
            "count": int(current_month.get("count") or 0) if isinstance(current_month, dict) else 0,
            "average_return_pct": current_month.get("average_return_pct") if isinstance(current_month, dict) else None,
            "median_return_pct": current_month.get("median_return_pct") if isinstance(current_month, dict) else None,
            "positive_months_pct": current_month.get("positive_months_pct") if isinstance(current_month, dict) else None,
            "holdout_survived": int((seasonality_payload.get("held_out_summary") or {}).get("survived") or 0),
        },
        "market_context": {
            "breadth": nifty500_breadth if nifty500_ready else None,
            "relative_strength": relative_strength,
            "as_of_date": nifty500_context.get("as_of_date"),
        },
        "catalysts": catalysts,
        "watchpoints": watchpoints,
        "limitations": [
            "This joins validated observations; it does not forecast the market or recommend a trade.",
            "Historical regime windows overlap and are not independent observations.",
            "NIFTY 500 breadth and sector returns use current constituents and therefore carry survivorship bias.",
            "Sector relative strength is an equal-weight stock observation, not an official sector-index return.",
            "Portfolio sensitivity is calculated in the browser only after a holdings upload.",
        ],
    }


def build_news_events_workspace(
    *,
    reviewed_on: date,
    live_items: list[dict[str, object]] | None = None,
    sources: tuple[dict[str, object], ...] = NEWS_EVENT_SOURCES,
    event_windows: tuple[dict[str, object], ...] = REGIME_VALIDATION_EVENTS,
) -> dict[str, object]:
    """Expose an honest source-readiness contract before live news ingestion."""
    imported_items = live_items if isinstance(live_items, list) else []
    source_rows = [
        {
            "key": str(source["key"]),
            "label": str(source["label"]),
            "category": str(source["category"]),
            "authority": str(source["authority"]),
            "url": str(source["url"]),
            "terms_url": str(source.get("terms_url") or ""),
            "coverage": str(source["coverage"]),
            "status": (
                "manual_file_imported"
                if source["key"] == "nse_corporate_filings" and imported_items
                else "manual_csv_ready"
                if source["key"] == "nse_corporate_filings"
                else "not_connected"
            ),
            "permission_state": (
                "manual_download_only_automated_collection_prohibited"
                if source["key"] == "nse_corporate_filings"
                else "ingestion_review_required"
            ),
            "last_item_at": (
                max(
                    (
                        str(item.get("published_at"))
                        for item in imported_items
                        if item.get("source_key") == "nse_corporate_filings_manual_csv"
                    ),
                    default=None,
                )
                if source["key"] == "nse_corporate_filings"
                else None
            ),
        }
        for source in sources
    ]
    historical_events = []
    for event in event_windows:
        start = event.get("start")
        end = event.get("end")
        if not isinstance(start, date) or not isinstance(end, date) or end < start:
            continue
        historical_events.append(
            {
                "key": str(event.get("key") or "historical_event"),
                "label": str(event.get("label") or "Historical event window"),
                "category": "retrospective_stress_window",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "status": "available_in_market_sentiment",
                "source": "Fixed internal validation window",
                "selection_note": "Selected retrospectively with hindsight; not a live event signal.",
            }
        )
    return {
        "ok": True,
        "status": "manual_import_ready",
        "scope": "official_source_registry_and_local_event_windows",
        "reviewed_on": reviewed_on.isoformat(),
        "contract": {
            "version": "news-events-foundation-v1",
            "live_ingestion_enabled": False,
            "manual_csv_import_enabled": True,
            "nse_automated_collection_allowed": False,
            "headline_sentiment_enabled": False,
            "automated_impact_score_enabled": False,
        },
        "coverage": {
            "official_sources_reviewed": len(source_rows),
            "connected_sources": 0,
            "manually_imported_sources": 1 if imported_items else 0,
            "live_items": len(imported_items),
            "local_historical_events": len(historical_events),
        },
        "sources": source_rows,
        "live_items": imported_items,
        "historical_events": historical_events,
        "limitations": [
            "NSE automated collection is disabled because its published terms prohibit systematic or automated website collection.",
            "NSE records may be imported only from a CSV the user manually downloads from the official page.",
            "Source permissions, rate limits, identifiers, revision handling, and attachment retention must be approved before collection.",
            "Historical stress windows were selected retrospectively with hindsight and are not upcoming-event forecasts.",
            "No headline sentiment, materiality score, trade signal, or portfolio instruction is generated.",
        ],
    }


def parse_nse_announcement_csv(csv_payload: str) -> list[dict[str, object]]:
    """Normalize a user-downloaded NSE announcement CSV without fetching NSE."""
    if not isinstance(csv_payload, str) or not csv_payload.strip():
        raise ValueError("invalid_nse_announcement_csv")
    reader = csv.DictReader(io.StringIO(csv_payload.lstrip("\ufeff")))
    if reader.fieldnames is None:
        raise ValueError("invalid_nse_announcement_csv")

    def normalized_header(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    header_lookup = {
        normalized_header(header): header
        for header in reader.fieldnames
        if isinstance(header, str)
    }

    def find_header(aliases: tuple[str, ...], *, required: bool = True) -> str | None:
        for alias in aliases:
            header = header_lookup.get(normalized_header(alias))
            if header is not None:
                return header
        if required:
            raise ValueError("unsupported_nse_announcement_csv_columns")
        return None

    symbol_header = find_header(("symbol", "nse symbol", "nse_symbol"))
    company_header = find_header(("company name", "company", "company_name"))
    headline_header = find_header(("subject", "headline", "purpose", "description"))
    published_header = find_header(
        (
            "broadcast date/time",
            "broadcast datetime",
            "broadcast date",
            "announcement date",
            "submission date",
            "date",
        )
    )
    attachment_header = find_header(
        ("attachment url", "attachment", "file url", "document url"),
        required=False,
    )

    def parse_published(value: str) -> str:
        cleaned = value.strip()
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is None:
            for pattern in (
                "%d-%b-%Y %H:%M:%S",
                "%d-%b-%Y %H:%M",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%d-%m-%Y",
                "%d-%b-%Y",
            ):
                try:
                    parsed = datetime.strptime(cleaned, pattern)
                    break
                except ValueError:
                    continue
        if parsed is None:
            raise ValueError("invalid_nse_announcement_date")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=INDIA_TIMEZONE)
        return parsed.isoformat(timespec="seconds")

    rows: list[dict[str, object]] = []
    for raw_row in reader:
        if not isinstance(raw_row, dict) or not any(str(value or "").strip() for value in raw_row.values()):
            continue
        symbol = str(raw_row.get(symbol_header) or "").strip().upper()
        company_name = str(raw_row.get(company_header) or "").strip()
        headline = str(raw_row.get(headline_header) or "").strip()
        published_text = str(raw_row.get(published_header) or "").strip()
        if (
            not re.fullmatch(r"[A-Z0-9&.\-]{1,32}", symbol)
            or not company_name
            or len(company_name) > 240
            or not headline
            or len(headline) > 2000
            or not published_text
        ):
            raise ValueError("invalid_nse_announcement_row")
        attachment_url = None
        if attachment_header is not None:
            candidate = str(raw_row.get(attachment_header) or "").strip()
            if candidate:
                parsed_url = urllib.parse.urlsplit(candidate)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    raise ValueError("invalid_nse_announcement_attachment")
                attachment_url = candidate
        rows.append(
            {
                "source_key": "nse_corporate_filings_manual_csv",
                "published_at": parse_published(published_text),
                "symbol": symbol,
                "company_name": company_name,
                "category": "corporate_announcement",
                "headline": headline,
                "attachment_url": attachment_url,
                "raw": {
                    str(key): str(value or "")
                    for key, value in raw_row.items()
                    if key is not None
                },
            }
        )
        if len(rows) > 5000:
            raise ValueError("nse_announcement_csv_too_many_rows")
    if not rows:
        raise ValueError("nse_announcement_csv_empty")
    return rows


def parse_earnings_csv(csv_payload: str) -> list[dict[str, object]]:
    """Validate a user-supplied quarterly earnings CSV without fetching issuer data."""
    if not isinstance(csv_payload, str) or not csv_payload.strip():
        raise ValueError("invalid_earnings_csv")
    reader = csv.DictReader(io.StringIO(csv_payload.lstrip("\ufeff")))
    if reader.fieldnames is None:
        raise ValueError("invalid_earnings_csv")
    aliases = {re.sub(r"[^a-z0-9]", "", name.lower()): name for name in reader.fieldnames}
    required = {
        "symbol", "companyname", "sector", "basis", "fiscalyear", "quarter",
        "periodend", "reportedat", "currency", "unit", "revenue", "netprofit",
        "eps", "sourceurl",
    }
    if not required.issubset(aliases):
        raise ValueError("unsupported_earnings_csv_columns")

    def field(row: dict[str, str], key: str) -> str:
        return str(row.get(aliases[key]) or "").strip()

    def number(value: str) -> float:
        text = value.replace(",", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = f"-{text[1:-1]}"
        try:
            result = float(text)
        except ValueError as error:
            raise ValueError("invalid_earnings_value") from error
        if not math.isfinite(result):
            raise ValueError("invalid_earnings_value")
        return result

    rows: list[dict[str, object]] = []
    for raw in reader:
        symbol = field(raw, "symbol").upper()
        company_name = field(raw, "companyname")
        sector = field(raw, "sector")
        basis = field(raw, "basis").lower()
        fiscal_year = field(raw, "fiscalyear")
        quarter = field(raw, "quarter").upper()
        currency = field(raw, "currency").upper()
        unit = field(raw, "unit").lower()
        source_url = field(raw, "sourceurl")
        fiscal_match = re.fullmatch(r"(20\d{2})-(\d{2})", fiscal_year)
        parsed_url = urllib.parse.urlsplit(source_url)
        if (
            not re.fullmatch(r"[A-Z0-9][A-Z0-9&.-]{0,39}", symbol)
            or not company_name
            or len(company_name) > 160
            or not sector
            or len(sector) > 120
            or basis not in {"consolidated", "standalone"}
            or fiscal_match is None
            or int(fiscal_match.group(2)) != (int(fiscal_match.group(1)) + 1) % 100
            or quarter not in {"Q1", "Q2", "Q3", "Q4"}
            or currency != "INR"
            or unit not in {"crore", "lakh", "million"}
            or parsed_url.scheme != "https"
            or not parsed_url.netloc
        ):
            raise ValueError("invalid_earnings_row")
        try:
            period_end = date.fromisoformat(field(raw, "periodend"))
            reported_at = date.fromisoformat(field(raw, "reportedat"))
        except ValueError as error:
            raise ValueError("invalid_earnings_date") from error
        if reported_at < period_end or reported_at > datetime.now(INDIA_TIMEZONE).date():
            raise ValueError("invalid_earnings_date")
        revenue = number(field(raw, "revenue"))
        net_profit = number(field(raw, "netprofit"))
        eps = number(field(raw, "eps"))
        if revenue < 0:
            raise ValueError("invalid_earnings_value")
        rows.append(
            {
                "symbol": symbol,
                "company_name": company_name,
                "sector": sector,
                "basis": basis,
                "fiscal_year": fiscal_year,
                "quarter": quarter,
                "period_end": period_end.isoformat(),
                "reported_at": reported_at.isoformat(),
                "currency": currency,
                "unit": unit,
                "revenue": revenue,
                "net_profit": net_profit,
                "eps": eps,
                "source_url": source_url,
                "raw": dict(raw),
            }
        )
        if len(rows) > 5000:
            raise ValueError("earnings_csv_too_many_rows")
    if not rows:
        raise ValueError("earnings_csv_empty")
    return rows


def build_earnings_analysis(records: list[dict[str, object]]) -> dict[str, object]:
    """Build latest-quarter growth evidence from append-only imported records."""
    identities: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for record in records:
        identity = (
            str(record.get("symbol") or ""),
            str(record.get("basis") or ""),
            str(record.get("fiscal_year") or ""),
            str(record.get("quarter") or ""),
        )
        existing = identities.get(identity)
        if existing is None or str(record.get("imported_at") or "") > str(existing.get("imported_at") or ""):
            identities[identity] = record
    clean_records = list(identities.values())
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for record in clean_records:
        groups.setdefault((str(record["symbol"]), str(record["basis"])), []).append(record)

    def growth(current: float, prior: float) -> float | None:
        return round(((current / prior) - 1) * 100, 2) if prior > 0 else None

    rows: list[dict[str, object]] = []
    for (symbol, basis), series in groups.items():
        series.sort(key=lambda item: (str(item["period_end"]), str(item["reported_at"])))
        latest = series[-1]
        fiscal_start = int(str(latest["fiscal_year"])[:4])
        prior_year_label = f"{fiscal_start - 1}-{fiscal_start % 100:02d}"
        yoy = next(
            (
                item for item in reversed(series[:-1])
                if item["fiscal_year"] == prior_year_label and item["quarter"] == latest["quarter"]
            ),
            None,
        )
        quarter_number = int(str(latest["quarter"])[1])
        if quarter_number == 1:
            previous_quarter = "Q4"
            previous_fiscal_year = prior_year_label
        else:
            previous_quarter = f"Q{quarter_number - 1}"
            previous_fiscal_year = str(latest["fiscal_year"])
        qoq = next(
            (
                item for item in reversed(series[:-1])
                if item["fiscal_year"] == previous_fiscal_year
                and item["quarter"] == previous_quarter
            ),
            None,
        )
        comparable_yoy = bool(
            yoy
            and yoy["currency"] == latest["currency"]
            and yoy["unit"] == latest["unit"]
        )
        comparable_qoq = bool(
            qoq
            and qoq["currency"] == latest["currency"]
            and qoq["unit"] == latest["unit"]
        )
        latest_profit = float(latest["net_profit"])
        yoy_profit = float(yoy["net_profit"]) if comparable_yoy and yoy else None
        if yoy_profit is None:
            profit_state = "comparison_unavailable"
        elif latest_profit > 0 >= yoy_profit:
            profit_state = "turned_profitable"
        elif latest_profit < 0 <= yoy_profit:
            profit_state = "moved_to_loss"
        elif latest_profit > yoy_profit:
            profit_state = "profit_improved"
        elif latest_profit < yoy_profit:
            profit_state = "profit_declined"
        else:
            profit_state = "profit_unchanged"
        rows.append(
            {
                "symbol": symbol,
                "company_name": latest["company_name"],
                "sector": latest["sector"],
                "basis": basis,
                "fiscal_year": latest["fiscal_year"],
                "quarter": latest["quarter"],
                "period_end": latest["period_end"],
                "reported_at": latest["reported_at"],
                "currency": latest["currency"],
                "unit": latest["unit"],
                "revenue": round(float(latest["revenue"]), 2),
                "revenue_yoy_pct": growth(float(latest["revenue"]), float(yoy["revenue"])) if comparable_yoy and yoy else None,
                "revenue_qoq_pct": growth(float(latest["revenue"]), float(qoq["revenue"])) if comparable_qoq and qoq else None,
                "net_profit": round(latest_profit, 2),
                "net_profit_yoy_pct": growth(latest_profit, yoy_profit) if yoy_profit is not None else None,
                "net_profit_yoy_change": round(latest_profit - yoy_profit, 2) if yoy_profit is not None else None,
                "eps": round(float(latest["eps"]), 2),
                "eps_yoy_pct": growth(float(latest["eps"]), float(yoy["eps"])) if comparable_yoy and yoy else None,
                "profit_state": profit_state,
                "status": "ready" if comparable_yoy else "partial_history",
                "source_url": latest["source_url"],
            }
        )
    rows.sort(
        key=lambda row: (
            row["revenue_yoy_pct"] is None,
            -float(row["revenue_yoy_pct"]) if row["revenue_yoy_pct"] is not None else 0.0,
            str(row["symbol"]),
        )
    )
    latest_reported = max((str(row["reported_at"]) for row in rows), default=None)
    return {
        "ok": True,
        "status": "earnings_ready" if rows else "no_earnings_data",
        "contract_version": "earnings-analysis-v1",
        "as_of_date": latest_reported,
        "coverage": {
            "stored_records": len(records),
            "distinct_quarters": len(clean_records),
            "latest_rows": len(rows),
            "companies": len({row["symbol"] for row in rows}),
            "yoy_ready": sum(row["status"] == "ready" for row in rows),
            "turnarounds": sum(row["profit_state"] == "turned_profitable" for row in rows),
            "moved_to_loss": sum(row["profit_state"] == "moved_to_loss" for row in rows),
        },
        "rows": rows,
        "required_columns": [
            "Symbol", "Company Name", "Sector", "Basis", "Fiscal Year", "Quarter",
            "Period End", "Reported At", "Currency", "Unit", "Revenue", "Net Profit",
            "EPS", "Source URL",
        ],
        "limitations": [
            "Only manually imported issuer or exchange results are used; automated website collection is disabled.",
            "YoY comparisons require the same symbol, basis, quarter, currency, and unit in the prior fiscal year.",
            "Percentage profit and EPS growth is withheld when the comparison value is zero or negative.",
            "No consensus estimate, surprise score, valuation conclusion, recommendation, or trading signal is produced.",
        ],
    }


def _portfolio_headers_and_rows(raw_rows: list[list[object]]) -> tuple[list[str], list[dict[str, object]]]:
    """Turn a worksheet-like matrix into a bounded, JSON-safe table."""
    def header_score(row: list[object]) -> int:
        keys = [re.sub(r"[^a-z0-9]", "", str(cell).lower()) for cell in row if str(cell).strip()]
        if len(keys) < 2:
            return 0
        symbol = any(
            any(token in key for token in ("symbol", "ticker", "instrument", "scrip", "security", "stockcode", "nsecode"))
            for key in keys
        )
        measure = any(
            "quantity" in key or "qty" in key or key in {"units", "shares"}
            or "weight" in key or "allocation" in key
            or ((any(prefix in key for prefix in ("current", "market", "closing", "present", "total"))) and "val" in key)
            for key in keys
        )
        optional = sum(
            any(token in key for token in ("average", "avg", "cost", "sector", "industry", "company", "name"))
            for key in keys
        )
        return (10 if symbol else 0) + (10 if measure else 0) + optional

    candidates = [
        (header_score(row), index)
        for index, row in enumerate(raw_rows[:25])
        if any(str(cell).strip() for cell in row)
    ]
    first = max(
        candidates,
        key=lambda item: (
            item[0],
            -sum(bool(str(cell).strip()) for cell in raw_rows[item[1]]),
        ),
        default=(0, None),
    )[1]
    if candidates and max(candidates)[0] < 20:
        first = next((index for index, row in enumerate(raw_rows) if any(str(cell).strip() for cell in row)), None)
    if first is None:
        raise ValueError("portfolio_file_empty")
    headers = [str(cell).strip() for cell in raw_rows[first]]
    while headers and not headers[-1]:
        headers.pop()
    if not headers or len(headers) > MAX_PORTFOLIO_COLUMNS or any(not header for header in headers):
        raise ValueError("invalid_portfolio_headers")
    normalized = [re.sub(r"[^a-z0-9]", "", header.lower()) for header in headers]
    if any(not header for header in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("duplicate_portfolio_headers")
    rows: list[dict[str, object]] = []

    def normalized_row(raw: list[object]) -> list[str]:
        values = [re.sub(r"[^a-z0-9]", "", str(value).lower()) for value in raw[:len(headers)]]
        values.extend([""] * (len(headers) - len(values)))
        return values

    header_positions = [
        index for index, raw in enumerate(raw_rows)
        if normalized_row(raw) == normalized
    ]
    if len(header_positions) > 1:
        # Some personal trackers place several identically shaped Excel tables on
        # one sheet. Read each contiguous table body and stop at its first blank
        # row so later summaries are not mistaken for holdings.
        for header_position in header_positions:
            for raw in raw_rows[header_position + 1:]:
                values = list(raw[:len(headers)])
                values.extend([""] * (len(headers) - len(values)))
                if not any(str(value).strip() for value in values):
                    break
                if normalized_row(raw) == normalized:
                    break
                rows.append({header: value for header, value in zip(headers, values)})
                if len(rows) > MAX_PORTFOLIO_ROWS:
                    raise ValueError("portfolio_file_too_many_rows")
    else:
        for raw in raw_rows[first + 1:]:
            values = list(raw[:len(headers)])
            values.extend([""] * (len(headers) - len(values)))
            if not any(str(value).strip() for value in values):
                continue
            rows.append({header: value for header, value in zip(headers, values)})
            if len(rows) > MAX_PORTFOLIO_ROWS:
                raise ValueError("portfolio_file_too_many_rows")
    if not rows:
        raise ValueError("portfolio_file_empty")
    return headers, rows


def parse_portfolio_csv(payload: bytes) -> tuple[list[str], list[dict[str, object]], str | None]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("portfolio_csv_not_utf8") from error
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    matrix = [list(row) for row in csv.reader(io.StringIO(text), dialect)]
    headers, rows = _portfolio_headers_and_rows(matrix)
    return headers, rows, None


def _excel_column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Za-z]+", cell_reference or "")
    if letters is None:
        raise ValueError("invalid_portfolio_xlsx")
    result = 0
    for character in letters.group(0).upper():
        result = result * 26 + ord(character) - 64
    return result - 1


def parse_portfolio_xlsx(payload: bytes) -> tuple[list[str], list[dict[str, object]], str | None]:
    """Read the first XLSX worksheet with the standard library only."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("invalid_portfolio_xlsx") from error
    with archive:
        members = archive.infolist()
        if len(members) > 500 or sum(item.file_size for item in members) > 50 * 1024 * 1024:
            raise ValueError("portfolio_xlsx_too_large")
        names = {item.filename for item in members}
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(names):
            raise ValueError("invalid_portfolio_xlsx")
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (ET.ParseError, KeyError) as error:
            raise ValueError("invalid_portfolio_xlsx") from error
        relationship_targets = {
            item.attrib.get("Id", ""): item.attrib.get("Target", "")
            for item in relationships
        }
        sheets = workbook.findall(".//{*}sheet")
        if not sheets:
            raise ValueError("invalid_portfolio_xlsx")
        sheet = sheets[0]
        relationship_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = relationship_targets.get(relationship_id, "")
        target = target.lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        if ".." in Path(sheet_path).parts or sheet_path not in names:
            raise ValueError("invalid_portfolio_xlsx")
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            try:
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = ["".join(node.itertext()) for node in shared_root.findall(".//{*}si")]
            except ET.ParseError as error:
                raise ValueError("invalid_portfolio_xlsx") from error
        try:
            worksheet = ET.fromstring(archive.read(sheet_path))
        except (ET.ParseError, KeyError) as error:
            raise ValueError("invalid_portfolio_xlsx") from error
        matrix: list[list[object]] = []
        for row_node in worksheet.findall(".//{*}sheetData/{*}row"):
            row: list[object] = []
            for cell in row_node.findall("{*}c"):
                column = _excel_column_index(cell.attrib.get("r", ""))
                if column >= MAX_PORTFOLIO_COLUMNS:
                    raise ValueError("portfolio_file_too_many_columns")
                row.extend([""] * (column + 1 - len(row)))
                cell_type = cell.attrib.get("t", "")
                value_node = cell.find("{*}v")
                if cell_type == "inlineStr":
                    inline = cell.find("{*}is")
                    value: object = "" if inline is None else "".join(inline.itertext())
                else:
                    raw_value = "" if value_node is None else (value_node.text or "")
                    if cell_type == "s":
                        try:
                            value = shared_strings[int(raw_value)]
                        except (ValueError, IndexError) as error:
                            raise ValueError("invalid_portfolio_xlsx") from error
                    elif cell_type in {"str", "b", "e"}:
                        value = raw_value
                    else:
                        try:
                            number = float(raw_value)
                            value = int(number) if number.is_integer() else number
                        except ValueError:
                            value = raw_value
                row[column] = value
            matrix.append(row)
            if len(matrix) > MAX_PORTFOLIO_ROWS + 25:
                raise ValueError("portfolio_file_too_many_rows")
        headers, rows = _portfolio_headers_and_rows(matrix)
        return headers, rows, sheet.attrib.get("name") or "Sheet 1"


def parse_home_loan_tracker_xlsx(payload: bytes) -> dict[str, object] | None:
    """Read an optional home-loan worksheet from an uploaded portfolio workbook."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("invalid_portfolio_xlsx") from error
    with archive:
        members = archive.infolist()
        if len(members) > 500 or sum(item.file_size for item in members) > 50 * 1024 * 1024:
            raise ValueError("portfolio_xlsx_too_large")
        names = {item.filename for item in members}
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (ET.ParseError, KeyError) as error:
            raise ValueError("invalid_portfolio_xlsx") from error
        sheet = next(
            (
                item for item in workbook.findall(".//{*}sheet")
                if "loan" in re.sub(r"[^a-z0-9]", "", str(item.attrib.get("name") or "").lower())
            ),
            None,
        )
        if sheet is None:
            return None
        relationship_targets = {
            item.attrib.get("Id", ""): item.attrib.get("Target", "")
            for item in relationships
        }
        relationship_id = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
        )
        target = relationship_targets.get(relationship_id, "").lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        if ".." in Path(sheet_path).parts or sheet_path not in names:
            raise ValueError("invalid_portfolio_xlsx")
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            try:
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = ["".join(node.itertext()) for node in shared_root.findall(".//{*}si")]
            except ET.ParseError as error:
                raise ValueError("invalid_portfolio_xlsx") from error
        try:
            worksheet = ET.fromstring(archive.read(sheet_path))
        except (ET.ParseError, KeyError) as error:
            raise ValueError("invalid_portfolio_xlsx") from error

        matrix: dict[int, list[object]] = {}
        for row_node in worksheet.findall(".//{*}sheetData/{*}row"):
            try:
                row_number = int(row_node.attrib.get("r", "0"))
            except ValueError as error:
                raise ValueError("invalid_portfolio_xlsx") from error
            if row_number <= 0 or row_number > MAX_PORTFOLIO_ROWS:
                continue
            row: list[object] = []
            for cell in row_node.findall("{*}c"):
                column = _excel_column_index(cell.attrib.get("r", ""))
                if column >= MAX_PORTFOLIO_COLUMNS:
                    continue
                row.extend([""] * (column + 1 - len(row)))
                cell_type = cell.attrib.get("t", "")
                value_node = cell.find("{*}v")
                if cell_type == "inlineStr":
                    inline = cell.find("{*}is")
                    value: object = "" if inline is None else "".join(inline.itertext())
                else:
                    raw_value = "" if value_node is None else (value_node.text or "")
                    if cell_type == "s":
                        try:
                            value = shared_strings[int(raw_value)]
                        except (ValueError, IndexError) as error:
                            raise ValueError("invalid_portfolio_xlsx") from error
                    elif cell_type in {"str", "b", "e"}:
                        value = raw_value
                    else:
                        try:
                            number = float(raw_value)
                            value = int(number) if number.is_integer() else number
                        except ValueError:
                            value = raw_value
                row[column] = value
            matrix[row_number] = row

        def cell(row_number: int, column: int) -> object:
            row = matrix.get(row_number, [])
            return row[column] if column < len(row) else ""

        payment_rows: list[dict[str, object]] = []
        totals: dict[str, float | None] = {"principal": None, "interest": None, "payment": None}
        outstanding: float | None = None
        outstanding_as_of: str | None = None
        annual_rate_pct: float | None = None
        for row_number in sorted(matrix):
            label = str(cell(row_number, 0) or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}", label):
                principal = _portfolio_number(cell(row_number, 1))
                interest = _portfolio_number(cell(row_number, 2))
                total = _portfolio_number(cell(row_number, 3))
                if any(value not in (None, 0) for value in (principal, interest, total)):
                    payment_rows.append({
                        "fiscal_year": label,
                        "principal": principal or 0.0,
                        "interest": interest or 0.0,
                        "payment": total if total is not None else (principal or 0.0) + (interest or 0.0),
                    })
            elif label.lower() == "total":
                totals = {
                    "principal": _portfolio_number(cell(row_number, 1)),
                    "interest": _portfolio_number(cell(row_number, 2)),
                    "payment": _portfolio_number(cell(row_number, 3)),
                }
            elif label.lower().startswith("outstanding"):
                outstanding = _portfolio_number(cell(row_number, 1))
                rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(cell(row_number, 2) or ""))
                annual_rate_pct = float(rate_match.group(1)) if rate_match else None
                date_match = re.search(r"as\s+on\s+(.+?)\)?$", label, re.IGNORECASE)
                if date_match:
                    raw_date = date_match.group(1).strip()
                    try:
                        outstanding_as_of = datetime.strptime(raw_date, "%b %d %Y").date().isoformat()
                    except ValueError:
                        outstanding_as_of = raw_date

        rent_totals: dict[str, float | None] = {"rent": None, "maintenance": None, "net_rent": None}
        for row_number in sorted(matrix):
            if str(cell(row_number, 8) or "").strip().lower() == "total":
                rent_totals = {
                    "rent": _portfolio_number(cell(row_number, 9)),
                    "maintenance": _portfolio_number(cell(row_number, 10)),
                    "net_rent": _portfolio_number(cell(row_number, 11)),
                }
                break

        if not payment_rows and outstanding is None:
            return None
        latest_payment = next((row for row in reversed(payment_rows) if float(row["payment"]) > 0), None)
        suggested_monthly_payment = (
            round(float(latest_payment["payment"]) / 12, 2) if latest_payment else None
        )
        return {
            "contract_version": "home-loan-tracker-v1",
            "sheet_name": sheet.attrib.get("name") or "Loan payments",
            "payment_rows": payment_rows,
            "totals": totals,
            "outstanding": outstanding,
            "outstanding_as_of": outstanding_as_of,
            "annual_rate_pct": annual_rate_pct,
            "suggested_monthly_payment": suggested_monthly_payment,
            "suggested_payment_basis": (
                f"{latest_payment['fiscal_year']} annual payment divided by 12" if latest_payment else None
            ),
            "rent_totals": rent_totals,
        }


def parse_portfolio_file(file_name: str, payload: bytes) -> dict[str, object]:
    if not payload or len(payload) > MAX_PORTFOLIO_FILE_BYTES:
        raise ValueError("invalid_portfolio_file_size")
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        headers, rows, sheet_name = parse_portfolio_csv(payload)
        loan_tracker = None
    elif suffix == ".xlsx":
        headers, rows, sheet_name = parse_portfolio_xlsx(payload)
        loan_tracker = parse_home_loan_tracker_xlsx(payload)
    else:
        raise ValueError("unsupported_portfolio_file")
    mapping = infer_portfolio_mapping(headers, rows)
    return {
        "ok": True,
        "contract_version": "portfolio-upload-preview-v1",
        "file_name": file_name,
        "sheet_name": sheet_name,
        "headers": headers,
        "row_count": len(rows),
        "sample_rows": rows[:8],
        "rows": rows,
        "detected_mapping": mapping,
        "loan_tracker": loan_tracker,
        "persistence": "browser_memory_only",
    }


def infer_portfolio_mapping(
    headers: list[str], rows: list[dict[str, object]]
) -> dict[str, str | None]:
    """Detect common Indian broker and portfolio-export column names."""
    normalized = {header: re.sub(r"[^a-z0-9]", "", header.lower()) for header in headers}
    aliases = {
        "symbol": (
            "symbol", "tradingsymbol", "ticker", "instrument", "stock", "scrip",
            "security", "nsecode", "stockcode", "nsesymbol", "securitysymbol",
            "tradingscrip", "scripcode",
        ),
        "quantity": (
            "quantity", "qty", "netqty", "netquantity", "holdingqty", "holdingsqty",
            "units", "shares", "availableqty", "availablequantity", "totalqty",
            "totalquantity", "freeqty", "freequantity", "settledqty", "holdingquantity",
            "holding", "holdings", "balance", "netposition", "positionqty",
        ),
        "weight": (
            "weight", "weightpct", "weightpercentage", "portfolioweight",
            "allocation", "allocationpct", "allocationpercentage",
        ),
        "average_cost": (
            "averagecost", "avgcost", "averageprice", "avgprice", "buyaverage",
            "buyavg", "costprice", "averagebuyprice", "avgcostprice", "buyprice",
        ),
        "current_value": (
            "currentvalue", "curvalue", "marketvalue", "holdingvalue", "presentvalue",
            "currentvaluation", "marketvaluation", "valuation", "curval", "mktvalue",
            "marketval", "currentmarketvalue", "presentmarketvalue", "closingvalue",
            "netvalue", "totalvalue", "currval", "cmpvalue", "holdingvaluation",
        ),
        "latest_price": (
            "ltp", "latestprice", "currentprice", "marketprice", "lasttradedprice",
            "cmp", "nav", "currentnav", "latestnav",
        ),
        "entry_date": (
            "entrydate", "purchasedate", "buydate", "investmentdate",
            "acquisitiondate", "dateofpurchase", "transactiondate",
        ),
        "invested_value": (
            "investedamount", "investmentamount", "investedvalue", "buyvalue",
            "purchasevalue", "totalcost", "costvalue", "costbasis",
        ),
        "sector": ("sector", "industry", "industryname", "sectorname"),
        "name": (
            "companyname", "company", "securityname", "instrumentname", "stockname", "name", "instrument",
        ),
    }

    def match(field: str) -> str | None:
        candidates = aliases[field]
        exact = next(
            (
                header for candidate in candidates
                for header, key in normalized.items()
                if key == candidate
            ),
            None,
        )
        if exact is not None:
            return exact
        return next(
            (
                header for header, key in normalized.items()
                if any(len(alias) >= 5 and (key.startswith(alias) or key.endswith(alias)) for alias in candidates)
            ),
            None,
        )

    mapping = {field: match(field) for field in aliases}
    if mapping["quantity"] is None:
        mapping["quantity"] = next(
            (
                header for header, key in normalized.items()
                if "quantity" in key or "qty" in key or "units" in key or "shares" in key
                or key in {"holding", "holdings", "balance", "netposition"}
            ),
            None,
        )
    if mapping["weight"] is None:
        mapping["weight"] = next(
            (header for header, key in normalized.items() if "weight" in key or "allocation" in key),
            None,
        )
    if mapping["current_value"] is None:
        mapping["current_value"] = next(
            (
                header for header, key in normalized.items()
                if "val" in key and any(prefix in key for prefix in ("current", "market", "closing", "present", "total", "net"))
            ),
            None,
        )
    if mapping["average_cost"] is None:
        mapping["average_cost"] = next(
            (
                header for header, key in normalized.items()
                if any(prefix in key for prefix in ("average", "avg", "buy", "cost"))
                and any(suffix in key for suffix in ("price", "cost", "rate"))
            ),
            None,
        )
    if mapping["symbol"] is None:
        symbol_candidates: list[str] = []
        for header in headers:
            values = [str(row.get(header, "")).strip().upper() for row in rows[:100]]
            populated = [value for value in values if value]
            if populated and sum(bool(re.fullmatch(r"(?:NSE:|BSE:)?[A-Z0-9&-]{1,32}(?:-(?:EQ|BE|RR))?", value)) for value in populated) / len(populated) >= 0.90:
                symbol_candidates.append(header)
        if len(symbol_candidates) == 1:
            mapping["symbol"] = symbol_candidates[0]
    if mapping["symbol"] is None:
        raise ValueError("portfolio_symbol_column_not_recognized")
    if mapping["quantity"] is None and mapping["weight"] is None and mapping["current_value"] is None:
        raise ValueError("portfolio_quantity_weight_or_value_not_recognized")
    return mapping


def _portfolio_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    cleaned = re.sub(r"[₹,$%\s]", "", str(value)).replace(",", "")
    if not cleaned:
        return None
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        result = float(cleaned)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _portfolio_date(value: object) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        serial = float(value)
        if 1 <= serial <= 100000:
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        serial = float(text)
    except ValueError:
        serial = None
    if serial is not None and math.isfinite(serial) and 1 <= serial <= 100000:
        return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
    for format_text in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, format_text).date()
        except ValueError:
            continue
    return None


def classify_portfolio_asset_class(
    symbol: str,
    company_name: str,
    *,
    has_exchange_evidence: bool = False,
) -> str:
    """Classify a holding conservatively from its label and market evidence."""
    text = re.sub(r"[^a-z0-9]+", " ", f"{symbol} {company_name}".lower()).strip()
    compact = text.replace(" ", "")

    if any(term in text for term in ("gold", "silver", "commodity")):
        return "Commodity"
    if any(term in text for term in (
        "multi asset", "balanced advantage", "dynamic asset allocation",
        "aggressive hybrid", "conservative hybrid", "equity savings", "arbitrage",
        "hybrid fund",
    )):
        return "Hybrid"
    if any(term in text for term in (
        "cash", "bank balance", "savings account", "sweep account",
    )):
        return "Cash"
    if (
        re.search(r"\bncd\b|\bbond\b|\bdebenture\b|\bdebt\b|\bgilt\b|\btreasury\b", text)
        or any(term in text for term in (
            "fixed deposit", "short term fund", "ultra short", "low duration",
            "liquid fund", "overnight fund", "money market", "corporate bond",
            "dynamic bond", "banking and psu", "banking psu", "credit risk",
            "target maturity", "fixed income", "income fund", "floater fund",
        ))
    ):
        return "Debt"
    if (
        has_exchange_evidence
        or any(term in text for term in (
            "equity", "large cap", "largecap", "mid cap", "midcap", "small cap",
            "smallcap", "flexi cap", "flexicap", "multi cap", "multicap",
            "bluechip", "elss", "index fund", "opportunities", "focused fund",
            "focussed fund", "value fund", "contra fund", "dividend yield",
        ))
        or compact.endswith("bees")
    ):
        return "Equity"
    return "Other"


def resolve_portfolio_amfi_scheme(company_name: str) -> dict[str, object] | None:
    """Resolve a reviewed working-portfolio label to one exact AMFI scheme."""
    normalized = set(re.findall(r"[a-z0-9]+", str(company_name).lower()))
    for scheme in AMFI_PORTFOLIO_SCHEMES:
        if all(term in normalized for term in scheme["required_terms"]):
            return {
                key: value
                for key, value in scheme.items()
                if key != "required_terms"
            }
    return None


def parse_amfi_nav_history_text(
    text: str,
    requested_scheme_codes: set[str],
) -> dict[str, list[dict[str, object]]]:
    """Parse AMFI's semicolon report while tolerating its current column variants."""
    requested = {str(code).strip() for code in requested_scheme_codes if str(code).strip()}
    rows_by_scheme: dict[str, dict[date, dict[str, object]]] = {
        code: {} for code in requested
    }
    for line in text.splitlines():
        fields = [field.strip() for field in line.split(";")]
        if len(fields) < 4 or fields[0] not in requested:
            continue
        nav = _portfolio_number(fields[-2])
        try:
            session_date = datetime.strptime(fields[-1], "%d-%b-%Y").date()
        except ValueError:
            continue
        if nav is None or nav <= 0:
            continue
        rows_by_scheme[fields[0]][session_date] = {
            "date": session_date,
            "close": nav,
        }
    return {
        code: [by_date[key] for key in sorted(by_date)]
        for code, by_date in rows_by_scheme.items()
    }


def fetch_amfi_portfolio_nav_histories(
    schemes: list[dict[str, object]],
    through_date: date,
    *,
    lookback_days: int = AMFI_NAV_LOOKBACK_DAYS,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, str]]:
    """Fetch bounded official NAV history for reviewed portfolio schemes."""
    requested = {
        str(scheme.get("scheme_code") or ""): str(scheme.get("amc_id") or "")
        for scheme in schemes
        if str(scheme.get("scheme_code") or "") and str(scheme.get("amc_id") or "")
    }
    if not requested:
        return {}, {}
    start_date = through_date - timedelta(days=max(180, min(int(lookback_days), 730)))
    cache_key = ":".join((start_date.isoformat(), through_date.isoformat(), *sorted(requested)))
    with _SESSION_LOCK:
        cached = _AMFI_NAV_HISTORY_CACHE.get(cache_key)
        if cached and time.monotonic() - float(cached.get("created_at", 0)) < AMFI_NAV_CACHE_SECONDS:
            histories = cached.get("histories")
            failures = cached.get("failures")
            if isinstance(histories, dict) and isinstance(failures, dict):
                return {
                    str(code): [dict(row) for row in rows if isinstance(row, dict)]
                    for code, rows in histories.items() if isinstance(rows, list)
                }, {str(code): str(reason) for code, reason in failures.items()}

    codes_by_amc: dict[str, set[str]] = defaultdict(set)
    for code, amc_id in requested.items():
        codes_by_amc[amc_id].add(code)

    def fetch_amc(amc_id: str, codes: set[str]) -> tuple[dict[str, list[dict[str, object]]], dict[str, str]]:
        merged: dict[str, dict[date, dict[str, object]]] = {code: {} for code in codes}
        failures: dict[str, str] = {}
        chunk_start = start_date
        while chunk_start <= through_date:
            chunk_end = min(chunk_start + timedelta(days=AMFI_NAV_CHUNK_DAYS - 1), through_date)
            query = urllib.parse.urlencode({
                "mf": amc_id,
                "tp": "1",
                "frmdt": chunk_start.strftime("%d-%b-%Y"),
                "todt": chunk_end.strftime("%d-%b-%Y"),
            })
            request = urllib.request.Request(
                f"{AMFI_NAV_HISTORY_URL}?{query}",
                headers={
                    "Accept": "text/plain,*/*;q=0.8",
                    "Accept-Encoding": "identity",
                    "Referer": AMFI_NAV_SOURCE_URL,
                    "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    final_url = urllib.parse.urlsplit(response.geturl())
                    if response.status != HTTPStatus.OK or (final_url.hostname or "").lower() != "portal.amfiindia.com":
                        raise ValueError("amfi_nav_source_unavailable")
                    body = response.read(MAX_AMFI_NAV_RESPONSE_BYTES + 1)
                    if len(body) > MAX_AMFI_NAV_RESPONSE_BYTES:
                        raise ValueError("amfi_nav_response_too_large")
                text = body.decode("utf-8-sig")
                if "<html" in text[:500].lower():
                    raise ValueError("invalid_amfi_nav_response")
                parsed = parse_amfi_nav_history_text(text, codes)
                for code, rows in parsed.items():
                    for row in rows:
                        merged[code][row["date"]] = row
            except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError, OSError):
                for code in codes:
                    failures[code] = "amfi_nav_source_unavailable"
                break
            except (UnicodeDecodeError, ValueError) as error:
                reason = str(error) or "invalid_amfi_nav_response"
                for code in codes:
                    failures[code] = reason
                break
            chunk_start = chunk_end + timedelta(days=1)
        histories = {
            code: [by_date[key] for key in sorted(by_date)]
            for code, by_date in merged.items()
            if by_date
        }
        for code in codes:
            if code not in histories and code not in failures:
                failures[code] = "amfi_nav_history_unavailable"
        return histories, failures

    histories: dict[str, list[dict[str, object]]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(codes_by_amc))) as executor:
        futures = {
            executor.submit(fetch_amc, amc_id, codes): amc_id
            for amc_id, codes in codes_by_amc.items()
        }
        for future in as_completed(futures):
            try:
                fetched, failed = future.result()
            except Exception:
                fetched = {}
                failed = {
                    code: "amfi_nav_source_unavailable"
                    for code in codes_by_amc[futures[future]]
                }
            histories.update(fetched)
            failures.update(failed)
    with _SESSION_LOCK:
        _AMFI_NAV_HISTORY_CACHE[cache_key] = {
            "created_at": time.monotonic(),
            "histories": {
                code: [dict(row) for row in rows]
                for code, rows in histories.items()
            },
            "failures": dict(failures),
        }
    return histories, failures


def calculate_xirr(cash_flows: list[tuple[date, float]]) -> float | None:
    """Return an annualized money-weighted return percentage for dated cash flows."""
    valid = [
        (flow_date, float(amount))
        for flow_date, amount in cash_flows
        if isinstance(flow_date, date)
        and isinstance(amount, (int, float))
        and not isinstance(amount, bool)
        and math.isfinite(float(amount))
        and float(amount) != 0
    ]
    if (
        len(valid) < 2
        or not any(amount < 0 for _, amount in valid)
        or not any(amount > 0 for _, amount in valid)
    ):
        return None
    valid.sort(key=lambda item: item[0])
    start = valid[0][0]
    if valid[-1][0] <= start:
        return None

    def xnpv(rate: float) -> float:
        base = 1 + rate
        if base <= 0:
            return math.inf
        try:
            return sum(
                amount / (base ** ((flow_date - start).days / 365.0))
                for flow_date, amount in valid
            )
        except (OverflowError, ZeroDivisionError):
            return math.inf

    low = -0.9999
    high = 1.0
    low_value = xnpv(low)
    high_value = xnpv(high)
    while math.isfinite(high_value) and low_value * high_value > 0 and high < 1_000_000:
        high = high * 2 + 1
        high_value = xnpv(high)
    if not math.isfinite(low_value) or not math.isfinite(high_value) or low_value * high_value > 0:
        return None
    for _ in range(200):
        midpoint = (low + high) / 2
        midpoint_value = xnpv(midpoint)
        if not math.isfinite(midpoint_value):
            low = midpoint
            continue
        if abs(midpoint_value) < 1e-7:
            return round(midpoint * 100, 2)
        if low_value * midpoint_value <= 0:
            high = midpoint
            high_value = midpoint_value
        else:
            low = midpoint
            low_value = midpoint_value
    return round(((low + high) / 2) * 100, 2)


def calculate_cashflow_matched_benchmark_return(
    positions: list[dict[str, object]],
    benchmark_history: list[dict[str, object]],
    valuation_date: date,
) -> dict[str, object]:
    """Compare dated portfolio investments with matched NIFTY 50 purchases."""
    history = sorted(
        (
            (row.get("date"), _portfolio_number(row.get("close")))
            for row in benchmark_history
        ),
        key=lambda item: item[0] if isinstance(item[0], date) else date.min,
    )
    history = [
        (session_date, close)
        for session_date, close in history
        if isinstance(session_date, date)
        and session_date <= valuation_date
        and close is not None
        and close > 0
    ]
    if not history:
        return {"return_pct": None, "covered_positions": 0, "required_positions": len(positions), "as_of_date": None}
    latest_date, latest_close = history[-1]
    benchmark_units = 0.0
    invested_total = 0.0
    covered = 0
    for position in positions:
        entry_date = _portfolio_date(position.get("entry_date"))
        invested_value = _portfolio_number(position.get("invested_value"))
        if not isinstance(entry_date, date) or invested_value is None or invested_value <= 0:
            continue
        entry_row = next(
            ((session_date, close) for session_date, close in reversed(history) if session_date <= entry_date),
            None,
        )
        if entry_row is None:
            continue
        benchmark_units += invested_value / float(entry_row[1])
        invested_total += invested_value
        covered += 1
    return_pct = (
        round(((benchmark_units * float(latest_close)) / invested_total - 1) * 100, 2)
        if covered == len(positions) and invested_total > 0
        else None
    )
    return {
        "return_pct": return_pct,
        "covered_positions": covered,
        "required_positions": len(positions),
        "as_of_date": latest_date.isoformat(),
    }


def calculate_portfolio_risk_metrics(
    positions: list[dict[str, object]],
    price_histories: dict[str, list[dict[str, object]]],
    benchmark_history: list[dict[str, object]],
    *,
    risk_free_annual_pct: float = 0.0,
    minimum_sessions: int = 126,
    minimum_weight_coverage_pct: float = 90.0,
) -> dict[str, object]:
    """Calculate transparent risk metrics from a current-holdings daily backtest.

    Uploaded holdings are a point-in-time snapshot, not a transaction ledger. The
    return series therefore keeps today's portfolio weights constant and only
    reports metrics when daily price coverage clears the explicit gate.
    """
    included_positions = [
        position
        for position in positions
        if not bool(position.get("exclude_from_risk"))
        and _portfolio_number(position.get("weight_pct")) is not None
        and float(position["weight_pct"]) > 0
    ]
    excluded_positions = [
        position
        for position in positions
        if bool(position.get("exclude_from_risk"))
        and _portfolio_number(position.get("weight_pct")) is not None
        and float(position["weight_pct"]) > 0
    ]
    included_weight = sum(float(position["weight_pct"]) for position in included_positions)
    required_positions = [
        {
            **position,
            "risk_weight_pct": float(position["weight_pct"]) / included_weight * 100,
        }
        for position in included_positions
    ] if included_weight > 0 else []
    histories_by_symbol: dict[str, dict[date, float]] = {}
    historical_positions = 0
    historical_weight = 0.0
    for position in required_positions:
        symbol = str(position.get("symbol") or "").strip().upper()
        history_key = str(position.get("risk_history_key") or symbol)
        observations = {
            row["date"]: float(row["close"])
            for row in price_histories.get(history_key, [])
            if isinstance(row.get("date"), date)
            and _portfolio_number(row.get("close")) is not None
            and float(row["close"]) > 0
        }
        if len(observations) >= 2:
            histories_by_symbol[history_key] = observations
            historical_positions += 1
            historical_weight += float(position["risk_weight_pct"])

    coverage = {
        "historical_positions": historical_positions,
        "required_positions": len(required_positions),
        "historical_weight_pct": round(historical_weight, 2),
        "minimum_weight_pct": round(float(minimum_weight_coverage_pct), 2),
        "minimum_sessions": int(minimum_sessions),
        "excluded_positions": len(excluded_positions),
        "excluded_weight_pct": round(
            sum(float(position["weight_pct"]) for position in excluded_positions), 2
        ),
    }
    unavailable = {
        "status": "unavailable",
        "method": "current_holdings_constant_weight_backtest",
        "risk_free_annual_pct": round(float(risk_free_annual_pct), 2),
        "coverage": coverage,
        "sessions": 0,
        "start_date": None,
        "end_date": None,
        "annualized_return_pct": None,
        "annualized_volatility_pct": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "beta": None,
        "jensen_alpha_pct": None,
        "maximum_drawdown_pct": None,
        "calmar_ratio": None,
        "tracking_error_pct": None,
        "information_ratio": None,
        "correlation": None,
    }
    if not required_positions or historical_weight < minimum_weight_coverage_pct:
        return {**unavailable, "reason": "historical_weight_coverage_below_threshold"}

    benchmark_by_date = {
        row["date"]: float(row["close"])
        for row in benchmark_history
        if isinstance(row.get("date"), date)
        and _portfolio_number(row.get("close")) is not None
        and float(row["close"]) > 0
    }
    benchmark_dates = sorted(benchmark_by_date)
    portfolio_returns: list[float] = []
    benchmark_returns: list[float] = []
    aligned_dates: list[date] = []
    session_coverages: list[float] = []
    for previous_date, current_date in zip(benchmark_dates, benchmark_dates[1:]):
        weighted_return = 0.0
        covered_weight = 0.0
        for position in required_positions:
            symbol = str(position.get("symbol") or "").strip().upper()
            history_key = str(position.get("risk_history_key") or symbol)
            history = histories_by_symbol.get(history_key)
            if history is None or previous_date not in history or current_date not in history:
                continue
            weight = float(position["risk_weight_pct"])
            weighted_return += weight * (history[current_date] / history[previous_date] - 1)
            covered_weight += weight
        if covered_weight + 1e-9 < minimum_weight_coverage_pct:
            continue
        portfolio_returns.append(weighted_return / covered_weight)
        benchmark_returns.append(
            benchmark_by_date[current_date] / benchmark_by_date[previous_date] - 1
        )
        aligned_dates.append(current_date)
        session_coverages.append(covered_weight)

    coverage["aligned_sessions"] = len(portfolio_returns)
    coverage["minimum_daily_weight_pct"] = (
        round(min(session_coverages), 2) if session_coverages else None
    )
    if len(portfolio_returns) < minimum_sessions:
        return {
            **unavailable,
            "reason": "insufficient_aligned_history",
            "coverage": coverage,
            "sessions": len(portfolio_returns),
            "start_date": aligned_dates[0].isoformat() if aligned_dates else None,
            "end_date": aligned_dates[-1].isoformat() if aligned_dates else None,
        }

    count = len(portfolio_returns)
    portfolio_mean = sum(portfolio_returns) / count
    benchmark_mean = sum(benchmark_returns) / count
    portfolio_variance = sum(
        (value - portfolio_mean) ** 2 for value in portfolio_returns
    ) / (count - 1)
    benchmark_variance = sum(
        (value - benchmark_mean) ** 2 for value in benchmark_returns
    ) / (count - 1)
    covariance = sum(
        (portfolio_value - portfolio_mean) * (benchmark_value - benchmark_mean)
        for portfolio_value, benchmark_value in zip(portfolio_returns, benchmark_returns)
    ) / (count - 1)
    portfolio_deviation = math.sqrt(portfolio_variance)
    benchmark_deviation = math.sqrt(benchmark_variance)
    risk_free_daily = (1 + float(risk_free_annual_pct) / 100) ** (1 / 252) - 1
    mean_excess = portfolio_mean - risk_free_daily
    downside_deviation = math.sqrt(
        sum(min(value - risk_free_daily, 0.0) ** 2 for value in portfolio_returns) / count
    )
    beta = covariance / benchmark_variance if benchmark_variance > 0 else None
    alpha = (
        (mean_excess - beta * (benchmark_mean - risk_free_daily)) * 252
        if beta is not None else None
    )
    growth = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for daily_return in portfolio_returns:
        growth *= 1 + daily_return
        peak = max(peak, growth)
        maximum_drawdown = min(maximum_drawdown, growth / peak - 1)
    annualized_return = growth ** (252 / count) - 1 if growth > 0 else None
    active_returns = [
        portfolio_value - benchmark_value
        for portfolio_value, benchmark_value in zip(portfolio_returns, benchmark_returns)
    ]
    active_mean = sum(active_returns) / count
    active_variance = sum((value - active_mean) ** 2 for value in active_returns) / (count - 1)
    active_deviation = math.sqrt(active_variance)

    return {
        "status": "available",
        "reason": None,
        "method": "current_holdings_constant_weight_backtest",
        "risk_free_annual_pct": round(float(risk_free_annual_pct), 2),
        "coverage": coverage,
        "sessions": count,
        "start_date": aligned_dates[0].isoformat(),
        "end_date": aligned_dates[-1].isoformat(),
        "annualized_return_pct": round(annualized_return * 100, 2) if annualized_return is not None else None,
        "annualized_volatility_pct": round(portfolio_deviation * math.sqrt(252) * 100, 2),
        "sharpe_ratio": round(mean_excess / portfolio_deviation * math.sqrt(252), 2) if portfolio_deviation > 0 else None,
        "sortino_ratio": round(mean_excess / downside_deviation * math.sqrt(252), 2) if downside_deviation > 0 else None,
        "beta": round(beta, 2) if beta is not None else None,
        "jensen_alpha_pct": round(alpha * 100, 2) if alpha is not None else None,
        "maximum_drawdown_pct": round(maximum_drawdown * 100, 2),
        "calmar_ratio": round(annualized_return / abs(maximum_drawdown), 2) if annualized_return is not None and maximum_drawdown < 0 else None,
        "tracking_error_pct": round(active_deviation * math.sqrt(252) * 100, 2),
        "information_ratio": round(active_mean / active_deviation * math.sqrt(252), 2) if active_deviation > 0 else None,
        "correlation": round(covariance / (portfolio_deviation * benchmark_deviation), 2) if portfolio_deviation > 0 and benchmark_deviation > 0 else None,
    }


def parse_google_finance_quote_html(
    html_text: str,
    expected_symbol: str,
) -> dict[str, object]:
    """Extract one NSE quote from the bounded Google Finance page payload."""
    symbol = expected_symbol.strip().upper()
    if not symbol or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol):
        raise ValueError("invalid_google_finance_symbol")
    script_match = re.search(
        r'<script[^>]*class="ds:(?:13|2)"[^>]*>(.*?)</script>',
        html_text,
        re.DOTALL,
    )
    if script_match is None:
        raise ValueError("invalid_google_finance_response")
    data_match = re.search(
        r"\bdata:(.*),\s*sideChannel:",
        script_match.group(1),
        re.DOTALL,
    )
    if data_match is None:
        raise ValueError("invalid_google_finance_response")
    try:
        data = json.loads(data_match.group(1))
        quote = data[0][0][0]
        quote_symbol, exchange = quote[1]
        latest_price = float(quote[5][0])
        last_close = float(quote[7])
        observed_timestamp = int(quote[11][0])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid_google_finance_response") from error
    if (
        str(quote_symbol).upper() != symbol
        or str(exchange).upper() != "NSE"
        or not math.isfinite(latest_price)
        or not math.isfinite(last_close)
        or latest_price <= 0
        or last_close <= 0
        or observed_timestamp <= 0
    ):
        raise ValueError("invalid_google_finance_response")
    return {
        "symbol": symbol,
        "exchange": "NSE",
        "company_name": str(quote[2] or symbol),
        "currency": str(quote[4] or "INR"),
        "last_close": round(last_close, 2),
        "latest_price": round(latest_price, 2),
        "observed_at": datetime.fromtimestamp(observed_timestamp, timezone.utc).isoformat(),
        "source": "Google Finance",
        "source_url": GOOGLE_FINANCE_QUOTE_URL.format(
            symbol=urllib.parse.quote(symbol, safe="&-")
        ),
    }


def fetch_google_finance_quote(symbol: str) -> tuple[dict[str, object] | None, str | None]:
    """Load a public Google Finance quote with strict host and size checks."""
    normalized = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9&-]{1,32}", normalized):
        return None, "unsupported_google_finance_symbol"
    now = time.monotonic()
    with _SESSION_LOCK:
        cached = _GOOGLE_FINANCE_QUOTE_CACHE.get(normalized)
        if cached and now - float(cached.get("created_at", 0)) < GOOGLE_FINANCE_CACHE_SECONDS:
            payload = cached.get("payload")
            if isinstance(payload, dict):
                return dict(payload), None
    url = GOOGLE_FINANCE_QUOTE_URL.format(
        symbol=urllib.parse.quote(normalized, safe="&-")
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final_url = urllib.parse.urlsplit(response.geturl())
            if (
                response.status != HTTPStatus.OK
                or (final_url.hostname or "").lower() != "www.google.com"
                or not final_url.path.startswith("/finance/quote/")
            ):
                return None, "google_finance_unavailable"
            body = response.read(MAX_GOOGLE_FINANCE_RESPONSE_BYTES + 1)
            if len(body) > MAX_GOOGLE_FINANCE_RESPONSE_BYTES:
                return None, "google_finance_response_too_large"
            quote = parse_google_finance_quote_html(body.decode("utf-8"), normalized)
    except urllib.error.HTTPError:
        return None, "google_finance_unavailable"
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return None, "google_finance_unavailable"
    except (UnicodeDecodeError, ValueError) as error:
        return None, str(error)
    with _SESSION_LOCK:
        _GOOGLE_FINANCE_QUOTE_CACHE[normalized] = {
            "created_at": time.monotonic(),
            "payload": dict(quote),
        }
    return quote, None


def fetch_google_finance_quotes(
    symbols: set[str],
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """Fetch a bounded quote set concurrently so uploads remain responsive."""
    requested = sorted(
        symbol.strip().upper()
        for symbol in symbols
        if re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol.strip().upper())
    )[:MAX_GOOGLE_FINANCE_SYMBOLS]
    quotes: dict[str, dict[str, object]] = {}
    failures: dict[str, str] = {}
    if not requested:
        return quotes, failures
    worker_count = min(6, len(requested))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(fetch_google_finance_quote, symbol): symbol
            for symbol in requested
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                quote, reason = future.result()
            except Exception:
                quote, reason = None, "google_finance_unavailable"
            if quote is not None:
                quotes[symbol] = quote
            else:
                failures[symbol] = reason or "google_finance_unavailable"
    return quotes, failures


def fetch_nifty_gsec_total_return_history(
    through_date: date,
    *,
    years: int = 5,
) -> tuple[list[dict[str, object]], str | None]:
    """Fetch fixed annual windows of the official 10-year G-Sec total-return index."""
    if years < 1 or years > 10:
        raise ValueError("invalid_gsec_history_window")
    cache_key = f"{through_date.isoformat()}:{years}"
    now = time.monotonic()
    with _SESSION_LOCK:
        cached = _NIFTY_GSEC_HISTORY_CACHE.get(cache_key)
        if cached and now - float(cached.get("created_at", 0)) < NIFTY_GSEC_CACHE_SECONDS:
            rows = cached.get("rows")
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)], None

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    common_headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
    }
    try:
        session_request = urllib.request.Request(
            NIFTY_GSEC_HISTORY_PAGE_URL,
            headers={**common_headers, "Accept": "text/html,application/xhtml+xml"},
            method="GET",
        )
        with opener.open(session_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != HTTPStatus.OK:
                return [], "nifty_gsec_source_unavailable"
            response.read(1)
        rows_by_date: dict[date, dict[str, object]] = {}
        first_year = through_date.year - years + 1
        for year in range(first_year, through_date.year + 1):
            start_date = date(year, 1, 1)
            end_date = min(date(year, 12, 31), through_date)
            request_body = json.dumps({
                "cinfo": json.dumps({
                    "name": "NIFTY GS 10YR",
                    "startDate": start_date.strftime("%m/%d/%Y"),
                    "endDate": end_date.strftime("%m/%d/%Y"),
                    "indexName": "NIFTY 10 YR BENCHMARK G-SEC",
                }, separators=(",", ":")),
            }).encode("utf-8")
            request = urllib.request.Request(
                NIFTY_GSEC_HISTORY_URL,
                data=request_body,
                headers={
                    **common_headers,
                    "Content-Type": "application/json; charset=utf-8",
                    "Origin": "https://www.niftyindices.com",
                    "Referer": NIFTY_GSEC_HISTORY_PAGE_URL,
                },
                method="POST",
            )
            with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                final_url = urllib.parse.urlsplit(response.geturl())
                if response.status != HTTPStatus.OK or (final_url.hostname or "").lower() != "www.niftyindices.com":
                    return [], "nifty_gsec_source_unavailable"
                body = response.read(MAX_NIFTY_GSEC_RESPONSE_BYTES + 1)
                if len(body) > MAX_NIFTY_GSEC_RESPONSE_BYTES:
                    return [], "nifty_gsec_response_too_large"
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, list):
                return [], "invalid_nifty_gsec_response"
            for item in payload:
                if not isinstance(item, dict) or str(item.get("INDEX_NAME") or "").strip().lower() != NIFTY_GSEC_INDEX_NAME.lower():
                    continue
                session_date = datetime.strptime(str(item.get("HistoricalDate") or ""), "%d %b %Y").date()
                values = {
                    key: _portfolio_number(item.get(source_key))
                    for key, source_key in (("open", "OPEN"), ("high", "HIGH"), ("low", "LOW"), ("close", "CLOSE"))
                }
                if any(value is None or value <= 0 for value in values.values()):
                    continue
                rows_by_date[session_date] = {"date": session_date, **values}
        rows = [rows_by_date[key] for key in sorted(rows_by_date)]
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return [], "nifty_gsec_source_unavailable"
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return [], "invalid_nifty_gsec_response"
    if not rows:
        return [], "nifty_gsec_history_unavailable"
    with _SESSION_LOCK:
        _NIFTY_GSEC_HISTORY_CACHE.clear()
        _NIFTY_GSEC_HISTORY_CACHE[cache_key] = {"created_at": now, "rows": [dict(row) for row in rows]}
    return rows, None


def build_portfolio_analysis(
    rows: list[dict[str, object]],
    mapping: dict[str, object],
    price_histories: dict[str, list[dict[str, object]]],
    *,
    constituents: list[dict[str, str]] | None = None,
    fno_symbols: set[str] | None = None,
    market_quotes: dict[str, dict[str, object]] | None = None,
    benchmark_history: list[dict[str, object]] | None = None,
    gsec_benchmark_history: list[dict[str, object]] | None = None,
    position_history_overrides: dict[int, dict[str, object]] | None = None,
    valuation_date: date | None = None,
    refresh_prices: bool = False,
) -> dict[str, object]:
    """Validate and summarize an uploaded portfolio without persisting holdings."""
    if not rows or len(rows) > MAX_PORTFOLIO_ROWS or not isinstance(mapping, dict):
        raise ValueError("invalid_portfolio_rows")
    headers = {str(key) for row in rows if isinstance(row, dict) for key in row}
    symbol_column = mapping.get("symbol")
    quantity_column = mapping.get("quantity")
    weight_column = mapping.get("weight")
    if not isinstance(symbol_column, str) or symbol_column not in headers:
        raise ValueError("portfolio_symbol_mapping_required")
    if not any(
        isinstance(column, str) and column in headers
        for column in (quantity_column, weight_column, mapping.get("current_value"))
    ):
        raise ValueError("portfolio_quantity_weight_or_value_required")
    for key in (
        "quantity", "weight", "average_cost", "current_value", "latest_price",
        "entry_date", "invested_value", "sector", "name",
    ):
        column = mapping.get(key)
        if column not in (None, "") and (not isinstance(column, str) or column not in headers):
            raise ValueError("invalid_portfolio_mapping")
    uses_uploaded_weight = isinstance(weight_column, str) and weight_column in headers
    uses_uploaded_current_value = not uses_uploaded_weight and bool(mapping.get("current_value"))

    constituent_lookup = {
        item["symbol"].upper(): item for item in (constituents or []) if item.get("symbol")
    }
    fno_symbols = {symbol.upper() for symbol in (fno_symbols or set())}
    market_quotes = {
        str(symbol).upper(): quote
        for symbol, quote in (market_quotes or {}).items()
        if isinstance(quote, dict)
    }
    position_history_overrides = {
        int(row_number): override
        for row_number, override in (position_history_overrides or {}).items()
        if isinstance(row_number, int) and isinstance(override, dict)
    }
    symbols: list[str] = []
    duplicate_keys: list[str] = []
    name_column = mapping.get("name")
    for row in rows:
        raw_symbol = str(row.get(symbol_column, "")).strip().upper()
        symbol = re.sub(r"^(NSE:|BSE:)", "", raw_symbol)
        symbol = re.sub(r"-(EQ|BE|RR)$", "", symbol)
        symbols.append(symbol)
        uploaded_name = str(row.get(str(name_column), "")).strip().upper() if name_column else ""
        duplicate_keys.append(f"{symbol}|{uploaded_name}" if uploaded_name else symbol)
    counts: dict[str, int] = defaultdict(int)
    for duplicate_key in duplicate_keys:
        if duplicate_key:
            counts[duplicate_key] += 1

    prepared: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    for index, (row, symbol, duplicate_key) in enumerate(zip(rows, symbols, duplicate_keys), start=2):
        reasons: list[str] = []
        symbol_pattern = r"[A-Z0-9& ._/-]{1,64}" if (uses_uploaded_weight or uses_uploaded_current_value) else r"[A-Z0-9&-]{1,32}"
        if not re.fullmatch(symbol_pattern, symbol):
            reasons.append("invalid_symbol")
        if symbol and counts[duplicate_key] > 1:
            reasons.append("duplicate_symbol")
        quantity = _portfolio_number(row.get(str(quantity_column))) if isinstance(quantity_column, str) else None
        uploaded_weight = _portfolio_number(row.get(str(weight_column))) if isinstance(weight_column, str) else None
        average_cost = _portfolio_number(row.get(str(mapping.get("average_cost")))) if mapping.get("average_cost") else None
        current_value = _portfolio_number(row.get(str(mapping.get("current_value")))) if mapping.get("current_value") else None
        uploaded_price = _portfolio_number(row.get(str(mapping.get("latest_price")))) if mapping.get("latest_price") else None
        raw_entry_date = row.get(str(mapping.get("entry_date"))) if mapping.get("entry_date") else None
        entry_date = _portfolio_date(raw_entry_date)
        explicit_invested_value = _portfolio_number(row.get(str(mapping.get("invested_value")))) if mapping.get("invested_value") else None
        invested_value = (
            explicit_invested_value
            if explicit_invested_value is not None and explicit_invested_value > 0
            else (
                float(quantity) * float(average_cost)
                if quantity is not None and quantity > 0 and average_cost is not None and average_cost > 0
                else None
            )
        )
        if not uses_uploaded_weight and not uses_uploaded_current_value and (quantity is None or quantity <= 0):
            reasons.append("invalid_quantity")
        if uses_uploaded_weight and (uploaded_weight is None or uploaded_weight < 0):
            reasons.append("invalid_weight")
        if average_cost is not None and average_cost < 0:
            issues.append({"row_number": index, "symbol": symbol or "—", "reason": "invalid_average_cost"})
            average_cost = None
        if uses_uploaded_current_value and (current_value is None or current_value <= 0):
            reasons.append("invalid_current_value")
        if raw_entry_date not in (None, "") and entry_date is None:
            issues.append({"row_number": index, "symbol": symbol or "—", "reason": "invalid_entry_date"})
        history = price_histories.get(symbol, [])
        local_latest = history[-1] if history else None
        local_price = float(local_latest["close"]) if local_latest else None
        local_price_date = (
            local_latest["date"].isoformat()
            if local_latest and isinstance(local_latest.get("date"), date)
            else None
        )
        market_quote = market_quotes.get(symbol, {})
        google_latest = _portfolio_number(market_quote.get("latest_price"))
        google_last_close = _portfolio_number(market_quote.get("last_close"))
        history_override = position_history_overrides.get(index, {})
        override_history = history_override.get("history")
        override_latest = (
            override_history[-1]
            if isinstance(override_history, list) and override_history
            else None
        )
        override_price = (
            _portfolio_number(override_latest.get("close"))
            if isinstance(override_latest, dict)
            else None
        )
        override_date_value = override_latest.get("date") if isinstance(override_latest, dict) else None
        override_price_date = (
            override_date_value.isoformat()
            if isinstance(override_date_value, date)
            else str(override_date_value or "") or None
        )
        if refresh_prices:
            price = google_latest if google_latest is not None and google_latest > 0 else (
                override_price if override_price is not None and override_price > 0 else (
                    local_price if local_price is not None and local_price > 0 else uploaded_price
                )
            )
        else:
            price = google_latest if google_latest is not None and google_latest > 0 else (
                uploaded_price if uploaded_price is not None and uploaded_price > 0 else local_price
            )
        last_close = (
            google_last_close
            if google_last_close is not None and google_last_close > 0
            else (
                override_price
                if refresh_prices and override_price is not None and override_price > 0
                else local_price
            )
        )
        observed_at = str(market_quote.get("observed_at") or "") or None
        if google_latest is not None and google_latest > 0:
            price_source = "google_finance"
            price_date = observed_at[:10] if observed_at else local_price_date
        elif refresh_prices and override_price is not None and override_price > 0:
            price_source = "amfi_nav"
            price_date = override_price_date
        elif refresh_prices and local_price is not None and local_price > 0:
            price_source = "local_eod"
            price_date = local_price_date
        elif uploaded_price is not None and uploaded_price > 0:
            price_source = "uploaded_price_fallback"
            price_date = None
        elif local_price is not None and local_price > 0:
            price_source = "local_eod_fallback"
            price_date = local_price_date
        else:
            price_source = "unavailable"
            price_date = None
        last_close_date = (
            override_price_date
            if refresh_prices and google_last_close is None and override_price is not None
            else local_price_date
        )
        metadata = constituent_lookup.get(symbol, {})
        uploaded_sector = str(row.get(str(mapping.get("sector")), "")).strip() if mapping.get("sector") else ""
        uploaded_name = str(row.get(str(mapping.get("name")), "")).strip() if mapping.get("name") else ""
        company_name = uploaded_name or metadata.get("name") or symbol or "—"
        uploaded_traded_security = bool(
            uploaded_price is not None
            and uploaded_price > 0
            and symbol not in {"MF", "NCD", "FD", "CASH"}
            and re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
        )
        asset_class = classify_portfolio_asset_class(
            symbol,
            str(company_name),
            has_exchange_evidence=bool(metadata or history or market_quote or uploaded_traded_security),
        )
        risk_label = re.sub(r"[^a-z0-9]+", " ", f"{symbol} {company_name}".lower())
        exclude_from_risk = bool(
            re.search(r"\bncd\b|\bdebenture\b|\bfixed deposit\b", risk_label)
        )
        risk_history_key = (
            f"portfolio-row-{index}"
            if isinstance(override_history, list) and override_history
            else symbol
        )
        prepared.append({
            "row_number": index,
            "symbol": symbol,
            "company_name": company_name,
            "asset_class": asset_class,
            "sector": uploaded_sector or metadata.get("sector") or "Unclassified",
            "quantity": quantity,
            "uploaded_weight": uploaded_weight,
            "average_cost": average_cost,
            "provided_current_value": current_value,
            "uploaded_price": uploaded_price,
            "entry_date": entry_date.isoformat() if entry_date else None,
            "invested_value": round(invested_value, 2) if invested_value is not None else None,
            "last_close": last_close,
            "last_close_date": last_close_date,
            "latest_price": price,
            "price_date": price_date,
            "price_observed_at": observed_at,
            "price_source": price_source,
            "price_source_url": market_quote.get("source_url"),
            "in_nifty500": symbol in constituent_lookup,
            "in_local_fno_universe": symbol in fno_symbols,
            "risk_history_key": risk_history_key,
            "risk_history_source": history_override.get("source"),
            "risk_history_scheme_code": history_override.get("scheme_code"),
            "exclude_from_risk": exclude_from_risk,
            "reasons": reasons,
        })
        for reason in reasons:
            issues.append({"row_number": index, "symbol": symbol or "—", "reason": reason})

    if uses_uploaded_weight:
        basis = "uploaded_weight"
        valid_weights = [float(item["uploaded_weight"]) for item in prepared if not item["reasons"] and item["uploaded_weight"] is not None]
        fractional = bool(valid_weights and max(valid_weights) <= 1 and sum(valid_weights) <= 1.5)
        for item in prepared:
            item["basis_value"] = (
                float(item["uploaded_weight"]) * (100 if fractional else 1)
                if not item["reasons"] and item["uploaded_weight"] is not None else None
            )
    elif mapping.get("current_value"):
        basis = "refreshed_price_with_uploaded_value_fallback" if refresh_prices else "uploaded_current_value"
        for item in prepared:
            has_refreshed_price = item.get("price_source") in {"google_finance", "amfi_nav", "local_eod"}
            item["basis_value"] = (
                float(item["quantity"]) * float(item["latest_price"])
                if (
                    refresh_prices
                    and not item["reasons"]
                    and has_refreshed_price
                    and item.get("quantity") is not None
                    and float(item["quantity"]) > 0
                    and item.get("latest_price") is not None
                )
                else (item["provided_current_value"] if not item["reasons"] else None)
            )
    else:
        basis = "quantity_times_latest_close"
        for item in prepared:
            if not item["reasons"] and item["quantity"] is not None and item["latest_price"] is not None:
                item["basis_value"] = float(item["quantity"]) * float(item["latest_price"])
            else:
                item["basis_value"] = None
                if not item["reasons"] and item["latest_price"] is None:
                    item["reasons"].append("price_unavailable")
                    issues.append({"row_number": item["row_number"], "symbol": item["symbol"] or "—", "reason": "price_unavailable"})

    basis_total = sum(float(item["basis_value"]) for item in prepared if item.get("basis_value") is not None and float(item["basis_value"]) > 0)
    positions: list[dict[str, object]] = []
    for item in prepared:
        basis_value = item.get("basis_value")
        weight = round(float(basis_value) / basis_total * 100, 2) if basis_total > 0 and basis_value is not None and float(basis_value) > 0 else None
        latest_price = item.get("latest_price")
        average_cost = item.get("average_cost")
        if latest_price is not None and average_cost is not None and float(average_cost) > 0:
            return_pct = round((float(latest_price) / float(average_cost) - 1) * 100, 2)
        elif (
            basis == "uploaded_current_value"
            and basis_value is not None
            and item.get("quantity") is not None
            and float(item["quantity"]) > 0
            and average_cost is not None
            and float(average_cost) > 0
        ):
            return_pct = round(
                (float(basis_value) / (float(item["quantity"]) * float(average_cost)) - 1) * 100,
                2,
            )
        else:
            return_pct = None
        status = "ready" if weight is not None else (str(item["reasons"][0]) if item["reasons"] else "excluded")
        positions.append({
            **{key: item[key] for key in (
                "row_number", "symbol", "company_name", "sector", "quantity", "average_cost",
                "last_close", "last_close_date", "latest_price", "price_date", "price_observed_at", "price_source",
                "price_source_url", "entry_date", "invested_value", "asset_class", "in_nifty500",
                "in_local_fno_universe", "risk_history_key", "risk_history_source",
                "risk_history_scheme_code", "exclude_from_risk"
            )},
            "current_value": (
                round(float(basis_value), 2)
                if basis_value is not None and basis != "uploaded_weight"
                else (
                    round(float(item["provided_current_value"]), 2)
                    if item.get("provided_current_value") is not None
                    else None
                )
            ),
            "weight_pct": weight,
            "return_since_average_cost_pct": return_pct,
            "status": status,
        })
    positions.sort(key=lambda item: (item["weight_pct"] is None, -float(item["weight_pct"] or 0), str(item["symbol"])))
    eligible = [item for item in positions if item["weight_pct"] is not None]
    asset_class_order = ("Equity", "Debt", "Commodity", "Hybrid", "Cash", "Other")
    asset_totals: dict[str, dict[str, float | int]] = {
        asset_class: {"weight_pct": 0.0, "current_value": 0.0, "positions": 0, "valued_positions": 0}
        for asset_class in asset_class_order
    }
    for item in eligible:
        asset_class = str(item.get("asset_class") or "Other")
        if asset_class not in asset_totals:
            asset_class = "Other"
        total = asset_totals[asset_class]
        total["weight_pct"] = float(total["weight_pct"]) + float(item["weight_pct"] or 0)
        total["positions"] = int(total["positions"]) + 1
        current_value = _portfolio_number(item.get("current_value"))
        if current_value is not None:
            total["current_value"] = float(total["current_value"]) + current_value
            total["valued_positions"] = int(total["valued_positions"]) + 1
    asset_allocation = [
        {
            "asset_class": asset_class,
            "weight_pct": round(float(asset_totals[asset_class]["weight_pct"]), 2),
            "current_value": (
                round(float(asset_totals[asset_class]["current_value"]), 2)
                if int(asset_totals[asset_class]["valued_positions"]) == int(asset_totals[asset_class]["positions"])
                else None
            ),
            "position_count": int(asset_totals[asset_class]["positions"]),
        }
        for asset_class in asset_class_order
        if int(asset_totals[asset_class]["positions"]) > 0
    ]
    sector_weights: dict[str, float] = defaultdict(float)
    for item in eligible:
        sector_weights[str(item["sector"])] += float(item["weight_pct"])
    sectors = [
        {"sector": sector, "weight_pct": round(weight, 2), "position_count": sum(item["sector"] == sector for item in eligible)}
        for sector, weight in sector_weights.items()
    ]
    sectors.sort(key=lambda item: (-float(item["weight_pct"]), str(item["sector"])))
    weights = sorted((float(item["weight_pct"]) for item in eligible), reverse=True)
    top_one = round(weights[0], 2) if weights else None
    top_five = round(sum(weights[:5]), 2) if weights else None
    hhi = round(sum(weight * weight for weight in weights), 2) if weights else None
    if top_one is None:
        concentration = "not_available"
    elif top_one > 25 or (top_five or 0) > 70:
        concentration = "high_concentration"
    elif top_one > 15 or (top_five or 0) > 50:
        concentration = "moderate_concentration"
    else:
        concentration = "broadly_distributed"
    price_dates = [str(item["price_date"]) for item in eligible if item.get("price_date")]
    resolved_valuation_date = valuation_date
    if resolved_valuation_date is None:
        parsed_price_dates = [_portfolio_date(value) for value in price_dates]
        resolved_valuation_date = max(
            (value for value in parsed_price_dates if value is not None),
            default=datetime.now(INDIA_TIMEZONE).date(),
        )
    metric_ready = [
        item for item in eligible
        if _portfolio_number(item.get("invested_value")) is not None
        and float(item["invested_value"]) > 0
        and _portfolio_number(item.get("current_value")) is not None
        and float(item["current_value"]) >= 0
    ]
    total_invested = (
        round(sum(float(item["invested_value"]) for item in metric_ready), 2)
        if metric_ready and len(metric_ready) == len(eligible)
        else None
    )
    total_current_value = (
        round(sum(float(item["current_value"]) for item in metric_ready), 2)
        if total_invested is not None
        else None
    )
    current_return = (
        round(float(total_current_value) - float(total_invested), 2)
        if total_invested is not None and total_current_value is not None
        else None
    )
    net_return_pct = (
        round(float(current_return) / float(total_invested) * 100, 2)
        if current_return is not None and total_invested and total_invested > 0
        else None
    )
    dated_ready = [
        item for item in metric_ready
        if _portfolio_date(item.get("entry_date")) is not None
        and _portfolio_date(item.get("entry_date")) < resolved_valuation_date
    ]
    xirr_flows = [
        (_portfolio_date(item["entry_date"]), -float(item["invested_value"]))
        for item in dated_ready
    ]
    if dated_ready and len(dated_ready) == len(eligible) and total_current_value is not None:
        xirr_flows.append((resolved_valuation_date, float(total_current_value)))
        portfolio_xirr_pct = calculate_xirr(xirr_flows)
    else:
        portfolio_xirr_pct = None
    benchmark = calculate_cashflow_matched_benchmark_return(
        dated_ready,
        benchmark_history or [],
        resolved_valuation_date,
    )
    if len(dated_ready) != len(eligible):
        benchmark["return_pct"] = None
    gsec_benchmark = calculate_cashflow_matched_benchmark_return(
        dated_ready,
        gsec_benchmark_history or [],
        resolved_valuation_date,
    )
    if len(dated_ready) != len(eligible):
        gsec_benchmark["return_pct"] = None
    risk_price_histories = dict(price_histories)
    for row_number, override in position_history_overrides.items():
        override_history = override.get("history")
        if isinstance(override_history, list) and override_history:
            risk_price_histories[f"portfolio-row-{row_number}"] = override_history
    risk_metrics = calculate_portfolio_risk_metrics(
        eligible,
        risk_price_histories,
        benchmark_history or [],
    )
    return {
        "ok": True,
        "status": "portfolio_ready" if eligible else "portfolio_not_ready",
        "contract_version": "portfolio-analysis-v1",
        "as_of_date": max(price_dates, default=None),
        "weight_basis": basis,
        "persistence": "request_memory_only",
        "coverage": {
            "input_rows": len(rows),
            "unique_symbols": len({symbol for symbol in symbols if symbol}),
            "eligible_positions": len(eligible),
            "excluded_rows": len(positions) - len(eligible),
            "priced_positions": sum(item["latest_price"] is not None for item in positions),
            "google_finance_priced": sum(item["price_source"] == "google_finance" for item in positions),
            "amfi_nav_priced": sum(item["price_source"] == "amfi_nav" for item in positions),
            "local_eod_priced": sum(item["price_source"] == "local_eod" for item in positions),
            "uploaded_price_fallback": sum(item["price_source"] == "uploaded_price_fallback" for item in positions),
            "local_eod_fallback": sum(item["price_source"] == "local_eod_fallback" for item in positions),
            "sector_classified": sum(item["sector"] != "Unclassified" for item in eligible),
            "nifty500_overlap": sum(bool(item["in_nifty500"]) for item in eligible),
            "local_fno_overlap": sum(bool(item["in_local_fno_universe"]) for item in eligible),
            "amfi_history_positions": sum(item.get("risk_history_source") == "AMFI" for item in eligible),
            "risk_excluded_positions": sum(bool(item.get("exclude_from_risk")) for item in eligible),
        },
        "concentration": {
            "state": concentration,
            "largest_position_pct": top_one,
            "top_five_pct": top_five,
            "hhi": hhi,
        },
        "portfolio_summary": {
            "total_invested": total_invested,
            "current_value": total_current_value,
            "current_return": current_return,
            "net_return_pct": net_return_pct,
            "portfolio_xirr_pct": portfolio_xirr_pct,
            "valuation_date": resolved_valuation_date.isoformat(),
            "valued_positions": len(metric_ready),
            "dated_positions": len(dated_ready),
            "required_positions": len(eligible),
        },
        "benchmark": {
            "name": "NIFTY 50",
            **benchmark,
        },
        "gsec_benchmark": {
            "name": NIFTY_GSEC_INDEX_NAME,
            "source_url": NIFTY_GSEC_SOURCE_URL,
            **gsec_benchmark,
        },
        "risk_metrics": risk_metrics,
        "asset_allocation": asset_allocation,
        "positions": positions,
        "sectors": sectors,
        "issues": issues,
        "limitations": [
            "The uploaded file and mapped holdings are processed by the local server for this request and are not written to the database.",
            "Weights are normalized across eligible rows; cash and assets without a mapped row are not inferred.",
            "Last close uses the approved price source available for that instrument and can be delayed or unavailable.",
            (
                "An EOD-triggered revaluation prefers user-enabled Google Finance, reviewed AMFI NAV, and newly stored local EOD prices; uploaded values remain explicit fallbacks."
                if refresh_prices
                else "Current-value and return calculations use user-enabled Google Finance first, with uploaded LTP/NAV and then local completed EOD data as fallbacks."
            ),
            "Asset classes are inferred from instrument names and exchange-price evidence; uncertain holdings remain in Other and are not silently guessed.",
            "Risk ratios use a current-holdings, constant-weight historical backtest rather than the investor's actual transaction history; they require at least 126 aligned sessions and 90% daily portfolio-weight coverage.",
            "Reviewed Direct-Growth mutual-fund mappings use official AMFI NAV history; unmatched funds remain unavailable rather than being assigned a similar scheme.",
            "NCDs, debentures, and fixed deposits without a daily mark-to-market history are excluded from the risk-ratio universe and their uploaded weight is disclosed.",
            "Sharpe, Sortino, and Jensen alpha currently use an explicit 0% annual risk-free assumption; no short-term risk-free rate is silently inferred.",
            "Volatility contribution, scenario analysis, sentiment alignment, and recommendations are not included in this slice.",
        ],
    }


def build_macro_events_calendar(
    *,
    today: date,
    events: tuple[dict[str, object], ...] = MACRO_EVENTS,
    sources: tuple[dict[str, object], ...] = MACRO_EVENT_SOURCES,
) -> dict[str, object]:
    """Build a frozen, source-linked calendar without scraping live news feeds."""
    source_lookup = {str(source["key"]): source for source in sources}
    rows: list[dict[str, object]] = []
    for event in events:
        start_text = str(event.get("start_at") or "")
        try:
            start_date = date.fromisoformat(start_text[:10])
            end_date = date.fromisoformat(str(event.get("end_at") or start_text)[:10])
        except ValueError as error:
            raise ValueError("invalid_macro_event_calendar") from error
        if end_date < start_date:
            raise ValueError("invalid_macro_event_calendar")
        if end_date < today:
            continue
        source_key = str(event.get("source_key") or "")
        source = source_lookup.get(source_key)
        if source is None or source.get("status") != "verified_snapshot":
            raise ValueError("invalid_macro_event_calendar")

        def india_time(value: object) -> str | None:
            if not isinstance(value, str) or "T" not in value:
                return None
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError("invalid_macro_event_calendar")
            return parsed.astimezone(INDIA_TIMEZONE).isoformat(timespec="minutes")

        rows.append(
            {
                "key": str(event["key"]),
                "title": str(event["title"]),
                "region": str(event["region"]),
                "category": str(event["category"]),
                "start_at": start_text,
                "end_at": event.get("end_at"),
                "decision_at": event.get("decision_at"),
                "india_time": india_time(event.get("decision_at") or start_text),
                "timezone": str(event["timezone"]),
                "days_until": max(0, (start_date - today).days),
                "ongoing": start_date < today <= end_date,
                "source_key": source_key,
                "source_label": source["label"],
                "source_url": source["url"],
                "source_status": source["status"],
                "note": event.get("note"),
            }
        )
    rows.sort(key=lambda row: (str(row["start_at"]), str(row["title"])))
    verified_sources = [source for source in sources if source.get("status") == "verified_snapshot"]
    pending_sources = [source for source in sources if source.get("status") != "verified_snapshot"]
    return {
        "ok": True,
        "status": "official_calendar_snapshot_ready",
        "scope": "scheduled_macro_events_only",
        "as_of_date": today.isoformat(),
        "contract": {
            "version": "macro-events-calendar-v1",
            "automated_sync_enabled": False,
            "unscheduled_news_enabled": False,
            "impact_scoring_enabled": False,
        },
        "coverage": {
            "upcoming_events": len(rows),
            "next_7_days": sum(int(row["days_until"]) <= 7 for row in rows),
            "next_30_days": sum(int(row["days_until"]) <= 30 for row in rows),
            "india_events": sum(row["region"] == "India" for row in rows),
            "us_events": sum(row["region"] == "United States" for row in rows),
            "verified_sources": len(verified_sources),
            "pending_sources": len(pending_sources),
        },
        "next_event": rows[0] if rows else None,
        "events": rows,
        "sources": list(sources),
        "limitations": [
            "This is a reviewed calendar snapshot, not an automatically synchronized feed.",
            "Dates can change; verify the linked official source before relying on an event time.",
            "RBI meeting dates come from its official 23-Mar-2026 schedule; that schedule does not specify decision times.",
            "No unscheduled news, consensus estimate, surprise, sentiment, or trade impact score is shown.",
        ],
    }


def normalize_index_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("&", "AND"))


def discover_sectoral_indices(csv_payload: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Bind the official sector list only to index symbols present in Kite's current NSE master."""
    reader = csv.DictReader(io.StringIO(csv_payload))
    required = {"tradingsymbol", "name", "segment", "exchange"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid_instrument_master")

    inventory: dict[str, str] = {}
    for row in reader:
        if row.get("exchange") != "NSE" or row.get("segment") != "INDICES":
            continue
        symbol = (row.get("tradingsymbol") or "").strip()
        name = (row.get("name") or "").strip()
        if not symbol:
            continue
        for candidate in (symbol, name):
            if candidate:
                inventory.setdefault(normalize_index_name(candidate), symbol)

    targets: list[tuple[str, str, str]] = [(BASE_INDEX[0], BASE_INDEX[1], "broad_market")]
    missing: list[str] = []
    for display_name in OFFICIAL_SECTORAL_INDICES:
        candidates = (display_name, *INDEX_NAME_ALIASES.get(display_name, ()))
        symbol = next(
            (inventory[normalize_index_name(candidate)] for candidate in candidates
             if normalize_index_name(candidate) in inventory),
            None,
        )
        if symbol is None:
            missing.append(display_name)
            continue
        targets.append((display_name, f"NSE:{symbol}", "sectoral"))
    return targets, missing


def normalize_index_snapshot(
    provider_payload: dict[str, object],
    targets: list[tuple[str, str, str]],
) -> tuple[list[dict[str, object]], list[str]]:
    data = provider_payload.get("data")
    if provider_payload.get("status") != "success" or not isinstance(data, dict):
        raise ValueError("invalid_provider_response")

    rows: list[dict[str, object]] = []
    missing: list[str] = []
    for display_name, instrument, category in targets:
        quote = data.get(instrument)
        ohlc = quote.get("ohlc") if isinstance(quote, dict) else None
        values = {
            "open": ohlc.get("open") if isinstance(ohlc, dict) else None,
            "high": ohlc.get("high") if isinstance(ohlc, dict) else None,
            "low": ohlc.get("low") if isinstance(ohlc, dict) else None,
            "previous_close": ohlc.get("close") if isinstance(ohlc, dict) else None,
            "last_price": quote.get("last_price") if isinstance(quote, dict) else None,
        }
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in values.values()
        ):
            missing.append(display_name)
            continue
        rows.append(
            {
                "display_name": display_name,
                "instrument": instrument,
                "category": category,
                **values,
            }
        )
    return rows, missing


class PGTerminalHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, static_directory: str, **kwargs):
        super().__init__(*args, directory=static_directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/kite/status":
            with _SESSION_LOCK:
                connected = bool(_ACTIVE_KITE_SESSION)
                last_error = _KITE_DIAGNOSTICS["last_error"]
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "connected": connected, "last_error": last_error},
            )
            return
        if path == "/api/kite/indices/ohlc":
            self._send_index_snapshot()
            return
        if path == "/api/kite/indices/eod-summary":
            self._send_index_eod_summary()
            return
        if path == "/api/kite/market-breadth":
            self._send_market_breadth()
            return
        if path == "/api/stocks/ytd":
            self._send_stock_ytd(urllib.parse.urlsplit(self.path).query)
            return
        if path == "/api/dashboard/market-sentiment-summary":
            self._send_dashboard_market_sentiment_summary()
            return
        if path == "/api/dashboard/fno-summary":
            self._send_dashboard_fno_summary()
            return
        if path == "/api/dashboard/seasonality-summary":
            self._send_dashboard_seasonality_summary()
            return
        if path == "/api/dashboard/screener-summary":
            self._send_dashboard_screener_summary()
            return
        if path == "/api/dashboard/market-story":
            self._send_dashboard_market_story()
            return
        if path == "/api/seasonality/local":
            self._send_local_seasonality(urllib.parse.urlsplit(self.path).query)
            return
        if path == "/api/screener/local":
            self._send_local_screener()
            return
        if path == "/api/news-events/local":
            self._send_local_news_events()
            return
        if path == "/api/earnings/local":
            self._send_local_earnings()
            return
        if path == "/api/events/calendar":
            self._send_macro_events_calendar()
            return
        if path == "/api/kite/seasonality":
            self._send_seasonality(urllib.parse.urlsplit(self.path).query)
            return
        if path == "/api/market-sentiment/domestic-core":
            self._send_domestic_sentiment_core()
            return
        if path == "/api/market-sentiment/regime-validation":
            self._send_regime_validation(urllib.parse.urlsplit(self.path).query)
            return
        if path == "/api/market-sentiment/regime-validation-universe":
            self._send_regime_validation_universe()
            return
        if path == "/api/market-sentiment/cross-index-validation":
            self._send_cross_index_validation()
            return
        if path == "/api/historical-regimes":
            self._send_historical_regimes(urllib.parse.urlsplit(self.path).query)
            return
        super().do_GET()

    def _send_domestic_sentiment_core(self) -> None:
        try:
            payload = self._calculate_sentiment_payload()
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": str(error)})

    def _send_dashboard_market_sentiment_summary(self) -> None:
        try:
            payload = build_dashboard_market_sentiment_summary(
                self._calculate_sentiment_payload(),
                self._calculate_cross_index_validation_payload(),
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_dashboard_fno_summary(self) -> None:
        try:
            rows = _get_eod_store().load_futures_eod_snapshots()
            payload = build_dashboard_fno_summary(
                calculate_futures_oi_summary(rows),
                stored_history_sessions=len(
                    {
                        item["date"]
                        for item in rows
                        if isinstance(item.get("date"), date)
                    }
                ),
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_dashboard_seasonality_summary(self) -> None:
        summaries: dict[str, dict[str, object]] = {}
        for instrument in SEASONALITY_INDICES:
            try:
                summaries[instrument] = build_dashboard_seasonality_summary(
                    self._calculate_local_seasonality_payload(
                        kind="index",
                        instrument=instrument,
                    )
                )
            except ValueError:
                continue
        self._send_json(
            HTTPStatus.OK,
            build_dashboard_seasonality_universe_summary(summaries),
        )

    def _send_dashboard_screener_summary(self) -> None:
        try:
            payload = build_dashboard_screener_summary(
                self._calculate_local_screener_payload()
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_dashboard_market_story(self) -> None:
        try:
            with _SESSION_LOCK:
                cached_breadth = _BREADTH_CACHE.get("payload")
            nifty500_context = (
                cached_breadth.get("market_context")
                if isinstance(cached_breadth, dict) else None
            )
            if not isinstance(nifty500_context, dict):
                stored_context = _get_eod_store().load_latest_workspace_snapshot(
                    "nifty500-market-context"
                )
                nifty500_context = (
                    stored_context.get("payload")
                    if isinstance(stored_context, dict) else None
                )
            futures_rows = _get_eod_store().load_futures_eod_snapshots()
            futures_summary = build_dashboard_fno_summary(
                calculate_futures_oi_summary(futures_rows),
                stored_history_sessions=len(
                    {
                        item["date"]
                        for item in futures_rows
                        if isinstance(item.get("date"), date)
                    }
                ),
            )
            payload = build_dashboard_market_story(
                build_dashboard_market_sentiment_summary(
                    self._calculate_sentiment_payload(),
                    self._calculate_cross_index_validation_payload(),
                ),
                build_dashboard_screener_summary(
                    self._calculate_local_screener_payload()
                ),
                futures_summary,
                self._calculate_regime_validation_payload(
                    target_index="Nifty 50",
                    benchmark_index=None,
                ),
                self._calculate_local_seasonality_payload(
                    kind="index",
                    instrument="Nifty 50",
                ),
                build_macro_events_calendar(
                    today=datetime.now(INDIA_TIMEZONE).date()
                ),
                nifty500_context,
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_local_seasonality(self, raw_query: str) -> None:
        try:
            query = urllib.parse.parse_qs(raw_query, keep_blank_values=True)
            kinds = query.get("kind", [])
            instruments = query.get("instrument", [])
            if len(kinds) != 1 or len(instruments) != 1:
                raise ValueError("invalid_seasonality_request")
            payload = self._calculate_local_seasonality_payload(
                kind=kinds[0],
                instrument=instruments[0],
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_local_screener(self) -> None:
        try:
            payload = self._calculate_local_screener_payload()
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_local_news_events(self) -> None:
        live_items = _get_eod_store().load_news_event_records()
        self._send_json(
            HTTPStatus.OK,
            build_news_events_workspace(
                reviewed_on=datetime.now(INDIA_TIMEZONE).date(),
                live_items=live_items,
            ),
        )

    def _send_local_earnings(self) -> None:
        self._send_json(
            HTTPStatus.OK,
            build_earnings_analysis(_get_eod_store().load_earnings_records()),
        )

    def _send_macro_events_calendar(self) -> None:
        self._send_json(
            HTTPStatus.OK,
            build_macro_events_calendar(today=datetime.now(INDIA_TIMEZONE).date()),
        )

    @staticmethod
    def _calculate_local_screener_payload() -> dict[str, object]:
        store = _get_eod_store()
        stock_inventory = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock",
                display_name=str(item["display_name"]),
            )
            for item in stock_inventory
        }
        return calculate_stock_screener(
            stock_histories,
            store.load_candles(kind="index", display_name="Nifty 50"),
            expected_through=completed_history_date(datetime.now(INDIA_TIMEZONE)),
        )

    @staticmethod
    def _calculate_local_seasonality_payload(
        *,
        kind: str,
        instrument: str,
    ) -> dict[str, object]:
        if kind not in {"index", "stock"} or not instrument or len(instrument) > 64:
            raise ValueError("invalid_seasonality_request")
        store = _get_eod_store()
        if kind == "index":
            if instrument not in SEASONALITY_INDICES:
                raise ValueError("instrument_not_available")
        else:
            available_stocks = {
                str(item["display_name"])
                for item in store.list_instruments(kind="stock")
            }
            if instrument not in available_stocks:
                raise ValueError("instrument_not_available")
        now = datetime.now(INDIA_TIMEZONE)
        completed_through = completed_history_date(now)
        candles = store.load_candles(
            kind=kind,
            display_name=instrument,
            start=historical_lookback_start(completed_through),
            end=completed_through,
        )
        if len(candles) < 2:
            raise ValueError("no_completed_historical_data")
        month_rows, weekday_rows = calculate_seasonality(candles, today=now.date())
        try:
            validation = calculate_seasonality_validation(candles, today=now.date())
            validation_ready = True
        except ValueError as error:
            if str(error) != "no_completed_historical_data":
                raise
            turn = _turn_of_month_analysis(candles)
            month_names = (
                "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            )
            validation = {
                "turn_rows": turn["rows"],
                "turn_edge_pct": turn["edge_pct"],
                "turn_t_statistic": turn["t_statistic"],
                "turn_p_value": turn["p_value"],
                "holdout_split_date": None,
                "held_out_rows": [
                    {
                        "period": period,
                        "train_count": 0,
                        "train_excess_pct": None,
                        "train_significant": False,
                        "test_count": 0,
                        "test_excess_pct": None,
                        "same_direction": False,
                        "survived": False,
                    }
                    for period in month_names
                ],
                "held_out_summary": {
                    "same_direction": 0,
                    "train_significant": 0,
                    "survived": 0,
                },
                "turn_held_out_rows": [],
            }
            validation_ready = False
        populated_months = sum(int(row.get("count") or 0) > 0 for row in month_rows)
        readiness_status = (
            "historical_evidence_ready"
            if populated_months == 12 and validation_ready
            else "partial_history"
        )
        return {
            "ok": True,
            "instrument": instrument,
            "kind": kind,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "from_date": candles[0]["date"].isoformat(),
            "as_of_date": candles[-1]["date"].isoformat(),
            "completed_sessions": len(candles),
            "readiness": {
                "status": readiness_status,
                "populated_months": populated_months,
                "validation_ready": validation_ready,
            },
            "historical_requests": 0,
            "persistent_store": True,
            "stored_sessions_before_sync": len(candles),
            "new_sessions": 0,
            "duplicate_sessions": 0,
            "local_history_reused": True,
            "local_only": True,
            "sync_from_date": None,
            "month_rows": month_rows,
            "weekday_rows": weekday_rows,
            **validation,
            "return_definition": "close-to-close percentage change",
            "range_definition": "(high - low) / low * 100",
            "price_source": "Validated local Kite EOD candles",
        }

    def _send_regime_validation(self, query: str) -> None:
        try:
            parameters = urllib.parse.parse_qs(query, keep_blank_values=True)
            target_index = parameters.get("index", ["Nifty 50"])[0]
            benchmark_value = parameters.get("benchmark", ["Nifty 50"])[0]
            if target_index not in SEASONALITY_INDICES or benchmark_value not in {"Nifty 50", "none"}:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "reason": "invalid_regime_validation_selection"},
                )
                return
            benchmark_index = None if benchmark_value == "none" or benchmark_value == target_index else benchmark_value
            payload = self._calculate_regime_validation_payload(
                target_index=target_index,
                benchmark_index=benchmark_index,
            )
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": str(error)})

    def _send_regime_validation_universe(self) -> None:
        store = _get_eod_store()
        stock_names = {
            str(item["display_name"])
            for item in store.list_instruments(kind="stock")
        }
        payload = build_regime_validation_universe(
            store.list_instruments(kind="index"),
            stock_names=stock_names,
            constituent_snapshot=load_index_constituent_snapshot(),
        )
        self._send_json(HTTPStatus.OK, payload)

    def _send_cross_index_validation(self) -> None:
        try:
            payload = self._calculate_cross_index_validation_payload()
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as error:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "reason": str(error)})

    def _send_historical_regimes(self, query: str) -> None:
        try:
            parameters = urllib.parse.parse_qs(query, keep_blank_values=True)
            instrument = parameters.get("index", ["Nifty 50"])[0]
            if instrument not in SEASONALITY_INDICES:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "reason": "invalid_historical_regime_selection"},
                )
                return
            store = _get_eod_store()
            candles = store.load_candles(
                kind="index",
                display_name=instrument,
            )
            self._send_json(
                HTTPStatus.OK,
                build_historical_regime_workspace(
                    candles,
                    instrument=instrument,
                    official_history_rows=store.load_historical_series_observations(),
                ),
            )
        except ValueError as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error)},
            )

    def _send_historical_series_refresh(self) -> None:
        observations: list[dict[str, object]] = []
        for source in RBI_HISTORICAL_SERIES_SOURCES:
            request = urllib.request.Request(
                str(source["url"]),
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Referer": "https://rbi.org.in/scripts/AnnualPublications.aspx?head=Handbook%20of%20Statistics%20on%20Indian%20Economy",
                    "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
                },
                method="GET",
            )
            text_payload, reason = self._request_provider_text(request, RBI_MAX_RESPONSE_BYTES)
            if reason is not None:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "reason": "rbi_historical_series_source_unavailable"},
                )
                return
            try:
                observations.extend(
                    parse_rbi_annual_series_table(
                        text_payload or "",
                        series_key=str(source["series_key"]),
                        source_url=str(source["url"]),
                        source_title=str(source["title"]),
                        vintage_date=source["vintage_date"],
                        value_column=int(source["value_column"]),
                        unit=str(source["unit"]),
                        aggregation=str(source.get("aggregation", "annual average")),
                        allow_non_positive=bool(source.get("allow_non_positive", False)),
                        base_period_override=(
                            str(source["base_period"])
                            if source.get("base_period") is not None
                            else None
                        ),
                        maximum_end_year=(
                            int(source["maximum_end_year"])
                            if source.get("maximum_end_year") is not None
                            else None
                        ),
                        duplicate_resolution=str(source.get("duplicate_resolution", "last")),
                    )
                )
            except ValueError:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"ok": False, "reason": "invalid_rbi_historical_series_response"},
                )
                return
        try:
            store = _get_eod_store()
            write_result = store.append_historical_series_observations(
                observations,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = build_historical_series_summary(
                store.load_historical_series_observations()
            )
        except HistoricalSeriesConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_historical_series_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_rbi_historical_series_response"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "source": RBI_HISTORICAL_SERIES_SOURCE,
                "write_result": write_result,
                "official_history": summary,
            },
        )

    @staticmethod
    def _calculate_cross_index_validation_payload() -> dict[str, object]:
        store = _get_eod_store()
        index_inventory = store.list_instruments(kind="index")
        stock_inventory = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock", display_name=str(item["display_name"])
            )
            for item in stock_inventory
        }
        constituent_snapshot = load_index_constituent_snapshot()
        readiness = build_regime_validation_universe(
            index_inventory,
            stock_names=set(stock_histories),
            constituent_snapshot=constituent_snapshot,
        )
        histories = {
            name: store.load_candles(kind="index", display_name=name)
            for name in SEASONALITY_INDICES
        }
        india_vix_candles = store.load_candles(kind="index", display_name="India VIX")
        nifty50_candles = histories.get("Nifty 50", [])
        institutional_flow_rows = store.load_institutional_flows()
        confirmed_fpi_rows = store.load_confirmed_fpi_investments()
        macro_snapshot_rows = store.load_macro_snapshots()
        global_risk_rows = store.load_global_risk_observations()
        futures_snapshot_rows = store.load_futures_eod_snapshots()
        external_rows = {
            "institutional": institutional_flow_rows,
            "confirmed_fpi": confirmed_fpi_rows,
            "macro": macro_snapshot_rows,
            "global": global_risk_rows,
            "futures": futures_snapshot_rows,
        }
        external_readiness = build_regime_external_cluster_readiness(
            institutional_flow_rows=institutional_flow_rows,
            confirmed_fpi_rows=confirmed_fpi_rows,
            macro_snapshot_rows=macro_snapshot_rows,
            global_risk_rows=global_risk_rows,
            futures_snapshot_rows=futures_snapshot_rows,
        )
        futures_history_row = next(
            (
                item
                for item in external_readiness["rows"]
                if item["key"] == "kite_futures_oi"
            ),
            {},
        )
        futures_oi_summary = calculate_futures_oi_summary(futures_snapshot_rows)
        cache_contract = {
            "rule_version": REGIME_RULE_VERSION,
            "recovery_contract": (
                REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
                REGIME_RECOVERY_MAXIMUM_SESSIONS,
            ),
            "directional_contract": (
                REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
                REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
                REGIME_LONG_HORIZON_SESSIONS,
                REGIME_SHORT_HORIZON_SESSIONS,
                REGIME_RISK_TAIL_PERCENTILE,
                REGIME_ADVERSE_DISTANCE_LEVELS_PCT,
                REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT,
                REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT,
                REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT,
            ),
            "constituent_snapshot_as_of": constituent_snapshot.get("as_of"),
            "constituent_membership_history": {
                name: [
                    (
                        item["effective_from"].isoformat(),
                        item["effective_to"].isoformat() if item["effective_to"] else None,
                        item["symbols"],
                    )
                    for item in snapshots
                ]
                for name, snapshots in constituent_snapshot.get("history", {}).items()
            },
            "indices": [
                (
                    name,
                    len(history),
                    history[-1]["date"].isoformat() if history else None,
                )
                for name, history in sorted(histories.items())
            ],
            "stocks": [
                (
                    name,
                    len(history),
                    history[-1]["date"].isoformat() if history else None,
                )
                for name, history in sorted(stock_histories.items())
            ],
            "external_history": {
                key: (
                    len(rows),
                    max(
                        (item["date"].isoformat() for item in rows if isinstance(item.get("date"), date)),
                        default=None,
                    ),
                )
                for key, rows in external_rows.items()
            },
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with _CROSS_INDEX_VALIDATION_LOCK:
            if _CROSS_INDEX_VALIDATION_CACHE.get("key") == cache_key:
                cached = _CROSS_INDEX_VALIDATION_CACHE.get("payload")
                if isinstance(cached, dict):
                    payload = json.loads(json.dumps(cached))
                    payload["cache_hit"] = True
                    return payload

            rows: list[dict[str, object]] = []
            excluded: list[dict[str, object]] = []
            constituent_indices = constituent_snapshot["indices"]
            constituent_history = constituent_snapshot.get("history", {})
            for state in readiness["indices"]:
                name = str(state["display_name"])
                if not state["validation_ready"]:
                    reason = (
                        "insufficient_history"
                        if not state["walk_forward_ready"]
                        else "insufficient_fno_constituent_breadth"
                    )
                    excluded.append({"index": name, "reason": reason})
                    continue
                validation = calculate_regime_walk_forward_validation(
                    histories[name],
                    stock_histories,
                    india_vix_candles=india_vix_candles,
                    target_index=name,
                    benchmark_candles=nifty50_candles,
                    benchmark_index="Nifty 50" if name != "Nifty 50" else None,
                    constituent_symbols=constituent_indices[name],
                    constituent_membership_history=constituent_history.get(name, []),
                    constituent_snapshot_as_of=str(constituent_snapshot.get("as_of") or ""),
                    institutional_flow_rows=institutional_flow_rows,
                    confirmed_fpi_rows=confirmed_fpi_rows,
                    macro_snapshot_rows=macro_snapshot_rows,
                    global_risk_rows=global_risk_rows,
                    futures_snapshot_rows=futures_snapshot_rows,
                )
                metrics = validation["overall"]["horizons"]["20"]
                transition = validation.get("transition_analysis", {})
                recovery_state = next(
                    (
                        row
                        for row in transition.get("by_state", [])
                        if row.get("label_key") == "recovering_market"
                    ),
                    None,
                )
                recovery_metrics = (
                    recovery_state.get("horizons", {}).get("20", {})
                    if isinstance(recovery_state, dict) else {}
                )
                recovery_exits = transition.get("exit_counts", {})
                directional_states = transition.get("directional_state_evidence", [])
                long_states = [
                    item
                    for item in directional_states
                    if item.get("research_bias") == "long_research_candidate"
                ]
                short_states = [
                    item
                    for item in directional_states
                    if item.get("research_bias") == "short_research_candidate"
                ]
                long_state = max(
                    long_states,
                    key=lambda item: (
                        float(item["median_excess_return_pct"])
                        if item.get("median_excess_return_pct") is not None
                        else float(item["median_return_pct"])
                    ),
                    default=None,
                )
                short_state = min(
                    short_states,
                    key=lambda item: (
                        float(item["median_excess_return_pct"])
                        if item.get("median_excess_return_pct") is not None
                        else float(item["median_return_pct"])
                    ),
                    default=None,
                )
                recovery_incremental = transition.get(
                    "recovery_incremental_evidence", {}
                )
                current_state = validation.get("current_state", {})
                current_transition_key = current_state.get("transition_label_key")
                matched_state_evidence = next(
                    (
                        item
                        for item in directional_states
                        if item.get("label_key") == current_transition_key
                    ),
                    None,
                )
                futures_confirmation = build_index_futures_confirmation(
                    constituent_indices[name],
                    fno_constituent_count=int(
                        validation["breadth_universe"]["fno_constituent_count"]
                    ),
                    futures_summary=futures_oi_summary,
                    history_ready=bool(futures_history_row.get("history_ready")),
                    current_state_date=(
                        str(current_state.get("as_of_date"))
                        if current_state.get("as_of_date") else None
                    ),
                )
                is_benchmark = name == "Nifty 50"
                if is_benchmark:
                    current_decision = "market_context_only"
                elif not current_state.get("classification_ready"):
                    current_decision = "insufficient_evidence"
                elif not isinstance(matched_state_evidence, dict):
                    current_decision = "insufficient_evidence"
                elif matched_state_evidence.get("research_bias") == "long_research_candidate":
                    current_decision = "long_candidate"
                elif matched_state_evidence.get("research_bias") == "short_research_candidate":
                    if futures_confirmation["short_gate_passed"]:
                        current_decision = "short_candidate"
                    elif not futures_confirmation["history_ready"]:
                        current_decision = "short_watch_history_building"
                    elif not futures_confirmation["current_confirmation_ready"]:
                        current_decision = "short_watch_unconfirmed"
                    else:
                        current_decision = "avoid_no_short_confirmation"
                elif matched_state_evidence.get("research_bias") == "countertrend_rebound_study":
                    current_decision = "countertrend_watch"
                elif matched_state_evidence.get("research_bias") == "tactical_rebound_study":
                    current_decision = "tactical_watch"
                elif matched_state_evidence.get("research_bias") == "reversal_short_study":
                    current_decision = "reversal_watch"
                elif matched_state_evidence.get("research_bias") == "insufficient_sample":
                    current_decision = "insufficient_evidence"
                else:
                    current_decision = "avoid_no_validated_edge"
                rows.append(
                    {
                        "index": name,
                        "is_benchmark": is_benchmark,
                        "sessions": validation["overall"]["sessions"],
                        "median_return_pct": metrics["median_return_pct"],
                        "positive_rate_pct": metrics["positive_rate_pct"],
                        "median_excess_return_pct": 0.0 if is_benchmark else metrics["median_excess_return_pct"],
                        "outperformance_rate_pct": None if is_benchmark else metrics["outperformance_rate_pct"],
                        "worst_max_drawdown_pct": metrics["worst_max_drawdown_pct"],
                        "worst_relative_drawdown_pct": 0.0 if is_benchmark else metrics["worst_relative_drawdown_pct"],
                        "official_constituent_count": validation["breadth_universe"]["official_constituent_count"],
                        "fno_constituent_count": validation["breadth_universe"]["fno_constituent_count"],
                        "evaluation_start": validation["evaluation_start"],
                        "evaluation_end": validation["evaluation_end"],
                        "recovery_episode_count": int(transition.get("episode_count") or 0),
                        "recovery_sessions": int(
                            recovery_state.get("sessions") or 0
                            if isinstance(recovery_state, dict) else 0
                        ),
                        "recovery_positive_exit_count": int(
                            recovery_exits.get("positive_market_confirmed") or 0
                        ),
                        "recovery_relapse_count": int(
                            recovery_exits.get("relapsed_to_risk") or 0
                        ),
                        "recovery_timeout_count": int(
                            recovery_exits.get("maximum_window_reached") or 0
                        ),
                        "recovery_open_count": int(recovery_exits.get("still_open") or 0),
                        "recovery_20d_median_return_pct": recovery_metrics.get(
                            "median_return_pct"
                        ),
                        "recovery_20d_positive_rate_pct": recovery_metrics.get(
                            "positive_rate_pct"
                        ),
                        "recovery_20d_worst_return_pct": recovery_metrics.get(
                            "worst_return_pct"
                        ),
                        "recovery_20d_worst_drawdown_pct": recovery_metrics.get(
                            "worst_max_drawdown_pct"
                        ),
                        "recovery_20d_median_excess_return_pct": (
                            0.0
                            if is_benchmark and recovery_metrics
                            else recovery_metrics.get("median_excess_return_pct")
                        ),
                        "recovery_20d_outperformance_rate_pct": (
                            None
                            if is_benchmark else recovery_metrics.get("outperformance_rate_pct")
                        ),
                        "recovery_comparable_base_sessions": int(
                            recovery_incremental.get("comparable_base_sessions") or 0
                        ),
                        "recovery_base_20d_median_return_pct": (
                            recovery_incremental.get("comparable_base_20d", {}).get(
                                "median_return_pct"
                            )
                        ),
                        "recovery_incremental_median_return_pct": recovery_incremental.get(
                            "delta_median_return_pct"
                        ),
                        "recovery_incremental_positive_rate_pct": recovery_incremental.get(
                            "delta_positive_rate_pct"
                        ),
                        "recovery_incremental_status": recovery_incremental.get("status"),
                        "historical_long_state": long_state,
                        "historical_short_state": short_state,
                        "current_state": current_state,
                        "current_state_historical_evidence": matched_state_evidence,
                        "futures_short_confirmation": futures_confirmation,
                        "current_decision": current_decision,
                    }
                )
            rows.sort(
                key=lambda row: (
                    -float(row["median_excess_return_pct"])
                    if row["median_excess_return_pct"] is not None else math.inf,
                    str(row["index"]),
                )
            )
            for rank, row in enumerate(rows, start=1):
                row["rank"] = rank
            decision_priority = {
                "long_candidate": 0,
                "short_candidate": 1,
                "short_watch_unconfirmed": 2,
                "short_watch_history_building": 3,
                "countertrend_watch": 4,
                "tactical_watch": 5,
                "reversal_watch": 6,
                "avoid_no_short_confirmation": 7,
                "avoid_no_validated_edge": 8,
                "insufficient_evidence": 9,
                "market_context_only": 10,
            }
            decision_rows = sorted(
                rows,
                key=lambda row: (
                    decision_priority.get(str(row["current_decision"]), 9),
                    -float(
                        (row.get("current_state_historical_evidence") or {}).get(
                            "median_excess_return_pct"
                        )
                        or (row.get("current_state_historical_evidence") or {}).get(
                            "median_return_pct"
                        )
                        or 0
                    )
                    if row["current_decision"] == "long_candidate"
                    else float(
                        (row.get("current_state_historical_evidence") or {}).get(
                            "median_excess_return_pct"
                        )
                        or (row.get("current_state_historical_evidence") or {}).get(
                            "median_return_pct"
                        )
                        or 0
                    )
                    if row["current_decision"] == "short_candidate"
                    else 0,
                    str(row["index"]),
                ),
            )
            for rank, row in enumerate(decision_rows, start=1):
                row["decision_rank"] = rank
            payload = {
                "ok": True,
                "status": "historical_exploratory_comparison",
                "horizon_sessions": 20,
                "benchmark": "Nifty 50",
                "constituent_snapshot_as_of": constituent_snapshot.get("as_of"),
                "rows": rows,
                "current_decision_rows": decision_rows,
                "recovery_state_contract": {
                    "minimum_prior_risk_sessions": REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
                    "maximum_recovery_sessions": REGIME_RECOVERY_MAXIMUM_SESSIONS,
                    "status": "validation_only_outcome_blind_rule",
                    "eligible_indices": sum(
                        int(row["recovery_episode_count"] > 0) for row in rows
                    ),
                },
                "directional_research_contract": {
                    "minimum_state_sessions": REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
                    "absolute_median_return_threshold_pct": REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
                    "positive_rate_long_threshold_pct": REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                    "positive_rate_short_threshold_pct": 100
                    - REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                    "relative_median_excess_threshold_pct": REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
                    "long_horizon_sessions": REGIME_LONG_HORIZON_SESSIONS,
                    "short_horizon_sessions": REGIME_SHORT_HORIZON_SESSIONS,
                    "tail_percentile": REGIME_RISK_TAIL_PERCENTILE,
                    "adverse_distance_levels_pct": list(REGIME_ADVERSE_DISTANCE_LEVELS_PCT),
                    "status": "historical_research_only_not_live_signal",
                },
                "futures_short_confirmation_contract": {
                    "history_sessions_required": REGIME_EXTERNAL_HISTORY_SESSIONS,
                    "stored_history_sessions": int(
                        futures_history_row.get("stored_sessions") or 0
                    ),
                    "history_ready": bool(futures_history_row.get("history_ready")),
                    "minimum_clear_constituent_states": REGIME_FUTURES_SHORT_MINIMUM_STATE_COUNT,
                    "minimum_constituent_coverage_pct": REGIME_FUTURES_SHORT_MINIMUM_COVERAGE_PCT,
                    "minimum_bearish_share_pct": REGIME_FUTURES_SHORT_BEARISH_SHARE_THRESHOLD_PCT,
                    "status": "confirmation_gate_not_trading_signal",
                },
                "excluded": excluded,
                "limitations": [
                    "Long research uses 20-session outcomes; downside-continuation research uses 5-session outcomes. Neither is a trade signal.",
                    "Tail loss, adverse excursion, and distance-breach rates are historical risk evidence, not stop or position-size recommendations.",
                    "Breadth uses current constituents within the current liquid F&O universe and carries survivorship bias.",
                    "Overlapping forward windows are descriptive rather than independent observations.",
                ],
                "cache_hit": False,
            }
            _CROSS_INDEX_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.update({"key": cache_key, "payload": payload})
            return payload

    @staticmethod
    def _calculate_regime_validation_payload(
        *,
        target_index: str = "Nifty 50",
        benchmark_index: str | None = None,
    ) -> dict[str, object]:
        store = _get_eod_store()
        index_candles = store.load_candles(kind="index", display_name=target_index)
        benchmark_candles = (
            store.load_candles(kind="index", display_name=benchmark_index)
            if benchmark_index else []
        )
        india_vix_candles = store.load_candles(kind="index", display_name="India VIX")
        instruments = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock", display_name=str(item["display_name"])
            )
            for item in instruments
        }
        constituent_snapshot = load_index_constituent_snapshot()
        institutional_flow_rows = store.load_institutional_flows()
        confirmed_fpi_rows = store.load_confirmed_fpi_investments()
        macro_snapshot_rows = store.load_macro_snapshots()
        global_risk_rows = store.load_global_risk_observations()
        futures_snapshot_rows = store.load_futures_eod_snapshots()
        external_rows = {
            "institutional": institutional_flow_rows,
            "confirmed_fpi": confirmed_fpi_rows,
            "macro": macro_snapshot_rows,
            "global": global_risk_rows,
            "futures": futures_snapshot_rows,
        }
        constituent_indices = constituent_snapshot["indices"]
        constituent_symbols = constituent_indices.get(target_index, [])
        if not constituent_symbols:
            raise ValueError("index_constituent_snapshot_unavailable")
        cache_contract = {
            "rule_version": REGIME_RULE_VERSION,
            "recovery_contract": (
                REGIME_RECOVERY_MINIMUM_RISK_SESSIONS,
                REGIME_RECOVERY_MAXIMUM_SESSIONS,
            ),
            "directional_contract": (
                REGIME_DIRECTIONAL_MINIMUM_STATE_SESSIONS,
                REGIME_DIRECTIONAL_RETURN_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_POSITIVE_RATE_THRESHOLD_PCT,
                REGIME_DIRECTIONAL_EXCESS_THRESHOLD_PCT,
                REGIME_LONG_HORIZON_SESSIONS,
                REGIME_SHORT_HORIZON_SESSIONS,
                REGIME_RISK_TAIL_PERCENTILE,
                REGIME_ADVERSE_DISTANCE_LEVELS_PCT,
            ),
            "target_index": target_index,
            "benchmark_index": benchmark_index,
            "index_sessions": len(index_candles),
            "index_latest": index_candles[-1]["date"].isoformat() if index_candles else None,
            "vix_sessions": len(india_vix_candles),
            "vix_latest": india_vix_candles[-1]["date"].isoformat() if india_vix_candles else None,
            "benchmark_sessions": len(benchmark_candles),
            "benchmark_latest": benchmark_candles[-1]["date"].isoformat() if benchmark_candles else None,
            "constituent_snapshot_as_of": constituent_snapshot.get("as_of"),
            "constituent_symbols": constituent_symbols,
            "constituent_membership_history": [
                (
                    item["effective_from"].isoformat(),
                    item["effective_to"].isoformat() if item["effective_to"] else None,
                    item["symbols"],
                )
                for item in constituent_snapshot.get("history", {}).get(target_index, [])
            ],
            "stocks": [
                (
                    name,
                    len(history),
                    history[-1]["date"].isoformat() if history else None,
                )
                for name, history in sorted(stock_histories.items())
            ],
            "external_history": {
                key: (
                    len(rows),
                    max(
                        (item["date"].isoformat() for item in rows if isinstance(item.get("date"), date)),
                        default=None,
                    ),
                )
                for key, rows in external_rows.items()
            },
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with _REGIME_VALIDATION_LOCK:
            if _REGIME_VALIDATION_CACHE.get("key") == cache_key:
                cached = _REGIME_VALIDATION_CACHE.get("payload")
                if isinstance(cached, dict):
                    payload = json.loads(json.dumps(cached))
                    payload["cache_hit"] = True
                    return payload
            payload = calculate_regime_walk_forward_validation(
                index_candles,
                stock_histories,
                india_vix_candles=india_vix_candles,
                target_index=target_index,
                benchmark_candles=benchmark_candles,
                benchmark_index=benchmark_index,
                constituent_symbols=constituent_symbols,
                constituent_membership_history=constituent_snapshot.get("history", {}).get(
                    target_index, []
                ),
                constituent_snapshot_as_of=str(constituent_snapshot.get("as_of") or ""),
                institutional_flow_rows=institutional_flow_rows,
                confirmed_fpi_rows=confirmed_fpi_rows,
                macro_snapshot_rows=macro_snapshot_rows,
                global_risk_rows=global_risk_rows,
                futures_snapshot_rows=futures_snapshot_rows,
            )
            payload["cache_hit"] = False
            _REGIME_VALIDATION_CACHE.clear()
            _REGIME_VALIDATION_CACHE.update({"key": cache_key, "payload": payload})
            return payload

    @staticmethod
    def _calculate_sentiment_payload() -> dict[str, object]:
        store = _get_eod_store()
        index_candles = store.load_candles(kind="index", display_name="Nifty 50")
        india_vix_candles = store.load_candles(kind="index", display_name="India VIX")
        institutional_flow_rows = store.load_institutional_flows()
        confirmed_fpi_rows = store.load_confirmed_fpi_investments()
        macro_snapshot_rows = store.load_macro_snapshots()
        global_risk_rows = store.load_global_risk_observations()
        futures_snapshot_rows = store.load_futures_eod_snapshots()
        instruments = store.list_instruments(kind="stock")
        stock_histories = {
            str(item["display_name"]): store.load_candles(
                kind="stock", display_name=str(item["display_name"])
            )
            for item in instruments
        }
        return calculate_domestic_sentiment_core(
            index_candles,
            stock_histories,
            india_vix_candles=india_vix_candles,
            institutional_flow_rows=institutional_flow_rows,
            confirmed_fpi_rows=confirmed_fpi_rows,
            macro_snapshot_rows=macro_snapshot_rows,
            global_risk_rows=global_risk_rows,
            futures_snapshot_rows=futures_snapshot_rows,
        )

    def _send_sentiment_factor_snapshot(self) -> None:
        try:
            payload = self._calculate_sentiment_payload()
            evidence = json.loads(json.dumps(payload, allow_nan=False))
            candidate_regime = evidence.pop("candidate_regime", None)
            freshness = evidence.get("freshness")
            if isinstance(freshness, dict):
                freshness.pop("retrieved_at", None)
            as_of_date = date.fromisoformat(str(payload["as_of_date"]))
            write_result = _get_eod_store().append_sentiment_factor_snapshot(
                as_of_date=as_of_date,
                model_version=SENTIMENT_EVIDENCE_MODEL_VERSION,
                evidence=evidence,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "as_of_date": as_of_date.isoformat(),
                    "model_version": SENTIMENT_EVIDENCE_MODEL_VERSION,
                    "candidate_rule_version": (
                        candidate_regime.get("rule_version")
                        if isinstance(candidate_regime, dict)
                        else REGIME_RULE_VERSION
                    ),
                    "write_result": write_result,
                },
            )
        except (KeyError, TypeError, ValueError) as error:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "reason": str(error) or "sentiment_factor_snapshot_unavailable"},
            )

    def _send_index_snapshot(self) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "reason": "kite_not_connected"},
            )
            return

        try:
            targets, inventory_missing = self._current_index_targets(api_key, access_token)
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return

        query = urllib.parse.urlencode([("i", instrument) for _, instrument, _ in targets])
        request = urllib.request.Request(
            f"{OHLC_URL}?{query}",
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "application/json",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        provider_payload, reason = self._request_provider_json(request, exchange=False)
        if reason is not None:
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return

        try:
            rows, quote_missing = normalize_index_snapshot(provider_payload or {}, targets)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_provider_response"},
            )
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
                "missing": [*inventory_missing, *quote_missing],
                "official_sector_count": len(OFFICIAL_SECTORAL_INDICES),
                "available_sector_count": sum(
                    1 for row in rows if row.get("category") == "sectoral"
                ),
            },
        )

    def _send_index_eod_summary(self) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return
        try:
            self._current_index_targets(api_key, access_token)
            with _SESSION_LOCK:
                tokens = dict(_ACTIVE_DASHBOARD_INDEX_TOKENS)
            if set(tokens) != set(DASHBOARD_EOD_INDICES):
                raise ValueError("dashboard_index_not_available")

            now = datetime.now(INDIA_TIMEZONE)
            from_date = now.date() - timedelta(days=400)
            store = _get_eod_store()
            rows: list[dict[str, object]] = []
            for index, display_name in enumerate(DASHBOARD_EOD_INDICES):
                if index:
                    time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                query = urllib.parse.urlencode(
                    {"from": from_date.isoformat(), "to": now.date().isoformat(), "continuous": "0", "oi": "0"}
                )
                request = urllib.request.Request(
                    f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=tokens[display_name])}?{query}",
                    headers={
                        "Authorization": f"token {api_key}:{access_token}",
                        "X-Kite-Version": "3",
                        "Accept": "application/json",
                        "User-Agent": "PG-terminal-local/0.1",
                    },
                    method="GET",
                )
                provider_payload, reason = self._request_provider_json(request, exchange=False)
                if reason is not None:
                    raise ValueError(reason)
                candles = parse_daily_candles(
                    provider_payload or {}, today=now.date(), now_time=now.time().replace(tzinfo=None)
                )
                history = [(row["date"], float(row["close"])) for row in candles]
                if display_name == "India VIX":
                    try:
                        store.append_candles(
                            kind="index",
                            display_name=display_name,
                            provider_token=tokens[display_name],
                            candles=candles,
                            retrieved_at=datetime.now(timezone.utc).isoformat(),
                        )
                    except CandleConflictError as error:
                        raise ValueError("stored_candle_conflict") from error
                rows.append(calculate_index_ytd(display_name, history))
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return

        self._send_json(
            HTTPStatus.OK,
            {"ok": True, "retrieved_at": datetime.now(timezone.utc).isoformat(), "rows": rows},
        )

    def _current_index_targets(
        self, api_key: str, access_token: str
    ) -> tuple[list[tuple[str, str, str]], list[str]]:
        with _SESSION_LOCK:
            cached = list(_ACTIVE_INDEX_TARGETS)
            seasonality_tokens = dict(_ACTIVE_SEASONALITY_INDEX_TOKENS)
        if cached and seasonality_tokens:
            available_names = {target[0] for target in cached if target[2] == "sectoral"}
            return cached, [name for name in OFFICIAL_SECTORAL_INDICES if name not in available_names]

        request = urllib.request.Request(
            NSE_INSTRUMENTS_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        csv_payload, reason = self._request_provider_text(request, MAX_INSTRUMENT_BYTES)
        if reason is not None:
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            raise ValueError(reason)
        try:
            targets, missing = discover_sectoral_indices(csv_payload or "")
            equity_tokens = parse_equity_tokens(csv_payload or "")
            dashboard_index_tokens = parse_dashboard_index_tokens(csv_payload or "")
            seasonality_index_tokens = parse_seasonality_index_tokens(csv_payload or "")
        except ValueError as error:
            raise ValueError(str(error)) from error
        with _SESSION_LOCK:
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_INDEX_TARGETS.extend(targets)
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.update(dashboard_index_tokens)
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_SEASONALITY_INDEX_TOKENS.update(seasonality_index_tokens)
            _ACTIVE_EQUITY_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.update(equity_tokens)
        return targets, missing

    def _send_seasonality(self, raw_query: str) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        query = urllib.parse.parse_qs(raw_query, keep_blank_values=True)
        kinds = query.get("kind", [])
        instruments = query.get("instrument", [])
        if len(kinds) != 1 or len(instruments) != 1:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_seasonality_request"})
            return
        kind = kinds[0]
        instrument = instruments[0]
        if kind not in {"index", "stock"} or not instrument or len(instrument) > 64 or instrument.strip() != instrument:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_seasonality_request"})
            return

        cache_key = (kind, instrument)
        with _SESSION_LOCK:
            cached = _SEASONALITY_CACHE.get(cache_key)
        if cached and time.monotonic() - float(cached["created_at"]) < SEASONALITY_CACHE_SECONDS:
            cached_payload = cached.get("payload")
            if is_complete_seasonality_payload(cached_payload):
                self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
                return
            with _SESSION_LOCK:
                _SEASONALITY_CACHE.pop(cache_key, None)

        try:
            if kind == "index":
                if instrument not in SEASONALITY_INDICES:
                    raise ValueError("instrument_not_available")
                self._current_index_targets(api_key, access_token)
                with _SESSION_LOCK:
                    token = _ACTIVE_SEASONALITY_INDEX_TOKENS.get(instrument)
            else:
                symbol = instrument.upper()
                if symbol != instrument or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol):
                    raise ValueError("instrument_not_available")
                token = self._current_equity_tokens(api_key, access_token).get(symbol)
            if token is None:
                raise ValueError("instrument_not_available")
            payload = self._build_seasonality(api_key, access_token, token, kind, instrument)
            with _SESSION_LOCK:
                _SEASONALITY_CACHE[cache_key] = {
                    "payload": payload,
                    "created_at": time.monotonic(),
                }
            self._send_json(HTTPStatus.OK, {**payload, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})

    def _build_seasonality(
        self,
        api_key: str,
        access_token: str,
        token: str,
        kind: str,
        instrument: str,
    ) -> dict[str, object]:
        now = datetime.now(INDIA_TIMEZONE)
        completed_through = completed_history_date(now)
        history_start = historical_lookback_start(completed_through)
        store = _get_eod_store()
        coverage_before = store.coverage(kind=kind, display_name=instrument)
        last_stored = coverage_before["last_session"]
        sync_start = max(history_start, last_stored + timedelta(days=1)) if last_stored else history_start
        ranges = incremental_history_ranges(history_start, completed_through, last_stored)
        inserted_sessions = 0
        duplicate_sessions = 0
        for index, (from_date, to_date) in enumerate(ranges):
            if index:
                time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
            query = urllib.parse.urlencode(
                {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                    "continuous": "0",
                    "oi": "0",
                }
            )
            request = urllib.request.Request(
                f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=token)}?{query}",
                headers={
                    "Authorization": f"token {api_key}:{access_token}",
                    "X-Kite-Version": "3",
                    "Accept": "application/json",
                    "User-Agent": "PG-terminal-local/0.1",
                },
                method="GET",
            )
            provider_payload, reason = self._request_provider_json(
                request,
                exchange=False,
                maximum_bytes=MAX_HISTORICAL_RESPONSE_BYTES,
            )
            if reason is not None:
                raise ValueError(reason)
            parsed_candles = parse_daily_candles(
                provider_payload or {},
                today=now.date(),
                now_time=now.time().replace(tzinfo=None),
            )
            try:
                write_result = store.append_candles(
                    kind=kind,
                    display_name=instrument,
                    provider_token=token,
                    candles=parsed_candles,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                )
            except CandleConflictError as error:
                raise ValueError("stored_candle_conflict") from error
            inserted_sessions += write_result["inserted"]
            duplicate_sessions += write_result["duplicates"]

        candles = store.load_candles(
            kind=kind,
            display_name=instrument,
            start=history_start,
            end=completed_through,
        )
        if len(candles) < 2:
            raise ValueError("no_completed_historical_data")
        month_rows, weekday_rows = calculate_seasonality(candles, today=now.date())
        validation = calculate_seasonality_validation(candles, today=now.date())
        return {
            "ok": True,
            "instrument": instrument,
            "kind": kind,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "from_date": candles[0]["date"].isoformat(),
            "as_of_date": candles[-1]["date"].isoformat(),
            "completed_sessions": len(candles),
            "historical_requests": len(ranges),
            "persistent_store": True,
            "stored_sessions_before_sync": coverage_before["session_count"],
            "new_sessions": inserted_sessions,
            "duplicate_sessions": duplicate_sessions,
            "local_history_reused": coverage_before["session_count"] > 0,
            "sync_from_date": sync_start.isoformat() if ranges else None,
            "month_rows": month_rows,
            "weekday_rows": weekday_rows,
            **validation,
            "return_definition": "close-to-close percentage change",
            "range_definition": "(high - low) / low * 100",
            "price_source": "Kite Connect historical daily candles",
        }

    def _send_market_breadth(self) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
            cached_payload = _BREADTH_CACHE.get("payload")
            cached_at = _BREADTH_CACHE.get("created_at")
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return
        if (
            isinstance(cached_payload, dict)
            and isinstance(cached_at, (int, float))
            and time.monotonic() - float(cached_at) < BREADTH_CACHE_SECONDS
        ):
            public_payload = {
                key: value for key, value in cached_payload.items()
                if not str(key).startswith("_")
            }
            self._send_json(HTTPStatus.OK, {**public_payload, "cache_hit": True})
            return
        if not _BREADTH_BUILD_LOCK.acquire(blocking=False):
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "breadth_refresh_in_progress"},
            )
            return

        try:
            payload = self._build_market_breadth(api_key, access_token)
            with _SESSION_LOCK:
                _BREADTH_CACHE.clear()
                _BREADTH_CACHE.update({"payload": payload, "created_at": time.monotonic()})
            public_payload = {
                key: value for key, value in payload.items()
                if not str(key).startswith("_")
            }
            self._send_json(HTTPStatus.OK, {**public_payload, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
        finally:
            _BREADTH_BUILD_LOCK.release()

    def _send_stock_ytd(self, query: str) -> None:
        values = urllib.parse.parse_qs(query).get("year", [])
        if len(values) > 1 or (values and not re.fullmatch(r"20\d{2}", values[0])):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_stock_ytd_year"})
            return
        requested_year = int(values[0]) if values else None
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
            cached_payload = _BREADTH_CACHE.get("payload")
            cached_at = _BREADTH_CACHE.get("created_at")
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        cache_hit = (
            isinstance(cached_payload, dict)
            and isinstance(cached_at, (int, float))
            and time.monotonic() - float(cached_at) < BREADTH_CACHE_SECONDS
            and isinstance(cached_payload.get("_stock_ytd_by_year"), dict)
        )
        if not cache_hit:
            if not _BREADTH_BUILD_LOCK.acquire(blocking=False):
                self._send_json(HTTPStatus.CONFLICT, {"ok": False, "reason": "breadth_refresh_in_progress"})
                return
            try:
                cached_payload = self._build_market_breadth(str(api_key), str(access_token))
                with _SESSION_LOCK:
                    _BREADTH_CACHE.clear()
                    _BREADTH_CACHE.update({"payload": cached_payload, "created_at": time.monotonic()})
            except ValueError as error:
                reason = str(error)
                if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                    self._clear_session()
                self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
                return
            finally:
                _BREADTH_BUILD_LOCK.release()

        by_year = cached_payload.get("_stock_ytd_by_year") if isinstance(cached_payload, dict) else None
        if not isinstance(by_year, dict) or not by_year:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": "stock_ytd_unavailable"})
            return
        available_years = sorted((int(year) for year in by_year), reverse=True)
        selected_year = requested_year if requested_year is not None else available_years[0]
        result = by_year.get(selected_year)
        if not isinstance(result, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_stock_ytd_year"})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                **result,
                "available_years": available_years,
                "cache_hit": cache_hit,
                "universe_source": NIFTY500_CONSTITUENTS_URL,
                "price_source": "Kite Connect historical daily candles",
            },
        )

    def _build_market_breadth(self, api_key: str, access_token: str) -> dict[str, object]:
        constituent_request = urllib.request.Request(
            NIFTY500_CONSTITUENTS_URL,
            headers={
                "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
                # The public download endpoint serves its website shell to
                # unknown application user agents. Use an ordinary browser
                # identity, without cookies or access-control workarounds.
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        constituent_csv, reason = self._request_provider_text(
            constituent_request, MAX_CONSTITUENT_BYTES
        )
        if reason is not None:
            raise ValueError(f"constituent_source_{reason}")
        constituents = parse_nifty500_constituents(constituent_csv or "")
        tokens = self._current_equity_tokens(api_key, access_token)
        missing_symbols = [item["symbol"] for item in constituents if item["symbol"] not in tokens]

        now = datetime.now(INDIA_TIMEZONE)
        from_date = now.date() - timedelta(days=NIFTY500_HISTORY_LOOKBACK_DAYS)
        histories: dict[str, list[tuple[date, float]]] = {}
        requested = 0
        for constituent in constituents:
            symbol = constituent["symbol"]
            token = tokens.get(symbol)
            if token is None:
                continue
            if requested:
                time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
            query = urllib.parse.urlencode(
                {"from": from_date.isoformat(), "to": now.date().isoformat(), "continuous": "0", "oi": "0"}
            )
            request = urllib.request.Request(
                f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=token)}?{query}",
                headers={
                    "Authorization": f"token {api_key}:{access_token}",
                    "X-Kite-Version": "3",
                    "Accept": "application/json",
                    "User-Agent": "PG-terminal-local/0.1",
                },
                method="GET",
            )
            provider_payload, reason = self._request_provider_json(
                request,
                exchange=False,
                maximum_bytes=MAX_HISTORICAL_RESPONSE_BYTES,
            )
            requested += 1
            if reason is not None:
                raise ValueError(reason)
            histories[symbol] = parse_daily_closes(
                provider_payload or {}, today=now.date(), now_time=now.time().replace(tzinfo=None)
            )

        rows, as_of, evaluated = calculate_market_breadth(constituents, histories)
        store = _get_eod_store()
        index_histories = {
            str(item["display_name"]): [
                (row["date"], float(row["close"]))
                for row in store.load_candles(
                    kind="index",
                    display_name=str(item["display_name"]),
                )
            ]
            for item in store.list_instruments(kind="index")
        }
        try:
            market_context = calculate_nifty500_market_context(
                constituents,
                histories,
                index_histories,
            )
        except ValueError as error:
            market_context = {
                "ok": False,
                "reason": str(error),
                "as_of_date": as_of.isoformat(),
            }
        if market_context.get("ok") is True:
            store.save_workspace_snapshot(
                snapshot_key="nifty500-market-context",
                as_of_date=as_of,
                payload=market_context,
            )
        monthly_returns = calculate_month_to_date_returns(histories, as_of=as_of)
        stock_ytd_by_year = {
            year: build_stock_ytd_table(constituents, histories, as_of=as_of, year=year)
            for year in range(as_of.year, as_of.year - 5, -1)
        }
        with _SESSION_LOCK:
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.update(
                {"as_of": as_of, "returns": monthly_returns}
            )
            _MONTHLY_LEADERS_CACHE.clear()
        return {
            "ok": True,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "as_of_date": as_of.isoformat(),
            "universe": "NIFTY 500",
            "universe_count": len(constituents),
            "evaluated_count": evaluated,
            "missing_count": len(constituents) - evaluated,
            "unmatched_instrument_count": len(missing_symbols),
            "historical_requests": requested,
            "rows": rows,
            "market_context": market_context,
            "one_day_change_definition": "percentage-point change in share above 20DMA",
            "universe_source": NIFTY500_CONSTITUENTS_URL,
            "price_source": "Kite Connect historical daily candles",
            "_stock_ytd_by_year": stock_ytd_by_year,
        }

    def _current_equity_tokens(self, api_key: str, access_token: str) -> dict[str, str]:
        with _SESSION_LOCK:
            cached = dict(_ACTIVE_EQUITY_TOKENS)
        if cached:
            return cached
        request = urllib.request.Request(
            NSE_INSTRUMENTS_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        csv_payload, reason = self._request_provider_text(request, MAX_INSTRUMENT_BYTES)
        if reason is not None:
            raise ValueError(reason)
        tokens = parse_equity_tokens(csv_payload or "")
        with _SESSION_LOCK:
            _ACTIVE_EQUITY_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.update(tokens)
        return tokens

    def _send_monthly_leaders(self, payload: dict[str, object]) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
            equity_snapshot = dict(_MONTHLY_EQUITY_RETURNS_CACHE)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        raw_symbols = payload.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or not raw_symbols
            or len(raw_symbols) > 250
            or any(
                not isinstance(symbol, str)
                or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
                for symbol in raw_symbols
            )
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_monthly_leader_request"})
            return
        symbols = tuple(sorted(set(raw_symbols)))
        if len(symbols) != len(raw_symbols):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_monthly_leader_request"})
            return

        as_of = equity_snapshot.get("as_of")
        equity_returns = equity_snapshot.get("returns")
        if not isinstance(as_of, date) or not isinstance(equity_returns, dict):
            self._send_json(HTTPStatus.CONFLICT, {"ok": False, "reason": "monthly_stock_data_not_ready"})
            return
        eligible_stock_returns = {
            symbol: float(equity_returns[symbol])
            for symbol in symbols
            if symbol in equity_returns
        }
        if not eligible_stock_returns:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": "monthly_stock_data_unavailable"})
            return

        cache_key = hashlib.sha256("\n".join(symbols).encode("ascii")).hexdigest()
        with _SESSION_LOCK:
            cached_key = _MONTHLY_LEADERS_CACHE.get("key")
            cached_payload = _MONTHLY_LEADERS_CACHE.get("payload")
            cached_at = _MONTHLY_LEADERS_CACHE.get("created_at")
        if (
            cached_key == cache_key
            and isinstance(cached_payload, dict)
            and isinstance(cached_at, (int, float))
            and time.monotonic() - float(cached_at) < SEASONALITY_CACHE_SECONDS
        ):
            self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
            return

        try:
            self._current_index_targets(api_key, access_token)
            with _SESSION_LOCK:
                index_tokens = dict(_ACTIVE_SEASONALITY_INDEX_TOKENS)
            missing = [name for name in SEASONALITY_INDICES if name not in index_tokens]
            if missing:
                raise ValueError("instrument_not_available")
            month_start = date(as_of.year, as_of.month, 1)
            from_date = month_start - timedelta(days=10)
            index_histories: dict[str, list[tuple[date, float]]] = {}
            now = datetime.now(INDIA_TIMEZONE)
            for index, display_name in enumerate(SEASONALITY_INDICES):
                if index:
                    time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                query = urllib.parse.urlencode(
                    {
                        "from": from_date.isoformat(),
                        "to": as_of.isoformat(),
                        "continuous": "0",
                        "oi": "0",
                    }
                )
                request = urllib.request.Request(
                    f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=index_tokens[display_name])}?{query}",
                    headers={
                        "Authorization": f"token {api_key}:{access_token}",
                        "X-Kite-Version": "3",
                        "Accept": "application/json",
                        "User-Agent": "PG-terminal-local/0.1",
                    },
                    method="GET",
                )
                provider_payload, reason = self._request_provider_json(request, exchange=False)
                if reason is not None:
                    raise ValueError(reason)
                index_histories[display_name] = parse_daily_closes(
                    provider_payload or {},
                    today=now.date(),
                    now_time=now.time().replace(tzinfo=None),
                )
            index_returns = calculate_month_to_date_returns(index_histories, as_of=as_of)
            if "Nifty 50" not in index_returns or not index_returns:
                raise ValueError("monthly_index_data_unavailable")
            best_index = max(index_returns.items(), key=lambda item: (item[1], item[0]))
            best_stock = max(eligible_stock_returns.items(), key=lambda item: (item[1], item[0]))
            result: dict[str, object] = {
                "ok": True,
                "as_of_date": as_of.isoformat(),
                "month": as_of.strftime("%B %Y"),
                "nifty50_mtd_pct": index_returns["Nifty 50"],
                "best_index": {"instrument": best_index[0], "return_pct": best_index[1]},
                "best_stock": {"instrument": best_stock[0], "return_pct": best_stock[1]},
                "indices_evaluated": len(index_returns),
                "fo_stocks_evaluated": len(eligible_stock_returns),
                "return_definition": "last completed close versus previous month final close",
            }
            with _SESSION_LOCK:
                _MONTHLY_LEADERS_CACHE.clear()
                _MONTHLY_LEADERS_CACHE.update(
                    {"key": cache_key, "payload": result, "created_at": time.monotonic()}
                )
            self._send_json(HTTPStatus.OK, {**result, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})

    def _send_historical_month_leaders(self, payload: dict[str, object]) -> None:
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return

        raw_symbols = payload.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or not raw_symbols
            or len(raw_symbols) > 250
            or any(
                not isinstance(symbol, str)
                or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
                for symbol in raw_symbols
            )
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_historical_month_leader_request"},
            )
            return
        symbols = tuple(sorted(set(raw_symbols)))
        if len(symbols) != len(raw_symbols):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_historical_month_leader_request"},
            )
            return

        selected_month = payload.get("month")
        if (
            not isinstance(selected_month, int)
            or isinstance(selected_month, bool)
            or selected_month < 1
            or selected_month > 12
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_historical_month_leader_request"},
            )
            return

        now = datetime.now(INDIA_TIMEZONE)
        price_history_through = completed_history_date(now)
        cache_key = hashlib.sha256(
            f"{selected_month}\n{SEASONALITY_LOOKBACK_YEARS}\n".encode("ascii")
            + "\n".join(symbols).encode("ascii")
        ).hexdigest()
        with _SESSION_LOCK:
            cached_key = _HISTORICAL_MONTH_LEADERS_CACHE.get("key")
            cached_payload = _HISTORICAL_MONTH_LEADERS_CACHE.get("payload")
        if (
            cached_key == cache_key
            and isinstance(cached_payload, dict)
            and cached_payload.get("price_history_requested_through")
            == price_history_through.isoformat()
        ):
            self._send_json(HTTPStatus.OK, {**cached_payload, "cache_hit": True})
            return
        if not _HISTORICAL_MONTH_LEADERS_LOCK.acquire(blocking=False):
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "historical_rank_refresh_in_progress"},
            )
            return

        try:
            self._current_index_targets(api_key, access_token)
            with _SESSION_LOCK:
                index_tokens = dict(_ACTIVE_SEASONALITY_INDEX_TOKENS)
            equity_tokens = self._current_equity_tokens(api_key, access_token)
            if any(name not in index_tokens for name in SEASONALITY_INDICES):
                raise ValueError("instrument_not_available")
            if any(symbol not in equity_tokens for symbol in symbols):
                raise ValueError("instrument_not_available")

            month_index = selected_month - 1
            index_averages: dict[str, tuple[float, int]] = {}
            stock_averages: dict[str, tuple[float, int]] = {}
            total_requests = 0
            history_start = historical_lookback_start(now.date())
            store = _get_eod_store()

            def evaluate(kind: str, instrument: str, token: str) -> tuple[float, int] | None:
                nonlocal total_requests
                coverage = store.coverage(kind=kind, display_name=instrument)
                last_stored = coverage["last_session"]
                needs_sync = last_stored is None or last_stored < price_history_through
                with _SESSION_LOCK:
                    cache_item = _SEASONALITY_CACHE.get((kind, instrument))
                cached = None
                if cache_item and time.monotonic() - float(cache_item["created_at"]) < SEASONALITY_CACHE_SECONDS:
                    cached = cache_item.get("payload")
                if needs_sync:
                    if total_requests:
                        time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                    try:
                        cached = self._build_seasonality(
                            api_key, access_token, token, kind, instrument
                        )
                    except ValueError as error:
                        if str(error) == "no_completed_historical_data":
                            return None
                        raise
                    total_requests += int(cached.get("historical_requests", 0))
                elif not isinstance(cached, dict):
                    stored_candles = store.load_candles(
                        kind=kind,
                        display_name=instrument,
                        start=history_start,
                        end=now.date(),
                    )
                    if len(stored_candles) >= 2:
                        month_rows, _weekday_rows = calculate_seasonality(
                            stored_candles, today=now.date()
                        )
                        cached = {"month_rows": month_rows, "historical_requests": 0}
                    else:
                        if total_requests:
                            time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                        try:
                            cached = self._build_seasonality(
                                api_key, access_token, token, kind, instrument
                            )
                        except ValueError as error:
                            if str(error) == "no_completed_historical_data":
                                return None
                            raise
                        total_requests += int(cached.get("historical_requests", 0))
                    if is_complete_seasonality_payload(cached):
                        with _SESSION_LOCK:
                            _SEASONALITY_CACHE[(kind, instrument)] = {
                                "payload": cached,
                                "created_at": time.monotonic(),
                            }
                month_rows = cached.get("month_rows")
                if not isinstance(month_rows, list) or len(month_rows) != 12:
                    raise ValueError("invalid_provider_response")
                row = month_rows[month_index]
                if not isinstance(row, dict):
                    raise ValueError("invalid_provider_response")
                count = row.get("count")
                average = row.get("average_return_pct")
                if not isinstance(count, int) or count < 1 or not isinstance(average, (int, float)):
                    return None
                return float(average), count

            for instrument in SEASONALITY_INDICES:
                value = evaluate("index", instrument, index_tokens[instrument])
                if value is not None:
                    index_averages[instrument] = value
            for symbol in symbols:
                value = evaluate("stock", symbol, equity_tokens[symbol])
                if value is not None:
                    stock_averages[symbol] = value

            index_rank = rank_historical_month_averages(index_averages)
            stock_rank = rank_historical_month_averages(stock_averages)
            result: dict[str, object] = {
                "ok": True,
                "calendar_month": date(2000, selected_month, 1).strftime("%B"),
                "month": selected_month,
                "completed_year": now.year - 1,
                "history_start": historical_lookback_start(now.date()).isoformat(),
                "lookback_years": SEASONALITY_LOOKBACK_YEARS,
                "completed_through": (date(now.year, now.month, 1) - timedelta(days=1)).isoformat(),
                "index": index_rank,
                "stock": stock_rank,
                "indices_requested": len(SEASONALITY_INDICES),
                "stocks_requested": len(symbols),
                "indices_without_history": len(SEASONALITY_INDICES) - int(index_rank["evaluated"]),
                "stocks_without_history": len(symbols) - int(stock_rank["evaluated"]),
                "historical_requests": total_requests,
                "price_history_requested_through": price_history_through.isoformat(),
                "return_definition": "mean close-to-close return for the selected calendar month across completed years",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
            with _SESSION_LOCK:
                _HISTORICAL_MONTH_LEADERS_CACHE.clear()
                _HISTORICAL_MONTH_LEADERS_CACHE.update({"key": cache_key, "payload": result})
            self._send_json(HTTPStatus.OK, {**result, "cache_hit": False})
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
        finally:
            _HISTORICAL_MONTH_LEADERS_LOCK.release()

    def _send_institutional_flow_refresh(self) -> None:
        request = urllib.request.Request(
            NSE_FII_DII_URL,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.nseindia.com/reports/fii-dii",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        text_payload, reason = self._request_provider_text(request, MAX_RESPONSE_BYTES)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "institutional_flow_source_unavailable"},
            )
            return
        try:
            parsed_payload = json.loads(text_payload or "")
            rows = parse_institutional_flows(parsed_payload, today=datetime.now(INDIA_TIMEZONE).date())
            store = _get_eod_store()
            write_result = store.append_institutional_flows(
                rows,
                source=NSE_FII_DII_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_institutional_flow_summary(store.load_institutional_flows())
        except InstitutionalFlowConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_institutional_flow_conflict"},
            )
            return
        except (json.JSONDecodeError, ValueError):
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_institutional_flow_response"},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {"ok": True, **summary, "write_result": write_result},
        )

    def _send_confirmed_fpi_refresh(self) -> None:
        request = urllib.request.Request(
            NSDL_FPI_MONTHLY_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://www.fpi.nsdl.co.in/",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        text_payload, reason = self._request_provider_text(request, NSDL_MAX_RESPONSE_BYTES)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "confirmed_fpi_source_unavailable"},
            )
            return
        try:
            now = datetime.now(INDIA_TIMEZONE)
            rows = parse_nsdl_confirmed_fpi(text_payload or "", today=now.date())
            store = _get_eod_store()
            write_result = store.append_confirmed_fpi_investments(
                rows,
                source=NSDL_FPI_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_confirmed_fpi_summary(
                store.load_confirmed_fpi_investments(), today=now.date()
            )
        except ConfirmedFpiConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_confirmed_fpi_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_confirmed_fpi_response"},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True, **summary, "write_result": write_result})

    def _send_macro_context_refresh(self) -> None:
        request = urllib.request.Request(
            RBI_HOME_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        text_payload, reason = self._request_provider_text(request, RBI_MAX_RESPONSE_BYTES)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "rbi_macro_source_unavailable"},
            )
            return
        try:
            rows = parse_rbi_macro_snapshot(text_payload or "")
            store = _get_eod_store()
            write_result = store.append_macro_snapshots(
                rows,
                source=RBI_MACRO_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_macro_context_summary(store.load_macro_snapshots())
        except MacroSnapshotConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_macro_snapshot_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_rbi_macro_response"},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True, **summary, "write_result": write_result})

    def _send_global_risk_refresh(self) -> None:
        today = datetime.now(INDIA_TIMEZONE).date()
        earliest = today - timedelta(days=460)
        query = urllib.parse.urlencode(
            {"id": ",".join(FRED_GLOBAL_SERIES), "cosd": earliest.isoformat()}
        )
        request = urllib.request.Request(
            f"{FRED_GRAPH_CSV_URL}?{query}",
            headers={
                "Accept": "application/zip,text/csv,*/*",
                "User-Agent": NIFTY_INDICES_PUBLIC_USER_AGENT,
            },
            method="GET",
        )
        zip_payload, reason = self._request_fred_export(request)
        if reason is not None:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "global_risk_source_unavailable"},
            )
            return
        try:
            rows = parse_fred_global_zip(zip_payload or b"", today=today, earliest=earliest)
            store = _get_eod_store()
            write_result = store.append_global_risk_observations(
                rows,
                source=FRED_GLOBAL_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_global_risk_summary(store.load_global_risk_observations())
        except GlobalRiskConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_global_risk_conflict"},
            )
            return
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "invalid_fred_global_response"},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True, **summary, "write_result": write_result})

    def _send_futures_eod_refresh(self, payload: dict[str, object]) -> None:
        raw_symbols = payload.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or not raw_symbols
            or len(raw_symbols) > 250
            or any(
                not isinstance(symbol, str)
                or not re.fullmatch(r"[A-Z0-9&-]{1,32}", symbol)
                for symbol in raw_symbols
            )
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_futures_universe"})
            return
        symbols = tuple(raw_symbols)
        if len(set(symbols)) != len(symbols):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_futures_universe"})
            return
        with _SESSION_LOCK:
            session = dict(_ACTIVE_KITE_SESSION)
        api_key = session.get("api_key")
        access_token = session.get("access_token")
        if not api_key or not access_token:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "kite_not_connected"})
            return
        now = datetime.now(INDIA_TIMEZONE)
        completed_through = completed_history_date(now)
        while completed_through.weekday() >= 5:
            completed_through -= timedelta(days=1)
        instrument_request = urllib.request.Request(
            NFO_INSTRUMENTS_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "text/csv",
                "Accept-Encoding": "identity",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        csv_payload, reason = self._request_provider_text(instrument_request, MAX_NFO_INSTRUMENT_BYTES)
        if reason is not None:
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return
        try:
            contracts, inventory_missing = parse_near_month_stock_futures(
                csv_payload or "", symbols, as_of=now.date()
            )
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": str(error)})
            return
        if not contracts:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": "futures_contracts_unavailable"})
            return
        try:
            if now.time().replace(tzinfo=None) >= datetime_time(15, 40):
                quote_query = urllib.parse.urlencode(
                    [("i", f"NFO:{contract['tradingsymbol']}") for contract in contracts]
                )
                quote_request = urllib.request.Request(
                    f"{FULL_QUOTE_URL}?{quote_query}",
                    headers={
                        "Authorization": f"token {api_key}:{access_token}",
                        "X-Kite-Version": "3",
                        "Accept": "application/json",
                        "User-Agent": "PG-terminal-local/0.1",
                    },
                    method="GET",
                )
                provider_payload, reason = self._request_provider_json(
                    quote_request, exchange=False, maximum_bytes=MAX_QUOTE_RESPONSE_BYTES
                )
                if reason is not None:
                    raise ValueError(reason)
                snapshots, quote_missing = normalize_futures_eod_quotes(
                    provider_payload or {}, contracts, now=now
                )
                retrieval_mode = "post_close_bulk_quote"
            else:
                snapshots = []
                quote_missing = []
                history_start = completed_through - timedelta(days=10)
                for index, contract in enumerate(contracts):
                    if index:
                        time.sleep(HISTORICAL_REQUEST_INTERVAL_SECONDS)
                    history_query = urllib.parse.urlencode(
                        {
                            "from": history_start.isoformat(),
                            "to": completed_through.isoformat(),
                            "continuous": "0",
                            "oi": "1",
                        }
                    )
                    history_request = urllib.request.Request(
                        f"{HISTORICAL_URL_TEMPLATE.format(instrument_token=contract['instrument_token'])}?{history_query}",
                        headers={
                            "Authorization": f"token {api_key}:{access_token}",
                            "X-Kite-Version": "3",
                            "Accept": "application/json",
                            "User-Agent": "PG-terminal-local/0.1",
                        },
                        method="GET",
                    )
                    history_payload, reason = self._request_provider_json(
                        history_request,
                        exchange=False,
                        maximum_bytes=MAX_HISTORICAL_RESPONSE_BYTES,
                    )
                    if reason is not None:
                        if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                            raise ValueError(reason)
                        quote_missing.append(str(contract["underlying"]))
                        continue
                    snapshot = parse_futures_daily_snapshot(
                        history_payload or {}, contract, completed_through=completed_through
                    )
                    if snapshot is None:
                        quote_missing.append(str(contract["underlying"]))
                    else:
                        snapshots.append(snapshot)
                retrieval_mode = "latest_completed_history"
            if not snapshots:
                raise ValueError("futures_eod_data_unavailable")
            store = _get_eod_store()
            write_result = store.append_futures_eod_snapshots(
                contracts,
                snapshots,
                source=KITE_FUTURES_SOURCE,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            summary = calculate_futures_oi_summary(store.load_futures_eod_snapshots())
        except FuturesSnapshotConflictError:
            self._send_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "reason": "stored_futures_snapshot_conflict"},
            )
            return
        except ValueError as error:
            reason = str(error)
            if reason in {"access_token_invalid_or_expired", "authentication_failed"}:
                self._clear_session()
            self._send_json(HTTPStatus.BAD_GATEWAY, {"ok": False, "reason": reason})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                **summary,
                "requested_count": len(symbols),
                "contract_count": len(contracts),
                "snapshot_count": len(snapshots),
                "inventory_missing": inventory_missing,
                "quote_missing": quote_missing,
                "retrieval_mode": retrieval_mode,
                "completed_through": completed_through.isoformat(),
                "write_result": write_result,
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        if self.path == "/api/portfolio/preview":
            payload = self._read_json_payload(MAX_PORTFOLIO_IMPORT_BYTES)
            if payload is not None:
                self._send_portfolio_preview(payload)
            return

        if self.path == "/api/portfolio/analyze":
            payload = self._read_json_payload(MAX_PORTFOLIO_IMPORT_BYTES)
            if payload is not None:
                self._send_portfolio_analysis(payload)
            return

        if self.path == "/api/earnings/import":
            payload = self._read_json_payload(MAX_EARNINGS_IMPORT_BYTES)
            if payload is not None:
                self._send_earnings_import(payload)
            return

        if self.path == "/api/news-events/nse-manual-import":
            payload = self._read_json_payload(MAX_NEWS_IMPORT_BYTES)
            if payload is not None:
                self._send_nse_manual_import(payload)
            return

        if self.path == "/api/market-sentiment/factor-snapshot":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_sentiment_factor_snapshot()
            return

        if self.path == "/api/market-sentiment/futures-eod/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_futures_eod_refresh(payload)
            return

        if self.path == "/api/market-sentiment/macro-context/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_macro_context_refresh()
            return

        if self.path == "/api/market-sentiment/global-risk/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_global_risk_refresh()
            return

        if self.path == "/api/market-sentiment/institutional-flows/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_institutional_flow_refresh()
            return

        if self.path == "/api/market-sentiment/confirmed-fpi/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_confirmed_fpi_refresh()
            return

        if self.path == "/api/historical-regimes/official-history/refresh":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_historical_series_refresh()
            return

        if self.path == "/api/kite/historical-month-leaders":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_historical_month_leaders(payload)
            return

        if self.path == "/api/kite/monthly-leaders":
            payload = self._read_json_payload()
            if payload is not None:
                self._send_monthly_leaders(payload)
            return

        if self.path == "/api/kite/disconnect":
            payload = self._read_json_payload()
            if payload is None:
                return
            with _SESSION_LOCK:
                _ACTIVE_KITE_SESSION.clear()
                _ACTIVE_INDEX_TARGETS.clear()
                _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
                _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
                _ACTIVE_EQUITY_TOKENS.clear()
                _BREADTH_CACHE.clear()
                _SEASONALITY_CACHE.clear()
                _MONTHLY_EQUITY_RETURNS_CACHE.clear()
                _MONTHLY_LEADERS_CACHE.clear()
                _HISTORICAL_MONTH_LEADERS_CACHE.clear()
                _REGIME_VALIDATION_CACHE.clear()
                _CROSS_INDEX_VALIDATION_CACHE.clear()
                _KITE_DIAGNOSTICS["last_error"] = None
            print("Kite session state: disconnected", flush=True)
            self._send_json(HTTPStatus.OK, {"ok": True, "connected": False})
            return

        if self.path not in {"/api/kite/session", "/api/kite/validate"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not_found"})
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        if self.path == "/api/kite/session":
            self._exchange_and_connect(payload)
        else:
            self._validate_existing_token(payload)

    def _exchange_and_connect(self, payload: dict[str, object]) -> None:
        api_key = payload.get("api_key")
        api_secret = payload.get("api_secret")
        request_token_input = payload.get("request_token")
        if (
            not self._valid_credential(api_key, 256)
            or not self._valid_credential(api_secret, 512)
            or not self._valid_credential(request_token_input, 4096)
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "missing_or_invalid_credentials"},
            )
            return

        request_token = extract_request_token(request_token_input)
        if not self._valid_credential(request_token, 2048):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "request_token_not_found"},
            )
            return

        form_body = urllib.parse.urlencode(
            {
                "api_key": api_key,
                "request_token": request_token,
                "checksum": build_checksum(api_key, request_token, api_secret),
            }
        ).encode("ascii")
        request = urllib.request.Request(
            TOKEN_URL,
            data=form_body,
            headers={
                "X-Kite-Version": "3",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="POST",
        )

        provider_payload, reason = self._request_provider_json(request, exchange=True)
        if reason is not None:
            self._clear_session()
            self._set_last_error(reason)
            print(f"Kite token exchange: {reason}", flush=True)
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": reason})
            return

        data = provider_payload.get("data") if isinstance(provider_payload, dict) else None
        access_token = data.get("access_token") if isinstance(data, dict) else None
        if not self._valid_credential(access_token, 2048):
            self._clear_session()
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "reason": "access_token_missing_from_provider"},
            )
            return

        profile_reason = self._profile_failure_reason(api_key, access_token)
        if profile_reason is not None:
            self._clear_session()
            self._set_last_error(profile_reason)
            print(f"Kite profile verification: {profile_reason}", flush=True)
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "reason": profile_reason},
            )
            return

        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_KITE_SESSION.update({"api_key": api_key, "access_token": access_token})
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _SEASONALITY_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_LEADERS_CACHE.clear()
            _HISTORICAL_MONTH_LEADERS_CACHE.clear()
            _REGIME_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.clear()
            _KITE_DIAGNOSTICS["last_error"] = None
        print("Kite session state: authenticated", flush=True)
        self._send_json(HTTPStatus.OK, {"ok": True, "connected": True})

    def _validate_existing_token(self, payload: dict[str, object]) -> None:
        api_key = payload.get("api_key")
        access_token = payload.get("access_token")
        if not self._valid_credential(api_key, 256) or not self._valid_credential(access_token, 2048):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "missing_or_invalid_credentials"},
            )
            return

        reason = self._profile_failure_reason(api_key, access_token)
        if reason is not None:
            self._clear_session()
            self._set_last_error(reason)
            print(f"Kite profile verification: {reason}", flush=True)
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": reason})
            return

        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_KITE_SESSION.update({"api_key": api_key, "access_token": access_token})
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _SEASONALITY_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_LEADERS_CACHE.clear()
            _HISTORICAL_MONTH_LEADERS_CACHE.clear()
            _REGIME_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.clear()
            _KITE_DIAGNOSTICS["last_error"] = None
        print("Kite session state: authenticated", flush=True)
        self._send_json(HTTPStatus.OK, {"ok": True, "connected": True})

    def _profile_failure_reason(self, api_key: str, access_token: str) -> str | None:
        request = urllib.request.Request(
            PROFILE_URL,
            headers={
                "Authorization": f"token {api_key}:{access_token}",
                "X-Kite-Version": "3",
                "Accept": "application/json",
                "User-Agent": "PG-terminal-local/0.1",
            },
            method="GET",
        )
        payload, reason = self._request_provider_json(request, exchange=False)
        if reason is not None:
            return reason
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "success"
            or not isinstance(payload.get("data"), dict)
        ):
            return "invalid_provider_response"
        return None

    def _request_provider_json(
        self,
        request: urllib.request.Request,
        *,
        exchange: bool,
        maximum_bytes: int = MAX_RESPONSE_BYTES,
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            with _PROVIDER_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
                    return None, "provider_response_too_large"
                payload = json.loads(body.decode("utf-8"))
                if response.status != HTTPStatus.OK or not isinstance(payload, dict):
                    return None, "invalid_provider_response"
                return payload, None
        except urllib.error.HTTPError as error:
            return None, self._classify_provider_error(error, exchange=exchange)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            return None, classify_network_error(error)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None, "invalid_provider_response"

    def _request_provider_text(
        self,
        request: urllib.request.Request,
        maximum_bytes: int,
    ) -> tuple[str | None, str | None]:
        try:
            with _PROVIDER_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(maximum_bytes + 1)
                if len(body) > maximum_bytes:
                    return None, "provider_response_too_large"
                if response.status != HTTPStatus.OK:
                    return None, "invalid_provider_response"
                return body.decode("utf-8-sig"), None
        except urllib.error.HTTPError as error:
            return None, self._classify_provider_error(error, exchange=False)
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            return None, classify_network_error(error)
        except (UnicodeDecodeError, ValueError):
            return None, "invalid_provider_response"

    def _request_fred_export(
        self, request: urllib.request.Request
    ) -> tuple[bytes | None, str | None]:
        """Fetch the fixed public FRED export, allowing its standard HTTPS redirect handling."""
        last_error: BaseException | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    final_host = (urllib.parse.urlsplit(response.geturl()).hostname or "").lower()
                    if final_host != "fred.stlouisfed.org" or response.status != HTTPStatus.OK:
                        return None, "invalid_provider_response"
                    body = response.read(FRED_MAX_RESPONSE_BYTES + 1)
                    if len(body) > FRED_MAX_RESPONSE_BYTES:
                        return None, "provider_response_too_large"
                    return body, None
            except urllib.error.HTTPError as error:
                return None, self._classify_provider_error(error, exchange=False)
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        return None, classify_network_error(last_error or OSError("fred_request_failed"))

    @staticmethod
    def _classify_provider_error(error: urllib.error.HTTPError, *, exchange: bool) -> str:
        error_type = ""
        try:
            body = error.read(MAX_RESPONSE_BYTES + 1)
            if len(body) <= MAX_RESPONSE_BYTES:
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, dict):
                    error_type = str(payload.get("error_type", ""))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass

        if error_type == "TokenException":
            return "request_token_invalid_expired_or_used" if exchange else "access_token_invalid_or_expired"
        if error_type == "InputException":
            return "token_exchange_input_rejected" if exchange else "provider_input_rejected"
        if error_type == "PermissionException":
            return "profile_access_denied"
        if error.code in (401, 403):
            return "authentication_failed"
        return "provider_rejected_request"

    def _send_nse_manual_import(self, payload: dict[str, object]) -> None:
        file_name = payload.get("file_name")
        csv_text = payload.get("csv_text")
        if (
            not isinstance(file_name, str)
            or not re.fullmatch(r"[A-Za-z0-9._ -]{1,128}\.csv", file_name)
            or not isinstance(csv_text, str)
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_nse_announcement_import"},
            )
            return
        try:
            parsed = parse_nse_announcement_csv(csv_text)
            store = _get_eod_store()
            write_result = store.append_news_event_records(
                parsed,
                source_file_name=file_name,
            )
            workspace = build_news_events_workspace(
                reviewed_on=datetime.now(INDIA_TIMEZONE).date(),
                live_items=store.load_news_event_records(),
            )
        except ValueError as error:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": str(error)},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {**workspace, "write_result": write_result},
        )

    def _send_earnings_import(self, payload: dict[str, object]) -> None:
        file_name = payload.get("file_name")
        csv_text = payload.get("csv_text")
        if (
            not isinstance(file_name, str)
            or not re.fullmatch(r"[A-Za-z0-9._ -]{1,128}\.csv", file_name)
            or not isinstance(csv_text, str)
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_earnings_import"})
            return
        try:
            parsed = parse_earnings_csv(csv_text)
            store = _get_eod_store()
            write_result = store.append_earnings_records(parsed, source_file_name=file_name)
            workspace = build_earnings_analysis(store.load_earnings_records())
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": str(error)})
            return
        self._send_json(HTTPStatus.OK, {**workspace, "write_result": write_result})

    def _send_portfolio_preview(self, payload: dict[str, object]) -> None:
        file_name = payload.get("file_name")
        encoded = payload.get("content_base64")
        if (
            not isinstance(file_name, str)
            or not re.fullmatch(r"[A-Za-z0-9._ ()&-]{1,128}\.(?:csv|xlsx)", file_name, re.IGNORECASE)
            or not isinstance(encoded, str)
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_portfolio_file"})
            return
        try:
            raw = base64.b64decode(encoded, validate=True)
            preview = parse_portfolio_file(file_name, raw)
        except (ValueError, binascii.Error) as error:
            reason = str(error) if isinstance(error, ValueError) else "invalid_portfolio_file"
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": reason})
            return
        self._send_json(HTTPStatus.OK, preview)

    def _send_portfolio_analysis(self, payload: dict[str, object]) -> None:
        rows = payload.get("rows")
        mapping = payload.get("mapping")
        use_google_finance = payload.get("use_google_finance") is True
        refresh_prices = payload.get("refresh_prices") is True
        if (
            not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or not isinstance(mapping, dict)
        ):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_portfolio_rows"})
            return
        normalized_symbols = {
            re.sub(r"-(EQ|BE|RR)$", "", re.sub(r"^(NSE:|BSE:)", "", str(row.get(str(mapping.get("symbol")), "")).strip().upper()))
            for row in rows
        }
        store = _get_eod_store()
        stock_inventory = {str(item["display_name"]) for item in store.list_instruments(kind="stock")}
        histories = {
            symbol: store.load_candles(kind="stock", display_name=symbol)
            for symbol in normalized_symbols
            if symbol in stock_inventory
        }
        benchmark_history = store.load_candles(kind="index", display_name="Nifty 50")
        valuation_date = datetime.now(INDIA_TIMEZONE).date()
        gsec_history, gsec_reason = fetch_nifty_gsec_total_return_history(valuation_date)
        name_column = mapping.get("name")
        resolved_amfi_by_row: dict[int, dict[str, object]] = {}
        if isinstance(name_column, str):
            for row_number, row in enumerate(rows, start=2):
                scheme = resolve_portfolio_amfi_scheme(str(row.get(name_column) or ""))
                if scheme is not None:
                    resolved_amfi_by_row[row_number] = scheme
        amfi_histories, amfi_failures = fetch_amfi_portfolio_nav_histories(
            list(resolved_amfi_by_row.values()),
            valuation_date,
        )
        position_history_overrides = {
            row_number: {
                "history": amfi_histories.get(str(scheme["scheme_code"]), []),
                "scheme_code": scheme["scheme_code"],
                "scheme_name": scheme["name"],
                "source": "AMFI",
                "source_url": AMFI_NAV_SOURCE_URL,
            }
            for row_number, scheme in resolved_amfi_by_row.items()
            if amfi_histories.get(str(scheme["scheme_code"]))
        }
        if use_google_finance:
            google_quotes, quote_failures = fetch_google_finance_quotes(normalized_symbols)
        else:
            google_quotes, quote_failures = {}, {}
        fno_symbols = {
            str(item.get("underlying") or "").upper()
            for item in store.load_futures_eod_snapshots()
            if item.get("underlying")
        }
        try:
            result = build_portfolio_analysis(
                rows,
                mapping,
                histories,
                fno_symbols=fno_symbols,
                market_quotes=google_quotes,
                benchmark_history=benchmark_history,
                gsec_benchmark_history=gsec_history,
                position_history_overrides=position_history_overrides,
                valuation_date=valuation_date,
                refresh_prices=refresh_prices,
            )
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": str(error)})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                **result,
                "google_finance_source_status": (
                    "available" if google_quotes else (
                        "unavailable" if use_google_finance else "disabled"
                    )
                ),
                "google_finance_source_url": "https://www.google.com/finance/",
                "google_finance_failures": quote_failures,
                "gsec_benchmark_source_status": "available" if gsec_history else "unavailable",
                "gsec_benchmark_source_reason": gsec_reason,
                "amfi_nav_source_status": (
                    "available" if position_history_overrides else (
                        "unavailable" if resolved_amfi_by_row else "not_applicable"
                    )
                ),
                "amfi_nav_source_url": AMFI_NAV_SOURCE_URL,
                "amfi_nav_resolved_positions": len(position_history_overrides),
                "amfi_nav_requested_positions": len(resolved_amfi_by_row),
                "amfi_nav_failures": amfi_failures,
                "price_refresh_requested": refresh_prices,
            },
        )

    def _read_json_payload(
        self, maximum_bytes: int = MAX_REQUEST_BYTES
    ) -> dict[str, object] | None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"ok": False, "reason": "invalid_content_type"},
            )
            return None

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if content_length <= 0 or content_length > maximum_bytes:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "reason": "invalid_request_size"},
            )
            return None

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "invalid_json"})
            return None
        return payload

    @staticmethod
    def _valid_credential(value: object, maximum_length: int) -> bool:
        return (
            isinstance(value, str)
            and 0 < len(value) <= maximum_length
            and value.strip() == value
            and all(character.isprintable() for character in value)
        )

    @staticmethod
    def _clear_session() -> None:
        with _SESSION_LOCK:
            _ACTIVE_KITE_SESSION.clear()
            _ACTIVE_INDEX_TARGETS.clear()
            _ACTIVE_DASHBOARD_INDEX_TOKENS.clear()
            _ACTIVE_SEASONALITY_INDEX_TOKENS.clear()
            _ACTIVE_EQUITY_TOKENS.clear()
            _BREADTH_CACHE.clear()
            _SEASONALITY_CACHE.clear()
            _MONTHLY_EQUITY_RETURNS_CACHE.clear()
            _MONTHLY_LEADERS_CACHE.clear()
            _HISTORICAL_MONTH_LEADERS_CACHE.clear()
            _REGIME_VALIDATION_CACHE.clear()
            _CROSS_INDEX_VALIDATION_CACHE.clear()

    @staticmethod
    def _set_last_error(reason: str) -> None:
        with _SESSION_LOCK:
            _KITE_DIAGNOSTICS["last_error"] = reason

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Never log POST request lines, bodies, or headers.
        if self.command == "GET" and not self.path.startswith("/api/"):
            super().log_message(format, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local PG-terminal server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8510, type=int)
    args = parser.parse_args()

    static_directory = str(Path(__file__).resolve().parent / "dist")

    def handler(*handler_args, **handler_kwargs):
        return PGTerminalHandler(
            *handler_args,
            static_directory=static_directory,
            **handler_kwargs,
        )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"PG-terminal available at http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
