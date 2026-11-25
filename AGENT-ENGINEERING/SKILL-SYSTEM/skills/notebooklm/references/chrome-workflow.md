# Browser-Tool Workflow

Use this path when the shell cannot drive Chrome through AppleScript, when you
need to see the app, or when you need to recapture an RPC. That covers a host
without `osascript` access, `nblm.py` exiting `11` or `12`, and visual checks.
It uses the same `scripts/nblm.js` client as the CLI. Steps 1–4 were run
with Claude-in-Chrome on 2026-10-23, with the packaged client loaded in the
page; the run stopped before `uploadPicked` so as not to add a duplicate
source. `uploadPicked` hands each picked file to `uploadFile`, which the CLI
exercised end to end, and `createAudio` likewise ran through the CLI. The
Codex Chrome plugin notes at the end are an untested adaptation.

## 1. Get a tab and check the session

Call `tabs_context_mcp`, create a tab, and navigate it to
`https://notebook.google.com/`. Then confirm the account without returning any
token:

```js
({account: WIZ_global_data.oPEP7c, signedIn: Boolean(WIZ_global_data.SNlM0e)})
```

Proceed only if `account` is `$CHROME_PROFILE_EMAIL` and `signedIn` is true.
Otherwise ask the user to sign in in that Chrome profile. Never type
credentials.

## 2. Load the client

Read `scripts/nblm.js` and pass its full text to `javascript_tool`. It
evaluates to `nblm v1 ready`. `javascript_tool` runs in the page's main world,
so `window.nblm` persists across the app's in-page navigation, for example
opening a notebook from the home page. It is lost on a reload or a `navigate`
call; load it again then.

Code injected through AppleScript, which is what `nblm.py` does, runs in a
separate isolated world. A copy loaded there is invisible to `javascript_tool`,
and the reverse is also true.

## 3. Call it

Each `javascript_tool` call can `await` one or a few client calls. Return
compact objects. Examples:

```js
const nb = await nblm.createNotebook('Sliding-window beats linear attention');
nb.id
```

```js
await nblm.listArtifacts('<notebook id>')
```

Keep each call short. Poll a generating artifact with repeated
`listArtifacts` calls 15–30 s apart. Do not hold one long `waitForArtifact`
await inside a single tool call.

The extension's output filter blanks values that look like query strings,
cookies, or tokens; it once blanked a long PDF file name as a "JWT token".
Return ids, titles, sizes, and statuses, and slice long strings.

## 4. Upload a file

The app opens a native file dialog, which the extension cannot drive. The
client therefore brings its own input:

1. `nblm.filePicker()` adds an `<input type=file aria-label="nblm file input">`.
2. `find` with the query "nblm file input" returns its ref.
3. `file_upload` with that ref and the absolute path. Repository paths were
   accepted here; the extension caps one call at 10 MB.
4. `await nblm.uploadPicked('<notebook id>')` uploads every picked file and
   removes the input.
5. `await nblm.waitForSources('<notebook id>')` returns once each source is
   `ready`, usually within seconds for a paper.

## 5. Generate audio

```js
await nblm.createAudio('<notebook id>', {
  format: 'deep_dive', length: 'short', language: 'en',
  focus: 'Both hosts are experts in this field. The focus is on deeply exploring every single topic at a PhD level.',
})
```

The call returns the artifact id at once; generation continues on Google's
side even if the tab closes. Options and their limits are in
[audio-overview.md](audio-overview.md).

## 6. Download

The audio URLs are not readable from the notebook page because of CORS. The
app's own Download menu item calls
`window.open(<mp4_download url>, '_blank')`, and Chrome saves the attachment
to `~/Downloads/<Title_With_Underscores>.m4a`. Either:

- run `python3 scripts/nblm.py download <notebook> <artifact> --out TEMP/`
  from the shell, if AppleScript works; or
- in the page, run
  `window.open((await nblm.listArtifacts(id)).find(a => a.id === artifactId).audio.media.find(m => m.kind === 'mp4_download').url, '_blank')`.
  Then move the new `.m4a` out of `~/Downloads` with the shell.

Do not use the `mp4` rendition for downloads. It redirects to `googlevideo.com`
and is throttled to about twice playback speed. The user asked for the audio
file, so the download itself needs no extra confirmation. Do not download
episodes they did not ask for.

## 7. Finish

Close the tabs you created. The notebook and its audio stay in the user's
account.

## Codex Chrome plugin (untested adaptation)

The same client should work through `tab.playwright.evaluate`. Evaluate the
file text once per page load, then call
`tab.playwright.evaluate(() => nblm.listNotebooks())` and similar. For uploads,
call `nblm.filePicker()`, then use Playwright's `setInputFiles` on
`#nblm-file-input`. For downloads, prefer `nblm.py download`, or wait for the
browser download event after `window.open` of the `mp4_download` URL. Follow
the plugin's own session-naming and tab-finalizing rules.
