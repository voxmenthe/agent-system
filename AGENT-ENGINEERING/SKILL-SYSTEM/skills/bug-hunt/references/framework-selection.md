# Framework selection and setup

Use the engine the target's ecosystem already uses. Install it only in a
scratch environment that imports the target by path (stop rule 3). API
details below were checked against Hypothesis 6.170, fast-check 4.11,
proptest 1.12, Go 1.27, and cargo-fuzz `main`; recheck names against the
installed version's docs before relying on one.

## Choose

| Target | Default | Switch or add when |
|---|---|---|
| Python, in process | Hypothesis | The code can crash the interpreter or hang: run each case in a subprocess worker. Raw-bytes C-extension parsing: add Atheris. |
| TypeScript or JavaScript | fast-check | Async races: add `fc.scheduler()`. |
| Rust crate that already uses proptest | proptest | Explicit shrinkers, `ephyra check`, multi-failure runs, or coverage steering are worth a 0.0.1 dependency: Ephyra. |
| Rust crate with no PBT yet | proptest, or Ephyra if the user accepts it | |
| Go | `testing.F` native fuzzing | Structure: decode the fuzzed bytes into a structured value inside the target. |
| Untrusted bytes, memory safety, undefined behaviour | `cargo-fuzz` (libFuzzer) | Always as a complement to oracle-based properties, never as a replacement. |
| Non-Rust system needing many stacked oracles | Ephyra Rust driver with a JSON-lines worker | See [ephyra-playbook.md](ephyra-playbook.md). |

For every engine, settle the same eight things before hunting: scratch
install, structured generators, stateful sequences, diversity counts, the
shrink self-check, deterministic replay, the budget, and the state it leaves.

## Hypothesis (Python)

- **Install:** a scratch venv (`python3 -m venv`, or `uv venv`) with
  `hypothesis`, plus `pytest` and `coverage` if wanted.
- **Generators:** `@st.composite` functions that build values from the
  grammar; `st.sampled_from(POOL)` for colliding names; `st.lists(...,
  max_size=N)`; `st.recursive(base, extend, max_leaves=N)` for nesting;
  `st.from_regex(pattern, fullmatch=True)` for tokens; `st.text(alphabet=...)`
  with the format's special characters in the alphabet; `st.data()` when a
  later draw depends on an earlier result.
- **Discards:** avoid `.filter()` and `assume()` for common cases. The
  `filter_too_much` health check fails a run that rejects too many draws;
  never add it to `suppress_health_check` to get a pass.
- **Stateful:** `hypothesis.stateful.RuleBasedStateMachine` with `@rule`,
  `@precondition`, `@invariant` (checked after every step), `@initialize`,
  and `Bundle` with `consumes()` for handles. Run it as `Machine.TestCase`
  or with `run_state_machine_as_test`; `stateful_step_count` (default 50)
  sets sequence length.
- **Diversity:** `hypothesis.event(label)` in the test body; pytest
  `--hypothesis-show-statistics` prints each event's share. In a meta-test
  without pytest, call the `@given` function directly and count labels in a
  dict.
- **Targeting:** `hypothesis.target(score, label="...")` steers toward high
  scores during the `target` phase.
- **Shrink self-check:** `hypothesis.find(strategy, condition)` returns the
  minimal example satisfying `condition`. Assert it has the expected minimal
  shape, for example two sections and nothing else for `len(doc) >= 2`.
- **Several bugs:** with `report_multiple_bugs=True` (the default)
  Hypothesis reports failures with different exception types or locations
  separately. One `assert` covering two bugs reports only one of them.
- **Replay:** pytest `--hypothesis-seed=N` or the `@seed(N)` decorator;
  `derandomize=True` for a fixed run; `print_blob=True` prints a
  `@reproduce_failure(...)` line for the exact case; `@example(...)` pins an
  input. The plain-suite reproducer uses the literal shrunk value instead.
- **Budget:** `@settings(max_examples=N, deadline=None)`; the default 200 ms
  `deadline` reports slow cases as failures, so treat a sudden slow case as a
  hang candidate before removing it. A profile keeps this in one place:
  `settings.register_profile("hunt", max_examples=5000, deadline=None,
  database=None)` then `settings.load_profile("hunt")` or pytest
  `--hypothesis-profile=hunt`. Cap wall-clock time from outside.
