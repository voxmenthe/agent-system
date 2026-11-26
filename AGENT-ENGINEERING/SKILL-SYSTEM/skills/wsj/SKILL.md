---
name: wsj
description: Research The Wall Street Journal through the user's authenticated Chrome profile. Use for a broad overview of current WSJ news, latest-headline monitoring, article extraction or summarization, targeted WSJ searches, historical coverage reviews, and across-time synthesis of intersecting themes such as AI-company financing, listings, demand, hyperscaler capex, cloud infrastructure, power, chips, or private credit. Do not use for generic web research, non-WSJ sources, or attempts to bypass authentication or access controls.
disable-model-invocation: true
---

# WSJ Research

## Overview

Use WSJ's authenticated pages in the user's Chrome session to discover, read,
compare, and synthesize coverage. Every transport below works inside the user's
real, signed-in Chrome, which preserves the subscriber session.

WSJ exposes most discovery and article content in `#__NEXT_DATA__`. Read that
structured payload with page JavaScript, selecting only the fields needed for
the task. Normal structured retrieval does not require scrolling through every
article.

## Choose a Transport

On every host, use the first of these that works:

1. **Claude in Chrome tools.** Use them when your tool list has
   `javascript_tool`, `navigate`, `tabs_context_mcp`, `tabs_create_mcp`, and
   `tabs_close_mcp` from a `claude-in-chrome` or `claude_in_chrome` server:
   `mcp__claude-in-chrome__*` in Claude Code, `mcp__claude_in_chrome__*` in
   Codex. Antigravity lists them under `# claude_in_chrome` and calls them
   through `call_mcp_tool`. They work without bringing Chrome or the tab to
   the front.
2. **The helper script** `scripts/wsj_research.py`, on a host with a shell. It
   connects to Claude in Chrome itself, so it also stays in the background. It
   switches to AppleScript, in a Chrome window of its own, only when Claude in
   Chrome does not connect after one retry. The `transport` field of its JSON
   says which one ran.
3. **The host's own browser tools**, such as Codex's `chrome:control-chrome`
   or Antigravity's `open_browser_url` and `browser_*` tools. These can bring
   Chrome to the front. Use them only when the helper cannot run (no shell) or
   fails with exit `11` or `12`.

Do not try to start a missing transport's server or extension mid-task. When
you move to the next transport, tell the user which transport ran and why.

### When Claude in Chrome counts as failed

Move past the Claude in Chrome tools only when one of these holds:

- The tools are not in your tool list.
- `tabs_context_mcp` reports no connected browser or extension, or times out,
  and it fails the same way on one retry.

These are not connection failures. Fix the call and stay on Claude in Chrome:

- A result that comes back as `[BLOCKED: …]`, `[TRUNCATED]`, or
  `[value redacted]`, or is cut off. The extension filters what it returns.
  Return smaller slices and URL paths without query strings, and avoid key
  names like `auth`, `token`, or `session`. See
  [claude-in-chrome-workflow.md](references/claude-in-chrome-workflow.md)
  section 3.
- A JavaScript timeout after 45 seconds. Split the work across calls.
- One page that does not load. Retry it, or rediscover its URL.
- A signed-out page. Ask the user to sign in (see the authentication boundary
  below).

The helper script applies the same rule to its own connection.

### First: Claude in Chrome

Read [claude-in-chrome-workflow.md](references/claude-in-chrome-workflow.md)
before the first call. The sequence:

1. Call `tabs_context_mcp`. If it lists tabs, create your own with
   `tabs_create_mcp`. Outside Claude Code, agents and the helper script share
   one tab group, so the listed tabs may be theirs. If there is no group, call
   `tabs_context_mcp` with `createIfEmpty: true` and use the tab it creates.
   Use only your own tab for the whole task.
2. `navigate` that tab to the WSJ page you need, then verify sign-in with one
   `javascript_tool` call that returns booleans only.
3. Read the needed `#__NEXT_DATA__` fields with `javascript_tool`. Reach other
   WSJ pages with `fetch()` from inside that tab, not with new tabs.
4. Stay in the background: no clicks, scrolling, screenshots, or window
   resizing unless the user asks to watch.
5. When finished, close your tab with `tabs_close_mcp`. If you created the
   group and other tabs have joined it, leave your tab open: closing the
   group's first tab ends the group for everyone in it.

### Second: The Helper Script

Read [applescript-fallback.md](references/applescript-fallback.md) for the
command reference and failure table. Operating rules:

