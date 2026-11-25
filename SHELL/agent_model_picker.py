"""Readable catalog details and terminal selection; no discovery or model launches."""

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from agent_model_sources import JSON, Model, SourceError


def _paint(value: str, code: str, color: bool) -> str:
    return f"\033[{code}m{value}\033[0m" if color else value


def _metadata_lines(label: str, value: JSON, indent: str = "  ") -> list[str]:
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", label).replace("_", " ")
    label = label[:1].upper() + label[1:]
    if value is None or value == "" or value == [] or value == {}:
        return []
    if isinstance(value, dict) or (
        isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value)
    ):
        items = value.items() if isinstance(value, dict) else enumerate(value, 1)
        return [f"{indent}{label}:"] + [
            line
            for key, item in items
            for line in _metadata_lines(str(key), item, indent + "  ")
        ]
    text = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    if isinstance(value, bool):
        text = "yes" if value else "no"
    return [f"{indent}{label}: {text}"]


def _rate_line(label: str, rates: dict[str, JSON] | None) -> str:
    if not rates:
        return f"  {label}: not published"
    names = {
        "input": "in",
        "output": "out",
        "cache_read": "cache read",
        "cache_write": "cache write",
        "cache_write_1h": "cache write 1h",
    }
    parts = []
    for key, value in rates.items():
        key = {
            "cacheRead": "cache_read",
            "cacheWrite": "cache_write",
            "cacheWrite1h": "cache_write_1h",
        }.get(key, key)
        if key in names:
            parts.append(
                f"{names[key]} {'unpublished' if value is None else f'${value:g}'}"
            )
    if rates.get("tier"):
        tier = rates["tier"]
        label += f" ({tier.get('type') or 'tier'}: {tier.get('size', 'unpublished')})"
    return f"  {label}: " + "  ·  ".join(parts)


def detail(model: Model, *, color: bool = False) -> str:
    badges = "  ".join(b.upper() for b in model.badges)
    fields = [
        _paint(model.name, "1", color)
        + ("  " + _paint(badges, "33", color) if badges else ""),
        _paint(model.key, "2", color),
    ]
    if model.description:
        fields.extend(("", model.description))
    remaining = dict(model.details)
    offer = dict(remaining.pop("offer", {}) or {})
    source = {
        "offer_source": offer.pop("source", None),
        "offer_id": offer.pop("id", None),
        "offer_reviewed_at": offer.pop("checked_at", None),
    }
    if "discounts" in offer:
        offer["discounts_by_plan"] = {
            plan: f"{percent:g}% off"
            for plan, percent in offer.pop("discounts").items()
        }
    evidence = {kind: getattr(model, kind) for kind in model.badges}
    evidence["advertised_free"] = offer.pop("free", None)
    if offer.get("endsWhen") == offer.get("condition"):
        offer.pop("endsWhen", None)
    if offer.get("kind") == "boosted usage allowance" and "discountPercent" in offer:
        offer["advertised_percent"] = offer.pop("discountPercent")
    tiers = remaining.pop("published_tiers", [])
    availability = remaining.pop("plan_availability", {})
    pricing = [
        _rate_line("Catalog" if len(model.pricing) == 1 else f"Catalog {i}", rates)
        for i, rates in enumerate(model.pricing, 1)
    ]
    for i, tier in enumerate(tiers, 1):
        label = " · ".join(str(tier[k]) for k in ("label", "context") if tier.get(k))
        pricing.append(f"  {label or f'Published tier {i}'}")
        pricing.append("  " + _rate_line("Current", tier.get("rates")))
        if "listRates" in tier:
            pricing.append("  " + _rate_line("Reference", tier["listRates"]))
    remaining.update(
        context=f"{model.context:,} tokens" if model.context else "not published",
        max_output=f"{model.output:,} tokens" if model.output else "not published",
        efforts=model.efforts
        or (
            "encoded in exact UID"
            if model.cli == "devin"
            else "native default; not pinned"
        ),
        billing=model.billing_basis.replace("-", " "),
        eligibility="not verified"
        if model.eligibility == "unknown"
        else model.eligibility,
        available_on=[k for k, v in availability.items() if v],
        unavailable_on=[k for k, v in availability.items() if not v],
        aliases=model.aliases,
        native_cost_tier=remaining.pop("cost_tier", None),
    )
    for key, stamp in (
        ("released", model.released_at),
        ("first seen locally", model.first_seen),
    ):
        if stamp:
            source[key] = datetime.fromtimestamp(stamp, UTC).isoformat()

    def section(
        heading: str, values: dict[str, JSON], lines: list[str] | None = None
    ) -> None:
        lines = (lines or []) + [
            line
            for key, value in values.items()
            for line in _metadata_lines(key, value)
        ]
        if lines:
            fields.extend(("", _paint(heading, "1;36", color), *lines))

    summaries = {
        k: remaining.pop(k)
        for k in ("cost_summary", "console_prices")
        if remaining.get(k)
    }
    section(
        "PRICING · USD / MILLION TOKENS"
        if pricing
        else "PRICING · NATIVE ACCOUNT RATES",
        summaries,
        pricing or ([] if summaries else ["  Token prices: not published"]),
    )
    section("OFFER", offer)
    for heading, keys in (
        (
            "MODEL",
            (
                "context",
                "max_output",
                "efforts",
                "input_modalities",
                "output_modalities",
                "tools",
                "group",
                "family",
                "zdr",
            ),
        ),
        (
            "ACCESS & BILLING",
            (
                "billing",
                "native_cost_tier",
                "eligibility",
                "offer_coverage",
                "minimum_plan",
                "available_on",
                "unavailable_on",
                "billing_note",
                "notice",
                "console_notices",
            ),
        ),
    ):
        section(heading, {k: remaining.pop(k) for k in keys if k in remaining})
    source.update(
        {
            k: remaining.pop(k)
            for k in (
                "catalog_source",
                "catalog_checked_at",
                "catalog_version",
                "metadata_status",
            )
            if k in remaining
        }
    )
    section("EVIDENCE", evidence)
    section("OTHER DETAILS", remaining)
    section("SOURCE", source)
    return "\n".join(fields)


