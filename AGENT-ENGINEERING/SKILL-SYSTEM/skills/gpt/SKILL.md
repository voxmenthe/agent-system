---
name: gpt
description: Query ChatGPT Pro (currently gpt-5.6-sol) through the user's logged-in Chrome on macOS. Use when the user explicitly invokes $gpt or asks for GPT/ChatGPT/Pro, cdme/ask codex, or a second opinion on difficult implementation, design, reasoning, or multi-file review work. Do not use for questions answerable with local tools or ordinary web access. Primary CLI is scripts/chatgpt_ask.py for file uploads, verified send-only submission, polling, citations, and threading. Also covers cdme, the scoped OpenAI Codex CLI GPT-5.6 Sol max-effort final-output alternative.
disable-model-invocation: true
---

# gpt

Use ChatGPT Pro through the user's already-logged-in Chrome; this does **not**
use the OpenAI API. Pro runs usually take 5-25 minutes, sometimes ~30 minutes
for large reviews. Wait at least 9 minutes before the first recovery `--fetch`.
Hard rule: Pro may first emit polished partial prose; never accept unexpectedly
short output as final. Wait, then `--fetch` the same conversation.

## Use

Use this skill only when the user asks for GPT/ChatGPT/Pro, `cdme`, `ask codex`,
or a second opinion. Prefer Pro for architecture/design decisions, complex
multi-part implementation reviews, file-attachment analysis with citations,
and multi-turn threaded critique. Use `cdme` for a repository-aware Codex review
at max reasoning effort, or when the Pro rate window is exhausted and waiting
is not worth it.

## Rate Limit

Before every Pro send, check:

```bash
tail -n 3 ~/.chatgpt_pro_requests.log
```

Max **2 prompt sends per 18 minutes** and **at least 7 minutes between sends**,
including the one about to be sent. `chatgpt_ask.py` logs immediately before
sending to `~/.chatgpt_pro_requests.log` and keeps the newest 20 entries;
`--fetch` reads do not count. If either limit would be violated, wait or use
`cdme`. Over-limit sends exit `13` without touching Chrome and print the retry
wait; sleep that long and retry once. Attempts that fail mid-send still count.

## Pro CLI

Use `scripts/chatgpt_ask.py`; do not hand-roll AppleScript/JS for normal asks.
It handles profile-pinned Chrome automation, Pro selection, uploads,
polling, citations, conversation IDs, and final-answer detection.

```bash
CHATGPT="$HOME/.agents/skills/gpt/scripts/chatgpt_ask.py"

python3 "$CHATGPT" --prompt "Explain the tradeoffs between X and Y." \
  --output /tmp/gpt_answer.md

python3 "$CHATGPT" --prompt "Review this code for bugs and concurrency issues." \
  --files src/auth.py src/auth_test.py --output /tmp/gpt_review.md

python3 "$CHATGPT" --prompt "Explain this article in detail." \
  --files article.md --send-only

python3 "$CHATGPT" --prompt-file /tmp/question.md --files context_bundle.md \
  --output /tmp/answer.md --json

python3 "$CHATGPT" --prompt "Now critique your design." \
  --conversation-id <CID> --output /tmp/followup.md

python3 "$CHATGPT" --fetch <CID> --output /tmp/finished_answer.md --json
```

Rules:
- Prompt text must be task-only: no agent/meta commentary about plans, user
  preferences, rate limits, or why a model/tool is being used.
- Always pass `--output PATH` unless the answer is known to be tiny; read the
  saved file selectively.
- The helper selects the current Pro model (`gpt-5.6-sol`). Pro no longer
  exposes a configurable reasoning-effort step, so the helper does not attempt one.
- Use `--send-only` to return after upload, send, and conversation verification
  without waiting for or reading the assistant response. It cannot use `--output`.
- Pass attachments with `--files` instead of pasting contents. Max 10 files; for
  more, concatenate into a bundle, often via the `prepare-context` skill.
- Use `--prompt-file` for long prompts or shell-awkward text, `--json` for
  conversation URL/model/citation metadata, and `--quiet` inside scripts.
- Use `--timeout` above the 1200s default for very large multi-file reviews.

## Chrome/Tab Model

`chatgpt_ask.py` owns a dedicated Chrome window pinned to the ChatGPT-logged-in
profile (the one whose email is in `CHROME_PROFILE_EMAIL`). It
creates/reuses tabs there, stores window/session state under this skill folder,
and reads answers by `conversation_id`. Do not activate arbitrary ChatGPT tabs,
use `agent-browser`, or write custom AppleScript for normal asks.

