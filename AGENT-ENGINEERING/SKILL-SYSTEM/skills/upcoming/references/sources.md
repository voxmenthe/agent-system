# Source map for upcoming market catalysts

Last endpoint review and live free-account trial: **2026-08-10**. Recheck provider documentation before changing an adapter. A successful HTTP response is not proof that the underlying calendar is complete or current.

## Decision rule

Use sources in this order:

1. **First-party schedule:** issuing agency, central bank, Treasury, exchange or clearing calendar, or company investor relations.
2. **Documented calendar API/feed:** stable discovery and normalization, with its confidence state preserved.
3. **Public visual calendar:** bounded manual cross-check only when its calculation method or coverage is not auditable.

Only automate a source when its endpoint is documented or explicitly published, its schema and timezone can be validated, and its access terms permit the intended use. Otherwise use a browser/manual check and disclose the gap. Do not depend on reverse-engineered internal web endpoints.

## Executable free-only boundary

The collector must never attempt a paid, trial-to-paid, credit-card-gated, or free-credit operation. Its request policy fail-closes to these exact GET endpoints and documented operations:

| Provider | Exact endpoint and operation | Credential handling | Role and hard limit |
|---|---|---|---|
| BEA | `https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics` | None | Official U.S. macro schedule feed. |
| Finnhub | `https://finnhub.io/api/v1/calendar/earnings` with `from`, `to`, and `international=false` | `FINNHUB_API_KEY` only in `X-Finnhub-Token` | Primary U.S. earnings discovery. Query partitions span at most five dates. Exactly 1,500 raw rows triggers a possible-cap warning and mandatory cross-check. |
| Alpha Vantage | `https://www.alphavantage.co/query` with fixed `function=EARNINGS_CALENDAR` and `horizon=3month` | `ALPHAVANTAGE_API_KEY` is a required query parameter | Secondary earnings cross-check. Request with `Accept: */*`; `text/csv` returned HTTP 406 in the 2026-08-10 trial. |
| FRED | `https://api.stlouisfed.org/fred/releases/dates` with fixed JSON, future-date, paging, and sort parameters | `FRED_API_KEY` is a required query parameter | Optional date-only macro gap detector. Enable explicitly with `--use-fred`; filter through the asserted release-ID/name allowlist. |

The Alpha Vantage and FRED URLs acquire credentials only inside the transport immediately before I/O. The transport denies redirects and strips request details from diagnostics. A provider response that asks for an upgrade is a provider failure, never permission to try another operation. Environment variables with other provider names are ignored.

## U.S. macro: accepted sources

