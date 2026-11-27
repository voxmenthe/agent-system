# Motion and layout patterns

Read before writing a board's scene. Every pattern keeps `render(t)` pure: it
reads `t`, constants and nodes built once, and only sets attributes.

## Beats and timing

- One row per beat in `BEATS`: `start`, `end`, caption. The caption slot shows
  the beat whose window holds `t`; the last beat ends at `END`.
- Inside `render(t)`, each change gets its own window with `span(t, a, b)`
  (eased 0 to 1). Windows may overlap across beats; finish a beat's main
  change about 0.2 s before the beat ends so its settled frame is clean.
- Stagger a group by index: `span(t, a + i * 0.05, b + i * 0.05)`.
- Use a linear `clamp((t - a) / (b - a))` instead of `span` for anything that
  stands for time itself (a playhead, a clock), so its speed is honest.
- Derived values (a counter, a peak) are recomputed from `t` every frame,
  never accumulated: `queued = tokens whose arrival time <= t`.

## Draw-on strokes

```js
const edge = svg("path", { d: "M80 400 H880", fill: "none", class: "s-ink",
  "stroke-width": 2.5, pathLength: 1, "stroke-dasharray": "1 1" }, strokes);
// in render(t)
edge.setAttribute("stroke-dashoffset", 1 - span(t, 0.2, 1.0));
```

`pathLength: 1` makes the dash math independent of the real length. Use
`path` elements for anything drawn on; draw a box as `M x y H x2 V y2 H x Z`.

## Tokens and queues

A token's position is a function of its own schedule, not of the previous
frame:

```js
const enter = 2 + i * 0.6;                       // seconds, fixed at build time
const p = span(t, enter, enter + 0.8);
node.setAttribute("cx", lerp(fromX, slotX(i), p));
```

For a queue that shifts when the head leaves, compute the slot from counts:
`slot = (tokens ahead of i that have arrived) - (tokens served by t)`. Both
counts come from fixed schedules, so seeking backwards works.

Pop-in: scale the radius, `r = 7 * clamp((t - at) / 0.3)`. Fade-out: opacity
`1 - span(t, a, b)`. Hide parked nodes with opacity 0 or radius 0; nodes may
sit off the board while hidden, and the check ignores invisible text.

## Seeded randomness

```js
const rand = mulberry32(index + SALT);           // one stream per element
const delay = rand() * windowSeconds;            // drawn at build time only
```

Draw every random value while building the scene, in a fixed order. Pick
`SALT` so the outcome is representative rather than flattering, and say on the
board or in the note that the model is seeded.

## Computed models

When the idea is a process (retries, scheduling, caching), simulate it once at
load from named constants and let captions quote the results with template
strings, so the words cannot drift from the picture. Keep the model small
enough to state in one sentence in the note under the board.

## Toggles and sliders

Keep controls outside `[data-ct="board"]` (in or beside the transport strip).
Store choices in a `params` object that `render(t)` reads, and re-render on
change:

```js
const params = { jitter: true };
toggle.addEventListener("click", () => {
  params.jitter = !params.jitter;
  toggle.setAttribute("aria-pressed", String(params.jitter));
  window.chalkTalk.seek(window.chalkTalk.state().t);
});
```

Capture a toggle in video with `render --action "click:#jitter@4"`.

## Layout budget (viewBox 960 by 540)

- Margins of at least 24 units; region titles at the top-left of each region.
- Text sizes: 20 to 24 for titles, 16 to 17 for labels, 14 for monospaced
  numbers. Below 14 is unreadable once the board scales down.
- Reserve rows: a title row, the region body, a legend or axis row. Give
  moving labels their own row so they never cross static text; split a
  playhead line so it skips label rows.
- Two labels in the same place must crossfade with non-overlapping windows;
  the check flags fully visible labels that overlap.
- Put a non-breaking space between a number and its unit in captions
  (`"wait 2\u00a0s"` in a JavaScript string) so a unit never wraps alone.
- Captions: at most two lines at 1200 px wide; the starter's narrow-screen CSS
  stacks the slots and allows four lines on phones. Check a phone layout with
  `--viewport 390x844` when the board will be read on one.

## Colour roles

Use classes, not colours: `f-ink`/`s-ink` for the stage, `f-dim` for
secondary text, `f-hi`/`s-hi` for the current focus (a playhead, the active
token), `f-warn`/`s-warn` for failure or overload, `f-good`/`s-good` for
success, `s-faint` for guide lines. Both themes map these roles to colours
with at least 4.5:1 contrast. SVG presentation attributes do not accept CSS
variables, so set colour through these classes. Never encode meaning in colour
alone: pair it with shape (filled versus hollow dot, a cross) or a label.

## Sketch style

`data-style="sketch"` applies a displacement filter to `.ct-sketch` groups.
It reads as hand-drawn on curves and short strokes; on long straight lines at
1x pixel density it can leave small steps or specks, so chart-like boards
should use `clean`. The filter region uses `userSpaceOnUse` so perfectly
horizontal lines (zero-height boxes) do not vanish. Keep text outside
`.ct-sketch` so it stays crisp. Reduced motion turns the filter off.

## Grid silhouettes (at most 32 by 32)

To draw a recognisable shape (a server, a cloud, a key) as cells that light
up, trace a reference PNG:

```sh
python3 <skill-directory>/scripts/board_tool.py trace shape.png --grid 20 --format json
```

The output is `{"columns", "rows", "cells"}` where each cell row is a string
of `#` and `.`. Paste `cells` into the board and build one `rect` per `#`
at build time, then reveal them in `render(t)` by row, or by distance from a
starting cell for a fill effect. The shape is cropped to its bounding box;
`--no-crop` keeps the margins, `--invert` traces the background, and
`--fill` sets how much of a cell must be ink. `trace` reads non-interlaced PNG
only and decodes in pure Python, so downscale large images first.

## Reading check defects

| DEFECT | Usual cause and fix |
|---|---|
| horizontal overflow | a fixed-width element wider than the viewport; use `max-width` and `min-width: 0` |
| status slot overflows | caption longer than two lines; shorten it, never grow the slot per beat |
| text clipped by the board edge | label anchored too close to an edge; anchor `end` near the right margin |
| visible labels overlap | two labels share a row or a crossfade overlaps; move one or separate the windows |
| CSS animations run inside the board | a `transition` on board nodes; delete it and animate in `render(t)` |
| board height changes | a slot without fixed height, or content added during play |
| Replay does not restore the exact board | `render(t)` reads state it changes, or nodes are created after build |
| one second of clock moved playback by ... | the play loop ignores frame timestamps; keep the starter's transport |
| beforeprint or reduced motion | the starter's handlers were removed; restore section 5 |
| external request | a remote font, image or script; inline it or delete it |
