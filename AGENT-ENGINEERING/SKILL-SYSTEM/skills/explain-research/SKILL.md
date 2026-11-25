---
name: explain-research
description: Create a rich, self-contained HTML guide to papers, reports, specifications, or other documents as either an evidence synthesis or a deep tutorial with interspersed rotating quizzes. Use only when the user explicitly invokes $explain-research for a reading list or document corpus. Do not use for routine web research, codebase or diff explanations, ordinary summaries, or prose-only literature reviews.
disable-model-invocation: true
---

# Explain Research

Turn the requested source set into a traceable synthesis or a deep tutorial, then present it as a polished interactive HTML guide. Optimize for understanding the evidence or the underlying material, not for producing disconnected document summaries.

## Establish the corpus and evidence

1. State the research question, intended audience, requested documents, and boundaries of the corpus. If the question is implicit, infer a narrow working question and label it.
2. Acquire and read the actual sources when available. Prefer the original paper, report, specification, dataset documentation, or official artifact over secondary summaries. Do not rely on an abstract for claims that require methods, results, or limitations.
3. Build an evidence ledger before drafting. For each source, record:
   - full title, authors or issuing body, date, and stable link or local filename;
   - research question or purpose;
   - method, dataset or sample, comparison, and assumptions;
   - central findings with page, section, figure, or table anchors;
   - limitations, threats to validity, and important scope conditions.
4. Normalize terms that differ across documents, but preserve meaningful disagreements. Distinguish clearly among a source's measured result, the authors' interpretation, and your cross-source synthesis.
5. Calibrate every claim to its evidence. Report sample sizes, uncertainty, effect sizes, baselines, and units when supplied. Never invent missing values, citations, causal conclusions, or consensus.
6. Note inaccessible, unreadable, or only partially inspected sources. Do not silently substitute a review, blog post, or search snippet for a requested primary document.

Quote only when wording itself matters; otherwise paraphrase and cite. Keep quotations short and respect applicable copyright limits.

## Choose the track

1. **Synthesis track** — Use when the user asks for an overview, literature synthesis, evidence comparison, or decision-oriented guide. Follow the synthesis narrative below.
2. **Tutorial track** — Use when the user asks to learn, be taught, or receive a deep tutorial on the material. Read [references/tutorial-track.md](references/tutorial-track.md) completely before outlining or writing. Teach the concepts and reasoning that the sources support; do not turn the track into a longer paper-by-paper overview.
3. **Combined track** — Use both only when the user explicitly requests a synthesis and a tutorial in one artifact. Keep the evidence verdict and the instructional sequence distinct, and reuse rather than duplicate explanations.

Default to the synthesis track when the request does not identify a learning goal. Produce one artifact unless the user asks for separate outputs.

## Build the synthesis track

For the synthesis track, scale the depth to the corpus, but normally include these sections in this order:

1. **Orientation** — State the question, why it matters, the corpus, audience assumptions, and a concise synthesis up front.
2. **Conceptual primer** — Explain the minimum background, terminology, measurements, and methodological concepts needed to evaluate the sources.
3. **Corpus map** — Introduce the documents by the role each plays in the evidence, not merely by publication order. Show the reading strategy and important source relationships.
4. **Synthesis by question** — Organize the main body around the questions the evidence can answer. For each conclusion, show supporting sources, contrary evidence, boundary conditions, and confidence.
5. **Methods and results comparison** — Compare populations or datasets, interventions, baselines, metrics, designs, and limitations in a scannable matrix. Explain when results are not directly comparable.
6. **Disagreements and uncertainty** — Diagnose whether apparent conflicts come from definitions, methods, populations, time, assumptions, statistical uncertainty, or genuinely different findings.
7. **Implications and open questions** — Separate source-backed implications from your inference. Identify missing evidence and the next readings or experiments that would reduce uncertainty.
8. **Guided reading path** — Recommend an efficient order for readers who have 10 minutes, one hour, or time for the full corpus.
9. **Interspersed knowledge checks** — After every major section, insert a short quiz that displays exactly two questions drawn from a per-section bank of at least six. Use the question-and-reveal format below and provide a **New questions** button at each checkpoint so the reader can rotate through unseen questions without exposing the full pool. Both tracks use these checkpoints; the tutorial track adds spaced retrieval and a substantial question library (see [references/tutorial-track.md](references/tutorial-track.md)).