| Source | Best use | Programmatic access | Limits and fallback |
|---|---|---|---|
| [BLS release calendar](https://www.bls.gov/schedule/) | Employment, CPI, PPI, productivity, and other BLS releases | Published iCalendar feed: `https://www.bls.gov/schedule/news_release/bls.ics`. Subscribe or download with an approved calendar client/browser, then pass the file to `--bls-ics`. | Direct scripted retrieval returned HTTP 403 in the 2026-08-09 host check. [BLS robot policy](https://www.bls.gov/bls/blsterms.htm) permits blocking and says robots should carry owner contact information, so the collector does not spoof a browser or fetch this by default. Verify a market-moving release on the official page. |
| [BEA release schedule](https://www.bea.gov/news/schedule) | GDP, personal income and outlays/PCE, trade, and other BEA releases | Published ICS: `https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics`. Published JSON alternative: `https://apps.bea.gov/API/signup/release_dates.json`. | The ICS carries event detail and time; the JSON is useful for monitoring but may have broader names or duplicate dates. Prefer the ICS for event rows and verify revisions on the schedule page. |
| [Census economic indicators](https://www.census.gov/economic-indicators/calendar-listview.html) | Retail sales, durable goods, housing, construction, trade, and related indicators | No stable documented calendar API is accepted here. | Use the official list view interactively. HTML parsing is allowed only as an explicitly brittle, monitored fallback with fixtures and failure alarms; it is not part of the bundled collector. |
| [Federal Reserve calendar](https://www.federalreserve.gov/newsevents/calendar.htm) and [FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | FOMC decisions, minutes, testimony, speeches, and Board releases | No stable documented comprehensive calendar feed is accepted here. | Check the official pages manually. Confirm whether a time refers to a release, meeting start, press conference, or publication. |
| [Treasury tentative auction schedule](https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.pdf) | Refundings and auctions when duration supply is market-moving | Official PDF, not a stable event API. | Read the current PDF and then confirm the auction announcement or TreasuryDirect notice. Preserve `tentative` until confirmed. |

Reading notes from the 2026-10-11 week-ahead build:

- **BLS:** the monthly schedule page (`https://www.bls.gov/schedule/YYYY/MM_sched.htm`) loaded for a delegate while the ICS returned 403. It is the manual fallback; the collector's BLS next action names the window's months.
- **Fed:** the monthly calendar page (`https://www.federalreserve.gov/newsevents/YYYY-month.htm`, e.g. `2026-october.htm`) is server-rendered and loads with a plain request. Items run newest first, each item's day number comes after it, and no timezone is printed; times are ET by convention. Pair each item with the day number that follows it: a delegate put a Waller speech on the wrong date by pairing it with the number above.
- **Treasury:** the tentative auction PDF downloads and parses with `pdftotext -layout` in one call; a delegate's reader could not open it, so read it locally and give the delegate the rows.
- **Issuer sites:** GS, MS, ASML, TSMC and Domino's IR sites blocked automated reads. An issuer's own dated release on PR Newswire or Business Wire is first-party content and confirms a date.

## Broader macro discovery and confirmation

### FRED

The documented [FRED releases/dates API](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html) can include future source dates when `include_release_dates_with_no_data=true`. It provides a release date but not the actual announcement time or timezone, and FRED warns that a source release date need not equal availability on FRED. The collector therefore uses it only as an opt-in U.S. gap detector, keeps time unknown, ignores weekends and unasserted releases, and fails if an allowlisted release ID changes name. Confirm every promoted event with its issuing agency.

### Global first-party checks

Use the applicable official institution for any selected global event. Common starting points:

- [ECB monetary-policy calendar](https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html)
- [Bank of England upcoming MPC dates](https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates)
- [Bank of Japan calendar](https://www.boj.or.jp/en/about/calendar/index.htm) and [MPM schedule](https://www.boj.or.jp/en/mopo/mpmsche_minu/)
- [Eurostat release calendar](https://ec.europa.eu/eurostat/news/release-calendar)

This list is a routing aid, not a claim of global completeness.

## Earnings: accepted sources

There is no universal first-party forward calendar across public companies. Use a broad discovery feed, define its covered universe, and then verify every final company with issuer investor relations.

| Source | Best use | Programmatic access | Confidence and limits |
|---|---|---|---|
| Company investor relations | Final date confirmation for a selected company | Many issuers publish pages, press releases, RSS, or ICS, but there is no uniform cross-issuer schema. | Ground truth for the company. A date can still change; record retrieval time. A webcast time is not always the release time. |
| [Finnhub earnings calendar](https://finnhub.io/docs/api/earnings-calendar) | Primary expected-earnings candidate list | Documented `calendar/earnings` request with inclusive date bounds and token header. The collector uses short partitions and preserves `bmo`, `amc`, and `dmh` alongside normalized sessions. | The live free-account response can be very large and may cap at exactly 1,500 rows. It does not supply a company name. Treat every date/session as expected and cross-check shortlisted symbols. |
| [Alpha Vantage earnings calendar](https://www.alphavantage.co/documentation/) | Independent expected-earnings cross-check | `function=EARNINGS_CALENDAR`, `horizon=3month`, CSV response, API key required. The collector filters the returned calendar locally to the requested dates. | The 2026-08-10 free-account trial returned broad coverage, but many rows lacked sessions. The collector requires company, symbol, and report date while treating any session as optional and non-exact. |
| [Nasdaq earnings calendar](https://www.nasdaq.com/market-activity/earnings) | Visual cross-check | No documented public API is accepted here. | Nasdaq states that its displayed list is derived algorithmically from historical reporting dates. Treat unconfirmed entries as `estimated`; do not automate an undocumented internal endpoint. |

### Foreign issuers with U.S. read-through

[foreign-issuers.tsv](foreign-issuers.tsv) is the standing list: symbol as the feeds carry it, IANA zone, reporting months, IR calendar and the read-through. It holds TSMC, ASML, SAP, LVMH, Samsung and Nestlé (10-11: LVMH's Monday Q3 revenue was in neither feed, and Finnhub omitted ASML and TSMC). The collector stamps each listed issuer's earnings row with its `source_timezone`. When that zone is ahead of the display zone it adds a next action, because the feed's date-only row carries the issuer's local date: TSMC's 14:00 Taipei call on Oct. 15 was 23:00 PT on Oct. 14. It also names each listed issuer with a reporting month in the window and no feed row, so its IR calendar gets checked. Add an issuer when a run needed one the list lacked.

## Options expirations: accepted sources

The bundled collector has no options-expiration adapter. Check these current official calendars manually and retain the source link in the final summary.

| Source | Best use | Programmatic access | Confidence and limits |
|---|---|---|---|
| [Cboe U.S. options hours and holidays](https://www.cboe.com/about/hours/us-options/) | Primary route to the current annual expiration calendar | The page links the current annual Cboe expiration-calendar PDF. No parser is bundled. | The calendar distinguishes standard equity, ETF/ETN, index, AM-settled index, VIX, end-of-month, and end-of-quarter dates. It also says dates are subject to change, so use the current-year document and record retrieval time. |
| [OCC/OIC options expiration calendar](https://www.optionseducation.org/referencelibrary/expiration-calendar) | Cross-check for standard listed-options expiration dates | Interactive page only; no stable documented feed is accepted here. | Use it to corroborate the standard date. Use the relevant exchange calendar for product-specific last-trading-day, settlement, weekly, or holiday details. |

Do not generate expiration dates from third-Friday, month-end, or holiday arithmetic when an official current-year calendar is available. Do not treat routine daily and weekly expirations as key catalysts without separate evidence of unusual positioning or market relevance.

## Freshness and conflict handling

- Save the retrieval timestamp and provider-reported last update when available.
- Use IANA timezones for conversion. Keep the original timestamp and source timezone in machine data.
- Re-fetch immediately before publication when the window includes today or tomorrow.
- On disagreement, do not average or silently choose. Report both, check the first party, and label the unresolved state.
- A provider that returns zero rows can be successful but incomplete. A provider error or missing credential must remain visible in `coverage.providers`.
- Use `coverage.next_actions` for bounded browser fallbacks. Do not widen programmatic retrieval beyond the static request allowlist.
- Never carry a date forward from an old summary without a current schedule check.
