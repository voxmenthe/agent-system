# Explain the gap stresses and competing gamma views

Read this when creating a reader-facing report. The numerical helper supplies the map; the agent's job is to explain what is noteworthy **in this capture** and how it changes the interpretation. Write concise, visible commentary beside each relevant chart/table in both HTML and Markdown. Define unfamiliar terms on first use, then spend the space on the actual data rather than repeating the methodology.

Use the pattern **observation → interpretation → decision implication → what would change it**. Separate calculated facts from conditional inferences. Choose the strongest few observations; do not mechanically enumerate every row or force a dramatic conclusion when the inputs do not support one.

## Gap-stress map and outcome densities

### Give the reader a way to read the displays

- Each row is a **what-if shift of the closing forward**, not a predicted opening gap or a chronological path. The vertical tick is that scenario's shifted forward; the dotted vertical line is closing cash SPX. They are different references.
- The thick bar spans ±1 log-standard-deviation and the thin bar ±3, around the scenario's modeled log-price center. These are expiry-outcome intervals under an assumed lognormal distribution, not guaranteed trading ranges, stop levels or confidence intervals for the estimated forward. The forward tick need not be exactly at their midpoint.
- The companion density curves show how outcomes are distributed **within each assumed scenario**. Area over a price interval has a probability interpretation inside that illustrative model; the curve's height at a single price is not a probability. A taller peak does not mean its gap scenario is more likely. The overlapping curves are alternatives, not a weighted mixture.
- All shifts retain the same **closing-to-expiry log variance**. Similar relative widths are imposed by construction; dollar widths vary with the shifted forward. This is not evidence that risk is unchanged after a real overnight event, nor a calculation of the variance remaining after that event. Gap size changes location here; it does not estimate a volatility shock.

### Select meaningful features from the current results

| Look for | Explain why it matters |
|---|---|
| Gap displacement relative to `sigma_points` | Compare a selected scenario's shift in points with the closing one-standard-deviation proxy. A shift comparable to that proxy can make the old central band a poor sole reference even before modeling further movement. |
| Overlap or separation of central intervals | Identify which scenarios still overlap the closing band or a named decision level, and which move their central interval beyond it. Overlap does not establish a likely reversal or a probability of returning to the close. |
| A gamma boundary inside a stressed interval | Explain that the illustrated outcomes span different modeled hedging regimes; a single gamma label cannot describe the whole interval. Identify the expiry scope and inventory assumption. |
| Unequal downside/upside delta-wing distances | Contrast the actual skew-aware delta bands with the simpler ATM-lognormal illustrations. Do not attribute smile skew to the shifted lognormal curves or treat a 10-delta endpoint as a 10% physical tail probability. |
| A newer cash-location scenario, or its absence | State the cash observation's timestamp and whether it is genuinely newer. If unavailable, call the map a closing-data stress exercise; do not substitute raw ES for SPX. |

Use `distributions.scenarios`, `distributions.bands`, `forward`, `spot`, `sigma_points`, `delta_bands` and `newer_cash_reference` in the current `analysis.json`. Quantify selected overlaps/distances from those values rather than eyeballing the drawing. State that the outer envelope covers the displayed stresses, not every possible outcome.

## Competing gamma views

### Separate the two questions being varied

1. **Expiry coverage:** compare target, 7-day, 30-day and 90-day portfolios **under the same inventory assumption**. The plotted curves vary expiry coverage using conventional call-long/put-short signs only; they do not show all five inventory assumptions. These portfolios overlap and must not be added together or counted as independent votes.
2. **Inventory assumption:** compare the conventional and reduced-call/reduced-put cases **within one expiry scope**, using the scenario table. These are competing hypothetical dealer books, not measured ownership or fitted probabilities. The all-long/all-short rows are mathematical exposure bounds over retained OI, not two additional forecasts to average in.

The horizontal axis of the gamma plot is hypothetical **spot**, not option strike, time or a price forecast. Its vertical axis is modeled option exposure in **$bn per 1% move**, not observed hedge trades. The zero crossings are model-specific flips under frozen closing volatility/OI and forward/spot ratios. A root is not automatically support, resistance or a price target; no crossing in the displayed scan does not establish that none exists anywhere.

