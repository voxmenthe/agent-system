---
name: frame-change
description: Frame a sufficiently understood, nontrivial change as a compact contract for outcome, acceptance evidence, non-goals, invariants, risk, authority, stop conditions, and recovery. Use before design or implementation to prevent costly misunderstanding; do not use for tiny obvious edits, ambiguous upstream intent, or implementation design.
---

# Frame a bounded change

Create the smallest decision record that makes later design, implementation, and verification predictable. This skill owns the **change contract**, not product-intent discovery or implementation shape.

## Preconditions and boundaries

- The desired outcome is sufficiently understood. Reuse a confirmed intent brief when one exists.
- If materially different outcomes remain plausible, do not replace `intent`; stop for upstream intent clarification.
- Skip this skill for a trivial, obvious, reversible edit with a direct verifier.
- Do not map the repository deeply, choose architecture, edit files, commit, publish, deploy, or perform external writes.

## Workflow

1. **State the outcome.** Describe what should become possible for a user or system without embedding a guessed implementation.
2. **Name success evidence.** Identify observable facts that would establish the outcome. Prefer inspectable artifacts over a builder's claim. For a filter, threshold, or default change, say which representative inputs change, disappear, or fall back, with the denominator: "14 of 220 tickers fall below the new volume floor", not "a few drop out".
3. **Sharpen the method (optional).** When the outcome depends on domain craft, ask what a top practitioner would add: the rawest source to work from, the specific methods they would use, and the outside evidence that would show the result is right. Fold what changes the contract into acceptance evidence and boundaries; the implementation stays with design.
4. **Set boundaries.** Record non-goals, affected contracts, and what must not change. From the accepted outcome, domain terms, and public contract, not an implementation, name the purpose-level invariants and the boundary examples that pin them.
5. **Classify risk.** Choose the lightest adequate mode:
   - **Fast:** local, reversible, obvious verifier, no meaningful contract or authority change.
   - **Guided:** multiple modules, a meaningful design choice, user-facing behavior, unfamiliar code, or moderate operational risk.
   - **Supervised:** persistence, permissions, sensitive data, public contracts, destructive actions, external side effects, or poor observability.
6. **Bound authority.** State allowed read, write, execution, network, Git, and external-effect scope. An effect ceiling is not an authorization grant.
7. **Name uncertainty.** Identify the unresolved question with the greatest effect on the required outcome or change surface.
8. **Define stop conditions.** Stop if the contract, risk class, authority, or expected change surface materially expands.
9. **Define recovery.** State how the candidate can be reverted, disabled, or restored.

## Output

Produce a compact **Change Brief** with only relevant fields:

- Outcome
- Acceptance evidence
- Non-goals
- Risk mode and reason
- Purpose-level invariants and boundary examples; affected contracts
- Highest-value uncertainty
- Authority boundary
- Stop conditions
- Recovery posture

Do not pad the brief with empty sections. Clearly label facts, user decisions, and material inferences.

## Stop conditions

- The user outcome is unsettled or contested.
- A public contract or authority decision needs an authorized owner.
- Repository evidence contradicts a material premise.
- Recovery cannot be stated credibly.
