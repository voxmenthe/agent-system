---
name: nyt
description: "Research The New York Times through the user's authenticated Chrome session. Use for current-news overviews, article reading and summarization, focused publication searches, historical coverage, and across-time synthesis on nytimes.com (including requests naming nyt.com). Do not use for generic web research, other publications, or bypassing authentication or access controls."
disable-model-invocation: true
---

# The New York Times Research

Use the user's existing Chrome session for the profile named by `$CHROME_PROFILE_EMAIL`.
The canonical publication is `www.nytimes.com`; normalize requests for `nyt.com` to that site.
Use the Chrome plugin when callable; on hosts without it, use the bundled
AppleScript helper. Choose by actual host capabilities, not model family.

## Chrome plugin workflow

1. Follow the installed `chrome:control-chrome` skill and read the selected
   browser's complete documentation. Do not hard-code its installation path or
   invent tool names. Use the documented Node REPL browser-client surface.
2. Name the session. Claim a suitable existing publication tab, or create one
   disposable tab in the intended browser. Never select an arbitrary front tab.
3. Inspect visible account controls and access gates. A generic Account button
   alone does not establish a paid subscription; absence of Log In does not
   establish authentication. Record unknown when evidence is ambiguous.
4. Use read-only page evaluation for semantic headings, links, article paragraphs,
   and public metadata. [scripts/extract.js](scripts/extract.js) provides a
   transport-neutral evaluation function. Load its text using the host's file
   reader and supply the function through the documented evaluation API. Do not
   use page evaluation to fetch endpoints or inspect private application stores.
5. Open representative articles. Verify the displayed body and ending before
   claiming complete access. The extractor reports `completeness: unverified`;
   a paragraph count, account control, or script payload is not completeness proof.
6. Finalize the session according to the plugin docs; release claimed user tabs
   and clean up disposable research tabs.

Do not assume WSJ's `#__NEXT_DATA__`, entitlement field, search parameters, or
`flattenedBody` exists here. See [site-map.md](references/site-map.md).

## Select the research workflow

- **Current overview:** open the homepage, preserve editorial order, follow
  relevant section links, and open representative stories. Use displayed dates
  for recency; homepage rank is not chronological order.
- **Targeted/history:** use the publication's search UI or the search route in
  the site map. Run several focused queries, inspect available sort/date controls,
  and apply exact requested date bounds to verified article dates. Deduplicate
  canonical URLs. State page/result caps; never promise exhaustive coverage.
- **One article:** navigate to its canonical URL, collect title, author, publication
  and update dates, then read the rendered body. Use metadata only if sufficient.
  Missing dates stay unknown; do not infer them solely from the URL.
- **Synthesis:** build an evidence matrix of title, URL, dates, claim, and evidence
  type. Preserve chronology, disagreement, and the distinction between reported
  fact, attributed opinion, and your inference. Label Opinion and live coverage.

## Fallback and access boundaries

Read [fallback.md](references/fallback.md) before shell automation. Run `status`
first. Serialize browser work across both publication skills and all workers.
Do not use a separate automation channel when the Chrome plugin is connected;
follow its recovery guidance first. A plugin file on disk without callable
runtime tools is not an available transport.

If explicitly signed out, ask the user to sign in to this publication in the
intended Chrome session and retry. A page-specific gate is not proof of global
logout: check the homepage status before making that diagnosis. Stop at a
paywall or challenge. Never inspect cookies, local storage, Chrome profile files,
passwords, tokens, hidden article payloads behind a gate, or credential stores.
Never switch profiles, enter credentials, reuse gift tokens, or substitute web
search/archive mirrors to work around access controls.

## Evidence and output

Link material claims to canonical article titles and dates. Discovery snippets
are not article-body evidence. Prefer paraphrase and short essential quotations;
do not reproduce full articles in the final answer. Report missing access,
truncation, unverified completeness, extraction fallback, and date gaps honestly.
