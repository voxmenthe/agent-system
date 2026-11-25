from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import tomlkit
from configlib import merge_config
from hostlib import GuidanceError, load_host_manifest

HTTP_FORMATS = {
    "claude": ("mcpServers", "url", {"type": "http"}),
    "codex": ("mcp_servers", "url", {}),
    "antigravity": ("mcpServers", "serverUrl", {"disabled": False}),
    "kimi": ("mcpServers", "url", {}),
    "devin": ("mcpServers", "url", {"transport": "http"}),
}


def expected_mcp_outputs(root: Path) -> dict[Path, str]:
    """Render shared HTTP servers into canonical native config fragments, without writes."""
    manifest = load_host_manifest(root)
    projections = [item for item in manifest["projections"] if "shared_mcp" in item]
    if not projections:
        return {}
    try:
        registry = json.loads((root / "config/mcp/servers.json").read_bytes())
    except ValueError as exc:
        raise GuidanceError(f"invalid shared MCP registry: {exc}") from exc
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise GuidanceError("shared MCP registry needs schema_version 1")
    servers = registry.get("servers")
    if not isinstance(servers, dict):
        raise GuidanceError("shared MCP registry needs a servers object")
    for name, server in servers.items():
        if not name or not isinstance(server, (dict, type(None))):
            raise GuidanceError(f"invalid shared MCP server: {name}")
        if server is None:
            continue
        if set(server) != {"url"} or not isinstance(server["url"], str):
            raise GuidanceError(
                f"shared MCP server {name} needs only a url; credentials stay local"
            )
        try:
            url = urlsplit(server["url"])
        except ValueError as exc:
            raise GuidanceError(f"invalid shared MCP URL for {name}: {exc}") from exc
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            raise GuidanceError(f"invalid shared MCP URL for {name}")

    outputs = {}
    for projection in projections:
        reference = projection["shared_mcp"]
        if not isinstance(reference, dict) or set(reference) != {"format", "servers"}:
            raise GuidanceError(
                f"{projection['id']}: shared_mcp needs format and servers"
            )
        dialect, names = reference["format"], reference["servers"]
        if not isinstance(dialect, str) or dialect not in HTTP_FORMATS:
            raise GuidanceError(f"{projection['id']}: unknown shared MCP format")
        if (
            not isinstance(names, list)
            or not names
            or not all(isinstance(name, str) for name in names)
            or len(names) != len(set(names))
        ):
            raise GuidanceError(
                f"{projection['id']}: shared MCP servers must be unique names"
            )
        section, url_key, fields = HTTP_FORMATS[dialect]
        paths = tuple((section, name) for name in names)
        if "managed_keys" in projection and any(
            list(path) not in projection["managed_keys"] for path in paths
        ):
            raise GuidanceError(
                f"{projection['id']}: shared MCP entries need explicit managed_keys"
            )
        if set(names) - servers.keys():
            raise GuidanceError(
                f"{projection['id']}: shared MCP server missing from registry"
            )
        source = root / projection["source"]
        file_format = "toml" if dialect == "codex" else "json"
        if source.suffix != f".{file_format}":
            raise GuidanceError(
                f"{projection['id']}: shared MCP format disagrees with source suffix"
            )
        native = {
            section: {
                name: {**fields, url_key: servers[name]["url"]}
                for name in names
                if servers[name] is not None
            }
        }
        fragment = (
            tomlkit.dumps(native) if file_format == "toml" else json.dumps(native)
        )
        outputs[source] = merge_config(
            source.read_bytes(),
            fragment.encode(),
            paths,
            file_format=file_format,
        ).decode()
    return outputs
