# Use visual evidence for a specific visual claim

Use this when real rendering matters: clipping, overlap, missing content,
responsive behavior or agreement with an approved design. Begin with the
intended result. An older screenshot is historical evidence, not automatically
the correct target, and a visual check is not a functional acceptance test.

## Render the real thing

Read the component's props/data contract and actual styling. Select stress
cases that can reach it: long values, empty/minimal content, loading/error
states, large counts, or narrow containers. Drop irrelevant dimensions. Import
the actual component and its style dependencies rather than rebuilding a
lookalike. Fixture data belongs at that component's input or external network
boundary; do not replace the behavior whose integration you claim to verify.

Fixed-width component scenarios expose local layout. A real viewport/page
case checks media queries and surrounding layout. Use both when both claims
matter; a narrow container in a wide viewport is not a mobile viewport.
Label component fixtures separately from real-backend/browser journeys.

For a generated HTML report or explainer, run
`python3 <skill-directory>/scripts/html_preflight.py FILE` before rendering:
it reports a file that is not whole and simple SVG shapes painted past their
viewBox. It lists what it could not check (paths, transforms, CSS-positioned
elements) instead of passing it, and it does not replace rendering.

When the report promises figures, add `--expect-images N` with the number it
should hold. The preflight then prints a one-line media inventory per file and
reports a `DEFECT` when a file has fewer than N images, so a chart that failed
to build or a screenshot that was never embedded cannot hide inside an
otherwise whole document. It counts every `<img>` and `<canvas>` and each
outermost `<svg>` that is not decorative; an `<svg>` with `aria-hidden="true"`
or the role `presentation` or `none` is decorative, like an icon. The count
shows that the markup is present, not that a figure rendered or shows the
right content.

## Make captures comparable and truthful

Align viewport, device scale, fonts, data, UI state and animation/time where
relevant. Wait for the intended loaded state and fonts before capturing. Keep
the full relevant view and use a crop only to inspect a named feature; retain
the surrounding boundary where clipping or spill could hide.

Inspect capture integrity before judging the component. A blank capture,
repeated stitched tile, wrong viewport or stale frame is an evidence failure.
Prefer a truthful viewport capture when full-page stitching is unreliable,
and state what is outside that capture. Do not hide content, blur it or shrink
the crop to improve a comparison score.

## Check landmarks, not a universal quality score

For a layout claim, combine visible inspection with relevant geometry: a
control stays inside its panel, text does not cross a neighboring control, or
the page has no unintended horizontal overflow. Preserve expected content
assertions too; an empty page can trivially satisfy an overflow check.

Use image differences, crops, edge maps or contrast measurements only when
they help locate the claimed defect. Numeric resemblance does not select the
correct design. An intentionally sparse/empty-state component can be valid;
low edge density is not grounds to reject it. Structural diagram checks prove
only their declared syntax/layout rules, not semantic truth.

Exercise the instrument with a known rendered defect and a protected valid
edge case. Retain aligned before/after images, the detecting observation and
the exact repair. A controlled fixture mutation establishes sensitivity, not
a newly discovered product bug. Re-render after a relevant fix and keep
uncertain visual judgments explicit instead of converting them to a pass.

Source ideas: Jakub Krehel's real-component break scenarios and dzhng's
target-aware screenshot comparison and known-answer fixtures. No inherited
palette, numeric threshold set, project dependency layout or one-look limit.
