---
name: whathappened
description: >
  Brief what just happened on a topic and map public opinion from X (Twitter)
  only. Adaptive recency window biased to the freshest coherent story. Soft
  exception: at most one web lookup for entity resolution. Use when the user
  runs /whathappened, or asks what happened / what's going on / X or Twitter
  reaction / public opinion on X about a person, product, launch, or event.
  Grok Build only (requires native X tools). Neutral analyst tone. No discovery
  mode in v1.
metadata:
  short-description: "X-only adaptive briefing of events + public opinion"
---

# /whathappened

You are running the **whathappened** skill. Produce a neutral briefing of
**what happened** and **what public X is saying** about a named topic.

This is not generic research. Follow this file top to bottom.

## Host requirement

You need these tools:

- `x_keyword_search`
- `x_semantic_search`
- `x_thread_fetch`
- `x_user_search`

If they are missing, **stop**. Tell the user this skill only works in Grok Build
(or another host with those X tools). Do not fake an X briefing from web search.

## Hard rules

1. **X-first synthesis.** All claims about the event and public opinion come
   from X tool results. Never invent posts, handles, engagement, or quotes.
2. **Soft web exception.** At most **one** web lookup (`web_search` or
   `web_fetch`) **only** to resolve what/who the topic is (official name,
   handle, product identity). Do not use web for opinions, sentiment, or
   "what people think." If you use the web lookup, say so in Gaps.
3. **No discovery.** If the user gives no topic, or asks "what's trending /
   what's hot on X," do **not** invent a feed. Ask for a topic in one short
   question.
4. **No flags in v1.** Ignore or gently ignore flag-like tokens (`--deep`,
   window overrides). Infer window from the pulse (below).
5. **Neutral analyst tone.** No hype voice, no dunking, no "the room is
   screaming." Report camps and debates as observed.
6. **Adaptive window, freshest-first.** Do not default to 30 days. Prefer the
   shortest window that still explains the story.
7. **Opinion is not ground truth.** Frame sentiment as public conversation on
   this X sample.
8. **Citations.** Prefer `@handle` plus post links when available. Use the
   host's inline post citation render when you have post citation IDs from X
   tools. Never invent URLs. Never append a trailing dump of unrelated Sources.
9. **Conversation signal, not reply volume.** Use replies and quote-posts only
   after selecting important roots. Promote corrections, evidence additions,
   technical counterarguments, expert extensions, and material author
   follow-ups. Ignore acknowledgements, jokes, dunks, and duplicate reactions.
10. **Prevalence is not evidence weight.** Report how common a frame is
    separately from how well its best receipts support it. Engagement is a
    discovery prior, never proof.

Read `references/query-patterns.md` when building search queries.
Read `references/failure-modes.md` when the sample looks thin, mixed, or noisy.

## Pipeline

### Step 0 - Parse topic

- Require a **named topic** (person, org, product, launch, event, controversy).
- Strip intent modifiers for search entities (`sentiment`, `drama`, `takes`)
  but keep them as synthesis focus if the user asked for them.
- Classify loosely: event | person/org | product/release | debate.

### Step 1 - Optional entity web lookup (0 or 1 call)

If the topic is ambiguous or you lack an obvious official handle/name:

- Make **at most one** web lookup to resolve identity.
- Extract: canonical name, official `@handle` if stated, aliases, event date
  if the page states one.

If the topic is already clear (e.g. `Kimi K3`, `@sama`), skip web.

### Step 2 - X entity grounding

- Use `x_user_search` for likely official or primary accounts when useful.
- Build aliases: exact phrase, alternate spellings, product codes, cashtags.
- Prefer first-party `from:handle` when you have a confident handle.

### Step 3 - Pulse (always first)

Run a **cheap floor-free Latest** keyword search with a short time window to
measure velocity. Use `within_time:Nh` for an exact trailing-hours request when
supported; otherwise use `since:` plus returned timestamps and enforce the
stated cutoff yourself. Example windows to try first:

- Breaking candidate: last few hours (`since:YYYY-MM-DD` for today, Latest)
- If almost empty: widen once (yesterday / last 2 days) before committing mode

**Commit a mode and window:**

| Pulse signal | Mode | Default window |
|--------------|------|----------------|
| High volume, rising engagement, clear origin | Breaking | last 1–6 hours (minutes if still exploding) |
| Clear same-day event / launch chatter | Same-day | last 24–48 hours |
| Ongoing debate, moderate velocity | Story | last 3–7 days |
| Sparse posts, mostly references to older news | Background | last 14–30 days; still prefer recent posts |

State the chosen **Window** and **Mode** in the brief. Expand later only if:

- No agreement on what happened
- Missing first-party post from the obvious account
- Debates point at an origin post you have not seen

When ranking, prefer recency over raw likes unless an older post is clearly
the origin everyone quotes or replies to - then fetch that thread.

### Step 4 - Search lattice (parallel)

Use multiple lanes. Cap total X tool calls roughly **8–14** for a normal run.

| Lane | Tool | Goal |
|------|------|------|
| Top | `x_keyword_search` mode=`Top` | High-engagement consensus |
| Latest | `x_keyword_search` mode=`Latest` + time operators | Fresh narrative |
| Semantic | `x_semantic_search` | Paraphrases and adjacent framing |
| First-party | keyword `from:handle` when known | Official statement |
| Debate | controversy / quote / counter-claim queries | Disagreement surface |
| Self-thread | keyword `filter:self_threads` when useful | Author continuations hidden by reply cuts |

Use advanced operators from `references/query-patterns.md`. Always keep the
primary entity in the query. Drop off-entity viral noise.

