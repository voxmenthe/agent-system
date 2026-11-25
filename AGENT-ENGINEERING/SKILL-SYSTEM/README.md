# Personal Skill System

This directory is the owner-controlled source and recovery boundary for the
personal agent skill system. It manages only explicitly declared names under
`~/.agents/skills`.

The design is deliberately small:

- `skills/` contains canonical custom skill sources.
- `registry.json` owns lifecycle, install targets, dependencies, effect
  ceilings, ownership, provenance, and evaluation profiles.
- `skill_system/` validates, reconciles, projects exact skills, refreshes
  eligible managed projections through one-skill transactions, and retains
  rollback material.
- `bin/skill-system` is the repository-local command. Nothing is added to shell
  startup or a global executable path.
- `schemas/` documents the versioned registry, install-state, and journal
  formats.
- `evaluations/` holds pre-canonical candidates, fresh-context scenarios and
  run records. It is gitignored: it stays on the working machine and is not
  published, so the references to it below are to local files.

Projection copies each validated skill directory into place rather than
linking it, for offline availability and the journaled rename and rollback
contract.

For ordinary use, start with the
[Personal Coding Skills User Guide](USER-GUIDE.md), or
[Poteto usage](POTETO-USAGE.md) for feature delivery and standalone verification
recipes.

## Availability is binary

A personal skill is **live** when its directory is under
`~/.agents/skills` and the runtime can discover it. A skill is **retired** when
it is absent from that live directory and cannot be selected.

The command named `quarantine` is only the reversible mechanism used to retire
a skill: it moves the exact directory to recovery storage and retains a
journal. That retained tree is a backup, not a third availability state and
not part of the live library. Permanent backup deletion is a separate retention
decision with no effect on whether the skill is available.

## Personal harness boundary

This system is the owner-controlled part of a personal agent harness, and it
follows this partition:

- keep general-purpose reasoning procedures out of the durable core when model
  behavior already provides them;
- keep last-mile intent, policy, authority, acceptance, and verification rules
  because they encode owner- and task-specific requirements;
- make skills state **what** must hold and how success is checked without
  micromanaging **how** the model reasons;
- keep private, highly specific, recent, and rapidly changing context in
  memory, repositories, and tool connections rather than copying it into every
  skill; and
- defer optional capabilities until routed, then retire wrappers that duplicate
  a model, policy pack, plugin, or deeper skill.

The working budget is about 20 live names under `~/.agents/skills`, including
the owned core and deliberately retained personal capability skills. It is a
design pressure, not authorization to retire a name. System and plugin
skills are a separate runtime inventory and should not be copied into this
owned core merely to make them locally visible.

## Backups and recovery floor

Every install, refresh and quarantine is a journaled one-skill transaction
that keeps what it displaced, so `rollback <operation_id>` can restore it.
Backups and transaction preimages are never pruned automatically. Do not
extract or copy a backup over `~/.agents`; restore an exact target only after
comparing the live path and choosing an explicit recovery operation.

## Command interface

Run commands from this directory:

```bash
bin/skill-system validate
bin/skill-system audit
bin/skill-system audit-codex
bin/skill-system status
bin/skill-system install frame-change --dry-run
bin/skill-system install frame-change --apply
bin/skill-system refresh --dry-run
bin/skill-system refresh --apply
bin/skill-system sync --dry-run
bin/skill-system sync --apply
bin/skill-system sync --force --dry-run
bin/skill-system sync --force --apply
bin/skill-system rollback <operation-id> --dry-run
bin/skill-system rollback <operation-id> --apply
bin/skill-system quarantine <exact-skill> --dry-run
bin/skill-system quarantine <exact-skill> --apply
bin/skill-system migrate-lock --dry-run
bin/skill-system migrate-lock --apply
bin/skill-system relocate --from <old checkout> --dry-run
bin/skill-system relocate --from <old checkout> --apply
bin/skill-system configure-antigravity --dry-run
bin/skill-system configure-antigravity --apply
bin/skill-system configure-claude --dry-run
bin/skill-system configure-claude --apply
bin/skill-system configure-mimo --dry-run
bin/skill-system configure-mimo --apply
bin/skill-system configure-grok --dry-run
bin/skill-system configure-grok --apply
bin/skill-system configure-grok --force --dry-run
bin/skill-system configure-grok --force --apply
```

