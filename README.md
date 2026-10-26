# PG-terminal

An original, TradingQnA-inspired web frame for a private market terminal.

Run `python server.py` and open `http://127.0.0.1:8510/`. The local server serves
the interface, exchanges the owner-entered Kite request token for the daily
access token, and verifies the read-only profile endpoint. The API secret is used
only for the token checksum and is never retained. The API key and access token
remain only in server-process memory and are not written to files or logs. The
current workflows are read-only. Completed-session market history, reviewed
evidence and workspace snapshots use the local SQLite data foundation; missing,
partial and stale observations remain explicit.

Use [docs/OPERATIONS.md](docs/OPERATIONS.md) for startup, navigation, command
palette, Kite/EOD workflows, portfolio-ledger behaviour, backup/recovery,
troubleshooting and final-delivery checks.

See [docs/PROJECT_MILESTONES.md](docs/PROJECT_MILESTONES.md) for the recorded
build sequence, completion criteria, and deferred features.
Use [docs/TRADING_DECISION_FRAMEWORK.md](docs/TRADING_DECISION_FRAMEWORK.md) as
the standard reasoning process for interpreting seasonality and future trading
evidence.
The proposed architecture and validation plan for the next page is recorded in
[docs/MARKET_SENTIMENT_BLUEPRINT.md](docs/MARKET_SENTIMENT_BLUEPRINT.md).

All pages load `dist/styles.css` after page-specific styles. It contains the
shared terminal shell, dual themes, compact Calibri typography, accessibility
states and workspace composition rules.
