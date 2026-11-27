# Knowledge checks

Knowledge checks are off by default in both modes. Add one only when the user asks for a quiz, practice, or a way to test understanding; then read this file completely before writing questions. Codebase mode uses a bank of eight questions; change mode uses six to eight.

## Question-and-reveal format

This format replaces multiple-choice and separate Feynman-style exercises.

- Show an open-ended question that the reader can answer briefly in their head or aloud, then a **Show answer** control. Do not offer answer choices, text boxes, textareas, editable response areas, submission, or automatic grading.
- Test understanding rather than bare recall: ask the reader to explain a causal mechanism, predict behavior, locate responsibility and justify it, diagnose a failure, or reason through a tradeoff or changed assumption. Avoid file-name trivia and definition-only prompts.
- Target **70% medium-level and 30% advanced** questions across the bank, rounding to whole questions. Medium questions apply or explain a taught mechanism; advanced questions combine concepts, analyze a boundary case, or transfer reasoning to an unfamiliar scenario. Keep this mix over a rotation cycle, not in every two-question display.
- Reveal a concise model answer followed by an expanded explanation: the reasoning, important assumptions or boundaries, a likely misconception when useful, and supporting `path:line` anchors. Keep both answer and explanation hidden until requested; a new question starts collapsed. Do not require a separate teach-back prompt or rubric.

## Rotation

- Display exactly two questions at a time from the bank. Give each question a stable ID and record its objective, difficulty, prompt, model answer, explanation, and source anchors. Use a native **New questions** button to swap in unseen eligible questions. Do not repeat until the eligible pool is exhausted; announce a new cycle and show accurate progress.
- Keep the undisplayed bank in escaped structured data, not a visible list, hidden DOM subtree, or print appendix. Escape `<` in embedded JSON and build question content with DOM text APIs, not `innerHTML`. Refresh replaces the current pair and resets their answer reveals without reloading the page.
- Use native `<details><summary>Show answer</summary>…</details>` or an equivalent keyboard-operable disclosure with accessible names and expanded state. Announce rotation and cycle resets through `aria-live`, preserve useful keyboard focus, and keep the initial two questions with working answer disclosures in semantic HTML when JavaScript is disabled.

## Verify

1. Check the difficulty mix and that every model answer and expanded explanation is source-grounded and readable by assistive technology after reveal.
2. Confirm reveals start collapsed, including after rotation, and run one complete refresh cycle: no premature repeats, an announced reset, accurate progress, and no full-bank exposure in the page or print layout.
3. With JavaScript disabled, confirm the initial two questions and their answer disclosures still work.
