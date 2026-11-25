# Selection and Confirmation

Run receipts make experiments auditable; they do not make heterogeneous
results comparable. The agent must extract task-specific evidence and apply
the task's gates and objectives.

## Build a comparison from primary output

For each eligible candidate:

1. locate the exact receipt and evaluator output;
2. verify inputs, environment, budget, and protocol are comparable;
3. check hard gates before ranking objectives;
4. extract the primary measure and material tradeoffs from the authoritative
   output;
5. compare the observed result with the prediction recorded before the run;
   and
6. record whether the task model was confirmed, weakened, or falsified.

Do not add a generic score field merely to make unlike tasks look uniform. A
Markdown table, a task-native result file, a small parser, or a focused
analysis script is appropriate when it reflects the evaluator's real
semantics.

## Keep candidate identities separate

Maintain distinct references for:

- the original baseline;
- the incumbent best accepted or provisionally best candidate;
- the latest experiment; and
- exploratory branches not yet eligible for selection.

Do not overwrite the baseline or promote the newest result automatically.
When a candidate is selected, record its exact code, prompt, weights,
configuration, inputs, and receipt paths needed to reproduce it.

## Account for noise and search bias

Use repeats, paired cases, matched seeds, confidence intervals, or a practical
effect threshold when noise could reverse the decision. Treat differences
inside the decision threshold as ties and prefer lower retained complexity
when other evidence is equal.

Search adapts to development evidence. Prompt mutations informed by evaluator
feedback, hyperparameters selected on a validation set, kernels specialized to
sampled shapes, and code changed to satisfy visible tests can all overfit.
Reserve independent evidence proportional to that risk.

## Confirm the winner

Before acceptance:

- rerun hard correctness, safety, compatibility, and resource gates;
- reproduce the primary result with the same baseline protocol;
- use a clean process, fresh seed set, held-out cases, unseen workloads,
  independent scorer, or human review where applicable;
- inspect for missing work, cache artifacts, contamination, evaluator gaming,
  or shifted inputs; and
- report search cost separately when it is not part of the deployed outcome.

If confirmation fails, retain the receipt as evidence, demote the candidate,
and update the task model. Do not erase the failed confirmation or quietly tune
against the held-out boundary while continuing to describe it as independent.
