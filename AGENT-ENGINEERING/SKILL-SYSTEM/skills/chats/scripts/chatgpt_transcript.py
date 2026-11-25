"""Normalize and persist user-visible ChatGPT conversation transcripts."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_CHATGPT_HOSTS = {"chatgpt.com", "www.chatgpt.com", "chat.openai.com"}
_INTERNAL_CONTENT_TYPES = {
    "model_editable_context",
    "reasoning_recap",
    "thoughts",
    "user_editable_context",
}
_MODEL_METADATA_KEYS = (
    "model_slug",
    "default_model_slug",
    "resolved_model_slug",
    "thinking_effort",
    "finish_details",
)


class TranscriptError(ValueError):
    """The source conversation or requested export violates the contract."""


class ExportWriteError(TranscriptError):
    """A new export directory could not be completed safely."""


@dataclass(frozen=True)
class ExportBundle:
    """Complete in-memory export, ready for an atomic local write."""

    normalized: dict[str, Any]
    markdown: str


def utc_now() -> str:
    """Return a stable, second-resolution UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_conversation_id(value: str) -> str:
    """Parse a bare conversation id or an exact private ChatGPT /c/ URL."""
    candidate = value.strip()
    if not candidate:
        raise TranscriptError("Conversation URL or id is empty.")

    if "://" not in candidate:
        conversation_id = candidate
    else:
        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError as error:
            raise TranscriptError(f"Invalid ChatGPT conversation URL: {error}") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _CHATGPT_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise TranscriptError(
                "Expected an https://chatgpt.com/c/<id> URL or a bare conversation id."
            )
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) != 2 or segments[0] != "c":
            raise TranscriptError(
                "Only private ChatGPT /c/<id> conversation URLs are supported; "
                "share links are a different retrieval surface."
            )
        conversation_id = segments[1]

    if not _CONVERSATION_ID.fullmatch(conversation_id):
        raise TranscriptError(
            "Invalid ChatGPT conversation id; expected 8-128 letters, digits, hyphens, "
            "or underscores."
        )
    return conversation_id


def canonical_conversation_url(conversation_id: str) -> str:
    return f"https://chatgpt.com/c/{conversation_id}"


_GENERIC_TITLES = {"new chat", "untitled", "chatgpt conversation"}


def is_meaningful_title(title: str | None) -> bool:
    """Check if a conversation title is meaningful (not generic, empty, or placeholder)."""
    if not title or not isinstance(title, str):
        return False
    stripped = title.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered in _GENERIC_TITLES:
        return False
    if lowered.startswith("chatgpt conversation"):
        return False
    return True


def slugify_title(title: str | None, fallback: str = "") -> str:
    """Derive a safe, readable semantic slug from a conversation title.

    If the title is missing, generic, or non-meaningful, returns fallback.
    Otherwise, returns a lowercase, hyphen-separated slug safe for filenames.
    """
    if not is_meaningful_title(title):
        return fallback
    assert title is not None
    cleaned = re.sub(r"[^\w\s-]", " ", title.strip())
    slug = re.sub(r"[-\s]+", "-", cleaned).strip("-").lower()
    if len(slug) > 80:
        slug = slug[:80].rstrip("-")
    return slug or fallback


