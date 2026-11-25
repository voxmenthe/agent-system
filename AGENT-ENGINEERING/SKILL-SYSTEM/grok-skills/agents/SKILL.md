---
name: agents
description: >
  High-signal X research on building agents and agentic coding systems:
  harnesses, evals, context and memory, orchestration, tools, permissions,
  sandboxes, debugging, checkpoints, and human workflows. Use for /agents in
  Grok, or when the user asks for actionable agent-building practices and the
  best technical conversations on X. Designed to extract procedures,
  measurements, failure boundaries, artifacts, corrections, and replications
  from noisy streams and reply trees. Grok Build only; requires native X tools.
metadata:
  short-description: "Actionable agent-building practices and conversations on X"
---

# /agents

Find the **few conversations that can change how someone builds, evaluates, or
operates an agentic system**. Prefer inspectable practices and failure evidence
over product enthusiasm, screenshots, model fandom, or generic “agents are the
future” posts.

## Host requirement

Require:

- `x_keyword_search`
- `x_semantic_search`
- `x_thread_fetch`
- `x_user_search`

If unavailable, stop and explain that `/agents` requires Grok Build's native X
tools. Do not synthesize supposed X consensus from web results.

## Read before searching

- `references/query-patterns.md` - mechanism-first discovery and reply recovery
- `references/source-seeds.md` - seed accounts, roles, and promotion gates
- `references/failure-modes.md` - hype, benchmark, and conversation traps

## Hard rules

1. **Actionability gate.** A promoted practice normally satisfies at least
   **two** of:
   - reproducible procedure or configuration
   - measurable outcome or evaluation
   - named failure mode, tradeoff, or boundary
   - inspectable artifact, benchmark, repository, or trace
2. **Model × harness × task.** Do not rank models abstractly from agent results.
   Preserve the model/version, harness/tools/prompting, task/eval, and relevant
   constraints whenever stated.
3. **Seeds are priors, not an allowlist.** Use named builders to discover
   vocabulary and roots. Promote other sources by role and contribution.
4. **Roots before replies.** Discover broadly, shortlist **2–5 load-bearing
   roots**, then fully enrich the best **2–3** under a normal budget. Do not
   sweep every reply tree.
5. **Reply promotion requires information gain.** Keep author follow-ups,
   corrections, replications, evidence additions, technical counterarguments,
   expert extensions, and clarified boundaries. Drop praise, dunking, sales
   replies, model-team slogans, and duplicates.
6. **Preserve the edge.** Every promoted reply or quote node needs its own
   ID/URL, root ID/URL, relation, source role, independence, what changed, and
   caveat.
7. **Engagement is discovery, not evidence.** A quiet bug report or maintainer
   correction can outweigh a viral demo. Report prevalence separately.
8. **Artifact does not equal validation.** A linked repo, skill, benchmark, or
   trace makes a claim inspectable, not necessarily correct. State whether the
   X run observed a report, an independent use, a correction, or only an
   announcement.
9. **Exact windows.** Honor user-fixed time bounds. Prefer `within_time:Nh`
   when supported; otherwise validate timestamps. Label older roots fetched
   only to explain in-window discussion.
10. **No invented operational detail.** Quote only returned X text. Never
    reconstruct configs, benchmark scores, repository links, or post edges.

## Source roles

Assign roles per claim:

| Role | Typical value | Main caveat |
|------|---------------|-------------|
| Builder report | Procedure, architecture, trace, observed failure | Interested source; selection effects |
| Maintainer / repository evidence | Implementation boundary, issue, benchmark setup | Project-specific; artifact still needs inspection |
| User replication | Independent attempt, transferability, failure report | Setup may differ |
| Independent critic | Confound, benchmark weakness, unsafe shortcut | Prefer concrete mechanism and counterexample |
| Correction / boundary voice | Version, cost, permissions, reliability caveat | May be narrow but high information gain |
| Product announcement | Availability and intended capability | Low practice/evidence weight without details |

One person can occupy multiple roles. Author self-threads remain one source
chain; they are not independent corroboration.

## Practice domains

Route discoveries into one or more:

- harness and tool interface
- evaluation, graders, verifiers, anti-cheating, and task design
- context, memory, compaction, and checkpointing
- orchestration, delegation, planning, and concurrency
- permissions, sandboxing, secrets, and destructive-action safety
- debugging, observability, traces, and failure recovery
- repository/worktree/CI workflow
- human review, specification, and handoff
- latency, token, cost, and reliability tradeoffs

## Pipeline

### Step 0 - Parse the ask and commit the window

Extract:

- practice domain, tool/harness, model, benchmark, or open scan
- exact window
- desired output: quick practices, conversation map, debate, evaluation
  comparison, failure analysis, or all

Defaults:

- named topic/tool: last 30 days unless specified
- open `/agents`: last 7 days, with a 24-hour pulse first

### Step 1 - Build mechanism anchors

Use concrete mechanism terms, not category hype:

- eval, grader, verifier, trajectory, defect, benchmark, contamination
- harness, tool call, permission, sandbox, worktree, hook, checkpoint
- context, memory, compaction, handoff, plan, delegation
- turns, latency, token, cost, reliability, recovery, rollback

Add the user-named tool, model, or task. Keep query groups small.

### Step 2 - Broad root discovery

Spend **4–7 calls**, stopping when roots stabilize:

1. Seed-account roots and `filter:self_threads`
2. Mechanism + domain keyword roots with `-filter:replies`
3. Constrained semantic search over the same window
4. Artifact/benchmark/trace lane
5. Failure/correction/replication lane
6. Quote-post lane for substantive counterexamples

