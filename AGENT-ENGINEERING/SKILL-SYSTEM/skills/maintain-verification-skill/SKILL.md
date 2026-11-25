---
name: maintain-verification-skill
description: Repair and re-drive an existing target-local verification recipe and its owned helpers. Use when a nontrivial or high-impact change or demonstrated harness drift materially affects its commands, fixtures, interactions, or evidence coverage. Do not use for unrelated edits, unchanged adequate recipes, missing capabilities, routine test runs, or product fixes.
---

# Keep the affected verification path accurate

Correct the existing operating capability, then execute what changed. This
leaf owns verification files, not product behavior or acceptance criteria.

Name the affected operating path or demonstrated drift from the task context.
An unchanged adequate recipe or ordinary test run needs no maintenance pass.
Small changes can still matter when they affect an important invariant.

## Resolve the target and write boundary

Find the recipe through the target's actual runbook/test/discovery entry.
Select the one implicated by the change; ask only if evidence leaves materially
different targets unresolved. No target means a setup handoff to
`create-verification-skill`, not permission to invent one here.

Read the existing recipe in full, its owned driver/fixtures, affected source,
accepted feature contract, focused tests, and relevant changes. Declare exactly
which verification-owned files may change. Follow their current format rather
than create a second map. Inspect index links when that index is affected.

- Edit only those declared files. Production code and accepted expectations
  are outside scope. A feature change may intentionally revise behavior only
  when the accepted contract supports it, not because the current build does it.
- Own necessary bounded verification glue under the task's existing authority
  and applicable implementation/testing policy. `implement-change` is optional
  when eligible; its explicit-only policy must not become a hidden prerequisite.
- Use one driver owner. Reuse disposable owned resources or declared serial
  access; separate worktrees do not isolate databases or browser profiles.
- Local verification writes do not authorize external effects, install,
  publication, production-data changes, or resetting personal sessions.
- Do not launch source-reader swarms or schedule a periodic whole-map sweep.
  For an expressly scoped whole-map audit, account for every claimed feature.

## Reconcile and exercise

| Observed problem | Action |
| --- | --- |
| Stale command, navigation, prerequisite, or description | Correct from source and the accepted contract, then re-drive |
| Harness cannot drive working product behavior | Repair the declared driver/fixture glue under applicable implementation/testing policy; re-drive |
| Product violates accepted behavior | Report a product regression to implementation; do not edit product code or weaken the recipe |
| Required prerequisite or safe resource access unavailable | Record attempted path, missing prerequisite, and unverified coverage |
| Recipe and affected behavior match | Still drive the claimed affected path before returning clean |

Run the recipe's exact launch and doctor before the first drive and for each
fresh session when sessions are its unit. Associate the actual executed
binary/module/process with the source candidate, not just a reported SHA.
Drive the required public path and relevant preserved/negative cases; existing
tests on another path do not establish this one.

Update the affected claims, actions, and witnesses in the existing recipe,
keeping materially preserved coverage. Do not replace the baseline with only
the newest feature or load every capability-building reference for routine
upkeep. Check that changed selectors, output parsers, and restart instructions
still reach the real result rather than merely making the harness green.

After surprising behavior, doctor again. Reset or relaunch owned state when a
healthy process can still have a wedged interaction. Correct a proven recipe
failure within scope and retry under the run's remaining repair allowance;
do not hide a product defect behind repeated harness changes.

Capture actions, results, and relevant side effects. Retain failed-attempt proof.
Clean failed attempts as well as the final drive, releasing only run-owned
resources and stopping exact owned processes. Evidence survives teardown;
read it back at the named location. A repaired driver must be exercised, not
merely syntax-checked.

## Return one outcome

- **clean:** every claimed affected path has source and live coverage; no
  correction needed.
- **changed:** owned corrections were made and re-driven; the report is a local
  evidence handoff, not a PR or independent product-acceptance verdict.
- **blocked:** required coverage or a safe correction could not finish. Retain
  useful corrections and evidence while naming the incomplete surface.

List target and changed files, source/runtime identities, covered and unverified
paths, commands/results, surviving proof, resource cleanup, and any product
regression separately. An unreachable or untested feature cannot be called
clean. Mixed completed/incomplete coverage is blocked for the overall claimed
scope; smaller verified claims may still be useful.

Publication remains with the authorized parent. `verify-change` owns the separate
acceptance pass and may reject a plausible but incorrect recipe; independent
verification requires a non-author.

Adapted from Lauren Tan's Cursor pstack; see [attribution](NOTICE.md).
