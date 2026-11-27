# Council procedure

Commands for each stage in [SKILL.md](../SKILL.md). Run them in a tool shell
(bash). Every path is absolute.

```bash
COUNCIL=<this skill's directory>               # e.g. $HOME/.agents/skills/council
DELEGATE="$HOME/.agents/skills/delegate/scripts"
WS=<absolute task workspace>                   # panelists and judges start here
RUN=<run root>/<YYYYMMDD-HHMM>-<slug>          # see "Run root" below
```

## Run root

1. A path the user names.
2. `<learning-workspace>/council/` when a learning workspace is active for
   the task.
3. `<repo>/.council/` when the task already writes in the repository (say so
   in the bill; `.council/` is not gitignored).
4. Otherwise `~/.local/state/council/runs/`.

A single run needs no learning workspace: its run directory is the
transcript and resume record. For multi-round campaigns or council rounds
inside a longer investigation, use option 2. Keep pointers and conclusions
in the workspace notes, never candidate text, and record candidate claims as
hypotheses that only your grounding checks promote.

## 0. Name check, bill and frame

Check every launcher before any call; print nothing for a good name:

```bash
for n in <panel launchers> <judge launchers>; do
  bash -c 'source ~/.bash_agents >/dev/null 2>&1; declare -F "$1" >/dev/null' _ "$n" ||
    echo "undefined in ~/.bash_agents: $n"
  "$DELEGATE/run-worker.sh" --help | tr -s ' (),;:' '\n' | grep -qx "$n" ||
    echo "not accepted by delegate: $n"
done
```

On a failure, show the likely fix (for example, `ccxb` is undefined and
`ccbx` was probably meant) and launch only on the user's OK.

The name check proves a launcher exists, not that it works. For a launcher
that is suspect or was just edited, run `"$DELEGATE/probe-launcher" <name>`
by hand: one read-only external call that reports launch, failure class,
final message and routed model. Say so in the bill. It is a diagnostic,
not a gate: never run it on every launcher or before every wave.

Bill inputs: `bash -c 'source ~/.bash_agents >/dev/null 2>&1; usage'`.

Code or PR council: fix known defects and run the cheap local checks before
anything below, so the preflight records the state the panel reviews. When
your task does not authorize edits, list the known defects in `TASK.md` so
panelists look past them. Skip both for code about to be replaced.

Create the run directory and freeze the task and the preflight state:

```bash
mkdir -p "$RUN/parent" "$RUN/judge"
# write "$RUN/TASK.md": the task as for one strong agent, then
# "# SOURCE DOCUMENTS" with absolute paths; no deliverable path, no hist refs
git -C "$WS" status --porcelain >"$RUN/preflight.txt" 2>&1 || echo "not a git workspace" >"$RUN/preflight.txt"
```

`RUN.md` template; keep `## Ledger` last so ledger lines can be appended:

```markdown
# Council run: <slug>

Bill: <launchers>; <n> external calls; ~<minutes> min; quota: <windows>
Panel budget: none (or <minutes> min, run-wave --timeout <seconds>)
Deliverable: <absolute path>
Workspace: <WS>
Preflight: preflight.txt

## Roster

| Letter | Seat | Launcher | Lane |
| --- | --- | --- | --- |
| A | panel | <launcher> | <lane or -> |
| B | sealed parent | - | <lane or -> |

Judges: <launchers>. Lane choices and why: <one line each, roles on only>

## Ledger

- <UTC> launched panel-1
```

## 1. Panel

Draw the sealed letter and build the manifest. Panel order follows the
invocation; letters are A, B, ... for panelists plus the parent.

```bash
panel=(cax ccfh dswe)                          # the roster, in order
n=$(( ${#panel[@]} + 1 ))
letters=($(printf '%s\n' {A..Z} | head -n "$n"))
SEALED=${letters[RANDOM % n]}                  # record in RUN.md before launch
{ printf 'COMMON:\nROLE: analyze\nWORKSPACE: %s\n' "$WS"
  printf 'OBJECTIVE: Answer the task in CONTEXT completely and independently. Put the complete answer under FINDINGS.\n'
  printf 'SCOPE: Read-only. Read every source document named in CONTEXT in full, and anything else you need; edit nothing.\n'
  printf 'CONTEXT:\n'; awk '{print "  " $0}' "$RUN/TASK.md"
  printf 'CONSTRAINTS: Work alone; other models answer the same task. Do not name your model, vendor, tools, or any task id. Do not edit files, commit, or delegate. The task in CONTEXT is the whole bar: add no review round, sign-off gate or scope above it, and report a problem the sources already had in one line instead of blocking on it.\n'
  printf 'VERIFY: Ground claims about code or documents in what you actually read; list it under EVIDENCE.\n'
  i=0
  for L in "${letters[@]}"; do
    [[ $L == "$SEALED" ]] && continue
    printf '@@ launcher=%s name=%s\n' "${panel[i]}" "$L"; i=$((i + 1))
  done
} >"$RUN/wave.txt"
"$DELEGATE/run-wave.sh" --wave "$RUN/wave.txt" --jobs-dir "$RUN/dry" --dry-run >/dev/null && rm -r "$RUN/dry"
```

