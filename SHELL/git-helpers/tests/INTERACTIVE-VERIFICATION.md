# Verify the real `peek` terminal path

Run from `SHELL/git-helpers` with Python 3.10+, Git, fzf and tmux already
installed:

```bash
python3 -B tests/verify_peek_tui.py --helpers-dir . --root /tmp/peek-check-unique
```

Choose a **new, nonexistent** root each time. The helper creates three commits
in its own fixture repository, drives the real `navigation.py peek` and fzf,
and retains `evidence/` plus the fixture. No product checkout, shell profile or
personal tmux session is changed. Missing prerequisites or invalid input fail
with exit 2; nothing is installed. `--timeout` bounds each state wait (default
20 seconds, maximum 120).

## Path and evidence

| Claim | Action | Witness |
|---|---|---|
| Actual interactive branch, not the CLI fallback | Start in an owned tmux controlling terminal | Python foreground, source hashes/tool versions, real picker frame |
| Selection reaches changed content | Enter commit, then file | `src/task.py`, then two-hunk picker |
| Navigation and interruption recover | Escape back; Ctrl-C within file picker | Current commit-picker frame, followed by working input |
| Resize preserves operation | 100×30 → 132×40, then Down/Enter | Reported terminal geometry and subsequent file-picker transition |
| Read-only browser leaves Git untouched | Exit at top level | Equal index/worktree hashes, HEAD and `status -z` |
| Owned resources close | Return to shell, then close private tmux server's session | Shell response, absent owned session and no observed owned PIDs |

Each transition waits for a current rendered frame, not a raw transcript
substring or old scrollback. `transcript.raw` preserves the byte stream;
numbered captures preserve states; `summary.json`, `commands.log` and
`identity.json` retain outcomes and source/runtime identity. Failed runs keep
partial evidence and a failure capture. The fresh socket and empty tmux config
isolate the driver from existing sessions. Only resources it created are closed.

The October capability record
contains real-run evidence and the pilot's limits. Cleanup failure makes the
probe fail. After inspection, remove only the explicitly selected owned root
to remove retained fixture/evidence.

This supplements the existing non-interactive and mocked-picker tests. It does
not certify color/contrast or visual fidelity, `--dirs`, editor launch,
substring filtering, every preview key, another terminal emulator, or another
operating system. A replay drives the same operations again, not the same OS
schedule.
