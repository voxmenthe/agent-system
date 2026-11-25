# The Washington Post page map

- Home: `https://www.washingtonpost.com/`.
- Search: `https://www.washingtonpost.com/search/?query=` plus a URL-encoded query. Treat this as a navigation route to verify live, not a stable search API. If it fails, use the site's visible Search control.
- Article candidates: dated paths discovered from visible story links. Preserve canonical URL; strip tracking queries and fragments from citations.
- Discovery: visible `main` headings and story links, capped at 60 in the helper.
- Body candidates: `[data-qa="article-body"] p`, then `article p`. These are candidates, not guarantees; inspect the rendered page when counts are zero or text contains unrelated modules.
- Metadata: visible byline and time controls, canonical link, and public description/author/article date meta tags. Missing metadata may require visible inspection. Do not dump application state.

A DOM fallback can include captions, recommendations, or newsletter prompts.
Check the beginning and ending and exclude furniture in synthesis. Live blogs,
video, interactive articles, and Opinion can use different templates. No latest
feed or machine-readable full-body schema is assumed. Missing content requires
inspection or a reported limitation, never hidden-state access.

Observed 2026-09-06: `/search/?query=artificial+intelligence` renders “Ask The Post AI” with article links. Treat those links as discovery only; do not cite an AI answer as reporting or assume exhaustive, chronological, or Boolean search. Use visible search controls to inspect available modes and open source articles.

Direct smoke observation, 2026-09-06: Homepage returned story links; the tested politics article used `[data-qa="article-body"]` and returned 36 paragraphs plus publication/update meta tags. No recognized account control was found, so access remained `unknown` despite visible body content. This is single-template evidence, not a guarantee for all article types.
