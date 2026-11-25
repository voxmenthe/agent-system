---
name: create-verification-skill
description: Build and exercise a reusable target-local verification recipe and its necessary tools. Use when a nontrivial or high-impact task has a material launch, drive, observation, or proof gap that existing tests and runbooks cannot cover. Do not use for routine test runs, tiny edits, adequate existing recipes, or product acceptance.
---

# Establish a usable verification path

Leave instructions that a fresh agent can execute without the author's
navigation help. A generated recipe is a draft until its own public path has
run successfully and its evidence survives cleanup.

Use this capability only when the task has a material operating or evidence
gap. A normal test command, adequate recipe, or small one-off probe should stay
on the direct path. Judge impact by the behavior at risk, not the diff's size.
Explicit invocation can still return **reused**; do not manufacture a tool.

## Scope and ownership

- Start with the affected feature and necessary adjacent paths. Reuse the
  target's tooling, fixtures, and verification location. An adequate existing
  runbook is a successful **reused** result; do not generate a second owner.
- Write only the declared recipe, needed driver/fixture glue, and its discovery
  link. Own that bounded glue directly under the task's existing authorization
  and applicable implementation/testing policy. `implement-change` is optional
  when eligible, not a prerequisite or a transitive invocation grant.
- This is local-write capability setup, not acceptance or publication. Product
  fixes return to implementation. No install, provider, external-write,
  production-data, or process-reset authority follows from invoking this skill.
- One driver owner uses disposable owned resources or declared serialized
  access. Do not copy personal sessions, credentials, profiles, or working data.

## Inspect, then build only the missing capability

Read the selected surface, callers, focused tests, docs, and launch configuration.
Resolve these facts from the repository before asking for missing information:

| Question | Evidence needed |
| --- | --- |
| What does the user do? | Public command/call/route, prerequisites, actions, observable end state |
| What runs? | Exact launch/build command, working directory, readiness, candidate association |
| What drives it? | Existing driver and real arguments/selectors; no internal setters bypassing integration |
| What is owned? | Processes, ports, profiles, databases, caches, files, background work; shared resources need a serial owner |
| What proves it? | Actions and results, relevant side effects, a discriminating negative case, durable evidence location |
| How is it found? | Existing runbook/test entry or verified target-host discovery convention |

A not-yet-built feature is expected to be absent. Prove an existing path first
and record the intended new-feature scenario as **not yet exercised**. If the
base cannot run, distinguish a recipe/harness problem from a product defect or
unavailable prerequisite. Fix only owned verification problems; hand off the
other blocker precisely. Do not teach a workaround that changes product behavior.

Put one affected-surface recipe in the target's existing verification location.
If a host-local skill entry is needed, verify its discovery convention in that
host and link the recipe rather than duplicate it. Do not assume `.cursor/` or
create a full-product atlas. See the short [recipe example](references/recipe.md)
when choosing the shape; replace illustrative commands with verified commands.

Read only the reference needed for the missing capability:

| Gap | Reference |
| --- | --- |
| Turn a successful operation or raw output into a repeatable driver, client, parser, or check | [Tool construction](references/tool-construction.md) |
| Connect affected user behavior to executable checks and observable outcomes | [Coverage and witnesses](references/coverage.md) |
| Drive a browser or choose the correct UI surface and restart boundary | [UI drivers](references/ui-drivers.md) |
| Exercise prompts, keyboard transitions, resize or interruption in a real terminal | [Terminal control](references/terminal.md) |
| Check a sequence of state changes and replay its concrete inputs | [Stateful workloads](references/stateful-workloads.md) |
| Render real components and distinguish layout defects from capture defects | [Visual checks](references/visual-checks.md) |

These are methods, not preinstalled tools. Prefer a target-local helper; no
reference requires a new dependency, global runner, or separate module for
each step. Unexercised platform branches remain unverified.

The recipe must contain:

1. **Launch and doctor:** exact prerequisites/commands; health and readiness;
   evidence associating the executed binary/module/process with the candidate.
   A SHA typed into a report is not instance identity.
2. **User path:** entry, actions and expected observations, with stable handles
   and fixtures. Distinguish intended changes from preserved behavior. Record
   navigation gotchas that a cold agent would otherwise have to rediscover.
3. **Proof:** capture action/result and side effects appropriate to the claim.
   A dry-run name does not prove absence of writes or network effects: inspect
   its implementation and observe those boundaries. Record wrong path/build and
   unavailable prerequisites as unverified, not passing.
4. **Cleanup:** remove only resources created by this run, including failed
   attempts. Stop exact owned processes, never processes by name. Keep evidence
   outside disposable state and verify it still exists after teardown.

Any helper script is executable, has a documented invocation, and fails clearly
at its input, identity, readiness, or cleanup boundary. Do not add a global
runner when a target-local command suffices.

## Prove and hand off

Execute launch → identity/health → one real user path → capture → cleanup.
After a surprising failure, doctor again; reset or relaunch only owned state
when health alone cannot establish readiness. Re-drive any corrected harness.
Retain evidence from failed attempts as well as the successful path.

Return **reused**, **created**, or **blocked**, with:

- recipe/discovery location and declared verification-owned files;
- source/runtime identity, covered user paths and commands actually run;
- evidence still accessible after cleanup and resources released;
- unbuilt paths, unavailable prerequisites, and remaining gaps;
- the next affected-surface upkeep route, `maintain-verification-skill`.

`created` establishes operating capability only. `verify-change` assesses the
recipe and product against the accepted outcome in its declared evidence mode;
independence requires a non-author, not merely a different skill name.

Adapted from Lauren Tan's Cursor pstack; see [attribution](NOTICE.md).
