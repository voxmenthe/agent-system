---
name: prepare-context
description: Build a local reviewer context bundle. Use when asked to prepare a handoff or bundle source context; do not use to transmit files, start an external chat, or implement changes.
disable-model-invocation: true
---

# Prepare Context

Create one self-contained reviewer bundle under `PLANS/PREPARED_CONTEXT/`. This skill creates local files only; it does not upload them or start an external model conversation.

## Resolve and assemble

Use the [resolver helper script](scripts/resolve_prepare_context.py) from the target repository root. Set `skill_dir` to the directory containing this loaded `SKILL.md`, not a fixed host path. Requires Python 3.12 or newer and the standard library.

```bash
uv run --no-project --python 3.12 python "$skill_dir/scripts/resolve_prepare_context.py" --create-output-dir --title "review-topic" "Full user request"
```

The helper creates an output directory and manifest JSON. It does not write the component documents or final bundle; their paths direct the following work.

1. Inspect the manifest, repository structure, key entry documents, and dedicated output directory before preparing or delegating components. Bounded scans and scores are hints, not coverage guarantees. Search beyond candidates where the request requires it; read the relevant source units and documents fully before relying on excerpts.
2. Consider the manifest's recent plans and commit narratives even when absent from starter lists. Decide relevance explicitly; recency is not automatic inclusion. Empty candidate buckets are not proof that no relevant material exists.
3. Write `request_summary_path`: topic, full request, constraints, reviewer questions, repository identity and current revision when available, and a compact structural overview. Note dirty-worktree or scan-coverage limits that affect the evidence. Keep the summary factual.
4. Write all four `component_paths` using the focus and component shape below. For a component with no relevant material, state what was checked and the gap rather than padding it. Prepare directly for small tasks; use the optional parallel mode when worthwhile.
5. After every component is complete, concatenate the request summary and four components in the manifest's `assembly_order` into `final_bundle_path`. The parent owns final assembly, including when workers prepare components.
6. Read the assembled bundle: confirm every component appears once, in order, under its component heading; reconcile contradictory claims and duplicate excerpts; repair thin or irrelevant sections. Each reviewer question must have enough context to answer or an explicit evidence gap. Do not treat a manifest or partial bundle as completion.
7. Report the final local path, intentional omissions, and evidence gaps.

## Component focus and shape

| Component | What the remote reviewer needs |
| --- | --- |
| Project/task overview | Purpose, architecture, key abstractions, configuration, and the relevant repository structure. Follow useful entry documents into nearby documentation and source. |
| Plan context | Current decisions, alternatives, constraints, open questions, and next steps relevant to the request. If `PLANS/` is absent, inspect relevant design docs, roadmap, changelog, or supplied planning material; distinguish historical intent from current behavior. |
| Recent change context | Relevant changes and their rationale or implications. If `PLANS/COMMITS/` is absent or insufficient, use bounded, path-scoped Git history and inspect relevant diffs. Do not invent rationale from commit titles or pull merely to prepare context. |
| Code context | Load-bearing interfaces, contracts, control flow, data models, configuration, tests, and error paths. Group by subsystem; use exact excerpts where reasoning depends on code and summarize repetitive bodies. |

Use this compact shape for each substantive component; adapt its length to the evidence:

```markdown
## <Component title>
### Why this matters
Connection to the request and reviewer questions.
### Source inventory
- Repository-relative path — why selected; revision or line references when useful.
### Extracted context
Focused excerpts with source paths and enough framing to interpret them.
### Preparation notes
Omissions, uncertainties, and limitations that affect the review.
```

Paths are provenance, not a substitute for content the reviewer cannot open.

## Optional parallel preparation

Use available, authorized native workers when substantial components can be prepared independently. Do not require a named Claude agent, a particular model, or four workers for every request. Otherwise prepare the components directly.

- The parent reads the manifest and key entry documents first and writes the request summary. Give each worker the full request and constraints, manifest path, assigned component paths, search roots and exclusions, starter hints, recent-context candidates, and the component guidance above.
- Assign exactly one writer to each component file; one worker may own several components. Workers may explore the supplied source boundary but write only their assigned outputs, not product files, another worker's component, or the final bundle. Do not recursively delegate component work.
- Join all workers before assembly. On failure or cancellation, stop and join any remaining writer before taking over its file; finish directly when feasible or report the incomplete component. Do not assemble a supposedly complete bundle from partial worker output.
- The parent checks coverage across components, resolves contradictions or duplicated material, and performs final assembly and readback. Proceed within existing authorization without a separate preview-approval checkpoint.

## Content contract

Include exact repository-relative paths and focused excerpts where reasoning depends on them. Prefer current source, active plans, tests, and relevant change evidence over stale design prose. Separate facts, inferences, and unverified runtime behavior. Supply enough context without relying on past conversation or linked local files; do not paste giant files indiscriminately.

Exclude credentials and unrelated private content. Existing output directories are not reused: choose a new title or output directory instead of overwriting a bundle. Preparing context does not authorize implementation or external transmission.
