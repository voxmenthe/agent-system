// Evaluate in an x.com tab; defines window.__xb and returns its status.
// Read-only: copies response bodies the page already requested for its own
// rendering. It sends no request and reads no cookies, tokens, or storage.
// A full page load removes it; navigate with __xb.go() to keep it.
(() => {
  if (window.__xb) return window.__xb.status();
  const OPS = /\/(BookmarkFolderTimeline|BookmarkFoldersSlice|TweetDetail)(?:\?|$)/;
  const responses = [];
  const labels = {};
  let lastStop = null;
  let dumpText = null, dumpBounds = [];

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const waitFor = async (test, ms) => {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(150)) if (test()) return true;
    return Boolean(test());
  };
  const routeFolder = () => location.pathname.match(/^\/i\/history\/bookmarks\/(\d+)/)?.[1] ?? null;
  const routePost = () => location.pathname.match(/\/status\/(\d+)/)?.[1] ?? null;
  const iso = ms => (Number.isFinite(ms) ? new Date(ms).toISOString() : null);
  const unescape = s => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

  const keep = (url, status, body) => {
    const op = url.match(OPS)?.[1];
    if (!op) return;
    let vars = {};
    try {
      vars = JSON.parse(new URL(url, location.origin).searchParams.get('variables') ?? '{}');
    } catch (error) {
      if (!(error instanceof SyntaxError || error instanceof TypeError)) throw error;
    }
    responses.push({
      op, status, body, at: Date.now(),
      folder: vars.bookmark_collection_id ?? (op === 'BookmarkFolderTimeline' ? routeFolder() : null),
      focal: vars.focalTweetId ?? (op === 'TweetDetail' ? routePost() : null),
      reqCursor: vars.cursor ?? null,
    });
  };

  const XO = XMLHttpRequest.prototype.open, XS = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (_method, url) {
    this.__xbUrl = String(url);
    return XO.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    if (OPS.test(this.__xbUrl ?? '')) this.addEventListener('load', () => keep(this.__xbUrl, this.status, this.responseText));
    return XS.apply(this, arguments);
  };
  const F = window.fetch;
  window.fetch = async function (input) {
    const response = await F.apply(this, arguments);
    const url = String(input?.url ?? input);
    if (OPS.test(url)) response.clone().text().then(text => keep(url, response.status, text));
    return response;
  };

  const post = (result, fallbackId = null) => {
    const r = result?.tweet ?? result;
    if (!r?.legacy) {
      const id = r?.rest_id ?? fallbackId;
      return { id, url: `https://x.com/i/status/${id}`, unavailable: r?.__typename ?? 'missing' };
    }
    const L = r.legacy, note = r.note_tweet?.note_tweet_results?.result;
    const user = r.core?.user_results?.result;
    const handle = user?.core?.screen_name ?? user?.legacy?.screen_name ?? null;
    const urls = [...(note?.entity_set?.urls ?? []), ...(L.entities?.urls ?? [])];
    const expanded = new Map(urls.filter(u => u.url && u.expanded_url).map(u => [u.url, u.expanded_url]));
    let text = note?.text ?? unescape(L.full_text ?? '');
    for (const [short, long] of expanded) text = text.split(short).join(long);
    for (const m of L.entities?.media ?? []) if (m.url) text = text.split(m.url).join('');
    const card = r.card?.legacy?.binding_values?.find?.(b => b.key === 'card_url')?.value?.string_value ?? null;
    return {
      id: r.rest_id,
      handle,
      url: `https://x.com/${handle ?? 'i'}/status/${r.rest_id}`,
      published_at: iso(Date.parse(L.created_at)),
      text: text.trim(),
      links: [...new Set(expanded.values())],
      card_url: expanded.get(card) ?? card,
      article_title: r.article?.article_results?.result?.title ?? null,
      media: (L.extended_entities?.media ?? []).map(m => ({
        type: m.type,
        url: m.media_url_https,
        alt: m.ext_alt_text ?? null,
        video: (m.video_info?.variants ?? [])
          .filter(v => v.content_type === 'video/mp4')
          .sort((a, b) => (b.bitrate ?? 0) - (a.bitrate ?? 0))[0]?.url ?? null,
      })),
      reply_to: L.in_reply_to_status_id_str ?? null,
      conversation_id: L.conversation_id_str ?? null,
      quoted: r.quoted_status_result?.result ? post(r.quoted_status_result.result) : null,
    };
  };

  const entriesOf = (body, path) =>
    (path(JSON.parse(body)) ?? []).flatMap(i => i.entries ?? (i.entry ? [i.entry] : []));

  const pageOf = response => {
    const entries = entriesOf(response.body, j => j?.data?.bookmark_collection_timeline?.timeline?.instructions);
    const items = entries
      .filter(e => e.entryId?.startsWith('tweet-'))
      .map(e => post(e.content?.itemContent?.tweet_results?.result, e.entryId.slice(6)));
    const bottom = entries.find(e => e.entryId?.startsWith('cursor-bottom'))?.content?.value ?? null;
    return { at: response.at, items, bottom };
  };

  // Pages are chained by request cursor, so refetches and top-cursor polls
  // neither duplicate nor reorder the folder.
  const folderState = folder => {
    const got = responses.filter(r => r.op === 'BookmarkFolderTimeline' && r.folder === folder);
    const byCursor = new Map();
    for (const r of got) if (r.status === 200 && !byCursor.has(r.reqCursor ?? '')) byCursor.set(r.reqCursor ?? '', r);
    const chain = [];
    for (let key = ''; byCursor.has(key); ) {
      const page = pageOf(byCursor.get(key));
      chain.push(page);
      if (!page.items.length || !page.bottom || page.bottom === key) break;
      key = page.bottom;
    }
    const last = chain.at(-1);
    const oldest = chain.findLast(p => p.bottom)?.bottom;
    return {
      chain,
      end: Boolean(last && !last.items.length),
      firstPage: byCursor.has(''),
      errors: got.filter(r => r.status !== 200).map(r => r.status),
      oldest: oldest ? -Number(oldest) : null,
    };
  };

  const folderList = () => {
    const r = responses.findLast(x => x.op === 'BookmarkFoldersSlice' && x.status === 200);
    const slice = r && JSON.parse(r.body)?.data?.viewer?.user_results?.result?.bookmark_collections_slice;
    return slice ? { items: slice.items ?? [], more: Boolean(slice.slice_info?.next_cursor) } : null;
  };

  const currentFolder = () => routeFolder() ?? responses.findLast(r => r.folder)?.folder ?? null;
  const account = () => document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]')?.innerText.match(/@\w+/)?.[0] ?? null;
  const errorShown = () => /Something went wrong/.test(document.querySelector('main')?.innerText ?? '');
  const historyTab = () => document.querySelector('[role="tablist"] [role="tab"]');
  const labelOf = folder => {
    if (!labels[folder] && routeFolder() === folder) labels[folder] = historyTab()?.innerText.trim() || null;
    return labels[folder] ?? null;
  };
  const menuItems = () => [...document.querySelectorAll('[role="menuitemradio"]')];
  const norm = s => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const openMenu = async () => {
    if (menuItems().length) return true;
    historyTab()?.click();
    return waitFor(() => menuItems().length, 4000);
  };
  // The menu ignores Escape; its full-viewport backdrop closes it.
  const closeMenu = () => {
    const menu = document.querySelector('[role="menu"]');
    const group = menu?.closest('[role="group"]');
    [...(group?.querySelectorAll('div') ?? [])]
      .find(d => !d.contains(menu) && !menu.contains(d) && d.getBoundingClientRect().height >= innerHeight * 0.9)
      ?.click();
  };

  const xb = {
    status(folder = currentFolder()) {
      const s = folder ? folderState(folder) : null;
      return {
        view: routeFolder() ? 'folder' : routePost() ? 'post' : location.pathname === '/i/history' ? 'history' : 'other',
        account: account(),
        folder,
        label: folder ? labelOf(folder) : null,
        pages: s?.chain.length ?? 0,
        records: s?.chain.reduce((n, p) => n + p.items.length, 0) ?? 0,
        first_page: s?.firstPage ?? false,
        end: s?.end ?? false,
        oldest_cursor_time: iso(s?.oldest),
        http_errors: s?.errors ?? [],
        error_banner: errorShown(),
        last_stop: lastStop,
      };
    },

    // Single-page navigation keeps this helper installed; a page load would not.
    async go(target) {
      const path = new URL(String(target), location.origin).pathname;
      if (location.pathname !== path) {
        history.pushState({}, '', path);
        dispatchEvent(new PopStateEvent('popstate', { state: {} }));
      }
      await sleep(1500);
      return { path_changed: location.pathname === path, view: xb.status().view };
    },

    async folders() {
      if (!(await openMenu())) return { error: 'folder menu did not open; go("/i/history") first' };
      await sleep(500);
      const shown = menuItems().map(e => ({ label: e.innerText.trim(), selected: e.getAttribute('aria-checked') === 'true' }));
      closeMenu();
      const list = folderList();
      const ids = new Map((list?.items ?? []).map(f => [f.name, f.id]));
      return {
        folders: shown.map(f => ({ ...f, id: ids.get(f.label) ?? null })),
        more_exist: list ? list.more : 'unknown',
      };
    },

    async open(target) {
      let folder;
      if (/^\d+$/.test(String(target))) {
        folder = String(target);
        await xb.go(`/i/history/bookmarks/${folder}`);
        if (routeFolder() !== folder) return { error: 'folder route did not open' };
      } else {
        if (!(await openMenu())) return { error: 'folder menu did not open; go("/i/history") first' };
        const matches = menuItems().filter(e => norm(e.innerText) === norm(String(target)));
        if (matches.length !== 1) {
          closeMenu();
          return { error: `${matches.length} menu labels equal ${JSON.stringify(target)}; run folders()` };
        }
        const label = matches[0].innerText.trim();
        matches[0].click();
        if (!(await waitFor(routeFolder, 6000))) return { error: 'route did not change to a folder' };
        folder = routeFolder();
        labels[folder] = label;
      }
      await waitFor(() => folderState(folder).firstPage, 8000);
      return xb.status(folder);
    },

    async more({ until = null, budgetMs = 35000, pauseMs = 800, maxIdle = 6 } = {}) {
      const folder = routeFolder();
      if (!folder) return { error: 'not on a bookmark folder route' };
      const untilMs = until == null ? null : new Date(until).getTime();
      const t0 = Date.now();
      for (let idle = 0; ; ) {
        const s = folderState(folder);
        lastStop = !s.firstPage ? 'no_first_page'
          : s.end ? 'end'
          : untilMs != null && s.oldest != null && s.oldest < untilMs ? 'until'
          : s.errors.length || errorShown() ? 'error'
          : idle >= maxIdle ? 'idle'
          : Date.now() - t0 > budgetMs ? 'budget'
          : null;
        if (lastStop) return xb.status(folder);
        const before = responses.length;
        window.scrollTo(0, document.documentElement.scrollHeight);
        if (await waitFor(() => responses.length > before, 3000)) {
          idle = 0;
          await sleep(pauseMs);
        } else idle += 1;
      }
    },

    records(folder = currentFolder()) {
      return folderState(folder).chain.flatMap((page, p) =>
        page.items.map((item, i) => ({ page: p + 1, pos: i + 1, ...item })));
    },

    json({ folder = currentFolder(), pages = null } = {}) {
      const s = folderState(folder);
      const kept = Math.min(pages ?? s.chain.length, s.chain.length);
      return {
        schema: 'x-bookmark-folder-capture/1',
        exported_at: new Date().toISOString(),
        account: account(),
        folder: { id: folder, label: labelOf(folder), url: `https://x.com/i/history/bookmarks/${folder}` },
        complete: s.end,
        last_stop: lastStop,
        http_errors: s.errors,
        pages: s.chain.map((p, i) => ({
          page: i + 1, items: p.items.length, fetched_at: iso(p.at),
          cursor: p.bottom, cursor_time: iso(p.bottom ? -Number(p.bottom) : null),
        })),
        exported_pages: kept,
        records: xb.records(folder).filter(r => r.page <= kept),
      };
    },

    // The post's thread: parent context, the author's own continuation
    // chain, and a count of other replies. Keys avoid "auth", which the
    // Claude in Chrome output filter redacts.
    async thread(target = routePost()) {
      const id = String(target).match(/(\d+)\/?$/)?.[1];
      if (!id) return { error: 'give a post URL or ID' };
      const have = () => responses.some(r => r.op === 'TweetDetail' && r.focal === id && r.status === 200);
      if (!have()) {
        await xb.go(/\/status\//.test(String(target)) ? target : `/i/status/${id}`);
        if (!(await waitFor(have, 8000))) return { error: 'no TweetDetail response for that post', view: xb.status().view };
      }
      const details = responses.filter(x => x.op === 'TweetDetail' && x.focal === id && x.status === 200);
      const fetched = new Set(details.map(r => r.reqCursor));
      const posts = new Map();
      const folds = [];  // post IDs of each module that still hides replies
      for (const r of details) {
        for (const e of entriesOf(r.body, j => j?.data?.threaded_conversation_with_injections_v2?.instructions)) {
          const items = e.content?.items?.map(x => ({ entryId: x.entryId, item: x.item?.itemContent }))
            ?? [{ entryId: e.entryId, item: e.content?.itemContent }];
          const ids = [];
          let folded = false;
          for (const { entryId, item } of items) {
            if (/cursor-showmore/.test(entryId) && !fetched.has(item?.value)) folded = true;
            const p = item?.tweet_results?.result && post(item.tweet_results.result);
            if (!p?.id) continue;
            ids.push(p.id);
            if (!posts.has(p.id)) posts.set(p.id, p);
          }
          if (folded) folds.push(ids);
        }
      }
      const all = [...posts.values()];
      const focal = posts.get(id);
      if (!focal) return { error: 'focal post missing from the response' };
      const chain = new Set([id]);
      for (let grew = true; grew; ) {
        grew = false;
        for (const p of all) {
          if (!chain.has(p.id) && p.handle === focal.handle && chain.has(p.reply_to)) {
            chain.add(p.id);
            grew = true;
          }
        }
      }
      const context = all.slice(0, all.indexOf(focal));
      return {
        focal_id: id,
        context,
        self_thread: all.filter(p => chain.has(p.id)),
        other_replies: all.length - context.length - chain.size,
        self_thread_truncated: folds.some(ids => ids.some(i => chain.has(i))),
      };
    },

    download(filename = null, options = {}) {
      const doc = xb.json(options), text = JSON.stringify(doc);
      const stamp = doc.exported_at.replace(/[-:]/g, '').slice(0, 15);
      const name = filename ?? `x-bookmarks-${doc.folder.id}-${stamp}.json`;
      const a = Object.assign(document.createElement('a'), {
        href: URL.createObjectURL(new Blob([text], { type: 'application/json' })), download: name,
      });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 60000);
      return { filename: name, chars: text.length, records: doc.records.length };
    },

    // Fallback export: chunk i of JSON text into a hidden <article> that
    // get_page_text reads. Chunk 0 freezes the text so later chunks match it.
    dump(i = 0, { chunk = 40000, data = undefined, ...options } = {}) {
      if (i === 0 || dumpText == null) {
        dumpText = JSON.stringify(data === undefined ? xb.json(options) : data);
        dumpBounds = [0];
        while (dumpBounds.at(-1) < dumpText.length) {
          let end = Math.min(dumpBounds.at(-1) + chunk, dumpText.length);
          if (end < dumpText.length && /[\ud800-\udbff]/.test(dumpText[end - 1])) end -= 1;
          dumpBounds.push(end);
        }
      }
      let el = document.getElementById('__xbdump');
      if (!el) {
        el = Object.assign(document.createElement('article'), { id: '__xbdump' });
        el.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0.01;overflow:hidden;z-index:-1';
        document.body.append(el);
      }
      el.textContent = dumpText.slice(dumpBounds[i], dumpBounds[i + 1]);
      return { chunk: i, of: dumpBounds.length - 1, chars: el.textContent.length, total: dumpText.length };
    },
  };
  window.__xb = xb;
  return xb.status();
})();
