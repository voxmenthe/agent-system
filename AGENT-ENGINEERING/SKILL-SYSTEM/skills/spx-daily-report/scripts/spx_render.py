"""Self-contained, printable trading brief with source clocks and model comparisons."""

from __future__ import annotations

import html
import io

MODEL_LABELS = {
    "calls_long_puts_short": "Calls + / puts −",
    "half_calls_long_puts_short": "Half calls + / puts −",
    "calls_long_half_puts_short": "Calls + / half puts −",
    "all_short_bound": "All short (bound)",
    "all_long_bound": "All long (bound)",
}


def fmt(value: float | None, digits: int = 1) -> str:
    return "unavailable" if value is None else f"{value:,.{digits}f}"


def table(headers: list[str], rows: list[list[object]]) -> str:
    def escape(x: object) -> str:
        return str(x).replace("|", "\\|").replace("\n", " ")

    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(escape(v) for v in row) + " |" for row in rows],
        ]
    )


def _html_table(headers: list[str], rows: list[list[object]]) -> str:
    return (
        '<div class="table-scroll"><table><thead><tr>'
        + "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def _plots(analysis: dict) -> tuple[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none"}
    )
    fig, ax = plt.subplots(figsize=(10.5, 3.6), layout="constrained")
    for p in analysis["profiles"]:
        if p["model"] == "calls_long_puts_short":
            ax.plot(analysis["grid"], p["curve"], label=p["scope"], linewidth=2)
    ax.axhline(0, color="#67798b", linewidth=0.8)
    ax.axvline(analysis["spot"], color="#15283b", linestyle=":", label="Closing SPX")
    ax.set(
        xlabel="Hypothetical SPX (frozen strike volatility / OI)",
        ylabel="$bn per 1% move",
        title="Conventional sign model · expiry coverage changes the answer",
    )
    ax.legend(ncol=5, loc="upper left", frameon=False)
    ax.grid(alpha=0.15)
    output = io.StringIO()
    fig.savefig(output, format="svg")
    plt.close(fig)
    gamma_svg = output.getvalue().split("<svg", 1)[1]
    nodes = sorted(
        analysis["concentrations"].get("target", [])[:10], key=lambda n: n["strike"]
    )
    fig, ax = plt.subplots(figsize=(10.5, 3.6), layout="constrained")
    xs = list(range(len(nodes)))
    ax.bar(
        [x - 0.2 for x in xs],
        [n["call_gex_bn"] for n in nodes],
        width=0.4,
        label="Calls · unsigned",
        color="#0c827c",
    )
    ax.bar(
        [x + 0.2 for x in xs],
        [n["put_gex_bn"] for n in nodes],
        width=0.4,
        label="Puts · unsigned",
        color="#b34d79",
    )
    ax.set_xticks(xs, [fmt(n["strike"], 0) for n in nodes])
    ax.set(
        ylabel="$bn per 1% move",
        xlabel="Strike",
        title="Target-expiry convexity concentrations · ownership unknown",
    )
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.15)
    output = io.StringIO()
    fig.savefig(output, format="svg")
    plt.close(fig)
    return "<svg" + gamma_svg, "<svg" + output.getvalue().split("<svg", 1)[1]


