# WSJ Site Map and Stable Knobs

Observed in the owner's authenticated Chrome session through the
Chrome plugin on 2026-08-09. Treat semantic structures and embedded data fields
as more stable than generated CSS classes.

## Authentication

- Intended Chrome account: `$CHROME_PROFILE_EMAIL`.
- Read through the transport `SKILL.md` selects. With Claude in Chrome, use the
  tab in your own group; with the host Chrome plugin, claim the exact WSJ tab
  returned by `chrome.user.openTabs()`.
- Verify the subscriber state in the page you are reading. Do not inspect Chrome's
  profile files, cookies, local storage, passwords, or credential stores.
- Authenticated pages currently expose both:
  - a non-generic account button showing the subscriber's name
  - a nonempty `props.pageProps.dylanEntitlementToken`
- Older `/articles/` templates can render a minimal header with no account
  button. On those pages a nonempty `dylanEntitlementToken` plus the absence
  of a `Sign In` control is sufficient evidence of the subscriber session.
- A `Sign In` or `Log In` header signal is an explicit signed-out result.
  Treat other missing or conflicting account/entitlement signals as
  unresolved until the visible header and page type are inspected.

Never emit entitlement contents. Never inspect cookies or credential stores.

### Legacy helper failure meanings

The bundled Python helper remains a compatibility path for hosts with neither
Claude in Chrome tools nor a Chrome plugin. Its state is stored under
`~/.codex/state/wsj-research/browser.json`.

- Exit `10` is an authenticated-session failure. Helpers predating the
  sparse-header fix false-positive on older `/articles/` pages that render no
  account button; confirm with `status` on the homepage before treating it as
  a logout.
- Exit `11` means JavaScript from Apple Events is disabled.
- Exit `12` is a browser-target transport failure, not an authentication result.
  If a visible WSJ window opened, AppleScript may still have attached to a
  different same-bundle or headless Chrome process; no article retrieval occurred.

## Homepage

URL: `https://www.wsj.com/`

Purpose: editorial rank and framing.

Useful structure:

- semantic `main h2` headings label modules such as `Top Stories`, section
  names, and `Opinion`
- following `main h3` elements provide ranked story headlines and links
- link query parameters such as `mod=hp_lead_pos1` encode module position
- `#__NEXT_DATA__` → `props.pageProps` contains structured story objects
  throughout `leadCollections`, `featureCollections`,
  `superTopperCollections`, and other collections
- story objects commonly expose `articleUrl`, `headline`, `summary`,
  `authors`, `timestamp`, `flashline`, and `modCode`

The Chrome workflow uses semantic headings for section/rank and recursively
matches the structured story object for summaries and metadata. Exclude Buy
Side and video modules unless the request includes them.

## Latest Headlines

URL: `https://www.wsj.com/news/latest-headlines`

Purpose: chronological monitoring and breaking-news discovery.

`#__NEXT_DATA__` → `props.pageProps.latestHeadlines` currently contains 50
items. Fields include:

- `articleUrl`
- `headline`
- `summary`
- `timestamp`
- `flashline`
- `bylineData`
- `isOpinion`
- `isVideo`
- `type`

This feed can include live coverage and Opinion. Keep those labels during
analysis.

Fifty items is a count, not a time window. On a weekend it reaches back only
about a day (a Sunday-evening read ended near Saturday 16:00 PT), so a Friday
evening scoop can be absent from it. When the task window is longer than the
feed, sweep section pages (`/finance`, `/finance/stocks`, `/economy`,
`/business`, `/politics`, `/world/middle-east`, `/world/china`, as the topic
needs) for article URLs; see the section-sweep note in
[claude-in-chrome-workflow.md](claude-in-chrome-workflow.md).

## Search

Base URL: `https://www.wsj.com/search`

Visible input:

- type: `search`
- aria-label: `Search the Wall Street Journal`
- placeholder: `Enter News, Quotes, Companies or Videos`

Stable query parameters:

| Parameter | Values | Meaning |
|---|---|---|
| `query` | URL-encoded text | search text |
| `dateRange` | `1d`, `7d`, `30d`, `1yr`, `all` | preset time filter |
| `sort` | `relevance`, `desc`, `asc` | relevance, newest first, oldest first |
| `products` | comma-separated source names | result source filters |
| `page` | positive integer | result page; 20 organic results per page |

Product values:

- `wsj`: Articles
- `video`: Videos
- `audio`: Podcasts
- `livecoverage`: Live Coverage
- `buyside`: Buy Side
- `games`: Games

Structured data:

`#__NEXT_DATA__` → `props.pageProps.searchResults` contains organic results.
`sponsoredContent` is separate and excluded. Each result commonly has:

- `articleUrl`
- `headline`
- `summary`
- `timestamp`
- `flashline`
- `bylineData`
- `printHeadline`
- `printPublicationDate`
- `seoPathValue`

Other useful page fields are `advancedSearchFields`, `pageNumber`,
`queryValue`, and `resultsCountMeta`.

WSJ offers no arbitrary date picker. Retrieve preset/all-time pages through the
selected transport, sort them, and apply ISO date bounds to the extracted results.
Date-only bounds are UTC; the upper bound is inclusive through the named day.
Page caps can still truncate a middle or broad date interval.

## Article pages

Standard story URLs can occur under many paths, including `/articles/`,
`/tech/ai/`, `/finance/`, `/business/`, and others. Do not identify articles by
the `/articles/` prefix alone.

Preferred structured path:

`#__NEXT_DATA__` → `props.pageProps.articleData`

Useful metadata:

- `headline.text`
- `standFirst.content`
- `canonicalUrl`
- `byline`
- `authors`
- `publishedDateTimeUtc`
- `updatedDateTimeUtc`
- `sectionName`
- `sectionType`
- `typeDisplayName`
- `printHeadline`
- `printPublicationDate`

Preferred body:

- `articleData.flattenedBody`: an **array of typed blocks** (`paragraph`,
  `hed`, `image`, `inset`, `ad`, ...), not a string
- `paragraph` nodes: text sits in nested segments; a link or emphasis segment
  carries its own `content` or `nested` children. Recurse and join every
  `text` value in order
- `hed` nodes: section headings
- `inset` with `insetType=ai_summary_bullets`: quick-summary bullets
- `ad` nodes: ignore

`props.pageProps.isFreeArticle` and `paywallIndex` describe access. The skill
still requires an authenticated header/entitlement state even if content
happens to be embedded in source.

JSON-LD `NewsArticle` plus `main p` is a fallback for nonstandard pages such as
some live-coverage formats. It is noisier and marked `dom_fallback`.

## Drift recovery

If extraction returns empty data on an authenticated page:

1. Recheck authentication in the exact tab you are reading.
2. Inspect that exact tab, never whichever tab happens to be frontmost.
3. Check `#__NEXT_DATA__` and enumerate `props.pageProps` keys.
4. Prefer replacement semantic fields or data objects over CSS classes.
5. Compare one homepage, one latest or search page, and one standard article.
6. Patch the field mapping or guidance and rerun all three smoke tests.
7. If WSJ removed authenticated content from the page payload, stop and report
   the limitation. Do not seek a bypass.
