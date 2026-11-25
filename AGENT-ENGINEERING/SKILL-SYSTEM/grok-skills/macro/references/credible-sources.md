# Credible macro sources (hard allowlist)

**Purpose:** Hard filter for `/macro`. If an author is not on this list (and not
a one-run user-requested exception), **do not** use their post as evidence.

Handles change; treat this as a living list. Prefer fewer high-quality voices
over expanding into noise. When unsure, leave them out.

**Not on this list (by design):** central banks, stats agencies, treasuries, and
other official institutional feeds. Desk and analyst signal is the product;
official dumps are low value for this skill.

## How to use

1. Search with batched `from:handle1 OR from:handle2 OR ...` (see query-patterns).
2. After every tool result, **drop** posts whose author is not below.
3. Apply **post-level** noise and on-topic filters (below) even for allowlisted
   authors.
4. Tier weights for ranking: **A > B**.
5. Tier B is secondary color - do not let a news-brand account alone define a
   contested market read if Tier A is silent or split.

## Promotion rules

Add a permanent source only after a recent feed-and-conversation review
establishes repeatable value across multiple dates or events. Do **not** require
a particular posting format: original roots, substantive quote-post commentary,
replies that add analysis, evidence, or correction, and consistently useful
repost/relay curation can all qualify. An account with rare original posts may
therefore still belong on the allowlist.

Record the source's current role, any domain gate, and the post-level caveat
that affects how it can be used. For a reply-led source, verify the parent/root
and preserve the conversation relationship; banter alone does not qualify. For
a curator or relay, trace and cite the underlying author/source: the selection
may be useful evidence of attention, but it is neither the curator's original
analysis nor independent corroboration. The underlying claim enters core
synthesis only if its original author is also allowlisted or is a user-requested
exception for that run; otherwise it remains a discovery lead. A single useful
interaction, adjacency, biography, or follower count can nominate a candidate
but does not establish repeatable value. Resolve renamed handles from known
post IDs or returned author identity rather than from a guessed username.

## Active trader trajectory overlay (anecdotal only)

Use this overlay only to answer **how one author's stated view or book changed**.
It is not evidence of market-wide positioning, consensus, factual truth, or
verified performance. Multiple posts by one author remain one voice.

A trajectory needs a timestamped baseline plus a later same-author state update.
Substantive replies and quote commentary count; an original root is not required.
Label each observation precisely as **intention, order, claimed fill, holding,
hedge, add, trim, exit, or flat**. Do not infer execution, direction, size, or P&L.
A single post may establish a point-in-time stance, but not a change. Prefer
pre-outcome disclosures; a retrospective win or loss is usable only as an update
to an earlier receipt, never as the start of a reconstructed track record.

Keep text-bearing reasoning, uncertainty, invalidations, and adverse updates.
Drop chart-only calls, unexplained alerts, P&L screenshots, victory laps, and
product teasers. Do not use a source whose free feed reveals trades mainly after
the fact or says subscribers received the actionable disclosure first. Claimed
size or returns never increase evidence weight.

**Current macro trajectory set:** `Fullcarry` (rates/curve book and hedges),
`PauloMacro` (on-topic commodities/macro stance), `BlacklionCTA`
(rates/futures tactical stance; personal position only when explicit), and
`patternartist_` (dated multi-asset journals with later stops/covers/exits).
For `patternartist_`, retain the instrument and event reasoning, track declared
open positions across dates, and do not turn end-of-day recaps into live calls,
verified fills, or core macro facts.

## Post-level filters (all tiers)

Apply after author allowlist check:

| Filter | Rule |
|--------|------|
| Hashtag / quality | **Do not drop an allowlisted post solely because it has more than one `#hashtag`.** Count is a quality tell, not an automatic kill. Keep if the free text is still a usable desk or research claim (boilerplate topic stamps on real analysis stay in). Drop only if the post **also** devolves into low quality: tag soup with no thesis, engagement farming, promo/teaser, cheerleading, or the tags doing the work instead of the prose. For **non-allowlist** list/semantic/Top noise, 2+ hashtags remain a spam tell and stay out of core. |
| Off-entity | In topic mode, drop allowlisted posts that are not about the topic. |

Engagement does not create eligibility. Quality still beats a viral empty post.

