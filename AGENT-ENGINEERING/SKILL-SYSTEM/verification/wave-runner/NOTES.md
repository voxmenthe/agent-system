# Delegate wave runner supervision

**Property.** The wave runner keeps the promises in
`skills/delegate/references/wave-runner.md`: at most `--jobs` adapters run at
once; a launcher that refused for quota or quarantine starts no more of the
wave, nor does any launcher on an account whose quota a worker exhausted, and
only that exhaustion bars an account; a runner failure or a signal stops dispatch; every worker ends with a
status, and its `.status` file says so; and exit 0 means every adapter exited
0 and nothing the wave started is still alive.

**Harm if broken.** The orchestrator trusts the exit code and the status
files. A wrong 0 lets it reuse a worktree that an orphaned process (an MCP
server, a build) is still writing; a wrong status hides a timeout or a failed
worker; dispatch past a refusal or a failed status write burns quota and
leaves evidence the summary does not describe.

Properties, all checked in every main config:

- **CapRespected**, **ActiveCounts**: no more than `--jobs` adapters at once,
  and `active` counts exactly the launched, uncollected ones.
- **NoLaunchAfterRunnerFailure**: after a failed status, evidence, sleep or
  summary write, or a group that survived SIGKILL, no worker starts.
- **NoBarredLaunch**: a barred launcher's queued workers do not start, nor
  do queued workers on any launcher of a barred account.
- **AccountBarsNeedExhaustion**: an account is barred only after one of its
  workers exhausted its quota; a launcher's own rate limit or quarantine
  leaves the account's other launchers eligible.
- **InterruptStopsDispatch**: after a signal at most one worker starts, the
  one already past the dispatch check (line 284).
- **EveryWorkerHasAStatus**, **StatusFilesMatch**: at exit every worker has a
  status, and its file holds it unless a write failed and the wave exits
  nonzero.
- **NoUnreportedLiveGroup**: the runner never exits while a worker's process
  group is alive unless it marks that worker `unconfirmed` and exits nonzero.
- **ExitZeroIsClean**: exit 0 means every status and file is `0`, the summary
  was written, and no group is alive.
- **TimeoutIsReported**: a worker stopped for `--timeout` never reads as an
  ordinary exit.
- **SettledStatusesSurvive** (a step property): a finished, barred or
  not-started status changes only to `unconfirmed`.
- **Termination**: the runner always exits, with `--timeout` even if an
  adapter never exits.

## Scope

- Lines 179-367 of `scripts/run-wave.sh`: dispatch, reaping, refused-launcher
  and exhausted-account bars, timeout and leftover stopping, cleanup, status files, the summary and
  the exit code. Parsing and task writing (1-178) are not modelled; the model
  starts with every `.task` written.
- Up to three workers, each on either of two launchers (every assignment),
  `--jobs` 1 to 3, with and without `--timeout`, and at most one failed write,
  redirection or sleep per run. The two launchers share one account in every
  config but `two-workers-split-accounts.cfg`, where each has its own. Termination is checked for one worker: TLC's
  liveness check did not finish for two in 400 s.
- The environment is adversarial: a leader exits at any time with 0, nonzero,
  a refusal or an account's exhausted quota; leftovers appear and disappear, may ignore SIGTERM and may
  survive SIGKILL; the timeout and the 5 s and 2 s windows elapse at any
  point; SIGINT or SIGTERM arrives at any time. Exit 143 is folded into 130.

Atomicity: within one loop iteration the script reads only its own worker's
processes, and a dead leader or group never comes back, so one iteration is
one step. Each environment event fires just before the runner's next read of
what it changes; an event elsewhere gives the same outcomes moved to that
point, since nothing in between reads it. The full argument is in the header
of `WaveRunner.tla`.

## Results on the RX-10 change (October 26)

The account-scoped bars, checked on the code committed as 3119afc962ff,
which the coverage record names.

