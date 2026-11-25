# Overengineering and subtraction

Evaluate retained complexity across concepts, states, files, layers, call
hops, configuration, registries, dependencies, operational surfaces,
duplicated policy, compatibility, recovery, and observability.

Before reporting overengineering, establish all five:

1. a current observable cost;
2. evidence the machinery is not required by a consumer, contract, framework,
   safety boundary, or credible irreversible failure mode;
3. a smaller available replacement;
4. the behavior and safeguards that replacement preserves; and
5. a falsifying verification method.

Prefer, in order: keep when no problem exists; delete dead or speculative
behavior; reuse the repository owner; use platform or standard library; use an
existing dependency that truly owns the problem; write the smallest local
behavior; generalize only when several concrete cases become simpler with less
coupling.

Do not use line count, branch count, dependency count, or number of files as a
quality objective. They may locate a question but cannot establish a finding.

## Common false positives

- Similar syntax is not harmful duplication unless policy or changes must stay
  synchronized.
- One implementation does not invalidate a deep module.
- Validation is not redundant until the owning boundary proves the invariant.
- Compatibility is not speculative when formats, external consumers, mixed
  versions, public APIs, or rollback depend on it.
- Performance machinery needs a measured or structurally unbounded relevant
  cost, but a bounded scan may already be the simplest correct solution.
- Tests may be verbose because they make ownership of behavior visible.

If a proposed cut crosses correctness, safety, data, concurrency,
compatibility, recovery, accessibility, or observability, surface that boundary
and route the appropriate specialist review before adoption.