Free-text claim gates are not a blanket attachment-discovery filter. For a
chart-aware brief, an eligible in-domain source's terse-caption attachment can
remain an **unread visual lead** under the [delegated packet contract](../SKILL.md#delegated-evidence-packet-contract).
This does not establish a claim or action, relax trajectory bans, or admit
promotional/paywall-only material; the parent must inspect the pixels first.

## Tier A - Named macro analysts, strategists, PMs, specialists

High-signal individuals and research brands. Core "desk twitter" set.
**Not exhaustive** - expand carefully; never add engagement farmers.

### Core cross-asset anchors

| Handle | Notes |
|--------|-------|
| dampedspring | rates & macro. Absolute top tier - dive into every post and conversation in detail |
| TimmerFidelity | Jurrien Timmer, Fidelity |
| MichaelKantro | Michael Kantrowitz |
| lisaabramowicz1 | Lisa Abramowicz, Bloomberg. Macro/credit bridge: rates, credit supply, issuer spreads, and equity-valuation transmission. Strong curator and synthesizer; distinguish sourced reporting from proprietary analysis. |
| AndreasSteno | Andreas Steno Larsen |
| elerianm | Mohamed A. El-Erian |
| OddStats | Retired Finance Guy |
| BobEUnlimited | Bob Elliott, Unlimited cofounder and CIO. Repeated public analysis of Treasury/Fed duration, official FX flows, discount rates, and household-demand versus investment growth. Keep substantive free-text claims, not product or media teasers. Label proprietary estimates and contested transmission arguments; distinguish holdings valuation changes, rolloff, and sales, and preserve reply corrections. Curated research is not independent corroboration. |

### Rates, Fed, US macro

| Handle | Notes |
|--------|-------|
| ericwallerstein | Macro Strategist |
| biancoresearch | Jim Bianco / Bianco Research |
| darioperkins | macro commentator |
| LizAnnSonders | Charles Schwab Strategist |
| conorsen | Conor Sen |
| Claudia_Sahm | labor macro econ |
| jasonfurman | Jason Furman |
| M_C_Klein | Matt Klein |
| kurtsaltrichter | Macro Commentary - plenty of chart images |
| deerpointmacro | Macro Commentary - plenty of chart images |
| krugermacro | Alex Kruger macro advisory |
| ApolloAcademy | Apollo macro |
| JosephPolitano | data-heavy macro |
| CalculatedRisk | housing/macro data |
| TheStalwart | Joe Weisenthal |
| tracyalloway | Tracy Alloway |
| CardiffGarcia | Cardiff Garcia |
| greg_ip | Greg Ip, WSJ economics columnist |
| Neil_Irwin | Neil Irwin |
| nicktimiraos | Nick Timiraos (Fed telegraph) |
| SteveMiran | Stephen Miran - Fed reaction-function, inflation, and US policy analysis |
| josephwang | Joseph Wang - Fed / plumbing |
| JeffSnider_AIP | Eurodollar/plumbing (niche; use when on-topic) |
| LukeGromen | Luke Gromen |
| RaoulGMI | Raoul Pal - use sparingly; often broader crypto-macro |
| TaviCosta | Tavi Costa - commodities/macro |
| jsblokland | cross-asset macro |
| Frances_Donald | Frances Donald |
| DonRissmiller | Strategas / Don Rissmiller |
| LizCapoMcCormick | Liz Capo McCormick, Bloomberg rates |
| Brian_Chappatta | Brian Chappatta |
| KrishnaGuha | Krishna Guha / Evercore ISI policy |
| EvercoreISI | Evercore ISI |
| bubbleboienjoyr | Occasional banger macro/rates comments |
| INArteCarloDoss | too much politics but some decent macro commentary |
| JackFarley96 | Too many podcast links but also good posts that capture zeitgeist |
| alaidi | macro commentator |
| Tyler_Neville_ | Macro manager - FG |
| qthomp | Quinn Thompson - CIO - FG |
| Fullcarry | Rates/curve trader. Useful for explicit curve-book and hedge disclosures plus ongoing rates reasoning. Treat every position as self-reported; do not infer a later add, trim, or exit from a market-level view. |
| BlacklionCTA | Macro/derivatives practitioner. Useful for text-bearing rates/futures stance, levels, risk-reward revisions, and substantive replies. Treat as an individual tactical-state signal; do not infer a personal position from alerts or tape commentary, and drop chart-only or ambiguous fill references. |
| TruthGundlach | Jeffrey Gundlach, DoubleLine founder. Sparse but high-signal credit/rates skepticism; useful on issuance quality, ratings, and market-implied stress. |
| AnnaEconomist | Anna Wong, Bloomberg Chief US Economist - Fed reaction function, financial conditions, and policy-path analysis |
| tdarling1 | investor - commentator |
| RenMacLLC | macro advisory |
| kierangoodwin | macro + equities |
| DianeSwonk | Diane Swonk, KPMG Chief Economist - Fed history, committee dynamics, and macro consequences |
| fcastofthemonth | Omair Sharif |
| DannyDayan5 | Danny Dayan - global macro volatility PM; financial conditions, positioning, and event-risk transmission. Keep free-text claims; label proprietary models and do not rely on Substack-only detail. |
| IrvingSwisher | Skanda Amarnath / Employ America - domain-gated to labor, inflation, and Fed reaction-function analysis. |
| GregDaco | Gregory Daco - economist; live Fed quote capture and macro-policy interpretation. Prefer attributed quotes and original analysis over clip-only posts. |
| sonalibasak | Sonali Basak / iCapital - policy-communication, vote-math, and cross-asset tape. Use for event synthesis; corroborate exact pricing with a primary market source. |
| shortl2021 | macro posts - many retweeted images but still useful |
| spomboy | macro commentator - more conversations than posts |
| Markzandi | economist |
| kit_lowe | macro / currency investor |
| TimDuy | rates, Fed etc. |
| sidprabhu | Fed, macro |
| LoganMohtashami | Housing and labor-market specialist. Keep data-backed inventory, mortgage, employment, and Fed-transmission posts; drop combative asides and link-only promotion. |
| Schuldensuehner | Holger Zschäpitz, *Die Welt*. Global fiscal, sovereign supply, Bunds, US long end, Germany/China industrial. Dense morning charts with auction levels, debt stock, term-premium framing. |
| Callum_Thomas | Callum Thomas, Topdown Charts. Global asset allocation, valuations, breadth, regime charts. Same class as Timmer, with more allocation/valuation craft. Drop link-only recap posts. |
| BrianLe_Blanc | Brian LeBlanc, PNC senior economist (personal). US consumer, card data, seasonal adjustment, labor rules of thumb. Sparse. When he posts: Prime Day calendar theft vs Census, card-spend threads, Okun/tariff arithmetic. Bespoke amplified the retail-sales thread. |
| jasongoepfert | Jason Goepfert. Breadth, sentiment internals, high-low models. Prefer the **person** over `@sentimentrader`. The brand account is paywall/API/product. |
| traderhc | Self-described multi-PM. Cross-asset tape: duration vs liquidity, IWM as rates invoice, OPEX pin vs cascade, gold/oil/copper splits. Short falsifiable tape tests ("duration tax, not a drain"; "OPEX removes the pin but does not create a seller"). Occasional BTC/journal lines. Underweight relative to more credible voices such as dampedspring/Constan |
| albertedwards99 | Albert Edwards, SocGen global strategist. 40y City career; rates/bond-bear with chart claims (long-end breakouts, MACD, 2% inflation-target critique). Keep free-text market posts; drop joke-only asides. Named bear camp, not consensus. London hours. |
| fejau_inc | some decent macro commentary - part of the Forward Guidance crew |
| ericlonners | Eric Lonergan, London macro. Sparse. Keep fiscal→AI-capex, Fed time-inconsistency, and bubble/correlation-one posts (equities driving bonds). Drop event/book promo. |
| ScottSkyrm | Fed and repo market etc. |
| chabot_ben | macro commentator & professor |
| Andrea_Lisi_CFA | Andrea Lisi, CFA / Lisi Quant Analysis. US duration, auction microstructure, issuance/take-downs, SEP path arithmetic. Keep numbered auction tables and falsifiable path claims; drop LinkedIn-style hooks and emoji packaging. Domain gate: rates/issuance/financial conditions, not equity tape. |
| MichaelRStrain | Michael R. Strain, AEI Director of Economic Policy Studies; Georgetown; FT contributing columnist. FOMC reaction-function and committee-center-of-gravity analysis with explicit hold-vs-hike-cycle tests. Sparse original roots allowed; keep free-text forecasts and invalidations, drop pure media clips. |
| byHeatherLong | Heather Long, Navy Federal chief economist; Marketplace contributor. Translates SEP/dots into path claims and mid-cycle framing that others then argue with. Sparse; keep numbered SEP arithmetic and inflation-path claims, drop podcast/video-only plugs. |
| WarrenPies | 3Fourteen Research cofounder and strategist. Repeated free-text work on CPI/PCE nowcast uncertainty, Fed reaction functions, physical-versus-paper oil, and event volatility. Preserve analytical reply context; policy thresholds and model signals are his interpretation, not committee rules. Keep substantive public claims and drop client-report, ETF, or appearance-only promotion. |
| EPBResearch | Eric Basmajian / EPB Research. US business-cycle sequencing across housing, equipment/AI investment, cyclical employment, and aggregate growth. Keep the free-text calculation or mechanism, not newsletter/Operator teasers. Identify his cyclical subsets and period definitions; distinguish net from gross saving/investment and verify consequential accounting comparisons. |
| wabuffo | Bill, a pseudonymous investor. Original US employment-income monitoring from federal payroll-tax withholding, with explicit weekday/month-end calendar adjustments and adverse updates. Keep the method and comparison period with the table. Withholding is a nominal income proxy, not a direct headcount or real-wage measure; do not infer a verified professional affiliation. |
| LHMacro | Lighthouse Macro, a macro research feed. Repeated public rates/cycle work connects Japan funding and Treasury demand, real yields, curve shape, and labor measures to policy scenarios. Keep the free-text mechanism and comparison period; verify historical analogs, vintages, and decompositions. Drop subscription-only teasers and copyable-book/performance promotion; no verified individual employment or performance is implied. |

### Topic-conditional (mixed personal / markets feed)

High quality **when** posting about markets; feeds often include non-macro.
Always apply the **on-topic only** post filter.
Always call out when they comment on markets.

| Handle | Notes |
|--------|-------|
| PolemicTMM | On-topic only. Strong on macro/markets when he is on topic. |
| EffMktHype | On-topic only. Same profile as PolemicTMM - keep markets/macro posts only. |
| VKMacro | On-topic only. Anonymous London-hours oil/rates/FX desk. Keep physical diffs, UST/JPY/BoC shorthand, and other mechanism-bearing posts; drop empty chat. Identity unresolved: do not treat as a named firm or a second independent corroboration of LVision/Hansen flow counts. |
| dsquareddigest | On-topic only. Dan Davies, London. Bank/UST plumbing and fund-leverage (regulatory arb, mark-to-model, HF risk). Keep mechanism posts and analytical replies; drop festival/personal. Preserve parent context on replies. |
| RobinWigg | On-topic only. Robin Wigglesworth, FT Alphaville editor. Oslo/London hours. Zeitgeist journalism with a free-text claim (ABCP, HF de-risking, Treasury intervention). Keep markets/plumbing posts; drop book-tour, podcast-history, and personal. A Wigglesworth post is not a second independent corroboration of the linked FT story; retain the on-X claim. Prefer named strategists when they contest the same fact. |
| PauloMacro | On-topic only. Positioning and commodities specialist with useful FX/rates mechanics in quote commentary and substantive trader replies; original research is often linked off-platform. Keep mechanism- or positioning-bearing posts and replies, preserve quoted/parent context, and drop the feed's frequent banter, memes, and politics without a market mechanism. |
| HayekAndKeynes | On-topic only - can be an additional component of sentiment surveys in terms of focus of recent posts - posts infrequently |
| profplum99 | Michael Green, market-structure investor; current profile identifies Tier1 Asset Management. On-topic only. Useful analytical replies on passive/index-flow concentration, active-versus-passive wrapper definitions, and bank-to-nonbank credit transmission. Preserve parents and source lineage, label disputed mechanisms and asset-manager incentives, and drop satire, politics, podcasts, or chart-only claims. |

### High-frequency newsy posts but above-average signal/noise for that type of account

| Handle | Notes |
|--------|-------|
| KobeissiLetter | The Kobeissi Letter |



### Industry specialists (higher bar; domain-gated)

Sector/industry analysts. **Higher quality bar than general Tier A adds:** only
list people with a clear research track record in a defined industry. Do not
grow this section with semi-informed sector Twitter.

**Usage:**

- Include in search batches when the user topic or discovery cluster touches
  their domain (e.g. shipping/freight, a named commodity chain, a sector print).
- Drop posts outside their industry lane, even if markets-flavored noise.
- In pure broad discovery with no sector angle, optional light sample is fine;
  do not let them dominate the brief.

| Handle | Domain / notes |
|--------|----------------|
| SKundojjala | Industry specialist (semiconductors). Keep in-domain research-grade posts only; drop generic macro hot takes and off-domain content. |
| VolSignals | Options / equity-index volatility specialist. Career SPX market-maker perspective on dealer gamma, vanna, and event vol; keep positioning/market-structure posts and label vendor model estimates. |
| options_insight | Imran Lakha / Options Insight. Former institutional index-options trader and European options-desk head; repeated work on index versus single-name residual books, skew and spot-vol behavior, OPEX hedge decay, VIX carry, and common GEX sign errors. Keep substantive free-text analysis and corrections, label every street/dealer-position claim as an estimate, and drop masterclass, community, or product-only promotion. |
| Ksidiii | Kris Sidial, Ambrus co-CIO and volatility/tail-risk PM. Useful for compensation-aware short-vol analysis, convexity and tail construction, event-vol flow footprints, and challenges to vague positioning claims such as "everyone is hedged." Posting can be episodic; keep mechanism-bearing work, distinguish structural frameworks from a current dealer map, and drop firm or appearance promotion. |
| Alpha_Ex_LLC | Dean Curnutt / Alpha Exchange. Macro Risk Advisors founder and cross-asset volatility/derivatives specialist. Repeated original work on dispersion and realized correlation, long-dated single-name skew, collars and option overlays, and delta-implied-vol interaction. The feed is a brand/podcast hybrid: keep Dean's on-X analysis, separate guest or linked-source material, and label overlay assumptions rather than treating them as positioning facts. |
| KrisAbdelmessih | Kris Abdelmessih / Moontower, a former options market maker and relative-value volatility PM. Conversation-led source for surface and skew diagnostics, FLEX and exercise microstructure, option-relative-value boundaries, and corrections to simplified market-maker stories. Recover the parent for substantive replies, keep live on-X analysis, and drop off-topic posts, newsletter cards, product notices, and generic education without a current market application. |
| SPXVIX | Renamed from @isellpremium (its August post IDs now resolve under /SPXVIX/; checked 2026-09-27). Options/premium-selling voice. Breadth (% green, average stock vs SPX), IV kinks, GEX/pin maps, earnings IV. Close internals dumps; pin-or-shove questions; some chat and victory-adjacent MRNA lines. **Keep on sentiment panel**, or promote to EQ-B options **with the same vendor-label as `alphaticaio`**. GEX dollars are not a second audit of VolSignals. Breadth counts are the highest-value free text. |
| GammaGirlLab | Self-described floor → derivatives desk. First-person SPX structures, hedges, regime notes. Thin following; diary, not research. Add to the **trajectory overlay** (same role as `wey_how12640`) if you want a second options diary. Anecdotal only. |
| choffstein | Corey Hoffstein / Newfound Research. Systematic portfolio and financing specialist: portable-alpha crowding, futures financing, overlay opportunity costs, and leveraged-note wrappers. Analytical replies are particularly useful; recover their parents. Label issuer interests, construction assumptions, and backtests; drop Return Stacked AUM/launch promotion and do not infer a current dealer book or single-stock thesis. |
| chigrl | Energy/products economist (NinjaTrader Live / Hilltower; Renegade Resources). Physical diesel/distillate, export-policy counterfactuals, Jones Act, crack microstructure, Saudi/Europe cargo premiums. Keep complete free-text mechanism posts; drop show plugs, Substack-only teasers, and generic Fed charts. Domain gate: physical energy/products only. |

When adding more industry names: require a specific domain label in the table
and the same domain-gate rules. Prefer one excellent specialist per sleeve over
five mediocre ones.

**Mag 7 / tech / multi-sector equity sleeve:** for Mag 7 names, AI infra equities,
semis stock sentiment, related second-tier names (NVDA, META, AAPL, MSFT, ORCL,
CRWV, etc.), **or** dense company-level equity research / special sits in any
sector, also load `credible-equity-sources.md` and hard-filter **equity market
takes** to that equity allowlist (EQ-A > EQ-B). Use its batches and post-level
filters. Do **not** expand this macro table ad hoc with equity Twitter. Do not
treat a macro-only handle as equity evidence just because they tweeted a ticker.
Macro industry specialist **SKundojjala** stays domain-gated here for pure semi
research; prefer the equity list for Mag 7 **market** takes.

### Global macro, FX, Europe

| Handle | Notes |
|--------|-------|
| MacroAlf | Alfonso Peccatiello |
| GeorgeSaravelos | George Saravelos, DB FX. No public X account: @GeorgeSaravelos does not exist and @GSaravelos is protected with 0 posts (checked 2026-09-27); DB FX research arrives via relays. Not queried. |
| robin_j_brooks | Robin Brooks, IIF |
| donnelly_brent | Brent Donnelly / Spectra Markets - FX, rates, and central-bank reaction functions |
| JStanleyFX | James Stanley / FOREX.com - FX positioning and policy-path repricing |
| ING_Economics | ING Economics |
| NordeaMarkets | Nordea Markets |
| DBForex | Deutsche Bank FX brand if active |
| Commerzbank | research when macro |
| Danske_Research | Danske Bank research if active |
| acrossthespread | mostly Yen - not particularly high quality, but occasionally adds useful context |
| StephenSpratt | rates & FX |
| Brad_Setser | Global trade, balance-of-payments, and cross-border flow analysis |
| michaelxpettis | Michael Pettis, Carnegie. Beijing hours. China investment, surplus, involution, household income share, A-share peculiarities. Keep mechanism posts; drop culture asides. Pair with Brad_Setser; not a US-equity PM. |
| mark_dow | macro commentary |
| INArteCarloDoss | macro commentary |
| super_macro | need to filter out promotional posts but still worth following |
| ClausVistesen | Claus Vistesen, Pantheon eurozone economist. Reply-led ECB/HICP, European growth, fiscal, and gas-to-inflation analysis with explicit forecast revisions and alternative scenarios. On-topic only; recover parents and distinguish Pantheon forecasts from observations. Drop politics/personal posts and trace quoted energy or reporting inputs to their origin. |
| VPatelFX | Viraj Patel / Vanda Research. G10, especially USD/GBP, policy-data interpretation: UK labor and wages, inflation breadth, and FOMC dissent/history. Useful short original claims across multiple releases; posting is intermittent, not a continuous Asia-session feed. Label historical sample statistics and proprietary estimates, and drop jokes or chart-only captions. |

### Credit, quant macro, cross-asset

| Handle | Notes |
|--------|-------|
| hussmanjp | John Hussman - equity/macro valuation |
| junkbondinvest | junkbondinvestor. Instrument-level high-yield and distressed-credit specialist: cash-bond points/yields, CDS, ratings, new-issue versus secondary pricing, leverage, and coverage. Strong for AI-infrastructure credit when ORCL/CRWV or data-center debt is live. Bio flags satire, so verify ironic position claims and chart-only marks. |
| Gloeschi | MacroTourist; cross-asset CIO. Useful for breadth, equal-weight versus cap-weight tape, dispersion, volatility, and precious-metals ETF flows. Keep quantified market-internals posts; drop single-name wire notes and hashtag-heavy chatter. |

### Commodities / energy (macro-relevant)

| Handle | Notes |
|--------|-------|
| JeffCurrie | Jeff Currie. No public X presence: @JeffCurrie has 0 posts and a people search finds no other match (checked 2026-09-27). Not queried. |
| energyaspects | Energy Aspects if active |
| RystadEnergy | Rystad when energy-macro |
| GavMcCracken | Oil and Commodities |
| JavierBlas | Bloomberg energy and commodities columnist. High-frequency physical-market reporting plus interpretation across oil, metals, logistics, and industrial inputs; separate reported facts from his causal framing. |
| Ole_S_Hansen | Saxo commodity strategist. Positioning, exchange inventories, metals, agriculture, and cross-commodity regime analysis; keep quantified free-text posts and identify chart or COT inputs. |
| Rory_Johnston | Commodity Context oil-market researcher. Physical-flow, inventory, SPR, pipeline, and policy analysis; free posts may point to paid work, so retain the on-X claim and its stated method. |
| aeberman12 | Art Berman. Energy systems and upstream production analysis; useful stock-versus-flow mechanisms and production constraints, with chart estimates independently checked when load-bearing. |
| LVision_Trading | Physical oil-flow and Hormuz vessel-forensics specialist. Uses AIS records, satellite imagery, named vessels, and explicit estimates; preserve methodology labels such as "guesstimate" and do not treat tracker output as official truth. |
| TomKloza | Tom Kloza, Gulf Oil / OPIS co-founder. US products, cracks, pump prices, refinery runs, EIA. Regional crack tables (CME / NYH / GC / LA), diesel $/gal, utilization streaks, named refiner tape. Complements Blas/Johnston (crude/flow) with the **product** invoice the notes kept needing. In-window: "$100/bbl cracks will do that" on refiner ATHs. |
| ericnuttall | Eric Nuttall, Ninepoint energy PM. Oil macro + Canadian E&P equities. Disclosed long-energy camp. SPR/floating-storage arithmetic, Hormuz vs official mb/d, China import rebound, "how does this end?" Invalidation is usually status-quo duration. Occasional fund video. Equity EQ-B energy (with `JoshYoung`) Fills the energy-equity PM gap the equity file already names. Treat as a disclosed camp, not a flow audit. |
| GasBuddyGuy | Patrick De Haan, GasBuddy. Retail gasoline/diesel, pump prices, refining slack, product cracks. | Pump and futures levels (RBOB/ULSD vs WTI), EIA distillate "red alert," Russia refinery-attack transmission. Some travel/personal. |
| TankerTrackers | TankerTrackers.com. AIS/satellite oil shipments; named vessels, Kharg, blockade-line mb/d. Primary loading/flow counts; corrections of official 8–10 mb/d claims; Iranian production ≈ domestic runs. Some snark. Macro commodities, AIS (with `LVision_Trading`) |
| LSREnergy | oil & energy markets |
| HFI_Research | HFI Research, an oil/gas research service. Repeated public inventory, SPR, seaborne-flow, and refining-margin calculations, including explicit corrections. Keep units, vintages, methodology, and later corrections; distinguish weekly estimates from monthly data and trace borrowed flow inputs. Drop geopolitical speculation, book cheerleading, and subscription-only teasers. Commodity eligibility does not confer core equity eligibility. |


### When the topic is a named person on X

If the topic **is** a Tier A person, pull `from:that_handle` heavily (still
apply the hashtag/quality gate and on-topic-only rules). If they are not on this list but
the user named them, apply **user-requested exception** for that run only.

## Tier B - Quality markets journalism and editorial

Use for framing and amplification. Prefer named Tier A reporters/strategists
over brand firehoses when both exist.

| Handle | Notes |
|--------|-------|
| DavidInglesTV | Bloomberg TV |
| markets | Bloomberg Markets |
| business | Bloomberg Business |
| BloombergTV | Bloomberg TV |
| FT | Financial Times |
| WSJ | Wall Street Journal |
| Reuters | Reuters |
| Economist | The Economist |
| FTAlphaville | FT Alphaville |
| CNBC | lower weight than FT/WSJ/Bloomberg named voices |
| oddlots | Odd Lots / Bloomberg podcast |
| labubu_trader | equity and bond market commentary |
| colbyLsmith | NY Times reporter covering Fed etc. |

## Tier C - High frequency newsy posts - lower signal but helpful for context

| Handle | Notes |
|--------|-------|
| FirstSquawk | Fast attributed headline and tape relay. Use for timestamped market levels, economic releases, company news, and attributed policy remarks; corroborate consequential claims and exclude unverified geopolitics or crypto price dumps. |
| Barchart | Very frequent posts - mostly informational but worth monitoring |

## Ranking hygiene (noise)

Hard-allowlist is enough for queries; you do not need a long deny list. When
Top/semantic results surface non-list authors (meme finance, clip accounts,
outrage accounts, classic noise amplifiers), **discard** them. Do not discuss
or promote them in the brief.

## Batching handles for `from:` queries

X query strings break if too long, and a roster-plus-keyword query with more
than four `from:` handles silently drops its `since:`/`until:` bounds. The
batches below are source families: run a family as `from:` groups of at most
**four** handles whenever the query also carries keyword terms or an
exact-time bound; a handle-only, date-granular sweep may use 6–10. The full
batching rules are in `query-patterns.md`.

```text
(from:dampedspring OR from:TimmerFidelity OR from:MichaelKantro OR from:lisaabramowicz1 OR from:AndreasSteno OR from:biancoresearch OR from:SteveMiran OR from:albertedwards99) since:YYYY-MM-DD
```

```text
(from:nicktimiraos OR from:lisaabramowicz1 OR from:LizCapoMcCormick OR from:TheStalwart OR from:greg_ip OR from:PolemicTMM OR from:EffMktHype OR from:VKMacro OR from:dsquareddigest OR from:RobinWigg) since:YYYY-MM-DD
```

```text
(from:robin_j_brooks OR from:MacroAlf OR from:donnelly_brent OR from:JStanleyFX OR from:AndreasSteno OR from:Frances_Donald OR from:michaelxpettis) since:YYYY-MM-DD
```

```text
(from:JavierBlas OR from:Ole_S_Hansen OR from:Rory_Johnston OR from:aeberman12 OR from:LVision_Trading OR from:energyaspects OR from:GavMcCracken OR from:PauloMacro OR from:VKMacro OR from:HFI_Research) (oil OR crude OR Hormuz OR SPR OR tanker OR pipeline OR inventory OR refinery OR diesel OR positioning) since:YYYY-MM-DD
```

```text
(from:Ole_S_Hansen OR from:JavierBlas OR from:TaviCosta OR from:energyaspects OR from:RystadEnergy OR from:PauloMacro) (copper OR gold OR silver OR platinum OR agriculture OR commodities OR inventory OR positioning OR COT OR OI OR CTA) since:YYYY-MM-DD
```

```text
(from:LoganMohtashami OR from:CalculatedRisk OR from:conorsen OR from:Claudia_Sahm OR from:JosephPolitano OR from:IrvingSwisher) (housing OR mortgage OR inventory OR labor OR employment OR payrolls OR participation) since:YYYY-MM-DD
```

```text
(from:VolSignals OR from:options_insight OR from:Gloeschi OR from:Fullcarry OR from:qthomp OR from:krugermacro) (FOMC OR CPI OR payrolls OR breadth OR dispersion OR gamma OR volatility OR positioning) since:YYYY-MM-DD
```

```text
(from:Ksidiii OR from:Alpha_Ex_LLC OR from:KrisAbdelmessih) (VIX OR volatility OR vol OR skew OR surface OR gamma OR convexity OR tail OR dispersion OR correlation OR dealer OR hedging OR OPEX OR expiry) since:YYYY-MM-DD
```

```text
(from:junkbondinvest OR from:lisaabramowicz1 OR from:TruthGundlach OR from:TheStalwart OR from:albertedwards99 OR from:dsquareddigest OR from:ericlonners) (bond OR credit OR CDS OR spread OR issuance OR leverage OR rating OR "private credit" OR fiscal OR capex) since:YYYY-MM-DD
```

```text
(from:nicktimiraos OR from:GregDaco OR from:sonalibasak OR from:DannyDayan5 OR from:AnnaEconomist OR from:DianeSwonk OR from:Fullcarry OR from:dampedspring OR from:albertedwards99 OR from:FirstSquawk) (FOMC OR "press conference" OR "rate hike" OR "rate cut" OR "financial conditions" OR dissents) since:YYYY-MM-DD
```

```text
(from:WarrenPies OR from:EPBResearch OR from:wabuffo OR from:BobEUnlimited OR from:LHMacro) (CPI OR PCE OR inflation OR payrolls OR withholding OR housing OR cyclical OR growth OR Treasury OR Fed OR rates OR FIMA OR Japan OR yen OR JGB OR BOJ) since:YYYY-MM-DD
```

```text
(from:choffstein OR from:profplum99) (passive OR index OR financing OR futures OR leverage OR liquidity OR NDFI OR overlay OR "portable alpha" OR credit) since:YYYY-MM-DD
```

```text
(from:ClausVistesen OR from:VPatelFX) (ECB OR HICP OR Europe OR eurozone OR GBP OR USD OR wages OR labor OR inflation OR FOMC OR gas) since:YYYY-MM-DD
```

Rotate batches by topic:

- **US data / FOMC:** rates + Fed reporters + albertedwards99 + PolemicTMM / EffMktHype / VKMacro / dsquareddigest / RobinWigg (on-topic filter after); ericlonners when fiscal/AI-capex is live
- **FX/Europe:** Saravelos / Brooks / MacroAlf / Donnelly / Stanley / Steno; ClausVistesen for ECB/eurozone and VPatelFX for USD/GBP data-policy work; VKMacro when JPY/intervention is live
- **China / global imbalances:** michaelxpettis + Brad_Setser; drop Pettis culture asides
- **Options / event vol:** VolSignals and options_insight for live dealer/skew/GEX mechanics; Ksidiii for tail and short-vol compensation; Alpha_Ex_LLC and KrisAbdelmessih for correlation, surface, and microstructure. Split the batches so a prolific or reply-led feed does not crowd out the others.
- **US cycle / income / policy:** WarrenPies for inflation/Fed uncertainty; EPBResearch for cyclical subsets; wabuffo for calendar-adjusted nominal withholding; BobEUnlimited for rates, official flows, and demand. These are different measures and interpretations, not four audits of one print.
- **Systematic financing / passive flows:** choffstein + profplum99 for mechanisms and analytical replies; recover parents and do not infer a current book.
- **Housing / labor:** Logan Mohtashami plus housing, labor, and Fed specialists
- **Physical energy:** Blas / Hansen / Johnston / Berman / LVision / HFI_Research plus established energy research; retain data vintages and corrections
- **Cross-asset internals:** Gloeschi plus options and macro PMs when breadth, dispersion, or ETF flows are live
- **Active trader trajectory:** Fullcarry / PauloMacro / BlacklionCTA / patternartist_ only for
  same-author stance changes under the overlay rules; never as sample breadth
- **Sector / industry:** specialists batch only when domain is live
- **Discovery scan:** 2–4 Tier A batches in-window; optional light specialist sample; skip empty sleeves
- **Semiconductor industry:** A higher priority industry to track

After each batch, apply the hashtag/quality gate and drop off-topic posts.

## Current coverage gaps

The list remains thinnest in independent hard-credit/capital-structure work,
continuous Asia-session FX, non-oil physical commodities, and free macro trader
diaries with explicit position-state follow-through. China/global-imbalance
coverage improved with `michaelxpettis`; that does not fill Asia FX. Use
discovery lanes to generate candidates, but keep them outside the synthesis
core until they pass the promotion rules above.

## Handle verification

If `from:handle` returns empty or wrong person, run `x_user_search` once,
correct the handle for this session, and note uncertainty in Gaps. Do not
guess a similar username.

`roster.tsv` beside this file indexes every registered handle with its
registry section and last verified date. The parent's
`xgrok_roster.py check` flags brief handles absent from it (with near matches
for typos), and a monthly `probe-brief` run of single-handle `from:` searches
refreshes the dates so dead or renamed accounts surface before a live run.
Membership there is provenance, not a quality verdict; this file remains the
rules source.
