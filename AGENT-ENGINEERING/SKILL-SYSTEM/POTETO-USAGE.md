# Using Poteto and the verification skills

Use **Poteto for a concrete software outcome you want carried through assessment,
implementation, independent verification and PR handoff**. Start with one useful
feature or improvement. Describe the result and what must stay unchanged; let
the agent choose the necessary stages and routine implementation details.

This guide explains the current native Codex workflow. The linked skill sources
own behavior and authority; this document is practical usage guidance, not a
second policy. Poteto and the verification-capability skills remain experimental
under `~/.agents/skills/`. Poteto is explicit-only. Change-impact mapping,
boundary design, verification setup, upkeep, and acceptance are agent-discoverable
only when their specific uncertainty or evidence gap remains.

## Quick start: one feature through a PR

Start in the target repository and send this as one initial request. Replace
the angle-bracket fields, including the exact GitHub repository and base:

```text
Use $poteto with $implement-change.

Deliver <feature or improvement> in <repository/path>.
Success means <observable user behavior>. Preserve <existing behavior>.
Use one coherent work unit. You may make scoped local edits/commits and
create/update its PR in <owner/repository>, targeting <base branch>.
Keep unrelated work intact. Do not merge or deploy. Explanations off.
```

**Why these initial mentions?** Poteto and its implementation owner remain
explicit-only; naming Poteto does not make an omitted explicit-only skill
eligible. Mapping and architecture may resolve uncertain impact or an unsettled
consequential boundary decision. Verification setup, upkeep, and acceptance may
close material capability or evidence gaps. `frame-change` and `diff-review`
also have implicit eligibility. Existing maps, designs, recipes, and sufficient
proof are reused. You do not need to forward work between stages. A missing
required skill is reported, not silently replaced.

If you want local preparation only, replace the commit/PR grant with “Local edits
only; do not commit or publish.” That produces useful local work, but not a
completed frozen-candidate/PR handoff. Existing authorization carries forward;
the agent should not repeatedly ask permission for ordinary authorized steps.

## Give it an outcome, not a task inventory

The most useful brief contains:

- **A real use:** who needs the change and what they should be able to do.
- **Observable success:** for example, export the currently filtered rows to
  CSV, preserve column order, and handle an empty result explicitly.
- **Preserved behavior:** for example, the unfiltered report and existing export
  remain unchanged.
- **Scope and authority:** the target, allowed edits, PR destination and anything
  you want to decide yourself.

Supply known commands, fixtures or runbooks when you have them. The agent should
inspect the repository for the rest. Do not prescribe a new framework or a
separate document for every stage unless that is part of the required outcome.

## Choose the amount of autonomy

| Need | Best entry |
| --- | --- |
| One new feature or improvement | The quick-start request; one work unit is the default |
| Several useful slices toward one objective | Add bounded autonomous mode and a finite total budget |
| Resume an interrupted run | Point to its saved `RUN.md`; retain its remaining bounds |
| Establish a missing runnable verification path | Use `create-verification-skill` directly |
| Repair or refresh an existing verification recipe | Use `maintain-verification-skill` directly |
| Typo or obvious tiny edit | Ask for the edit directly; no coordinator or run state needed |

For a bounded objective, keep the initial skill mentions and replace the
one-unit line with something like:

```text
Use bounded autonomous mode for <objective>. Choose the next useful slice
from the remaining gaps. Maximum two total work units, two open run-owned
PRs and two no-progress repairs across the entire run, including resumes.
Stop earlier if the objective is satisfied; do not produce work to fill a quota.
```

There is always one implementation writer. Two open PRs and two no-progress
repairs are defaults, not a promise to produce or spend them. Finite work-unit
bounds are useful when complete token/child-cost accounting is unavailable.
Bounded autonomous mode runs in an active native session; it is not a daemon
that wakes itself after shutdown.

## Request an explanation when it helps you review

Add this to the initial request when you want an accessible walkthrough:

```text
Also use $show-me-clearly. Set pr_explanations to show-me-clearly and include
a saved, checked, source-pinned explanation with each PR.
```

Leave explanations off for changes you can review directly from the diff and
proof. **Required verification evidence remains available either way.** An
explanation describes the change; it does not replace independent acceptance.

## Steer, check status, resume or stop

