from __future__ import annotations

import argparse
import contextlib
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import chatgpt_ask  # noqa: E402
import chatgpt_lib as cgpt  # noqa: E402


def test_submit_returns_after_verified_send_without_polling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_state = {"active": False}
    call_order: list[str] = []
    attachment = tmp_path / "context.md"
    attachment.write_text("review context", encoding="utf-8")

    @contextlib.contextmanager
    def fake_send_lock():
        lock_state["active"] = True
        try:
            yield True
        finally:
            lock_state["active"] = False

    monkeypatch.setattr(cgpt, "_send_lock", fake_send_lock)
    monkeypatch.setattr(cgpt, "ensure_chatgpt_available", lambda: (1, 1))
    monkeypatch.setattr(
        cgpt,
        "_new_tab_in_dedicated_window",
        lambda _url: (1, 2),
    )
    monkeypatch.setattr(cgpt, "_activate_tab", lambda *_target: None)
    monkeypatch.setattr(cgpt, "_wait_tab_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cgpt, "get_session", lambda **_kwargs: {})
    monkeypatch.setattr(cgpt, "recent_conversation_ids", lambda **_kwargs: [])
    monkeypatch.setattr(
        cgpt,
        "ensure_chat_mode",
        lambda **_kwargs: (assert_lock_held(lock_state), call_order.append("chat")),
    )
    monkeypatch.setattr(
        cgpt,
        "attach_files",
        lambda *_args, **_kwargs: (
            assert_lock_held(lock_state),
            call_order.append("attach"),
        ),
    )
    monkeypatch.setattr(
        cgpt,
        "select_pro",
        lambda **_kwargs: (assert_lock_held(lock_state), call_order.append("pro")),
    )
    monkeypatch.setattr(
        cgpt,
        "send_prompt",
        lambda *_args, **_kwargs: (
            assert_lock_held(lock_state),
            call_order.append("send"),
        ),
    )
    monkeypatch.setattr(
        cgpt,
        "capture_conversation_for_prompt",
        lambda *_args, **_kwargs: "conversation-123",
    )
    monkeypatch.setattr(cgpt, "_save_session", lambda _cid: None)
    monkeypatch.setattr(
        cgpt,
        "wait_for_response",
        lambda **_kwargs: pytest.fail("submit() must not poll the response"),
    )

    submission = cgpt.submit("Explain this article.", files=[attachment])

    assert submission == cgpt.Submission(conversation_id="conversation-123")
    assert call_order == ["chat", "attach", "pro", "send"]
    assert lock_state["active"] is False


def assert_lock_held(lock_state: dict[str, bool]) -> None:
    assert lock_state["active"] is True


def test_send_only_cli_submits_without_waiting_for_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    article = tmp_path / "article.md"
    article.write_text("# Article\n")
    args = argparse.Namespace(
        prompt="Explain this article.",
        prompt_file=None,
        fetch=None,
        files=[article],
        output=None,
        send_only=True,
        continue_chat=False,
        conversation_id=None,
        conversation_url=None,
        timeout=1200.0,
        json_out=True,
        quiet=True,
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(chatgpt_ask, "parse_args", lambda: args)
    monkeypatch.setattr(chatgpt_ask, "_reserve_send_slot", lambda _prompt: 0.0)

    def fake_submit(**kwargs: object) -> cgpt.Submission:
        calls.append(kwargs)
        return cgpt.Submission(conversation_id="conversation-123")

    monkeypatch.setattr(cgpt, "submit", fake_submit)
    monkeypatch.setattr(
        cgpt,
        "ask",
        lambda **_kwargs: pytest.fail("send-only must not call ask()"),
    )

    assert chatgpt_ask.main() == chatgpt_ask.EXIT_OK
    assert calls == [
        {
            "prompt": "Explain this article.",
            "files": [article],
            "new_chat": True,
            "conversation_id": None,
            "on_progress": calls[0]["on_progress"],
        }
    ]
    metadata = json.loads(capsys.readouterr().out)
    assert metadata == {
        "status": "submitted",
        "conversation_id": "conversation-123",
        "conversation_url": "https://chatgpt.com/c/conversation-123",
        "duration_seconds": metadata["duration_seconds"],
        "attached_files": [str(article)],
    }


def test_send_only_rejects_response_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "chatgpt_ask.py",
            "--prompt",
            "Question",
            "--send-only",
            "--output",
            "answer.md",
        ],
    )

    with pytest.raises(SystemExit) as error:
        chatgpt_ask.parse_args()

    assert error.value.code == 2


