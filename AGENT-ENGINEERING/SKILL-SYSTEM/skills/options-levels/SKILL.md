---
name: options-levels
description: Turn an options author's levels pages (GammaGirlLab's weekly SPX PDF, its QQQ card or a daily card, or another author's levels map) into a checked transcript, a front-month ES/NQ map and today's read in futures points, with the `mkt levels` commands. Use only when the user or a market-run prompt explicitly invokes $options-levels or names this skill for such a map. Do not use automatically, to compute dealer positioning yourself, for a live options feed, or for trade execution.
disable-model-invocation: true
---

# Options levels

The reading is yours: open every page at full size and type what it prints. Everything after the reading is
scripted, so the map, the spec and today's table come from one transcript instead of a hand-typed JSON (10-25: a
hand spec took about 10 minutes and its axis error showed only in the PNG; 10-26: a 26-minute helper build, and a
draft that kept numbers from before the map re-rendered).

Run the commands from the repository root of the market runs (`tracking-context-td`), where `scripts/grok-X-adhoc/mkt`
lives; the code stays there beside the palette, chain and basis code it imports.

## Take the path the day needs

| Day | Path | Commands |
|---|---|---|
| Sunday, the weekly PDF | Read, transcribe, check, spec, map, today | `transcript`, `check`, `spec`, `map`, `today` |
| A weekday | Carry the week's map forward and read it against today's price | `spec --carry PRIOR_WORKDIR`, `map`, `today` |
| A daily card or the QQQ card | Transcribe the newer clock and let it replace its expiries | `transcript --daily`, `check`, `spec --carry PRIOR_WORKDIR`, `map`, `today` |

1. `mkt levels transcript WORKDIR ROOT_ID [--daily]` writes `images/ROOT_ID.md` in the transcript template, with the
   root's self-replies in the run's posts as its pages and their saved images. Missing pages: `mkt posts pull` the
   IDs or give `--pages`; missing images: `mkt media WORKDIR --post ID`.
2. Read each page at full size and fill every section: [what each GammaGirlLab page holds](references/gammagirllab.md),
   [how to fill the template](references/transcript-template.md).
3. `mkt levels check TRANSCRIPT` refuses an unfilled or empty section, a missing text box, or a level with no unit,
   expiry or calculation clock. Fix the transcript, not the check.
4. `mkt levels spec WORKDIR [--carry PRIOR_WORKDIR] --fetch-chains` writes `charts/options/levels.json`. For one
   source and one expiry, the transcript with the newest OI snapshot holds every row; expired rows drop, and the
   command prints both. It never replaces a levels.json it did not write. `--fetch-chains` first fetches, from CBOE
   (network), the SPX or QQQ chain of each panel the run holds none for in `WORKDIR/chains/`, and records each fetch's
   clock and the file's own last-trade clock, or its error, in the spec's `chain_fetches`; a failed fetch leaves that
   panel without a chain (10-27: the first map lacked chain gamma because the fetch had not run). Leave the flag off
   to replay a past run offline.
5. `mkt levels map WORKDIR` renders `charts/options/futures-levels.png` with its `.md` and `.json`. It exits 1 when
   fewer than half of a panel's levels sit within 4% of the mark: check the transcript's units and values before
   looking at the chart. Open the PNG. The conversion rules are in [basis](references/basis.md).
6. `mkt levels today WORKDIR` writes `charts/options/levels-today.md`: each level's distance from the newest complete
   front-month bar in points and in today's implied 1σ, whether price crossed it since its OI snapshot, today's net
   gamma and the clocks that date the map. Run it again after any re-render, and before drafting the options section.

What the report shows, and how: [report](references/report.md).

## Rules

- Read every page at full size; transcribe every text box verbatim, headline, verdict and footer included.
- Never invent a level. A number the page does not print is not a row; a band's midpoint is a level only when the
  page prints it.
- Keep SPX, SPY, ES, NDX, QQQ and NQ units separate. Type the unit as printed; the map converts.
- Keep the source, publication, observation and calculation clocks apart. Scenario weights stay dated weights from
  the author's OI snapshot, not new probabilities.
- The dealer-sign convention is the author's. Say so; do not adopt or invert it.
- Cross-checks: the run's CBOE chain (`cboe_chain.py`, joined to the map from `WORKDIR/chains/`) carries a naive
  dealer sign, stated as such, and `spx-daily-report` gives competing gamma views. A matching level is not proof of
  the author's positions, and a mismatch is not proof of an error.
