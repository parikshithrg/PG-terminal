# PG-terminal operations guide

Updated: 2026-10-26

PG-terminal is a local, read-only market-research workspace. It does not place
orders, control a broker account, publish recommendations, or replace missing
evidence with neutral estimates.

## 1. Start and stop the workspace

From the repository root:

```bash
python3 server.py
```

Open `http://127.0.0.1:8510/`. Stop the server with `Ctrl+C` in the terminal
that started it. Run only one server process against the live database unless a
separate database path is deliberately being tested.

The local database is `data/pg_terminal_eod.sqlite3`. Market history and
reviewed evidence are stored there; Kite credentials are not.

## 2. Health check

```bash
curl --fail http://127.0.0.1:8510/api/health
```

This endpoint makes no provider requests. A ready response requires:

- SQLite `PRAGMA quick_check(1)` returns `ok`;
- the database remains in WAL journal mode;
- `index.html`, `styles.css`, `reference-universes.js`, and
  `earnings-template.csv` exist in `dist/`;
- the EOD retry and verified-backup contracts are active.

HTTP 503 means the local application is degraded. Read every reported failure;
do not manufacture a value or delete evidence merely to make health pass.

## 3. Terminal navigation

The sidebar opens these workspaces:

1. Dashboard — joined current-market and portfolio story.
2. Market Sentiment — regime, breadth, price, flow, currency/rates and global-risk evidence.
3. F&O — same-contract futures price/open-interest observations.
4. Screener — transparent price, trend and Nifty-relative diagnostics.
5. Seasonality Analysis — calendar effects with chronological holdout checks.
6. Earnings Analysis — imported filing evidence and comparable-quarter breadth.
7. Portfolio Analysis — editable holdings, performance, risk, diversification and overlap.
8. Events Calendar — reviewed macro-event dates and sources.
9. Stock Data YTD — current-constituent calendar-year performance.
10. Historical Regimes — sourced episode and policy-cycle stories.
11. Backtests — chronological validation contracts and outcomes.
12. Alpha Research — evidence gates through candidate/card publication.

Use `Ctrl+K` or `Cmd+K` to open the command palette. Type a page or function,
use Up/Down to move, Enter to execute, and Escape to close. An unmatched
security query is handed to the Screener. The palette also exposes EOD update,
Kite connection, theme switching, market breadth, and the portfolio ledger.

The light/dark preference and browser-local portfolio ledger persist in that
browser profile. The skip-to-content link appears when focused from the
keyboard.

## 4. Kite connection

Choose **Kite login**, enter the API key and secret, open the Kite login page,
then paste the returned request token or redirect URL. The secret is used only
for the token exchange. API key and access token remain in server-process
memory and are not written to the database or logs.

A new Kite session is normally required after restarting the server or when the
daily broker token expires. Disconnecting clears the in-memory session.

## 5. EOD update

Choose **EOD update** after the market's completed session is available. The
button displays the active stage and percentage. Fifteen stages run in order:

1. current index snapshot;
2. completed index candles;
3. provisional institutional flows;
4. confirmed FPI flows;
5. RBI and currency context;
6. global risk context;
7. futures and open interest;
8. NIFTY 500 breadth;
9. five-year NIFTY 500 stock history;
10. current-month leaders;
11. ten-year local history;
12. official RBI long-run history;
13. market-sentiment calculation;
14. sentiment evidence snapshot;
15. all workspace and portfolio summaries.

Every failed stage is retried once. Unrelated stages continue when one provider
fails. The final control reports:

- **Successful** — all 15 stages completed;
- **Partial · n/15** — some stages completed and unavailable stages are named in
  the button tooltip/accessible description and completion notice;
- **Failed** — the run aborted or no stage completed.

Partial is a data-readiness state, not permission to treat missing observations
as zero. Run the update again after checking the named provider or connection.

Global observations are completed-session/EOD observations only. FRED is the
primary global source; supported Yahoo Finance chart series are the bounded
fallback when the FRED export is unavailable. Provider and fallback provenance
remain stored with each observation.

## 6. Portfolio ledger and uploads

Portfolio Analysis supports two paths:

