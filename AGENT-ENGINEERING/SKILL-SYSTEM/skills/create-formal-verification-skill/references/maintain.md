# Maintain an existing verification

Adapted from Lauren Tan's `maintain-formal-verification-skill` in
[Cursor pstack](https://github.com/cursor/plugins/blob/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/maintain-formal-verification-skill/SKILL.md)
(MIT), made concrete for the bundled runner.

A check can keep passing while it describes code that no longer exists, and that pass looks like a proof. A
generated verify skill handles a change that an agent makes while using it. This pass handles the changes that skipped
it: merges, edits made without the skill, and drift across many commits. Unchanged coverage hashes say only that no
covered text changed; they do not show that the model still matches the code, or that no new code writes the state a
property guards.

## Outcomes

Give each check one outcome:

- **in sync**: no change since the sync commit alters what the check describes, and it passes.
- **updated**: the code changed, the model now describes the new code, and the check passes.
- **bug**: the model describes the current code, and the code breaks the property. This is a finding, not drift.
- **blocked**: the check could not be brought back in line or could not run. Say exactly why.

A check can be both updated and bug.

## Edit scope

Edit only the verification: models, configs, `view.mjs`, `manifest.json`, `NOTES.md`, the runner copy and the verify
skill. Never edit product code unless the user asks. Never weaken a property or the model to make a check pass.

## Pass

1. **Find the checks.** `**/verification/*/manifest.json`; each names its verify skill in `skill`. Read the skill and
   `NOTES.md`. If no verification exists, stop and offer `$create-formal-verification-skill`.
2. **Run it as it is.** `<verification>/check <target> --quick`, before changing anything. Exit 1 with "covered code
   changed" is the drift signal, not a verdict; a property failure here can be drift or a bug, so do not decide until
   step 5. Also compare `<verification>/check` with the canonical `scripts/check` of this skill, and recopy it when it
   differs; never keep a local fork.
3. **Read every change to covered code.** `git log` and `git diff <syncCommit>` over the covered files, reading each
   commit message. Look for covered units that were renamed, split or moved, and for new code that writes the state a
   property guards. Classify each change:
   - **No effect**: nothing the model describes changed. Check this against the model, not the commit message.
   - **The model no longer describes the code**: an indivisible step became two, a branch or check moved or appeared,
     a new path reaches the guarded state, or a value's range changed.
   - **The promise changed on purpose**, with evidence in the change: a doc comment, test, changelog or commit
     message. The property must change; cite the evidence.
   - **The promise may be broken**: the code changed and nothing says the promise did. Treat a later failure as a bug
     candidate.
4. **Update from the code, not from the result.** Write each model change from the code before rerunning, with new
   line citations. Change a property only for a promise that changed on purpose, recording the old wording, the new
   wording and the evidence. Keep the bounds unless the change makes them wrong, and report any reduction.
5. **Rerun and judge each result**, with the full tier only where the affected claim needs it.
   - **Pass:** add a mutation config that breaks the new code the way the property guards against, and confirm the
     check catches it.
   - **Fail:** replay the counterexample against the real code, as a test with the suite's own fixtures. If a step
     cannot happen in the code, fix the model and say what was wrong. If every step happens, it is a bug: name the
     commit that introduced it, tell the steps in the code's words, and state the harm in one sentence. Until the
     replay reproduces it, it is an unconfirmed candidate.
   - **A finding config that now passes** because its bug was fixed: apply "Show that every property can fail" in
     `SKILL.md` (it becomes a pre-fix mutation, and its replay a regression test).
6. **Update the verify skill and the coverage.** Update the covered units, commands, bounds and assumptions in the
   skill, `manifest.json` and `NOTES.md`. Hashes cover each unit's text, not its position, so before moving the sync
   commit remap every model line citation into a file that changed since the old one. When the covered files equal
   HEAD, run `<verification>/check <target> --update-coverage`; otherwise ask the user before committing. Never update
   the coverage for a blocked check, and say so. Then follow the verify skill once as the next agent would.

## Report

For each check: its outcome and the commits read; what changed in the verification and why (the code changed shape,
or the promise changed on purpose, with the evidence); the rerun result and the mutation that shows it can still
fail; each bug in plain words with its harm and the commit that introduced it; and what the verification still does
not cover, including new code it should. Say which failures were drift and which were bugs. For a check that passed
before the update and fails after, say that the old pass was on a stale description.

Keep the verification updates in a change of their own, separate from any product fix.
