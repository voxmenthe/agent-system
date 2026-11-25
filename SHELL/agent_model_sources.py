"""Live catalog and offer adapters for the three agent-model routes."""

import copy
import json
import math
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path

type JSON = None | bool | int | float | str | list[JSON] | dict[str, JSON]
CMD_CATALOG = "https://api.commandcode.ai/provider/v1/models?view=client"
CMD_OFFERS = "https://commandcode.ai/docs/resources/pricing-limits"
OC_OFFERS = "https://opencode.ai/v2/docs/console/models/"
OC_PROVIDERS = frozenset(("opencode", "opencode-go"))


class SourceError(ValueError):
    pass


@dataclass
class Model:
    cli: str
    native_id: str
    name: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    efforts: list[str] = field(default_factory=list)
    context: int | None = None
    output: int | None = None
    pricing: list[dict[str, JSON]] = field(default_factory=list)
    billing_basis: str = "unknown"
    free: list[str] = field(default_factory=list)
    deal: list[str] = field(default_factory=list)
    stealth: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    released_at: float | None = None
    first_seen: float | None = None
    locally_new: bool = False
    eligibility: str = "unknown"
    details: dict[str, JSON] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.cli}:{self.native_id}"

    @property
    def badges(self) -> list[str]:
        return [
            kind for kind in ("free", "deal", "stealth", "new") if getattr(self, kind)
        ]

    def record(self) -> dict[str, JSON]:
        return {**asdict(self), "key": self.key, "badges": self.badges}


@dataclass
class Catalog:
    cli: str
    models: list[Model] = field(default_factory=list)
    status: str = "ok"
    source: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: str | None = None
    error: str | None = None
    offers: str = "unsupported"
    offer_error: str | None = None

    def record(self) -> dict[str, JSON]:
        return {k: v for k, v in asdict(self).items() if k != "models"}


def object_value(value: JSON) -> dict[str, JSON]:
    if not isinstance(value, dict):
        raise SourceError("expected a JSON object")
    return value


def object_rows(value: JSON) -> list[dict[str, JSON]]:
    if not isinstance(value, list):
        raise SourceError("expected a JSON array")
    return [object_value(row) for row in value]


def text_value(value: JSON) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceError("missing or invalid text field")
    return value


def optional_text(value: JSON) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SourceError("invalid optional text field")
    return value


def optional_flag(value: JSON) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise SourceError("invalid optional boolean field")
    return value


def identity(value: JSON) -> str:
    result = text_value(value)
    if not re.fullmatch(r"[\w./:@+\-]+", result):
        raise SourceError("invalid native model identity")
    return result


def strings(value: JSON) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SourceError("expected a string array")
    return value


def number(value: JSON) -> float | int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise SourceError("invalid nonnegative numeric field")
    return value


def token_limit(value: JSON) -> int | None:
    result = number(value)
    if result is not None and int(result) != result:
        raise SourceError("token limit must be an integer")
    return int(result) if result is not None else None


def read_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "agent-models/1"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = response.read(8_000_001)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"{url}: {type(exc).__name__}") from exc
    if len(data) > 8_000_000:
        raise SourceError("metadata response exceeds 8 MB")
    return data.decode("utf-8")


