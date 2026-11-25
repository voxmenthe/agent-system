---
name: show-code
description: Explain a code change or focused mechanism through real source, relevant callers, data contracts, runtime flow, and consumers. Use when the user asks for show-code or a code-focused walkthrough that shows how a diff fits the existing codebase; do not use for implementation, a full defect review, broad repository onboarding, or an unsettled plan.
disable-model-invocation: true
---

# Show Code

Make the code understandable in its actual setting. The reader knows ordinary
programming but not this repository's names, inputs, or boundaries. They should
be able to explain what the important lines do, why they work here, and what
their callers and consumers depend on—without opening every linked file.

Use a guided explanation as the spine. Weave in a concrete runtime trace, the
data contracts needed to understand it, and questions that test the reader's
mental model. These are complementary lenses, not four reports to concatenate.

## Resolve the subject and read its context

1. Pin the question, comparison, and representative input. For a diff, resolve
   base and head separately; for uncommitted work, identify the inspected
   worktree/staged state and relevant edits. For a mechanism without a diff,
   name the inspected revision and omit invented before/after claims. Infer
   routine scope from the request and repository; ask only if materially
   different interpretations remain unresolved.
2. Read the complete relevant functions or types, the real caller and input
   preparation, the output consumer, and focused tests. Use history where it
   distinguishes intent from present behavior. A diff locates the change; it
   does not contain all the context needed to explain it.
3. Follow a value through that boundary, including the return path and material
   state, side effects, failure, or cleanup. Expand inspection when a claim
   depends on another seam; do not turn a focused walkthrough into a repository
   inventory. Distinguish imports, ownership, data flow, and actual call order.

Explain the inspected code; do not implement fixes, settle architecture, or
turn review questions into a full approval verdict. Separately authorized
implementation or review retains its own scope.

## Build one connected explanation

Start from [the walkthrough template](assets/walkthrough.md). Read
[the explanation patterns](references/explanation-patterns.md) when composing
the code walkthrough; they show how the four lenses reinforce one another.
Adapt headings to the subject and remove sections that add no understanding.

### Answer and orient

Open with the result and the load-bearing idea in two or three sentences.
Then state **Scope**: exact question, revision(s), representative input, and
whether this is the whole requested change or a named slice.

Give one small relation-specific map or before/after table. Mark **new**,
**changed**, and **existing context** accurately. Show where the changed code
joins its caller and consumer; a directory listing alone rarely answers that.
For a diagram, favor roughly seven elements and sixteen lines; split at a real
boundary if labels or connectors become hard to read. These are diagram
readability guides, not source-code line limits. Meaning must survive without
color. Mermaid is optional only when requested and must be rendered and checked.

### Teach the important code in context

For each load-bearing mechanism, keep this movement local:

- **Before the excerpt:** identify who calls it and what its input already
  means. Define repository-local names and transformations when first needed.
- **The excerpt:** show the exact expression, branch, signature, or type that
  carries the behavior. Include unchanged caller or consumer code when it
  supplies the missing explanation, not merely more changed lines.
- **After the excerpt:** walk the representative value through those lines,
  identify the consumer and preserved invariant, and explain the consequence.
  Attach precise source links to that connection.

Use paragraphs rather than repeating these labels. Prefer a complete local
thought over a fixed hunk count. Use language-tagged fences; source code may
wrap or scroll in its own panel without being squeezed into an ASCII diagram.
Trim irrelevant lines, but mark every elision and label simplified pseudocode.
Distinguish **real diff subset**, **new-file excerpt**, and **existing context**.
Never manufacture removed lines for a new file or call edited code verbatim.

### Carry the instance and contracts through the explanation

Keep one input or event recognizable from trigger to visible result. Show
important values at handoffs, including conversions, defaults, and the return
journey. A source-derived trace is not a captured runtime execution; label
worked arithmetic, illustrative inputs, and actual observations accordingly.

Explain the data meaning where it matters: producer, shape, units, ownership,
lifetime, and consumer expectations. Use a small type excerpt or table when it
clarifies the boundary. For caches or derived state, distinguish value changes
from invalidation and work that still runs. For absent/error values, explain
both the producer's condition and the consumer's handling; do not silently
turn null, zero, unavailable, or unbounded into the same concept.

### Answer the questions that would expose a wrong model

Use natural questions to organize the walkthrough or finish unresolved points:
why this branch exists, what remains unchanged, what happens at a boundary,
what a counterexample reveals, or which test checks the connection. Choose the
questions the code warrants, not a mandatory FAQ or safety checklist.

Connect evidence across seams: caller and callee, producer and consumer, or
mechanism and meaningful test. Code inspection supports behavior descriptions;
a test's presence is not a passing run, and a passing run is not proof of every
case. Do not infer a whole-system guarantee from a local optimization or check.

Finish with **Keep this line**: one accurate sentence the reader can repeat.

## Evidence and delivery

- Put compact receipts beside the claims they support. Show the file and
  complete cited line range; link each noncontiguous range separately. Use
  repository-relative file links with `#L<start>` when they resolve, or pinned
  repository URLs. When the host supports editor links, use its working
  file/line format. Check from the saved artifact's directory.
- Old claims need base evidence; new claims need head evidence. A current file
  link does not pin historical code. If the relevant checkout or remote is
  unavailable, preserve only the necessary exact excerpts with revision, path,
  and original line numbers; a source archive is not a routine deliverable.
- Keep material inference, proposed behavior, conditional guarantees, and
  unmeasured effects visible in the prose. Report tests as run now, prior
  results inspected, source assertions read, or not run. Run a focused check
  only when the explanation needs fresh behavioral evidence.
- Save a new `<topic>-YYYYMMDD.md` in the requested folder; otherwise use
  `PLANS/EXPLANATIONS/` relative to the subject repository. Markdown is the
  authored source. By default also render its sibling HTML using the helper
  below; honor Markdown-only requests. Do not make a new gallery or emit all
  four lenses as separate files.

## Render and verify

The optional helper script requires Python 3 and Pandoc already on the host:

```bash
python3 <skill-directory>/scripts/render.py <artifact-YYYYMMDD.md>
```

It creates sibling HTML with embedded CSS, syntax-highlighted code, a contents
list, and optional responsive code/explanation pairs. It does not fetch or
rewrite source links, copy source trees, or require a server. Use `--replace`
only to regenerate your own HTML. If Pandoc is unavailable, return the complete
Markdown and state that HTML was not rendered; do not install tooling just to
explain code. Keep authored HTML free of remote assets and required JavaScript.

Read the result as the target reader. Check code excerpts against their source
side, trace continuity, units and absent-value handling, and local links/ranges.
Remove repeated facts and unexplained identifiers. For HTML, inspect the final
desktop and narrow layout in an available browser; fix clipped explanations
and page overflow. Distinguish rendering checks from tests of the subject code.
Return links to the artifact(s), what they explain, and any material evidence
or rendering limitation.
