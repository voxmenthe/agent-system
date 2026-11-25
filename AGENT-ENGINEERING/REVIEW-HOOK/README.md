# Integrated Review System

This directory is the repository source of truth for the review-after-commit
system used by the Codex command-line agent, Kimi Code, and Antigravity. It
contains the shared runtime, deterministic Python scan, host adapters,
installation manager, policy, tests, and operating instructions.

The system is advisory. It observes successful commits and may ask the current
agent to review the exact committed range. It does not block a commit or edit
the repository being reviewed.

See [USAGE.md](USAGE.md) for normal use, installation, status, and rollback.

**Selected route, rechecked 2026-10-03:** Codex CLI `0.160.0` and its managed
bundle are current. A real isolated commit triggered delivery, canonical
`diff-review`, and the reviewer's private result command. Replayed/concurrent
Codex callbacks emit only once. Kimi Code and Antigravity have not been
re-proven on their current CLIs. Captured host CLI versions are recorded, not
enforced: the manager installs onto newer CLIs and `status` reports both
versions. The [host matrix](HOST-CAPABILITY-MATRIX.md) separates this proof
from the historical all-host results.

## Modes

The launchers support two review modes:

```bash
cdx --review-mode cadence
cdx --review-mode auto
```

The same choices work with `kimm` for Kimi Code and `agg` for Antigravity.

- **Cadence mode** requests a review after a configured number of successful
  commits.
- **Automatic mode** scans every successful committed range. It immediately
  requests a review when conservative Python evidence matches the checked-in
  policy and remains silent otherwise.
- Omitting the review option leaves the host unhooked.

There is no separate learning-only mode. Automatic mode is the live dogfood
behavior.

## Automatic outcome capture

During automatic-mode use, the system privately records:

- each exact range scanned, including silent nonmatches and scan failures;
- whether the selector requested a review;
- whether Codex, Kimi Code, or Antigravity delivered it; and
- whether the reviewing agent reported findings or no findings, including the
  finding count.

The reviewing agent records its result through a command included in the
review request. The user does not keep notes, label examples, collect groups,
choose evidence windows, export files, or send a handoff.

The private records contain stable identities rather than repository paths or
source bodies. They live outside the repository being reviewed. They show how
the automatic path behaves in real use, but they do not prove that silent
commits contained no defects.

## Component boundaries

| Component | Responsibility |
| --- | --- |
| Shared runtime | Observe successful commits, identify exact ranges, count cadence events, avoid duplicates |
| Review Scan | Read immutable Git content and produce bounded Python evidence |
| Automatic selection policy | Decide whether that evidence is strong enough to request a review |
| Canonical `diff-review` skill | Inspect the whole exact range and make contextual findings |
| Host adapters | Translate the shared request into each host's native lifecycle |
| Outcome store | Record scans, delivery, and reviewer results outside the target repository |
| Management command | Validate, install, inspect, activate, deactivate, and roll back |

The scan allocates review attention. It is not a quality score or a verdict.
The reviewer may honestly report no findings.

## Host behavior

- **Codex command-line agent:** captures state before a Bash tool call and can
  deliver review context immediately after a successful commit.
- **Kimi Code:** captures state before a Bash tool call and delivers at stop or
  before the next Bash command using its proven retry boundary.
- **Antigravity:** captures a workspace snapshot before an invocation and
  delivers a selected review at the next invocation. Its plugin may remain
  enabled because it returns immediately when no review mode was selected.

Kimi launch wrappers trust the current folder before starting. This avoids a
trust prompt, but it also permits repository-declared tool servers to load; see
the security note in [USAGE.md](USAGE.md#kimi-code-folder-trust).

## Validate and inspect

From this directory:

```bash
/usr/bin/python3 -B scripts/review_hook.py validate
/usr/bin/python3 -B scripts/review_hook.py status --all-hosts
/usr/bin/python3 -B scripts/review_hook.py outcome-status
```

Source validation does not prove that the live installations are current;
`status --all-hosts` checks those projections separately.

## Development checks

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
/opt/homebrew/bin/bash tests/test_shell_integration.sh
/opt/homebrew/bin/bash tests/test_kimi_launcher_trust.sh
```
