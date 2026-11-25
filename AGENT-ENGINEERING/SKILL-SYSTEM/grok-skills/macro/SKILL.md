---
name: macro
description: >
  High-signal X-only macro and equity briefing for /macro or questions about
  rates, FX, credit, central banks, data, broad equity tape, key stocks, semis,
  or AI infrastructure. Core claims are hard-filtered to curated analysts and
  desks. Participant-native equity runs may add a separately labeled weaker
  sample for mood, phrasing, and action. Supports adaptive or user-fixed
  windows. Requires Grok Build native X tools. Direct runs return chat plus a
  durable X-RESULTS/MACRO note; delegated xgrok workers return only an evidence
  packet and do not archive.
metadata:
  short-description: "Allowlist-core macro/equity X brief + labeled sentiment sample"
---

# /macro

You are running the **macro** skill. Produce a **high-signal macro/equity
markets briefing** from X. Keep the claim backbone hard-filtered to credible
desk/analyst sources; when the product is participant-native, add a clearly
separate sentiment sample rather than weakening the core filter.

**Two outputs by default:**

1. **Chat brief** - compact desk read (chat template), or the bounded evidence
   packet requested when operating as a delegated worker.
2. **Durable archive** - request-shaped, auditable Markdown under
   `X-RESULTS/MACRO/` (Step 8). Opt out only if the user says chat-only / no
   file, or when the parent explicitly invoked this run as a retrieval worker.

This is a specialized fork of `/whathappened` for a domain with very low
signal-to-noise. Retail hype, meme finance, official dump accounts, and
anonymous engagement bait remain **out of scope** in every evidence role.
Follow this file top to bottom.

## Host requirement

You need these tools:

- `x_keyword_search`
- `x_semantic_search`
- `x_thread_fetch`
- `x_user_search`

If they are missing, **stop**. Tell the user this skill only works in Grok Build
(or another host with those X tools). Do not fake a macro brief from web search.

## Hard rules

1. **Two evidence roles; one credibility hard filter.** Synthesize factual
   claims, mechanisms, company conclusions, informed disagreement, and claims
   about professional consensus, prevalence, or breadth **only** from posts by
   the active macro/equity allowlists. Use EQ-A/EQ-B for the core equity read;
   a macro-only handle does not qualify because it tweeted a ticker. When
   participant wording, mood, action, or equity temperature matters, load
   `references/equity-sentiment-panel.md`. It alone defines the weaker labeled
   sentiment-sample and context-only roles. Neither can establish a core claim
   or market-wide prevalence. Popularity never creates eligibility.
2. **Post-level noise filters (even for allowlisted authors).**
   - **Hashtag / quality:** do **not** drop an allowlisted post solely for
     more than one `#hashtag`. Keep usable desk/research prose even with
     boilerplate topic tags. Drop only if the post also devolves into low
     quality (tag soup, promo, engagement farming). Full rule in
     `credible-sources.md`. Non-allowlist noise with 2+ hashtags stays out of
     core. In equity mode, apply that same hashtag/quality rule plus the
     equity file’s paywall-bait, cheerleading, and domain-gate table.
   - **On-topic only:** for handles marked that way (e.g. `@PolemicTMM`,
     `@EffMktHype`, `@VKMacro`, `@dsquareddigest`, `@RobinWigg`), keep only
     posts clearly about markets/macro; discard the rest.
   - **Industry specialists:** for handles in that section (e.g. `@SKundojjala`),
     keep only in-domain research-grade posts; higher bar; do not let them
     dominate broad discovery.
   - **EQ-B / forensic bias:** EQ-B supplies market mechanics or factual drivers
     only - never alone define a contested stock read if EQ-A is silent or
     split. Label options/vendor models as estimates. Forensic/activist shorts
     are one-sided; label interest when synthesizing.
