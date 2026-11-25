# The New York Times page map

- Home: `https://www.nytimes.com/`.
- Search: `https://www.nytimes.com/search?query=` plus a URL-encoded query. Treat this as a navigation route to verify live, not a stable search API. If it fails, use the site's visible Search control.
- Article candidates: dated paths discovered from visible story links. Preserve canonical URL; strip tracking queries and fragments from citations.
- Discovery: visible `main` headings and story links, capped at 60 in the helper.
- Body candidates: `section[name="articleBody"] p`, then `article p`. These are candidates, not guarantees; inspect the rendered page when counts are zero or text contains unrelated modules.
- Metadata: visible byline and time controls, canonical link, and public description/author/article date meta tags. Missing metadata may require visible inspection. Do not dump application state.

A DOM fallback can include captions, recommendations, or newsletter prompts.
Check the beginning and ending and exclude furniture in synthesis. Live blogs,
video, interactive articles, and Opinion can use different templates. No latest
feed or machine-readable full-body schema is assumed. Missing content requires
inspection or a reported limitation, never hidden-state access.

Direct smoke observation, 2026-09-06: Homepage and search returned story links; the tested standard article used `section[name="articleBody"]` and returned 44 paragraphs plus publication/update meta tags. The visible Account control supports only `account_visible`, not verification of subscription tier. This is single-template evidence, not a guarantee for all article types.
