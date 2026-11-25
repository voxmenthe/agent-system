# Filling the transcript template

The template is `scripts/grok-X-adhoc/templates/options-levels-transcript.md`; `mkt levels transcript` writes it and
the other commands read only it. The weekly form has every section; the daily form (`--daily`) keeps Pages, Clocks,
Text boxes, Levels, Bands and Implied moves.

- **Header.** Chart label: the short source label the chart and tables show ("GGL, Fri OI"). Read: when you finished
  reading every page at full size, `YYYY-MM-DD HH:MM PT`.
- **Pages.** Written for you. Delete a row that is not a page (a later self-reply with no levels).
- **Clocks.** `YYYY-MM-DD HH:MM PT · as printed: "..."`, converted from the page's zone (ET minus 3 hours). Marks
  and OI snapshot are required; OI refresh and Re-check after may be `none`. Re-check after is the next event that
  dates the map ("re-check about an hour after" a 2:00 pm ET Fed decision is 12:00 PT).
- **Text boxes.** One line a box, `- p1 "TITLE": "words as printed"`, every box on every page.
- **Tables.** One row a printed item. Numbers as printed (commas, a typographic minus and a leading `~` are fine);
  units as printed; expiries as `YYYY-MM-DD`; never a `|` inside a cell (write `/`). Page is the Pages table's
  number. Calc is the calculation clock in words ("Fri 10/23 close OI").
- **Levels.** Kind is one of call_wall, put_wall, flip, vol_trigger, node, shelf, pivot, range, target, other. Label
  is an optional short chart label ("reclaim", "break line"). Text is the page's words for the level.
- **Bands.** Display `shade` draws the band; `audit_only` keeps it in the tables only (a day's 70% range).
- **Scenarios.** Three rows, break, chop and reclaim; Line is the break row's upper bound and the reclaim row's lower
  bound, blank for chop. A stated condition goes on a `- Condition: "..."` line under the table.
- **Hedging asymmetry.** One session's flows a table. Level is the level each move reaches as printed (the base ×
  (1 + move) when the page prints only the move), in its Unit, for the Expiry session; `check` refuses a row whose
  implied base, Level ÷ (1 + move), is more than 0.1% from the rows' median. Flow is signed, selling negative; a
  printed "~flat" is 0, explained on a `- Note:` line. The panel's headline goes on a `- Line: "..."` line (the
  chart's hedge title) and the flows' timing on a `- When: "..."` line ("Mon 11/2 at the open"). `spec` carries the
  table to the map, which writes it into futures-levels.md as "### Modeled hedging by move", each level converted
  like the map's, for the report to paste.
- **Implied moves.** 1σ without its ±. Today's row gives `mkt levels today` its σ column.
- A section the pages do not cover reads `none on these pages`; Pages, Clocks, Text boxes and Levels never do.

`mkt levels check` prints each problem as `section NAME row N: Column problem`. The transcript is also the run's
image transcription of the root post (`images/<id>.md`), so `mkt quotes`, `mkt challenge` and the page read its
text boxes as the image's words; until its FILL markers are gone they count the post as untranscribed.
