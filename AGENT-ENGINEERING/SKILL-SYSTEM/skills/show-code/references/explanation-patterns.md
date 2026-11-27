# Four lenses, one reading journey

Sections A–E compose the four lenses. Sections F–K cover multi-file diffs,
diagram choice, state machines, UI changes, and redaction.

## A · Guided code is the spine

An isolated `return withSelection(input, cached.surface)` explains little.
The useful explanation establishes where the builder lives, who creates the
input, what the surface retains, and who consumes the returned selection.

Keep those facts next to the code they explain. When a local name hides a
type boundary, spell it out: a panel's `analysis.analysis` can mean the scenario
analysis nested inside a richer workspace analysis, rather than two analysis
calls. Quote the type or caller only when it helps the reader see that boundary.

For a change, pair old and new behavior at the same level. An old caller using
coarse samples and a new caller using a focused model are comparable; an old
architecture diagram beside one new assignment is not yet an explanation.

## B · Trace a value through the spine

The trace can be the document's order or a small local zoom:

```text
pointer X → domain-relative price → reducer-owned selected price
          → normalized analysis → exact selected result → chart + readout
```

This is an illustrative data flow, not a literal call stack. A real explanation
names the inspected functions and shows conversions where they occur. Include
the return journey: if rendering replaces DOM nodes, restoring focus or open
disclosures is part of understanding the interaction, not incidental UI trivia.

Carry the same value across sections. If the pointer rounds to cents but a
model test uses extra decimals, distinguish those paths rather than suggesting
the browser supplies the test's exact input.

## C · Explain contracts at the handoff that needs them

Types are useful when they explain a distinction, not as an inventory.

| Data | Meaning to explain | Why it can matter |
|---|---|---|
| Observed value | Input captured from context | Moving a hypothetical cursor must not redefine it |
| Selected value | Current user-controlled scenario | Must agree with the returned numeric result |
| Retained surface | Values reusable under a named key | Cursor moves must not grow its history |
| Optional result | Domain-specific absence | Consumer must distinguish unavailable from zero |

For a cache, trace the owner of the cached closure as well as the key. Creating
a builder inside a render function differs from creating it once outside.
Explain which inputs invalidate the cache and which still cause work elsewhere.
For example, a table-only control may invalidate a shared surface even when
main-curve values are numerically unchanged.

For nullable data, pair the producer's branch with the consumer's guard. A
non-null assertion is not self-explanatory, and seeing `null` in a type does not
tell the reader what the UI does with it.

## E · Questions reveal the important consequences

Choose questions whose answers need actual code connections. Useful examples:

- Does this operation reuse old results, or can it return stale values?
- Does a display boundary also limit the underlying calculation?
- Which unchanged code still runs before this optimization?
- Which test would fail if the producer and consumer disagreed?

Answer first, walk a concrete case, show the mechanism, then state the limit.
If a test compares a cached build with a fresh one, explain what that comparison
can falsify. Do not substitute a test count for understanding or imply that a
source-derived scenario was executed.

## Compose, do not stack

A cache change might use this order:

1. Result and small before/after view.
2. Caller constructs the input; explain its significant fields.
3. One event reaches the cache decision; trace its value and key dependencies.
4. Exact source shows how the result is constructed and consumed.
5. A boundary question tests the model; a focused assertion supports the answer.
6. The remaining limit and repeatable takeaway.

The same field should not be reintroduced in a type catalog, runtime catalog,
and review catalog. Add a separate trace or table only when prose alone leaves
the handoff hard to follow. A small neighborhood map can orient the reader,
but a change atlas is not another required output mode.

## F · Fold a multi-file diff by attention

A twelve-file change explained at one depth buries the three lines that matter.
Plan coverage before writing.

**Group and order.** Group changed files by concern, and keep each test with
the code it tests. Order the groups from the caller-facing entry point down
through the layers, never alphabetically.

**Rate each group.** **Read closely** goes deep. **Read through** gets a short
paragraph per change. **Skim** gets a sentence or two. The rating sets prose
depth; it never removes a change from coverage.