def _distribution_plots(analysis: dict) -> tuple[str, str]:
    import matplotlib.pyplot as plt

    distribution = analysis["distributions"]
    fig, ax = plt.subplots(figsize=(10.5, 3.6), layout="constrained")
    labels = {
        "Closing forward",
        "-2.0% gap stress",
        "-1.0% gap stress",
        "+1.0% gap stress",
        "+2.0% gap stress",
        "Newer cash-price location scenario",
    }
    for curve in distribution["densities"]:
        if curve["label"] in labels:
            ax.plot(
                distribution["grid"],
                curve["density"],
                label=curve["label"],
                linewidth=2 if curve["label"] == "Closing forward" else 1.2,
            )
    ax.set(
        xlabel="Illustrative expiry SPX",
        ylabel="Probability density / point",
        title="Wider outcome view · shifted locations, unchanged closing variance",
    )
    ax.legend(fontsize=8, ncol=2, frameon=False)
    ax.grid(alpha=0.15)
    output = io.StringIO()
    fig.savefig(output, format="svg")
    plt.close(fig)
    density = "<svg" + output.getvalue().split("<svg", 1)[1]
    scenarios = distribution["scenarios"]
    fig, ax = plt.subplots(figsize=(10.5, 4), layout="constrained")
    for i, scenario in enumerate(scenarios):
        ax.plot(
            [scenario["low_3sigma"], scenario["high_3sigma"]],
            [i, i],
            color="#a7cbd0",
            linewidth=4,
        )
        ax.plot(
            [scenario["low_1sigma"], scenario["high_1sigma"]],
            [i, i],
            color="#0c827c",
            linewidth=9,
        )
        ax.plot(scenario["forward"], i, "|", color="#172a42", markersize=14)
    ax.set_yticks(range(len(scenarios)), [s["label"] for s in scenarios])
    ax.axvline(analysis["spot"], color="#172a42", linestyle=":", linewidth=1)
    ax.set(
        xlabel="Illustrative expiry SPX · thick: ±1 log-σ; thin: ±3 log-σ",
        title="Overnight gap stress map · no probabilities assigned to the gaps",
    )
    ax.grid(axis="x", alpha=0.15)
    output = io.StringIO()
    fig.savefig(output, format="svg")
    plt.close(fig)
    return density, "<svg" + output.getvalue().split("<svg", 1)[1]


