---
name: explain-research
description: Create a rich, self-contained HTML guide to papers, reports, specifications, or other documents as either an evidence synthesis or a deep tutorial with interspersed rotating quizzes. Use only when the user explicitly invokes $explain-research for a reading list or document corpus. Do not use for routine web research, codebase or diff explanations, ordinary summaries, or prose-only literature reviews.
disable-model-invocation: true
---

# Explain Research

Turn the requested source set into a traceable synthesis or a deep tutorial, then present it as a polished interactive HTML guide. Optimize for understanding the evidence or the underlying material, not for producing disconnected document summaries.

## Establish the corpus and evidence

1. State the research question, intended audience, requested documents, and boundaries of the corpus. If the question is implicit, infer a narrow working question and label it.
2. Acquire and read the actual sources when available. Prefer the original paper, report, specification, dataset documentation, or official artifact over secondary summaries. Do not rely on an abstract for claims that require methods, results, or limitations. Open every source you cite and confirm it makes the claim, or uses the term, the way you cite it; cut any citation you cannot confirm.
3. Build an evidence ledger before drafting. For each source, record:
   - full title, authors or issuing body, date, and stable link or local filename;
   - research question or purpose;
   - method, dataset or sample, comparison, and assumptions;
   - central findings with page, section, figure, or table anchors;
   - limitations, threats to validity, and important scope conditions.
4. Normalize terms that differ across documents, but preserve meaningful disagreements. Distinguish clearly among a source's measured result, the authors' interpretation, and your cross-source synthesis.
5. Calibrate every claim to its evidence. Report sample sizes, uncertainty, effect sizes, baselines, and units when supplied. Never invent missing values, citations, causal conclusions, or consensus. When a comparison rests on a small sample, say how far one case moves the result (with 43 cases, one case moves a rate by about 2.3 points, so smaller gaps are ties), and flag author, funder, or evaluator conflicts of interest and consequential denominator choices.
6. Note inaccessible, unreadable, or only partially inspected sources, and report retrieval gaps in the Orientation, such as a paywalled paper, a search that returned nothing after a date, or a section that would not extract. Do not silently substitute a review, blog post, or search snippet for a requested primary document, or silently narrow the corpus to what loaded.
7. Keep measured results from primary sources apart from secondary commentary, community reports, and press coverage. A forum thread is evidence that people report something, not that it is true.
8. Give every load-bearing factual claim either a citation link to its bibliography entry or an explicit `[unverified]` marker when it rests on model background knowledge or cannot be confirmed in the corpus. Never blend unsourced knowledge into cited prose. If `[unverified]` claims carry much of the argument, say so in the Orientation.

Quote only when wording itself matters; otherwise paraphrase and cite. Keep quotations short and respect applicable copyright limits. Mark every quotation with `<q>` or `<blockquote>`, copy it verbatim from the source text, and mark any omission with an ellipsis; the citation check compares each quotation with the sources.

## Choose the track

1. **Synthesis track** — Use when the user asks for an overview, literature synthesis, evidence comparison, or decision-oriented guide. Follow the synthesis narrative below.
2. **Tutorial track** — Use when the user asks to learn, be taught, or receive a deep tutorial on the material. Read [references/tutorial-track.md](references/tutorial-track.md) and [references/knowledge-checks.md](references/knowledge-checks.md) completely before outlining or writing. Teach the concepts and reasoning that the sources support; do not turn the track into a longer paper-by-paper overview.
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
9. **Knowledge checks (opt-in)** — Only when the user asks for practice, quizzes, or self-testing, insert a checkpoint after every major section, following [references/knowledge-checks.md](references/knowledge-checks.md). Otherwise spend that depth on the evidence. The tutorial track always uses checkpoints, with spaced retrieval and a substantial question library (see [references/tutorial-track.md](references/tutorial-track.md)).

For a single long document, adapt the corpus map into a structure-and-argument map. For a small source set, combine sections instead of manufacturing breadth. Never omit source traceability.

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
- Keep each SVG figure to at most 9 primary nodes, 12 arrows, and 2 accented elements; split an overview from its detail beyond that. Build a mechanism with three or more moving parts over two or three figures that each add one part, keeping the same geometry.
- Treat every drawn edge as a claim: each support, qualify, or challenge arrow in an evidence map must match a ledger entry.
- Give every figure a title, one-sentence takeaway, legend, source note, and text alternative. Place citations next to the claim or visual they support, not only in a bibliography.
- Use stable citation chips or footnote markers that link to a numbered bibliography: give each entry `id="src-<n>"` and link to it with `href="#src-<n>"`, the form the citation check reads. Cite local documents by filename plus page or section, and web sources with direct stable links. Include access dates when relevant.
- Present equations with embedded MathML or readable HTML when needed; define every symbol and immediately explain the equation in words. Do not require a CDN-rendered math library.

## Write plain, checkable prose

