# Advanced GPT Skill Reference

Read this only when debugging or extending `scripts/chatgpt_ask.py`, diagnosing Chrome/profile/UI drift, or needing the reverse-engineered chatgpt.com API, DOM, file-upload, raw-evidence, or TODO notes. Routine usage should stay in `SKILL.md`.

## Contents

- Multi-window robustness and dedicated Chrome-window rationale
- Exit codes, operational caveats, and helper scripts
- Internal API and live UI probing guide
- Historical model/effort selector evidence, DOM hooks, and network flow
- File-upload protocol, raw evidence, TODOs, and deeper failure modes

---

## Current operational state (2026-07-28)

ChatGPT Pro currently resolves to `gpt-5.6-sol` and no longer exposes a
configurable reasoning-effort step. The production helper selects the visible
Pro entry only. Sections 4-5 and the raw network examples below are retained as
historical 2026-05-08 evidence for debugging protocol and selector drift; they
do not describe the current production selection flow.

#### Multi-window robustness (why this matters)

The user typically has **many Chrome windows open with dozens of chatgpt.com tabs,
across several Chrome profiles** — and only ONE profile (the one named by `CHROME_PROFILE_EMAIL`) is
logged in to chatgpt.com. "active tab of front window" drifts between osascript
calls, AppleScript has no notion of Chrome profiles, and a frozen background tab
can hang JS execution (and with it the whole run). The tool is hardened against
all three:

- **The skill owns one dedicated, profile-pinned Chrome window.** It is opened via
  `open -na "Google Chrome" --args --profile-directory=<dir>` — Chrome honors that
  switch even while already running, so the window lands deterministically in the
  chatgpt-logged-in profile (the dir is resolved from Chrome's Local State by the
  email in `CHROME_PROFILE_EMAIL`, which must be set). Its window
  id is persisted in `~/.cache/gpt-skill/dedicated_window.json` and reused. Every
  tab the tool creates or reads lives in this window — never the user's other
  windows, never another profile.
- **Sends are bound to a specific tab, by conversation.** For `--conversation-id`
  / `--continue`, `ask()` locates (or opens+navigates) the tab actually showing that
  conversation, **verifies the URL**, and drives the composer **in that exact tab**
  (`tab N of window id W`), never "whatever is front". For a new chat it opens a
  **fresh tab in the dedicated window**. Each new-chat ask leaves one such tab open;
  continues of the same conversation reuse its existing tab.
- **Chat mode is explicit.** ChatGPT serves Chat and Work from the same root URL.
  A composer can therefore be ready while its model pill exposes Work's Codex-style
  effort controls. Before uploading files, the helper selects Chat and verifies
  that it remains selected; only then does it open the Pro picker.
- **The send is verified.** After sending, the tool confirms the prompt text appears
  as a new user message in the target conversation. If it didn't land there, it
  **raises loudly** (exit `1`) rather than returning a stale answer.
- **Reads are by-id, in a tab the run owns.** The answer is polled from the pinned
  `conversation_id` via synchronous XHR **in the run's own tab** (or another
  dedicated-window tab) — never an arbitrary user tab, where a frozen background
  page can block the sync XHR and hang the osascript bridge. The pinned id is
  saved to `~/.cache/gpt-skill/last_session.json` for `--fetch`.
- **New-chat capture is text-matched.** The new conversation is identified by matching
  the user-message text we sent (not "the newest conversation"), so a concurrent
  unrelated send can't be mistaken for ours.
- **Concurrent sends are serialized.** A lockfile
  (`~/.cache/gpt-skill/send.lock`) serializes the brief send+capture window across
  processes; the long answer-wait runs *outside* the lock. Still, prefer threading
  explicitly with `--conversation-id` over running many sends at once.

You do **not** need to manage Chrome windows or tabs — and never hand-roll
AppleScript to "activate a chatgpt tab": that activates a RANDOM tab in a random
profile and then nothing works (the historical focused-a-tab-then-did-nothing
failure). The send brings the *correct* tab to the front while it types; reads
never steal focus.

### Exit codes (branch on these)

| Code | Meaning | Action |
|------|---------|--------|
| `0`  | OK | proceed; read the output file, or use the conversation URL after `--send-only` |
| `10` | Not logged in to chatgpt.com in Chrome | tell the user to log in; do not retry until confirmed |
| `11` | Chrome's "Allow JavaScript from Apple Events" is off | ask the user to enable **Chrome → View → Developer → Allow JavaScript from Apple Events**; do not retry until confirmed |
| `12` | Timed out waiting for response, `--fetch` found the conversation still incomplete, or ChatGPT read-throttled | the run may still be going; wait, then `--fetch --json` the same `conversation_id` again. For read throttles, wait several minutes and do not send a new prompt |
| `13` | Rate limited (would violate 2 sends per 18 minutes or the 7-minute minimum gap) | nothing was sent; sleep the wait printed on stderr, then retry — see the rate-limit section above |
| `64` | Bad arguments | fix the invocation |
| `1`  | Other error (incl. **mis-send abort**: a `--continue`/`--conversation-id` follow-up that didn't land in the target thread, or a new send whose conversation couldn't be identified) | read stderr; for threading, retry with an explicit `--conversation-id` |

## Other scripts in this skill

- `scripts/chatgpt_chat.py` — interactive **human-facing** CLI with prompts
  and colored output. Do **not** invoke from an agent flow; it expects a TTY.
- `scripts/chatgpt_lib.py` — the underlying Python library. Import directly
  only when you need behavior the CLI doesn't expose (custom flow, extra
  headers, programmatic citation handling, etc.).

## Operational caveats

- **macOS only** (relies on `osascript`).
- **All tabs live in the skill's dedicated window, pinned to the
  `CHROME_PROFILE_EMAIL` Chrome profile** (the only profile logged in to chatgpt.com).
  If the user switches which profile holds the ChatGPT login, set
  `CHROME_PROFILE_EMAIL` to the new profile's primary email. Opening the
  dedicated window (first run, or after the user closes it / restarts Chrome)
  fronts Chrome once; afterwards runs reuse it quietly.
- **The send drives one specific tab in the foreground.** The script brings the
  *correct* tab (the one bound to the target conversation, or a fresh tab for a new
  chat) to the front, selects Chat rather than Work, and types into it. Let it
  complete the send — don't fight it for focus during the brief mode-select +
  model-select + type + send window. Once the prompt is
  in, the long answer-wait reads the conversation **by id in the background** and
  does not need Chrome foregrounded, so you can switch away while it thinks.
- The pill menu exposes the current **Pro** model (`gpt-5.6-sol`). The helper
  selects Pro but does not configure reasoning effort because the current Pro
  UI no longer offers that step. Switching to a different major version needs
  the `Configure…` modal, which the script does **not** drive yet.
