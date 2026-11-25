---
name: gpt-context
description: Start a new ChatGPT conversation in Chat mode, never Work, from uploaded context files, submit the fixed no-response context prompt, and title it from the first file. Use when the user asks to seed or create a fresh ChatGPT context conversation. Do not use to ask ChatGPT for an answer, continue an existing conversation, or manage chat history.
disable-model-invocation: true
---

# GPT Context

Create one new context-only conversation through the user's authenticated
ChatGPT website session. Invocation for named files authorizes that one external
conversation creation and rename; it does not authorize retries that might
create duplicates, follow-up prompts, or changes to other conversations.

**Always use Chat mode, never Work.** Verify Chat before uploading and again
before submitting. If the mode is unknown or changes after upload, stop; do not
switch modes with attachments staged or fall back to Work. Leave the selected
Chat model and effort unchanged; context seeding does not require Pro or a
particular model/effort.

## Run

Run from the directory containing this `SKILL.md`:

```bash
python3 scripts/start_context_chat.py FILE [FILE ...]
```

Pass files in the intended order. The script uses the first file's basename,
including its extension, as the exact conversation title. ChatGPT currently
accepts at most 10 files in one message, and the script requires at least one.

The deterministic helper:

- opens a fresh tab in the profile-pinned Chrome window owned by the sibling
  `gpt` skill;
- selects and verifies ChatGPT **Chat** mode before uploading;
- uploads every file;
- rechecks Chat before each send attempt and submits exactly
  `Don't respond, this is just for context.`;
- captures the conversation by matching that user message in the new thread;
- renames the conversation with the authenticated website endpoint; and
- verifies the prompt, every attachment's name/size/MIME (including portal-added
  collision suffixes such as `(1)`) and the final title before reporting success.
  It rejects known Work-model metadata rather than treating it as success.

It does not read or return an assistant response. Leave the created tab open.
Do not replace the fixed prompt, paste file contents into the composer, or use
the read-only `chats` exporter to mutate the title.

## Output and recovery

Success is one JSON object containing the conversation ID, URL, exact title,
uploaded filenames, `mode: "chat"`, and verification flags including `chat_mode`.
The model and effort fields are observations, not requirements: they may be
`null`. Both effort fields report the raw stored value, without a UI-label
translation. Report the URL and title to the user.

The bridge requires macOS, a logged-in ChatGPT Chrome profile, and Chrome's
**View -> Developer -> Allow JavaScript from Apple Events** setting. Exit codes
match the sibling bridge where practical: `10` means login is required, `11`
means JavaScript from Apple Events is disabled, `12` is a timeout or temporary
read throttle, `64` is invalid input, and `1` is another failure.

If failure occurs after the prompt may have been sent, inspect the reported
target tab or conversation URL before retrying. Never blindly rerun: the first
conversation may already exist even if capture, metadata verification, or the
rename failed.
