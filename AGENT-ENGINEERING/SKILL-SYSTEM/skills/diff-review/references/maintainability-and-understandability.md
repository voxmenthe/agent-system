# Maintainability and understandability

Use this lens only when the change crosses a material boundary or the user asks
for a deep maintainability review. Tie every concern to a concrete reading,
debugging, testing, or likely change task.

## Questions with evidence value

- Can normal and exceptional behavior be understood near its use?
- Does one owner control each state, policy, and invariant?
- Are effects, sequencing, and error propagation visible?
- Does an interface hide substantial complexity or merely rename a call?
- Would a plausible follow-on change touch fewer concepts and owners?
- Did each new flag, file, layer, dependency, or dispatch hop remove a larger
  burden?
- Are absence, failure, retry, and partial completion represented honestly?
- Can important behavior be tested through a stable seam?

Reader load is not file length, function size, branch count, or abstraction
count. Name the execution or navigation path, state reconstruction, semantic
nesting, duplicated policy, or change ripple that creates the cost.

## Deep-module test

A module can be valuable with one implementation when it owns a stable
invariant, volatile platform boundary, compatibility seam, coherent state
machine, or small caller-facing interface over substantial behavior. Do not
recommend extraction unless it creates coherent ownership, a stable test seam,
reusable policy, or simpler callers.

Moving the same branches into helpers, handlers, registries, factories, or
lookup tables is not simplification when state knowledge and navigation burden
remain.

## Counterexamples

- A parser or protocol decoder may be branch-heavy because the domain is.
- A lock, transaction, retry, or migration seam may be verbose because it
  protects a demonstrated irreversible failure mode.
- An adapter can be thin yet necessary when it is the verified compatibility
  or host boundary.
- A long cohesive function can be clearer than fragmented helpers that share
  hidden state.

When structure is justified, say what invariant it protects and recommend no
change.
