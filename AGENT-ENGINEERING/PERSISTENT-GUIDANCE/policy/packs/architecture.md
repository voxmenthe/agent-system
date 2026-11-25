# Architecture and design

## Applies when

Load this pack before planning work that crosses modules or subsystems; introduces or changes a public API, domain model, module, service boundary, storage model, or abstraction; performs a broad refactor; or changes load-bearing performance or observability behavior.

## Does not apply when

Do not load it for a purely mechanical rename, formatting-only change, isolated documentation correction, or an obvious local fix whose interface and dependencies do not change. Load it when inspection reveals hidden coupling even if the original request looked local.

## Non-negotiable rules

- **Architectural friction is a reassessment signal, not automatic permission to broaden scope.** Special cases, data passed unchanged through three or more calls, reaching into another module’s internals, “just in case” defenses, copy-paste with variations, or hard parts that feel forced require investigation. Redesign only when the friction is causal to the current requirement or exposes a boundary the change depends on.
- **Track abstraction cost.** New interfaces, cross-boundary transforms, configuration surfaces, and inheritance add cost. Unified paths, removed special cases, removed duplication, and simpler call sites reduce it. Net new complexity needs an explicit reason.
- **Evidence-gate behavior abstractions.** Generalize behavior only when at least three concrete cases are simplified, specific code is removed, and coupling decreases. Type-level constraints that narrow behavior are allowed earlier when they make invalid states unrepresentable.
- Keep the core pure and place I/O, databases, networks, filesystems, UI, and external services at explicit edges behind stable interfaces.
- Prefer a narrow waist: a small stable domain model and ports in the center, with policy and infrastructure variation in adapters.
- Prefer deep modules: small public surfaces with substantial implementation hidden behind them, each runnable and verifiable through its own surface.
- Apply the deletion test. A well-isolated module or behavior abstraction can be removed in one sentence and usually within one or two files. More than five scattered changes indicates leakage.
- Commands modify state and may return the result of that operation, such as a created identifier. Queries return data without side effects. Make expensive or side-effecting operations obvious in names.
- Prefer monotonic, associative, commutative, and idempotent operations where practical. Isolate non-monotonic work behind explicit coordination boundaries.
- Observability is part of the design at system boundaries, not an afterthought.

## Procedure

1. **Describe the minimum mechanism first.** Ask what the code would look like if the problem nearly solved itself, then work backward; everything beyond that shape needs justification.
2. **Map the system before choosing a shape.** Identify the target, callers, dependents, data ownership, side effects, critical paths, failure modes, and likely future modifications.
3. **Name the hardest two or three parts first.** Sketch how each design handles them. A design that needs special cases or boundary leaks at the hardest points is not ready.
4. **State the break and change blast radii.** Separate reversible edge failures from irreversible or load-bearing failures affecting data integrity, transactions, SLOs, or critical flows.
5. **Design data before control flow.** Look for tables, maps, registries, schemas, discriminated unions, state machines, or event streams that remove branching and special cases.
6. **Write the public types or signatures first** for a new module or feature. A consumer should normally import no more than three things, avoid boolean flag arguments, and fit a normal usage example in about five lines, preferably the call or command that checks it on its own. Keep an interface between two components provisional until real data has flowed across it; finalizing a seam before that hides the contract errors the first real call would expose.
7. **Check subsystem glue.** Estimate mapping/transform lines divided by business-logic lines. A ratio above roughly 2:1 is a signal to investigate, not a redesign threshold. Redesign only when evidence shows that the boundary causes complexity in the current change.
8. **Compare alternatives proportionally.** For consequential or difficult-to-reverse design decisions, compare a materially different alternative and test the favored design against scale, partial failure, and evolving requirements. Do not manufacture alternatives when the minimum mechanism is already clear.
9. **Use progressive commitment for new systems.** Build a walking skeleton first: the thinnest concrete path through every layer the feature touches, with each layer present and wired to the next. Stubbed or hardcoded internals are fine; a missing or unwired layer is not. Run it for real against real dependencies, cover the path with an end-to-end test, and only then deepen one component at a time. Treat that path as the architectural probe, observe the second case, and generalize behavior only after evidence from the third.
10. **Make hidden costs visible.** State expected input sizes for load-bearing code. Expose indexing, caching, materialization, remote calls, and potentially repeated scans in the API or design.
11. **Place observability at critical seams.** Define structured error context, metrics, tracing/correlation identifiers, and capacity signals where failures cross boundaries.

Prefer dispatch maps, pattern matching, declarative configuration, versioned interfaces, pipeline stages with contracts, event-driven decoupling, idempotent handlers, and explicit transactions. Avoid lying abstractions, unnecessary middle layers, god functions, deep call stacks without value, hidden dependencies, repeated branch ladders, and mutable global state.

## Done criteria

- The hardest parts follow the design naturally rather than through exceptions.
- Public interfaces are small, honest about cost, and stable at the right boundary; each module can be exercised and observed without standing up the whole system.
- Break and change blast radii, reversibility, and failure containment are explicit.
- Any new behavior abstraction passes the evidence gate and deletion test.
- Core logic is separable from effects; ownership and transaction/coordination boundaries are clear.
- Performance assumptions and observability at load-bearing seams are explicit.
- The plan includes proportional validation and a migration path when compatibility or persistence is involved.
