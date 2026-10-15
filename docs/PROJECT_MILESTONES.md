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
19. **Dashboard summary layer — all-index Seasonality complete.** The Dashboard
   and detail workspace now expose every supported index with its own locally
   stored month, weekday, turn-of-month, chronological holdout, session count,
   calendar coverage, and readiness state. The Dashboard selector routes the
   selected index into the full detail view. Short-history indices remain
   visible rather than inheriting Nifty 50 evidence: the current local store
   reports 18 ready indices and Nifty Chemicals as partial with 214 sessions and
   10/12 populated calendar months. All language keeps historical averages
   separate from forecasts, and the workflow does not require a Kite session.
20. **Screener workspace contract — complete.** The Screener now loads the
   locally stored 210-stock NSE F&O universe through a versioned
   `local-stock-screener-v1` contract. It preserves ready, partial-history,
   stale, and unavailable rows; exposes search, readiness and price-evidence
   filters; and supports transparent sorting across 20/60-session returns,
   20-session excess return versus Nifty 50, moving-average position, 52-week
   position/drawdown, and realized volatility. Formula definitions, freshness,
   coverage, and current evidence limitations are visible in the workspace.
   The screen is descriptive EOD evidence, not a recommendation or backtest.
21. **Dashboard summary layer — Screener slice complete.** The Dashboard now
   summarizes the versioned local screen with universe readiness, freshness,
   positive 20-session return count, 200-session-average breadth, and the count
   outperforming Nifty 50 over 20 sessions. It labels the highest and lowest
   observed excess-return rows as descriptive extremes, preserves stale and
   partial states, and routes to the full Screener. Counts and extremes are
   explicitly not recommendations, validated ranks, or risk-adjusted alpha.
22. **Events Calendar v1 — complete.** Replaced the News & Events workspace with
   the versioned `macro-events-calendar-v1` contract. It lists 13 upcoming
   October–December 2026 India and U.S. macro events from reviewed official
   MoSPI, Federal Reserve, and U.S. BLS calendar snapshots, converts specified
   release times to IST, and supports region and event-type filters. The source
   table distinguishes verified snapshots from any date-pending sources.
23. **RBI date-safety boundary — corrected and complete.** The official RBI
   23-Mar-2026 MPC schedule is now verified and supplies the 5–7 October 2026,
   2–4 December 2026, and 3–5 February 2027 meetings. Multi-day events remain
   visible through their end date, fixing the omission of an in-progress meeting.
   No policy-decision time is assumed because the official schedule does not
   state one. Weekend MoSPI releases retain the next-working-day caveat.
24. **News work paused by owner direction.** The earlier corporate-filings source
   review and manual NSE CSV importer remain dormant and are not exposed in the
   active workspace. Unscheduled news, headlines, sentiment, surprise estimates,
   impact scores, recommendations, and trade interpretation are out of scope.
25. **Dashboard summary layer — Events Calendar slice complete.** The Dashboard
   now reuses `macro-events-calendar-v1` to show the next event, seven- and
   thirty-day counts, total upcoming events, India/U.S. coverage, snapshot date,
   and verified versus date-pending source readiness. It links to the complete
   calendar and repeats that the data is a reviewed snapshot whose official
   dates must be verified; it does not introduce a second calendar contract.
26. **Shared table-interpretation guidance — complete.** Audited all 21 populated
   tables across Dashboard, Market Sentiment, F&O, Screener, Seasonality, and
   Events Calendar. Every table now has nearby plain-language guidance explaining
   what its rows and key columns mean, which readiness/sample checks matter, how
   to compare typical outcomes with tail risk, and why descriptive evidence is
   not automatically a recommendation. Empty future workspaces have no tables to
   annotate yet. Extend calendar coverage only when official dates are verified.
27. **Stock Data YTD v1 — complete.** The Stock Data YTD workspace now ranks
   every security in the current official NIFTY 500 constituent snapshot by
   calendar-year return. It shows company name, symbol, sector, completed close,
   selected-year performance, and distance from the trailing 20- and 200-session
   simple moving averages. The user can select any of the five available years,
   reverse the best-to-worst order, filter by sector, and search by company or
   symbol. Historical-year prices and averages are aligned to that year's final
   available completed session. Partial and unavailable rows remain visible,
   and the current-universe survivorship limitation is explicit.
28. **Earnings Analysis v1 — complete.** Replaced the empty workspace with an
   append-only local quarterly-results workflow. A reviewed CSV can import
   consolidated or standalone issuer figures with fiscal quarter, reporting
   date, revenue, net profit, EPS, declared currency/unit, and an HTTPS filing
   source. The page calculates comparable revenue YoY/QoQ, profit and EPS YoY,
   preserves absolute profit change when a percentage would be misleading, and
   labels turnarounds, moves to loss, and partial-history rows. Search, sector,
   and reporting-basis filters are available. Automated exchange scraping,
   consensus estimates, surprise scores, recommendations, and signals remain
   disabled.
