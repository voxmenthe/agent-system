# Notes Template

Use this shape for `notes.md`. Keep all six sections. Omit optional fields that
cannot affect action. Raw evidence stays at its source; this is an index
and current model.

```markdown
# Task contract
- goal:
- terminal condition:
- budget:
- workspace and write boundary:
- allowed mutations / renewed approvals:
- authoritative evidence source:
- bounded query method:
- sensitive, large, or non-idempotent hazards:
- owner's explicit choices for this task (launchers, second opinions, tracking; source):

# Current frontier
- confirmed current model:
- current recommendation and its decisive evidence:
- first decision-relevant uncertainty:
- prediction:
- next action:

# Claims
## K-1 [hypothesis|confirmed|ruled-out|superseded]
- statement:
- evidence for:
  - evidence: <kind>:<locator>
- evidence against:
- action consequence:
- grounding check: <claim boundary; observable signal; result that changes the claim; rerun trigger>
- authority/budget constraint:
- superseded-by: K-<n>

# Warnings and guards
W-<n> [dormant|live|obsolete] WHEN <observable trigger> THEN <guard/action> BECAUSE <evidence pointer>

# Reusable procedures
- purpose:
- required inputs:
- command or steps:
- bounded output / raw-output path:
- named fixture or self-check:

# Resume state
- current state and last material action:
- next action and expected result:
- skills to reread:
- live warnings:
- active or external processes:
- partial effects and cleanup obligations:
- last safe replay boundary:
- drift checks:
- validation command and rerun trigger:
- inferred decisions that matter (source; what would reverse it):
- owed decisions (source; required now|deferred|superseded):
- close-out, at the end (what to promote or keep; why; what remains uncertain):
```

Keep the owner's choices apart from your inferences so neither passes for the
other; they bind this task only, never later ones.

## Claim rules

Use immutable, increasing IDs:

```text
hypothesis -> confirmed | ruled-out | superseded
confirmed -> superseded
```

Never rewrite a claim in place. Append a new claim, then add
`superseded-by: K-<n>` to the old one. A hypothesis needs a grounding check or
a real authority or budget constraint. A check can confirm only the boundary
it directly observes. Otherwise keep the hypothesis and record the narrower
result.

Use one evidence-pointer shape:

```text
evidence: <kind>:<locator>
evidence: run:helpers/check.py#fixture-3
evidence: trace:events.jsonl#L18-L24
evidence: artifact:raw.bin#sha256=<digest>
```

Point to the observed task signal. If a helper derives the conclusion,
point to its source and self-check. Use native stable event IDs; do not
add an index only to normalize syntax.

## Compact without losing provenance

At 16 KiB, append closed and superseded records to `notes-archive.md`; preserve
IDs, pointers, and supersession links. Keep the contract, frontier, active
claims and warnings, next action, partial effects, replay boundary, validation
command, and rerun trigger in `notes.md`.
