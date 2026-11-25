# Failure modes for `/agents`

## 1. Product-news sludge

**Symptom:** Launches, funding, job posts, and model fandom dominate.

**Response:** Tighten to procedures, configs, evals, traces, measurements,
failures, and artifacts. A product announcement is discovery, not practice.

## 2. Model leaderboard without the tuple

**Symptom:** “Model A is best at agents” from one score.

**Response:** Require model/version × harness/tools × task/eval × constraints.
If missing, label the comparison unresolved.

## 3. Artifact equals proof

**Symptom:** A repo or benchmark link is reported as independent validation.

**Response:** Label it inspectable but uninspected. Distinguish announcement,
builder report, maintainer evidence, user replication, and critique.

## 4. Actionable in name only

**Symptom:** Advice is generic (“write better prompts”, “use subagents”).

**Response:** Apply the two-of-four gate: procedure/config, measurement,
failure/boundary, artifact. Demote failures to Watchlist or theme.

## 5. Harness effects laundered into model capability

**Symptom:** A workflow improvement is attributed solely to the model.

**Response:** Preserve model × harness × task; state which component the post
actually varied.

## 6. Latest-only reply blindness

**Symptom:** New praise hides an earlier bug report or maintainer correction.

**Response:** Pair thread fetch with floor-free exact conversation,
self-thread, and local time-box lanes.

## 7. Engagement floor deletes the bug report

**Symptom:** `min_faves` keeps demos but removes a quiet reproduction failure.

**Response:** Never use engagement as evidence gate. Keep a floor-free lane and
rank specificity, role, evidence, and information gain separately.

## 8. `to:` cross-thread contamination

**Symptom:** Replies to a prolific builder from other roots are attached to the
selected practice.

**Response:** Use `to:` only as fallback; require exact returned
`conversation_id == root_id`.

## 9. Author self-thread counted as corroboration

**Symptom:** Several builder continuations become several independent voices.

**Response:** Count one source chain. Label independent evidence only when it
adds a distinct attempt, artifact, measurement, or technical argument.

## 10. Praise mistaken for adoption evidence

**Symptom:** “Trying this!” or “great idea” is counted as successful use.

**Response:** Require setup and observed outcome for replication. Otherwise
drop or mark an unverified lead.

## 11. Benchmark shortcut or cheating ignored

**Symptom:** A strong score is accepted without checking solution leakage,
grader gaming, task contamination, or invalid tool access.

**Response:** Search exact conversation and quote critiques for evaluation
defects. Report the score and validity concern separately.

## 12. Safety advice without threat model

**Symptom:** A permission or sandbox rule is universalized from one workflow.

**Response:** Preserve assets, actor, tool authority, reversibility, and failure
mode. State the boundary rather than broadening the rule.

## 13. Coverage accounting drift

**Symptom:** Inspected posts, roots, conversations, nodes, and authors are mixed.

**Response:** Deduplicate IDs and reconcile inspected → candidate roots →
conversations enriched → promoted nodes. Report unique authors separately.

## 14. Seed capture and unverified expansion

**Symptom:** The whole brief follows the existing seeds, or promotes a new
account from one good reply, a biography, or product-post volume.

**Response:** Use seeds for vocabulary and roots, then seek maintainer,
replication, critique, and correction roles. Before adding a new durable seed,
require two distinct qualifying own-root conversations; one self-thread is one
event. If the broader window is quiet, say so instead of fabricating diversity.
