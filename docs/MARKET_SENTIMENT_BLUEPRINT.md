# Market Sentiment and Regime blueprint

Status: Phase 1 complete; Phase 2 in progress. The domestic-core page calculates local EOD
trend, F&O-equity participation, price strength, and realised volatility. No
external source or portfolio action is approved merely by this document.

## Purpose

The Market Sentiment page should answer:

> What market environment are Indian equities operating in, which independent
> evidence supports that conclusion, and how reliable and current is it?

It is a broad-market context layer for research and portfolio-risk review. It is
not a price prediction, trade signal, or automatic asset-allocation engine.

## Design lessons from reference products

Tickertape's Market Mood Index combines FII activity, volatility and skew,
momentum, breadth, price strength, and demand for gold. This is a useful factor
checklist, but PG-terminal should show the underlying observations and validate
its own thresholds rather than reproduce Tickertape's proprietary score.

Two open-source dashboard patterns are particularly useful:

- Group correlated indicators into evidence clusters so the same risk theme
  cannot vote several times.
- Give every row a value, band, source, as-of time, freshness state, and reason.
  Missing or stale evidence should reduce confidence rather than silently become
  neutral.

PG-terminal should begin with an explainable categorical model. A 0-100 score
can be added only after its weights and thresholds survive walk-forward testing.

## Proposed evidence clusters

### 1. Domestic cash trend

- Nifty 50 relative to 20-, 50-, and 200-session averages.
- 20- and 50-session average slopes.
- Nifty 50 drawdown from its 52-week high.
- Broad-market versus large-cap relative strength.

Primary source: validated completed Kite daily candles stored locally.

### 2. Participation and price strength

- Percentage of the 210-stock NSE F&O universe above 20-, 50-, and 200-session averages.
- Daily and five-session advance/decline balance.
- Percentage near 52-week highs minus percentage near 52-week lows.
- Sector participation and concentration of the index move.

The 210-stock F&O universe is the intentional scope because it concentrates on
liquid, derivatives-eligible equities and supports a later price/open-interest
positioning layer. Primary source: locally stored validated candles and the
versioned NSE F&O eligibility list. Exchange-published breadth can be a
cross-check, not a hidden substitute.

### 2A. Derivatives positioning extension

For each eligible stock future, classify price and open-interest changes using
an explicit daily convention:

- price up and OI up: long build-up;
- price down and OI up: short build-up;
- price down and OI down: long unwinding;
- price up and OI down: short covering.

This requires more than the current equity EOD candles. Contract identity,
expiry, rollover, volume, open interest, and the chosen near-month aggregation
rule must be stored and versioned. Expiry-day and rollover effects must be kept
separate from genuine position changes. Results should show stock counts,
notional or OI-weighted participation, and coverage rather than presenting a
single unexplained long/short score.

### 3. Volatility and downside stress

- India VIX level, five-session change, and rolling percentile.
- 20-session realised Nifty volatility and its change.
- India VIX versus realised volatility.
- Nifty downside range and gap frequency.
- Nifty option skew only after the required option data and methodology are
  verified.

India VIX is the NSE's estimate of expected Nifty volatility over the next 30
calendar days. A high value means high expected movement, not necessarily a
directional decline.

### 4. Institutional flows and liquidity

- FII/FPI cash net purchases over 1, 5, and 20 sessions.
- DII cash net purchases over the same windows.
- FII minus DII balance, normalised by cash-market turnover.
- FII index-futures positioning as a later, separately sourced input.

Primary sources should be the official NSE FII/DII reports and, where needed,
confirmed NSDL FPI data. Provisional and confirmed flows must not be mixed
without labels.

### 5. Currency and sovereign rates

- USD/INR change over 5 and 20 sessions and rolling volatility.
- EUR/INR, GBP/INR, and JPY/INR for broad rupee pressure.
- Cross pairs such as USD/JPY only when a permitted source is selected.
- India 10-year government yield level and 5-/20-session change.
- Yield-curve slope when reliable short-tenor data is available.

Use official FBIL reference FX rates republished by RBI for the first spot-context
adapter. Keep Kite currency futures separate because expiring contracts require
explicit rollover treatment. The RBI government-securities panel supplies the
sovereign-rate observation, with the exact security name stored alongside the
nearest-to-10-year maturity selection. A rising yield or USD/INR is context, not automatically bearish;
the rate of change and confirmation from other clusters matter.

### 6. Global risk backdrop

- S&P 500 and a broad emerging-market benchmark trend.
- Global implied volatility and volatility term structure.
- US dollar trend, USD/JPY, gold/equity relative strength, and Brent crude.
- Asian-market breadth or trend where a licensed, reliable source exists.

