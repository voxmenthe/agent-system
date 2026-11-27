---
name: show-me-clearly
description: Explain unfamiliar code, a pinned code change, or a settled technical plan in a saved, source-backed Markdown walkthrough. Use when an early-career engineer needs a clear mental model, a small ASCII map, and precise source links. This skill explains existing decisions; it does not implement code or settle an open design.
disable-model-invocation: true
---

# Show Me Clearly

Make unfamiliar code click for a moderately technical early-career engineer.
The reader should be able to explain the mechanism after one pass, use that
understanding to make a sound decision, and follow source links when they want
to verify a claim.

Use one dependable reading journey. Adapt the questions and zooms to the
subject; do not make the reader learn a new document shape every time.

## Stay inside the boundary

This skill explains:

- one code mechanism, relationship, representative runtime path, or interface;
- one observed code change between resolved revisions; or
- an already-settled phased technical plan whose boundaries are supplied.

It does not implement the code, choose architecture, invent plan phases, or
turn an unresolved design question into a settled explanation. If the subject,
revision, comparison side, or plan boundary cannot be resolved, stop and ask
for that missing fact.

Always save the explanation as a new Markdown file with a descriptive name and
`YYYYMMDD` suffix, in `PLANS/EXPLANATIONS/` of the subject repository unless
the user names a folder. Return a link to it.

## Write for this reader

Assume the reader knows ordinary programming ideas and some of the domain.
They are new to this repository, its local names, and this mechanism.

Write like a knowledgeable teammate talking through the code: conversational
language, natural contractions, active verbs, short paragraphs. Start with
substance. Cut throat-clearing, formal filler, recap lines, and stacked noun
phrases. Give headings enough meaning that a quick skim reveals the argument.

Keep the technical detail and honest complexity. Use exact state names, hashes,
processes, and failure boundaries when they matter. Define local jargon once,
and ground abstractions in one concrete example. Plain language should expose
the real mechanism with its precision intact.

Keep this skill's machinery and framing out of the document. Headings and
prose never name its working tools or stages ("claim ledger", "evidence
ledger", "reading spine", "orientation map"), narrate the document ("in the
zoom below we inspect…"), or print pacing labels ("the one idea to hold onto",
"the key insight", "at its core"). Title the orientation section for the
subject, such as "Where one upload goes". The spine's fixed headings and the
receipt label are the only exceptions.

### Write in short lines

One idea per sentence. Most sentences run 5–15 words; split a sentence that
carries two claims. Split a paragraph that exceeds four lines at an idea
boundary. Vary sentence length and structure: avoid repeated sentence frames,
rule-of-three cadences, and stacked corrective negation ("not X but Y",
"never Z"). Keep negations that carry the safety model ("no raw fallback");
delete the ones that only sound careful. Crisping means splitting sentences,
never removing precision — byte limits, digests, lock ordering, and failure
boundaries stay in the text. A revision that reads simpler but says less is
wrong.

Call each thing by its real name: the code identifier or the user's own words.
Do not coin labels like "the switch-back note". Write "it", "this", or "that"
only when the referent sits in the same or the previous sentence. Start each
bullet with the word that sets it apart (a state, a verdict, a function name),
not an opener every bullet shares; a skimming reader sees the first two words.

When goals compete, use this order:

1. The reader can explain the mechanism accurately.
2. The reader can act or decide from that model.
3. The reader can verify the important claims against source.

## Keep this reading spine

Every saved explanation follows the same cognitive order:

```text
# <concrete result title>

<two or three sentences that answer the question>

## Scope
<revision, exact question, representative path or instance>

## <orientation heading for this subject>
<one small color-assisted ASCII map or table>

## <the reader's first real question>
<answer, concrete instance, mechanism, significance, receipt>

### Zoom — <local question, only when needed>
<small visual, plain words, mechanism, significance, receipt>

## <failure, limit, or misconception question when material>

## Keep this line
<one sentence the reader can repeat accurately>
```

Angle brackets are placeholders. Keep **Scope** and the final synthesis stable;
write the other headings as questions or concrete labels that fit the subject.
Use as many question sections as the explanation needs, but no section that
does not improve the reader's model.

Steps 1 and 2 below prepare the evidence. Steps 3 through 8 fill this spine.

## Build the explanation

### 1. Frame and pin one question