For a single long document, adapt the corpus map into a structure-and-argument map. For a small source set, combine sections instead of manufacturing breadth. Never omit source traceability or the interspersed knowledge checks.

## Use question-and-reveal knowledge checks

Use this format in both tracks, including diagnostics and inline practice. It replaces multiple-choice and separate Feynman-style exercises.

- Show an open-ended question that the reader can answer briefly in their head or aloud, then a **Show answer** control. Do not offer answer choices, text boxes, textareas, editable response areas, submission, or automatic grading.
- Test understanding rather than bare recall: ask why a mechanism works, predict a consequence, apply an idea to a new case, diagnose a misconception, or reason about an assumption or evidence limitation. Avoid trivia and definition-only prompts.
- Target **70% medium-level and 30% advanced** questions across the bank, rounding to whole questions. Medium questions apply or explain a taught concept; advanced questions combine concepts, analyze boundary cases, or transfer reasoning to an unfamiliar scenario. Distribute both levels across sections and preserve the mix over a rotation cycle, not in every two-question display.
- Reveal a concise source-grounded model answer followed by an expanded explanation of the reasoning, assumptions, boundary conditions, and useful misconception corrections, with evidence-ledger anchors. Keep both answer and explanation hidden until requested; a new question starts collapsed. Do not require a separate teach-back prompt or rubric.
- Give each question a stable ID and record its objective, difficulty, prompt, model answer, explanation, and source references. Keep the undisplayed bank in escaped structured data, not a visible list, hidden DOM subtree, or print appendix. Escape `<` in embedded JSON and build question content with DOM text APIs, not `innerHTML`.
- Use a native **New questions** button to replace the current pair with unseen eligible items and reset their answer reveals without reloading the page. Track seen IDs, avoid repeats until the eligible pool is exhausted, announce a new cycle, and show accurate progress.
- Prefer native `<details><summary>Show answer</summary>…</details>` or an equivalent keyboard-operable disclosure with accessible names and expanded state. Announce rotation and cycle resets through `aria-live` and preserve useful keyboard focus. With JavaScript disabled, the initial two questions at each checkpoint and their working answer disclosures must remain in semantic HTML; only rotation may be unavailable.

## Use a research-specific visual language

- Assign a stable visual identity to each source, theory, or evidence class and reuse it across source cards, timelines, comparison tables, and evidence maps. Pair color with labels or shapes.
- Prefer visualizations that clarify an actual relationship:
  - an argument or claim-evidence map showing which sources support, qualify, or challenge a conclusion;
  - a lineage or timeline only when chronology changes interpretation;
  - a comparison matrix for methods, samples, measures, and limitations;
  - small multiples for genuinely comparable quantitative results;
  - an uncertainty or applicability map for scope conditions and evidence gaps.
- Encode numbers only from source data. Preserve units and baselines, label transformations, avoid false precision, and never draw an apparently quantitative chart from qualitative impressions.
- Make non-comparability visible rather than forcing unlike results onto one scale. Use annotations to explain the reason.
- Give every figure a title, one-sentence takeaway, legend, source note, and text alternative. Place citations next to the claim or visual they support, not only in a bibliography.
- Use stable citation chips or footnote markers that link to a numbered bibliography. Cite local documents by filename plus page or section, and web sources with direct stable links. Include access dates when relevant.
- Present equations with embedded MathML or readable HTML when needed; define every symbol and immediately explain the equation in words. Do not require a CDN-rendered math library.

## Produce one excellent HTML artifact