def _picker_rows(models: list[Model], color: bool, columns: int) -> list[str]:
    names = [" ".join(m.name.split()) for m in models]
    width = 32
    rows = []
    units = {"input": "in", "output": "out", "cached input": "cached"}
    for i, model in enumerate(models):
        route = (
            ("GO" if model.native_id.startswith("opencode-go/") else "ZEN")
            if model.cli == "oc"
            else model.cli.upper()
        )
        name = names[i] if len(names[i]) <= width else names[i][: width - 1] + "…"
        badges = " ".join(
            b.upper() for b in model.badges if b != "deal" or "free" not in model.badges
        )
        price = model.details.get("cost_summary") or "price unknown"
        if model.details.get("cost_summary"):
            price = re.sub(
                r"\s*/\s*1M\s+(Cached input|Input|Output)\b",
                lambda match: " " + units[match[1].casefold()],
                price,
                flags=re.IGNORECASE,
            )
        elif model.details.get("cost_tier"):
            price += f" · tier: {model.details['cost_tier']}"
        if model.pricing:
            rates = model.pricing[0]
            price = (
                "/".join(
                    "?" if rates.get(k) is None else f"${rates[k]:g}"
                    for k in ("input", "output")
                )
                + " in/out"
            )
            if len(model.pricing) > 1:
                price += " + tiers"
        if model.billing_basis == "subscription":
            price = "subscription"
        elif "free" in model.badges:
            price = "$0 tokens" if model.pricing else "native free tier"
        offer = model.details.get("offer") or {}
        if (
            "deal" in model.badges
            and "free" not in model.badges
            and offer.get("discountPercent") is not None
        ):
            discount = (
                "boosted usage"
                if offer.get("kind") == "boosted usage allowance"
                else f"{offer['discountPercent']:g}% off"
            )
            price = f"{price} · {discount}"
        elif "deal" in model.badges and offer.get("discounts"):
            percentages = sorted(set(offer["discounts"].values()))
            discount = f"{percentages[0]:g}"
            if len(percentages) > 1:
                discount += f"–{percentages[-1]:g}"
            price = f"{price} · {discount}% off (plan)"
        price = " ".join(str(price).split())
        summary = (
            f"{route:<5}  {name:<{width}}  "
            + _paint(
                f"{badges or '—':<17}", "32" if "free" in model.badges else "33", color
            )
            + f"  {price}"
        )
        search = f"{model.description}  {model.key}  {model.name}"
        # Keep full IDs/descriptions searchable without crowding the visible columns.
        visible_width = len(re.sub(r"\033\[[0-9;]*m", "", summary))
        rows.append(
            f"{i}\t{summary}"
            + " " * max(4, columns - visible_width)
            + _paint(" ".join(search.split()), "2", color)
        )
    return rows


