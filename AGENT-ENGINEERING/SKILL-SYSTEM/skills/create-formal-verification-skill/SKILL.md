---
name: create-formal-verification-skill
description: "Formally verify the code where a bug costs the most and tests reach the least, then leave a one-command check and a project-local verify skill that keep the verification in step with the code. Use only when the user explicitly invokes $create-formal-verification-skill, for example to model-check a race, a crash window, a retry or a state machine, or to prove an invariant, or to bring an existing verification back in line with the code after merges or many commits. Do not use automatically or for ordinary testing."
disable-model-invocation: true
---

# Create a formal verification skill

A test checks the cases that someone thought to write. Formal verification
checks every case in a stated scope: every order of steps in a model, every
input up to a bound, or every input. This skill finds the part of the repo
where that matters most, verifies its promises, and leaves a project-local
skill that lets the next agent check a change against them. Write that skill
for an agent who reads it cold, mid-change, and has never seen your work. The
user must be able to trust the result and act on it without learning the
verification language.

## Choose the target from the code

Answer from the codebase, and ask the user only what you cannot observe. If
the user named an area or a bug, start there.

A good target is a promise the code makes, where a break harms users and
tests rarely reach the case that breaks it. Choose the strongest such target
in the repo, not the one that is easiest to verify. Read its tests: the
failure points, orders and sizes they inject are where the model starts, and
the cases between them are where bugs hide (a stop between a rename and the
journal write that records it, a stop inside recovery, an operation order the
docs allow and no test checks).

## Let the question choose the tool

Pick the tool that answers the question at the lowest cost. Whether events can
happen in a bad order usually suits a model checker over a small model of the
design, and TLA+ with TLC is the default for that in any language; the
bundled runner supports it. Whether the code itself behaves for every input,
as with memory safety, overflow, or a data-structure invariant, usually suits
a verifier that runs on the code. If no verifier runs on this language, say
so, and test the real code with generated inputs, not a hand model of the
function. A property that must hold at every size can need a proof. Prefer a
tool the repo's developers can install and run, pin its version, and tell the
user why you chose it. With a tool other than TLC, write a runner with the
same contract as `scripts/check` (below).

## What makes it good

- **True to the code.** Every action in the model cites the lines it models,
  taken from a numbered listing of the file at the sync commit. What the model
  treats as one indivisible step is one in the code, and the model's header
  argues why. Names come from this repo.
- **Able to fail.** A check you have never seen fail proves nothing. Show each
  property failing on a broken variant of the code it guards.
- **Findings stay findings.** When the current code breaks a property, report
  it with the counterexample in the code's terms, and replay it against the
  real code. Do not weaken the property or the model until it passes, and do
  not change product code unless the user asks.
- **Honest about scope.** Say what is verified, under which bounds and
  assumptions, and what is left out. A pass covers the model and the bound,
  not the whole system.
- **Readable without the tool.** State each property and its harm in one
  plain sentence. Tell a counterexample as a short sequence of steps in the
  code's words.
- **Cheap to rerun.** One command, a pinned tool version, and a quick tier
  short enough (about a minute) that the next agent runs it on every relevant
  change. Larger bounds go in a full tier.
- **Kept in step with the code.** Record which functions or regions each
  model covers and the commit at which you last confirmed that the model
  describes them, so a later change to that code is reported.

Read [the modelling lessons](references/tla-lessons.md) before writing the
model: they cover atomicity, keeping the state space small, liveness, crash
windows, readable traces, and telling a model error from a bug.

## Lay it out

```text
<verification>/                 # beside the code it covers, e.g. src/verification
  check                         # a copy of scripts/check
  .gitignore                    # */runs/
  <target>/
    <Model>.tla
    view.mjs                    # the reader's words for the statechart skill
    <main>.cfg                  # the real code; expected to pass
    mutations/<x>-<what>.cfg    # one broken variant each; expected to break its property
    findings/F<n>-<what>.cfg    # a bug in the real code; expected to break its property
    sufficiency/<what>.cfg      # optional: one of two guards removed; expected to pass
    manifest.json
    NOTES.md
.agents/skills/verify-<target>/SKILL.md
.claude/skills/verify-<target>  -> ../../.agents/skills/verify-<target>   # when the repo has Claude project skills
```

Write `view.mjs` (about 20 lines) for the `statechart` skill: state and step
labels in the reader's words, a step's label read from its `from` state, every
instance of a parameter rather than one, and a title that names the model.
Run it once on one mutation. A target made before views existed gets one the
first time someone wants a picture.

Use the repo's own convention for project skills when it has one. Mutations
and findings are switched on through a `Mutants` constant, so each is one
`IF "x" \in Mutants` in the model and one config, and each such config checks
only the property it targets.

`manifest.json` holds `spec`; `skill` (the verify skill's path from the repo
root); `tlaTools` (`version`, `url`, `sha256`); `checks`, each with `config`,
`expect` (`"pass"` or the property that must be the one violated), `quick`,
`what` and an optional `timeoutSeconds` (about three times the measured time;
a check over it could not run); and `coverage` with `syncCommit` and `code`
entries of `file`, `kind` (`py-function` with a qualified `unit` such as
`Store.save`, `sh-function`, or `sh-region` with exact `from` and `to` lines)
and `sha256`. Hash the units the
model describes, not their transitive dependencies, or most changes will be
reported. Start with an empty `syncCommit` and `sha256` values, write
`<sync-commit>` wherever the verify skill names the sync commit, then run
`check <target> --update-coverage`, which writes the commit there.

