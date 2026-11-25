# Four lenses, one reading journey

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
