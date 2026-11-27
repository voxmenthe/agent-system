---
name: chalk-talk
description: "Turn one technical idea into an animated, self-contained HTML board lesson with storyboarded beats, a deterministic render(t), play, replay and scrub controls, and a headless-browser check of every beat. Use when the user explicitly invokes $chalk-talk or asks for a chalk talk or an animated board explanation of a single mechanism. Do not use for static diagrams, slide decks, dashboards of real data, or code walkthroughs."
disable-model-invocation: true
---

# Chalk Talk

Teach one mechanism the way a person at a whiteboard would: draw the stage,
then move concrete values through it, beat by beat. The deliverable is one HTML
file that plays offline, replays identically, prints its final frame, and has
passed a live check of its beats.

## Stop rules

- Explicit-only. Build when the user invokes `$chalk-talk` or asks for a chalk
  talk by name; otherwise suggest it in one line and stop.
- One idea per board. If the request holds two, say so and build the one the
  user picks, or the first if they leave it to you. Never cram both.
- Zero external requests: no CDN, web font, remote image, analytics or
  `fetch`. System font stacks only; everything inline.
- Every number on the board comes from the user's material or from a model
  computed in the page and labelled as a toy. Never animate invented figures
  as fact.
- Do not hand over a board until `board_tool.py check` exits 0 and you have
  looked at its start, middle, end and replay PNGs. If Chromium cannot run,
  deliver the file marked **unverified** and say why.
- Never overwrite an existing file without asking. Video only on request.

## Principles

- **At most 2 regions, about 6 beats.** A region is one visual stage: lanes, a
  queue, a chart. Needing a third means a second board.
- **Concrete values over boxes.** Eight numbered clients, 4 requests a second,
  waits of 2, 4 and 8 s; not "Client", "Server", "delay".
- **Pure `render(t)`.** Build every node once, up front; `render(t)` only sets
  attributes from `t` and constants. No `Math.random`, `Date`, timers or CSS
  transitions in the board. Randomness comes from Mulberry32 seeded by element
  index, so every replay is identical.
- **Fixed geometry.** The board is an SVG `viewBox`; caption and counter slots
  have fixed heights, so the board never jumps between beats.
- **Single file.** Works over `file://`, inside an `<iframe>` (it posts its
  height), in print (final frame) and under reduced motion (final frame,
  paused).

## Phase 1: Frame the idea

State the idea as one claim. Ask at most one question, and only when the claim
or the audience is genuinely ambiguous. Then, before any code, write a short
ASCII storyboard and beat schedule in your reply:

    +------------- region 1: 8 client lanes --------------+
    | c1 x    o           o                      o      |
    +------------- region 2: server load per second -----+
    |        ##          ##     limit - - -     ##      |
    t=0-1.6 stage | 1.6-5 sweep, no jitter | 5-6.6 overload
    6.6-7.6 reset | 7.6-11.2 sweep, jitter | 11.2-14 numbers

Each beat gets one caption sentence (two lines at most) and one visible change.

## Phase 2: Build from the starter

Copy [assets/starter.html](assets/starter.html) to the save path: the user's
path, or `PLANS/EXPLANATIONS/<topic>-chalk-talk.html` at the repository root
(create the folder). Replace sections 1, 3 and 4 (beats, scene build,
`render(t)`) plus the title, `<desc>`, takeaway and note. Keep section 2
(helpers) and section 5 (transport and board contract) unchanged. Choose
`data-theme` (`slate` dark, `paper` light) and `data-style` (`sketch` adds a
subtle wobble to `.ct-sketch` strokes; `clean` suits chart-like boards).

Read [references/motion-and-layout.md](references/motion-and-layout.md) before
writing the scene: draw-on strokes, moving tokens, toggles, layout budgets,
colour roles and grid silhouettes.

## Phase 3: Verify the live beats

    python3 <skill-directory>/scripts/board_tool.py check <board.html> \
      --at 0.8,3.0,6.2,9.0,13.0 --dir <png-dir>

Pick `--at` times inside every beat, mid-motion as well as settled; without
`--at` it samples 85% of the way through each beat. The first run may create
`~/.cache/chalk-talk/venv` with Playwright and Chromium; that is expected.

The check seeks each time on a frozen clock, saves PNGs, and prints one
`DEFECT:` line per failure: console or page errors, external requests,
horizontal overflow, overflowing slots, clipped or overlapping visible text,
CSS animation in the board, board height drifting more than 2 px, Replay not
restoring the exact `t=0` board or not playing, and print or reduced motion
not showing the final frame. Fix and rerun until it exits 0.

Then open the start, a middle, the end and the replay PNG and look. Is every
label legible and inside its region? Does each beat show its one change? Does
the end frame state the takeaway with its numbers? Mechanical passes do not
catch a confusing board. Report the file path, its size and the PNGs you
inspected.

## Phase 4: Optional capture

Only on request:

    python3 <skill-directory>/scripts/board_tool.py render <board.html> \
      --format mp4 --rate 30 --viewport 1200x720 --out <path>.mp4

`render` replays from `t=0` on a virtual clock, so frames are exact. Add
`--action "click:<selector>@<sec>"` to press a toggle mid-capture, or `--page`
to capture the whole viewport. It needs `ffmpeg` on `PATH` and says so when it
is missing. For a grid silhouette of a reference shape,
`board_tool.py trace <image.png> --grid 24` prints rows of `#` and `.` (PNG
only, at most 32 by 32 cells).

## Board contract

`board_tool.py` drives the page through `window.chalkTalk`: `duration`,
`beats` (`start`, `end`, `caption`), `seek(t)` (pause and render `t`),
`play()`, `pause()`, `replay()` and `state()` (`t`, `playing`, `duration`),
plus the attributes `data-ct="board|play|replay|scrub"` and `data-ct-slot` on
the fixed slots. The starter implements all of it; keep it when you replace
the scene.

## Boundaries

Static diagrams belong to the `show-me` family, code walkthroughs to
`show-code` or `explain-code`, and research explainers to `explain-research`.