29. **Portfolio Analysis v1 — complete.** Replaced the empty workspace with a
   local, read-only CSV/XLSX workflow. A selected file is previewed and analyzed
   immediately using automatic recognition of common broker-export columns; no
   manual mapping controls are shown. Holdings remain in request/browser memory
   rather than being written to SQLite. The first slice validates symbols,
   duplicates, quantities, weights, costs, values, and missing prices; then
   shows normalized position weights, largest/top-five concentration,
   cost-relative return when available, and locally observed F&O overlap.
   An explicit privacy toggle enables Google Finance pricing by sending only NSE
   symbols; uploaded LTP/NAV and the most recent completed local EOD close remain
   local fallbacks. The position table shows the dated last completed close and
   omits the live-price, local F&O, sector, and NIFTY 500 columns. The sector-
   allocation section was removed because the working portfolio is primarily
   mutual funds. Six top-level metrics summarize total invested amount,
   current return, net return percentage, a cash-flow-matched NIFTY 50 return,
   and portfolio XIRR. A top-level asset-allocation section groups normalized
   weights and current values into Equity, Debt, Commodity, Hybrid, Cash, and
   Other using transparent name and exchange-evidence rules; uncertain holdings
   remain in Other. A second cash-flow-matched benchmark uses the official NIFTY
   10-year Benchmark G-Sec total-return index in fixed annual request windows;
   it is withheld when official history does not cover every purchase date.
   Benchmark and XIRR values require usable purchase dates and complete
   invested/current values for every eligible position. Invalid
   rows remain visible and excluded.
30. **Portfolio risk-ratio foundation — complete.** The performance section now
   calculates annualized return and volatility, Sharpe, Sortino, beta versus
   NIFTY 50, Jensen alpha, maximum drawdown, Calmar, tracking error, and
   information ratio plus NIFTY 50 correlation from aligned daily returns. The calculation is explicitly a
   current-holdings, constant-weight backtest, not a reconstruction of the
   investor's transaction history. Results require at least 126 aligned sessions
   and 90% portfolio-weight history coverage; otherwise every ratio is withheld
   and the coverage shortfall is shown. Sharpe, Sortino, and alpha disclose a 0%
   annual risk-free assumption until an approved short-term rate history is
   integrated.
31. **AMFI mutual-fund history integration — complete for the working portfolio.**
   The five reviewed Direct-Growth fund labels resolve to exact AMFI scheme codes
   and retrieve 300 days of official NAV history in bounded 90-day windows. The
   NCD is explicitly excluded and the remaining portfolio is renormalized for
   risk calculations. Live validation on 08-Oct-26 returned 195–202 NAV rows per
   fund, no source failures, and 177 aligned portfolio/NIFTY sessions with 90.75%
   risk-weight history coverage. The resulting current-holdings backtest produced
   2.92% annualized return, 5.61% volatility, 0.54 Sharpe, 0.78 Sortino, 0.37 beta,
   8.21% Jensen alpha, -3.69% maximum drawdown, 0.79 Calmar, 9.16% tracking error,
   1.87 information ratio, and 0.93 NIFTY 50 correlation. These values are a
   dated validation snapshot, not the investor's transaction-history performance.
32. **Next executable step:** add the approved RBI 91-day T-bill history for the
   risk-free rate, extend price coverage to the remaining ETFs/equity, and add
   position-level volatility contribution. Keep the whole-market Dashboard headline deferred
   until its evidence inputs, methodology, confidence rules, and wording are
   designed and reviewed with the owner.

## Approved product-integration milestones

### Shared presentation standard across every workspace

Use the simplified Mutual Funds Comparer as the site-wide presentation pattern.
Each page should lead with a small number of decision-relevant conclusions,
visual summaries, data freshness/coverage, and clear review points. Prefer data
inferences over long explanatory copy, and use plain language suitable for a
non-technical investor.

Tables are secondary: retain them only when the rows materially help the user
understand or act on the result. Keep technical catalogues, calculation inputs,
method contracts, and audit detail behind an optional detail surface or in the
calculation layer. Where a visible table still needs help, use one short reading
hint rather than a long explanation.

Every inference must distinguish observed facts from derived conclusions and
suggestions. Coverage, freshness, missing-data limitations, and confidence must
remain visible so a cleaner interface never creates false certainty. Apply this
standard incrementally whenever an existing page is refined and to every new
workspace from the start.

### A. Dashboard as the workspace summary

The Dashboard becomes a concise summary of every main workspace page. It should
not duplicate full analysis; each section must show the most decision-relevant
result, freshness/coverage state, and a clear route to the source page.

1. Add a prominent whole-market condition summary at the top of the Dashboard.
   Its methodology, evidence inputs, confidence rules, and exact wording will be
   designed later; do not invent or activate an overall-market conclusion before
   those decisions are reviewed.
2. Add one summary section for Market Sentiment, F&O, Screener, Seasonality,
   Earnings Analysis, Portfolio Analysis, Events Calendar, and Stock Data YTD.
3. Use a consistent card contract: headline state, two to four supporting
   measures, as-of date, missing-data warning, and `View details` action.
4. Keep unavailable or immature analysis visible with an honest readiness state;
   never replace missing evidence with a neutral-looking value.
5. Make the Dashboard responsive and keep the EOD update progress/freshness
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