- **Coverage:** `coverage run --branch --source=PACKAGE -m pytest`, then
  `coverage report -m`; point `COVERAGE_FILE` into the scratch directory.
- **Amplify:** `python3 -X dev` turns on default warnings and
  `faulthandler`; `faulthandler.dump_traceback_later(seconds, exit=True)` is
  an in-process watchdog.
- **State:** the example database `.hypothesis/` in the working directory.
  Use `database=None` or `HYPOTHESIS_STORAGE_DIRECTORY=<scratch>`, or delete
  it at teardown.

## fast-check (TypeScript and JavaScript)

- **Install:** a scratch package (`npm init -y`, `npm install fast-check`)
  that imports the target by path.
- **Generators:** `fc.record({...})`, `fc.tuple(...)`,
  `fc.constantFrom(...POOL)` for colliding names, `fc.oneof(...)`,
  `fc.letrec(tie => ({...}))` for recursive grammars,
  `fc.uniqueArray(arb, { selector })`, `fc.stringMatching(regex)`; `.map()`
  and `.chain()` for derived and dependent values. `fc.pre(cond)` skips a run;
  skips are capped by `maxSkipsPerRun`.
- **Stateful:** `fc.commands([...], { maxCommands })` with command objects
  implementing `check(model)` and `run(model, real)`, executed by
  `fc.modelRun(() => ({ model, real }), cmds)` or `fc.asyncModelRun`;
  `fc.scheduler()` explores async interleavings.
- **Diversity:** `fc.statistics(arb, v => label, { numRuns: 10000 })` prints
  each label's share; `fc.sample(arb, n)` shows raw values.
- **Shrink self-check:** `fc.check(property, { seed })` returns run details
  instead of throwing: assert `failed`, read `counterexample`, `numShrinks`,
  and `numSkips`.
- **Replay:** a failure prints `{ seed: ..., path: "...", endOnFailure: true }`;
  pass it back to `fc.assert(property, { seed, path, endOnFailure: true })`.
  `examples: [...]` pins inputs.
- **Budget:** `numRuns`; since 4.10 prefer the plugins
  `plugins: [fc.interruptAfterTimeLimit(ms, { failOnInterrupt: true })]` and
  `fc.timeout(ms)` (no effect on synchronous predicates) over the deprecated
  parameters of the same names. An interrupted run counts as passed unless
  `failOnInterrupt` (or the older `markInterruptAsFailure`) is set, so set it
  when a clean result matters.
- **Coverage:** the project's tool (c8, Vitest `--coverage`, or Node's
  `--experimental-test-coverage`).
- **State:** none by default; delete the scratch package and coverage output.

## proptest (Rust)

- **Install:** a standalone scratch test crate with `proptest` and the target
  as a path dependency; set `debug-assertions = true` and
  `overflow-checks = true` in its `[profile.test]` and `[profile.release]`.
- **Generators:** `prop_compose!`, `prop_oneof!`,
  `proptest::sample::select(POOL)` for colliding names,
  `proptest::collection::vec(s, 0..N)`, `Strategy::prop_recursive` for
  nesting, string literals such as `"[a-z]{1,4}"` as regex strategies;
  `prop_map` keeps shrinking, `prop_flat_map` handles dependent values.
  `prop_filter` and `prop_assume!` reject, and the run aborts after
  `max_local_rejects` or `max_global_rejects`.
- **Stateful:** the `proptest-state-machine` crate: `ReferenceStateMachine`
  for the model, `StateMachineTest` for the system under test,
  `prop_state_machine!` for the test.
- **Diversity:** no built-in label histogram; count classes yourself in a
  fixed-seed run.
- **Shrink self-check:** run the strategy through `TestRunner::run` with a
  synthetic failing predicate and assert the minimal value in
  `TestError::Fail(_, value)`.
- **Replay:** failures persist as `cc <hex>` lines in
  `proptest-regressions/`, in a file parallel to the test's source path, and
  replay first next time; fix a seed with `PROPTEST_RNG_SEED`.
