# Change explainer mode

Create one self-contained HTML page that helps a skeptical reader understand what a code change actually accomplishes. Explain behavior first. Use code as evidence, not as the outline.

The page must answer:

1. Why was the change made?
2. What behavior, workflow, state transition, or failure path changed?
3. How fully does the change achieve its goals today?
4. How does the implementation produce that result?
5. What remains unchanged, unfinished, riskier, or more complicated?

A polished page cannot compensate for an unsupported verdict or a missing behavioral explanation.

## Contents

1. Investigate before writing
2. Reach a present-day verdict
3. Explain the relevant journey
4. Use visuals and code only when they help
5. Test claims against costs and counterevidence
6. Build the HTML narrative
7. Verify and hand off

## 1. Investigate before writing

1. **Identify the reader and purpose.** Use the user's stated audience, goals, and decision. If any are missing, make a reasonable assumption and label it.
2. **Pin the comparison.** Establish the exact base and head: working tree, staged changes, commit, merge base, branch, or pull request. Record immutable commit IDs when available and state the comparison in the artifact.
3. **Read the evidence.** Read repository instructions, the complete diff, and the relevant callers, tests, configuration, data models, examples, and documentation.
4. **Find the stated intent.** Prefer issues, PR descriptions, plans, ADRs, acceptance criteria, audits, commit messages, and tests. Extract concrete goals and intended end-state behavior.
5. **Define the scope.** State whether the diff is a complete change, a milestone, or an enabling slice of a larger program. Identify later work required for the promised end state.
6. **Trace behavior.** Follow at least one representative example through both the old and new behavior. Include an edge or failure case when it motivates the change.
7. **Record source anchors.** Support important implementation claims with repository-relative `path:line` anchors. Copy excerpts exactly and label shortened excerpts, omissions, illustrative code, or pseudocode.

If intent is not documented, say so. Do not infer a flattering motivation from the implementation. Do not stop at a file-by-file paraphrase: explain how the edits combine into a behavior change and why each important edit is necessary.

Keep an internal evidence ledger for important claims:

| Claim | Status | Evidence |
| --- | --- | --- |
| What changed | observed | diff or source anchor |
| Why it changed | stated or inferred | issue, plan, test, or reasoning |
| Practical effect | demonstrated or projected | workflow, command, test, or plan |

Label inference and projection clearly. Distinguish direct user value, enabling architecture, safety hardening, migration work, deletion, tests or documentation, and incidental edits.

Lead with behavior and practical effect. Put file inventories, commit lists, and line counts in optional depth unless they explain the outcome.

Quantify only what tests a real claim. If simplification or code reduction is claimed, separate production-source changes from tests, plans, generated files, and documentation. Line counts and conceptual consolidation are evidence, not proof, of simplicity.

## 2. Reach a present-day verdict

Assess each stated goal before designing the page. Use a scorecard for a multi-goal or staged change; use one compact paragraph for a small change.

For each goal, answer:

- What was difficult or impossible before?
- What does this exact diff remove, shorten, enable, or make safer?
- Can someone exercise the improvement now?
- What still blocks the full goal?
- What is the verdict?

Use these verdicts:

- **Clear improvement** — the diff delivers a usable outcome.
- **Partial improvement** — useful progress is available, but an important part remains.
- **Enabler only** — the architecture changed, but the intended payoff has not landed.
- **Unchanged** — the goal is not materially affected.
- **Regression or added cost** — the diff makes the goal harder or adds meaningful complexity.

Apply the stop-here test:

> If development stopped at this commit, would it be accurate to say the goal was achieved?

For a milestone or partial migration, answer that question near the beginning. Include a direct sentence equivalent to: **“If the project stopped here, …”**

Do not confuse:

- easier configuration with a faster end-to-end workflow;
- a cleaner authority model with a simpler implementation;
- planned deletion with complexity already removed;
- future behavior with behavior available today.

Avoid vague praise such as “foundation,” “coherent,” or “moves authority” unless it is followed by a concrete present-day effect.

## 3. Explain the change through the relevant journey

Choose the actor or system journey most closely tied to the main goal. It may involve a user, author, operator, maintainer, API consumer, runtime request, state transition, or failure path.

Show the journey before and after with concrete files, commands, inputs, outputs, and states. Explain:

- what the actor creates, edits, runs, or observes;
- which systems or files they touch;
- where external calls, billable usage, durable writes, deployments, or other side effects occur;
- what they can inspect after success or failure;
- what an edit invalidates or rebuilds;
- how quickly they can repeat the loop.

Include a representative failure path when it explains the value—for example, whether invalid input fails before a build, credential lookup, provider call, durable write, or deployment.

If the intended workflow is incomplete, show the usable partial path and the missing step. Never present a planned command or state as current behavior.

Before writing HTML, draft:

1. a one-sentence, falsifiable verdict;
2. the goal assessment;
3. the before-and-after journey;
4. the smallest technical mechanism that explains the change;
5. the main cost, limitation, and unfinished work.