3. **X-first synthesis and task fit.** Claims about markets and consensus come
   from X tool results on allowlisted voices. Never invent posts, handles,
   quotes, or levels. When the user asks for sentiment, participant
   observations, or live debate, let the tape, attributed voices, and material
   revisions carry the narrative; factual checks qualify that read rather than
   replacing it with an analyst-owned framework. An explicit research or
   decision memo may instead lead with adjudication. Do not manufacture camps,
   conversations, or source counts when the sample does not support them.
   An explicit **participant-native** orientation applies when the request names
   it or makes participant wording, complete posts, replies, and conversational
   texture central to the product. Preserve exact signal-bearing language. For
   equity Temperature, apply the Delta/Temperature, source-role, and recurrence
   contract in `equity-sentiment-panel.md`; do not improvise a looser off-list
   path.
   Neutrality governs the synthesis; it does not require flattening or
   sanitizing the selected verbatim language.
4. **Soft web exception.** At most **one** web lookup (`web_search` or
   `web_fetch`) **only** to resolve a data release name, calendar event, or
   official series identity. Do not use web for "what traders think." If used,
   note it in Gaps.
5. **Discovery is allowed.** Unlike `/whathappened`, topic may be omitted.
   Empty `/macro` or "what's happening in macro" means: scan allowlisted
   accounts in the committed window and cluster what they are discussing.
6. **Time window is first-class.**
   - If the user specifies a window (`past 6h`, `last 3 days`, `since Friday`,
     `past week`), **honor it exactly**.
   - If not specified, use the adaptive pulse (below). State the window clearly.
   - Keep the working window and output in Pacific time (PST/PDT as applicable).
     Grok-native `x_keyword_search` supports exact timestamped Pacific
     `since:`/`until:` bounds; use `_PDT` or `_PST` as applicable. Use
     `within_time:Nh` for a simple trailing window. Convert to RFC 3339 UTC only
     for API `start_time`/`end_time` parameters that require it.
   - Reuse the same bound across core and sentiment lanes. Slice a busy native
     Latest interval into 60-90 minute Pacific windows; on other search
     surfaces, use their supported bounds and validate returned timestamps.
7. **Neutral desk-analyst tone.** No hype, no "market is melting," no cheerleading
   a camp. Report levels and claims as attributed, not as your forecast.
8. **Opinion is not market truth.** Frame consensus as "among these credible
   accounts in this window," not as ground truth or a trade recommendation.
9. **Citations.** Prefer `@handle` plus post links when available. Use the
   host's inline post citation render when you have post citation IDs. Never
   invent URLs. Select receipts; do not dump noise. In ordinary mode, keep only
   load-bearing receipts. In participant-native orientation, do not let a fixed
   receipt cap suppress distinct high-signal posts or replies; quote density
   follows the requested product and the evidence. When a distinct **Notable
   posts / receipts** block is warranted, reproduce selected short posts there
   verbatim when their phrasing carries sentiment, including seemingly
   throw-away comments. For posts roughly over 250 words, multi-name research
   notes, transcript read-throughs, or list-like threads, summarize and link;
   quote only wording whose phrasing carries signal. One long post cannot
   satisfy source or participant-language diversity. A separate receipt
   block is optional in compact chat. Inline
   attribution plus a real post link or ID is sufficient when it makes the
   load-bearing claim auditable without repeating it.
10. **No trade advice.** Do not recommend positions. Describe what sources claim.
11. **Supplementary lists are not the allowlist.** Two broad markets lists may be
    checked late for blind spots under `references/supplementary-lists.md`.
    Allowlisted hits keep their normal role; registered panel hits keep only
    their panel role; all others are re-query leads or isolated context. A list
    never establishes core claims or aggregate sentiment.
12. **Durable archive by default; delegated workers do not archive.** After
    synthesis, write a timestamped note under `X-RESULTS/MACRO/` unless the
    user explicitly opts out (`chat only`, `no file`, `don't save`, `skip
    archive`) **or** the request identifies this run as an xgrok/Grok retrieval
    worker. A delegated worker returns its evidence packet only; a normal direct
    `/macro` run still produces chat plus archive.
13. **Roots before replies.** Discover broadly, shortlist only 2–5 load-bearing
    roots, then fully enrich the best 2–3 under a normal budget. These are
    triage heuristics, not global caps for an explicit participant-native or
    conversation-rich request. Enrich additional roots only when each adds
    distinct language, participant positioning, or a material conversation
    edge. Do not read every reply tree. Use `query-patterns.md` for core-node
    promotion and `equity-sentiment-panel.md` for the participant-native
    social/emotional extension.
