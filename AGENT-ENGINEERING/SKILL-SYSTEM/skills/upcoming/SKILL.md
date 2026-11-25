---
name: upcoming
description: Build a source-labeled, timezone-normalized summary of the most important macroeconomic releases, central-bank events, Treasury events, public-company earnings, and key U.S. listed-options expiration dates scheduled over the next few days. Use for upcoming market calendars, week-ahead catalyst lists, or near-term macro, earnings, and options-expiration previews. Do not use for post-release recaps, live market reaction, historical event research, or claims that an unbounded calendar is complete.
disable-model-invocation: true
---

# Upcoming

Build a short, decision-useful calendar of near-term market catalysts. Treat machine feeds as candidate discovery, preserve schedule confidence, and verify every item that survives the importance cut with the relevant first-party source.

## Non-negotiables

- State the exact inclusive date window, retrieval timestamp, and display timezone.
- Never call the result complete unless the covered geography, company universe, providers, and successful retrievals make that claim auditable. The default claim is **candidate set only**.
- Keep schedule evidence separate from importance analysis. A credible story about why an event matters does not confirm its date or time.
- Prefer the issuing agency for macro events, issuer investor relations for earnings, and the exchange or clearing calendar for options expirations. An aggregator cannot overrule a first-party schedule.
- Never call a paid, trial-to-paid, credit-card-gated, or free-credit API. The bundled collector may call only the exact permanently free endpoints allowlisted in its transport policy. A provider key already present in the environment does not authorize any other endpoint or operation.
- Preserve `confirmed`, `official-scheduled`, `aggregated-scheduled`, `tentative`, `expected`, `estimated`, `cancelled`, and `unknown` as different states.
- Do not turn a session label such as `pre-market` into an exact time. Do not invent consensus, prior values, expected moves, or market-cap rankings.
- Surface inaccessible sources, missing credentials, stale timestamps, conflicts, and timezone uncertainty in the output.

## 1. Fix the scope

Resolve these before collecting:

1. **Window:** use the user's dates. Otherwise use today plus the next four calendar days (five dates total).
2. **Timezone:** use the user's timezone. Otherwise use `America/New_York` and say so.
3. **Macro geography:** default to U.S. releases plus non-U.S. central-bank or data events likely to move U.S. risk assets.
4. **Earnings universe:** default to liquid U.S.-listed companies and foreign issuers with material U.S. index, sector, supply-chain, or macro read-through.
5. **Options universe:** cover key broad-market U.S. listed-options dates, not every daily or weekly contract. Include standard monthly expirations, quarterly expirations, and standard VIX expirations in the window; include end-of-month expirations when they are materially relevant.
6. **Density:** default to all Tier 1 macro events, a small number of Tier 2 macro events, and about 8–12 earnings announcements when that many strong candidates exist. Use fewer earnings names rather than padding the list with weak or unverified entries.

For the default five-day window only, if no key options expiration falls inside it, name the next standard monthly expiration as an explicitly outside-window watch item. Never extend a user-specified window silently.

Use inclusive local dates in prose. Use a half-open interval internally: local midnight on the first date through local midnight after the last date.

## 2. Read the source map

Read [references/sources.md](references/sources.md) before retrieval. It records the accepted programmatic endpoints, source hierarchy, brittle-source fallbacks, and known coverage limits.

Do not substitute a reverse-engineered private endpoint merely because an official page is inconvenient. Use the official page interactively and disclose the manual check.

## 3. Collect candidates

The bundled standard-library collector normalizes stable feeds and emits JSON to stdout. If the BLS ICS has been downloaded through an approved calendar client or browser, pass it as a local read-only input:

```bash
python3 scripts/collect_upcoming.py \
  --from-date 2026-08-10 \
  --days 5 \
  --timezone America/New_York \
  --bls-ics /path/to/bls.ics \
  --use-fred \
  --strict
```

It always attempts the official BEA calendar. It parses BLS only from `--bls-ics`, because direct scripted retrieval is access-controlled and was not reliable enough to make a default adapter. It uses Finnhub as the primary earnings-discovery lane and Alpha Vantage as an independent cross-check when these environment variables are already configured:

- `FINNHUB_API_KEY` — documented earnings calendar; the collector sends it only in `X-Finnhub-Token` and partitions requests into windows of at most five dates.
- `ALPHAVANTAGE_API_KEY` — documented expected-earnings CSV calendar.
- `FRED_API_KEY` — optional conservative U.S. macro date-gap detector, enabled only with `--use-fred`; FRED does not supply an event time here.

The caller may export these variables or source a trusted shell environment before invocation. The collector never reads a dotfile itself. Alpha Vantage and FRED require their credentials as query parameters, so the transport constructs those credential-bearing URLs only at the final network edge, denies redirects, and never logs, persists, or emits them. Do not request, print, or persist credentials in the skill tree.

Every programmatic request is checked before I/O against an exact endpoint, query-key, fixed-value, header, and `Accept` allowlist. There is no executable fallback to a paid provider. Missing keys leave explicit provider diagnostics and bounded official/manual next actions.

The collector does not rank events, declare earnings confirmed, or collect options expirations. Inspect `coverage.providers`, `coverage.lanes`, `coverage.next_actions`, and `coverage.automation_status` before using `events`, then check the official options calendars manually. `manual-collection-required` means an empty automated lane is not evidence that the window has no events. Exit `1` means every attempted provider failed. With `--strict`, exit `2` means at least one requested lane remains unresolved or an official source (BLS, BEA) did not load; otherwise a successful but partial run can still exit `0`.

## 4. Fill coverage gaps and confirm finalists

### Macro

