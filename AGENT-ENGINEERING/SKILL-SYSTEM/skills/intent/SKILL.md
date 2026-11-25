---
name: intent
description: Run an explicitly invoked, high-leverage interview that uncovers the user's underlying intent, intent hierarchy, and final vision, then distills them into a compact decision lens. Use when the user invokes $intent to clarify what they are really trying to achieve, align on the why or north star before consequential decisions, separate a proposed solution from the outcome it should cause, or resolve competing goals without yet eliciting requirements.
disable-model-invocation: true
---

# Intent

Discover the smallest set of intent truths that makes later choices predictable.

**Do not maximize the number of questions answered; minimize the consequential intent left ambiguous.**

Stay upstream of requirements. Clarify the desired change, the reasons it matters, and the values that should govern tradeoffs. Do not turn the session into feature discovery, specification, planning, or implementation. Treat the user's proposed artifact or approach as a possible means, not automatically as the end.

## Start from evidence

Read the conversation and any supplied context before asking anything. Research discoverable facts yourself; ask the user only for their perspective, aspirations, priorities, and judgments.

When genuine ambiguity exists, build multiple evidence-backed readings of the user's intent; otherwise keep the single supported reading and do not manufacture alternatives. Maintain a private, revisable model of:

- the means currently proposed;
- the governing perspective, decision rights, or hard constraints when stakeholders differ, and the situation in which they matter;
- the concrete change they want in the world;
- what that change enables or ultimately serves;
- the relative priority of multiple intents;
- values or qualities that must survive tradeoffs;
- which parts of the proposed form are essential to the intent and which are replaceable;
- an unacceptable or hollow version of success;
- observable evidence that the intended change occurred.

Use these as diagnostic lenses, not required questionnaire fields. Infer from evidence where safe, omit what does not matter, and never ask a question merely to fill a heading.

If the context already makes the remaining plausible readings decision-equivalent, ask no questions; synthesize the Intent Brief for confirmation.

## Make every question earn its place

Ask a question only when all of these are true:

1. The user is uniquely positioned to answer it; it is not a discoverable fact.
2. Context has not already answered it or made one answer sufficiently safe to infer.
3. At least two materially different answers remain plausible.
4. Those answers would change several important downstream choices, resolve a central contradiction, or prevent a costly wrong direction.
5. Its prerequisites are settled, so the user can answer it now.
6. It is not redundant with an earlier answer or user prompt.

Before asking, be able to name the plausible answers and the decisions each would change. If the answers lead to the same choices, do not ask. Prefer the candidate with the greatest:

`downstream reach × uncertainty × cost of a wrong assumption × separation between plausible answers × answerability ÷ (user effort + anchoring risk)`

Do not calculate a score mechanically. Use it to reject low-yield questions.

## Interview in compact rounds

Work in rounds, as follows:

1. Form competing intent hypotheses from current evidence.
2. Find the **intent frontier**: unresolved, consequential distinctions whose prerequisites are settled.
3. Ask three questions by default. Batch at most ten only when they are genuinely independent; ask fewer at a time when answers could change the need or wording of subsequent questions.
4. Number questions. Make each number one independently answerable decision, not a bundle of unrelated prompts.
5. Anchor each question in the actual situation. When useful, include:
   - **Current read:** a concise, explicitly provisional inference the user can accept or correct.
   - **Unlocks:** the downstream choices this answer will govern.
6. Let the user answer tersely, accept a current read, reject the premise, or supply a missing alternative.
7. Update the intent model, surface material contradictions instead of silently resolving them, and recompute the frontier.

Do not recommend what the user ought to want. When evidence favors one interpretation, offer it as a tentative read. When genuine ambiguity remains, present balanced alternatives and allow “neither.” Recommend downstream means only after intent is settled.

Recap only material changes between rounds. Preserve an answer unless new evidence contradicts it; when reopening one, quote the conflict and explain why it matters.

If the user cannot answer a consequential question, reframe it once as a concrete contrast or scenario when that lowers the burden. If it remains unknown, or the user declines more interviewing, stop asking. Preserve it as an **open intent hinge**, state which later choices it prevents the brief from governing, and present the rest as provisional rather than confirmed. Treat three substantive rounds as a warning: before adding another, identify the single unresolved hinge and why its value justifies more user effort; otherwise synthesize.

