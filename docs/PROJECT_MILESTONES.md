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

### Active milestone status — Market Sentiment Phases 2–3

Completed and available in the local EOD workflow:

- India VIX history and implied-versus-realised volatility context.
- Official provisional NSE FII/FPI and DII cash-flow snapshots, summaries, and
  daily/cumulative charts.
- Official NSDL custodian-confirmed FPI equity investment, preserved as separate
  stock-exchange, primary-market-and-others, and subtotal routes. Reporting lag,
  latest values, and 5-/20-session totals are explicit; the series is never
  blended with NSE provisional cash activity.
- Official RBI/FBIL USD, GBP, EUR, and JPY reference rates plus the RBI-listed
  government security nearest ten-year maturity. Exact security identity is
  retained and 5-/20-session changes appear only after enough observations.
- Contract-keyed near-month price, volume, and open-interest baselines for the
  210-stock F&O universe, collected with one post-close bulk Kite request.
  Contract rollover creates a new baseline rather than a false OI comparison.
- Data freshness, coverage, missing-stock details, and explicit unavailable or
  unranked states. The main EOD update triggers every completed Phase 2 adapter.
- A Phase 3 global-risk foundation using one FRED EOD export: S&P 500 trend,
  CBOE VIX, broad U.S. dollar, USD/JPY, and Brent. Each series retains its own
  observation date and source ID. The cluster is descriptive and unscored.

Next Phase 2 steps, in order:

1. Accumulate and inspect same-contract futures observations across normal days
   and at least one expiry rollover.
2. Validate the implemented descriptive price/OI quadrants after continuity
   checks: long build-up, short build-up, long unwinding, and short covering.
   A sortable/filterable detail table and explicit exploratory noise, liquidity,
   gap, missing-coverage, and rollover safeguards are implemented but unscored.
3. Validate minimum volume/OI coverage, missing-contract handling, thresholds,
   and persistence before those states influence sentiment.
4. Accumulate NSDL and NSE observations, document their date/coverage
   differences, and validate any future side-by-side reconciliation measure.
5. Accumulate RBI/FBIL history, calculate 5-/20-session changes, and validate
   currency/rate thresholds before scoring the macro cluster.

Phase 2 remains read-only. No derivative signal, regime score, portfolio change,
or order action is activated by these data foundations.

Phase 3 next requires observed publication-lag/failure validation and threshold
testing. The available FRED Nasdaq Emerging Markets series requires pre-approval
and was rejected; a permitted broad emerging-market equity benchmark remains open.

Phase 4 has started with immutable, versioned daily evidence snapshots. The EOD
workflow stores a canonical hash and preserves changed same-day evidence as an
auditable revision. `market-regime-candidate-v1` now freezes six cluster weights,
score boundaries, coverage/freshness gates, missing-data treatment, and
confidence levels separately from the evidence model. It is validation-only and
does not replace the visible `Score not ready` state. A trailing-only walk-forward
report now compares 5-, 20-, and 60-session Nifty outcomes by confirmed regime
and against the Nifty 200DMA baseline. Two-session confirmation reduced historical
one-day state changes materially, but the report remains exploratory because it
uses today's F&O membership, overlapping outcome windows, and only the 60% of
candidate weight available from domestic historical evidence. Named-event and
point-in-time-universe validation are next.

### Phase 4A — multi-index opportunity and risk validation

1. **Interface and readiness — complete.** Added a target-index selector,
   Nifty 50 benchmark choice, dynamic stored-session counts, and explicit
   insufficient-history states. Current-regime analysis becomes eligible at 252
   sessions; a complete 60-session walk-forward outcome needs at least 312.
2. **Per-index engine — complete.** The trailing-only walk-forward engine now
   evaluates every sufficiently mature locally supported index without changing
   the frozen candidate-v1 thresholds.
3. **Relative outcomes — complete.** Reports include excess return versus Nifty
   50, probability of outperforming it, benchmark-relative drawdown, and
   regime-conditioned performance.
4. Keep the broad-market regime separate from the selected index's opportunity
   and risk layer. Do not present a sector reading as a trading instruction.
5. **Constituent-aware breadth — complete for the current snapshot.** Official
   NSE Indices membership is intersected with the liquid 210-stock F&O universe;
   reports expose both counts and retain a survivorship warning. Indices with
   fewer than five eligible constituents are withheld. Point-in-time membership
   remains preferred when an authoritative historical source becomes available.
6. **Cross-index historical comparison — complete.** The table ranks eligible
   indices by 20-session median excess return and shows absolute return,
   outperformance rate, absolute/relative drawdown risk, sample size, and liquid
   constituent coverage. It excludes failed readiness gates and is explicitly
   historical rather than a live trading leaderboard.
