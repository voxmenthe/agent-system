from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import chatgpt_transcript as transcript
import download_chatgpt_conversation as cli


CONVERSATION_ID = "conv-12345678"


def _node(
    node_id: str,
    parent: str | None,
    *,
    message_id: str | None = None,
    role: str = "user",
    parts: list[object] | None = None,
    content_type: str = "text",
    metadata: dict[str, object] | None = None,
    create_time: float | None = None,
) -> tuple[str, dict[str, object]]:
    message = None
    if message_id is not None:
        message = {
            "id": message_id,
            "author": {"role": role},
            "create_time": create_time,
            "update_time": create_time,
            "status": "finished_successfully",
            "end_turn": role == "assistant",
            "recipient": "all",
            "content": {
                "content_type": content_type,
                "parts": parts or [],
            },
            "metadata": metadata or {},
        }
    return node_id, {
        "id": node_id,
        "parent": parent,
        "children": [],
        "message": message,
    }


def _conversation() -> dict[str, object]:
    mapping = dict(
        [
            _node("root", None),
            _node(
                "context",
                "root",
                message_id="context-message",
                content_type="user_editable_context",
                parts=["Hidden user context"],
                metadata={"is_user_system_message": True},
            ),
            _node(
                "user-1-node",
                "context",
                message_id="user-1",
                parts=["Initial question"],
                create_time=1.0,
            ),
            _node(
                "assistant-1-node",
                "user-1-node",
                message_id="assistant-1",
                role="assistant",
                parts=["Initial answer"],
                metadata={
                    "model_slug": "gpt-test",
                    "content_references": [
                        {
                            "title": "Primary source",
                            "url": "https://example.com/source",
                        }
                    ],
                },
                create_time=2.0,
            ),
            _node(
                "user-active-node",
                "assistant-1-node",
                message_id="user-active",
                content_type="multimodal_text",
                parts=[
                    {
                        "content_type": "image_asset_pointer",
                        "asset_pointer": "file-service://image-1",
                    },
                    "Question on the active branch",
                ],
                metadata={
                    "attachments": [
                        {
                            "id": "file-1",
                            "name": "notes.txt",
                            "mime_type": "text/plain",
                            "size": 12,
                            "url": "https://[malformed",
                        }
                    ]
                },
                create_time=3.0,
            ),
            _node(
                "thinking",
                "user-active-node",
                message_id="internal-thought",
                role="assistant",
                content_type="thoughts",
                parts=["Hidden reasoning"],
                create_time=3.5,
            ),
            _node(
                "recap",
                "thinking",
                message_id="reasoning-recap",
                role="assistant",
                content_type="reasoning_recap",
                create_time=3.75,
            ),
            _node(
                "assistant-active-node",
                "recap",
                message_id="assistant-active",
                role="assistant",
                parts=["Answer on the active branch"],
                metadata={
                    "citations": [
                        {
                            "title": "Nested source",
                            "metadata": {"url": "https://example.net/nested"},
                        }
                    ]
                },
                create_time=4.0,
            ),
            _node(
                "user-alternate-node",
                "assistant-1-node",
                message_id="user-alternate",
                parts=["Question on the alternate branch"],
                create_time=5.0,
            ),
            _node(
                "assistant-alternate-node",
                "user-alternate-node",
                message_id="assistant-alternate",
                role="assistant",
                parts=["Answer on the alternate branch"],
                create_time=6.0,
            ),
            _node(
                "tool-node",
                "user-1-node",
                message_id="tool-message",
                role="tool",
                parts=["Hidden tool payload"],
                create_time=2.5,
            ),
        ]
    )
    mapping["recap"]["message"]["content"] = {
        "content_type": "reasoning_recap",
        "content": "Worked for 59s",
    }
    return {
        "conversation_id": CONVERSATION_ID,
        "title": "Branching Example\nTitle",
        "create_time": 1.0,
        "update_time": 6.0,
        "current_node": "assistant-active-node",
        "mapping": mapping,
    }


