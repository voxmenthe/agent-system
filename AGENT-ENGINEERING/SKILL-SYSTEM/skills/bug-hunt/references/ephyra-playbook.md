# Ephyra playbook (opt-in)

Ephyra is a Rust property-based testing library from Datadog's systems
research group, built for agents: the author writes the generator, support
predicate, shrinker, and mutator, and the library verifies them. This page
was checked against the upstream repository at revision `3983b2e` (crate
version `0.0.1`, API not frozen). Recheck names with `ephyra guide` and the
crate's `API.md` when the installed version differs.

## When it is worth installing

- A Rust library or CLI where explicit shrinkers, `ephyra check`,
  multi-failure runs, and in-process coverage steering pay for a new
  dev-dependency.
- A deep hunt on a non-Rust system (database, compiler, Python SDK) with many
  stacked oracles, driven by a Rust test crate over an API, CLI, connection,
  or a JSON-lines worker.

Otherwise use the ecosystem's native engine. The CLI is usually not
installed: `cargo install ephyra-cli` writes to the user's Cargo home, so ask
first. Put the dependency in a separate scratch test crate:

```toml
[dev-dependencies]
ephyra = "0.0.1"

[profile.release]
debug-assertions = true
overflow-checks = true
```

## Properties

```rust
use ephyra::prelude::*;

#[ephyra::test(gen = documents(), tests = 5000)]
fn print_then_parse_round_trips(doc: Doc) {
    assert_eq!(parse(&print(&doc)), Ok(doc));
}
```

A property returns `()`, `bool`, `Result`, or `TestResult`; prefer `()` with
`assert!` and `assert_eq!`. `ephyra::assume!(cond)` discards an input that
does not apply; too many discards end the run as `GaveUp`. Not caught in
process: stack overflow, `abort`, segfaults, infinite loops, out-of-memory.
`Config::timeout_ms` limits the whole run, not one case, and there is no
per-test timeout or process isolation: run such targets in a child process
with your own watchdog.

## Generators and the hook-loss trap

`Source` primitives: `int(range)`, `index(len)`, `bool()`, `bool_with(p)`,
`pick(&[...])`, `weighted(&[...])`, `f64()`, `f64_bits()`, `size()`,
`draw(&gen)`, `discard("reason")`. Use no other randomness in a generator.
Constructors in `gens` include `int`, `edges`, `string_len`, `vec(elem)` then
`.len(range)`, `option`, `one_of`, `frequency`, `recursive`, `dependent`,
`constant`, and `pick_from`.

| Combinator | Keeps shrink and mutate? | Use for |
|---|---|---|
| `.map(f)`, `.and_then(f)` | No | Cheap reshaping, then `.with_shrink` on the final type |
| `.iso(forward, back)` | Yes, through a real bijection | Newtypes and wrappers |
| `.dependent(\|a\| gen_b)` | Yes; returns `(A, B)` | A query over a schema, an index into a length |
| `.filter("why", pred)` | Filters candidates too; discards after 100 misses | Rare exclusions only |
| `.with_shrink(f)` | Adds candidates, tried first | A shrinker on the final type |
| `.with_mutate(f)` | Replaces the mutator | A custom mutator |

The symptom of hook loss is `shrinking: 0 of 0 candidates` in a report. Attach
hooks after the last lossy step, use `.iso` for true bijections, or derive
them with `#[derive(ephyra::Arbitrary)]` (`#[ephyra(gen = ...)]` per field).
`#[ephyra::shrinker]` turns an eager `fn(&T) -> Vec<T>` into a shrinker; a
shrinker emits only strictly smaller candidates, never its input.

**Size schedule:** at iteration `i` the size is `floor(log2(i + 1))`, capped
at `max_size` (100), so with the default 10,000 tests it never exceeds 13.
Write `.len(0..=N)` or `string_len(c, 0..=N)` when long inputs matter; an
explicit length does not grow with size.

## Verify generators before hunting

Mark generators and their support predicates:

```rust
#[ephyra::generator(valid_doc, metrics = doc_metrics)]
fn documents() -> impl Gen<Value = Doc> { /* built from the grammar */ }
```

- `ephyra check --list` reads the source without building and lists work
  left (`needs a generator: <predicate>`).
- `ephyra check` (or `ephyra check NAME`, `--tests N`) runs every check: each
  value satisfies its predicate; the first 64 shrink candidates differ from
  the value and stay valid; following first candidates stays valid, never
  revisits a value, and settles within 1,000 steps; four mutants are drawn
  without a discard and stay valid; every metric is finite. Exit 0 passed,
  1 failed or did not build, 2 passed with work left.
- In code: `check_generator(&config, gen, support)`,
  `check_shrinker(&config, gen, support, size)`, and
  `check_mutator(&config, gen, support)`. Give the generator's real support,
  not the property's weaker invariant.

Health warnings to act on (`report.health`):

