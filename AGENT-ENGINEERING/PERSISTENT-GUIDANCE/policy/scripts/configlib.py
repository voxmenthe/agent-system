from __future__ import annotations

import copy
import json
import math
import tomllib
from collections.abc import MutableMapping
from typing import Any, Literal

import tomlkit

KeyPaths = tuple[tuple[str, ...], ...]
ConfigFormat = Literal["toml", "json"]
ABSENT = object()


class ConfigError(ValueError):
    pass


def _comparison_value(value: object) -> object:
    if value is ABSENT:
        return ABSENT
    if isinstance(value, dict):
        return (
            "table",
            tuple(
                sorted((key, _comparison_value(item)) for key, item in value.items())
            ),
        )
    if isinstance(value, list):
        return ("array", tuple(_comparison_value(item) for item in value))
    if isinstance(value, float) and math.isnan(value):
        return ("float", "nan")
    return (type(value).__name__, value)


def config_view(
    data: bytes, paths: KeyPaths, *, file_format: ConfigFormat = "toml"
) -> tuple[dict[str, Any], tuple[object, ...]]:
    """Return typed comparison views of unmanaged values and owned paths."""
    parsed = (
        json.loads(data.decode("utf-8"))
        if file_format == "json"
        else tomllib.loads(data.decode("utf-8"))
    )
    if not isinstance(parsed, dict):
        raise ConfigError("managed config must contain an object")
    values = []
    for path in paths:
        node = parsed
        parents = []
        for key in path[:-1]:
            if key not in node:
                node = None
                break
            child = node[key]
            if not isinstance(child, dict):
                raise ConfigError(f"non-table parent of managed key {'.'.join(path)}")
            parents.append((node, key))
            node = child
        values.append(node.pop(path[-1], ABSENT) if node is not None else ABSENT)
        for parent, key in reversed(parents):
            if not parent[key]:
                del parent[key]
    return (
        {key: _comparison_value(value) for key, value in parsed.items()},
        tuple(_comparison_value(value) for value in values),
    )


def merge_config(
    target: bytes, source: bytes, paths: KeyPaths, *, file_format: ConfigFormat = "toml"
) -> bytes:
    """Replace only owned values, preserving unowned values and TOML text.

    A missing owned value in source removes that value from target. A selected
    table owns its whole subtree. Non-table parents fail rather than being replaced.
    """
    unmanaged, _ = config_view(target, paths, file_format=file_format)
    _, expected = config_view(source, paths, file_format=file_format)
    parse = json.loads if file_format == "json" else tomlkit.parse
    document = parse(target.decode("utf-8"))
    source_document = parse(source.decode("utf-8"))
    for path, value in zip(paths, expected, strict=True):
        node = document
        for key in path[:-1]:
            if key not in node:
                if value is ABSENT:
                    node = None
                    break
                node[key] = {} if file_format == "json" else tomlkit.table()
            child = node[key]
            if not isinstance(child, MutableMapping):
                raise ConfigError(f"non-table parent of managed key {'.'.join(path)}")
            node = child
        if node is None:
            continue
        if value is ABSENT:
            node.pop(path[-1], None)
        else:
            item = source_document
            for key in path:
                item = item[key]
            node[path[-1]] = copy.deepcopy(item)
    text = (
        json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if file_format == "json"
        else tomlkit.dumps(document)
    )
    result = text.encode("utf-8")
    actual_unmanaged, actual = config_view(result, paths, file_format=file_format)
    if actual_unmanaged != unmanaged or actual != expected:
        raise ConfigError("managed config merge changed unowned or unexpected values")
    return result


def select_config(
    data: bytes, paths: KeyPaths, *, file_format: ConfigFormat = "toml"
) -> bytes:
    """Return a config fragment containing only selected values."""
    empty = b"{}" if file_format == "json" else b""
    return merge_config(empty, data, paths, file_format=file_format)