This cluster remains unavailable until provider permissions, symbols, update
times, and historical access are documented. Do not scrape an unstable website
or use an unexplained free-data fallback.

## Regime output

Use two visible dimensions before assigning a label:

1. **Market direction:** positive, mixed, or negative, derived mainly from
   cash trend, participation, and flows.
2. **Stress:** low, elevated, or acute, derived mainly from volatility,
   currency/rates, and the global backdrop.

Candidate investor-facing labels:

- **Positive market:** broad trend and participation are healthy; stress is low.
- **Cautiously positive:** headline trend is positive but breadth, flows, or macro
  confirmation is weak.
- **Uncertain market:** evidence is mixed or a prior regime is changing.
- **Weak market:** trend and participation are weak without unusually high stress.
- **High-risk market:** several independent clusters are adverse.
- **Recovering market:** stress is easing, but positive participation is not yet
  restored.
- **Not enough reliable data:** missing or stale inputs prevent a dependable classification.

Internal calculation keys may remain `constructive`, `mixed`, and `defensive`
for compatibility, but the interface must display the plain-language labels
`Positive`, `Mixed`, and `Negative`.

Count clusters, not raw indicators. One red volatility family should not outweigh
five calm independent families merely because it contains several related rows.

### Frozen validation candidate — `market-regime-candidate-v1`

This first candidate is deliberately simple and remains unavailable for trading
or portfolio instructions until walk-forward validation is complete.

| Independent cluster | Weight | Current scoring input |
| --- | ---: | --- |
| Domestic cash trend | 25% | Trend band |
| Participation and price strength | 20% | Equal average of breadth and price-strength bands |
| Volatility and stress | 15% | Equal average of realised-volatility and available India VIX bands |
| Institutional flows | 15% | Unranked until thresholds are validated |
| Currency and sovereign rates | 10% | Unranked until thresholds are validated |
| Global risk | 15% | Unranked until thresholds are validated |

Positive, mixed, and negative internal bands map to `+1`, `0`, and `-1`.
The weighted total is divided by available weight, so missing evidence is never
silently treated as neutral. Classification requires fresh EOD data, at least
80% F&O stock coverage, and at least 60% weighted evidence. Confidence is low at
60%, medium at 75%, and high at 90% available weight, with corresponding stock
coverage requirements of 80%, 90%, and 95%.

Validation-only score boundaries are: Positive market at `>= +55`, Cautiously
positive from `+20` to below `+55`, Uncertain market above `-20` and below
`+20`, Weak market above `-55` through `-20`, and High-risk market at `<= -55`.
A future displayed label requires two-session confirmation. Recovering market is
transition-dependent and cannot be assigned from a single snapshot. These
thresholds are frozen for testing, not asserted as empirically valid.

## Confidence and freshness contract

Every indicator must publish:

- value and unit;
- green/amber/red or unranked band;
- source and source type;
- observation date and retrieval time;
- formula and threshold version;
- freshness state: fresh, not due, pending, stale, unavailable, or error;
- a plain-language reason for its band.

Only fresh observations may confirm a regime. Stale or unavailable inputs lower
confidence and remain visible. A failed provider call must never be translated
into a neutral reading.

## Portfolio context

The regime may support a portfolio review, but should not directly rebalance it.
The Portfolio Analysis page can later show a read-only checklist such as:

- whether portfolio beta and cyclical-sector concentration fit the environment;
- whether position correlations and downside concentration have increased;
- whether new exposure deserves tighter sizing or stronger confirmation;
- whether a stabilising regime is confirmed by portfolio-relevant sectors.

These are review prompts, not target weights or automated transactions.

## Validation before use

1. Freeze every formula and threshold version.
2. Use only information available as of each historical EOD.
3. Fit thresholds on an earlier period and evaluate later periods with rolling
   walk-forward tests.
4. Measure future 5-, 20-, and 60-session Nifty return distributions and maximum
   drawdowns by regime.
5. Report sample count, median, dispersion, worst outcome, false alarms, missed
   stress events, regime duration, and transition frequency.
6. Use hysteresis or a two-session confirmation rule to prevent daily label
   whipsaw, then test the resulting delay explicitly.
7. Compare the transparent rule model with simpler baselines such as Nifty above
   or below its 200-session average. Complexity must earn its place.
8. Do not connect the model to portfolio guidance until the held-out results and
   limitations are displayed in the interface.

## Recommended build order

### Phase 1 — static contract and domestic core