| Kind | Fires when | Fix |
|---|---|---|
| `discard_ratio` | More than half of 20 or more attempts discarded | Generate valid values directly |
| `low_distinct_inputs` | Under 50% distinct inputs | Widen the space or raise `max_size` |
| `slow_generation` | Generation over 100 ms and over 4x property time | Simplify the generator |
| `size_never_reached` | Gave up with the largest passing size under half of `max_size` | Discards concentrate at large sizes |
| `mutator_inert` | Over half of mutants identical (from `check_mutator`) | Write a real mutator |
| `flaky` | A failure did not reproduce on rerun | Look for state, time, or threads |
| `shrink_budget` | Shrinking stopped early | Raise `config.shrink.max_steps` |
| `cover` | A `cover(cond, label)` share below 5% | Steer the generator |
| `coverage_plateau` | Coverage stopped growing | The generator is too narrow |
| `config_env` | An `EPHYRA_*` variable has a bad value | Fix the variable |

## Many failures, signatures, replay

- `EPHYRA_FAILURES=N` (or `Config::failures(n)`, or `failures = n` on the
  attribute) keeps searching until `N` distinct failures; each is shrunk while
  keeping its signature and reported with its own replay line;
  `report.failures` lists `signature`, `count`, `failure`.
- A signature is, first match wins: `ephyra::signature("area__kind__detail")`
  inside the property; `Config::signature(...)`; else the panic location, a
  fixed `returned false`, or the `Err` message with numbers blanked.
  Shrinking treats `Err` or `false` from two different checks as the same
  failure: give each check its own `assert!` line or name.
- Replay: `EPHYRA_REPLAY=seed:iteration` from the report. Budget and seeds:
  `EPHYRA_TESTS`, `EPHYRA_SEED`, `EPHYRA_BUDGET_MS`, `EPHYRA_MAX_SIZE`;
  `EPHYRA_SHRINK=0` reports the original input; `EPHYRA_REPORT_JSON=path`
  appends JSON reports.
- Failures are remembered in `.ephyra/regressions/<name>.jsonl` under the
  working directory and replayed first next run; a failure at iteration 0 on
  a rerun may be that replay. Set `EPHYRA_REGRESSIONS=0` or delete the file
  at teardown. `ephyra test` also writes reports and coverage pages under
  `.ephyra/`.

## Coverage steering and its traps

1. Enable the `coverage` feature on the ephyra dependency and build with
   `-C instrument-coverage`, for example in the scratch crate's
   `.cargo/config.toml` under `[build] rustflags`.
2. An exported `RUSTFLAGS` overrides `[build] rustflags` and turns coverage
   off silently: check `echo "$RUSTFLAGS"`.
3. Point `LLVM_PROFILE_FILE` away from the code under test so build scripts
   leave no `.profraw` files in its source tree.
4. From a separate test crate set `EPHYRA_COVERAGE_FILTER=<crate_name>`
   (underscores) or `config.coverage.filter`; the default tracks the test
   crate itself. Check the report's `coverage:` line names the target.
5. Run with `RUST_TEST_THREADS=1`: counters are process-global.
6. Read `never reached` and `partly covered` in the report, or
   `.ephyra/coverage/<property>.html`; steer with
   `config.coverage.targets` or `.ephyra/targets.jsonl`.

## Loops

`ephyra::target(score)` inside a property drives a targeted phase.
`ephyra::loops` ships `fuzz` (inputs reaching new coverage become seeds),
`target` (seeds ranked by score), and `perf_fuzz` (toward slow inputs), each
taking `(run, pool, fuel)` where `fuel` counts draws and mutations and ignores
`Config::tests`; with coverage, `localize(run, fuel, patience)`. Install one with
`#[ephyra::test(search = |run| ...)]`. For stateful traces, `loops::causality`
rewinds a failing trace to earlier prefixes, reruns each with fresh
randomness, and reports how often the failure recurs: a jump marks the step
after which it became likely. The generator implements `Trace`.

## Cross-language driver pattern

From the upstream case studies (a Python SDK, a Git implementation, a
database API):

- A Rust driver owns one long-lived worker (for example `worker.py` in a
  locked venv, the target imported from its source tree via `PYTHONPATH`)
  and speaks JSON lines to it. The worker hosts a loopback mock server; the
  driver can fragment writes inside UTF-8 sequences and JSON tokens.
- Repeated short `ephyra::check` calls (200 tests, at most 30 s each) inside
  a run script that owns the seed, the total seconds, and restarts.
- Each oracle panics at its own line with a signature such as
  `stream__<field>__<provider>`; a dead worker is its own signature, and a
  watchdog turns a hang into `hang__timeout` or `crash__timeout`.
- Signatures already reported are skipped and counted (`known_sig_skips` in
  a stats file), and known bugs are masked narrowly with a `NO_MASK`-style
  toggle to check fixes.
- Speed and authority in two tiers: a fast batch oracle first, every
  disagreement re-decided by the authoritative tool before it counts.
- Coverage of the Python side through `coverage run -p --source=...` when
  `COVERAGE_FILE` is set.
- The harness was calibrated against hand-written mutant patches, each caught
  within two 60-second runs before clean runs were trusted.

## Things that do not exist

`gens::vec_of`, `gens::vec_of_len`, `gens::tuple_vec`, `gens::bool_`;
`i128` and `u128` generators (draw `i64` and widen); a per-test timeout or
process isolation; a public `Report::new`; a driver for subprocesses or
servers (write it: spawn, feed input, compare output, with a timeout);
automatic seeding from files (read them and `pool.invest(...)` them).