1. Accept local `.csv` and `.xlsx` uploads with an automatic preview-and-analysis
   step. Recognize common broker column names for instrument/symbol and quantity,
   portfolio weight, or current value; optional fields can include average cost,
   sector, and company name. Ambiguous files must fail visibly instead of asking
   the user to configure mappings.
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
8. A separate Home Loan Tracker tab now reads the workbook's loan-payment sheet
   in memory, summarizes fiscal-year principal and interest, outstanding balance,
   rate, and rental totals, and provides an editable reducing-balance early-
   repayment calculator with payoff period, time saved, interest saved, and an
   annual projection plus a dated month-by-month payment timeline. The calculator
   supports an upfront lump sum, additional monthly payments, and a recurring
   lump sum after every 12th payment. The suggested monthly payment is explicitly identified as
   an editable estimate derived from the latest recorded annual payment.
9. Mutual Funds Comparer is now consolidated into Portfolio Analysis as the
   third tab beside Holdings Analysis and Home Loan Tracker. Its local upload,
   allocation, overlap, true-diversification score and three improvement paths
   retain their existing calculation contracts; the redundant standalone
   sidebar destination has been removed.
10. The Portfolio Analysis entry point now uses `universal-portfolio-import-v1`.
    A single local CSV, XLSX or text-based PDF upload is inspected for stock and
    mutual-fund holdings, split conservatively, and routed to the holdings and
    fund-comparison analyses. Unclassified rows remain explicit. Image-only PDFs
    require OCR and are rejected visibly rather than guessed.
11. Holdings Analysis is now the combined portfolio narrative. Its primary
    sequence is total stock value, mutual-fund value, total portfolio value and
    diversification score; portfolio performance; risk-adjusted and benchmark
    ratios; allocation/diversification; direct-stock, fund and cross-holding
    redundancy; and three improvement paths. Detailed row previews, positions,
    validation issues and calculation limitations remain available in a
    collapsed audit disclosure. The Mutual Funds Comparer tab remains the
    security-level drill-down.
12. The universal Holdings Analysis upload now displays a staged progress bar
    immediately below the file control. It reports browser file reading,
    holdings detection, stock/fund separation, portfolio calculations and fund
    diversification analysis, with elapsed time and explicit success or error
    completion states.
13. A compact file-format indicator now appears above the universal upload and
    opens a visual table-format dialog. It uses sample stock and mutual-fund
    sheets to distinguish minimum identity/value columns from the cost/date
    fields needed for performance and XIRR, and visually flags layouts to avoid.
14. Holdings Analysis now follows the simplified Mutual Funds Comparer visual
    system: a concise hero and upload card, numbered story sections, compact
    surface-backed metrics, right-aligned live inferences, optional reading
    guides and a collapsed technical audit. Repeated prose and loose status
    blocks were removed without changing any calculation contract.
15. Holdings Analysis now applies data-aware disclosure. Missing stock or fund
    groups are labelled explicitly in the overview, sections without usable
    calculations are hidden, and the redundancy section shows the five highest
    fund-pair similarities plus the five largest repeated underlying holdings
    instead of only a sentence summary.

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
   The first source-readiness workspace and compliant NSE manual CSV importer are
   complete; automated NSE collection remains disabled under the published terms.
8. **Evidence-grounded analyst** — answer questions only from approved local
   calculations and documents, with source, timestamp, and calculation citations.

### Dashboard portfolio story foundation — complete

- The Dashboard now carries the current uploaded portfolio into the front-page
  story: current value, net return, portfolio XIRR, and observed excess return
  versus a cash-flow-matched NIFTY 50 comparison.
- Supporting context includes the matched 10Y G-Sec return, valuation date, risk-
  history coverage, beta, Sharpe ratio, and maximum drawdown when available.
- Holdings and results remain browser-memory-only. The copy explicitly treats
  benchmark outperformance as observed excess return, not validated persistent
  alpha, and discloses the current-holdings backtest limitations.

### Portfolio performance and Alpha Opportunities — queued

Build this in dependency order so the opportunity layer rests on auditable
portfolio performance rather than a current-holdings approximation:

1. Add transaction-based performance using dated purchases, sales, dividends,
   fees, taxes, deposits, and withdrawals when those records are available.
2. Replace the temporary 0% risk-free assumption with an approved RBI 91-day
   T-bill history aligned to each performance period.
3. Complete permitted historical-price coverage for the portfolio's ETFs and
   equities, while continuing to exclude instruments such as the NCD until a
   genuine mark-to-market or cash-flow history exists.
4. Add position-level return and risk attribution, including volatility and
   drawdown contribution, with reconciliation to portfolio totals.
5. Build an **Alpha Opportunities** layer combining independently validated
   valuation, momentum, earnings, seasonality, and market-regime evidence. For
   every candidate, show the evidence, uncertainty, and estimated effect on
   portfolio concentration, beta, and drawdown risk before any user decision.

This remains a read-only research workflow. Candidate ranking must not be
presented as guaranteed alpha, a recommendation, or an automated trade.

### Unified EOD refresh — complete

- A single EOD update now refreshes current and completed index data,
  institutional flows, RBI/currency context, permitted global-risk series,
  futures/OI, NIFTY 500 breadth and five-year ranking history, monthly leaders,
  ten-year local history, official RBI long-run Sensex/WPI history, sentiment,
  and its saved evidence snapshot.
