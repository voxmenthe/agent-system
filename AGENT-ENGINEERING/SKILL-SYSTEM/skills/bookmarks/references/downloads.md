# Downloading bookmark-linked resources

Select resources from the user's requested content types, not from an implicit
quality screen. One bookmarked reading list may name many files. A recent
bookmark can recommend an older paper; paper publication date is not a
bookmark-save filter.

## Identify the real resource

- Resolve the post's explicit links, relevant author-thread continuations,
  quoted recommendations, and title images. Record the path from bookmark to
  resource in a sources file beside the manifest (the 2026-09-30 intake used
  `AA-DOCS/x-bookmark-paper-sources-<date>.json`) so a later run can reuse
  verified resolution rather than rediscover it. Keep image evidence that
  identified a paper in `AA-DOCS/source-images/`.
- Use primary metadata for title, authors/publisher, canonical identity,
  publication date, and version; for arXiv, the `arxiv` skill's `get_abstract`
  returns it without a download. Use the versionless numeric ID as identity
  and retain the exact retrieved version separately. Do not equate papers
  because their acronyms match. When the post calls a paper something other
  than its verified title, keep both.
- An alphaXiv/intermediary page can contain unrelated arXiv IDs in author,
  profile, or reference widgets. Select its subject or explicitly recommended
  resources, not every ID in its HTML.
- A non-numeric intermediary route can link an author-hosted PDF. Follow the
  actual author/publisher link, check its PDF title, and leave publication date
  explicitly unknown when unavailable; do not manufacture an arXiv ID/date.
- A blog, code repository, video, model, or discussion without an identified
  downloadable paper is a valid non-PDF disposition. Say “no matching PDF
  located in the checked sources,” not “no paper exists.”

## Transfer and validate

Use `bookmarks.py fetch` for public files:

```bash
python3 -I scripts/bookmarks.py fetch https://arxiv.org/pdf/2609.37725v1 \
  --dest PAPERS/ADHOC --name context-language-models-260929-2609.37725 \
  --kind pdf --manifest PAPERS/ADHOC/AA-DOCS/x-bookmarks-downloads-<date>.jsonl \
  --ref https://x.com/a1zhang/status/2105409935936782708
```

It reads the whole response before writing anything. It rejects truncated
bodies, HTML login or error pages, a type other than `--kind`, and PDFs with
no `%%EOF` or that `pdfinfo` cannot parse. It then creates the file
exclusively: identical bytes report `reused`, and different bytes under the
same name fail without touching the existing file. Each success prints and
appends one row with `status`, `path`, `bytes`, `sha256`, the requested and
final URLs, `retrieved_at`, `checks` (PDF pages and title), and `refs`. Exit 1
is a failed transfer; record it and continue with the next resource.

`fetch` does not establish identity. For PDFs still check readable text where
expected, first-page title/identity against the `checks.title` or the page
itself, and exact arXiv version where applicable. Inspect the first page when extraction order prevents a
clean title match; document that check rather than silently relaxing identity.
Scanned PDFs may require visual verification/OCR instead of rejecting them for
having no extracted text.

For other data, `fetch --kind data` rejects only HTML. Add format-appropriate
checks: parse CSV/JSON/Parquet, inspect units/schema and row counts, verify
archive members before extraction, or compare a published checksum. Do not
execute downloaded scripts to validate them.
Authenticated downloads stay in the permitted browser route; public HTTP
retrieval must not copy session credentials or bypass access restrictions.

### Official arXiv recovery

Use an official PDF URL for the verified ID/version. If an exact-version
response is truncated or returns HTTP 406, try the canonical versionless
`https://arxiv.org/pdf/<ID>` endpoint and verify the version in the resulting
PDF. If canonical responses remain truncated, an exact-version
`https://export.arxiv.org/pdf/<ID>v<N>` recovered a large survey in the original
intake. This is a demonstrated fallback, not a promise that every endpoint will
work. Revalidate the entire transfer after each changed endpoint; do not accept
partial bytes or infer success from HTTP status alone. Bound recovery attempts
and retain failures without losing the folder capture.

## Save without losing provenance

Follow the destination's existing naming convention. For the owner's arXiv
library use `<lowercase-title>-<YYMMDD>-<arxiv-id>.pdf`, where the date comes from
verified first-submission metadata. Use a stable descriptive filename for
non-arXiv resources, not guessed publication metadata.

Deduplicate by canonical identity/version and content hash, retaining all
referring bookmark links (pass one `--ref` per referring bookmark). Reuse a
verified identical existing file. If the content differs, save a distinct
version/suffixed filename rather than overwriting it; a later paper revision
coexists visibly with the earlier one.

Read back delivered files and reconcile both directions: every downloaded
resource has a manifest entry, and every manifest file exists with matching
bytes/hash. Count unique assets, references, and paper-bearing bookmarks
separately. Write a verified-success manifest only after those checks; a
partial intake keeps its explicit unresolved list and partial status.
