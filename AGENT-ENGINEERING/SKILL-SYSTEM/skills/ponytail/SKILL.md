---
name: ponytail
description: Use only when the user explicitly requests the smallest practical implementation or design for a bounded coding task. Do not use for review, audit, acceptance verification, Review Scan interpretation, or as an automatic posture for every coding task.
disable-model-invocation: true
---

# Ponytail

Build the least machinery that fully satisfies the accepted contract.
Simplicity never weakens correctness, safety, data integrity, compatibility,
or truthful evidence.

## Boundary

Use this skill only for an explicit implementation or design request. It does
not own review findings, whole-repository audits, acceptance verification,
publication, commits, deployment, or external effects. Follow the task's
existing authority and repository policy.

## Method

1. State the required behavior, invariants, and credible failure modes.
2. Ask whether code or a new abstraction is necessary.
3. Prefer deleting the need, existing repository ownership, platform or
   standard library behavior, then an existing dependency that truly owns the
   problem.
4. Otherwise implement the smallest local coherent behavior behind the
   narrowest stable interface.
5. Generalize only when at least three concrete cases become simpler with less
   coupling.
6. Preserve validation, concurrency, persistence, compatibility, rollback,
   and observability machinery when it protects a demonstrated boundary.
7. Verify behavior and negative paths in proportion to risk; do not use a
   blanket one-test minimum or line-count target.

Fewer lines, files, layers, or dependencies are secondary signals. A direct
solution is worse when it hides required state, errors, or irreversible
failure. A deep module with one implementation is valid when it consolidates a
stable invariant or makes callers substantially simpler.

Report the chosen minimal shape, what was deliberately omitted, the safeguards
retained, and the evidence run. Stop when the bounded contract is satisfied.
