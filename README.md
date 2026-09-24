# PG-terminal

An original, TradingQnA-inspired web frame for a private market terminal.

Run `python server.py` and open `http://127.0.0.1:8510/`. The local server serves
the interface, exchanges the owner-entered Kite request token for the daily
access token, and verifies the read-only profile endpoint. The API secret is used
only for the token checksum and is never retained. The API key and access token
remain only in server-process memory and are not written to files or logs. The
Current workflows are read-only. Seasonality now stores validated completed
daily candles in a local append-only SQLite database and requests only newer
sessions on later loads; the same persistent foundation will next be extended
to dashboard and breadth workflows.

See [docs/PROJECT_MILESTONES.md](docs/PROJECT_MILESTONES.md) for the recorded
build sequence, completion criteria, and deferred features.
Use [docs/TRADING_DECISION_FRAMEWORK.md](docs/TRADING_DECISION_FRAMEWORK.md) as
the standard reasoning process for interpreting seasonality and future trading
evidence.
The proposed architecture and validation plan for the next page is recorded in
[docs/MARKET_SENTIMENT_BLUEPRINT.md](docs/MARKET_SENTIMENT_BLUEPRINT.md).

All pages must load `dist/styles.css` after their page-specific styles. It is the
shared typography contract for the 14px body, 16–18px headings, and 13px
secondary text.
