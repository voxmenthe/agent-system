# tools/chatgpt — Drive ChatGPT Pro from your logged-in Chrome

Two CLIs around `chatgpt_lib.py`:

- **`chatgpt_ask.py`** — agent-friendly. Structured args, parseable output, exit codes.
- **`chatgpt_chat.py`** — human-friendly. Interactive prompts, colored progress, sensible defaults.

Both drive your real, logged-in Chrome session via AppleScript → JavaScript in
the chatgpt.com tab. They use the composer UI for model selection / file
uploads / sending, and `GET /backend-api/conversation/<id>` to capture the
completed response.

The library also exposes `fetch_conversations_page(offset, limit, archived=...)`
as a narrow, read-only browser edge for the sibling conversation-archive skill.
It returns one validated updated-descending index page and deliberately caps the
page size at 20 because current website responses embed large mappings. The
caller owns pagination, filtering, and output redaction.

The homepage can expose either Chat or Work at the same URL. Before attaching
files, the tools explicitly select and verify Chat mode so the model picker
contains the Pro option rather than Work's Codex-style effort controls.

## One-time setup

In Chrome, enable: **View → Developer → Allow JavaScript from Apple Events**
(persistent across restarts).

You also need to be signed in to chatgpt.com in Chrome — specifically in the
profile whose primary Google account is `CHROME_PROFILE_EMAIL` (export it in
`~/.config/agent-system/shell.local.sh`). The tools drive a dedicated Chrome window
pinned to that profile (window id persisted in `~/.cache/gpt-skill/dedicated_window.json`);
other profiles' windows are never touched.

## Agent CLI: `chatgpt_ask.py`

```
chatgpt_ask.py --prompt "What is 2+2?" --output answer.md
chatgpt_ask.py --prompt-file question.txt --files data.csv notes.md \
                --output report.md
chatgpt_ask.py --prompt "Explain this article." --files article.md --send-only
chatgpt_ask.py --prompt "follow up question" --conversation-id <ID>   # robust threading
chatgpt_ask.py --prompt "follow up question" --continue               # last conversation
chatgpt_ask.py --prompt "What's the title?" --files paper.pdf --json
```

To keep multiple turns in one thread, pass `--conversation-id <id>` on every
follow-up. The id is **printed on stderr at the end of every run** (and is in the
`--json` output), so you can just copy it forward. `--conversation-id` binds the
send to that exact conversation (and verifies it landed) instead of typing into
"whatever Chrome tab is in front" — the failure mode that used to split follow-ups
into other threads.

Outputs:
- Response markdown → `--output PATH` (or stdout if omitted)
- `--send-only` → return after a verified upload/send without reading a response
- Progress lines → stderr (silence with `--quiet`)
- With `--json` → JSON metadata on stdout (status, conversation URL, model, citations)
- Every send appends a timestamped line to `~/.chatgpt_pro_requests.log` (kept to
  the newest 20 entries); sends are capped at 2 per 18 minutes with a 7-minute
  minimum gap (`--fetch` doesn't count)

Exit codes:
- `0` success
- `10` not logged in
- `11` Chrome's JS-from-Apple-Events setting is off
- `12` timed out, still incomplete on `--fetch`, or ChatGPT read-throttled
- `13` rate limited (would violate 2-per-18-minutes or 7-minute-gap limit; retry wait printed on stderr)
- `64` argument problem
- `1` other error

## Human CLI: `chatgpt_chat.py`

```
chatgpt_chat.py                                  # fully interactive
chatgpt_chat.py "Summarize this:" -f notes.md    # one-shot inline prompt
chatgpt_chat.py --files report.pdf               # interactive prompt, pre-filled files
```

Interactive mode asks for files, then the prompt (multi-line, finish with
Ctrl-D). Response prints to stdout with progress + summary on stderr.

## Library

```python
from tools.chatgpt import chatgpt_lib as cgpt

response = cgpt.ask(
    prompt="What is in this file?",
    files=["./paper.pdf"],
    new_chat=True,              # False to continue an existing chat
    conversation_id=None,       # set (with new_chat=False) to target a specific thread
    timeout=600,
    on_progress=print,
)
print(response.text)
print(response.conversation_id, response.model_slug)

submission = cgpt.submit(
    prompt="Explain this article.",
    files=["./article.md"],
)
print(submission.conversation_id)
```

## Limitations

- macOS only (relies on `osascript`).
- All tabs are created and read inside the skill's dedicated, profile-pinned
  window. Opening that window (first run, or after Chrome restarts) fronts
  Chrome once; later runs reuse it quietly.
- Selects "Pro" of the current major version exposed in the composer pill,
  currently `gpt-5.6-sol`. Pro does not expose a configurable reasoning-effort
  step. Other major versions need the `Configure…` modal, which isn't wired up.
- The `/f/conversation` POST is anti-bot-protected (sentinel PoW), so we
  always go through the UI, not direct API calls. The **send** drives one
  specific tab in the foreground (the one bound to the target conversation, or a
  fresh tab for a new chat); let it finish typing + sending before you grab focus
  back.
- The **answer-wait reads by conversation id in the background** and does not need
  Chrome foregrounded — you can switch away while the model thinks.
