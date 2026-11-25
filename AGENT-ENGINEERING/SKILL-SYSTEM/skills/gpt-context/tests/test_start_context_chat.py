from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "start_context_chat.py"
SPEC = importlib.util.spec_from_file_location("start_context_chat", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_validate_files_preserves_first_file_for_title(tmp_path: Path) -> None:
    first = tmp_path / "first context.md"
    second = tmp_path / "second.pdf"
    first.write_text("first", encoding="utf-8")
    second.write_bytes(b"second")

    assert module.validate_files([first, second]) == [first.resolve(), second.resolve()]


@pytest.mark.parametrize(
    ("initial_mode", "mode_after_upload", "succeeds"),
    [
        ("chat", None, True),
        ("work", None, True),
        ("work-locked", None, False),
        ("loading", None, False),
        ("unknown", None, False),
        ("ambiguous", None, False),
        ("chat", "work", False),
        ("chat", "unknown", False),
    ],
)
def test_context_seeding_requires_chat_at_upload_and_send(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_mode: str,
    mode_after_upload: str | None,
    succeeds: bool,
) -> None:
    source = tmp_path / "context.md"
    source.write_text("context", encoding="utf-8")
    state = {"mode": initial_mode, "sent": False}
    effects: list[str] = []
    upload = {"name": source.name, "size": 7, "mime": "text/markdown"}
    clock = iter(value / 4 for value in range(1000))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.cgpt, "_send_lock", lambda: contextlib.nullcontext(True))
    monkeypatch.setattr(
        module, "_open_fresh_target", lambda _progress: ((1, 2), {"old"})
    )

    def mode_state(_target: tuple[int, int]) -> dict[str, object]:
        return {
            "has_mode_controls": True,
            "chat_selected": state["mode"] in {"chat", "ambiguous", "loading"},
            "work_selected": state["mode"] in {"work", "work-locked", "ambiguous"},
            "composer_ready": state["mode"] != "loading",
            "pill": "Thinking" if state["mode"] == "chat" else "5.6 Sol",
        }

    def browser(_target: tuple[int, int], script: str, **_kwargs: object) -> str:
        if "chat.click()" in script:
            if state["mode"] != "work-locked":
                state["mode"] = "chat"
            return ""
        if "editor.innerHTML" in script:
            assert state["mode"] == "chat", "Must verify Chat before staging the prompt"
            return ""
        if "prompt_visible" in script:
            return json.dumps(
                {
                    "path": "/c/cid" if state["sent"] else "/",
                    "composer": "" if state["sent"] else module.PROMPT,
                    "prompt_visible": state["sent"],
                }
            )
        if "button.click()" in script:
            assert state["mode"] == "chat", "Must verify Chat before sending"
            effects.append("send")
            state["sent"] = True
            return "click"
        pytest.fail("Context seeding must not select Work or change the selected model")

    def attach(_paths: list[Path], **_kwargs: object) -> list[dict[str, object]]:
        assert state["mode"] == "chat", "Must verify Chat before uploading"
        effects.append("upload")
        if mode_after_upload is not None:
            state["mode"] = mode_after_upload
        return [upload]

    monkeypatch.setattr(module.cgpt, "_composer_mode_state", mode_state)
    monkeypatch.setattr(module.cgpt, "_js", browser)
    monkeypatch.setattr(module.cgpt, "attach_files", attach)
    monkeypatch.setattr(
        module.cgpt, "capture_conversation_for_prompt", lambda *_a, **_kw: "cid"
    )
    monkeypatch.setattr(module.cgpt, "prepare_continue_tab", lambda _cid: (1, 2))
    monkeypatch.setattr(
        module.cgpt, "verify_user_prompt_present", lambda *_a, **_kw: True
    )
    monkeypatch.setattr(
        module.cgpt, "fetch_conversation", lambda *_a, **_kw: {"mapping": {}}
    )
    monkeypatch.setattr(
        module.cgpt,
        "_matching_user_msg",
        lambda *_a, **_kw: {
            "metadata": {
                "attachments": [
                    {"name": source.name, "size": 7, "mime_type": "text/markdown"}
                ]
            },
        },
    )
    monkeypatch.setattr(
        module, "rename_conversation", lambda *_a, **_kw: effects.append("rename")
    )

    if succeeds:
        result = module.start_context_chat([source])
        assert result.verified["chat_mode"] is True
        assert result.model_slug is None
        assert result.stored_thinking_effort is None
        assert effects == ["upload", "send", "rename"]
    else:
        with pytest.raises(module.cgpt.ChatGPTError, match="Chat"):
            module.start_context_chat([source])
        assert effects == (["upload"] if mode_after_upload else [])


