---
name: architecture-plan
description: Resolve an authorized change's consequential module, API, data-ownership, or integration-boundary decision. Use when that decision remains unsettled; skip local fixes, conventional modules with established patterns, and already-settled designs.
---

# Architecture planning workflow

Resolve the smallest consequential boundary decision that the authorized change
still needs. A new module, an architecture keyword, or a large task does not by
itself require this workflow. Reuse settled designs and existing patterns.

Follow the architecture, implementation, and testing packs under
`${CODEX_HOME:-$HOME/.codex}/policy/packs`, plus other applicable packs. Reuse
already-loaded current policy and source evidence; read missing material rather
than repeat mapping or routing. This skill adds no implementation, delegation,
publication, or external-effect authority.

## Establish the decision

- Name the unresolved module, API, data-ownership, or integration choice and
  its consequence for correctness or future change cost. If no such choice
  remains, return to the task without producing an architecture plan.
- Reuse the change contract and brownfield map. Inspect missing targets,
  callers, tests, invariants, side effects, failure ownership, and relevant
  history before choosing a shape. Label facts, inferences, contradictions,
  and behavior that still needs runtime validation.
- State the design concept and the load-bearing concerns. Resolve decisions
  that constrain other decisions first; a design tree is useful only when
  those dependencies need explanation.

## Design outside in

1. **Start with the minimum mechanism.** Prefer deep modules: substantial
   behavior behind a small, stable interface. Callers need the purpose,
   contract, errors, costs, and side effects, not internal sequencing. Depth
   is the simplicity of that interface relative to what it hides, not size.
2. **Show normal use before internals.** Define the public types/functions,
   inputs, outputs, owned data, invariants, errors, and effects needed by the
   actual consumer. Make expensive work explicit; keep core logic separable
   from I/O. Avoid pass-through layers and option bags that expose internals.
3. **Challenge the hardest boundary.** Show how the design handles its real
   failure and integration cases without special-case coordination or private
   reach-through. Compare a materially different alternative when the choice
   is consequential or hard to reverse, not just to fill an options table.
4. **Check change cost and divergence.** Identify what fails if this boundary
   breaks and what must change when it evolves. Apply the deletion test and
   inspect synchronized edits. For partial-context edits, if a contributor
   copies the nearest example, what elsewhere can silently diverge, and what
   catches it? Probe split writers, competing routes, bypassable internals,
   and hand-synced inventories or identities. Prefer one owner/derivation or
   a real parity check; preserve justified adapters, versioned routes, and
   independently owned policy.
5. **Define proof at the public boundary.** Plan or write the focused assertion
   permitted by the task, covering normal behavior and the load-bearing
   failure/invariant. Tests should observe behavior without freezing private
   implementation. Keep new integration seams provisional until real data
   has flowed across them; choose the first thin end-to-end check accordingly.

Short usage examples, few imports, low glue ratios, and localized deletion are
diagnostic aids, not numerical pass/fail gates. Investigate what a long example
or scattered edit exposes; redesign only when the boundary causes a concrete
problem in this change. The policy's evidence gate still applies to new
behavior-generalizing abstractions: three concrete cases simplified, specific
code removed, and reduced coupling. Type constraints may narrow invalid states
earlier.

## Proportional handoff

Record the decision in the existing plan, task brief, or conversation. Create a
separate durable plan only when requested or needed for future consumers. Use
only the fields that change the next action:

- decision and source-backed reason, including the relevant alternative;
- public contract, normal usage, responsibilities hidden behind it, and
  explicit non-goals;
- break/change blast radius, failure ownership, costs, and observability at
  load-bearing seams;
- boundary validation and the first real integration check;
- compatibility, migration, and recovery only where the change needs them;
- remaining consequential uncertainty and the next authorized action.

Link an adequate existing map or decision instead of restating it. Do not make
every field a mandatory section or restart a settled design exercise.

## Finish or reassess

Finish when the needed boundary is clear, its hardest cases have a credible
mechanism, and proportional evidence can test the contract. Return to the
owning workflow and continue authorized work without a routine approval gate.

Reassess when evidence invalidates the decision, callers must depend on private
state or sequencing, a failure case lacks an owner, or the proposed abstraction
fails its evidence gate. Expand design scope only for friction causal to the
current requirement. Ask only for a genuinely unresolved material decision or
authority the current task does not provide; continue independent authorized
work meanwhile.