def run_metadata(arguments: list[str]) -> str:
    # A regular file avoids the installed OpenCode CLI's large-pipe truncation.
    with tempfile.TemporaryFile(mode="w+") as output:
        try:
            result = subprocess.run(
                arguments,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.PIPE,
                text=True,
                timeout=18,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SourceError(f"{arguments[0]} metadata: {type(exc).__name__}") from exc
        if result.returncode:
            raise SourceError(f"{arguments[0]} metadata exited {result.returncode}")
        output.seek(0)
        return output.read()


def parse_cmd(payload: JSON) -> list[Model]:
    data = object_value(payload)
    if type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1:
        raise SourceError("unsupported Command Code client schema (expected 1)")
    models = []
    for row in object_rows(data.get("data")):
        if optional_flag(row.get("hidden")) is True:
            continue
        display = object_value(row.get("display", {}))
        pricing = object_value(row.get("pricing", {}))
        rates = {
            name: number(pricing[key])
            for key, name in (
                ("inputCost", "input"),
                ("outputCost", "output"),
                ("cacheReadCost", "cache_read"),
                ("cacheWriteCost", "cache_write"),
                ("cacheWrite1hCost", "cache_write_1h"),
            )
            if key in pricing
        }
        model = Model(
            "cmd",
            identity(row.get("id")),
            text_value(row.get("name")),
            description=optional_text(display.get("description")),
            aliases=strings(row.get("aliases", [])),
            efforts=strings(row.get("reasoningEfforts") or []),
            context=token_limit(row.get("context_length")),
            output=token_limit(row.get("maxOutputTokens")),
            pricing=[rates] if rates else [],
            billing_basis="published-token-rates",
        )
        model.details = {
            "group": optional_text(display.get("group")),
            "badge": optional_text(display.get("badge")),
            "notice": optional_text(display.get("notice")),
            "minimum_plan": optional_text(row.get("minimumPlan")),
            "input_modalities": strings(row.get("inputModalities", [])),
            "zdr": optional_flag(row.get("zdr")),
        }
        if all(rates.get(k) == 0 for k in ("input", "output")) and all(
            v == 0 for v in rates.values()
        ):
            model.free = ["current catalog token rates are zero"]
        if (
            model.native_id.lower().startswith("stealth/")
            or "stealth" in model.description.lower()
        ):
            model.stealth = ["provider namespace/description"]
        models.append(model)
    return models


def parse_oc(payload: JSON, directory: str) -> list[Model]:
    data = object_value(payload)
    location = object_value(data.get("location"))
    if (
        Path(text_value(location.get("directory"))).resolve()
        != Path(directory).resolve()
    ):
        raise SourceError("OpenCode catalog returned a different project location")
    models = []
    for row in object_rows(data.get("data")):
        provider = text_value(row.get("providerID"))
        if provider not in OC_PROVIDERS:
            continue
        capabilities = object_value(row.get("capabilities", {}))
        if row.get("enabled") is not True or row.get("status") in (
            "disabled",
            "deprecated",
        ):
            continue
        if capabilities.get("tools") is not True or "text" not in strings(
            capabilities.get("output", [])
        ):
            continue
        pricing = []
        for cost in object_rows(row.get("cost", [])):
            rates = {
                key: number(cost[key]) for key in ("input", "output") if key in cost
            }
            cache = object_value(cost.get("cache", {}))
            rates.update(
                {
                    f"cache_{key}": number(cache[key])
                    for key in ("read", "write")
                    if key in cache
                }
            )
            if "tier" in cost:
                tier = object_value(cost["tier"])
                rates["tier"] = {
                    "type": optional_text(tier.get("type")),
                    "size": number(tier.get("size")),
                }
            pricing.append(rates)
        limits = object_value(row.get("limit", {}))
        released = number(object_value(row.get("time", {})).get("released"))
        if released:
            try:
                datetime.fromtimestamp(released / 1000, UTC)
            except (ValueError, OverflowError, OSError) as exc:
                raise SourceError("invalid OpenCode release timestamp") from exc
        model = Model(
            "oc",
            f"{provider}/{identity(row.get('id'))}",
            text_value(row.get("name")),
            description=optional_text(row.get("description")),
            efforts=[
                identity(v.get("id")) for v in object_rows(row.get("variants", []))
            ],
            context=token_limit(limits.get("context")),
            output=token_limit(limits.get("output")),
            pricing=pricing,
            released_at=released / 1000 if released else None,
            billing_basis="subscription"
            if provider == "opencode-go"
            else "published-token-rates",
        )
        model.details = {
            "route": "OpenCode Go" if provider == "opencode-go" else "OpenCode Zen",
            "status": optional_text(row.get("status")),
            "family": optional_text(row.get("family")),
            "input_modalities": strings(capabilities.get("input", [])),
            "output_modalities": strings(capabilities.get("output", [])),
            "tools": True,
        }
        if provider == "opencode-go":
            model.details["billing_note"] = (
                "Go subscription/allowance; catalog rates are not a free-account offer"
            )
        elif pricing and all(
            p.get("input") == p.get("output") == 0
            and all(p.get(k, 0) == 0 for k in ("cache_read", "cache_write"))
            for p in pricing
        ):
            model.free = ["current Zen catalog token rates are zero"]
        if row.get("family") == "stealth" or "stealth" in model.description.lower():
            model.stealth = ["provider family/description"]
        models.append(model)
    return models


def parse_devin(payload: JSON) -> list[Model]:
    data = object_value(payload)
    models = []
    for family in object_rows(data.get("families")):
        for row in object_rows(family.get("variants")):
            model = Model(
                "devin",
                identity(row.get("model_uid")),
                text_value(row.get("label")),
                description=optional_text(row.get("description")),
                context=token_limit(row.get("max_context_tokens")),
                output=token_limit(row.get("max_output_tokens")),
                billing_basis="native-account-pricing",
                eligibility="native account catalog",
            )
            model.details = {
                "family": optional_text(family.get("family_label")),
                "cost_tier": optional_text(row.get("cost_tier")),
                "cost_summary": optional_text(row.get("cost_summary")),
                "is_beta": optional_flag(row.get("is_beta")),
                "is_new": optional_flag(row.get("is_new")),
                "effort_note": "effort is encoded in the exact model UID",
            }
            summary = optional_text(row.get("cost_summary"))
            nonzero = any(
                float(n) > 0 for n in re.findall(r"\$(\d+(?:\.\d+)?)", summary)
            )
            if optional_text(row.get("cost_tier")).casefold() == "free" and not nonzero:
                model.free = ["native account catalog cost_tier: Free"]
            if row.get("is_new") is True:
                model.new = ["native is_new flag"]
            if "stealth" in model.description.lower():
                model.stealth = ["native description"]
            models.append(model)
    return models


class OfferHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.paragraphs: list[str] = []
        self.rows: list[list[tuple[str, bool]]] = []
        self._script: list[str] | None = None
        self._paragraph: list[str] | None = None
        self._cell: list[str] | None = None
        self._deleted = False
        self._has_deleted = False
        self._row: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self._script = []
        elif tag == "p":
            self._paragraph = []
        elif tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._cell, self._has_deleted = [], False
        elif tag == "del":
            self._deleted, self._has_deleted = True, True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script))
            self._script = None
        elif tag == "p" and self._paragraph is not None:
            self.paragraphs.append("".join(self._paragraph))
            self._paragraph = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(("".join(self._cell).strip(), self._has_deleted))
            self._cell = None
        elif tag == "tr":
            self.rows.append(self._row)
        elif tag == "del":
            self._deleted = False

    def handle_data(self, text: str) -> None:
        if self._script is not None:
            self._script.append(text)
        if self._paragraph is not None:
            self._paragraph.append(text)
        if self._cell is not None and not self._deleted:
            self._cell.append(text)


