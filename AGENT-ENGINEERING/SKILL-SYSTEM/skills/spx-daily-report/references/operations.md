# Operations

## Environment and ownership

Requires `uv` and the active Options checkout at `~/repos/options` (override with `OPTIONS_REPO`). That project declares Python, numpy, scipy, yfinance, exchange-calendars and the `plots` extra. The launcher uses `uv run --project ... --extra plots`; the environment is resolved from the checkout rather than the agent's working directory. No global Python installs are needed.

The required storage API is `src/options_app/spx_report_store.py` in the Options repository. Its three public operations are `save_snapshot`, `load_snapshot` and `list_snapshots`. Do not copy or synchronize the implementation into the skill. If the module is absent on another machine, use an Options revision containing it before invoking this workflow.

Only the separate `data/spx_reports/` directory is used by default. Existing settlement OI databases, application configuration, saved portfolios and archived prototypes are untouched. No API server is needed.

## Commands

Run these relative to the skill directory, or use the absolute path to its launcher:

```bash
# Normal daily run; output paths are printed as JSON.
scripts/spx-daily-report collect --yfinance

# Core inputs only; explicit new report directory.
scripts/spx-daily-report collect --out /tmp/spx-new-report

# Offline replay; no provider calls.
scripts/spx-daily-report report --snapshot latest --out /tmp/spx-replay

# A known snapshot ID can replace "latest".
scripts/spx-daily-report export --snapshot latest --out /tmp/spx-input-export

# History queries never delete records.
scripts/spx-daily-report history --days 90
scripts/spx-daily-report history --all
```

To isolate a test store, use `scripts/spx-daily-report --db /tmp/spx-test.sqlite3 ...`. The database path option precedes the subcommand. Export writes original bytes as `cboe-marks.raw`, `occ-oi.raw`, and optional `yfinance-context.raw`, plus normalized snapshot and source metadata.

For archived raw files:

```bash
scripts/spx-daily-report --db /tmp/spx-test.sqlite3 import-files \
  --marks /path/to/saved-cboe.csv --oi /path/to/saved-occ.txt \
  --captured-at 2026-09-17T07:30:00+00:00 \
  --out /tmp/spx-imported-report
```

Use the files' **known original retrieval timestamp**, not the example timestamp. The historical import does not pretend to fill missing days. Replaying an old snapshot produces an explicit stale-reference warning when its date differs from the newest expected close.

Optional calculation inputs are `--target-expiry YYYY-MM-DD` and `--rate 0.04` (annual decimal). Default rate is zero and printed. Expiry must be an available SPXW series. OI dating can be supplied only as a pair: `--oi-asof YYYY-MM-DD --oi-date-evidence 'independent evidence and source'`. An asserted date is preserved as supplied metadata, not independently verified by the script.

## Finish a reader-facing report

`collect`, `import-files` and `report` produce the numerical baseline, not agent-written analysis. For a report-generation request, follow [interpretation guidance](interpretation.md) after the command succeeds: read that run's `analysis.json`, add the explanations to **both** its `report.html` and `report.md`, and inspect the resulting layout. Place the text with the relevant charts/tables, not only in a separate response or appendix. Label it as interpretation of the stated snapshot.

Edit only the newly generated report directory for this request. Preserve `analysis.json`, source files, numeric tables, SVG charts, timestamps, warnings and snapshot identifiers. Simple calculations used in the prose, such as a distance from spot to a flip, must be checked against that JSON. Do not change a model or regenerate prices to fit a narrative. Keep the HTML and Markdown explanations consistent. Offline replay into a **new** directory is the way to create a fresh copy from the same snapshot; the script does not retain previously agent-authored prose.

## Storage contract

A new SQLite store is marked with an application ID and schema version. Existing foreign databases or unknown versions are rejected, not migrated or overwritten. A single `BEGIN IMMEDIATE` transaction stores the snapshot, compressed source blobs and their links. SHA-256 identifies source bytes; raw blobs are deduplicated. Snapshot identity covers normalized inputs and raw source hashes while excluding retrieval-clock changes alone. Repeating the same inputs returns the original ID and first-capture time. Corrections create new snapshots.

Reads use SQLite read-only mode. A missing database is an error, not an empty history. Capture-time metadata is normalized to UTC for chronological ordering; original timestamps remain in the payload and source records. Back up the database with SQLite's backup API when a writer may be active; a filesystem copy is sufficient only while no writer is running. There is no automatic purge or migration command. The 90-day query window is relative to the newest stored **quote date**, measured in calendar days.

The report shows up to five recent distinct quote dates; the database retains the complete history. Historical replay excludes records captured after the selected snapshot, preventing newer revisions from appearing as information available earlier. Spot/IV/flip changes are descriptive: they are not automatically attributed to dealer flow.

## Failure handling

- **Stale Cboe file:** `collect` checks the expected trading-session close with a 30-minute publication allowance. Retry after publication if appropriate. `--allow-stale` explicitly permits historical capture; it does not remove the stale label. Holidays and early closes use the existing exchange-calendar helper.
- **Yahoo rate limit/missing symbol:** use the remaining labeled context or omit `--yfinance`. Do not add repeated aggressive retries or silently turn ES into a cash SPX quote.
- **Missing OI date:** normal for this source; preserve the caveat and continue with assumption-based analysis. Missing matched contracts are excluded from signed gamma, never zero-filled.
- **Changed CSV or OCC format:** stop and inspect the actual downloaded response. Fix and test the parser before declaring the new shape supported.
- **Output directory exists:** choose a new path. Reports are not overwritten. Default paths include a timestamp to avoid collisions.
- **Rendering failure after save:** use `report --snapshot <id>` to retry offline. Collection and report rendering are separate recoverable operations.
- **No digital probabilities:** raw call slopes sometimes violate convexity. The current version suppresses invalid tails rather than presenting a fabricated probability distribution. The separately labeled lognormal illustrations remain available.

## Validation

From the skill directory:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --project "$HOME/repos/options" --extra plots \
  python -m unittest discover -s tests -v
```

From the Options checkout:

```bash
uv run python -m pytest tests/test_spx_report_store.py -q
```

Use `OPTIONS_REPO`'s value in place of the default path if necessary. Tests cover the real closing-price fixture, finite-difference gamma, no-flip bounds, wider-gap coverage, settlement clocks, Yahoo failure handling, parsing, storage idempotence, rollback, retention, concurrent writers and wrong-database rejection. Skill-system validation and exact managed-install checks are separate packaging checks.
