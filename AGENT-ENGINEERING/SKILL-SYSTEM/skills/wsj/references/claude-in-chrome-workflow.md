# WSJ Through Claude in Chrome

This is the first transport on every host. The Claude in Chrome extension runs
inside the user's signed-in Chrome, and the tools reach it through a local
bridge. Your tab group lives in its own window, and pages there report
themselves as visible and focused. Nothing has to come to the front, as long as
you only navigate and run JavaScript.

## Tool names

| Host | Tool names |
|---|---|
| Claude Code | `mcp__claude-in-chrome__javascript_tool`, `…__navigate`, `…__tabs_context_mcp`, `…__tabs_close_mcp` |
| Codex | `mcp__claude_in_chrome__javascript_tool`, and so on |

Other MCP clients show the same tool names under their own server prefix. In
Codex, the server is a config entry, `[mcp_servers.claude_in_chrome]`, that
runs `claude --claude-in-chrome-mcp`, an undocumented Claude Code flag. If the
tools are absent, use the next transport in `SKILL.md` and tell the user.
Registering the server is the user's config change, not a task step.

## 1. Get one tab

Call `tabs_context_mcp` with `createIfEmpty: true`. It creates this session's
tab group and returns a tab id. Do this once per task and reuse that tab.
Creating a group is the one step observed bringing a window to the front when
called from a non-Claude client. The tools act only on tabs in your own group,
so they cannot claim a WSJ tab the user already has open.

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
and the last expression is the result. Its output channel has limits:

- A result containing a URL with a query string is replaced by
  `[BLOCKED: Cookie/query string data]`. Return `url.split("?")[0]` or paths
  only.
- Long results are truncated (observed near 1,000 characters). Return one
  compact slice per call.
- The tool stops waiting after about 45 seconds. Split long fetch batches
  across calls.
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

Close your tab with `tabs_close_mcp`. Closing the group's last tab removes the
group.

## Recovery

- **No connected browser, or a call times out:** call `tabs_context_mcp` once
  more. If it still fails, Chrome or the extension is not connected. Use the
  next transport and tell the user.
- **Signed out:** ask the user to sign in to WSJ in that Chrome session and
  retry.
- **Empty structured data:** follow the drift recovery in
  [site-map.md](site-map.md).
