# PG-terminal

An original, TradingQnA-inspired web frame for a private market terminal.

Run `python server.py` and open `http://127.0.0.1:8510/`. The local server serves
the interface, exchanges the owner-entered Kite request token for the daily
access token, and verifies the read-only profile endpoint. The API secret is used
only for the token checksum and is never retained. The API key and access token
remain only in server-process memory and are not written to files or logs. EOD
updates are not connected yet.

All pages must load `dist/styles.css` after their page-specific styles. It is the
shared typography contract for the 14px body, 16–18px headings, and 13px
secondary text.
