# WSJ AppleScript Fallback Workflow

Use this path only when neither Claude in Chrome tools
([claude-in-chrome-workflow.md](claude-in-chrome-workflow.md)) nor a host
Chrome plugin ([chrome-plugin-workflow.md](chrome-plugin-workflow.md)) is
available. Check for both first.

The helper `scripts/wsj_research.py` drives the signed-in
`$CHROME_PROFILE_EMAIL` Chrome profile through AppleScript. It never reads
cookies or credentials and never switches profiles. The same authentication
boundary as the browser-tool transports applies: if WSJ is signed out, ask the user to
sign in; do not work around the paywall.

## Commands

Run `status` first, then the discovery or article commands.

| Command | Purpose | Key flags |
|---|---|---|
| `status` | Verify profile and WSJ login | — |
| `frontpage` | Editorially ranked homepage stories | `--max`, `--exclude-opinion`, `--include-extras` |
| `latest` | Latest Headlines feed (50 items) | `--max`, `--exclude-opinion`, `--exclude-video` |
| `search QUERY` | Paginated search with exact date bounds | `--date-range {1d,7d,30d,1yr,all}`, `--sort {relevance,desc,asc}`, `--products`, `--pages`, `--max-results`, `--from`, `--to` |
| `article URL` | Extract one article | `--metadata-only`, `--max-characters` |

All commands print JSON. `search` applies `--from` / `--to` (YYYY-MM-DD, UTC;
`--to` is inclusive through the named day) after retrieval and reports
`truncated: true` when page or result caps can hide results.

## Timing

AppleScript transport is slow. Budget for it instead of aborting:

- Each page navigation can wait up to ~30s for `#__NEXT_DATA__`.
- Each login check can add several seconds before the header renders.
- `search --pages 3` can therefore run for minutes.

Set the shell timeout to at least 300s or run as a background task and poll.
A backgrounded command is usually still working; read its log before calling
it failed.

## Serialization

The helper holds an exclusive lock at
`~/.codex/state/wsj-research/browser.lock` and drives one shared Chrome tab
recorded in `browser.json`. Run one command at a time, sequentially. Parallel
invocations queue on the lock, multiply wall time, and contend for the tab;
they are a known source of flaky failures.

## Exit codes

| Exit | Meaning | Action |
|---|---|---|
| `10` | Signed out | Run `status`. If `status` is authenticated, the failure is page-specific, not a logout — retry a canonical section URL and do not ask the user to sign in. If `status` also fails, ask the user to sign in to WSJ in the `$CHROME_PROFILE_EMAIL` Chrome profile. |
| `11` | JavaScript from Apple Events disabled | Enable *View > Developer > Allow JavaScript from Apple Events* in Chrome, then retry. |
| `12` | Browser targeting/navigation failed | Not an authentication verdict. Multiple same-bundle, headless, or pending-restart Chrome processes can make AppleScript observe a different process than the visible window. Retry with a single Chrome process; prefer the plugin when available. |

If an `article` call dies with AppleScript `Invalid index` / “Can't get item … of every tab,” treat it as transient tab targeting rather than a logout: re-run `status`, then retry that URL alone one more time before dropping the story. The helper checks its saved tab by window and tab id, walks every tab only when that tab is gone, and retries a failed walk once, since tabs opening and closing mid-walk (another browser agent's tab group) make the walk's index go stale.
| `64` | Usage error | Fix the arguments; see `--help`. |

## Diagnostics

Do not import Python modules from the live managed projection of this skill:
importing creates `__pycache__` files, changes the projection hash, and makes
the installer correctly report a local modification. Diagnose the canonical
source instead, or set `PYTHONDONTWRITEBYTECODE=1` when a live-tree import is
genuinely necessary.
