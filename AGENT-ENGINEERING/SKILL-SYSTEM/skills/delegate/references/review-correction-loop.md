# Review-correction loop

Use this when the user authorizes repeated review → fix → re-review rounds
over one change, plan or document, with reviewers they name (for example
`cam` or `ccfx`). A single review needs only the skill's Integrate and verify
section.

## Before the first round

- **Roster:** the reviewers the user named, and only those. A default
  reviewer count never overrides a named roster.
- **Budget:** the rounds the user authorized. If they named none, use three
  and say so.
- **Target identity:** what each round reviews, recorded before it starts.
  For a commit range, the base and head object IDs. For a single draft,
  `git hash-object <file>`. For an uncommitted change across files,
  `~/.agents/skills/delegate/scripts/review-identity <base> <path>...`: it
  covers every in-scope file, tracked or untracked, with deletions and modes,
  and exits non-zero without printing when it cannot. A `git diff` alone
  misses new files. Nothing needs committing just to get an identity.
- **Configuration:** one brief, one base and one diff command for every
  round, so rounds are comparable.

## Keep one finding ledger

Keep it where the task keeps its notes, one entry per finding:

```text
F<n> | source: <launcher> or owner | class, priority | location | claim
     | disposition: open | fixed in <identity> | disagreed: <evidence> | declined: <reason>
     | remaining disagreement
```

- A finding keeps its ID across rounds. A later report of the same defect,
  from any reviewer or the owner, joins the existing entry and adds its
  source.
- An owner-authored finding or correction is never dropped when findings are
  merged. Keep its source, identity and disposition; it need not be verbatim.
  Reviewer agreement does not outrank it.
- Use `diff-review`'s classes (`Change`, `Verify`, `Consider`) and its
  consequence-based priority. Rare is not minor: a rare path to data loss, a
  security exposure or a concurrency failure keeps its priority.

## Run each round

1. Record the target identity. Do not edit the target while a round runs.
2. Send the same brief, the ledger, and the change since the previous
   round's identity. Ask each reviewer to mark every open ID `resolved` or
   `still open: <reason>`, and to raise new findings in the changed code, or
   elsewhere only when an open finding requires it.
3. Check each finding against the code or source yourself. Then fix it with
   the smallest change, disagree with evidence, or decline with a reason.
   Record the identity a fix landed in.
4. Run the covering checks before the next round.

## A sign-off covers one identity

An approval covers exactly the identity that reviewer reviewed. Any later
edit, including a fix for another reviewer's finding, makes a new identity
that the old approval does not cover: send the delta for review, or report
the approval as covering the earlier identity only.

## Stop

- **Agreement:** each reviewer's latest verdict approves the current
  identity, and no `Change` finding is open.
- **No progress:** a round fixes nothing and adds no new evidence, or a
  finding stays disputed after two exchanges. Show both sides in two or three
  lines each; the user decides.
- **Budget end is not approval.** Open findings stay open in the report,
  with their sources.

Report the rounds run, the roster, each round's identity, findings by
disposition and source, what stays open or disputed, and each reviewer's
outcome (`folded`, `not-run`, `failed` or `no-usable-output`).