- After acquisition, every derived workspace is reloaded: Dashboard summaries,
  Screener, Seasonality, Events, Earnings, regime-validation readiness, and the
  current in-memory Portfolio story.
- If a portfolio is loaded, the refresh prefers current AMFI NAV, Google Finance
  when the user enabled it, and newly stored local EOD prices. Uploaded values
  remain visible fallbacks for instruments without an approved current source.
- Stages are fault-isolated: one unavailable provider no longer prevents later
  datasets and workspaces from refreshing, and the completion notice identifies
  unavailable stages instead of claiming an all-clear.

### Connected Dashboard market story — complete

- The Dashboard now opens with an infographic narrative that connects the
  validated Nifty 50 regime, full NIFTY 500 breadth, 20-session tape, realised
  volatility, futures/OI positioning, historical regime outcomes,
  current-month seasonality, and reviewed macro catalysts.
- Each completed NIFTY 500 EOD refresh persists a restart-safe market-context
  snapshot. The story ranks the strongest and weakest stored indices and the
  strongest and weakest equal-weight NIFTY 500 sectors by aligned 20-session
  excess return versus Nifty 50, with coverage and survivorship limits visible.
- Historical analogues show 5-, 20-, and 60-session mean/median outcomes,
  positive frequency, worst return, and average maximum drawdown for the current
  trailing-only regime. Overlapping-window and survivorship-bias limitations are
  visible beside the results.
- An uploaded portfolio is joined locally in the browser. The story explains its
  equity and defensive allocation, beta, current-holdings drawdown, and a clearly
  labelled beta-scaled sensitivity to the 20-session historical analogue. This
  is scenario context, not a forecast, recommendation, or promise of protection.
- The final panel names the evidence that could change the view—participation,
  derivatives-history readiness, and the next verified macro catalyst—so the
  narrative remains falsifiable rather than becoming a static opinion.

### Historical Regimes story foundation and early-episode evidence spine — complete

- Added a dedicated **Historical regimes** workspace and local API using the
  completed daily history already stored for every supported index.
- `historical-regimes-v9` keeps the transparent daily 20% bull/bear reversal,
  isolated 10–20% corrections, rapid-bear candidates, duration, confirmation
  delay, recovery to the prior peak, and 20/60/120/252-session paths from each
  episode extreme.
- Added a 1875-present Indian market story map. Every era must answer four
  questions: what happened, how it happened, what came out of it, and how the
  market recovered or adapted. Quantitative tables support that account rather
  than becoming the product's main output.
- Frozen a frequency ladder: event/annual evidence for 1875–1978,
  monthly/quarterly for 1978/79–1990, weekly/monthly for 1990–1995, and daily
  with weekly/monthly context from 1995 onward. The backend can roll validated
  closes to period-end weekly, monthly, quarterly, and annual observations and
  never interpolates missing prices.
- The initial era scaffolds cover exchange formation, the controlled-capital
  period, benchmark formation, liberalisation and market-structure reform,
  electronic-market/global-shock history, the pre-GFC boom and crisis,
  post-crisis resets, and the pandemic/inflation transition. Each scaffold
  carries an evidence grade, analysis frequency, and visible research state so
  an unfinished narrative cannot look fully validated.
- Registered official SEBI, BSE, NSE Indices, and RBI source families in the
  interface. The numerical spine now imports seven RBI Handbook series: annual
  BSE Sensex averages, all-commodities WPI, real GDP growth, call-money rates,
  INR/USD annual averages, the central gross fiscal deficit as a share of GDP,
  and the end-financial-year foreign-exchange reserve stock. The joined
  financial-year timeline contains 75 annual periods; each
  series retains its own honest coverage rather than being forward-filled.
- Official observations are stored separately from daily candles with their
  financial-year label, honest annual frequency, publication URL, publication
  vintage, authority, unit, and stated index base. Overlapping RBI publication
  vintages are retained; the latest vintage resolves the displayed series.
- The WPI importer retains all six published base periods and uses the latest
  base block when the current Handbook publishes overlapping observations.
  Year-on-year WPI change is withheld across a base break instead of turning a
  rebasing discontinuity into false inflation.
- Historical Regimes now shows the imported coverage, latest values and an
  12-column financial-year evidence table joining market, growth, inflation,
  money-market, currency, fiscal, and reserve observations. The official-history
  update is idempotent and is included as a fault-isolated EOD Update stage.
- Added four cited, source-linked episode stories for 1978/79-1995: the
  1979-80 growth break and rebound, the late-1980s acceleration with widening
  imbalances, the 1991 balance-of-payments crisis and rupee reset, and the
  liberalisation/market-structure rebound. Each chapter leads with what
  happened, how it happened, what followed, and how markets adapted, then shows
  the exact official annual observations supporting the narrative.
- `historical-regimes-v5` extends the sourced story through 2003-04 with three
  more chapters: electronic trading and dematerialisation, Asian-crisis
  transmission without a repeat of the 1991 reserve break, and the technology
  boom/bust followed by settlement-system repair. Official NSE milestones,
  SEBI annual reports and reform history, and RBI crisis/growth history anchor
  the narrative. Each chapter also displays the Sensex annual-change low and
  the foreign-exchange-reserve path across its window.
