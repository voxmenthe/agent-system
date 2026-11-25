# Integrated Review System Usage

This is the operating guide for the repository-owned review-after-commit
system used by the Codex command-line agent, Kimi Code, and Antigravity.

Run management commands from this directory:

```bash
cd AGENT-ENGINEERING/REVIEW-HOOK    # from the checkout root
```

## Installed system

The three host integrations and the shared `diff-review` skill are installed
as managed, reversible copies of this repository source. Antigravity's plugin
is enabled and remains dormant unless a launch explicitly selects review mode.
Kimi Code launch wrappers trust the current folder by default.

Rechecked on 2026-10-03: Codex `0.160.0` matches the current repository bundle.
The exact bundle passed a real isolated host commit → delivery → reviewer
response → private outcome round-trip. The selected profile was created by the
manager; the raw headless probe explicitly enabled hook trust with
`--dangerously-bypass-hook-trust`. Ordinary interactive launches still use the
host's trust behavior. This is not a claim that every launch configuration
has been exercised.

Kimi Code and Antigravity adapters were captured against `0.39.1` and `1.1.22`.
The manager records those versions but does not require them, so installation
proceeds on current binaries, and `status` reports captured and actual versions.
Neither host has been re-proven end to end on its current binary. Do not treat
the August all-host proof as current compatibility. See the
[dated host matrix](HOST-CAPABILITY-MATRIX.md).

Check current state instead of relying on an old status claim:

```bash
/usr/bin/python3 -B scripts/review_hook.py validate
/usr/bin/python3 -B scripts/review_hook.py status --all-hosts

cd ../SKILL-SYSTEM
bin/skill-system status
```

`validate` checks repository source and that each host CLI reports a version. It does not
prove that installed files match. `status --all-hosts` compares each live
installation with current source.

Open a new shell after launcher changes. Existing host processes are
intentionally unaffected.

## Everyday launches

### No review hook

```bash
cdx
kimm
agg
```

The wrappers clear inherited review settings before a normal launch, so an
earlier selected shell cannot accidentally enable the hook.

### Automatic review

```bash
cdx  --review-mode auto
kimm --review-mode auto
agg  --review-mode auto
```

Automatic mode scans every successful committed range. A conservative Python
match immediately asks the current agent to review that exact range. A
nonmatch remains silent.

This is the live dogfood mode. There is no separate learning-only mode and no
activation gate. Do not add cadence intervals to an automatic launch.

### Scheduled review

```bash
cdx  --review-mode cadence
kimm --review-mode cadence
agg  --review-mode cadence
```

Scheduled review defaults to every successful commit on the standard branch.
Positive integer intervals may be supplied:

```bash
cdx --review-mode cadence --review-standard-every 3
kimm --review-mode cadence --review-branch-every 5
agg --review-mode cadence --review-standard-every 2 --review-branch-every 5
```

The available interval options are:

```text
--review-standard-every N
--review-branch-every N
```

The older spelling remains a cadence alias at the existing launcher boundary:

```bash
cdx --hook review-after-commit
kimm --hook review-after-commit
agg --hook review-after-commit
```

Do not combine the older spelling with `--review-mode`. Duplicate modes,
unsupported modes, zero or negative intervals, non-numeric intervals, and
cadence intervals in automatic mode fail before the host starts. `--` ends
wrapper parsing.

Host constraints:

- Codex review selection cannot be combined with a separately selected Codex
  profile.
- Kimi Code review selection is for its interactive wrapper path and cannot be
  combined with `-p` or `--prompt`.
- Antigravity can use review selection in interactive or print mode.

## What happens after a commit

The hook identifies the exact immutable Git range created by a successful
commit command. It then either applies the scheduled counter or runs the
automatic Python scan.

When review is due, the host gives the canonical `diff-review` skill a compact,
read-only request. The reviewer inspects the whole exact range and may report
findings or an honest no-finding result. The scan is attention context, not a
quality score or a verdict.

Codex consumes each processed tool event once, including concurrent callbacks;
sequential replay is silent and does not advance counters or duplicate private
outcomes. This is at-most-once consumption, not exactly-once delivery across a
process crash between recording the event and emitting its prompt. The other
hosts retain their existing retry-driven delivery behavior.

The system does not:

- block `git commit`;
- edit the reviewed repository;
- run project tests automatically;
- declare that a silent commit is defect-free; or
- treat complexity counts as defects by themselves.

## Automatic evidence requires no user work

For every successful commit event in automatic mode, the system privately
records the scan, selection decision, and any host delivery. A delivered
review includes a private result command. The reviewing agent runs it once
with the number of findings before replying; zero means no findings.

The user does **not**:

- keep notes or a review diary;
- copy event identities;
- label examples or assemble comparison groups;
- choose an evidence window;
- export records;
- report follow-up commits; or
- hand results back to the assistant.

The assistant can inspect aggregate behavior directly:

```bash
/usr/bin/python3 -B scripts/review_hook.py outcome-status
```

That summary includes scan counts, Python-changing scans, selected reviews,
delivery by host, missing reviewer results, findings, no findings, and scan
failures.

These records show the yield and reliability of selected reviews. They do not
measure defects missed in silent events, because ordinary dogfooding does not
independently review every silent event.

## Kimi Code folder trust

The live Kimi Code wrappers create Kimi Code's normal trust record for the
current folder before launch. This implements default folder trust for `kimm`,
`kimh`, `kiml`, `kimb`, and `kimbs`. Running the raw `kimi` executable keeps
Kimi Code's ordinary trust prompt.

Folder trust permits tool servers declared by that repository to start. In
plain language, an untrusted repository may name local commands or remote
services that Kimi Code loads as tools. Inspect those declarations before
opening untrusted code with a wrapper.

