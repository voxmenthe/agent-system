# Experiment Strategy

Choose experiments for information value as well as possible improvement. The
best next action is often the cheapest one that separates plausible task
models, not the largest run the remaining budget permits.

## Turn an explanation into a prediction

For each live hypothesis, identify:

- the causal change it proposes;
- the observation expected if it is right;
- an invariant that should not change;
- a result that would count against it; and
- the cost, side effects, and reversibility of the probe.

Prefer hypotheses whose predictions diverge. If several explanations predict
the same result, that action cannot distinguish them even if it produces an
interesting number.

## Move from probes to batches

Use a small probe while a mechanic is uncertain. A probe may be a reduced
input, a single profiler region, one training step, a synthetic counterexample,
one prompt mutation, a feature toggle, or a local code change with a focused
test.

Once the premise predicts correctly:

1. state the expected result of the larger run;
2. preserve a known-good comparison point;
3. bound cost and define an early stop;
4. run the batch or automation; and
5. compare exact output with the prediction before continuing.

Batching unvalidated assumptions produces more output, not more knowledge.

## Control attribution

Change one causal idea at a time when attribution matters. Combine changes
only when they are inseparable, individually established, or the task is in a
deliberate broad search phase. If a compound candidate wins, ablate its pieces
before making strong causal claims.

Keep rejected candidates and no-op results available long enough to prevent
repeating them. Errors and invalid actions may reveal constraints more cheaply
than a successful run.

## Select without fooling the loop

- Compare candidates with the same evaluator protocol.
- Distinguish the baseline, incumbent best, newest candidate, and exploratory
  branch.
- Treat tiny wins inside expected noise as ties.
- Re-run surprising improvements and inspect for changed inputs, cache state,
  leakage, missing work, or a broken gate.
- Charge search cost when it is part of the real objective; otherwise report it
  separately from deployment or inference cost.
- Prefer a simpler candidate when evidence cannot distinguish it from a more
  complex one.

## Reset the model, not just the candidate

Trigger a wrong-model reset when several discriminating predictions fail,
apparent gains vanish under exact comparison, or effort grows without a better
account of the evaluator and state transitions.

During reset:

1. stop adding variants inside the old explanation;
2. preserve confirmed observations and ruled-out hypotheses;
3. inspect raw state, controls, data flow, and evaluation behavior again;
4. propose materially different task models; and
5. choose a cheap action whose outcomes separate those models.

## Stop with intent

Continue only while the next experiment could plausibly alter acceptance,
candidate selection, or the task model within budget. Stop on acceptance,
budget exhaustion, a hard failure, an authority boundary, or when remaining
differences are below the decision threshold. State why the final candidate is
good enough rather than implying that search space was exhausted.
