---
name: dlresearch
description: >
  High-signal map of deep-learning research conversations on X: new papers,
  technical breakdown threads, author follow-ups, replications, critiques,
  missing ablations, and open questions. Use for /dlresearch in Grok, or when the
  user asks what serious ML researchers and practitioners are saying on X.
  Designed to find a few information-dense conversations inside noisy streams
  and reply trees. X is treated as the interpretation and discovery layer, not
  as proof that an underlying paper is correct. Grok Build only; requires
  native X tools.
metadata:
  short-description: "Deep-learning paper and research conversations on X"
---

# /dlresearch

Map the **few deep-learning research conversations that materially advance the
reader's understanding**. Favor technical anatomy, corrections, replications,
and limitations over virality, generic AI news, or paper-title aggregation.

This is Grok's X-native research skill. It intentionally has a narrower contract
than a general web or repository research skill.

## Host requirement

Require:

- `x_keyword_search`
- `x_semantic_search`
- `x_thread_fetch`
- `x_user_search`

If these tools are unavailable, stop and say that `/dlresearch` requires Grok
Build's native X tools. Do not simulate X results with web search.

## Read before searching

- `references/query-patterns.md` - search lattice and conversation recovery
- `references/source-seeds.md` - seed accounts and source-role model
- `references/failure-modes.md` - common false positives and reply failures

## Hard rules

1. **X is a commentary layer.** A post may identify, interpret, or criticize a
   paper; it does not verify the paper. Label claims as paper-author claim,
   independent interpretation, reported replication, or critique. Say
   `primary paper not checked in this X-only run` when applicable.
2. **Seeds are discovery priors, not an allowlist.** Named exemplars help find
   good roots and vocabulary. Promote other accounts when their role and
   contribution are explicit.
3. **Roots before replies.** Discover broadly, shortlist **2–5 load-bearing
   roots**, then fully enrich the best **2–3** under a normal budget. Never read
   every reply tree.
4. **Reply promotion requires information gain.** Keep author continuations,
   corrections, evidence additions, technical counterarguments, expert
   extensions, and clarifications/open boundaries. Drop praise, identity
   signaling, jokes, slogans, and duplicate summaries.
5. **Preserve the edge.** Every promoted non-root node needs its own ID/URL, the
   root ID/URL, relationship class, source role, independence label, why it
   changes the read, and caveat.
6. **Engagement is not evidence.** Use it to find visible roots or estimate
   prevalence only. Never require likes for a correction or multiply
   engagement into an evidence score.
7. **Separate prevalence from evidence weight.** Ten derivative summaries may
   show attention but add less evidence than one specific independent
   replication or one decisive methodological correction.
8. **Identity before synthesis.** Resolve the paper/report title, authors or
   lab, identifier/link if returned, and claimed contribution before merging
   posts about it. Do not fuse similarly named papers.
9. **Exact windows.** Honor user-fixed bounds. Prefer `within_time:Nh` for
   trailing hours when supported; otherwise validate returned timestamps.
   Older roots may be fetched only when an in-window node points to them, and
   must be labeled older context.
10. **Receipts, not reconstructions.** Quote only text returned by X tools.
    Never invent a post URL, paper title, result, number, or relationship.

## Research source roles

Classify authors per claim, not permanently:

| Role | Typical value | Main caveat |
|------|---------------|-------------|
| Paper or lab author | Contribution, method, results, intended boundary | Interested source; may omit weaknesses |
| Independent technical explainer | Connects method, prior work, implications | Interpretation, not replication |
| Peer expert | Correction, extension, field context | Expertise must be evident in the post/thread |
| Replicator / practitioner | Reproduction, implementation behavior, failure case | Check setup and comparability |
| Critic | Missing ablation, confound, evaluation or scaling objection | Prefer specific falsifiable critique |
| Aggregator / news account | Discovery and attention only | Low evidence weight unless it adds primary material |

A source can play different roles in different conversations. Preserve whether
a node is an **author continuation** or an **independent** voice.

## Pipeline

### Step 0 - Parse the ask and commit the window

Extract:

- topic, paper, author, lab, method, or open-ended scan
- exact window
- desired emphasis: paper anatomy, critiques, replications, implications,
  frontier themes, or all

Defaults:

- named recent paper/topic: last 30 days unless the user specifies otherwise
- open-ended `/dlresearch`: last 7 days, with a short 24-hour pulse first

State the committed window. Do not silently widen a user-fixed bound.

### Step 1 - Build anchors

For a named paper or topic, collect the smallest useful anchor set:

- exact title fragment or distinctive method name
- author/lab handles if known from X results
- paper/report identifier or returned link
- 2–5 technical aliases, benchmarks, or mechanism terms

For an open scan, use concrete research mechanisms and evaluation terms rather
than broad `AI`, `LLM`, or `AGI` alone.

### Step 2 - Broad root discovery

Use **4–7 calls**, stopping early when roots stabilize:

1. Lexical roots with title/method/author anchors and `-filter:replies`
2. `filter:self_threads` for technical seed accounts and paper authors
3. Constrained semantic search with the same date window
4. Paper/lab-author roots
5. Independent explainer, replication, and critique lanes
6. Quote-post lane when a root is being challenged or extended

`-filter:replies` is only a **root-discovery overview**. It is not a rule
against selected conversation enrichment.

Track the funnel:

```text
inspected → candidate roots → conversations enriched → promoted nodes
```

Deduplicate by post ID before counting.

