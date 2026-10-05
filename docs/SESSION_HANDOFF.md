# Session handoff

Updated: 2026-09-29

## Linux migration checkpoint — 2026-10-05

- `PG-terminal` is the active product repository. The separate
  `custom_terminal` repository contains transition and research-migration
  material; its later 05-Oct commits do not supersede this product history.
- Linux checkout: `/home/parikshith/Documents/PG-terminal`.
- Restored product baseline: `main` at `1e70921b5aadde380b9a1c1536f3514854bf6022`
  (`Expand cross-index validation and decision research`), matching GitHub and
  the external-backup checkout exactly.
- Runtime: isolated Python `3.12.14` in `.venv`. PG-terminal currently uses only
  the Python standard library and has no separate pip requirements file.
- Validation completed on Linux: Python compilation passed; all 67 offline unit
  tests passed; the local HTTP server returned `200`; no Kite login, provider
  request, market-data update, research run, recommendation, or trade action was
  performed.
- Restored local store: `data/pg_terminal_eod.sqlite3`, 108,425,216 bytes,
  SHA-256 `3b00eb4cb5ebee9c0877c3eddc86db1c93ae3886d9a6ced4f2e16e2d610de183`.
  It matches the external backup byte-for-byte, has no WAL/SHM sidecars, and
  passes read-only `PRAGMA quick_check(1)` with 9 tables.
- The repository was clean and synchronized with GitHub before this checkpoint
  note. `.venv`, Python caches, and the local SQLite store remain local-only.
- Node.js is not installed and is not required at runtime. The live page loaded
  successfully; repeat an optional Node-based JavaScript syntax check only if a
  future frontend change warrants it.
- Resume development from the existing **Next work** item below: candidate risk
  controls and horizon-specific validation. Preserve the analysis-only boundary
  and reconnect Kite manually only when the owner explicitly chooses a workflow
  that requires it.

## Saved state

- Branch: `main`
- Baseline pushed commit before this session: `f4c494d` — Add walk-forward and multi-index regime validation
- Phase 4 foundation commit: `d7fcb23` — Start versioned sentiment validation snapshots
- Verification at handoff: 67 automated tests passed; Python and embedded browser JavaScript syntax checks passed.

## Current milestone

Market Sentiment Phase 4 validation and cross-sectional decision research are in
progress. The EOD workflow stores canonical,
hashed daily sentiment-evidence snapshots with an explicit model version.
Identical reruns are idempotent, while changed evidence for the same day is
preserved as a separate immutable revision for audit.

The evidence snapshot is not yet a market-regime score, trading signal, or
portfolio instruction.

`market-regime-candidate-v1` is now frozen separately from the evidence model.
It defines six cluster weights, validation-only score boundaries, fresh-data and
coverage gates, explicit missing-data behavior, and low/medium/high confidence
requirements. Its label and score remain hidden from the main regime card. The
walk-forward, event/control, recovery, and current cross-index evidence is now
reviewable on Market Sentiment but remains research-only and is not approved for
orders or position sizing.

## Latest implementation

- Added the first candidate-v1 walk-forward engine and Market Sentiment report.
  Every classification uses trailing data only, applies the 80% breadth coverage
  gate and two-session confirmation, and reports 5-, 20-, and 60-session return
  and maximum-drawdown outcomes alongside a Nifty 200DMA baseline. The report
  surfaces its current-universe survivorship bias and remains exploratory.
- Started the multi-index extension with target-index and Nifty 50 benchmark
  selectors plus live stored-history readiness. Indices with fewer than 252
  sessions remain selectable and visibly marked insufficient; full 60-session
  walk-forward evaluation requires 312 stored sessions.
- Wired the selector into the trailing-only engine for all mature supported
  indices. Reports now add median excess return, Nifty 50 outperformance rate,
  and worst benchmark-relative drawdown at each horizon. Target-index trend and
  volatility remain separate from the main broad-market sentiment regime.
- Added an official current-constituent snapshot for all 19 supported indices.
  Historical index breadth now uses only current members also present in the
  liquid F&O universe, exposes official/eligible counts, and withholds indices
  with fewer than five eligible members. This improves relevance but does not
  remove current-membership survivorship bias.
- Added an on-demand cross-index historical comparison. Eligible indices are
  ranked by median 20-session excess return versus Nifty 50 with absolute return,
  positive/outperformance rates, absolute/relative drawdowns, sample size, and
  constituent coverage. Failed readiness gates are listed separately.
- Added fixed named-event reviews to each selected-index validation for the 2018
  India NBFC stress, 2020 COVID-19 shock, 2022 inflation/Ukraine shock, and June
  2024 Indian election-result shock. Reports include absolute/relative returns,
  drawdowns, entry/exit regime, stressed-session share, and detection timing.
  The UI states that these hindsight-selected windows are descriptive.
- Added normal-period distributions around every event review. Non-overlapping
  windows use the same session count and exclude all named events; the report
  compares control-median return and shows event return, drawdown-severity, and
  stressed-session percentiles.
- Added point-in-time constituent-membership support to the loader and validation
  engine. Dated effective-from/effective-to snapshots are applied per session
  when supplied. The checked-in dataset still contains only the official current
  snapshot, so the UI continues to disclose current-membership survivorship bias.
- Added an external historical-evidence readiness table to walk-forward
  validation. It separately audits NSE provisional flows, NSDL confirmed FPI,
  RBI/FBIL currency and rates, permitted FRED global-risk series, and Kite
  futures/OI. It exposes 252-session history and 312-session full-test gates and
  never converts sparse or merely sufficient coverage into a score.
