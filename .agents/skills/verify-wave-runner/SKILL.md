---
name: verify-wave-runner
description: "Model-check the delegate wave runner's supervision loop (dispatch, --jobs cap, refused-launcher and exhausted-account bars, timeouts, leftover process groups, cleanup, status files and exit code) with TLA+. Use when a change touches the supervision loop of AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/run-wave.sh (its runner state and traps, write_status, bar_refused, reap_finished, stop_groups, the main loop, or cleanup and exit), or the wave runner's documented promises in delegate/references/wave-runner.md."
---

# Verify the wave runner

`AGENT-ENGINEERING/SKILL-SYSTEM/verification/wave-runner/` holds a TLA+ model
of `run-wave.sh`'s supervision loop, checked with TLC. Its properties are the
runner's promises: at most `--jobs` adapters at once, no launch after a
launcher or account bar, a runner failure or a signal, an account barred only
for its own exhausted quota, a status and a matching `.status`
file for every worker, exit 0 only when every adapter exited 0 and nothing the
wave started is alive, and the runner always exits. `NOTES.md` there states
each property, the bounds and what the model leaves out.

## Does the change touch the verified code?

Coverage record, sync commit `3119afc962ff`, in `run-wave.sh`:

- the runner state and traps (`pids=() statuses=() ...` through `set -m`)
- `write_status`, `bar_refused`, `reap_finished`, `stop_groups`
- the main loop (`lingering=0` through the `sleep 0.05` line)
- cleanup, statuses and exit (`# A returned adapter with a live local
  descendant ...` through `exit "$result"`)

`manifest.json` holds the same record with a hash of each unit; the check
reports any unit whose text changed since the sync commit. A change elsewhere
(argument parsing, the manifest reader, task writing) does not need this check
unless it changes a variable the loop reads.

## Run it

```bash
AGENT-ENGINEERING/SKILL-SYSTEM/verification/check wave-runner --quick
```

About a minute: two workers with every option (on one account and on two),
three workers serial, termination for one worker, and the fourteen mutations. Before calling a change
to the loop done, also run the full tier (`check wave-runner`, without
`--quick`), which adds three workers at each `--jobs` value and takes about
40 minutes on this machine.

Exit 0 passes. Exit 1 prints each problem: a property violated by the real
code, a mutation no longer caught, a covered unit that changed, or this skill
not naming the sync commit. Exit 2 means it could not run: it needs Java 11+
(Homebrew's `openjdk@21` is found without PATH changes) and downloads
`tla2tools.jar` 1.7.4 to `~/.cache/tla2tools/`, checked against the sha256
in `manifest.json`. Full TLC output is in `wave-runner/runs/`.

The runner prints each counterexample one line per step: the model action,
then the variables it changed. Each action in `WaveRunner.tla` cites the
`run-wave.sh` lines it models. To show a person the path, use the
`statechart` skill. This target has no `view.mjs` yet: write one beside the
model first (about 20 lines, as `$create-formal-verification-skill`
describes; `verification/skill-install/view.mjs` is an example). Then, from
`wave-runner/`:

```bash
~/.agents/skills/statechart/scripts/run WaveRunner.tla --config mutations/<x>.cfg --view view.mjs --out "$(mktemp -d)/chart"
```

Chart only mutation configs and small purpose-built ones, never a main
config: its first TLC run has no bound.

## Real bug or modeling error?

When a property fails on the real code:

1. Map each step of the counterexample to the cited lines and replay it
   against the real script, with stub launchers as
   `skills/delegate/tests/test_wave_runner.py` does. If the replay reaches the
   same state, it is a bug: report it with the steps in the script's words
   and the replay, and leave the model alone. Until it reproduces, report it
   as an unconfirmed candidate.
2. If a step is something the script cannot do (an event at a point the code
   never observes, a branch the code does not have), the model is wrong. Fix
   the model action, say why in its comment, and rerun.
3. Do not weaken a property to make a run pass. A property that no longer
   matches `wave-runner.md` changes only together with the documentation.

When a mutation is no longer caught, the model stopped describing the line
that mutation removes; find what changed in that action.

## When the change is intended

Covered code changed and the check says so:

1. `git diff 3119afc962ff -- AGENT-ENGINEERING/SKILL-SYSTEM/skills/delegate/scripts/run-wave.sh`
   and update each model action whose lines changed, including its line
   citations. Add a property if the change makes a new promise, and a
   mutation config under `mutations/` that removes the new code and must be
   caught.
2. Run `check wave-runner` (full tier) until it passes.
3. The sync commit is the commit whose code the model describes. When the
   covered file equals HEAD, run `check wave-runner --update-coverage`; it
   records HEAD as the sync commit and updates the commit named in this
   skill. If the change is not committed yet, ask the user before
   committing.
4. Update the results table and observations in `NOTES.md`.

## Findings

None: every property holds on the real code within the bounds. The model
catches the dispatch guard as it stood before 1ad297d4a
(`mutations/a-dispatch-after-runner-failure.cfg`). Lines 275 and 308-310 are
each sufficient alone to keep leftovers from going unreported
(`sufficiency/`); keep both. Cleanup signals owned groups without a liveness
check, so a reused PGID could be signalled; the model assumes no PID reuse.
