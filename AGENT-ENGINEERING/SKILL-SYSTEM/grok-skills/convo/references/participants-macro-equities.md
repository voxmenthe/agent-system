# Macro and equity-markets participant allowlist for `/convo`

This file is the **hard conversation-eligibility source of truth** for the
**macro and equities** topic area selected by `SKILL.md`.

It was seeded on **2026-07-30** from the hard source registries in the standard
`/macro` skill:

- `../../macro/references/credible-sources.md`
- `../../macro/references/credible-equity-sources.md`

This is a deliberate snapshot, not a runtime import. Changes to `/macro` do not
silently change `/convo`, and changes here do not change `/macro`.

## Contents

- Conversation-specific eligibility
- Macro and equity participant lanes
- Post-level gates and handle cautions
- Discovery priority and maintenance

## Conversation-specific eligibility

- Normalize returned authors by stripping a leading `@` and comparing exact
  handles case-insensitively. Do not fuzzy-match or infer renamed accounts.
- A conversation qualifies only through a substantive root, reply, self-thread
  continuation, or exactly linked quote post authored by a handle below.
- A promoted conversation must contain at least two substantive, exactly linked
  nodes. A standalone post from a credible source is still **not** a `/convo`
  conversation.
- An off-list root or reply may remain as labeled context after an allowlisted
  participant establishes eligibility.
- The allowlist gates participation; it does not certify a claim, establish
  consensus, or turn a disclosed position or proprietary model into fact.

## How to read the registry

Every backticked comma-separated token below is one exact allowlisted handle.
Lane names are stable batching and ranking hints, not additional eligibility
conditions. Split any lane longer than 10 handles into `from:` batches of
roughly 6-10.

### Macro participants

| Lane | Exact allowlisted handles | Conversation use |
|------|----------------------------|------------------|
| `macro-seed` | `dampedspring`, `TimmerFidelity`, `MichaelKantro`, `lisaabramowicz1`, `AndreasSteno`, `elerianm`, `OddStats` | First pulse for broad macro discussion |
| `us-macro-rates-1` | `ericwallerstein`, `biancoresearch`, `darioperkins`, `LizAnnSonders`, `conorsen`, `Claudia_Sahm`, `jasonfurman`, `M_C_Klein`, `TorstenSlok`, `krugermacro` | US macro, rates, labor, and policy |
| `us-macro-rates-2` | `ApolloAcademy`, `JosephPolitano`, `CalculatedRisk`, `TheStalwart`, `tracyalloway`, `CardiffGarcia`, `greg_ip`, `Neil_Irwin`, `nicktimiraos`, `SteveMiran` | Data, policy reporting, and reaction function |
| `us-macro-rates-3` | `josephwang`, `JeffSnider_AIP`, `LukeGromen`, `RaoulGMI`, `TaviCosta`, `jsblokland`, `Frances_Donald`, `DonRissmiller`, `LizCapoMcCormick`, `Brian_Chappatta` | Plumbing, cross-asset, rates, and credit |
| `us-macro-rates-4` | `KrishnaGuha`, `EvercoreISI`, `INArteCarloDoss`, `JackFarley96`, `alaidi`, `Tyler_Neville_`, `qthomp`, `Fullcarry`, `TruthGundlach`, `AnnaEconomist` | Policy, PM, rates, and event interpretation |
| `us-macro-rates-5` | `tdarling1`, `RenMacLLC`, `kierangoodwin`, `DianeSwonk`, `fcastofthemonth`, `DannyDayan5`, `IrvingSwisher`, `GregDaco`, `sonalibasak`, `shortl2021`, `spomboy`, `Markzandi`, `kit_lowe` | Economists, advisers, positioning, and event synthesis |
| `macro-conditional` | `PolemicTMM`, `EffMktHype`, `KobeissiLetter` | Markets-only posts; use the stricter cautions below |
| `macro-specialists` | `SKundojjala`, `VolSignals` | Semiconductors or options/volatility only |
| `global-macro-fx` | `MacroAlf`, `GeorgeSaravelos`, `robin_j_brooks`, `donnelly_brent`, `JStanleyFX`, `ING_Economics`, `NordeaMarkets`, `DBForex`, `Commerzbank`, `Danske_Research` | FX, Europe, and global central banks |
| `credit-cross-asset` | `hussmanjp`, `junkbondinvest` | Valuation, high yield, distressed credit, CDS, and issuer structure |
| `commodities-energy` | `JeffCurrie`, `energyaspects`, `RystadEnergy`, `GavMcCracken` | Commodity and energy mechanisms |
| `macro-secondary` | `DavidInglesTV`, `markets`, `business`, `BloombergTV`, `FT`, `WSJ`, `Reuters`, `Economist`, `FTAlphaville`, `CNBC`, `oddlots`, `FirstSquawk` | Secondary reporting or chronology; never let relays alone define the read |

### Equity-markets participants