The wrapper refuses to replace a malformed or unexpected existing trust
record. This setting does not change Codex or Antigravity.

## Manual review tools

The shared skills also work without commit hooks:

- `diff-review` reviews a concrete working tree, commit, range, branch, or pull
  request;
- `verify-change` independently checks a completed change;
- `simplify-review` looks for removable retained complexity in one concrete
  change; and
- `simplify-audit` performs an explicitly requested repository-wide
  simplification audit.

## Run the deterministic scan directly

Resolve both boundaries to full committed Git identities, then scan the fixed
range:

```bash
BASE_COMMIT=$(git -C /absolute/repository rev-parse HEAD^)
HEAD_COMMIT=$(git -C /absolute/repository rev-parse HEAD)

/usr/bin/python3 -B scripts/review_hook.py scan \
  --repo /absolute/repository \
  --base "$BASE_COMMIT" \
  --head "$HEAD_COMMIT" \
  --full \
  --format json
```

The scan reads committed Git content and uses the bundled Ruff checker plus
the checked-in hook policy. Its output is bounded reviewer evidence.

## Management commands

Management operations are previews unless `--apply` is present.

### Validate and inspect

```bash
/usr/bin/python3 -B scripts/review_hook.py validate
/usr/bin/python3 -B scripts/review_hook.py validate \
  --host codex --host kimi --host antigravity
/usr/bin/python3 -B scripts/review_hook.py status --all-hosts
/usr/bin/python3 -B scripts/review_hook.py outcome-status
```

Important installation status values:

| Status | Meaning |
| --- | --- |
| `current` | Installed managed files match repository source. |
| `installed-disabled` | Antigravity is installed and registered but switched off. |
| `absent` | No managed installation exists. |
| `stale` or `stale-disabled` | A recognized managed installation needs a refresh. |
| `locally-modified`, `unrecognized`, `contract-incompatible`, or `broken` | Stop; the manager cannot safely prove what it would replace. |

### Install or refresh

Preview each exact host:

```bash
/usr/bin/python3 -B scripts/review_hook.py install --host codex
/usr/bin/python3 -B scripts/review_hook.py install --host kimi
/usr/bin/python3 -B scripts/review_hook.py install --host antigravity
```

Apply after reviewing the preview:

```bash
/usr/bin/python3 -B scripts/review_hook.py install --host codex --apply
/usr/bin/python3 -B scripts/review_hook.py install --host kimi --apply
/usr/bin/python3 -B scripts/review_hook.py install --host antigravity --apply
```

Antigravity installation is disabled-first. Its switch is a separate,
reversible action:

```bash
/usr/bin/python3 -B scripts/review_hook.py activate-antigravity
/usr/bin/python3 -B scripts/review_hook.py activate-antigravity --apply

/usr/bin/python3 -B scripts/review_hook.py deactivate-antigravity
/usr/bin/python3 -B scripts/review_hook.py deactivate-antigravity --apply
```

Activation changes only this plugin's enabled setting and records recovery
information. It does not change ordinary unselected launches.

### Selected Codex and Kimi Code homes

Launchers normally create their selected profile or hook configuration. The
underlying recovery commands are:

```bash
/usr/bin/python3 -B scripts/review_hook.py materialize-profile \
  --canonical-home /absolute/canonical-codex-home \
  --selected-home /absolute/selected-codex-home

/usr/bin/python3 -B scripts/review_hook.py rollback-profile \
  --selected-home /absolute/selected-codex-home
```

```bash
/usr/bin/python3 -B scripts/review_hook.py materialize-kimi-config \
  --canonical-config /absolute/canonical/config.toml \
  --selected-home /absolute/selected-kimi-home \
  --desired-config /absolute/generated/config.toml

/usr/bin/python3 -B scripts/review_hook.py rollback-kimi-config \
  --selected-home /absolute/selected-kimi-home
```

Add `--apply` only for the intended write. Do not hand-edit ownership receipts.

### Roll back

Preview first:

```bash
/usr/bin/python3 -B scripts/review_hook.py rollback --host codex
/usr/bin/python3 -B scripts/review_hook.py rollback --host kimi
/usr/bin/python3 -B scripts/review_hook.py rollback --host antigravity
```

For Codex or Kimi Code, restore each selected profile or configuration while
the managed installation is still present, restore the launcher preimage, and
only then apply the host rollback. Deactivate Antigravity before rolling back
its files. Follow recorded receipts; do not replace this order with manual
deletion.

## Private state and recovery material

Installer releases, backups, locks, and receipts live under:

```text
<canonical-host-home>/.review-after-commit-installer/
```

Scheduled counters and per-host delivery state live under:

```text
<selected-host-home>/hook-state/review-after-commit/
```

Automatic scan, delivery, and reviewer results default to:

```text
${REVIEW_AFTER_COMMIT_OUTCOME_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/review-after-commit}/repositories/<private-repository-identity>/outcomes.jsonl
```

The current scheduled-counter reader is strict: it accepts the current fields
and rejects unknown older shapes instead of guessing or rewriting them. In
plain language, old counter files are left untouched and a newly selected home
starts fresh. This is a saved-file rule, not a release-number system for the
hook, Codex, Kimi Code, or Antigravity.

The automatic outcome store likewise has one current shape. The replaced
learning-only store contained no live event records, so no compatibility
reader, duplicate writer, or migration machinery is retained.

## Development verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
/opt/homebrew/bin/bash tests/test_shell_integration.sh
/opt/homebrew/bin/bash tests/test_kimi_launcher_trust.sh
```

Repository tests use fixtures and disposable homes. Claims about actual host
installation require the separate live status and smoke evidence in
[HOST-CAPABILITY-MATRIX.md](HOST-CAPABILITY-MATRIX.md).
