---
name: simplify-review
description: Review one concrete diff for safe simplification of retained complexity when explicitly requested; diff-review owns general reviews merely mentioning accidental complexity. Do not use for automatic cleanup, line-count reduction, or repository-wide audits.
---

# Simplify review

Give read-only advice about one frozen change. The goal is less retained
complexity with the complete accepted contract preserved, not shorter code.

## Boundary

Resolve the exact diff and read its owners, callers, tests, docs, and relevant
history. Do not edit, delete, restore, stage, commit, install, publish, or
broaden the target. This is a focused simplification lens, not a substitute for
full correctness, security, concurrency, migration, or compatibility review.

## Method

For each candidate cut, prove:

1. the current observable burden in concepts, state, policy, layers, call
   hops, configuration, dependencies, or operations;
2. that the machinery is not required by a contract, consumer, framework,
   safety boundary, or credible irreversible failure mode;
3. a concrete smaller replacement;
4. the behavior, safety, data, compatibility, recovery, and observability
   invariants it preserves; and
5. the check that would falsify the proposal.

Prefer keeping justified structure; deleting dead or speculative behavior;
reusing the owning repository layer; platform or standard library behavior;
an existing dependency that genuinely owns the problem; then the smallest
local implementation. Generalize only when several concrete cases become
simpler with less coupling.

Duplication requires duplicated policy or synchronized-change burden. A
wrapper is removable only when it owns no stable policy or boundary.
Validation is removable only when the owning boundary proves the invariant.
Compatibility must account for persisted formats, public APIs, wire contracts,
external consumers, mixed versions, and rollback. A type or module can be
justified by one implementation when it consolidates an invariant or reduces
caller knowledge.

Do not optimize lines, branches, dependencies, abstractions, or files as raw
counts. Do not move the same state burden into helpers, registries, factories,
or configuration and call it simpler.

## Output

Rank only supported proposals. Each gives the current burden, evidence,
smaller replacement, preserved safeguards, and verification. End with a
compact summary of complexity removed, safeguards retained, and validation
required. If nothing useful can be removed, say so without filler.
