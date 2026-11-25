# Subject: observed change between revisions

Read this before writing an explanation of a code change. It assumes the spine,
prose rules, and visual limits in `SKILL.md`.

## Pin both sides

Pin base and head separately. Pair old and new behavior at the same
granularity. Give old claims base evidence and new claims head evidence.
Explain the observable effect, not only the edited lines.

## The plan is provenance, not content

When the change implements a supplied plan, the plan is provenance. Cite it in
Scope, then explain the diff. The reader can read the plan themselves. What
they cannot get elsewhere is what the code actually does, where it lives, and
how it differs from what came before. If a section's claims all trace to plan
documents rather than code, rewrite the section from the diff.

## Diff the shape that changed

The orientation view answers one question: what shape is different now? Diff
that shape, not always the source lines. Four shapes cover most changes:

- **Component change** — diff the component tree; `+` the added child in place.
- **File-layout change** — diff the file tree; show a split file as `-` the old
  path and `+` the new directory with its children.
- **Call-tree change** — diff the call tree; a new call appears as a `+` line
  at its real depth.
- **State or control-flow change** — diff the pseudocode; show the new branch
  and what it now returns.

```diff
 submitForm
   createSession
     persistPrompt
+    expandSkillMention
     launchAgent
```

A small ASCII two-lane comparison works when the point is a before/after pair
rather than a shape edit. A source-line diff is the right choice when the point
is *which lines* carry a mechanism — that belongs in the load-bearing-diffs
section below.

## Add a load-bearing-diffs section

After the orientation element, add a dedicated section of real diff hunks —
"The load-bearing diffs". Include 4–8 hunks from `git diff base..head`, one per
key mechanism. Each hunk:

- is trimmed to the lines that carry the mechanism (a subset is fine — say so
  in the caption);
- is verbatim unless an elision is marked with `...`;
- has a one-line caption stating why it carries weight;
- starts from a compact file/change table (≤7 rows: file, what changed) when the
  diff spans more than a few files.

New files have no base revision. Show them as fenced `text` excerpts labeled
"new file — excerpt, not a diff"; never fake `-`/`+` lines for them.

Fenced `diff` and `text` blocks count as visuals under the checker: at most 16
nonblank lines (12 under a Zoom heading) and 88 visible columns. Trim hunks to
fit, and abbreviate any source line over 88 columns with a marked elision plus
a note.

Diffs are evidence for the journey, not a substitute for it. The question
sections still explain mechanism and consequence in prose.
