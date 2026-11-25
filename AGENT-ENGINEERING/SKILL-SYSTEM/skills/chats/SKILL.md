---
name: chats
description: List recent or date-bounded private ChatGPT website conversations and export a selected conversation through the user's logged-in Chrome into local Markdown and normalized JSON. The deterministic scripts support archived-chat discovery, timezone-aware creation or update date filters, active and alternate branches, audio transcriptions, attachments, citations, and integrity manifests. Use when the user asks to list, find, locate, download, save, export, archive, or obtain ChatGPT conversations or chat history.
disable-model-invocation: true
---

# Chats

Discover private conversations or export one complete transcript with
deterministic pagination, filtering, normalization, rendering, and validation.
Do not send, edit, archive, or otherwise mutate any ChatGPT conversation.

## Authentication route

1. Prefer the authenticated Chrome connector when it is available. Use a
   controlled signed-in ChatGPT tab only as transport for the read-only
   conversation-index or conversation-detail endpoint; keep pagination,
   validation, filtering, normalization, rendering, and local writes
   deterministic.
2. Do not read Chrome's `Local State` on the connector route. Retrieval through
   that route does not need it.
3. Use the standalone Python commands only when the connector is unavailable or
   the user explicitly requests the CLI path. Those commands use the sibling
   gpt skill's AppleEvents bridge and may need `Local State` only to bootstrap a
   new profile-pinned window.
4. Treat the routes as separate implementations. Success through one route does
   not validate the other.

## Discovery contract

- `recent` means most recently **updated**, matching ChatGPT's supported index
  order. It searches active chats by default.
- `range` uses inclusive calendar dates in an explicit IANA timezone. It filters
  on creation time by default and searches both active and archived chats.
- Pass `--date-field updated` when “in the range” means last updated rather than
  created. The endpoint rejects creation-time ordering, so both modes paginate
  in updated-descending order. After validating that no chat was updated before
  it was created, either mode stops safely once updates cross the lower bound.
- Pass `--archive-scope active`, `archived`, or `all` to override the defaults.
- Print schema-versioned JSON to stdout. Include only conversation ID, URL,
  title, creation/update timestamps, and archive state; never print or persist
  access tokens, cookies, raw mappings, or session metadata.
- Treat ChatGPT's index `total` field as pagination look-ahead, not a stable
  full-history count. Stop on a short or empty page and fail loudly on duplicate
  IDs, ordering drift, malformed items, or archive-scope mismatches.
- Treat pagination as a best-effort non-snapshot read. Duplicate detection catches
  common concurrent insert/archive drift, but a conversation deleted during a
  long scan can still create an undetectable omission. The JSON reports
  `snapshot_consistency: best_effort` rather than claiming a transactional list.

## List conversations

Run from the directory containing this SKILL.md:

```bash
python3 scripts/list_chatgpt_conversations.py recent --limit 10

python3 scripts/list_chatgpt_conversations.py range \
  --from-date 2026-08-01 \
  --to-date 2026-08-07 \
  --timezone America/Los_Angeles

python3 scripts/list_chatgpt_conversations.py range \
  --from-date 2026-08-01 \
  --to-date 2026-08-07 \
  --timezone America/Los_Angeles \
  --date-field updated \
  --archive-scope active
```

The range's `from-date` and `to-date` are both inclusive. The output records the
equivalent UTC `start_inclusive` and `end_exclusive` bounds so downstream use is
unambiguous. Redirect stdout only when the user explicitly wants a saved index.

## Export contract

- Accept a bare conversation ID or an exact private
  https://chatgpt.com/c/CONVERSATION_ID URL.
- Treat “complete conversation” as every user-visible user or assistant message
  in the conversation mapping, including alternate branches that are not on the
  current path.
- Exclude hidden context, reasoning (including “Worked for …” reasoning
  recaps), tool, and system nodes from the transcript.
- Preserve message IDs, tree relationships, timestamps, model metadata,
  structured content, attachment metadata, citations, and source links in the
  normalized JSON.
- Render the Markdown as a reading view: one heading per run of consecutive
  messages from the same speaker, with no message IDs, timestamps, or messages
  that have no visible content. Replace ChatGPT's inline citation and widget
  markers with the reference's own Markdown `alt` text, or drop them when they
  are UI-only. An alternate-branch message quotes the opening of the message it
  replies to.
