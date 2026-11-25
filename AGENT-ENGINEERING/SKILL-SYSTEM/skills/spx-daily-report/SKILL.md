---
name: spx-daily-report
description: Collect free Cboe SPX/SPXW closing marks and OCC open interest, retain snapshots, and generate a trading-focused report with skew-aware ranges, overnight gap stresses, and competing gamma views. Use when explicitly asked for this daily SPX workflow or its archived reports; not for trade execution, a live options feed, or another vendor's proprietary dealer positions.
disable-model-invocation: true
---

# SPX daily decision report

Improve the user's trading decisions first. Broader market understanding and research are secondary. Use several estimates and aggregations with specific caveats; unresolved dealer sign does not block useful analysis. Do not confuse matching a vendor's levels with verifying its positions.

## Run the complete workflow

The helper script `scripts/spx-daily-report` runs through the existing Options Python environment. It defaults to `~/repos/options`; set `OPTIONS_REPO` for another checkout. That checkout must contain `options_app.spx_report_store`. No API keys or paid services are required.

From this skill directory:

```bash
scripts/spx-daily-report collect --yfinance
scripts/spx-daily-report history --days 90
```

The first command downloads the two official files, stores their exact bytes and normalized snapshot, and emits paths to `report.html`, `report.md` and `analysis.json`. `--yfinance` adds best-effort SPX/VIX/ES context; omit it for Cboe/OCC-only operation. The default store is `data/spx_reports/history.sqlite3` **inside the Options checkout**, independent of the invocation directory. Report output goes next to it in dated directories. Existing report directories are never overwritten.

For a chosen output directory, use `collect --out /path/to/new-report`. Put the global `--db /path/to/store.sqlite3` **before** the subcommand to use a different store. For offline replay, original-file import, export, validation and troubleshooting, read [operations](references/operations.md).

## Read and interpret the output

1. Read the generated Markdown and the quality/source metadata in `analysis.json`. Confirm quote date, target expiry, OI-date status and missing coverage. Cboe closing indicative marks are not current executable options quotes. Default expiry is the first SPXW expiry still alive **at quote time**.
2. Lead with the decision map: concentrations worth watching, delta-range edges, and conditions that would change the interpretation. Explain whether the expiry scopes and inventory assumptions agree; do not merely recite every statistic.
3. Consult the wider overnight view, not only the central band. It includes 1%/5% delta wings, 1σ/2σ/3σ reference bands, seven gap stresses and two distribution charts. A valid newer SPX cash reference adds another location scenario. These are explicitly illustrative, not calibrated probabilities of the gap or fresh remaining variance.
4. Use the gamma-at-level table to distinguish price movement through a modeled root from new information about inventory. Compare target-expiry, 7-day, 30-day and 90-day scopes and the alternative sign fractions. “No root in scan” is valid. Never force a switch or infer direction solely from positive/negative gamma.
5. Finish with concise trading implications and the limitations that change those implications. Unverified OI dating, stale prices, scope disagreements and provider failures matter; generic disclaimer repetition does not. Do not fabricate an executable entry premium, a probability of profit or a validated trading edge.

For report-generation requests, read [chart interpretation and narrative guidance](references/interpretation.md) and **add data-specific explanations to the generated HTML and Markdown**, beside the gap-stress and competing-gamma sections. Explain how to read each display, highlight the most consequential features in this capture, and connect them to conditional trading implications. A table recap, generic definitions, or commentary only in the chat does not complete the report.

The helper script produces a deterministic numerical baseline: self-contained HTML with expandable detail and inline SVG charts, readable Markdown and machine-readable results. The agent then adds clearly labeled interpretation without changing calculated data, charts or provenance. Keep the report self-contained with no remote assets. Its four main sections can span more than four printed pages because the added distributions, tables and explanations are retained. Link the actual enriched report in the response.

## Data and ownership boundaries

- Only the published Cboe marking-price CSV and OCC batch download are core sources. Do not scrape the restricted delayed quote table, silently substitute SPY options, add paid/trial APIs, or invent historical files. [Source and calculation reference](references/methodology.md)
- Store **all** captured dates; the default 90-day history view is a query window, not a deletion policy. History initially contains only the collected dates. Repeating identical inputs is idempotent; changed input bytes produce a new immutable snapshot.
- Raw OCC series downloads do not establish an OI effective date. Leave it unverified unless independent evidence supports `--oi-asof` together with `--oi-date-evidence`. The capture date and quote date are not substitutes.
- Keep closing-range calculations and supplemental newer prices separate. Do not convert `ES=F` directly to cash SPX, mix contract rolls, or shorten the IV clock without a stated new model. The widening stress view preserves closing total variance on purpose.
- Core parser/download failures stop the run with a specific error. Optional Yahoo failures are reported and do not erase usable core data. A saved snapshot may remain available if rendering fails; replay it rather than redownloading.
- No trading orders, publishing, broker login, scheduler installation or edits to the Options UI/configuration are part of this skill. Run collection after the closing file is published, normally after 16:30 ET, or invoke it when needed. A requested recurring job can call the same command without changing the data model.

## Extend carefully

Read [methodology](references/methodology.md) before changing pricing, gamma signs, clocks, scopes or charts. The scripts own numerical results; narrative does not override them. Test changed formulas against the recorded price fixture and invariants, not against a desired vendor level. The database implementation remains in the active Options package, not in archived prototypes or a second skill-local copy.