14. **Keep prevalence separate from evidence weight.** Engagement and repeated
    phrasing can indicate visibility or recurrence in a labeled sample; they do
    not make a claim more credible or justify market-wide prevalence. Deduplicate
    relays, self-threads, and conversation clusters before counting recurrence.
    A quiet, allowlisted correction may outweigh a popular root. Preserve the
    root/reply edge and source independence.
15. **Individual trader trajectories are anecdotal.** The active-trader overlay
    answers only how one author's stated stance or self-reported book changed.
    Preserve timestamps and label intention, order, claimed fill, holding,
    hedge, add, trim, exit, or flat without inference. Require an earlier state
    plus a later update before claiming a change. Never count repeated posts by
    one author as breadth, verified performance, or market-wide positioning.
16. **External agenda anchors stay role-separated.** When a parent supplies a
    potentially material factual development, treat it as a bounded research
    anchor rather than a market claim Grok must prove. Search X separately for
    attributed reporting receipts, participant uptake, proposed transmission,
    and counterchannels. Do not promote reporters into the strategist allowlist,
    infer that X silence makes the development irrelevant, or edit a parent
    state document. Follow `references/external-development-transmission.md`.

## Reference routing - load only the matching row

| Condition | Load |
|---|---|
| Every run | Only the operator/window section and relevant lane recipe in `query-patterns.md`; do not preload the whole reference |
| Macro lane selected | `credible-sources.md` |
| Any equity/company read | `credible-equity-sources.md` + `equity-retrieval.md`; macro allowlist alone is insufficient |
| Equity Temperature, participant wording, or first-person action | Add `equity-sentiment-panel.md`; it is the single runtime authority for the extension |
| Parent supplies an external factual development or factual-agenda anchor | Add `external-development-transmission.md`; use its separate reporting, uptake, transmission, and counterchannel roles |
| Supplementary-list lane actually used | `supplementary-lists.md` |
| `from:` returns empty or an unexpected author | `roster.tsv` (registry membership and last verified date) plus the Handle verification rule in the loaded registry |
| Sample becomes thin, mixed, or noisy | Relevant section of `failure-modes.md` |
| Full-depth product selected | `full-depth-output.md` at Step 7 |
| Skill revision or historical regression only | `evaluation.md`; never during an ordinary brief |

Do not preload conditional references.

## Delegated evidence-packet contract