- The `/f/conversation` endpoint is anti-bot-protected (sentinel proof-of-
  work). That is why we drive the UI rather than the raw API.
- Don't poke ChatGPT with garbage probes in a tight loop — the sentinel
  layer can shadow-flag the user's account.

## Reference material (skim only when extending or debugging)

The rest of this document is reverse-engineered notes about the chatgpt.com
client: endpoint shapes, DOM hooks, network sequence, file-upload protocol,
and known TODOs. Read it when:
- The script is failing in a way the exit code doesn't explain.
- You need to extend `chatgpt_lib.py` (Configure-modal model picking, a new
  endpoint, an unhandled `use_case`, etc.).
- You're debugging selector drift after a chatgpt.com bundle update.

For routine usage, you do **not** need to read past this point.

---

# ChatGPT (chatgpt.com) Internal API + Live UI Probing Guide

Operational notes for a future me investigating chatgpt.com's internal APIs and
driving its UI from the user's already-logged-in Chrome on macOS. Captured live
on 2026-05-08 against the chatgpt.com Pro web client.

The user is a ChatGPT Pro subscriber on this machine; their Chrome session
is already authenticated. We control Chrome via AppleScript -> `execute javascript`
in the active tab.

---

## TL;DR — what's verified vs. open

✅ **Verified end-to-end:**
- Chrome cookie → `/api/auth/session` → JWT
- `GET /backend-api/models` (full slug + thinking-effort matrix)
- Model+effort UI selection (Radix menus, Enter-key activation)
- Persistence: `GET /backend-api/settings/user_last_used_model_config?model_slug=...&thinking_effort=...`
- Composer typing + sending via DOM
- File upload: `POST /backend-api/files` → `PUT` Azure SAS → `POST /backend-api/files/process_upload_stream`
- Asking about file, reading citations
- Reading the stored conversation: `GET /backend-api/conversation/<id>` (the oracle)
- Field names: `action, model, thinking_effort, messages, parent_message_id, conversation_id, attachments`
- Effort values: `min | standard | extended | max` (UI: Light/Standard/Extended/Heavy)

⚠️ **Inferred but not byte-captured:**
- Exact wire format of `POST /backend-api/f/conversation` (we have field names from the stored conversation; haven't intercepted the actual request bytes — the bundle's fetch reference is captured before our patches install)
- Sentinel header name carrying the PoW token
- `library_file_id` (`libfile_*`) source — probably from `process_upload_stream` response

❌ **Out of scope (deliberately):**
- Sentinel proof-of-work solver (`window.SentinelSDK` is sealed after init; reproducing requires running their `sdk.js` in a sandbox)

The single most useful endpoint when something fails: **`GET /backend-api/conversation/<id>`** — it returns the full message tree with metadata, which echoes whatever fields were sent.

---

## 0. Quick map

- **Auth handoff:** cookie session in Chrome → `/api/auth/session` → JWT in `accessToken` field → use as `Authorization: Bearer <jwt>` for `/backend-api/*`.
- **Model + thinking effort selector** is one Radix-UI menu attached to a single composer pill button (`button.__composer-pill` with text = current effort, e.g. "Thinking", "Heavy"). It does **not** live in the page header.
- **Model list endpoint:** `GET /backend-api/models` — lists every model slug with full effort metadata.
- **Persistence on selection:** `GET /backend-api/settings/user_last_used_model_config?model_slug=<slug>&thinking_effort=<effort>`.
- **Send message:** `POST /backend-api/f/conversation` (preceded by `/f/conversation/prepare`, sentinel proof-of-work, etc).
- **File upload:** 3-step flow — `POST /backend-api/files` → `PUT` to returned Azure SAS URL → `POST /backend-api/files/process_upload_stream`. Then attach the `file_id` to a user message under `metadata.attachments`.
- **Read what was sent:** `GET /backend-api/conversation/<id>` — the **single most useful debugging endpoint**. It returns the full message tree with all metadata (model_slug, thinking_effort, attachments, citations, system messages). Because stored == sent, it's our oracle when wire capture fails.

---

## 1. Prerequisites (one-time setup on the user's machine)

1. Chrome's setting **View → Developer → Allow JavaScript from Apple Events** must be enabled. There is a confirmation dialog.
2. Without that, `osascript ... execute javascript ...` returns:
   > Executing JavaScript through AppleScript is turned off.
3. We CANNOT toggle this menu via UI scripting unless `osascript` has macOS Accessibility permission, which the agent typically does not. Just ask the user to enable it once.

`agent-browser` (Vercel) is **not a substitute** here — it spawns its own Chromium with no shared cookies, so the user would have to log in inside the disposable browser. Use Chrome.

---

## 2. The boilerplate

### 2.1 Get a chatgpt.com tab to probe (use the dedicated window)

**Do NOT scan all windows and activate "the first chatgpt tab"** — windows span
several Chrome profiles (only the `CHROME_PROFILE_EMAIL` profile is logged in to
chatgpt.com), and a frozen background tab will hang `execute javascript`
indefinitely. That anti-pattern is what used to focus a random gpt tab and then
do nothing. For debugging, reuse the library's window management:

```bash
python3 - <<'EOF'
import os, sys; sys.path.insert(0, os.path.expanduser('~/.agents/skills/gpt/scripts'))
import chatgpt_lib as L
print(L.ensure_chatgpt_available())   # (window_id, tab_index) in the dedicated profile window
EOF
```

To open the dedicated window manually (profile-pinned; works while Chrome runs):
`open -na "Google Chrome" --args --profile-directory=Default --new-window "https://chatgpt.com/"`
(resolve the profile dir for an email from `~/Library/Application Support/Google/Chrome/Local State` →
`profile.info_cache.<dir>.user_name`).

### 2.2 Run JS in the active tab

```bash
osascript <<'EOF'
tell application "Google Chrome"
  set theTab to active tab of front window
  return execute theTab javascript "document.title + ' | ' + location.href"
end tell
EOF
```

**Critical limitation:** `execute javascript` returns the *synchronous* return value. Promises become useless objects. For async work, use the **stash-and-poll pattern**:

```javascript
// First osascript call: kick off async, stash result
window.__probe = null;
(async () => {
  try {
    const data = await fetch('/whatever').then(r => r.json());
    window.__probe = JSON.stringify(data);
  } catch(e) { window.__probe = JSON.stringify({err: String(e)}); }
})();
// (Return value of the IIFE is irrelevant; AppleScript sees nothing useful.)
'kicked off';
```

Then `sleep 2` in shell, then a second osascript that returns `window.__probe || 'still null'`.

---

## 3. Authentication

Chrome holds the session cookie. The web client exchanges it for a JWT
on every page load.

