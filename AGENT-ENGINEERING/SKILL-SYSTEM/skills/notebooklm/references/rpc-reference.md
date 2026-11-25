# Gemini Notebook RPC Reference

Observed in the owner's signed-in Chrome session on 2026-10-22/23
against build `boq_labs-tailwind-frontend_20261021.16_p0`. The site is
`https://notebook.google.com/` ("Gemini Notebook"); media and image hosts still
say `notebooklm`, and the backend is the former NotebookLM `LabsTailwindUi`
service. Nothing here is a public API. Google can change any shape without
notice; `scripts/nblm.js` is the executable form of this page, and the last
section explains how to recapture a call that stops working.

Every shape below was captured from the web app's own traffic unless it is
marked *inferred*.

## Transport

All calls are `POST /_/LabsTailwindUi/data/batchexecute` from a
`notebook.google.com` page, same-origin, using the page's cookies.

Query parameters:

| Param | Value |
|---|---|
| `rpcids` | the RPC id, e.g. `rLM1Ne` |
| `source-path` | the app route the call is made from: `/` or `/notebook/<id>` |
| `bl` | build label, `WIZ_global_data.cfb2h` |
| `f.sid` | session id, `WIZ_global_data.FdrFJe` |
| `hl` | `en` |
| `_reqid` | any increasing integer |
| `rt` | `c` (chunked framing) |

Headers: `content-type: application/x-www-form-urlencoded;charset=utf-8`,
`x-same-domain: 1`, and `x-goog-ext-525006520-jspb: <CTX as JSON>`.

Body: `f.req=<json>&at=<WIZ_global_data.SNlM0e>&`, where
`f.req = [[[rpcId, JSON.stringify(args), null, "generic"]]]`. `SNlM0e` is the
XSRF token. Read it inside the page and send it; never print or persist it.

Response (`rt=c`): a `)]}'` line, then alternating byte-count lines and
one-line JSON arrays. The useful envelope is
`["wrb.fr", rpcId, "<payload JSON string>", null, null, null, "generic"]`. A
`null` payload with a status array at index 5 is a rejection; an `["er", …]`
envelope is a transport error.

Boot data lives in `window.WIZ_global_data` in the page's main world. It also
appears in an inline `<script>` that any JavaScript world can read through the
DOM. Useful keys: `SNlM0e` (XSRF), `FdrFJe` (session id), `cfb2h` (build),
`QrtxK` (`authuser` index, `"0"` here), `oPEP7c` (signed-in email).

### Client contexts

```js
CTX        = [2,null,[1],[1,null,null,null,null,null,null,null,null,null,[1,3]]]
STUDIO_CTX = [2,null,null,[1,null,null,null,null,null,null,null,null,null,[1]],[[1,4,8,10,14,2,3,6]]]
```

`CTX` is the last (or first) argument of notebook, source, and listing calls.
Artifact creation sends `STUDIO_CTX` first.

## Notebook calls

| RPC | Purpose | Args | Payload |
|---|---|---|---|
| `wXbhsf` | List my notebooks, most recent first | `[null,1,null,CTX,null,[[null,null,[]],[[]],[null,[]]]]` | `[[notebook, …]]` |
| `rLM1Ne` | Get one notebook with its sources | `[id,null,CTX,null,1,[[null,null,[]]]]` | `[notebook]` |
| `CCqFvf` | Create an empty "Untitled notebook" | `["",null,null,CTX]` | *inferred:* a notebook record, id at `[2]` (see note) |
| `s0tc2d` | Rename | `[id,[[null,null,null,[null,title]]],CTX]` | notebook record |
| `JFMDGd` | Sharing/collaborator info | `[id,CTX]` | `[[[email,1,[],[name,avatar]]],…]` |
| `VfAZjd` | Auto summary shown on an opened notebook | `[id,CTX]` | `[[[summaryMarkdown], …]]` |

Notebook record: `[title, [source, …], id, emoji, null, meta, …]`. The app
picks the emoji itself after the first source finishes.