- Write one self-contained HTML file with embedded CSS and optional JavaScript and no network-loaded fonts, scripts, styles, images, or shader code. The document must remain useful if JavaScript is disabled; use JavaScript only for progressive enhancement.
- Save it under `PLANS/EXPLANATIONS/` at the relevant repository or workspace root by default. Create the directory if needed. Prefix the filename with the local timestamp in `YYMMDD-HHMM-` format, followed by a descriptive slug, such as `PLANS/EXPLANATIONS/260721-1430-agent-memory-literature.html`.
- Use one long, coherent page with semantic section headings and anchored navigation. Do not use tabs for the top-level narrative. Include a compact sticky table of contents on wide screens and a simple collapsible contents control on narrow screens.
- Give the page a clear title, explanatory deck, corpus/scope note, and reading-time estimate. Keep prose columns near `65–75ch`; let evidence maps, tables, and figures use the wider canvas.
- Write in clear, careful expository prose. Lead with the question each section answers, define technical terms on first use, distinguish fact from inference, and use transitions that make the evolving argument explicit.
- Establish a deliberate design system with CSS custom properties, consistent spacing, type scale, border treatment, and semantic colors. Support light and dark color schemes, high contrast, visible keyboard focus, and `prefers-reduced-motion`.
- Use semantic HTML. Use real `<button>` elements for controls, `aria-expanded` where appropriate, keyboard-operable interactions, and status text that does not rely on color. Make quiz feedback available to assistive technology.
- Draw baseline diagrams with semantic HTML/CSS or inline SVG. Do not use ASCII art. Avoid decorative charts, illegible axis labels, tiny citations, and connector lines that cross text. Put wide comparison tables in labeled scrolling regions on phones.
- Use `<pre><code>` for quoted structured text or code. Preserve whitespace and provide safe overflow behavior. Escape all source text before inserting it into HTML.
- Use callouts sparingly for definitions, evidence-quality warnings, contradictions, and scope conditions. Use native `<details>` for per-paper depth or methods notes, while keeping the track's primary explanation visible by default.
- Add print styles that remove sticky UI and controls, expand essential evidence notes, preserve citations and URLs, and produce a legible PDF or paper copy.
- Keep interactions purposeful: evidence filtering, source highlighting, optional methods detail, citation navigation, and quiz checkpoints or rotation are useful.

## Use contemporary visual capabilities selectively

Effects are optional. Add them only when they materially improve understanding of evidence relationships, chronology, comparison, scale, uncertainty, or navigation. A clear static artifact is complete.

- Prefer modern CSS as progressive enhancement: logical properties, grid and subgrid, container queries, `clamp()`, perceptual color functions such as `oklch()` and `color-mix()`, and feature-gated view or scroll-driven transitions when they clarify the argument. Supply durable cascade or `@supports` fallbacks.
- Use motion to direct attention or preserve spatial context, not as ambient decoration. Respect `prefers-reduced-motion`; also consider `prefers-contrast`, forced colors, keyboard focus, and print. Do not hide evidence behind animation.
- Inline SVG is the default for research figures. Use Canvas, WebGL2 shaders, or WebGPU only when GPU rendering makes a source-backed relationship substantially easier to understand, such as a large evidence network, high-density parameter surface, or time-varying model state.
- A GPU view must be paired with a semantic explanation, values or source data when applicable, and a static SVG/HTML fallback. Feature-detect APIs, handle initialization failure and context or device loss, cap device-pixel ratio and work per frame, resize correctly, pause when offscreen or hidden, and stop continuous animation for reduced-motion users.
- Keep shaders small, local, deterministic, and subordinate to the argument. Never infer, interpolate, or decorate missing quantitative evidence in a way that appears measured. Do not place moving high-contrast shader fields behind long-form text.
- Use at most one primary motion or shader system unless each additional system answers a different research question. Remove any effect whose explanatory value cannot be stated in one sentence.

## Verify the artifact

Before handing it off:

1. Audit each substantive claim against the evidence ledger. Confirm citations resolve to the claimed page, section, figure, table, or stable source.
2. Search for missing bibliography entries, ambiguous source labels, accidental causal language, inconsistent units, false precision, placeholders, and unlabeled inference.
3. Confirm every interactive control works with keyboard input. Check quiz difficulty distribution, source-grounded model answers and expanded explanations, initially collapsed reveals, and a complete refresh cycle without premature repeats or full-bank exposure.
4. Check desktop, narrow phone, tablet, reduced-motion, light/dark, and print presentations when tooling permits. Exercise the static fallback for every optional modern feature.
5. Confirm the page makes sense in reading order with styles or JavaScript unavailable.
6. Run `python3 ~/.agents/skills/create-verification-skill/scripts/html_preflight.py <file>` and fix every `DEFECT` it reports; what it lists as not checked still needs visual inspection.
7. Open or render the finished file, fix visible defects, and report the absolute output path plus any corpus limitations.
