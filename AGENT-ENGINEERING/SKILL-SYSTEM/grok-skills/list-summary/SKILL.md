---
name: list-summary
description: >
  Summarize the latest posts and conversation themes from members of a named
  X (Twitter) list. List-first briefing: adaptive recency window, theme
  clustering, active voices, and receipts from list members only. Use when the
  user runs /list-summary, or asks for a list feed digest / list briefing /
  "what's new on my list" / summary of posts from an X list URL or list ID
  (e.g. Interp and Alignment). Grok Build only (requires native X tools).
  Neutral analyst tone.
metadata:
  short-description: "X list member feed digest + theme map"
---

# /list-summary

You are running the **list-summary** skill. Produce a concise briefing of
**what list members have been posting** and **what themes are active** on a
named X list.

This is not a global X firehose brief and not a topic-first opinion map.
Follow this file top to bottom.

## Host requirement

You need these tools:

- `x_keyword_search` (required; uses the `list:{id}` operator)
- `x_thread_fetch` (for high-signal threads)
- `x_semantic_search` (optional lane; still filter to list authors when possible)
- `x_user_search` (optional; only if resolving a named member)

If `x_keyword_search` is missing, **stop**. Tell the user this skill only works
in Grok Build (or another host with that X tool). Do not fake a list digest from
web search or public list pages.

## Hard rules

1. **List-first synthesis.** All claims come from posts returned under the
   resolved `list:{id}` constraint (or clearly authored by members already seen
   in that list sample). Never invent posts, handles, engagement, or quotes.
2. **No public scrape substitute.** Do not use `web_fetch` / browser scraping of
   `x.com/i/lists/...` as the primary source. The native `list:` operator is the
   source of truth for membership-filtered posts.
3. **Soft web exception.** At most **one** web lookup only if you must resolve a
   non-numeric list identity the user named vaguely and it is not in
   `references/known-lists.md`. Prefer asking the user for a list URL/ID over a
   web hunt. If you use web, say so in Gaps.
4. **Discovery is allowed.** Empty `/list-summary` with a known default list, or
   "what's new on my Interp list," means: scan that list in the committed window
   and cluster themes. No global trending discovery.
5. **Time window is first-class.** Honor user windows (`past 6h`, `last 3 days`,
   `past week`). If omitted, use the adaptive pulse (below).
6. **Optional topic filter.** If the user adds a topic ("interp SAE papers",
   "evals"), keep `list:{id}` and add topic tokens. Do not drop the list constraint.
7. **Neutral analyst tone.** No hype, no dunking. Report themes and camps as
   observed among list members.
8. **List sample is not the field.** Frame conclusions as "among this list in
   this window," not as the entire community or ground truth.
9. **Citations.** Prefer `@handle` plus post links when available. Use the
   host's inline post citation render when you have post citation IDs. Never
   invent URLs.
10. **Privacy / access.** If `list:{id}` returns empty after widening, the list
    may be private to another account, empty, or inaccessible to the host's X
    auth. Report that honestly; do not invent members.
11. **Replies are conditional enrichment.** Use `-filter:replies` when needed
    for a clean overview, but never assume it found the best conversation
    evidence. Enrich only selected roots and preserve material reply IDs,
    relationships, and membership status.
12. **Prevalence is not evidence weight.** Engagement and list volume help find
    candidates; they do not decide which correction or technical reply matters.

Read `references/known-lists.md` when resolving list aliases.
Read `references/query-patterns.md` when building queries.
Read `references/failure-modes.md` when the sample looks thin, mixed, or noisy.

## Pipeline

### Step 0 - Parse list, topic, and window

**List (required to search):**

| User gave | Resolve how |
|-----------|-------------|
| URL `https://x.com/i/lists/{id}` or `twitter.com/i/lists/{id}` | Extract numeric `{id}` |
| Bare numeric list id | Use as `list:{id}` |
| Known alias / short name | Look up in `references/known-lists.md` |
| Nothing, but a default is set in known-lists | Use **default list** for this user |
| Nothing and no default | Ask once for list URL, id, or known alias |

Strip path junk; keep only the numeric id for the operator.

**Topic (optional):**

- Named focus inside the list (paper, lab, technique, controversy).
- No topic: **full list scan** - cluster whatever members are discussing.

**Window:**

