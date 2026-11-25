// nblm.js: in-page client for Gemini Notebook (notebook.google.com, formerly NotebookLM).
//
// Evaluate this whole file in a signed-in https://notebook.google.com tab. It defines
// window.nblm and evaluates to a status string; evaluating it again is harmless. The client
// rides the page's own session: it sends the page's XSRF token with each call and never
// returns it, cookies, or any other credential.
//
// Every call goes to the private batchexecute RPC endpoint the web app itself uses. The
// payload shapes were observed on 2026-10-22 (build boq_labs-tailwind-frontend_20261021.16_p0)
// and are documented in references/rpc-reference.md. Google can change them without notice;
// when a call starts failing, recapture it from the app (see that reference's last section).
(() => {
  const VERSION = 1;
  if (window.nblm?.version === VERSION) return `nblm v${VERSION} ready`;
  if (location.origin !== 'https://notebook.google.com') {
    throw new Error('nblm: evaluate this in a https://notebook.google.com tab');
  }

  // Client contexts the app attaches to its calls. CTX goes on notebook and source calls,
  // STUDIO_CTX on artifact creation.
  const CTX = [2, null, [1], [1, null, null, null, null, null, null, null, null, null, [1, 3]]];
  const STUDIO_CTX = [2, null, null, [1, null, null, null, null, null, null, null, null, null, [1]],
    [[1, 4, 8, 10, 14, 2, 3, 6]]];
  const ARTIFACT_FILTER = 'NOT artifact.status = "ARTIFACT_STATUS_SUGGESTED"';
  const LIST_VIEW = [[null, null, []], [[]], [null, []]];

  const FORMATS = {deep_dive: 1, brief: 2, critique: 3, debate: 4};
  const LENGTHS = {short: 1, default: 2, long: 3};
  // The customize dialog offers these lengths per format; Brief has no length control.
  const LENGTHS_BY_FORMAT = {
    deep_dive: ['short', 'default', 'long'],
    brief: [],
    critique: ['short', 'default'],
    debate: ['short', 'default'],
  };
  const SOURCE_STATUS = {1: 'processing', 2: 'ready', 5: 'awaiting_upload'};
  const ARTIFACT_TYPE = {1: 'audio', 3: 'video', 4: 'quiz', 7: 'infographic'};
  const ARTIFACT_STATUS = {2: 'generating', 3: 'ready'};
  const MEDIA_KIND = {1: 'mp4', 2: 'hls', 3: 'dash', 4: 'mp4_download'};
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

  const invert = (table) => Object.fromEntries(Object.entries(table).map(([k, v]) => [v, k]));
  const FORMAT_NAME = invert(FORMATS);
  const LENGTH_NAME = invert(LENGTHS);
  const label = (table, code, prefix) => (code == null ? null : table[code] ?? `${prefix}_${code}`);
  const iso = (stamp) => (Array.isArray(stamp) && stamp[0] ? new Date(stamp[0] * 1000).toISOString() : null);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const notebookPath = (id) => `/notebook/${id}`;

  function requireId(value, what) {
    if (typeof value !== 'string' || !UUID.test(value)) throw new Error(`nblm: ${what} must be a UUID, got ${JSON.stringify(value)}`);
    return value;
  }

  // Session values from the page's boot data. AppleScript's `execute javascript` runs in an
  // isolated world that shares the DOM but not page globals, so fall back to the inline
  // boot script there.
  function session() {
    if (window.WIZ_global_data?.SNlM0e) return window.WIZ_global_data;
    const boot = [...document.scripts].map((s) => s.textContent).find((t) => t.includes('WIZ_global_data')) || '';
    const pick = (key) => boot.match(new RegExp(`"${key}":"([^"]*)"`))?.[1];
    return {SNlM0e: pick('SNlM0e'), FdrFJe: pick('FdrFJe'), cfb2h: pick('cfb2h'), QrtxK: pick('QrtxK'), oPEP7c: pick('oPEP7c')};
  }

  let reqid = 100000 + Math.floor(Math.random() * 800000);

  async function rpc(id, args, sourcePath = location.pathname) {
    const page = session();
    if (!page?.SNlM0e || !page?.FdrFJe) {
      throw new Error('nblm: page session data missing; reload the tab and confirm it is signed in');
    }
    const query = new URLSearchParams({
      rpcids: id, 'source-path': sourcePath, bl: page.cfb2h, 'f.sid': page.FdrFJe,
      hl: 'en', _reqid: String((reqid += 100000)), rt: 'c',
    });
    const body = new URLSearchParams({
      'f.req': JSON.stringify([[[id, JSON.stringify(args), null, 'generic']]]),
      at: page.SNlM0e,
    });
    const response = await fetch(`/_/LabsTailwindUi/data/batchexecute?${query}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'content-type': 'application/x-www-form-urlencoded;charset=utf-8',
        'x-same-domain': '1',
        'x-goog-ext-525006520-jspb': JSON.stringify(CTX),
      },
      body: `${body}&`,
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`nblm: ${id} HTTP ${response.status}`);
    // rt=c framing: ")]}'", then alternating byte-count lines and one-line JSON envelopes.
    for (const line of text.split('\n')) {
      if (!line.startsWith('[[')) continue;
      let envelopes;
      try { envelopes = JSON.parse(line); } catch { continue; }
      for (const envelope of envelopes) {
        if (envelope[0] === 'er') throw new Error(`nblm: ${id} error ${JSON.stringify(envelope).slice(0, 200)}`);
        if (envelope[0] !== 'wrb.fr' || envelope[1] !== id) continue;
        if (envelope[2] == null) throw new Error(`nblm: ${id} rejected, status ${JSON.stringify(envelope[5])}`);
        return JSON.parse(envelope[2]);
      }
    }
    throw new Error(`nblm: ${id} returned no payload`);
  }

  function parseSource(raw) {
    const meta = raw[2] || [];
    return {
      id: raw[0]?.[0],
      name: raw[1],
      status: label(SOURCE_STATUS, raw[3]?.[1], 'status'),
      mime: meta[19] ?? null,
      added: iso(meta[2]),
    };
  }

  function parseNotebook(raw) {
    return {id: raw[2], title: raw[0], emoji: raw[3] || '', sources: (raw[1] || []).map(parseSource)};
  }

  function parseArtifact(raw) {
    const artifact = {
      id: raw[0],
      title: raw[1],
      type: label(ARTIFACT_TYPE, raw[2], 'type'),
      status: label(ARTIFACT_STATUS, raw[4], 'status'),
      sources: (raw[3] || []).map((entry) => entry?.[0]?.[0]),
      created: iso(raw[15]),
      updated: iso(raw[10]),
    };
    const audio = raw[2] === 1 ? raw[6] : null;
    if (audio) {
      const options = audio[1] || [];
      artifact.audio = {
        format: label(FORMAT_NAME, options[6], 'format'),
        length: label(LENGTH_NAME, options[1], 'length'),
        language: options[4] ?? null,
        focus: options[0] ?? null,
        durationSeconds: audio[6]?.[0] ?? null,
        media: (audio[5] || []).map(([url, kind, mime]) => ({kind: label(MEDIA_KIND, kind, 'kind'), mime: mime ?? null, url})),
      };
    }
    return artifact;
  }

  async function listNotebooks() {
    const result = await rpc('wXbhsf', [null, 1, null, CTX, null, LIST_VIEW], '/');
    return (result?.[0] || []).map((raw) => {
      const {sources, ...notebook} = parseNotebook(raw);
      return {...notebook, sourceCount: sources.length};
    });
  }

  async function getNotebook(notebookId) {
    requireId(notebookId, 'notebookId');
    const result = await rpc('rLM1Ne', [notebookId, null, CTX, null, 1, [[null, null, []]]], notebookPath(notebookId));
    return parseNotebook(result[0]);
  }

  async function renameNotebook(notebookId, title) {
    requireId(notebookId, 'notebookId');
    if (!title?.trim()) throw new Error('nblm: title must be non-empty');
    await rpc('s0tc2d', [notebookId, [[null, null, null, [null, title]]], CTX], notebookPath(notebookId));
    const notebook = await getNotebook(notebookId);
    if (notebook.title !== title) throw new Error(`nblm: rename did not stick (title is ${JSON.stringify(notebook.title)})`);
    return notebook;
  }

  async function createNotebook(title) {
    const result = await rpc('CCqFvf', ['', null, null, CTX], '/');
    const id = requireId(result?.[2], 'created notebook id');
    return title ? renameNotebook(id, title) : getNotebook(id);
  }

  // Registers a source slot, then sends the bytes through the resumable upload endpoint.
  async function uploadFile(notebookId, file, name = file.name) {
    requireId(notebookId, 'notebookId');
    if (!(file instanceof Blob) || !file.size) throw new Error('nblm: uploadFile needs a non-empty File or Blob');
    const slot = await rpc('o4cbdc', [[[name, 3]], notebookId, CTX], notebookPath(notebookId));
    const sourceId = requireId(slot?.[0]?.[0]?.[0]?.[0], 'registered source id');
    const authuser = session().QrtxK ?? '0';
    const start = await fetch(`/upload/_/?authuser=${encodeURIComponent(authuser)}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'content-type': 'application/x-www-form-urlencoded;charset=utf-8',
        'x-goog-upload-command': 'start',
        'x-goog-upload-header-content-length': String(file.size),
        'x-goog-upload-protocol': 'resumable',
      },
      body: JSON.stringify({PROJECT_ID: notebookId, SOURCE_NAME: name, SOURCE_ID: sourceId}),
    });
    const uploadUrl = start.headers.get('x-goog-upload-url');
    if (!start.ok || !uploadUrl) throw new Error(`nblm: upload start failed (HTTP ${start.status})`);
    const finish = await fetch(uploadUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'x-goog-upload-command': 'upload, finalize', 'x-goog-upload-offset': '0'},
      body: file,
    });
    if (!finish.ok || finish.headers.get('x-goog-upload-status') !== 'final') {
      throw new Error(`nblm: upload of ${name} failed (HTTP ${finish.status})`);
    }
    return {id: sourceId, name};
  }

  async function waitForSources(notebookId, sourceIds, {timeoutMs = 300000, intervalMs = 3000} = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const {sources} = await getNotebook(notebookId);
      const wanted = sourceIds ? sources.filter((s) => sourceIds.includes(s.id)) : sources;
      if (sourceIds && wanted.length !== sourceIds.length) throw new Error('nblm: a source id is not in this notebook');
      if (wanted.every((s) => s.status === 'ready')) return wanted;
      if (Date.now() > deadline) throw new Error(`nblm: sources not ready: ${JSON.stringify(wanted.filter((s) => s.status !== 'ready'))}`);
      await sleep(intervalMs);
    }
  }

  async function addUrls(notebookId, urls) {
    requireId(notebookId, 'notebookId');
    const entries = urls.map((url) => (/^https:\/\/(www\.)?(youtube\.com|youtu\.be)\//.test(url)
      ? [null, null, null, null, null, null, null, [url], null, null, 1]
      : [null, null, [url], null, null, null, null, null, null, null, 1]));
    const result = await rpc('izAoDd', [entries, notebookId, CTX], notebookPath(notebookId));
    return (result?.[0] || []).map(parseSource);
  }

  async function addText(notebookId, title, text) {
    requireId(notebookId, 'notebookId');
    const result = await rpc('izAoDd', [[[null, [title, text], null, 2, null, null, null, null, null, null, 1]], notebookId, CTX],
      notebookPath(notebookId));
    return (result?.[0] || []).map(parseSource);
  }

  function audioOptions({format = 'deep_dive', length, focus = '', language = 'en'} = {}) {
    if (!(format in FORMATS)) throw new Error(`nblm: format must be one of ${Object.keys(FORMATS).join(', ')}`);
    const allowed = LENGTHS_BY_FORMAT[format];
    const chosen = length ?? (allowed.length ? 'default' : null);
    if (allowed.length ? !allowed.includes(chosen) : chosen != null) {
      throw new Error(`nblm: ${format} accepts length ${allowed.length ? allowed.join(' | ') : 'none (omit it)'}, got ${chosen}`);
    }
    return {format, length: chosen, focus: focus.trim(), language};
  }

  // Starts an Audio Overview. Omitting sourceIds uses every ready source, as the dialog does.
  async function createAudio(notebookId, options = {}) {
    requireId(notebookId, 'notebookId');
    const {format, length, focus, language} = audioOptions(options);
    const sourceIds = options.sourceIds
      ?? (await getNotebook(notebookId)).sources.filter((s) => s.status === 'ready').map((s) => s.id);
    if (!sourceIds.length) throw new Error('nblm: no ready sources to base the audio on');
    const audio = [focus || null, length ? LENGTHS[length] : null, null, sourceIds.map((id) => [id]), language, null, FORMATS[format]];
    const result = await rpc('R7cb6c',
      [STUDIO_CTX, notebookId, [null, null, 1, sourceIds.map((id) => [[id]]), null, null, [null, audio]]],
      notebookPath(notebookId));
    const artifactId = result?.[0]?.[0];
    return {id: requireId(artifactId, 'created artifact id'), format, length, focus, language, sourceIds};
  }

  async function listArtifacts(notebookId) {
    requireId(notebookId, 'notebookId');
    const result = await rpc('gArtLc', [CTX, notebookId, ARTIFACT_FILTER], notebookPath(notebookId));
    return (result?.[0] || []).map(parseArtifact);
  }

  async function waitForArtifact(notebookId, artifactId, {timeoutMs = 3600000, intervalMs = 15000} = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const artifact = (await listArtifacts(notebookId)).find((a) => a.id === artifactId);
      if (!artifact) throw new Error(`nblm: artifact ${artifactId} is gone (generation failed or was deleted)`);
      if (artifact.status === 'ready') return artifact;
      if (artifact.status !== 'generating') throw new Error(`nblm: artifact has unmapped status ${artifact.status}; check it in the app`);
      if (Date.now() > deadline) throw new Error(`nblm: artifact still ${artifact.status} after ${timeoutMs} ms`);
      await sleep(intervalMs);
    }
  }

  // Usage meter behind the dialog's "AI Usage" bar. Observed windows: code 1 resets about
  // daily and code 2 about weekly.
  async function usage() {
    const result = await rpc('EylDcb', [CTX], location.pathname);
    return (result?.[1] || []).map((w) => ({window: w[4], resetsAt: iso(w[5]), usedPct: w[6], remainingPct: w[7]}));
  }

  // Claude-in-Chrome upload path: create a file input, set its file with the extension's
  // file_upload tool (find it by the label "nblm file input"), then call uploadPicked.
  function filePicker() {
    let input = document.getElementById('nblm-file-input');
    if (!input) {
      input = Object.assign(document.createElement('input'), {type: 'file', id: 'nblm-file-input', multiple: true});
      input.setAttribute('aria-label', 'nblm file input');
      input.style.cssText = 'position:fixed;left:0;bottom:0;width:160px;height:32px;z-index:2147483647';
      document.body.appendChild(input);
    }
    input.value = '';
    return 'file input ready: aria-label "nblm file input"';
  }

  async function uploadPicked(notebookId) {
    const input = document.getElementById('nblm-file-input');
    const files = [...(input?.files || [])];
    if (!files.length) throw new Error('nblm: no file picked; run filePicker() and set a file with file_upload first');
    const uploaded = [];
    for (const file of files) uploaded.push(await uploadFile(notebookId, file));
    input.remove();
    return uploaded;
  }

  // AppleScript path: the CLI streams base64 chunks in, then uploads the staged bytes.
  const staged = new Map();
  function stage(key, chunk) {
    if (!staged.has(key)) staged.set(key, []);
    return staged.get(key).push(chunk);
  }
  async function uploadStaged(notebookId, key, name, mime) {
    const chunks = staged.get(key);
    staged.delete(key);
    if (!chunks) throw new Error(`nblm: nothing staged under ${key}`);
    const bytes = Uint8Array.from(atob(chunks.join('')), (c) => c.charCodeAt(0));
    return uploadFile(notebookId, new File([bytes], name, {type: mime}));
  }

  // AppleScript returns only synchronous values, so the CLI starts a job and polls it.
  const jobs = new Map();
  let jobCount = 0;
  function start(method, ...args) {
    if (typeof api[method] !== 'function') throw new Error(`nblm: unknown method ${method}`);
    const id = `job${++jobCount}`;
    const job = {done: false};
    jobs.set(id, job);
    Promise.resolve()
      .then(() => api[method](...args))
      .then((value) => Object.assign(job, {done: true, ok: true, value}),
        (error) => Object.assign(job, {done: true, ok: false, error: String(error?.message || error)}));
    return id;
  }
  function poll(id) {
    const job = jobs.get(id) ?? {done: true, ok: false, error: `nblm: unknown job ${id}`};
    if (job.done) jobs.delete(id);
    return JSON.stringify(job);
  }

  function status() {
    const page = session();
    return {version: VERSION, signedIn: Boolean(page.SNlM0e), account: page.oPEP7c || null, build: page.cfb2h || null, path: location.pathname};
  }

  const api = {
    version: VERSION, rpc, status, usage,
    listNotebooks, getNotebook, createNotebook, renameNotebook,
    uploadFile, filePicker, uploadPicked, stage, uploadStaged, waitForSources, addUrls, addText,
    audioOptions, createAudio, listArtifacts, waitForArtifact,
    start, poll,
    enums: {FORMATS, LENGTHS, LENGTHS_BY_FORMAT, SOURCE_STATUS, ARTIFACT_TYPE, ARTIFACT_STATUS, MEDIA_KIND},
  };
  window.nblm = api;
  return `nblm v${VERSION} ready`;
})();