| Config | Result | Distinct states | Time |
| --- | --- | --- | --- |
| `two-workers.cfg` every option, one account | pass | 6,212,688 | 11 s |
| `three-workers-serial.cfg` `--jobs 1`, no `--timeout` | pass | 12,204,132 | 19 s |
| `two-workers-split-accounts.cfg` every option, two accounts | pass | 6,508,536 | 11 s |
| `three-workers-jobs-1.cfg` (full tier) | pass | 60,817,204 | 93 s |
| `three-workers-jobs-2.cfg` (full tier) | pass | 407,255,134 | 10 m 7 s |
| `three-workers-jobs-3.cfg` (full tier) | pass | 894,109,592 | 27 m 12 s |
| `termination.cfg` one worker, fair scheduling | Termination holds | 29,330 | 2 s |
| `sufficiency/lingering-alone.cfg` without 308-310 (full tier) | NoUnreportedLiveGroup holds | 6,071,928 | 9 s |
| `sufficiency/final-check-alone.cfg` without 275 (full tier) | NoUnreportedLiveGroup holds | 5,716,624 | 9 s |
| `mutations/a` 284 without `runner_failed == 0` (before 1ad297d4a) | NoLaunchAfterRunnerFailure violated | 12,450 | 1 s |
| `mutations/b` 289 removed: a barred worker starts | NoBarredLaunch violated | 2,978 | 1 s |
| `mutations/c` 284 with `active <= jobs` | CapRespected violated | 818 | 1 s |
| `mutations/d` 340 without the group check | NoUnreportedLiveGroup violated | 4,412 | 1 s |
| `mutations/e` 366 removed: a failed summary still exits with the workers' result | ExitZeroIsClean violated | 7,030 | 1 s |
| `mutations/f` 220 removed: a timed-out worker reads as its exit code | TimeoutIsReported violated | 3,438 | 1 s |
| `mutations/g` 284 without `interrupted == 0` | InterruptStopsDispatch violated | 1,562 | 1 s |
| `mutations/hi` 275 and 308-310 both removed | NoUnreportedLiveGroup violated | 3,310 | 1 s |
| `mutations/j` 348 starting at the first worker | SettledStatusesSurvive violated | 2,803 | 1 s |
| `mutations/k` 348 removed | EveryWorkerHasAStatus violated | 4,001 | 1 s |
| `mutations/m` 344 removed: `unconfirmed` not written | StatusFilesMatch violated | 2,672 | 1 s |
| `mutations/n` 269-273 removed: a group that survives SIGKILL | Termination violated | 4,846 | 1 s |
| `mutations/o` 202-203 matching every refusal: a launcher's own refusal bars its account | AccountBarsNeedExhaustion violated | 930 | 1 s |
| `mutations/x` 286-288 removed: a worker on an exhausted account starts | NoBarredLaunch violated | 3,712 | 1 s |

The quick tier (`--quick`) is the first three rows, termination and the
mutations: about a minute. The full tier adds the three-worker `--jobs` rows
and the sufficiency configs: about 40 minutes. The `exhausted` exit kind
roughly doubled the three-worker state spaces (b22bbdbe914c: 47.6, 254.7 and
478.7 million).

Each mutation config checks only the property it is meant to break, and the
runner requires that property to be the one violated. Times are on a 32-core
machine; a counterexample's state count varies a little between runs, because
TLC's workers stop at different points.

## Retro-check

`mutations/a` is line 284 as it stood before 1ad297d4a, without
`runner_failed == 0`. The model catches it in a second:

1. W1 runs on launcher L and is refused for quota, so L is barred.
2. In the same dispatch pass, W2 (also on L) is barred, and its status write
   fails, which sets `runner_failed`.
3. The inner loop's guard does not read `runner_failed`, so W3 (on M) starts.

## Findings

None. Every property holds on the real code within the bounds above.

## Observations

- The two leftover backstops are each sufficient alone. Line 275 (a returned
  worker's live group keeps the loop running) and lines 308-310 (the final
  group check fails the runner into cleanup) each keep NoUnreportedLiveGroup
  (`sufficiency/`); removing both is caught (`mutations/hi`). Keep both:
  line 275 is what lets a worker keep its exit status after its leftovers are
  stopped, and 308-310 turns a missed case into `unconfirmed`.
- Cleanup sends SIGTERM and SIGKILL to every owned group without checking it
  is still alive (lines 314, 327). A group is disowned only when a check sees
  it gone (237, 254), so a group that ends just before cleanup can have its
  PGID reused and signalled. The model assumes no PID reuse; the window is
  small but real.
- A signal that arrives after the final check (line 311) exits 130 without
  cleanup. That is safe: every group was just confirmed gone and every status
  written.

## Outside the model

Argument parsing, manifest reading and task writing (1-178); `run-worker.sh`
and the adapters (a refusal is modelled as a nonzero exit with the failure
class on the last stderr line); `refusals.py`'s choice of which messages
exhaust an account, and the harness match (lines 202-203), which the model
folds into the exit kind; `launcher-routes.tsv` and the account lookup
(lines 48-59, 141-148), modelled as the constant `AccountOf`; what the summary contains; bash itself (traps
run between commands, `wait` returns the leader's status, `kill -0` on a
group); PID and PGID reuse; a second signal; more than one I/O failure;
termination for more than one worker.

## Code to model map

Lines are in `skills/delegate/scripts/run-wave.sh`. Every action in
`WaveRunner.tla` cites its lines; `manifest.json` hashes each unit below.

| Code | Model |
| --- | --- |
| runner state and traps (179-188) | `Init`, `Interrupt` |
| `write_status` (189-194) | the status write in `ReapOne`, `GuardBarred`, `MarkOne`, `RestOne` |
| `bar_refused` (198-213) | `barred` and `exhaustedAccounts` in `ReapOne` |
| `reap_finished` (214-241) | `ReapSkip`, `ReapOne`, `ReapDone` |
| `stop_groups` (248-278) | `StopPass`, `StopVanished`, `StopTimeout`, `StopEscalate`, `LingerIf`, `StopDone` |
| main loop (279-306) | `Loop`, `Brk1`, `DispatchOpen`, `GuardClosed`, `Barred`, `GuardBarred`, `GuardLaunch`, `ForkFails`, `Fork`, `Brk2`, `Sleep` |
| cleanup, statuses and exit (307-367) | `Confirm`, `Cleanup`, `Term`, `Wait`, `WaitCheck`, `KillAll`, `MarkOne`, `MarkDone`, `RestOne`, `RestDone`, `Summary`, `Exit` |
