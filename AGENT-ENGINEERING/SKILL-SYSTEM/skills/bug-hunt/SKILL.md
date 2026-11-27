---
name: bug-hunt
description: "Hunt bugs nobody has reported yet in real code with property-based testing: a property contract quoted from the docs, independent oracles, generators checked before use, a seeded-mutant gate before any clean result, coverage-steered generator evolution, and four-way triage. Native engines by default, Ephyra opt-in. Use only when the user explicitly invokes $bug-hunt. Do not use automatically, to diagnose a known failure, for routine unit tests, user-path verification recipes, or TLA+ model checking."
disable-model-invocation: true
---

# Bug hunt

A finding is a valid input, a quoted expectation it breaks, a standalone
reproducer, and a regression test that fails on unmodified code.

## Stop rules and isolation

1. Never weaken an oracle or silently filter failing inputs to get a green
   run. Every mask is narrow, counted, and turned off by `NO_MASK=1`.
2. Do not edit product code or existing tests. Fix only when asked, and then:
   no minimal reproducer, no fix.
3. Do not change manifests or lockfiles (`pyproject.toml`, `package.json`,
   `Cargo.toml`, `go.mod`) without asking; keep harness dependencies in a
   scratch venv, package, or crate.
4. Isolate side effects: throwaway `HOME` and working directory, network off
   (loopback mocks only), an overall time, disk, and case budget set before
   the first run (never an unbounded `cargo fuzz run` or `go test -fuzz`),
   teardown of every worker and mock server, and removal of `.hypothesis/`,
   `proptest-regressions/`, `testdata/fuzz/`, `fuzz/`, and `.ephyra/` from
   the target unless the user asks to keep a suite.
5. Never file issues, pull requests, or comments upstream without explicit
   authorization; report security findings privately to the user.
6. Amplify bugs: Rust `debug-assertions` and `overflow-checks` on, also in
   release; Python `-X dev`; cheap sanitizers; a per-case subprocess watchdog
   for code that can hang, abort, or segfault.

## Pick the right skill

| Skill | Starts from | Runs | Leaves |
|---|---|---|---|
| `create-verification-skill` | Known user path, no reliable driver | Hand-chosen journeys on the real app | Target-local verify recipe and driver |
| `create-formal-verification-skill` | High-stakes concurrency, crash, or protocol promise | Bounded exhaustive TLA+ model checking | Model, manifest, project-local verify skill |
| `debugging` | Known symptom, error, flake, or regression | Repro loop, hypotheses, instrumentation | Minimal fix, regression test, post-mortem |
| `evidence-driven-loop-*` | Metric or quality target | Edit-measure-decide cycles | Improved artifact, evidence log |
| `bug-hunt` | No known bug | Valid-by-construction generators, independent oracles, coverage-steered evolution | Triaged bug ledger, standalone reproducers, native regression tests |

Hand a confirmed bug to `debugging` when the user wants root cause and a fix.

## Phase 1: Scope surfaces and write the Property Contract Table

Read the docs, types, tests, fixtures, and cited standards. Pick 3-5
surfaces where a bug would hurt: parsers and printers, serializers,
evaluators, stateful engines, cross-boundary adapters (stream vs batch, sync
vs async).

Before any generator, write `Surface | Property and oracle rung | Quotable
source`: a doc sentence, type, existing test, cited standard, or universal
rule (no crash, hang, or data loss on valid input). Show it to the user, or
write it to the run notes when unattended. A row with no source is a spec
question, not a property.

## Phase 2: Choose the engine and design independent oracles

Default to the target's native engine; Ephyra is opt-in for Rust targets or
cross-language multi-oracle hunts. Set up with
[framework-selection.md](references/framework-selection.md); read
[ephyra-playbook.md](references/ephyra-playbook.md) only if Ephyra is chosen.

Oracle ladder, by yield per effort; a new oracle beats running an old one
longer:

1. Crash, hang, assertion, or sanitizer report on valid input.
2. Round trip: `parse(print(x)) == x`, write then reopen, `a; b` separation.
3. Differential: a simple reference model, another implementation, or an
   internal dual path (stream vs non-stream, `str` vs parsed type).
4. Invariants: idempotence, conservation, bounds, cache laws.
5. Metamorphic: with and without an index, cache, middleware, comments,
   line-ending change, or chunk fragmentation.
6. Stateful sequences: 2-5 interleaved handles, checked after every step
   and after close and reopen.

Never compute the expected value with the target's own algorithm. A new
oracle failing on more than about 1% of inputs is suspect first: reread the
docs. Give each check its own assertion line or signature so shrinking never
drifts between bugs. Blueprints, masks, and templates:
[oracle-and-triage-patterns.md](references/oracle-and-triage-patterns.md).

## Phase 3: Build generators and pass the self-checks

Build inputs valid by construction from the grammar, types, or schema, not by
filtering. Draw names, keys, and values from small colliding pools (3-6
entries) so collisions happen constantly; mix in the project's fixtures.

Gates before any long run:

- **Generator self-check.** Ephyra: `ephyra check` passes and no `.map()` or
  `.and_then()` drops a shrinker. Hypothesis, fast-check, proptest: a
  meta-test shows every value is in the documented domain, discards stay
  under 20%, every diversity bucket is hit, and a synthetic failing predicate
  shrinks to a minimal value.
- **Seeded-mutant calibration gate.** Inject at least one small realistic
  bug into a scratch copy or by monkeypatching, or replay a known historical
  bug, and confirm the harness catches and shrinks it. Confirm the target is
  unchanged afterwards. No clean run is reportable without this kill.

## Phase 4: Hunt: run, measure, evolve, pivot

1. Fixed-seed smoke run of seconds: throughput, signatures, shrinking.
2. Sustained run inside the budget: several seeds, coverage on.
3. When nothing fails, read uncovered branches and diversity counts and
   evolve one generator gap at a time, comparing coverage before and after.
   Rerun the generator self-check after every evolution: coverage rewards
   invalid inputs that reach error paths. Audit skip, discard, and mask
   counts.
4. Two consecutive rounds with no new failure and flat coverage: pivot to the
   next surface. Stop when the hunt budget is spent.

## Phase 5: Replay, triage, hand off

Replay every failure three times with its seed; one that does not reproduce
is a flake to record, not a bug. Distill each into a standalone reproducer
with no PBT dependency, then put it in exactly one bucket:

1. **Real product bug.** Valid input; the result contradicts a quotable
   sentence or universal rule. Dedupe, then write a native-suite regression
   test that fails on unmodified code.
2. **Spec / contract ambiguity.** Docs are silent or contradictory. Report
   the minimal case and the conflicting citations; invent no rule.
3. **Generator invalid-input bug.** The input breaks a documented
   precondition. Tighten the generator, rerun its self-check, and never
   weaken the oracle.
4. **Oracle / environment bug.** The oracle misread the spec, missed a
   legitimate equivalence, or hit a tool, locale, or version artifact;
   documented behaviour that looks wrong lands here. Fix the oracle, then
   re-verify the seeded-mutant kill.

## Report

Give the contract table with cases and coverage per property, calibration
kills, the bug ledger (version, minimal input, command, expected and actual,
quoted source, regression test), spec questions, flakes, mask counts, cleanup
done, and the next surface.
