#!/usr/bin/env python3
"""List OpenRouter models from the public catalog, newest first, or show
how much money is left on your API key.

  or models [TERM ...]   models whose id or name contains every TERM
  or free [TERM ...]     the same, limited to free models
  add --since YYYY-MM-DD or --since N to keep models created on or after
  that UTC date or within the past N days
  or key                 money left on $OPENROUTER_API_KEY, and the account
                         balance that also caps it
  add --json for the raw API records instead of a table

Installed as ~/.local/bin/or (OR also works on case-insensitive volumes).
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# Public endpoint; no API key needed. Returns text-output models by default.
MODELS_URL = "https://openrouter.ai/api/v1/models"
# These two need the API key. OpenRouter documents /credits as management-key
# only, but on 2026-11-09 it also answered a regular key.
KEY_URL = "https://openrouter.ai/api/v1/key"
CREDITS_URL = "https://openrouter.ai/api/v1/credits"
SECONDS_PER_DAY = 86_400

Model = dict[str, Any]  # one raw record from the catalog's `data` array


def fetch_models() -> list[Model]:
    with urllib.request.urlopen(MODELS_URL, timeout=30) as response:
        return json.load(response)["data"]


def _fetch_authorized(url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def fetch_key(api_key: str) -> dict[str, Any]:
    """The key's record: `limit`, `limit_remaining`, `usage*`, `expires_at`, ..."""
    return _fetch_authorized(KEY_URL, api_key)


def fetch_credits(api_key: str) -> dict[str, Any] | None:
    """Account `total_credits` and `total_usage`, or None if this key may not read them."""
    try:
        return _fetch_authorized(CREDITS_URL, api_key)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            return None
        raise


def is_free(model: Model) -> bool:
    pricing = model["pricing"]
    return float(pricing["prompt"]) == 0 and float(pricing["completion"]) == 0


def matches(model: Model, terms: list[str]) -> bool:
    haystack = f"{model['id']} {model['name']}".lower()
    return all(term.lower() in haystack for term in terms)


def parse_since(value: str, now: float) -> float:
    """Return the earliest `created` timestamp kept by --since VALUE.

    All digits means the past N days, counted back from `now`; otherwise
    VALUE must be YYYY-MM-DD and means 00:00 UTC on that date, so the result
    agrees with the table's UTC CREATED column.
    """
    if value.isdigit():
        days = int(value)
        if days == 0:
            raise argparse.ArgumentTypeError("number of days must be at least 1")
        return now - days * SECONDS_PER_DAY
    try:
        start = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected YYYY-MM-DD or a number of days, got {value!r}"
        ) from None
    return start.timestamp()


def select_models(
    models: list[Model], terms: list[str], free_only: bool, created_since: float
) -> list[Model]:
    """Models matching every filter, newest first."""
    selected = [
        model
        for model in models
        if matches(model, terms)
        and (not free_only or is_free(model))
        and model["created"] >= created_since
    ]
    return sorted(selected, key=lambda model: model["created"], reverse=True)


def _per_million(price: str) -> str:
    dollars = float(price) * 1_000_000
    if dollars < 0:
        return "variable"  # routers such as openrouter/auto report -1
    return f"{dollars:.2f}" if dollars == 0 or dollars >= 0.01 else f"{dollars:.4g}"


def _date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def format_table(models: list[Model]) -> str:
    header = ("ID", "CONTEXT", "IN $/M", "OUT $/M", "MODALITY", "TOOLS", "CREATED", "EXPIRES")
    rows = [header]
    for model in models:
        rows.append((
            model["id"],
            f"{round(model['context_length'] / 1000):,}K",
            _per_million(model["pricing"]["prompt"]),
            _per_million(model["pricing"]["completion"]),
            model["architecture"]["modality"],
            "yes" if "tools" in model["supported_parameters"] else "-",
            _date(model["created"]),
            model.get("expiration_date") or "",
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in rows
    )


def _dollars(amount: float) -> str:
    """Cents when exact; otherwise four decimals, so $49.9986 isn't shown as $50.00."""
    return f"${amount:,.2f}" if abs(amount - round(amount, 2)) < 5e-5 else f"${amount:,.4f}"


def format_key_summary(key: dict[str, Any], credits: dict[str, Any] | None) -> str:
    """What the key can still spend: the smaller of its own limit and the account balance."""
    caps = {}
    if key["limit"] is None:
        key_line = f"no limit · {_dollars(key['usage'])} spent"
    else:
        caps["key limit"] = key["limit_remaining"]
        reset = key["limit_reset"] or "no reset"
        key_line = (
            f"{_dollars(key['limit'])}, {reset} · {_dollars(key['usage'])} spent"
            f" · {_dollars(key['limit_remaining'])} left"
        )
    if credits is None:
        account_line = "not readable with this key"
    else:
        balance = credits["total_credits"] - credits["total_usage"]
        caps["account balance"] = balance
        account_line = (
            f"{_dollars(balance)} ({_dollars(credits['total_credits'])} credits"
            f" − {_dollars(credits['total_usage'])} used)"
        )
    if caps:
        binding = min(caps, key=caps.get)
        spendable = f"{_dollars(caps[binding])}  ({binding} is the tighter cap)"
        if credits is None:
            spendable += "; the account balance may be lower"
    else:
        spendable = "unknown: the key has no limit and the account balance is unreadable"
    rows = [
        ("spendable now", spendable),
        ("key limit", key_line),
        ("spent on key", (
            f"{_dollars(key['usage_daily'])} today (UTC) · {_dollars(key['usage_weekly'])} this week"
            f" · {_dollars(key['usage_monthly'])} this month"
        )),
        ("account balance", account_line),
    ]
    if key.get("expires_at"):
        rows.append(("key expires", key["expires_at"]))
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"{label.ljust(width)}  {value}" for label, value in rows)


def show_key(as_json: bool) -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("or: OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1
    try:
        key = fetch_key(api_key)
        credits = fetch_credits(api_key)
    except urllib.error.URLError as error:
        print(f"or: could not read the key's balance from OpenRouter: {error}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({"key": key, "credits": credits}, indent=2))
    else:
        print(format_key_summary(key, credits))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="or",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", type=str.lower, choices=("models", "free", "key"))
    parser.add_argument("terms", nargs="*", help="case-insensitive; all must match the id or name")
    parser.add_argument(
        "-s",
        "--since",
        metavar="DATE|DAYS",
        type=lambda value: parse_since(value, time.time()),
        default=0.0,
        help="created on or after YYYY-MM-DD (UTC), or within the past N days",
    )
    parser.add_argument("--json", action="store_true", help="print the raw API records as JSON")
    args = parser.parse_args()

    if args.command == "key":
        if args.terms or args.since:
            parser.error("`or key` takes no search terms or --since")
        return show_key(args.json)

    try:
        models = fetch_models()
    except urllib.error.URLError as error:
        print(f"or: could not fetch {MODELS_URL}: {error}", file=sys.stderr)
        return 1

    selected = select_models(models, args.terms, args.command == "free", args.since)

    if args.json:
        print(json.dumps(selected, indent=2))
    elif selected:
        print(format_table(selected))
    summary = f"{len(selected)} of {len(models)} text-output models"
    if args.since:
        cutoff = datetime.fromtimestamp(args.since, timezone.utc)
        summary += f" created since {cutoff:%Y-%m-%d %H:%M} UTC"
    print(summary, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