Write clear, careful expository prose. Lead with the question each section answers, define technical terms on first use, distinguish fact from inference, and use transitions that make the evolving argument explicit.

- **First words:** Start each list item and callout with the words that set it apart, such as **Confirmed:**, **Disputed:**, **Gap:**, or the method's name, never an opener every item shares.
- **Linked terms:** In the primer and glossary, bold other defined terms inside a definition and say how they relate. When you carry a term across papers or fields, say what carries over and where the analogy breaks.
- **Real names:** Use the source's own term, dataset name, or identifier, give each concept one name, and avoid "this" or "it" without an obvious referent.
- **No filler:** Cut sentences that would fit any corpus, stock metaphors such as "substrate" or "flywheel", and framing labels such as "the key insight" or "at its core". State the finding instead.

## Produce one excellent HTML artifact

- Write one self-contained HTML file with embedded CSS and optional JavaScript and no network-loaded fonts, scripts, styles, images, or shader code. The document must remain useful if JavaScript is disabled; use JavaScript only for progressive enhancement.
- Place this policy immediately after `<meta charset>`: `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:;">`. It blocks every network fetch while inline CSS, scripts, and SVG and `data:` images and fonts keep working; links to sources still navigate. If an inlined library needs something it blocks, such as `eval`, a worker, or a remote fetch, ship its rendered output instead of loosening the policy.
- Save it under `PLANS/EXPLANATIONS/` at the relevant repository or workspace root by default. Create the directory if needed. Prefix the filename with the local timestamp in `YYMMDD-HHMM-` format, followed by a descriptive slug, such as `PLANS/EXPLANATIONS/260721-1430-agent-memory-literature.html`.
- Use one long, coherent page with semantic section headings and anchored navigation. Do not use tabs for the top-level narrative. Include a compact sticky table of contents on wide screens and a simple collapsible contents control on narrow screens.
- Give the page a clear title, explanatory deck, corpus/scope note, and reading-time estimate. Keep prose columns near `65–75ch`; let evidence maps, tables, and figures use the wider canvas.
- Establish a deliberate design system with CSS custom properties, consistent spacing, type scale, border treatment, and semantic colors. Support light and dark color schemes, high contrast, visible keyboard focus, and `prefers-reduced-motion`.
- Use semantic HTML. Use real `<button>` elements for controls, `aria-expanded` where appropriate, keyboard-operable interactions, and status text that does not rely on color.
- Draw baseline diagrams with semantic HTML/CSS or inline SVG. Do not use ASCII art. Avoid decorative charts, illegible axis labels, tiny citations, and connector lines that cross text. Put wide comparison tables in labeled scrolling regions on phones.
- Use `<pre><code>` for quoted structured text or code. Preserve whitespace and provide safe overflow behavior. Escape all source text before inserting it into HTML.
- Use callouts sparingly for definitions, evidence-quality warnings, contradictions, and scope conditions. Use native `<details>` for per-paper depth or methods notes, while keeping the track's primary explanation visible by default.
- Add print styles that remove sticky UI and controls, expand essential evidence notes, preserve citations and URLs, and produce a legible PDF or paper copy.
- Keep interactions purposeful: evidence filtering, source highlighting, optional methods detail, citation navigation, and requested or tutorial quiz checkpoints are useful.

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
2. Run `python3 <skill-directory>/scripts/citation_ledger.py <file> --source <source-text> ...`, where `<skill-directory>` holds this file and each `--source` is the text of a quoted source (extract a PDF or web page to a scratch text file first). Fix every `DEFECT`: a page with no `#src-` citation link, an in-page link whose target is missing, a duplicate `id`, or a quotation not found verbatim in any source. Its count of prose blocks with neither a citation nor `[unverified]` is not verified by the check; read those blocks yourself.
3. Search for missing bibliography entries, ambiguous source labels, accidental causal language, inconsistent units, false precision, placeholders, and unlabeled inference.
4. Confirm every interactive control works with keyboard input. If the page has knowledge checks, run the checks in [references/knowledge-checks.md](references/knowledge-checks.md).
5. Check desktop, narrow phone, tablet, reduced-motion, light/dark, and print presentations when tooling permits. Exercise the static fallback for every optional modern feature.
6. Confirm the page makes sense in reading order with styles or JavaScript unavailable.
7. Run `python3 ~/.agents/skills/create-verification-skill/scripts/html_preflight.py <file>` and fix every `DEFECT` it reports; what it lists as not checked still needs visual inspection.
8. Open the finished file in a browser at 1× scale. Confirm the console shows no CSP or script errors, and look for clipped or overlapping text, labels detached from their connectors, connectors crossing boxes, content cut at a figure edge, and text too small to read; inspect tall figures in viewport-sized slices. Fix by restructuring before nudging coordinates, and stop after two fix passes. Report the absolute output path, corpus limitations, the citation check's counts, and any defect left.
