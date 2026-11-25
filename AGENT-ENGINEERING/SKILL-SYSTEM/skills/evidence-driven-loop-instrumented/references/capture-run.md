# Capture Run

`scripts/capture_run.py` is a standard-library command wrapper for local,
non-interactive commands. It captures provenance and raw output without
attempting to parse task metrics or decide success.

## What it writes

Each invocation creates one unique directory under the explicit
`--records-dir`:

```text
<timestamp>-<label>-<id>/
├── started.json
├── stdout.txt
├── stderr.txt
└── receipt.json        # absent if the wrapper itself died before finalization
```

`started.json` records intent before the child starts. `receipt.json` records
argv, working directory, timestamps, duration, mechanical status, return code,
timeout state, output filenames, and optional artifact metadata. Output files
are streamed to disk rather than retained in memory.

The wrapper does not capture environment variables, parse a score, append to a
shared index, retry commands, or invoke a shell.

## Required arguments

- `--records-dir PATH`: exact parent for unique run directories.
- `--label TEXT`: short human identifier used in the directory slug.
- `--prediction TEXT`: expected observation stated before execution.
- `--success-condition TEXT`: what the run must emit or establish for the
  named experiment, still subject to agent inspection.
- `-- COMMAND ARG ...`: argv to execute; shell operators and expansion are not
  interpreted.

## Optional arguments

- `--cwd PATH`: child working directory; defaults to the caller's current
  directory.
- `--timeout SECONDS`: positive wall-clock limit. On timeout the wrapper sends
  termination to the child process group on POSIX, waits briefly, then kills
  the group if necessary. This cannot guarantee cancellation of detached
  grandchildren or remote work the command already submitted.
- `--artifact RELATIVE_PATH`: repeatable path relative to `--cwd`. The wrapper
  records missing files, file sizes and SHA-256 hashes, or directory presence
  after the command. Absolute paths and paths escaping `--cwd` are rejected
  before execution.

## Exit behavior

- On ordinary completion, the wrapper returns the child's exit code.
- A timeout returns `124` after writing a timed-out receipt.
- Local interruption returns `130` after attempting cleanup and writing an
  interrupted receipt.
- A spawn error returns `125` after writing a spawn-error receipt.
- Invalid wrapper arguments return `2` without executing the child.

Use the receipt path printed by the wrapper to locate evidence. A nonzero
wrapper exit may be an expected observation in the experiment; a zero exit may
still fail every task-level gate.

## Security and operational limits

The full argv, prediction, success condition, stdout, and stderr are persisted.
Do not place passwords, tokens, private data, or secret-bearing output in a
captured run. Prefer a task-specific redacted evaluator or skip capture.

The wrapper owns only the local child process it starts. It does not monitor a
submitted cluster job, hosted training run, service request, or detached
process after the local command returns. Record those systems' native job IDs
and lifecycle evidence separately.

Do not run destructive or externally mutating commands merely because the
wrapper can record them. Existing task authority and safety policy still
govern the command.
