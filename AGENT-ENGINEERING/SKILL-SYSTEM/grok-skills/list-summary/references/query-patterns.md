# X query patterns for /list-summary

Use with `x_keyword_search`. Always keep `list:{id}` in keyword lanes so results
stay membership-filtered.

## Core operators

| Operator | Use |
|----------|-----|
| `list:{numeric_id}` | **Required.** Posts from accounts on that list |
| `since:YYYY-MM-DD` | Lower bound for adaptive / user window |
| `until:YYYY-MM-DD` | Upper bound if needed |
| `"exact phrase"` | Papers, product names, multi-word topics |
| `OR` | Aliases (must be uppercase OR) |
| `from:user` | Rare; only when focusing one known list member *inside* a list query if needed |
| `filter:replies` / `-filter:replies` | Include or cut pure reply noise |
| `filter:self_threads` | Recover list-member author continuations hidden by reply cuts |
| `filter:quote` | Quote-tweet debate surface |
| `conversation_id:{root_id}` | Exact selected conversation; membership is not implied |
| `filter:has_engagement` | Drop zero-engagement spam when Latest is noisy |
| `min_faves:N` / `min_replies:N` / `min_retweets:N` | Raise signal floor on busy lists |

If an operator errors or returns nothing, simplify rather than invent syntax.
Never drop `list:{id}` to "get more results" unless the user explicitly wants
global X (then this is the wrong skill - point them at `/whathappened`).

## Extracting list id from URLs

```text
https://x.com/i/lists/2034096409167991117
https://twitter.com/i/lists/2034096409167991117
https://x.com/i/lists/2034096409167991117?x=…
```

→ id = `2034096409167991117` → query token `list:2034096409167991117`

## Lane recipes

### Pulse (Latest, short window)

```text
list:{id} since:{today}
```

Mode: `Latest`. Limit 8–10.

### Full list scan (committed window)

```text
list:{id} since:{bound}
```

Mode: `Latest`. Run once or twice with different bounds if the first pass is thin.
Optionally a second pass:

```text
list:{id} since:{bound} filter:has_engagement
```

### Topic focus inside the list

```text
list:{id} ({topic} OR {alias}) since:{bound}
```

Examples:

```text
list:2034096409167991117 (SAE OR "sparse autoencoder" OR "mech interp" OR interpretability) since:2026-07-15
```

```text
list:2034096409167991117 (eval OR evals OR "alignment eval" OR scheming) since:2026-07-15
```

### Higher-signal subset

```text
list:{id} since:{bound} min_faves:5
```

Tune `min_faves` down if the list is low-engagement / research-quiet.

### Quote / debate surface

```text
list:{id} filter:quote since:{bound}
```

### Cut reply-only noise (optional)

```text
list:{id} -filter:replies since:{bound}
```

Use when the pulse is mostly "same" / short acks. Note in Gaps that pure replies
were de-emphasized. This is a root-discovery lane, not the end of conversation
retrieval; author self-threads and selected-root replies still need enrichment.

### Member self-threads

When a member's technical breakdown continues through self-replies:

```text
list:{id} filter:self_threads since:{bound}
```

Add topic tokens when focused. If the list operator and self-thread filter do
not compose in the host, identify the member/root from the list sample and
thread-fetch it.

### Selected conversation

After root selection, start with `x_thread_fetch`, then:

```text
conversation_id:{root_id}
```

Mode: Latest, floor-free. Conversation results are not list-scoped. Keep
member-authored nodes as list evidence; label other nodes outside-list context.
A root counts as enriched only after both the thread fetch and this floor-free
exact-conversation query complete. Under a normal budget, run the pair for the
best 2–3 of 2–5 shortlisted roots. Put completed checks with zero additive nodes
in Coverage, the search log, or Gaps rather than Key conversations.

If a material mid-thread node falls outside the Latest result cap:

```text
conversation_id:{root_id} since:{node_time_lower} until:{node_time_upper}
```

One modest engagement comparison is allowed after the floor-free pass:

```text
conversation_id:{root_id} min_faves:{small_N}
```

Never use it alone. Quiet technical replies often have zero likes.

### Top mode (optional, often empty)

```text
list:{id}
```

Mode: `Top`. If empty (common), **do not** abandon the skill - rank Latest results
by engagement yourself. Optionally try:

```text
list:{id} min_faves:1
```

with Top; still fall back to Latest ranking if empty.

### Semantic lane (optional)

`x_semantic_search` is **not** list-scoped. If you use it:

1. Search the natural-language topic.
2. Keep a post only if its author already appeared in your `list:{id}` Latest
   sample, **or** re-verify with a targeted Latest list query.
3. Prefer skipping semantic entirely when list Latest is already rich.

## Adaptive `since:` guidance

- **Breaking:** `since:` today (mentally filter to last hours via timestamps)
- **Same-day:** today and yesterday
- **Story:** ~last 3–7 days
- **Background:** ~7–14 days (up to ~30 for very quiet lists); still sort to newest coherent clusters

When Latest is flooded with low-substance replies, use `-filter:replies` for the
overview, select roots, then run exact conversation enrichment. Engagement
floors are a late precision lens only.

## Thread selection

Prefer fetching threads for posts that are:

1. Original research / technical writeups
2. Clear debate starters among members
3. Most specific evidence-bearing in-window originals
4. Clearest camp A and camp B posts on a live split
5. Corrective posts that change the read ("actually the paper says…")

Avoid spending the whole thread budget on ack replies and duplicate quote-RTs.
Do not promote a reply without its node ID/link, root relationship, text, and
member/outside-list label.