- `historical-regimes-v6` carries the sourced story through 2009-10. One new
  chapter follows the 2003-08 credit, investment, capital-flow and earnings
  expansion; a second follows global-crisis transmission, the 2008-09 market
  and currency shock, RBI liquidity support, fiscal widening and the first
  annual-market stabilisation. RBI Annual Reports 2007-08 and 2008-09 plus the
  2008-09 operations record anchor the causal account, while the seven-series
  annual spine remains the numerical evidence layer.
- `historical-regimes-v7` carries the sourced story through the 2019-20
  pre-pandemic boundary with four separate chapters: post-GFC recovery and
  inflation tightening; the growth slowdown and 2013 taper/rupee shock;
  disinflation, flexible inflation targeting and the demonetisation/GST
  transition; and the 2018-20 NBFC-liquidity and activity slowdown. The real-GDP
  spine now joins RBI Handbook 2006, 2016, 2023 and 2024 vintages, preserving the
  2004-05/2011-12 base transition and allowing official contractions.
- `historical-regimes-v8` carries the sourced story through 2024-25 with four
  more chapters: the pandemic activity stop and emergency stabilisation; the
  reopening and liquidity-supported rebound; the Ukraine/inflation shock and
  250-basis-point tightening cycle; and disinflation with resilient growth
  under restrictive policy. RBI Annual Reports and the July 2020 Financial
  Stability Report anchor the causal account. A new 2026 Annual Report GDP
  vintage adds revised 2023-24 and completed 2024-25 growth at 2022-23 prices;
  its starred 2025-26 advance estimate and repeated composition-share columns
  are deliberately excluded from historical actuals.
- `historical-regimes-v9` adds a ten-category fingerprint to every sourced
  episode: trend, breadth, leadership, volatility, flows/liquidity,
  rates/currency/credit, global risk, derivatives, earnings/valuation, and
  macro growth/inflation. Daily selected-index and FRED market evidence is used
  only where its dates overlap the episode; annual RBI evidence remains at its
  honest frequency. Unavailable point-in-time breadth, membership, derivatives,
  flow, earnings and valuation histories stay visibly unavailable rather than
  being inferred from current constituents or hindsight. A recurring-trait map
  compares only traits observed in at least two episode windows. These are
  retrospective full-window descriptors and are explicitly blocked from the
  current-regime classifier until entry-date snapshots and held-out validation
  exist.
- `historical-regimes-v10` creates the first outcome-blind entry information
  set for every sourced episode. Price trend and volatility plus aligned global
  market observations use only dates available by the episode start; forward
  20/60/120/252-session outcomes are stored separately. The episode sequence is
  split chronologically into the earliest 70% of eligible entry snapshots for
  discovery and the latest 30% for held-out testing; documentary-only episodes
  stay outside the validation sample. Repeated discovery traits are compared with later matches, but
  classifier admission stays blocked until there are at least three held-out
  matches, multiplicity/stability checks, effective-dated membership, and
  release-dated unrevised macro, credit, flow, derivatives, earnings and
  valuation histories. Current RBI Handbook vintages continue to support the
  retrospective story only and never enter an entry snapshot.
- `historical-regimes-v11` adds a formal point-in-time evidence-readiness
  ledger. Macro growth/inflation, rates/currency/credit, external-balance and
  effective-dated membership families are audited separately. An observation
  can enter an entry snapshot only when its publication date and revision state
  are retained; a Handbook retrieval vintage never substitutes for the date an
  investor could first know the value. Retrospective rows remain available to
  the story layer and visibly excluded from historical decision sets.
- `historical-regimes-v12` begins the release-native evidence store with five
  explicitly registered RBI balance-of-payments and external-debt releases.
  Observation date, original publication date, revision state and source
  identity are retained separately; only releases published by an episode's
  entry date can enter that historical information set.
- `historical-regimes-v13` adds a continuous monthly non-food bank-credit
  vintage from RBI's official Sectoral Deployment of Bank Credit archive for
  2024 onward. The importer discovers releases from the official year
  catalogue, preserves each publication date, records the stated year-on-year
  growth rate, and uses the actual last reporting Friday when the release
  supplies it. Previously stored release IDs are not downloaded again. Missing
  or malformed catalogue years remain visible in the EOD source audit rather
  than being interpolated or replaced with a later Handbook value.
- `historical-regimes-v14` adds the first continuous release-native policy-rate
  cycle. Six original RBI decision and implementation pages preserve the full
  May 2022–February 2023 tightening path from 4.40% to 6.50%, including each
  effective/publication date, stated rate change, source URL and initial-release
  status. The parser requires the visible RBI date to match the effective date
  and the extracted rate to match the explicitly registered decision; changed
  page structure or a conflicting value is rejected rather than guessed. These
  event observations can enter an episode snapshot only from their publication
  date. Earlier policy cycles and post-February-2023 decisions remain visibly
  incomplete, so the rates/currency/credit family is still partial rather than
  promoted to a complete historical classifier input.
- Market cycles and economic cycles are deliberately separate. Recession and
  depression sections remain visibly unclassified until a versioned definition
  and authoritative point-in-time macro history are available; an equity
  drawdown never silently becomes an economic label.
