# X-list paper feeds

Load this reference only when the user explicitly asks for recent papers from
a particular X list. X is a discovery surface and evidence of what list
members posted; it is not authoritative evidence for paper metadata or claims.

## Identify the exact list

1. Extract `LIST_ID` from an exact URL such as
   `https://x.com/i/lists/{LIST_ID}`. Accept a numeric ID supplied directly by
   the user.
2. Do not replace the requested list with a topical X search, a guessed member
   set, or a similarly named list.
3. Record the list URL or ID, observation time, requested time window, and
   timezone. If the user says "latest" without a window, inspect the newest
   available feed entries and state where retrieval stopped.

## Retrieve through complementary read-only routes

Prefer the **authenticated Chrome connector** for the exact list URL when it is
available and the user has authorized browser use. It can expose the rendered
list order, current member roster, native reposts, expanded post text, status
URLs, timestamps, and link cards that a search result may omit.

- Keep browser work read-only. Do not read, export, or reuse cookies, tokens,
  local storage, or other credentials.
- Expand truncated posts or link cards only when needed to resolve a paper.
- Preserve feed order as rendered. A repost's position reflects the repost
  event, not necessarily the original post's timestamp.

Use the installed `xgrok` workflow for bounded discovery or backfill. Query
`list:{LIST_ID}` in Latest mode, use an explicit time window, and page with the
returned `max_id` only while the remaining call budget and coverage need
justify it.

- Treat `xgrok` results as best-effort rather than exhaustive. Search pages may
  be capped, ordering may not reproduce the rendered list exactly, native
  reposts may be absent, and a post's linked paper may be truncated.
- Report the number of calls or pages used and the oldest timestamp reached.
  Stop when the requested window is covered, results repeat or empty out, or
  the agreed budget is exhausted.
- Use search to fill visible gaps, not to override contradictory exact-list UI
  evidence.

An unauthenticated request to the public list URL may return only an
application shell or login interstitial. If no posts are present in that
response, treat it as a failed feed route. Do not scrape application bundles,
claim access to the list timeline, or substitute unrelated public search
results.

If neither the exact authenticated list nor bounded `xgrok` retrieval is
available, report the access limitation. Do not claim that a general web
search represents the requested list.

## Extract and reconcile paper candidates

For each qualifying original post or repost, preserve:

- list position and posting or repost timestamp;
- member handle and the original author when different;
- direct X status URL;
- enough post text to establish the paper association;
- linked paper URL, title, or identifier; and
- whether the association is direct, inferred from a visible link card, or
  still unresolved.

Normalize an arXiv identifier by stripping `arXiv:`, `/abs/`, `/pdf/`, a
trailing `.pdf`, and a version suffix only when grouping versions of the same
paper. Preserve the exact versioned ID in the evidence record. Deduplicate the
final paper list by normalized arXiv ID while retaining every supporting X post
under that paper.

Verify every resolved paper with canonical arXiv metadata before reporting its
title, authors, identifier, or publication date. Prefer `get_abstract`; use an
official arXiv abstract page when the MCP route is unavailable. Never guess an
identifier from a partial title. Keep a candidate visibly unresolved when
canonical verification fails.

## Report compactly

State the list, observation time, timezone, retrieval routes, requested window,
and coverage limit before the results. Order papers by their newest observed
position in the exact list when available; otherwise label the ordering as
best-effort `xgrok` recency.

For each verified paper, include the member, observed timestamp, canonical
title and arXiv ID, and the link set `[X] · [abstract] · [PDF]`:

```text
[X](STATUS_URL) · [abstract](https://arxiv.org/abs/{ARXIV_ID}) · [PDF](https://arxiv.org/pdf/{ARXIV_ID})
```

Distinguish original posts from reposts and combine duplicate mentions without
discarding their provenance. End with material limitations such as UI-only
ordering, truncated searches, unresolved links, missing reposts, or an
incomplete time window. Do not call the result exhaustive unless the requested
window was fully traversed through the exact list feed.

Construct direct abstract and PDF links without fetching the PDF. Do not
download papers, mutate an X account, save browser state, or create persistent
monitoring unless the user separately and explicitly requests that action.
