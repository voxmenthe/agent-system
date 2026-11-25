---
argument-hint: <free-form prompt; mention any local file paths you want attached>
description: Ask ChatGPT Pro (GPT-5.x Pro/Thinking) a question, optionally attaching local files
allowed-tools: Bash, Read, Write
---

Read `~/.claude/skills/gpt/SKILL.md` first if you haven't this session — it
documents `scripts/chatgpt_ask.py`, exit codes, and operational caveats.

## Request

The user's prompt is `$ARGUMENTS` — free-form text that may reference local
file paths the user wants ChatGPT Pro to read alongside the question.

## Steps

1. **Parse `$ARGUMENTS`.** Extract any file paths the user mentions: bare
   paths (`src/foo.py`, `/abs/x.md`), backticked paths, or directives like
   "attach X", "look at Y", "use Z.pdf". Strip those directives from the
   prompt text but preserve any meaningful framing. Verify each path exists
   before running. If a path is ambiguous, ask the user before invoking the
   script — Pro requests are slow and metered, don't burn one on a
   clarification.

2. **Pick an output path.** Default `/tmp/gpt-<short-slug>.md` where the slug
   is derived from the prompt topic (≤6 words, kebab-case). Use a path under
   the project (e.g. `PLANS/...` or `docs/`) only if the answer is meant to
   persist and the project already uses such a directory.

3. **Run `chatgpt_ask.py`.**
   ```bash
   python3 ~/.claude/skills/gpt/scripts/chatgpt_ask.py \
     --prompt "<cleaned prompt>" \
     --files <path1> <path2> ... \
     --output <output_path> \
     --effort extended \
     --json
   ```
   - Omit `--files` entirely if the user did not reference any files.
   - If the prompt is long or contains shell metacharacters, write it to a
     tmp file first and pass `--prompt-file <tmp>` instead of `--prompt`.
   - `--effort extended` is the default; drop to `standard` only if the
     user explicitly asked for speed.
   - `--json` ensures you get `conversation_url`, `model_slug`, and
     `citations` on stdout for the summary in step 5.

4. **Handle non-zero exit codes** per the table in `~/.claude/skills/gpt/SKILL.md`:
   - `10` (not logged in): ask the user to sign in to chatgpt.com in Chrome.
   - `11` (JS-from-Apple-Events disabled): ask the user to enable
     **Chrome → View → Developer → Allow JavaScript from Apple Events**.
   - `12` (timeout): confirm Chrome stayed frontmost; consider raising
     `--timeout`.
   - `64` (bad args): fix the invocation.
   Do not retry blindly on `10` or `11` — wait for the user to confirm.

5. **Report back.** `Read` the output file, summarize the relevant parts for
   the user, and surface the `conversation_url` from the JSON metadata so
   they can keep the chat going in their browser if they want. Include the
   model slug and effort that were actually used.
