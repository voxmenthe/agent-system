---
name: dialectic
description: "Examine a genuine tension through two independent committed perspectives, checked evidence, and parent-led synthesis. Use when explicitly requested; do not use for a simple factual lookup or quick comparison."
disable-model-invocation: true
---

# Dialectic

Build the strongest grounded case for each position, then determine what the
disagreement actually turns on. Committed advocacy is a method of exploration,
not permission to invent facts or demand equal weight for unequal evidence.

## Frame and bound the inquiry

Use the user's stated decision, values, constraints, sources, and desired output
to define the tension. For a stress test, formulate the strongest relevant
alternative; for two supplied positions, sharpen both without replacing them.
Explain the framing briefly and proceed when it is clear. Ask only for missing
information that materially changes the inquiry, not a fixed interview sequence.

Prepare one neutral briefing for both perspectives: the question, constraints,
known facts and source locations, user-reported priorities, explicit assumptions,
and unresolved factual questions. Research consequential gaps within the user's
budget. Do not infer hidden personality types or substitute generic life advice
for the user's actual circumstances.

Use available native agents with independent initial contexts. Preserve the
user's provider, model, time, and cost choices; inspect the host's actual context
and effort options rather than assuming particular parameters. If independent
agents are unavailable or disallowed, report that limit. A parent-only comparison
may still help, but label it as such, not an independent-agent dialectic. Do not
automatically launch external workers; the separate `delegate` skill requires
its own explicit invocation.

## Give each perspective its own assignment

Launch two bounded reader/analyst assignments, each receiving the neutral
briefing and its own position, not the other's draft or the parent's preferred
answer. They may run sequentially if capacity requires it. Tell each agent:

- Make a fully committed, specific case for the assigned position, not a neutral
  comparison. Correct the obvious straw version of the disagreement.
- Explain the central premises, decisive evidence, and why the strongest
  opposing argument fails under those premises.
- Distinguish sourced facts, user testimony, inference, and unknowns. Name the
  load-bearing assumption and evidence that would defeat the argument.
- Return the argument, source locations, and unresolved checks within the given
  budget. Do not edit shared files, expand scope, or delegate again.

The parent owns the final artifact. Wait for both assignments to settle; retain
failures as failures, not empty arguments. Before replacement, ensure the prior
worker has stopped. On cancellation, stop owned workers and report partial work.

## Validate and synthesize in the parent

1. Read both arguments. Check that they differ in premises or mechanisms, not
   just conclusions. Identify missing perspectives without manufacturing
   disagreement or automatically commissioning another round.
2. Verify consequential factual claims against their cited sources. Agent
   confidence and agreement are not evidence. Resolve unsupported claims or
   exclude them from the conclusion; label remaining uncertainty.
3. Analyze internal tensions in each position, the precise collision between
   them, shared assumptions, and any specific limitation the evidence exposes.
   Separate factual disagreement from different goals, values, or constraints.
4. Form the conclusion yourself. Preserve supported insights and test proposed
   connections against concrete cases. A new framing is useful when supported;
   a well-supported choice, conditional decision, or unresolved tension is also
   a valid result. Do not force novelty or agreement.
5. Check the conclusion against each side's strongest objection and ask what
   would overturn it. When useful within the existing budget, return it to the
   original agents for focused critique. Their assent does not establish truth.
   Incorporate supported corrections without an extra approval ritual.

Return the two positions, checked evidence, contradiction analysis, conclusion,
what changed in understanding, and the next decision or discriminating check.
For a requested file, keep this trace in one Markdown artifact unless the user
needs separate outputs. State skipped validation and unresolved claims. Stop
when the requested inquiry is answered or its budget is reached; further rounds
are not a default obligation.
