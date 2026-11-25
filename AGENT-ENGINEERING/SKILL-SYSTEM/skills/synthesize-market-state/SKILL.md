---
name: synthesize-market-state
description: Use when explicitly invoked as `$synthesize-market-state` to maintain a persistent source-linked market-state ledger and produce a recurring macro/equity synthesis. Do not use automatically for ordinary market questions, news summaries, or one-off ticker research.
disable-model-invocation: true
---

# Synthesize Market State

Maintain continuity without allowing the previous causal map to constrain
discovery. Coordinate broad factual research, X-native participant retrieval,
mechanism-tested synthesis, an append-only report, and one serialized update to
the durable state ledger.

## Non-negotiable boundaries

- Treat `X-RESULTS/INTEGRATED/CURRENT-MARKET-STATE.md` as a fallible prior, not a
  search whitelist, source of truth, or list of required topics.
- Begin factual discovery without a fixed domain taxonomy. War, global economic
  policy, domestic politics/economic policy, national security, regulation,
  technology, industry, health, and climate are examples only. The important
  development may come from somewhere not anticipated.
- Keep factual significance, market transmission, participant attention, and
  actual market pricing separate. Market silence never decides factual
  relevance.
- Promote a cross-factor connection only when the factors share a real variable
  or bottleneck. News proximity is not causality.
- Keep timestamped reports append-only. The coordinating agent is the only
  writer of the current-state file; retrieval workers never write or archive.
- Treat the state edit as single-writer work. Listing comparisons detect many
  overlaps but are not a lock and do not authorize simultaneous coordinators.
- Do not turn the state ledger into a news feed, scoring system, confidence-grade
  table, or trade recommendation.

## Step 0 - Commit the comparison

1. Commit one exact evidence window and Pacific cutoff before retrieval.
2. List the integrated reports by timestamp in the filename and read the most
   recent relevant reports. Do not use filesystem modification time as market
   chronology. Capture the exact filename listing for the later concurrency
   check.
3. Read the current-state file completely. Record its evidence cutoff, regime
   anchor, and stable factor IDs before dispatching any worker.
4. Compare against both the immediately prior report and the deliberate regime
   anchor. Do not silently roll the anchor forward.
5. If the state file does not exist, derive a provisional anchor and initial
   factor set from the user-specified source reports. State the source boundary
   explicitly and do not fill gaps from memory.

## Step 1 - Build the factual agenda

Use the `$wsj` skill for authenticated WSJ research and primary sources when a
load-bearing fact needs stronger support. Complete four distinct operations:

1. **Surface scan:** inspect the homepage and Latest Headlines without topic
   keywords or section restrictions.
2. **Active-assumption scan:** seek developments that confirm, weaken,
   invalidate, or change the horizon of active state factors, reaction
   functions, incentives, or constraints.
3. **Outside-model scan:** seek consequential straight news absent from both the
   state ledger and recent reports.
4. **Targeted follow-up:** investigate promoted candidates with their native
   actors, institutions, events, and vocabulary.

At least one pass must avoid market, price, security, investor, and prior-theme
terms. At least one pass must ask what changes the causal map even if markets
have not noticed it. Rewording the same expected theme does not create a second
blind pass.

Apply transmission questions only after broad reading. Ask whether a candidate
changes the level, probability, timing, duration, or distribution of growth or
cash flows; inflation, supply, or productive capacity; a policy or institutional
reaction function; capital availability, financing demand, or discount rates;
legal or institutional constraints; liquidity, volatility, or market structure;
or an assumption supporting an active theme. These are gates, not search quotas.

## Step 2 - Promote factors without laundering uncertainty

For each serious candidate, record:

- a stable factor ID;
- a neutral current-state statement;
- basis: `observed fact`, `supported inference`, or `unresolved scenario`;
- change versus the prior report and versus the regime anchor;
- horizon and possible transmission channels;
- participant attention, participant interpretation, action, and actual pricing
  as separate fields;
- source links; and
- a concrete invalidator or next test.

Promote a candidate into durable state only when it is persistent, changes a
load-bearing assumption or reaction function, or materially changes another
active factor's level, probability, timing, duration, or distribution. A
material one-off can lead the timestamped report without becoming a state row.

## Step 3 - Retrieve participant uptake and transmission