1. Check the BLS and BEA official schedules directly for the window, especially when the collector has no BLS input or reports zero BEA rows.
2. Check Federal Reserve/FOMC, Census, and Treasury sources directly for the window; these do not have an accepted stable adapter in this skill. Follow the structured `coverage.next_actions` entries rather than widening to an undocumented endpoint.
3. For global scope, check the relevant central bank and national statistical office directly.
4. Confirm the displayed time, original timezone, release period, and whether the date is tentative.
5. Use a provider forecast only when the provider and retrieval time are named. Leave forecast/prior blank when not sourced.

### Earnings

1. Use Finnhub output to discover candidates and Alpha Vantage to cross-check coverage; neither proves the date.
2. If the automated earnings lane has no candidates, inspect the public Nasdaq earnings calendar as an `estimated` discovery surface; do not automate its undocumented endpoints.
3. For every company included in the final short list, check its investor-relations events page or dated earnings-release announcement.
4. Label it `confirmed` only when the issuer supplies the date. Preserve `expected` or `estimated` otherwise.
5. If two providers disagree, report the conflict. Prefer the issuer and record which candidate changed.
6. For a foreign issuer, a feed's date is the issuer's local date. Where `source_timezone` is ahead of the display zone, convert the issuer's own release time; the display date may be the day before. Check the issuers the collector's next actions name from [references/foreign-issuers.tsv](references/foreign-issuers.tsv).

If neither the allowlisted free APIs nor the manual public earnings discovery surface can be checked, stop and report that the combined macro-and-earnings request is not fulfillable with the available coverage. Do not try a paid or trial endpoint as a fallback.

SEC filings confirm that a report happened; they are not a complete forward earnings calendar.

### Options expirations

1. Check the current Cboe annual expiration calendar for standard equity, ETF/ETN, index, VIX, end-of-month, and end-of-quarter dates.
2. Cross-check the standard expiration date in the OCC/OIC interactive calendar when available.
3. Distinguish expiration from the last trading day and note AM versus PM settlement only when the official calendar establishes it.
4. Do not infer a date from a third-Friday or holiday rule when the current official calendar can be checked.
5. Omit routine daily and weekly expirations unless the user requests them or current positioning makes one unusually consequential.

If neither Cboe nor OCC/OIC can be checked, mark options-expiration coverage unresolved rather than silently omitting the lane or deriving dates from a calendar rule.

### Delegated checks

A task handed to a research delegate asks for one status word per row, exactly from the vocabulary above, plus a retrieval column: `direct`, `indexed copy`, `wire release`, `search snippet` or `archived copy`. Answers that mix "confirmed (dated wire release)" with "confirmed via indexed copy" leave the table's status column to be re-derived by hand, and a weak retrieval hides in the notes (10-11).

## 5. Select what matters

Rank causally, not by how many feeds mention an item.

### Macro tiers

- **Tier 1:** major central-bank decisions and press conferences; CPI/PCE and other key inflation releases; payrolls and unemployment; GDP; retail sales; major PMIs; high-salience Treasury refunding or coupon-auction events when rates are the active market driver.
- **Tier 2:** releases with a credible policy, growth, inflation, rates, FX, commodity, or sector transmission channel in the current regime.
- Omit routine low-signal releases unless the user requests exhaustiveness or the current market debate makes them unusually consequential.

### Earnings tiers

Prioritize index weight and market capitalization, sector leadership, crowded positioning, supply-chain read-through, consumer or enterprise-demand read-through, and sensitivity to the current macro debate. Use a sourced index membership or market-cap field when making a quantitative claim. Otherwise explain the qualitative transmission channel.

### Options-expiration tiers

- **Always include when in the window:** standard monthly equity, ETF/ETN, and broad-index expiration; quarterly broad-index expiration; and standard VIX expiration.
- **Include when material:** end-of-month expiration or an unusually consequential weekly expiration supported by current positioning evidence.
- Do not imply that expiration alone predicts market direction. Explain the plausible liquidity, hedging, settlement, or position-roll channel and label any positioning claim separately from the schedule evidence.

Existing macro summaries, `$xgrok`, and `$wsj` may help identify the current debate or belief shift. They are optional enrichment sources, never schedule authorities.

## 6. Produce the summary

Use this compact structure:

```markdown
# Upcoming market catalysts

**Window:** Mon Aug 10–Fri Aug 14, 2026 (America/New_York; inclusive)
**Retrieved:** 2026-08-09 18:40 ET
**Coverage:** Candidate set only — [successful sources]; [gaps/errors]

## Macro
| Local date/time | Event (period) | Region | Forecast / prior | Why it matters | Schedule status and source | Retrieval |

## Earnings
| Date/session | Company (ticker) | Status | Why it matters | Schedule source | Retrieval |

## Options expirations
| Date | Expiration type / products | Trading or settlement note | Why it matters | Status and source |

## Changes, conflicts, and coverage gaps
- ...
```

Order each table chronologically, but lead the prose with the two or three highest-impact catalysts when useful. Link the schedule authority directly. If importance context comes from another source, link it separately.

## Final audit

Before answering:

- Recompute date inclusion after timezone conversion, including DST boundaries.
- Confirm no selected item falls outside the stated window.
- Confirm every earnings finalist has an issuer check or an explicit non-confirmed label.
- Confirm the options-expiration lane is present, even if it says no key date falls in the window.
- Confirm every listed expiration comes from the current official calendar and that last-trading-day and settlement language matches the source.
- Confirm source failures and missing-key gaps remain visible.
- Confirm exact-time, forecast, and completeness language does not exceed the evidence.
- Stop and report partial coverage if a load-bearing source cannot be checked.
