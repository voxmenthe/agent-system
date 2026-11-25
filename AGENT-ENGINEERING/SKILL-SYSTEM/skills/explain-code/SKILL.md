---
name: explain-code
description: Create a rich, self-contained HTML guide to a codebase or a code change. Use only when the user explicitly invokes $explain-code to explain an unfamiliar repository, subsystem, working-tree diff, commit, branch, or pull request. Do not use for ordinary repository exploration, implementation, code review, research corpora, or prose-only explanations.
disable-model-invocation: true
---

# Explain Code

Create one evidence-grounded, self-contained HTML artifact that helps a reader understand either a codebase or a code change. Preserve the two workflows below; they answer different questions.

## Choose the mode

1. **Codebase mode** — Use when the subject is the current structure and behavior of a repository, application, package, service, or subsystem. Read [references/codebase.md](references/codebase.md) completely before investigating or writing.
2. **Change mode** — Use when the subject is a working-tree diff, staged change, commit, branch, or pull request. Read [references/change.md](references/change.md) completely before investigating or writing.
3. **Combined mode** — Read both references only when the user explicitly wants both an architectural orientation and a change assessment in the same artifact. Keep the current-system model and the before/after verdict visibly distinct.

If the request is ambiguous, infer the mode from the named subject. Do not broaden a codebase guide into a diff review or a change explanation into a repository catalog.

Do not modify the codebase while producing the explanation unless the user separately asks for code changes.

## Shared artifact contract

- Produce one long, coherent HTML file with embedded CSS and optional JavaScript. Load no fonts, scripts, styles, images, or shader code from the network.
- Save it under `PLANS/EXPLANATIONS/` at the repository root by default, creating the directory if needed. Prefix the filename with the local timestamp in `YYMMDD-HHMM-` format and a descriptive slug.
- Keep the document useful without JavaScript. Essential text, evidence, navigation, conclusions, and source anchors must exist in semantic HTML; JavaScript is progressive enhancement.
- Use semantic headings and anchored navigation rather than top-level tabs. Keep prose near `65–75ch`; allow diagrams, tables, and code to use a wider responsive canvas.
- Establish a restrained design system with CSS custom properties, a consistent type and spacing scale, semantic colors, light and dark schemes, strong contrast, visible keyboard focus, and print styles.
- Make controls keyboard-operable with native elements and appropriate names, states, and status text. Never rely on color, motion, hover, or a canvas as the only carrier of meaning.
- Check desktop, narrow phone, and tablet layouts. Prevent horizontal page overflow while giving wide tables, diagrams, and code intentional local scrolling or reflow.

## Use question-and-reveal knowledge checks

Apply this format whenever the selected mode includes a quiz. It replaces multiple-choice and separate Feynman-style exercises.

- Show an open-ended question that the reader can answer briefly in their head or aloud, then a **Show answer** control. Do not offer answer choices, text boxes, textareas, editable response areas, submission, or automatic grading.
- Test understanding rather than bare recall: ask the reader to explain a causal mechanism, predict behavior, locate responsibility and justify it, diagnose a failure, or reason through a tradeoff or changed assumption. Avoid file-name trivia and definition-only prompts.
- Target **70% medium-level and 30% advanced** questions across the bank, rounding to whole questions. Medium questions apply or explain a taught mechanism; advanced questions combine concepts, analyze a boundary case, or transfer reasoning to an unfamiliar scenario. Keep this mix over a rotation cycle, not in every two-question display.
- Reveal a concise model answer followed by an expanded explanation: the reasoning, important assumptions or boundaries, a likely misconception when useful, and supporting `path:line` anchors. Keep both answer and explanation hidden until requested; a new question starts collapsed. Do not require a separate teach-back prompt or rubric.
- Display exactly two questions at a time from the mode's larger bank. Give each question a stable ID and record its objective, difficulty, prompt, model answer, explanation, and source anchors. Use a native **New questions** button to swap in unseen eligible questions. Do not repeat until the eligible pool is exhausted; announce a new cycle and show accurate progress.
- Keep the undisplayed bank in escaped structured data, not a visible list, hidden DOM subtree, or print appendix. Escape `<` in embedded JSON and build question content with DOM text APIs, not `innerHTML`. Refresh replaces the current pair and resets their answer reveals without reloading the page.
- Use native `<details><summary>Show answer</summary>…</details>` or an equivalent keyboard-operable disclosure with accessible names and expanded state. Announce rotation and cycle resets through `aria-live`, preserve useful keyboard focus, and keep the initial two questions with working answer disclosures in semantic HTML when JavaScript is disabled.

## Use contemporary visual capabilities selectively

Effects are optional. Add them only when they materially improve understanding of structure, causality, comparison, state, scale, uncertainty, or navigation. A quiet semantic HTML/CSS document is a complete and often preferable result.

- Prefer modern CSS as progressive enhancement: logical properties, grid and subgrid, container queries, `clamp()`, perceptual color functions such as `oklch()` and `color-mix()`, and feature-gated view or scroll-driven transitions when they clarify the narrative. Provide durable fallbacks with normal cascade order or `@supports`.
- Use motion to direct attention or preserve spatial context, not as ambient decoration. Respect `prefers-reduced-motion`; also consider `prefers-contrast`, forced colors, keyboard focus, and print. Do not hide required content behind animation.
- Inline SVG is the default for crisp explanatory diagrams. Use Canvas, WebGL2 shaders, or WebGPU only when GPU rendering makes a relationship substantially clearer—for example, a large topology, animated execution flow, state field, or genuinely data-backed surface.
- If Mermaid is selected, use [the focused authoring notes](references/mermaid-authoring.md) and verify the final rendered diagram; keep the artifact self-contained.
- Keep GPU visuals behind a stable semantic explanation or static SVG/HTML fallback. Feature-detect APIs, handle initialization failure and context or device loss, cap device-pixel ratio and work per frame, resize correctly, pause when offscreen or hidden, and stop continuous animation for reduced-motion users.
- Keep shaders small, local, deterministic, and subordinate to the prose. Do not place moving high-contrast shader fields behind long-form text. Never require a GPU effect to read evidence, operate controls, follow citations, or understand the conclusion.
- Use at most one primary motion or shader system unless multiple systems answer clearly different explanatory questions. Remove any effect whose explanatory value cannot be stated in one sentence.

## Verify and hand off

Follow the selected mode's evidence and narrative checks, then:

1. Search for placeholders, invented identifiers, broken anchors, missing source references, and claims stronger than the inspected evidence.
2. Confirm reading order and essential content without CSS or JavaScript. Exercise every control by keyboard and verify accessible names, states, and feedback. For quizzes, check the difficulty mix, source-grounded answers, initially collapsed reveals, and a complete refresh cycle without premature repeats or full-bank exposure.
3. Inspect desktop, phone, tablet, reduced-motion, light/dark, and print presentations when tooling permits. Exercise the static fallback for every optional modern feature.
4. Run `python3 ~/.agents/skills/create-verification-skill/scripts/html_preflight.py <file>` and fix every `DEFECT` it reports; what it lists as not checked still needs visual inspection.
5. Open or render the finished file, fix visible defects, and report its absolute path plus the exact repository scope or comparison explained.