A useful opening sentence is specific and mixed when the evidence is mixed:

> This diff removes the core-registration step from Evaluation authoring and adds provider-free build validation, but it does not yet deliver the interactive development loop or reduce total production code.

If the explanation cannot answer “why should I care?” without relying on internal module names, investigate further.

For a substantial change, prefer this page order:

1. **Bottom line** — old outcome, new outcome, verdict, scope, and missing pieces.
2. **Goal assessment** — a scorecard or compact verdict.
3. **Before and after** — the main journey or failure path.
4. **Larger-program context** — only when the diff is one stage of a broader effort.
5. **Core mechanism** — the minimum technical idea needed to understand the result.
6. **Change map and implementation** — edits grouped by what they accomplish, not diff order.
7. **Costs, risks, and unfinished work.**
8. **Evidence and validation** — tests, measurements, source anchors, and comparison metadata.

Combine or omit sections when appropriate. Name the page after the practical outcome, not only the internal mechanism. Keep the verdict and journey in the main reading path. Move secondary edge cases, schema details, exhaustive inventories, and low-level defenses into `<details>` or an evidence appendix.

Delete any fact that does not change the reader's understanding, decision, or ability to work with the change. Keep evidence, counterevidence, constraints, and uncertainty.

## 4. Use visuals and code only when they help

Choose each visual by the question it answers:

- Use a before-and-after journey as the first substantial visual.
- Use a milestone map for a staged change.
- Use a system or data-flow diagram only after the outcome is clear.
- Use tables for scorecards, authority changes, compatibility, and repeated mappings.

Keep before-and-after diagrams geometrically comparable. Dim unchanged elements; mark additions, removals, unchanged elements, and future elements with text or shape as well as color. Use realistic commands, data, and artifacts. Connect each changed code group to the journey step it affects.

Every figure needs a title, one-sentence takeaway, legend when needed, source note, and text alternative. Avoid decorative statistics, ambiguous counters, and card grids that merely restyle prose. Use at most one primary visual structure for each question, and keep the opening compact enough that the verdict appears in the initial laptop viewport. Do not make low-level machinery the visual center unless it is the reader's main concern.

Use side-by-side code only when both panes remain readable. Otherwise show old then new with matching highlighted regions and a concise explanation between them.

Explain implementation in proportion to its effect:

- Start each technical subsection with the behavior it enables or protects.
- Explain the concept before showing source detail.
- Cite important claims with repository-relative `path:line` anchors.
- Copy excerpts exactly; label omissions, shortened excerpts, and pseudocode.
- Connect each excerpt to a journey, behavior, or invariant.
- Move defensive details to optional depth unless they change the verdict.

Do not paraphrase every changed file. Apply the parent skill's optional-effects rule: animation, shaders, WebGL, and WebGPU are appropriate only when they explain the change better than a stable before/after diagram.

## 5. Test the claims against costs and counterevidence

Look for:

- new commands, files, concepts, or mandatory services;
- production-code growth or duplicated paths;
- transitional bridges or dual authorities;
- missing semantic validation;
- compatibility breaks or unsupported persisted data;
- new side effects in formerly pure operations;
- performance, memory, cache, or build costs;
- stale documentation or examples;
- planned deletion that has not occurred;
- acceptance criteria that remain unexercised.

State whether complexity was **removed**, **concentrated behind a boundary**, **shifted elsewhere**, or **temporarily increased**. These are different outcomes.

## 6. Build the HTML narrative

- Give the page a clear title, explanatory deck, comparison/scope note, and reading-time estimate.
- Write in clear, causal, classic expository prose. Use concrete nouns and verbs, open each section with the question it answers, and make transitions explain how one idea leads to the next.
- Keep the old/new story, verdict, and surrounding context visible in the primary reading path.
- Use callouts sparingly for definitions, invariants, edge cases, and “why this matters.” Use native `<details>` for optional depth.
- Interactive controls are optional. Useful examples include before/after emphasis, trace highlighting, optional detail, and copyable paths.
- A knowledge check is optional unless requested. When useful, build a bank of six to eight substantive questions using the parent skill's question-and-reveal format, 70% medium / 30% advanced target, and two-question display with **New questions** rotation. Emphasize motivation, practical behavior, tradeoffs, and migration consequences over line-number trivia.

## 7. Mode-specific verification and handoff

1. Recheck the comparison IDs and working-tree scope.
2. Verify every command, path, excerpt, line anchor, statistic, and compatibility claim.
3. Search for placeholders, invented identifiers, broken anchors, and inferred intent presented as fact.
4. Ensure the opening verdict is no stronger than the evidence in the body.
5. Keep achieved behavior, enabling work, and future work visibly distinct.
6. Confirm a reader can identify—without reading the code walkthrough—the goal, prior friction, current behavior, remaining gap, principal cost, and present-day verdict.
7. In the handoff, report the absolute output path and exact comparison explained.