def _cmd_offer_rows(html: str) -> list[dict[str, JSON]]:
    parser = OfferHTML()
    parser.feed(html)
    rows: dict[str, dict[str, JSON]] = {}

    def visit(value: JSON) -> None:
        if isinstance(value, dict):
            if all(k in value for k in ("id", "name", "tiers", "availability")):
                rows[text_value(value["id"])] = value
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for script in parser.scripts:
        if not script.startswith("self.__next_f.push(") or not script.endswith(")"):
            continue
        payload = json.loads(script[len("self.__next_f.push(") : -1])
        if (
            not isinstance(payload, list)
            or len(payload) < 2
            or not isinstance(payload[1], str)
        ):
            continue
        for line in payload[1].splitlines():
            _, separator, content = line.partition(":")
            if separator and content.startswith(("[", "{")):
                try:
                    visit(json.loads(content))
                except json.JSONDecodeError:
                    continue
    if not rows:
        raise SourceError("Command Code pricing row representation changed")
    return list(rows.values())


def _offer_current(expires: JSON, now: float) -> bool | None:
    if expires is None or expires == "":
        return True
    if not isinstance(expires, str):
        return None
    try:
        date = datetime.fromisoformat(expires)
    except ValueError:
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return date.timestamp() + (86400 if len(expires) == 10 else 0) > now


