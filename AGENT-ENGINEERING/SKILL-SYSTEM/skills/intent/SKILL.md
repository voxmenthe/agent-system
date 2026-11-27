---
name: intent
description: Run an explicitly invoked, high-leverage interview that uncovers the user's underlying intent, intent hierarchy, final vision, and any major directional forks, then distills them into a compact decision lens. Use when the user invokes $intent to clarify what they are really trying to achieve, align on the why or north star before consequential decisions, separate a proposed solution from the outcome it should cause, settle macro approach or UI forks that shape the overall direction, or resolve competing goals without yet eliciting requirements or detailed design.
disable-model-invocation: true
---

# Intent

Discover the smallest set of intent truths—and, when warranted, high-level directional commitments—that makes later choices predictable.

**Do not maximize the number of questions answered; minimize the consequential intent and macro direction left ambiguous.**

Stay upstream of requirements and detailed design. Clarify the desired change, the reasons it matters, and the values that should govern tradeoffs. Do not turn the session into feature discovery, specification, planning, or implementation. Treat the user's proposed artifact or approach as a possible means, not automatically as the end.

The one exception is a **directional fork**: a high-level implementation choice that is either inextricably tied to the intent (changing the meaning of the outcome, how a person actually uses it, or a hard boundary) or a macro direction-setter before work starts (hard to reverse, or materially reshaping scope, cost, risk, or overall direction). When the work is user-facing, pay particular attention to how humans will actually use the feature—meaningfully different UI designs or interaction models are often part of the intent itself, not mere implementation detail. Give these forks a brief, high-level discussion so you do not hand back an abstract brief that invites an unaligned bet. Leave local, reversible, low-impact, and detailed implementation or visual-polish choices for later.

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
- any directional fork visible from the prompt or light context/codebase inspection—including, for user-facing work, how people will actually use the feature and whether meaningfully different UI designs would create a different experience, or whether competing paths commit the effort to a different macro direction;
- an unacceptable or hollow version of success;
- observable evidence that the intended change occurred.

Use these as diagnostic lenses, not required questionnaire fields. Infer from evidence where safe, omit what does not matter, and never ask a question merely to fill a heading.

If the context already makes the remaining plausible readings decision-equivalent and leaves no directional fork open, ask no questions; synthesize the Intent Brief for confirmation.

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

Apply the same bar to implementation and UI choices. Raise a directional fork only when competing high-level paths—or, for user-facing work, competing UI designs and interaction flows—either change how the feature is used, what counts as the intended outcome, or hard boundaries, or materially alter scope, cost, risk, or reversibility for the whole effort. Do not ask about local, reversible, or detailed choices (libraries, schemas, file layout, internal APIs, tuning, or minor visual polish) unless one is itself a hard-to-reverse directional bet.

## Interview in compact rounds

Work in rounds, as follows:

1. Form competing intent hypotheses—and any directional forks—from current evidence.
2. Find the **intent frontier**: unresolved, consequential distinctions whose prerequisites are settled.
3. Ask three questions by default. Batch at most ten only when they are genuinely independent; ask fewer at a time when answers could change the need or wording of subsequent questions.
4. Number questions. Make each number one independently answerable decision, not a bundle of unrelated prompts.
5. Anchor each question in the actual situation. When useful, include:
   - **Current read:** a concise, explicitly provisional inference the user can accept or correct.
   - **Unlocks:** the downstream choices this answer will govern.
6. Let the user answer tersely, accept a current read, reject the premise, or supply a missing alternative.
7. Update the intent model, surface material contradictions instead of silently resolving them, and recompute the frontier.

Do not recommend what the user ought to want. When evidence favors one interpretation, offer it as a tentative read. When genuine ambiguity remains, present balanced alternatives and allow “neither.” For a directional fork, you may name the competing high-level approaches or UI shapes, their concrete tradeoffs, and a tentative read when evidence favors one—without drifting into detailed design or recommending local implementation choices before intent is settled.

Recap only material changes between rounds. Preserve an answer unless new evidence contradicts it; when reopening one, quote the conflict and explain why it matters.

If the user cannot answer a consequential question, reframe it once as a concrete contrast or scenario when that lowers the burden. If it remains unknown, or the user declines more interviewing, stop asking. Preserve it as an **open intent hinge**, state which later choices it prevents the brief from governing, and present the rest as provisional rather than confirmed. Treat three substantive rounds as a warning: before adding another, identify the single unresolved hinge and why its value justifies more user effort; otherwise synthesize.

Protect speed and brevity as the default. Keep approach and UI discussion high-level—aim to frame the competing directions and tradeoffs in a few lines and settle or rule out a direction within the normal compact rounds. If resolving a directional fork genuinely requires deeper technical exploration, codebase investigation, or multi-round design tradeoffs, do **not** silently gloss over it and do **not** automatically expand `/intent` into a deep design session. Instead, stop with an explicit **unresolved directional hinge**, state why deeper technical exploration or multi-round design is highly warranted and what downstream choices depend on it, and give the user the option to do that next rather than making it the default.

## Generate discriminating questions

Selectively adapt these patterns when useful; never march through them as a checklist.

