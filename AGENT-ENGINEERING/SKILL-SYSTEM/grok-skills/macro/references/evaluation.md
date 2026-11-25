# Participant-native equity evaluation

Use this protocol when changing the dual-role retrieval design or investigating
a regression in a combined macro/equity synthesis. It is not part of an
ordinary `/macro` run.

## Fixed historical fixture

Use the August 14, 2026 close window as the primary regression fixture:

- exact reader-facing bound: August 14, 2026, 10:45 a.m.-8:00 p.m. PDT
  (Grok-native query equivalent: `since:2026-08-14_10:45:00_PDT` through
  `until:2026-08-14_20:00:00_PDT`; API transport equivalent:
  `2026-08-14T17:45:00Z` through `2026-08-15T03:00:00Z`);
- comparison context: the relevant August 14 reports in
  `X-RESULTS/INTEGRATED/`;
- known name-coverage checks: AVGO, AMAT, WDAY, SNDK, and RDDT when each was
  material in the chosen prior/live-agenda map;
- known behavioral seams: breadth versus cap-weight, volatility complacency
  versus rates stress, first-person premium/hedge changes, and company reactions
  whose replies or throw-away language can change the interpretation.

Do not feed known quotable answers into the retrieval prompt. The named checks
test coverage, not rote reproduction.

## A/B setup

Run both arms with the same exact window, tool availability, core allowlists,
dynamic name map, and maximum retrieval budget.

### Arm A - core-only

- Use macro Tier A/B and equity EQ-A/EQ-B.
- Run the existing dynamic company and conversation lanes.
- Do not load the probationary sentiment panel or open texture harvests.

### Arm B - dual-role

- Keep every Arm A core lane.
- Add role-separated tape/action, company-conversation, review-before-use, and
  discovery/relay panel batches.
- Add one non-tech and one open texture harvest.
- Time-slice busy Latest lanes and build both ledgers.

Run each arm more than once when retrieval ranking is visibly unstable. Judge
the union of unique receipts separately from run-to-run ordering.

## Evidence packet checks

Check assets and field propagation, not exact prose wording:

1. Every retained item has author, timestamp, ID/URL, dependencies, signal
   type, evidence role, novelty/recurrence, independence, and paraphrase-loss
   treatment. Exact text is required when wording, action, or conversation is
   the signal; wording-immaterial facts may be terse summaries.
2. Core, sentiment-sample, review-before-use, and context-only items remain
   distinguishable through the final packet.
3. Each material fixture name is explicitly attempted in a core lane and, when
   Temperature is relevant, a texture/conversation lane. A failed attempt is
   recorded as such; a generic AI-capex post does not count.
4. First-person action preserves intention, order, claimed fill, holding, hedge,
   add, trim, exit, flat, watch-only, and horizon rather than collapsing these
   into generic positioning.
5. Selected conversations include the root/quoted post and additive replies or
   author continuations. A social/emotional node may survive when it changes
   the temperature read even if it adds no fact.
6. Relays, self-threads, and one conversation do not create independent
   recurrence.

## Comparative judgments

Compare the two arms on:

| Dimension | Better dual-role behavior |
|---|---|
| Key-name coverage | Material names receive actual company-level attempts rather than being inferred from index or AI-capex commentary |
| Temperature yield | More distinct, attributable mood/stance/action tells with clear paraphrase loss |
| Conversation value | Replies or quote dependencies materially sharpen or reverse the root-only interpretation |
| Source diversity | No one author, thread, or shared research input dominates the Temperature read |
| Claim hygiene | Panel/context posts never acquire core factual or consensus weight |
| Noise cost | Generic retail emotion, ticker spray, promotion, and hindsight remain excluded |
| Final compression | The parent can produce Bottom line, Delta, Tape temperature, and key-stock conversations without exposing a search catalog |

## Pass gate

The dual-role arm passes only when all of the following hold:

- it preserves the core arm's load-bearing facts and informed disagreements;
- it attempts each selected key name through the appropriate core and texture
  paths;
- it recovers at least one genuinely informative first-person action or
  conversational tell when the fixture contains one;
- no author exceeds the sentiment concentration gates, or the resulting claim
  is explicitly narrowed;
- every promoted item retains its evidence role through synthesis;
- delegated-worker mode stays within the default six-receipt/1,500-word packet
  budget (unless the parent's `Delegated budget:` line expands it) and creates
  no archive or full memo;
- the improvement comes from participant information, not simply more quotes
  or more posts.

If Arm B fails on noise while improving recall, tighten the current-post or
role gate before removing the dual-role boundary. If it adds no participant
information, inspect time slicing, dynamic-name coverage, and conversation
recovery before expanding the panel.