| User said | Commit |
|-----------|--------|
| `past Nh` / `last N hours` | last N hours (`since:` today + mental hour filter) |
| `past Nd` / `last N days` / `past week` | last N days via `since:YYYY-MM-DD` |
| `since {date/day}` | that lower bound |
| nothing | adaptive pulse (Step 3) |

### Step 1 - Resolve list identity

1. Open `references/known-lists.md` if the user used a name/alias or omitted the id.
2. Record for the brief: **list display name**, **list id**, **aliases matched**.
3. If unresolved: ask for `https://x.com/i/lists/{id}` (one short question). Do not guess random ids.

### Step 2 - Optional soft resolve (0 or 1 call)

Only if the user named a list that is not in known-lists and gave no id/URL:

- Prefer asking the user.
- At most one web lookup if they already pointed at a public page that might
  contain the id; extract numeric list id only.
- Never invent an id from memory.

### Step 3 - Pulse (always first unless user fixed a short window)

Run a **cheap Latest** keyword search:

```text
list:{id} since:{today_or_short_bound}
```

Mode: `Latest`. Limit ~10.

If almost empty, widen once (yesterday / 2–3 days) before committing mode.

**Commit a mode and window:**

| Pulse signal | Mode | Default window |
|--------------|------|----------------|
| High volume same-day posts, clear live thread | Breaking | last 1–6 hours |
| Steady same-day chatter | Same-day | last 24–48 hours |
| Multi-day ongoing threads | Story | last 3–7 days |
| Sparse, slower research-style posting | Background | last 7–14 days (cap ~30); prefer newest |

If the user fixed the window, honor that bound; still label density mode.

State **Window**, **Mode**, **List name + id** in the brief.

### Step 4 - Search lattice (list-constrained)

Cap total X tool calls roughly **8–14** for a normal run.

| Lane | Tool | Goal |
|------|------|------|
| List Latest | `x_keyword_search` mode=`Latest` | Fresh member posts |
| List + topic | keyword `list:{id}` + topic tokens | Focused digest |
| List + engagement floor | `list:{id}` + `min_faves:N` or `filter:has_engagement` | Higher-signal subset |
| List Top (optional) | mode=`Top` with `list:{id}` | May return empty; if so, rank Latest yourself |
| Thread fetch | `x_thread_fetch` | Origin / long technical threads |
| Semantic (optional) | `x_semantic_search` | Adjacent framing; **keep only authors already seen in list sample** or re-check with list Latest |

**Critical host note:** Pure `list:{id}` queries are reliable in **Latest**. **Top**
mode often returns empty for bare list queries. Prefer Latest plus substance and
source-role triage over trusting Top or engagement alone.

Always keep `list:{id}` in keyword queries for membership filtering.

Optional filters (use sparingly):

- `-filter:replies` when pure reply chains drown original posts (note if you drop replies)
- `filter:self_threads` when list members' long author continuations matter
- `filter:quote` when quote-debate is the story
- Topic keywords only when the user asked for a focus

### Step 5 - Select and enrich conversations

Shortlist roughly **2–5** roots before spending reply calls. Under a normal
budget, fully enrich only the best **2–3** and reserve at least two calls per
fully enriched root (normally **4–6 conversation calls**), prioritizing:

1. Original technical / research posts (not "same" / emoji replies)
2. Threads that define a live debate among members
3. Specific evidence-bearing in-window originals
4. Clear steelman and clear critique when a split exists
5. Origin posts that many list members are replying to (even if slightly older)

For each selected root:

1. `x_thread_fetch` the root or important node.
2. Run floor-free `conversation_id:{root_id}` Latest.
3. Use `filter:self_threads` for member-author continuations. Time-box around a
   known correction if Latest is dominated by newer noise.
4. Use one modest `min_faves` pass only after the floor-free sample. It is a
   precision comparison, not the reply universe.
5. Use `to:{author} filter:replies` only as fallback; keep exact
   `conversation_id` matches.

A root counts as an **enriched conversation** only after both steps 1 and 2
complete. A thread-only root remains a candidate. If a completed enrichment
yields no additive child or quote node, record the negative check in the search
log or Gaps rather than presenting a root-only row as a key conversation.

Classify retained nodes as author follow-up, correction, evidence addition,
technical counterargument, expert extension, clarification/open boundary, or
social/noise. Skip the last class.

Thread context and replies may include non-members. Label each material
non-member **outside-list context** and never count them in Active voices,
member prevalence, or list receipts. They may still be a lower-weight
correction/counterevidence node when their relationship and text are grounded.

