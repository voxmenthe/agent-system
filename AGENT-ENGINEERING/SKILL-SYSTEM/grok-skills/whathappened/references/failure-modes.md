# Failure modes for /whathappened

Recognize these early. Prefer shrinking claims over stretching a bad sample.

## 1. No topic / discovery request

**Symptoms:** "what's hot", "trending on X", empty `/whathappened`.

**Do:** Ask for a topic. Do not run a global X firehose brief (v1 has no discovery).

## 2. Missing X tools

**Symptoms:** Only web/search tools available.

**Do:** Refuse the skill path. Explain Grok Build X tools are required. Do not
produce a fake X opinion map from Google.

## 3. Entity collision

**Symptoms:** Results mix two products, two people, or a common English word.

**Do:** Tighten to `"Exact Phrase"`, official `from:`, and aliases from the single
web resolve. Discard off-entity high-engagement posts even if viral.

## 4. Thin sample

**Symptoms:** Few unique authors, mostly retweets, or only one thread.

**Do:** Confidence `thin`. Shorten opinion map. Expand Gaps. Optionally widen
window one step. Never invent camps to fill the table.

## 5. Bot / engagement farm noise

**Symptoms:** Near-identical text, brand-new accounts, engagement without replies,
hashtag spam.

**Do:** Select human-looking roots with specific claims, then inspect a small
number of exact conversations. A reply count is not proof of a useful chain.
Use an engagement floor only after a floor-free sample; note bot risk in Gaps.

## 6. Official silence

**Symptoms:** Lots of secondary takes, no `from:official` in window.

**Do:** Say so in What happened / Gaps. Do not treat rumor volume as confirmation.

## 7. Origin post outside short window

**Symptoms:** Everyone replies to or quotes a post older than your Breaking window.

**Do:** Fetch that origin thread even if older. Mention that the conversation is
fresh but the trigger is older.

## 8. Web leakage into sentiment

**Symptoms:** Temptation to cite articles, Reddit, or blogs for "what people think."

**Do:** Stop. Web is resolve-only (max one call). Sentiment stays X-only.

## 9. Over-long window on a fresh launch

**Symptoms:** Same-day launch but you searched 30 days and mixed prior product talk.

**Do:** Re-pulse. Commit Same-day or Breaking. Prior product discourse goes to
Gaps or a single "prior context" sentence, not the main opinion map.

## 10. Quote fabrication

**Symptoms:** Paraphrase that looks like a quote; reconstructed status URLs.

**Do:** Only quote text returned by tools. Only link URLs/IDs the tools provided.
If you lack a URL, cite `@handle` and paraphrase without a fake link.

## 11. Single-camp tunnel vision

**Symptoms:** Top lane is pure hype or pure hate.

**Do:** Force a debate lane and Latest lane. If the other side truly is absent,
say the sample is one-sided rather than inventing balance.

## 12. Percentages as false precision

**Symptoms:** "67.3% bullish" from 12 posts.

**Do:** Rough buckets only (`~half`, `~1/3`, or coarse percents) with explicit
"qualitative from this sample" language.

## 13. Latest-only reply blindness

**Symptoms:** A popular conversation's newest ten posts are jokes or residual
confusion, while an older official correction or expert branch is missing.

**Do:** Thread-fetch the important node, run floor-free
`conversation_id:{root}`, then time-box around the known node timestamp. Do not
declare the Latest slice to be the full conversation.

## 14. `to:` contamination

**Symptoms:** `to:{author} filter:replies` returns on-topic posts from several
unrelated conversations.

**Do:** Treat `to:` as a fallback author-activity lane. Retain only posts whose
tool-returned `conversation_id` equals the selected root. Never infer a reply
edge from topic similarity alone.

## 15. Engagement floor erases minority signal

**Symptoms:** A clean `min_faves` result contains popular acknowledgements but
drops zero-like technical corrections or extensions.

**Do:** Always run one floor-free conversation sample first. Use at most one
modest floor as a precision comparison, not as the evidence universe.

## 16. Conversation receipt loses its edge

**Symptoms:** The brief says "a strong reply argued..." without the reply post
ID/URL, root ID/URL, or relationship.

**Do:** Demote it to an unresolved lead. A promoted node must retain both ends
of the relationship plus its substantive class and load-bearing text.

## 17. Funnel or call-accounting drift

**Symptoms:** Coverage says five thread fetches while the search log lists six,
or raw inspected counts are presented as usable evidence.

**Do:** Reconcile the search log before sending. Report approximate inspected,
candidate-root, enriched-conversation, and promoted-node counts separately.