Mutation commands default to dry run. `--apply` is required to write. `sync`
and the host adapters expose `--force` for their documented collision paths;
there is no blanket removal, global launcher, daemon, hook, or automatic
publication.

`sync` always installs `~/.agents/skills`, which every host reads. Its Claude,
MiMo and Grok stages run only for hosts that `~/.config/agent-system/machine.json`
enables (`claude`, `mimo`, `grok`, `grok2`, `grok3`), and for all of them when that
file is absent; a skipped stage reports `host-disabled`. The `configure-*`
commands always act, since they name their host.

`audit-codex` is a separate read-only check of `<home>/.codex/skills`, including
root and hidden/nested declarations. It exits 1 for personal declarations or
unresolved discovery-capable symlinks, 2 for inspection errors, and 0 when no
personal discrepancy is found. It reports non-skill files without treating them
as skills. The direct `.system` entry is a provider-owned exception, not a
validated personal package. It does not traverse symlink targets, scan plugin
caches, change install state, or remove anything. Use it alongside `audit` and
`status`; a passing canonical audit alone does not cover this host-local surface.

`--root` and `--home` support isolated fixtures:

```bash
bin/skill-system \
  --root /path/to/canonical-copy \
  --home /tmp/isolated-home \
  install frame-change --apply
```

Command output is JSON. Expected contract failures use exit status 2 and write
the reason to standard error.

### Antigravity CLI discovery

Antigravity CLI uses a separate global discovery configuration and does not
discover the managed `~/.agents/skills` projection by default. Configure the
bridge once after installing `agy`:

```bash
bin/skill-system configure-antigravity --dry-run
bin/skill-system configure-antigravity --apply
```

The command creates `~/.gemini/config/skills.json` with the resolved absolute
path of the existing shared projection. It does not copy skills or add a second
install target, so later installs and refreshes remain owned by the existing
journaled workflow. The absolute path is intentional: Antigravity CLI `1.1.15`
rejects the documented `~/` form as non-absolute. If the configuration already
declares the resolved shared directory, the command is a no-op. If the path
already contains different or malformed data, the command fails without
overwriting it.

To undo the bridge, remove only that generated `skills.json`, and only while it
still contains no owner-added entries. The shared skill directories are
unaffected; this host configuration is outside the journaled skill rollback.

The 2026-08-19 live probe found all 51 direct skill directories under the
shared root in `agy /skills`, with no missing or unexpected shared paths.

### MiMo Desktop projection

MiMo Desktop does not scan `~/.agents/skills` or `~/.claude/skills`. It
discovers global skills from `~/.config/mimocode/skills/<id>/SKILL.md` and
prefers real directory copies over symlinks. After the shared install is
current, project active skills into that layout:

```bash
bin/skill-system configure-mimo --dry-run
bin/skill-system configure-mimo --apply
```

The applied command copies each active shared skill, writes
`locales/en-US.json` and `locales/zh-CN.json` display metadata derived from
`agents/openai.yaml`, and records a `.mimo-projection.json` source-hash
marker. `sync --apply` reruns this projection after the Claude stage. Restart
MiMo Desktop or start a new conversation so newly copied skills load.

### Grok-only projection

`configure-grok` links the immediate skill directories in `grok-skills/` into
`~/.grok/skills`, `~/.grok2/skills` and `~/.grok3/skills`. Source edits are immediately visible
through the links. Existing colliding entries require `--force` and are retained
outside discovery, never deleted. `sync` runs this stage after Claude and MiMo.
Account authentication and settings remain separate. Read the
[Grok catalog and recovery contract](grok-skills/README.md) before adoption.

### Read-only commands

- `validate` reads canonical registry and custom sources only. It does not use
  live skill content to decide whether a source is valid.
- `validate` and `audit` also check native Grok package envelopes and report
  their source hashes separately under `grok_skills`.
- `audit` adds strict parsing of current install state.
- `status` reconciles canonical hashes, install state, and live target hashes.
  Its separate `grok` map reports `current`, `absent`, or `unmanaged-collision`
  for each native skill in each Grok home.

