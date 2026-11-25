# X signal and conversation playbook

Read this reference when the delegated task involves a high-volume feed, a
popular post, replies, quote-post debate, a self-thread, or the instruction to
find the *few* posts that matter.

The objective is not maximum recall. It is a fast, auditable funnel from a noisy
stream to a small set of roots and conversation nodes that could change the
parent model's analysis.

## Protect the integrated read before fanout

For a broad request spanning several themes, market sleeves, or names, begin
with one specialized run that can see the whole committed window and has enough
budget to identify both the main themes and the conversations carrying them.
Use that integrated pass to choose targeted follow-ups.

Do not make the first wave a collection of isolated decision questions whose
small per-run budgets leave no room for conversation recovery. Parallel or
factor-specific runs are useful after the integrated pass when they fill a
known coverage gap, test a competing explanation, or verify an important
receipt without starving the reply ladder. Skip the integrated pass when the
request is already narrow, names one conversation, or explicitly asks for
separate audits.

## Signal funnel

Report these stages separately:

1. **Inspected** - approximate raw posts returned by tools.
2. **Candidates** - roots worth closer inspection before reply calls.
3. **Enriched** - roots for which both a local-context thread fetch and a
   floor-free exact-conversation query ran.
4. **Promoted** - roots, replies, or quote-posts that enter the evidence packet.

Do not call every inspected post a candidate or every candidate a receipt.
Approximate counts are fine; internally inconsistent call or post counts are
not.

## Batch size, bounds, and silence tests

Crowding is batch size times window density. On 2026-09-21, ten-handle
`from:` batches over the cash session returned ten posts from one or two
prolific accounts and proved nothing about the other eight; four-handle
batches over a sparse three-hour window returned under the cap and doubled as
silence proofs.

- Batch at most four handles when the window is under about three hours.
- Query a handle alone when a prolific poster is in the set or the window
  spans the cash session.
- Test silence in two stages: one four-handle batch per group first, then
  isolate only the handles inside a batch that returned at the result cap.
  Fourteen single-handle calls to learn that nine accounts were silent is
  correct but expensive.
- An under-cap, floor-free, in-bounds handle-only return can support bounded
  silence for the queried, identity-verified handles and elapsed window. A
  keyword query tests its wording, not whether an account posted at all; a
  crowded page or omitted source proves neither.
- Report known-matching misses with the omitted post ID, exact query, bounds,
  fetch time and match basis. An under-cap page is not negative coverage when
  that query family demonstrably missed a matching post. Mark that coverage
  unproven; do not automatically discard an independent handle-only check.
- Compare the upper bound to the actual launch clock before interpreting a
  recent empty window. Record newest returned and fetch timestamps; future
  minutes are not indexed minutes and cannot demonstrate index lag.

Date bounds fail silently on long queries. Every query that combined a keyword
OR-list with a `from:` roster of more than four handles returned posts from
weeks before its `since:` bound; single-handle, `conversation_id:`,
`quoted_tweet_id:`, and short keyword queries honored it.

- Keep each query to one keyword group plus at most one `from:` group of four
  handles, or split roster from keywords.
- If any returned post is outside the bound, the query is bound-failed: report
  it as such in the Search log, drop the leaked posts, do not count the page
  as coverage, and split the query. The wave runner lints literal queries in
  briefs for this shape before launch.

## Reach, outcome and exclusion queries

- **Reach versus outcome.** A Top or `min_faves` query finds what has reach,
  so it carries topic words only: tickers, names, the index. Outcome or
  explanation words (selling, crash, "why is", a candidate cause) run in
  Latest with no floor. On 2026-10-08 a wire headline that started a selloff
  carried no sell words, so a reach query built on sell words missed it.
- **Floors on long OR lists.** On an open query (no `from:` or `list:`
  scope), keep at most about five OR terms when a floor is set; otherwise
  split it into short floor-free queries. A fourteen-term `min_faves:5` query
  returned nothing on 2026-10-08. A list-scoped token pack keeps its own "if
  thin, drop the floor" rule. The wave runner warns before launch on a
  floored open query with more than eight OR terms.