The app always creates a notebook untitled, then renames it. Only the
`CCqFvf` request was captured, in a dry run that blocked it; the response shape
comes from the `s0tc2d` response, which returns the same record. `nblm.js`
validates that `[2]` is a UUID and fails loudly otherwise.

## Source calls

| RPC | Purpose | Args |
|---|---|---|
| `o4cbdc` | Register an upload slot for a local file | `[[[fileName,3]],notebookId,CTX]` → `[[[[sourceId],fileName,meta]], …]` |
| `izAoDd` | Add website / YouTube / pasted-text sources | `[[entry, …],notebookId,CTX]` |
| `tr032e` | Source guide (summary and key topics) | `[[[[sourceId]]],CTX]` |

`izAoDd` entries, one per source:

```js
website:  [null,null,[url],null,null,null,null,null,null,null,1]
youtube:  [null,null,null,null,null,null,null,[url],null,null,1]
text:     [null,[title,text],null,2,null,null,null,null,null,null,1]
```

### File upload (three steps)

1. `o4cbdc` registers the slot and returns `sourceId`. The `3` after the
   file name was sent for a PDF; the app's picker accepts pdf, txt, md, docx,
   csv, pptx, epub, audio, image, odt, rtf, and hwp files.
2. `POST /upload/_/?authuser=<QrtxK>`, same-origin, with headers
   `x-goog-upload-command: start`, `x-goog-upload-protocol: resumable`,
   `x-goog-upload-header-content-length: <bytes>`, and body
   `{"PROJECT_ID":notebookId,"SOURCE_NAME":fileName,"SOURCE_ID":sourceId}`.
   The response header `x-goog-upload-url` is the session URL.
3. `POST <session URL>` with `x-goog-upload-command: upload, finalize`,
   `x-goog-upload-offset: 0`, and the raw bytes. Success is
   `x-goog-upload-status: final` and the body
   `OK: Enqueued blob bytes to spanner queue for processing.`

Source record: `[[sourceId], name, meta, [null, statusCode]]`, with the MIME
type at `meta[19]` once processed. Status codes observed in order for one PDF:
`5` awaiting upload → `1` processing → `2` ready (about 3 s for a 387 KB
paper). A source limit of 300 per notebook was shown on this Pro account.

## Studio artifacts (Audio Overview)

| RPC | Purpose | Args |
|---|---|---|
| `R7cb6c` | Create an artifact (audio is type `1`) | see below |
| `gArtLc` | List a notebook's artifacts | `[CTX,notebookId,'NOT artifact.status = "ARTIFACT_STATUS_SUGGESTED"']` → `[[artifact, …]]` |
| `otmP3b` | Suggested focus prompts for the audio dialog | `[CTX,notebookId,[[sourceId],…],1]` → `[[[label,prompt],…]]` |
| `EylDcb` | Usage meter ("AI Usage" bar) | `[CTX]` |

Create an Audio Overview:

```js
["R7cb6c", [STUDIO_CTX, notebookId,
  [null, null, 1, [[[srcA]], [[srcB]]], null, null,
    [null, [focus|null, length|null, null, [[srcA], [srcB]], language, null, format]]]]]
```

Appending `null,null,null,[1]` after the third argument is the dialog's
"Generate later": it saves the configuration without generating.

The audio options tuple, mapped from one dry run per dialog setting:

| Field | Index | Values |
|---|---|---|
| focus ("What should the AI hosts focus on?") | 0 | string, or `null` when empty |
| length | 1 | `1` Short, `2` Default, `3` Long; `null` for Brief |
| sources | 3 | `[[id], …]`; the outer list repeats them as `[[[id]], …]` |
| language | 4 | language code, e.g. `en` |
| format | 6 | `1` Deep Dive, `2` Brief, `3` Critique, `4` Debate |

Lengths offered per format: Deep Dive Short/Default/Long; Critique and Debate
Short/Default; Brief none.

