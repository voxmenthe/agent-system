---
name: evidence-driven-loop-minimal
description: "Run a compact prediction-action-observation loop for any task with observable acceptance evidence. Use only when the user explicitly invokes $evidence-driven-loop-minimal or asks for a minimal evidence-first improvement loop. Do not use for ordinary one-pass implementation, open-ended advice with no observable outcome, or work the agent lacks authority to perform."
disable-model-invocation: true
---

# Evidence-Driven Loop: Minimal

Improve the requested outcome by acting in the real task environment and
reading what actually happened. The task may be code optimization, model
training, prompt search, debugging, data work, or anything else with observable
evidence. Do not assume its evaluator, state, or controls follow a standard
shape; discover them from the task.

Put hard validity and acceptance conditions ahead of the improvement target,
and the improvement target ahead of secondary concerns such as experiment
speed, unless the user sets a different priority. A fast or high-scoring result
that fails a hard condition does not count.

## Work the loop

1. Inspect the current state, available tools, authority, budgets, and any
   evaluation conventions. Read formats, legends, test definitions, benchmark
   setup, and failure output before relying on them. Ask the user only when a
   missing judgment, scope choice, or authority boundary materially changes
   the task.
2. Identify the hard gates and the primary outcome. Establish the smallest
   credible baseline when safe and affordable. If the evidence is weak or the
   evaluator is only a proxy, say so.
3. Before each meaningful action, state the current model, the predicted
   result, and what observation would distinguish it from plausible
   alternatives.
4. Take the smallest useful action, then inspect the exact result. Treat
   errors, rejected actions, resets, timeouts, unchanged output, and consumed
   budget as evidence too.
   Expect hidden ceilings, reset conditions, cache effects, or resource limits
   until observations rule them out.
5. Prefer parsers, targeted queries, diffs, profiles, and small summaries over
   reading large raw states by eye or flooding context with logs. The task's
   raw output is authoritative; the conversation summary is not.
6. Use one or two cheap probes to test an uncertain mechanic. Once the premise
   predicts correctly, batch or automate a longer sequence. Before a costly
   sequence, simulate or reason through the expected result, then compare the
   real result with that prediction.
7. Keep durable task-local notes when the run may outlive the current context.
   Separate confirmed findings, live hypotheses, and ruled-out explanations.
   Keep useful parsers or helper scripts so results can be reproduced instead
   of re-derived.
8. If predictions keep failing, progress costs several times more than before,
   or the result cannot be explained, stop searching inside the current model.
   Record what it ruled out and re-derive the task from the observed objects,
   controls, data flow, and evaluator as if arriving fresh.
9. Repeat until the hard gates pass and the outcome is accepted, the agreed
   budget or stop condition is reached, or further action crosses an authority
   boundary. Confirm the best result with the same protocol used for the
   baseline and include a clean rerun when practical.

Do not mistake a successful command, a saved artifact, or an evaluator receipt
for proof that the task succeeded. Inspect the result it produced. Do not add a
database, daemon, universal schema, or permanent service merely to run this
loop.

At completion, report the best accepted result, the baseline and comparison
protocol, the decisive evidence, failed or ruled-out directions that matter,
and any limitation that remains unverified.
