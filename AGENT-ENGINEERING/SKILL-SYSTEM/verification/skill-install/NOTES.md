# Skill install, quarantine and rollback transactions

**Property.** Every install and quarantine can be rolled back to exactly what
was there before it, rolling back one skill never changes another, and when no
operation is incomplete `status` tells the truth about every install target.

**Harm if broken.** A rollback or a crash leaves a skill missing, shows a tree
the tool installed as someone else's (so `install` refuses it), or reports
success while the new tree stays live. The README promises rollback "LIFO per
affected path", that "after a stop inside an install, quarantine, lock
migration, or rollback, the next mutation stops and names the incomplete
operation", and that operations on different skills "can be rolled back in any
order" (`README.md` 483-567).

Properties, all checked in the main configs:

- **NoStuckRollback.** A rollback of the tool's own operation never refuses
  because of its own trees.
- **RollbackRestores.** A rollback that finishes leaves its skill's tree and
  install-state entry as they were before the operation.
- **RollbackStaysOnItsSkill.** A rollback changes no other skill's entry.
- **StatusAgrees.** With nothing running and no incomplete operation, no
  skill is `missing-managed` or `locally-modified`, and only a tree the user
  made is `unmanaged-collision`.

## Scope

- Two skills, three or four operations: any interleaving of installs (plain
  and `--force`), quarantines, source updates and rollbacks. One skill with
  four operations for any rollback order the code accepts. Exhaustive within
  those bounds.
- One mutating command at a time: `_lock` takes a non-blocking exclusive
  flock, so commands run one after another. `refresh` and `sync` run one
  `_install_under_lock` per candidate, so they are sequences of installs here.
- A command may stop between any two of its writes (a crash, or an exception
  such as a failed fsync or validation), and what it wrote stays.
  `StopWindows` picks where: `journal` is right after a journal write, which
  is where the tests inject (`fail_after`); `unjournaled` is after a rename or
  state write the journal does not show yet; `rollback` is inside a rollback.
- `every-window.cfg` and `every-window-four.cfg` stop in every window and
  roll back in any order the code accepts. `journal-stops*.cfg` and
  `one-skill-any-order.cfg` are the narrower configs that passed before the
  fixes; the findings came from the other windows and orders.
- Trees and the state file are reduced to content hashes: `v1`, `v2` and
  `foreign`, a tree the user made.

Atomicity: each `atomic_write_bytes`/`atomic_write_json` and each
same-filesystem rename is one step. A command's reads and checks happen in the
step that starts it, since nothing else writes while it holds the lock.

## Results at 17de28bd0d5f

| Config | Result | Distinct states | Time |
| --- | --- | --- | --- |
| `journal-stops.cfg` two skills, three ops, newest-first | pass | 596,872 | 2 s |
| `one-skill-any-order.cfg` one skill, four ops, any accepted order | pass | 133,165 | 1 s |
| `every-window.cfg` two skills, three ops, every window, any accepted order | pass | 1,557,078 | 4 s |
| `journal-stops-four.cfg` two skills, four ops (full tier) | pass | 10,010,634 | 19 s |
| `every-window-four.cfg` two skills, four ops, every window, any order (full tier) | pass | 28,320,750 | 59 s |
| `mutations/a` rollback without `_ensure_no_newer_active_operation` (709) | NoStuckRollback violated | 647 | 1 s |
| `mutations/c` rollback without `_restore_state_entry` (826, 938) | RollbackRestores violated | 30,634 | 1 s |
| `mutations/d` quarantine leaves the managed entry (896-899) | StatusAgrees violated | 43,974 | 2 s |
| `mutations/f` rollback without moving the new tree aside (820-821) | NoStuckRollback violated | 8,096 | 1 s |
| `mutations/g` whole-file state restore, as before F1's fix | RollbackStaysOnItsSkill violated | 4,168 | 1 s |
| `mutations/h` line 799 from the journaled phase, as before F3's fix | NoStuckRollback violated | 552 | 1 s |
| `mutations/i` a prepared operation moved nothing, as before F2's fix | NoStuckRollback violated | 372 | 1 s |
| `mutations/j` rollback journals nothing until it ends, as before F4's fix | StatusAgrees violated | 1,453 | 1 s |

The quick tier (`--quick`) is every row but the two four-operation configs:
about 15 s. The full tier takes about 1 min 45 s.

Each mutation config checks only the property it is meant to break, and the runner requires that property to be the one violated. A
counterexample's state count varies a little between runs, because TLC's
workers stop at different points.

## Findings

None open. The model found four bugs at `b22bbdbe914c`, none reached by the
tests then: `fail_after` raises only after a journal write, and the
out-of-order rollback test never checked `status` afterwards. All four are
fixed, and their finding configs and replay scripts were retired:
`every-window.cfg` checks each one's property at its bound or larger (two
skills, three operations, every stop window, any rollback order the code
accepts), mutations g, h, i and j put back the code each fix replaced and are
caught, and each fix has a regression test that stops the real code the way
the replays did (`tests/helpers.py` `stop_before_journaling`).

