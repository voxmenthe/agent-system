---
name: orchestrate
description: "Coordinate native agents on bounded independent work. Use when explicitly requested and parallel work materially helps; do not use as an external-model launcher or to split tightly coupled work."
disable-model-invocation: true
---

# Orchestrate

Use native agent tools to divide independent work, supervise completion, and
deliver one verified result. The separate `delegate` skill owns explicitly
requested external workers; missing native tools do not authorize that workflow.

For Codex, launch only when the user requests delegation or an applicable
instruction explicitly calls for it. Reading a skill for review or inspiration
is not invocation. Do not self-invoke a workflow to manufacture authorization.

## Assign useful work

Delegate a bounded assignment that can proceed independently alongside useful
parent work, or a required independent review/judgment. Keep tightly coupled
work local or sequence its dependencies. Three children is a routine maximum,
not a minimum, for Codex; a fourth or fifth needs independently useful work.
The configured hard-cap target is five children, excluding the parent. Verify
the active surface's capacity and whether idle/completed children release it.
Use waves for additional independent work. If a method requires more simultaneous
children than fit, report the conflict and require a supported, explicitly
authorized per-run override; do not silently serialize that method or raise the
global default.

## Codex-native launch settings

Use these model/effort pairs for authorized Codex assignments unless the user
has selected other settings. Other hosts retain their existing choices.

| Assignment | Model | Reasoning effort |
|---|---|---|
| Ordinary bounded worker | `gpt-6-astra` | `low` |
| Explorer | `gpt-5.6-sol` | `medium` |
| Independent reviewer (`commit-diff-risk-reviewer`) | `gpt-6-astra` | `high` |
| Independent LLM judge deciding whether to accept an improvement | `gpt-6-astra` | `high` |

The acceptance judge uses higher effort because its error can approve a worse
artifact without an objective test exposing it. Higher effort is not proof of
a correct verdict; inspect the judgment's evidence and omissions.

Inspect the actual tool schema and relevant home/profile before relying on
settings. Global defaults are not ceilings. Pass the approved model and effort
through supported launch parameters where permitted; verify resolution from
runtime metadata, not a role label, prompt instruction, or child's self-report.
Record effective permissions and service tier when observable; preserve parent
settings and user tier choices. A task packet does not enforce a permission
sandbox, and configuration discovery does not prove custom-role selection.

When named-role selection is unavailable, use a packet-based native assignment
with supported, permitted model/effort settings. Do not invent `agent_type` or
create a custom profile. If neither defaults nor permitted overrides establish
the required settings, keep ordinary work local and report the unsupported
control. Required independent review or judgment remains unmet; the parent's
verdict cannot substitute for it.

## Select context before launching

Narrow means relevant, not necessarily short. An instruction inside a child
cannot remove history already inherited at launch.

| Mode | Use when |
|---|---|
| Fresh (preferred for independent work) | A self-contained briefing can preserve the complete task contract. On interfaces exposing `fork_turns`, choose `"none"` explicitly. |
| Bounded inheritance | Necessary recent discussion is hard to reproduce reliably; include the relevant turns, not an arbitrary short slice. |
| Full inheritance | Necessary decisions cannot be preserved by a brief or bounded history. State why and accept the host's model/effort limitations. |

On Codex interfaces where full-history forks inherit the parent and reject
overrides, do not claim lower-effort defaults apply. Never omit a requirement
to obtain a cheaper launch. If necessary inheritance conflicts with required
settings, use the unsupported-assignment handling above. Honor stricter fresh,
independent judge contexts; do not copy the optimizer's history into a judge.

Before launching, inspect the workspace and provide a task packet:

```text
ROLE: implement | analyze | review | verify | judge
OBJECTIVE: one accepted observable outcome
WORKSPACE: absolute project path
SCOPE: owned files, symbols, or read-only surface
CONTEXT: necessary facts, errors, earlier decisions, dependencies, source references
CONSTRAINTS: invariants, compatibility, exact boundaries, authority, exclusions, no redelegation
VERIFY: required evidence and targeted checks or judgment criteria
RETURN: status, findings or changes, evidence, blockers
```

Include project instructions, earlier conversational constraints, rejected
approaches, required evidence, and authority limits that affect the assignment.
Quote a user constraint when paraphrasing could change its meaning. Read the
relevant behavioral unit fully, expanding for demonstrated dependencies; give
facts and file/symbol references instead of forwarding entire plans or logs.
For independent review/judgment, supply requirements, criteria, and source
artifacts without steering toward the parent's preferred conclusion. Summaries
must not replace evidence the worker needs to inspect.

Maintain one writer per file, including shared manifests, generated files, and
formatting outputs. The parent must not edit a worker's active write scope.
Readers may overlap, but a review requiring a stable result waits for writers.
Preserve pre-existing changes. Delegation inherits the task's authority; it does
not authorize commits, publication, destructive actions, or unrelated work.

## Supervise through the host

Use only the host's available tool parameters. Preserve user-selected models,
providers, and budgets. Do not switch providers to obtain missing capabilities.
No recursive delegation: put that constraint in every packet. Do not treat a
thread cap or an unverified `max_depth` setting as proof of depth enforcement.

Bound active agents to useful independent work and host capacity. Keep the user
informed while doing non-overlapping parent work. Use existing task tracking to
record each assignment's actual agent ID, role, model/effort/tier (or observation
gap), context mode, scope, dependencies, status, and completion condition. No
mandatory persisted manifest or unsupported per-worker token allocation.

On failure, inspect the returned evidence and actual workspace. A timeout does
not prove the worker stopped: confirm settlement or cancellation before reusing
its scope. An interruption request alone does not establish subprocess cleanup.
Use a narrow follow-up for a specific gap, not an open-ended retry. On task
cancellation, stop owned workers and account for partial edits without discarding
unrelated work. Do not leave child work running past the parent handoff.

Finish on the agreed evidence. Add workers, loops, or follow-ups only for a
concrete unresolved need; do not duplicate completed work by default. Keep large
logs/artifacts outside the parent conversation and return conclusions, evidence
references, uncertainty, and missing checks. UI checks name affected views and
task flows; retries follow observed defects, not an open-ended checking quota.

Leave rollout budgets off unless the user opts into a task-scoped budget. If
enabled, treat the reported remainder as shared and potentially stale. Leave
headroom for outstanding work, required checks, and parent integration before
adding work; as it narrows, collect bounded findings and unfinished items.
Preserve required checks and chosen models; report an honest partial result if
completion does not fit. Do not automatically retry after exhaustion, raise or
disable the limit, restart a root, or switch accounts to evade it. A shared work
budget is neither a worker allocation nor an account-spend ceiling.

## Join and verify

Read every result and inspect actual changes after writers settle. Resolve
conflicts against the user's contract and source evidence, not worker confidence.
Integrate dependencies and run the narrowest sufficient combined checks. Report
what each worker contributed, what the parent verified, failures, and remaining
limitations. Never present an incomplete assignment as completed work.
