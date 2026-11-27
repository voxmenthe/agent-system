# Attribution

Adapted from Lauren Tan's `maintain-verification-skill` in
[Cursor pstack](https://github.com/cursor/plugins/tree/93b00b89ef425a9c1bac0d0b317dfc49c930ac99/pstack),
revision `93b00b89ef425a9c1bac0d0b317dfc49c930ac99`.

Copyright (c) 2026 Lauren Tan. The upstream [MIT license](LICENSE) is retained.

This owner-directed adaptation uses the target's verified discovery/runbook
convention, affected-surface coverage, one driver owner, and the existing
implementation/acceptance owners. It removes Cursor-only paths, compulsory
parallel source readers, whole-map sweeps, and publication from the leaf. It
adds a handoff of formal model checks to `create-formal-verification-skill`,
a covered-file drift read, proportional escalation, and a quoted negative-case
re-check after each repair, after pstack's prove-it-works principle.
