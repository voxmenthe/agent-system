---
name: implement-change
description: Implement one settled, bounded vertical slice under current repository policy, tests, and authority. Use when the change contract and slice are clear and implementation is authorized. Do not use for an obvious tiny edit that needs no workflow, an unsettled outcome or interface, open-ended redesign, independent review, or publication.
disable-model-invocation: true
---

# Implement one bounded slice

Make the approved behavior real with the smallest coherent diff and inspectable evidence. This skill owns implementation of one slice; it does not authorize a wider contract, a commit, or publication.

## Preconditions and boundaries

- The outcome, slice, invariants, authority, and stop conditions are settled enough to act.
- Skip this skill for a trivial or tiny edit when the direct repository workflow is clearer.
- Read the complete target, callers, dependents, focused tests, documentation, and relevant history before changing it.
- Follow active policy packs and repository instructions.
- Do not automatically commit, push, publish, deploy, run a full suite, or invoke review ceremony.

## Workflow

1. Restate the approved slice, invariants, effect boundary, verifier, and stop conditions.
2. Inspect the worktree and preserve unrelated work.
3. For a bug, establish a regression assertion that fails before the fix unless genuinely impossible, and test the rule the bug broke, not only its input. For new behavior, take the expected behavior from the accepted outcome and contract, not from the candidate algorithm, and define the boundary assertion before or with implementation.
4. Implement only the one approved vertical slice. Keep core logic pure and side effects explicit where the existing design permits.
5. Fail loudly at violated boundaries; do not hide required data or configuration behind silent defaults.
6. Run the narrowest sufficient checks for the changed behavior. Expand validation only when risk or discovered coupling warrants it.
7. Review the diff for scope, accidental churn, hidden contract changes, error paths, and source-of-truth drift. Remove any new abstraction, dependency, configuration surface, compatibility path, or test helper that the accepted outcome does not need.
8. Report changed behavior, performed verification, observed results, assumptions, and unverified runtime behavior.

## Stop conditions

Stop and return to the appropriate decision layer when:

- the contract, risk class, authority, or coherent change surface materially expands;
- repository evidence invalidates a premise;
- a public API, persistent format, permission model, or migration needs an unapproved decision;
- the slice is no longer independently runnable or reviewable;
- unrelated areas must change without a demonstrated causal reason;
- two repairs address symptoms without reducing the underlying failure; or
- recovery becomes unclear.

Do not begin the next slice. Do not commit or publish unless the user separately invokes the authorized Git edge.

## Handoff

Provide a concise builder evidence packet. It is a claim set for independent verification, not self-certification.
