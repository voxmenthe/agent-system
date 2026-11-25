# Equity sentiment panel

Use this reference only when equity-market **temperature**, participant
language, first-person action, or conversational texture is part of the ask.
It supplements `credible-equity-sources.md`; it does not weaken or replace that
hard allowlist.

## Evidence contract

Keep three evidence roles separate from retrieval through synthesis:

| Role | Eligible sources | May support | Must not support |
|---|---|---|---|
| **Core evidence** | Active macro/equity allowlists | Facts, mechanisms, company conclusions, informed disagreement, and carefully bounded professional consensus/breadth | - |
| **Sentiment sample** | Core sources plus eligible posts from the probationary panel below | Exact mood, stance, first-person action, repeated phrasing within the labeled sample, and conversation behavior | Disputed facts, company conclusions, professional consensus, or market-wide prevalence/breadth |
| **Context/discovery only** | Discovery/relay accounts and one-off off-list roots or replies that pass the post gate | A search lead, quoted-post dependency, or isolated attributed tell | Aggregate sentiment, independent corroboration, facts, or a core conclusion |

Use phrases such as "in this sentiment sample" or "three independent sampled
participants" when describing recurrence. Never shorten that to "the market
believes" or "traders agree." A single colorful post remains an isolated tell.

## Probationary registry

These handles earned a **retrieval trial** in recent equity-sentiment probes.
They are not EQ-A/EQ-B, are not permanently credible by inclusion here, and
must pass the current-post gate on every run.

### Tape and first-person action

| Handle | Useful role | Current-post gate |
|---|---|---|
| `SPXVIX` (renamed from `isellpremium`) | Index/volatility language, premium-selling stance, breadth and risk-price comparisons | Treat levels and structures as participant claims unless core evidence confirms them; keep explicit action, refusal, or risk-boundary language |
| `traderhc` | Fast tape interpretation, rotation/cover arguments, and falsifiable near-term tests | Preserve stated horizon and any later correction; do not promote a level or causal claim into the core read |
| `GammaGirlLab` | Self-reported book-state, sizing, hedging, and regime changes | Label intention/order/claimed fill/holding/add/trim/exit/flat exactly; never validate position, performance, or breadth from the diary |
| `saltydocEM` | Cross-asset tape observations and concise risk-appetite language | Use the wording as texture; re-check numbers or causal claims against core evidence |

### Company conversation

| Handle | Useful role | Current-post gate |
|---|---|---|
| `asknaksha` | Company-specific post-event reaction, valuation tension, and cycle language | Require a named company/catalyst and retain the strongest informed alternative; not company consensus |
| `justmikeel` | TMT/software deal, product, and valuation framing, often in compact conversational form | Recover the quoted/root post and separate reported event, interpretation, satire, and market reaction |

### Review before use

| Handle | Rule |
|---|---|
| `BlueTradeIn` | Inspect the selected post, its parent, and enough of the current feed to establish market context. Use only a specific labeled conversation node that passes the post gate; do not aggregate this handle into the sample-wide temperature read without a later promotion review. |

### Discovery or relay only

| Handle | Rule |
|---|---|
| `LeopoldQF` | Use research-note headlines or company figures only to find the underlying source or trigger a core-source re-query. A relay is not independent evidence. |
| `Morpheu5Watcher` | Use fast recap or rumor language as a lead and, when unusually telling, isolated context. Verify the event and causal claim elsewhere. |
| `ZeroGEXOptions` | Use proprietary options-map posts to discover a live structure or conversation. Any quoted map remains a labeled model estimate and cannot establish broad positioning. |
| `quantedOptions` | Same discovery-only gate for options-map levels and calendar structures; trace shared inputs and do not count restatements as independent. |

## Trader panel

A fixed set of traders who state their own trades with tickers. A standing lane reads their trade posts every
run, so each member builds a history and each name a stable denominator (`mkt panel`, and the `trader-panel`
lane from `mkt briefs`).
Members carry the roster tag `trader-panel:<style>`; this section owns their rules. Panel rows are a sentiment
sample: the evidence contract above applies.

