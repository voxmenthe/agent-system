---
name: map-change
description: Map uncertain contracts, callers, and coupling for an authorized existing-code change. Do not use for obvious local edits, already-mapped changes, greenfield work, general explanations, or implementation.
---

# Map the existing change surface

Build a read-only, evidence-backed map that lets the next decision use the smallest coherent scope. Resistance is evidence to investigate, not automatic permission to redesign.

Reuse a current map and source inspection; investigate only the remaining
change-impact uncertainty. General "how does this work?" questions belong to
`codebase-search-and-understanding-expert`. Do not run both workflows over the
same evidence just because both could describe the code.

## Boundaries

- Do not modify files, install dependencies, mutate Git, or perform external writes.
- Skip this skill for a trivial or tiny edit whose target, contract, and verifier are already obvious.
- Do not recommend an implementation before the map supports it.
- Do not broaden into an architectural redesign unless discovered friction is causal to the current requirement.

## Workflow

1. Read the active instructions and the complete target artifacts.
2. Identify the entry point and trace the primary call or data path.
3. Identify callers, dependents, public contracts, owned state, side effects, and failure ownership.
4. Read focused tests, documentation, configuration, and relevant history.
5. State the invariants the current system appears to preserve.
6. Look for hidden coupling: duplicated policy, boundary reach-through, pass-through layers, repeated defensive checks, implicit sequencing, or locally unchanged data threaded through multiple calls.
7. Separate observed facts from inferences and behavior that still needs runtime validation.
8. Identify contradictions, missing information, and the question that would collapse the most remaining uncertainty.
9. Stop when evidence demonstrates that the change is local. Otherwise name the smallest coherent change surface and the reason each part belongs.

## Output

Return the smallest useful inline map, omitting settled or irrelevant fields:

- Entry point and primary path
- Targets, callers, and dependents
- Contracts, invariants, side effects, and ownership
- Existing tests, docs, and relevant history
- Hidden coupling or architectural friction
- Facts, inferences, and unverified runtime behavior
- Smallest coherent change surface
- Remaining uncertainty and stop/escalation condition

Support every material claim with repository paths and symbols when available.
Do not create a separate document or repeat an existing map merely to satisfy
this output shape.

## Stop conditions

- The requested outcome or contract is materially ambiguous.
- Required evidence is unavailable without new authority.
- Mapping reveals persistence, concurrency, security, or public-interface risk that requires a dedicated policy or architecture decision.
- The change is demonstrated to be local; hand off rather than manufacture more ceremony.
