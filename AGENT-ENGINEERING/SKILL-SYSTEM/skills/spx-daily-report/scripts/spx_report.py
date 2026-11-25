#!/usr/bin/env python3
"""Collect, retain and replay an SPX decision map from free closing data."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from urllib.error import URLError

# Projected skills are hash-tracked: no bytecode beside the sibling modules.
sys.dont_write_bytecode = True

from options_app.spx_report_store import (
    SourceBlob,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)
from spx_analytics import analyze
from spx_render import build_report, fmt
from spx_sources import (
    CBOE_URL,
    OCC_URL,
    build_snapshot,
    expected_quote_date,
    fetch_source,
    fetch_yahoo_context,
)


def _default_db() -> Path:
    import options_app

    return (
        Path(options_app.__file__).resolve().parents[2]
        / "data"
        / "spx_reports"
        / "history.sqlite3"
    )


def history_summary(db: Path, current: dict, *, rate: float) -> dict:
    infos = list_snapshots(db, days=None)
    # Historical replay must not read future captures or revisions.
    eligible = [
        i
        for i in infos
        if i.quote_date <= current["quote_date"]
        and datetime.fromisoformat(i.captured_at)
        <= datetime.fromisoformat(current["captured_at"])
    ]
    latest = {i.quote_date: i for i in eligible}
    from datetime import date, timedelta

    cutoff = date.fromisoformat(current["quote_date"]) - timedelta(days=89)
    rows = []
    for info in list(latest.values())[-5:]:
        prior = load_snapshot(db, info.snapshot_id)
        a = analyze(prior.payload, rate=rate)
        conventional = next(
            (
                p
                for p in a["profiles"]
                if p["scope"] == "30d" and p["model"] == "calls_long_puts_short"
            ),
            None,
        )
        rows.append(
            [
                info.quote_date,
                fmt(a["spot"], 2),
                f"{a['atm_iv']:.2%}",
                fmt(a["straddle_points"], 2),
                ", ".join(fmt(v) for v in conventional["roots"])
                if conventional
                else "unavailable",
            ]
        )
    return {
        "days_collected": len(latest),
        "days_in_90": sum(d >= cutoff.isoformat() for d in latest),
        "rows": rows,
    }


def write_report(
    db: Path,
    snapshot_id: str,
    out: Path | None,
    *,
    target_expiry: str | None,
    rate: float,
) -> Path:
    stored = load_snapshot(db, snapshot_id)
    payload = stored.payload
    analysis = analyze(payload, target_expiry=target_expiry, rate=rate)
    analysis["snapshot_id"] = stored.info.snapshot_id
    analysis["sources"] = [
        {
            "name": s.name,
            "url": s.url,
            "retrieved_at": s.retrieved_at,
            "sha256": hashlib.sha256(s.content).hexdigest(),
            "bytes": len(s.content),
        }
        for s in stored.sources
    ]
    history = history_summary(db, payload, rate=rate)
    stale = payload["quote_date"] != expected_quote_date(datetime.now(UTC))
    markdown, document = build_report(
        payload, analysis, stored.info.snapshot_id, history, stale=stale
    )
    if out is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        out = db.parent / "reports" / f"{analysis['target_expiry']}-{stamp}"
    out = out.expanduser().resolve()
    if out.exists():
        raise FileExistsError(
            f"report output already exists; choose a new --out directory: {out}"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".spx-report-", dir=out.parent))
    try:
        (temporary / "analysis.json").write_text(
            json.dumps(analysis, indent=2, allow_nan=False) + "\n"
        )
        (temporary / "report.md").write_text(markdown)
        (temporary / "report.html").write_text(document)
        temporary.rename(out)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_db(),
        help="separate append-only SPX SQLite store",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser(
        "collect", help="download current Cboe/OCC files, save and generate a report"
    )
    collect.add_argument(
        "--yfinance",
        action="store_true",
        help="collect optional SPX/VIX/ES market context",
    )
    collect.add_argument(
        "--allow-stale",
        action="store_true",
        help="explicitly archive old data; report remains labeled stale",
    )
    ingest = commands.add_parser(
        "import-files", help="archive saved inputs without contacting a provider"
    )
    ingest.add_argument("--marks", type=Path, required=True)
    ingest.add_argument("--oi", type=Path, required=True)
    ingest.add_argument(
        "--captured-at",
        required=True,
        help="known original retrieval timestamp with timezone",
    )
    for sub in (collect, ingest):
        sub.add_argument(
            "--oi-asof", help="only with independent evidence of the cleared OI date"
        )
        sub.add_argument(
            "--oi-date-evidence",
            help="basis for --oi-asof; never infer solely from retrieval time",
        )
    replay = commands.add_parser(
        "report", help="offline replay of an archived snapshot"
    )
    replay.add_argument("--snapshot", default="latest")
    for sub in (collect, ingest, replay):
        sub.add_argument(
            "--out",
            type=Path,
            help="new output directory; never overwrites existing reports",
        )
        sub.add_argument(
            "--target-expiry",
            help="SPXW expiry; default earliest unexpired at quote time",
        )
        sub.add_argument(
            "--rate",
            type=float,
            default=0.0,
            help="annual decimal discount rate; default 0, explicitly reported",
        )
    history = commands.add_parser(
        "history", help="list stored snapshots without deleting data"
    )
    history.add_argument("--days", type=int, default=90)
    history.add_argument("--all", action="store_true")
    export = commands.add_parser(
        "export", help="export original input bytes and metadata from SQLite"
    )
    export.add_argument("--snapshot", default="latest")
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    db = args.db.expanduser().resolve()
    try:
        if args.command == "history":
            print(
                json.dumps(
                    [
                        asdict(i)
                        for i in list_snapshots(
                            db, days=None if args.all else args.days
                        )
                    ],
                    indent=2,
                )
            )
            return 0
        if args.command == "export":
            stored = load_snapshot(db, args.snapshot)
            args.out.mkdir(parents=True, exist_ok=False)
            for source in stored.sources:
                (args.out / f"{source.name}.raw").write_bytes(source.content)
            (args.out / "snapshot.json").write_text(
                json.dumps(stored.payload, allow_nan=False)
            )
            (args.out / "sources.json").write_text(
                json.dumps(
                    [
                        {
                            "name": s.name,
                            "url": s.url,
                            "retrieved_at": s.retrieved_at,
                            "sha256": hashlib.sha256(s.content).hexdigest(),
                        }
                        for s in stored.sources
                    ],
                    indent=2,
                )
            )
            print(args.out.resolve())
            return 0
        if args.command == "report":
            snapshot_id = args.snapshot
        else:
            if args.command == "collect":
                marks, oi = (
                    fetch_source("cboe-marks", CBOE_URL),
                    fetch_source("occ-oi", OCC_URL),
                )
            else:
                marks = SourceBlob(
                    "cboe-marks", CBOE_URL, args.captured_at, args.marks.read_bytes()
                )
                oi = SourceBlob(
                    "occ-oi", OCC_URL, args.captured_at, args.oi.read_bytes()
                )
            sources = (marks, oi)
            context = None
            if args.command == "collect" and args.yfinance:
                context, extra = fetch_yahoo_context()
                sources += (extra,)
            payload = build_snapshot(
                marks,
                oi,
                oi_asof=args.oi_asof,
                oi_evidence=args.oi_date_evidence,
                context=context,
            )
            payload["captured_at"] = max(
                datetime.fromisoformat(s.retrieved_at) for s in sources
            ).isoformat()
            if args.command == "collect" and not args.allow_stale:
                expected = expected_quote_date(datetime.now(UTC))
                if payload["quote_date"] != expected:
                    raise ValueError(
                        f"Cboe quote date {payload['quote_date']} != latest expected {expected}; use --allow-stale only for labeled historical capture"
                    )
            analyze(payload, target_expiry=args.target_expiry, rate=args.rate)
            snapshot_id = save_snapshot(db, payload, sources)
        out = write_report(
            db, snapshot_id, args.out, target_expiry=args.target_expiry, rate=args.rate
        )
    except (ValueError, OSError, sqlite3.Error, URLError) as exc:
        print(f"SPX report failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "database": str(db),
                "snapshot_id": load_snapshot(db, snapshot_id).info.snapshot_id,
                "report": str(out / "report.html"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
