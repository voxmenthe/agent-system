# X query patterns for /macro

Use with `x_keyword_search` (and date filters where supported). Combine
sparingly; over-constrained queries return empty. **Always hard-filter core
evidence to the active allowlist** (macro `credible-sources.md` and/or equity
`credible-equity-sources.md`), then apply post-level filters. In a
participant-native equity run, route eligible posts from
`equity-sentiment-panel.md` to a separate sentiment ledger; never merge them
into EQ-A/EQ-B. For a broad equity product, build the dynamic lane and name map
in `equity-retrieval.md` before selecting recipes here.

## Contents

- [Core operators and filters](#core-operators)
- [Window parsing](#parsing-user-windows)
- [Lane recipes](#lane-recipes)
- [Equity mode](#equity-mode---mag-7--tech--semis--special-sits)
- [Equity sentiment panel](#equity-sentiment-panel-participant-native-runs)
- [Conversation recovery](#selected-conversation-recovery)
- [Adaptive windows and entity hygiene](#adaptive-since-guidance-when-user-did-not-fix-window)
- [Root selection and call budget](#root-selection)

## Core operators

| Operator | Use |
|----------|-----|
| `from:user` | Allowlisted accounts (primary tool) |
| `from:a OR from:b` | At most 4 handles when the query also carries keyword terms or an exact-time bound; 6–10 only for handle-only, date-granular sweeps |
| `list:{id}` | **Supplementary only** - membership-filtered list feed (see supplementary-lists.md) |
| `"exact phrase"` | CPI, "payrolls", "rate cut", speech titles |
| `OR` | Aliases (must be uppercase OR) |
| `$TICKER` / cashtags | `$SPX` `$DXY` `$TLT` `$USOIL` sparingly |
| `since:YYYY-MM-DD_HH:MM:SS_PDT` | Exact lower bound in Grok-native `x_keyword_search` only; use `_PST` in standard time |
| `until:YYYY-MM-DD_HH:MM:SS_PDT` | Exact upper bound in Grok-native `x_keyword_search` only; use `_PST` in standard time |
| `since:YYYY-MM-DD` / `until:YYYY-MM-DD` | Portable date-granular bounds |
| `within_time:Nh` | Exact trailing-hour keyword window when the host supports it |
| `min_faves:N` | Optional floor inside allowlist Latest noise; **preferred on NBTQ** |
| `filter:quote` | Quote-tweet debate among pros |
| `filter:self_threads` | Recover author continuations that root-only search misses |
| `conversation_id:{root_id}` | Inspect one selected conversation; validate returned id |
| `-filter:replies` | Root-discovery overview when reply spam appears; **required for the InvQ overview** |
| `filter:has_engagement` | Drop zero-engagement when Latest is empty-looking |

If an operator errors or returns nothing, simplify rather than invent syntax.
If one author supplies more than half of a batched result, split the batch or
query the missing handles alone before treating them as silent. Ranking
starvation is not evidence of inactivity.

Two batching rules from live runs. First, a query that combines a keyword
OR-group with a `from:` group of more than four handles silently drops its
`since:`/`until:` bounds and returns weeks-old posts: keep each query to one
keyword group plus at most one four-handle `from:` group, or split roster
from keywords, and when any returned post is outside the bound treat the
query as bound-failed (drop the leaked posts, do not count the page as
coverage, split and rerun). Second, batch at most four handles when the
window is under about three hours and query a handle alone when a prolific
poster is in the set or the window spans the cash session; test silence in
two stages, a four-handle batch first and single-handle isolation only for
handles inside a batch that returned at the cap. An under-cap return is the
only proof of silence.

Use source-role-aware retrieval. Keep core, sentiment-sample, and
context/discovery results in separate collections from the first fetch.
Root-only discovery is an overview, not an
activity test. For a reply-led allowlisted source, run a focused
`from:handle filter:replies` pass or inspect selected conversations, then
preserve the parent/root relationship. For a curation- or relay-led source,
inspect the account feed with the supported tool rather than assuming that
`from:` search exposes native reposts, and follow useful items to the underlying
author/source. Attribute the underlying claim there; a curator's selection is
not a second independent source. Apply the hard allowlist to that original
author before using the claim in core synthesis; an off-allowlist original is a
theme lead for re-query, not an allowlist bypass.

## Post-level filters (after every search)

1. Author must be allowlisted (or a user-requested exception) **for core
   synthesis**. An equity sentiment-panel author must pass that reference's
   current-post gate and remain in the labeled sentiment ledger. Other
   supplementary-list or harvest hits are theme leads or isolated context, not
   a core or aggregate sentiment read.
2. **Hashtag / quality** (see `credible-sources.md`): do not drop an
   allowlisted post for 2+ `#hashtag` tokens alone. Keep usable desk/research
   prose. Drop only if it also devolves into tag soup, promo, or engagement
   farming. Non-allowlist 2+ hashtag noise stays out of core.
3. For **on-topic only** handles (e.g. `PolemicTMM`, `EffMktHype`,
   `PauloMacro`, `VKMacro`, `dsquareddigest`, `RobinWigg`): keep only
   markets/macro posts.
4. For **industry specialists** (e.g. `SKundojjala`): keep only in-domain, research-grade posts.
5. Topic mode: keep only on-entity posts.
6. List lanes: also drop chart-emoji spam, retail tips, personal/off-domain,
   paywall bait, and official dump accounts (see supplementary-lists.md).

## Parsing user windows

Convert user language to search bounds before the lattice:

| User phrase | Example bound |
|-------------|----------------|
| past 6 hours / last 6h | `within_time:6h`, or compute exact timestamped Pacific bounds in Grok-native search when fixed endpoints matter |
| past 24 hours / today | exact Grok-native Pacific lower bound, or the surrounding date bound plus returned-timestamp validation on another surface |
| last 3 days / past 3d | `since:` (today − 3 days) |
| past week / last 7 days | `since:` (today − 7 days) |
| since Friday / since June 1 | calendar date → `since:YYYY-MM-DD` |
| adaptive / omitted | pulse table in SKILL.md |

Semantic lane: set `from_date` / `to_date` to match the same committed window.

Define, query, compare, and report the window in Pacific time. In Grok-native
`x_keyword_search`, exact bounds use
`since:YYYY-MM-DD_HH:MM:SS_PDT until:YYYY-MM-DD_HH:MM:SS_PDT` (or `_PST` as
applicable). This syntax is native-tool-specific; ordinary/public X query
surfaces document date-granular `since:`/`until:`. Convert to RFC 3339 UTC only
for API-style `start_time`/`end_time` parameters. UTC is a transport detail, not
the reader-facing timezone.

When a native Latest lane is busy, split the interval into adjacent 60-90
minute Pacific slices. On another surface, use its supported bounds, split
source batches if needed, and post-filter timestamps. Deduplicate post IDs and
compare author coverage; do not treat the last returned page or one prolific
author as the whole window.

## Lane recipes

The batches below name source families. When a recipe pairs a family with a
keyword group or an exact-time bound, run it as `from:` groups of at most four
handles per query; the batch shown is the family, not one query.

### Pulse - allowlist Latest (short window)

```text
(from:dampedspring OR from:TimmerFidelity OR from:MichaelKantro OR from:lisaabramowicz1 OR from:AndreasSteno OR from:biancoresearch OR from:MacroAlf) since:{today_or_yesterday}
```

Mode: `Latest`. Limit modest (5–10). If thin, run another Tier A batch (rates /
global), not official institutions.

### Integrated macro + key-equities pulse

For a combined macro-and-equity sentiment request, keep one exact time window
across the relevant macro Tier A and equity EQ-A discovery lanes. Cluster those
results jointly before ticker-, factor-, or thesis-specific fanout, then target
only the missing evidence and high-value conversations. When participant
temperature is requested, run the separate sentiment-panel pulse below under
the same bound. Do not squeeze every handle into one oversized query, and skip
unrelated lanes when the request is narrow.

### Discovery scan (no topic)

Run 2–4 Tier A batches Latest + one Top:

```text
(from:dampedspring OR from:TimmerFidelity OR from:MichaelKantro OR from:biancoresearch OR from:JosephPolitano OR from:albertedwards99 OR from:ericlonners) since:{bound}
```

```text
(from:nicktimiraos OR from:lisaabramowicz1 OR from:LizCapoMcCormick OR from:TheStalwart OR from:greg_ip OR from:PolemicTMM OR from:EffMktHype OR from:VKMacro OR from:dsquareddigest OR from:RobinWigg) since:{bound}
```

```text
(from:robin_j_brooks OR from:MacroAlf OR from:ING_Economics OR from:AndreasSteno OR from:Frances_Donald OR from:michaelxpettis OR from:Gloeschi) since:{bound}
```

Cluster themes from what they actually posted. Apply the hashtag/quality gate
(allowlisted analysis stays even with boilerplate tags). Drop off-topic posts
from topic-conditional accounts (`PolemicTMM`, `EffMktHype`, `VKMacro`,
`dsquareddigest`, `RobinWigg`), and off-domain
specialist posts before clustering. Do not invent a global "trending" list
outside these posts.

### Topic + allowlist

```text
(from:HANDLE1 OR from:HANDLE2 OR ...) (CPI OR "consumer price" OR inflation) since:{bound}
```

```text
(from:HANDLE1 OR from:HANDLE2 OR ...) (FOMC OR "rate cut" OR "rate hike" OR "dot plot" OR Powell OR Warsh) since:{bound}
```

```text
(from:HANDLE1 OR from:HANDLE2 OR ...) ("10-year" OR "10y" OR "term premium" OR "Treasury" OR yields) since:{bound}
```

### Fed day (example lattice)

1. Rates / Fed Tier A batch + (FOMC OR Powell OR Warsh OR "press conference")
2. `from:nicktimiraos` and rates reporters batch
3. Run the event-synthesis batch below for reaction function, votes, and tape:

```text
(from:nicktimiraos OR from:GregDaco OR from:sonalibasak OR from:DannyDayan5 OR from:AnnaEconomist OR from:DianeSwonk OR from:Fullcarry OR from:dampedspring OR from:albertedwards99 OR from:FirstSquawk) (FOMC OR "press conference" OR "rate hike" OR "rate cut" OR "financial conditions" OR dissents) since:{bound}
```

4. Include `from:PolemicTMM OR from:EffMktHype OR from:VKMacro OR from:dsquareddigest OR from:RobinWigg OR from:albertedwards99 OR from:ericlonners` in a batch; keep only macro posts after fetch for the topic-conditional handles; drop Edwards joke-only asides and Lonergan event promo
5. Semantic: `FOMC decision market reaction rates path` with date bounds → filter to allowlist + post-level rules

### Data print day (CPI / NFP / PCE)

```text
(from:lisaabramowicz1 OR from:biancoresearch OR from:MichaelKantro OR from:TimmerFidelity OR from:dampedspring OR from:albertedwards99 OR from:ericlonners OR from:PolemicTMM OR from:EffMktHype) (CPI OR payrolls OR PCE OR "nonfarm" OR inflation OR unemployment) since:{bound}
```

### Housing / labor detail

```text
(from:LoganMohtashami OR from:CalculatedRisk OR from:conorsen OR from:Claudia_Sahm OR from:JosephPolitano OR from:IrvingSwisher) (housing OR mortgage OR inventory OR labor OR employment OR payrolls OR participation) since:{bound}
```

### US cycle / withholding / policy transmission

```text
(from:WarrenPies OR from:EPBResearch OR from:wabuffo OR from:BobEUnlimited OR from:LHMacro) (CPI OR PCE OR inflation OR payrolls OR withholding OR housing OR cyclical OR growth OR Treasury OR Fed OR rates OR FIMA OR Japan OR yen OR JGB OR BOJ) since:{bound}
```

Keep cyclical subsets, calendar-adjusted nominal income, and policy-model
interpretations distinct. This supplements the print-day batch; recover
from-only posts if terminology or ranking hides a quiet specialist.

### Systematic financing / passive-flow mechanics

```text
(from:choffstein OR from:profplum99) (passive OR index OR financing OR futures OR leverage OR liquidity OR NDFI OR overlay OR "portable alpha" OR credit) since:{bound}
```

Preserve reply parents and portfolio-construction assumptions. These macro
roles do not confer EQ-A company coverage or establish a current dealer book.

### Cross-asset internals / event-vol mechanics

```text
(from:VolSignals OR from:options_insight OR from:Gloeschi OR from:Fullcarry OR from:qthomp OR from:krugermacro OR from:albertedwards99 OR from:ericlonners) (FOMC OR CPI OR payrolls OR breadth OR dispersion OR gamma OR volatility OR positioning OR capex OR fiscal) since:{bound}
```

```text
(from:Ksidiii OR from:Alpha_Ex_LLC OR from:KrisAbdelmessih) (VIX OR volatility OR vol OR skew OR surface OR gamma OR convexity OR tail OR dispersion OR correlation OR dealer OR hedging OR OPEX OR expiry) since:{bound}
```

Keep the specialist lane separate when possible: low-volume or reply-led posts
from these accounts can disappear behind a prolific cross-asset feed. Preserve
parent context for analytical replies and distinguish a structural framework
from a current positioning claim.

### Active macro trader trajectory (anecdotal overlay)

```text
(from:Fullcarry OR from:PauloMacro OR from:BlacklionCTA OR from:patternartist_) (position OR long OR short OR hedge OR added OR adding OR trimmed OR sold OR covered OR flat OR entry OR exit OR SL OR BE OR "changed my mind" OR "not sure") since:{bound}
```

Use this lane to find a **current state**, then search the same author plus the
instrument/theme over a wider bound to recover the origin and any later update.
Preserve chronology and the exact state label: intention, order, claimed fill,
holding, hedge, add, trim, exit, or flat. A point-in-time view is not a trajectory;
multiple posts by one author are not breadth. Keep older origins labeled outside
the user window when they are needed only as a baseline.

### Sector / industry (when domain is live)

```text
(from:JavierBlas OR from:Ole_S_Hansen OR from:Rory_Johnston OR from:aeberman12 OR from:LVision_Trading OR from:energyaspects OR from:GavMcCracken OR from:VKMacro OR from:HFI_Research) (oil OR crude OR Hormuz OR SPR OR tanker OR pipeline OR inventory OR refinery OR diesel) since:{bound}
```

```text
(from:Ole_S_Hansen OR from:JavierBlas OR from:TaviCosta OR from:energyaspects OR from:RystadEnergy) (copper OR gold OR silver OR agriculture OR commodities OR inventory OR positioning OR COT) since:{bound}
```

```text
from:SKundojjala (semiconductor OR foundry OR memory OR packaging OR fab OR capex) since:{bound}
```

Adjust domain keywords when useful (freight, shipping, oil, copper, semis, etc.).
After fetch: keep specialist posts only if in-domain and research-grade.

For **Mag 7 / tech / semis stock sentiment / multi-sector equity research**, do
**not** rely on this macro industry batch alone. Use the **equity lattice**
below (loads `credible-equity-sources.md`).

### Equity mode - Mag 7 / tech / semis / special sits

When topic or discovery is stock-level (NVDA, META, AAPL, MSFT, GOOGL, TSLA,
ORCL, CRWV, company theses, forensic shorts), search the **EQ-A / EQ-B**
families below. Hard-filter authors to `credible-equity-sources.md`; weight
**EQ-A > EQ-B**. Do not treat macro Tier A alone as equity consensus. For a
balanced macro/equity update, devote roughly 60% of first-wave retrieval to the
separate equity lanes in `equity-retrieval.md`, about half of all first-wave
calls to company questions.

#### Broad tape, breadth, and rotation

```text
(from:bespokeinvest OR from:Stephanie_Link OR from:StockSavvyShay OR from:DanielTNiles OR from:GavinSBaker OR from:citrini) (breadth OR rotation OR factor OR momentum OR equal-weight OR earnings OR guidance OR multiple OR positioning) since:{bound}
```

Use this as the broad equity overview, not as a substitute for company lanes.

#### Company pulse (no topic vocabulary)

```text
($TICKER1 OR COMPANY1 OR $TICKER2 OR COMPANY2 OR $TICKER3 OR $TICKER4) since:{bound} -filter:replies
(from:HANDLE1 OR from:HANDLE2 OR from:HANDLE3 OR from:HANDLE4) ($TICKER1 OR COMPANY1 OR $TICKER2 OR COMPANY2) since:{bound}
```

Batch up to four names from the parent's baseline and name map, using each
ticker and a validated company name or alias (`$NVDA OR NVIDIA`; not a bare
word such as `Apple` that matches unrelated text without its cashtag). Do not
add capex, earnings or other required topic words: the pulse looks for what is
being discussed. The open form surfaces the conversation, filtered after fetch
under the normal gates; the roster form checks whether the lane's own sources
discussed the names. Report each name searched, capped, unqueried or failed.

#### Dynamic selected-name template

```text
(from:HANDLE1 OR from:HANDLE2 OR ...) (TICKER1 OR COMPANY1 OR TICKER2 OR COMPANY2 ...) (earnings OR guidance OR estimate OR margin OR capex OR cash-flow OR valuation OR position OR risk) since:{bound}
```

Use this to deepen a name the pulse or name map made a priority; replace the
topic group with the brief's question, or drop it. Populate the names from the
current name map, not a permanent Mag 7 shotgun. Run hyperscalers, semis/supply
chain, and each selected non-tech family separately so a prolific tech author
cannot crowd out the other sleeves.

#### Active equity trader trajectory (anecdotal overlay)

```text
(from:TheValueist OR from:wey_how12640 OR from:patternartist_) (long OR holding OR bought OR added OR "top up" OR trimmed OR sold OR closed OR stop OR hedge OR flat OR entry OR exit OR SL OR BE OR "core remained" OR "damage control") since:{bound}
```

Run only when individual positioning or a sentiment change is relevant. For a
surviving post, query the same author and ticker without the short user-window
floor when necessary to recover the timestamped origin, then fetch the selected
thread/context. Do not convert a watchlist, consideration, or planned trade into
execution; do not publish claimed P&L as validated performance. For
`patternartist_`, compare declared open positions across dated journals; an
end-of-day recap is not a timestamped live entry alert.

### Equity sentiment panel (participant-native runs)

Load `equity-sentiment-panel.md`. It is the single authority for the probationary
registry, extra query batches, current-post gate, sentiment ledger, and
concentration rules. These lanes never expand EQ-A/EQ-B.

#### EQ-A pulse / gold + multi-sector

```text
(from:TheValueist OR from:bespokeinvest OR from:KerrisdaleCap OR from:CulperResearch OR from:blueorcainvest OR from:ResearchGrizzly OR from:ScorpionFund OR from:JehoshaphatRsch) since:{bound}
```

#### EQ-A non-tech / SMID long activist

```text
from:Adam_Wyden since:{bound}
```

Keep free-text company estimates and mechanisms. This is an episodic,
concentrated activist camp; discard slogans and link-only campaign posts.

#### EQ-A forensic + estimate

```text
(from:muddywatersre OR from:sprucepointcap OR from:viceroyresearch OR from:Bleecker__St OR from:WolfpackReports OR from:sssjeffpu OR from:p_ferragu) since:{bound}
```

#### EQ-A company research / AI stack

```text
(from:borrowed_ideas OR from:CaieKelley OR from:RihardJarc OR from:saso_capital OR from:EricJhonsa) since:{bound}
```

#### EQ-A cross-sector PM / print

```text
(from:Stephanie_Link OR from:jukan05 OR from:EconomyApp OR from:JonahLupton) since:{bound}
```

#### EQ-A Mag 7 PM / strategist / wire

```text
(from:GavinSBaker OR from:munster_gene OR from:mingchikuo OR from:garyblack00 OR from:DanielTNiles OR from:StockSavvyShay OR from:SouthernValue95 OR from:citrini OR from:RichLightShed OR from:RihardJarc) since:{bound}
```

#### AI financing / neocloud capital structure

```text
(from:TheValueist OR from:GavinSBaker OR from:TechFundies OR from:RHouseResearch OR from:SouthernValue95 OR from:StockSavvyShay OR from:DanielTNiles OR from:RihardJarc OR from:CaieKelley OR from:malinvested) (ORCL OR CRWV OR CoreWeave OR hyperscaler OR neocloud OR RPO OR capex OR FCF OR debt OR CDS OR lease OR SPV OR financing OR "side pocket" OR redemption OR gate OR illiquid) since:{bound}
```

#### EQ-B industry / news (drivers only)

```text
(from:firstadopter OR from:DylanOnChips OR from:dnystedt OR from:SemiAnalysis_ OR from:fabknowledge OR from:PatrickMoorhead OR from:danielnewmanUV OR from:pequityresearch) since:{bound}
```

#### EQ-B company-language / product / industry comparisons (drivers only)

```text
(from:markgurman OR from:TheTranscript_ OR from:Beth_Kindig OR from:dougclinton OR from:anni_sen) since:{bound}
```

#### EQ-B options / market structure (mechanics only)

```text
(from:Yam_Trades OR from:spotgamma OR from:VolSignals OR from:alphaticaio OR from:options_insight OR from:JoeyGEX) (SPX OR SPY OR QQQ OR gamma OR volatility OR skew OR flow OR positioning OR dispersion OR correlation OR darkpool OR OPEX OR expiry) since:{bound}
```

```text
(from:Ksidiii OR from:Alpha_Ex_LLC OR from:KrisAbdelmessih) (options OR VIX OR volatility OR vol OR skew OR surface OR gamma OR convexity OR tail OR dispersion OR correlation OR dealer OR hedging OR collar OR FLEX OR exercise) since:{bound}
```

Label proprietary positioning estimates and use this lane to explain magnitude
or regime, not to infer fundamental direction by itself. The first batch mixes
vendor maps with an explicit dealer/GEX critic; the second adds professional
tail, correlation, surface, and microstructure cross-checks. Preserve the
parent or quoted root for conversation-led analysis.

#### EQ-B technical structure / session statistics

```text
(from:ProbableChris OR from:notprofgreen) (NQ OR ES OR futures OR statistical OR statistics OR OOS OR "random walk" OR reversion OR expectancy OR MAE OR MFE OR fractal OR session) since:{bound}
```

```text
(from:alphatrends OR from:cfromhertz) (VWAP OR VPOC OR breadth OR sector OR ETF OR SPY OR QQQ OR NVDA OR TLT OR GLD OR "implied move") since:{bound}
```

Keep the two families distinct: statistical-method criticism is not a technical
level, and neither establishes a dealer book or company value. Recover
methodological replies and author narrowing; do not quote a high historical
hit rate as a current trading edge. Apply the ordinary in-domain/free-claim
filter to mixed personal and commercial feeds.

#### EQ-B insurance accounting / deal structure

```text
from:NickNemo17 (insurance OR insurer OR captive OR statutory OR affiliate OR "related party" OR merger OR BHF OR Brighthouse) since:{bound}
```

Read the public article or analytical reply, not only the hook. Preserve
permitted-practice, source-dependence, and ownership-inference qualifications;
verify decision-critical claims in the underlying filings. Exclude unrelated
SMID calls and paid-trade teasers.

#### EQ-B ETF / fund structure

```text
from:EricBalchunas (ETF OR fund OR inflow OR outflow OR flows OR redemption OR creation OR liquidity OR AUM OR wrapper) since:{bound}
```

Use for wrapper and flow mechanics, not company valuation or aggregate
consensus. Trace relayed colleague/guest material to its origin.

#### EQ-B healthcare specialist

```text
(from:deathtouch2k OR from:adamfeuerstein OR from:A_May_MD) (biotech OR healthcare OR clinical OR trial OR FDA OR PDUFA OR acquisition OR placebo OR "open label" OR "cash burn" OR ATM) since:{bound}
```

#### EQ-B energy-equity specialist

```text
from:JoshYoung (energy OR oil OR gas OR E&P OR services OR producer) since:{bound}
```

Use each only within the named sector. Label possible or disclosed positions
and verify clinical, regulatory, and commodity claims when decision-critical.

#### Combined Mag 7 topic (when query length allows)

```text
(from:TheValueist OR from:DanielTNiles OR from:sssjeffpu OR from:GavinSBaker OR from:TechFundies OR from:RHouseResearch OR from:SouthernValue95 OR from:StockSavvyShay OR from:citrini OR from:RihardJarc) (NVDA OR META OR AAPL OR MSFT OR GOOGL OR TSLA OR ORCL OR CRWV) since:{bound}
```

After equity fetches: drop paywall-only teasers, cheerleading, low-quality
tag-soup/promo (not allowlisted analysis with boilerplate tags), and
off-domain posts. Label forensic shorts as one-sided.
Never let EQ-B alone define a contested multiple / positioning / risk-reward read.

Choose sleeve roles and caveats from `credible-equity-sources.md`; keep the
executable handle combinations in this file.

### FX / dollar / Europe

```text
(from:robin_j_brooks OR from:MacroAlf OR from:donnelly_brent OR from:JStanleyFX OR from:AndreasSteno OR from:Frances_Donald OR from:VKMacro OR from:michaelxpettis) (EURUSD OR dollar OR DXY OR "ECB" OR "FX" OR "exchange rate" OR intervention OR FIMA OR China OR surplus) since:{bound}
```

```text
(from:ClausVistesen OR from:VPatelFX) (ECB OR HICP OR Europe OR eurozone OR GBP OR USD OR wages OR labor OR inflation OR FOMC OR gas) since:{bound}
```

ClausVistesen and VPatelFX add eurozone and USD/GBP data-policy interpretation,
not continuous Asia-session FX coverage. Retain forecast and sample caveats.

### Debate surface (allowlist only)

Prefer opposing claims **inside** allowlist results over controversy keywords
that suck in retail:

```text
(from:A OR from:B OR from:C) ("higher for longer" OR "cut" OR "recession" OR "soft landing" OR "no landing" OR "term premium") since:{bound}
```

Or fetch quote threads of a strong Tier A origin post.

### Semantic lane

Natural language, then **drop non-allowlist authors** from core. Apply the
hashtag/quality gate; 2+ hashtags on non-allowlist noise stay out:

```text
macro strategists on the latest CPI print and rates path
```

```text
what professional macro accounts are saying about the dollar and yields
```

```text
FOMC reaction from economists and rates strategists
```

Equity mode semantic examples (still filter to EQ allowlist after):

```text
Mag 7 AI infrastructure equity risk reward from PMs and research
```

```text
semiconductor estimate revisions and NVDA stack positioning
```

Semantic search is a recall tool, not a credibility tool.

### Supplementary list lane (after allowlist core)

Full noise notes and rules: `references/supplementary-lists.md`.

**Ids:** NBTQ `209841180` · InvQ `960008892343246848`

Cap **1–2** list calls per run. Mode: `Latest`. Always keep `list:{id}`. These
queries discover candidate roots; they do not prohibit selected-conversation
enrichment. Never let non-allowlist list authors define the primary read.

**Macro token pack (discovery):**

```text
(yields OR FOMC OR CPI OR Fed OR rates OR inflation OR "10y" OR dollar OR DXY OR credit OR recession OR "soft landing" OR payrolls OR PCE OR ECB OR RBA OR "jobless" OR Treasury OR curve)
```

**NBTQ root overview (mixed desk + chart spam - need engagement floor):**

```text
list:209841180 since:{bound} -filter:replies ({topic_or_macro_tokens}) min_faves:3
```

If thin: drop `min_faves` once. If chart-brand flood: try `min_faves:5`.

**InvQ root overview (reply-heavy - never bare list):**

```text
list:960008892343246848 since:{bound} -filter:replies ({topic_or_macro_tokens})
```

Optional `min_faves:2` if still chatty. A bare InvQ feed is usually unusable
for root discovery (short-reply flood). Once an allowlisted root is selected,
inspect that exact conversation rather than reopening the whole list feed.

**Topic example (FOMC day):**

```text
list:209841180 since:{bound} -filter:replies (FOMC OR Powell OR "rate cut" OR "rate hike" OR "dot plot") min_faves:3
```

```text
list:960008892343246848 since:{bound} -filter:replies (FOMC OR Powell OR "rate cut" OR "rate hike")
```

**After list results:** merge allowlisted authors into the main sample; re-query
allowlist if a new theme appears; at most 1–3 lower-weight **List check**
bullets for high-substance non-allowlist posts. Drop non-allowlist 2+ hashtag
spam, chart-emoji spam, retail tips, personal/off-domain, paywall bait,
official dump accounts. Allowlisted list hits use the hashtag/quality gate.

## Selected-conversation recovery

Do this only after broad search has produced a shortlist of **2–5 load-bearing
roots**. Under a normal budget, fully enrich the best **2–3** and reserve at
least two calls per root. No single X query exposes a complete popular reply
tree.

1. `x_thread_fetch` the root or a material child node.
2. Search `conversation_id:{root_id}` in Latest **without an engagement floor**.
3. Search `conversation_id:{root_id} filter:self_threads` when the author is
   publishing a numbered or continued analysis.
4. If a material child appears near a known timestamp, use exact tool time
   parameters when exposed; otherwise use surrounding date bounds and
   post-filter to the local interval.
5. Optionally compare one modest `min_faves` lane for precision. Never use it
   alone: quiet corrections and technical replies often have near-zero likes.
6. Only if necessary, query `to:{root_author} filter:replies`, then post-filter
   every returned post to exact `conversation_id == root_id`.

A root counts as enriched only after both steps 1 and 2 complete. A thread-only
root remains a candidate. A completed check with zero additive nodes belongs in
Coverage, the search log, or Gaps, not the Key conversations table.

`in_reply_to_tweet_id:` may fail on the current backend; treat it as optional
and do not burn retries. Classify retained nodes as author follow-up,
correction, evidence addition, technical counterargument, expert extension,
or clarification/open boundary. Drop empty praise, dunks, slogans, and
duplicates. When the participant-native extension is active, use the expanded
social/emotional node classes in `equity-sentiment-panel.md` instead.

For each retained node record:

- root id/URL and reply id/URL
- relationship class
- core source tier
- author continuation versus independent voice
- what changed in the read and the caveat

Use the larger field contract in `equity-sentiment-panel.md` for its extension.

Stop after the root plus floor-free/local samples cover the material relation
classes, or when roughly 70% of new IDs are duplicates with no new substantive
claim.

## Adaptive `since:` guidance (when user did not fix window)

- **Breaking:** `since:` today; emphasize last hours by timestamp
- **Same-day:** today and yesterday
- **Story:** ~last 7 days
- **Background:** up to ~30 days; attention still on newest coherent cluster

When Latest is sparse after allowlist + post-level filters, widen window one
step before declaring thin. Do **not** compensate by admitting non-allowlist
virality or tag-soup promo.

## Entity hygiene (macro collisions)

| Risk | Mitigation |
|------|------------|
| `Apple` vs markets | Prefer CPI/FOMC context; avoid bare tech names |
| `soft` | Use `"soft landing"` phrase |
| `cut` | Pair with Fed/FOMC/rates |
| Common surnames | Prefer `@handle` and full name phrases |
| Cashtags | Supportive only; not a substitute for allowlist |
| PolemicTMM / EffMktHype / VKMacro / dsquareddigest / RobinWigg off-topic | Author allowlisted but post dropped unless markets/macro |
| Industry specialist off-domain | e.g. SKundojjala kept only for in-domain research-grade posts |
| Mag 7 / stock tape via macro-only | Load equity allowlist; do not synthesize NVDA sentiment structure from macro Tier A alone |
| EQ-B as market consensus | Drivers only; require EQ-A for contested stock reads |
| Forensic short as neutral truth | Keep free-text math; always label one-sided interest |
| Bare list Latest (esp. InvQ) | Root overview uses `-filter:replies` + topic/macro tokens; selected roots use exact conversation recovery |
| List non-allowlist as primary read | Re-query allowlist or use List check only; never equal-weight core evidence |
| `to:` reply contamination | Post-filter exact returned `conversation_id`; otherwise discard |
| Engagement floor hides corrections | Always pair any precision floor with a floor-free exact-conversation lane |

Always keep the primary event token in topic-mode keyword queries.

## Root selection

Select 2–5 allowlisted, post-filter-passing roots that are:

1. Best level-set (what printed, what the market did per source)
2. Strongest material disagreement, alternate interpretation, or outlier from
   Tier A, when present
3. Corrective take that changes the data read
4. Plumbing / micro structure when that is the debate (FedGuy, etc.)
5. On-topic high-signal from topic-conditional accounts (e.g. PolemicTMM, EffMktHype, VKMacro, dsquareddigest, RobinWigg)
6. In-domain industry specialists when that sleeve is live
7. Equity mode: best EQ-A level-set / evidence-shaped sentiment structure /
   estimate path; optional EQ-B factual driver only

Avoid near-duplicate "wow big number" posts and low-quality tag-soup promo.
Then use the progressive conversation recovery above; do not spend the reply
budget uniformly across every candidate.

## Call budget sketch (normal run)

1. Pulse Latest Tier A batch (1–2 calls) - **equity mode:** EQ-A gold/PM pulse;
   participant-native mode adds a separately labeled sentiment-panel pulse
2. Commit window
3. Topic or discovery batches Latest (2–3) - equity: EQ-A then light EQ-B if needed
4. Equity temperature, first-person action, and dynamic-name sentiment batches
   when the product requires them; time-slice busy results
5. Top or semantic comparison (1–2) → route to the correct evidence role
6. Supplementary list root overview (0–1; at most 2 when genuinely additive)
7. Selected-conversation recovery (4–6 calls across the best 2–3 of 2–5 shortlisted roots)

Stay roughly within **10–14** X calls for an ordinary core brief. For an
explicit participant-native combined macro/equity product, treat that as a
starting budget, not a cap: cover the required equity roles and stop when new
independent source families repeat existing facts, names, sentiment registers,
and conversation edges. List and conversation calls still compete for budget.
