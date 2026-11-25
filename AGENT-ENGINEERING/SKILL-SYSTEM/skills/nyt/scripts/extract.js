() => {
  const visible = e => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const safeUrl = s => { try { const u = new URL(s, location.href); return u.origin + u.pathname; } catch { return ''; } };
  const controls = [...document.querySelectorAll('a,button')].filter(visible).map(e => clean(e.innerText || e.getAttribute('aria-label')));
  const signedOut = controls.some(s => /^(sign in|log in)$/i.test(s));
  const accountControl = controls.some(s => /^(account|my account|your account)$/i.test(s));
  const gate = [...document.querySelectorAll('[role="dialog"], [data-testid*="paywall"], [id*="gateway"], [class*="paywall"]')].filter(visible).some(e => /subscribe|sign in|log in|subscription/i.test(e.innerText || ''));
  const challenge = /^(access denied|just a moment|security check)/i.test(document.title) || /verify you are human/i.test(document.body?.innerText || '');
  const roots = ['section[name="articleBody"]', '[data-qa="article-body"]', 'article'];
  let selector = roots.find(s => document.querySelector(s + ' p')) || null;
  const paragraphs = selector ? [...document.querySelectorAll(selector + ' p')].filter(visible).map(e=>clean(e.innerText)).filter(Boolean) : [];
  const items = [...document.querySelectorAll('main a, article a')].filter(visible).filter(e=>e.querySelector('h2,h3') || /\/\d{4}\/\d{2}\/\d{2}\//.test(e.pathname || '')).map(e=>({title:clean(e.innerText),url:safeUrl(e.href)})).filter(x=>x.title && new URL(x.url).hostname===location.hostname);
  const seen = new Set();
  const stories = items.filter(x=>!seen.has(x.url) && seen.add(x.url)).slice(0,60);
  const meta = key => document.querySelector(`meta[property="${key}"],meta[name="${key}"]`)?.content || null;
  return {url:safeUrl(location.href),canonicalUrl:safeUrl(document.querySelector('link[rel="canonical"]')?.href || location.href),title:clean(document.querySelector('h1')?.innerText || document.title),description:meta('description'),author:meta('author'),published:meta('article:published_time'),updated:meta('article:modified_time'),access:{signedOut,accountControl,gate,challenge,verdict:challenge?'challenge':gate?'blocked':signedOut?'signed_out':accountControl?'account_visible':'unknown'},extraction:'rendered_dom',selector,paragraphCount:paragraphs.length,paragraphs:gate||challenge?[]:paragraphs,stories,truncatedDiscovery:items.length>60,completeness:'unverified'};
}