If the assumed book is representative and dealers delta-hedge it, positive gamma implies selling into rises and buying into falls, potentially damping moves; negative gamma implies buying into rises and selling into falls, potentially reinforcing either direction. **Positive is not bullish; negative is not bearish.** Neither sign guarantees price behavior or establishes that these flows dominate other trading. [Cboe's explanation of the hedging mechanism](https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options)

### Highlight the disagreement that changes the reading

- **At the reference price:** say which scopes agree under conventional signs, and whether changing inventory fractions reverses that sign. Agreement across nested scopes is not robustness to ownership assumptions.
- **Between roots:** find price regions where the target bucket and broader portfolio have different signs. Explain the conflict rather than averaging their roots into one “true switch.” Read actual curve signs on either side; do not assume every crossing is negative-below/positive-above.
- **Magnitude as well as sign:** compare exposure near relevant levels and any pronounced increase or fading in sensitivity along the curve. A near-zero aggregate can reflect cancellation between large call/put exposures, not little outstanding optionality. An unsigned concentration is a location of convexity, not proven defense.
- **Which assumption matters most:** compare root displacement from expiry coverage, relative call/put weights and `vol_sensitivity_30d`. If changing the tested weights reverses sign while the tested volatility changes barely move the root, say the interpretation is more sensitive to the tested inventory assumptions. That is a local comparison, not a general ranking of risks.
- **What is relatively stable:** similar 30-/90-day roots may mean additional expiries have little effect on that crossing under this model, even when total magnitude changes. It does not validate dealer sign or imply the extra expiries never matter.

Use `profiles` for model/scope, closing exposure and roots; `grid` with each profile's `curve` for signs at other prices; `level_regimes` for the existing **conventional-only** level table; and `concentrations`, `expiry_buckets`, `vol_sensitivity_30d` and `finite_shocks_30d` for supporting detail. Do not extrapolate beyond the scan. Prefer appropriately rounded levels: interpolated roots on a 201-point grid are not executable tick-precision boundaries.

End with a conditional reading, such as: “If price enters this region, the target-expiry model suggests damping while the broader book still suggests amplification; confirmation would require current price behavior and refreshed inputs, not merely touching the first root.” Adapt the statement to the actual signs and name the boundary or assumption that would change it. Do not invent evidence of a reclaim, rejection, dealer trade or profitable setup.

## Worked observations from the initial archived example

These illustrate the expected explanatory depth, **not levels to reuse in future reports**. They refer to the September 16 closing capture for September 17, 2026 expiry; recompute from the new report's JSON.

- The +1% stress shifts the forward from about 7554 to 7629, roughly one closing standard deviation. Its central interval is about 7556–7703 versus 7481–7626 unshifted. This moves the central outcome region while retaining considerable overlap; it neither forecasts a +1% gap nor promises a return to the close.
- At hypothetical SPX 7600, conventional target-expiry exposure is about **+$4.9bn per 1%**, while 30-day exposure is about **−$29.2bn**. The roots near 7574 and 7635 therefore describe materially different portfolios, with opposing conditional hedge behavior between those boundaries—not two estimates to average blindly.
- Reducing the assumed short-put fraction changes 30-day closing exposure from about **−$63.2bn to +$67.6bn**. In contrast, the tested ±10% total-volatility changes leave its conventional root around 7635–7636, close relative to the scan spacing. Ownership assumptions dominate that particular sensitivity comparison; the stable volatility root does not establish a reliable dealer regime.

## Finish the report, not just the reply

Add brief “How to read this” and data-specific interpretation blocks beside the gap-stress map and competing-gamma views; equivalent natural headings are fine. Keep the key observations visible without opening a technical disclosure. Mirror the explanation in Markdown, preserve numerical artifacts and provenance, and check that commentary matches the displayed capture, units and assumptions. Verify the HTML remains readable at desktop and mobile widths. Leave deep formulas in the methodology and use the response to link the enriched report.