7. **Named stress-event review — complete for the first fixed windows.** Selected-
   index reports now review the 2018 India NBFC liquidity stress, 2020 COVID-19
   shock, 2022 global inflation/Ukraine shock, and June 2024 Indian election-
   result shock. They show return, drawdown, benchmark-relative outcome, entry/
   exit regime, stressed-session share, and detection timing. These windows are
   retrospective and explicitly not treated as independent samples.
8. **Normal-period controls — complete.** Every named event is now compared with
   non-overlapping windows of equal session length that exclude all named events.
   Reports show the control median return plus event return, drawdown-severity,
   and stressed-session percentiles. The controls are descriptive distributions,
   not hand-picked calm dates or causal counterfactuals.
9. **Point-in-time membership path — ready, data pending.** The validation engine
   and constituent loader accept dated effective-from/effective-to membership
   snapshots and apply the matching membership at each historical session. The
   repository currently contains only the official 29-Sep-26 current snapshot,
   so reports retain the survivorship warning until an authoritative historical
   source is approved and populated.
   NSE Indices describes historical/end-of-day constituent data as a subscription
   product (`https://www.niftyindices.com/offerings/data-subscription`). Public
   press releases may document individual changes but are not treated as a
   complete, machine-audited membership history.
10. **External-history readiness — complete.** The validation report now audits
   complete dated sessions for provisional institutional cash flow, confirmed
   FPI investment, RBI/FBIL currency and rates, permitted FRED global-risk data,
   and liquid-universe futures/OI snapshots. A 252-session history gate and
   312-session full walk-forward gate are explicit. Passing a coverage gate does
   not activate scoring; directional thresholds still require separate review.
11. **Ongoing:** continue accumulating these EOD histories, freeze candidate
   thresholds for each external cluster, and evaluate them out of sample. Source
   authoritative dated constituent membership in parallel if access is approved.
12. **Recovering-market transition rule — complete for validation.** A frozen,
   outcome-blind state machine enters `Recovering market` only after at least five
   consecutive confirmed weak/high-risk sessions improve to uncertain or
   cautiously positive. Recovery lasts at most 20 sessions and ends immediately
   on positive confirmation or renewed risk. The report measures its later
   returns and drawdowns only after assignment and keeps it off the current signal.
13. **Cross-index recovery stability — complete.** The frozen recovery rule now
   runs across every eligible index, not only Nifty 50. The comparison exposes
   episode counts, exits to Positive market, relapses, absolute and Nifty-relative
   20-session outcomes, and worst returns/drawdowns. Named-event reports also
   compare recovery-session frequency with same-length normal controls.
14. **Incremental and directional state evidence — complete.** Recovery is now
   compared with the same index's ordinary Uncertain/Cautiously positive sample.
   A separate historical research map applies fixed 60-session, absolute-return,
   positive-rate, and Nifty-relative gates to every index-state combination.
   Trend/recovery states may qualify as long research candidates; only validated
   downside continuation in weak/high-risk states may qualify as short research.
   Positive post-selloff returns are labelled countertrend rebound studies rather
   than misleading long signals. No short state currently clears the frozen gate.
15. **Current cross-sectional decision board — complete for research.** Every
   eligible index is classified through the latest completed session, separately
   from the 60-session-truncated outcome sample, then joined to its own validated
   state history. The board ranks simultaneous long, short, countertrend/tactical
   watch, avoid, and insufficient-evidence rows. Nifty 50 is context only.
16. **Candidate risk controls and signal horizons — complete for research.**
   Long evidence now uses 20-session outcomes while downside-continuation
   evidence uses five sessions. The board exposes the 10th-percentile oriented
   outcome, 90th-percentile adverse excursion, and 2%/3%/5% adverse-distance
   breach rates as historical risk evidence, not stop or sizing advice. Short
   candidates additionally require at least 252 complete futures/OI sessions,
   same-session coverage, and bearish index-constituent breadth; sparse history
   remains visibly unconfirmed and cannot promote a short.
17. **Dashboard summary layer — Market Sentiment slice complete.** The Dashboard
   now loads a compact server-side summary of the current cross-sectional
   decision mix, domestic freshness, evidence-cluster/index coverage, and the
   futures/OI short-history gate. Its `View details` action opens Market
   Sentiment, and the card preserves the research-only/no-execution boundary.
18. **Dashboard summary layer — F&O slice complete.** The Dashboard now shows
   latest contract coverage, eligible same-contract comparisons, bullish and
   bearish quadrant counts, stored-session depth, rollover/stale/liquidity
   exclusions, and the active noise safeguards. Rollover baselines remain
   visibly withheld rather than compared across contracts, and `View details`
   opens the descriptive F&O workspace.
