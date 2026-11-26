# WSJ Through Claude in Chrome

This is the first transport on every host. The Claude in Chrome extension runs
inside the user's signed-in Chrome, and the tools reach it through a local
bridge. Your tab group lives in its own window, and pages there report
themselves as visible and focused. Nothing has to come to the front, as long as
you only navigate and run JavaScript.

## Tool names

| Host | Tool names |
|---|---|
| Claude Code | `mcp__claude-in-chrome__javascript_tool`, `…__navigate`, `…__tabs_context_mcp`, `…__tabs_create_mcp`, `…__tabs_close_mcp` |
| Codex | `mcp__claude_in_chrome__javascript_tool`, and so on |
| Antigravity | `call_mcp_tool` with `ServerName: "claude_in_chrome"` and `ToolName: "javascript_tool"`, and so on |

Other MCP clients show the same tool names under their own server prefix.
Antigravity lists MCP tools lazily, under a `# claude_in_chrome` heading in the
system prompt rather than as top-level tools. Each tool's input schema is in
`~/.gemini/antigravity-cli/mcp/claude_in_chrome/<tool>.json`. Antigravity's own
top-level browser tools (`open_browser_url`, `read_browser_page`,
`execute_browser_javascript`, `browser_subagent` and the other `browser_*`
tools) are the host's own browser, the third transport. Each host registers
the server as a config entry that runs `claude --claude-in-chrome-mcp`, an
undocumented Claude Code flag. If the tools are absent, use the next transport
in `SKILL.md` and tell the user. Registering the server is the user's config
change, not a task step.

## 1. Get one tab

Each Claude Code session has a tab group of its own. Every other client (Codex,
Antigravity, and the helper script, which all run `claude --claude-in-chrome-mcp`)
shares one group. So:

1. Call `tabs_context_mcp`. If it lists tabs, create your own with
   `tabs_create_mcp`. The listed tabs may belong to another agent or the
   helper script; never navigate or close them.
2. If there is no group, call `tabs_context_mcp` with `createIfEmpty: true`. It
   creates the group in a new window and returns that window's tab. Use it.

Keep that one tab for the whole task. Creating a group is the one step that
brings Chrome to the front, from any client except Claude Code. Adding a tab
to an existing group does not. The tools act only on tabs in the group, so
they cannot claim a WSJ tab the user already has open.

## 2. Navigate and verify sign-in

Call `navigate` with the tab id and `https://www.wsj.com/` (or the page you
need). The homepage took about 12 seconds. Then make one `javascript_tool` call
that returns booleans only:

```js
(() => {
  const raw = document.querySelector("#__NEXT_DATA__")?.textContent || "";
  let pageProps = {};
  try { pageProps = JSON.parse(raw)?.props?.pageProps || {}; } catch {}
  const controls = [...document.querySelectorAll("a,button")];
  const label = (e) => `${e.getAttribute("aria-label") || ""} ${e.textContent || ""}`.trim();
  return {
    signedOut: controls.some((e) => /^(sign in|log in)$/i.test((e.textContent || "").trim())),
    accountControl: controls.some((e) => /account|profile|my wsj/i.test(label(e)) && !/sign in|log in/i.test(label(e))),
    entitlementPresent: Boolean(pageProps.dylanEntitlementToken),
  };
})()
```

Interpret the result with the authentication signals in
[site-map.md](site-map.md). Never return the entitlement value, cookies, or
storage.

## 3. Read pages

`javascript_tool` evaluates an expression in the page. Top-level `await` works,
and the last expression is the result. An async function's promise is returned
unawaited unless you write `await` before it. Its output channel filters what it
returns (store build 1.0.109 of the extension, read 2026-11-24):

- Each string longer than 1,000 characters is cut and marked `[TRUNCATED]`.
  Arrays keep their first 100 items, and a whole result stops at 51,200
  characters. Return one compact slice per call.
- A string that contains `=` together with `;` or `&` (a URL with a query
  string, for example) becomes `[BLOCKED: Cookie/query string data]`. Return
  `url.split("?")[0]` or paths only. A string that is entirely base64, entirely
  long hex, or shaped like a JWT is blocked too.
- A key whose name contains `auth`, `token`, `session`, `secret`, `password`,
  `credential`, `bearer` or `api_key`, or is `cookie`, comes back as
  `[BLOCKED: …]`, so `authors` is blocked. Rename keys (`writers`, `signed_in`).
- A top-level array comes back only as `Array(n)`. Return an object that holds
  the array.
- The tool stops waiting after 45 seconds. Split long fetch batches across
  calls.
- `const` and `function` declarations do not persist between calls. Attach
  helpers and results to `window` (for example `window._res`).
- Navigation clears `window` state. Stay on one signed-in WSJ page and
  `fetch()` everything else, or redefine helpers after each `navigate`.

Read another WSJ page without navigating by fetching it inside the page, so the
browser sends the session itself:

```js
const html = await fetch(url).then((r) => r.text());
const doc = new DOMParser().parseFromString(html, "text/html");
const pageProps = JSON.parse(doc.querySelector("#__NEXT_DATA__").textContent).props.pageProps;
```

Select only the fields named in [site-map.md](site-map.md) and
[chrome-plugin-workflow.md](chrome-plugin-workflow.md) section 3, never all of
`pageProps`. Further notes:

- Live-coverage pages (`/livecoverage/...`) may expose no `articleData`. Read
  the visible posts from `main` text instead.
- If an expected list such as `latestHeadlines` comes back empty, walk
  `pageProps` for objects that carry both a headline and a URL before
  concluding the feed is empty.
- Section sweep, for a window older than Latest Headlines reaches (weekends):
  `fetch()` each section page, collect story URLs with
  `/https:\/\/www\.wsj\.com\/(?:[a-z0-9-]+\/)+[a-z0-9-]+-[0-9a-f]{8}\b/g`
  (stories end in an 8-hex id), and dedupe. Then `fetch()` each story and read
  its `__NEXT_DATA__` metadata to date-filter before reading bodies.
- Body text: `flattenedBody` is an array of blocks. A recursive join works:

  ```js
  const text = n => typeof n === "string" ? n : Array.isArray(n) ? n.map(text).join("")
    : (n?.text ?? "") + text(n?.content ?? []) + text(n?.nested ?? []);
  body.filter(b => b.type === "paragraph").map(text)
  ```

## 4. Stay in the background

Use only `tabs_context_mcp`, `navigate`, `javascript_tool`, and
`tabs_close_mcp`. Clicking, screenshots (`computer`), `resize_window`, and GIF
recording interact with the visible page. Use them only when the user asks to
watch.

## 5. Finish

Close your tab with `tabs_close_mcp`. One exception: if you created the group
and other tabs have joined it, leave your tab open. The group's first tab
anchors it. When that tab closes, the extension drops the group, and its other
tabs stay open in Chrome where no tool can reach them (seen 2026-11-24).
Closing the group's last tab removes the group.

## Recovery

- **No connected browser, or a call times out:** call `tabs_context_mcp` once
  more. If it still fails, Chrome or the extension is not connected. Use the
  next transport, the helper script, and tell the user. Output filtering,
  timeouts of single scripts, and one page failing to load are not reasons to
  switch (`SKILL.md`, "When Claude in Chrome counts as failed").
- **Signed out:** ask the user to sign in to WSJ in that Chrome session and
  retry.
- **Empty structured data:** follow the drift recovery in
  [site-map.md](site-map.md).