def build_export(
    raw_conversation: Mapping[str, object],
    conversation_id: str,
    *,
    exported_at: str | None = None,
) -> ExportBundle:
    """Build a normalized tree and Markdown transcript from a ChatGPT API response."""
    parsed_id = parse_conversation_id(conversation_id)
    raw = _expect_mapping(raw_conversation, "conversation response")
    mapping = _conversation_mapping(raw)
    current_node = raw.get("current_node")
    if not isinstance(current_node, str) or current_node not in mapping:
        raise TranscriptError("Conversation response has no valid current_node in mapping.")

    response_id = raw.get("conversation_id")
    if response_id is not None and response_id != parsed_id:
        raise TranscriptError(
            f"Fetched conversation id {response_id!r} does not match requested id {parsed_id!r}."
        )

    active_node_ids = _path_to_root(mapping, current_node)
    active_node_set = set(active_node_ids)
    visible_by_node: dict[str, dict[str, Any]] = {}
    message_ids: set[str] = set()

    for ordinal, (node_id, node) in enumerate(mapping.items()):
        message = _normalize_visible_message(node_id, node, ordinal)
        if message is None:
            continue
        message_id = message["id"]
        if message_id in message_ids:
            raise TranscriptError(f"Duplicate visible message id in conversation: {message_id}")
        message_ids.add(message_id)
        message["on_active_branch"] = node_id in active_node_set
        visible_by_node[node_id] = message

    active_message_ids = [
        visible_by_node[node_id]["id"]
        for node_id in active_node_ids
        if node_id in visible_by_node
    ]
    if not active_message_ids:
        raise TranscriptError("The active conversation branch has no user-visible messages.")

    parent_cache: dict[str, str | None] = {}
    for node_id, message in visible_by_node.items():
        parent_node_id = _nearest_visible_parent(
            node_id,
            mapping,
            visible_by_node,
            parent_cache,
        )
        message["parent_id"] = (
            visible_by_node[parent_node_id]["id"] if parent_node_id is not None else None
        )
        message["children"] = []

    messages = sorted(visible_by_node.values(), key=_message_sort_key)
    by_message_id = {message["id"]: message for message in messages}
    for message in messages:
        parent_id = message["parent_id"]
        if parent_id is not None:
            by_message_id[parent_id]["children"].append(message["id"])
    for message in messages:
        message["children"].sort(key=lambda child_id: _message_sort_key(by_message_id[child_id]))
        message.pop("_ordinal")

    title_value = raw.get("title")
    if title_value is None:
        title = f"ChatGPT conversation {parsed_id}"
    elif isinstance(title_value, str):
        title = _single_line(title_value) or f"ChatGPT conversation {parsed_id}"
    else:
        raise TranscriptError("Conversation title must be a string or null.")

    if exported_at is not None and (not isinstance(exported_at, str) or not exported_at):
        raise TranscriptError("Export timestamp must be a non-empty string.")
    timestamp = exported_at or utc_now()
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": timestamp,
        "source": {
            "service": "chatgpt",
            "conversation_id": parsed_id,
            "conversation_url": canonical_conversation_url(parsed_id),
            "title": title,
            "create_time": _json_scalar(raw.get("create_time"), "conversation create_time"),
            "update_time": _json_scalar(raw.get("update_time"), "conversation update_time"),
        },
        "counts": {
            "active_messages": len(active_message_ids),
            "alternate_messages": len(messages) - len(active_message_ids),
            "visible_messages": len(messages),
            "source_nodes": len(mapping),
        },
        "active_message_ids": active_message_ids,
        "messages": messages,
    }
    _validate_json_value(normalized, "normalized transcript")
    return ExportBundle(normalized=normalized, markdown=render_markdown(normalized))