Important status values include:

- `absent`;
- `current`;
- `source-updated`;
- `locally-modified`;
- `unmanaged-collision`;
- `legacy-current`, `legacy-modified`, or `legacy-absent`; and
- `external-present` or `external-absent`.

An existing custom target without a matching managed state entry is reported as
an unmanaged collision and is never overwritten.

## Install, refresh, and rollback contract

Each install manages exactly one `custom` registry record:

1. take a non-blocking process-scoped advisory lock;
2. strictly validate canonical source, registry, state, and prior journals;
3. refuse unmanaged targets and locally modified managed targets;
4. copy and validate a staged tree on the target filesystem;
5. durably record the operation and retain state/target preimages;
6. use same-filesystem renames for the visible directory transition;
7. validate the installed hash;
8. atomically replace install state; and
9. retain the journal and preimages for explicit rollback.

Canonical trees reject symlinks and special files. Content hashes include
sorted relative paths, file bytes, file types, and mode bits.

### Managed refresh

`refresh` reconciles the complete registry and live state before selecting any
work. Its only candidates are already-managed, installable `custom` skills in
`source-updated` state. It reports every other registry name under an exclusion
reason such as `current`, `absent`, `locally-modified`,
`unmanaged-collision`, or `lifecycle-retired`; it never installs or adopts
those names.

Dry run is the default. With `--apply`, refresh holds one exclusive advisory
lock, verifies that every candidate can use the documented same-filesystem
transaction path before the first write, and then processes candidates in
sorted order. Each candidate remains a separate install operation with its own
journal, preimage, state commit, operation ID, and rollback path.

Refresh is therefore recoverable and idempotent, but not globally atomic. If it
stops after some child installs commit, those installs remain committed. Run
`status`; explicitly roll back any named incomplete child operation; then rerun
`refresh --apply` to reconcile the remaining `source-updated` skills.

### Managed sync

`sync` is the one command that reconciles the full set of installable `custom`
skills against canonical sources. It installs `absent` skills, refreshes
`source-updated` ones, and reports every other registry name under an exclusion
reason. `sync` never removes skills; removal is a separate quarantine step.

`unmanaged-collision` and `locally-modified` skills are reported as exclusions
(warnings) by default. With `--force`, they become candidates and canonical
content wins: the displaced live content is retained as a preimage so each
adoption is individually rollback-able. Without `--force`, those targets are
left untouched.

Dry run is the default. With `--apply`, sync holds one exclusive advisory lock,
preflights the same-filesystem transaction path for every candidate before the
first write, and then processes candidates in sorted order with install
candidates before force candidates. Each candidate is a separate install
operation with its own journal, preimage, state commit, operation ID, and
rollback path — the same crash model and per-skill recovery as `refresh`.

### Moved checkout

The install state records each managed skill's source as an absolute path, and
Grok skills are links into the checkout. After the checkout moves (for example
from the old monorepo to its own repository), `status` and `sync` stop with
"source path disagrees". `relocate --from <old SKILL-SYSTEM directory>` rewrites
those source paths and relinks the Grok skills to this checkout. It changes
only entries that name the old checkout, and it refuses, before any write, a
state entry that names neither checkout. `--from` may be a link to the old
location, and the old checkout may already be gone.

The rewritten state is validated before the write. The previous state file is
kept as `install-state.before-relocate-<time>.json` beside it, and each link is
replaced atomically. Relocate is not journaled: after an interruption, run it
again. It resumes with the remaining links and reports `already-current` once
nothing names the old checkout.

### Crash model

The implementation does not claim that a multi-file transaction is universally
atomic. It provides these narrower guarantees:

- journal phase changes, staged file content, relevant parent directories, and
  state replacements are flushed before the next visible phase;
- install and quarantine renames are refused across filesystems;
- only one mutating command runs at a time within this tool;
- a lingering lock file is not mistaken for lock ownership;
- after a stop inside an install, quarantine, lock migration, or rollback, the
  next mutation stops and names the incomplete operation (a rollback journals
  `rolling-back` before its first change);