- [x] Build the page frame with regime, confidence, as-of, and six cluster panels.
- [x] Reuse local Nifty history for trend and realised volatility.
- [x] Calculate transparent participation and price strength from all 210 NSE
  F&O equities currently stored locally. This is the permanent liquid-universe
  scope and must not be labelled Nifty 500.
- [x] Display component values without a composite score.

### Phase 2 — official domestic context

- [x] Add India VIX from the authenticated Kite inventory, persist completed
  daily history, and show its level, five-session change, one-year percentile,
  and implied-versus-realised volatility gap.
- [x] Add append-only ingestion of the official NSE combined-exchange FII/FPI
  and DII cash-market report, explicitly labelled provisional, with latest,
  five-session, and twenty-session summaries as local history accumulates.
- [x] Add confirmed NSDL FPI investment as a separately labelled append-only
  series, preserving stock-exchange, primary-market-and-others, and subtotal
  routes with reporting-date lag. It never silently replaces or mixes with
  provisional exchange activity.
- [ ] After enough overlapping observations accumulate, validate any
  side-by-side NSDL/NSE reconciliation measure against their different timing
  and coverage definitions before presenting a numerical difference.
- [x] Add append-only RBI/FBIL currency references (USD, GBP, EUR and JPY) and
  the RBI-listed government security nearest ten-year maturity, preserving the
  exact security label and leaving the cluster unranked until thresholds are validated.
- [ ] Accumulate enough official sessions to show 5-/20-session FX and yield
  changes and validate directional thresholds before scoring the cluster.
- [x] Add contract-keyed, append-only near-month futures price/OI snapshots for
  the 210-stock F&O universe using one post-close bulk quote request. Preserve
  trading symbol, expiry, lot size, and provider token; never compare OI across
  a contract rollover.
- [ ] Accumulate same-contract observations, validate coverage and rollover
  behaviour, then validate the descriptive long build-up, short build-up, long
  unwinding, and short-covering quadrants before allowing them to influence sentiment.
  The interface now provides sortable/filterable contract detail, a 0.25% price
  and 1.0% OI exploratory noise floor, positive volume/OI requirements, and a
  maximum four-calendar-day comparison gap. These safeguards are visible and
  remain excluded from regime scoring pending observed-data validation.

### Phase 3 — global source decision

- [x] Select the Federal Reserve Bank of St. Louis FRED EOD export as the first
  global-context adapter. Preserve the originating series IDs, citations,
  component dates, and provider failure state. S&P 500 and VIX are
  citation-required series; Federal Reserve USD/JPY and broad-dollar series and
  EIA Brent are public-domain/citation-requested series distributed by FRED.
- [x] Add S&P 500 trend, CBOE VIX level/one-year percentile, broad U.S. dollar,
  USD/JPY, and Brent spot as their own append-only, descriptive global cluster.
  The adapter uses one bounded export request and remains outside regime scoring.
- [ ] Accumulate observations, confirm normal publication lags and failures, and
  validate thresholds before allowing global context to influence a regime.
- [x] Evaluate the FRED-distributed Nasdaq Emerging Markets Index candidate.
  It is explicitly marked "Copyrighted: Pre-Approval Required," so it is not
  integrated. Do not substitute an unexplained ETF or scraped proxy.
- [ ] Obtain documented permission for a broad emerging-market equity benchmark
  or select another source whose redistribution terms permit this local use.

### Phase 4 — regime validation

- [x] Store canonical, hashed daily evidence snapshots with an explicit model
  version. Exact reruns are idempotent; changed same-day evidence is preserved
  as another immutable revision for audit rather than overwritten.
- [x] Add a collapsible plain-language interpretation guide that exposes the
  provisional domestic reading, freshness, F&O coverage, cluster coverage, and
  limitations before a composite score is activated.
- [x] Define and freeze `market-regime-candidate-v1` separately from the
  evidence-snapshot version, including weights, score boundaries, freshness and
  coverage gates, missing-data treatment, and confidence levels.
- [x] Run the first trailing-only walk-forward report across 5-, 20-, and
  60-session outcomes, enforce the 80% historical breadth-coverage gate, compare
  with a Nifty 200DMA baseline, and test two-session confirmation. The report is
  exploratory: the current 210-stock universe creates survivorship/membership
  bias, overlapping outcome windows are not independent, and only 60% of the
  candidate weight is historically populated.
- [x] Add the first fixed named-event stress review, covering the 2018 India NBFC
  liquidity stress, 2020 COVID-19 shock, 2022 global inflation/Ukraine shock,
  and June 2024 Indian election-result shock. Report detection timing, entry/
  exit state, returns, drawdowns, and benchmark-relative outcomes; treat these
  hindsight-selected windows as descriptive rather than independent tests.
