# WSJ Helper Script

`scripts/wsj_research.py` is the second transport in `SKILL.md`, for a host
with a shell. `mkt wsj` calls it too. It drives the signed-in
`$CHROME_PROFILE_EMAIL` Chrome itself and prints JSON. It never reads cookies or
credentials and never switches profiles. The browser-tool transports'
authentication boundary applies: if WSJ is signed out, ask the user to sign in;
do not work around the paywall.

## Transports

`--transport auto`, the default, tries these in order:

1. **Claude in Chrome.** The helper starts `claude --claude-in-chrome-mcp` and
   talks to it over stdio, in the tab group that every client other than Claude
   Code shares. Nothing comes to the front, except when no group exists yet.
   The new group's window then brings Chrome to the front once, and the helper
   hands the front back to the app you were in.
   - If it created the group, it keeps that tab, saved in
     `~/.codex/state/wsj-research/claude-in-chrome.json`, and reuses it. That
     keeps the group and its window, because closing the group's first tab
     would end the group.
   - In a group someone else created, it adds a tab for the run and closes it
     afterward. It never touches another tab in the group.
   - Results come back as gzip+base64 parts, which pass the extension's output
     filters intact. A damaged part fails the command with exit `12` rather
     than corrupting text.
2. **AppleScript.** Used only when Claude in Chrome does not connect after one
   retry: `claude` missing, no connected browser, or no answer within 20
   seconds. stderr says why. It drives a window the helper opened itself with
   `make new window`, never a tab you opened, and checks that window's profile
   once. Creating the window brings Chrome to the front, and the helper hands
   the front back. The window is reused, through `browser.json`, until someone
   closes it.

`--transport claude-in-chrome` or `--transport applescript` forces one, with no
fallback. The `transport` field of every command's JSON says which one ran.

## Commands

Run `status` first, then the discovery or article commands.

| Command | Purpose | Key flags |
|---|---|---|
| `status` | Verify the transport and WSJ login | — |
| `frontpage` | Editorially ranked homepage stories | `--max`, `--exclude-opinion`, `--include-extras` |
| `latest` | Latest Headlines feed (50 items) | `--max`, `--exclude-opinion`, `--exclude-video` |
| `search QUERY` | Paginated search with exact date bounds | `--date-range {1d,7d,30d,1yr,all}`, `--sort {relevance,desc,asc}`, `--products`, `--pages`, `--max-results`, `--from`, `--to` |
| `article URL` | Extract one article | `--metadata-only`, `--max-characters` |

`--transport` goes before the command. `search` applies `--from` / `--to`
(YYYY-MM-DD, UTC; `--to` is inclusive through the named day) after retrieval
and reports `truncated: true` when page or result caps can hide results.

## Timing

Through Claude in Chrome, one command took about 4 seconds on 2026-11-24
(homepage 4.7, article 3.7). AppleScript is slower:

- Each page navigation can wait up to ~30s for `#__NEXT_DATA__`.
- Each login check can add several seconds before the header renders.
- `search --pages 3` can therefore run for minutes.

Set the shell timeout to at least 300s or run as a background task and poll.
A backgrounded command is usually still working; read its log before calling
it failed.

## Serialization

The helper holds an exclusive lock at
`~/.codex/state/wsj-research/browser.lock` for either transport and drives one
tab. Run one command at a time, sequentially. Parallel invocations queue on the
lock and multiply wall time.

## Exit codes

| Exit | Meaning | Action |
|---|---|---|
| `10` | Signed out | Run `status`. If `status` is authenticated, the failure is page-specific, not a logout — retry a canonical section URL and do not ask the user to sign in. If `status` also fails, ask the user to sign in to WSJ in the `$CHROME_PROFILE_EMAIL` Chrome profile. |
| `11` | JavaScript from Apple Events disabled (AppleScript only) | Enable *View > Developer > Allow JavaScript from Apple Events* in Chrome, then retry. |
| `12` | The browser could not be reached, a navigation timed out, or a result arrived damaged | Not an authentication verdict, and no article was retrieved. Read stderr. "Chrome opened the helper's window in profile …" means Chrome's most recently used profile is another one: use a `$CHROME_PROFILE_EMAIL` window once, then retry. |
| `64` | Usage error | Fix the arguments; see `--help`. |

An AppleScript `Invalid index` / "Can't get item … of every tab" error is
transient tab targeting, not a logout: re-run `status`, then retry that URL
alone once before dropping the story.

## Diagnostics

Do not import Python modules from the live managed projection of this skill:
importing creates `__pycache__` files, changes the projection hash, and makes
the installer correctly report a local modification. Diagnose the canonical
source instead, or set `PYTHONDONTWRITEBYTECODE=1` when a live-tree import is
genuinely necessary.