| Finding | Pre-fix mutation | Regression test |
| --- | --- | --- |
| F1 | `mutations/g` | `test_rollback_restores_only_its_own_skill_state` |
| F2 | `mutations/i` | `test_stops_between_a_rename_and_its_journal_write_roll_back` |
| F3 | `mutations/h` | `test_stops_between_a_rename_and_its_journal_write_roll_back` (fresh case) |
| F4 | `mutations/j` | `test_a_stopped_rollback_stays_incomplete_and_resumes` and the tests below |

**F1, an out-of-order rollback across skills restored the whole install
state.** `install alpha`, `install beta`, then `rollback <alpha's op>`
(allowed: nothing newer touches alpha's path) wrote back the state from
before alpha, without beta's entry: beta showed `unmanaged-collision` and
`install beta` refused it. Fix: `_restore_state_entry` (768-787) puts back
only the operation's own skill entry. Test:
`test_rollback_restores_only_its_own_skill_state`.

**F2, a stop between a rename and its journal write left a rollback that
refused.** Install moves the old tree into `preimage/` (665) before journaling
`preimage-preserved` (668); quarantine moves the target (887) before
journaling `target-quarantined`. Stopped there, rollback read `prepared`,
expected the old tree at the target and refused, and every mutation stayed
blocked. Fix: both rollbacks decide from the disk whether the old tree is held
in the transaction (807, 918). Tests:
`test_stops_between_a_rename_and_its_journal_write_roll_back`,
`test_a_stop_before_the_quarantine_move_is_journaled_rolls_back`, and for lock
migration `test_a_stop_before_the_lock_replacement_is_journaled_rolls_back`.

**F3, a fresh install stopped after its staged rename rolled back
"successfully" and left the tree live.** The journal said
`preimage-preserved`, so rollback did not think the new tree visible and never
moved it aside; status then showed `unmanaged-collision`. Fix: the new tree is
live when `staged/` and `rollback-new/` are both empty (799). Test: the fresh
case of `test_stops_between_a_rename_and_its_journal_write_roll_back`.

**F4, a stop inside a rollback left a skill missing with no incomplete
operation.** Rollback journaled nothing until it ended, so a stop after moving
the new tree aside left `missing-managed`, and both `rollback` and `install`
then refused. Fix: once its checks pass, rollback journals `rolling-back`
(`_begin_rollback`, 762-766), which `list_incomplete_operations` reports, and
a repeated rollback resumes from the disk. Tests:
`test_a_stopped_rollback_stays_incomplete_and_resumes`,
`test_a_stopped_quarantine_rollback_resumes`, and
`test_a_lock_rollback_stopped_before_its_journal_write_resumes`.

A refused rollback still changes nothing and leaves the operation as it was
(`test_refused_rollback_changes_nothing_and_blocks_nothing`), because the
`rolling-back` mark comes after the checks.

## Observations

- Install's `_ensure_no_incomplete` (583) is not caught as necessary: the
  model has no recoverability property ("every incomplete operation can still
  be rolled back"), and with newest-first rollbacks a second operation started
  over an incomplete one is rolled back first. The mutation was tried and
  dropped rather than kept as a check that cannot fail.
- `mutations/a` shows why the per-path check exists: rolling back an older
  operation over a newer one on the same path finds the newer tree and
  refuses. Across paths, the per-entry state restore keeps rollbacks
  independent.
- The occupied-target check (807-809) backstops line 799: with 799 decided
  from the phase (`mutations/h`), the stopped rollback refuses rather than
  reporting success with the new tree live, which was F3.

## Outside the model

Lock migration and `_rollback_lock` (decided from the lock's hash like the
others, and covered by `tests/test_migration.py`); skill-tree validation and hashing (taken
as given); host projections (Claude, mimo, grok) and the Codex audit; a user
editing a managed tree (no `locally-modified` path is generated); trees and
transactions on different filesystems (renames are assumed atomic); disk
contents of the state file beyond each skill's hash; concurrent commands
(excluded by the flock, which is not modelled).

## Code to model map

Lines are in `skill_system/operations.py` unless named. Every action in
`SkillInstall.tla` cites the lines it models; `manifest.json` hashes each unit
below.

| Code | Model |
| --- | --- |
| `SkillSystem._install_under_lock` (575-692) | `StartInstall` (checks, staged copy), `InstallStep` |
| `SkillSystem.quarantine` (828-909) | `StartQuarantine`, `QuarantineStep` |
| `SkillSystem.rollback` (694-723) | `RollbackAllowed`, `StartRollback`, `RefuseRollback`, the `journal` step of `RollbackStep` |
| `_rollback_install` (789-826), `_preserve_current` (755-760) | `NewLive`, `OldHeld`, `RollbackRefused`, the `aside` and `restore` steps |
| `_rollback_quarantine` (911-938) | `OldHeld`, `RollbackRefused`, the `restore` step |
| `_begin_rollback` (762-766) | the `begin` step of `RollbackStep` |
| `_restore_state_entry` (768-787) | the `state` step of `RollbackStep` |
| `_ensure_no_newer_active_operation` (732-753) | `NewerOnPath` |
| `_ensure_no_incomplete` (346-356), `journal.py` `list_incomplete_operations` (181-189) | `Incomplete` |
| `_phase` (397-407) | each phase write; the `journal` stop window |
| `model.py` `iter_skill_states` (771-782) | `Status` |