- Added the validation-only Recovering market transition state. Its rule is
  outcome-blind: five prior confirmed weak/high-risk sessions, improvement to
  uncertain/cautiously positive, a maximum 20-session recovery window, and
  immediate exit on positive confirmation or renewed risk. The UI reports state
  outcomes and episode exits but does not expose it as a current market signal.
- Extended that identical recovery rule across every eligible supported index.
  The cross-index study now reports episode/exit/relapse counts, absolute and
  Nifty-relative 20-session outcomes, and worst recovery losses. Event reviews
  compare recovery-session frequency with equal-length normal controls.
- Reframed Market Sentiment around cross-sectional trading decisions rather than
  one overall-market signal. Each index-state pair now has a fixed historical
  directional research gate. Recovery is compared with the same index's ordinary
  Uncertain/Cautiously positive observations; positive outcomes after weak/high-
  risk states are identified as countertrend rebound studies, not ordinary longs.
  No weak/high-risk state currently passes the frozen downside-continuation short
  gate, which remains an honest research result rather than a forced signal.
- Added a current cross-sectional decision board. Every eligible index uses its
  latest completed-session trailing state—not the 60-session-truncated outcome
  sample—and is joined only to its own historical state evidence. The board can
  show simultaneous long, short, tactical/countertrend watch, avoid, and
  insufficient rows; Nifty 50 is context only.
- The latest verified stored-session board (28-Sep-26) showed Nifty Auto as the
  sole long research match, Nifty Financial Services and Nifty PSU Bank as
  countertrend watches, the two MidSmall indices as tactical watches, eleven
  avoid/no-edge rows, no validated short, and Nifty 50 as context. This snapshot
  is expected to change after later EOD updates and is not a saved recommendation.
- Added a persistent site-wide light/dark theme switcher, including dark-aware
  tables, dialogs, notices, forms, and canvas charts.
- Corrected the incremental EOD history path so NIFTY 50 and the 210-stock F&O
  universe request sessions after their last stored date even when an unrelated
  EOD adapter fails. Historical-ranking cache reuse is now trading-date aware.
- India VIX is aligned to the sentiment as-of date instead of being rejected
  merely because its local history is newer than stale cash-market history.
- Price strength now includes an aligned historical chart for the shares near
  52-week highs, near 52-week lows, and their net difference.
- The EOD action shows deterministic progress across twelve named stages, from
  0% through 100%, with a compact mobile presentation.
- Added a dedicated F&O sidebar page and moved futures price/open-interest
  summaries, safeguards, filters, classifications, and sortable contract detail
  out of Market Sentiment.
- Replaced technical investor-facing regime terms with plain language:
  Positive, Mixed, Negative, Monitoring only, and Score not ready. Future regime
  labels use Positive market, Cautiously positive, Uncertain market, Weak market,
  High-risk market, Recovering market, and Not enough reliable data.
- Standardized user-facing dates across the site as `DD-MMM-YY`, while keeping
  provider and storage dates unchanged internally.
- Fixed a date-formatter initialization error that prevented the theme, Kite
  login, and EOD update controls from receiving their event handlers. Browser
  checks confirmed theme switching, Kite-panel opening, and staged EOD progress.
- Added a collapsible score-interpretation guide at the top of Market Sentiment.
  It explains Positive, Mixed, and Negative readings and builds a live snapshot
  from the domestic evidence count, data freshness, F&O coverage, and available
  clusters. It explicitly states that the composite score is not active and the
  reading is context rather than a buy/sell instruction.

## Next work

1. Add candidate risk controls and horizon-specific validation: slower long
   setups, shorter downside-continuation tests, tail-loss/stop-distance evidence,
   and futures/OI confirmation when enough snapshots accumulate.
2. Continue daily collection for institutional flows, macro context, global risk,
   and futures/OI; freeze their directional thresholds only after adequate
   coverage, then test them out of sample.
3. Source and audit authoritative dated index membership before populating the
   new point-in-time schema; never infer historical membership from today's list.
4. Display any decision layer only after its evidence and limitations are
   reviewable in the interface.

## Approved longer-range product milestones

1. Turn Dashboard into the summary layer for every workspace page, with one
   concise section per page, freshness/readiness state, and a route to details.
2. Recompose Market Sentiment as a macro-to-micro decision story: broad risk
   context, walk-forward validation, macro/global drivers, independent sector/
   index states, simultaneous long/short candidates, and stock-level follow-through.
3. Build Portfolio Analysis around local `.csv`/`.xlsx` upload, preview and
   column mapping. Combine holdings with validated sentiment and seasonality to
   provide evidence-linked, scenario-based allocation review prompts. Keep the
   workflow local, read-only, and separate from broker execution.

## Open data decision

The FRED-distributed Nasdaq Emerging Markets Index candidate was rejected
because it is marked `Copyrighted: Pre-Approval Required`. A permitted broad
emerging-market equity benchmark remains an open source-selection item; do not
silently substitute an ETF or scraped proxy.

NSE Indices states that historical/end-of-day constituent data is available as a
subscription product. Its public press-release archive records many individual
index changes, but PG-terminal does not treat those notices as a complete dated
membership dataset without a separate reconstruction and audit. The engine is
ready for licensed or otherwise authoritative effective-dated snapshots; until
then it keeps the current-membership warning visible.

## Resume note

Kite credentials remain in server memory only, so reconnect Kite whenever the
local server is restarted. The latest browser verification completed through
`28-Sep-26` with all 210 F&O stocks aligned. Future EOD updates request only
missing dates.

Do not store API keys, API secrets, request tokens, or access tokens in this
handoff or in Git.