- **Negative keywords.** For one deliberate "explanations other than the
  default story" call, exclude the dominant story's terms (`-oil -yields
  -Iran`), in Latest with no floor. The exclusion also drops posts that
  mention the dominant story in passing; say so in coverage.
- **Company lanes read handle-only roster pages.** For a mega-cap, the
  lane's handle-only roster pages are the coverage; read them for the name.
  The roster-paired form `(from:A OR from:B OR from:C) ($AAPL OR Apple)` is
  only a short-window "did they mention it" check, never coverage: in October
  it returned 2.1 posts per call and nothing on 46% of calls, and on
  2026-10-09 it missed all seven in-window posts by @GavinSBaker, two of them
  on the lane's central argument (recall audit, 2026-10-10). An open mega-cap
  cashtag runs only in Top with topic words, because an open Latest page fills
  in about a minute (2026-10-08: an ORCL/CRWV Latest page held ten posts from
  one minute). Keep the open Latest cashtag form for less crowded names. The
  topic words are the company's own (capex, guidance), never a broad macro
  word such as rates, yields or oil required beside one ticker: on 2026-10-21
  `($AAPL OR Apple) rates` found another sense of "rates". The wave runner
  warns before launch on such a query.
- **Trigger relays around the break.** To find an unknown trigger, query
  headline relays handle-only, with no keywords, from about ten minutes before
  the break on the 1-minute bars to five minutes after it, never the whole
  session: four relays filled a ten-post page in about nine minutes.

## Discover durable source seeds

When the delegated task asks for posters similar to exemplars, split discovery
from validation:

1. Generate a bounded candidate set from exemplar self-threads, material
   replies, quote-posts, and semantic searches for the desired posting
   *behavior*.
2. Review each candidate across the posting modes relevant to its apparent
   role: roots and self-threads, replies and conversations, quote-post
   commentary, and native repost/relay curation when the tools expose it.
3. Require repeatable substantive value across multiple dates or events, but
   do not require a particular posting format. Original analysis, replies that
   add evidence or reasoning, and consistently useful curation can all qualify.
4. Label the account a close behavioral match or a complementary source role,
   and preserve the role-specific caution.

“Accounts similar to X,” social-graph adjacency, biography, employer, and one
excellent interaction are candidate generators, not recurrence evidence.
Product or announcement volume also does not establish repeated technical
practice. For a reply-led source, recover the parent/root and identify what the
reply adds. For a curator or relay, trace the underlying author/source: the
selection can be useful, but it is neither the curator's original analysis nor
independent corroboration. If native reposts are unavailable through the X
tools, report that coverage limit rather than treating the candidate as
inactive.

## Select roots before reading replies

Use broad, floor-free discovery to identify candidate roots. Rank them on
separate axes:

- relevance to the delegated decision;
- claim or mechanism specificity;
- source role and domain fit;
- evidence, artifact, or quantitative detail;
- novelty, correction, or disconfirming value;
- freshness within the committed window.

Engagement is a discovery prior, not an evidence axis and never a requirement.
A zero-like technical reply can outrank a viral acknowledgement. Avoid
multiplicative formulas in which low engagement reduces an otherwise strong
post to zero.

Shortlist roughly 2-5 roots, but reserve at least **two calls per fully enriched
conversation**. A normal 10-14-call run should fully enrich the best 2-3 roots,
not fetch every thread in the discovery sample. A root counts as enriched only
after both `x_thread_fetch` and a floor-free exact `conversation_id` sample.

## Progressive conversation ladder

No single X query is a complete reply tree. Use the smallest complementary
sequence that resolves the question.

| Stage | Query/tool | What it adds | Known limitation |
|---|---|---|---|
| Local context | `x_thread_fetch` on the known root or important node | Parent/root discovery, author continuation, a small contextual reply sample | Selection is partial and opaque |
| Floor-free tree surface | `conversation_id:{root_id}` in Latest | Recent nodes tied to the exact conversation | A popular tree's newest noise can push older signal outside the result cap |
| Author continuation | `filter:self_threads` or thread fetch | Long breakdowns and live measurement chains | `-filter:replies` can hide these posts |
| Independent reaction | Quote-post query when supported, or focused quote lane | Critique, replication, and downstream framing | Quote-posts are not independent evidence of the underlying claim |
| Time slice | `conversation_id:{root_id}` plus narrow `since`/`until` | Recovers a known mid-thread correction cluster without a popularity floor | Requires a useful node timestamp |
| Precision lens | One modest `min_faves` pass after a floor-free pass | Removes residual noise in a very large tree | Deletes low-engagement minority signal; never use as the only reply lane |
| Last-resort author lane | `to:{author} filter:replies` plus topic/window | Finds replies when conversation operators are unavailable | Author-global and cross-conversation; retain only results whose returned `conversation_id` matches |

Treat `in_reply_to_tweet_id:` as opportunistic. It may fail upstream and should
not be a required step. If a query operator errors twice, record the failure
and use the next lane rather than spending the budget retrying it.

Do not combine an exact `conversation_id:` lane with broad reply terms in one
large `OR` query. The broad branch can swamp or contaminate the exact branch.

A conversation sample need not echo its root: Latest caps, reply-only
surfaces, and windows excluding the root can all omit it. If the sample is
empty **despite known eligible children or a conflicting reply count**,
recheck root ID, elapsed bounds and filters; make at most one corrected probe
within budget, then report unresolved operator/index coverage rather than
thread silence. A reply count is a diagnostic, not proof every reply is
public or in-window. Zero rows with no contradictory evidence are an empty
retrieved sample, not proof the thread has no replies. Quote-post counts do
not establish missing replies; use the quote lane when quotes matter.

If a completed conversation yields zero additive nodes, record that negative
result in Coverage, Search log, or Gaps. Do not place a root-only row in **Key
conversations**; that table is reserved for a material root-to-node edge.

## Classify nodes before promotion

Assign one relationship class:

- **author follow-up** - the root author adds evidence, scope, or a revision;
- **correction** - identifies and supports a factual or interpretive error;
- **evidence addition** - adds a source, measurement, artifact, or concrete case;
- **technical counterargument** - challenges mechanism or inference with reasons;
- **expert extension** - adds a material boundary, mechanism, or implication;
- **clarification / open boundary** - sharpens the claim but does not settle it;
- **social / noise** - praise, dunk, joke, repetition, promotion, or empty quote.

Promote a reply only when its content and relationship are both recoverable. For
each promoted node preserve:

- node author, timestamp, post ID, URL, and load-bearing text;
- root post ID and URL;
- parent or quoted node ID when the tool provides it;
- relationship class;
- claim and why it changes the read;
- source role, independence, and caveat.

An unanswered question is a follow-up lead, not evidence that its implied
failure exists.

## Prevalence is not evidence weight

Track two judgments separately:

- **Prevalence:** how much of the sampled stream or conversation repeats a theme.
- **Evidence weight:** how specific, well-sourced, independent, and
  decision-relevant the best receipts are.

A noisy majority can be prevalent and weak. A rare correction can be
low-prevalence and load-bearing. Never infer public consensus from reply counts.

## Stop rules

Stop conversation expansion when:

1. the root and important parent/quote relationships are grounded;
2. at least one floor-free conversation sample and one local-context sample
   have run for a load-bearing root;
3. a deliberate correction or counterevidence lane has been attempted;
4. a new call is about 70% duplicate IDs, or two consecutive lanes add no new
   substantive relationship class; and
5. the remaining uncertainty is explicit enough for the parent to judge.

Do not stop after Latest alone on a popular thread. Do not keep searching merely
to fill a receipt quota.

For accounting, report:

- inspected = unique returned post IDs examined;
- candidate roots = unique roots surviving initial gates;
- conversations enriched = roots that completed both required calls;
- promoted nodes = unique retained root posts plus additive child/quote nodes.

## Domain promotion gates

### Deep-learning research

Distinguish paper/lab author, independent technical explainer, peer expert,
replication/critique, and aggregator. Treat X as a pointer and interpretation
layer. A paper result remains unverified until the primary paper or artifact is
checked outside X.

Prefer roots with a paper/report identity, measured claim, method or ablation
detail, limitations, and technical continuation. `filter:self_threads` is often
more useful than `-filter:replies` for breakdown threads.

### Agents and agentic coding

Distinguish builder report, maintainer/repository evidence, user replication,
independent critique, correction/boundary, and product announcement.

Call a practice actionable only when it has at least two of:

- a procedure or configuration;
- a measurable outcome;
- a named failure mode or boundary;
- an inspectable artifact, benchmark, or repository.

An anecdote can still be a useful lead, but label it as such.

### Macro and equities

Preserve the active allowlist and domain-tier rules. Use replies to recover
author math, corrections, competing causal accounts, and expert mechanics.
Off-allowlist replies may be labeled counterevidence or context, but cannot
establish allowlist consensus by themselves.

## Brief fields for noisy work

Add these to the normal delegated brief when relevant:

```markdown
Output orientation: participant-native | hybrid | research-adjudication
Role of X evidence: subject | major input | supporting evidence
Participant question: What are participants observing, disputing, or revising?
Narrative center: The requested reader-facing center, or "discover from evidence".
Signal target: What would make a post or reply analysis-changing?
Conversation depth: roots only | selected roots | named thread deep dive
Enrichment order: named roots (root IDs, not reply IDs) before discovery
Query shape: one keyword group + at most one four-handle `from:` group per query
Promotion classes: correction, evidence addition, technical counterargument, ...
Stop rule: Call cap plus novelty/duplicate threshold.
```