def choose(models: list[Model]) -> Model | None:
    try:
        descriptor = os.open("/dev/tty", os.O_RDONLY)
    except OSError as exc:
        raise SourceError(
            "selection needs a terminal; use an exact CLI:model key or --list"
        ) from exc
    with (
        os.fdopen(descriptor, "r") as terminal_input,
        open("/dev/tty", "w") as terminal_output,
    ):
        if shutil.which("fzf"):
            color = "NO_COLOR" not in os.environ
            columns = max(80, os.get_terminal_size(terminal_output.fileno()).columns)
            rows = _picker_rows(models, color, columns)
            with tempfile.TemporaryDirectory(prefix="agent-model-preview-") as preview:
                for i, model in enumerate(models):
                    (Path(preview) / str(i)).write_text(detail(model, color=color))
                result = subprocess.run(
                    [
                        "fzf",
                        "--delimiter=\t",
                        "--with-nth=2..",
                        "--no-multi",
                        "--ansi",
                        "--layout=reverse",
                        "--border=rounded",
                        "--border-label= Agent models ",
                        "--info=inline-right",
                        "--no-hscroll",
                        "--ellipsis=",
                        "--highlight-line",
                        "--prompt=Find model › ",
                        "--header=Enter launch · Esc cancel · Tab preview · Ctrl-F expand · Shift-↑/↓ scroll\n"
                        + f"{'CLI':<5}  {'MODEL':<32}  {'SIGNALS':<17}  PRICE / OFFER",
                        "--preview-window=right,50%,wrap-word,border-left,<64(down,55%,border-top)",
                        "--bind=tab:toggle-preview,ctrl-f:change-preview-window(default,down,85%,wrap-word,border-top|),shift-up:preview-up,shift-down:preview-down",
                        "--color=bw"
                        if not color
                        else "--color=prompt:cyan,hl:cyan,hl+:cyan,pointer:magenta,info:yellow,border:gray,label:cyan",
                        "--preview",
                        f"cat {shlex.quote(preview)}/{{1}}",
                    ],
                    input="\n".join(rows),
                    stdout=subprocess.PIPE,
                    stderr=terminal_output,
                    text=True,
                    env={
                        **os.environ,
                        "FZF_DEFAULT_OPTS": "",
                        "FZF_DEFAULT_OPTS_FILE": "",
                    },
                    check=False,
                )
            if result.returncode in (1, 130):
                return None
            if result.returncode:
                raise SourceError(f"fzf exited {result.returncode}")
            index = result.stdout.split("\t", 1)[0]
            if not index.isdecimal() or not 0 <= int(index) < len(models):
                raise SourceError("invalid picker selection")
            return models[int(index)]
        for i, model in enumerate(models, 1):
            print(f"{i}. {detail(model)}", file=sys.stderr)
        print(
            "Model number (empty cancels): ", file=terminal_output, end="", flush=True
        )
        answer = terminal_input.readline().strip()
        if not answer:
            return None
        if not answer.isdecimal() or not 1 <= int(answer) <= len(models):
            raise SourceError("invalid model number")
        return models[int(answer) - 1]
