# Running

## Workspace

The run lives in a learning workspace in the repository, placed by
`learning-workspace`'s rules, unless the user names another place:

```text
<task-root>/.learning-workspace/<slug>/
  notes.md                    # learning-workspace notes; evidence source: solutionize/RUN.md
  solutionize/
    .gitignore                # "tree/": keeps every worktree out of git status and git add
    BRIEF.md                  # problem, check, what is known, search scope, tools, base
    RUN.md                    # the record (template below)
    git-status-before.txt
    wave-001/
      wave.txt  preview/  jobs/
      <line-id>/ANSWER.md
      <line-id>/change.patch  # the line's change, saved before its worktree is removed
      <line-id>/tree/         # the line's detached worktree
    checks/<claim-id>/
      solution.patch  rerun.log  tree/
      check/                  # only when a checker agent is used
```

For a problem outside a repository, skip the worktrees. Attackers work in
their own directories, and confirmation reruns the claim's `REPRODUCE` steps
in a fresh directory.

## Set up

```bash
DELEGATE="$HOME/.agents/skills/delegate/scripts"
WS=<the learning workspace>
RUN="$WS/solutionize"
mkdir -p "$RUN" && RUN=$(cd "$RUN" && pwd -P)    # resolved, so it matches git's worktree paths
printf 'tree/\n' > "$RUN/.gitignore"
REPO=$(git -C "$RUN" rev-parse --show-toplevel)
WS_PATH=$(git -C "$WS" rev-parse --show-prefix)  # the workspace, relative to the repository root
git -C "$REPO" status --porcelain -- ":(exclude)$WS_PATH" > "$RUN/git-status-before.txt"
BASE=$(git -C "$REPO" stash create); BASE=${BASE:-$(git -C "$REPO" rev-parse HEAD)}
```

`git stash create` records uncommitted tracked changes as a commit without
touching the working tree or the stash list, so every worktree starts from
what the user sees. It does not include untracked files; copy any that the
problem needs. Record `BASE` in `BRIEF.md` and `RUN.md`.

In the workspace's `notes.md`:

- name `solutionize/RUN.md` as the authoritative evidence source;
- keep the current wave and the next action in `Resume state`;
- list `solutionize` among the skills to reread.

## Compose a wave

Write the wave's manifest, `$W/wave.txt`, from [briefs](briefs.md). Draw each
random line's passage first. By default, the draw reads the repository's
tracked files:

```bash
W="$RUN/wave-001"
DRAW='
import random, sys
paths = [p for p in sys.stdin.read().split("\0") if p]
random.shuffle(paths)
for path in paths:
    try:
        lines = [(n, l.rstrip()[:200]) for n, l in enumerate(open(path, encoding="utf-8"), 1) if l.strip()]
    except (OSError, UnicodeDecodeError):
        continue
    if len(lines) >= 3:
        k = min(random.randint(3, 5), len(lines))
        i = random.randrange(len(lines) - k + 1)
        print(f"{path}:{lines[i][0]}", *(l for _, l in lines[i:i + k]), sep="\n")
        break'
mkdir -p "$W/<line-id>"
(cd "$REPO" && git ls-files -z | python3 -c "$DRAW") > "$W/<line-id>/inspiration.txt"
```

- For a directory the user names, feed the draw that directory's files,
  skipping hidden ones:
  `(cd <dir> && find . -type f ! -path '*/.*' -print0 | python3 -c "$DRAW")`.
- The first line of `inspiration.txt` is the passage's `path:line`; the rest
  is the passage.
- An empty `inspiration.txt` means no text file had three non-blank lines.
  Make that line an own-choice line.
- After a stall, draw angles the same way from this skill's
  `references/angles.md`, adding each draw to the wave's record:
  `printf '%s\0' "$HOME/.agents/skills/solutionize/references/angles.md" | python3 -c "$DRAW" >> "$W/angles.txt"`.
  Draw again when the passage holds no angle.

## Launch a wave

