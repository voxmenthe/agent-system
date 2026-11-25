---
name: codemap
description: Create a concise CODE-MAP.md explaining a codebase through two short paragraphs per area, with specific source links and evidence-backed design choices. Use when the user explicitly invokes codemap for a project or subsystem; do not use for general code questions, implementation, defect reviews, or exhaustive API documentation.
disable-model-invocation: true
---

# Codemap

Create an approachable, source-backed map of how a codebase works and why it
has its current structure. The reader knows programming but not this project.
This skill is explicit-invocation only; it is not an automatic onboarding step.

## Scope and destination

- Use the named codebase or subsystem; if none is named, use the current project.
- Honor the requested destination. Otherwise write `CODE-MAP.md` at the root of
  the mapped codebase. State the scope if it covers only a subsystem.
- Read an existing map before updating it. Change only the requested document;
  leave source, configuration, tests, and other documentation untouched.
- Produce Markdown only unless the user requests another format. Do not turn
  this into an architecture audit, redesign proposal, or generated source atlas.

## Understand the actual project

1. Read repository instructions and locate entrypoints, central data types,
   owning modules, tests, configuration, and nearby operating documentation.
   Start with scoped `rg --files` and `rg -n`; do not index an entire repository
   just to write the map.
2. Follow a representative input through its transformations to its output and
   consumers. Read the relevant behavioral units in full, including callers,
   important failure paths, and external or persistent boundaries.
3. Identify the project's real responsibilities. Include its main execution
   path and material supporting paths: interfaces, storage or retrieval,
   provider integrations, evaluation, tests/CI, packaging, and generated assets
   where they exist. Do not invent sections for machinery the project lacks.
4. Check rationale against code, tests, docs, and relevant history. Treat old
   plans as historical evidence, not a substitute for current implementation.
   If intent is undocumented, describe the visible tradeoff as an inference
   rather than inventing an author's motivation.

## Writing contract

Use a title followed by numbered area headings. Begin with the project as a
whole, then follow its execution path and supporting workflows. Group by
responsibility, not mechanically by file; a small project needs fewer sections
than a large one. There is no fixed section count.

Under **every area heading, write exactly two short paragraphs**:

- **First paragraph: how it works.** Explain the mechanism, important inputs
  and outputs, and a concrete function, type, rule, or execution path.
- **Second paragraph: why this shape.** Explain the meaningful design choice,
  ownership boundary, invariant, or tradeoff, supported by specific code.

Aim for roughly 50–90 words per paragraph, without padding a simple mechanism
or hiding an important distinction. Use plain language, natural prose, and
one or two meaningful **bold phrases** to make the central idea easy to scan.
Weave identifiers into explanations; do not dump symbol lists.

Each paragraph should link its load-bearing claims to concrete source examples,
usually one to three links. Use paths relative to the output document with
verified line anchors such as `src/reader.py#L42`; name the function or behavior
in the link label. Verify the file, line, and surrounding behavioral unit, not
just that the path exists. Avoid machine-specific absolute paths, fabricated
examples, or citations to a module that does not support the claim.

Keep the generated map in the two-paragraph format: no bullet lists, tables,
code dumps, diagrams, quizzes, extra how/why subheadings, or repeated summaries
unless the user requests them. Explain relevant failure behavior and limits
within the owning section. Separate current behavior, inferred rationale,
test coverage, and runtime evidence; a test's existence is not a passing run,
and a model-output schema is not proof of factual correctness.

## Tone example

This example illustrates prose and emphasis, not a required architecture.
An actual map must use the target codebase's behavior and verified code links.

Compacting is **deterministic selection, not an LLM summary**. Facts are grouped
by kind, category, code, and unit. Presets retain all history, several recent
timestamp groups, or only the latest group. Selection rules preserve active
items regardless of age, collapse unchanged categorical observations, and
supplement shortened numeric series with first/minimum/maximum readings—keeping
baselines and extremes alongside recent results.

The structure favors **explainability and auditability**: section rules declare
placement and budgets, while rendering directly produces text rather than an
intermediate display tree. Each emitted row gets a source-linked character
span; each omission gets a reason. Selected timestamp ties survive whole, so
conflicting measurements are not silently resolved. The underlying record
remains intact for lookup, making compression an inspectable view rather than
destructive data loss.

## Verify and deliver

Read the map against the code: check execution continuity, coverage of material
responsibilities, exact links and line anchors, and whether each design claim
is supported or clearly inferred. Check that every area has exactly two short
paragraphs and remove repeated detail or generic praise. Verify Markdown and
whitespace with the narrowest available checks; do not install tooling, run
expensive suites, or call providers merely to write documentation.

Return a link to the document, a brief statement of its coverage, and any
material scope or evidence limitation. Distinguish documentation checks from
tests or live execution of the subject project.
