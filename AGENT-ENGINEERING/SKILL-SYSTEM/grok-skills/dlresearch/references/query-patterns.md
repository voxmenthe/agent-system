# X query patterns for `/dlresearch`

Use lexical anchors for precision, semantic search for recall, and exact
conversation queries only after selecting roots. Keep one variable loose per
query; giant keyword piles hide which term found the result.

## Useful operators

| Operator | Use |
|----------|-----|
| `from:{handle}` | Paper/lab author or seed-account lane |
| `"exact title fragment"` | Paper identity and direct discussion |
| `filter:self_threads` | Author/explainer continuations; load-bearing for breakdown threads |
| `filter:quote` | Independent framing, criticism, and replication |
| `-filter:replies` | Root-discovery overview only |
| `conversation_id:{root_id}` | Exact selected conversation |
| `within_time:Nh` | Trailing-hour window when supported |
| `since:` / `until:` | Calendar bounds and local reply time boxes |
| `min_faves:N` | Optional precision comparison, never the only reply lane |

If an operator fails, simplify once. Do not invent syntax or repeatedly retry a
backend-rejected `in_reply_to_tweet_id:` query.

## Page cap and time splits

The page limit is 10; asking for more does nothing. When a Latest page returns
10, split the window before concluding anything from it: two-day blocks for
discovery, one-day blocks for a handle. Over a week, small Latest pages
otherwise collapse onto the last day or two.

## Open research pulse

Prefer mechanism and evaluation terms:

```text
(pretraining OR posttraining OR reasoning OR distillation OR interpretability
OR mechanistic OR "test-time compute" OR "scaling law" OR benchmark OR ablation
OR replication OR "technical report") since:{bound} -filter:replies
```

Split this into 2–3 smaller queries in practice. Pair with a semantic prompt:

```text
new deep learning papers with concrete methods, experiments, replications, or technical critiques
```

Broad `AI`, `AGI`, `LLM`, or `agents` alone is too noisy.

## Named paper or method

```text
"{distinctive title fragment}" since:{bound} -filter:replies
```

```text
("{method name}" OR "{benchmark}" OR "{paper identifier}") since:{bound}
```

```text
(from:{author_handle} OR from:{lab_handle}) ("{method}" OR "{title fragment}") since:{bound}
```

After resolving a likely author:

```text
from:{author_handle} since:{bound} filter:self_threads
```

## Technical breakdown lane

Seeds are in `source-seeds.md`.

```text
from:{seed_handle} since:{bound} filter:self_threads
```

Add a title/method anchor when topic-specific. Do not require
`-filter:replies`: exemplar breakdowns may be stored as self-thread
continuations that the root-only lane misses.

To pulse several seeds at once, batch at most four handles:

```text
(from:{a} OR from:{b} OR from:{c} OR from:{d}) -filter:replies since:{bound} until:{bound}
```

The parentheses are required. Without them X applies the bounds and filter to
the last handle only, and the other handles come back from any date; on
2026-11-19 seven such roster pages hid about 15 seeds' activity.

For a seed whose row in `source-seeds.md` says the signal is reply-shaped, add
`from:{handle} filter:replies` in one- or two-day bounds. Multi-day `from:`
pages missed known posts that one-day bounds returned.

## Source-seed expansion

When discovering similar technical posters, keep two phases separate.

**Candidate discovery:** inspect an exemplar's substantive self-threads,
material replies, and quote-post neighborhood. Pair that with a semantic search
for repeated behavior, such as:

```text
authors who repeatedly explain deep-learning papers with methods, experiments,
numbers, limitations, or technical critiques
```

These lanes produce leads only. Validate each candidate against their own feed:

```text
from:{candidate} (paper OR method OR benchmark OR ablation OR replication OR
experiment) since:{bound} -filter:replies
```

```text
from:{candidate} (paper OR method OR benchmark OR ablation OR replication OR
experiment) since:{bound} filter:self_threads
```

Promote a durable seed only after finding at least two distinct substantive
own-root conversations in the committed window. Multiple nodes in one
self-thread count as one event. Each qualifying root should contain at least
two of: method/conditions/numbers, code or experiment, baseline or ablation,
and limitation/confound/falsifier. Label close behavioral matches separately
from complementary authors, replicators, or critics.

## Replication and critique lanes

Use specific evidence vocabulary:

```text
("{paper_or_method}" OR "{benchmark}") (replicate OR reproduced OR implementation
OR code OR checkpoint OR "did not reproduce" OR ablation) since:{bound}
```

```text
("{paper_or_method}") (confound OR leakage OR baseline OR ablation OR
"evaluation setup" OR limitation OR failure) since:{bound}
```

For quote reactions:

```text
"{paper_or_method}" filter:quote since:{bound}
```

Semantic equivalents are useful, but post-filter for direct technical content.

## Progressive conversation recovery

Shortlist only 2–5 roots. Under a normal budget, fully enrich the best 2–3:

1. `x_thread_fetch(root_or_material_node)`
2. `conversation_id:{root_id}` in Latest, no engagement floor
3. if step 2 is empty, or misses children the thread fetch or another query
   already showed: `to:{root_author} since:{bound} until:{bound}` next, before
   semantic search or other lanes; retain exact conversation ID only
4. `conversation_id:{root_id} filter:self_threads`
5. local `since:{day} until:{day}` or timestamp inspection around a material node
6. optional `conversation_id:{root_id} min_faves:2` as a precision comparison

A root counts as enriched only after both steps 1 and 2 complete. A thread-only
root remains a candidate. A completed check with zero additive nodes belongs in
Coverage, the search log, or Gaps, not the Key conversations table.

The floor-free lane protects quiet corrections. The self-thread lane protects
technical continuations. `to:` is contaminated across roots unless post-filtered.

An under-cap page is not proof of silence. Time-boxed and floor-free
`conversation_id:` pages, multi-day `from:{handle}` pages, and time-boxed reply
pages all missed posts already returned elsewhere on 2026-11-19, while bounded
`to:{root_author}` recovered replies that `conversation_id:` returned empty. A
query family that missed a known post in this run cannot support a silence
claim for that thread or handle; label the miss a known-matching miss.

## Query stopping rules

Stop broad discovery when:

- 2–5 roots cover primary claim, independent anatomy, and critique/replication;
- a new query mostly repeats known IDs or abstract paraphrases; or
- the window is genuinely quiet.

Stop a reply tree when roughly 70% of new IDs are duplicates and no new
substantive relation class appears.

## Search log fields

Track:

| Field | Example |
|-------|---------|
| Lane | paper author / breakdown / critique / replication / conversation |
| Query or root ID | exact query text or ID |
| Returned | approximate count |
| New unique IDs | count after dedupe |
| Kept | candidate roots or promoted nodes |
| Drop reason | duplicate / vague / social / wrong paper / outside window |
