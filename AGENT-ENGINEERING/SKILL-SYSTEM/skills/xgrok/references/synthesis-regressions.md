# XGrok synthesis regression fixtures

Use these fixtures when changing xgrok's parent-synthesis guidance or checking
whether a large macro artifact still matches the requested product. They are
comparative examples, not golden templates.

## Primary forward-test prompt

```text
Macro and sentiment summary for key equities over the past 12 hours.
```

This normally calls for a participant-native product: current tape, the few
high-signal practitioner observations, material disagreements, and any
conversation or revision that changes the read. Verification may qualify
claims, but it should not silently replace that product with a generic research
memo or risk framework.

The output passes without any prescribed number of voices, camps, sections, or
conversation rows. A one-sided tape, one dominant conversation, or a thin
sample should remain one-sided, singular, or thin.

## Fixture A - participant-native event post-mortem

Source:
`X-RESULTS/MACRO/2026-07-29_2227Z_fomc-hold-postmortem-outlook.md`

Useful properties:

- identifies the live market tape and the professional disagreement early;
- attributes participant observations and revisions throughout the analysis;
- uses official checks to bound X claims without erasing the participant map;
- lets the dispute's actual shape organize the report.

Do not copy its section order or force a two-camp split. Preserve the property
that a reader can tell what market participants observed, where they differed,
and what the synthesizing model concluded.

## Fixture B - hybrid analysis with displacement risk

Source:
`X-RESULTS/MACRO/2026-07-30_2231Z_degrossing-risk-reentry.md`

Useful properties:

- contains careful evidence ceilings, competing-thesis analysis, and
  falsifiable decision logic;
- distinguishes observed facts from missing private positioning and flow data.

Regression risk:

- an analyst-owned state machine and risk-governance frame can become the
  product even when the user primarily asked for participant sentiment,
  observations, and key conversations;
- material X voices can be relegated to a late evidence ledger instead of
  remaining a visible analytical input.

For a hybrid request, retain the useful adjudication while keeping material
participant observations and conversation changes distinguishable from parent
judgment. For an explicit research-adjudication request, a fact-led structure
may be correct; the fixture is not a ban on decision memos.

## Qualitative acceptance check

Judge the result against the user's request, not against a section checklist:

1. Is the selected orientation consistent with the requested product?
2. If X is the subject or a major input, did its material native signal survive
   synthesis?
3. Can the reader distinguish participant statements from verification and
   parent judgment?
4. Did broad fanout preserve an integrated read and enough budget for the
   conversations that mattered?
5. Were camps, conversations, and source counts allowed to follow the evidence
   rather than a quota?
6. Did the result honor the requested granularity, or did the available template
   and receipt set inflate a summary into an archive-style report?
7. For a concise product, was the answer recomposed from the load-bearing
   evidence, or did the retrieval packet remain visible as a coverage inventory?
8. Was each important claim rendered once at its most useful level, or repeated
   across observations, disagreement tables, and receipts without information
   gain?