@pytest.mark.parametrize(
    "pill", ["Instant", "Thinking", "Pro", "5.6 Sol", "", "Unknown"]
)
def test_mode_guard_without_radio_controls(
    monkeypatch: pytest.MonkeyPatch,
    pill: str,
) -> None:
    monkeypatch.setattr(
        module.cgpt,
        "_composer_mode_state",
        lambda _target: {
            "has_mode_controls": False,
            "chat_selected": False,
            "work_selected": False,
            "composer_ready": True,
            "pill": pill,
        },
    )
    if pill in {"Instant", "Thinking", "Pro"}:
        module._require_chat_mode(target=(1, 2))
    else:
        with pytest.raises(module.ContextChatError, match="Chat mode"):
            module._require_chat_mode(target=(1, 2))


@pytest.mark.parametrize(
    ("model_slug", "effort"),
    [("chat-model", "standard"), ("chat-model", None), (None, None)],
)
def test_submission_evidence_checks_files_without_pinning_model_or_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_slug: str | None,
    effort: str | None,
) -> None:
    first = tmp_path / "alpha.md"
    second = tmp_path / "beta.pdf"
    first.write_text("alpha", encoding="utf-8")
    second.write_bytes(b"beta")
    message = {
        "metadata": {
            "working_turn_id": "turn-1",
            "attachments": [
                {"name": "alpha.md", "size": 5, "mime_type": "text/markdown"},
                {"name": "beta.pdf", "size": 4, "mime_type": "application/pdf"},
            ],
        }
    }
    conversation = {
        "default_model_slug": model_slug,
        "mapping": {
            "assistant": {
                "message": {
                    "author": {"role": "assistant"},
                    "metadata": {
                        "working_turn_id": "turn-1",
                        "model_slug": model_slug,
                        "thinking_effort": effort,
                    },
                }
            }
        },
    }
    monkeypatch.setattr(
        module.cgpt,
        "fetch_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        module.cgpt, "_matching_user_msg", lambda *_args, **_kwargs: message
    )

    evidence = module.wait_for_submission_evidence(
        "cid",
        [
            {"name": "alpha.md", "size": 5, "mime": "text/markdown"},
            {"name": "beta.pdf", "size": 4, "mime": "application/pdf"},
        ],
        target=(1, 2),
        timeout=0.1,
    )

    assert evidence == module.SubmissionEvidence(
        model_slug=model_slug,
        thinking_effort=effort,
        attachment_names=("alpha.md", "beta.pdf"),
    )


@pytest.mark.parametrize(
    "model_source",
    ["user", "assistant", "conversation", "resolved", "assistant-with-default"],
)
def test_submission_evidence_rejects_work_metadata(
    monkeypatch: pytest.MonkeyPatch,
    model_source: str,
) -> None:
    message = {"metadata": {"attachments": []}}
    assistant = {"author": {"role": "assistant"}, "metadata": {}}
    conversation = {"mapping": {"assistant": {"message": assistant}}}
    metadata = {
        "user": message["metadata"],
        "assistant": assistant["metadata"],
        "conversation": conversation,
        "resolved": message["metadata"],
        "assistant-with-default": assistant["metadata"],
    }[model_source]
    key = "default_model_slug" if model_source == "conversation" else "model_slug"
    if model_source == "resolved":
        metadata["model_slug"] = "gpt-5.6-sol"
        key = "resolved_model_slug"
    if model_source == "assistant-with-default":
        conversation["default_model_slug"] = "gpt-5.6-sol"
    metadata[key] = "gpt-5.6-sol-wm"
    monkeypatch.setattr(
        module.cgpt, "fetch_conversation", lambda *_a, **_kw: conversation
    )
    monkeypatch.setattr(module.cgpt, "_matching_user_msg", lambda *_a, **_kw: message)

    with pytest.raises(module.ContextChatError, match="Work model metadata"):
        module.wait_for_submission_evidence("cid", [], target=(1, 2))