def render_markdown(normalized: Mapping[str, object]) -> str:
    """Render a normalized schema-v1 conversation as readable Markdown."""
    source = _expect_mapping(normalized.get("source"), "normalized source")
    counts = _expect_mapping(normalized.get("counts"), "normalized counts")
    raw_messages = normalized.get("messages")
    if not isinstance(raw_messages, list):
        raise TranscriptError("Normalized transcript messages must be a list.")
    messages = [_expect_mapping(item, "normalized message") for item in raw_messages]
    active_ids_value = normalized.get("active_message_ids")
    if not isinstance(active_ids_value, list) or not all(
        isinstance(item, str) for item in active_ids_value
    ):
        raise TranscriptError("Normalized active_message_ids must be a list of strings.")
    by_id: dict[str, dict[str, Any]] = {}
    for message in messages:
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id or message_id in by_id:
            raise TranscriptError(
                "Normalized transcript has missing, invalid, or duplicate message ids."
            )
        by_id[message_id] = message

    title = _single_line(str(source.get("title") or "ChatGPT conversation"))
    lines = [
        f"# {title}",
        "",
        f"- Conversation: {source.get('conversation_url')}",
        f"- Active messages: {counts.get('active_messages')}",
        f"- Alternate-branch messages: {counts.get('alternate_messages')}",
        "",
        "## Active conversation",
        "",
    ]
    # A reading view: ids, timestamps, and empty messages stay in the JSON only.
    previous_label: str | None = None
    for message_id in active_ids_value:
        message = by_id.get(message_id)
        if message is None:
            raise TranscriptError(f"Active message {message_id!r} is absent from messages.")
        body = _render_message_body(message)
        if not body:
            continue
        label = _speaker_label(message)
        if label != previous_label:
            lines.extend([f"### {label}", ""])
            previous_label = label
        lines.extend(body)

    alternates = [message for message in messages if not message.get("on_active_branch")]
    if alternates:
        lines.extend(
            [
                "## Alternate branches",
                "",
                "These user-visible messages are stored in the conversation tree but are not "
                "on the branch selected by ChatGPT's `current_node`.",
                "",
            ]
        )
        for message in alternates:
            body = _render_message_body(message)
            if not body:
                continue
            lines.extend(
                [
                    f"### {_speaker_label(message)} — alternate branch",
                    "",
                    f"Replies to: {_replies_to(message, by_id)}",
                    "",
                    *body,
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def write_export(
    output_directory: Path,
    bundle: ExportBundle,
    *,
    slug: str | None = None,
) -> dict[str, Any]:
    """Create a new export directory and write its verified manifest last."""
    output = output_directory.expanduser()
    markdown_bytes = bundle.markdown.encode("utf-8")
    json_bytes = (
        json.dumps(
            bundle.normalized,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    source = _expect_mapping(bundle.normalized.get("source"), "normalized source")
    source_conversation_id = source.get("conversation_id")
    if not isinstance(source_conversation_id, str):
        raise TranscriptError("Normalized source conversation id must be a string.")
    conversation_id = parse_conversation_id(source_conversation_id)
    if conversation_id != source_conversation_id:
        raise TranscriptError("Normalized source conversation id must be canonical.")

    title_val = source.get("title")
    title_str = str(title_val) if isinstance(title_val, str) else None
    chosen_slug = (
        slug.strip()
        if slug and slug.strip()
        else slugify_title(title_str, fallback=conversation_id)
    )

    markdown_name = f"{chosen_slug}.md"
    json_name = f"{chosen_slug}.json"
    manifest_name = f"{chosen_slug}.manifest.json"

    file_payloads = {
        markdown_name: markdown_bytes,
        json_name: json_bytes,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "exported_at": bundle.normalized.get("exported_at"),
        "conversation_id": conversation_id,
        "conversation_url": source.get("conversation_url"),
        "slug": chosen_slug,
        "files": {
            name: {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for name, payload in file_payloads.items()
        },
    }
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ExportWriteError(
            f"Could not create export parent directory {output.parent}: {error}"
        ) from error
    try:
        output.mkdir()
    except FileExistsError as error:
        raise TranscriptError(
            f"Output directory already exists; refusing to overwrite: {output}"
        ) from error
    except OSError as error:
        raise ExportWriteError(
            f"Could not create output directory {output}: {error}"
        ) from error

    completed: list[Path] = []
    try:
        for name, payload in file_payloads.items():
            destination = output / name
            _atomic_write(destination, payload)
            completed.append(destination)
            if destination.read_bytes() != payload:
                raise OSError(f"post-write verification failed for {destination}")
        manifest_path = output / manifest_name
        _atomic_write(manifest_path, manifest_bytes)
        completed.append(manifest_path)
    except OSError as error:
        _remove_incomplete_export(output, completed)
        raise ExportWriteError(f"Could not complete export in {output}: {error}") from error
    return manifest


def _conversation_mapping(raw: Mapping[str, object]) -> dict[str, dict[str, object]]:
    mapping_value = raw.get("mapping")
    if not isinstance(mapping_value, dict) or not mapping_value:
        raise TranscriptError("Conversation response mapping must be a non-empty object.")
    mapping: dict[str, dict[str, object]] = {}
    for node_id, node_value in mapping_value.items():
        if not isinstance(node_id, str) or not node_id:
            raise TranscriptError("Conversation mapping node ids must be non-empty strings.")
        mapping[node_id] = _expect_mapping(node_value, f"conversation node {node_id}")
    return mapping


def _path_to_root(mapping: Mapping[str, Mapping[str, object]], leaf: str) -> list[str]:
    reversed_path: list[str] = []
    seen: set[str] = set()
    current: str | None = leaf
    while current is not None:
        if current in seen:
            raise TranscriptError(f"Conversation mapping contains a parent cycle at {current}.")
        seen.add(current)
        node = mapping.get(current)
        if node is None:
            raise TranscriptError(f"Conversation mapping references missing node {current}.")
        reversed_path.append(current)
        parent = node.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise TranscriptError(f"Conversation node {current} has a non-string parent.")
        current = parent
    return list(reversed(reversed_path))


def _normalize_visible_message(
    node_id: str,
    node: Mapping[str, object],
    ordinal: int,
) -> dict[str, Any] | None:
    raw_message = node.get("message")
    if raw_message is None:
        return None
    message = _expect_mapping(raw_message, f"message in node {node_id}")
    author = _expect_mapping(message.get("author"), f"author in node {node_id}")
    role = author.get("role")
    if role not in {"user", "assistant"}:
        return None
    metadata_value = message.get("metadata")
    metadata = (
        {}
        if metadata_value is None
        else _expect_mapping(metadata_value, f"metadata in node {node_id}")
    )
    if metadata.get("is_user_system_message") or metadata.get(
        "is_visually_hidden_from_conversation"
    ):
        return None

    content = _expect_mapping(message.get("content"), f"content in node {node_id}")
    content_type = content.get("content_type") or "unknown"
    if not isinstance(content_type, str):
        raise TranscriptError(f"Message content_type in node {node_id} must be a string.")
    if content_type in _INTERNAL_CONTENT_TYPES:
        return None

    attachments = _copy_json_list(metadata.get("attachments"), f"attachments in node {node_id}")
    references = _copy_json_list(
        metadata.get("content_references"), f"content references in node {node_id}"
    )
    citations = _copy_json_list(metadata.get("citations"), f"citations in node {node_id}")
    blocks = _normalize_content_blocks(content, content_type, node_id)
    content_metadata = {
        key: copy.deepcopy(value)
        for key, value in content.items()
        if key not in {"content_type", "parts"}
    }

    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise TranscriptError(f"Visible message in node {node_id} has no string id.")
    author_name = author.get("name")
    if author_name is not None and not isinstance(author_name, str):
        raise TranscriptError(f"Author name in node {node_id} must be a string or null.")

    model = {
        key: copy.deepcopy(metadata[key])
        for key in _MODEL_METADATA_KEYS
        if key in metadata and metadata[key] is not None
    }
    return {
        "id": message_id,
        "node_id": node_id,
        "parent_id": None,
        "children": [],
        "role": role,
        "author_name": author_name,
        "create_time": _json_scalar(message.get("create_time"), f"create_time in node {node_id}"),
        "update_time": _json_scalar(message.get("update_time"), f"update_time in node {node_id}"),
        "status": _json_scalar(message.get("status"), f"status in node {node_id}"),
        "end_turn": _json_scalar(message.get("end_turn"), f"end_turn in node {node_id}"),
        "recipient": _json_scalar(message.get("recipient"), f"recipient in node {node_id}"),
        "channel": _json_scalar(message.get("channel"), f"channel in node {node_id}"),
        "content_type": content_type,
        "content": blocks,
        "content_metadata": content_metadata,
        "attachments": attachments,
        "references": references,
        "citations": citations,
        "model": model,
        "_ordinal": ordinal,
    }


def _normalize_content_blocks(
    content: Mapping[str, object],
    content_type: str,
    node_id: str,
) -> list[dict[str, Any]]:
    parts = content.get("parts")
    if parts is not None:
        if not isinstance(parts, list):
            raise TranscriptError(f"Content parts in node {node_id} must be a list or null.")
        blocks: list[dict[str, Any]] = []
        for part in parts:
            block = _normalize_part(part)
            if block is not None:
                blocks.append(block)
        return blocks

    body = {key: copy.deepcopy(value) for key, value in content.items() if key != "content_type"}
    if not body:
        return []
    return [{"type": content_type, "data": body}]


def _normalize_part(part: object) -> dict[str, Any] | None:
    if isinstance(part, str):
        return {"type": "text", "text": part}
    if isinstance(part, dict):
        part_type = part.get("content_type") or part.get("type") or "object"
        if not isinstance(part_type, str):
            part_type = "object"
        if part_type in _INTERNAL_CONTENT_TYPES:
            return None
        return {"type": part_type, "data": copy.deepcopy(part)}
    if part is None:
        return None
    if isinstance(part, (bool, int, float, list)):
        return {"type": "value", "data": copy.deepcopy(part)}
    raise TranscriptError(
        f"Conversation content contains unsupported value {type(part).__name__}."
    )


def _nearest_visible_parent(
    node_id: str,
    mapping: Mapping[str, Mapping[str, object]],
    visible_by_node: Mapping[str, Mapping[str, object]],
    cache: dict[str, str | None],
) -> str | None:
    if node_id in cache:
        return cache[node_id]
    current_value = mapping[node_id].get("parent")
    if current_value is not None and not isinstance(current_value, str):
        raise TranscriptError(f"Conversation node {node_id} has a non-string parent.")
    current = current_value
    trail: list[str] = []
    seen = {node_id}
    while current is not None:
        if current in seen:
            raise TranscriptError(f"Conversation mapping contains a parent cycle at {current}.")
        seen.add(current)
        if current in visible_by_node:
            result: str | None = current
            break
        if current in cache:
            result = cache[current]
            break
        parent_node = mapping.get(current)
        if parent_node is None:
            raise TranscriptError(f"Conversation mapping references missing node {current}.")
        trail.append(current)
        parent_value = parent_node.get("parent")
        if parent_value is not None and not isinstance(parent_value, str):
            raise TranscriptError(f"Conversation node {current} has a non-string parent.")
        current = parent_value
    else:
        result = None

    cache[node_id] = result
    for hidden_node_id in trail:
        cache[hidden_node_id] = result
    return result


def _message_sort_key(message: Mapping[str, object]) -> tuple[int, float, str, int, str]:
    create_time = message.get("create_time")
    ordinal = message.get("_ordinal")
    ordinal_value = ordinal if isinstance(ordinal, int) else 0
    message_id = str(message.get("id") or "")
    if isinstance(create_time, (int, float)) and not isinstance(create_time, bool):
        return (0, float(create_time), "", ordinal_value, message_id)
    if isinstance(create_time, str):
        return (1, 0.0, create_time, ordinal_value, message_id)
    return (2, 0.0, "", ordinal_value, message_id)


def _speaker_label(message: Mapping[str, object]) -> str:
    role = str(message.get("role") or "message")
    label = role.capitalize()
    model = _expect_mapping(message.get("model"), f"model for message {message.get('id')}")
    model_slug = model.get("model_slug") or model.get("resolved_model_slug")
    if role == "assistant" and model_slug:
        label += f" ({_single_line(str(model_slug))})"
    return label


def _replies_to(message: Mapping[str, object], by_id: Mapping[str, Mapping[str, object]]) -> str:
    parent_id = message.get("parent_id")
    if parent_id is None:
        return "(conversation start)"
    parent = by_id.get(str(parent_id))
    if parent is None:
        raise TranscriptError(
            f"Parent {parent_id!r} of message {message.get('id')!r} is absent from messages."
        )
    for block in _message_content(parent):
        if block.get("type") == "text":
            text = block.get("text")
        elif block.get("type") == "audio_transcription":
            text = _field_from_mapping(block.get("data"), "text")
        else:
            continue
        if isinstance(text, str) and text.strip():
            preview = _single_line(text)
            if len(preview) > 80:
                preview = preview[:79].rstrip() + "…"
            return f'"{preview}"'
    return "(a message without text)"


def _message_content(message: Mapping[str, object]) -> list[dict[str, Any]]:
    content = message.get("content")
    if not isinstance(content, list):
        raise TranscriptError(f"Message {message.get('id')} content must be a list.")
    return [
        _expect_mapping(block, f"content block for message {message.get('id')}")
        for block in content
    ]


def _render_message_body(message: Mapping[str, object]) -> list[str]:
    references = message.get("references")
    citations = message.get("citations")
    if not isinstance(references, list) or not isinstance(citations, list):
        raise TranscriptError(f"Message {message.get('id')} references must be lists.")

    lines: list[str] = []
    for block in _message_content(message):
        if block.get("type") == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise TranscriptError(f"Text block for message {message.get('id')} is invalid.")
            text = _resolve_inline_markers(text, references)
            if text.strip():
                lines.extend([text, ""])
        else:
            lines.extend(_render_non_text_block(block))

    attachments = message.get("attachments")
    if not isinstance(attachments, list):
        raise TranscriptError(f"Message {message.get('id')} attachments must be a list.")
    if attachments:
        lines.extend(["**Attachments**", ""])
        for attachment in attachments:
            lines.append(f"- {_attachment_label(attachment)}")
        lines.append("")

    rendered_sources = _render_sources([*references, *citations])
    if rendered_sources:
        lines.extend(["**Sources**", "", *rendered_sources, ""])
    return lines


def _resolve_inline_markers(text: str, references: list[object]) -> str:
    # ChatGPT wraps inline citations and widgets in private-use spans starting at U+E200;
    # a reference's `alt` is the site's own Markdown for its span, and None means UI-only.
    for reference in references:
        if not isinstance(reference, dict):
            continue
        matched_text = reference.get("matched_text")
        if isinstance(matched_text, str) and matched_text.startswith("\ue200"):
            alt = reference.get("alt")
            text = text.replace(matched_text, alt if isinstance(alt, str) else "")
    return text


def _render_non_text_block(block: Mapping[str, object]) -> list[str]:
    block_type = str(block.get("type") or "content")
    data = block.get("data")
    if block_type == "audio_transcription":
        transcription = _field_from_mapping(data, "text")
        if transcription is not None:
            return [transcription.strip(), ""] if transcription.strip() else []
    if "image" in block_type:
        pointer = _field_from_mapping(data, "asset_pointer") or _field_from_mapping(data, "url")
        label = f"Image asset: {_single_line(pointer)}" if pointer else "Image asset"
        return [f"> {label}", ""]
    if "audio" in block_type:
        pointer = _field_from_mapping(data, "asset_pointer") or _field_from_mapping(data, "url")
        label = f"Audio asset: {_single_line(pointer)}" if pointer else "Audio asset"
        return [f"> {label}", ""]
    if block_type == "code" and isinstance(data, dict):
        code = data.get("text") or data.get("code")
        if isinstance(code, str):
            language_value = data.get("language")
            language = (
                re.sub(r"[^A-Za-z0-9_+.-]", "", language_value)[:64]
                if isinstance(language_value, str)
                else ""
            )
            return [f"```{language}", code, "```", ""]
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    return [f"**{_single_line(block_type)}**", "", "```json", encoded, "```", ""]


def _attachment_label(value: object) -> str:
    if not isinstance(value, dict):
        return _single_line(str(value))
    name = value.get("name") or value.get("file_name") or value.get("id") or "attachment"
    display_name = _single_line(str(name))
    details = [
        _single_line(str(item))
        for item in (value.get("mime_type"), value.get("size"), value.get("id"))
        if item not in (None, "")
    ]
    suffix = f" ({', '.join(details)})" if details else ""
    url = value.get("url") or value.get("download_url")
    if isinstance(url, str) and _safe_http_url(url):
        return f"[{_escape_link_text(display_name)}]({url}){suffix}"
    return f"{display_name}{suffix}"


def _render_sources(values: list[object]) -> list[str]:
    rendered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        url = _reference_url(value)
        title = value.get("title") or value.get("name") or value.get("attribution") or url
        if isinstance(title, dict):
            title = title.get("title") or title.get("name") or url
        label = _single_line(str(title or value.get("id") or "Source"))
        key = f"{url or ''}\0{label}"
        if key in seen:
            continue
        seen.add(key)
        if url is not None:
            rendered.append(f"- [{_escape_link_text(label)}]({url})")
        else:
            rendered.append(f"- {label}")
    return rendered


def _reference_url(reference: Mapping[str, object]) -> str | None:
    direct = reference.get("url")
    if isinstance(direct, str) and _safe_http_url(direct):
        return direct
    for key in ("source", "attribution", "metadata"):
        nested = reference.get(key)
        if isinstance(nested, dict):
            candidate = nested.get("url")
            if isinstance(candidate, str) and _safe_http_url(candidate):
                return candidate
    return None


def _safe_http_url(value: str) -> bool:
    if any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
    )


def _field_from_mapping(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(key)
        return candidate if isinstance(candidate, str) else None
    return None


def _json_scalar(value: object, label: str) -> str | int | float | bool | None:
    if isinstance(value, float) and not math.isfinite(value):
        raise TranscriptError(f"{label} must be a finite JSON number.")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TranscriptError(f"{label} must be a JSON scalar or null.")


def _copy_json_list(value: object, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TranscriptError(f"{label} must be a list or null.")
    copied = copy.deepcopy(value)
    _validate_json_value(copied, label)
    return copied


def _validate_json_value(value: object, label: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise TranscriptError(f"{label} must contain strict JSON values: {error}") from error


def _expect_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TranscriptError(f"{label} must be an object.")
    result = dict(value)
    if not all(isinstance(key, str) for key in result):
        raise TranscriptError(f"{label} keys must be strings.")
    return result


def _single_line(value: str) -> str:
    return " ".join(value.replace("\r", "\n").splitlines()).strip()


def _escape_link_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _atomic_write(destination: Path, payload: bytes) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _remove_incomplete_export(output: Path, completed: list[Path]) -> None:
    for path in reversed(completed):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return
    try:
        output.rmdir()
    except OSError:
        pass
