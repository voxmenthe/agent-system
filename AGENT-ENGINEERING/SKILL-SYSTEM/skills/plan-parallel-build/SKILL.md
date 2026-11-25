---
name: plan-parallel-build
description: Write a parallel-build plan for a sufficiently specified greenfield or early-stage project when the user wants a plan for coding agents. Do not use for feasibility, unmapped brownfield work, implementation, or ticket publication.
---

# Plan a parallel build

Create the implementation map that coding agents can execute with little human
coordination. Optimize equally for an early usable integrated result and for
boundaries that let each area evolve without recurring cross-stream edits.

This is a planning-only skill. Its deliverable is one Markdown plan. Do not run
the workstreams, spawn implementation agents, create branches or worktrees,
publish tickets, or modify production code.

A large autonomous task alone does not request a parallel-build plan.

## Route the request

Use this skill when all of the following are true:

- the intended product behavior and meaningful constraints are sufficiently
  settled;
- the remaining work is direct implementation rather than feasibility testing;
- at least two coherent implementation outcomes could proceed independently,
  or one apparently large outcome should be tested for safe decomposition; and
- the user wants a plan that can be handed mostly to coding agents.

Do not force a build plan when a load-bearing uncertainty is still “can this
work?” Route that uncertainty to a feasibility-spike workflow first. Likewise,
resolve unsettled product intent before planning, map an unknown brownfield
change surface before decomposing it, implement a single already-settled slice
directly, and use a tracker workflow when the requested output is published
tickets.

If only a small amount is missing, state the assumption and proceed when it is
safe and reversible. Stop for user input only when the answer would materially
change the integrated outcome, a public contract, safety, or the workstream
boundaries.

## Planning standard

Treat a workstream as a coherent implementation outcome, not a list of files or
a time estimate. It is well bounded when one competent coding agent can:

- understand it from the brief and named evidence without reconstructing the
  rest of the project;
- implement and test it end to end without waiting for another same-wave
  stream's unmerged behavior;
- own a non-overlapping change surface and one clear responsibility; and
- return a reviewable change whose integration handoff is explicit.

Do not assign point scores, hour or day estimates, or a universal size threshold
unless the user asks. Use the boundary and split rules below as the sizing rule.

### Prefer durable boundaries

Choose the decomposition that reaches an integrated usable path quickly while
remaining aligned with likely future change. When those goals conflict, keep
the more durable boundary if the faster partition would predictably require
recurring coordination across streams; then find the earliest usable slice
inside that boundary.

Each boundary should pass these checks:

- **Ownership:** one stream has final authority over each module, contract, and
  shared file.
- **Future-change:** a likely follow-on change has one natural owning stream
  rather than edits scattered across several interiors.
- **Contract:** consumers need only the declared interface, data shape, errors,
  and side effects—not the producer's implementation details.
- **Integration:** the stream has standalone acceptance evidence plus a named
  way to prove it composes with its consumers.

### Split a stream when the split is real

Split a long, complex, or critical-path stream further when at least one of
these conditions exposes a stable seam:

- it contains multiple independently valuable acceptance outcomes;
- distinct modules or domains can meet through a small contract or fixture;
- an intermediate result can be tested and consumed without knowing the later
  implementation;
- separate concerns have different owners, dependencies, or failure modes; or
- it is expected to dominate completion time and a split would let additional
  agents make useful progress concurrently.

After splitting, apply the same tests recursively. Prefer more active lanes
until another split would create shared ownership, speculative interfaces,
coordination work larger than the implementation, or fragments that cannot be
tested and integrated independently.

Keep work together when the proposed pieces would edit the same core files or
mutable state, need unresolved decisions from each other, or amount only to
tiny setup and glue tasks. If a dominant stream has no safe seam, keep it whole
and explain the constraint in the plan instead of manufacturing parallelism.

## Build the plan

### 1. Establish the source of truth

Read the confirmed brief, existing plans, repository instructions, relevant
architecture decisions, and—when code exists—the smallest relevant code and
test surface. Separate confirmed facts, planning decisions, assumptions, and
unresolved blockers. Do not silently turn an assumption into a contract.

Use the user's requested plan path. Otherwise follow the repository's planning
convention; if none exists, write
`PLANS/<YYYY-MM-DD>-<project-slug>-parallel-build.md`.

### 2. Define the integrated delivery target

State one observable outcome that makes the project usable, the shortest normal
usage or demo path, fixed constraints, explicit non-goals, and hardening that
may be deferred. Plan toward this integrated target rather than maximizing the
number of streams.

Prefer an early thin end-to-end path. Do not make every stream wait for a large
foundation when settled contracts and fixtures can support parallel work.

