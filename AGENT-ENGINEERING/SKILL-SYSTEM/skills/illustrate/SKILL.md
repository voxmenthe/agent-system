---
name: illustrate
disable-model-invocation: true
description: "User-invoked English Xiaohei article-illustration skill. Use when the user explicitly invokes illustrate. Do not use unless the user names this skill, and do not use for commercial illustration, PPT infographics, cute cartoons, code visuals, Mermaid, HTML explainers, or illustrate-cn."
---

# Ian Xiaohei Absurd Article Illustrations

Run only when the user explicitly invoked this skill by name or slash command. Nearby talk about illustrations, drawings, or figures is not invocation.

This is the English workflow. The original Chinese skill is `$illustrate-cn`.

## Core job

Design and generate 16:9 landscape article illustrations. The goal is not commercial illustration, PPT infographics, or cute cartoons. Turn a key judgment, process, structure, state, or metaphor from the article into a clean, absurd, inventive, readable-but-not-instructional hand-drawn explainer.

The default visual IP is Xiaohei (小黑): solid black, white-dot eyes, thin legs, blank expression, seriously doing one absurd-but-coherent job. Xiaohei must perform the picture's core action, not stand nearby as decoration.

Handwritten labels follow the source article: short English (1-3 words) for English text, unless the user specifies otherwise.

## Read these references as needed

Do not load every file into context at once:

- `references/style-dna.md`: style DNA, color, type, taboos.
- `references/xiaohei-ip.md`: Xiaohei's look, temperament, action library, and taboos.
- `references/composition-patterns.md`: structure types, original-metaphor method, anti-copy rules.
- `references/prompt-template.md`: single-image generation template.
- `references/qa-checklist.md`: post-generation checks and iteration.
- `assets/examples/`: infrequent visual calibration only. Do not copy their compositions, objects, or labels.

## Workflow

### 1. Digest the article

Read the user's prose, links, Notion pages, Markdown, or screenshot text. Extract:

- the core claim
- which paragraphs are cognitive turning points
- which content is worth drawing
- which parts should stay text-only

Do not illustrate evenly. Prefer cognitive anchors: a core judgment, two breakpoints, an input-output loop, a split, a before/after, one-fish-many-uses, a handoff path, common pits, or a role-state change.

### 2. Publish a shot list first

If the user only asks to analyze where images belong, output a shot list. For each image state:

- after which paragraph it goes
- theme
- core meaning
- structure type
- what Xiaohei is doing
- suggested elements
- suggested handwritten labels

Default 4-8 images. Short pieces: 1-3. Even long essays should rarely exceed 9. Enough is enough; do not turn the article into a picture book.

### 3. Generate one image at a time

If the user explicitly asks to generate / output / make images, do not wait for confirmation. Call the host image tool once per image. Never pack several pictures into one generation.

Host tools:

- Grok Build: `image_gen` with `aspect_ratio` `16:9`. Prefer `image_edit` to remove titles or fix letters.
- Codex: built-in `imagegen`. Use an image editor when available; otherwise regenerate per the QA checklist.

Each image explains one core structure. Every prompt must include:

- 16:9 landscape article illustration
- pure white background
- black hand-drawn line work
- sparse red/orange/blue handwritten labels
- lots of empty space
- Xiaohei as the core action subject
- no PPT, commercial illustration, cute/childish look, complex architecture, or top-left type titles

Do not copy prior cases. Examples only calibrate line density and how Xiaohei participates. Do not reuse compositions such as "conveyor two breakpoints / Xiaohei pulling a cable / material-fish / stamp toolbox / common-pits path" unless the user asks to recreate a specific image. Invent a new strange-but-coherent metaphor from this article.

### 4. Check and iterate

After generation, check `references/qa-checklist.md`. Prefer regenerate or local edit if:

- Xiaohei is only decoration
- the frame is too full
- it looks like a flowchart or PPT
- labels are too many or badly misspelled
- a top-left title such as "Common pits / flowchart / system architecture" appears
- the drawing is too cute, childish, or rigid
- the background is not clean white

### 5. Save delivery

If the user is in a workspace, copy finals to:

```text
assets/<article-slug>-illustrations/
```

Name in order:

```text
01-topic-name.png
02-topic-name.png
```

Keep original generated files. Do not overwrite existing assets unless the user asks to replace them.

## Delivery voice

Strategy output before generation should be short and exact. After generation, report:

- how many images
- what each is for
- save paths
- which images are solid, which are optional

Do not lecture about style theory; let the pictures talk.
