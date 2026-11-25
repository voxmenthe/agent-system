# Data, schema, and compatibility safety

## Applies when

Load this pack before changing database schemas, migrations, backfills, transaction boundaries, durable state, serialized or wire formats, event schemas, caches whose contents survive deployment, public compatibility contracts, or code that can corrupt, lose, duplicate, or irreversibly reinterpret data.

## Does not apply when

Do not load it for an in-memory-only model refactor whose external and persistent representations are unchanged. Load it when that assumption is uncertain.

## Non-negotiable rules

- Do not perform destructive data operations, drops, irreversible rewrites, unsafe backfills, persistent-format changes, or compatibility removals without explicit authorization, a tested recovery path, and a safer alternative considered first.
- Use coexistence or staged-rollout machinery only for a concrete data-integrity risk or supported compatibility obligation. Prefer direct replacement when old state can be recreated or completely migrated, or when no supported consumers remain. When staging is necessary, use the smallest mechanism that covers the risk and make its removal part of the migration.
- Compatibility is an explicit, time-bounded obligation; do not infer it from old code, public symbols, tests, or data formats alone. Temporary compatibility paths must identify what they protect, their exit criteria, and their deletion step. Remove them once those criteria are met.
- Treat data integrity and transaction semantics as higher priority than local elegance or brevity.
- Parse strictly, version explicitly, validate at boundaries, and reject malformed input with clear errors. Do not silently reinterpret old data.
- Make operations idempotent where retries or partial execution are possible. Record progress durably for resumable backfills.
- Never claim rollback is possible unless it has been designed and, where practical, exercised.

## Procedure

1. **Inventory the contract.** Identify producers, consumers, storage locations, versions, volume, retention, ownership, replication, transaction boundaries, and external clients.
2. **Classify reversibility.** Separate restart-fixable state from corruption, loss, duplication, or semantic reinterpretation. State the maximum acceptable blast radius.
3. **Choose the transition shape.** Determine whether direct replacement is safe. If coexistence is necessary, identify the concrete data or supported consumers requiring it, choose the smallest mechanism that covers that risk, and define cutover, verification, and removal criteria before adding it.
4. **Design required compatibility.** When supported producers or consumers require overlap, specify version negotiation, defaults for genuinely absent optional fields, rejection behavior for unknown or invalid data, and the support window.
5. **Design transactions and idempotence.** State which effects commit together, which can be retried, how duplicates are detected, and how partial failure is reconciled.
6. **Plan the backfill.** Bound batch size, rate, locking, load, checkpointing, retries, cancellation, resume behavior, and verification. Avoid unbounded scans or updates inside opaque loops.
7. **Add observability before execution.** Define counts, error categories, lag/progress, mismatch rates, checksums or reconciliation queries, and alerts. Include a dry run or read-only validation path.
8. **Plan recovery.** Choose rollback or roll-forward in proportion to the failure mode. Preserve old data only when it materially improves recovery. Backups are useful only when restoration time and procedure are understood.
9. **Test representative old and new data.** Include malformed, missing, duplicated, partially migrated, and concurrent cases. Test downgrade/rollback semantics when claimed.
10. **Require explicit authorization at the irreversible boundary.** Planning, additive preparation, tests, and dry runs may proceed; destructive execution does not.

## Done criteria

- Producers, consumers, versions, volume, ownership, and transaction boundaries are mapped.
- The transition is direct or staged according to the identified risk; when staged, it is observable, resumable, and idempotent where needed.
- Compatibility and malformed-input behavior are explicit and tested.
- Rollback or roll-forward is credible; any retained old data has a stated recovery purpose and deletion criterion.
- Destructive steps are isolated, clearly labeled, and not executed without authorization.
- Verification can detect loss, duplication, corruption, and semantic mismatch rather than merely command success.