`-filter:replies` is a **root overview**, not a complete evidence universe.

Track:

```text
inspected → candidate roots → conversations enriched → promoted nodes
```

Deduplicate by ID and keep author chains distinct from independent voices.

### Step 3 - Shortlist 2–5 load-bearing roots

Rank separate axes:

- relevance to the requested workflow
- procedural/configuration specificity
- measurement and evaluation quality
- named failure mode or operating boundary
- inspectable artifact, benchmark, trace, or issue
- independent replication/correction
- novelty and freshness

Use engagement only to find visible roots or describe attention. Favor a set
that covers:

1. strongest builder procedure
2. best measured result or inspectable eval
3. strongest failure/correction/counterexample
4. independent use or maintainer boundary
5. genuinely distinct practice domain when useful

Under a normal budget, fully enrich only the best **2–3** roots and reserve at
least two calls per fully enriched root.

### Step 4 - Enrich selected conversations

For each selected root:

1. `x_thread_fetch` root or material node.
2. Floor-free `conversation_id:{root_id}` Latest.
3. `conversation_id:{root_id} filter:self_threads` for author continuations.
4. Local timestamp box around a material correction or benchmark discussion.
5. Optional modest engagement-floor comparison, never alone.
6. `to:{root_author} filter:replies` only as fallback; retain exact returned
   `conversation_id == root_id`.

A root counts as an **enriched conversation** only after both steps 1 and 2
complete. A thread-only root remains a candidate. If a completed enrichment
yields no additive child or quote node, record the negative check in Coverage,
the search log, or Gaps rather than presenting a root-only row as a key
conversation.

Treat `in_reply_to_tweet_id:` as optional when the backend rejects it.

Classify retained nodes:

- author follow-up
- correction
- user replication
- evidence/artifact addition
- technical counterargument
- expert extension
- clarification/open boundary

Stop when substantive relation classes are covered or roughly 70% of new IDs
are duplicates without a new claim.

### Step 5 - Build practice cards

For each promoted practice, record:

| Field | Requirement |
|-------|-------------|
| Practice | Concrete action, configuration, or workflow |
| Problem | Failure or constraint it addresses |
| Evidence on X | Measurement, trace, artifact, report, correction, replication |
| Context tuple | Model/version × harness/tools × task/eval × constraints |
| Cost / risk | Latency, tokens, complexity, permissions, brittleness, review burden |
| Boundary | Where it failed, remains unknown, or should not generalize |
| Confidence | Announcement / builder report / independently exercised / contested |

If fewer than two actionability criteria are present, demote the item to
**watchlist**, **theme**, or **open question** rather than an actionable practice.

### Step 6 - Synthesize

Use the template below. Normal budget: **10–14 X calls**, including **4–6
conversation calls** to fully enrich the best **2–3** shortlisted roots. Shrink
claims when the sample is thin.

## Output template

```markdown
# /agents: {topic or "agent-building practices scan"}

**Window:** {exact human window} · as of {UTC}
**Coverage:** ~{N inspected} → {N candidate roots} → {N conversations enriched}
→ {R promoted nodes} ({P} roots + {A} additive child/quote nodes); {N unique authors}
**Scope:** X-native reports and conversations; linked artifacts not independently inspected
**Confidence:** {high|medium|thin}

## What changed
3–6 bullets on new practices, measurements, failures, or changed consensus.

## Actionable practices
| Practice | Problem addressed | Evidence / artifact on X | Model × harness × task | Boundary / cost |
|----------|-------------------|--------------------------|------------------------|-----------------|
| … | … | … | … | … |

## Key conversations
| Root | Material node | Relation | Role / independence | Why it changes the read |
|------|---------------|----------|---------------------|-------------------------|
| [@root](root_url) · {root_id} | [@node](node_url) · {node_id} | correction / replication / evidence / counterargument | author follow-up or independent {role} | … |

Include only material root-to-node edges. Put completed checks with zero
additive nodes in Coverage, the search log, or Gaps instead.

## Practice map
| Domain | High-signal theme | Evidence weight | Prevalence in this sample |
|--------|-------------------|-----------------|---------------------------|
| evals / harness / context / safety / workflow / cost | … | … | … |

## Tensions and counterevidence
1. **{tension}:** strongest case on each side; what would resolve it

## Watchlist
Promising but below the two-of-four actionability gate.

## Receipts
- [@handle](url) · {post_id} · {role}
  > {verbatim load-bearing text}

  **Why it matters:** {one line}

## Gaps / next checks
- Missing configuration, task mismatch, uninspected artifact, absent
  replication, reply-tree limitation, window/language bias
```

## Pre-flight checklist

- [ ] Native X tools present
- [ ] Topic and exact window committed
- [ ] Mechanism anchors chosen; broad hype terms avoided
- [ ] Seeds treated as priors, not allowlist
- [ ] 4–6 conversation calls reserved for the best 2–3 shortlisted roots

## Post-synthesis checklist

- [ ] Funnel counts reconcile unique IDs
- [ ] Enriched count includes only roots with thread fetch + floor-free exact-conversation search
- [ ] Root-only checks with zero additive nodes are in Coverage/Search log/Gaps, not Key conversations
- [ ] Each actionable practice passes at least two of four gates
- [ ] Model × harness × task preserved where available
- [ ] Artifact report not mislabeled independent validation
- [ ] Every promoted node retains its root edge
- [ ] Author continuation and independent evidence distinguished
- [ ] Engagement and prevalence separated from evidence weight
- [ ] Thin or contested claims are labeled
