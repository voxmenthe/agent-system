---
name: backwards
description: Use only when explicitly invoked as `$backwards` to work backwards from an imagined finished outcome — interview by decision frontier, maintain one living document written as if the work already shipped (release narrative plus FAQ or blog post), and optionally turn it into a public presentation artifact. Do not use implicitly for ordinary planning, design, research, or implementation requests.
disable-model-invocation: true
---

# Backwards

Work from the finished outcome toward the project that must exist to make it true. Prose is the cheapest prototype: first make the imagined result coherent and compelling, then expose every decision, risk, and dependency hidden behind it.

Adapt the genre to the project: release notes or a README for a library or tool, a blog post for a product, an abstract or findings writeup for research. The audience may be customers, developers, readers, or the user themselves — establish which early.

Produce, in sequence:

1. One living Working Backwards document: release narrative, specification, FAQ.
2. If asked by the user (and after document approval): a launch post, interactive explainer, or demo site presenting the work as shipped.

## Establish the workspace

Read supplied plans, repository docs, and implementation context before asking questions. Research discoverable facts yourself; ask the user only for decisions, aspirations, taste, and priorities.

Choose one durable Markdown file, in priority order: the user's requested path; an existing repo convention for specs; `PLANS/<slug>-working-backwards.md` if `PLANS/` exists; `docs/<slug>-working-backwards.md` if `docs/` exists; otherwise `<slug>-working-backwards.md` in the project root. Announce the path, create it once the first interview round yields content, and update it after every round.

## Interview by decision frontier

Model the project as a **design tree**: every decision branches into the decisions that depend on it. The **frontier** is the set of unresolved decisions whose prerequisites are settled. Work in rounds:

1. Ask every question on the current frontier in one numbered batch, each with a concrete recommended answer and short rationale.
2. Defer any question whose answer depends on another open question.
3. Let the user answer tersely, accept recommendations, reject premises, or redirect the project.
4. Resolve contradictions explicitly; never silently pick one answer.
5. After each round, update the document with settled answers, keep unresolved items as open questions, summarize the material changes, and recompute the frontier.
6. Continue until the frontier is empty and no branch rests on a silent assumption.

Ask for decisions even when you can recommend the answer — the user's informed preference is part of the design, not missing data. Use subagents or tools for independent fact-finding; a pending fact blocks only its dependent branch, never the rest of the frontier.

Adapt the tree to the project, but cover these branches before declaring it complete (record why any doesn't apply):

- **Audience** — who it's for (user, developer, reader, beneficiary), who is excluded, the triggering need.
- **Problem** — status quo, current alternatives, why they fail, why now.
- **Outcome** — what exists when done, the transformed result, the believable reason to adopt it.
- **Behavior** — end-to-end walkthrough of the finished work: user journey, API/CLI surface, or findings as consumed; edge cases, failure, recovery.
- **Demonstration** — representative inputs and outputs, benchmarks, or examples that make the advance tangible.
- **Scope** — tenets, non-goals, tradeoffs, success metrics, acceptance promises, kill/pivot criteria.
- **Delivery** — top technical challenges, dependencies, risks, failure modes, constraints, sequencing.
- **Presentation** (public outcomes only) — intended audience reaction, narrative arc, release format.

## Maintain the document

Keep it a narrative, not an interview transcript. Rewrite earlier sections whenever later answers sharpen or invalidate them. Adapt structure to genre; a solid default:

1. **State header** — project, imagined ship date, draft/approved, audience, last updated.
2. **Release narrative** — headline, vivid problem, elegant solution, why now, a user or builder quote, call to action.
3. **Walkthrough** — concrete end-to-end story of the finished work in use.
4. **Results** — outcomes worth trumpeting, with specific imagined metrics, comparisons, or evidence.
5. **Full specification** — complete behavior from first contact through advanced use, edge cases, failure and recovery.
6. **FAQ** — the questions a skeptic would ask, external and internal: cost, access, trust, feasibility, risks, dependencies, why it could fail.
7. **Tenets, non-goals, promises** — durable tradeoff rules, exclusions, success measures, claims that become acceptance criteria.
8. **Open questions** — genuinely unresolved frontier items only; delete when empty.

Keep the narrative free of internal jargon; put uncomfortable honesty in the FAQ. Polished language must not conceal an incoherent experience, unsupported causal story, or unresolved risk.

## Write from inside the imagined future

State that the work exists, works, and achieves its designed results. No "concept," "proposed," or "if we build this" hedging unless the user asks. This is a document imagining the final product as if already shipped.

## Gate on approval

When the frontier is empty, state that shared understanding appears complete and ask the user to approve the document. Revisions reopen every affected branch: ask the newly exposed frontier, round by round, and seek approval again.

Then ask whether a presentation artifact serves the goal. If yes, recommend a format (editorial release post, interactive explainer, or demo/launch site) with a one-line rationale, and get confirmation before building.

## Build the presentation artifact

The approved document is the content source of truth; present the work as shipped and effective. Use the project's frontend stack if it has one, else a self-contained static site in a clearly named sibling directory. Load the `frontend-design` skill when available.

Commit to a distinctive visual direction derived from the project, not a generic template. Pace the narrative: immediate promise → problem-to-outcome transition → live-feeling demo → capabilities in realistic use → evidence → scannable FAQ → call to action. Use modern browser techniques — WebGL, scroll-driven storytelling, view transitions, variable typography, data visualization — purposefully and fairly aggressively, where they make an abstract capability felt.

Preserve quality while experimenting: progressive enhancement, reduced-motion and keyboard support, semantic structure, legible contrast, responsive behavior, no ornamental motion, no heavy assets blocking the narrative. Verify representative viewports, primary interactions, and graceful degradation in a real browser.

Do not implement the underlying project itself — only the artifact, including whatever demos or simulations communicate the approved future.

## Completion conditions

- The decision frontier is empty and the user has approved the document.
- The artifact question is settled; if built, it faithfully expresses the approved narrative, walkthrough, and results, and works responsively and accessibly with graceful fallbacks.
- The final reply links the document and, if built, the artifact entry point.