ChatGPT serves both Chat and Work from `https://chatgpt.com/`. Work exposes a
Codex-style model/effort picker rather than Pro. Before uploading files or
opening the model picker, the helper explicitly selects and verifies **Chat**
mode; a visible composer alone is not sufficient readiness evidence.

Sending briefly foregrounds the exact target tab to select the model, type, and
send. Let it have focus until the prompt is sent; after that, the long wait and
`--fetch` read by conversation ID in the background and Chrome need not stay
foregrounded. If the window was closed or Chrome restarted, the script reopens
it. If exit `10` or profile/login drift appears, ask the user to log into
ChatGPT in Chrome or set `CHROME_PROFILE_EMAIL` correctly.

## Threading and Recovery

Every run prints the conversation URL and a reusable `--conversation-id <CID>`
follow-up command to stderr. For multi-turn work, reuse that exact ID every time;
`--conversation-id` binds the send to that conversation's tab and verifies the
prompt landed there. `--continue` targets only the last conversation this tool
created and is racy if another GPT call interleaved. Without either flag, a call
starts a fresh conversation.

Pro/tool-use runs can emit coherent interim text. Completion is determined by
the conversation state, not by whether the prose sounds complete. Wait at least
9 minutes after a send before the first recovery fetch. For recovery, run
`--fetch <CID> --output answer.md --json`: consume `answer.md` only when the JSON
`status` is `"ok"`. If status is `"incomplete"` or the command exits `12`, wait
and fetch again. Do **not** send a follow-up asking GPT to continue, expand, or
fix truncation; that starts a new turn and often confuses the run. If `--fetch`
hits "Too many requests", treat it as a read-side throttle: wait several minutes
and retry the same `--fetch --json`; do not ask the user or send a new prompt.

## Prompt Context

GPT Pro and a newly launched `cdme` task know only what you provide. Never include
agent/meta commentary. Focus on complete, high-quality task content such as:
- Codebase context: relevant files, callers, tests, types, configs, and bundles
  when the 10-file Pro limit is tight; for `cdme`, name the relevant paths and
  desired inspection scope.
- Planning/history/intent: goal, attempted/rejected approaches, constraints,
  versions, style, prior decisions, and relevant `PLANS/` docs.
- A self-contained ask: desired output shape (decision, critique, patch, etc.)
  and success criteria; do not refer to unseen conversation state.

A thin prompt wastes a slow Pro run; a grounded prompt should let an engineer
with zero project context answer definitively.

## Codex Alternative: `cdme`

`cdme` is defined in `~/.bash_agents` and runs the OpenAI Codex CLI with the
repository-scoped Codex home and GPT-5.6 Sol at `max` reasoning effort. It emits
only the final answer on stdout and is not subject to the ChatGPT Pro send cap.

```bash
source ~/.bash_agents
cdme 'Compare approach A vs B for <problem>; recommend one and justify.'
```

Run it from the repository whose scoped tools and context it should use. It can
read or modify local files and run commands, so phrase the request as a review
or question when edits are not intended and state the relevant file paths
explicitly. Failures print status and the captured run log to stderr.

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | OK | Read the output file, or use the printed conversation URL after `--send-only`. |
| `10` | Not logged in to chatgpt.com in Chrome | Ask the user to log in; do not retry until confirmed. |
| `11` | Chrome JavaScript-from-Apple-Events disabled | Ask the user to enable Chrome -> View -> Developer -> Allow JavaScript from Apple Events. |
| `12` | Timed out, `--fetch` found the conversation still incomplete, or ChatGPT read-throttled | Wait and `--fetch --json` by ID again; for read throttles wait several minutes, and for active runs consider higher `--timeout`. |
| `13` | Send would violate the 2-per-18-minutes or 7-minute-gap limit | Nothing sent; sleep the printed wait and retry once. |
| `64` | Bad arguments | Fix invocation. |
| `1` | Other error, including mis-send abort | Read stderr; for threading retry with explicit `--conversation-id`. |

## Advanced Reference

For routine usage, stop here. Read `ADVANCED.md` only when debugging or extending
the tool: dedicated Chrome-window/profile behavior, low-level AppleScript/JS
probing, operational caveats, helper scripts, internal API endpoints, model/DOM
selector drift, file-upload protocol, raw evidence, TODOs, and deeper failure
modes live there.