class TranscriptTests(unittest.TestCase):
    def test_parses_only_private_conversation_urls_or_bare_ids(self) -> None:
        valid = {
            CONVERSATION_ID: CONVERSATION_ID,
            f"https://chatgpt.com/c/{CONVERSATION_ID}": CONVERSATION_ID,
            f"https://chat.openai.com/c/{CONVERSATION_ID}?model=gpt-test": CONVERSATION_ID,
        }
        for value, expected in valid.items():
            with self.subTest(value=value):
                self.assertEqual(expected, transcript.parse_conversation_id(value))

        invalid = (
            "",
            "short",
            f"http://chatgpt.com/c/{CONVERSATION_ID}",
            f"https://evil.example/c/{CONVERSATION_ID}",
            f"https://chatgpt.com/share/{CONVERSATION_ID}",
            f"https://chatgpt.com/c/{CONVERSATION_ID}/extra",
            "https://user@chatgpt.com/c/conv-12345678",
            "https://[malformed",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(transcript.TranscriptError):
                    transcript.parse_conversation_id(value)

    def test_normalizes_active_path_and_all_visible_alternate_messages(self) -> None:
        bundle = transcript.build_export(
            _conversation(),
            CONVERSATION_ID,
            exported_at="2026-08-07T12:00:00Z",
        )
        normalized = bundle.normalized
        self.assertEqual(
            ["user-1", "assistant-1", "user-active", "assistant-active"],
            normalized["active_message_ids"],
        )
        self.assertEqual(
            {
                "active_messages": 4,
                "alternate_messages": 2,
                "visible_messages": 6,
                "source_nodes": 11,
            },
            normalized["counts"],
        )

        messages = {message["id"]: message for message in normalized["messages"]}
        self.assertEqual(
            {
                "user-1",
                "assistant-1",
                "user-active",
                "assistant-active",
                "user-alternate",
                "assistant-alternate",
            },
            set(messages),
        )
        self.assertEqual("user-active", messages["assistant-active"]["parent_id"])
        self.assertEqual("assistant-1", messages["user-alternate"]["parent_id"])
        self.assertFalse(messages["assistant-alternate"]["on_active_branch"])
        self.assertEqual(
            "file-1",
            messages["user-active"]["attachments"][0]["id"],
        )
        self.assertEqual(
            "multimodal_text",
            messages["user-active"]["content_type"],
        )

        self.assertIn("# Branching Example Title", bundle.markdown)
        self.assertIn("## Active conversation", bundle.markdown)
        self.assertIn("## Alternate branches", bundle.markdown)
        self.assertIn("file-service://image-1", bundle.markdown)
        self.assertIn("notes.txt", bundle.markdown)
        self.assertIn("https://example.com/source", bundle.markdown)
        self.assertIn("https://example.net/nested", bundle.markdown)
        self.assertNotIn("https://[malformed", bundle.markdown)
        self.assertNotIn("Hidden reasoning", bundle.markdown)
        self.assertNotIn("Worked for 59s", bundle.markdown)
        self.assertNotIn("Hidden tool payload", bundle.markdown)
        self.assertNotIn("message_id", bundle.markdown)
        self.assertNotIn("assistant-active", bundle.markdown)
        self.assertNotIn("1970-01-01", bundle.markdown)
        self.assertNotIn("2026-08-07", bundle.markdown)
        self.assertIn('Replies to: "Initial answer"', bundle.markdown)

    def test_markdown_merges_speaker_runs_and_omits_empty_messages(self) -> None:
        mapping = dict(
            [
                _node("root", None),
                _node("user-node", "root", message_id="user", parts=["Question"]),
                _node(
                    "empty-node",
                    "user-node",
                    message_id="empty",
                    role="assistant",
                    parts=[""],
                    metadata={"model_slug": "gpt-silent"},
                ),
                _node(
                    "first-node",
                    "empty-node",
                    message_id="first",
                    role="assistant",
                    parts=["First part"],
                    metadata={"model_slug": "gpt-test"},
                ),
                _node(
                    "second-node",
                    "first-node",
                    message_id="second",
                    role="assistant",
                    parts=["Second part"],
                    metadata={"model_slug": "gpt-test"},
                ),
            ]
        )
        conversation = {
            "conversation_id": CONVERSATION_ID,
            "current_node": "second-node",
            "mapping": mapping,
        }

        markdown = transcript.build_export(conversation, CONVERSATION_ID).markdown

        self.assertNotIn("gpt-silent", markdown)
        self.assertEqual(1, markdown.count("### Assistant (gpt-test)"))
        self.assertIn("First part\n\nSecond part", markdown)

    def test_markdown_resolves_inline_citation_markers(self) -> None:
        web_marker = "\ue200cite\ue202turn0view0\ue201"
        file_marker = "\ue200filecite\ue202turn1file0\ue202L4-L9\ue201"
        mapping = dict(
            [
                _node("root", None),
                _node(
                    "assistant-node",
                    "root",
                    message_id="assistant",
                    role="assistant",
                    parts=[f"Web claim {web_marker}. File claim {file_marker}."],
                    metadata={
                        "content_references": [
                            {
                                "type": "grouped_webpages",
                                "matched_text": web_marker,
                                "alt": "([arXiv](https://arxiv.org/abs/1))",
                            },
                            {"type": "file", "matched_text": file_marker, "alt": None},
                            {"type": "sources_footnote", "matched_text": " ", "alt": ""},
                        ]
                    },
                ),
            ]
        )
        conversation = {
            "conversation_id": CONVERSATION_ID,
            "current_node": "assistant-node",
            "mapping": mapping,
        }

        markdown = transcript.build_export(conversation, CONVERSATION_ID).markdown

        self.assertIn("Web claim ([arXiv](https://arxiv.org/abs/1)). File claim .", markdown)
        self.assertNotIn("\ue200", markdown)

    def test_preserves_empty_but_visible_messages(self) -> None:
        mapping = dict(
            [
                _node("root", None),
                _node(
                    "empty-user-node",
                    "root",
                    message_id="empty-user",
                    parts=[],
                    create_time=1.0,
                ),
                _node(
                    "empty-assistant-node",
                    "empty-user-node",
                    message_id="empty-assistant",
                    role="assistant",
                    parts=[],
                    create_time=2.0,
                ),
            ]
        )
        conversation = {
            "conversation_id": CONVERSATION_ID,
            "current_node": "empty-assistant-node",
            "mapping": mapping,
        }
        bundle = transcript.build_export(conversation, CONVERSATION_ID)

        self.assertEqual(
            ["empty-user", "empty-assistant"],
            bundle.normalized["active_message_ids"],
        )
        self.assertEqual(2, bundle.normalized["counts"]["visible_messages"])

    def test_renders_audio_transcription_text_in_markdown(self) -> None:
        mapping = dict(
            [
                _node("root", None),
                _node(
                    "audio-node",
                    "root",
                    message_id="audio-message",
                    create_time=1.0,
                ),
            ]
        )
        mapping["audio-node"]["message"]["content"] = {
            "content_type": "audio_transcription",
            "direction": "in",
            "text": "Words visible in the ChatGPT transcript.",
        }
        conversation = {
            "conversation_id": CONVERSATION_ID,
            "current_node": "audio-node",
            "mapping": mapping,
        }

        bundle = transcript.build_export(conversation, CONVERSATION_ID)

        self.assertEqual(
            [
                {
                    "type": "audio_transcription",
                    "data": {
                        "direction": "in",
                        "text": "Words visible in the ChatGPT transcript.",
                    },
                }
            ],
            bundle.normalized["messages"][0]["content"],
        )
        self.assertIn("Words visible in the ChatGPT transcript.", bundle.markdown)
        self.assertNotIn("> Audio asset", bundle.markdown)

    def test_rejects_mismatches_cycles_and_non_json_values(self) -> None:
        mismatched = _conversation()
        mismatched["conversation_id"] = "different-1234"
        with self.assertRaisesRegex(transcript.TranscriptError, "does not match"):
            transcript.build_export(mismatched, CONVERSATION_ID)

        cyclic = _conversation()
        cyclic["mapping"]["assistant-active-node"]["parent"] = "assistant-active-node"
        with self.assertRaisesRegex(transcript.TranscriptError, "parent cycle"):
            transcript.build_export(cyclic, CONVERSATION_ID)

        non_json = _conversation()
        user_message = non_json["mapping"]["user-active-node"]["message"]
        user_message["metadata"]["attachments"][0]["size"] = float("nan")
        with self.assertRaisesRegex(transcript.TranscriptError, "strict JSON"):
            transcript.build_export(non_json, CONVERSATION_ID)

        with self.assertRaisesRegex(transcript.TranscriptError, "timestamp"):
            transcript.build_export(
                _conversation(),
                CONVERSATION_ID,
                exported_at="",
            )

    def test_writes_verified_bundle_and_refuses_existing_destination(self) -> None:
        bundle = transcript.build_export(
            _conversation(),
            CONVERSATION_ID,
            exported_at="2026-08-07T12:00:00Z",
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            manifest = transcript.write_export(destination, bundle)
            markdown_name = "branching-example-title.md"
            json_name = "branching-example-title.json"
            manifest_name = "branching-example-title.manifest.json"

            self.assertEqual(
                {markdown_name, json_name, manifest_name},
                {path.name for path in destination.iterdir()},
            )
            stored_manifest = json.loads((destination / manifest_name).read_text())
            self.assertEqual(manifest, stored_manifest)
            for name in (markdown_name, json_name):
                payload = (destination / name).read_bytes()
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(),
                    stored_manifest["files"][name]["sha256"],
                )

            before = {
                path.name: path.read_bytes()
                for path in destination.iterdir()
            }
            with self.assertRaisesRegex(transcript.TranscriptError, "refusing to overwrite"):
                transcript.write_export(destination, bundle)
            self.assertEqual(
                before,
                {
                    path.name: path.read_bytes()
                    for path in destination.iterdir()
                },
            )

    def test_rejects_unsafe_conversation_id_before_writing(self) -> None:
        bundle = transcript.build_export(_conversation(), CONVERSATION_ID)
        bundle.normalized["source"]["conversation_id"] = "../escape"

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            with self.assertRaisesRegex(transcript.TranscriptError, "conversation id"):
                transcript.write_export(destination, bundle)
            self.assertFalse(destination.exists())

    def test_removes_only_the_incomplete_new_export_on_write_failure(self) -> None:
        bundle = transcript.build_export(_conversation(), CONVERSATION_ID)
        real_atomic_write = transcript._atomic_write

        def fail_on_json(destination: Path, payload: bytes) -> None:
            if destination.name == "branching-example-title.json":
                raise OSError("synthetic disk failure")
            real_atomic_write(destination, payload)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            with mock.patch.object(
                transcript,
                "_atomic_write",
                side_effect=fail_on_json,
            ):
                with self.assertRaisesRegex(
                    transcript.ExportWriteError,
                    "synthetic disk failure",
                ):
                    transcript.write_export(destination, bundle)
            self.assertFalse(destination.exists())


class FakeBridge:
    class ChatGPTError(Exception):
        pass

    class NotLoggedInError(ChatGPTError):
        pass

    class JSExecBlockedError(ChatGPTError):
        pass

    class ChatGPTTimeoutError(ChatGPTError):
        pass

    class ChatGPTReadThrottledError(ChatGPTTimeoutError):
        pass

    def __init__(self) -> None:
        self.target = (17, 23)
        self.session_targets: list[tuple[int, int]] = []
        self.fetches: list[tuple[str, tuple[int, int]]] = []
        self.failure: Exception | None = None

    def ensure_chatgpt_available(self) -> tuple[int, int]:
        if self.failure is not None:
            raise self.failure
        return self.target

    def get_session(self, *, target: tuple[int, int]) -> dict[str, str]:
        self.session_targets.append(target)
        return {"accessToken": "never-written"}

    def fetch_conversation(
        self,
        conversation_id: str,
        *,
        target: tuple[int, int],
    ) -> dict[str, object]:
        self.fetches.append((conversation_id, target))
        return _conversation()


class CliTests(unittest.TestCase):
    def test_download_uses_one_target_and_writes_no_session_material(self) -> None:
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            result = cli.download(CONVERSATION_ID, destination, bridge)

            self.assertEqual([bridge.target], bridge.session_targets)
            self.assertEqual([(CONVERSATION_ID, bridge.target)], bridge.fetches)
            self.assertEqual(CONVERSATION_ID, result["conversation_id"])
            all_content = b"".join(
                path.read_bytes()
                for path in destination.iterdir()
            )
            self.assertNotIn(b"never-written", all_content)

    def test_main_maps_known_bridge_failures_and_reraises_unknown_ones(self) -> None:
        bridge = FakeBridge()
        cases = (
            (bridge.NotLoggedInError("login required"), cli.EXIT_NOT_LOGGED_IN),
            (bridge.JSExecBlockedError("blocked"), cli.EXIT_JS_BLOCKED),
            (bridge.ChatGPTTimeoutError("timeout"), cli.EXIT_TEMPORARY_READ_FAILURE),
            (bridge.ChatGPTError("bridge"), cli.EXIT_ERROR),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for index, (error, expected) in enumerate(cases):
                with self.subTest(error=type(error).__name__):
                    bridge.failure = error
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        result = cli.main(
                            [
                                CONVERSATION_ID,
                                "--output",
                                str(Path(temporary) / f"export-{index}"),
                            ],
                            bridge=bridge,
                        )
                    self.assertEqual(expected, result)
                    self.assertIn(str(error), stderr.getvalue())

            bridge.failure = RuntimeError("unexpected")
            with self.assertRaisesRegex(RuntimeError, "unexpected"):
                cli.main(
                    [
                        CONVERSATION_ID,
                        "--output",
                        str(Path(temporary) / "unexpected"),
                    ],
                    bridge=bridge,
                )

    def test_main_prints_a_machine_readable_success_summary(self) -> None:
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = cli.main(
                    [CONVERSATION_ID, "--output", str(destination)],
                    bridge=bridge,
                )
            self.assertEqual(cli.EXIT_OK, result)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(CONVERSATION_ID, summary["conversation_id"])
            self.assertEqual(str(destination.resolve()), summary["output_directory"])
            self.assertEqual(
                [
                    "branching-example-title.md",
                    "branching-example-title.json",
                    "branching-example-title.manifest.json",
                ],
                summary["files"],
            )

    def test_main_supports_explicit_slug_override(self) -> None:
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = cli.main(
                    [
                        CONVERSATION_ID,
                        "--output",
                        str(destination),
                        "--slug",
                        "custom-slug-override",
                    ],
                    bridge=bridge,
                )
            self.assertEqual(cli.EXIT_OK, result)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(
                [
                    "custom-slug-override.md",
                    "custom-slug-override.json",
                    "custom-slug-override.manifest.json",
                ],
                summary["files"],
            )

    def test_slugify_title_cases(self) -> None:
        self.assertEqual(
            transcript.slugify_title("Research MAI 1 Paper", fallback="fallback-id"),
            "research-mai-1-paper",
        )
        self.assertEqual(
            transcript.slugify_title("rlenv explorations ", fallback="fallback-id"),
            "rlenv-explorations",
        )
        self.assertEqual(
            transcript.slugify_title("TurnSight - turn-level hindisi", fallback="fallback-id"),
            "turnsight-turn-level-hindisi",
        )
        self.assertEqual(
            transcript.slugify_title("DL-research-v1-xtra-res-260824", fallback="fallback-id"),
            "dl-research-v1-xtra-res-260824",
        )
        self.assertEqual(
            transcript.slugify_title("New chat", fallback="fallback-id"),
            "fallback-id",
        )
        self.assertEqual(
            transcript.slugify_title("ChatGPT conversation conv-123", fallback="fallback-id"),
            "fallback-id",
        )
        self.assertEqual(
            transcript.slugify_title("", fallback="fallback-id"),
            "fallback-id",
        )
        self.assertEqual(
            transcript.slugify_title(None, fallback="fallback-id"),
            "fallback-id",
        )
        self.assertEqual(
            transcript.slugify_title("翻譯請求", fallback="fallback-id"),
            "翻譯請求",
        )

    def test_main_maps_local_write_failure_without_calling_it_usage_error(self) -> None:
        bridge = FakeBridge()
        stderr = io.StringIO()
        with mock.patch.object(
            cli,
            "download",
            side_effect=transcript.ExportWriteError("disk unavailable"),
        ):
            with redirect_stderr(stderr):
                result = cli.main(
                    [CONVERSATION_ID, "--output", "unused-output"],
                    bridge=bridge,
                )
        self.assertEqual(cli.EXIT_ERROR, result)
        self.assertIn("disk unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
