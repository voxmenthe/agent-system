# Worked examples, one per visual grammar

Illustrations, not extra rules. Every example still obeys the limits in
`SKILL.md` step 4: 16 nonblank lines (12 under a Zoom heading), 88 visible
columns, 7 named elements, 9 connectors, 2 nesting levels, one relation type.

## Indented call tree — runtime control flow

Nesting carries the relation, so no connectors are drawn.

```text
submitForm
  createSession
    persistPrompt
    launchAgent
  navigateToSession
```

## Pseudocode — logic, an algorithm, or a decision sequence

Real local names, so the reader can grep them. Keep the shape, drop the
ceremony.

```text
on(save)
  if digest is unchanged
    return cached result
  write new content
  invalidate cache
  return fresh result
```

## File or module tree — ownership, registration, containment

Containment only; this says nothing about runtime order. Annotate nodes whose
location the reader cannot guess.

```text
skills/show-me-clearly/
├── SKILL.md
├── references/
│   └── observed-change.md
└── scripts/check_output.py
```

## Component tree — UI structure

State hooks appear beside the component that owns them, with owning paths in
parentheses.

```text
<SessionPage> (apps/web/src/routes/session.tsx)
  useSessionEvents()
  <SessionToolbar> (packages/ui)
```

## Connector flow map — state machine, commit or failure boundary

Connectors earn their place here: the failure edge leaves the main path, which
indentation cannot express. Colors pair with word labels.

```html
<pre>
<span style="color:#0969da"><strong>■ CHECK</strong></span> validate the old and new state
             |
             v
<span style="color:#9a6700"><strong>■ SAVE</strong></span> retain the old value
             |
             v
<span style="color:#1a7f37"><strong>■ LIVE</strong></span> expose the new value
             |
             `-- failure --&gt; <span style="color:#cf222e"><strong>■ STOP</strong></span> preserve evidence
</pre>
```

## Shape diff — what is different now

A `+` line at its real depth shows the new call without a source-line diff.

```diff
 submitForm
   createSession
     persistPrompt
+    expandSkillMention
     launchAgent
```