@pytest.mark.parametrize(
    "attachment",
    [
        {"name": "wrong.md", "size": 7, "mime_type": "text/markdown"},
        {"name": "context.md", "size": 99, "mime_type": "text/markdown"},
        {"name": "context.md", "size": 7, "mime_type": "application/pdf"},
    ],
)
def test_submission_evidence_still_requires_matching_attachments(
    monkeypatch: pytest.MonkeyPatch,
    attachment: dict[str, object],
) -> None:
    clock = iter(value / 4 for value in range(100))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module.cgpt, "fetch_conversation", lambda *_a, **_kw: {})
    monkeypatch.setattr(
        module.cgpt,
        "_matching_user_msg",
        lambda *_a, **_kw: {
            "metadata": {"attachments": [attachment]},
        },
    )
    with pytest.raises(module.ContextChatError, match="required prompt/attachments"):
        module.wait_for_submission_evidence(
            "cid",
            [{"name": "context.md", "size": 7, "mime": "text/markdown"}],
            target=(1, 2),
            timeout=1,
        )


@pytest.mark.parametrize(
    ("click_sends", "drift_at", "expected_actions"),
    [
        (True, None, ["click"]),
        (False, None, ["click", "keyboard"]),
        (False, "typing", []),
        (False, "click", ["click"]),
    ],
)
def test_context_send_checks_mode_and_avoids_duplicate_submission(
    monkeypatch: pytest.MonkeyPatch,
    click_sends: bool,
    drift_at: str | None,
    expected_actions: list[str],
) -> None:
    actions: list[str] = []
    state = {"typed": False, "sent": False, "mode": "chat"}

    def fake_js(_target: tuple[int, int], script: str, **_kwargs: object) -> str:
        if "editor.innerHTML" in script:
            state["typed"] = True
            if drift_at == "typing":
                state["mode"] = "work"
            return ""
        if "prompt_visible" in script:
            return json.dumps(
                {
                    "path": "/c/cid" if state["sent"] else "/",
                    "composer": "" if state["sent"] else module.PROMPT,
                    "prompt_visible": state["sent"],
                }
            )
        if "button.click()" in script or "KeyboardEvent('keydown'" in script:
            assert state["typed"] is True
            assert state["sent"] is False
            assert state["mode"] == "chat"
            method = "click" if "button.click()" in script else "keyboard"
            actions.append(method)
            state["sent"] = click_sends or method == "keyboard"
            if drift_at == "click":
                state["mode"] = "work"
            return method
        pytest.fail("Unexpected browser operation")

    monkeypatch.setattr(module.cgpt, "_js", fake_js)
    monkeypatch.setattr(
        module.cgpt,
        "_composer_mode_state",
        lambda _target: {
            "has_mode_controls": True,
            "chat_selected": state["mode"] == "chat",
            "work_selected": state["mode"] == "work",
            "composer_ready": True,
        },
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    if drift_at is None:
        module.send_context_prompt(module.PROMPT, target=(1, 2))
        assert state["sent"] is True
    else:
        with pytest.raises(module.ContextChatError, match="Chat mode"):
            module.send_context_prompt(module.PROMPT, target=(1, 2))
        assert state["sent"] is False
    assert actions == expected_actions


def test_attachment_match_accepts_portal_collision_suffixes() -> None:
    expected = [
        {"name": "SKILL.md", "size": 12, "mime": "text/markdown"},
        {"name": "report.tar.gz", "size": 20, "mime": "application/gzip"},
    ]
    actual = [
        {"name": "report.tar(2).gz", "size": 20, "mime_type": "application/gzip"},
        {"name": "SKILL(1).md", "size": 12, "mime_type": "text/markdown"},
    ]

    assert module._attachments_match(expected, actual) is True


def test_rename_uses_patch_and_waits_for_stable_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expressions: list[str] = []

    def fake_async(expression: str, **_kwargs: object) -> dict[str, object]:
        expressions.append(expression)
        return {"ok": True, "status": 200, "body": ""}

    monkeypatch.setattr(module.cgpt, "_run_js_async", fake_async)
    monkeypatch.setattr(
        module.cgpt,
        "fetch_conversation",
        lambda *_args, **_kwargs: {"mapping": {}, "title": "context.md"},
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    module.rename_conversation("cid", "context.md", target=(1, 2))

    assert "method:'PATCH'" in expressions[0]
    assert "JSON.stringify({title})" in expressions[0]
    assert "context.md" in expressions[0]


def test_rename_reapplies_after_delayed_auto_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patches: list[str] = []
    titles = iter(
        [
            "context.md",
            "Auto title",
            "Auto title",
            "Auto title",
            "context.md",
            "context.md",
            "context.md",
            "context.md",
        ]
    )

    def fake_async(expression: str, **_kwargs: object) -> dict[str, object]:
        patches.append(expression)
        return {"ok": True, "status": 200, "body": ""}

    monkeypatch.setattr(module.cgpt, "_run_js_async", fake_async)
    monkeypatch.setattr(
        module.cgpt,
        "fetch_conversation",
        lambda *_args, **_kwargs: {"mapping": {}, "title": next(titles)},
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    module.rename_conversation("cid", "context.md", target=(1, 2))

    assert len(patches) == 2


def test_start_context_chat_runs_one_new_verified_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "context.md"
    second = tmp_path / "diagram.png"
    first.write_text("context", encoding="utf-8")
    second.write_bytes(b"image")
    calls: list[str] = []

    @contextlib.contextmanager
    def lock():
        calls.append("lock")
        yield True

    monkeypatch.setattr(module.cgpt, "_send_lock", lock)
    monkeypatch.setattr(
        module, "_open_fresh_target", lambda _progress: ((1, 2), {"old"})
    )
    monkeypatch.setattr(
        module.cgpt,
        "ensure_chat_mode",
        lambda **_kwargs: calls.append("select"),
    )
    monkeypatch.setattr(
        module.cgpt,
        "attach_files",
        lambda paths, **_kwargs: (
            calls.append("attach:" + ",".join(p.name for p in paths))
            or [
                {"name": "context.md", "size": 7, "mime": "text/markdown"},
                {"name": "diagram.png", "size": 5, "mime": "image/png"},
            ]
        ),
    )
    monkeypatch.setattr(
        module,
        "send_context_prompt",
        lambda prompt, **_kwargs: calls.append("prompt:" + prompt),
    )
    monkeypatch.setattr(
        module.cgpt,
        "capture_conversation_for_prompt",
        lambda *_args, **_kwargs: "cid-123",
    )
    monkeypatch.setattr(
        module.cgpt, "verify_user_prompt_present", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(module.cgpt, "prepare_continue_tab", lambda _cid: (1, 2))
    monkeypatch.setattr(
        module,
        "rename_conversation",
        lambda _cid, title, **_kwargs: calls.append("rename:" + title),
    )
    monkeypatch.setattr(
        module,
        "wait_for_submission_evidence",
        lambda *_args, **_kwargs: (
            calls.append("verify")
            or module.SubmissionEvidence(
                model_slug="chat-model",
                thinking_effort="extended",
                attachment_names=("context.md", "diagram.png"),
            )
        ),
    )

    monkeypatch.setattr(
        module.cgpt,
        "_composer_mode_state",
        lambda _target: {
            "chat_selected": True,
            "work_selected": False,
            "composer_ready": True,
        },
    )
    result = module.start_context_chat([first, second])

    assert calls == [
        "lock",
        "select",
        "attach:context.md,diagram.png",
        "prompt:" + module.PROMPT,
        "verify",
        "rename:context.md",
    ]
    assert result.title == "context.md"
    assert result.conversation_url == "https://chatgpt.com/c/cid-123"
    assert result.uploaded_files == ("context.md", "diagram.png")
    assert result.stored_attachment_names == ("context.md", "diagram.png")
    assert result.thinking_effort == "extended"
    assert result.stored_thinking_effort == "extended"
    assert result.verified == {
        "prompt": True,
        "attachments": True,
        "chat_mode": True,
        "title": True,
    }


def test_main_prints_machine_readable_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.md"
    source.write_text("context", encoding="utf-8")
    result = module.ContextChatResult(
        status="ok",
        conversation_id="cid",
        conversation_url="https://chatgpt.com/c/cid",
        title="input.md",
        uploaded_files=("input.md",),
        stored_attachment_names=("input.md",),
        prompt=module.PROMPT,
        model_slug="chat-model",
        thinking_effort="extended",
        stored_thinking_effort="extended",
        mode="chat",
        verified={
            "prompt": True,
            "attachments": True,
            "chat_mode": True,
            "title": True,
        },
    )
    monkeypatch.setattr(module, "start_context_chat", lambda *_args, **_kwargs: result)

    assert module.main(["--quiet", str(source)]) == 0
    assert json.loads(capsys.readouterr().out) == result.to_json_dict()
