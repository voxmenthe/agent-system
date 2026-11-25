# Failure modes for /list-summary

Recognize these early. Prefer shrinking claims over stretching a bad sample.

## 1. No list identity

**Symptoms:** Empty `/list-summary` with no default; "summarize a list" with no
URL/id/alias; ambiguous name not in known-lists.

**Do:** Ask once for list URL, numeric id, or a known alias. Do not invent an id.
If a default exists in `known-lists.md`, use it and state that you did.

## 2. Missing X tools

**Symptoms:** Only web/browser tools available; no `x_keyword_search`.

**Do:** Refuse the skill path. Explain Grok Build X tools are required. Do not
produce a fake digest from public HTML or memory of who "should" be on the list.

## 3. Empty list sample / access failure

**Symptoms:** `list:{id}` returns nothing even after widening to ~14–30 days.

**Do:** Confidence `thin`. Report possible causes: private list (other account),
empty membership, wrong id, host auth cannot see the list, or genuinely quiet.
Do not invent members or posts.

## 4. Top mode empty (common)

**Symptoms:** `list:{id}` Top returns no results while Latest works.

**Do:** Treat as host quirk, not as "nothing happened." Rank Latest by engagement
and substance. Note Top-empty only if relevant in Gaps.

## 5. Reply-heavy / low-substance flood

**Symptoms:** Sample is mostly "same", "lol", single-emoji, or empty quote-RTs.

**Do:** Use `-filter:replies` for root discovery, then enrich only selected
roots with thread fetch plus floor-free `conversation_id:`. Do not start with
`min_faves`; it can delete zero-like technical replies. Expand Gaps:
"reply-heavy window; overview biased to originals; selected conversations
enriched separately."

## 6. Thin sample

**Symptoms:** Few unique authors, one megathread, or one prolific account dominating.

**Do:** Confidence `thin` or `medium`. Shorten theme map. Name the domination risk
("~half of volume from @x"). Never invent themes to fill the table.

## 7. Off-list contamination

**Symptoms:** Semantic search or thread parents pull in non-members.

**Do:** Label non-members as **origin outside list** if needed for context; do not
put them in Active voices as list members. Theme map and receipts stay list-first.

## 8. Wrong list / alias collision

**Symptoms:** User said "alignment list" but multiple known lists could match.

**Do:** Prefer exact alias table match. If still ambiguous, ask. Do not merge two
list ids in one brief.

## 9. Over-long window mixes stale arcs

**Symptoms:** Quiet list, you search 30 days, and mix three unrelated old arcs as
if they were one live story.

**Do:** Re-pulse. Prefer Story/Same-day when a fresh cluster exists. Put older
background in one short "prior context" line or Gaps.

## 10. Treating the list as the whole field

**Symptoms:** "The mech interp community believes…" from one private list sample.

**Do:** Frame as "on this list in this window." List bias (who the user follows
into the list) is always a caveat.

## 11. Quote fabrication

**Symptoms:** Paraphrase that looks like a quote; reconstructed status URLs.

**Do:** Only quote text returned by tools. Only link URLs/IDs the tools provided.
If you lack a URL, cite `@handle` and paraphrase without a fake link.

## 12. Web leakage into list membership

**Symptoms:** Temptation to scrape x.com list pages or guess handles from bios.

**Do:** Stop. Membership filtering is `list:{id}` only. Web is at most one
id-resolve assist, not a member census.

## 13. Topic filter over-constrained

**Symptoms:** User asked for a topic; list+topic returns empty while full list scan
is rich.

**Do:** Widen topic aliases once. If still empty, report no in-window hits for
that focus, then optionally offer a one-line pointer to what the list *was*
discussing (without switching skills silently).

## 14. Percentages / heat as false precision

**Symptoms:** "62% of the list is bearish on evals" from 11 posts.

**Do:** Rough heat buckets (`high` / `med` / `low`) and coarse shares only, with
explicit "this list sample" language.

## 15. Off-list reply becomes a list voice

**Symptoms:** Thread fetch surfaces a sharp expert reply, and the brief puts that
author in Active voices or list prevalence without membership evidence.

**Do:** Label it **outside-list context**. It can be a grounded correction or
counterevidence node, but not a list-member receipt or list-volume observation.

## 16. Latest-only conversation miss

**Symptoms:** The newest conversation results are jokes/promos while a known
older correction or author continuation is absent.

**Do:** Thread-fetch the material node and time-box `conversation_id:` around its
timestamp. Use `filter:self_threads` for author continuations.

## 17. `to:` cross-conversation bleed

**Symptoms:** A topic-filtered `to:{author}` query looks relevant but returned
posts belong to other conversation IDs.

**Do:** Use `to:` only as fallback. Retain exact target `conversation_id`
matches; discard the rest.

## 18. Conversation edge or accounting lost

**Symptoms:** A reply is summarized without IDs/relationship, or Coverage and
Search log disagree on tool-call counts.

**Do:** Demote an ungrounded reply to a lead. Reconcile calls and report the
funnel as inspected posts, candidate roots, enriched conversations, and promoted
nodes.
