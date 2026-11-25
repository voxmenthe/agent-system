# Debug: Log → Localize → Fix

A structured loop to avoid thrash.

## Loop (max 2 iterations)
1) **Localize**: add one log/assert at the narrowest suspected choke point; run once; capture exact values and path taken.
2) **Update model**: write a 2–3 sentence causal hypothesis consistent with the log.
3) **Targeted micro-fix**: the smallest safe change that makes the hypothesis false.
4) **Prove**: run failing case, a near neighbor, and a sanity check; attach output.

## Deliverables
- Before/after logs that explain the causal chain.
- A minimal diff and tests that lock the fix.
- If inconclusive after 2 loops, stop and produce a fresh hypothesis set.

## Additional Context (Optional)
$ARGUMENTS