- **Admission.** A member states their own trade, position or plan in a named ticker, not only views or levels,
  and is not a promoter. The 2026-10-16 probe read 14 days of trade-language posts from 50 candidates (the
  registry's tape handles, the 11 multi-day action authors and recent trade voices; one `from:` call each,
  `X-RESULTS/WORK/2026-10-16_trader-panel-probe`): 32 admitted, 6 excluded as promoters, 12 with no own trade.
- **History.** The 2026-10-16 backfill read each member's trade-language posts from Aug. 17 to Oct. 2 in two
  windows (`X-RESULTS/WORK/2026-10-16_trader-panel-backfill`): 333 rows from 28 members, 34 sampled, 1 wrong
  (3%). It is a floor, not a history: 13 members filled a window's page, so their older posts went unseen, and
  `patternartist_`'s daily entry/exit lists are 95 rows from 11 posts. `IntraSwings` and `KnoxValue` returned
  nothing in either window; `ChrisDungeon`, `Sam_Badawi` and `shrewdinvest` returned posts but no trade row.
- **Exclusion.** A paid group, signal or newsletter sale, Discord or course funnel, referral pitch or reply bot
  disqualifies, as does undisclosed promotion of a held name. Judge on the evidence post's full text, never on a
  worker's flag alone. A long post's pitch often sits past the embed's ~280-character cut, so read it on x.com
  (10-16: KyleReidhead's posts end in a Milk Road PRO link the hydrated text lacked).
- **Churn.** Drop a member after 20 sessions without a trade row and record why below. A rename keeps the
  member (`mkt hydrate` shows the new handle). Re-run admission when the panel falls under 30.
- **Claims.** A trade row is the poster's claim, never a verified fill, position or performance. Posters delete
  losing calls, so surviving history flatters them. Rows stay `tagged_by: worker` until the parent reads the
  post; any profile states its machine-tagged share and the sampled error rate (`mkt panel review`).
- **Counting.** Write "7 of 32 panel traders", never "traders are" or "X attention". One author is one voice per
  name per session. Publish the style mix with any attention claim: the panel leans long, toward retail tech and
  memory, and has no short-seller. The board's Panel talk column (`mkt equity board`) is this count as a share
  against the 20 sessions before.
- **Labels.** `mkt panel context WORKDIR`, after `mkt panel rows`, writes `trader-context.md`: each member's 60-day
  profile and a label per trade post against their own history. A member needs 10 trade posts on 8 sessions for
  any flag; below that the label is "no baseline (n=k)". Give a label as written, in italics beside its post
  (in quotation marks, `mkt quotes` checks it against the post's words). Flags are on
  trial until the 10-session evaluation shows flagged posts led price moves or the poster's own revisions more
  often than unflagged ones.
- **Pronouns.** Pseudonymous members are they/them.

### Members (admitted 2026-10-16)

Style is a first read of each member's probe rows; revise it at the 20-session review. Probe column: trade
rows in the 14-day probe, then the most-named tickers (one or two rows is thin; churn decides).

| Handle | Style | Probe rows: names | Note |
|---|---|---|---|
| `1Powerplayer` | swing | 9: META, QQQ, AMZN, INTC |  |
| `alphatrends` | swing | 2: NKE |  |
| `bazhenov_tt` | swing | 11: DDOG, FTNT, PANW, ALAB |  |
| `Egalmar1` | swing | 1: TDIC |  |
| `IntraSwings` | swing | 3: JNJ, LRCX | renamed from `mjolnir_swings` |
| `LRealcommander` | swing | 6: BAC, IBIT, VLO, RKT |  |
| `patternartist_` | swing | 11: XNDU, ALAB, STRC, RKLB |  |
| `StocksByJulian` | swing | 2: TTWO, MPC |  |
| `ylroc_` | swing | 16: SKHY, MU, SNDK |  |
| `ChrisDungeon` | options | 1: TSLA |  |
| `GammaGirlLab` | options | 6: IWM, KRE, SPY, PLTR | also Tape and first-person action |
| `kust1983` | options | 6: CCI, GDX, AMT, ARKG |  |
| `Salty_Trades` | options | 8: NVDA |  |
| `saltydocEM` | options | 1: SPX | also Tape and first-person action |
| `TheMarketRaven` | options | 2: IWM, TSLL |  |
| `TraderJonesy` | options | 8: SPY, SKYD, MU, IBIT |  |
| `Yam_Trades` | options | 3: SPX, ES |  |
| `JegBaxter18` | momentum | 8: CRWV, NBIS, AMD, META |  |
| `kovainvest` | momentum | 1: LITE |  |
| `otigart` | momentum | 10: SPCX, DRAM, SMH, ONDS |  |
| `outliercapx` | momentum | 5: MU, SKHY, IQE, CRDO |  |
| `StockSavvyShay` | momentum | 2: ASTS, RKLB |  |
| `amitisinvesting` | long-term | 15: SMCI, TSM, AVGO, NBIS |  |
| `JonahLupton` | long-term | 2: DDOG, PLTR |  |
| `Sam_Badawi` | long-term | 1: NBIS |  |
| `shrewdinvest` | long-term | 5: NVDA, AMZN, MU, AVGO |  |
| `TheValueist` | long-term | 1: CLMT |  |
| `wey_how12640` | long-term | 5: IOVA, SNDK, LITE, SPCX |  |
| `GavMcCracken` | value | 2: CLMT |  |
| `KnoxValue` | value | 3: AAPL, AVGO, NFLX |  |
| `Para_Capital` | value | 5: LPTH, KRKNF, MOG.A, NBIS |  |
| `ValueNValues` | value | 5: IREN, APP, TMUS, PEP |  |

### Probe exclusions (2026-10-16)

| Handle | Reason |
|---|---|
| `BretRosenthal` | Promoter: sells the ARMR Risk Monitor reports (`2109675463643631700`) |
| `cfromhertz` | Promoter: setups and position recaps "sent to members" (`2109431974053957730`) |
| `PrimeTrading_` | Promoter: paid group that shares its trades (`2110870538084139278`) |
| `HedgebergCom` | Promoter: "I share my execution on my website" (`2110380822968852882`) |
| `KyleReidhead` | Promoter: posts end in a Milk Road PRO pitch ("signals to buy", "$1"; `2107833506332315824`), past the embed's cut |
| `TT_stocks_` | Promoter: Discord funnel and a "$25K to $1M challenge" in micro-caps (`2110657683820806627`) |
| `SPXVIX` | No own trade in 14 days: three "should" calls (advice); stays in Tape and first-person action |
| `traderhc`, `GaryBlack00`, `dampedspring`, `options_insight` | No own trade row in 14 days of trade-language posts; registry roles unchanged |
| `beqdn8`, `saso_capital`, `smallcapsnipa`, `wraith_` | No own trade row in 14 days |
| `asknaksha`, `h8upesci`, `southernvalue95` | No trade-language post in 14 days (empty page) |

## Current-post eligibility gate

A panel post survives only when all of these are true:

1. It falls inside the exact committed window, or is an explicitly labeled
   older root needed to understand an in-window conversation.
2. It is market- or company-specific and displays enough context to distinguish
   informed shorthand from generic retail emotion.
3. Its exact wording reveals at least one of: conviction, hesitation, boredom,
   irritation, defensiveness, resignation, embarrassment, regret, relief,
   disbelief, jinx avoidance, contempt, FOMO, refusal, or action state.
4. The full short post and any load-bearing parent/quoted post are recoverable.
5. It is not ticker spray, engagement bait, a context-free slogan, a chart-only
   call, an after-the-fact victory lap, or a paid-channel funnel.

Drop a post that fails the gate without demoting the entire handle. Conversely,
one good post does not promote the handle into the core allowlist.

## Retrieval and context recovery

Keep the requested window and all reported timestamps in Pacific time. Replace
`{window_bound}` below with `within_time:Nh` for a simple trailing window or,
in Grok-native `x_keyword_search`, exact
`since:YYYY-MM-DD_HH:MM:SS_PDT until:YYYY-MM-DD_HH:MM:SS_PDT` bounds (`_PST` as
applicable). Convert to UTC only for API-style exact-time parameters. Do not
port the Grok-native timestamp syntax to ordinary X query surfaces.

Search each role separately so a prolific feed does not crowd out the others:

```text
(from:SPXVIX OR from:traderhc OR from:GammaGirlLab OR from:saltydocEM) {window_bound}
```

```text
(from:SPXVIX OR from:traderhc OR from:GammaGirlLab OR from:saltydocEM) (buying OR bought OR adding OR holding OR trimming OR selling OR hedging OR waiting OR flat OR chase OR capitulated OR capitulating OR "changed my mind" OR "not touching") {window_bound}
```

```text
(from:asknaksha OR from:justmikeel) (TICKER1 OR COMPANY1 OR TICKER2 OR COMPANY2) {window_bound}
```

Query `from:BlueTradeIn (TICKER_OR_TOPIC) {window_bound}` alone and apply the
review-before-use gate. Query discovery/relay handles separately:

```text
(from:LeopoldQF OR from:Morpheu5Watcher OR from:ZeroGEXOptions OR from:quantedOptions) (TICKER_OR_TOPIC) {window_bound}
```

Also run one bounded open texture harvest and one explicitly outside mega-cap
technology. Time-slice a busy Grok-native Latest lane with exact Pacific
bounds; on another surface, use its supported bounds, split source batches,
and post-filter timestamps.

For a selected item, fetch the root and quoted-post dependency plus relevant
author continuations and replies. Retain analytical nodes and also seemingly
minor nodes whose emotional or social behavior is the signal: casual dismissal,
embarrassment, regret, defensive repetition, jinx avoidance, a repeated proverb,
or conspicuous absence of concern. Empty praise, dunks, and slogans still drop.

## Sentiment ledger

Record one row per candidate tell:

| Field | Record |
|---|---|
| Market/name | Broad tape, sector, ticker, and live catalyst |
| Exact tell | Complete short text or the minimal signal-bearing passage |
| Signal type | Sentiment tell, first-person action, conversation edge, or context lead |
| Register | The observed emotional/social register; use plain language rather than forcing a taxonomy |
| Action state/horizon | Intention, order, claimed fill, holding, hedge, add, trim, exit, flat, watch-only; plus stated horizon |
| Novelty | New, changed, repeated, or unchanged relative to the prior report |
| Recurrence | Independent authors versus copied relay, self-thread, or one conversation |
| Source role | Core evidence, sentiment sample, review-before-use, or context/discovery only |
| Paraphrase loss | What the exact wording communicates that a summary would erase |
| Dependencies/caveat | Parent/quote IDs, unverified level, disclosed interest, model estimate, or missing context |

The ledger is private working state, not the delegated response. Unless the
parent's `Delegated budget:` line expands it, promote at most six receipts and
stay under 1,500 words. Return one dense table that compresses the fields
above. Reproduce complete short text only when phrasing, action, or a
conversation edge is the evidence; summarize wording-immaterial facts and
retain the author, Pacific timestamp, and ID/link. Add at most one sentence
each for the coverage boundary and the material gap, plus one overflow line
with any other qualifying IDs. No search diary or narrative memo.

In delegated mode the source-role column is provenance: record `allowlist`,
`panel`, or `off-list` (and `parent roster` when the parent named the handle)
and leave weight and admissibility to the parent. Do not drop, discount, or
caveat a parent-named off-list post. The "Must not support" column above
governs a direct run's synthesis, not a worker's packet.

## Aggregation and concentration gates

- One author is one voice. A root, self-thread, replies, and repeated posts by
  that author do not create breadth.
- A relay and the relayed post share one underlying information source unless
  the relay adds an independent interpretation.
- Normally promote no more than two sentiment tells from one author. When at
  least eight tells survive, no author should supply more than 25% of them; if
  that happens, rerun missing role families or narrow the conclusion.
- Use a plural sample-level temperature claim only when at least three
  independent eligible authors across at least two role families support it.
  With fewer, report the observations individually.
- Repetition can be the finding even when the underlying thesis is unchanged,
  but count recurrence only after deduplication and independence review.
- Treat an absence of concern as evidence only after the relevant sources and
  time slices were actually covered. An empty or crowded query is not silence.

## Promotion review

Do not edit the hard allowlist during a live run. A later promotion review must
sample multiple dates, include adverse updates or corrections where relevant,
check free-text and off-topic rates, and assign a stable domain/role. Until then,
keep every panel use explicitly labeled.
