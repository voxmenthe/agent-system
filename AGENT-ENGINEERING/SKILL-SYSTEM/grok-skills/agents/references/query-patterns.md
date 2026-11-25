# X query patterns for `/agents`

Search for mechanisms, measurements, and failures. Broad category terms are
recall aids only; they should not define the final sample.

## Useful operators

| Operator | Use |
|----------|-----|
| `from:{handle}` | Seed builder or discovered maintainer |
| `filter:self_threads` | Builder continuation, benchmark method, postmortem |
| `filter:quote` | Replication, critique, or counterexample |
| `-filter:replies` | Root-discovery overview only |
| `conversation_id:{root_id}` | Selected reply tree |
| `within_time:Nh` | Exact trailing-hour window when supported |
| `since:` / `until:` | Calendar bounds and local time boxes |
| `min_faves:N` | Optional precision comparison, never evidence gate |

## Seed pulse

See `source-seeds.md`.

```text
(from:{seed_a} OR from:{seed_b}) since:{bound} -filter:replies
```

Always compare with:

```text
(from:{seed_a} OR from:{seed_b}) since:{bound} filter:self_threads
```

Sample one to three role-compatible seeds per call rather than placing every
seed in one large `OR`. Do not conclude the seeds are quiet from the root-only
query.

## Source-seed expansion

Use an exemplar's substantive self-threads, material replies, quote-post
neighborhood, and behavior-focused semantic search to generate a bounded
candidate set. Then verify recurrence in each candidate's own feed:

```text
from:{candidate} (agent OR harness OR eval OR benchmark OR trace OR sandbox OR
AGENTS.md OR CLAUDE.md) since:{bound} -filter:replies
```

```text
from:{candidate} (agent OR harness OR eval OR benchmark OR trace OR sandbox OR
AGENTS.md OR CLAUDE.md) since:{bound} filter:self_threads
```

Promote a durable seed only after at least two distinct substantive own-root
conversations in the committed window. Multiple nodes in one self-thread are
one event, and each root must independently pass the normal two-of-four gate:
procedure/config, measurement, failure/boundary, or inspectable artifact.
Separate close workflow matches from complementary maintainers, security
critics, and power users. A biography, employer, reputation, or repeated
product announcements do not satisfy recurrence.

## Mechanism lanes

### Evals and harnesses

```text
(agent OR coding) (eval OR benchmark OR grader OR verifier OR trajectory OR
defect OR contamination OR cheating OR harness) since:{bound} -filter:replies
```

### Context, memory, and orchestration

```text
(agent OR coding) (context OR memory OR compaction OR checkpoint OR handoff OR
delegation OR orchestration OR subagent) since:{bound} -filter:replies
```

### Permissions, sandboxes, and failure recovery

```text
(coding agent OR agentic) (permission OR sandbox OR secret OR rollback OR
recovery OR destructive OR worktree OR hook) since:{bound} -filter:replies
```

### Cost and reliability

```text
(coding agent OR harness) (turns OR latency OR tokens OR cost OR reliability OR
success rate OR failure rate) since:{bound} -filter:replies
```

Split long examples into smaller queries. Add the user-named tool/model/task.

## Artifact and benchmark lane

```text
(agent OR coding) (github OR repo OR benchmark OR skill OR config OR trace OR
"open source") since:{bound} -filter:replies
```

An artifact is a lead. Search quote posts and exact conversations for
independent exercise, implementation boundaries, or benchmark flaws.

## Correction and replication lane

```text
("{tool_or_practice}") (tried OR reproduced OR failed OR bug OR regression OR
counterexample OR "does not work" OR caveat) since:{bound}
```

```text
"{tool_or_benchmark}" filter:quote since:{bound}
```

Prefer concrete task/config/measurement details over verdicts.

## Semantic prompts

Useful constrained prompts:

```text
agentic coding practices with concrete procedures, evaluations, traces, or failure modes
```

```text
technical criticism or independent replication of coding-agent harness and evaluation claims
```

Post-filter generic product announcements, job posts, and model-team slogans.

## Progressive conversation recovery

Shortlist only 2–5 roots. Under a normal budget, fully enrich the best 2–3:

1. `x_thread_fetch(root_or_material_node)`
2. floor-free `conversation_id:{root_id}` Latest
3. `conversation_id:{root_id} filter:self_threads`
4. local time box around a correction, benchmark detail, or replication
5. optional modest `min_faves` comparison
6. fallback `to:{root_author} filter:replies`, then exact conversation-ID filter

A root counts as enriched only after both steps 1 and 2 complete. A thread-only
root remains a candidate. A completed check with zero additive nodes belongs in
Coverage, the search log, or Gaps, not the Key conversations table.

Do not repeatedly retry `in_reply_to_tweet_id:` after a backend error.

Classify useful nodes as author follow-up, correction, user replication,
evidence/artifact addition, technical counterargument, expert extension, or
clarification/open boundary.

## Root promotion rubric

Rank separate axes:

- procedural/config specificity
- measured outcome and evaluation setup
- named failure/boundary
- inspectable artifact/trace
- independent replication/correction
- relevance and freshness

The normal actionable gate is any two of: procedure, measurement, failure
boundary, artifact. Engagement is neither a gate nor a multiplier.

## Stop rules and search log

Stop broad search when 2–5 roots cover builder practice, evidence, and
failure/counterevidence, or when new queries mostly repeat IDs and generic
claims. Stop a reply tree at ~70% duplicate new IDs with no information gain.

Log lane, query/root ID, approximate returned count, new unique IDs, kept roots
or nodes, and drop reason.