Stop when another lane is mostly duplicate IDs or adds no substantive
relationship class.

### Step 6 - Rank and cluster

- **On list:** author appeared under `list:{id}` sample (or is the same handle from that sample).
- **Substance:** original claim, paper, result, argument, or useful pointer > pure social ack.
- **Information gain:** correction, mechanism, evidence, boundary, or
  counterexample > repetition. Engagement is discovery-only and can be zero.
- **Clusters:** merge posts that advance the same theme into one theme bullet.
- **Active voices:** tally distinct handles with substantive posts (not total tweet count only).

Discard: off-list contamination if any leaked, pure engagement bait, empty replies.

### Step 7 - Synthesize

Emit the brief using the template below. Include **2–4 short attributed quotes**
from real list-member posts when usable text exists.

If the sample is thin, say so. Prefer honest uncertainty over fake consensus.

## Output template

Use this structure. Keep headings. No extra blog-style sections.

```markdown
# /list-summary: {list display name}

**List:** {name} · id `{id}` · [open list](https://x.com/i/lists/{id})
**Window:** {human window} · mode {Breaking|Same-day|Story|Background} · as of {UTC or local stamp}
**X sample:** ~{N} inspected → ~{C} candidate roots → {K} conversations enriched → {R} promoted nodes ({P} roots + {A} additive child/quote nodes) · ~{M} distinct list members · confidence {high|medium|thin}
**Focus:** {full list scan | topic: …}

## What's active
2–5 sentences. What list members have been talking about in this window. Stick
to what the list sample supports.

## Theme map
| Theme | Heat (rough) | Core claim / activity | Voices |
|-------|--------------|------------------------|--------|
| … | high/med/low | … | @a, @b |

Heat is qualitative from this list sample only.

## Active voices
- **@handle** - one-line what they pushed (role: research / critique / pointer / debate)
- … (up to ~8; substantive only)

## Key conversations
| Root | Material node(s) | Relationship | What it adds or changes | Membership | Weight / prevalence |
|------|------------------|--------------|-------------------------|------------|---------------------|
| @member + ID/link | @handle + ID/link | correction / extension / ... | ... | member / outside-list context | high/med/lead · high/med/low |

Include only material root-to-node edges; omit roots with zero additive nodes.
Keep 2–5. `lead` means an unanswered boundary or unverified claim, not evidence.

## Notable posts (receipts)
- [@handle](url or status link if known) - why it matters (role: origin / technical / steelman / critique / pointer)
- … (5–10 max)

## Gaps / caveats
- Thin sample, reply-heavy noise, private/inaccessible list risk, Top-empty quirk,
  topic filter miss, language bias, default-list assumption, etc.
- What would change this read if true
```

### Formatting notes

- Use plain hyphens `-`, not em dashes.
- Neutral wording: "several list members argue", not "the alignment community knows".
- Heat and camp shares are rough sample judgment only.
- If confidence is thin, shrink theme map and expand Gaps.
- End after Gaps unless the user asked follow-ups.

### Saving new lists

If the user wants a new alias remembered, append it to
`references/known-lists.md` (id, display name, aliases) only when they clearly
ask to save/remember it. Do not rewrite their lists unprompted.

## Pre-flight checklist (before first tool call)

- [ ] X tools available (else refuse)
- [ ] List id resolved (URL / id / known-lists / default) or ask
- [ ] Window: user-specified or will pulse adaptively
- [ ] Topic mode vs full-list scan decided
- [ ] Web budget remaining: 0 or 1 resolve-only
- [ ] Will keep `list:{id}` on keyword lanes
- [ ] 4–6 reply calls reserved to fully enrich the best 2–3 shortlisted roots

## Post-synthesis checklist (before send)

- [ ] List name + id + window + mode stated
- [ ] Every quoted line attributable to a fetched list-sample post
- [ ] No off-list authors in receipts or theme table (unless labeled origin outside list)
- [ ] Every promoted reply has root/node IDs, relationship, and membership label
- [ ] Enriched count includes only roots with thread fetch + floor-free exact-conversation search
- [ ] Root-only checks with zero additive nodes are in Search log/Gaps, not Key conversations
- [ ] No invented URLs or handles
- [ ] Theme heat labeled as rough sample judgment
- [ ] Prevalence separated from evidence weight
- [ ] Search-log calls and signal-funnel counts reconcile
- [ ] Gaps honest about sample limits and access quirks
- [ ] Did not treat list sample as the whole field
