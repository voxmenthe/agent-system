# Figure Gallery: Script-Grounded Examples Beyond the Core Tutorials

Each section names the upstream script it distills (see [demos.md](demos.md)
for links), states when to reuse the idea, and shows the load-bearing lines.
Implement shared behavior through the [api.md](api.md) helpers where they fit;
copy script-specific mechanics only for the chart type at hand.

---

## 1) Stacked composition bars with hatch overlays and in-bar values

**Source:** `figure_Brainteaser/plot_brute_force.py` → `figures/brute_force.png`.

**Use when:** each bar is a composition (shares summing to 1) and both the
method color and the subtype must survive grayscale print.

**Mechanics:**

- One subplot per prompt in a `GridSpec(2, 5)` canvas (`figsize=(52, 12)`); the
  last cell of each row is a legend-only panel.
- Methods carry the fill color; subtypes carry the hatch:
  `hatch_styles = ['/', '\\', '', 'x']`, stacked with `bottom=np.cumsum(...)`.
- Black edges everywhere: `edgecolor='black', linewidth=2`.
- The first subtype value is printed inside the bar in gold with a black
  stroke so it reads on any fill:

```python
for bar in bars:
    ax.text(bar.get_x() + bar.get_width() / 2, height / 2, f'{height:.3f}',
            ha='center', va='center', color='#FFD700', fontsize=20,
            path_effects=[path_effects.Stroke(linewidth=4, foreground='black'),
                          path_effects.Normal()])
```

- Two legend-only panels: one for methods (color), one for subtypes (hatch on
  white fill). Build a proxy bar per entry, collect handles, remove the proxy
  bars, then `ax.legend(...); ax.set_axis_off()`.

---

## 2) Horizontal ablation bars with an alpha completeness gradient

**Source:** `figure_ImmunoStruct/plot_bars.py` → `figures/bars_ablation_IEDB.png`.

**Use when:** an ablation removes components stepwise and the figure should
read "fuller method, stronger color."

**Mechanics:**

- `ax.barh` with one shared hue at stepped alpha:
  `color=[(0.215686, 0.458824, 0.729412, a) for a in np.linspace(0.2, 1.0, 12)]`.
- Symmetric error bars: `xerr=std, ecolor='k', capsize=5`.
- Tight per-metric `xlim` plus explicit ticks so neighboring panels stay
  comparable; y-tick labels only on the first panel, decoded from binary
  ablation codes into `A + B` strings.

---

## 3) Grouped-by-dataset bars with scientific-notation axes

**Source:** `figure_Cflows/plot_comparison_Trajectory.py` →
`figures/fig2_comparison_Trajectory.png` (also `.pdf`).

**Use when:** the same methods repeat across datasets inside each metric
panel and values are small.

**Mechanics:**

- Offset arithmetic places dataset groups side by side:
  `np.arange(num_methods) + dataset_idx * (num_methods + 1)`, with group
  centers precomputed into `xtick_list`.
- `ax.ticklabel_format(axis='y', style='sci', scilimits=(0, 0))` for RMSE/EMD
  scales; per-panel `set_ylabel` plus a shared `Dataset` xlabel.
- Legend collected once (`if dataset_idx == 0`) into a dedicated
  legend-only fourth panel; dual export to `.png` and `.pdf`.

---

## 4) Cumulative trends with event annotations and hatched fills

**Source:** `figure_ophthal_review/plot_trend.py` → `figures/trend_by_month.png`.

**Use when:** showing cumulative publication (or adoption) counts with
release events marked on the curve.

**Mechanics:**

- Plot `np.cumsum(monthly)` as both `fill_between` area and `lw=3` line; the
  second panel adds `hatch='///'` / `'\\\\\\'` with `edgecolor='black'` so the
  two areas differ in print, plus a white-edge overdraw pass that erases the
  fill border.
- `mark_events` annotates release labels with `arrowstyle='-|>'` arrows;
  trailing `*` characters in a label raise its text offset instead of
  printing.
- Sparse time ticks (`time_arr[2::6]`), per-panel `ylim`, and stacked
  two-row layout (`figsize=(14, 8)`).