Artifact record (`gArtLc`):

| Index | Meaning |
|---|---|
| 0 | artifact id |
| 1 | title (the app writes it; at first it is the notebook title) |
| 2 | type: `1` audio, `3` video, `4` quiz, `7` infographic (others unmapped) |
| 3 | sources, `[[[id]], …]` |
| 4 | status: `2` generating, `3` ready (others unmapped) |
| 6 | audio block (type 1 only) |
| 10 / 15 | updated / created timestamps, `[seconds, nanos]` |

Audio block `[6]`: `[null, options, url, url, true, media, [seconds, nanos]]`.
`options` echoes the request tuple, with `true` filling index 5. `media` lists
renditions as `[url, kind, mime?]`:

| Kind | URL suffix | Meaning |
|---|---|---|
| 4 | `=m140-dv-mp2` | MP4 audio, the download rendition |
| 1 | `=mm,140` | MP4 audio, streaming |
| 2 | `=mm,hls` | HLS manifest |
| 3 | `=mm,dash` | DASH manifest |

The URLs are on `lh3.googleusercontent.com/notebooklm/…`, need the signed-in
cookies, and are not CORS-readable from `notebook.google.com`. Open one as a
top-level page in the signed-in profile, then read it same-origin there. That
is what `nblm.py download` does.

Usage meter (`EylDcb`): `payload[1]` holds windows
`[null,null,null,null,code,[resetSeconds],usedPct,remainingPct]`. Code `1`
reset about 5 h after the observation (daily), code `2` about 7 days after
(weekly). `payload[3]` lists per-type estimates; audio's was `9.8`. Observed
moves per episode were between about 4 and 10 points, and the value can drift
down between readings.

## Calls seen but not mapped

`ozz5Z`, `sODAg` (`[]` → `[true]`), `I3xc3c` (home page),
`e3bVqc`, `vB2zic`, and `sqTeoe` fire during page loads and returned empty
lists for a fresh notebook. Delete calls for notebooks, sources, and artifacts
were deliberately not captured. Delete things in the app UI, and only when the
user asks.

## Recapturing a call

Use a transport that runs in the page's main world, such as Claude-in-Chrome
`javascript_tool` or a Playwright `evaluate`. AppleScript's world cannot see
the app's `fetch`. The app calls `fetch(Request)`, so read bodies from a clone:

```js
window.__cap = [];
window.__fetch0 = window.__fetch0 || window.fetch;
window.fetch = function (input, init) {
  const u = String(input instanceof Request ? input.url : input);
  if (/batchexecute/.test(u)) {
    const rec = {rpc: (u.match(/rpcids=([^&]+)/) || [])[1]};
    window.__cap.push(rec);
    (input instanceof Request ? input.clone().text() : Promise.resolve(init && init.body))
      .then((b) => { rec.freq = new URLSearchParams(b).get('f.req'); });
  }
  return window.__fetch0.apply(this, arguments);
};
```

Then drive the UI once and read `window.__cap`. Return only `rpc` and `freq`.
The extension's output filter blanks anything that looks like a query string or
cookie, and the request URL carries the session id.

To map a mutating call without performing it, wrap once more and short-circuit
calls whose `rpcids` are not on a read-only list. Return
`new Response(")]}'\n", {status: 500})` after recording `f.req`. The UI shows a
transient error and nothing reaches the server. This is how the audio
format/length matrix, "Generate later", notebook create, and URL/text source
shapes were captured without spending usage. Uploads go through
`XMLHttpRequest`, not `fetch`; guard `XMLHttpRequest.prototype.send` too when
dry-running anything near the source dialog. Reload the tab afterwards to
discard the UI's optimistic state.

The app's file picker creates its `<input type=file>` on demand and calls
`.click()` on it, which opens a native dialog. To drive the real picker,
override `HTMLInputElement.prototype.click` for `type === 'file'` so it
attaches the input to the DOM instead. Then set the file with the extension's
`file_upload` tool.