## Generate discriminating questions

Selectively adapt these patterns when useful; never march through them as a checklist.

- **Means–end test:** When the chain is already well supported, ask: “My current read is that `<requested thing>` is a means to `<desired change>`, so that `<deeper outcome>` becomes true. If the requested thing worked perfectly but the deeper outcome did not happen, would it count?” If the chain itself is uncertain, use competing futures instead of embedding it in the question.
- **Competing futures:** “I see two coherent readings: `<future A>` and `<future B>`. Which is closer, or what important intent do both miss?”
- **Proof scene:** “What future moment, changed behavior, meaningful trend, or absence of failure would make you say, ‘Yes, that is the outcome I meant’?”
- **Unacceptable success:** “What could satisfy the literal request and still make you feel we built the wrong thing?”
- **Priority collision:** “When `<intent A>` conflicts with `<intent B>`, which should win?” Ask only after the tension is real, not hypothetically invented.
- **Solution-swap test:** “If a completely different approach produced the same stated outcome, would it satisfy the intent? If not, what value is embedded in this particular form?”
- **Preservation test:** “What valuable quality of the current situation must not be lost while creating this change?”

Prefer a concrete contrast, counterfactual, or future scene over “What is your vision?” or repeated “Why?” questions. One prompt may request one coherent artifact such as a scene or ranking; do not hide several independent questions inside it.

## Synthesize a decision lens

As soon as the remaining plausible intent models are equivalent for consequential decisions, stop interviewing and present a compact **Intent Brief**. Include only relevant sections:

- **Final vision** — one sentence about the changed future, not the deliverable.
- **Governing perspective** — whose outcome or judgment takes precedence, or how joint, constrained, or unresolved decision rights work.
- **Intent stack** — the primary intent and any supporting intents, ranked when they can conflict.
- **Decision rules** — only the few “prefer X over Y when…” principles that resolve real collisions.
- **Unacceptable win** — the nearest result that looks successful but violates the intent.
- **Proof scene** — an observable moment, behavior, trend, threshold, or absence of failure that demonstrates the change.
- **Proposed means** — the current approach, explicitly separated from the ends it serves, including any aspect of the form that is itself essential.
- **Material assumptions** — only consequential inferences that remain provisional.

Add one to three representative downstream implications: “This intent would choose A over B because…” For broad efforts, use at least two. Use only already-surfaced choices or high-level outcome and value forks; do not introduce named features, workflows, technologies, architectures, or requirements. Treat implications as semantic calibration, not design decisions. Include the closest alternative vision and why it does not fit only when that alternative was genuinely plausible, and ground the rejection in explicit user evidence.

Keep the brief in the conversation unless the user asks for a file or the surrounding workflow already has a designated artifact.

## Stop at decision-ready intent

Before seeking confirmation, test the brief:

1. **Compression:** Can the final vision and governing intent be stated compactly without losing what matters?
2. **Discrimination:** Does the brief explain why the chosen future fits and a nearby plausible future does not?
3. **Prediction:** Does it predict the direction of the representative, high-impact downstream choices?
4. **Conflict resolution:** Does it say which intent wins in value collisions that are actually likely?
5. **Grounding:** Is every material claim user-stated or clearly marked as an inference?

Try to construct two materially different directions that both satisfy the brief. If one unresolved intent distinction makes both plausible, ask exactly the question that separates them. If the remaining differences are implementation-level, reversible, low-impact, or equally compatible with the intent, leave them for later.

The goal is not an empty question tree. It is **decision-ready intent**.

## Confirm without inviting reflex agreement

After showing the Intent Brief and its downstream implications, ask:

> What is materially wrong, overstated, or missing here? If nothing is, reply `confirmed`.

Do not treat silence, partial answers, or enthusiasm that does not assent to the brief as confirmation. Treat clear semantic assent such as “yes,” “correct,” or “looks right—go ahead” as confirmation; do not require the literal word `confirmed`. A correction reopens only the affected part of the intent model; revise it, rerun the tests, and ask another question only if a consequential distinction remains.

Do not plan, design, or implement from the brief until the user explicitly confirms it. After confirmation, resume an already-requested surrounding task if one exists; otherwise stop and hand back the confirmed decision lens.