def annotate_cmd_offers(models: list[Model], html: str, now: float) -> None:
    index: dict[str, list[Model]] = {}
    for model in models:
        for key in {
            s.casefold()
            for s in (
                model.native_id,
                model.native_id.rsplit("/", 1)[-1],
                *model.aliases,
            )
        }:
            index.setdefault(key, []).append(model)
    for row in _cmd_offer_rows(html):
        matches = index.get(text_value(row["id"]).casefold(), [])
        if len(matches) != 1:
            continue
        model = matches[0]
        tiers = []
        # Whitelist rate categories; Next.js references stay unknown, not prices.
        for original in object_rows(row["tiers"]):
            tier = {
                k: optional_text(original[k])
                for k in ("label", "context")
                if k in original
            }
            for key in ("rates", "listRates"):
                if isinstance(original.get(key), dict):
                    tier[key] = {
                        k: number(v)
                        for k, v in original[key].items()
                        if k
                        in (
                            "input",
                            "output",
                            "cacheRead",
                            "cacheWrite",
                            "cacheWrite1h",
                        )
                    }
                elif key in original:
                    tier[key] = None
            tiers.append(tier)
        model.details["published_tiers"] = tiers
        model.details["plan_availability"] = {
            k: v
            for k, v in object_value(row["availability"]).items()
            if isinstance(v, bool)
        }
        deal = row.get("deal")
        if not isinstance(deal, dict):
            continue
        offer = {
            k: optional_text(deal[k])
            for k in ("id", "expires", "endsWhen", "revertNote", "note", "description")
            if k in deal
        }
        offer.update(
            {
                k: number(deal[k])
                for k in ("discountPercent", "usageMultiplier")
                if k in deal
            }
        )
        if "free" in deal:
            offer["free"] = optional_flag(deal["free"])
        if offer.get("discountPercent") is not None and offer["discountPercent"] > 100:
            raise SourceError("invalid advertised discount percentage")
        offer["source"] = CMD_OFFERS
        active = _offer_current(deal.get("expires"), now)
        offer["status"] = (
            "advertised"
            if active
            else "expired"
            if active is False
            else "unknown expiry"
        )
        if not deal.get("expires"):
            offer["condition"] = deal.get("endsWhen") or "advertised; end not published"
        model.details["offer"] = offer
        if active is not True:
            continue
        rates = [t["rates"] for t in tiers if isinstance(t.get("rates"), dict)]
        contradictory = any(
            any(v is not None and v > 0 for v in r.values()) for r in rates
        )
        if deal.get("free") is True and (
            contradictory
            or any(
                any(isinstance(v, (int, float)) and v > 0 for v in p.values())
                for p in model.pricing
            )
        ):
            offer["status"] = "conflicting free terms"
            model.free = []
        elif deal.get("free") is True:
            model.free.append("currently advertised free offer")
        percent = number(deal.get("discountPercent"))
        if percent and not str(offer["status"]).startswith("conflicting"):
            unit = (
                "boosted usage allowance"
                if "usage" in str(deal.get("id", ""))
                else "advertised token discount"
            )
            offer["kind"] = unit
            model.deal = [
                f"{unit}: provider advertises {percent:g}%; not an account billing quote"
            ]


