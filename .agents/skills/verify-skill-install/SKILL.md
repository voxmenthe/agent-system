---
name: verify-skill-install
description: "Model-check the skill system's install, quarantine and rollback transactions (journal phases, crash windows, LIFO rollback, the install-state file, status) with TLA+. Use when a change touches SkillSystem's install, quarantine or rollback paths in AGENT-ENGINEERING/SKILL-SYSTEM/skill_system/operations.py, the incomplete-operation journal, or status classification."
---

# Verify skill install transactions

`AGENT-ENGINEERING/SKILL-SYSTEM/verification/skill-install/` holds a TLA+
model of `SkillSystem`'s install, quarantine and rollback, checked with TLC
under stops between any two writes. Its properties: a rollback of the tool's
own operation never refuses, a finished rollback restores its skill's tree and
entry, a rollback changes no other skill's entry, and with nothing incomplete
`status` tells the truth. `NOTES.md` there states each property, the bounds
and what the model leaves out.

## Does the change touch the verified code?

Coverage record, sync commit `17de28bd0d5f`:

- `skill_system/operations.py`: `SkillSystem._install_under_lock`,
  `quarantine`, `rollback`, `_rollback_install`, `_rollback_quarantine`,
  `_begin_rollback`, `_restore_state_entry`, `_preserve_current`,
  `_ensure_no_newer_active_operation`, `_ensure_no_incomplete`, `_phase`
- `skill_system/journal.py`: `list_incomplete_operations`
- `skill_system/model.py`: `iter_skill_states`

`manifest.json` holds the same record with a hash of each function; the check
reports any function whose text changed since the sync commit. `refresh` and
`sync` call `_install_under_lock` once per candidate and are covered through
it. Lock migration, validation, host projections and the Codex audit are not
modelled; `_rollback_lock` is covered by `tests/test_migration.py`.

## Run it

```bash
AGENT-ENGINEERING/SKILL-SYSTEM/verification/check skill-install --quick
```

About 15 seconds. The full tier (`check skill-install`) adds four operations
over two skills, with and without every stop window: about 1 min 45 s in all.

Exit 0 passes: the main configs hold and every mutation is caught. Exit 1
prints each problem: a property violated by the real code, a mutation no
longer caught, a covered
function that changed, or this skill not naming the sync commit. Exit 2 means
it could not run: it needs Java 11+ (Homebrew's `openjdk@21` is found without
PATH changes) and downloads `tla2tools.jar` 1.7.4 to `~/.cache/tla2tools/`,
checked against the sha256 in `manifest.json`. Full TLC output is in
`skill-install/runs/`.

The runner prints each counterexample one line per step: the model action,
then the variables it changed. Each action in `SkillInstall.tla` cites the
`operations.py` lines it models. To show a person the path, use the
`statechart` skill with the model's `view.mjs`, from `skill-install/`:

```bash
~/.agents/skills/statechart/scripts/run SkillInstall.tla --config mutations/<x>.cfg --view view.mjs --out "$(mktemp -d)/chart"
```

It reports the shortest path to the broken property in plain words and
writes a Mermaid chart. Chart only mutation configs and small purpose-built
ones, never a main config: its first TLC run has no bound. A mutation is a
broken variant of the code, so its chart shows what a guard prevents, not a
bug in the current code.

## Real bug or modeling error?

When a property fails on the real code:

1. Map each step to the cited lines. Replay it against the real code in a
   fake home, as a test in `tests/test_installer.py`: build a system with
   `make_system` and make a stop with `stop_before_journaling(phase)`, both
   from `tests/helpers.py`. If the replay reaches
   the same state, it is a bug: report it with the test and `status` output,
   and leave the model alone. Until it reproduces, report it as an
   unconfirmed candidate.
2. If a step is something the code cannot do, the model is wrong. Fix the
   action, say why in its comment, and rerun.
3. Do not weaken a property to make a run pass.

When a mutation is no longer caught, the model stopped describing the code
that mutation removes; find what changed in that action.

## Findings

None open. The model found four bugs, now fixed. `every-window.cfg` checks
each one's property at its bound or larger, mutations g-j put back the code
each fix replaced, and each fix has a regression test (`NOTES.md` lists
them). If `every-window.cfg` fails, a change may have brought one back:
replay it as above and fix the code, not the model.

- **F1**: a rollback restores only its own skill's install-state entry
  (`_restore_state_entry`), so rolling back an older operation after a newer
  one on another skill leaves that skill alone. `mutations/g` is the
  whole-file restore it replaced.
- **F2**: rollback decides from the disk whether the old tree is in
  `preimage/` or the quarantine path, so a stop between that rename and its
  journal write rolls back. `mutations/i` trusts the `prepared` phase
  instead.
- **F3**: the new tree counts as live when `staged/` and `rollback-new/` are
  empty, so a fresh install stopped after its staged rename rolls back to no
  tree. `mutations/h` trusts the phase instead; the occupied-target check
  then refuses.
- **F4**: rollback journals `rolling-back` once its checks pass, so a stop
  inside it is reported as incomplete and a repeated rollback resumes.
  `mutations/j` journals nothing until the end.

## When the change is intended

Covered code changed and the check says so:

1. `git diff 17de28bd0d5f -- AGENT-ENGINEERING/SKILL-SYSTEM/skill_system/`
   and update each model action whose lines changed, including its line
   citations. Add a mutation config under `mutations/` for new guarding
   code, which must be caught.
2. Run `check skill-install` (full tier) until it passes.
3. The sync commit is the commit whose code the model describes. When the
   covered files equal HEAD, run `check skill-install --update-coverage`; it
   records HEAD as the sync commit and updates the commit named in this
   skill. If the change is not committed yet, ask the user before
   committing.
4. Update the results table and findings in `NOTES.md`.