- rollback verifies retained/current hashes before moving anything, and a
  refused rollback changes nothing;
- rollback decides what to undo from the disk (the staged, preimage, and
  moved-aside trees, or the lock's hash), not from the last journaled phase,
  so it recovers a stop between a rename and its journal write, and repeating
  an interrupted rollback resumes it;
- rollback restores only its own skill's install-state entry, so operations on
  different skills can be rolled back in any order; and
- rollback is LIFO per affected path, so an older operation cannot cross a
  newer committed install, quarantine, or lock migration.

After process or host failure, run `status`, inspect the named journal under
`~/.agents/.skill-system/transactions/`, and use an explicit rollback. Storage
hardware, filesystem, or operating-system failures outside the documented
flush/rename model may still require restoring from the frozen snapshot.

## Ownership boundaries

### Custom

`custom` records have canonical sources and may be projected only after full
validation. An effect ceiling describes the most consequential behavior the
skill may propose; it is not authorization. For example, `git-mutation` still
requires the task and policy kernel to authorize the exact Git action.

### Legacy unmanaged

`legacy-unmanaged` records are frozen audit evidence. The installer cannot
project or overwrite them. Their observed snapshot hashes make drift visible.
Conversion requires a separately reviewed quarantine of the live legacy
directory before a custom replacement can use that runtime name. In user-facing
terms, the legacy skill is retired before the replacement becomes live.

### External

No external skill records remain.

## Adding or changing a custom skill

1. Start with a concrete, bounded responsibility and both positive and negative
   trigger cases.
2. Stage any unapproved draft under
   `evaluations/candidates/<name>/`, outside the strict canonical `skills/`
   directory and every live discovery root.
3. Initialize the candidate with the built-in `skill-creator` tooling, explicitly
   targeting `AGENT-ENGINEERING/SKILL-SYSTEM/evaluations/candidates/<name>/`
   from the repository root. Do not accept an authoring or installer tool's
   default `~/.codex/skills` destination for owner-controlled personal skills.
4. Keep procedure in `SKILL.md` and runtime UI metadata in
   `agents/openai.yaml`. The optional `disable-model-invocation: true`
   frontmatter key keeps a skill user-invoked only on Grok and Kimi; pair it
   with `allow_implicit_invocation: false` for the same effect on Codex.
   Canonical validation rejects mismatches in either direction, treating an
   omitted key as model invocation enabled for its host.
5. After approval, move the candidate to `skills/<name>/` and add one strict
   `custom` record to `registry.json` in the same reviewed change. Never leave
   an unregistered directory under `skills/`.
6. Declare dependencies and the narrowest honest effect ceiling.
7. Add focused structural and behavior assertions.
8. Run the built-in validator and this repository's validation/tests.
9. Use an isolated fake home before any real projection.
10. Dry-run one exact install, inspect paths/hashes, then apply only if intended.

Do not encode slash-command calls to other skills. Composition remains a
routing decision, not a hidden mandatory chain.

## Evaluation

Fresh-context cases live in
evaluations/scenarios/release-1.json.
Expected routing is evaluator data and must never be sent to the fresh context.
A routing-only calibration may use one constant wrapper for every case, with
the `prompt` field inserted only as the request payload. This is classification
evidence, not a substitute for an executable fixture or a real-task result.
When the prompt describes executable work, either provide an isolated fixture
that actually contains that work or record the run as routing-only.

Record only meaningful, sanitized experiments using
evaluations/runs/README.md. Invocation counts,
commits, generated lines, and pull-request volume are not primary success
measures.

## Validation

Focused tests use only temporary fake homes:

```bash
python3 -m unittest discover -s tests -v
```

They cover strict source/registry/state/journal parsing, dry-run byte
preservation, idempotence, managed-only refresh selection, whole-candidate
preflight, partial refresh recovery, collisions, local edits, same-filesystem
refusal, deterministic lock contention, crash phases, rollback, quarantine,
exact lock migration behavior, and collision-safe Antigravity discovery setup.

The runtime uses only the Python standard library. The JSON Schemas are
versioned interoperability artifacts; the dependency-free runtime performs the
same load-bearing checks directly and rejects unknown versions and fields.