def annotate_oc_offers(models: list[Model], html: str, now: float) -> None:
    parser = OfferHTML()
    parser.feed(html)
    identities: dict[str, set[str]] = {}
    for row in parser.rows:
        if len(row) == 4 and row[2][0].startswith("https://opencode.ai/inference/"):
            identities.setdefault(row[0][0], set()).add(row[1][0])
    pricing = [row for row in parser.rows if len(row) == 5 and row[0][0] != "Model"]
    if not identities or not pricing:
        raise SourceError("OpenCode pricing tables changed")
    by_id = {m.native_id: m for m in models if m.native_id.startswith("opencode/")}
    for row in pricing:
        label = row[0][0]
        name = re.sub(r"\s*\([^)]*off\)\s*$", "", label).strip()
        matches = identities.get(name, set())
        if len(matches) > 1:
            raise SourceError("ambiguous OpenCode offer/model join")
        model = by_id.get("opencode/" + next(iter(matches), ""))
        if model is None:
            continue
        model.details["console_prices"] = {
            k: cell[0]
            for k, cell in zip(
                ("input", "output", "cache_read", "cache_write"), row[1:]
            )
        }
        notices = [p for p in parser.paragraphs if name in p]
        if notices:
            model.details["console_notices"] = notices
        if not any(cell[1] for cell in row[1:]):
            continue
        expires = None
        unknown_expiry = False
        for notice in notices:
            match = re.search(
                r"(?:through|until|expires(?: on)?|ends(?: on)?) ([A-Za-z]+ \d{1,2}, \d{4})",
                notice,
                re.IGNORECASE,
            )
            if match:
                try:
                    expires = (
                        datetime.strptime(match[1], "%B %d, %Y")
                        .replace(tzinfo=UTC)
                        .isoformat()
                    )
                except ValueError:
                    raise SourceError(
                        "unrecognized OpenCode promotion expiry"
                    ) from None
            elif re.search(
                r"\b(?:through|until|expires|ends)\b", notice, re.IGNORECASE
            ):
                unknown_expiry = True
        active = None if unknown_expiry else _offer_current(expires, now)
        model.details["offer"] = {
            "source": OC_OFFERS,
            "label": label,
            "expires": expires,
            "status": "advertised"
            if active
            else "expired"
            if active is False
            else "unknown expiry",
            "condition": "advertised; end not published"
            if not expires
            else "published expiry",
        }
        if active:
            model.deal = [f"{label}: struck-through reference token prices"]


