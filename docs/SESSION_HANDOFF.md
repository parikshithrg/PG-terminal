# Session handoff

Updated: 2026-09-28

## Saved state

- Branch: `main`
- Latest pushed commit before this handoff: `90a62d1` — Improve sentiment workflow and add F&O workspace
- Phase 4 foundation commit: `d7fcb23` — Start versioned sentiment validation snapshots
- Verification at handoff: 55 automated tests passed; Python and embedded browser JavaScript syntax checks passed.

## Current milestone

Market Sentiment Phase 4 has started. The EOD workflow now stores canonical,
hashed daily sentiment-evidence snapshots with an explicit model version.
Identical reruns are idempotent, while changed evidence for the same day is
preserved as a separate immutable revision for audit.

The evidence snapshot is not yet a market-regime score, trading signal, or
portfolio instruction.

## Latest implementation

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

1. Define and freeze the first candidate regime-rule version separately from
   the evidence model version.
2. Specify transparent factor weights, thresholds, missing-data behavior, and
   confidence/coverage requirements.
3. Produce validation outputs for walk-forward periods and major market events.
4. Compare the candidate regime with forward returns, drawdowns, volatility,
   breadth, institutional flows, macro context, global risk, and futures/OI.
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