## Use the runner

Copy `scripts/check` into the verification directory unchanged. If the
runner is wrong, fix this skill's copy and recopy it; never leave a local
fork. `check
<target>` runs every check; `--quick` only those marked quick;
`--update-coverage` records HEAD and the covered code's hashes, refuses while
a covered file differs from HEAD or the verify skill does not name the current
sync commit, and rewrites that sync commit in the skill. Exit 0 is a pass, 1 a problem (a property violated on the real
code, a mutation or finding not caught, covered code changed, or the skill
naming a different sync commit), 2 could not run. Each problem prints its
counterexample one step per line: the action, then the variables it changed.

The runner downloads the pinned `tla2tools.jar` to `~/.cache/tla2tools/` and
refuses one with a different sha256. If the repo records third-party tools,
record that download there. TLC needs Java 11 or newer; on macOS the runner
also finds Homebrew's keg-only `openjdk`.

## Show that every property can fail

- One mutation per guard: remove a check, reorder a step, or widen a bound,
  and require the targeted property to be the one violated.
- Model the pre-fix version of any recently fixed bug in the area as a
  mutation. Catching it shows the model would have found it.
- When two guards protect the same property, remove each alone in a
  sufficiency config, so the notes can say whether each is load-bearing.
- Set each main config at the largest tested bound where the real code
  passes within its time budget. A larger bound that breaks a property on the
  real code is a finding; state the passing bound in the notes.
- A mutation that is not caught means a property is missing, the bound never
  reaches the mutated step, or the mutation changes nothing observable; tell
  which before adding a property, or drop the mutation and record the gap in
  the notes. Never keep a check that cannot fail. Give each mutation config
  constants that a passing main config also covers, so its violation can only
  come from the mutant.
- A finding config is expected to fail and passes the check while the bug
  stands. When a fix lands, turn the finding into a mutation of the code
  before the fix (it must still break its property), and make sure a main
  config checks that property at the finding's bound or larger. Delete the
  finding config unless it covers a bound or order no main config does. The
  replay becomes the fix's regression test in the repo's suite; write it
  with the suite's own fixtures from the start.

## Write the notes

`NOTES.md` states each property and its harm, the scope and bounds, the
atomicity argument, a results table (config, result, distinct states, time),
each finding as numbered steps in the code's words with the replay command and
a suggested fix, observations such as redundant guards, what is outside the
model, and a map from each covered unit to the model actions that describe it.

Chart only configs whose recorded run is under about 50,000 states and a few
seconds: mutations, findings and small purpose-built configs. Never chart a
main or full-tier config, because the statechart's first TLC run has no
bound and uses one worker. Above 500 states it draws only the bug paths.
Write its output to a new folder outside the repo.

## Generate the verify skill

Write a project-local skill with frontmatter that names the area and says when
to use it. Without frontmatter, the skill never registers. From the skill
alone, the next agent must be able to:

1. **Tell whether a change touches the verified code.** List the coverage
   record and the sync commit, and name what is not covered.
2. **Run the check.** The real command, both tiers and their times, the exit
   codes, and what it needs installed.
3. **Read a result.** The runner's step-per-line trace and the line citations
   in the model. Name the `statechart` skill and this target's chart command
   for showing a person a counterexample.
4. **Tell a real bug from a modelling error.** Map each step to the cited
   lines and replay it on the real code; a step the code cannot take is a
   model error.
5. **Handle the findings.** Each in plain words, and what to change when one
   is fixed.
6. **Update the verification when a change is intended.** Classify each
   change as no effect, model stale, promise changed on purpose (with the
   evidence) or promise may be broken, and end each check in sync, updated,
   bug or blocked. Diff the covered code since the sync commit, update the
   affected actions and citations, add a mutation for any new guard, and run
   the full tier. The sync commit is the commit whose code the model
   describes: when the covered files equal HEAD, run `--update-coverage`;
   otherwise ask the user before committing.
   After merges or many commits that skipped this skill, follow
   `$create-formal-verification-skill`'s maintain procedure instead.

Use this repo's real commands, paths, and nouns, and leave no placeholders
other than `<sync-commit>` before the first `--update-coverage`.

## Maintain an existing verification

When the code changed without the verify skill (merges, edits made without it,
drift across many commits), follow [the maintain procedure](references/maintain.md):
run the check as it is, read every change since the sync commit, update the
model from the code, rerun, and give each check one outcome.

## Prove it before you hand off

Follow the generated skill once, as the next agent would, on a scratch change
that breaks a property in the real code. Make it in a throwaway worktree, never
in the live tree: `git worktree add --detach /tmp/<name> HEAD`, then copy the
untracked verification and skill into it. The check must first report the
changed code; once the model is updated to match the change, as the skill
says, it must fail with a counterexample. Then remove the worktree (`git
worktree remove --force /tmp/<name>`), after checking that it holds no commit
or ignored file you need, and confirm that the check in the real
tree is back where it started: passing, with every finding still shown. A
verify skill that was never run is a draft. If the skill misses the break or a
step does not run, fix the skill or the verification, not the scratch change.

## Hand off

Summarise `NOTES.md` for the user in plain words, and say which tool you
used and why, how to run the check and what it costs. Offer a fix for each
finding without making it. Where it is cheap, check the fix in a scratch
variant of the model and give the bound at which it passes; otherwise label
it unverified. Suggest a second target only if you found a close one. The
verify skill's update section is the upkeep loop for later changes.
