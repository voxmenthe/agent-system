# Sources, models and interpretation

## Sources and clocks

- [Cboe marking-price documentation](https://www.cboe.com/markets/us/options/market-statistics/product-data/proprietary-index-marking-prices) and its [published closing CSV](https://cdn.cboe.com/resources/marking_prices/eod_marking_prices_list.csv): paired indicative call/put bids and asks, underlying values, message times and series identifiers. This rolling file is not an archive or live NBBO feed.
- [OCC batch documentation](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/series-search-batch-processing) and [SPX series query](https://marketdata.theocc.com/series-search?symbolType=U&symbol=SPX): standard SPX/SPXW series-level OI. Join root, expiry and strike, retaining call and put counts separately. The raw response does not establish its cleared effective date.
- [yfinance history interface](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html): optional five-minute SPX, VIX and ES bars. Preserve each bar's timezone and time; availability and delays vary. `ES=F` is not a verified same-contract, basis-adjusted SPX overnight anchor.

The current parser infers the marking date from the modal option-message date and explicitly uses the corresponding regular-session closing time as the valuation clock. Source timing inference is printed in the stored snapshot. Reject future dates and malformed layouts; do not derive a date from the output filename. Calls and puts at the same root/expiry/strike share the same long-option volatility estimate.

SPXW settlement uses the session close; SPX standard settlement uses the session open. The market calendar handles holidays and early closes. This is an approximation for AM settlement's opening-basket process, not a prediction of the settlement value. Treat a newly introduced/nonstandard root or settlement convention as unsupported until verified. Use [Cboe specifications](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications) when changing this behavior.

## Price-derived layer

For each root/expiry, estimate `F = median(K + (Cmid − Pmid)/D)` from the nearest eleven valid two-sided strikes to closing SPX, where `D = exp(−rT)`. Require at least three and report parity dispersion. Default `r=0` is an explicit short-horizon approximation, not a retrieved yield curve.

Use the OTM side to solve Black prices for total volatility `a=σ√T`. Keep positive bids, non-crossed markets and a bounded OTM spread; count rejected rows. The spread filter excludes markets wider than `max(1 point, half the midpoint)`. Invalid model bounds are excluded with a count. The current parity-MAD rejection threshold is `max(5 points, 0.5% of spot)`; it is a data-quality heuristic, not a market confidence level.

Delta strikes use absolute **undiscounted forward delta** `Φ(±d1)`, interpolated between adjacent strikes. Missing or multiple crossings are unavailable, not extrapolated. Display 1/5/10/15/25-delta wings. These are delta labels, not exact physical probabilities or `Φ(d2)` expiry probabilities.

ATM straddle is the actual indicative midpoint sum at the nearest retained strike to the inferred forward. The report's standard-deviation proxy is `F × a` at that strike. Annualized IV uses time from the closing mark to settlement. A straddle premium and a 68% interval are not the same quantity.

Raw call-spread slopes estimate interval-averaged risk-neutral tails. The implementation suppresses the near-forward digital set when it violates probability bounds or monotone tails. It does not fit an arbitrage-free density or claim the skew-derived prices constitute a physical forecast.

## Wider overnight view

The outcome charts are **illustrative ATM-lognormal distributions**: `log(S_T/F) ~ N(−a²/2, a²)`. They show 1σ/2σ/3σ log-price bands and forward shifts of −2%, −1%, −0.5%, 0%, +0.5%, +1% and +2%. No probabilities are assigned to those gap scenarios. They retain the whole closing-to-expiry variance, so they are not a model of variance remaining after an observed gap.

A newer `^GSPC` bar can add a location-only scenario if its timestamp is after the quote clock, no later than capture, and before target settlement. This uses the actual cash observation, not raw ES. The chart envelope expands around that observation; a test exercises an 8% move. The plots cover the illustrated stresses plus their 3σ tails, **not every possible outcome**. Gaussian/lognormal tails can understate jumps; the skew-aware outer delta strikes are an additional view rather than a claim that the lognormal captures the skew.

Gamma's hypothetical spot scan covers at least ±5% of closing SPX, extended to the wider distribution envelope. No chart is forcibly cropped to the original report's central band.

## Gamma layer

Long calls and puts both have positive gamma. The scenarios assume signed dealer fractions `(call OI weight, put OI weight)`:

| Scenario | Fractions |
|---|---|
| Conventional | `(1, −1)` |
| Reduced long calls | `(0.5, −1)` |
| Reduced short puts | `(1, −0.5)` |
| All-short bound | `(−1, −1)` |
| All-long bound | `(1, 1)` |

These are sensitivity assumptions, not estimated ownership fractions or a probability-weighted ensemble. Uniformly scaling both fractions changes magnitude but not roots. The all-long/short scenarios are extrema over the retained OI, not plausible-position forecasts.

Scopes are target SPXW expiry and all qualified SPX/SPXW expiries within 7/30/90 calendar days of the quote date. Full available strike coverage is retained after quality filters. A root is a zero of the **repriced portfolio**, not a histogram or cumulative-strike crossing. The 201-point scan holds strike total volatility, positions and each expiry's forward/spot ratio fixed. It linearly interpolates crossings and may report multiple or no roots. It is not a time-decay or sticky-delta simulation.

Dollar exposure for a 1% move is `0.01 × 100 × S² × Σ(N_i Γ_i)`. The report divides by `1e9`. Both call and put concentration bars are unsigned. Expiry buckets and put/call OI ratios cover the retained priced-and-matched contracts, not a census of all OI. Missing OI is not zero.

The 30-day profile also varies total volatility ±10%, and computes finite ±0.5%/±1% hedge-notional changes from option delta differences under conventional signs. Hedge flow has the opposite sign from the option-delta change; the notional uses the shocked underlying price. These are hypothetical responses, not detected trades. No vanna/charm/new-flow decomposition or inferred participant identity is implemented.

## What the reference experiment established

The test fixture is a bounded extract of the publicly retrieved September 16, 2026 marks and OCC response for September 17 SPXW, strikes 7000–7900. It tests calculations against observed prices, not an invented surface. The six printed 10/15/25-delta endpoints reproduce within about two points. Changes from the exploratory note's exact outputs reflect explicitly changed strike coverage, forward estimation and spot-versus-forward conventions.

The original next-expiry conventional flip was about 7574; broader-expiry coverage approached the vendor's 7635–7650 zone. This supports a replication hypothesis, not true dealer ownership. The added September 17 PNGs repeat the preparation map; their separate commentary claims a later positive-gamma shelf. Keep those clocks and claims separate. There is still no multi-day predictive validation or direct dealer-inventory ground truth in this free workflow.
