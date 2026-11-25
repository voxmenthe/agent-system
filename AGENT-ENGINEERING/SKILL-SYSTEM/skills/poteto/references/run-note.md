# One run note

Use the task's existing note; otherwise use the entry's task-local `RUN.md`.
These are semantic fields, not a serialization schema or a new event store.
Omit irrelevant fields, but never infer missing authority, ownership, or proof.

## Retain across checkpoints

| Section | Facts needed for the next decision |
| --- | --- |
| Contract | Objective/criteria revision, mode, preserved contracts, authority and exact Git/PR destination, reserved choices, explanation setting, coordinator/leaf source identities |
| Frontier | Assess/implement/verify stage, current slice, design/acceptance pointer, first required check, blocker and next useful action |
| Work and proof | Baseline, branch/checkout, complete base/head/checkpoint IDs, unit dependencies, checks, separate review/acceptance results, actual runtime identity, durable proof and PR/explanation links |
| Decisions | Material keep/reject/revise outcomes and owner corrections with decisive evidence; retain rejected directions |
| Resume | Current execution owner/session and handoff/end evidence, owned resources/cleanup, pending external effects, safe replay boundary, spent and remaining bounds/backlog |

Count total work units, repair attempts, and child effort rather than only
successful PRs. Keep measurement limits explicit. Store raw logs where the
task already stores evidence and link them; do not copy private transcripts.

Before replacing the frontier, preserve the previous complete checkpoint in the
same note (or the task's existing versioned evidence). Read the saved note back.
This is a single-owner human/agent note, not a crash-safe transaction journal.
On ambiguous/truncated state, reconcile from Git, host and forge evidence or stop
the affected effects honestly.

## Short filled example (illustrative, not a run receipt)

**Contract:** offline capture inspection, criteria r2. Bounded autonomous,
maximum two units, two no-progress repairs, two open run-owned PRs. Existing
archive output preserved. Local edits/commits authorized; publication has no
grant yet. Explanations off. Sources recorded in the task's source manifest.

**Frontier:** verify unit 1, human-readable capture summary. Chose to reuse the
validated capture loader rather than parse raw JSON twice. First check: public
CLI rejects malformed capture and creates no archive. Brief and commands are
in `evidence/unit-1.md`.

**Work/proof:** branch `capture-summary`, task-owned checkout; exact base/head
IDs and invoked script path/hash in that evidence file. Unit 2 depends on unit
1's summary semantics. Builder checks passed; fresh acceptance pending, no PR.

**Decisions:** owner correction r2: missing-parent warnings must remain visible.
Earlier “count-only means complete” interpretation rejected. Evidence for that
old interpretation is invalid; ordinary archive proof remains useful.

**Resume:** previous executor explicitly handed off after saving this note.
No live processes; disposable outputs cleaned and evidence read back. One of
two units attempted, one unit remaining; zero repair attempts, zero open PRs.
Token usage unavailable; the work-unit bound is the enforceable total. No
pending external effects. Next: establish ownership, reconcile checkout/head,
then dispatch fresh verification; do not publish without a grant.

## Resume checks

1. Establish ended/handed-off ownership before mutation; age is not evidence.
2. Read contract, frontier, corrections/rejections, bounds and exact pointers.
3. Reconcile real branch/head, worktree changes, PR base/head/status, owned
   runtime resources, pending effects, and evidence accessibility.
4. Invalidate affected readiness after source, requirement, recipe or runtime
   changes. Query interrupted publication before retrying; uncertainty stops
   that write instead of creating another PR.
5. Resume the recorded next useful action under remaining bounds. Active native
   compaction and an explicitly started fresh session are distinct evidence;
   neither proves unattended restart.
