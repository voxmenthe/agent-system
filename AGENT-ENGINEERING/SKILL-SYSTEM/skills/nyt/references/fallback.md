# AppleScript fallback

Use only when the host lacks callable Chrome-plugin tools. Requires macOS,
Python 3, Chrome, automation permission, and JavaScript from Apple Events.
Use the helper from this skill's directory (or an absolute path):

```bash
python3 -B scripts/news_research.py status
# When a known window is required (also applies to status):
python3 -B scripts/news_research.py --window-id WINDOW_ID status
python3 -B scripts/news_research.py --window-id WINDOW_ID frontpage
python3 -B scripts/news_research.py --window-id WINDOW_ID search "artificial intelligence"
python3 -B scripts/news_research.py --window-id WINDOW_ID --metadata-only article CANONICAL_URL
python3 -B scripts/news_research.py --window-id WINDOW_ID --max-characters 12000 article CANONICAL_URL
```

It finds windows already containing this publication and returns candidate window
IDs if ambiguous. Select the window known from task context to be the intended
profile; if that is unknown, ask the user to identify it. It does not verify the
profile identity by reading disk files. Open the site in the intended window if
none exists. Every command creates and closes its own disposable tab; existing
user tabs are not navigated. A shared lock under
`~/.codex/state/publication-research/browser.lock` serializes both helpers.
Serialize plugin use and delegated browser tests as well; the lock cannot govern
other automation tools. State lives outside the installed skill.

Allow several minutes per command (each AppleScript call has a 40-second
limit). Poll background work and inspect its final exit before retrying. If tab
creation times out, inspect Chrome before retrying: creation may have occurred
without returning an ID. Cleanup failure is reported on stderr.

| Exit | Meaning and action |
| --- | --- |
| 0 | Extraction returned; inspect access verdict and completeness. Not proof of subscriber access or a complete article. |
| 10 | Visible sign-in or access gate. Recheck homepage status to distinguish site login from a page-specific gate. Ask user to sign in only when signed out is established. |
| 11 | JavaScript from Apple Events disabled. Ask user to enable View > Developer > Allow JavaScript from Apple Events. |
| 12 | Targeting, navigation, automation, or timeout failure. Not an authentication verdict. Check Chrome responsiveness; do not keep opening tabs or label the site inaccessible. |
| 13 | Challenge detected. Stop for user/browser recovery; do not bypass. |
| 14 | No article paragraphs found. Inspect template or report extraction incomplete. |
| 64 | Rejected URL. Use a canonical HTTPS URL on this publication without queries or fragments. |

Standard argparse usage errors return 2. Authentication is heuristic: `account_visible`
is a UI observation, and `unknown` must stay unknown. The helper intentionally
never emits cookies, tokens, unrelated tab URLs, or full application state.

For aggb and ocsf, check actual exposed tools first. If the documented Node REPL
Chrome surface is missing but shell is available, invoke this helper directly;
do not install standalone Playwright, start a CDP browser, or adapt WSJ's helper.
If neither transport works, return exact failure evidence and request a supported
browser session or user-provided article text. Do not claim a successful read.
