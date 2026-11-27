# Knowledge checks

Read this file completely before writing any question.

- **Tutorial track:** checkpoints are mandatory. Follow this format and [tutorial-track.md](tutorial-track.md), which sets the diagnostic, the per-module checkpoints, spaced retrieval, and the library of at least 36 questions.
- **Synthesis track:** checkpoints are off by default. Add them only when the user asks for practice, quizzes, or self-testing; then place one after every major section, showing exactly two questions drawn from a per-section bank of at least six.

## Question-and-reveal format

Use this format for every question, including diagnostics and inline practice. It replaces multiple-choice and separate Feynman-style exercises.

- Show an open-ended question that the reader can answer briefly in their head or aloud, then a **Show answer** control. Do not offer answer choices, text boxes, textareas, editable response areas, submission, or automatic grading.
- Test understanding rather than bare recall: ask why a mechanism works, predict a consequence, apply an idea to a new case, diagnose a misconception, or reason about an assumption or evidence limitation. Avoid trivia and definition-only prompts.
- Target **70% medium-level and 30% advanced** questions across the bank, rounding to whole questions. Medium questions apply or explain a taught concept; advanced questions combine concepts, analyze boundary cases, or transfer reasoning to an unfamiliar scenario. Distribute both levels across sections and preserve the mix over a rotation cycle, not in every two-question display.
- Reveal a concise source-grounded model answer followed by an expanded explanation of the reasoning, assumptions, boundary conditions, and useful misconception corrections, with evidence-ledger anchors. Keep both answer and explanation hidden until requested; a new question starts collapsed. Do not require a separate teach-back prompt or rubric.

## Rotation

- Give each question a stable ID and record its objective, difficulty, prompt, model answer, explanation, and source references. Keep the undisplayed bank in escaped structured data, not a visible list, hidden DOM subtree, or print appendix. Escape `<` in embedded JSON and build question content with DOM text APIs, not `innerHTML`.
- Use a native **New questions** button to replace the current pair with unseen eligible items and reset their answer reveals without reloading the page. Track seen IDs, avoid repeats until the eligible pool is exhausted, announce a new cycle, and show accurate progress.
- Prefer native `<details><summary>Show answer</summary>…</details>` or an equivalent keyboard-operable disclosure with accessible names and expanded state. Announce rotation and cycle resets through `aria-live` and preserve useful keyboard focus. With JavaScript disabled, the initial two questions at each checkpoint and their working answer disclosures must remain in semantic HTML; only rotation may be unavailable.

## Verify

1. Check the difficulty distribution and that every model answer and expanded explanation is source-grounded and readable by assistive technology after reveal.
2. Confirm reveals start collapsed, including after rotation, and run each **New questions** button through a complete cycle: no premature repeats, an announced reset, accurate progress, and no full-bank exposure in the page or print layout.
3. With JavaScript disabled, confirm the initial questions at every checkpoint and their answer disclosures still work.