Use `awk`, not `sed`, to indent the task: macOS `sed` drops the final
newline and the manifest is rejected.

### Roles on

Drop the `OBJECTIVE` line from `COMMON`. Give each worker block its own,
carrying its lane text from [roles](roles.md), and write `lanes.tsv` for
every candidate, the sealed parent included:

```bash
printf '@@ launcher=%s name=%s\nOBJECTIVE: Answer the task in CONTEXT from the %s lane: %s Put your complete answer for this lane under FINDINGS.\n' \
  dswe A implementer "Write the COMPLETE working implementation; ..."
printf 'A\timplementer\tcomplete-answer\n' >>"$RUN/lanes.tsv"
```

### Launch

Run this **in the background** (Claude Code: `run_in_background`; elsewhere
`&` plus the host's completion notice) with nothing chained after it:

```bash
budget=''                     # seconds, only when the user named a time budget
"$DELEGATE/run-wave.sh" --wave "$RUN/wave.txt" --jobs-dir "$RUN/panel-1" \
  --jobs "${#panel[@]}" ${budget:+--timeout "$budget"} >"$RUN/panel-1.log" 2>&1
```

There is no default timeout: council workers can legitimately run for a very
long time. With a budget, a worker still running past it gets status
`timeout`. To stop the whole panel early, at the user's say, send `kill -TERM`
to the `run-wave.sh` process; it stops every worker group and writes their
statuses.

## 2. Seal

Next action after launching: write `$RUN/parent/$SEALED.md` with the lines
`STATUS:`, `FINDINGS:`, `EVIDENCE:`, `BLOCKERS:` (the panel's format), the
complete answer under `FINDINGS:`. Then:

```bash
printf -- '- %s sealed parent/%s.md sha256 %s\n' "$(date -u +%FT%TZ)" "$SEALED" \
  "$(shasum -a 256 "$RUN/parent/$SEALED.md" | cut -d' ' -f1)" >>"$RUN/RUN.md"
```

Only now may you check status or read anything under `panel-*/`. From then
on, while slower panelists or judges run, you may read finished `.out` files
and check their load-bearing claims against the sources. Keep it read-only:
no edits, and no command that writes into the workspace (formatters, builds,
tests that leave caches) until every panelist and judge has finished. Note
checks in `$RUN/verify.md`, never under `parent/`: the packet script reads
every `parent/*.md` as a candidate.

## Status (also the first command on resume)

```bash
for d in "$RUN"/panel-*/; do
  if [[ -f $d/SUMMARY.tsv ]]; then cat "$d/SUMMARY.tsv"
  else grep -H . "$d"*.status 2>/dev/null || echo "$d: no status yet"; fi
done
pgrep -fl "$RUN" || echo "no live runner for this run"
```

A missing `.status` means unknown, never failure. Rerun only a letter whose
runner is confirmed dead, into the next `panel-<n>`, keeping its launcher
and block:

```bash
k=2 id=D
{ sed '/^@@/,$d' "$RUN/wave.txt"
  awk -v id="$id" '/^@@ /{keep = ($NF == "name=" id)} keep' "$RUN/wave.txt"; } >"$RUN/wave-$k.txt"
"$DELEGATE/run-wave.sh" --wave "$RUN/wave-$k.txt" --jobs-dir "$RUN/panel-$k" \
  ${budget:+--timeout "$budget"} >"$RUN/panel-$k.log" 2>&1        # background
```

## 3. Judges

```bash
"$COUNCIL/scripts/judge-packet.sh" "$RUN" "$COUNCIL/references/judge.md"
```

It prints each letter as included or excluded, fails below two usable
external candidates, and writes `judge/packet.md`. Then run every judge in
parallel, in the background, from the workspace:

```bash
judges=(camb)            # the default (ccbm for a Codex/OpenAI parent), or every named judge
for j in "${judges[@]}"; do
  ( cd "$WS" && "$DELEGATE/run-worker.sh" "$j" --task-file "$RUN/judge/packet.md" \
      >"$RUN/judge/$j.out" 2>"$RUN/judge/$j.stderr"; echo $? >"$RUN/judge/$j.status" ) &
done; wait
for j in "${judges[@]}"; do
  echo "== $j exit $(cat "$RUN/judge/$j.status")"
  grep -E '^(RANKING|BASE|DELTAS):' "$RUN/judge/$j.out" || echo "$j: missing selection lines"
done
```

A judge that fails or omits the selection lines is a failed judge; continue
on the others. If all fail, retry once with the other default judge
(`camb`/`ccbm`), then fall back to the [fast lane](#fast-lane) and mark the
run degraded in `RUN.md` and the report. A retry that lands on your own
vendor (a Claude parent retrying with `ccbm`) records
`reduced judge independence`.

## 4. Synthesize

No commands. Choose the outcome from what the candidates and your checks
show, not from how many judges agreed:

| Outcome | When | What you write |
| --- | --- | --- |
| Adopt | Strong candidates converge on one shape and your checks hold it up. | The base with its verified fixes. Note the convergence; graft nothing just to credit a seat. |
| Hybrid | One base is best; other candidates hold a few load-bearing ideas it lacks. | The base, edited under one coherent model, with at most one or two grafts per other candidate, each folded in by hand rather than pasted. |
| Revise first | Candidates answered different questions, or rest on incompatible premises the sources cannot settle. | No merged deliverable. The audit and the report name the open decision as one question the user can answer, which candidates took which reading, and a revised `TASK.md` with the bill for a new round. |

Agreement is a correlated prior, so Adopt still needs your checks. If the
invocation already settled the open decision and `TASK.md` dropped it, say
so: the framing slip is yours, and the revised `TASK.md` restores it.

Tie-break, for two viable bases still close after your grounding checks;
stop at the first step that separates them:

1. Correctness and fit to the user's intent.
2. Grounding in real files, tests and behavior you checked.
3. The simpler, reversible first cut that does not block the intended
   future.
4. The better validation and rollback story.
5. Lower execution cost, once quality is acceptable.

Rank the answer apart from its executor: a plan can win while a different
model is the better choice to build it. Say so separately when it matters.

Write the deliverable (none for Revise first), then close the ledger by
appending the audit after its last line:

```markdown
## Audit

Outcome: <Adopt | Hybrid | Revise first>: <why, one line>
Open decision: <the question; letter: reading, ...> (Revise first only)
Base: <letter> (<launcher>, <lane>); judges: <judge: RANKING / BASE each>
Judge independence: <full, or reduced: judges and your vendor>
Adopted: <letter (launcher): idea>; ...
Extended: <letter (launcher): idea, and how>; ...
Rejected: <letter (launcher): claim, and the evidence against it>; ...
Judge overrides: <what, and the evidence> (or none)
Verified: <load-bearing claim: how checked>; ...
Unverified: <claim>; ...
```

## 5. Check

```bash
diff "$RUN/preflight.txt" <(git -C "$WS" status --porcelain 2>&1)
```

Expected differences: the deliverable, and the run root when it lives in the
repository. Anything else is a worker edit to report.

Report: the deliverable path (or, for Revise first, the open decision and
the proposed round); the roster actually used (letter, launcher, lane);
failures and exclusions; judge rankings and your overrides; the outcome;
judge independence; what remains unverified; and the run directory. Give
each panelist and judge one outcome: `folded`, `not-run`, `failed` or
`no-usable-output`, as defined in `delegate`'s Integrate and verify.
`folded` means its output entered the judging or synthesis, not that any of
it was adopted; the audit says what was.

## Fast lane

`judge: parent`, only on request: skip the seal and the external judge.
Write `judge/analysis.md` by the [judge](judge.md) prompt (its ground
rules, sections and three selection lines) before touching the deliverable;
then synthesize as in stage 4. Record `Judge independence: none (parent judged)`
in the audit and say so in the report.

## Resume

Run the status command, then resume at the first missing artifact:

| Present | Missing | Resume at |
| --- | --- | --- |
| `TASK.md`, `RUN.md` | `panel-1/` | Launch (stage 1). |
| `panel-1/` | some `.status` | Check processes. Rerun only confirmed-dead letters. |
| panel running or done | `parent/<L>.md` | Write it now. It is sealed only if no panel output has been read; if some has, record that in the ledger and move it to `unsealed/` so the packet leaves it out. |
| at least 2 usable external | `judge/<judge>.status` | Stage 3: run only the missing judges. |
| judge output | the audit in `RUN.md` | Stage 4: synthesize. |
| the audit | the report | Stage 5: check, then report. |

`hist sessions --workers` can recover Claude and Codex worker transcripts if
an `.out` is lost; other providers have only their `.out`.
