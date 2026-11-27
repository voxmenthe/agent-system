# Tutorial track

Use this track to teach the underlying material deeply enough that a learner can explain, apply, and critique it. Treat the inspected sources as the evidence and teaching foundation, not as the page's organizing structure.

Quiz checkpoints are mandatory on this track. Read [knowledge-checks.md](knowledge-checks.md) with this file; every question here uses its question-and-reveal format, rotation rules, and checks.

## Contents

- [Design the learning path](#design-the-learning-path)
- [Teach each module deeply](#teach-each-module-deeply)
- [Interleave practice with instruction](#interleave-practice-with-instruction)
- [Build a substantial question library](#build-a-substantial-question-library)
- [Rotate questions without exposing the bank](#rotate-questions-without-exposing-the-bank)
- [Keep questions evidence-bound](#keep-questions-evidence-bound)
- [Verify the tutorial](#verify-the-tutorial)

## Design the learning path

1. Define the intended learner, prerequisites, learning objectives, and the tasks the learner should perform afterward. Infer a narrow learner profile only when necessary and label the assumption.
2. Build a concept dependency map from the evidence ledger. Order concepts by prerequisite, not by source or publication date.
3. Open with a motivating problem, concrete phenomenon, or worked case plus a short learning contract. Do not lead with a literature overview or a document catalog.
4. Use four to eight major learning modules for a normal corpus. Combine concepts when the evidence does not support that breadth; split a dense module when it contains independent prerequisite chains.
5. Begin with a short diagnostic checkpoint that activates prerequisites without revealing the later question bank.
6. End with an integrative application or capstone and a mastery map that points back to weak concepts. This supplements the interspersed checkpoints; it does not replace them with one final quiz.

## Teach each module deeply

Give every major module a learner-facing objective and normally include:

1. an intuitive model tied to a concrete example;
2. the mechanism, derivation, causal chain, or argument in explicit steps;
3. equations, diagrams, or worked examples when they materially improve understanding;
4. assumptions, boundary conditions, common misconceptions, and failure cases;
5. a transfer example that differs from the teaching example;
6. source anchors for factual claims and a clear label on pedagogical analogies or synthesis;
7. an immediate quiz checkpoint before the next major module.

Define terms at first use. Explain symbols in words. Use source titles only where provenance matters; organize the primary narrative around concepts, questions, and skills rather than documents.

## Interleave practice with instruction

- Place a diagnostic near the beginning and a checkpoint after every major learning module. Never defer all questions to the end.
- Show exactly two questions at each checkpoint, drawn from a per-module bank of at least six. Use the question-and-reveal format in [knowledge-checks.md](knowledge-checks.md) for all practice, including the diagnostic; do not add separate Feynman prompts or text-entry exercises.
- From the third module onward, mix at least one retrieval or transfer question from an earlier objective into each checkpoint.
- Invite the learner to articulate a brief answer mentally or aloud, then click **Show answer** for a model answer and expanded explanation of the reasoning, assumptions, and concept to revisit. No answer selection, submission, or grading is involved.
- Keep practice in the narrative flow. A global mixed-review control may supplement module checkpoints, but it must not become the only place questions appear.
- Do not use countdown timers, streak pressure, or punitive scoring unless the user explicitly requests them.

## Build a substantial question library

Author at least 36 distinct questions for a normal tutorial and target 48–72 when the corpus supports that depth. Do not pad a shallow source set with trivia, superficial paraphrases, or unsupported claims; if 36 defensible questions are impossible, state the smaller count and evidence limitation in the artifact and handoff.

Cover the learning objectives with materially different reasoning tasks:

- concept comparison with justification;
- mechanism or next-step prediction;
- worked calculation, derivation, or argument completion;
- misconception diagnosis and error correction;
- boundary-condition or counterexample analysis;
- transfer to a new scenario;
- evidence, method, or limitation interpretation; and
- concise causal explanation in plain language, with a concrete example or an analogy's limits.

Target **70% medium-level and 30% advanced** questions across the bank, rounding to whole questions, and distribute both levels across modules. Follow the difficulty definitions in [knowledge-checks.md](knowledge-checks.md); no separate question-type quota is needed. Variants must change the reasoning demand, scenario, misconception, or transfer context—not merely rename entities or paraphrase the prompt.

Represent the bank as structured data with fields equivalent to `id`, `module`, `objective`, `difficulty`, `prompt`, `answer`, `explanation`, and `sourceRefs`. All items use the same question-and-reveal interaction; omit choice lists, correct-option keys, response inputs, and grading rubrics. Validate required fields before the artifact is handed off.

## Rotate questions without exposing the bank

- Render exactly two questions at each checkpoint. Do not render the entire question bank up front, in a terminal mega-quiz, or in an expanded hidden DOM subtree.
- Store additional items as escaped structured data, such as JSON inside a non-executing `<script type="application/json">`, and construct later question controls safely. Escape `<` in serialized JSON so source text cannot terminate the script element; parse its `textContent` and populate controls with DOM text APIs rather than `innerHTML`.
- Provide a native button labeled **New questions** at every checkpoint. Replace the current set with unused eligible items from that module plus any scheduled retrieval items, without reloading the page. Reset both answer disclosures to collapsed for the new pair.
- Track seen question IDs for the current page session. Do not repeat a question from an eligible pool until that pool is exhausted. When a new cycle begins, announce that all available questions were seen before resetting the pool.
- Show a compact progress message such as “6 of 10 questions seen in this module.” Send rotation and cycle-reset messages through an `aria-live` status region and move focus only when that helps keyboard users retain context.
- Keep answer reveal and rotation operable by keyboard with native disclosure elements and buttons. Both the concise answer and expanded explanation stay hidden until the reader explicitly reveals them.
- Treat rotation as progressive enhancement. With JavaScript disabled, the initial interspersed questions, working answer disclosures in semantic HTML using `<details>`, concepts, examples, and citations must remain useful; only access to the larger rotating pool may be unavailable.

## Keep questions evidence-bound

- Link every question, model answer, and expanded explanation to one or more learning objectives and evidence-ledger anchors.
- Make prompts clear under the stated assumptions. Where multiple explanations or approaches are valid, describe the essential reasoning and acceptable alternatives without implying that the reader must reproduce the model answer verbatim.
- Preserve units, baselines, populations, and scope conditions in quantitative or empirical questions. Recheck calculations independently.
- Distinguish what the source measured, what its authors inferred, what the tutorial synthesizes, and what a hypothetical exercise assumes.
- Never turn an unresolved disagreement into a single-answer question unless the question tests recognition of that uncertainty.

## Verify the tutorial

Before handoff:

1. Confirm the module order follows concept prerequisites and that the primary path teaches mechanisms rather than summarizing documents.
2. Confirm a diagnostic and a quiz checkpoint appear in context before or after every major module, with spaced retrieval after the early modules.
3. Audit question IDs, counts, objective coverage, the 70% medium / 30% advanced difficulty mix, model answers, expanded explanations, calculations, and source references.
4. Exercise each **New questions** button through a complete pool. Confirm no item repeats before exhaustion, the reset is announced, progress is accurate, and module eligibility is preserved.
5. Test every answer reveal, its collapsed state after rotation, keyboard operation, focus behavior, and `aria-live` announcements. Confirm there are no answer choices, response text boxes, or separate teach-back exercises.
6. Inspect the page with JavaScript disabled. Confirm the initial interspersed practice and all instructional content remain coherent without the rotating bank.
7. Check that the full bank is not dumped into the visible page or print layout and that later questions do not leak their answers before interaction.
8. Report the total bank size, medium/advanced counts, modules covered, and any evidence-limited shortfall in the handoff.