- [x] Compare every named event with non-overlapping, equal-session control
  windows outside all named events. Expose return, drawdown-severity, and
  stressed-session percentiles rather than selecting a favourable calm date.
- [x] Add the engine and file-schema path for dated point-in-time index membership.
  It activates only when authoritative effective-from/effective-to snapshots are
  present; the current snapshot is never relabelled as historical membership.
- [ ] Populate and audit authoritative point-in-time membership, then repeat the
  study with historically available external clusters.
- [x] Add an external-history readiness audit for institutional flows, confirmed
  FPI, RBI/FBIL macro observations, permitted global-risk series, and futures/OI.
  Require 252 complete sessions for historical features and 312 for a full
  60-session walk-forward outcome. Keep scoring disabled until thresholds are
  frozen and reviewed independently.
- [x] Freeze an outcome-blind Recovering market transition rule for validation:
  require five prior confirmed weak/high-risk sessions, enter only on improvement
  to uncertain/cautiously positive, cap the state at 20 sessions, and exit on
  positive confirmation or renewed risk. Measure outcomes after state assignment.
- [x] Compare recovery-state stability across all eligible indices and named/
  control windows, including Nifty-relative outcomes and relapse/positive-exit
  counts. Keep excluded short-history/thin-breadth indices visible.
- [x] Test incremental value versus each index's base Uncertain/Cautiously
  positive states with minimum-sample and consistency gates.
- [x] Add a historical long/short research map across every eligible index-state
  pair. Long candidates are limited to Positive/Cautiously positive/Recovering
  states; short candidates require validated downside continuation in Weak/High-
  risk states. Post-selloff rebounds remain a separate countertrend study.
- [x] Join each index's latest completed-session state to its validated historical
  map so long, short, watch, avoid, and insufficient-evidence candidates coexist.
  Calculate current state separately from the forward-outcome cutoff and keep
  Nifty 50 as context only.
- [ ] Add candidate-level risk controls, shorter-horizon downside-continuation
  tests, and futures/OI confirmation before treating the board as actionable.
- Publish the evidence table and limitations before activating a composite label.

#### Multi-index extension

- [x] Add the index-selection, benchmark-selection, and automatic history-readiness
  interface. Short-history indices remain visible and automatically become
  current-regime eligible at 252 sessions.
- [x] Generalize trailing-only outcomes to every supported index and add excess
  return, outperformance probability, and relative-drawdown measures versus
  Nifty 50.
- [x] Add constituent-aware breadth from the official current membership snapshot,
  intersected with the liquid F&O universe and withheld below five eligible
  members. This remains subject to survivorship bias.
- [x] Add an exploratory cross-index table ranking eligible indices by historical
  20-session absolute/relative outcomes, outperformance, drawdown, sample size,
  and constituent coverage. Keep it separate from the current broad-market regime.

### Phase 5 — portfolio reference

- Pass the validated regime and confidence to Portfolio Analysis.
- Reorder the Market Sentiment page into a top-to-bottom story: overall regime,
  walk-forward evidence, macro/global drivers, broad-index regime, sector/index
  regimes, and stock-level follow-through.
- Show exposure diagnostics and scenario-based allocation review prompts without
  executing allocation changes.
- Accept locally processed `.csv` and `.xlsx` portfolio uploads only after a
  preview, column-mapping, and validation step. Holdings stay in memory unless
  the user explicitly approves persistence.
- Combine regime confidence/freshness and relevant seasonality evidence with
  portfolio concentration, sector weights, risk contribution, and drawdown
  diagnostics. Keep every recommendation explainable and review-only.

## Reference material

- [Tickertape Market Mood Index methodology](https://www.tickertape.in/blog/how-mmi-can-help-in-timing-your-investments-better/)
- [NSE India VIX methodology](https://www.nseindia.com/static/products-services/indices-indiavix-index)
- [NSE FII/FPI and DII reports](https://www.nseindia.com/reports/fii-dii)
- [RBI data releases](https://statistics.rbi.org.in/)
- [FRED S&P 500](https://fred.stlouisfed.org/series/SP500)
- [FRED CBOE VIX](https://fred.stlouisfed.org/series/VIXCLS)
- [FRED broad U.S. dollar index](https://fred.stlouisfed.org/series/DTWEXBGS)
- [FRED USD/JPY](https://fred.stlouisfed.org/series/DEXJPUS)
- [FRED Brent crude](https://fred.stlouisfed.org/series/DCOILBRENTEU)
- [Canary regime dashboard contract](https://github.com/osauer/canary/blob/main/docs/docs/internals/regime-dashboard.md)
- [5 Stars market dashboard](https://github.com/lssee003/trading-dashboard)
