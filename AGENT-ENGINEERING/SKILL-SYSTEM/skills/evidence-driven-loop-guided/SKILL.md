---
name: evidence-driven-loop-guided
description: "Design and run an instruction-rich but infrastructure-light improvement loop whose evaluator is chosen for the task. Use only when the user explicitly invokes $evidence-driven-loop-guided or asks for a guided evidence-driven campaign across coding, performance, training, prompt optimization, or another observable task. Do not use for a routine one-pass change, a task with no actionable evidence, or as a substitute for domain-specific safety and authority rules."
disable-model-invocation: true
---

# Evidence-Driven Loop: Guided

Run a task-specific improvement campaign without imposing a universal
evaluator, experiment schema, or workspace layout. Own the epistemic discipline
of the loop; let the task determine what is measured, how evidence is produced,
and which artifacts are worth keeping.

Hard correctness, safety, validity, and acceptance gates outrank optimization
targets. A better proxy score is not an improvement when a gate fails or when
the proxy no longer represents the requested outcome.

## Load only the guidance the task needs

- Read [evaluation design](references/evaluation-design.md) when success,
  baselines, measurement validity, noise, or leakage need to be worked out.
- Read [experiment strategy](references/experiment-strategy.md) when choosing
  probes, batching changes, selecting among candidates, or recovering from a
  wrong task model.
- Read [domain patterns](references/domain-patterns.md) for conditional
  guidance on software, PyTorch or MLX performance, small-model training, and
  prompt or program optimization.
- Read [long-running work](references/long-running-work.md) when the campaign
  may cross context windows, sessions, handoffs, or expensive checkpoints.

These references are lenses, not required phases. Do not load a branch that
does not apply.

## Establish the task contract

Before optimizing, determine from repository context, tools, evaluator output,
and the user:

- the requested outcome and hard gates;
- the primary measure and any secondary tradeoffs;
- what counts as a comparable baseline and an accepted result;
- the allowed actions, side effects, cost or time budget, and stop conditions;
- the evidence needed to distinguish real progress from noise or evaluator
  gaming; and
- which product judgment or authority questions only the user can answer.

Do not require a predictable evaluator format. If evaluation is missing,
design the smallest task-specific check that can guide the next decision, state
what it does not establish, and improve it only when a concrete failure demands
more fidelity.

## Run the campaign

1. **Orient.** Inspect the current state and the machinery that produces it.
   Read exact formats and conventions. Locate existing tests, benchmarks,
   profiles, datasets, held-out cases, logs, and prior results before creating
   replacements.
2. **Baseline.** Run the smallest credible reference measurement. Preserve the
   command, inputs, environment details that materially affect comparability,
   and raw output needed to audit the conclusion.
3. **Model.** Explain the current causal account of the bottleneck or failure.
   Separate observed facts, inferences, live hypotheses, and unknowns.
4. **Predict.** Before a meaningful action, state what should change, what
   should stay invariant, and which observation would falsify the hypothesis.
5. **Probe.** Prefer a cheap discriminating action over a large batch while a
   premise is uncertain. Count errors, rejected operations, no-ops, resets,
   timeouts, and resource use as observations.
6. **Inspect.** Compare exact outputs, diffs, profiles, traces, metrics, or
   artifacts. Parse large states mechanically and bring conclusions into
   context rather than copying the whole state.
7. **Update.** Revise the task model and next experiment from the observation.
   Preserve a known-good baseline and current best; do not let a new candidate
   silently replace either.
8. **Scale deliberately.** Batch, automate, train longer, or broaden evaluation
   only after the premise predicts correctly and the larger run answers a
   named question worth its cost.
9. **Select and confirm.** Compare candidates under the same protocol. Recheck
   hard gates, negative cases, held-out evidence where relevant, and a clean
   end-to-end run before claiming the result.

Continue while the next experiment has a credible chance to change the task
model or accepted result within the remaining budget. Stop when the result is
accepted, the budget is exhausted, the user withdraws or narrows authority, or
the next action requires a material decision only the user can make.

## Reset a failing model

Do not respond to persistent prediction failure by searching a wider area
inside the same explanation. Pause when several discriminating predictions
fail, apparent progress cannot be reproduced, or the cost rises sharply
without a clearer account.

Record what is confirmed and ruled out, then reconstruct the task from primary
evidence: the objects or components present, the controls available, the
actual data and state transitions, and the evaluator's real behavior. A stale
plan is not a commitment; invalidate it when its premises fail.

## Keep infrastructure proportional

Use task-local notes, scripts, parsers, and checkpoints only when they reduce
re-derivation or error. There is no mandatory ledger, schema, database, daemon,
or MCP service in this variant. A command receipt proves that a command ran;
only inspection of its result can establish what the task learned.

At handoff, report the current best and baseline, comparison protocol, hard
gate status, decisive observations, confirmed and ruled-out mechanics,
remaining uncertainty, budget state, and the next predicted action if work is
continuing.