### Step 3 - Shortlist 2–5 load-bearing roots

Rank candidates on separate axes:

- relevance to the user ask
- claim and mechanism specificity
- source role and proximity to the underlying work
- quantitative, methodological, code, benchmark, or experiment detail
- novelty, correction, disconfirmation, or limitation
- freshness inside the window

Use engagement only as a discovery prior. Prefer a set that covers roles:

1. paper/lab claim or closest primary pointer
2. best independent technical anatomy
3. strongest specific critique or missing ablation
4. replication/implementation evidence if available
5. a genuinely distinct implication or expert extension

Do not promote five paraphrases of the abstract.
Under a normal budget, fully enrich only the best **2–3** roots and reserve at
least two calls per fully enriched root.

### Step 4 - Enrich selected conversations

For each selected root, progress only as far as new information warrants:

1. `x_thread_fetch` on the root or important node.
2. Floor-free `conversation_id:{root_id}` Latest search.
3. `conversation_id:{root_id} filter:self_threads` for author continuations.
4. A local `since:`/`until:` box around a material mid-thread node.
5. One modest engagement-floor comparison only if useful.
6. `to:{root_author} filter:replies` only as fallback; post-filter exact
   returned `conversation_id == root_id`.

A root counts as an **enriched conversation** only after both steps 1 and 2
complete. A thread-only root remains a candidate. If a completed enrichment
yields no additive child or quote node, record the negative check in Coverage,
the search log, or Gaps rather than presenting a root-only row as a key
conversation.

Treat `in_reply_to_tweet_id:` as optional if the backend rejects it; do not
spend repeated calls on it.

Stop a conversation when:

- root, author continuation, and floor-free/local samples cover the substantive
  relation classes; or
- roughly 70% of newly returned IDs are duplicates and no new claim appears.

### Step 5 - Build the paper/conversation map

For each promoted paper or report, record:

| Field | Requirement |
|-------|-------------|
| Identity | Title/identifier/link only when returned; otherwise explicit unresolved label |
| Claimed contribution | What is reportedly new, with attribution |
| Conditions | Model, data, scale, benchmark, compute, or setting when stated |
| Mechanism | Why it might work, separated from measured result |
| Evidence on X | Author claim, technical interpretation, replication, critique |
| Limitations | Missing ablation, confound, generalization boundary, open question |
| Verification state | X-only pointer/commentary; primary source checked or not |

An unanswered question is a **lead**, not counterevidence. A critique is stronger
when it names the confound, missing control, or falsifying observation.

### Step 6 - Synthesize

Use the template below. Shrink the brief rather than padding a thin sample.
Normal budget: **10–14 X calls**, including **4–6 conversation calls** to fully
enrich the best **2–3** shortlisted roots.

## Output template

```markdown
# /dlresearch: {topic or "deep-learning research scan"}

**Window:** {exact human window} · as of {UTC}
**Scope:** X-native research conversations; primary papers {not checked | checked only where explicitly stated}
**Coverage:** ~{N inspected} → {N candidate roots} → {N conversations enriched}
→ {R promoted nodes} ({P} roots + {A} additive child/quote nodes); {N unique authors}
**Confidence:** {high|medium|thin} on conversation map; not a paper-validity judgment

## What changed
3–6 bullets on genuinely new papers, methods, evidence, or shifts in the debate.

## Key insights
| Insight | Source role | Evidence on X | Boundary / uncertainty |
|---------|-------------|---------------|------------------------|
| … | author / explainer / replicator / critic | … | … |

## Key conversations
| Root | Material node | Relation | Role / independence | Why it changes the read |
|------|---------------|----------|---------------------|-------------------------|
| [@root](root_url) · {root_id} | [@node](node_url) · {node_id} | correction / evidence / counterargument / extension | author continuation or independent {role} | … |

Include only material root-to-node edges. Put completed checks with zero
additive nodes in Coverage, the search log, or Gaps instead.

## Paper map
| Paper / report | Claimed contribution | Best technical read | Critique / missing evidence | Verification state |
|----------------|----------------------|---------------------|-----------------------------|--------------------|
| … | … | … | … | X commentary only |

## Themes and tensions
- **{theme}:** prevalence in this sample; strongest evidence for and against

## Receipts
- [@handle](url) · {post_id} · {role}
  > {verbatim load-bearing text}

  **Why it matters:** {one line}

## Gaps / next checks
- Missing role, unresolved identity, no replication, reply-tree limitation,
  time-zone/language bias, or primary paper that should be checked next
```

## Pre-flight checklist

- [ ] Native X tools present
- [ ] User topic and exact window committed
- [ ] Seed accounts treated as priors, not allowlist
- [ ] Primary-paper verification boundary explicit
- [ ] 4–6 conversation calls reserved for the best 2–3 shortlisted roots

## Post-synthesis checklist

- [ ] Coverage funnel reconciles unique IDs
- [ ] Only the best 2–3 of 2–5 shortlisted conversations fully enriched
- [ ] Enriched count includes only roots with thread fetch + floor-free exact-conversation search
- [ ] Root-only checks with zero additive nodes are in Coverage/Search log/Gaps, not Key conversations
- [ ] Every promoted node retains its root edge and own receipt
- [ ] Author continuation and independent evidence distinguished
- [ ] Paper claim, interpretation, replication, and critique not conflated
- [ ] Engagement not treated as evidence
- [ ] Prevalence and evidence weight reported separately
- [ ] No unsupported claim that a paper result was verified
