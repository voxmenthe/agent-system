# Hugging Face Daily Papers

Load this reference only for an explicit request to check top Hugging Face
Daily Papers for a date or to return direct paper-download links. The Daily
Papers feed is a community-curated subset of AI and computer-science papers; it
is not an exhaustive daily arXiv ranking, and the feed date is not necessarily
the paper's original arXiv publication date.

## Fetch one day

Use the public read-only endpoint. Require a concrete ISO date (`YYYY-MM-DD`)
for an arbitrary-day request; resolve relative dates against the user's
timezone and state the resulting date.

```bash
curl --fail --silent --show-error \
  'https://huggingface.co/api/daily_papers?date=YYYY-MM-DD&sort=trending&limit=20'
```

The supported `limit` range is 1-100. Set `sort=trending` for a request for
"top" papers. Treat the returned array order as the ranking; do not re-rank it
from comments, summaries, or other fields.

Each array item contains a nested `paper` object. Read the arXiv ID from
`paper.id` and the canonical title from `paper.title`; do not assume those
fields occur at the top level.

If the `hf` CLI is installed and its `papers` command is available, this is an
equivalent convenience path:

```bash
hf papers ls --date YYYY-MM-DD --sort trending --limit 20 --format json
```

Do not install `huggingface_hub`, another CLI, or an MCP server solely for this
workflow. Fall back to the REST endpoint when the CLI is absent or stale.

## Construct direct links

Validate each returned or already identified paper ID against one of these
arXiv forms:

- modern: `YYMM.NNNNN` or `YYMM.NNNN`, optionally followed by `vN`
- legacy: `archive/YYMMNNN`, optionally followed by `vN`

Percent-encode the ID as a URL path while preserving `/` for a legacy ID.
Construct source links deterministically:

```text
abstract: https://arxiv.org/abs/{ARXIV_ID}
PDF:      https://arxiv.org/pdf/{ARXIV_ID}
```

Prefer the versioned ID returned by the source when one is present. A direct
PDF URL is a link, not proof that the remote file was fetched successfully. If
the user asks for verified working links, make bounded `HEAD` or small-range
requests and report failures; do not retry-loop on rate limits.

## Return a compact result

For each Daily Papers result, return:

1. Daily Papers rank
2. title
3. arXiv ID
4. direct arXiv PDF link

For a direct-link-only request, omit Daily Papers rank and return the known
title, validated arXiv ID, and direct PDF link. Do not invent a title or rank
when the user supplied only an ID.

Add the Hugging Face paper-page or arXiv abstract link only when requested or
useful. State the exact queried date, requested limit, and number returned.
If the response is empty, say that no Daily Papers entries were returned for
that date; do not silently substitute a nearby day. If an item lacks a valid
arXiv ID, omit its generated PDF link and identify the malformed entry.

Do not download, cache, or save papers unless the user explicitly asks. For a
download request, use the direct arXiv URLs, preserve the returned IDs, and
apply the skill's normal persistent-state and PDF-validation safeguards.
