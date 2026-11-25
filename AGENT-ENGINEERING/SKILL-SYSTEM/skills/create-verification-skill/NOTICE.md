# Attribution

Adapted from Lauren Tan's `create-verification-skill` in
[Cursor pstack](https://github.com/cursor/plugins/tree/93b00b89ef425a9c1bac0d0b317dfc49c930ac99/pstack),
revision `93b00b89ef425a9c1bac0d0b317dfc49c930ac99`.

Copyright (c) 2026 Lauren Tan. The upstream [MIT license](LICENSE) is retained.

This owner-directed adaptation uses the target's verified discovery/runbook
convention, affected-surface coverage, one driver owner, and the existing
implementation/acceptance owners. It removes Cursor-only paths, compulsory
parallel source readers, whole-map sweeps, and publication from the leaf.

`scripts/html_preflight.py` adapts the document-completeness and viewBox
checks of `scripts/self_check.py` in
[diagram-design](https://github.com/cathrynlavery/diagram-design), revision
`d35ae86`. Copyright (c) 2025 Cathryn Lavery, MIT license. The adaptation
drops the diagram-specific accessibility, asset and motion contracts, widens
the paired-tag list to common report containers, and lists unmodeled SVG
geometry as not checked instead of skipping it.