Use `$xgrok` to send bounded evidence briefs to Grok `/macro`. Supply the exact
common window, the factual anchor and source, its native actors and vocabulary,
the relevant state slice, and the ambiguity to test. Request these fields:

`agenda anchor | reporting receipt | participant uptake | transmission channel | horizon | interaction candidate | counterevidence`

Ask for four role-separated lanes: reporting receipt on X, participant
absorption, market transmission, and counterchannel/disconfirmation. Grok does
not establish the parent-supplied fact as market truth. It returns X evidence
and makes no archive or state write. Structure the uptake field with attention
(`present`, `partial`, or `not found`) and interpretation (`shared`, `disputed`,
`unclear`, or `not applicable`), with action and pricing separate.

Continue the ordinary participant-native macro/equity and sentiment retrieval
required by the governing market prompt. External anchors supplement rather
than replace open-ended X discovery.

## Step 4 - Build the causal reads

Build a private factor ledger and a small interaction ledger before drafting.
For every proposed interaction, write:

`development -> real variable or common bottleneck -> market transmission -> affected assets and horizon`

Classify the interaction as reinforcing, offsetting, or conditional. Test at
least one counterchannel. Return `no supported connection` when the common
variable is missing. Keep sourced fact, participant interpretation, coordinator
inference, and observed pricing visibly distinct in the working ledger.

Produce three linked reads:

- **Delta:** what information, belief, framing, conviction, or market expression
  changed since the prior report.
- **Temperature:** what participants now say easily, repeatedly, defensively,
  jokingly, reluctantly, or through changed action.
- **Regime:** which persistent conditions strengthened, weakened, changed
  horizon, or became more consequential through interaction since the anchor.

## Step 5 - Write the timestamped synthesis

Use `PROMPTS/markets-grok-main.md` as the authority for report shape, quote
selection, evidence roles, and equity coverage. Let a significant changed fact
or mechanism lead even when participant uptake is absent, but preserve the
participant-native character of the overall product. Label a quiet uptake
search rather than inventing a market reaction.

Write the completed report under `X-RESULTS/INTEGRATED/` with a Pacific timestamp.
Never overwrite an existing timestamped report; append `-2`, `-3`, and so on
when two reports would otherwise receive the same filename. Record the exact
output path for the concurrency check.

## Step 6 - Perform the single-writer state update

Only after the timestamped report is safely written:

1. Reread the entire current-state file and relist the latest integrated reports
   immediately before editing.
2. Compare the live listing with the Step 0 listing, excluding this run's exact
   output path. If any other report appeared during retrieval, read it
   completely. Reconstruct and merge its durable candidates, or stop before
   editing when they cannot be reconciled safely.
3. Compare the live evidence cutoff and factor rows with the state snapshot
   captured in Step 0. Do not edit while another coordinator is known to be
   updating the same state file.
4. Reread state and relist once more immediately before applying the edit. Merge
   by stable factor ID and latest evidence time. Preserve any newer row or
   source boundary. Add only independent changes that remain valid against the
   newer state.
5. If an overlapping run cannot be merged without guessing, leave the
   timestamped report intact and stop before replacing current state. Report the
   conflict explicitly.
6. Preserve the regime anchor unless the report explicitly demonstrates a
   structural reset and records why the old anchor no longer answers the
   comparison question.
7. After writing, reread state and relist reports. If a newer report appeared,
   flag pending reconciliation and do not perform a blind second overwrite.

Keep this state structure:

1. evidence cutoff, regime anchor, owner, and source-report boundary;
2. active factors with stable IDs, basis, prior and anchor deltas, horizon and
   channels, participant uptake, market expression, evidence, and invalidator;
3. load-bearing interactions with mechanism, relation, horizon, counterchannel,
   and evidence/inference boundary;
4. open assumptions and coverage gaps; and
5. retired or invalidated factors, retaining their IDs and reason.

## Final gate

Before handing off, verify that:

- all four factual-discovery operations were genuinely distinct;
- at least one discovery pass was outside the inherited model;
- no candidate was discarded merely because X or the market was quiet;
- every promoted interaction has a common variable, horizon, and counterchannel;
- fact, inference, scenario, participant uptake, and observed pricing remain
  distinguishable;
- the report is participant-native rather than a generic news digest; and
- the append-only report exists and the state update passed the reread-and-merge
  concurrency check.