- **Budget:** `ProptestConfig` fields `cases`, `max_shrink_iters`,
  `max_shrink_time`, `fork`, `timeout`, or the variables `PROPTEST_CASES`,
  `PROPTEST_MAX_SHRINK_TIME`, and `PROPTEST_TIMEOUT` (milliseconds per case;
  runs cases in a subprocess). `fork = true` survives aborts and segfaults.
- **State:** `proptest-regressions/`. Set
  `PROPTEST_DISABLE_FAILURE_PERSISTENCE` (presence alone disables it) or
  `failure_persistence: None`, and keep the shrunk value in a plain test.

## Go `testing.F`

- **Arguments:** only `[]byte`, `string`, `bool`, `byte`, `rune`,
  `float32`, `float64`, and the `int` and `uint` kinds. For structure, read
  the bytes as a sequence of grammar choices inside the target; seed with
  `f.Add(...)` from the project's fixtures.
- **Budget:** `go test -run='^$' -fuzz='^FuzzParse$' -fuzztime=60s ./pkg`.
  Without `-fuzztime` fuzzing runs forever; `-fuzztime=10000x` counts runs.
  `-fuzz` must match one fuzz test in one package. Minimization is built in
  (`-fuzzminimizetime`).
- **Self-check:** there is no shrinker to verify; count how often the byte
  decoder reaches each grammar production over a fixed corpus instead.
- **Replay:** failing inputs land in `testdata/fuzz/FuzzParse/` inside the
  package and become seeds for plain `go test`; replay one with
  `go test -run=FuzzParse/<file>`. Copy the case into a plain table test.
- **State:** `testdata/fuzz/` (delete unless kept) and the corpus cache in
  the build cache (`go clean -fuzzcache`).

## cargo-fuzz (libFuzzer)

- **Install:** `cargo install cargo-fuzz` installs a binary and needs a
  nightly toolchain: ask first. `cargo fuzz init` creates `fuzz/` inside the
  crate, so run it in a scratch copy of the target.
- **Structure:** `fuzz_target!(|input: Input| ...)` where `Input` derives
  `arbitrary::Arbitrary`.
- **Budget:** `cargo +nightly fuzz run TARGET -- -max_total_time=300
  -timeout=10 -rss_limit_mb=2048` (libFuzzer flags after `--`; `-runs=N`
  counts inputs). Debug assertions and overflow checks are on unless `-O`;
  AddressSanitizer is the default (`-s none` turns it off).
- **Findings:** `fuzz/artifacts/TARGET/crash-*` (also `timeout-*` and
  `oom-*`); minimize with `cargo fuzz tmin TARGET ARTIFACT`, print with
  `cargo fuzz fmt TARGET ARTIFACT`, then put the value in a plain `#[test]`.
  `cargo fuzz coverage TARGET` reports coverage.
- **State:** the whole `fuzz/` directory (targets, `corpus/`, `artifacts/`).

## Atheris (Python bytes)

For CPython code or C extensions whose risk is crashing on raw bytes:
`atheris.instrument_imports()`, `atheris.Setup(sys.argv, TestOneInput)`,
`atheris.Fuzz()`, and `atheris.FuzzedDataProvider` to carve typed values.
libFuzzer flags such as `-max_total_time` apply. Install it in the scratch
venv.

## Teardown checklist

| Engine | Leaves | Avoid or remove |
|---|---|---|
| Hypothesis | `.hypothesis/` | `database=None` or `HYPOTHESIS_STORAGE_DIRECTORY` |
| coverage.py | `.coverage*`, `htmlcov/` | `COVERAGE_FILE` in scratch |
| fast-check | nothing | delete the scratch package |
| proptest | `proptest-regressions/` | `PROPTEST_DISABLE_FAILURE_PERSISTENCE` |
| Go | `testdata/fuzz/`, cache corpus | delete; `go clean -fuzzcache` |
| cargo-fuzz | `fuzz/` | scratch copy, or delete |
| Ephyra | `.ephyra/` | run from scratch, `EPHYRA_REGRESSIONS=0`, or delete |

Finish with the target's own status check (`git status --porcelain` in a Git
repository) and confirm only files the user asked for remain; stop every
worker and mock server you started.