def annotate_curated_offers(models: list[Model], payload: JSON, now: float) -> None:
    data = object_value(payload)
    if (
        set(data) != {"schema_version", "offers"}
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise SourceError("unsupported curated offers schema (expected 1)")
    today = datetime.fromtimestamp(now, UTC).date()
    active: dict[str, dict[str, JSON]] = {}
    seen_ids = set()
    for row in object_rows(data["offers"]):
        if set(row) != {
            "id",
            "models",
            "discounts",
            "starts",
            "through",
            "checked_at",
            "source",
            "condition",
        }:
            raise SourceError("curated offer has missing or unexpected fields")
        offer_id = text_value(row["id"])
        if offer_id in seen_ids:
            raise SourceError(f"duplicate curated offer ID: {offer_id}")
        seen_ids.add(offer_id)
        keys = strings(row["models"])
        if not keys or len(set(keys)) != len(keys):
            raise SourceError(f"curated offer needs unique model keys: {offer_id}")
        for key in keys:
            cli, separator, native = key.partition(":")
            if not separator or cli not in ("cmd", "oc", "devin"):
                raise SourceError(f"curated offer needs exact CLI:model keys: {key}")
            identity(native)
        discounts = object_value(row["discounts"])
        if not discounts:
            raise SourceError(
                f"curated offer needs plan-specific discounts: {offer_id}"
            )
        for plan, percent in discounts.items():
            text_value(plan)
            value = number(percent)
            if value is None or not 0 < value <= 100:
                raise SourceError(f"invalid curated discount: {offer_id}")
        try:
            starts = date.fromisoformat(text_value(row["starts"]))
            through = date.fromisoformat(text_value(row["through"]))
            date.fromisoformat(text_value(row["checked_at"]))
        except ValueError as exc:
            raise SourceError(f"invalid curated offer date: {offer_id}") from exc
        if through < starts:
            raise SourceError(f"curated offer ends before it starts: {offer_id}")
        source = text_value(row["source"])
        if not source.startswith("https://"):
            raise SourceError(f"curated offer needs an HTTPS source: {offer_id}")
        condition = text_value(row["condition"])
        if not starts <= today <= through:
            continue
        offer = {
            k: row[k]
            for k in ("id", "discounts", "starts", "through", "checked_at", "source")
        }
        offer.update(
            status="advertised; manually curated",
            kind="advertised token discount by plan",
            condition=condition,
            eligibility="not verified for this account",
            expiry_basis="published date; inclusive UTC calendar day",
        )
        for key in keys:
            if key in active:
                raise SourceError(f"overlapping active curated offers: {key}")
            active[key] = offer
    for model in models:
        if model.key in active and not model.deal:
            model.details["offer"] = active[model.key]
            model.deal = [
                (
                    "provider-advertised plan-specific discount; manually curated; "
                    "account eligibility not verified"
                )
            ]


def _native_fallback(cli: str) -> list[Model]:
    command = (
        ["cmd", "--no-auto-update", "--list-models"]
        if cli == "cmd"
        else ["opencode", "models"]
    )
    models = []
    for line in run_metadata(command).splitlines():
        if cli == "cmd":
            match = re.match(r"^([\w./:@+\-]+)\s{2,}(.+)$", line)
            if match:
                models.append(
                    Model(
                        cli,
                        identity(match[1]),
                        match[1],
                        description=match[2],
                        details={
                            "metadata_notice": "native ID listing only; price and effort unknown"
                        },
                    )
                )
        elif (
            re.fullmatch(r"[\w.\-]+/[\w./:@+\-]+", line)
            and line.split("/", 1)[0] in OC_PROVIDERS
        ):
            models.append(
                Model(
                    cli,
                    line,
                    line,
                    details={
                        "metadata_notice": "native ID listing only; price, effort and capabilities unknown"
                    },
                )
            )
    if not models:
        raise SourceError("native fallback returned no usable IDs")
    return models


def fetch_catalog(cli: str, directory: str) -> Catalog:
    source = {
        "cmd": CMD_CATALOG,
        "oc": "opencode api model.list",
        "devin": "devin models list --format json",
    }[cli]
    catalog = Catalog(cli, source=source)
    try:
        if cli == "cmd":
            payload = json.loads(read_url(CMD_CATALOG))
            catalog.models = parse_cmd(payload)
            catalog.version = optional_text(payload.get("catalogVersion")) or None
        elif cli == "oc":
            payload = json.loads(
                run_metadata(
                    [
                        "opencode",
                        "api",
                        "model.list",
                        "--param",
                        f"location[directory]={directory}",
                    ]
                )
            )
            catalog.models = parse_oc(payload, directory)
        else:
            catalog.models = parse_devin(
                json.loads(
                    run_metadata(["devin", "models", "list", "--format", "json"])
                )
            )
        if (
            len({m.key for m in catalog.models}) != len(catalog.models)
            or not catalog.models
        ):
            raise SourceError("empty catalog or duplicate model identities")
    except (SourceError, json.JSONDecodeError, UnicodeError) as exc:
        catalog.status, catalog.error = "unavailable", str(exc)
        catalog.models = []
        if cli in ("cmd", "oc"):
            try:
                catalog.models = _native_fallback(cli)
                catalog.status = "reduced"
            except SourceError as fallback_error:
                catalog.error += f"; native fallback: {fallback_error}"
        return catalog
    try:
        annotated = copy.deepcopy(catalog.models)
        if cli in ("cmd", "oc"):
            url, annotate = (
                (CMD_OFFERS, annotate_cmd_offers)
                if cli == "cmd"
                else (OC_OFFERS, annotate_oc_offers)
            )
            annotate(annotated, read_url(url), datetime.now(UTC).timestamp())
            catalog.offers = "ok"
        else:
            # Keep Devin offers fresh: periodically update/reinstall this JSON.
            path = Path(__file__).with_name("agent_model_offers.json")
            annotate_curated_offers(
                annotated, json.loads(path.read_text()), datetime.now(UTC).timestamp()
            )
            catalog.offers = "curated"
        catalog.models = annotated
    except (SourceError, json.JSONDecodeError, UnicodeError, OSError) as exc:
        catalog.offers, catalog.offer_error = "unavailable", str(exc)
    if cli == "devin":
        for model in catalog.models:
            model.details["offer_coverage"] = (
                "manual annotations; not exhaustive; account eligibility not verified"
                if catalog.offers == "curated"
                else "curated source unavailable; promotion state unknown"
            )
    return catalog
