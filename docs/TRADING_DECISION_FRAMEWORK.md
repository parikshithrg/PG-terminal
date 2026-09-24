# Trading decision analysis framework

This document records the reasoning standard to use when interpreting PG-terminal
evidence. It supports disciplined analysis; it does not turn an observed pattern
into an automatic trade recommendation.

## Core principle

Separate **economic attractiveness** from **statistical reliability**.

A large historical average can be interesting while still being too uncertain
to trade. Seasonality is supporting evidence, not a standalone entry signal.

## Standard review sequence

1. **Describe the sample precisely**
   - Instrument, period, as-of date, and whether the current incomplete period is excluded.
   - Observation count, average and median return, positive-return frequency,
     average range, and best/worst observations.
2. **Measure the apparent edge**
   - Compare the selected period with all other periods, not with zero alone.
   - Report the excess return and whether a few outliers dominate the mean.
3. **Test statistical significance**
   - Use the two-sided Welch test because the selected and comparison samples
     can have unequal variance and unequal size.
   - Report the p-value without describing a near miss as significant.
4. **Correct for multiple testing**
   - When examining all twelve months, apply the Benjamini-Hochberg false
     discovery rate adjustment.
   - Use the adjusted q-value for the discovery decision rather than selecting
     whichever raw p-value looks best.
5. **Require chronological validation**
   - Discover the pattern only in the earlier training period.
   - Evaluate the later held-out period independently.
   - A pattern survives only when the training result is significant, the test
     effect has the same direction, and the held-out result meets its threshold.
6. **Check stability and risk**
   - Compare early and recent subsamples, positive-year frequency, dispersion,
     worst outcome, drawdown/range, and sensitivity to exceptional years.
   - Treat a direction reversal between train and test as evidence of instability.
7. **Translate evidence into a decision**
   - Classify the evidence as confirmed, suggestive, weak, or contradicted.
   - Do not use seasonality alone to enter a position.
   - Require contemporaneous confirmation such as trend, relative strength,
     breadth, liquidity, and relevant fundamental or event context.
   - Define position size, invalidation level, expected holding period, and exit
     conditions before acting. Avoid leverage when evidence is only suggestive.

## Interpretation language

- **Confirmed:** statistically significant after adjustment and survives the
  chronological held-out test in the same direction.
- **Suggestive:** economically meaningful and directionally stable, but does not
  pass all significance or held-out requirements.
- **Weak:** small sample, high dispersion, outlier dependence, or no statistical
  support.
- **Contradicted:** the held-out period reverses direction or materially rejects
  the training-period pattern.

## Nifty PSU Bank reference example

The ten-year sample showed October averaging approximately +7.32%, but the
full-sample Welch p-value was about 0.057 and the twelve-month adjusted q-value
was about 0.684. The later held-out sample remained positive but was not
significant. The correct classification was therefore **suggestive, not
confirmed**. September weakness reversed direction in the later sample and was
not stable. The resulting decision was to use October seasonality only as a
contextual tailwind and require live confirmation before considering a long.