You can steer ordinary work without taking over stage dispatch:

| Message | Expected behavior |
| --- | --- |
| “Status?” | Reports ready work, current work, blockers, bounds and links, then continues |
| “Keep the human output unchanged; put the new fields only in JSON.” | Updates the affected criteria, preserves useful independent work and obtains fresh affected proof |
| “Reject that approach; retain the independent export fix.” | Stops extending the rejected direction, identifies dependent work and rechecks any recovered candidate |
| “Cancel this run.” | Stops new effects, reconciles pending writes and stops/cleans only owned resources; does not delete published work |

After an executor has ended or explicitly handed off, start a fresh request:

```text
Use $poteto with $implement-change.
Resume <path-to-RUN.md>. Reconcile ownership and actual checkout/PR state,
retain the accepted criteria, explanation setting and spent/remaining bounds,
and continue the recorded next action.
```

Include `$show-me-clearly` too if the resumed run requires explanations. Use the
actual note path from the handoff. The fallback location is
`<authorized-task-root>/.poteto/<run-slug>/RUN.md`, not the installed skill folder.
Do not launch a second executor for an active run: uncertain ownership blocks
mutation. Native context compaction and explicit restart are different cases;
neither resets the budget or erases rejected directions.

## Use the verification skills without Poteto

Despite their names, these skills normally create or maintain **target-project
verification instructions and any necessary driver/fixture glue**, not another
globally installed skill. They do not independently accept product changes or
publish PRs.

For nontrivial or high-impact work, the agent may select creation when a material
launch/drive/observation gap is not covered by existing tooling, maintenance when
an existing path materially changes or demonstrably drifts, and acceptance when
important behavior or builder evidence needs structured assessment. Ordinary
test commands, unrelated edits, and adequate recipes do not require this chain.
Explicit requests remain available:

**Set up a missing path:**

```text
Use $create-verification-skill to establish a reusable
verification recipe for <feature/public path> in <repository>.
Reuse adequate existing instructions. Exercise a real path, retain evidence
after cleanup, and identify unbuilt or unavailable behavior. Do not fix product
code, install tools, commit or publish.
```

**Maintain an existing path:**

```text
Use $maintain-verification-skill to reconcile
<recipe path> with <accepted feature change or observed drift>.
Correct only the affected verification-owned files and re-drive the public
path. Report product regressions without changing product code or weakening
expected behavior. Do not commit or publish.
```

The recipe owners can implement their necessary bounded driver/fixture glue
under the task's existing authority; no additional skill mention is required.
Product changes remain outside these prompts' verification-only boundary. Setup returns
**reused / created / blocked**; upkeep returns **clean / changed / blocked**.
A missing prerequisite is not a pass. Neither skill needs Poteto run state.

## What a good handoff contains

Expect the chosen slice and material design decision, an integrated change,
separate fresh non-author defect review and criterion-by-criterion acceptance,
and proof tied to the actual source/runtime that was driven. Proof should check
the new behavior, preserved behavior and a negative case that could expose a
plausible but wrong implementation—not just a healthy help command or old tests.

For an authorized PR, expect its actual link, matching remote source identity,
accessible evidence and any requested explanation. For a longer run, also expect
the saved frontier, remaining bounds and recovery pointers. A source, criterion
or relevant recipe change needs current affected verification. Merge and
deployment remain separate actions requiring their own authority.

Keep required repository-template fields; otherwise use a compact explanation
of the outcome, mechanism, actual checks/limitations, affected consumers, and
reversibility of effects. Keep that handoff current with the final candidate.

## Sources and working example

- Contracts: [Poteto](skills/poteto/SKILL.md),
  [verification setup](skills/create-verification-skill/SKILL.md),
  [verification upkeep](skills/maintain-verification-skill/SKILL.md).
- Continuity fields: [one run note](skills/poteto/references/run-note.md).
- Installation and managed recovery: [system README](README.md).
- One full run covered human capture inspection followed by structured JSON,
  independent proof, a discovered and fixed verification false positive, and
  continuation and recovery checks.

Native Codex is the exercised host. Discovery on another host is not proof of
equivalent composition, independent review or lifecycle behavior. Broader
research campaigns, parallel implementation writers and unattended restarts
are outside this minimal workflow.
