# Credible equity sources

**Purpose:** Hard allowlist for **equity** signal on X - Mag 7 / tech / semis
**and** multi-sector free research (industrials, healthcare, consumer, special
sits). Companion to `credible-sources.md` (macro). Loaded by the `/macro` skill
when the topic or discovery cluster is Mag 7 / AI infra / semis **or** dense
company-level equity research in any sleeve (e.g. NVDA, META, AAPL, ORCL, CRWV,
RRX, TARS, GIL, etc.). See `SKILL.md` equity mode gate, Step 2, and
`equity-retrieval.md` for the coverage contract. Executable batches live only
in `query-patterns.md`. When participant-native equity temperature is part of
the product, also load `equity-sentiment-panel.md`; that file defines a separate,
weaker evidence role and does not expand this allowlist.

If an author is not on this list (and not a one-run user-requested exception),
**do not** use their post as **core equity evidence**. A post may qualify only
for the separately labeled sentiment-sample or context/discovery roles defined
in `equity-sentiment-panel.md`.

Handles change; treat this as a living list. Prefer fewer high-quality voices
over expanding into noise. When unsure, leave them out.

## Contents

- [Quality and promotion](#quality-rubric)
- [Trader overlay and filters](#active-trader-trajectory-overlay-anecdotal-only)
- [Evidence-file roles](#how-the-evidence-files-relate)
- [Tier EQ-A](#tier-eq-a---equity-market--pm--research-grade-takes)
- [Tier EQ-B](#tier-eq-b---domain-specialists-market-structure-and-industry-news)
- [Exclusions and ranking](#exclusion-policy)
- [Source routing](#source-routing-by-sleeve)
- [Expansion and verification](#expansion-rules-when-adding-more)
- [Current gaps](#current-coverage-gaps)

## Quality rubric

Use this when scoring new candidates. Do not add accounts that fail it.

### What "Valueist-class" means (and does not mean)

**Does mean:** high **information density** and **market signal** per post.
Connects facts to equities: risk, positioning, estimates, levels, catalysts,
variant perception, what must be true. Usable free text on X. On-topic enough
to not need babysitting. Length is irrelevant - a 2-line post that revises the
tape is better than a dry essay that does not.

For chart-aware retrieval, usable free text is a claim gate, not a blanket
attachment-discovery filter: an eligible in-domain source's terse-caption
attachment can remain an **unread visual lead** under the
[delegated packet contract](../SKILL.md#delegated-evidence-packet-contract).
It supplies no company conclusion or trader action before pixel inspection;
source/domain, trajectory and promotional/paywall exclusions still apply.

**Does not mean:** multi-thousand-word notes, academic valuation dumps, or
"research PDF exists." Do **not** filter on word count. Short posts are first-class
if dense. Long posts are only valuable when the density holds.

| Class | Shape | Examples |
|-------|--------|----------|
| **Gold** | High-signal equity takes (any length): facts → price/risk/positioning. Live market relevance. | TheValueist; KerrisdaleCap; DanielTNiles; sssjeffpu |
| **Core PM / estimate** | Named PM, CIO, or estimate-driven voice with free usable claims. | GavinSBaker, munster_gene, mingchikuo, garyblack00 |
| **Forensic / special sits** | Activist/forensic research with numbers in free text. Biased; high density when on a name. | CulperResearch, blueorcainvest, ScorpionFund, muddywatersre, Bleecker__St, WolfpackReports |
| **Industry / news** | High factual density on semis, Apple, AI hardware, Taiwan supply chain, or attributable earnings-call language. **Not** primary for market consensus. | firstadopter, DylanOnChips, dnystedt, SemiAnalysis_, fabknowledge, markgurman, TheTranscript_ |
| **Options / market structure** | Falsifiable levels and positioning models that explain amplification, not fundamental direction. Label vendor estimates. | Yam_Trades, spotgamma, VolSignals, options_insight, Ksidiii, Alpha_Ex_LLC, KrisAbdelmessih |
| **AI-infrastructure capital structure** | Prospectus, cash-flow, contract, lease, project-finance, and credit work that distinguishes secured assets from corporate risk. | TechFundies, RHouseResearch, SouthernValue95 |
| **Active trader trajectory (overlay)** | Same-author, self-reported stance and position-state changes. Anecdotal only; not factual support, consensus, or verified performance. | TheValueist; wey_how12640 |
| **Exclude** | Off-topic too often; paywall teasers; TV cheerleading; dry education with no live market take; snark without equity content. | — |

## Promotion rules

Apply the format-neutral promotion policy in `credible-sources.md`. Establish
repeatable value across multiple dates or events, but do **not** require
original root posts: substantive quote-post commentary, analytical replies,
and consistently useful repost/relay curation can also qualify. Label a
reply-led or curation-led role in the live row. Preserve parent/root context for
replies, and trace curated material to its underlying author/source; curation
is not independent corroboration or the curator's original analysis. An
underlying claim enters core equity synthesis only when its original author is
also allowlisted or is a user-requested exception for that run; otherwise it is
a discovery lead. A single useful interaction, adjacency, biography, or
follower count can nominate a candidate but cannot establish repeatable value.
Record the handle's domain gate and material caveat, and resolve renames from
known post identity rather than guessing from a similar username.

## Active trader trajectory overlay (anecdotal only)

Apply the trajectory rules in `credible-sources.md`. This overlay is separate
from EQ-A/EQ-B: it can show a change in one participant's self-reported stance or
book, but cannot establish company facts, market consensus, or sample breadth.

| Handle | Overlay role / gate |
|--------|---------------------|
| TheValueist | Existing EQ-A source. Use explicit hold/non-sell language and option-structure intentions as separate state labels; do not turn a considered structure into a claimed fill. |
| wey_how12640 | Equity swing/trend diary across growth and technology names. Keep text-bearing risk and position-state updates such as hold, add, de-risk, half-sale, re-entry, stop, or core retained. Treat all actions as self-reported, do not infer fills or size, and drop chart-only/watchlist posts. |
| patternartist_ | deafturtle, a pseudonymous multi-asset diarist. Dated same-day journals record declared entries/open positions and later adds, partials, stops, covers, and exits, with event waits and self-critique. Use a prior receipt and a later update in the same instrument; do not reconstruct intraday foresight from an end-of-day recap or infer fills, size, returns, or unspecified shorthand. Anecdotal only; no core factual or consensus role. |

## How the evidence files relate

| File | Primary use |
|------|-------------|
| `credible-sources.md` | Rates, Fed, inflation, FX, credit, broad macro |
| `credible-equity-sources.md` (this file) | Core equity facts, interpretation, disagreement, and bounded professional consensus |
| `equity-sentiment-panel.md` | Role-labeled equity mood, stance, action, repetition, and conversational texture; never a core-claim bypass |

- Do **not** silently promote a macro-only handle into equity synthesis because
  they once tweeted NVDA.
- Overlap is allowed only if the handle appears on **both** lists (or is
  user-requested for the run).
- Macro industry specialist **`SKundojjala`** stays domain-gated on the macro
  list for pure semi research. Prefer this equity list for Mag 7 **market** takes.

## How to use

1. Run the source-family batches in `query-patterns.md`; split crowded families.
2. After every core-evidence result, **drop** posts whose author is not below.
   Keep sentiment-panel and context/discovery candidates in separate ledgers;
   never merge them into EQ-A/EQ-B.
3. Apply **post-level** filters even for allowlisted authors.
4. Tier weights: **EQ-A > EQ-B**. The trajectory overlay is a separate,
   lower-weight individual-participant role, not a tier.
5. EQ-B is industry/news color. Do **not** let EQ-B alone define a contested
   market read (positioning, multiple, risk/reward) if EQ-A is silent or split.

## Post-level filters (all equity tiers)

| Filter | Rule |
|--------|------|
| Hashtag / quality | Same rule as `credible-sources.md`: do **not** drop an allowlisted post solely for 2+ `#hashtag` tokens. Keep usable free-text analysis. Drop only if it also devolves into tag soup, promo, or engagement farming. |
| Off-entity | In topic mode, drop posts not about the equity topic / related names. |
| Domain gate | Keep equity research / company theses / sector tape. Mag 7 topic mode: prefer Mag 7, semis, AI infra, cloud/ad, related second-tier. Multi-sector discovery: any named equity with free-text thesis is in scope. Drop politics, sports, pure personal, legal theater, or unrelated macro unless it clearly drives the equity tape. |
| Paywall bait | Prefer free-text analysis. Drop pure teaser posts that only point at a paywall with no usable claim. |
| Cheerleading | Drop pure ticker spam / emoji hype with no driver, level, or risk framing. |
| Media promo | Drop "great to be on CNBC" posts with no thesis; keep only if a real market claim is in the free text. |
| Trader trajectory | Keep a precise text-bearing state and its reasoning. Drop chart-only calls, retrospective victory laps without an earlier receipt, claimed P&L as proof, and feeds whose public actions appear mainly after subscribers received them. |

---

## Tier EQ-A - Equity market / PM / research-grade takes

Primary sources for equity market takes (Mag 7 and multi-sector).
Attribute camps; do not treat PM bullishness or activist short theses as forecast truth.

| Handle | Notes |
|--------|-------|
| TheValueist | High-signal discretionary L/S TMT+energy voice: read-throughs, margin/order quality, risk framing, and portfolio structure in long or short posts. One author counts as one voice. A long multi-name note does not satisfy source diversity; summarize it unless the wording itself carries signal. |

### EQ-A multi-sector high-signal research (any sector)

Company-level equity signal outside pure Mag 7 tape: thesis, numbers, risk,
variant perception. **Post length is irrelevant.** Prefer information-dense free
text (one sharp line or a numbered thread both count).

**Bias note:** several are activist / forensic short shops. High density when on
a name; always treat as **one-sided** (disclosed interest). Prefer math and
variant perception in free text, not PDF-link-only teasers.

| Handle | Notes | Sector / style |
|--------|-------|----------------|
| bespokeinvest | Bespoke Investment Group. Original, timestamped tape, breadth, factor, and cross-sector context with concrete levels and historical comparisons. Keep data-rich posts; drop promotion and banter. | Multi-sector research / tape |
| borrowed_ideas | MBI Deep Dives. Repeated company-level work on digital ads, travel marketplaces, and other compounders connects operating evidence to estimates and valuation. Keep substantive free text; drop link-only or premium teaser posts. | Multi-sector fundamental research |
| KerrisdaleCap | Kerrisdale Capital. Multi-sector L/S: multiples, margins, TAM, risk/reward; long and short. Strong free-text signal. | Multi-sector L/S |
| CulperResearch | Culper Research. Peak-sales math, royalty comps, addressable-market math. Dense free text (often threaded). | Healthcare / multi-sector short |
| blueorcainvest | Blue Orca Capital. Forensic short with governance/cash/liability detail. | Multi-sector forensic short |
| ResearchGrizzly | Grizzly Research. Forensic conclusions after DD. | Multi-sector forensic short |
| ScorpionFund | Scorpion Capital. Forensic evidence with hard numbers. Biased short; high signal when active. | Multi-sector forensic short |
| JehoshaphatRsch | Jehoshaphat Research. Free short summaries with growth/channel theses. Keep free-text claims. | Multi-sector forensic short |
| muddywatersre | Muddy Waters. Forensic short brand. Domain-gate legal theater / personal; keep company-research posts only. | Multi-sector forensic short |
| sprucepointcap | Spruce Point Capital. Forensic + occasional activist free-text. Keep research posts only. | Multi-sector forensic / activist |
| viceroyresearch | Viceroy Research. Forensic free-text when on a name. Domain-gate beef/snark. | Multi-sector forensic short |
| Bleecker__St | Bleecker Street Research. Activist short with free-text deal math, related-party and customer diligence (e.g. funding/channel claims). | Multi-sector forensic short |
| WolfpackReports | Wolfpack Research (Dan David). Free forensic threads with hard numbers and site-visit detail when on a name. | Multi-sector forensic short |
| CaieKelley | Independent AI-infrastructure and industrial-policy commentator. Repeated work on power/GW economics, government stakes, and accounting implications can sharpen equity read-throughs. Use substantive domain posts only and verify policy or accounting claims. | AI infrastructure / industrial policy |
| nodiligence | semiconductors and compute financing - kind of archaeology on corporate filings |
| GavMcCracken | commodity and energy guy + good geopolitical takes |
| Adam_Wyden | Adam Wyden, ADW Capital founder and CIO. Concentrated long-activist company work, especially non-tech SMID situations: sum-of-parts, liquidation value, and franchise economics. Free-text estimates are episodic and campaign-linked; retain their assumptions and distinguish his analysis from relayed sell-side or filing recaps. Drop slogans, letter-only promotion, and self-scored wins; treat this as an interested long camp, not broad consensus. | Non-tech / SMID long activist |

### EQ-A core - named PM / CIO / market strategist (Mag 7 / growth tech heavy)

| Handle | Notes | Fit vs rubric |
|--------|-------|----------------|
| GavinSBaker | Gavin Baker, Atreides CIO. Cross-over tech PM; AI stack margin structure, Mag 7 / semis market framing. Free-text theses. | Core PM |
| munster_gene | Gene Munster, Deepwater. Opinionated growth-tech investor; useful for Mag 7 thesis durability, timing, and what would change the bull case. Treat as a disclosed camp, not consensus. | Core PM |
| mingchikuo | Ming-Chi Kuo, TF International. Supply-chain estimates with market-moving equity impact (esp. Apple ecosystem). Prefer estimate + implication posts. | Estimate-driven |
| garyblack00 | Gary Black, Future Fund. Active TSLA / Mag 7 fundamental PM commentary; delivery vs promise framing. | Core PM |
| DanielTNiles | Dan Niles, Niles Investment Management. Tech PM; Mag 7 / AI "speedbump" risk-reward, token economics, SOX/momentum framing. High free-text density. | Same class as Baker/Munster |
| StockSavvyShay | Shay Boloor, Futurum Equities market strategist. Fast, chart-heavy post-print packaging across Mag 7, AI infrastructure, memory, and neoclouds. Useful for numbers and catalyst maps; verify transcript-sensitive claims and drop pure video promotion. | Market-side strategist |
| JonahLupton | Jonah Lupton, FirstWave CIO. Disclosed long-biased growth book across AI infrastructure, semis, software, and selected healthcare. Keep catalyst-to-model revisions, estimate tables, and explicit conviction or position changes. Domain-gate personal/lifestyle posts and treat long-dated price paths as an aggressive camp, not street consensus. | Growth PM / disclosed camp |
| SouthernValue95 | SouthernValue. Bull-leaning hyperscaler ROIC and data-center unit-economics modeler. Useful original GW, rental-price, IRR, and capex-to-earnings work; treat utilization, discount, and terminal-price inputs as assumptions rather than neutral tape. | AI-infra / hyperscaler ROIC |
| citrini | Citrini Research. Thematic cross-asset research; Mag 7 / AI allocation theses free on X. Can be punchy; keep market theses, drop pure vibes. | Research brand |
| RichLightShed | Rich Greenfield, LightShed Partners. Named TMT analyst; free market structure on media deals, streaming leverage, distributor power ($PSKY/$WBD etc.). Drop pure podcast promo. | TMT sell-side craft |

### EQ-A research - estimate abstracts / sell-side craft on X

Tech estimate and math signal (short abstracts count).

| Handle | Notes | Fit vs rubric |
|--------|-------|----------------|
| sssjeffpu | Jeff Pu. ~20y tech equity research + industry. Free abstracts: TPs, EPS revisions, margins, CoWoS/GPU demand, TSM/ASML/AMD/META read-throughs. | High-signal free abstracts |
| p_ferragu | Pierre Ferragu (New Street Research circle). Numbered takes on deals, capex, memory math. Domain-gate personal noise. | Estimate/math market takes |
| RihardJarc | Tech investor and company-research commentator. Repeated AI-stack, META, HBM, and neocloud work connects company claims to margins, capex, and equity read-throughs. Verify anonymous or secondary-source claims and drop banter. | AI stack / company research |
| saso_capital | SasoEquity. Repeated numbered earnings-call and company notes across hyperscalers, software, semis, and neoclouds connect management Q&A to mix, margins, estimates, and the multiple. Keep thesis-bearing free text; drop TA, buy-alert victory laps, and generic promotion. Verify transcript-derived figures and label the pseudonymous identity. | Company research / earnings-call abstracts |
| Stephanie_Link | Stephanie Link, Hightower chief investment strategist/PM. Concise post-print and style-factor takes, especially demand versus conversion and growth versus value. Use as an opinionated PM read, not a transcript source. | Cross-sector PM / strategist |
| TechFundies | TechStockFundamentals. Prospectus- and earnings-driven work on CoreWeave and hyperscaler capex/FCF; explicitly surfaces uncertainty and revises modeling assumptions. Strong for RPO, ROIC, depreciation, interest, and cash-conversion questions. | AI-infra fundamentals / cash flow |
| RHouseResearch | Rittenhouse Research. Neocloud, data-center lease, power/MW, SPV, and credit-structure specialist. Useful on secured versus unsecured pricing and operational delivery; disclose its Substack/ticker lean and verify terminal screenshots or second-hand CDS marks. | AI-infra credit / leases / operations |
| EricJhonsa | Eric Jhonsa. Company-level estimates and risk/reward across power-for-compute, semis, neoclouds, and software: named multiples, bookings, backlog, financing needs, and revisions. Strong free-text analytical replies complement the mega-cap core. Preserve parent/quote context, separate his valuation work from relayed technical claims, verify transcript inputs, and label PM/book incentives. | AI stack / power / company estimates |

### EQ-A estimate wire (Asia / print vs consensus)

| Handle | Notes | Fit vs rubric |
|--------|-------|----------------|
| jukan05 | Citrini-adjacent. Dumps of Asia research notes, TSMC/SK hynix estimate vs actual, local broker targets. High utility on print days - short posts fine. | Estimate/news hybrid; weight below gold/core when interpreting |
| EconomyApp | App Economy Insights. Multi-name earnings dumps (rev/margin/EPS/guide) with tickers; Mag 7 + semis prints. Drop pure newsletter upsell posts; keep numbers. | Print/data hybrid; weight below gold/core when interpreting |

**EQ-A usage:**

- Use **TheValueist** for high-signal Mag 7 / AI-infrastructure read-throughs,
  but count the account as one voice and summarize long multi-name research
  unless exact wording is the evidence.
- Prefer **KerrisdaleCap** among multi-sector free L/S ideas.
- Prefer **Culper / Blue Orca / Grizzly / Scorpion / Jehoshaphat / Muddy Waters / Bleecker / Wolfpack** for forensic/special-sits math - always label short-interest bias.
- Prefer **DanielTNiles**, **sssjeffpu**, **p_ferragu**, **RichLightShed** for estimate and risk framing on tech/TMT.
- Prefer **GavinSBaker / munster_gene / garyblack00 / StockSavvyShay /
  JonahLupton / SouthernValue95** for live Mag 7 / AI tape camps, applying each
  row's disclosed-camp and domain caveats.
- Prefer **borrowed_ideas / RihardJarc / CaieKelley / saso_capital** for
  company-level or AI-stack work inside their stated domains; apply each row's
  paywall, identity, transcript, source, and verification caveats.
- Prefer **TechFundies / RHouseResearch** for prospectus, cash-flow, contract,
  secured-credit, lease, and project-finance detail in neocloud/data-center names.
- Prefer **mingchikuo / jukan05 / EconomyApp / Beth_Kindig** for supply-chain,
  industry comparisons, Asia prints, and free earnings summaries; use EQ-B
  sources only for drivers.
- Do **not** prefer long posts over short ones. Prefer **signal density**.
- Apply domain gate, hashtag/quality, and media-promo filters always.

---

## Tier EQ-B - Domain specialists, market structure, and industry news

### Options / equity-market structure

Use for positioning, volatility regime, skew, and flow mechanics. These sources
help explain how a catalyst can be amplified; they do not establish the
fundamental direction of the market. Treat gamma, wall, pivot, and dealer-
exposure figures as **vendor or model estimates**, not audited exchange-wide
open interest.

| Handle | Notes |
|--------|-------|
| Yam_Trades | Yamco - SPX and single-name options flow, skew, and event-positioning maps. Repeated falsifiable levels and sized structures; usually attributes ConvexValue / OptionsDepth inputs. Keep free-text analysis, label third-party model data, and drop product-only promotion. |
| spotgamma | SpotGamma - index-options, correlation/dispersion, and volatility-regime analysis. Useful free-text risk pivots and cross-asset vol observations; heavy vendor/product footprint, so keep only substantive posts and label model estimates. |
| VolSignals | Equity-index options and dealer-hedging specialist. Multi-date gamma, vanna, skew, and event-volatility analyses are useful for amplification mechanics; label every proprietary reconstruction and avoid treating the model as audited market-wide positioning. |
| options_insight | Imran Lakha / Options Insight. Former institutional index-options trader and European options-desk head. Repeated free-text work distinguishes index from single-name residual books, tests OPEX hedge decay and skew/spot-vol regimes, explains VIX carry, and corrects per-strike or sign-naive GEX readings. Keep the on-X mechanism, label street/dealer positioning as inferred, and drop masterclass, community, or product-only promotion. |
| Ksidiii | Kris Sidial, Ambrus co-CIO and volatility/tail-risk PM. Adds compensation-aware short-vol and convexity analysis, event-vol flow footprints, tail-risk boundaries, and evidence-based challenges to generic positioning narratives. The feed can be episodic; distinguish structural frameworks from live inventory and drop firm or appearance promotion. |
| Alpha_Ex_LLC | Dean Curnutt / Alpha Exchange. Macro Risk Advisors founder and cross-asset volatility/derivatives specialist. Repeated original posts cover dispersion and realized correlation, long-dated single-name skew and collars, option overlays, and delta-implied-vol interaction. Keep Dean's free-text analysis, separate podcast guests or linked sources, and label construction assumptions and advocacy. |
| KrisAbdelmessih | Kris Abdelmessih / Moontower, former options market maker and relative-value volatility PM. Useful conversation-led work on live surface/skew diagnosis, FLEX and exercise microstructure, relative value, and market-maker mechanics. Recover parent context for replies; drop off-topic posts, newsletter cards, product notices, and generic education without a current market application. |
| alphaticaio | Alphatica. Repeated index and single-name GEX, dark-pool, breadth, and market-internals work includes explicit invalidation levels. Treat proprietary GEX and dark-pool figures as model outputs, and drop product-only promotion. |
| JoeyGEX | FZN Joe / Fuzion, a vendor-affiliated options voice. Repeated signed-versus-naive GEX/DEX distinctions, spread-versus-outright flow corrections, VIX spot/skew decomposition, and intraday positioning revisions. Treat dealer maps and inferred spread identities as estimates; preserve disappearing-wall updates and counterarguments. Separate Nomura/McElligott relays from his own analysis, and drop community/product promotion. Not fundamental direction or an independent audit of other vendors. |

### Technical structure and index-futures statistics

Use for conditional price structure, session distributions, and statistical
cross-checks. Historical frequencies, technical levels, and descriptive
breadth do not alone establish tradable expectancy or fundamental value.

| Handle | Notes |
|--------|-------|
| notprofgreen | Pseudonymous statistical tester and analytical-reply source for NQ/ES and related futures. Publishes negative results and corrections distinguishing candle survival, directional movement, and payoff; useful random-walk controls and challenges to out-of-sample overclaims. Preserve parents, samples, and instrument corrections. Statistics are not verified tradable expectancy or current positioning; drop affiliate/prop-account promotion and social banter. Credentials remain self-described. |
| ProbableChris | Chris / NQ Stats. Original NQ session distributions, opening/time-based ranges, volatility-state analysis, and current applications. Preserve sample windows, adverse excursions, and methodological replies: stable out-of-sample hit rates do not by themselves reject a random walk or establish positive expectancy. Public tables and private execution rules are distinct; verify consequential figures, label coaching interests, and drop victory laps. Not a company analyst or audited trading record. |
| cfromhertz | Christian Fromhertz / Tribeca Trade Group. Contemporaneous ETF and sector tape: equal-weight breadth, cross-sector divergences, trend/volume-at-price structure, and implied-move prints. Keep substantive free-text observations and inspect load-bearing charts; specify timestamp, universe, and model. Drop membership plugs, headline-only relays, and claimed performance. Tape description is not company valuation, verified flows, or a demonstrated trader trajectory. |
| alphatrends | Brian Shannon. Anchored-VWAP and multi-timeframe structure around live equities and ETF/underlying trading-hours differences. Keep explicit conditional scenarios, anchor choices, and invalidation context; inspect charts when levels depend on them. Distinguish a level of interest from a prediction or disclosed trade. Free analytical posts coexist with subscriber material; drop locked updates, product offers, and personal posts. Not fundamental valuation or a dealer-positioning model. |

### Capital structure and financing mechanics

Use for explicit security, funding, depreciation, and return-mechanism work.
This is a lower-weight specialist lane: verify quoted inputs and do not let it
define contested equity consensus without EQ-A support.

| Handle | Notes |
|--------|-------|
| malinvested | `malinvestment.jpeg`, a pseudonymous single-stock/macro analyst. Repeated substantive contributions connect AI-infrastructure capex to depreciation and ROIC, compare financing scale across credit markets, and examine single-name security and fund-liquidity mechanics. Keep explicit calculations and structure analysis; exclude satire/shitposts and verify inputs inherited from quoted research. |
| NickNemo17 | Nick Nemeth / Mispriced Assets. Narrow insurance-accounting role: public statutory/captive and related-party asset reconstructions, merger terms, and financing constraints. Separate his document reconstruction from credited reporting, academic work, and inferred ownership; verify load-bearing filing/legal claims. Hypothetical removal of a permitted practice is not established insolvency. Label short/long interests, preserve article qualifications, and drop paid-trade teasers or stock cheerleading; not a general SMID valuation source. |

### ETF and fund structure

Use for wrapper, flow, and liquidity mechanics, not company valuation or a
standalone claim about aggregate investor consensus.

| Handle | Notes |
|--------|-------|
| EricBalchunas | Eric Balchunas, Bloomberg ETF analyst. Useful for fund wrappers, creations/redemptions, flow-versus-AUM comparisons, and liquidity/portfolio constraints. Domain-gate the noisy personal/media feed; drop show/book promotion and crypto advocacy without a fund mechanism. Trace colleague/guest inputs rather than counting relays independently; verify regulatory or tax interpretations. ETF-flow commentary is not company valuation or aggregate investor consensus. |

### Sector specialists

Use only inside the named sector. These accounts can surface differentiated
company and mechanism work, but do not define market consensus. Treat holdings
and sector incentives as disclosed camps, and verify clinical, regulatory, or
company-specific factual claims independently when decision-critical.

| Handle | Notes |
|--------|-------|
| deathtouch2k | Pseudonymous healthcare/biotech investor who self-describes as a life-sciences hedge-fund CIO. Repeated multi-name work links clinical mechanisms, trial design, valuation, and catalysts. Keep thesis-bearing posts, label possible or disclosed positions, and independently verify clinical claims. |
| adamfeuerstein | Adam Feuerstein, STAT biotech reporter. Repeated named trial, regulatory, and M&A catalyst posts often map results to competing public equities. Use as healthcare catalyst/news and attributable trial language, not as a long-biased PM or valuation source; verify decision-critical clinical claims against primary materials. |
| JoshYoung | Josh Young, Bison Interests CIO and energy-equity PM. Repeated substantive contributions connect oil-market fundamentals and company events to E&P and services equities. Keep substantive sector posts; drop promotion, memes, and position gloating. |
| A_May_MD | Adam May, a self-described biotech investor who may hold discussed names; clinical credentials are not verified by the handle. Reply-led trial-design, commercial-incentive, cash-burn, and financing analysis across biotech names. Recover parents, distinguish cross-trial comparisons from head-to-head evidence, and retain combination-therapy counterarguments. Verify clinical/regulatory claims against primary materials; drop memes, insults, and legal speculation. Does not establish long-biased PM coverage or standalone valuation authority. |

### Industry, product, and primary-language news (drivers, not market consensus)

Useful for **what happened** (chip news, Apple products, supply chains,
hardware, or attributable management language). **Not** primary for valuation,
positioning, or risk/reward.

| Handle | Notes |
|--------|-------|
| firstadopter | Fast semiconductor and AI-infrastructure number/management-quote flagger with useful stock read-throughs. Often relays others' reporting; separate the underlying source from his interpretation and drop newsletter promotion. |
| DylanOnChips | Dylan Martin (CRN). Semiconductor industry news/features. |
| dnystedt | Dan Nystedt. Semi / Taiwan financial analyst + former journalist. Industry facts. |
| SemiAnalysis_ | SemiAnalysis firm feed. Strong industry research drops; treat as research/news, not desk market-making. |
| fabknowledge | Fabricated Knowledge. Semi / AI stack industry analysis; occasional equity bridge. Promote to EQ-A only if sustained high-signal equity framing. |
| markgurman | Mark Gurman, Bloomberg. Primary Apple product/strategy news. Drives AAPL sentiment; not valuation analysis. |
| PatrickMoorhead | Patrick Moorhead, Moor Insights. AI servers, NVDA platform, hyperscaler hardware industry reads. |
| danielnewmanUV | Daniel Newman, Futurum. AI infra / open-source / industry strategy. Domain-gate politics. |
| dougclinton | Doug Clinton, Deepwater / IA Funds. AI product + investing experiments; lighter market density. |
| pequityresearch | Semi supply-chain maps and free semi notes (CPO, margins, stack). Industry charts; not primary market consensus. |
| Beth_Kindig | Beth Kindig, I/O Fund. Recurring free-text comparisons across hyperscaler capex/cash flow, AI product revenue, TSM capacity, and adjacent infrastructure names. Keep named figures and estimate revisions; drop newsletter/link-in-bio teasers and chart-only repetition. Use as industry/print context, not sole support for contested valuation. |
| TheTranscript_ | Fast earnings-call excerpts and management-language relay across sectors. Use only for attributed call quotations; verify decision-critical numbers against company materials and do not treat it as analyst opinion. |
| TMTBreakout | Self-described 17yr tech HF manager; Street/alt-data recaps plus original tape. Free-text post-print maps (software vs AI-semi follow-through), OpenAI/Anthropic ARR acceleration. Some Substack and off-topic replies. |
| nickgerli1 | Nick Gerli / Reventure. US housing demand, mortgage applications, affordability/PITI math, demographics vs inventory. Keep numeric demand and rate-transmission posts; drop Reventure ZIP/product CTAs and pure chart dumps. Domain gate: housing/builders, not broad equity tape. |
| t1alpha | options market commentary - tends to be chart-heavy |
| anni_sen | Anni Sen / BluBird Capital newsletter. Firsthand conference summaries and process-level interpretation of HBM/base-die control, memory supply, and power-for-compute. Separate presenter/company statements and quoted research from her own investment framing. Verify technical inputs and distinguish headline lease value from attributable revenue, cash flow, and capex burden. Label holdings and drop winner-framed calls, appearance promotion, and newsletter-only teasers; not standalone valuation authority. |


**EQ-B usage:**

- Include when topic touches semis, Apple, AI hardware, or supply chain.
- Include options specialists when event positioning, skew, dispersion, or
  dealer-hedging mechanics are live; attribute the model and do not infer
  direction from gamma alone.
- Use **options_insight** to challenge dealer/GEX and index-versus-single-name
  assumptions; **Ksidiii** for tail and short-vol compensation;
  **Alpha_Ex_LLC** for dispersion, correlation, and long-dated surfaces; and
  **KrisAbdelmessih** for surface-relative-value and execution microstructure.
  These roles explain mechanics and boundaries, not fundamental direction.
- Use **JoeyGEX** for signed-versus-naive positioning and flow-structure
  corrections; label vendor models and keep intraday revisions.
- Use **ProbableChris** for NQ session statistics and **notprofgreen** for
  payoff/random-walk cross-checks; preserve disagreement rather than counting
  the pair as consensus. Use **alphatrends** for conditional VWAP/MTF structure
  and **cfromhertz** for timestamped ETF/sector tape.
- Use **anni_sen** for semiconductor/process and AI-power interpretation;
  separate presenter statements, relayed research, and her investment claims.
- Use **malinvested** as a lower-weight mechanism cross-check when the post
  contains explicit calculations, security terms, or fund-structure mechanics;
  verify quoted inputs and exclude satire.
- Use **NickNemo17** only for insurance-accounting and deal-structure work;
  retain article qualifications and source lineage. A permitted-practice
  counterfactual is not a finding of insolvency or wrongdoing.
- Use **EricBalchunas** for ETF wrapper, flow, and liquidity mechanics; fund
  flows do not alone establish investor intent, company value, or consensus.
- Use **deathtouch2k** for healthcare investment interpretation,
  **A_May_MD** for trial-design and commercial/financing cross-checks, and
  **adamfeuerstein** for healthcare catalyst/news language. None substitutes
  for independent clinical verification. Use **JoshYoung** only for energy
  equities and label sector incentives.
- Use **Beth_Kindig** for named hyperscaler/AI-industry comparisons after
  dropping newsletter teasers; do not let it alone settle a contested multiple.
- Never let EQ-B alone define "consensus on the stock."
- Prefer EQ-B for factual triggers; EQ-A for market interpretation.

---

## Exclusion policy

The live allowlist is authoritative for core evidence; do not maintain a
historical reject ledger here. A non-listed handle remains discovery-only
unless it is explicitly registered for the weaker sentiment-sample role in
`equity-sentiment-panel.md` or a fresh review satisfies the promotion rules.
If the user names one for a run, label it `user-requested (not on allowlist)` in
Gaps rather than silently expanding the list. Reject or domain-gate feeds
dominated by promotion, paywalls, relays, politics, ticker spray, stale
activity, unverifiable identity, or non-equity content.

---

## Ranking hygiene

Hard-allowlist is enough for **core** queries. When Top/semantic results surface
unregistered non-list authors (retail ticker spam, meme accounts, course
sellers, anonymous engagement farmers), discard them from the core. A
participant-native run may route a qualifying post to the explicitly labeled
sentiment or context ledger under `equity-sentiment-panel.md`; it still cannot
enter EQ-A/EQ-B or inherit factual weight.

---

## Source routing by sleeve

Use these role combinations to choose the executable family batches in
`query-patterns.md`. Keep families separate until ranking starvation has been
ruled out; the recovery ladder lives in `equity-retrieval.md`.

| Sleeve | Prefer |
|--------|--------|
| Broad Mag 7 / AI equity tape | bespokeinvest + TheValueist + PM/company-research/estimate roles (including JonahLupton and saso_capital when on-name); light EQ-B |
| Non-tech / SMID long activist | Adam_Wyden for named campaign estimates and capital structure + borrowed_ideas / TheValueist when on name; distinguish activist interests from independent support |
| Multi-sector discovery / special sits | KerrisdaleCap + Culper + Blue Orca + Grizzly + Scorpion + Jehoshaphat + Muddy Waters + Spruce Point + Bleecker + Wolfpack |
| Apple product / supply chain | markgurman + mingchikuo + munster_gene + TheValueist |
| Semis / AI infra / NVDA stack | anni_sen for process-level EQ-B context + EricJhonsa + TheValueist + sssjeffpu + p_ferragu + RihardJarc + CaieKelley + saso_capital + SemiAnalysis_ + fabknowledge + firstadopter + Beth_Kindig + DanielTNiles + StockSavvyShay + jukan05 + EconomyApp |
| Tesla | garyblack00 + TheValueist (if posting) |
| Neocloud / CRWV / ORCL | TheValueist + TechFundies + RHouseResearch + SouthernValue95 + StockSavvyShay + GavinSBaker + RihardJarc + CaieKelley + saso_capital + JonahLupton; light malinvested mechanism cross-check |
| Asia print (TSM, SK hynix) | jukan05 + sssjeffpu + dnystedt + p_ferragu + EconomyApp |
| Cross-sector earnings calls | TheTranscript_ for attributed language + TheValueist / EconomyApp / StockSavvyShay / saso_capital for interpretation and print packaging |
| Index / event vol / dispersion | JoeyGEX + Yam_Trades + spotgamma + VolSignals + alphaticaio + options_insight for maps and residual-book mechanics; Ksidiii + Alpha_Ex_LLC + KrisAbdelmessih for tail, correlation, surface, and microstructure cross-checks |
| Media / streaming / TMT M&A | RichLightShed + EconomyApp + citrini (when on name) |
| Insurance / captive / deal accounting | NickNemo17 for document reconstruction and qualifications; seek separate on-name EQ-A interpretation, not consensus from forensic allegations |
| Technical price structure / session statistics | alphatrends + cfromhertz for VWAP/MTF and ETF-sector tape; ProbableChris + notprofgreen for NQ distributions and methodological challenges; not fundamental value or verified expectancy |
| ETF wrappers / flows / liquidity | EricBalchunas for fund mechanics; distinguish flows from valuation-driven AUM changes and do not infer company fundamentals |
| Healthcare / biotech names | deathtouch2k + A_May_MD + adamfeuerstein + CulperResearch + ScorpionFund + KerrisdaleCap (when on name); distinguish catalyst news from investment interpretation and verify clinical claims independently |
| Energy equities | JoshYoung + TheValueist (when on name); cross-check commodity claims against macro energy specialists |

After each batch, apply the hashtag/quality gate and drop off-domain posts,
paywall-only teasers, and empty media promos.

---

## Expansion rules (when adding more)

**Add to EQ-A only if:**

1. Named PM, CIO, research brand, forensic/L/S shop, or estimate-driven analyst with equities track record, **and**
2. Posts routinely connect drivers → price, risk, positioning, or valuation (**short or long** - density matters, not length), **and**
3. On-topic rate is high (does not need heavy babysitting), **and**
4. Usable free-text claims appear on X (not mostly paywall/TV teasers), **and**
5. Sample of recent posts shows **live market signal** - not dry textbooks, not pure vibes.

**Add to EQ-B only if:**

1. Clear domain expertise (semi, Apple supply chain, AI hardware, options
   market structure, etc.), **and**
2. High factual density, **and**
3. Accept they will **not** define market consensus alone.

**Do not add:**

- High-engagement retail explainers without research/PM craft
- Pure news firehoses already covered by macro Tier B brands
- Dry education / valuation frameworks with no current market takes
- Accounts that fail the off-topic or paywall tests above
- Accounts selected mainly because posts are long

---

## Handle verification

If `from:handle` returns empty or wrong person, run `x_user_search` once,
correct the handle for this session, and note uncertainty in Gaps. Do not
guess a similar username.

`roster.tsv` beside this file indexes every registered handle (this list, the
macro list, and the sentiment panel) with its registry section and last
verified date; see the Handle verification section of `credible-sources.md`
for how the parent's check and the monthly probe use it. Membership there is
provenance, not a quality verdict.

## Current coverage gaps

- A broader non-AI power and infrastructure equities PM; `EricJhonsa` strengthens power-for-compute and adjacent company estimates but not that whole sleeve.
- A second pure-semiconductor sell-side voice posting usable free estimate abstracts.
- A healthcare long-biased specialist to balance the short and catalyst/news-heavy sleeve; `A_May_MD` adds analytical cross-checks and `adamfeuerstein` catalyst coverage, but neither establishes this role.
- Broader long-biased industrial, consumer, and financial-sector PM voices. `Adam_Wyden` adds concentrated non-tech activist work, not broad sector coverage; `NickNemo17` adds insurance accounting, not a financials long-PM sleeve.
- Additional non-US equity voices with repeatable free-text company analysis.
- More free multi-name trader diaries with contemporaneous entries and adverse
  updates or exits. `patternartist_` adds dated open-position journals and later
  adverse updates, not live execution proof; keep the trajectory overlay narrow.