- Render user-visible audio transcription text as message content in Markdown;
  do not replace it with a generic audio-asset placeholder.
- Create a new destination directory. Never overwrite or merge into an existing
  directory.
- Write the integrity manifest last, after read-back verification of the
  Markdown and JSON files.

## Run the exporter

1. Confirm that the source is a private /c/ URL or bare ID. Shared /share/ URLs
   use a different retrieval surface and are unsupported.
2. Choose a new destination directory. If the user did not specify one, use
   CHATGPT-EXPORTS/<semantic-slug> beneath the current working directory.
3. Run this command from the directory containing this SKILL.md:

       python3 scripts/download_chatgpt_conversation.py \
         "CONVERSATION_URL_OR_ID" \
         --output "NEW_OUTPUT_DIRECTORY"

   (Or omit `--output` to automatically export into
   `CHATGPT-EXPORTS/<semantic-slug>`. You may also pass `--slug "CUSTOM_SLUG"`.)

4. Read the JSON success summary printed to stdout. Report the exact output
   directory and any completeness limitation.
5. If the destination already exists, stop and ask the user whether to choose a
   different new directory. Do not remove or replace the existing export.

The standalone scripts may open or reuse the gpt skill's dedicated ChatGPT
window. If that window is not authenticated, ask the user to log in there and
rerun the same command. The bridge requires Chrome's **View → Developer → Allow
JavaScript from Apple Events** setting. Report a macOS privacy denial
accurately; do not describe it as a ChatGPT API requirement or scan arbitrary
user tabs.

## Output

The new directory contains:

- **<semantic-slug>.md** — reading view of the active conversation followed by
  every user-visible alternate-branch message.
- **<semantic-slug>.json** — schema-versioned normalized message tree with
  active path, parent and child links, source metadata, and counts.
- **<semantic-slug>.manifest.json** — completion marker plus byte counts and
  SHA-256 digests for the Markdown and normalized JSON.

The conversation ID is always preserved inside the JSON (`source.conversation_id`),
the Markdown header link, and the integrity manifest. If the conversation has a
meaningful title in ChatGPT, `<semantic-slug>` is derived directly from that title
(lowercased, hyphen-separated). If the conversation is untitled or has a generic
placeholder (such as “New chat” or “ChatGPT conversation”), it falls back to the
conversation ID.

## Cleanup and maintenance

To audit, migrate, or normalize existing exports in `CHATGPT-EXPORTS` so all
folders and files follow `<semantic-slug>.<suffix>` and have verified manifests:

```bash
# Preview planned renames and manifest updates
python3 scripts/cleanup_chatgpt_exports.py --dry-run

# Execute cleanup
python3 scripts/cleanup_chatgpt_exports.py

# Machine-readable output for agent automation
python3 scripts/cleanup_chatgpt_exports.py --json
```

The cleanup script:
1. Detects folders named with bare UUIDs or UUID-v* suffixes and renames them to
   semantic slugs based on their conversation titles.
2. Renames internal files (`conversation.*` or `<UUID>.*`) to `<semantic-slug>.*`.
3. Updates and cryptographically reverifies each manifest's file map and SHA-256 hashes.
4. Uses `git mv` / `git rm` / `git add` for git-tracked directories and files to keep git history clean.
5. Is completely idempotent: subsequent runs report `already_clean` with no modifications.

## Exit handling

- 0: export completed.
- 1: dependency, bridge, or local write failure.
- 10: the dedicated ChatGPT window is not logged in.
- 11: Chrome JavaScript execution is blocked.
- 12: temporary ChatGPT read throttling or timeout; retry later.
- 64: invalid conversation input, malformed response, or existing destination.

For listing, exit 64 also covers invalid dates/timezones and index consistency
failures. The authenticated conversation-index endpoint is an undocumented
ChatGPT website surface and may drift; its response shape is validated on every
page. Results cover private conversations visible in that index, not deleted or
expired temporary chats.

Unexpected exceptions intentionally retain a traceback. Do not retry-loop,
silently downgrade the export, or reconstruct missing messages.