- **Means–end test:** When the chain is already well supported, ask: “My current read is that `<requested thing>` is a means to `<desired change>`, so that `<deeper outcome>` becomes true. If the requested thing worked perfectly but the deeper outcome did not happen, would it count?” If the chain itself is uncertain, use competing futures instead of embedding it in the question.
- **Competing futures:** “I see two coherent readings: `<future A>` and `<future B>`. Which is closer, or what important intent do both miss?”
- **Proof scene:** “What future moment, changed behavior, meaningful trend, or absence of failure would make you say, ‘Yes, that is the outcome I meant’?”
- **Unacceptable success:** “What could satisfy the literal request and still make you feel we built the wrong thing?”
- **Priority collision:** “When `<intent A>` conflicts with `<intent B>`, which should win?” Ask only after the tension is real, not hypothetically invented.
- **Solution-swap test:** “If a completely different approach produced the same stated outcome, would it satisfy the intent? If not, what value is embedded in this particular form?”
- **Directional fork:** “I see two materially different high-level directions: `<approach or UI shape A>` (`<tradeoff/experience A>`) vs `<approach or UI shape B>` (`<tradeoff/experience B>`). Which fits what you want, should we rule one out, or does this warrant deeper technical exploration before choosing?”
- **Preservation test:** “What valuable quality of the current situation must not be lost while creating this change?”

Prefer a concrete contrast, counterfactual, or future scene over “What is your vision?” or repeated “Why?” questions. One prompt may request one coherent artifact such as a scene or ranking; do not hide several independent questions inside it.

## Synthesize a decision lens

As soon as the remaining plausible intent models—and any succinct directional forks—are settled (with heavier forks explicitly flagged), stop interviewing and present a compact **Intent Brief**. Include only relevant sections:

- **Final vision** — one sentence about the changed future, not the deliverable.
- **Governing perspective** — whose outcome or judgment takes precedence, or how joint, constrained, or unresolved decision rights work.
- **Intent stack** — the primary intent and any supporting intents, ranked when they can conflict.
- **Decision rules** — only the few “prefer X over Y when…” principles that resolve real collisions.
- **Unacceptable win** — the nearest result that looks successful but violates the intent.
- **Proof scene** — an observable moment, behavior, trend, threshold, or absence of failure that demonstrates the change.
- **Proposed means** — the initially proposed approach, explicitly separated from the ends it serves, including any aspect of the form that is itself essential.
- **High-level direction** — *(only when a directional fork was settled or ruled out)* the macro approach or UI direction chosen or eliminated and the tradeoffs accepted, kept explicitly separate from the underlying ends and short of detailed design.
- **Open hinges** — *(only when unresolved)* any open intent hinge or heavy technical fork where deeper technical exploration or multi-round design is highly warranted, what downstream choices depend on it, and an explicit option to explore it before planning or building.
- **Material assumptions** — only consequential inferences that remain provisional.

Add one to three representative downstream implications: “This intent would choose A over B because…” For broad efforts, use at least two. Use only already-surfaced choices, high-level outcome and value forks, or already-discussed directional forks; do not introduce un-discussed features, detailed workflows, technologies, architectures, or requirements. Treat implications as calibration of intent and macro direction, not detailed design. Include the closest alternative vision (or rejected macro direction) and why it does not fit only when that alternative was genuinely plausible, and ground the rejection in explicit user evidence.

Keep the brief in the conversation unless the user asks for a file or the surrounding workflow already has a designated artifact.

## Stop at decision-ready intent

Before seeking confirmation, test the brief:

1. **Compression:** Can the final vision and governing intent be stated compactly without losing what matters?
2. **Discrimination:** Does the brief explain why the chosen future fits and a nearby plausible future does not?
3. **Prediction:** Does it predict the direction of the representative, high-impact downstream choices—or explicitly flag any heavy directional fork that warrants deeper exploration?
4. **Conflict resolution:** Does it say which intent wins in value collisions that are actually likely?
5. **Grounding:** Is every material claim user-stated or clearly marked as an inference?

Try to construct two materially different directions that both satisfy the brief:

- If an unresolved intent distinction—or a directional fork that can be framed succinctly—makes both plausible, ask the question that separates them.
- If two materially different macro directions remain plausible **and** choosing between them requires deeper technical exploration or multi-round design tradeoffs, do not silently defer them or expand into a deep design review by default; record the fork under **Open hinges**, explain why deeper exploration is highly warranted, and give the user the option to do that next.
- If the remaining differences are local, reversible, low-impact, or detailed implementation choices that do not change the macro direction or outcome, leave them for later.

The goal is not an empty question tree. It is **decision-ready intent**.

## Confirm without inviting reflex agreement

After showing the Intent Brief and its downstream implications, ask:

> What is materially wrong, overstated, or missing here? If nothing is, reply `confirmed`.

When the brief flags a heavy technical fork where deeper technical exploration or multi-round design is highly warranted, also ask explicitly whether the user wants to opt into that exploration next (for example, continuing into deeper technical exploration or switching to a dedicated design/grilling step) rather than going straight to planning or implementation.

Do not treat silence, partial answers, or enthusiasm that does not assent to the brief as confirmation. Treat clear semantic assent such as “yes,” “correct,” or “looks right—go ahead” as confirmation; do not require the literal word `confirmed`. A correction reopens only the affected part of the intent model; revise it, rerun the tests, and ask another question only if a consequential distinction remains.

Do not plan, design, or implement from the brief until the user explicitly confirms it. After confirmation, resume an already-requested surrounding task if one exists; otherwise stop and hand back the confirmed decision lens.