- The page records the intended research architecture: point-in-time evidence,
  cycle identification, multi-factor fingerprints, behavioural hypotheses, and
  held-out outcome/analogue testing. Human emotion is represented only through
  measurable hypotheses such as participation, crowding, volatility, flows,
  leadership and recovery—not asserted as directly observed fact.
- Next, extend release-native coverage to pre-May-2022 and post-February-2023
  policy decisions, fuller balance-of-payments, external-debt and macro histories with their original release
  dates and revisions, populate effective-dated membership,
  and expand the held-out sample. Only traits that survive coverage gates,
  multiplicity/stability checks and later unseen regimes may be proposed for
  the current classifier.

### Backtests workspace foundation — complete

- Added a dedicated **Backtests** sidebar workspace and research registry.
- The page freezes the intended contract: pre-declared hypothesis, point-in-time
  information set, implementation frictions, chronological validation, and a
  result narrative that includes failures and regime dependence.
- The initial queue covers historical-regime transitions, breadth/relative
  strength, all-index seasonality, earnings/event reactions, and portfolio
  overlays. Every family remains visibly blocked until its source and validation
  contract is auditable; no strategy result or approval is implied.
- The registry starts empty by design. Discovery and held-out results, costs,
  failed variants, multiple-testing controls and benchmark choice must be
  reviewable before a test can move beyond exploration.

### Backtests v1 · historical-regime entry traits — complete

- Registered the first research contract using the existing
  `historical-entry-validation-v1` information set; the Backtests page does not
  redefine entry factors, episode boundaries or the chronological 70/30 split.
- The test compares repeated traits formed only from entry-date evidence with
  separately stored 252-session return and drawdown outcomes. Discovery and
  held-out periods, episode counts and unmatched or failed traits remain
  visible.
- A trait needs the same directional outcome across at least three held-out
  episode matches before its sample gate can pass. Even a passed sample gate
  remains research-only until stability and multiple-testing checks plus fuller
  point-in-time factor coverage exist.
- The registry explicitly marks transaction costs as not applicable because
  this is an episode-classification study, not a simulated portfolio or trade
  strategy. No test is approved for decision support.

### Backtests v2 · all-index month seasonality — complete

- Registered a second research contract covering month-of-year effects across
  every supported index with sufficient stored history; unavailable indices
  remain visible instead of silently shrinking the universe.
- Every index history is split chronologically in half. Discovery-month excess
  returns are tested against the other months, then Benjamini-Hochberg
  correction is applied across the complete index-by-month family—not one
  index at a time.
- The later half is not used to select a month. A corrected discovery candidate
  survives only when the held-out excess retains its direction and independently
  has p < 0.05. Failed directions and failed held-out significance remain in the
  payload and the interface reports a valid negative result when nothing
  survives.
- This is statistical effect validation, not a monthly trading simulation.
  Overlapping sector indices are not independent; no turnover, costs or
  investable portfolio are claimed, and no result is approved for decision
  support. Weekday and turn-of-month families remain future contracts.

### Backtests v3 · point-in-time evidence admission — complete

- Registered the release-aware regime-factor contract before testing any new
  factor/outcome relationship. The Backtests page now shows the same evidence
  families and admission state as Historical Regimes.
- Release-dated observations, retrospective-only rows, required series and the
  next missing source are visible for every family. The contract remains
  blocked while official credit/external-balance release vintages and
  effective-dated index membership are incomplete.
- A blocked admission is an expected research result. Revised historical facts
  cannot silently improve an old signal, and current constituents cannot be
  projected backwards into breadth or leadership tests.

### Historical Regimes v12 · RBI release-vintage importer — complete

- Added a conservative, explicitly registered importer for official RBI
  balance-of-payments and external-debt press releases. The first five source
  pages preserve observation date, publication date, preliminary/provisional
  status, source URL and release identifier.
- Current-account surpluses and deficits are stored as signed US-dollar-million
  observations; external debt is stored as a US-dollar-million stock. Signed
  deficits are permitted only when the source metadata explicitly opts into
  non-positive values.
- Release-native collection is best effort and independent of the existing RBI
  Handbook refresh: one unavailable or structurally changed press-release page
  is reported without erasing the long-run retrospective story layer.
- Entry snapshots select only observations whose observation date and release
  date were both known by the episode start. Later releases and later revisions
  remain excluded. Handbook rows without original release metadata remain
  story-only.
- The first registry is deliberately small and auditable. It establishes the
  ingestion and point-in-time contracts; it does not yet provide continuous
  historical coverage.

### Backtests v4 · release-aware entry evidence — complete

- Historical-regime entry snapshots now consume the stored release-native RBI
  evidence for rates, currency, credit and external balance, and separately for
  macro growth and inflation.
- A factor can be visibly partial when fewer than its required release-dated
  series were known at entry. The interface reports ready and partial factors
  separately instead of hiding partial historical evidence.
- No new trait, prediction or trading rule is inferred from the first sparse
  release set. The wider factor-admission gate remains blocked until coverage
  and effective-dated index membership are sufficient.

### Mutual Funds Comparer foundation — complete

- Added a dedicated **Mutual Funds Comparer** workspace to the sidebar.
- The page freezes an exact-scheme contract: AMC, plan, option and AMFI scheme
  code must match; a regular plan, IDCW option or similarly named scheme is
  never substituted for the requested Direct-Growth series.