```javascript
// Run inside the page; returns ~immediately.
const s = await fetch('/api/auth/session', {credentials:'include'}).then(r=>r.json());
window.__chatgptToken = s.accessToken;       // stash for later XHR
// s.user.{id,email,name}, s.expires (~90 days), s.account, s.accessToken (JWT)
```

Returned shape (key fields only):
```
{
  WARNING_BANNER, user: { id, email, name, picture, ... },
  expires: "2026-08-07T05:54:07.579Z",
  account: { account_user_id, role, ... },
  accessToken: "eyJhbGciOiJSUzI1NiI...",
  authProvider: "auth0", sessionToken, rumViewTags
}
```

Then for every `/backend-api/*` call, attach `Authorization: Bearer ${s.accessToken}`.
Same-origin fetches with `credentials: 'include'` also work because the
session cookies are present, but the JWT is the canonical auth header used
by the backend.

---

## 4. Discovering models + thinking effort options

### 4.1 The list endpoint

`GET /backend-api/models` (auth'd) returns:
```
{
  title, secondary_title, model_picker_version, default_model_slug,
  models: [ { slug, title, description, max_tokens, reasoning_type,
              configurable_thinking_effort, thinking_efforts: [...],
              enabled_tools: [...], tags: [...], capabilities, product_features } ],
  internal_groups, categories, versions, icons
}
```

Each model has:
- `reasoning_type`: `"none"`, `"auto"`, `"reasoning"`, or `"pro"`
- `configurable_thinking_effort`: bool
- `thinking_efforts`: array (only populated when configurable). Each entry:
  ```
  { thinking_effort: "min" | "standard" | "extended" | "max",
    full_label, mobile_full_label, short_label, description }
  ```

### 4.2 Snapshot of slugs (Pro account, captured 2026-05-08)

Models with **configurable thinking effort**:

| Slug                | Title              | reasoning_type | Efforts                           |
|---------------------|--------------------|----------------|-----------------------------------|
| `gpt-5-2-thinking`  | GPT-5.2 Thinking   | reasoning      | min, standard, extended, max      |
| `gpt-5-4-thinking`  | GPT-5.4 Thinking   | reasoning      | min, standard, extended, max      |
| `gpt-5-5-thinking`  | GPT-5.5 Thinking   | reasoning      | min, standard, extended, max      |
| `gpt-5-2-pro`       | GPT-5.2 Pro        | pro            | standard, extended                |
| `gpt-5-4-pro`       | GPT-5.4 Pro        | pro            | standard, extended                |
| `gpt-5-5-pro`       | GPT-5.5 Pro        | pro            | standard, extended                |

Effort label mapping (UI ↔ API):

| UI label   | API value   |
|------------|-------------|
| Light      | `min`       |
| Standard   | `standard`  |
| Extended   | `extended`  |
| Heavy      | `max`       |

For Pro models, the `extended` label is shown as "Extended Pro" in the UI but the API value is still `extended`.

Models with reasoning but **no** user-configurable effort (it's chosen for you):
`o3`, `o3-pro`, `gpt-5-4-t-mini`.

Auto / non-reasoning models: `gpt-5-3`, `gpt-5-3-instant`, `gpt-5-5`, `gpt-5-5-instant`, `gpt-5-2`, `gpt-5-2-instant`, `gpt-5-1`, `gpt-5`, `gpt-5-mini`, `gpt-5-3-mini`, `gpt-4-5`, `research`, `agent-mode`.

`research` = Deep Research, `agent-mode` = Agent. They expose different `enabled_tools`.

### 4.3 Useful one-liner

```javascript
// In the page, returns concise summary.
const r = await fetch('/backend-api/models', {credentials:'include',
            headers:{Authorization:'Bearer '+window.__chatgptToken}}).then(r=>r.json());
JSON.stringify(r.models.map(m => ({
  slug: m.slug, title: m.title, reasoning_type: m.reasoning_type,
  configurable_thinking_effort: m.configurable_thinking_effort,
  efforts: m.thinking_efforts.map(e => e.thinking_effort)
})), null, 2);
```

---

## 5. Driving the model + effort picker UI

### 5.1 The selector is the composer pill

Search criteria: a `<button>` with class `__composer-pill`, `aria-haspopup="menu"`, and `aria-expanded` toggling between `false` and `true`. Its text is **the currently active effort label** (e.g. "Thinking", "Heavy", "Light") — *not* the model name. The model name does not appear visibly in the composer once a thinking model is active.

```javascript
const pillBtn = Array.from(document.querySelectorAll('button'))
  .find(b => b.classList.contains('__composer-pill'));
// pillBtn.innerText -> "Heavy" / "Standard" / "Thinking" etc.
// pillBtn.getAttribute('data-state') -> "open" | "closed"
```

### 5.2 Radix UI rejects synthetic `.click()` and synthetic pointer events

`btn.click()` returns silently with no menu opening; `data-state` stays `"closed"`.
Radix appears to demand an actual user gesture (it inspects `event.isTrusted` indirectly via React's pointer event flow).

**The trick that works:** focus + KeyboardEvent('Enter'). Radix's `MenuTrigger` listens for keyboard activation and the synthetic keyboard event is accepted.

```javascript
btn.focus();
btn.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
btn.dispatchEvent(new KeyboardEvent('keyup',   {key:'Enter', bubbles:true, cancelable:true}));
```

After ~300–500 ms, two `[role=menu]` portals exist (one is the Radix shadow root mirror of the other; both have the same items).

### 5.3 The menu structure

Top-level menu items (testid → meaning):

| `data-testid`                                     | Type             | Text     |
|---------------------------------------------------|------------------|----------|
| `model-switcher-gpt-5-5`                          | `menuitemradio`  | Instant  |
| `model-switcher-gpt-5-5-thinking`                 | `menuitemradio`  | Thinking |
| `model-switcher-gpt-5-5-thinking-thinking-effort` | submenu trigger  | (icon)   |
| `model-switcher-gpt-5-5-pro`                      | `menuitemradio`  | Pro      |
| `model-switcher-gpt-5-5-pro-thinking-effort`      | submenu trigger  | (icon)   |
| `model-configure-modal`                           | `menuitem`       | Configure... |

The visible top-level only shows the **currently chosen "version" line** (here 5.5) with three flavors: Instant / Thinking / Pro. To switch to GPT-5.4 Thinking etc, click "Configure..." → opens the full modal model picker.

To open a thinking-effort submenu (same Enter trick, no hover):

```javascript
const trig = document.querySelector(
  '[data-testid="model-switcher-gpt-5-5-thinking-thinking-effort"]');
trig.focus();
trig.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
trig.dispatchEvent(new KeyboardEvent('keyup',   {key:'Enter', bubbles:true, cancelable:true}));
```

The submenu adds four `menuitemradio`s with `innerText` = `"Light" | "Standard" | "Extended" | "Heavy"` (for `min/standard/extended/max`). They have no `data-testid`. Pick by `innerText` match:

```javascript
const choice = Array.from(document.querySelectorAll('[role=menuitemradio]'))
  .find(e => e.innerText.trim() === 'Heavy');   // or 'Light'/'Standard'/'Extended'
choice.focus();
choice.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
choice.dispatchEvent(new KeyboardEvent('keyup',   {key:'Enter', bubbles:true, cancelable:true}));
```

After selection: menu closes, and the pill text immediately reflects the new label (e.g., "Heavy"). The page fires a persistence call:
```
GET /backend-api/settings/user_last_used_model_config?model_slug=gpt-5-5-thinking&thinking_effort=max
```
This GET stores the user's preference for next conversation. (Yes, it's a GET that mutates state — that's their choice, not ours.)

### 5.4 Switching to a different *base* model (e.g. GPT-5.4)

The pill menu only exposes the current major version's three flavors. Use either:

1. **`Configure...` modal.** Click the `[data-testid="model-configure-modal"]` item with the same Enter trick. It opens a modal that lets you pick any model.
2. **Direct API.** You can probably bypass the UI by calling
   `GET /backend-api/settings/user_last_used_model_config?model_slug=gpt-5-4-thinking&thinking_effort=extended`
   yourself with the JWT, then sending the conversation message. Verify before relying on it; the UI may also stash a value in localStorage / a cookie that the backend cross-checks.

---

## 6. Composer (typing + sending) automation

The composer is a contenteditable `<div id="prompt-textarea">` (likely TipTap / ProseMirror) that mirrors a hidden `<textarea placeholder="Ask anything">`.

```javascript
const ed = document.querySelector('#prompt-textarea');
ed.focus();
ed.innerHTML = '<p>your prompt here</p>';
ed.dispatchEvent(new InputEvent('input',
  {bubbles:true, cancelable:true, inputType:'insertText', data:'your prompt here'}));
```

Send button: `<button data-testid="send-button" aria-label="Send prompt">`. **`.click()` works here** (it's a plain button, not Radix). It also responds to Enter/space if focused.

```javascript
const btn = document.querySelector('[data-testid=send-button]');
btn.focus();
btn.click();
```

After send, the URL changes to `/c/<conversation-id>` via Next.js navigation, but globals on `window` survive (it's client-side routing, not a hard reload). The send button's `<button>` is replaced by a stop button while streaming.

---

## 7. The full network flow when you send a message

Captured via `performance.getEntriesByType('resource')`, in order of occurrence:

```
GET  /backend-api/settings/user_last_used_model_config?model_slug=...&thinking_effort=...
GET  /backend-api/settings/user
POST /backend-api/f/conversation/prepare                 # ~600 B response
GET  /backend-api/conversation/experimental/generate_autocompletions
GET  /backend-api/sentinel/heartbeat
GET  /backend-api/sentinel/sdk.js                        # SDK script
POST /backend-api/sentinel/chat-requirements/prepare     # ~50 KB! returns work for proof-of-work
GET  /backend-api/sentinel/ping                          # repeats periodically
GET  /backend-api/settings/is_adult
POST /backend-api/sentinel/chat-requirements/finalize    # client returns PoW solution
POST /backend-api/f/conversation                         # the actual streaming send (SSE)
GET  /backend-api/conversation/<id>/stream_status
GET  /backend-api/beacons/home?conversation_id=<id>
GET  /backend-api/conversation/<id>/textdocs
GET  /backend-api/lat/r
```

Tells:

- **`/backend-api/sentinel/*`** is OpenAI's anti-abuse / proof-of-work layer (the
  client must run a JS challenge and submit `chat-requirements/finalize` to
  receive a token that gates the conversation POST). This is the part that
  makes a curl-only client hard. Reverse-engineered handlers exist in OSS
  ChatGPT-API projects; expect this to drift.
- **`/backend-api/f/conversation`** (with the `f/` prefix) is the streaming
  send endpoint on this client. Older OSS clients used `/backend-api/conversation`
  (no `f/`). Both may still work; the `f/` is current.

### 7.1 The `/f/conversation` POST body — confirmed via stored conversation

We could not capture the live POST body (see §7.3 below for why), but the
**stored conversation** at `GET /backend-api/conversation/<id>` echoes the
exact field names and values used by the request, in message `metadata`
and at top-level. Confirmed live:

- Per-turn metadata stores: `model_slug`, `default_model_slug`,
  `thinking_effort`, `resolved_model_slug` (on user msgs),
  `request_id`, `turn_exchange_id`, `stream_topic_id`, `chime_version`,
  `message_type: "next"`, `is_temporal_turn`.
- Top-level conversation: `default_model_slug`, `gizmo_id`, `gizmo_type`,
  `voice`, `disabled_tool_ids`, `memory_scope`, `is_temporary_chat`,
  `is_do_not_remember`, `safe_urls`, `blocked_urls`.

So the POST body almost certainly contains `model: "<slug>"` and
`thinking_effort: "<value>"` at the top level, alongside the messages array.
The traditional ChatGPT-API community-reverse shape (action=next, messages,
parent_message_id, conversation_id, model, etc.) is consistent with this.

### 7.2 Conversation message tree shape (from GET)

```json
{
  "id": "<msg-uuid>",
  "message": {
    "id": "<msg-uuid>",
    "author": {"role": "user|assistant|system", "name": null, "metadata": {}},
    "content": {"content_type": "text", "parts": ["hi"]},
    "status": "finished_successfully",
    "end_turn": null | true,
    "weight": 1.0,
    "metadata": {
      "model_slug": "gpt-5-5-thinking",
      "default_model_slug": "gpt-5-5-thinking",
      "thinking_effort": "max",
      "request_id": "wfr_...",
      "turn_exchange_id": "<uuid>",
      "stream_topic_id": "conversation-turn-<uuid>",
      "parent_id": "<msg-uuid>",
      "chime_version": 1,
      "message_type": "next",
      "is_temporal_turn": true,
      "can_save": false,
      "developer_mode_connector_ids": [],
      "selected_sources": [],
      "selected_github_repos": [],
      "serialization_metadata": {"custom_symbol_offsets": []},
      "model_switcher_deny": []
    },
    "recipient": "all",
    "channel": null
  },
  "parent": "<msg-uuid>",
  "children": ["<msg-uuid>"]
}
```

Other observed `content_type`s besides `"text"`:
- `"user_editable_context"` (system-injected user profile + custom instructions): `{user_profile, user_instructions}`. This is how custom instructions are delivered to the model — they appear as a *user* role message with `is_user_system_message: true` in metadata.
- `"model_editable_context"`: `{model_set_context, repository, repo_summary, structured_context}` — the assistant's running notes about you.
- `"thoughts"`: `{thoughts: [...], source_analysis_msg_id}` — the model's reasoning trace for thinking models.

### 7.3 Field names verified by API probe

We sent the following minimal body directly to `POST /backend-api/f/conversation`
with a valid bearer token (no sentinel token):

```json
{
  "action": "next",
  "model": "gpt-5-5-thinking",
  "thinking_effort": "max",
  "messages": [{
    "id": "<uuid>",
    "author": {"role":"user"},
    "content": {"content_type":"text","parts":["ping"]}
  }],
  "parent_message_id": "<uuid>",
  "conversation_id": null
}
```

Response: **HTTP 403 `"Unusual activity has been detected from your device.
Try again later."`** — i.e. the **shape was accepted**; the request was
rejected at the sentinel/anti-abuse layer because we didn't include the
PoW-derived token. By contrast, sending `{"messages": []}` returned 422
`"Invalid conversation body"`. So:

- `action`, `model`, `thinking_effort`, `messages`, `parent_message_id`,
  `conversation_id` are **valid field names** at the request schema level.
- A second header (or body field) carrying the sentinel proof-of-work token
  from `/backend-api/sentinel/chat-requirements/finalize` is required to
  pass the anti-abuse gate. We have not yet identified which header — likely
  `OpenAI-Sentinel-Chat-Requirements-Token` or similar based on past clients.

⚠️ **Don't keep poking blindly with bad bodies on the user's real account** —
the sentinel system may temporarily rate-limit or shadow-flag the account.
A few probes are fine; dozens are not.

### 7.4 Why our interceptor missed the live POST body

Our fetch interceptor and Request constructor proxy do **not** see this call.
Hypothesis: the chunk that issues the request captured `window.fetch` (or used
its own bound reference) at module-eval time before our patches were installed.
Our self-test fetches *are* captured, confirming the patches themselves work
for new code paths, just not for the conversation chunk.

Workarounds to try next time, in order of effort:

1. **Patch fetch / Request before the bundle loads.** Requires either a Chrome
   extension content script with `run_at: "document_start"`, or relaunching
   Chrome with `--remote-debugging-port=9222` and using CDP's
   `Page.addScriptToEvaluateOnNewDocument` before navigating.
2. **Use CDP `Network.requestWillBeSent` / `Network.getRequestPostData`** for
   true at-the-wire capture (this is what DevTools Network tab uses). Easiest
   if Chrome was launched with remote debugging from the start.
3. **Have the user copy-paste a captured request from DevTools Network tab as
   cURL** ("Copy → Copy as cURL"). Cheapest and most reliable for one-off.
4. Patch `Body.prototype.text/json` and `Response.prototype.clone` to fingerprint
   the response side; only useful for response payloads, not requests.

When captured, the body is expected to be JSON of roughly this shape (based on
older reversals of the same product — verify before relying on field names):

```json
{
  "action": "next",
  "messages": [{
    "id": "<uuid>",
    "author": {"role": "user"},
    "content": {"content_type": "text", "parts": ["hi"]},
    "metadata": {}
  }],
  "parent_message_id": "<uuid>",
  "conversation_id": "<uuid or null on first turn>",
  "model": "gpt-5-5-thinking",
  "thinking_effort": "max",
  "timezone_offset_min": -480,
  "history_and_training_disabled": false,
  "conversation_mode": {"kind": "primary_assistant"},
  "force_paragen": false,
  "force_paragen_model_slug": "",
  "force_rate_limit": false,
  "websocket_request_id": "<uuid>",
  "system_hints": [],
  "supported_encodings": ["v1"]
}
```

The thinking-effort field is almost certainly `thinking_effort`, not
`reasoning_effort`, since that's what the persistence GET query string uses.
But confirm at the wire when possible.

---

## 8. Patching network at runtime (with caveats)

If you only need to learn **request URLs** (not bodies), `performance.getEntriesByType('resource')` is enough and survives client-side navigation. The bundle does not bypass it.

To attempt request body capture from the page itself:

```javascript
(() => {
  if (window.__patched) return;
  window.__cap = [];

  // 1. window.fetch
  const oFetch = window.fetch;
  window.fetch = async function(input, init) {
    try {
      const url = typeof input === 'string' ? input : input.url;
      if (url && (url.includes('/backend-api/') || url.includes('/api/'))) {
        let body = null;
        if (init && init.body) {
          body = typeof init.body === 'string' ? init.body.slice(0,16000)
                                                : '['+(init.body.constructor.name)+']';
        }
        window.__cap.push({kind:'fetch', method:init?.method||'GET', url, body});
      }
    } catch(e){}
    return oFetch.apply(this, arguments);
  };

  // 2. Request constructor (catches paths even if a stale fetch reference is used,
  //    *as long as the bundle still constructs Request via window.Request)
  const OR = window.Request;
  window.Request = new Proxy(OR, {
    construct(t, args) {
      try {
        const [u, init] = args;
        if (typeof u === 'string' && u.includes('/backend-api/')) {
          window.__cap.push({kind:'req', method:init?.method||'GET', url:u,
            body: typeof init?.body === 'string' ? init.body.slice(0,16000) : (init?.body ? '['+init.body.constructor.name+']' : null)});
        }
      } catch(e){}
      return new t(...args);
    }
  });

  // 3. XHR
  const X = window.XMLHttpRequest, oOpen = X.prototype.open, oSend = X.prototype.send;
  X.prototype.open = function(m, u){ this.__u=u; this.__m=m; return oOpen.apply(this,arguments); };
  X.prototype.send = function(b){
    try { if (this.__u && this.__u.includes('/backend-api/'))
            window.__cap.push({kind:'xhr', method:this.__m, url:this.__u,
              body: typeof b === 'string' ? b.slice(0,16000) : (b?'['+b.constructor.name+']':null)}); } catch(e){}
    return oSend.apply(this, arguments);
  };

  window.__patched = true;
})();
```

**Confirmed working for:** ad-hoc `fetch()` calls we make from the page.
**Confirmed NOT enough for:** the conversation chunk's actual `/f/conversation`
POST. Use one of the workarounds in §7.1.

---

## 9. Useful page globals & DOM hooks (current as of bundle d2cf4d37 build)

| What | Where |
|------|-------|
| Composer textarea (visible) | `#prompt-textarea` (contenteditable div) |
| Composer textarea (mirror) | first `<textarea placeholder="Ask anything">` |
| Send button | `[data-testid="send-button"]` |
| Stop button (mid-stream) | `[data-testid="stop-button"]` |
| Plus / attachments | `[data-testid="composer-plus-btn"]` |
| Sidebar toggle | `[data-testid="open-sidebar-button"]` |
| Model/effort pill | `button.__composer-pill` |
| Model menu trigger items | `[data-testid^="model-switcher-"]` |
| Configure modal opener | `[data-testid="model-configure-modal"]` |
| Last assistant message text | last `[data-message-author-role="assistant"]` |
| User message text | `[data-message-author-role="user"]` |

`window.__NEXT_DATA__` and `window.__remixContext` are **not present** on
this build — the page does NOT use the standard Next.js `__NEXT_DATA__`
initial-state hydration. Don't bother probing them.

---

## 10. Going forward: minimal scripts to keep around

### 10.1 Get model list (one-shot, shell)

```bash
osascript <<'EOF'
tell application "Google Chrome"
  set theTab to active tab of front window
  set js to "window.__r=null;(async()=>{const s=await fetch('/api/auth/session',{credentials:'include'}).then(r=>r.json());const m=await fetch('/backend-api/models',{credentials:'include',headers:{Authorization:'Bearer '+s.accessToken}}).then(r=>r.json());window.__r=JSON.stringify(m.models.map(x=>({slug:x.slug,title:x.title,reasoning:x.reasoning_type,cfg:x.configurable_thinking_effort,efforts:x.thinking_efforts.map(e=>e.thinking_effort)})),null,2);})();'kicked';"
  return execute theTab javascript js
end tell
EOF
sleep 2
osascript -e 'tell application "Google Chrome" to return execute (active tab of front window) javascript "window.__r||\"still null\""'
```

### 10.2 Switch model + effort (drives the UI)

```bash
EFFORT="Heavy"  # one of Light, Standard, Extended, Heavy
osascript <<EOF
tell application "Google Chrome"
  activate
  set theTab to active tab of front window
  set js to "(()=>{const b=document.querySelector('button.__composer-pill');b.focus();b.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));b.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',bubbles:true,cancelable:true}));return 'opened';})()"
  return execute theTab javascript js
end tell
EOF
sleep 0.5
# Open thinking-effort submenu (assumes you're already on a Thinking model)
osascript <<EOF
tell application "Google Chrome"
  set theTab to active tab of front window
  set js to "(()=>{const t=Array.from(document.querySelectorAll('[data-testid]')).find(e=>e.getAttribute('data-testid').endsWith('-thinking-effort'));t.focus();t.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));t.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',bubbles:true,cancelable:true}));return 'sub';})()"
  return execute theTab javascript js
end tell
EOF
sleep 0.4
osascript <<EOF
tell application "Google Chrome"
  set theTab to active tab of front window
  set js to "(()=>{const c=Array.from(document.querySelectorAll('[role=menuitemradio]')).find(e=>e.innerText.trim()==='${EFFORT}');c.focus();c.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));c.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',bubbles:true,cancelable:true}));return document.querySelector('button.__composer-pill').innerText;})()"
  return execute theTab javascript js
end tell
EOF
```

### 10.3 Type and send

```bash
PROMPT='hello'
osascript <<EOF
tell application "Google Chrome"
  activate
  set theTab to active tab of front window
  set js to "(()=>{const e=document.querySelector('#prompt-textarea');e.focus();e.innerHTML='<p>${PROMPT}</p>';e.dispatchEvent(new InputEvent('input',{bubbles:true,cancelable:true,inputType:'insertText',data:'${PROMPT}'}));const b=document.querySelector('[data-testid=send-button]');b.focus();b.click();return 'sent';})()"
  return execute theTab javascript js
end tell
EOF
```

(Naive escaping — for non-trivial prompts, base64-encode the string and decode in JS.)

---

## 11. File upload + asking-about-file (verified end-to-end on 2026-05-08)

The composer "+" menu offers "Add photos & files" (⌘U). The composer always
contains three hidden file inputs:

| Element id        | accept     | multiple | use                             |
|-------------------|------------|----------|---------------------------------|
| `#upload-files`   | (any)      | yes      | generic files (docs, code, etc) |
| `#upload-photos`  | `image/*`  | yes      | image gallery picker            |
| `#upload-camera`  | `image/*`  | yes      | webcam                          |

### 11.1 Programmatically attaching a file

Browsers forbid setting `<input type=file>.value` from JS, but you **can**
assign a `FileList` produced via `DataTransfer`:

```javascript
const inp = document.querySelector('#upload-files');
const file = new File([textOrBytes], 'name.txt', {type: 'text/plain'});
const dt = new DataTransfer();
dt.items.add(file);
inp.files = dt.files;                                 // works in Chrome
inp.dispatchEvent(new Event('change', {bubbles:true}));
```

Within ~1 second the chip appears in the composer (look for a `<div>` whose
`innerText` matches the file name). The send button is briefly disabled
during upload. The chip's container is class
`-mx-2.5 -mt-2.5 flex flex-col [grid-area:header] mb-2.5`.

### 11.2 Network sequence (observed via `performance.getEntriesByType`)

Per single small file (~100 B):

```
POST /backend-api/files                                  # ~635 B request
PUT  https://sdmntpr<region>.oaiusercontent.com/files/<azure-uuid>/raw?...SAS...   # the bytes
POST /backend-api/files/process_upload_stream            # ~1130 B request
POST /backend-api/lat/retrieval                          # ~320 B
GET  /backend-api/files/library                          # ~2 KB (refresh of file list)
POST /backend-api/sentinel/chat-requirements/prepare     # PoW (50 KB)
POST /backend-api/sentinel/chat-requirements/finalize    # PoW solution (~2.3 KB)
POST /backend-api/f/conversation/prepare
POST /backend-api/f/conversation                         # the actual send
```

The Azure host varies by data center (`sdmntprcentralus`,
`sdmntprnorthcentralus`, etc.). The SAS token in the query string
(`se=`, `sp=w`, `sv=`, `sig=`) is single-use and expires; never log it.

### 11.3 `POST /backend-api/files` — exact schema (verified)

Request body:
```json
{
  "file_name": "name.txt",
  "use_case": "my_files",
  "file_size": 105,           // optional but include it
  "mime_type": "text/plain"   // optional
}
```

Required fields per the server's own 422: `file_name`, `use_case`. Anything
else is currently ignored or optional.

Response body (200):
```json
{
  "status": "success",
  "upload_url": "https://sdmntpr<region>.oaiusercontent.com/files/<uuid>/raw?...SAS...",
  "file_id": "file_00000000<32-hex-id>"
}
```

The `file_id` is what you'll thread through the rest of the flow.

`use_case` values seen so far: `"my_files"`. Other values likely:
`"image_gen"`, `"profile_picture"`, `"voice_clone"`, `"connector"` — not
verified here.

### 11.4 PUT to Azure (the actual upload)

```javascript
await fetch(upload_url, {                          // upload_url comes from step 11.3
  method: 'PUT',
  body: file,                                     // a Blob/File
  headers: {'x-ms-blob-type': 'BlockBlob'}        // sometimes required for Azure SAS PUT
});
```

For the small text file we tested, no `x-ms-blob-type` header was sent by
the official client — Azure accepted the PUT anyway. For larger files
(>4 MB) it's almost certainly required.

### 11.5 `POST /backend-api/files/process_upload_stream` — exact schema (verified)

Request body (all required per the server's 422):
```json
{
  "file_id": "file_<id>",
  "file_name": "name.txt",
  "use_case": "my_files",
  "index_for_retrieval": true
}
```

We didn't capture the response body from the official client; based on
naming, this kicks off retrieval indexing for "my_files" cases (the result
shows up later as `retrieval_index_status` on the file record). Set
`index_for_retrieval: true` for documents you want the model to RAG over.

### 11.6 `GET /backend-api/files/<id>` — file detail (verified)

```json
{
  "id": "file_<id>",
  "owner_id": "user-<id>",
  "name": "name.txt",
  "creation_time": "2026-05-09T06:10:12+00:00",
  "state": "ready",
  "ready_time": null,
  "size": 105,
  "metadata": null,
  "use_case": "my_files",
  "retrieval_index_status": null,
  "file_size_tokens": null,
  "variants": null,
  "expiration_time": null,
  "mime_type": "text/plain",
  "no_auth_user_upload": false,
  "file_extension": "txt"
}
```

Use this to poll for `state === "ready"` after upload before sending the message.

### 11.7 Attaching the file to a conversation message

The composer adds the file to the next message's `metadata.attachments` array.
Verified shape (from the stored conversation):

```json
"metadata": {
  "attachments": [
    {
      "id": "file_<id>",                        // from POST /files response
      "name": "jc_test_marker.txt",
      "size": 105,
      "mime_type": "text/plain",
      "source": "library",
      "library_file_id": "libfile_<id>",        // server-assigned, comes back from process_upload_stream OR /files/library
      "is_big_paste": false
    }
  ]
}
```

**The `library_file_id` (`libfile_*`) is a separate id.** It's not the same as
`file_id` and we don't yet have its source endpoint pinned down (it's not in
`GET /backend-api/files/<id>`). Hypotheses, in order of likelihood:
1. Returned in the body of `POST /backend-api/files/process_upload_stream`.
2. Available at `GET /backend-api/files/library?file_id=<file_id>`.
3. Derived locally by the client (unlikely — it's prefixed `libfile_` and 32 hex chars).

If you want to send a file purely via API without the UI, this is the open
question to nail down.

### 11.8 Server-side flow for "ask about a file"

Once you send a message with attachments, the backend automatically:

1. Inserts a tool message with `author.name: "file_search"` (or similar) and
   `content_type: "multimodal_text"`. `parts[0]` is an instruction to the
   model: `"Make sure to include fileciteturn0file0 in your response to
   cite this file..."`. `parts[1]` is the file contents (or a chunk).
2. The model's response includes the citation token `fileciteturn0file0`
   (or similar) which the client renders into a clickable link.
3. The assistant message stores `metadata.citations[]` and
   `metadata.content_references[]` describing the citation:
   ```json
   "content_references": [{
     "matched_text": "fileciteturn0file0",
     "type": "file",
     "name": "jc_test_marker.txt",
     "id": "file_<id>",
     "source": "my_files",
     "input_pointer": {
       "message_index": 0, "message_id": "<tool-msg-id>", "file_index": 0
     }
   }]
   ```

This means **for small text files, the file content is just stuffed verbatim
into context** — no embedding round-trip required. For larger files, RAG
kicks in via the retrieval index from §11.5.

### 11.9 End-to-end working script (UI-driven)

```bash
osascript <<'EOF'
tell application "Google Chrome"
  activate
  set theTab to active tab of front window
  set js to "(async () => {
    const inp = document.querySelector('#upload-files');
    const content = 'SECRET: pinetree-banana\\nlive content';
    const file = new File([content], 'probe.txt', {type:'text/plain'});
    const dt = new DataTransfer(); dt.items.add(file);
    inp.files = dt.files;
    inp.dispatchEvent(new Event('change', {bubbles:true}));
    // wait for chip
    await new Promise(r => setTimeout(r, 1500));
    const ed = document.querySelector('#prompt-textarea');
    ed.focus();
    ed.innerHTML = '<p>What SECRET is in the file?</p>';
    ed.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:'What SECRET is in the file?'}));
    await new Promise(r => setTimeout(r, 300));
    document.querySelector('[data-testid=send-button]').click();
    return 'done';
  })()"
  return execute theTab javascript js
end tell
EOF
```

(Note: the `execute javascript` will return immediately because the value is
a Promise. Sleep ~5 s in shell, then call
`execute javascript "document.querySelectorAll('[data-message-author-role=assistant]').length"` to confirm a new
assistant turn arrived, then GET the conversation history.)

### 11.10 Reading the answer

```bash
osascript <<'EOF'
tell application "Google Chrome"
  set theTab to active tab of front window
  set js to "window.__a=null;(async()=>{const id=location.pathname.split('/c/')[1];const r=await fetch('/backend-api/conversation/'+id,{credentials:'include',headers:{Authorization:'Bearer '+window.__chatgptToken}}).then(r=>r.json());const msgs=Object.values(r.mapping).filter(v=>v.message&&v.message.author?.role==='assistant'&&v.message.content?.parts?.length);const last=msgs[msgs.length-1];window.__a=JSON.stringify({text:last.message.content.parts[0],citations:last.message.metadata.content_references},null,2);})();'kicked';"
  return execute theTab javascript js
end tell
EOF
sleep 1
osascript -e 'tell application "Google Chrome" to return execute (active tab of front window) javascript "window.__a||\"still null\""'
```

---

## 12. Open questions / TODO

- [x] ~~Confirm field name: `thinking_effort` vs `reasoning_effort`~~ → Confirmed `thinking_effort` (stored in conversation message metadata exactly).
- [x] ~~File upload, ask question, capture response~~ → Done (§11).
- [ ] Capture the actual live `POST /backend-api/f/conversation` body bytes (we have the field names from the stored conversation but haven't seen the full request envelope). Workarounds in §7.3. The simplest unblock is asking the user to "Copy as cURL" once from DevTools.
- [ ] Find the `POST /backend-api/files/process_upload_stream` *response* body — specifically whether it returns the `library_file_id` (`libfile_*`) or whether that comes from somewhere else. Without it, building a fully-API-driven file upload from scratch (no UI) requires guessing.
- [ ] Document `chat-requirements/prepare`/`finalize` payload (sentinel PoW). Probably not worth it unless we want a curl-only client; the client-side challenge changes regularly.
- [ ] Map the modal model-picker UI (`Configure...`) — find the testids for switching to GPT-5.4 Thinking etc, since the pill menu only exposes the current major version's three flavors.
- [ ] Verify whether `GET /backend-api/settings/user_last_used_model_config?...` alone is enough to switch model+effort server-side for the next message, without UI interaction. (The UI fires this on each pick — but is the backend reading it on the next conversation, or does the conversation POST carry `model` directly? Probably the latter; persistence is for the next page load.)
- [ ] Find a stable way to get the PoW token from outside the browser if we want a non-headless API client (probably requires running their `sdk.js` in jsdom or similar).

---

## 13. Failure modes / gotchas

- **JS-from-Apple-Events disabled** → osascript returns the explanatory error. Tell the user to enable it.
- **No chatgpt.com tab open** → `chatgpt_lib.ensure_chatgpt_available()` (opens the dedicated profile-pinned window; a bare `open -a` would land in whatever profile is frontmost, possibly logged out).
- **`execute javascript` hangs on a tab** → the tab's renderer is frozen/busy (common for long-idle background tabs). Don't poll it; target a tab in the dedicated window. The lib raises ChatGPTError after its subprocess timeout.
- **Page not yet loaded** → you'll see only 6 buttons (composer chrome). Wait 1–2 s and re-snapshot.
- **Radix menu won't open with `.click()`** → use `focus()` + `KeyboardEvent('Enter')`. (`pointerdown`/`mousedown` synthetic events also fail.)
- **Async fetch result invisible to AppleScript** → stash to `window.__var`, sleep, read back.
- **Captured 0 fetches but flow clearly happened** → the bundle has a stored fetch reference. Use Performance API for URLs, CDP for bodies.
- **Page client-navigates** (e.g. `/` → `/c/<id>`) — most `window.*` globals survive (no full reload). But verify with a sentinel like `window.__patched` before assuming.
- **Sentinel chat-requirements failure** → may be your account being flagged. Reload the page and retry. The full POW flow is run on every send.

---

## 14. Captured raw evidence (for reproducibility)

### 14.1 Auth session response (truncated)
```
{
  "WARNING_BANNER": "...",
  "user": {"id":"user-...","email":"<user>@..","name":"..."},
  "expires": "2026-08-07T05:54:07.579Z",
  "accessToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzQ0ZTY1...",
  "authProvider": "auth0",
  "sessionToken": "...",
  "rumViewTags": {...}
}
```

### 14.2 `/backend-api/me` response (truncated)
```
{ "object":"user", "id":"...", "email":"...", "name":"...",
  "groups":["labs","chatgpt-browsing","chatgpt-supercalc","chatgpt-plugin-developers"],
  "orgs":{"object":"list","data":[{ "id":"org-...", "title":"Personal", "personal":true, ...}]},
  "country":"US","region":"California","first_name":"..."}
```

### 14.3 `/backend-api/accounts/check/v4-2023-04-27` (truncated, key fields)
```
"plan_type": "pro",
"entitlement": {"subscription_plan":"chatgptpro","has_active_subscription":true,
                "expires_at":"2026-05-18T07:56:54+00:00","billing_period":"monthly"},
"features": [..."gpt5","gpt5_pro","o3","o3_pro","o4_mini","tools","tools2","tools3",...]
```

### 14.4 Effort selection persistence call
```
GET /backend-api/settings/user_last_used_model_config?model_slug=gpt-5-5-thinking&thinking_effort=max
```
This request fired the moment "Heavy" was clicked in the submenu. No request
body; everything is in the query string.

### 14.5 File upload — verified responses

**`POST /backend-api/files`** with body
`{file_name:"jc_test2.txt", file_size:42, use_case:"my_files"}`:
```json
{"status":"success",
 "upload_url":"https://sdmntprcentralus.oaiusercontent.com/files/<azure-uuid>/raw?se=...&sp=w&sv=...&sig=...",
 "file_id":"file_00000000<32hex>"}
```

**Empty body 422** (great schema disclosure):
```json
{"detail":[
  {"type":"missing","loc":["body","file_name"],"msg":"Field required"},
  {"type":"missing","loc":["body","use_case"],"msg":"Field required"}]}
```

**`POST /backend-api/files/process_upload_stream`** empty-body 422:
```json
{"detail":[
  {"type":"missing","loc":["body","file_id"],"msg":"Field required"},
  {"type":"missing","loc":["body","file_name"],"msg":"Field required"},
  {"type":"missing","loc":["body","use_case"],"msg":"Field required"},
  {"type":"missing","loc":["body","index_for_retrieval"],"msg":"Field required"}]}
```

**`GET /backend-api/files/<file_id>`**:
```json
{"id":"file_<id>","owner_id":"user-...","name":"jc_test_marker.txt",
 "creation_time":"2026-05-09T06:10:12+00:00","state":"ready","ready_time":null,
 "size":105,"metadata":null,"use_case":"my_files","retrieval_index_status":null,
 "file_size_tokens":null,"variants":null,"expiration_time":null,
 "mime_type":"text/plain","no_auth_user_upload":false,"file_extension":"txt"}
```

### 14.6 Sentinel chat-requirements/prepare response

```json
{"persona":"chatgpt-paid",
 "prepare_token":"gAAAAABp_tEAmX2Tw...<long base64 blob>",
 "turnstile":{"required":true,"dx":"<base64 challenge data>"}}
```

The `dx` blob is fed to the Turnstile JS challenge engine (loaded as
`https://chatgpt.com/sentinel/<version>/sdk.js`) which has to compute a
solution. `window.SentinelSDK` is removed from the global scope after
init — by design — so we can't trivially call `SentinelSDK.token(...)`
from a console snippet. To replicate without the official client, you
need to embed and run their sdk.js in a JS sandbox, or use an existing
reverse-engineered solver from the open-source ChatGPT-API community
(those tend to drift; pin a version).

### 14.7 Direct API probe results (POST `/backend-api/f/conversation`)

| Body shape                                                  | Status | Body                                                        |
|-------------------------------------------------------------|--------|-------------------------------------------------------------|
| `{action, model, thinking_effort}`                          | 403    | `Unusual activity has been detected from your device. ...`  |
| `{action, model, thinking_effort, messages, parent_message_id, conversation_id}` | 403 | (same)                                    |
| `{messages: []}`                                            | 422    | `"Invalid conversation body"`                               |

The shift from 422 (schema) to 403 (anti-abuse) on the larger bodies
confirms `action`, `model`, `thinking_effort`, `messages`,
`parent_message_id`, `conversation_id` are valid request fields.

---

*Operational note updated: 2026-07-28. Historical evidence captured:
2026-05-08.* Update when bundle hashes drift, endpoint paths change, or
someone finally captures the live `/f/conversation` request bytes (use CDP
via `--remote-debugging-port=9222` next time).
