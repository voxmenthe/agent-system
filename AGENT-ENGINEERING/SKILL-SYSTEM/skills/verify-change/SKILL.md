---
name: verify-change
description: Assess a bounded change against its accepted outcome and invariants. Use when a nontrivial or high-impact result needs structured acceptance across important behavior, boundaries, or uncertain builder evidence. Reuse sufficient current proof. Do not use for tiny edits settled by a direct check, routine test execution, implementation, or general defect review.
---

# Verify a change against its contract

Establish whether the actual result satisfies the accepted outcome. A builder summary is a claim set, not proof; inspect the relevant artifact and the evidence supporting each material claim.

## Boundaries

- State the evidence mode: **self-check** when the builder checks its own work; **independent verification** when a non-author reviewer reconstructs the contract and assesses the artifact and evidence without adopting the builder's conclusion. An adversarial stance or fresh context alone does not make an author independent.
- Honor an explicit independent-review requirement; self-checks cannot satisfy it. This skill alone does not require spawning a reviewer or adding a new workflow stage.
- Skip this skill for a trivial or tiny low-impact edit when one direct check is
  proportionate, or a request merely to run a known test command. A small change
  to an important invariant can still warrant structured acceptance.
- This verification pass is read-only. Return any needed fix to the existing authorized implementation workflow; verification neither expands nor cancels that authority.
- Never claim a command, test, runtime exercise, or negative case that was not actually performed.
- Do not commit, push, publish, deploy, or broaden authority.

## Workflow

1. Resolve the accepted outcome, invariants, repository instructions, actual change target, and relevant surrounding behavior. The user's request can be the contract; do not demand a separate contract document.
2. Map the material acceptance criteria to existing evidence. Bind it to the tested revision or artifact, inputs, command, environment, and result as needed to establish applicability. A test on another build, unexplained success claim, or stale log is not proof of this result.
3. Reuse attributable evidence when it covers the same artifact and material conditions and is sufficient for the claim. Read its results and assess what the check can actually falsify. Do not repeat tests or runtime exercises merely to produce a new packet; rerun only for changed inputs, stale or unverifiable provenance, failures, or a remaining risk seam. Independently assessed evidence need not be independently rerun.
4. Inspect the load-bearing path and close the remaining gaps with the narrowest sufficient checks. Cover changed contracts, invariants, errors, side effects, and recovery or observability where material. Include a relevant negative case capable of falsifying the key assumption; reuse one already evidenced when sufficient. Static inspection cannot stand in for runtime proof that the contract needs.
   Use the target's actual recipe and follow its actions through the claimed
   result, including persisted state or downstream artifacts when material.
   If a missing/stale tool prevents proof, identify the creation or maintenance
   work needed. Keep those local writes outside this read-only pass under the
   task's existing authority; do not force a three-skill pipeline or a new
   permission question for work already authorized.
5. Keep acceptance verification distinct from `diff-review`'s defect hunt. Reuse an applicable review's scope and findings; investigate only issues that affect acceptance or evidence validity, without starting a second general review. Account for material scope drift, assumptions, and break/change blast radius.
6. Distinguish observations made now, prior evidence inspected but not rerun, unsupported builder reports, inferences, and behavior still unverified. Stop checking once sufficient evidence covers the bounded contract.
7. Choose one disposition: **Accept**, **Revise**, **Return to design**, or **Restart**. Acceptance describes this contract and evidence mode, not permission to publish.

## Evidence packet

Return a compact result, linking existing evidence instead of duplicating logs:

- Target identity, evidence mode, and disposition
- Result by material acceptance criterion, including relevant negative-case and recovery evidence
- Checks performed now versus evidence reused, with pointers and results
- Material scope or contract deviations, assumptions, remaining risks, and unverified behavior
- Smallest corrective action when not accepted

For example, for a report whose acceptance asked for three named charts:

```text
Target: X-RESULTS/INTEGRATED/<report>.html, sha256:3f2a…, built by `mkt publish` at 14:02
Evidence mode: self-check. Disposition: Revise.
- Publishes once without overwriting: Passed (test_run_state, run now)
- Three charts present: Passed (preflight: three <img>, every file exists)
- Charts decode: Passed (each parses as a 1600×900 PNG)
- Charts show the 10-year yield, the curve, the Fed path: Failed (looked at each; the third repeats the first)
- Reads at phone width: Unverified (no browser check run)
Smallest correction: regenerate the Fed-path chart, then reopen it.
```

Keep the three image checks apart: a file can exist without decoding, and
decode without showing what was asked; only looking at the artifact checks
the third.

## Stop conditions

- Acceptance criteria remain materially ambiguous or contested after inspecting the request and available context.
- Required runtime evidence needs unavailable authority or credentials.
- The implementation changed a public contract or risk class without approval.
- Evidence shows a structurally wrong trajectory; return to design or restart instead of accumulating patches.

Report the specific gap and continue independent authorized work. Do not add a permission checkpoint when the existing request already authorizes the next step.