State the exact question the document answers. Pin the inspected commit or
named worktree state. For a change, pin base and head separately. For a settled
plan, pin the baseline and name the supplied plan source; label future behavior
`proposed`.

Choose one representative path or instance when the system has alternatives.
Name its trigger and caller-visible result. Do not silently merge paths.

### 2. Inspect before writing

Every subject uses the same reading journey; only the local questions and
visual grammar change. Identify the subject type, then read its reference
before writing — each carries the procedure and traps specific to that subject:

| Subject | Reference |
|---|---|
| Observed change between revisions | [`observed-change.md`](references/observed-change.md) |
| Static relationship or interface | [`static-relationship.md`](references/static-relationship.md) |
| Representative runtime path | [`runtime-path.md`](references/runtime-path.md) |
| Settled phased plan | [`settled-plan.md`](references/settled-plan.md) |

Read repository instructions, the complete target functions or types, relevant
callers and dependents, focused tests and docs, and history when intent cannot
be distinguished from present behavior without it.

Follow the actual data and call path. Notice ownership, state, process or
transport boundaries, persistence, side effects, failure, cleanup, and return
when they change the answer.

Keep a private claim ledger while working:

```text
claim | source side or revision | exact anchor | observed/inferred/proposed/conditional/unmeasured
```

Every node and edge you plan to draw is a claim too: record the call, import,
ownership, or transition that backs it. Do not print this ledger. It is a
correctness aid, not the reader's explanation.

### 3. Give the answer first

Open with two or three plain-language sentences that state:

- what the mechanism does;
- the load-bearing idea that makes the rest make sense; and
- the important result or consequence.

The answer must make sense before the visual. Do not start with scope metadata,
a file list, or a diagram the reader must decode.

### 4. Give one small orientation map

Choose the lightest grammar that still carries the relation, then keep it
inside the limits below. The limits are a ceiling, not a target: a five-line
tree that answers the question beats a compliant sixteen-line diagram that
answers it decoratively.

Match the visual grammar to the content, not to habit:

