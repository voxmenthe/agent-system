---
name: evidence-driven-loop-judged
description: "Run an ARC-inspired improvement loop when better depends on subjective, qualitative, preference-based, or otherwise fuzzy evidence. Use only when the user explicitly invokes $evidence-driven-loop-judged or asks for an iterative judged-improvement campaign with no reliable ground-truth metric. Requires fresh subagent LLM judges and supports final human adjudication. Do not use when deterministic tests or direct measurements can decide the task, for routine one-pass work, or when no independent judge can be used."
disable-model-invocation: true
---

# Evidence-Driven Loop: Judged

Improve an artifact when no direct score can settle whether it is better. Keep
the ARC-style cycle of prediction, cheap action, exact observation, model
revision, and premise-triggered replanning, but make comparative judgment the
evaluation surface.

An LLM verdict is evidence, not ground truth. The optimizing agent must not
approve its own preferred candidate.

## Use the right variant

Use this companion for report quality, prompt or agent behavior, interface
clarity, memory usefulness, qualitative model outputs, and other outcomes that
require judgment. Preserve deterministic checks as hard gates wherever they
exist.

Use another evidence-loop variant when correctness tests, benchmark results,
timings, or other direct observations can decide the task. Compose with the
repository's normal implementation, safety, and verification workflows rather
than replacing them.

## Required role separation

- **Primary agent:** owns the task model, candidates, hard gates, evidence
  record, and next experiment. It may predict a winner but may not issue the
  decisive judgment.
- **Judge subagent:** independently compares artifacts against the current
  criteria. Use at least one fresh subagent as the LLM judge for every material
  candidate decision. For Codex-native launches, read the `orchestrate` skill's
  **Codex-native launch settings** and use its acceptance-judge mapping.
  Verify the resolved model/effort; the generic low-effort default is not
  sufficient for this role. Other hosts keep their existing model choices
  unless the user or harness specifies another. Give it a judge role in the
  prompt; do not require a provider-specific agent type.
- **Human judge:** optionally decides product meaning, unresolved tradeoffs, or
  consequential promotion when model judgment cannot support the claim.

Keep judge contexts fresh and independent. Judges are read-only: they do not
edit candidates, criteria, cases, or the evaluation process. Hide candidate
lineage, the optimizer's hypothesis, and other judges' verdicts when feasible.

For role choices, counterbalanced comparison, evaluation epochs, and human
escalation, read [comparative-judgment.md](references/comparative-judgment.md).

## Run the loop

### 1. Orient from authoritative evidence

Read the task, artifacts, repository constraints, and any existing evaluation
material. Verify conventions and judge semantics rather than assuming them.
Keep large outputs and complete judge records in task-local files; inspect them
with focused searches, parsers, and exact diffs instead of repeatedly pasting
them into context.

### 2. Define the current decision

State, in task-native language:

- the outcome being improved and the incumbent;
- hard gates that every candidate must pass;
- a short set of criteria for the fuzzy outcome;
- representative cases and important capabilities the cases do not cover;
- what evidence could favor, weaken, or leave the claim unresolved;
- the comparison budget, promotion rule, and stop conditions.

Freeze the criteria, cases, judge prompt or role, presentation format,
aggregation rule, and tie policy as one **evaluation epoch**. If a flaw requires
changing any of them, keep the earlier evidence under its old meaning, start a
new epoch, and re-evaluate the incumbent before comparing scores or wins.

### 3. Preserve a revisitable baseline

Generate incumbent outputs on the same cases the candidate will face. Preserve
the raw artifacts, inputs, relevant environment identity, and judge briefing.
Do not collapse the baseline into one subjective score.

### 4. Predict, then make the smallest useful change

Before editing, record which criterion should improve, why, what should remain
unchanged, and what observation would challenge the current model. Change one
coherent causal idea where practical. Produce candidate and incumbent artifacts
under comparable conditions and run hard gates before spending judge calls.

### 5. Delegate judgment

For an exploratory probe or a low-risk, easily reversible selection, a single
fresh judge subagent may nominate or provisionally support a candidate. Label
that evidence as single-order and keep its position-bias limitation visible.
For consequential promotion, compare the same artifacts in both presentation
orders using separate fresh judge contexts:

1. blinded `A` versus `B`;
2. blinded `B` versus `A`.

Ask each judge for `A`, `B`, `tie`, or `insufficient`, criterion-level reasons,
and citations to the supplied artifacts or cases. If the same presentation
position wins both orders, record an order-sensitive tie. Do not convert fuzzy
preferences into a fictitious absolute score.

### 6. Inspect exact outcomes and update the model

Retain each verdict and rationale separately. Inspect criterion-level evidence,
disagreement, omissions, hard-gate results, and exact candidate differences.
Do not let a majority summary erase contradictory evidence.

Compare the result with the prediction. Update confirmed findings, rejected
hypotheses, uncovered risks, and the verification ceiling. If the observation
changes a load-bearing premise, invalidate queued experiments and re-orient
before continuing.

### 7. Scale only after the comparison is informative

Begin with the cheapest case or judge call that can discriminate between the
working explanations. Broaden cases, judges, or candidate generation only
after the rubric and artifact presentation yield interpretable evidence.
Budget judge calls, retries, ties, and unusable verdicts as actions.

For consequential promotion, require a candidate that:

- passes hard gates;
- wins a direct, counterbalanced comparison against the incumbent;
- shows no material regression in protected or uncovered capabilities after an
  independent coverage or attack review when the stakes or coverage gaps
  require it; and
- survives a clean confirmation appropriate to the stakes.

Keep the simpler incumbent when evidence is tied or unstable. A judged win
supports only the declared comparison; it does not prove universal improvement.

### 8. Reset or escalate when the frame fails

If repeated predictions fail, judges remain inconsistent, preferences cycle,
or the criteria cannot express the real tradeoff, do not add judges indefinitely
inside the same frame. Record what has been ruled out, return to raw artifacts,
rederive the task and evaluator model, and begin a new epoch if warranted.

Escalate to a human when the remaining decision changes product meaning,
requires stakeholder authority, affects poorly covered capabilities, remains
cyclic or order-sensitive, or has high and hard-to-reverse consequences.
Present the evidence and disagreement; never fabricate a human verdict.

## Stop conditions

Stop when a candidate satisfies the declared promotion rule, the budget is
spent, the current evaluator cannot produce a stable preference, remaining
uncertainty exceeds the verification ceiling, or a human decision is required.
Report what improved, what the judges actually established, material
disagreement and blind spots, and what remains unknown.
