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

Bill inputs: `bash -c 'source ~/.bash_agents >/dev/null 2>&1; usage'`.

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
  printf 'CONSTRAINTS: Work alone; other models answer the same task. Do not name your model, vendor, tools, or any task id. Do not edit files, commit, or delegate.\n'
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

Only now may you check status or read anything under `panel-*/`.

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
judges=(caxb)                                  # the default, or every named judge
for j in "${judges[@]}"; do
  ( cd "$WS" && "$DELEGATE/run-worker.sh" "$j" --task-file "$RUN/judge/packet.md" \
      >"$RUN/judge/$j.out" 2>"$RUN/judge/$j.stderr"; echo $? >"$RUN/judge/$j.status" ) &
done; wait
for j in "${judges[@]}"; do
  echo "== $j exit $(cat "$RUN/judge/$j.status")"
  grep -E '^(RANKING|BASE|DELTAS):' "$RUN/judge/$j.out" || echo "$j: missing selection lines"
done
```

## 4. Synthesize

No commands. Write the deliverable, then close the ledger by appending the
audit after its last line:

```markdown
## Audit

Base: <letter> (<launcher>, <lane>); judges: <judge: RANKING / BASE each>
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
