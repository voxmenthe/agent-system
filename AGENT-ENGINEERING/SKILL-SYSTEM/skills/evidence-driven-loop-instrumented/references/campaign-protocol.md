# Campaign Protocol

Use this protocol when the improvement loop may cross sessions, expensive
runs, handoffs, or context compaction. It gives the campaign a resumable edge
without turning it into a service.

## Choose one bounded evidence root

Prefer an existing task or repository convention. Otherwise choose a local
directory inside the authorized work area. State whether it is disposable,
ignored, or intended for version control before placing large outputs there.
Never default campaign output to a global skill directory or broad home path.

Keep the write ownership simple:

- `checkpoint.md` is updated by the active agent after a material evidence
  change;
- each captured run owns a new, unique directory under `runs/`;
- evaluator-owned artifacts remain where that evaluator expects them, with
  paths recorded in the checkpoint or receipt; and
- no process appends to a shared database or mutable run index.

Unique run directories make partial failure visible and avoid write races.
They are receipts, not a queue.

## Checkpoint the current theory

Use prose or the repository's existing format. Keep enough state to recover:

- objective, hard gates, primary and secondary measures;
- evaluator and exact comparison protocol;
- authority, side-effect, time, compute, and cost boundaries;
- baseline, incumbent best, and latest candidate as distinct identities;
- confirmed observations with receipt or source paths;
- tentative hypotheses and their pending discriminating tests;
- ruled-out explanations and the observations that ruled them out;
- last prediction, action, observation, and model update;
- environment or dependency changes that can break comparability;
- running external work, owners, cleanup, and safe cancellation path; and
- next predicted action, expected observation, and stop condition.

The checkpoint is not a raw log. Update it when evidence changes the model,
candidate selection, budget, or resumption point. Do not copy long stdout or
stderr into it.

## Interpret run states

A run directory may contain only a `started.json` and partial output if the
capturing process was killed before it could write `receipt.json`. Treat that
as interrupted evidence, inspect whether the underlying command or external
side effect survived, and reconcile it explicitly. Never relaunch an
effectful command merely because its receipt is incomplete.

Final receipt status has mechanical meaning only:

- `completed`: the command returned zero;
- `failed`: the command returned nonzero;
- `timed-out`: the wrapper reached its timeout and attempted to terminate the
  owned process group;
- `interrupted`: the wrapper received local interruption and attempted the
  same cleanup; or
- `spawn-error`: the command could not be started.

None of these statuses asserts correctness, score, or acceptance.

## Resume defensively

1. Read the task contract and checkpoint.
2. Verify the evaluator, baseline, incumbent, artifacts, and environment still
   exist and remain comparable.
3. Inspect the last decisive raw receipt and evaluator output.
4. Reconcile any partial run or external process before repeating work.
5. Restate the current causal model and predict the next observation.
6. Run a cheap orientation check before a high-cost continuation.

Invalidate stale plans when code, data, tools, dependency versions, model
weights, prompt wrappers, evaluator behavior, or user priorities changed.

## Hand off without pretending continuity

State which processes are actually running and who or what owns them. Include
job identifiers and a safe observation or cancellation method when available.
If no monitor exists, say so. The presence of a checkpoint does not cause an
agent, process, or service to continue working after handoff.
