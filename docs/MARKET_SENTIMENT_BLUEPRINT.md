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

1. **Risk appetite:** constructive, mixed, or defensive, derived mainly from
   cash trend, participation, and flows.
2. **Stress:** low, elevated, or acute, derived mainly from volatility,
   currency/rates, and the global backdrop.

Candidate lifecycle labels:

- **Constructive:** broad trend and participation are healthy; stress is low.
- **Fragile advance:** headline trend is positive but breadth, flows, or macro
  confirmation is weak.
- **Transition:** evidence is mixed or a prior regime is changing.
- **Orderly risk-off:** trend and participation are weak without acute stress.
- **Confirmed stress:** several independent clusters are adverse.
- **Stabilisation:** stress is easing, but constructive participation is not yet
  restored.
- **Data quality:** missing or stale inputs prevent a dependable classification.

Count clusters, not raw indicators. One red volatility family should not outweigh
five calm independent families merely because it contains several related rows.

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
- [ ] Add confirmed NSDL FPI reconciliation as a separately labelled series;
  never silently replace or mix it with provisional exchange activity.
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
  behaviour, then define and test build-up, unwinding, and short-covering labels.

### Phase 3 — global source decision

- Select providers only after checking permissions, EOD timing, symbols,
  historical coverage, and failure behaviour.
- Add global inputs as their own cluster, never as required hidden dependencies.

### Phase 4 — regime validation

- Store daily factor snapshots and regime versions locally.
- Run walk-forward and event validation.
- Publish the evidence table and limitations before activating a composite label.

### Phase 5 — portfolio reference

- Pass the validated regime and confidence to Portfolio Analysis.
- Show exposure diagnostics and review prompts without executing or prescribing
  allocation changes.

## Reference material

- [Tickertape Market Mood Index methodology](https://www.tickertape.in/blog/how-mmi-can-help-in-timing-your-investments-better/)
- [NSE India VIX methodology](https://www.nseindia.com/static/products-services/indices-indiavix-index)
- [NSE FII/FPI and DII reports](https://www.nseindia.com/reports/fii-dii)
- [RBI data releases](https://statistics.rbi.org.in/)
- [Canary regime dashboard contract](https://github.com/osauer/canary/blob/main/docs/docs/internals/regime-dashboard.md)
- [5 Stars market dashboard](https://github.com/lssee003/trading-dashboard)
