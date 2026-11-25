# Domain Patterns

Use only the branch that matches the current task. These are recurring failure
modes and evidence checks, not evaluator schemas.

## Software improvement and debugging

- Begin with the existing contract: tests, callers, runtime behavior,
  compatibility, and repository policy.
- Reproduce a failure or establish a baseline before changing the code when
  feasible.
- Inspect exact diffs and runtime output. A passing new test is weak evidence
  if it never failed against the previous behavior.
- Keep correctness and negative cases as gates around performance, cleanup, or
  feature work.
- Prefer the smallest causal change; unrelated refactoring obscures which
  action produced the outcome.

## PyTorch and MLX performance

- Fix representative shapes, dtypes, devices, layouts, batch sizes, versions,
  and numerical tolerances before comparing candidates.
- Separate warmup, compilation, graph capture, cache population, data transfer,
  synchronization, and steady-state execution. Measure the phase the user
  actually cares about.
- Synchronize asynchronous devices at timing boundaries when required by the
  framework. A host timer around queued work can report an imaginary speedup.
- Check correctness and numerical stability before accepting latency,
  throughput, or memory gains.
- Use profiles to form causal hypotheses, then use end-to-end measurements for
  acceptance. Kernel-level improvement may disappear after launch overhead,
  transfers, or a different workload mix.
- Confirm across held-out or boundary shapes when specialization could move
  cost elsewhere. Report compile-time, peak-memory, and portability tradeoffs
  when material.

## Training a small model

- Freeze data provenance, train/development/test boundaries, preprocessing,
  metric code, starting checkpoint, and compute budget before comparing runs.
- Treat training loss as a diagnostic, not benchmark success. Preserve an
  untouched confirmation split or evaluation path when overfitting is
  credible.
- Use matched seeds or repeated runs when variance could reverse selection.
  Do not hide failed seeds after choosing a favorable run.
- Account for changed parameter count, training examples, augmentation,
  inference cost, and external data when the comparison claims equal budget.
- Save only checkpoints that can answer a future question. A checkpoint's
  existence is not evidence that its behavior improved.
- Stop or reset when scaling a run no longer tests the stated learning
  hypothesis.

## Prompt, policy, or program optimization

- Preserve the exact task wrapper, model and sampling settings, tool contract,
  evaluator, and candidate budget that make results comparable.
- Separate proposal or mutation examples from selection cases and final
  confirmation cases. Evaluator feedback used to generate the next candidate
  is development data, including in GEPA-style reflective search.
- Keep candidate lineage and the feedback that motivated each mutation so a
  win can be understood and reproduced.
- Check for reward hacking, verbosity bias, formatting shortcuts, evaluator
  preference leakage, and regressions on cases the mutation did not target.
- Re-evaluate finalists on fresh cases and, when important, with an independent
  scorer or human review. Repeatedly selecting on the same small benchmark can
  improve the score while degrading the intended capability.
- Distinguish search-time cost from the cost of using the final prompt or
  program.

## Data, scientific, and operational tasks

- Validate units, schemas, missingness, sampling, and provenance before
  optimizing a downstream number.
- Keep raw observations separate from derived conclusions and inspect
  transformations at boundaries.
- Prefer a reduced fixture or replay before acting on live or irreversible
  state.
- When reality drifts during the campaign, mark comparisons that are no longer
  contemporaneous rather than treating all runs as one stationary experiment.