### 3. Draw ownership and contract boundaries

Identify cohesive capabilities, their owned code or artifact surfaces, and all
producer-consumer seams. For every cross-stream seam, settle:

- the owning producer and named consumers;
- interface or artifact shape, version, and compatibility expectation;
- normal behavior, material errors, and side effects;
- test doubles, fixtures, or examples consumers may build against; and
- the integration evidence that will prove both sides agree.

No same-wave dependency may remain “TBD.” If a contract cannot be settled in
the plan, give one earlier stream ownership of defining and proving it, or
sequence the dependent stream later.

### 4. Create and refine the workstreams

Start with outcome-shaped capabilities, apply the workstream standard, then
recursively apply the split rules to any stream expected to be long or to hold
the critical path. Every stream must name owned surfaces. Same-wave streams
must not make overlapping edits; when overlap is unavoidable, assign one owner
and sequence consumers after it.

An integration stream is justified only when it owns real glue code or an
end-to-end harness. Never use a catch-all integration stream to repair vague
contracts between the other streams.

### 5. Schedule safe waves

Place streams in the same wave only when:

- their contracts are already settled;
- neither needs the other's unmerged implementation;
- their write surfaces and shared mutable resources do not conflict; and
- each can validate locally against agreed fixtures or interfaces.

Use the smallest necessary earlier contract or foundation wave. At every wave
boundary, land producer contracts first where ordering matters, run the named
integration checks, and expose the next parallel frontier. Show the dependency
edges and identify the qualitative critical path; do not imply that all listed
streams can start immediately.

### 6. Specify proportionate evidence

Each stream needs focused acceptance evidence for its primary behavior, its
most material boundary or failure case, and its integration handoff. The whole
plan needs one end-to-end smoke path proving that the integrated result should
work together as expected.

Do not require extensive hardening unless it is necessary for the stated
delivery target. Name deferred performance work, exhaustive compatibility,
operational polish, security review, or edge-case expansion so it is visible
rather than accidentally implied complete.

## Write one coherent plan document

Use this order:

1. **Title and takeaway** — the integrated outcome and the decomposition logic
   in no more than three short bullets.
2. **Scope and source-of-truth ledger** — confirmed inputs, decisions,
   assumptions, blockers, non-goals, and deferred hardening.
3. **Parallel build map** — a compact renderer-independent text tree showing
   waves, workstream IDs, dependency edges, and integration checkpoints.
4. **Workstream index** — one table with ID, outcome, owned surface,
   dependencies, wave, and integration evidence.
5. **Contract matrix** — producer, consumer, interface or artifact, owner, and
   how agreement is checked.
6. **Workstream briefs** — one self-contained brief per stream using the
   template below.
7. **Integration and delivery plan** — landing order, wave gates, smoke path,
   critical path, and the next parallel frontier.
8. **Final readiness check** — unresolved items, intentionally deferred work,
   and the evidence required before dispatch.

The parallel build map is the primary visual. A Mermaid diagram is optional
and may contain no unique dependency, ownership, or contract fact. Keep labels
precise, keep the hierarchy shallow, and do not repeat the same relationships
in prose. The document should be easy for a human to steer and complete enough
to dispatch each brief to a coding agent without oral context.

Use this brief shape:

```markdown
### WS-<NN> — <outcome-led title>

- **Outcome:** Observable result this stream owns.
- **Why this boundary:** Why it can evolve and land independently.
- **Owned surface:** Exact modules, directories, schemas, or new artifacts.
- **Inputs:** Settled context, fixtures, and upstream contracts.
- **Outputs / contracts:** Interfaces and artifacts promised to consumers.
- **Implementation:** Bounded steps, ordered only where necessary.
- **Acceptance evidence:** Focused tests, demo, and material negative case.
- **Integration handoff:** Consumer, landing order, and composition check.
- **Excluded / deferred:** Work intentionally outside this stream.
- **Stop conditions:** Discoveries that require redesign or resequencing.
```

## Audit before handoff

Do not mark the plan ready until all answers are yes:

- Does every required behavior have exactly one owning stream?
- Can every same-wave stream proceed without an unresolved cross-stream
  decision, overlapping write, or another stream's unmerged code?
- Was each long or dominant stream tested for a real further split?
- Does every cross-stream dependency have a settled contract and owner?
- Does each brief contain enough evidence and context for a coding agent?
- Do wave gates prove integration rather than merely count completed streams?
- Is there an early usable path and one final integrated smoke path?
- Are extensive hardening and other non-goals explicitly deferred?
- Is the Markdown plan the only artifact changed by this skill?

If any answer is no, revise the decomposition or mark the exact blocker. Do not
paper over integration risk with optimistic prose.