- Run its `status` command before its discovery or article commands. Check
  `transport` in the output, and tell the user when it is `applescript` and
  why (the helper's stderr says).
- Serialize. One command at a time; the helper holds an exclusive lock and
  drives one tab. Never run WSJ commands in parallel.
- Through Claude in Chrome a command takes about 4 seconds. Through AppleScript,
  each navigation can wait up to ~30s and multi-page searches run for minutes.
  Use a shell timeout of at least 300s or a background task, and read a
  backgrounded job's log before calling it failed.
- Exit `10` means signed out; stop and ask the user to sign in. But verify
  with `status` first: if `status` reports authenticated, the exit `10` is
  page-specific, not a logout — do not ask the user to sign in again, and
  prefer canonical section URLs (`/finance/...`, `/business/...`) over old
  `/articles/` slugs.
- Exit `11` means Chrome has disabled JavaScript from Apple Events.
- Exit `12` means the browser could not be reached or a navigation failed. It
  does **not** prove that WSJ is signed out or inaccessible. Do not describe it
  as an authentication failure, and do not claim that article retrieval
  succeeded.

### Third: Host Chrome Plugin

When neither the Claude in Chrome tools nor the helper script works and the
host's Chrome plugin is available, follow the `chrome:control-chrome` skill and
use its browser-client API.

1. Select the Chrome browser family and read its complete browser
   documentation before interacting with a tab.
2. Name the browser session for the WSJ task.
3. Inspect open Chrome tabs and claim a suitable `wsj.com` tab when one exists.
   Otherwise create one agent tab and navigate it to the required WSJ URL.
4. Verify the page is signed in before using subscriber content. Check for a
   non-generic account control, absence of `Sign In` / `Log In`, and the boolean
   presence of the entitlement field. Never return or print the entitlement
   value.
5. Use read-only Playwright evaluation to extract semantic headings and the
   specific `props.pageProps` fields described in
   [site-map.md](references/site-map.md).
6. Open the representative articles needed to support the synthesis. A
   homepage headline or search snippet is discovery evidence, not article-body
   evidence.
7. Finalize the Chrome session according to the Chrome plugin instructions.
   Release claimed user tabs and omit disposable research tabs unless the user
   explicitly needs one kept open.

Read [chrome-plugin-workflow.md](references/chrome-plugin-workflow.md) for the
tab, authentication, extraction, and recovery sequence.

### Authentication boundary

Always use the Chrome session for the profile named by `$CHROME_PROFILE_EMAIL`. If the
WSJ page shows a signed-out state, ask the user to sign in in that
Chrome session and retry. Do not enter credentials, inspect cookies, read local
storage, extract tokens, switch profiles, or work around the paywall. Do not
substitute generic web search or another browser for authenticated WSJ content.

## Choose a Workflow

### Broad current-news overview

Read [research-playbook.md](references/research-playbook.md), then:

1. Inspect `https://www.wsj.com/` for editorial rank and section framing.
2. Inspect `https://www.wsj.com/news/latest-headlines` for the chronological
   breaking-news feed.
3. Separate reported news, live coverage, analysis, and Opinion.
4. Deduplicate canonical URLs and open the small set of articles needed to
   support the overview.
5. Report dominant themes, important new facts, competing signals, and stories
   likely to matter next. Link every cited story by title.

Homepage rank is editorial importance; Latest Headlines order is recency. Do
not conflate them. Exclude Opinion or video in the extraction step when the
request calls for straight news.

### Targeted or across-time research

Read [research-playbook.md](references/research-playbook.md), then:

1. Turn the topic into several overlapping concept baskets.
2. Use focused WSJ search URLs or the site's search UI to discover vocabulary,
   actors, anchor stories, and turning points.
3. Run narrower date and sort passes to fill the timeline.
4. Deduplicate by canonical URL and open the representative articles.
5. Build an evidence matrix before synthesizing causes, changes, tensions, and
   uncertainty.

WSJ search exposes preset date ranges rather than arbitrary dates. Apply exact
date bounds to the retrieved results and disclose page caps or truncation.
Search does not promise Boolean `AND` semantics; use several focused queries
rather than one overloaded query.

### Read one article

Navigate your agent tab to the canonical article URL, or `fetch()` it from a
signed-in WSJ tab. With the host Chrome plugin, an already-open matching WSJ
tab may be claimed instead. Prefer `articleData.flattenedBody`. A `dom_fallback`
result can contain page furniture; inspect it more cautiously. Metadata alone
is enough when the headline, dek, authors, section, and dates answer the task.
If `body` / `flattenedBody` looks empty, walk the JSON `blocks` array
(`type` + `text`) instead of treating the article as unreadable.

## Evidence and Output Discipline

- Treat homepage summaries and search snippets as discovery evidence, not as
  sufficient support for a nuanced claim. Open the underlying articles.
- For every material claim, record article title, canonical URL, published or
  updated date, and whether the claim is reported fact, attributed view, or
  inference.
- Prefer synthesis and paraphrase. Do not reproduce full articles or long
  passages; quote only short language essential to the analysis.
- Preserve disagreement and chronology. A newer article may update an older
  claim rather than merely corroborate it.
- Label Opinion separately from reported news.
- If the site structure has drifted, follow the read-only recovery steps in
  [site-map.md](references/site-map.md). Do not bypass access controls.
- If a guessed URL returns `dom_fallback` / 404, drop it and rediscover from homepage or Latest rather than reconstructing article text.
