# Session handoff

Updated: 2026-09-29

## Saved state

- Branch: `main`
- Baseline pushed commit before this session: `90a62d1` — Improve sentiment workflow and add F&O workspace
- Phase 4 foundation commit: `d7fcb23` — Start versioned sentiment validation snapshots
- Verification at handoff: 64 automated tests passed; Python and embedded browser JavaScript syntax checks passed.

## Current milestone

Market Sentiment Phase 4 has started. The EOD workflow now stores canonical,
hashed daily sentiment-evidence snapshots with an explicit model version.
Identical reruns are idempotent, while changed evidence for the same day is
preserved as a separate immutable revision for audit.

The evidence snapshot is not yet a market-regime score, trading signal, or
portfolio instruction.

`market-regime-candidate-v1` is now frozen separately from the evidence model.
It defines six cluster weights, validation-only score boundaries, fresh-data and
coverage gates, explicit missing-data behavior, and low/medium/high confidence
requirements. Its label and score remain hidden from the main regime card. The
first walk-forward report is now reviewable on Market Sentiment but remains
exploratory and is not approved for decisions.

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

1. Add the cross-index comparison table, retaining explicit membership-bias
   warnings and excluding indices that fail history or liquid-breadth gates.
2. Add named major-event validation and point-in-time F&O membership where source
   history permits it.
3. Extend historical coverage to institutional flows, macro context, global risk,
   and futures/OI so more than 60% of candidate weight can be tested.
4. Test transition behavior and define the recovering label without fitting to
   the displayed outcome sample.
5. Display a composite regime label only after its evidence and limitations are
   reviewable in the interface.

## Open data decision

The FRED-distributed Nasdaq Emerging Markets Index candidate was rejected
because it is marked `Copyrighted: Pre-Approval Required`. A permitted broad
emerging-market equity benchmark remains an open source-selection item; do not
silently substitute an ETF or scraped proxy.

## Resume note

Kite credentials remain in server memory only, so reconnect Kite whenever the
local server is restarted. The latest browser verification completed through
`28-Sep-26` with all 210 F&O stocks aligned. Future EOD updates request only
missing dates.

Do not store API keys, API secrets, request tokens, or access tokens in this
handoff or in Git.