- The five reviewed AMFI mappings already used by Portfolio Analysis are shown
  as the audited starting set, with their portfolio-only readiness clearly
  separated from comparison, ranking or recommendation.
- The planned report covers aligned trailing/CAGR returns, volatility, maximum
  drawdown, Sharpe, Sortino and benchmark excess. Category-appropriate
  benchmarks are required, and unlike fund categories will not be placed on one
  leaderboard.
- Broad AMFI catalogue discovery, category metadata and benchmark mapping are
  intentionally still pending. NAV history alone does not establish expense
  history, historical holdings, exit loads, taxes or investor cash flows.

### Mutual-fund holdings analysis v1 — complete

- Added one-step local CSV/XLSX upload to the Mutual Funds Comparer. The first
  table needs a fund or scheme name plus current value, invested amount or
  portfolio weight; weights are normalized across valid rows.
- Category allocation uses an uploaded category first, then the five reviewed
  exact AMFI scheme mappings, then transparent name-based broad-category rules.
  Unresolved schemes remain visibly unclassified.
- XLSX files may include an optional `Underlying Holdings` sheet with Scheme,
  Security and Weight %. Pairwise overlap is calculated only from these actual
  uploaded security weights. Results with less than 95% coverage on either fund
  are labelled as partial lower bounds.
- Added fund allocation, category allocation, concentration HHI, effective fund
  count, largest fund/category weights, pairwise overlap and portfolio
  look-through exposure. Validation issues remain visible.
- Added deterministic review prompts for single-fund/category concentration,
  high overlap, missing classifications, absent holdings detail and excessive
  fund count. These prompts are not product recommendations or buy/sell advice.
- Uploads remain in request/browser memory and are not written to the database.
  Expense ratios, exit loads, taxes, investor risk capacity and transaction
  cash flows are outside this slice.

### Mutual-fund performance comparison v1 — complete

- The same holdings upload now requests official AMFI NAV history for every
  reviewed exact Direct-Growth scheme in the file. Unreviewed names remain
  visible as unmatched; similarly named plans or options are never substituted.
- All measured funds use one intersection of available NAV dates, capped at 253
  common observations. The table reports aligned total and annualized returns,
  annualized volatility, maximum drawdown, Sharpe and Sortino from that same
  window.
- The first slice uses a disclosed 0% annual risk-free assumption. It does not
  silently infer a current deposit or Treasury rate, and it withholds ratios
  when the common history is insufficient.
- Official NAV performance remains separate from the holdings/category and
  overlap analysis. Expense ratios, exit loads, taxes, category benchmarks and
  investor cash flows are not included, and the table does not rank or recommend
  funds.
- NAV retrieval runs as a separate background request with a bounded source
  timeout, so slow or unavailable AMFI responses do not block category,
  concentration, overlap or diversification results.
- Category-specific benchmark series and longer three/five-year aligned windows
  remain the next Mutual Funds Comparer milestones.

### Mutual-fund scheme catalogue and classification v2 — complete

- The comparer now reads AMFI's current complete NAV report and builds a cached
  catalogue containing only current `Direct Plan` + `Growth` rows. Regular,
  IDCW, dividend, payout and reinvestment options are excluded before matching.
- Reviewed exact scheme codes take precedence. Other uploaded names require one
  exact normalized scheme-name match; duplicate candidates remain visibly
  ambiguous and no nearest-name substitution is made.
- Each successful match exposes the official scheme name, scheme code, AMC,
  latest NAV/date, stable mapped category, raw AMFI category heading and match
  status. The raw heading remains available to audit every local category.
- Category normalization is versioned as `amfi-category-map-v1`; catalogue
  behavior is versioned as `amfi-direct-growth-catalogue-v1`.
- Catalogue retrieval runs independently of allocation and performance work, so
  an unavailable official report cannot erase uploaded analysis or trigger a
  guessed match.
- Category benchmark mapping and three/five-year performance windows are next.
- Status: **held pending user-file validation**. The completed upload,
  catalogue and one-year performance foundations remain available, but no new
  Mutual Funds Comparer milestone will be started until representative user
  files can be tested.

### Mutual-fund true-diversification and holdings overlap v3 — complete

- Use the uploaded scheme summary to establish the investor's allocation to
  each fund, then map Regular and Direct plan variants to their shared
  underlying scheme portfolio for holdings analysis. Plan-specific NAV
  performance must remain separate and continue to use exact scheme codes.
- Acquire each fund's latest disclosed security-level portfolio from a
  permitted, auditable source, with an optional `Underlying Holdings` workbook
  sheet retained as the manual fallback. Record the portfolio date and source;
  never substitute a similarly named fund or silently mix disclosure dates.
- Normalize constituents by ISIN/security identity and calculate pairwise fund
  overlap as the sum of the smaller security weight in each shared holding.
  Report both overlap percentage and coverage so incomplete disclosures cannot
  appear artificially diversified.
- Calculate the investor's combined look-through exposure using the actual
  amount invested in each fund. Show repeated security, sector and market-cap
  exposure; unique exposure contributed by each fund; effective concentration;
  and large-, mid- and small-cap allocation across the complete portfolio.