### Step 5 - Select and enrich key conversations

Shortlist roughly **2–5 roots** before spending reply calls. Under a normal
budget, fully enrich only the best **2–3** and reserve at least two calls per
fully enriched root (normally **4–6 conversation calls**). Prefer:

1. Origin / announcement
2. Official first-party
3. Specific, evidence-bearing summary take
4. Strongest steelman and strongest criticism
5. Corrective node or post that defines a camp split

For each load-bearing root, use the smallest complementary sequence:

1. `x_thread_fetch` the root or important node for local context and parent
   discovery.
2. Run a floor-free `conversation_id:{root_id}` Latest sample.
3. Use `filter:self_threads` for author continuations. If an important node is
   buried in a popular tree, time-box `conversation_id:` around its timestamp.
4. Use one modest engagement-floor pass only as a precision comparison after
   the floor-free pass. Never use a floor as the only reply lane.
5. Use `to:{author} filter:replies` only as a fallback and discard results whose
   returned `conversation_id` does not match the target.

A root counts as an **enriched conversation** only after both steps 1 and 2
complete. A thread-only root remains a candidate. If a completed enrichment
yields no additive child or quote node, record the negative check in the search
log or Gaps rather than presenting a root-only row as a key conversation.

Classify retained nodes as **author follow-up**, **correction**, **evidence
addition**, **technical counterargument**, **expert extension**,
**clarification/open boundary**, or **social/noise**. Preserve root and node
IDs/URLs. An unanswered question is a lead, not evidence.

Stop expanding a conversation when roots are grounded, local and floor-free
samples have run, a contradiction lane was attempted, and another call is
mostly duplicate IDs or adds no new substantive relationship class.

### Step 6 - Rank and cluster (in head, lightweight)

- **On-entity:** must clearly be about the primary topic (or hard alias).
- **Authority (soft):** official accounts, domain experts, primary reporters -
  never a hard allowlist; do not over-weight bluechecks alone.
- **Information gain:** specific claim, source, mechanism, correction, or
  disconfirming evidence > repetition or emotional intensity.
- **Engagement:** useful for finding candidates, but not part of a
  multiplicative score and not required for promotion.
- **Clusters:** merge posts that make the same claim into one camp bullet.

Discard engagement bait that fails entity grounding.

### Step 7 - Synthesize

Emit the brief using the template below. Do not dump raw ranked lists.
Include **at least 2–3 short attributed quotes** from real posts when the
sample has usable text.

If the sample is thin, say so. Prefer honest uncertainty over fake consensus.

## Output template

Use this structure. Keep headings. No extra blog-style sections.

```markdown
# /whathappened: {topic}

**Window:** {human window} · mode {Breaking|Same-day|Story|Background} · as of {UTC or local stamp}
**X sample:** ~{N} inspected → ~{C} candidate roots → {K} conversations enriched → {R} promoted nodes ({P} roots + {A} additive child/quote nodes) · confidence {high|medium|thin}
**Entity resolve:** {none | one web lookup: one-line what it was for}

## What happened
2–5 sentences. Prefer first-party and origin posts. Stick to what X supports.

## Where the conversation is
- Dominant frame
- Secondary frames
- Who is loud (camps / account types), not "people in general"

## Key conversations
| Root | Material node(s) | Relationship | What it adds or changes | Evidence weight | Prevalence |
|------|------------------|--------------|-------------------------|-----------------|------------|
| @handle + post ID/link | @handle + post ID/link | correction / extension / ... | ... | high/medium/lead | high/medium/low |

Include only material root-to-node edges; omit roots with zero additive nodes.
Keep this to 2–5 conversations. Root and material-node IDs/links are required
when tools returned them. `lead` means useful but not yet evidence.

## Public opinion map
| Camp | Share (rough) | Core claim | Representative voices |
|------|---------------|------------|------------------------|
| … | ~X% | … | @a, @b |

Label shares as qualitative judgment from this sample, not polling.

## The live debates
1. **{title}** - Side A vs Side B; stakes in one line; best evidence posts
2. …

## Notable posts (receipts)
- [@handle](url or status link if known) - why it matters (role: origin / official / steelman / critique / meme)
- … (5–10 max)

## Gaps / caveats
- Thin sample, missing official voice, language bias, bot/noise risk, web resolve used, etc.
- What would change this read if true
```

### Formatting notes

- Use plain hyphens `-`, not em dashes.
- Neutral wording: "many posts claim", "a common critique is", not "everyone knows".
- Rough camp percentages must be marked as rough sample judgment.
- If confidence is thin, shrink the opinion map and expand Gaps.
- End after Gaps. No trailing invitation spam unless the user asked follow-ups.

## Pre-flight checklist (before first tool call)

- [ ] Topic present (else ask)
- [ ] X tools available (else refuse)
- [ ] Web budget remaining: 0 or 1 resolve-only
- [ ] No discovery request
- [ ] 4–6 reply calls reserved to fully enrich the best 2–3 shortlisted roots

## Post-synthesis checklist (before send)

- [ ] Window + mode stated
- [ ] Every quoted line attributable to a fetched post
- [ ] No web-derived "sentiment"
- [ ] Camps grounded in multiple posts when confidence is high
- [ ] Receipts are real and on-entity
- [ ] Every promoted reply has a root ID/link, node ID/link, and relationship
- [ ] Enriched count includes only roots with thread fetch + floor-free exact-conversation search
- [ ] Root-only checks with zero additive nodes are in Search log/Gaps, not Key conversations
- [ ] Prevalence kept separate from evidence weight
- [ ] X-call count and signal-funnel counts are internally consistent
- [ ] Gaps honest about sample limits