- the editable ledger is stored in browser `localStorage` and maps automatically
  to the Dashboard after analysis;
- CSV, XLSX and selectable-text PDF uploads remain in memory for the browser
  session and are not written to SQLite.

In the ledger, edit account, holding, symbol, entry date, quantity, average cost
or LTP/NAV. Invested value, current value, P&L and return are derived fields.
Use **Add row** or **Remove** to change the ledger, then **Save changes** to rerun
Portfolio Analysis and refresh the Dashboard mapping. **Reset** restores the
owner-supplied baseline holdings.

Google Finance pricing is opt-in. When enabled, only NSE symbols are sent to the
provider; quantities, values and the source file stay local. Uploaded prices
remain explicit fallbacks. Historical risk ratios stay unavailable until the
required local history and weight coverage thresholds are met.

To remove browser-local holdings permanently, clear this site's stored data in
the browser. The page's Clear action clears the current in-memory analysis; it
does not silently erase the saved ledger.

## 7. Evidence and interpretation rules

- A completed EOD session is the default time boundary.
- Missing, partial, stale and blocked evidence must remain visible.
- Current-constituent breadth and Stock Data YTD carry survivorship bias.
- Historical regime windows can overlap and are descriptive, not forecasts.
- Uploaded current holdings do not reconstruct the investor's historical portfolio.
- No candidate rank or research card is published until every frozen evidence
  gate passes.
- No page may emit a target price, position size, order or broker action.

## 8. Verify the local store

```bash
python3 scripts/backup_eod_store.py --verify-only
```

The command prints integrity, journal mode, schema version, database size,
table inventory and row counts. It does not contact providers.

## 9. Create a verified backup

Choose an explicit new destination outside the live database path:

```bash
python3 scripts/backup_eod_store.py \
  --destination /absolute/path/pg_terminal_eod-YYYY-MM-DD.sqlite3
```

The command uses SQLite's online backup API, verifies the completed copy with
`PRAGMA quick_check(1)`, and refuses to overwrite an existing file. Never copy
only a live WAL file or use the live database path as the destination.

## 10. Recovery drill

1. Stop the local server.
2. Verify the candidate with
   `python3 scripts/backup_eod_store.py --source BACKUP --verify-only`.
3. Preserve the current live database separately.
4. Copy the verified backup to a new test path; do not overwrite the only copy.
5. Start a disposable checkout against the restored copy, or instantiate an
   `EODStore` against it and verify again.
6. Confirm `/api/health`, representative index coverage, source provenance and
   the latest completed session.
7. Make the restored file live only after the checks pass.

The backup command is intentionally create-only. Selecting the live database is
a manual recovery decision.

## 11. Common problems

### Site does not open

Confirm the server process is running, port 8510 is free, and `/api/health`
responds. Restarting the browser alone does not start the server.

### EOD remains partial

Read the unavailable stage name from the EOD control. Confirm Kite for broker
stages and internet access for official/global providers. Retry once; do not
delete stored history. If the same stage repeats, inspect the server output and
the provider-specific reason returned by its endpoint.

### Portfolio analysis is incomplete

Check symbols, positive quantities, dates, average costs and LTP/NAV. Missing
historical ratios usually mean price-history coverage is below the published
threshold, not that the current-value calculation failed.

### Command palette finds no page

Use the exact workspace name or a related term. Any two-character-or-longer
unmatched query offers a Screener security search.

## 12. Release and final-delivery checklist

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
python3 scripts/backup_eod_store.py --verify-only
curl --fail http://127.0.0.1:8510/api/health
```

Then verify manually:

- a clean browser load has no console errors;
- all 12 sidebar pages open in light and dark themes;
- `Ctrl/Cmd+K`, arrow navigation, Enter and Escape work;
- an EOD run shows progress, retries and a truthful final state;
- a partial update names unavailable stages;
- portfolio row add/remove/edit/save updates its totals and Dashboard mapping;
- dense evidence audits remain keyboard-accessible and collapsed by default;
- missing/stale evidence and research-only boundaries remain visible;
- no recommendation, target, size, order or broker action is emitted;
- the working tree contains only intentional release changes.
