---
name: evidence-driven-loop-instrumented
description: "Operate a resumable improvement campaign with task-local receipts, checkpoints, and explicit selection evidence while leaving evaluation semantics to the agent. Use only when the user explicitly invokes $evidence-driven-loop-instrumented or requests a mechanically auditable, long-running loop for coding, performance, training, prompt search, or another observable task. Do not use for a short one-pass change, where persisted evidence may expose secrets, or when the added instrumentation would not improve decisions or recovery."
disable-model-invocation: true
---

# Evidence-Driven Loop: Instrumented

Operate a long-running, resumable campaign whose evidence can be audited after
conversation context is gone. This variant provides a narrow mechanical layer
for command execution and run receipts. It does not define a universal score,
evaluator, experiment database, or winner-selection algorithm; the agent still
designs those for the task.

Use command capture only when command-level provenance materially reduces error
or re-derivation. For confidential output, interactive UI, remote work whose
lifecycle the wrapper does not own, or an evaluator already providing adequate
records, keep task-native evidence in the checkpoint and skip the helper. The
campaign protocol remains usable for non-command observations.

## Campaign workspace

Use an existing repository convention when one exists. Otherwise choose one
explicit task-local evidence root, approved by the task's write boundary. A
typical campaign may contain:

```text
<evidence-root>/
├── checkpoint.md       # current task model and resumption point
└── runs/               # one immutable directory per captured command
```

Do not create this layout automatically, add it to version control
automatically, or place it in a global home directory. Keep large or sensitive
outputs out of Git unless repository policy and the user require otherwise.
Read [the campaign protocol](references/campaign-protocol.md) before starting a
multi-session campaign.

## Establish authority and evaluation

Define the requested outcome, hard validity gates, primary measure, comparison
protocol, side-effect boundary, budget, and stop conditions. Inspect existing
tests, benchmarks, datasets, profiles, and prior results before creating new
ones. The evaluator may be a test suite, timing harness, benchmark, training
metric, human rubric, model judge, external system observation, or a
task-specific combination.

Do not force these into the receipt format. A receipt proves what command ran,
when it ran, and what files it produced; it does not decide whether the
evaluator is credible or the result is better.

## Capture a run when it helps

The bundled [capture helper](scripts/capture_run.py) executes an argv vector
without a shell, writes stdout and stderr directly to a unique run directory,
records timing and exit status, and optionally hashes named task-local
artifacts. Read [the capture guide](references/capture-run.md) before first use.

A representative invocation is:

```bash
python3 <skill-dir>/scripts/capture_run.py \
  --records-dir <evidence-root>/runs \
  --cwd <task-root> \
  --label baseline \
  --prediction "The reference implementation passes and establishes latency" \
  --success-condition "Correctness passes and the benchmark emits comparable timing" \
  --timeout 300 \
  --artifact results.json \
  -- <command> <arg> ...
```

Use the repository's required Python launcher when it differs. Never put
credentials or other sensitive values in captured argv. Do not use the wrapper
for a command whose output should not be persisted. Inspect the command's
actual output after every run; zero exit status is not task acceptance.

## Operate the loop

1. **Orient and baseline.** Verify formats, evaluator behavior, environment,
   hard gates, and a credible reference result. Record only configuration that
   materially affects comparison.
2. **Checkpoint the model.** Separate confirmed observations, live hypotheses,
   ruled-out explanations, unknowns, current best, and the next predicted
   action. The checkpoint is a concise index; raw receipts and evaluator output
   remain authoritative.
3. **Name the experiment.** Before a captured run, state one hypothesis,
   prediction, success condition, invariant, cost bound, and early-stop
   condition. The helper requires the prediction and success condition so they
   cannot be retrofitted after seeing the result.
4. **Probe cheaply.** Use a small discriminating case while a premise is
   uncertain. Count failures, timeouts, rejected inputs, no-ops, and resource
   use as observations.
5. **Inspect exactly.** Query, parse, diff, profile, or summarize the stored
   output. Bring the conclusion and precise source path into context, not the
   entire log.
6. **Update deliberately.** Compare prediction with observation, revise the
   task model, and update the checkpoint only when evidence changes it. Keep
   the original baseline and incumbent best distinct from the latest
   candidate.
7. **Scale after validation.** Run longer batches, broader evaluations,
   training, or automated search only when the premise has predicted correctly
   and the additional cost answers a named question.
8. **Select and confirm.** Use the task-specific evaluator to compare eligible
   candidates under one protocol. Read
   [selection and confirmation](references/selection-and-confirmation.md) when
   noise, leakage, multiple objectives, or search bias could alter the winner.
9. **Reset when the model fails.** After repeated predictive failures or
   irreproducible gains, stop expanding the same search. Preserve confirmed and
   ruled-out evidence, then reconstruct the task from raw state, controls, data
   flow, and evaluator behavior.

## Resume and stop safely

On resume, verify that the checkpoint's evaluator, baseline, current best,
environment, artifacts, and authority boundary still exist. Inspect the last
decisive receipt and run a cheap orientation check before spending a large
remaining budget. Treat stale premises as invalidated, not as instructions.

Stop on accepted evidence, budget exhaustion, a hard gate that makes the
direction ineligible, user-requested stop, or an authority boundary. On
handoff, record running external work and cleanup obligations explicitly; do
not imply that this skill continues monitoring after the agent yields.

Report baseline and best accepted result, exact comparison and confirmation
protocol, hard-gate status, decisive receipt paths, failed directions that
changed the model, remaining uncertainty, and material instrumentation limits.
Do not propose an MCP server, shared database, daemon, or remote service until
repeated real campaigns demonstrate a stable capability that cannot be handled
reliably by the local skill and scripts.