def test_pro_selection_has_no_effort_step(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[str] = []
    state = {"selected": False, "menu": "closed"}

    def fake_js(_target: tuple[int, int] | None, script: str, **_kwargs: object) -> str:
        scripts.append(script)
        if "innerText || '')" in script:
            return "Pro" if state["selected"] else "Instant"
        if "getAttribute('data-state')" in script:
            return state["menu"]
        if "return pro ?" in script:
            return "false"
        if "pro.focus()" in script:
            state["selected"] = True
            state["menu"] = "closed"
            return ""
        if "const b = document.querySelector('button.__composer-pill')" in script:
            state["menu"] = "open" if state["menu"] == "closed" else "closed"
            return ""
        return ""

    monkeypatch.setattr(cgpt, "_js", fake_js)
    monkeypatch.setattr(cgpt, "ensure_chat_mode", lambda **_kwargs: None)
    monkeypatch.setattr(cgpt.time, "sleep", lambda _seconds: None)

    cgpt.select_pro(target=(1, 1))

    joined = "\n".join(scripts)
    assert "thinking-effort" not in joined
    assert "Extended" not in joined
    assert state["selected"] is True
    assert "effort" not in inspect.signature(cgpt.ask).parameters
    assert "effort" not in inspect.signature(cgpt.submit).parameters


def test_chat_mode_is_selected_and_stable_before_pro_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"mode": "work", "selection_events": 0}

    def fake_js(_target: tuple[int, int] | None, script: str, **_kwargs: object) -> str:
        if "return JSON.stringify" in script:
            return json.dumps(
                {
                    "has_mode_controls": True,
                    "chat_selected": state["mode"] == "chat",
                    "work_selected": state["mode"] == "work",
                    "composer_ready": True,
                    "pill": "Pro" if state["mode"] == "chat" else "5.6 Sol",
                }
            )
        if "chat.click()" in script:
            state["selection_events"] += 1
            state["mode"] = "chat"
            return ""
        raise AssertionError(f"Unexpected script: {script}")

    monkeypatch.setattr(cgpt, "_js", fake_js)
    monkeypatch.setattr(cgpt.time, "sleep", lambda _seconds: None)

    cgpt.ensure_chat_mode(target=(1, 2))

    assert state == {"mode": "chat", "selection_events": 1}


def test_fetch_conversations_page_uses_explicit_archive_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[int, int] | None]] = []

    def fake_get(path: str, *, target: tuple[int, int] | None = None) -> str:
        calls.append((path, target))
        return json.dumps(
            {
                "items": [
                    {
                        "id": "conv-12345678",
                        "title": "Example",
                        "create_time": "2026-08-01T00:00:00Z",
                        "update_time": "2026-08-02T00:00:00Z",
                        "is_archived": True,
                    }
                ],
                "offset": 20,
                "limit": 7,
                "total": 28,
            }
        )

    monkeypatch.setattr(cgpt, "_sync_xhr_get", fake_get)

    page = cgpt.fetch_conversations_page(
        20,
        7,
        archived=True,
        target=(9, 4),
    )

    assert page["items"][0]["id"] == "conv-12345678"
    assert calls == [
        (
            "/backend-api/conversations?offset=20&limit=7&order=updated&is_archived=true",
            (9, 4),
        )
    ]


@pytest.mark.parametrize(
    ("offset", "limit"),
    [(-1, 1), (0, 0), (0, 21), (True, 1), (0, False)],
)
def test_fetch_conversations_page_rejects_invalid_page_bounds(
    offset: int,
    limit: int,
) -> None:
    with pytest.raises(ValueError):
        cgpt.fetch_conversations_page(offset, limit, archived=False)


def test_fetch_conversations_page_rejects_malformed_or_throttled_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cgpt,
        "_sync_xhr_get",
        lambda *_args, **_kwargs: '{"items": {}}',
    )
    with pytest.raises(cgpt.ChatGPTError, match="malformed"):
        cgpt.fetch_conversations_page(0, 20, archived=False)

    monkeypatch.setattr(
        cgpt,
        "_sync_xhr_get",
        lambda *_args, **_kwargs: '{"detail": "Too many requests"}',
    )
    with pytest.raises(cgpt.ChatGPTReadThrottledError, match="listing conversations"):
        cgpt.fetch_conversations_page(0, 20, archived=False)


def test_fetch_conversations_page_does_not_scan_valid_chat_content_for_throttling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cgpt,
        "_sync_xhr_get",
        lambda *_args, **_kwargs: json.dumps(
            {
                "items": [
                    {
                        "id": "conv-12345678",
                        "title": "Rate limit investigation",
                        "mapping": {"node": {"message": "Too many requests"}},
                    }
                ],
                "offset": 0,
                "limit": 20,
                "total": 1,
            }
        ),
    )

    page = cgpt.fetch_conversations_page(0, 20, archived=False)

    assert page["items"][0]["title"] == "Rate limit investigation"


def test_fetch_conversation_does_not_scan_valid_chat_content_for_throttling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cgpt,
        "_sync_xhr_get",
        lambda *_args, **_kwargs: json.dumps(
            {
                "conversation_id": "conv-12345678",
                "title": "Rate limit investigation",
                "mapping": {"node": {"message": "Rate limits and too many requests"}},
            }
        ),
    )

    convo = cgpt.fetch_conversation("conv-12345678")

    assert convo["title"] == "Rate limit investigation"



def test_runtime_state_and_bytecode_stay_out_of_the_skill(tmp_path):
    # An installed skill is a hash-tracked copy: a file its run writes there blocks its next refresh.
    skill = SCRIPTS_DIR.parent
    for state in (cgpt._STATE_PATH, cgpt._WINDOW_STATE_PATH, cgpt._LOCK_PATH):
        assert not state.resolve().is_relative_to(skill.resolve()), state
    copy = tmp_path / "gpt"
    shutil.copytree(skill, copy, ignore=shutil.ignore_patterns("__pycache__"))
    before = sorted(p.relative_to(copy) for p in copy.rglob("*"))
    for script in ("chatgpt_ask.py", "chatgpt_chat.py"):
        subprocess.run([sys.executable, str(copy / "scripts" / script), "--help"], check=True,
                       capture_output=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert sorted(p.relative_to(copy) for p in copy.rglob("*")) == before