- Highlight funds that add little incremental diversification and explain the
  duplicated holdings behind that result. Keep this descriptive and
  evidence-linked: do not turn overlap alone into a buy, sell or switch
  recommendation.
- Acceptance example: holdings in a large-cap, mid-cap and small-cap fund must
  reveal both their stated cap allocation and any repeated securities at the
  fund-pair and combined-portfolio levels.
- Implemented the plan-independent holdings identity, ISIN-normalized overlap
  engine, investor-weighted combined look-through, repeated holdings, sector
  exposure, effective security count, per-fund unique/repeated contribution,
  mandate-level market-cap allocation and disclosure coverage/status tables.
- Added automatic official month-end disclosure adapters for Nippon India,
  Motilal Oswal, Axis, SBI, WhiteOak Capital, Edelweiss and PPFAS, plus a bounded ICICI Prudential official-archive
  adapter. Nippon's large/mid/small acceptance example resolves
  all three portfolios. The representative 14-fund upload now parses its `Fund`
  and `Current Value` columns and resolves all five Motilal Oswal portfolios.
  Live Axis validation selected the official 30-Sep-26 consolidated workbook,
  parsed 79 scheme sheets, and resolved Axis Value Fund with 86 ISIN holdings
  and 92.98% captured portfolio weight. ICICI's September 2026 archive exposes
  one workbook per scheme; only requested schemes are parsed, with ZIP entry,
  size and expansion limits. Because ICICI's download API rejects non-browser
  clients, the local adapter uses the newest official archive already downloaded
  from the disclosure page and reports a visible source failure when it is absent.
  End-to-end validation on the representative 14-fund workbook now resolves 10
  funds, captures 52.02% of investor-weighted look-through exposure and produces
  a 33.73% highest observed pairwise overlap from disclosures dated 30-Sep-26.
  SBI's public catalogue now selects the newest official consolidated workbook;
  live validation resolved SBI Arbitrage Fund with 196 positive-ISIN positions
  and 97.92% captured AUM. Futures rows without an ISIN are deliberately excluded,
  and the interface warns that arbitrage-fund overlap is gross security redundancy,
  not net directional equity exposure. Unsupported AMCs remain explicit
  adapter-pending rows. WhiteOak's public regulatory catalogue now selects the
  newest official scheme workbook; live validation resolved WhiteOak Capital
  Multi Asset Allocation Fund from 30-Sep-26 with 200 positive-ISIN positions
  and 83.97% captured weight. Non-ISIN derivatives, cash, reverse-repo and TREPS
  balances remain outside security-level overlap and are exposed through coverage.
- Edelweiss now has a bounded adapter for its official statutory spreadsheet
  catalogue and a consolidated/per-scheme workbook parser. Its API rejects the
  local server, so the adapter can use the newest official workbook downloaded
  from the browser disclosure page and otherwise reports the source as unavailable;
  no aggregator data is substituted. Live validation on 14-Oct-26 resolved
  Edelweiss Multi Asset Omni Fund of Fund from the 30-Sep-26 workbook with 10
  positive-ISIN fund-unit holdings and 99.41% captured weight. Fund-of-Funds
  units with valid ISINs are retained, while TREPS, cash and other non-ISIN rows
  stay outside the overlap calculation and reduce disclosed coverage.
- PPFAS discovery now parses the official portfolio-disclosure page, selects the
  newest consolidated monthly workbook and reads only requested scheme sheets.
  Live validation on 14-Oct-26 resolved Parag Parikh ELSS Tax Saver Fund from
  30-Sep-26 with 46 positive-ISIN positions and 96.82% captured weight. Cash,
  derivatives and other non-ISIN balances remain outside security overlap.
- Added dated security-level large/mid/small-cap classification from AMFI's
  official 30-Jun-26 average-market-cap workbook. The parser validates all
  5,427 rows and the required 100 large-cap / 150 mid-cap / 5,177 small-cap
  split, then joins holdings only by exact ISIN.
- The combined investor-weighted view now separates actual classified equity
  exposure from `Unclassified / not captured`. Unsupported funds, missing AMC
  disclosures, debt, cash, derivatives, foreign securities, fund units and
  unmatched ISINs are not guessed into a market-cap bucket. The former
  fund-category mandate allocation remains available separately for audit.
- The simplified overview now shows the security-level stock-size mix beside
  asset allocation and largest fund positions, with AMFI date and full-
  portfolio classification coverage. A source failure remains visible instead
  of falling back to the mandate view.
- Simplified the comparer interface into a layman-facing overview: upload,
  asset/fund allocation, the three most important overlap pairs, a transparent
  0–100 diversification score, and exactly three evidence-led improvement
  paths for every valid upload: simplify the fund structure, reduce duplicated
  exposure, and improve benchmark-relative return efficiency. Each path cites
  the available fund-count, weight, category or overlap evidence; missing
  holdings remain a visible data gap rather than zero overlap. Return efficiency
  is framed through common-period rolling returns, drawdown, consistency and
  costs, with no forecast or promise of higher future returns. Technical
  catalogue, NAV, source-audit and validation tables remain part of the local
  calculations but are no longer displayed in the primary workflow. The score
  is 80% structural diversification and 20% current-regime fit when a validated
  dashboard regime is available; it is explicitly preliminary when official
  holdings coverage is incomplete.

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
