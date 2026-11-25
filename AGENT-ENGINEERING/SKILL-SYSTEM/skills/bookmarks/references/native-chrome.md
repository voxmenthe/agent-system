# Native macOS Chrome fallback

Use this only when the active browser instructions permit native automation
and the request/session authorizes it. Prefer the Chrome connector/plugin when
it works. Its presence does not prove that its transport initialized; a
transport failure does not prove that the account is signed out.

## Bind the correct session and tab

Use AppleScript against the already-running Chrome session. Inspect only the
tab/window metadata necessary to identify the requested session; verify the X
account through its page. Do not bootstrap a profile by reading `Local State`,
restart the browser, launch another profile, or reuse ChatGPT/WSJ-specific
helpers against X.

Record the original window/tab and any temporary-setting states. Prefer one
task-owned tab in the correct existing window when an older X tab times out.
Reusing the same authenticated window was sufficient in the demonstrated
intake; the older tab's timeout was not a login verdict.

Chrome's AppleScript tab ID was returned as **text**. Match that text first,
then resolve its current numeric index. Re-resolve after tab changes; never
target whichever tab happens to be active. With `targetWindow` and
`targetTabID` bound to observed values:

```applescript
set targetIndex to missing value
repeat with i from 1 to count of tabs of targetWindow
  if (id of tab i of targetWindow as text) is targetTabID then
    set targetIndex to i as integer
    exit repeat
  end if
end repeat
if targetIndex is missing value then error "Owned target tab is absent"
```

Keep native navigation/reads serialized. Read only rendered DOM content needed
for the capture. Safely encode JavaScript passed through shell/AppleScript;
source containing quotes, backticks, or `$()` must not become shell code.
Do not read hidden application state or credential-bearing profile/storage
data to hunt for bookmark-added timestamps.

## Using the page helper natively

Not yet exercised over AppleScript; verify each step on first use. Pass the
helper without shell quoting by letting AppleScript read the file:
`execute targetTab javascript (read POSIX file "<skill>/scripts/x-folder.js" as «class utf8»)`.
`execute javascript` cannot await a promise. Start `__xb.go(...)`,
`__xb.open(...)`, or `__xb.more()` without waiting, then poll
`JSON.stringify(__xb.status())`. The final `JSON.stringify(__xb.json())`
returns the whole export to `osascript`'s standard output; redirect it to a
file instead of using `download()`.

## JavaScript setting and cleanup

Native DOM reads need **Chrome → View → Developer → Allow JavaScript from
Apple Events**. Probe with a harmless constant such as `String(1 + 1)` on the
exact target tab and record the prior state. If enabling is required, do so
within existing authorization and browser/host policy; do not silently grant
additional macOS recording or privacy permissions.

After collection, close only task-created tabs and restore the original user
tab/context. If a setting was originally enabled, leave it enabled. If it was
originally disabled and temporarily changed, attempt to disable it again and
verify both the visible checkbox and the harmless probe. A JavaScript-blocked
error is stronger restoration evidence than an automation command returning
success. Dismiss menus before interpreting a blocked or timed-out probe.

Native GUI actions were acknowledged but ineffective during the original
cleanup: the checkbox stayed checked and the probe still returned `2`.
After a small number of meaningfully different attempts, stop repeating the
same ineffective action, record the actual state, and provide the exact manual
cleanup path. Do not claim restoration succeeded or edit Chrome profile files
to force the setting.

| Symptom | Interpretation / recovery |
|---|---|
| Plugin bootstrap fails | Investigate the transport; use a permitted, already-authorized native fallback instead of assuming logout. |
| Native JavaScript is disabled | Identify the setting; do not misreport an authentication or X API failure. |
| Invalid tab index despite a matching-looking ID | Compare IDs as text and resolve the live index again. |
| Old X tab times out | Try one task-owned tab in the same authenticated window and verify the account. |
| Explicit signed-out page | The user must sign in in the selected session; do not handle credentials. |
| Privacy denial or unresponsive GUI action | Report the actual limitation; do not repeatedly toggle controls or expand permissions to make it work. |