**Fold by default.** Put each excerpt in a closed `<details>` with a summary
that says what the code does. Open it only when one of these fires:

| Trigger | When | Rating it survives |
|---|---|---|
| `SUBTLE` | edge cases, ordering, off-by-one, error or retry paths, concurrency, a tricky condition | any |
| `HIDDEN EFFECT` | the signature hides a mutation, side effect, or surprising return | any |
| `CORE` | the new non-trivial logic the reader came for, not reconstructable from its signature | any |
| `SMALL` | about ten changed lines or fewer | Read closely only |

A file being new is not a trigger. Routine wiring, boilerplate, and mechanical
churn fold however large they are; describe their shape in prose. These never
open:

- **Delegation facades** whose methods only forward: say what they front and
  where the real work lives. A method that does real work is judged on its own.
- **Whole test files** for code changed elsewhere: say what they cover. Open
  one test only when its setup is genuinely subtle. When the suite is the
  subject, show the representative and novel cases and fold the rest.
- **Generated files**: name the tool that produced them.

A folded excerpt in the Markdown source:

````markdown
<details>
<summary><code>cli.py</code> turns bytecode off before importing its sibling library (2 lines)</summary>

```python
sys.dont_write_bytecode = True
import lib  # noqa: E402
```

</details>
````

Leave a blank line after `<summary>` and before `</details>` so Pandoc still
renders the fenced code inside.

## G · Own each changed file once, and account for every file

Every changed file or symbol has exactly one owning section, usually its
highest-attention group, which explains it in full. Any other section that
touches it gets one line of context in its own terms and a link back to the
owner's heading, written as `[see How state leaves the skill](#how-state-leaves-the-skill)`.
Do not re-slice or re-explain the same lines there.

List the files you skip as mechanical in one folded line: lockfiles,
snapshots, fixtures, generated code, renames, and one-line path updates in
docs. For example: "Folded 4 mechanical
files: two deleted state files and two doc path updates." Before returning,
compare the owned and folded files with `git diff --name-only <base>..<head>`;
the counts must add up, so a reader can see nothing was silently dropped.

## H · Choose the diagram by what it must show

Ask two questions: does the reader need every path or one message's trace, and
does it cross components or stay inside one?

| | Every path | One message |
|---|---|---|
| Between components | `flowchart TD`: who exists, who imports or calls whom | sequence or service trace: one message crossing components and the state it changes |
| Inside one component | pseudocode and types: its state, payloads, branches | call stack as data flow: `result = fn(inputs)` rows nested with `├──` and `└──` |

Mark added nodes or edges with a thicker stroke or `==>`, never with color
alone. Never use a sequence diagram for static structure. Keep at most five
nodes across, and split a wider diagram at a real boundary.

## I · State machines: use the strongest evidence you have

1. **Checked model.** When a verified TLA+ model and its `view.mjs` cover the
   machine, show the `statechart` skill's chart and cite the check.
2. **Walked code.** For a pure reducer or transition function with at most
   about 2,000 reachable states, write a small throwaway script that imports
   the real function and walks it breadth-first from its initial state over
   every event. Give each rule a `holds` predicate and a state it `fails` on,
   and confirm the rule rejects that state, or the rule proves nothing. Draw
   what the walk reached and report dead ends, events that never fire, and the
   shortest path to any broken rule.
3. **Sketch.** Otherwise label the drawing an illustrative sketch and name the
   events, timers, or concurrency it leaves out.

## J · UI changes: cover four surfaces

A before/after of the entry button is not enough. Trace the entry affordance
(the toolbar, row, or menu item that changed), the surface it opens (dialog,
popover, sheet, inline editor), the resulting states (saved, empty, loading,
error, denied), and role or permission variants. Say which surfaces you
inferred rather than observed.

## K · Redact secrets

A diff can carry API keys, tokens, webhook URLs, signing secrets, private
email addresses, or `.env` values. Replace each with `<REDACTED>` in excerpts,
diagrams, captions, and prose, keep the variable name so the shape survives,
and mark the excerpt as redacted. Obvious placeholders from test fixtures may
stay.