def build_report(
    snapshot: dict, analysis: dict, snapshot_id: str, history: dict, *, stale: bool
) -> tuple[str, str]:
    a = analysis
    quote_at = snapshot["quote_at"]
    conventional = [p for p in a["profiles"] if p["model"] == "calls_long_puts_short"]
    signs = {
        1 if p["gex_bn_per_1pct"] > 0 else -1 if p["gex_bn_per_1pct"] < 0 else 0
        for p in conventional
    }
    regime = (
        "At closing spot: expiry scopes disagree"
        if len(signs) > 1
        else "At closing spot: conventional gamma positive"
        if signs == {1}
        else "At closing spot: conventional gamma negative"
        if signs == {-1}
        else "No usable OI regime"
    )
    nodes = a["concentrations"].get("target", [])
    nearby = [n for n in nodes if abs(n["strike"] - a["spot"]) <= 2 * a["sigma_points"]]
    watch = sorted(nearby[:5], key=lambda n: n["strike"])
    low = a["delta_bands"][-1]["put"]
    high = a["delta_bands"][-1]["call"]
    warnings = [
        "Dealer inventory is not observed. Signed gamma values are scenarios, not measured positions.",
        f"Closing indicative marks valued at {quote_at}; these are not executable or intraday option quotes.",
        "OI effective date is unverified; no same-day inventory or OI-flow claim is justified."
        if snapshot["oi_asof"] is None
        else f"OI date supplied as {snapshot['oi_asof']}: {snapshot['oi_date_evidence']}",
        "Annualized IV uses the quote-to-settlement clock; it is not silently shortened to publication time.",
    ]
    if stale:
        warnings.insert(
            0,
            "STALE RELATIVE TO THE LATEST EXPECTED CLOSE — historical reference only, not a fresh daily map.",
        )
    if snapshot["oi_matched_rows"] < snapshot["rows"]:
        warnings.append(
            f"OI matched {snapshot['oi_matched_rows']:,}/{snapshot['rows']:,} quote rows; missing OI is excluded, not zero-filled."
        )
    if any(b["put"] is None or b["call"] is None for b in a["delta_bands"]):
        warnings.append(
            "Some delta crossings are absent or ambiguous; do not extrapolate missing range edges."
        )
    warnings.extend(snapshot["context"]["warnings"])
    levels = (
        ", ".join(fmt(n["strike"], 0) for n in watch)
        or "no qualified nearby concentration"
    )
    decision_rows = [
        [
            "Around concentrations",
            f"Watch {levels}.",
            "Concentration is a location of sensitivity, not proven support/resistance.",
        ],
        [
            "Above the upper range",
            f"Acceptance above {fmt(high)} changes the location relative to the closing 25Δ range.",
            "Check current price/quotes; a call delta is not a breakout probability.",
        ],
        [
            "Below the lower range",
            f"Acceptance below {fmt(low)} moves outside the lower 25Δ reference.",
            "Short-gamma assumptions amplify either direction, not only declines.",
        ],
        [
            "Models disagree / data old",
            "Reduce reliance on a single switch; compare price behavior with each stated scenario.",
            "No numerical model vote is a calibrated probability or a sizing prescription.",
        ],
    ]
    scan = f"{fmt(a['grid'][0], 0)}–{fmt(a['grid'][-1], 0)}"
    profile_rows = [
        [
            p["scope"],
            MODEL_LABELS[p["model"]],
            fmt(p["gex_bn_per_1pct"], 2),
            ", ".join(fmt(r) for r in p["roots"]) or "none in scan",
        ]
        for p in a["profiles"]
    ]
    bucket_rows = [
        [
            b["root"],
            b["expiry"],
            f"{b['call_oi']:,}",
            f"{b['put_oi']:,}",
            fmt(b["put_call_oi_ratio"], 2),
            fmt(b["conventional_net_bn"], 2),
        ]
        for b in a["expiry_buckets"]
    ]
    bands = [
        [f"{b['delta']:.0%}", fmt(b["put"]), fmt(b["call"])] for b in a["delta_bands"]
    ]
    concentrations = [
        [
            fmt(n["strike"], 0),
            f"{n['call_oi']:,}",
            f"{n['put_oi']:,}",
            fmt(n["call_gex_bn"], 2),
            fmt(n["put_gex_bn"], 2),
        ]
        for n in nodes[:10]
    ]
    context_rows = [
        [
            q["symbol"],
            fmt(q["close"], 2),
            q["bar_start"],
            f"{q['interval_minutes']}-minute bar",
        ]
        for q in snapshot["context"]["quotes"]
    ]
    context_note = "Yahoo prices are supplemental, potentially delayed context. ES=F is a continuous-futures symbol; no ES-to-SPX basis conversion or live gamma revaluation is implied."
    sensitivity_rows = [
        [
            f"{s['total_vol_scale']:.0%}",
            ", ".join(fmt(r) for r in s["roots"]) or "none in scan",
        ]
        for s in a["vol_sensitivity_30d"]
    ]
    shock_rows = [
        [f"{s['spot_move_pct']:+.1f}%", fmt(s["hedge_notional_bn"], 2)]
        for s in a["finite_shocks_30d"]
    ]
    history_rows = history["rows"]
    history_note = f"{history['days_collected']} distinct quote dates retained; {history['days_in_90']} within the latest 90-calendar-day window. Accumulation has begun; missing days are not invented. All captured dates are retained."
    method = f"Spot {fmt(a['spot'], 2)}; parity forward {fmt(a['forward'], 2)}; decimal rate {a['rate']:.4f}; target SPXW {a['target_expiry']}, settlement {a['settlement_at']}. Gamma covers qualified, positive-bid OTM marks through 90 calendar days; full available strike range. Other-expiry scopes include SPX AM and SPXW PM contracts. A 201-point spot grid ({scan}, at least ±5% and widened for the stress envelope) uses fixed strike volatility and forward/spot ratios. Roots are interpolated, not exact ticks."
    units = "Gamma unit: option-exposure $bn per 1% underlying move = 0.01 × 100 × spot² × Σ(signed contracts × long-option gamma). Theoretical hedge changes have the opposite sign. Magnitudes assume the displayed fractions of OI belong to dealers; neither fractions nor sign are observed."
    gamma_svg, nodes_svg = _plots(a)
    density_svg, fan_svg = _distribution_plots(a)
    stress_rows = [
        [
            s["label"],
            fmt(s["forward"]),
            f"{fmt(s['low_1sigma'])}–{fmt(s['high_1sigma'])}",
            f"{fmt(s['low_3sigma'])}–{fmt(s['high_3sigma'])}",
        ]
        for s in a["distributions"]["scenarios"]
    ]
    band_rows = [
        [f"±{b['sigma']} log-σ", fmt(b["low"]), fmt(b["high"])]
        for b in a["distributions"]["bands"]
    ]
    level_rows = [
        [
            fmt(level["spot"]),
            *[
                fmt(level["scopes"].get(scope), 2)
                for scope in ("target", "7d", "30d", "90d")
            ],
        ]
        for level in a["level_regimes"]
    ]
    title = f"SPX decision map · {a['target_expiry']}"
    markdown = (
        f"# {title}\n\n**{regime} — model-dependent, not observed dealer sign.**\n\n"
    )
    markdown += "\n".join(f"- {w}" for w in warnings) + "\n\n"
    markdown += (
        "## Trading read\n\n"
        + table(["Situation", "Decision reference", "Limit"], decision_rows)
        + "\n\n"
    )
    markdown += f"## Priced range\n\nForward **{fmt(a['forward'], 2)}** · ATM straddle **{fmt(a['straddle_points'], 2)}** points · normal 1σ proxy **±{fmt(a['sigma_points'])}** · ATM IV **{a['atm_iv']:.2%}**, **{a['hours_from_quote']:.1f} hours at quote time**.\n\n"
    markdown += (
        table(["Absolute forward delta", "Put strike", "Call strike"], bands) + "\n\n"
    )
    markdown += (
        "## Overnight gaps and wider outcome distributions\n\n"
        + table(["Closing-reference band", "Lower", "Upper"], band_rows)
        + "\n\n"
        + table(
            ["Location scenario", "Forward", "±1 log-σ interval", "±3 log-σ interval"],
            stress_rows,
        )
        + "\n\n"
        + a["distributions"]["note"]
        + "\n\n"
    )
    markdown += f"10Δ IV: put {fmt(None if a['skew_10d_iv']['put'] is None else 100 * a['skew_10d_iv']['put'], 2)}%; call {fmt(None if a['skew_10d_iv']['call'] is None else 100 * a['skew_10d_iv']['call'], 2)}%. Straddle breakevens and a normal 68% proxy are different quantities; neither is a calibrated physical forecast.\n\n{a['digital_note']}\n\n"
    markdown += (
        "## Gamma scenarios\n\n"
        + table(
            ["Expiry scope", "Inventory assumption", "$bn / 1%", "Flip levels"],
            profile_rows,
        )
        + "\n\n"
        + units
        + "\n\n"
    )
    markdown += (
        "## Gamma at decision levels\n\n"
        + table(
            ["Hypothetical SPX", "Target $bn", "7d $bn", "30d $bn", "90d $bn"],
            level_rows,
        )
        + "\n\nConventional signs, spot repricing only: closing total variance and OI remain fixed. This is not observed intraday inventory.\n\n"
    )
    markdown += (
        "## Target-expiry unsigned concentrations\n\n"
        + table(
            ["Strike", "Call OI", "Put OI", "Call convexity $bn", "Put convexity $bn"],
            concentrations,
        )
        + "\n\n"
    )
    markdown += (
        "## By expiry\n\n"
        + table(
            ["Root", "Expiry", "Call OI", "Put OI", "P/C OI", "Conventional $bn"],
            bucket_rows,
        )
        + "\n\n"
    )
    markdown += (
        "## Sensitivity and finite shocks\n\n"
        + table(["Total-volatility scale", "30d conventional roots"], sensitivity_rows)
        + "\n\n"
        + table(["Finite spot move", "30d theoretical hedge $bn"], shock_rows)
        + "\n\n"
    )
    markdown += (
        "## Supplemental market context\n\n"
        + (
            table(["Symbol", "Price", "Bar starts", "Granularity"], context_rows)
            if context_rows
            else "Not available/requested; the closing-data analysis is intact."
        )
        + "\n\n"
        + context_note
        + "\n\n"
    )
    markdown += (
        "## History\n\n"
        + history_note
        + "\n\n"
        + table(
            ["Quote date", "Spot", "ATM IV", "Straddle", "30d conventional flips"],
            history_rows,
        )
        + "\n\n"
    )
    markdown += (
        "## Method and provenance\n\n"
        + method
        + "\n\n"
        + f"Usable model rows: {a['quality']['usable_rows']:,}. Exclusions: {a['quality']['excluded']}. These aggregates describe filtered coverage, not all outstanding contracts.\n\nSnapshot `{snapshot_id}` · captured {snapshot['captured_at']}.\n\nSources: [Cboe marking prices](https://www.cboe.com/markets/us/options/market-statistics/product-data/proprietary-index-marking-prices), [OCC series data](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/series-search-batch-processing). Exact inputs and their hashes are stored with the snapshot.\n"
    )

    def section(num: int, heading: str, body: str) -> str:
        return f'<section class="page"><div class="eyebrow">SPX LAB / {num:02d}</div><h2>{heading}</h2>{body}</section>'

    def para(text: str, css: str = "") -> str:
        return f'<p class="{css}">{html.escape(text)}</p>'

    page1 = (
        f'<h1>{html.escape(title)}</h1><div class="regime">{html.escape(regime)}</div>'
    )
    page1 += para(
        "A trading reference built from closing prices and explicit inventory scenarios—not an observed dealer book.",
        "lead",
    )
    page1 += (
        '<div class="metrics">'
        + "".join(
            f"<div><span>{label}</span><strong>{value}</strong></div>"
            for label, value in [
                ("Closing SPX", fmt(a["spot"], 2)),
                ("Forward", fmt(a["forward"], 2)),
                ("Straddle points", fmt(a["straddle_points"], 2)),
                ("1σ proxy", "±" + fmt(a["sigma_points"])),
            ]
        )
        + "</div>"
    )
    page1 += _html_table(["Situation", "Decision reference", "Limit"], decision_rows)
    page1 += para(
        f"Wider overnight envelope: {fmt(a['distributions']['grid'][0], 0)}–{fmt(a['distributions']['grid'][-1], 0)} across the illustrated gap stresses and 3σ tails. This is a stress display, not a forecast interval."
    )
    page1 += '<div class="caveats">' + "".join(para(w) for w in warnings) + "</div>"
    page2 = para(
        f"SPXW {a['target_expiry']} · ATM IV {a['atm_iv']:.2%} · {a['hours_from_quote']:.1f} hours from quote to settlement."
    )
    page2 += _html_table(["Absolute forward delta", "Put strike", "Call strike"], bands)
    page2 += para(
        "Skew-aware delta ranges are not symmetric probability bands. Straddle cost is not a 68% interval."
    ) + para(a["digital_note"])
    page2 += (
        "<h3>Overnight gaps & wider possible outcomes</h3>"
        + density_svg
        + fan_svg
        + para(a["distributions"]["note"], "small")
    )
    page2 += _html_table(["Closing band", "Lower", "Upper"], band_rows)
    page2 += (
        "<details><summary>All gap-stress intervals</summary>"
        + _html_table(
            ["Scenario", "Forward", "1σ interval", "3σ interval"], stress_rows
        )
        + "</details>"
    )
    page2 += nodes_svg + _html_table(
        ["Strike", "Call OI", "Put OI", "Call $bn", "Put $bn"], concentrations
    )
    page3 = (
        gamma_svg
        + _html_table(["Scope", "Assumption", "$bn / 1%", "Roots"], profile_rows)
        + para(units, "small")
    )
    page3 += (
        "<h3>Gamma at decision levels</h3>"
        + _html_table(
            ["Hypothetical SPX", "Target $bn", "7d $bn", "30d $bn", "90d $bn"],
            level_rows,
        )
        + para(
            "Conventional signs, spot repricing only: closing total variance and OI remain fixed. This is not observed intraday inventory.",
            "small",
        )
    )
    page3 += (
        "<details><summary>Expiry buckets and volatility / finite-shock sensitivity</summary>"
        + _html_table(
            ["Root", "Expiry", "Call OI", "Put OI", "P/C OI", "$bn"], bucket_rows
        )
        + _html_table(["Vol scale", "30d roots"], sensitivity_rows)
        + _html_table(["Spot move", "Hedge $bn"], shock_rows)
        + "</details>"
    )
    page4 = (
        "<h3>Supplemental context</h3>"
        + (
            _html_table(["Symbol", "Price", "Bar starts", "Granularity"], context_rows)
            if context_rows
            else para("No supplemental context collected.")
        )
        + para(context_note, "small")
    )
    page4 += (
        "<h3>Accumulating history</h3>"
        + para(history_note)
        + _html_table(["Date", "Spot", "IV", "Straddle", "30d flips"], history_rows)
    )
    page4 += "<h3>How to use this map</h3>" + para(
        "Treat concentrations as places to observe price behavior. Reassess a setup when price accepts beyond its reference range or the competing model views no longer support it. Confirm current quotes before evaluating a trade; this closing map does not price entries or establish expected returns."
    )
    page4 += (
        "<details open><summary>Calculation scope and provenance</summary>"
        + para(method)
        + para(
            f"Usable rows: {a['quality']['usable_rows']}; exclusions: {a['quality']['excluded']}."
        )
        + para(f"Snapshot {snapshot_id}; captured {snapshot['captured_at']}.", "small")
        + '<p><a href="analysis.json">Full calculation data</a> · <a href="report.md">Markdown report</a></p></details>'
    )
    css = """*{box-sizing:border-box}body{margin:0;background:#e9eef1;color:#162b40;font:15px/1.5 system-ui,sans-serif}.page{max-width:1120px;margin:28px auto;padding:38px;background:white;border-radius:16px;box-shadow:0 4px 25px #19304710}.eyebrow{font-weight:800;letter-spacing:.15em;color:#0c827c;font-size:12px}h1{font-size:38px;line-height:1.15;margin:18px 0}h2{font-size:28px;margin:10px 0 22px}h3{margin-top:30px}.regime{display:inline-block;background:#14283f;color:white;padding:9px 16px;border-radius:20px;font-weight:700}.lead{color:#52677a}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:25px 0}.metrics>div{background:#edf5f4;border-radius:10px;padding:18px}.metrics span{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.05em}.metrics strong{font-size:27px}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;margin:15px 0}th{text-align:left;background:#edf2f6;font-size:12px;letter-spacing:.02em}th,td{padding:10px 12px;border-bottom:1px solid #dde6ed}tbody tr:nth-child(even){background:#f7f9fb}td{vertical-align:top}.caveats{border-left:4px solid #ad7433;background:#fff8ec;padding:8px 18px;margin-top:20px;font-size:13px}.small{font-size:12px;color:#53677a;overflow-wrap:anywhere}svg{width:100%;height:auto;margin:15px 0}summary{cursor:pointer;font-weight:700;padding:12px 0}details{margin-top:15px}a{color:#006d75}@media(max-width:700px){.page{margin:10px;padding:20px}.metrics{grid-template-columns:repeat(2,1fr)}h1{font-size:29px}td,th{padding:8px;font-size:12px}}@media print{body{background:white}.page{box-shadow:none;border-radius:0;margin:0;padding:12mm;break-before:page;max-width:none}h1{font-size:26px}table{font-size:10px}td,th{padding:5px}.small{font-size:9px}.page:first-child{break-before:auto}details{display:block}summary{display:none}svg{max-height:70mm}@page{size:A4 landscape;margin:5mm}}"""
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'
        + html.escape(title)
        + "</title><style>"
        + css
        + "</style></head><body>"
    )
    document += (
        section(1, "Decision brief", page1)
        + section(2, "Priced ranges & concentrations", page2)
        + section(3, "Competing gamma views", page3)
        + section(4, "Context, history & decision discipline", page4)
    )
    document += "</body></html>"
    return markdown, document
