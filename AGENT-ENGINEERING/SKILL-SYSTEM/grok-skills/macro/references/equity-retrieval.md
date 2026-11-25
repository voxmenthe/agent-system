# Equity retrieval for /macro

Use this reference for a broad macro-and-equity update, an equity sentiment
scan, or any request that needs company-level conclusions. It governs coverage
and synthesis mechanics; core source roles live in
`credible-equity-sources.md`, sentiment roles live in
`equity-sentiment-panel.md`, and executable searches live in
`query-patterns.md`.

## Contents

- [Activation and coverage contract](#activation-and-coverage-contract)
- [First-wave lane matrix](#first-wave-lane-matrix)
- [Build a dynamic name map](#build-a-dynamic-name-map)
- [Pulse the companies, then deepen](#pulse-the-companies-then-deepen)
- [Route by source family](#route-by-source-family)
- [Recover a thin or crowded-out family](#recover-a-thin-or-crowded-out-family)
- [Build the equity delta ledger](#build-the-equity-delta-ledger)
- [Apply concentration and quotation gates](#apply-concentration-and-quotation-gates)
- [Stop and completion rules](#stop-and-completion-rules)

## Activation and coverage contract

Turn on equity mode when the user names equities, sectors, or tickers, or when
discovery clusters land on stock, tape, or company sentiment. Load both
`credible-equity-sources.md` and `query-patterns.md` before searching. If the
ask includes participant wording, mood, action, or market temperature, also
load `equity-sentiment-panel.md` and keep its evidence separate from EQ-A/EQ-B.

For a balanced macro-and-equity request, devote roughly **60% of first-wave
retrieval to equity lanes**, and count **company-directed** retrieval separately
from broad tape, breadth and options reconstruction: roughly half of all
first-wave calls go to company questions. A narrower or macro-dominant event
can justify another split; record the reason. Treat both as retrieval
allocations, not output quotas. A thin but honestly attempted lane may
disappear from the report; a rich lane may deserve more space.

Index commentary, breadth, or a general AI-capex thesis does not satisfy
company-level coverage. Neither do several names extracted from one author's
mega-thread. The retrieval must separately test which named companies benefit,
which pay, which face estimate or multiple risk, and how the view is being
expressed.

## First-wave lane matrix

Attempt each applicable lane separately before narrowing. Skip a lane only
when the request is genuinely narrower, and record that choice internally.

| Lane | Required attempt | Evidence sought |
|---|---|---|
| Broad tape | Breadth, factor, rotation, earnings reaction | What is leading, lagging, or changing beneath the index |
| Hyperscalers | Currently material cloud/platform names | Capex, utilization, monetization, cash conversion, concentration, or multiple read-through |
| Semis and supply chain | Currently material compute, memory, networking, equipment, and component names | Estimate revisions, bottlenecks, pricing, share shifts, inventory, or relative winners/losers |
| Non-tech | At least two material company or sector lanes chosen from the live agenda | Company-specific catalyst and sector read-through outside technology |
| Trade expression | Position change, relative-value expression, options/flow mechanic, or explicit risk boundary | How belief is being traded or hedged, without converting it into advice |
| Participant-native extension | Run the separate workflow in `equity-sentiment-panel.md` | Temperature, first-person action, replies/quotes, and blind texture harvests |

Do not count repeated variants of the same search as separate lanes. Do not
let a single prolific author satisfy multiple source families without an
independent check.

## Build a dynamic name map

Build the map before the company briefs are final, from four inputs:

1. **Standing baseline:** most of the approximate Nasdaq-100 top 20 the parent
   supplies as a dated snapshot (share classes are one company), not only the
   names with a fresh headline or a place in the last report;
2. **Continuity names:** open episodes and unresolved disagreements from recent
   reports, and long-lived reader interests such as NVIDIA;
3. **Event names:** earnings, filings, price outliers, deal and news
   developments, and their counterparties; and
4. **Discovery names:** company discussion returned by independent source
   families or repeatedly raised by independent allowlisted participants,
   including names outside mega-cap technology.

The baseline is a starting universe, not an exclusion list or a count to hit.
News and investor focus justify departures, and a non-Nasdaq or non-tech name
enters whenever it is material. A current catalyst or belief change decides
which names get deeper work and report space, not whether a baseline or
continuity name gets its pulse search.

A name that recurs only in the sentiment sample may enter the working map as a
search lead, but it still needs a core-source query before it can support a
company conclusion.

## Pulse the companies, then deepen

Separate **breadth** from **depth**. First give most baseline names, and the
day's other material names, a fresh ticker or company-name search in small
batches with no required topic vocabulary (the company pulse in
`query-patterns.md`). This tests what people are actually discussing; a
required capex or earnings word hides the conversation that is not about
capex or earnings. A handle-only feed, the prior report, local history or
index commentary is not a pulse search for the names it mentions. Pulse
returns are leads under the normal source gates: label off-list posts as
context and drop ticker spray rather than counting it.

Then deepen the names with the strongest current discussion, disagreement,
action or unresolved episode, normally two to four per lane. For each, write
one retrieval question that could change the prior frame, the two source
families most likely to answer it, and the check still missing. Examples:
whether capex is now being treated as revenue visibility or a cash-flow
penalty; whether a semi bottleneck is moving upstream or downstream; whether a
non-tech print changes a sector multiple rather than only the stock. A
searched name with no new discussion earns no paragraph.

An indirect product, executive or project mention needs an adjudicated
relationship before it counts for a company. A B200 rental-price post is a
GPU-economics read-through for NVIDIA, not NVIDIA revenue, orders or equity
conviction; a post about Zuck or Muse counts for META only once its META
referent is recovered.

Record each mapped name's coverage as **searched**, **capped**, **unqueried**
or **failed**. Capped, keyword-empty, polluted, failed and unqueried are not
quiet: only an under-cap, in-bounds search supports "no new discussion", and
only for that query. A quiet or unqueried result never makes an earlier
episode cooling.

## Route by source family

Use the role assignments in `credible-equity-sources.md`, then execute the
matching family batches from `query-patterns.md`. Keep these families separate
long enough to detect ranking starvation:

1. **Long-form company research** - dense thesis, model, contract, or
   capital-structure work.
2. **Research and sector specialists** - estimate, supply-chain, clinical,
   industry, or forensic detail within a defined domain.
3. **Tape, PM, and strategist voices** - live reaction, risk/reward, relative
   expression, and explicit changes of mind or book state.
4. **Primary-language and news relays** - earnings-call language, product
   news, trial results, and factual triggers; drivers rather than consensus.

Treat one author as **one voice**, however many names or posts they cover. As a
default promotion cap, keep no more than two posts from one handle unless a
third concerns a distinct ticker and adds a distinct claim that changes the
read. This is a concentration control, not a reason to discard uniquely
load-bearing evidence.

For sentiment-sample concentration, use the stricter gates in
`equity-sentiment-panel.md`; do not let the more permissive core-evidence cap
control the temperature read.

## Recover a thin or crowded-out family

Before declaring a family quiet, distinguish genuine silence from a crowded
query result:

1. Split large or heterogeneous `from:` batches by source family.
2. Query missing handles alone or in smaller batches when one author supplied
   more than half of the returned roots or the batch hit its result cap. Isolate
   the priority handle before spending the remaining calls on another open
   search.
3. Widen only the quiet family by roughly 12-24 hours when the user did not fix
   the window. Never silently widen a user-fixed bound.
4. Search replies, quote-posts, and self-threads for reply-led or continuation-
   led specialists, preserving the parent/root edge. A blanket
   `-filter:replies` must not erase a reply-led specialist's analysis.
5. Run a ticker- or sector-constrained allowlist search for the missing lane.
6. Use a semantic or harvest search for discovery, then apply the core promotion
   gate. Off-list discovery does not become core evidence in-run. For the
   participant-native recovery path, follow `equity-sentiment-panel.md`.

Do not substitute an unfiltered Mag 7, cashtag, or generic “equity sentiment”
Latest search for a missing source family: it crowds out quiet professionals
with ticker spray and engagement bait. The company pulse answers a different
question, what is being said about named companies, and its returns pass the
same gates.

## Build the equity delta ledger

For chart-aware retrieval, keep a small separate set of **unread visual
candidates** from the assigned eligible source families. A terse caption or
text-complete post can warrant inspection based on source domain and returned
context; do not require the caption to contain a cashtag or the word chart.
Use the delegated packet contract in `../SKILL.md`: normal post ID/URL and
Media fields, unknown image subject remains unknown, no guessed numbers or
findings. These leads cannot fill a company delta-ledger row or establish a
trajectory/action until the parent reads and verifies the relevant evidence.
Keep domain, topic, time, quality and source-role gates unchanged. Inspect
existing lane returns before spending another bounded source-family call;
there is no new call allowance or required chart quota.

Before drafting, maintain a **delta ledger** row for every name that might
survive:

| Field | Record |
|---|---|
| Ticker / company | Exact name and relevant sleeve |
| Actual catalyst | Print, guide, filing, product, policy, tape move, or new claim |
| Prior frame | What the most recent relevant report said or left unresolved |
| New belief / conviction | What participants now believe, how strongly, and what changed it |
| Disagreement | Strongest informed alternative or explicit silence |
| Market expression | Relative winner/loser, multiple, estimate, position, hedge, flow, or risk boundary |
| Source role | EQ-A/EQ-B role, independence, disclosed interest, and any transcript/model caveat; a sentiment-panel post cannot fill this field |

Delete a row that has only a ticker mention, factual announcement, or generic
sector thesis. Several rows derived from the same post remain one source voice
and must not be described as independent confirmation.

When the participant-native extension is active, build the separate sentiment
ledger defined in `equity-sentiment-panel.md`; do not add its rows to this core
delta ledger.

## Apply concentration and quotation gates

- If one author supplies more than half of the promoted name-level conclusions
  or quoted words, rerun the missing source families. If independent evidence
  remains absent, compress the dominant author and state the concrete boundary.
- Apply the separate Temperature concentration and recurrence gates in
  `equity-sentiment-panel.md` when that extension is active.
- A long multi-name note does not satisfy breadth, source diversity, or a
  participant-language diversity check. Extract its name-level implications as
  a summary.
- Quote a complete short post when phrasing carries conviction, hesitation,
  surprise, irony, positioning, or a changed mind.
- For posts roughly over **250 words**, multi-name research notes, transcript
  read-throughs, or list-like threads, summarize and link the original. Quote
  only the wording whose phrasing is itself analytical evidence; mark any
  omission explicitly.
- Distinguish independent authors from replies, quote-posts, self-threads, and
  relays of the same underlying report.

## Stop and completion rules

An equity pass is complete when:

1. every applicable first-wave lane has been attempted, most of the baseline
   has a pulse search, and each mapped name's coverage state is recorded, with
   a reason for any material baseline omission;
2. each promoted company conclusion has a usable delta-ledger row; when the
   participant-native extension is active, its promoted claims pass the
   separate sentiment-ledger gate;
3. thin families have gone through the recovery ladder or are honestly labeled;
4. required parent, quote, or reply relationships are grounded; and
5. new searches across **independent source families** are mostly repeating
   existing names, claims, sentiment registers, or conversation edges.

Repetition from one prolific author is not saturation. Stop after independent
families repeat, not after a source-count quota is filled.
