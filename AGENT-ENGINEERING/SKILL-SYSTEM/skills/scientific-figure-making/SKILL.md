---
name: scientific-figure-making
description: "Use only when the user explicitly invokes $scientific-figure-making to build publication-ready matplotlib figures for papers, slides, or reports with house style and vector export. Do not use for interactive web dashboards, exploratory-only plots, dominant 3D or GIS mapping, or Illustrator and Figma-first infographics."
disable-model-invocation: true
---

# Scientific Figure Making

Run only when the user explicitly invoked this skill by name or slash command. Nearby talk about plots, charts, or figures is not invocation.

## Core job

Produce publication-ready matplotlib figures for papers, slides, or reports: grouped or ablation bars, trend lines, heatmaps, radar comparisons, concept schematics, and multi-panel layouts, finished with the house style and print or vector export conventions.

This skill is not a second route beside `$illustrate`, `$show-me`, or `$explain-code`. Those cover Xiaohei article illustrations, quick visual explanations, and durable HTML guides. This skill covers matplotlib data plots with a publication target. Do not use it for Plotly, Altair, or Bokeh dashboards, seaborn or pandas exploratory plots with no publication target, or Illustrator and Figma-first infographic layout.

## Workflow

### 1. Confirm the brief

Before plotting, pin down what would change the figure: the comparison or message, panel count and layout, color roles for proposed versus baseline series, data shape, venue size hints, and output formats. When any of these are underspecified in a way that would change the figure, confirm with the user before finalizing.

### 2. Apply the house style first

Call `apply_publication_style` once before creating figures, using the `PALETTE` and `FigureStyle` contracts in [references/api.md](references/api.md) and the rationale in [references/design-theory.md](references/design-theory.md). In batch or headless runs, set a non-interactive backend before importing `pyplot` (for example `matplotlib.use("Agg")`).

### 3. Build with a pattern

Pick the closest match:

- Grouped bars, ablation bars, or stacked composition: [references/tutorials.md](references/tutorials.md) Tutorial 1, [references/common-patterns.md](references/common-patterns.md), and [references/figure-gallery.md](references/figure-gallery.md) sections 1-3.
- Trends, cumulative curves, or post-training panels with a shared legend: [references/tutorials.md](references/tutorials.md) Tutorial 2 and [references/figure-gallery.md](references/figure-gallery.md) sections 4 and 6.
- Heatmaps and matrices: [references/tutorials.md](references/tutorials.md) Tutorial 3 and [references/figure-gallery.md](references/figure-gallery.md) section 5.
- Radar, concept schematics, sphere illustrations, or anything else: [references/figure-gallery.md](references/figure-gallery.md) sections 7-9 with the canonical scripts in [references/demos.md](references/demos.md).

Keep semantic color roles stable across panels: blues for the proposed or key method, greens for improvements, reds for baselines or contrasts, neutrals for background. Use edges or hatching so categories survive grayscale print.

### 4. Export for publication

Save through `finalize_figure` to the user's path or a project `figures/` directory, normally as both `.png` and `.pdf` at `dpi=300` (`600` for dense bar panels). Parent directories are created as needed.

### 5. Verify before handing off

Reread the exported figure at its final size: exact values readable without a grid, legend fully visible and never covering data, y-limits tightened to the relevant range, tick labels legible, and no missing panel titles. Fix defects and re-export rather than describing them.

## Read references as needed

Do not load every file into context at once:

- `references/api.md`: palette, style, helper signatures, validation, export.
- `references/design-theory.md`: typography, color, layout, and export rationale.
- `references/common-patterns.md`: wide panels, legend-only axes, print-safe bars.
- `references/tutorials.md`: end-to-end grouped-bar, trend, and heatmap builds.
- `references/figure-gallery.md`: script-grounded examples beyond the three core tutorials.
- `references/demos.md`: canonical upstream `figure_*` projects and where each pattern lives.
