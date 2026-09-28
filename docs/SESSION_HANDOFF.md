# Session handoff

Updated: 2026-09-28

## Saved state

- Branch: `main`
- Latest pushed commit: `d7fcb23` — Start versioned sentiment validation snapshots
- Previous foundation commit: `468ff3e` — Expand market sentiment data foundations
- Verification at handoff: 54 automated tests passed; Python and embedded browser JavaScript syntax checks passed.
- Working tree was clean immediately after the latest push.

## Current milestone

Market Sentiment Phase 4 has started. The EOD workflow now stores canonical,
hashed daily sentiment-evidence snapshots with an explicit model version.
Identical reruns are idempotent, while changed evidence for the same day is
preserved as a separate immutable revision for audit.

The evidence snapshot is not yet a market-regime score, trading signal, or
portfolio instruction.

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

The local server was intentionally not restarted after the Phase 4 backend
change because the Kite session lives in server memory. On the next session,
restart the server to activate the new snapshot endpoint, then reconnect Kite
before running EOD Update.

Do not store API keys, API secrets, request tokens, or access tokens in this
handoff or in Git.