```bash
for line in <line-ids>; do
  mkdir -p "$W/$line" && git -C "$REPO" worktree add --detach "$W/$line/tree" "$BASE"
done
"$DELEGATE/run-wave.sh" --wave "$W/wave.txt" --jobs-dir "$W/preview" --dry-run
"$DELEGATE/wave-usage" "$W/wave.txt"
"$DELEGATE/run-wave.sh" --wave "$W/wave.txt" --jobs-dir "$W/jobs" --jobs <n> ${budget:+--timeout "$budget"}
```

- For a repair line, apply the failing claim's patch in the line's new
  worktree before launch (`git -C <tree> apply <patch>`).
- Read the preview before the real launch.
- Run the last command in the background with nothing chained after it.
- To use native subagents instead, send each `preview/*.task` as one subagent
  prompt, with as many running at once as the host allows.

## Read results and confirm a claim

```bash
"$DELEGATE/wave-status" "$W/jobs"
sed -n '1,/^---$/p' "$W/<line-id>/ANSWER.md"     # the header only

C="$RUN/checks/C-<n>"; T="$W/<line-id>/tree"
mkdir -p "$C"
git -C "$T" add -A && git -C "$T" diff --cached --binary "$BASE" > "$C/solution.patch"
git apply --numstat "$C/solution.patch"          # the files it touches: none may belong to the check
git -C "$REPO" worktree add --detach "$C/tree" "$BASE" && git -C "$C/tree" apply "$C/solution.patch"
(cd "$C/tree" && <the check command>) > "$C/rerun.log" 2>&1; echo "exit $?" >> "$C/rerun.log"
```

Read `rerun.log`, skim the diff for special-casing, and record the result in
`RUN.md`. When a checker agent is needed, give it `$C/check/` with its own
worktree, and launch the checker manifest from [briefs](briefs.md).

## Clean up

Save each line's change, then remove the worktrees this run created, and only
those:

```bash
for T in "$RUN"/wave-*/*/tree; do
  git -C "$T" add -A && git -C "$T" diff --cached --binary "$BASE" > "$(dirname "$T")/change.patch"
done
git -C "$REPO" worktree list --porcelain | awk '/^worktree /{print $2}' | grep "^$RUN/" |
  while read -r tree; do git -C "$REPO" worktree remove --force "$tree"; done
git -C "$REPO" status --porcelain -- ":(exclude)$WS_PATH" | diff "$RUN/git-status-before.txt" -
```

- Removal needs `--force` because attacker worktrees hold uncommitted
  changes. Their patches are already saved, and the `grep` keeps removal
  inside this run.
- The patch diffs from `$BASE`, so it keeps a line's commits but not its
  ignored files. Before removing, list them (`git -C "$T" status --short
  --ignored`) and copy any a line's result depends on.
- Report any difference in `git status`. Other sessions may be changing the
  repository too, so never revert anything.

## RUN.md

```markdown
# <slug>
Base: <commit>. Check: <the frozen check>; changed: never | <when and why>.
Search scope: web <none | allowed lookups>; local files <paths>.
Agents: <as named>. Budget: none | <as named>.

## Waves
| Wave | Lines | Agents | Returned | Claims | Note |

## Lines
| Line | Wave | Kind | Angle | Agent | Result |

## Claims
| Id | Line | Claim | Confirmed by | Result |

## Results passed on
| Id | Result | Label (rerun or reported) | Used in |

## Next
<the next wave and why>
```

In the Lines table, Kind is fresh, build-on, repair, own choice or random. A
random line's Angle cell holds your reading and the passage's `path:line`,
and so does a line built on a drawn angle. In the Waves table, note a stall,
and whether angles were drawn after it.

## Resume

Check for running workers first (`wave-status`, `pgrep -f run-worker.sh`).

| Present | Missing | Resume at |
| --- | --- | --- |
| `wave-N/wave.txt` | `wave-N/jobs/` | launching wave N |
| `wave-N/jobs/` | some `.status` files | waiting, or rerunning only the lines confirmed dead, into a new jobs directory; never relaunch into an existing one |
| `ANSWER.md` headers | their `RUN.md` rows | triage |
| `checks/C-k/solution.patch` | `rerun.log` | confirming claim `C-k` |
| every claim settled | `## Next` | composing the next wave |
