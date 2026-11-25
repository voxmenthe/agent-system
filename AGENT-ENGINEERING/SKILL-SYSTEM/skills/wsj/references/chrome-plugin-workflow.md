# WSJ Chrome Plugin Workflow

This is the second transport: the host's own Chrome plugin. Use it only when
Claude in Chrome tools are absent (see `SKILL.md`). Use this workflow after
selecting Chrome and reading the complete `chrome:control-chrome` browser
documentation. Reuse that browser binding for the whole task. Do not hard-code
a plugin cache path in this skill.

Page-reading notes that apply to every transport (fetching other pages from
one tab, live coverage, empty feeds, section sweeps, body text) are in
[claude-in-chrome-workflow.md](claude-in-chrome-workflow.md) section 3.

## 1. Name the session and obtain a tab

Name the session before opening or claiming tabs. Inspect `chrome.user.openTabs()`
for a suitable `wsj.com` page. Claim the exact returned tab object when one is
already open; otherwise create one tab with `chrome.tabs.new()` and navigate it
to the required WSJ URL.

Choose a tab from its current URL, title, recency, and tab group. Do not guess a
tab ID and do not substitute whichever tab happens to be frontmost.

For direct navigation:

```js
await tab.goto("https://www.wsj.com/");
await tab.playwright.waitForLoadState({
  state: "domcontentloaded",
  timeoutMs: 15000,
});
await tab.playwright.locator("#__NEXT_DATA__").waitFor({
  state: "attached",
  timeoutMs: 15000,
});
```

## 2. Verify authenticated access

Use one read-only page evaluation. Return booleans and labels, never the
entitlement value:

```js
const access = await tab.playwright.evaluate(() => {
  const raw = document.querySelector("#__NEXT_DATA__")?.textContent || "";
  let pageProps = {};
  try {
    pageProps = JSON.parse(raw)?.props?.pageProps || {};
  } catch {}

  const controls = [...document.querySelectorAll("a,button")];
  const signedOut = controls.some((element) =>
    /^(sign in|log in)$/i.test((element.textContent || "").trim()),
  );
  const accountControl = controls.some((element) => {
    const label = `${element.getAttribute("aria-label") || ""} ${
      element.textContent || ""
    }`.trim();
    return /account|profile|my wsj/i.test(label) && !/sign in|log in/i.test(label);
  });

  return {
    signedOut,
    accountControl,
    entitlementPresent: Boolean(pageProps.dylanEntitlementToken),
  };
});
```

Treat an explicit sign-in control as signed out. On currently observed pages,
an account control plus `entitlementPresent: true` verifies the subscriber
session. Older `/articles/` templates may render no account control; there
`entitlementPresent: true` with no sign-in control is sufficient. If other
signals conflict, inspect the visible header and page type; do not infer
access from embedded article body data alone.

Never inspect cookies, local storage, Chrome profile files, passwords, or
credential stores. Never emit `dylanEntitlementToken` or any other token.

## 3. Extract only the needed page fields

Perform parsing inside `tab.playwright.evaluate()` and return a compact,
JSON-serializable result. Do not return all of `pageProps`, because it contains
authentication and unrelated application state.

### Homepage

Use semantic `main h2` and `main h3` elements for module labels, visible rank,
headline, and link. Recursively match each canonical URL against structured
story objects in the selected page collections to add summary, author,
timestamp, flashline, and module code. Preserve visible order. Exclude Buy Side
and video unless requested.

### Latest Headlines

Navigate to `https://www.wsj.com/news/latest-headlines` and select only the
needed fields from `props.pageProps.latestHeadlines`. Preserve chronological
order and retain `isOpinion`, `isVideo`, and `type` labels.

### Search

Use the query parameters in [site-map.md](site-map.md). Select organic results
from `props.pageProps.searchResults`; exclude `sponsoredContent`. Deduplicate by
canonical URL. Apply exact ISO date bounds after retrieval and state when a page
cap can truncate the interval.

### Article

Select metadata and `props.pageProps.articleData.flattenedBody`. Convert
`paragraph` nodes to prose, `hed` nodes to headings, and the
`ai_summary_bullets` inset to labeled bullets; ignore advertisements. Use
JSON-LD plus semantic `main p` only as a marked `dom_fallback` for a
nonstandard article surface.

Scrolling is not a success criterion. A complete structured payload can be
read without visually scrolling through the page. Scroll only when a required
surface is genuinely lazy-loaded or when visual context is part of the task.

## 4. Recovery

- **Chrome plugin unavailable:** use the AppleScript fallback transport in
  `SKILL.md` and [applescript-fallback.md](applescript-fallback.md). Do not
  replace authenticated WSJ with a generic browser or web search.
- **Extension interruption or disconnection:** follow the Chrome plugin's
  troubleshooting guidance, then reacquire a tab from the existing browser
  binding if the binding remains connected.
- **Signed out:** ask the user to sign in to WSJ in the selected Chrome session
  and retry.
- **Missing structured data:** inspect the exact claimed tab, enumerate
  `props.pageProps` keys without returning their values wholesale, and compare
  one homepage, one latest/search page, and one standard article before
  changing field mappings.
- **Fallback exit `12`:** treat it as an AppleScript target/navigation failure,
  not as evidence that the Chrome session lacks access.
- **Helper diagnostics:** see the diagnostics note in
  [applescript-fallback.md](applescript-fallback.md). Do not import Python
  modules from the live managed projection.

## 5. Finish the browser session

Call `chrome.tabs.finalize({ keep })` once, as the final Chrome action. Omit
disposable research tabs. Claimed user tabs omitted from `keep` are released
rather than closed; keep a tab only when the user needs the live page as a
deliverable or handoff.
