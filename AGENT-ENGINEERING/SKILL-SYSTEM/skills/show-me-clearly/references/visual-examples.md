# Worked examples, one per visual grammar

Illustrations, not extra rules. Every example still obeys the limits in
`SKILL.md` step 4: 16 nonblank lines (12 under a Zoom heading), 88 visible
columns, 7 named elements, 9 connectors, 2 nesting levels, one relation type.

## Color-assisted `<pre>` block — markup and palette

Put the literal `■` glyph on every colored node and a subject-specific role
inside `<strong>` beside it:

```html
<pre>
<span style="color:#0969da"><strong>■ CHECK</strong></span> validate the old and new state
</pre>
```

Choose at most four roles from this palette and use it consistently:

| Color | Hex | Roles |
|---|---|---|
| blue | `#0969da` | entry, control, calls, checks |
| amber | `#9a6700` | state, ownership, waiting, retained data |
| green | `#1a7f37` | results, visible state, successful commit |
| red | `#cf222e` | failure, refusal, unsafe state, stop |

The word inside `<strong>` carries the meaning; the color only reinforces it.

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

## Paired policy-evaluation trace — why two inputs reach different outcomes

Run the same ordered rules down both columns, put a status word in every cell,
and mark only the first divergence. `SKIPPED` means the rule did not apply and
evaluation went on; `NOT REACHED` means evaluation stopped before that rule.
Keep the two apart, and never continue a denied trace as if later rules ran.

```text
rule, in evaluation order   A: fresh token           B: expired token
1 signature valid           PASS                     PASS
2 token unexpired           PASS                     FAIL  <-- first divergence
3 org membership            SKIPPED (service acct)   NOT REACHED
4 role grants write         PASS                     NOT REACHED
outcome                     ALLOW                    DENY 401
```

## Lifecycle phase rail — one subject's phases, retries, and terminal outcomes

Progress runs along the top rail. Waits and retries sit in a band below it, and
terminal outcomes sit in their own band. Cancellation and failure get separate
labeled boxes, and the retry edge names where it re-enters the rail.

```text
phase rail   QUEUED --start--> RUNNING --exit 0--> DONE
                                |   ^
                        timeout |   | retry while attempt <= 3
                                v   |
retry band                     BACKOFF
                                |
                                | no retries left
                                v
terminals    CANCELLED         FAILED
                ^
                `-- cancel from QUEUED, RUNNING, or BACKOFF
```

## Compensating-layers chain — what each defense stops and what still gets through

Order the layers as the threat meets them. After each layer, say what it stops
and what escapes to the next one. End with the residual risk and the response;
the last layer never makes the risk zero.

```text
threat   an uploaded archive writes outside its extract folder
   |
   v
1 member-name check   stops ../ segments and absolute paths
   |   escapes: a symlink member that points outside
   v
2 lstat walk          rejects symlinks and special files
   |   escapes: a file swapped in after the walk, before the copy
   v
3 hash after copy     detects a tree that differs from the one walked
   |   remains: a swap is caught after it lands, not prevented
   v
residual   detection only; the install rolls back on a hash mismatch
```
