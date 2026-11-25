# Connect behavior to executable witnesses

Use this when the target has commands or tests but it is unclear which user
claims they establish. Extend the existing recipe or evidence record; do not
create a second feature catalogue or a whole-product audit by default.

## Start at the user entry

For changed and materially preserved behavior, connect four facts:

| Claim | Public action | Decisive observation | Extra witness when needed |
| --- | --- | --- | --- |
| A reservation succeeds | Select an item/customer and submit in the UI | Confirmation with the created order ID | Retrieve that same order and compare its items; inspect stock/WAL if those effects are claimed |
| A background export completes | Start the export through its supported entry | Terminal success, not just job admission | Open the resulting file and check its content |
| Invalid input has no effect | Submit the relevant invalid request | The expected rejection | Unchanged affected state, if absence of a write matters |

These rows illustrate the relationship, not required scenarios or a schema.
The target supplies its real actions, values, and evidence paths. Health proves
readiness, not feature behavior. A screenshot proves what was captured, not a
backend effect or recovery property.

Compare the result with the intended input and accepted contract, not only
with another output from the same implementation. A UI, API, stock count and
WAL can agree on the wrong quantity. Agreement between witnesses is useful,
but cannot replace an independent expectation of what the user requested.

## Keep coverage scoped and honest

Read both the affected baseline and the accepted change. Preserve meaningful
adjacent coverage instead of replacing the recipe with only the newest path.
Existing tests may cover a criterion; reuse attributable evidence after checking
the build, inputs, conditions, and assertion. Do not rerun merely to fill a table.

Follow asynchronous work to the required terminal state, with a deadline and
an explicit incomplete result. If the public entry is missing, distinguish
unbuilt behavior, an unavailable prerequisite, and an actual reachability
defect. Do not infer dead code from one failed search or silently skip a
required acceptance criterion.

Keep passed, failed, unexercised, and blocked claims distinct. A path listed in
a map is not executed coverage, and several passing rows cannot hide an
untested material claim. Coverage arithmetic is useful for an expressly broad
audit, not a reason to invent a large matrix for a small change.

## Maintain the connection

When a feature changes, update only affected actions, fixtures, selectors,
expected observations, and their witnesses, then re-drive them. Separate a
product regression from a stale driver or mistaken oracle. Change an expected
result only when the accepted contract changed, never to accommodate a defect.

Source ideas: AutoQA's witnessed behavior map, Compound Engineering's user
journeys, and Agent-Native's per-area proof paths. Their full catalogues and
publication workflows are not required by this recipe.
