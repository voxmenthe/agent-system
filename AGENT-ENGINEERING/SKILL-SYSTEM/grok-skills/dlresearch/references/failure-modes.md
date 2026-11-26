# Failure modes for `/dlresearch`

## 1. Root-only false negative

**Symptom:** `from:{seed} ... -filter:replies` is empty, so the source is
declared quiet.

**Response:** Run `filter:self_threads`. Technical breakdowns often live in
author continuations or reply-shaped self-threads.

## 2. Abstract-paraphrase pileup

**Symptom:** Many accounts repeat the paper abstract but no one adds method,
conditions, limitation, or evidence.

**Response:** Count this as prevalence, not corroboration. Keep at most one
representative summary and search author, replication, and critique roles.

## 3. Paper identity collision

**Symptom:** Posts about similarly named methods or multiple report versions are
merged.

**Response:** Require a distinctive title fragment, author/lab, identifier, or
returned link. Split unresolved identities rather than guessing.

## 4. X interpretation laundered into result verification

**Symptom:** The brief says a result “works” because an explainer summarized it.

**Response:** Label X-only status. Separate paper-author claim, interpretation,
reported replication, and critique. The underlying paper remains unchecked
unless explicitly inspected outside this skill.

## 5. Latest-only reply blindness

**Symptom:** A popular conversation appears uniformly positive because Latest
shows only new praise.

**Response:** Pair thread fetch with floor-free exact conversation, self-thread,
and a local time box around material nodes.

## 6. Engagement floor hides the expert correction

**Symptom:** A clean `min_faves` result drops a near-zero-like technical reply.

**Response:** Never use the floor alone. Rank role, specificity, evidence, and
information gain separately from engagement.

## 7. `to:` cross-conversation bleed

**Symptom:** Replies to the same author from unrelated roots enter the selected
paper conversation.

**Response:** Use `to:` only as fallback; require exact returned
`conversation_id == root_id`.

## 8. Criticism by question mark

**Symptom:** “What about contamination?” is reported as proof of contamination.

**Response:** Treat an unanswered question as a lead. Promote a critique as
evidence only when it states a mechanism, observation, control, or falsifier.

## 9. Author thread mistaken for independent support

**Symptom:** Ten author continuations are counted as ten corroborating voices.

**Response:** Label all as one source chain. Distinguish author elaboration from
independent replication or critique.

## 10. Coverage arithmetic drift

**Symptom:** Search counts, enriched roots, and output-table rows disagree.

**Response:** Deduplicate IDs and reconcile inspected → candidate roots →
conversations enriched → promoted nodes. Count unique authors separately.

## 11. Open scan becomes AI-news sludge

**Symptom:** Product launches, policy chatter, generic AGI claims, and memes
dominate.

**Response:** Tighten to mechanisms, experiments, benchmarks, ablations,
replications, or specific papers. Shrink claims if the window is quiet.

## 12. One paper consumes the whole frontier scan

**Symptom:** A viral thread displaces every other topic without more evidence.

**Response:** Cap roots per paper unless the user asked for that paper. Seek
role and theme diversity, not arbitrary topic count.

## 13. Conversation neighbor promoted as a source seed

**Symptom:** One excellent reply beside an exemplar, or an “accounts like X”
result, is treated as proof that the account repeatedly publishes technical
breakdowns.

**Response:** Treat adjacency as candidate discovery. Require two distinct
substantive own-root conversations in the window; nodes in one self-thread
remain one source event.

## 14. Unparenthesized OR batch loses its bounds

**Symptom:** `from:a OR from:b OR from:c -filter:replies since:… until:…`
returns posts from long before the bound, often all from the first handle, and
the other handles look quiet.

**Response:** Parenthesize every OR group:
`(from:a OR from:b OR from:c) -filter:replies since:… until:…`. Without
parentheses X applies bounds and filters to the last OR term only. A page
whose posts all belong to the first OR term and fall outside the bound is
bound-failed; it proves nothing about the other handles.
