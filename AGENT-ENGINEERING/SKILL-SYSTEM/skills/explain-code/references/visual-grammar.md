# Visual grammar for code diagrams

Read this before drawing any figure in either mode. Each figure answers one question the reader has. Pick its form from what the code does, keep it inside the budget, and check it like prose.

## Diagram nodes and edges are claims too

Every box, arrow, label, import, call, and transition asserts something about the code. Check each one against inspected source the way you check a sentence; delete it, or mark the figure illustrative, when the code does not show it. A box labeled only "Cache" or an unlabeled arrow gives the reader nothing to check: name the real identifier and the message, value, or event that moves.

## Choose by behavior, then by layout

When behavior, state, enforcement, or risk carries the explanation, start from the matching pattern and lay it out in the nearest ordinary form. Use one primary pattern per figure; split overview and detail rather than combining two.

| The reader must understand | Pattern and required parts | Layout |
|---|---|---|
| many producers contending for one constrained service | **Fan-in queue:** distinct sources, a queue with a visible slot count, capacity in units (`8/hour`), admitted and deferred outcomes | data flow |
| the same questions asked at every stage | **Stage × slot grid:** fixed slot order in every stage, explicit empty cells | process |
| loose input becoming a durable record | **Input → artifact:** a source excerpt, one named transformation, fields with provenance links, visible unknowns | data flow |
| why two similar requests got different outcomes | **Paired policy traces:** the same ordered rules on both, `PASS`/`FAIL`/`SKIPPED`/`NOT REACHED` in words, one labeled first divergence | flowchart |
| which routes cross a trust boundary | **Paved road:** permitted ingress, blocked routes that stop visibly at the boundary, one privileged gate | architecture |
| which controls apply where | **Control catalog:** controls grouped by enforcement surface, with actor and timing | layer stack |
| how defenses reduce risk and what remains | **Compensating layers:** each layer's mitigation and what escapes it, ending in a stated residual risk | layer stack |
| what a system is made of, each part citable | **Block decomposition:** a stable ID per block, noun-phrase names, tree connectors only | tree |
| one subject moving through phases, waits, retries, and cancellation | **Lifecycle phase map:** a primary rail, a separate interruption/recovery band, distinct cancel and fail terminals | state machine |

When no pattern fits, use a plain component map, pipeline, sequence, state diagram, or table. Before drawing a state machine, find the strongest proof the mode reference describes.

## Budgets

- At most **9 primary nodes**, **12 arrows**, and **2 accented focal elements** per figure. Over budget, split into an overview and a detail figure; never shrink text to fit.
- At most 5 nodes across a row and 5 participants in a sequence diagram, so the figure fits the text column without page scrolling.
- Use a sequence diagram only for the order of messages between participants, never for static structure such as modules, types, states, or schema.
- In Mermaid, lay flowcharts out `flowchart TD` and stack before/after or package subgraphs vertically by linking them with `~~~`, never side by side. Syntax traps are in [mermaid-authoring.md](mermaid-authoring.md).
- Mark added, removed, and future elements with text, stroke weight, or dash pattern as well as color.

## Build up mechanisms with three or more moving parts

Draw a short series instead of one crowded figure. Each step redraws the previous one with the same geometry and adds one part: A to B, then C, then the return edge. Two or three steps usually suffice. One all-at-once figure saved for the end is a reference, not an explanation.

## Look at it at real size, at most twice

After `html_preflight.py` passes, open the page in a browser at 1× scale, at desktop and narrow-phone widths. Look for clipped or overlapping text; a label detached from its connector; a connector crossing a box it does not attach to or ending in empty space; stacked or converging connectors; uneven gaps; a dense cluster beside an empty band; content cut at the viewBox edge; text too small to read. Inspect a tall or dense figure in viewport-sized slices, not one zoomed-out capture. Check the console for CSP and script errors.

Fix by restructuring before nudging coordinates: change direction, regroup, shorten labels, merge parallel edges. Re-render at most twice, then report any defect that remains. With no browser available, report "preflight passed; not visually inspected".