| Content | Grammar |
|---|---|
| Runtime control flow | indented call tree |
| Logic or an algorithm | 4–8 lines of pseudocode |
| Ownership, registration, containment | shallow file or module tree |
| UI structure | component tree with state hooks shown |
| State machine, commit/failure boundary | connector flow map (`\|`, `v`, `` `-- ``) |
| Why two inputs reach different outcomes | paired policy-evaluation trace |
| One subject's phases, retries, and terminal outcomes | lifecycle phase rail |
| Defenses and the risk that still gets through | compensating-layers chain |

When a verified TLA+ model and its `view.mjs` cover a state machine, cite the
`statechart` skill's numbered path and the check rather than redrawing it; a
hand-drawn state map is only an illustration.

Reserve drawn connectors for relations indentation cannot express: a branch
that rejoins, a failure edge leaving the main path, a transition back to an
earlier state. When plain nesting carries the relation, nest. For a worked
example of any grammar in this table, see
[`references/visual-examples.md`](references/visual-examples.md).

Use a renderer-independent ASCII chart or ASCII table. Prefer a color-assisted
raw HTML `<pre>` block for saved Markdown: the literal `■` glyph on every
colored node, a subject-specific role inside `<strong>` beside it, and at most
four roles from the fixed palette. The same reference holds the markup
template and palette. Bracketed words like `[AMBER]` are ordinary text, not a
color swatch. If raw HTML is unsuitable, use the same `■ ROLE` labels in a
fenced `text` block.

Color must never be the only carrier of meaning: pair every color with a word
label so the visual still works when styles are stripped. Every grammar obeys
these rules; a colored `■ ROLE` node works inside a tree, beside the node it
names.

Keep every orientation visual within all of these limits:

- at most 16 nonblank lines;
- at most 88 visible columns;
- at most 7 named elements and 9 connectors;
- at most 2 nesting levels; and
- one relation type: flow, ownership, state, or change.

Fenced `diff` and `text` blocks count as visuals under these limits. Trim to
fit, and abbreviate any source line over 88 columns with a marked elision plus
a note.

For an ASCII table, use at most 5 columns and 7 data rows. Put its conclusion
in prose; do not make the reader infer the point from the cells.

Do not add Mermaid unless the user explicitly asks for it. If requested, keep
it supplemental and give it no claim missing from the ASCII view or prose.

### 5. Explain through the reader's questions

After the map, use actual questions as headings. Choose only questions the
reader needs, and order them so each answer prepares the next. Useful shapes
include "What happens to one concrete input?", "What can fail, stop, or remain
unfinished?", and "What is this easy to confuse with?". Phrase questions for
the real mechanism rather than copying a fixed FAQ.

Each answer should normally contain this movement:

1. **Direct answer.** Answer the heading in the first sentence.
2. **Concrete instance.** Walk one real value, call, object, or state through
   the mechanism.
3. **Technical mechanism.** Name the exact function, boundary, condition, or
   state transition that makes it true.
4. **Why it matters.** State what the reader can now predict or decide.

Use paragraphs, not four repeated labels, when the movement is already clear.

### 6. Add a zoom only when the map hides something important

A zoom is a small local visual placed under the question it answers. Add one
when the overview cannot show a material subflow, state transition, branch,
ownership seam, or before/after change without breaking its limits.

Do not add a zoom for decoration or to repeat prose. Each zoom must:

- answer one named question;
- show one relation type;
- use at most 12 nonblank lines and 88 visible columns; and
- reconnect to a label already present in the orientation map.

A zoom may be 4–8 lines of pseudocode instead of a diagram; prefer pseudocode
when the answer is an ordered sequence of decisions and returns, using real
local names so the reader can grep them.

Explain a zoom in this order: **Plain words** (the shortest accurate reading),
**Under the hood** (the exact technical mechanism), then **Why it matters**
(the consequence). Use the labels when they reduce effort for the reader; omit
one rather than write an empty or repetitive paragraph.

### 7. Put source receipts beside the explanation

After each load-bearing answer or zoom, add one compact receipt with one to
three precise source links. In renderers that support it, prefer:

```html
<details>
<summary><strong>Receipt — why this claim is true</strong></summary>

- link text `worker.py:40-58`; target `../../src/worker.py#L40`
- link text `test_worker.py:91-112`; target `../../tests/test_worker.py#L91`

</details>
```

Links must be repository-relative, display the complete cited range, and use
`#L<start>` or `#L<start>-L<end>` for navigation. Resolve every link from the
artifact directory, and link non-contiguous ranges separately.

Observed source-backed claims need no status badge. Label `inferred`,
`proposed`, `conditional`, or `unmeasured` where the reader first meets the
claim. Do not hide uncertainty inside a collapsed receipt.

For a number (a size, count, timing, or cost), say how you know it: **measured**
(read from a run, log, or file), **derived** (computed from measured values or
code constants; show the arithmetic once), or **inferred** (your judgment).

Do not end with a dense evidence table that repeats the document. If a compact
source map would materially help navigation, use at most six grouped links and
do not restate claims in it.

### 8. Close the mental model

State material failure boundaries and “what it is / what it is not” before the
end when the obvious wrong model would mislead the reader.

Finish with a heading such as **Keep this line** and one sentence the reader
could accurately repeat to another engineer. Nothing follows it.

## Verify before returning

Read the saved artifact once as the target reader and check:

- The subject reference for this document type was read before writing.
- The first paragraphs answer the question without the visual.
- The orientation map can be understood without color.
- Each visual uses the lightest grammar that carries its relation.
- One real instance makes the mechanism concrete.
- Every zoom earns its place and reconnects to the map.
- The explanation states why the mechanism matters.
- Important uncertainty appears in the prose.
- Source receipts are local, precise, clickable, and not a second explanation.
- Every cited line range covers the code it names — spot-check against the
  actual file; the checker verifies that each range exists, not what it covers.
- Diagram nodes and edges are claims too: every drawn call, import, ownership,
  or transition matches source, or the visual says it is illustrative.
- No skill machinery or framing label appears in a heading or in prose.
- The final sentence is accurate enough to repeat.

Then run the bundled checker:

```bash
python3 <skill-directory>/scripts/check_output.py /absolute/path/to/explanation-YYYYMMDD.md
```

The checker verifies mechanical visual bounds, the dated filename, local
source-link resolution, and that every cited range (a `#L<start>-L<end>` anchor
or `file:<start>-<end>` link text) does not end before it starts and ends inside
the file. It cannot judge whether the explanation is clear or technically
correct; perform the reader check yourself.
