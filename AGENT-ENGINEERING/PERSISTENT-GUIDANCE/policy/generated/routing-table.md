# Generated routing table

> Generated from `policy/manifest.json`; do not edit manually.

| Pack | Read before | Applies to | Dependencies | Risk |
|---|---|---|---|---|
| [`memory`](policy/packs/memory.md) | session start / handoff | all primary sessions; prior context; durable notes; handoff maintenance | — | elevated |
| [`implementation`](policy/packs/implementation.md) | edit | production code/config/scripts; implementation or bug-fix work | — | normal |
| [`testing`](policy/packs/testing.md) | plan/edit | behavior changes, bugs, tests, contracts, migrations, concurrency | — | normal |
| [`architecture`](policy/packs/architecture.md) | plan | cross-module/public interface/new module/deep module/broad refactor/abstraction | `implementation`, `testing` | elevated |
| [`python`](policy/packs/python.md) | edit/execute | Python/pyproject/uv/pytest artifacts or commands | `implementation` | normal |
| [`git`](policy/packs/git.md) | git mutation | commit/rebase/reset/restore/delete/push/PR/diff coordination | — | high |
| [`docs`](policy/packs/docs.md) | edit | docs/README/setup/comments/docstrings/CLI help | — | normal |
| [`data-safety`](policy/packs/data-safety.md) | plan | schema/migration/backfill/persistence/transaction/wire format | `architecture`, `git` | high |
| [`concurrency`](policy/packs/concurrency.md) | plan | async/thread/process/lock/queue/worker/race/cancellation | `architecture`, `testing` | high |

Use semantic judgment to select packs from the requested work and discovered scope; do not route by keyword occurrence alone. Read each selected pack and its dependencies before the listed phase.
