---
name: simplify-audit
description: Audit unnecessary complexity when requested, or when an affected repository plan or design shows concrete burden such as duplicated policy or unjustified lifecycle stages. Keep proactive work scoped; do not use for ordinary diff review or automatic cleanup.
---

# Simplify audit

Audit retained or proposed machinery across a repository or a repository-owned
plan or design. On its own, this skill is read-only and produces proposals. If
a separate user request already authorizes a plan or design edit, apply this as
a decision lens inside that workflow; this skill grants no additional write
authority.

For proactive use, first name a concrete burden already observed in the affected
feature, plan, or design: for example, competing owners of the same policy or a
lifecycle stage with no supported obligation. A keyword, several files, or the
mere presence of an abstraction is not a trigger. Reuse current inspection and
keep the audit inside that affected boundary; a wider repository audit requires
that scope in the request. Stop once the supported question is settled. Do not
append an audit to an otherwise sufficient review or invent a separate report
when a concise decision inside the owning task suffices.

## Default to the direct path

Prefer elegant simplicity: the fewest concepts, states, policies, owners, and
handoffs that satisfy the current contract. The smallest credible direct path
is the baseline, not merely one option to rank. Every extra lifecycle stage,
gate, artifact, handoff, compatibility path, or abstraction carries the burden
of proof.

For planned and existing machinery:

1. State the required outcome and invariants.
2. Construct the shortest direct delivery and ownership path that preserves
   them.
3. Inventory each mechanism added beyond that path and its continuing
   coordination cost.
4. For each addition, identify the concrete failure or supported obligation it
   prevents, cite the evidence that makes the risk credible, and compare it
   with direct delivery plus proportionate validation, rollback,
   observability, and dogfooding.
5. Propose removing or collapsing the addition unless it provides material
   protection the simpler path cannot.

Do not add or preserve an experimental lane, promotion stage, shadow path,
parallel artifact, or standing approval gate merely to manage ordinary,
recoverable uncertainty. Prefer a direct, reversible, observable production
path and learn from use. Keep only the smallest guard needed when the direct
path would expose a credible irreversible failure, safety or data-integrity
risk, unsupported mixed-version state, external one-way effect, or supported
compatibility obligation.

## Evidence boundary

Before proposing removal or consolidation, inspect:

- current usage, reachability, and load paths;
- planned lifecycle states, gates, artifacts, and owner handoffs;
- dependency, ownership, and configuration graphs;
- history, change hotspots, and synchronized-change burden;
- public, persisted, wire, compatibility, and mixed-version boundaries;
- generated, deployment, recovery, and observability surfaces; and
- deletion impact, proportional validation, rollback, and any required
  observation window.

This skill does not authorize editing, deleting, restoring, staging,
committing, installing, or publishing. A separately authorized owning
workflow may apply accepted findings within its own scope. Do not infer
absence from one search. Account for hidden entry points and dynamic loading
when the repository uses them. Treat unknown reachability as a verification
gap, not as dead code.

## Output

Lead with the smallest coherent operating model. Then identify:

- machinery to remove or collapse, with burden, evidence, known consumers,
  uncertainty, replacement, and verification;
- retained exceptions, each with the concrete boundary it protects, why the
  direct path is insufficient, and the minimum safeguard required;
- preserved behavior, safety, data, compatibility, recovery, deployment, and
  observability invariants; and
- remaining unknowns and the narrowest fact-finding needed to resolve them.

Rank proposed cuts by conceptual reduction and confidence, not line or
dependency count. Do not present extra machinery as a co-equal option when it
has not met its burden of proof.

Use the same deep-module and justified-complexity tests as bounded
simplification. One implementation can still own a valuable stable invariant.
Similar syntax is not duplication without duplicated policy or synchronized
change. A thin adapter can be load-bearing at a host or protocol boundary.

Keep findings within the declared repository or plan/design scope. Do not turn
an ordinary changed-code review into a debt hunt, and do not omit a valid
no-change result.
