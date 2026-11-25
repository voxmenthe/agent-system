# Attribution

Adapted from Lauren Tan's `create-formal-verification-skill` in
[Cursor pstack](https://github.com/cursor/plugins/tree/9580c23696ac8d7abed0c166f2f9918800afb819/pstack),
revision `9580c23696ac8d7abed0c166f2f9918800afb819`.

Copyright (c) 2026 Lauren Tan. The upstream [MIT license](LICENSE) is retained.

This owner-directed adaptation is explicit-only. It adds a TLC runner with
drift coverage and a sync-commit guard (`scripts/check`), a fixed layout for
models, views, mutations and findings, a scratch-worktree proof, and the
modelling lessons from its first use (`references/tla-lessons.md`). It names
the vendored `statechart` skill, with a `view.mjs` beside each model, for
showing a person a counterexample; the runner still prints each counterexample
one step per line. It adapts pstack's `/maintain-formal-verification-skill`
(revision `4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`) as
`references/maintain.md`, made concrete for the runner.
