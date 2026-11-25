"""Create and verify a file-seeded conversation in ChatGPT Chat mode."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GPT_SCRIPTS = Path(__file__).resolve().parents[2] / "gpt" / "scripts"
if str(GPT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(GPT_SCRIPTS))

try:
    import chatgpt_lib as cgpt
except ImportError as error:  # pragma: no cover - installation/configuration failure
    raise SystemExit(
        "The sibling gpt skill is required; expected chatgpt_lib.py under "
        f"{GPT_SCRIPTS}"
    ) from error


PROMPT = "Don't respond, this is just for context."
MAX_FILES = 10

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_LOGIN = 10
EXIT_JS_BLOCKED = 11
EXIT_TIMEOUT = 12
EXIT_USAGE = 64

Target = tuple[int, int]
Progress = Callable[[str], None]


class ContextChatError(cgpt.ChatGPTError):
    """The requested context conversation could not be proven correct."""


class ContextChatUsageError(ValueError):
    """The local file arguments do not satisfy the upload contract."""


@dataclass(frozen=True)
class SubmissionEvidence:
    model_slug: str | None
    thinking_effort: str | None
    attachment_names: tuple[str, ...]


@dataclass(frozen=True)
class ContextChatResult:
    status: str
    conversation_id: str
    conversation_url: str
    title: str
    uploaded_files: tuple[str, ...]
    stored_attachment_names: tuple[str, ...]
    prompt: str
    model_slug: str | None
    thinking_effort: str | None
    stored_thinking_effort: str | None
    mode: str
    verified: dict[str, bool]

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["uploaded_files"] = list(self.uploaded_files)
        data["stored_attachment_names"] = list(self.stored_attachment_names)
        return data


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _ArgumentParser(
        description=(
            "Upload files into one new ChatGPT Chat-mode context conversation, submit "
            "the fixed context-only prompt, and title it from the first file."
        )
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages; the JSON result still prints to stdout.",
    )
    return parser.parse_args(argv)


def validate_files(files: Iterable[str | Path]) -> list[Path]:
    paths = [Path(item).expanduser().resolve() for item in files]
    if not paths:
        raise ContextChatUsageError("at least one file is required")
    if len(paths) > MAX_FILES:
        raise ContextChatUsageError(
            f"ChatGPT accepts at most {MAX_FILES} files per context message; got {len(paths)}"
        )
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ContextChatUsageError("not a regular file: " + ", ".join(missing))
    return paths


def _require_chat_mode(*, target: Target) -> None:
    """Verify without switching modes, which could discard staged attachments."""
    state = cgpt._composer_mode_state(target)
    chat_selected = state.get("chat_selected") or (
        not state.get("has_mode_controls")
        and str(state.get("pill") or "").lower() in {"instant", "thinking", "pro"}
    )
    if (
        not chat_selected
        or state.get("work_selected")
        or not state.get("composer_ready")
    ):
        raise ContextChatError(
            "Chat mode could not be verified in the target composer; refusing to "
            "upload or send in Work or an unknown mode. Inspect the tab before retrying."
        )


def send_context_prompt(text: str, *, target: Target) -> None:
    """Submit only while Chat is verified, then observe the composer leave.

    A newly staged composer can ignore either its first synthetic click or
    its first keyboard activation. Try each only while the exact prompt remains
    staged, checking between attempts so a successful send cannot be duplicated.
    Navigation may also shift the tab index, so a disappearing target is treated
    as indeterminate here and the caller must still capture and verify by text.
    """
    if not text.strip():
        raise ContextChatError("The fixed context prompt is empty.")
    _require_chat_mode(target=target)
    cgpt._js(
        target,
        "(() => {"
        "  const editor = document.querySelector('#prompt-textarea');"
        "  if (!editor) throw new Error('composer textarea missing');"
        "  editor.focus();"
        f"  editor.innerHTML = {json.dumps('<p>' + cgpt._html_escape(text) + '</p>')};"
        "  editor.dispatchEvent(new InputEvent('input', {"
        "    bubbles:true, cancelable:true, inputType:'insertText',"
        f"    data:{json.dumps(text)}"
        "  }));"
        "})()",
    )

    def read_state() -> dict[str, Any] | None:
        try:
            raw = cgpt._js(
                target,
                "(() => {"
                f"  const wanted = {json.dumps(text)};"
                "  const editor = document.querySelector('#prompt-textarea');"
                "  const users = Array.from(document.querySelectorAll("
                "    '[data-message-author-role=user]'));"
                "  return JSON.stringify({"
                "    path:location.pathname,"
                "    composer:((editor && editor.innerText) || '').trim(),"
                "    prompt_visible:users.some(e => ((e.innerText || '').trim() === wanted))"
                "  });"
                "})()",
                timeout=5.0,
            )
        except cgpt.ChatGPTError:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def sent(state: dict[str, Any]) -> bool:
        return bool(
            "/c/" in str(state.get("path") or "")
            or state.get("prompt_visible")
            or not state.get("composer")
        )

    # Let the composer commit its React state after the synthetic input and
    # after the attachment helper's final chip check.
    time.sleep(0.8)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        state = read_state()
        if state is None:
            return
        if sent(state):
            return
        if state.get("composer") != text:
            raise ContextChatError(
                "The Chat composer no longer contains the fixed prompt."
            )

        for method in ("click", "keyboard"):
            _require_chat_mode(target=target)
            result = cgpt._js(
                target,
                "(() => {"
                "  const button = document.querySelector('[data-testid=send-button]');"
                "  if (!button || button.disabled) return 'waiting';"
                "  button.focus();"
                + (
                    "  button.click();"
                    if method == "click"
                    else (
                        "  button.dispatchEvent(new KeyboardEvent('keydown', {"
                        "    key:'Enter', code:'Enter', bubbles:true, cancelable:true}));"
                        "  button.dispatchEvent(new KeyboardEvent('keyup', {"
                        "    key:'Enter', code:'Enter', bubbles:true, cancelable:true}));"
                    )
                )
                + f"  return {json.dumps(method)};"
                "})()",
            )
            if result == "waiting":
                time.sleep(0.3)
                continue
            time.sleep(1.0)
            state = read_state()
            if state is None:
                return
            if sent(state):
                return
            if state.get("composer") != text:
                return
    raise ContextChatError(
        "The Chat composer retained the fixed prompt after click and keyboard attempts; "
        "no sent turn was observed."
    )


def _open_fresh_target(progress: Progress) -> tuple[Target, set[str]]:
    progress(f"ensuring ChatGPT Chrome session ({cgpt.CHROME_PROFILE_EMAIL} profile)")
    existing = cgpt.ensure_chatgpt_available()
    target = cgpt._new_tab_in_dedicated_window("https://chatgpt.com/")
    if target is None:
        progress("could not create a tab; reusing one in the dedicated window")
        target = existing
        cgpt._navigate_tab(target, "https://chatgpt.com/")
    cgpt._activate_tab(*target)
    if not cgpt._wait_tab_ready(target, require_no_cid=True, ready_timeout=25.0):
        raise cgpt.ChatGPTTimeoutError(
            "The fresh ChatGPT composer did not load in time."
        )
    cgpt.get_session(target=target)
    return target, set(cgpt.recent_conversation_ids(target=target))


def rename_conversation(
    conversation_id: str,
    title: str,
    *,
    target: Target,
) -> None:
    """Rename through the website endpoint, then require a stable by-ID title.

    ChatGPT can accept an early manual title and overwrite it moments later with
    its first-turn auto-title. Retry the same idempotent PATCH once only after a
    different stored title has itself remained stable.
    """
    expression = (
        "(async () => {"
        "  const session = await fetch('/api/auth/session', {credentials:'include'}).then(r => r.json());"
        "  if (!session.accessToken) throw new Error('not authenticated');"
        f"  const id = {json.dumps(conversation_id)};"
        f"  const title = {json.dumps(title)};"
        "  const response = await fetch('/backend-api/conversation/' + encodeURIComponent(id), {"
        "    method:'PATCH', credentials:'include',"
        "    headers:{'Authorization':'Bearer ' + session.accessToken, 'Content-Type':'application/json'},"
        "    body:JSON.stringify({title})"
        "  });"
        "  const body = await response.text();"
        "  return {ok:response.ok, status:response.status, body:body.slice(0,500)};"
        "})()"
    )
    observed: Any = None
    for attempt in range(2):
        result = cgpt._run_js_async(expression, target=target, timeout=30.0)
        if not isinstance(result, dict) or not result.get("ok"):
            raise ContextChatError(
                "ChatGPT rejected the conversation rename "
                f"(HTTP {(result or {}).get('status', 'unknown')}): "
                f"{(result or {}).get('body', '')}"
            )

        target_stable = 0
        other_stable = 0
        previous: Any = object()
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            convo = cgpt.fetch_conversation(
                conversation_id,
                retries=2,
                retry_wait=0.5,
                target=target,
                read_throttle_waits=(5.0,),
            )
            observed = convo.get("title")
            if observed == title:
                target_stable += 1
                other_stable = 0
                if target_stable >= 4:
                    return
            else:
                target_stable = 0
                other_stable = other_stable + 1 if observed == previous else 1
                if attempt == 0 and other_stable >= 3:
                    break
            previous = observed
            time.sleep(1.0)
    raise ContextChatError(
        f"Rename returned success, but the stored title did not remain {title!r}; "
        f"last observed {observed!r}."
    )


def _attachments(message: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    attachments = (message.get("metadata") or {}).get("attachments") or []
    return tuple(item for item in attachments if isinstance(item, dict))


def _portal_name_matches(actual: str, expected: str) -> bool:
    """Allow ChatGPT library collision suffixes such as `notes(1).md`."""
    if actual == expected:
        return True
    path = Path(expected)
    pattern = rf"{re.escape(path.stem)}\(\d+\){re.escape(path.suffix)}"
    return re.fullmatch(pattern, actual) is not None


def _attachments_match(
    expected: Sequence[dict[str, Any]], actual: Sequence[dict[str, Any]]
) -> bool:
    if len(expected) != len(actual):
        return False

    def compatible(want: dict[str, Any], got: dict[str, Any]) -> bool:
        want_name, got_name = want.get("name"), got.get("name")
        if not isinstance(want_name, str) or not isinstance(got_name, str):
            return False
        if not _portal_name_matches(got_name, want_name):
            return False
        if want.get("size") != got.get("size"):
            return False
        want_mime = want.get("mime")
        got_mime = got.get("mime_type")
        return not (want_mime and got_mime) or want_mime == got_mime

    def assign(index: int, remaining: tuple[int, ...]) -> bool:
        if index == len(expected):
            return True
        for position in remaining:
            if compatible(expected[index], actual[position]) and assign(
                index + 1, tuple(item for item in remaining if item != position)
            ):
                return True
        return False

    return assign(0, tuple(range(len(actual))))


def _stored_model_and_effort(
    conversation: dict[str, Any], user_message: dict[str, Any]
) -> tuple[str | None, str | None]:
    user_metadata = user_message.get("metadata") or {}
    model_slug = (
        user_metadata.get("model_slug")
        or user_metadata.get("resolved_model_slug")
        or conversation.get("default_model_slug")
    )
    effort = user_metadata.get("thinking_effort")
    observed_models = [
        user_metadata.get("model_slug"),
        user_metadata.get("resolved_model_slug"),
        conversation.get("default_model_slug"),
    ]
    working_turn_id = user_metadata.get("working_turn_id")
    for node in (conversation.get("mapping") or {}).values():
        message = (node or {}).get("message")
        if not message or (message.get("author") or {}).get("role") != "assistant":
            continue
        metadata = message.get("metadata") or {}
        if working_turn_id and metadata.get("working_turn_id") != working_turn_id:
            continue
        model_slug = model_slug or metadata.get("model_slug")
        effort = effort or metadata.get("thinking_effort")
        observed_models.extend(
            [
                metadata.get("model_slug"),
                metadata.get("resolved_model_slug"),
            ]
        )
    if any(
        model is not None and not isinstance(model, str) for model in observed_models
    ) or (effort is not None and not isinstance(effort, str)):
        raise ContextChatError("The stored model/effort metadata has an invalid type.")
    if any(model is not None and model.endswith("-wm") for model in observed_models):
        raise ContextChatError("Work model metadata was found, but Chat was required.")
    return model_slug, effort


def wait_for_submission_evidence(
    conversation_id: str,
    expected_uploads: Sequence[dict[str, Any]],
    *,
    target: Target,
    timeout: float = 35.0,
) -> SubmissionEvidence:
    deadline = time.monotonic() + timeout
    last_observed: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            convo = cgpt.fetch_conversation(
                conversation_id,
                retries=2,
                retry_wait=0.5,
                target=target,
                read_throttle_waits=(5.0,),
            )
        except cgpt.ChatGPTError:
            time.sleep(0.8)
            continue
        message = cgpt._matching_user_msg(convo, PROMPT)
        if message is None:
            last_observed = {"prompt": "missing"}
            time.sleep(0.8)
            continue
        try:
            model_slug, effort = _stored_model_and_effort(convo, message)
        except ContextChatError as error:
            raise ContextChatError(
                f"{error} Inspect https://chatgpt.com/c/{conversation_id} before retrying."
            ) from error
        attachments = _attachments(message)
        names = tuple(
            item.get("name")
            for item in attachments
            if isinstance(item.get("name"), str)
        )
        last_observed = {
            "model_slug": model_slug,
            "thinking_effort": effort,
            "attachment_names": names,
        }
        if _attachments_match(expected_uploads, attachments):
            return SubmissionEvidence(
                model_slug=model_slug,
                thinking_effort=effort,
                attachment_names=names,
            )
        time.sleep(0.8)
    raise ContextChatError(
        "The new conversation did not expose the required prompt/attachments "
        f"metadata within {timeout:.0f}s; last observed {last_observed!r}."
    )


def start_context_chat(
    files: Iterable[str | Path],
    *,
    on_progress: Progress | None = None,
) -> ContextChatResult:
    paths = validate_files(files)
    progress = on_progress or (lambda _message: None)
    title = paths[0].name
    conversation_id: str | None = None
    target: Target | None = None

    with cgpt._send_lock() as acquired:
        if not acquired:
            raise ContextChatError(
                "Could not acquire the shared ChatGPT send lock; nothing was sent."
            )
        target, prior_ids = _open_fresh_target(progress)
        progress("selecting Chat mode; leaving its model and effort unchanged")
        cgpt.ensure_chat_mode(target=target)
        progress(f"uploading {len(paths)} context file(s)")
        _require_chat_mode(target=target)
        uploaded = cgpt.attach_files(paths, target=target)
        progress("submitting the fixed context-only prompt")
        send_context_prompt(PROMPT, target=target)
        progress("capturing and verifying the new conversation")
        conversation_id = cgpt.capture_conversation_for_prompt(
            PROMPT,
            prior_ids,
            front_target=target,
        )
        if not conversation_id:
            raise ContextChatError(
                "The prompt may have been sent, but the new conversation ID could not be "
                "captured. Inspect the fresh ChatGPT tab before retrying."
            )
        # Navigation may remove or reorder tabs. Re-resolve by the captured
        # conversation URL before every subsequent read or mutation.
        target = cgpt.prepare_continue_tab(conversation_id)
        if not cgpt.verify_user_prompt_present(
            conversation_id,
            PROMPT,
            target=target,
        ):
            raise ContextChatError(
                f"The fixed prompt was not verified in https://chatgpt.com/c/{conversation_id}; "
                "inspect that conversation before retrying."
            )

    assert target is not None and conversation_id is not None
    progress("verifying uploaded files and observing stored model metadata")
    evidence = wait_for_submission_evidence(
        conversation_id,
        uploaded,
        target=target,
    )
    progress(f"renaming conversation to {title!r}")
    rename_conversation(conversation_id, title, target=target)
    return ContextChatResult(
        status="ok",
        conversation_id=conversation_id,
        conversation_url=f"https://chatgpt.com/c/{conversation_id}",
        title=title,
        uploaded_files=tuple(path.name for path in paths),
        stored_attachment_names=evidence.attachment_names,
        prompt=PROMPT,
        model_slug=evidence.model_slug,
        thinking_effort=evidence.thinking_effort,
        stored_thinking_effort=evidence.thinking_effort,
        mode="chat",
        verified={
            "prompt": True,
            "attachments": True,
            "chat_mode": True,
            "title": True,
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    progress = (
        (lambda _message: None)
        if args.quiet
        else (
            lambda message: print(
                f"[gpt-context] {message}", file=sys.stderr, flush=True
            )
        )
    )
    try:
        result = start_context_chat(args.files, on_progress=progress)
    except ContextChatUsageError as error:
        print(f"gpt-context: {error}", file=sys.stderr)
        return EXIT_USAGE
    except cgpt.NotLoggedInError as error:
        print(f"gpt-context: {error}", file=sys.stderr)
        return EXIT_LOGIN
    except cgpt.JSExecBlockedError as error:
        print(f"gpt-context: {error}", file=sys.stderr)
        return EXIT_JS_BLOCKED
    except (cgpt.ChatGPTTimeoutError, cgpt.ChatGPTReadThrottledError) as error:
        print(f"gpt-context: {error}", file=sys.stderr)
        return EXIT_TIMEOUT
    except (ContextChatError, cgpt.ChatGPTError, OSError) as error:
        print(f"gpt-context: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps(result.to_json_dict(), sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
