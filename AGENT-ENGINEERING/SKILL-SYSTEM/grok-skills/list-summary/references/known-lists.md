# Known lists for /list-summary

Personal list registry. Prefer exact numeric ids. Aliases are case-insensitive
match tokens (substring OK when unambiguous).

## Default list

When the user runs bare `/list-summary` or "my list" without naming one, use:

| Field | Value |
|-------|-------|
| Display name | Interp and Alignment |
| List id | `2034096409167991117` |
| URL | https://x.com/i/lists/2034096409167991117 |

Change this default only if the user asks.

## Registry

| Display name | List id | Aliases |
|--------------|---------|---------|
| Interp and Alignment | `2034096409167991117` | interp, interp and alignment, interp & alignment, alignment list, mech interp list, interpretability |
| llm coding + ai hacks | `1649636502786433025` | llm coding, llm coding + ai hacks, llm coding and ai hacks, ai hacks, coding hacks list, llm coding list |

## Notes

- Operator form: `list:2034096409167991117` (no spaces).
- List membership is enforced by the X search operator, not by hardcoding handles.
- If a list id stops returning posts, note access/privacy/empty in Gaps; do not
  invent members from memory.
- To add a list: append a row with display name, numeric id, and aliases. Set
  **Default list** only on explicit user request.