19. **Dashboard summary layer — Seasonality slice complete.** The Dashboard now
   summarizes Nifty 50's strongest/weakest historical calendar months, completed
   session and month coverage, chronological holdout survival, and the held-out
   turn-of-month result. `View details` loads the complete locally stored month,
   weekday, turn-of-month, and holdout tables without requiring a Kite session.
   All language keeps historical averages separate from forecasts.
20. **Next executable step:** establish the Screener workspace contract before
   adding its Dashboard card. Define the locally supported universe, filters,
   result columns, freshness/readiness states, and evidence limitations so the
   Dashboard can summarize a real screen rather than an empty placeholder.

## Approved product-integration milestones

### A. Dashboard as the workspace summary

The Dashboard becomes a concise summary of every main workspace page. It should
not duplicate full analysis; each section must show the most decision-relevant
result, freshness/coverage state, and a clear route to the source page.

1. Add one summary section for Market Sentiment, F&O, Screener, Seasonality,
   Earnings Analysis, Portfolio Analysis, News & Events, and Stock Data YTD.
2. Use a consistent card contract: headline state, two to four supporting
   measures, as-of date, missing-data warning, and `View details` action.
3. Keep unavailable or immature analysis visible with an honest readiness state;
   never replace missing evidence with a neutral-looking value.
4. Make the Dashboard responsive and keep the EOD update progress/freshness
   state visible without requiring users to open each page.

### B. Market Sentiment as a macro-to-micro story

Reorder Market Sentiment so a newer investor can move from the conclusion to its
supporting evidence and then from broad environment to specific opportunities or
risks. The intended top-to-bottom reading order is:

The page is a cross-sectional trading-decision workspace, not an overall-market
signal. The broad regime supplies risk context; each index/sector is classified
independently so long and short candidates may coexist.

1. Broad risk context, confidence, freshness, and a one-paragraph summary of what
   is driving the environment. Do not present it as the site's trading signal.
2. Walk-forward validation, interpretation boundaries, sample coverage, and
   limitations. Keep historical validation separate from the current reading.
3. Macro/global environment and liquidity: volatility, institutional flows,
   currency, sovereign yields, and global risk backdrop.
4. Broad-index regime and trend evidence.
5. Sector/index regimes, relative performance, breadth, and cross-index ranking.
6. Stock-level follow-through: participation, price strength, and liquid F&O
   leaders/laggards, clearly separated from trade recommendations.
7. Add short transition text between layers so the page explains why each layer
   follows from the previous one instead of presenting disconnected cards.

### C. Portfolio Analysis as a read-only allocation review

Portfolio Analysis should combine the user's holdings with validated Market
Sentiment and Seasonality evidence to indicate how the current allocation aligns
with the market environment. It remains an analytical review, not execution.

1. Accept local `.csv` and `.xlsx` uploads with an explicit preview-and-column-
   mapping step. Required fields should be instrument/symbol and quantity or
   portfolio weight; optional fields can include average cost and current value.
2. Validate symbols, duplicates, quantities, weights, missing prices, and file
   structure before calculation. Reject unsupported or ambiguous rows visibly.
3. Keep uploaded portfolio data local and in memory by default; do not transmit,
   commit, or persist a holdings file without explicit approval.
4. Calculate position and sector weights, concentration, cash allocation, beta,
   volatility contribution, drawdown exposure, and overlap with available index
   and F&O universes.
5. Bring in the current validated market regime, index/sector regimes, evidence
   confidence, freshness, and relevant seasonality observations.
6. Produce scenario-based allocation review prompts: over/under-exposure,
   concentration warnings, defensive/aggressive tilts, and instruments requiring
   review. Every suggestion must show the supporting evidence and uncertainty.
7. Never place orders or imply certainty. Recommendations require user review and
   must remain separate from automated broker actions.

1. **Market sentiment and regime foundation** — implement the approved
   [Market Sentiment blueprint](MARKET_SENTIMENT_BLUEPRINT.md) in phases,
   beginning with the static evidence contract and locally reproducible domestic
   trend, breadth, price-strength, and realised-volatility inputs. External flow,
   currency, rates, and global providers require explicit source review.
   Phase 1 now has a working local page using Nifty 50 history and the 210 stored
   NSE F&O equities. The 210-stock liquid universe is the intended permanent
   breadth scope. Phase 1 is complete. Phase 2 has started with persisted India
   VIX history, transparent implied-versus-realised volatility context, and an
   append-only official NSE provisional FII/FPI-DII cash-flow series. The
   separately stored NSDL custodian-confirmed FPI equity series is implemented;
   a validated cross-series reconciliation measure and futures-positioning
   labels remain pending.
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