---

## 5) Annotated count heatmaps with `n=` marginal labels

**Source:** `figure_ophthal_review/plot_composition.py` →
`figures/composition_heatmap.png`.

**Use when:** a matrix of counts needs exact values plus row/column totals.

**Mechanics:**

- `sns.heatmap(value_arr, annot=True, fmt='d', cmap='Reds', linewidths=1,
  linecolor='white')` with an explicit `vmin/vmax` and colorbar ticks.
- Row and column labels are augmented with totals:
  `subcategory + '\n' + rf'($n={row_sum}$)'`, so marginals travel with the
  axis instead of a separate table.

---

## 6) Post-training curves with alpha-gradient segments

**Source:** `figure_VIGIL/plot_posttraining.py` →
`figures/comparison_posttraining.png`.

**Use when:** later training steps deserve more visual weight than early
ones, against a shared starting baseline.

**Mechanics:**

- A dashed `axhline` marks the shared step-0 baseline; each method is a
  `LineCollection` of segments whose alpha ramps `np.linspace(0.3, 0.9)`,
  with `marker='o'` points overlaid and the raw line hidden (`linewidth=0`).
- Custom `Line2D` handles give the legend a line-plus-marker per method
  beside the `SFT only` baseline entry.

---

## 7) Radar comparisons with per-benchmark normalization

**Source:** `figure_VIGIL/plot_comparison_radar.py` →
`figures/comparison_radar.png`.

**Use when:** one polygon per method spans subtasks whose raw scales differ
(POPE-style 75-91 next to MathVista-style 30-61).

**Mechanics:**

- Each benchmark declares its own `radii` list; every spoke value is
  normalized by its benchmark range into a shared display band (45-90), with
  NaN filled by the row mean.
- Contour polygons are drawn per tick level across spokes; per-spoke numeric
  labels skip the innermost tick to avoid clutter; subtask labels sit outside
  the rim in monospace; export uses `bbox_inches='tight'`.

---

## 8) Concept schematics: distribution panel plus KDE manifold

**Source:** `figure_VIGIL/plot_concept.py` → `figures/concept.png`.

**Use when:** a concept figure must pair a 1D probabilistic story with a 2D
geometric story.

**Mechanics:**

- Left: Gaussian curves with `fill_between(..., alpha=0.12)`, a dotted
  `vlines` marker, and a double-headed `<->` annotate span labeled `VIG`.
- Right: KDE (`gaussian_kde`) contour shells over faint scatter, red star
  markers for aligned states, a dashed gray "shortcut" ridge beside a solid
  blue "ours" trajectory, and white-bbox text labels so type never fights
  the contours.

---

## 9) Sphere, geodesic, and 3D repel illustrations

**Source:** `figure_Dispersion/plot_illustration.py` →
`figures/illustration.png`.

**Use when:** the figure explains embedding geometry (dispersion,
decorrelation, orthogonalization) rather than reporting numbers.

**Mechanics:**

- Shaded-sphere disks are `imshow` intensity fields from a normal-dot-light
  computation (`ambient + 0.9 * intensity`), not 3D surfaces.
- Geodesics use SLERP arcs between lifted points with
  `FancyArrowPatch` heads; radial guides to the origin are dashed black.
- The 3D repel panel hides panes and grid (`nice_axes`), draws pairwise
  dispersion arrows in red and norm-regularization arrows in violet via an
  `Arrow3D` helper, and labels each arrow family with a `Line2D` marker-only
  legend handle.
- `text.usetex = True` with `font.family = 'sans-serif'` is used here; keep
  that pairing only when LaTeX is installed (see [api.md](api.md)).

---

## Related files

- [SKILL.md](../SKILL.md) — When to use this skill
- [api.md](api.md) — Palette, helpers, validation, export
- [tutorials.md](tutorials.md) — Core grouped-bar, trend, and heatmap builds
- [demos.md](demos.md) — Upstream projects these examples come from
- [common-patterns.md](common-patterns.md) — Layout and print-safe details
- [design-theory.md](design-theory.md) — Why the style choices exist