| Lane | Exact allowlisted handles | Conversation use |
|------|----------------------------|------------------|
| `equity-gold-multisector` | `TheValueist`, `bespokeinvest`, `JaguarAnalytics`, `KerrisdaleCap`, `CulperResearch`, `blueorcainvest`, `ResearchGrizzly`, `ScorpionFund`, `JehoshaphatRsch`, `muddywatersre`, `sprucepointcap`, `viceroyresearch`, `Bleecker__St`, `WolfpackReports` | High-density tape, long/short, forensic, and special-situations research |
| `equity-pm-strategy` | `GavinSBaker`, `munster_gene`, `mingchikuo`, `garyblack00`, `DanielTNiles`, `StockSavvyShay`, `SouthernValue95`, `citrini`, `RichLightShed` | PM, strategist, supply-chain, and TMT interpretation |
| `equity-estimates-fundamentals` | `sssjeffpu`, `p_ferragu`, `Stephanie_Link`, `TechFundies`, `RHouseResearch`, `jukan05`, `EconomyApp` | Estimates, print-versus-consensus, cash flow, leases, credit, and company fundamentals |
| `equity-options-structure` | `Yam_Trades`, `spotgamma`, `VolSignals` | Options, volatility, flow, and dealer-model mechanics |
| `equity-industry-news` | `firstadopter`, `DylanOnChips`, `dnystedt`, `SemiAnalysis_`, `fabknowledge`, `markgurman`, `PatrickMoorhead`, `danielnewmanUV`, `dougclinton`, `pequityresearch`, `Midnight_Captl`, `TheTranscript_` | Industry facts, product/supply-chain news, and attributable management language |

`VolSignals` intentionally appears in both macro-specialist and equity-options
lanes. It is one exact participant, not two independent sources.

## Post-level gates

Apply these to every returned node, including allowlisted authors:

1. Keep only macro, markets, or public-equity content with a concrete claim,
   mechanism, datum, calculation, correction, evidence addition, or substantive
   question.
2. Drop any post containing more than one `#hashtag` token.
3. Drop politics without a stated economic or market transmission mechanism;
   lifestyle, sports, personal beef, legal theater, crypto price chatter,
   ticker spam, cheerleading, trade solicitation, and generic vibes.
4. Drop paywall-only teasers, empty media promotion, and links without usable
   free-text analysis.
5. In a named-topic run, drop off-entity posts even when the author is listed.
6. Preserve disclosed long/short bias, vendor/model provenance, relayed
   reporting, and uncertainty. Do not synthesize a contested view as consensus
   from one camp or from secondary/industry lanes alone.

## Handle and lane cautions

| Handle or lane | Required caution |
|----------------|------------------|
| `PolemicTMM`, `EffMktHype` | Heavy mixed feeds; keep markets/macro posts only |
| `KobeissiLetter` | High-frequency newsy source; require an actual substantive exchange, not a headline relay |
| `RaoulGMI` | Keep only macro/market transmission; drop unrelated crypto promotion |
| `INArteCarloDoss` | Heavy politics; require concrete macro or market mechanism |
| `JackFarley96` | Drop podcast-only promotion; retain substantive free text |
| `SKundojjala` | Semiconductor research only |
| `VolSignals`, `Yam_Trades`, `spotgamma` | Label gamma, vanna, skew, walls, and dealer exposure as proprietary/vendor estimates; use for amplification mechanics, not fundamental direction |
| `junkbondinvest` | Verify irony or satire and chart-only marks; retain instrument-specific credit analysis |
| `macro-secondary` | Reporting and chronology are lower-weight; an allowlisted media root does not remove the two-node conversation requirement |
| `JaguarAnalytics` | Noisy feed; require a specific company catalyst or evidence-bearing market claim |
| `KerrisdaleCap`, `CulperResearch`, `blueorcainvest`, `ResearchGrizzly`, `ScorpionFund`, `JehoshaphatRsch`, `muddywatersre`, `sprucepointcap`, `viceroyresearch`, `Bleecker__St`, `WolfpackReports` | Label activist, forensic, long/short, or disclosed short bias; retain checkable math and claims, not legal or personal theater |
| `munster_gene`, `garyblack00`, `DanielTNiles`, `GavinSBaker`, `StockSavvyShay`, `Stephanie_Link` | Opinionated investor/strategist reads are not neutral consensus |
| `SouthernValue95` | Treat utilization, discount-rate, rental-price, and terminal assumptions as assumptions |
| `TechFundies`, `RHouseResearch` | Preserve modeling and publication bias; verify terminal screenshots, second-hand CDS marks, and decision-critical filings |
| `p_ferragu`, `danielnewmanUV` | Domain-gate personal or political noise |
| `EconomyApp`, `firstadopter` | Keep usable numbers or analysis; drop newsletter-only promotion and separate relayed reporting from interpretation |
| `equity-industry-news` | Establishes drivers and attributable language, not valuation or market consensus by itself |
| `TheTranscript_` | Use only for attributed management language; verify decision-critical numbers against company materials |

## Discovery priority

- **Named macro event or mechanism:** select only the relevant macro lanes, then
  add one opposing or specialist lane if it can change the read.
- **Named company, ticker, or sector:** start with the relevant EQ-A lane; add
  an EQ-B lane only for factual drivers or market-structure mechanics.
- **Open markets scan:** run one `macro-seed` pulse and one
  `equity-gold-multisector` or `equity-pm-strategy` pulse, then deepen only
  exact conversations that already contain substantive linked participation.
- Never exhaustively scan the entire registry merely because it is loaded.

## Maintenance

- Prefer an explicit, curated snapshot over dynamic expansion.
- A handle named by the user for one run is a labeled temporary exception.
- Change this file only when the user asks to persist an addition, removal,
  correction, or deliberate resync from `/macro`.
- When a handle appears renamed or empty, use one `x_user_search` to diagnose
  the current run and report the gap. Do not silently rewrite the allowlist.
