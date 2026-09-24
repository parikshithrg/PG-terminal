# PG-terminal milestones

This roadmap records intended build order. A milestone entry is not approval to
activate providers, conduct research, generate recommendations, or place trades.

## Current foundation

- TradingQnA-inspired interface and eight-page navigation frame.
- In-memory Kite authentication with no credential persistence.
- Read-only index snapshots and dashboard EOD summaries.
- NIFTY 500 market-breadth calculation.
- Ten-year index and F&O equity seasonality tables.
- Current-month and historical month leader/laggard contracts.

## Next milestone: persistent EOD data foundation v1

Status: in progress.

Implemented first slice:

- Append-only SQLite storage with canonical index/stock identity and validated
  OHLC session rows.
- Duplicate-safe writes that reject conflicting replacements.
- Chunk-by-chunk seasonality persistence, safe resume after interruption, and
  incremental requests beginning after the latest stored session.
- Seasonality results now read from local history after synchronization and
  report whether stored history was reused.

Still upcoming in this milestone:

- Extend the shared store to dashboard summaries, NIFTY 500 breadth, and
  full-universe leader/laggard refreshes.
- Add visible synchronization stages, progress, cancel/retry controls, exact
  missing-session reporting, and unavailable-instrument details.

Build an append-only local store for validated, completed Kite daily candles so
the terminal downloads history once and then requests only missing sessions.

Scope:

- Cover the current Kite-supported index universe and selected equity universe.
- Store canonical instrument identity, session date, OHLC values, source,
  retrieval timestamp, validation status, and schema version.
- Never store API secrets, access tokens, request tokens, or login material.
- Reject incomplete current-session candles and invalid/nonfinite OHLC values.
- Make updates idempotent and prevent duplicates or silent overwrites.
- Calculate breadth and seasonality from the validated local store after sync.
- Report exact coverage, missing sessions, unavailable instruments, and failures.
- Support interruption, cancellation, safe resume, and retry of missing work.
- Keep the feature read-only: no scoring, recommendations, backtests, or trading.

Completion criteria:

- [x] A first synchronization can populate up to ten years of eligible completed
  daily candles without duplicating records.
- [x] A second seasonality synchronization requests and writes only sessions
  after the latest stored date.
- [x] An interrupted seasonality synchronization resumes without restarting
  completed chunks.
- [ ] The interface shows stage progress and instrument counts.
- [ ] Existing dashboard, breadth, and seasonality results can all be reproduced
  from stored data.
- [ ] Automated tests cover identity, dates, OHLC validation, duplicate handling,
  incremental updates, interrupted runs, and unavailable-state behaviour.

## Subsequent milestones

### Active milestone status — Market Sentiment Phase 2

Completed and available in the local EOD workflow:

- India VIX history and implied-versus-realised volatility context.
- Official provisional NSE FII/FPI and DII cash-flow snapshots, summaries, and
  daily/cumulative charts.
- Official RBI/FBIL USD, GBP, EUR, and JPY reference rates plus the RBI-listed
  government security nearest ten-year maturity. Exact security identity is
  retained and 5-/20-session changes appear only after enough observations.
- Contract-keyed near-month price, volume, and open-interest baselines for the
  210-stock F&O universe, collected with one post-close bulk Kite request.
  Contract rollover creates a new baseline rather than a false OI comparison.
- Data freshness, coverage, missing-stock details, and explicit unavailable or
  unranked states. The main EOD update triggers every completed Phase 2 adapter.

Next Phase 2 steps, in order:

1. Accumulate and inspect same-contract futures observations across normal days
   and at least one expiry rollover.
2. Define transparent price/OI states only after continuity checks: long
   build-up, short build-up, long unwinding, and short covering.
3. Validate minimum volume/OI coverage, missing-contract handling, thresholds,
   and persistence before those states influence sentiment.
4. Add confirmed NSDL FPI reconciliation as a separate series without replacing
   or blending the provisional NSE report.
5. Accumulate RBI/FBIL history, calculate 5-/20-session changes, and validate
   currency/rate thresholds before scoring the macro cluster.

Phase 2 remains read-only. No derivative signal, regime score, portfolio change,
or order action is activated by these data foundations.

1. **Market sentiment and regime foundation** — implement the approved
   [Market Sentiment blueprint](MARKET_SENTIMENT_BLUEPRINT.md) in phases,
   beginning with the static evidence contract and locally reproducible domestic
   trend, breadth, price-strength, and realised-volatility inputs. External flow,
   currency, rates, and global providers require explicit source review.
   Phase 1 now has a working local page using Nifty 50 history and the 210 stored
   NSE F&O equities. The 210-stock liquid universe is the intended permanent
   breadth scope. Phase 1 is complete. Phase 2 has started with persisted India
   VIX history, transparent implied-versus-realised volatility context, and an
   append-only official NSE provisional FII/FPI-DII cash-flow series. Confirmed
   NSDL reconciliation and validated futures-positioning labels remain pending.
   Contract-keyed near-month futures price/open-interest baselines are now stored
   without comparing across rollovers. The domestic context block stores official RBI/FBIL
   FX references and the RBI-listed government security nearest ten-year maturity;
   it remains unranked while 5-/20-session history accumulates.
2. **Visible update pipeline** — separate inventory, candle synchronization,
   validation, breadth, seasonality, and summary stages with progress, cancel,
   resume, and precise failure details.
3. **Transparent factor screener** — independently testable momentum, relative
   strength, volatility, liquidity, valuation, quality, growth, revision, and
   earnings-sentiment inputs with as-of dates and visible formulas.
4. **Sector-relative analysis** — compare and rank equities within appropriate
   sectors rather than mixing structurally different industries.
5. **Portfolio risk diagnostics** — sector and position concentration,
   correlation, beta, volatility contribution, marginal risk, drawdown, and
   read-only stress scenarios.
6. **Performance attribution** — separate market, sector, factor, stock-selection,
   cost, and turnover contributions using explicit methodology.
7. **Indian events foundation** — evaluate permissions and source quality for
   exchange announcements, financial results, investor presentations,
   shareholding changes, insider disclosures, bulk/block deals, and transcripts.
8. **Evidence-grounded analyst** — answer questions only from approved local
   calculations and documents, with source, timestamp, and calculation citations.

## Validation work for observed seasonality

Before treating the apparent April strength as a usable effect, add median
returns, positive-return frequency, observation counts, best/worst years,
outlier removal, non-April comparisons, and five-year versus ten-year results.
Account explicitly for current-constituent and survivorship bias.

All future trading-decision discussions should follow the recorded
[trading decision analysis framework](TRADING_DECISION_FRAMEWORK.md): distinguish
effect size from reliability, correct for multiple testing, require
chronological held-out validation, assess stability and downside, and use
seasonality only as supporting evidence alongside current market confirmation.

## Deferred pending separate approval and stronger controls

- Automated broker orders or portfolio execution.
- Long-short or derivative execution.
- AI-generated trade recommendations or autonomous approvals.
- Mean-variance portfolio optimization.
- Short-availability and live-execution workflows.
- Crowding scores without a verified and permitted Indian data source.
