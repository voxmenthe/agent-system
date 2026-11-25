# Evaluation Design

Design evaluation for the current task rather than forcing the task into a
predefined score format. The purpose of evaluation is to support the next
decision and the final acceptance claim.

## Separate gates, objectives, and diagnostics

- **Hard gates** are non-negotiable: correctness, safety, validity,
  compatibility, resource ceilings, policy, or a user acceptance condition.
  A candidate that fails one is not eligible regardless of its score.
- **Primary objectives** rank candidates that pass the gates: latency,
  throughput, accuracy, reward, loss, cost, robustness, or another requested
  outcome.
- **Secondary objectives** expose tradeoffs but should not silently displace
  the primary objective.
- **Diagnostics** explain behavior. A profiler counter, training loss, or
  evaluator critique may guide an experiment without being the acceptance
  measure.

Keep these roles explicit. Optimizing a diagnostic as if it were the objective
is a common route to false progress.

## Test whether the evaluator deserves authority

Before trusting an evaluator, ask:

1. Does it measure the requested construct or only a convenient proxy?
2. Are inputs representative of the cases that matter?
3. Can it detect a change large enough to matter?
4. Is it repeatable enough to compare candidates, or must repeated samples,
   paired cases, confidence intervals, or a larger effect threshold be used?
5. Could the candidate see, memorize, contaminate, or exploit the evaluation?
6. Does instrumentation change the behavior being measured?
7. Which negative cases would reveal a superficially good but invalid result?
8. For a timed claim, did the region contain the intended completed, correct
   work—not errors, rejections, lazy/no-op execution, unawaited operations or
   unintended cache hits? Name the success/output check.
9. Is the claimed gain plausible given an observed limiter, resource ceilings
   and the changed component's share of end-to-end cost? A guessed cause
   remains a hypothesis.

Do not delay all work until evaluation is perfect. Use the smallest credible
check, name its blind spots, and add fidelity when evidence shows that a blind
spot could change selection or acceptance.

## Establish comparability

Record the baseline protocol before using it to select improvements. Preserve
material inputs and conditions such as versions, device, shape, dtype, seeds,
data split, warmup, cache state, sampling settings, prompt wrapper, scoring
rubric, and resource budget. Which fields matter is task-specific.

Compare a candidate and its baseline under the same protocol. When the system
is noisy or drifting, prefer paired comparisons close in time. Keep the
original baseline and the current best distinct so that a regression in the
best candidate does not erase the reference point.

## Protect final confirmation

Exploratory evidence is allowed to steer search and therefore becomes biased
toward what the loop has already seen. Reserve independent confirmation when
overfitting is credible: a held-out dataset, unseen workload, fresh seed set,
clean process, alternate measurement path, regression suite, or human review.

Do not repeatedly tune against the held-out check and still call it held out.
If confirmation data is consumed during search, relabel it as development
evidence and create a new confirmation boundary when feasible.

## Report honestly

An evaluation report should make clear:

- which hard gates passed or failed;
- baseline, candidate, and comparison protocol;
- effect size and uncertainty where they matter;
- evidence used for search versus evidence reserved for confirmation;
- evaluator limitations and known opportunities for gaming; and
- whether the result is accepted, promising but unconfirmed, or rejected.

A valid receipt, exit code, or generated artifact shows that machinery ran. It
does not by itself show that the evaluator was valid or that the outcome
improved.
