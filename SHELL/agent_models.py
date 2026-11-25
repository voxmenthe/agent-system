#!/usr/bin/env python3
"""Discover, choose, and resolve a live native coding-agent model."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from agent_model_picker import choose, detail
from agent_model_sources import (
    Catalog,
    Model,
    SourceError,
    fetch_catalog,
    object_value,
    run_metadata,
)

RECENT_SECONDS = 7 * 86400
SCOPES = ("cmd", "oc", "devin")


def update_first_seen(
    catalogs: list[Catalog], directory: str, now: float
) -> str | None:
    root = (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "agent-models"
    )
    try:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "first-seen.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = root / "first-seen.json"
            state = (
                json.loads(path.read_text())
                if path.exists()
                else {"version": 1, "scopes": {}}
            )
            if (
                not isinstance(state, dict)
                or state.get("version") != 1
                or not isinstance(state.get("scopes"), dict)
            ):
                raise SourceError("invalid first-seen baseline schema")
            observations = []
            for catalog in catalogs:
                if catalog.status != "ok":
                    continue
                profile = [
                    catalog.cli,
                    directory,
                    str(Path.home()),
                    shutil.which(
                        {"cmd": "cmd", "oc": "opencode", "devin": "devin"}[catalog.cli]
                    ),
                ]
                profile.extend(
                    os.environ.get(k, "")
                    for k in (
                        "XDG_CONFIG_HOME",
                        "OPENCODE_CONFIG",
                        "OPENCODE_CONFIG_DIR",
                    )
                )
                scope = hashlib.sha256(json.dumps(profile).encode()).hexdigest()
                baseline = state["scopes"].setdefault(
                    scope, {"initialized_at": now, "models": {}}
                )
                if (
                    not isinstance(baseline, dict)
                    or not isinstance(baseline.get("models"), dict)
                    or not isinstance(baseline.get("initialized_at"), (int, float))
                    or isinstance(baseline["initialized_at"], bool)
                    or not 0 < baseline["initialized_at"] <= now
                ):
                    raise SourceError("invalid first-seen scope")
                for model in catalog.models:
                    seen = baseline["models"].setdefault(model.key, now)
                    if (
                        isinstance(seen, bool)
                        or not isinstance(seen, (int, float))
                        or not baseline["initialized_at"] <= seen <= now
                    ):
                        raise SourceError("invalid first-seen timestamp")
                    observations.append(
                        (
                            model,
                            seen,
                            seen > baseline["initialized_at"]
                            and now - seen <= RECENT_SECONDS,
                        )
                    )
            descriptor, temporary = tempfile.mkstemp(prefix=".first-seen.", dir=root)
            try:
                with os.fdopen(descriptor, "w") as output:
                    json.dump(state, output)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            for model, seen, locally_new in observations:
                model.first_seen = seen
                model.locally_new = locally_new
                if locally_new:
                    model.new.append(
                        "locally first seen within 7 days (not a release claim)"
                    )
    except (OSError, json.JSONDecodeError, SourceError) as exc:
        return f"local-new signal unavailable: {exc}"
    return None


def add_release_evidence(models: list[Model], now: float) -> None:
    for model in models:
        if model.released_at and 0 <= now - model.released_at <= RECENT_SECONDS:
            model.new.append("provider release date within 7 days")
        elif model.released_at and model.released_at > now:
            model.details["release_notice"] = (
                "future provider release time ignored for newness"
            )


def validate_native(cli: str, arguments: list[str]) -> bool:
    forbidden = {
        "--model",
        "--effort",
        "--variant",
        "--resume",
        "--continue",
        "--session",
        "--session-id",
        "--fork-session",
        "--fork",
        "--server",
        "--standalone",
        "--attach",
        "--cloud",
        "--config",
        "--local-only",
    }
    short = ("-m", "-r", "-c") if cli != "oc" else ("-m", "-s", "-c")
    values = {
        "-p",
        "--prompt",
        "--print",
        "--prompt-file",
        "--agent",
        "-f",
        "--file",
        "--title",
        "-n",
        "--name",
        "--format",
        "--output-format",
        "--log-level",
        "--max-turns",
        "--mod",
        "--append-system-prompt",
        "--system-prompt",
        "--permission-mode",
        "--respect-workspace-trust",
        "--add-dir",
        "--theme",
        "--skill",
        "--mod-option",
        "--tools-enable",
    }
    print_mode = bool(arguments and arguments[0] == "run" and cli == "oc")
    positional = []
    i = 1 if print_mode else 0
    while i < len(arguments):
        argument = arguments[i]
        i += 1
        if argument == "--":
            positional.extend(arguments[i:])
            break
        if argument.split("=", 1)[0] in forbidden or any(
            argument.startswith(s) for s in short
        ):
            raise SourceError(
                f"{argument}: use am's model/effort selection; resume and alternate profiles/transports are not supported"
            )
        if argument in ("-h", "--help", "-v", "--version"):
            print_mode = True
        if argument in values:
            if argument in ("-p", "--prompt", "--print"):
                print_mode = True
            optional_prompt = cli != "oc" and argument in ("-p", "--print")
            if optional_prompt and (
                i == len(arguments) or arguments[i].startswith("-")
            ):
                continue
            if i == len(arguments):
                raise SourceError(f"{argument} requires a value")
            i += 1
        elif argument.startswith(("--prompt=", "--print=", "-p")):
            print_mode = True
        elif not argument.startswith("-"):
            positional.append(argument)
    if cli == "oc" and positional and not print_mode:
        raise SourceError(
            "OpenCode TUI uses the current directory; use -p for a headless prompt"
        )
    return print_mode


def exact_matches(models: list[Model], key: str) -> list[Model]:
    cli, native = key.split(":", 1)
    if cli != "cmd":
        return [m for m in models if m.key == key]
    direct = [m for m in models if m.native_id.casefold() == native.casefold()]
    if direct:
        return direct
    return [
        m
        for m in models
        if native.casefold()
        in {s.casefold() for s in (*m.aliases, m.native_id.rsplit("/", 1)[-1])}
    ]


def create_oc_session(model: Model, effort: str | None, directory: str) -> str:
    provider, native = model.native_id.split("/", 1)
    reference = {"providerID": provider, "id": native}
    if effort:
        reference["variant"] = effort
    payload = {
        "title": f"am: {model.name}",
        "model": reference,
        "location": {"directory": directory},
    }
    response = object_value(
        json.loads(
            run_metadata(
                ["opencode", "api", "session.create", "--data", json.dumps(payload)]
            )
        )
    )
    session = object_value(response.get("data"))
    actual_model = object_value(session.get("model"))
    if (
        any(actual_model.get(k) != v for k, v in reference.items())
        or object_value(session.get("location")).get("directory") != directory
    ):
        raise SourceError(
            "OpenCode session did not retain the selected model/effort/location; nothing launched"
        )
    session_id = session.get("id")
    if not isinstance(session_id, str) or not session_id.startswith("ses_"):
        raise SourceError("OpenCode did not return a session ID")
    return session_id


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    native = []
    if "--" in arguments:
        index = arguments.index("--")
        native, arguments = arguments[index + 1 :], arguments[:index]
    parser = argparse.ArgumentParser(
        prog="am",
        description=__doc__,
        epilog="Examples: am oc; am cmd --kind deal --list; am 'cmd:stealth/cat-jam:free' -- -p 'task'. OpenCode is Zen/Go only. Native options follow --.",
    )
    parser.add_argument(
        "selector",
        nargs="*",
        help="optional cmd/oc/devin scope, then search text or exact CLI:native-id",
    )
    parser.add_argument(
        "--kind",
        choices=("free", "deal", "stealth", "new", "all"),
        help="require one evidence category (default: interesting models)",
    )
    parser.add_argument(
        "--all", action="store_true", help="include all supported model categories"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list",
        action="store_true",
        help="full descriptions and all available normalized metadata; no launch",
    )
    mode.add_argument(
        "--json",
        action="store_true",
        help="catalog plus source status as JSON; no launch",
    )
    parser.add_argument(
        "--effort",
        help="advertised effort/variant (Devin: select the exact UID instead)",
    )
    parser.add_argument("--resolve-to", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_intermixed_args(arguments)
    tokens = options.selector
    scope = tokens.pop(0) if tokens and tokens[0] in SCOPES else None
    exact = (
        tokens[0]
        if len(tokens) == 1
        and tokens[0].split(":", 1)[0] in SCOPES
        and ":" in tokens[0]
        else None
    )
    if exact:
        exact_scope = exact.split(":", 1)[0]
        if scope and scope != exact_scope:
            raise SourceError("scope and exact key disagree")
        scope = exact_scope
    if options.all and options.kind and options.kind != "all":
        raise SourceError("--all and --kind disagree")
    if (options.list or options.json) and native:
        raise SourceError("listing does not accept native launch arguments")
    kind = "all" if options.all else options.kind
    directory = str(Path.cwd().resolve())
    catalogs = [fetch_catalog(cli, directory) for cli in ([scope] if scope else SCOPES)]
    for catalog in catalogs:
        for model in catalog.models:
            model.details.update(
                catalog_source=catalog.source,
                catalog_checked_at=catalog.checked_at,
                catalog_version=catalog.version,
                metadata_status=catalog.status,
            )
    now = time.time()
    baseline_error = update_first_seen(catalogs, directory, now)
    models = [m for c in catalogs for m in c.models]
    add_release_evidence(models, now)
    if exact:
        models = exact_matches(models, exact)
        if len(models) > 1:
            raise SourceError("ambiguous alias; use the full canonical model key")
    elif tokens:
        query = " ".join(tokens).casefold()
        models = [
            m
            for m in models
            if query in (m.key + " " + m.name + " " + m.description).casefold()
        ]
    if kind and kind != "all":
        models = [m for m in models if kind in m.badges]
    elif not kind and not exact and not tokens:
        models = [m for m in models if m.badges]
    failed = any(c.status != "ok" or c.offers == "unavailable" for c in catalogs)
    if options.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "sources": [c.record() for c in catalogs],
                    "local_new_status": baseline_error or "ok",
                    "models": [m.record() for m in models],
                },
                indent=2,
            )
        )
        return int(failed)
    for c in catalogs:
        print(
            f"{c.cli}: {c.status} · {c.checked_at} · {c.source}"
            + (f" · {c.error}" if c.error else ""),
            file=sys.stderr,
        )
        if c.offers == "unavailable":
            print(
                f"{c.cli}: offer source unavailable · {c.offer_error}", file=sys.stderr
            )
    if baseline_error:
        print(f"am: {baseline_error}", file=sys.stderr)
    if options.list:
        print("\n\n".join(detail(m) for m in models))
        return int(failed)
    if not models:
        raise SourceError("no matching live models")
    selected = models[0] if exact else choose(models)
    if selected is None:
        return 0
    print_mode = validate_native(selected.cli, native)
    if options.effort and (
        selected.cli == "devin" or options.effort not in selected.efforts
    ):
        raise SourceError(f"unsupported effort for {selected.key}: {options.effort}")
    if not options.resolve_to:
        raise SourceError(
            "launch through the am shell function; use --list for standalone discovery"
        )
    refreshed = fetch_catalog(selected.cli, directory)
    matches = [m for m in refreshed.models if m.key == selected.key]
    if not matches or refreshed.status == "unavailable":
        raise SourceError(
            f"selected route could not be revalidated: {selected.key}; nothing launched"
        )
    current = matches[0]
    add_release_evidence([current], time.time())
    if (
        selected.locally_new
        and selected.first_seen is not None
        and time.time() - selected.first_seen <= RECENT_SECONDS
        and refreshed.status == "ok"
    ):
        current.locally_new = True
        current.first_seen = selected.first_seen
        current.new.append("locally first seen within 7 days (not a release claim)")
    constraint = kind if kind != "all" else None
    if constraint and constraint not in current.badges:
        raise SourceError(
            f"{selected.key} no longer satisfies --kind {constraint}; nothing launched"
        )
    for offer_kind in ("free", "deal"):
        if offer_kind in selected.badges and offer_kind not in current.badges:
            raise SourceError(
                f"selected {offer_kind} terms changed or could not be refreshed; nothing launched"
            )
    if options.effort and options.effort not in current.efforts:
        raise SourceError("selected effort is no longer advertised; nothing launched")
    session = (
        create_oc_session(current, options.effort, directory)
        if current.cli == "oc" and not print_mode
        else ""
    )
    print(
        f"Launching {current.key} · effort: {options.effort or 'native default'} · {', '.join(current.badges) or 'catalog'}",
        file=sys.stderr,
    )
    options.resolve_to.write_text(
        json.dumps(
            {
                "cli": selected.cli,
                "native_id": selected.native_id,
                "effort": options.effort or "",
                "session": session,
                "native": native,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SourceError, json.JSONDecodeError, OSError) as error:
        print(f"am: {error}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)