When an xgrok or other parent agent invokes `/macro` as a retrieval worker,
follow the parent's packet schema and keep evidence roles separate. Unless the
parent expands the budget, return at most six promoted receipts and 1,500
words in one dense table, plus only the material coverage boundary, unresolved
gap, and a one-line overflow list of other qualifying IDs. A brief's
`Delegated budget:` line (for example "Delegated budget: the parent expands
the /macro default to 30 receipts / 5,000 words") replaces that default; honor
its receipt and word allowances and any relaxed concentration gate it states.
Preserve exact text only where wording is evidence. The participant-native
field contract and compact return shape live in `equity-sentiment-panel.md`.
Do not write an archive, narrative report, search diary, or recommendations.

For a chart-aware brief, retain up to three additional **unread visual
candidates** within the assigned receipt/word allowances and call ceiling.
Use normal receipts with actual Author, Posted, Post ID, URL, exact returned
caption and their own `- Media:` field, not bare IDs buried in overflow prose.
Terse captions or text-complete posts can warrant attachment inspection based
on source domain and returned context; unknown image subject stays unknown.
Label the visual content unread, state that context-supported reason, and
infer no image contents or numbers. `image-carried` still means the text
defers to the image, not attachment presence. Never fill slots with noise or
promote an unread chart into a core claim or a trader action.

Registry membership is provenance, not a verdict. Label every returned item
`allowlist`, `panel`, or `off-list` (plus `parent roster` when the parent named
the handle) and leave evidence weight to the parent: do not drop, discount, or
caveat an item because it is off-list, and do not write that an off-list post
"does not confirm" a claim. Query every handle the parent's roster names,
whether or not a registry contains it; report `not queried` only for handles
the budget prevented you from reaching. The hard-filter rules above govern a
direct run's synthesis, which a worker does not perform.

For a supplied external-development anchor, include these compact fields:
`agenda anchor | reporting receipt | participant uptake | transmission channel
| horizon | interaction candidate | counterevidence`. Mark the anchor as
parent-supplied, keep `not found` as a valid uptake result, and make no durable
state write. Inside `participant uptake`, separate attention (`present`,
`partial`, or `not found`) from interpretation (`shared`, `disputed`, `unclear`,
or `not applicable`); keep action and pricing in their own packet detail.

## Pipeline

### Step 0 - Parse intent and window

Choose named-topic or discovery mode, then commit the window before deep
search. Preserve sentiment, positioning, or participant-language terms as the
synthesis focus even when stripping them from entity queries.

Classify the requested read as **Delta**, **Temperature**, **Transmission**, or
a combination. Delta asks what changed. Temperature asks what participants now
say easily, repeatedly, defensively, jokingly, reluctantly, or with little need
to justify themselves. Transmission asks how a supplied factual development
could enter real economic or market variables and whether sampled discourse
has absorbed that mechanism. Novelty, prevalence, and transmission value are
separate axes.

| User said | Commit |
|-----------|--------|
| `past Nh` / `last N hours` | exact trailing N hours via `within_time:Nh`, or a computed Grok-native timestamped Pacific bound when fixed endpoints matter |
| `past Nd` / `last N days` / `past week` | Pacific calendar window; use Grok-native timestamped Pacific bounds for exact endpoints or date-granular bounds when sufficient |
| `since {date/day}` | that lower bound |
| nothing | adaptive pulse (Step 3) |

Classify loosely: data-print | central-bank | rates/FX | credit | growth/labor |
external-development | **equities-tech / Mag 7 / special sits** | person/desk |
discovery. An external development can originate in any domain; this label is
a routing instruction, not a domain taxonomy.

Turn on equity mode when the request names equities, sectors, tickers, or
company theses, or discovery lands on stock/tape sentiment. Load the equity
source and retrieval references in Step 2. Turn on the separate equity
sentiment sample when Temperature, participant language, or first-person action
is requested.

### Step 1 - Optional entity web lookup (0 or 1 call)

Only if a print or event identity is ambiguous, use at most one web lookup for
its official name, scheduled date, and aliases. Skip when the topic is clear.

### Step 2 - Load credibility set

For a macro lane, open `references/credible-sources.md`: Tier A supplies core
macro interpretation; Tier B supplies secondary reporting color. For an equity
lane, open `references/credible-equity-sources.md` and
`references/equity-retrieval.md`: EQ-A supplies contested company/tape
interpretation; EQ-B supplies mechanics, industry, product, and
primary-language drivers. Load only the relevant executable recipe from
`references/query-patterns.md`. For a participant-native equity run, also open
`references/equity-sentiment-panel.md` and initialize three separate
collections: core evidence, sentiment sample, and context/discovery only.

When the parent supplies a factual-agenda anchor, also load
`references/external-development-transmission.md`. Preserve the parent's
source and wording as the premise boundary. Reporting accounts recovered on X
may document or relay the event only in the separate reporting-anchor role;
they do not become macro strategists or establish participant consensus.

`references/roster.tsv` indexes every registered handle with its registry
section and last verified date. Parents build brief rosters from it and a
monthly single-handle probe refreshes it; it records who is registered, not
how to weigh them, and the registries above remain the rules source.

Never promote a non-list account into the synthesis core because it has high likes.
Do not search official institutional accounts (Fed, BLS, ECB, Treasury feeds, etc.).
Do not promote a macro-only handle into equity synthesis because it once posted
a ticker. Overlap counts only when the handle is on both lists.

If a user **names** a specific handle not on the list, you may include that
handle as a **scoped exception for this run only**, and label it
`user-requested (not on allowlist)` in Gaps. Do not silently expand the list.

### Step 3 - Pulse (always first unless user fixed a short window)

Run a **cheap Latest** sample with a short window to measure velocity.

- **Macro mode:** Tier A macro batch
- **Equity mode:** EQ-A gold/PM recipe from `query-patterns.md` (optionally one
  forensic batch for special sits); do not pulse only macro Tier A for NVDA tape
- **Participant-native equity mode:** add the separately labeled broad
  tape/action sentiment-panel pulse under the same exact window
- Breaking candidate: last few hours / today
- If almost empty: widen once (2 days, then ~7 days) before committing

**Commit a mode and window:**

| Pulse signal | Mode | Default window |
|--------------|------|----------------|
| Live data dump / CB decision / sharp market move chatter | Breaking | last 1–6 hours |
| Same-day print, speech, or auction | Same-day | last 24–48 hours |
| Multi-day debate (soft landing, term premium, etc.) | Story | last 3–7 days |
| Sparse, mostly structural commentary | Background | last 14–30 days; still prefer recent posts |

If the **user fixed** the window, skip mode inference for the bound: use their
window, still label mode by content density (Breaking vs Story, etc.).

State **Window**, **Mode**, and **Filter: core allowlist + post filters** in the
brief; when a sentiment sample or context-only post is used, label each separate
evidence role too.

Expand later only if:

- No agreement on the factual trigger (print / decision / move)
- Debates point at an origin post outside the window - then fetch that origin

### Step 4 - Search lattice (parallel, role-separated, core-first)

Cap total X tool calls roughly **10–14** for a normal run. Reserve **4–6**
calls to fully enrich the best **2–3** selected conversations; list checks come from the same
budget. Stop broad discovery once the major themes and candidate roots are
stable. For an explicit participant-native or conversation-rich request, this
is a starting budget rather than a cap; spend additional calls only to recover
distinct high-signal phrasing or material conversation edges.

For a broad combined macro-and-equity sentiment request, first complete one
coherent pass across the relevant macro Tier A and equity EQ-A sleeves under
the same committed window. Cluster that shared sample before splitting into
ticker-, factor-, or thesis-specific searches so cross-asset links and the
conversations carrying the tape remain visible. Skip unrelated sleeves when
the request is narrow. `references/equity-retrieval.md` owns the core equity
allocation and company lanes. When participant-native equity is active, run
the complete extension in `references/equity-sentiment-panel.md`; it owns the
extra temperature/action/texture lanes, queries, ledger, and concentration
gates. One author, mega-thread, conversation, or copied relay is one voice.

| Lane | Tool | Goal |
|------|------|------|
| Allowlist Latest | `x_keyword_search` mode=`Latest` | Fresh desk flow |
| Allowlist Top | `x_keyword_search` mode=`Top` | High-engagement among credible |
| Topic + allowlist | keyword with entity + `from:` batches | On-topic signal |
| Semantic (constrained) | `x_semantic_search` + matching bounds | Paraphrase capture; route each survivor to its eligible role |
| Debate | opposing claims **from allowlisted** accounts | Disagreement surface |
| Anchor reporting receipt | native actors/event terms under the exact window | Attributed X receipt for a parent-supplied development; never consensus |
| Anchor uptake | anchor vocabulary across eligible participant roles | Whether and how sampled participants absorbed the development |
| Anchor transmission | active allowlists + anchor-specific mechanism terms | Proposed real-variable and market channels |
| Anchor counterchannel | active allowlists + disconfirming/offsetting anchor terms | Alternative mechanism, limiting condition, or silence boundary |
| Trader trajectory overlay | `x_keyword_search` Latest + same-author origin/update recovery | Anecdotal stance or position change; never consensus/performance |
| Supplementary lists | `x_keyword_search` mode=`Latest` + `list:{id}` | Blind-spot / theme check only (max 1–2 calls) |

**Critical:** assign the evidence role before ranking. From every **core
allowlist** search, drop:

1. Authors not on the **active** allowlist (macro and/or equity; unless
   user-requested exception)
2. Allowlisted posts that fail the hashtag/**quality** gate in
   `credible-sources.md` (hashtag count alone is not a drop). Equity mode:
   same hashtag/quality gate plus equity-file paywall bait, cheerleading,
   media promo
3. Off-topic posts from **on-topic only** handles (e.g. `@PolemicTMM`, `@EffMktHype`, `@VKMacro`, `@dsquareddigest`, `@RobinWigg`)
4. Off-domain or low-grade posts from **industry specialists** (e.g. `@SKundojjala`)
   and from **EQ-B** when they are not in-domain mechanics or drivers for the sleeve
5. Off-entity posts in topic mode
6. Equity mode: pure macro noise unless it clearly drives the named equity tape

For the participant-native extension, apply the routing and filters in
`equity-sentiment-panel.md` as written. Semantic and Top lanes will return
noise; filter and role-label before synthesis.

Keep visual discovery separate from claim promotion: a caption-poor attachment
by an eligible, in-domain chart source may survive as an unread inspection
lead even when it cannot supply a usable free-text claim. This does not relax
source eligibility, topic/window bounds, promotional/paywall exclusions or
chart-only trajectory/action bans. Use attachments already returned by the
lane first; a narrowly justified missing source-family probe uses the existing
bounded author-only Latest recipe and call budget, not a new standing lane.

Batch `from:` queries per `references/query-patterns.md` (macro **and** equity
recipes). Always keep the primary entity in topic mode. In discovery mode, pure
allowlist `from:` batches in-window are the core; if clusters are equity-heavy,
switch remaining lattice to equity batches.

#### Step 4b - Supplementary list check (after allowlist core)

Run only after allowlist themes are stable and only if budget permits. Load
`references/supplementary-lists.md` and use its filtered NBTQ/InvQ root
recipes; never run bare list Latest. Merge allowlisted authors into the core.
A registered panel hit may enter only its labeled sentiment role after the
post gate. Another high-substance non-list hit may trigger an allowlist re-query
or become isolated labeled context after dependency recovery. It never
establishes facts, company conclusions, professional consensus, or market-wide
prevalence. Skip the lane when the allowlist and sentiment samples are already
rich for the requested product.

### Step 5 - Select roots, then enrich conversations

Shortlist **2–5 load-bearing roots** and normally enrich the best **2–3**;
expand only for distinct participant language or a material conversation edge.
Prioritize the level-set, strongest informed disagreement, likely correction,
and any specialist driver that changes an active sleeve.

For each selected root, run `x_thread_fetch` plus a floor-free
`conversation_id:{root_id}` Latest search. Add self-thread, time-slice, or one
precision-floor comparison only when needed; use `to:{author} filter:replies`
as a last resort and require the exact conversation id. A root is enriched only
after the first two calls. Follow the full ladder in `query-patterns.md`.

Classify and record core nodes with the contract in `query-patterns.md`. When
the participant-native extension is active, use its expanded social/emotional
classes and field schema in `equity-sentiment-panel.md`. Drop empty praise,
empty dunks, context-free slogans, and duplicates, but not a small node merely
because its signal is social. Off-list replies never enter the core read.

### Step 6 - Rank and cluster

Rank on separate axes: source role/tier, relevance, claim/mechanism specificity,
evidence quality and independence, **Delta value**, **Temperature value**,
**Transmission value**, **interaction value**, paraphrase loss, and freshness.
Rank within evidence roles before comparing across them: a panel post may carry
better wording without acquiring core factual weight, and a reporting receipt
may document an agenda anchor without becoming participant interpretation.
Treat engagement only as a discovery/visibility clue.

Merge duplicate claims and tag the market sleeve, but retain deduplicated
recurrence when repetition is itself a temperature signal. Discard engagement
bait, low-quality tag-soup/promo posts, off-domain or off-entity content,
paywall-only teasers, cheerleading, and unfiltered list reply spam. Do not
discard an allowlisted analysis post for hashtag count alone. Keep prevalence
separate from evidence weight.

In equity mode, build the core delta ledger in `equity-retrieval.md`. When the
participant-native extension is active, build and gate its separate sentiment
ledger in `equity-sentiment-panel.md`. Index commentary or generic AI capex does
not satisfy a company row.

### Step 7 - Synthesize

Set the narrative center from the requested product and the filtered sample. A
sentiment or "what are credible voices saying?" brief should foreground the
observed tape, attributed participant views, and material revisions. An
explicit research-adjudication or decision memo may foreground analytical
judgment, but must keep any material participant signal distinguishable. Do not
default a sentiment summary into a state machine or risk-governance memo merely
because deeper verification was also performed.

When both reads are requested, synthesize the Step 0 Delta and Temperature in
parallel. For a full participant-native equity product, surface Tape temperature
and dynamic key-stock conversations immediately after the bottom line/Delta
table, not only in a late asides section. Keep evidence roles clear without
turning the output into a methodology audit.

When Transmission is requested, state only mechanism-supported connections.
Use the chain `development -> real variable or common bottleneck -> market
transmission -> affected assets and horizon`, test at least one counterchannel,
and return `no supported connection` when the shared mechanism is missing.
Keep parent-supplied fact, X reporting receipt, participant interpretation, and
observed pricing distinct. Participant silence is a result, not a veto on the
factual agenda.

Requested granularity wins. For a concise brief or summary, compress the result
to the load-bearing tape, attributed observations, and material conversation
changes. Omit redundant analytical sections and receipts rather than reproducing
archive breadth in chat; there is no section or receipt minimum.

Choose the **Compact summary path** or **Full-depth chat scaffold** below before
drafting. If the user says concise, brief, summary, quick, or equivalent, use the
compact path unless they also request full tables, methodology, or receipts. Do
not select the full-depth scaffold merely because the retrieval found abundant
material.

If either evidence role is thin after filtering, say which one. Prefer honest
isolated observations over fake consensus. Never pad the primary read or
receipts with non-allowlist list noise. If list check added nothing, omit
**List check** or use one line: "no additive signal after filters."

When a trader trajectory is material, present it chronologically and keep the
state labels explicit. Call it self-reported when discussing execution, size, or
book state; do not publish claimed returns as validated performance or let the
trajectory stand in for market consensus.

Then proceed to **Step 8** unless the user opted out or this is a delegated
retrieval-worker run.

### Step 8 - Durable archive note (default on)

Write a request-shaped Markdown archive under `X-RESULTS/MACRO/` unless the
user says chat-only/no-file/skip-archive. **Do not write any archive when the
parent invoked this run as an xgrok/Grok retrieval worker; return only the
requested evidence packet.** Honor a user-named directory in a normal direct
run. A Delta ask adds continuity/discontinuity treatment, and a Temperature ask
adds the labeled tape/name sentiment read, without forcing chat to the same
depth.

#### Path and filename

Prefer the workspace-relative directory when the workspace already contains
`X-RESULTS/`; otherwise use the expanded home path. Create the directory if
needed. Name files `{YYYY-MM-DD_HHMMPDT}_{short-kebab-slug}.md` or
`{YYYY-MM-DD_HHMMPST}_{short-kebab-slug}.md`, as applicable, using Pacific
local time. Use `markets-scan` for discovery and a topic/delta slug otherwise.
Never overwrite; append `-2`, `-3`, and so on after a collision.

#### Archive vs chat

The archive inherits the requested product and granularity; durable does not
mean exhaustive. Apply the same filters as chat and include only enough method,
IDs, and source detail for its load-bearing claims to be auditable. End with
Document metadata (path, stamp, ask, not-advice), and state the relative archive
path in chat.

## Compact summary path

For a concise brief, summary, scan, or quick sentiment read, do not instantiate
the full-depth scaffold. Lead with the tape and sampled sentiment; when useful,
give Delta and Temperature one compact paragraph each. Keep window, evidence
roles, material coverage boundary, and archive status compact. Attribute
load-bearing observations inline and integrate only disagreements, revisions,
or conversations that change the read or materially reveal its temperature.
Omit a conversation section when no additive claim or sentiment node survives,
and keep only the receipts needed for auditability. A thin sample should make
the answer shorter.

## Compact finalization gate

Treat the retrieval packet as private working material. Identify the
observations, disagreements, revisions, and conversation edges that could
change the participant-native Delta **or** materially reveal Temperature;
delete everything else, then recompose from the survivors. An unchanged but
recurrent or unusually casual phrase can survive this gate. Do not repeat
evidence across an observation list, disagreement table, and receipt block
unless each rendering adds needed information. Surface funnel or gap detail
only when it changes the inference. If the result still reads as a search
catalog, repeat the deletion pass.

## Compact archive path

When the requested product is a concise brief or summary, archive the compact
synthesis rather than loading the full-depth reference. Add only the
methodology, IDs, receipt text, and metadata needed to make its load-bearing
claims auditable. A compact archive may be longer than chat, but it must
preserve the same narrative center and pass the same deletion test.

## Full-depth output paths

Only after selecting a deep, detailed, comprehensive, audit-style, or
decision-oriented chat response or archive, read
`references/full-depth-output.md` and use the relevant scaffold.
Do not load the full-depth reference for a compact product. Requested product,
evidence shape, and granularity still override the scaffold.

### Formatting notes

- Use plain hyphens `-`, not em dashes.
- Neutral wording: "several allowlisted strategists argue", not "everyone knows".
- Use rough camp shares only when the sample supports discrete camps, and label
  them as sample judgment.
- If evidence is thin, distinguish a thin core read from a thin sentiment
  sample. Shrink aggregate claims, preserve any genuinely telling isolated
  observation with that label, and state the concrete boundary.
- Keep internal coverage, evidence-weight, and confidence judgments private.
  Never render a reader-facing **Confidence** column or categorical grade;
  state a concrete boundary next to the affected claim instead.
- List check is optional and subordinate - never the bulk of the brief.
- In a Notable posts block, reproduce complete short posts when wording carries
  signal and label non-core roles. Summarize long research dumps and quote only
  their signal-bearing language.
- Chat: end after Gaps unless the user asked for follow-ups (archive may still
  include Suggested follow-ups).
- Always state archive path in chat when a file was written.

## Pre-flight checklist (before first tool call)

- [ ] X tools available; exact shared window, Delta/Temperature/Transmission read, and topic/discovery mode committed or pulse planned
- [ ] Active allowlist, executable recipes, and post filters loaded
- [ ] Equity mode: source roster plus `equity-retrieval.md` loaded; roughly 60% equity allocation (about half of first-wave calls on company questions), a pulse across most of the supplied baseline, and required lanes planned
- [ ] Participant-native equity mode: `equity-sentiment-panel.md` loaded; core,
      sentiment, and context collections separated before retrieval
- [ ] If relevant, trajectory overlay has same-author origin/update recovery
- [ ] List lane will use filtered NBTQ/InvQ recipe or be skipped
- [ ] Reserve 4–6 calls to enrich the best 2–3 roots; web budget is 0 or 1 resolve-only
- [ ] Direct run archives with a Pacific filename by default; delegated worker returns an evidence packet only
- [ ] Delegated worker: the brief's `Delegated budget:` line read; every parent-named handle will be queried; role labels will be provenance only
- [ ] External anchor, if supplied, has parent source, native actors/event vocabulary, applicable state slice, and separate reporting/uptake/transmission/counterchannel lanes

## Post-synthesis checklist (before send)

- [ ] Product, narrative center, and granularity preserved; no scaffold padding
- [ ] Window, mode, active allowlist, sentiment/context roles, and any filtered/skipped list check stated
- [ ] Delta and Temperature were both retained when requested; unchanged but
      recurrent/casual language was not discarded merely for lacking novelty
- [ ] Transmission request, if present, keeps premise, uptake, mechanism,
      counterchannel, pricing, and horizon separate; X silence is labeled rather
      than used to erase the anchor
- [ ] Funnel reconciled internally; enriched roots passed both required fetches
- [ ] Promoted replies retain IDs, URLs, relationship, source role, signal type,
      independence, sentiment/action state, and paraphrase-loss reason
- [ ] Prevalence remains separate from evidence weight; every quote is attributable
- [ ] Short signal-bearing posts are complete; long research dumps are summarized
- [ ] Post, domain, topic, and retail-noise filters passed
- [ ] Equity mode: required families attempted, both ledgers built, core and
      sentiment concentration checked, EQ-A anchors contested reads, and
      forensic bias labeled
- [ ] Trajectories have origin plus update and make no execution, P&L, or breadth inference
- [ ] No web-derived sentiment or trade recommendations
- [ ] Material gaps state consequential filter/sample limits, not search-log trivia
- [ ] Direct-run archive written (or opt-out honored), auditable, and linked;
      delegated worker created no archive or full memo and applied no
      off-list discount to parent-named evidence
- [ ] Delegated worker made no current-state write
