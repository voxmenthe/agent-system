# Attribution

Vendored from Lauren Tan's `statechart` skill in
[Cursor pstack](https://github.com/cursor/plugins/tree/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/statechart),
revision `4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`.

Copyright (c) 2026 Lauren Tan. The upstream [MIT license](LICENSE) is retained.

Every file under `scripts/` except `run` and `package.json` is byte-identical to upstream, and so is
`references/render.md`, so a re-sync is a re-copy. Local changes:

- `scripts/test/` (about 3.6 MB of fixtures and tests) is not vendored, and `package.json` keeps only `name`,
  `private` and `"type": "module"`.
- `scripts/run` (new) runs `scripts/statechart` offline on the pinned `tla2tools.jar` 1.7.4 that the
  formal-verification runner caches, checking its sha256 and finding Java, instead of upstream's mise install.
- `SKILL.md`: explicit-only wording; the run section uses `scripts/run` and a new `--out` folder outside the repo
  instead of a scratch working folder; a new section, "On a verification target", says which configs to chart and
  where the view lives, and points diagrams of code without a model to the explanation skills.
