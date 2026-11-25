# Debug: Add Targeted Instrumentation

Instrument before editing logic.

## Actions
1) **Define invariants** for the suspected code (what must be true at entry/exit).
2) Add structured logging at:
   - Function boundaries (args, return values, elapsed time).
   - Branch points (which path taken, key predicates).
   - External boundaries (I/O, API calls, DB queries).
3) Gate logs behind a single env flag (e.g., `DEBUG_TRACE=1`) and include a unique `trace_id`.
4) Add **assertions** for invariants with actionable messages.
5) **Re-run** the scenario once normally and once with max verbosity. Collect and summarize diffs.

## Deliverables
- Minimal diff that adds logs/asserts.
- A short log excerpt that narrows the fault to a specific branch or value.
- A proposed patch or next experiment informed by the logs.

## Additional Context (Optional)
$ARGUMENTS