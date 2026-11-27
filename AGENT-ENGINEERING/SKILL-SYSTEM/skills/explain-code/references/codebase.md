# Codebase explainer mode

Build a durable mental model of the requested codebase, then present it as a polished interactive HTML guide. Optimize for comprehension and navigation, not exhaustive inventory.

## Investigate before writing

1. Resolve the repository root and requested scope. If the user names a subsystem, explain its place in the larger system before zooming in.
2. Read repository instructions and orientation material first: `AGENTS.md`, README files, manifests, build configuration, architecture docs, and relevant plans or ADRs.
3. Map the implementation from evidence:
   - Identify languages, frameworks, deployable units, entry points, and external dependencies.
   - Locate the main modules, domain types, state stores, persistence boundaries, APIs, queues, and UI surfaces.
   - Trace at least one representative user or system action end to end through actual call sites.
   - Use tests to confirm contracts, edge cases, and intended behavior. Use history only when it clarifies why the current shape exists.
4. Record concrete source anchors while investigating. Support implementation claims with repository-relative `path:line` references. Label inference, approximation, generated code, and pseudocode explicitly.
5. Prefer a few causal stories over a directory-by-directory catalog. Explain what happens, why each boundary exists, and how data or control changes along the way.

## Build the narrative

Scale the depth to the repository, but normally include these sections in this order:

1. **Orientation** — State what the system is, who or what uses it, the scope inspected, audience assumptions, and a short “start here” summary.
2. **Domain primer** — Define the smallest set of product and domain concepts needed to read the code. Keep a visible glossary for terms that recur.
3. **System map** — Show the major components and external actors, their responsibilities, and the important communication or data boundaries.
4. **Runtime story** — Walk one concrete example from trigger to outcome using realistic toy data. Tie every step to the component and source file responsible for it.
5. **Guided code tour** — Explain the few files and abstractions that unlock the rest of the repository. Group by responsibility, not alphabetically.
6. **State and contracts** — Explain important data models, state transitions, invariants, public interfaces, persistence, concurrency, and failure behavior where relevant.
7. **How to change it** — Point to extension seams and show where a reader would start for several common change types. Describe relevant tests and local verification commands without pretending to have run commands that were not run.
8. **Sharp edges and open questions** — Separate verified constraints from suspected risks or areas not inspected.
9. **Knowledge check (opt-in)** — Only when the user asks for one, build a bank of eight understanding questions by [knowledge-checks.md](knowledge-checks.md), displayed two at a time with a **New questions** button. Test causal understanding, boundary ownership, and change location with justification rather than file-name trivia.

For a very small codebase, combine sections instead of padding them. Never omit the mental model, one execution flow, or source anchors.

## Use a codebase-specific visual language

Read [visual-grammar.md](visual-grammar.md) before drawing; its pattern choice, budgets, and claim check apply to every figure below.

- Teach from overview to detail. Reuse the same component names, colors, and shapes in the context map, component map, runtime trace, and file guide so the reader never has to relearn the legend.
- Use a restrained semantic palette: for example, one color each for UI, application logic, persistence, and external systems. Never use color as the only carrier of meaning.
- Mark “you are here” as the narrative moves from system to subsystem. Use breadcrumbs or scope labels rather than redrawing unrelated context.
- Prefer these diagram families:
  - a context or component map for ownership and boundaries;
  - a left-to-right sequence or pipeline for the representative runtime story;
  - a state transition diagram when behavior depends on lifecycle, drawn from the strongest proof in [Prove a state machine before drawing it](#prove-a-state-machine-before-drawing-it);
  - a curated file atlas showing only the important paths and their roles;
  - a simplified product surface when visible UI behavior is essential.
- Put realistic example data on arrows and at state transitions. A diagram of boxes without an explained message, value, or event is rarely sufficient.
- Keep the geometry stable for repeated diagrams and emphasize the current step. Pair every figure with a title, one-sentence takeaway, legend when needed, source note, and text alternative.
- Use short, exact excerpts copied from the repository. Put them in `<pre><code>` blocks, cite `path:line`, explain why the excerpt matters, and visually connect it to the relevant runtime step. Label shortened or illustrative excerpts.

## Prove a state machine before drawing it

When behavior depends on a lifecycle, status field, reducer, or retry loop, draw the state diagram from the strongest proof available, and let its caption say which proof backs it:

1. **Checked model.** When a verified TLA+ model and its `view.mjs` cover the behavior, use the `statechart` skill's chart and cite the model, config, and check result.
2. **Walked code.** When the transitions live in a pure function with no I/O inside a step, write a throwaway script in a scratch directory outside the repository. It imports the real function, starts from the real initial state, and applies every named event to each reachable state breadth-first. Stop above about 2,000 states and model fewer fields or events instead of drawing a partial walk. Draw only the transitions the walk found. Write each rule the figure claims as `{holds, fails}`: a predicate plus a state the rule must reject. A predicate that is true on its own `fails` state passes on any machine and proves nothing. Report dead ends, events that never fire, drawn states nothing reaches, and the shortest event path to any broken rule; a broken rule stays on the page as a finding. Caption the figure as walked from the imported file. When a step does I/O, such as a fetch, timer, or database write, copy its logic into a hand model, cite the `path:line` each step copies, and caption the figure as walked from a model of that file.
3. **Illustrative sketch.** Otherwise, caption the figure as an illustration not checked against the code, and name the events, timers, retries, or concurrent actors it leaves out.

Never give a weaker proof the caption or visual confidence of a stronger one. A walk covers only the events it was given, so say what it omits.

## Codebase-specific HTML details

- Give the page a clear title, explanatory deck, scope/source note, and reading-time estimate.
- Write in clear, causal, classic expository prose. Start sections with the question they answer, use smooth transitions, and prefer concrete nouns and verbs over generic architecture jargon.
- Draw baseline diagrams with semantic HTML/CSS or inline SVG. Do not use ASCII art. Avoid unlabeled arrows, tiny text, and connector lines that cross labels.
- Use `<pre><code>` for every code block. Preserve whitespace, set a readable tab size and horizontal overflow behavior, and escape source text before inserting it into HTML.
- Use callouts sparingly for definitions, invariants, caveats, and “why this matters.” Use native `<details>` for optional depth, but keep the primary explanation visible by default.
- Purposeful interactions include trace highlighting, optional detail, copyable paths, and a requested knowledge check. Apply the shared optional-effects rule to everything else.

## Mode-specific verification

1. Confirm source anchors support the implementation claims and code excerpts preserve whitespace exactly.
2. If the page has a knowledge check, run the checks in [knowledge-checks.md](knowledge-checks.md#verify).
3. Stress long paths, wide diagrams, tables, and code at narrow widths.
4. Confirm a reader can identify the system boundary, one representative execution path, the important state and contracts, and where to begin a common change.
