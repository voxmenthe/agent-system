# Failure modes for /macro

Recognize these early. Prefer shrinking claims over stretching a bad sample.
The whole point of this skill is **refusing noise**.

## Contents

- [Tool, noise, and thin-sample failures](#1-missing-x-tools)
- [Claims, attribution, and source control](#7-rumor-without-a-clear-level-set)
- [Equity allowlist and role failures](#21-equity-sleeve-without-equity-allowlist)
- [Lists, replies, and coverage accounting](#25-supplementary-list-becomes-the-brief)
- [Output-shape failures](#31-participant-native-signal-displaced-by-an-analyst-framework)
- [Trader-trajectory failures](#33-individual-trade-diary-becomes-consensus-or-verified-performance)
- [Company coverage and ranking starvation](#35-ai-capex-stands-in-for-equity-coverage)
- [Dual-read, sampling, and worker failures](#39-delta-only-gate-erases-temperature)

## 1. Missing X tools

**Symptoms:** Only web/search tools available.

**Do:** Refuse the skill path. Explain Grok Build X tools are required. Do not
produce a fake macro opinion map from Google headlines.

## 2. Noise flood / low SNR

**Symptoms:** Semantic or Top lanes return meme finance, political dunks,
crypto influencers, screenshot spam, multi-hashtag promo posts.

**Do:** Hard-drop non-allowlist authors from the **core**. In a
participant-native equity run, route only registered, current-post-eligible
panel voices to the separate sentiment sample; other off-list survivors remain
isolated context or discovery leads. Apply the hashtag/quality gate in
`credible-sources.md`: do not drop allowlisted analysis for tag count alone;
drop non-allowlist 2+ hashtag spam and allowlisted posts that also devolve
into tag soup or promo. If almost nothing remains, widen the permitted window one step or say which
evidence role is quiet. Never fill the brief with viral retail takes.

## 3. Allowlist too quiet

**Symptoms:** User window is short (e.g. past 2 hours) and Tier A silent.

**Do:** State quiet tape. Optionally note you checked N batches. Do not invent
a narrative. Offer that a wider window might help - do not silently expand
beyond a user-fixed window. Do not fall back to official institutional feeds.

## 4. User-fixed window ignored

**Symptoms:** User said "past 48 hours" but results or synthesis drift to last
month's FOMC.

**Do:** Re-filter to the committed bound. Older origin posts may be fetched
only when clearly the quote-target of in-window debate, and labeled as older
origin.

## 5. Entity / event collision

**Symptoms:** "CPI" mixed with unrelated inflation culture war posts; "soft"
without landing; wrong person with same name.

**Do:** Tighten phrases, require allowlist authors, prefer clear Tier A
level-sets. Discard off-entity even if high engagement.

## 6. Thin sample after filter

**Symptoms:** Few unique allowlisted authors; one thread dominating; many
drops from the hashtag/quality gate or on-topic-only rules.

**Do:** Label the affected sample thin in ordinary prose. Shorten aggregate
claims, preserve only genuinely telling isolated observations with that label,
and expand Gaps. Never invent camps to fill a grid.

## 7. Rumor without a clear level-set

**Symptoms:** Strategists debating a "leak" or rumor; no careful factual
framing in the sample.

**Do:** Say so explicitly. Do not treat rumor volume as confirmed policy.
Prefer "unconfirmed in this sample" language.

## 8. Origin post outside window

**Symptoms:** Everyone quotes yesterday's print take or last week's speech.

**Do:** Fetch the origin thread even if slightly older. Mark trigger as older
than conversation window.

## 9. Web leakage into sentiment

**Symptoms:** Temptation to cite Reuters/Bloomberg article text for "positioning"
or "traders think."

**Do:** Stop. Web is resolve-only (max one call). Sentiment stays on X and
within the defined core, sentiment-sample, and context roles.

## 10. Tier B carrying contested facts

**Symptoms:** Only a news brand account asserts a policy outcome; Tier A silent
or contradictory.

**Do:** Soften to "reported by @markets / Tier A not yet weighing in" or demote.
Prefer named Tier A voices for market interpretation.

## 11. Handle drift / wrong account

**Symptoms:** `from:X` empty or clearly the wrong person; brand renamed.

**Do:** One `x_user_search`, correct for session, note in Gaps. Do not fuzzy-match
a lookalike handle into the allowlist.

## 12. Single-camp tunnel vision

**Symptoms:** Allowlist batch happens to be all "cut soon" or all "higher forever."

**Do:** Force another Tier A batch and a debate-oriented query. If the other
side is truly absent among credible voices, say the sample is one-sided -
do not import retail contrarians for fake balance.

## 13. False precision on levels and percentages

**Symptoms:** "67% of macro twitter is bullish duration" from 9 posts; invented
basis-point paths.

**Do:** Rough buckets only. Attribute specific levels to specific posts. No
fake consensus percentages.

## 14. Trade-advice bleed

**Symptoms:** Closing with "so buy bonds" or position sizing.

**Do:** Remove. Describe camps and claimed levels only. Gaps may restate
"not trade advice."

## 15. Discovery becomes a firehose

**Symptoms:** Empty `/macro` turns into a dump of every allowlisted tweet.

**Do:** Cluster into sleeves (rates, data, FX, credit, policy). Keep only themes
that matter to Delta or Temperature. Quote density follows paraphrase loss and
source diversity, not the size of the raw result set.

## 16. Quietly expanding the allowlist

**Symptoms:** A smart-looking non-list account is in Top results; temptation to
treat them as Tier A "just this once."

**Do:** Do not expand the core. Only user-requested core exceptions for named
handles, labeled in Gaps. Registered probationary panel voices remain in the
weaker sentiment role; one good post does not promote them. Propose a separate
review if the user wants a permanent core-list edit.

## 17. Quote fabrication

**Symptoms:** Paraphrase that looks like a quote; reconstructed status URLs.

**Do:** Only quote tool-returned text. Only link URLs/IDs tools provided. If no
URL, cite `@handle` and paraphrase without a fake link.

## 18. US-hours and English bias

**Symptoms:** Asia session or EM macro under-represented on the list.

**Do:** Note bias in Gaps. For Asia/Europe topics, prioritize Tier A FX/global
handles (Saravelos, Brooks, MacroAlf, Steno, ING, `michaelxpettis` for China
imbalances, etc.).

## 19. Topic-conditional account pollution

**Symptoms:** `@PolemicTMM`, `@EffMktHype`, `@VKMacro`, `@dsquareddigest`,
`@RobinWigg` (or similar **on-topic only** handles)
dominate the sample with non-macro posts, or those posts sneak into receipts.

**Do:** Keep the author in search batches, but discard every non-markets post
before ranking. Only on-topic posts may appear in camps or receipts.

## 19b. Industry specialist overreach

**Symptoms:** `@SKundojjala` (or other industry specialists) fill the brief with
off-domain hot takes, or generic macro opinions outside their lane.

**Do:** Domain-gate. Keep research-grade in-domain posts only. In broad discovery,
a light optional sample is fine; do not let specialists dominate. Do not add
new industry names mid-run without a high-bar domain label.

## 20. Hashtag count treated as an automatic allowlist drop

**Symptoms:** An allowlisted desk/research post is discarded solely because the
body has more than one `#hashtag` (e.g. a real YCC/rates take stamped
`#economy #markets #yields #bonds`). Or the opposite: a tag-soup promo from
the same handle is kept because the author is allowlisted.

**Do:** Hashtag count is a quality tell, not a kill. Keep allowlisted posts
whose free text is still a usable claim. Drop only if the post also devolves
into low quality (no thesis, engagement farming, promo/teaser, cheerleading).
Non-allowlist 2+ hashtag noise stays out of core. Equity mode: also apply
equity-file paywall-bait / cheerleading / media-promo drops. See
`credible-sources.md`.

## 21. Equity sleeve without equity allowlist

**Symptoms:** User asks about NVDA / Mag 7 / semis stock sentiment / company
thesis, but the run only queries macro Tier A and treats a random Fed take as
stock consensus.

**Do:** Load `credible-equity-sources.md`. Pulse and lattice **EQ-A** (then EQ-B
for drivers). Hard-filter core equity takes to EQ handles. When Temperature or
participant wording is requested, also load `equity-sentiment-panel.md` and keep
that weaker sample separate. State the evidence roles in the Filter line.

## 22. EQ-B alone defines the stock read

**Symptoms:** Only SemiAnalysis / Gurman / industry news assert positioning,
multiple, or risk/reward; EQ-A silent or split.

**Do:** Treat EQ-B as factual drivers ("what happened"). Soften or omit contested
market consensus. Prefer "EQ-A not yet weighing in" over industry-news consensus.

## 23. Forensic short treated as neutral forecast

**Symptoms:** Culper / Blue Orca / Bleecker / Wolfpack (etc.) thesis presented as
unbiased "the stock is broken" without labeling interest.

**Do:** Keep free-text math. Always attribute as activist/forensic short with
disclosed interest. Do not launder into neutral Tier A consensus.

## 24. Macro-only handle promoted into equity evidence

**Symptoms:** A macro strategist tweets NVDA once; synthesis treats them as
equity EQ-A because they are on the macro list.

**Do:** Do not. Core equity evidence requires the equity allowlist (or a labeled
user-requested exception). A registered sentiment-panel post may support only
its weaker role. Core-list overlap exists only when the handle appears on both
allowlists.

## 25. Supplementary list becomes the brief

**Symptoms:** Bare NBTQ (`list:209841180`) or InvQ (`list:960008892343246848`)
Latest floods with chart brands, short replies (InvQ), retail tips, or personal
chatter; those posts fill receipts or the primary sentiment read.

**Do:** Lists are **supplementary only** (max 1–2 filtered calls). Always use
`-filter:replies` + topic/macro tokens for the **root overview**; NBTQ prefers
`min_faves:3+`. Merge allowlisted authors only into the core sample. Route a
registered, eligible panel hit to the separate sentiment sample; other
non-allowlist hits trigger a core re-query or remain isolated context. Never let
list noise replace the hard allowlist or become an aggregate mood poll. For a
selected root, leave the list firehose and inspect its exact conversation. If
list lanes add nothing, omit List check or say "no additive signal after
filters." See
`references/supplementary-lists.md`.

## 26. Latest-only reply blindness

**Symptoms:** A popular root looks unanimous because `conversation_id` Latest
returned only the newest praise or jokes; an earlier correction is missing.

**Do:** Pair `x_thread_fetch` with a floor-free exact-conversation search. If a
material mid-thread node appears, time-box around it; check `filter:self_threads`
for author continuations. No single reply query is complete.

## 27. `to:` contamination

**Symptoms:** `to:{author} filter:replies` returns good-looking posts from
several unrelated conversations and they are attributed to the selected root.

**Do:** Use `to:` only as fallback and post-filter exact returned
`conversation_id == root_id`. Discard nodes whose edge cannot be established.

## 28. Engagement floor erases minority signal

**Symptoms:** `min_faves` produces a clean conversation but removes a
zero-like correction, quantitative caveat, or technical expert reply.

**Do:** Engagement is a discovery prior, not an evidence gate. Always pair a
precision-floor comparison with a floor-free exact-conversation lane. Rank
specificity, source role, evidence, and information gain separately.

## 29. Reply promoted without its edge

**Symptoms:** A sharp reply enters the brief with no root ID, relationship, or
independence label; the reader cannot tell whether it corroborates or disputes
the original claim.

**Do:** Preserve root and node IDs/URLs, relation class, author continuation
versus independent voice, why the node changes the read, and caveat. If the
edge is unknown, omit the node.

## 30. Coverage accounting drift

**Symptoms:** The brief claims five conversations were enriched but the search
log or table contains six roots; inspected, usable, and promoted counts are
mixed.

**Do:** Reconcile the funnel explicitly: inspected → candidate roots →
conversations enriched → promoted nodes. Count unique IDs once and keep
allowlisted core voices separate from lower-weight contextual replies.

## 31. Participant-native signal displaced by an analyst framework

**Symptoms:** A request for sentiment, live debate, or what market participants
are saying becomes a state machine or risk-governance memo. Attributed voices,
conversations, and changes of mind appear only in a late evidence ledger.

**Do:** Re-check the requested product. When participant discourse is central,
foreground the tape, attributed observations, disagreements, and revisions;
use verification to bound that read rather than replace it. An explicitly
research- or decision-oriented memo may remain fact-led. Do not force a fixed
number of camps, conversations, voices, or sections.

## 32. Compact answer repeats the evidence packet

**Symptoms:** The same claim appears in a sleeve list, a disagreement table,
and a receipt block; coverage accounting and negative checks occupy more space
than the market read; the output is shorter than an archive but still feels like
a trimmed catalog.

**Do:** Treat retrieval as private working material. Apply the deletion test,
then recompose from the survivors. Inline attribution and links are usually
enough for compact auditability. Surface funnel details or a distinct receipt
block only when they change confidence, add information, or the user requests
them. This is not a word limit or a fixed theme count.

## 33. Individual trade diary becomes consensus or verified performance

**Symptoms:** Several posts by one trader are counted as breadth; an intention is
described as a fill; claimed size or P&L is treated as verified; one current post
is narrated as a change without an earlier state.

**Do:** Treat the trajectory overlay as anecdotal same-author context only.
Preserve timestamps and label intention, order, claimed fill, holding, hedge,
add, trim, exit, or flat exactly. Require an origin plus a later update before
claiming a change. State that positions are self-reported when material, and do
not let one author establish consensus, facts, or performance.

## 34. Hindsight or an advisory funnel masquerades as a trader diary

**Symptoms:** The useful-looking evidence begins after the move, consists of
winning P&L screenshots or “called it” posts, omits losses/exits, or says paid
subscribers received the actionable trade first. Charts or alerts carry the
claim while the public text never states a position or reason.

**Do:** Require a public pre-outcome receipt and retain adverse updates,
invalidations, trims, and exits. Drop chart-only calls and retrospective track
records without an earlier receipt. Exclude the source from this role when the
free feed is mainly promotion or after-the-fact disclosure; do not reconstruct a
public history from paid-channel claims.

## 35. AI capex stands in for equity coverage

**Symptoms:** The report explains the AI-buildout mechanism but never connects
it to specific hyperscalers, semis, suppliers, or relative non-tech winners and
losers. Index breadth is presented as company commentary.

**Do:** Use `equity-retrieval.md`. Build a dynamic name map and a delta-ledger
row for each surviving company. Separately attempt broad tape, material
hyperscalers, semis/supply chain, two live non-tech lanes, trade expression,
and a blind equity harvest when the request is broad.

A related failure: a brief names a company that no query ever searches (10-06:
NVDA in the semis brief, while that lane's ticker queries named AMD, MRVL, STX
and WDC), or a required topic word hides the conversation that was actually
happening (the open `$META` query required capex/monetization/spend words). Pulse the names by ticker and company name
without topic words, and report each one searched, capped, unqueried or failed.

## 36. One mega-post stands in for multiple names or voices

**Symptoms:** A single long multi-name research post supplies most tickers,
quoted words, and conclusions, then is counted as source diversity or as enough
direct X text.

**Do:** One author is one voice. Summarize a long research dump and link it;
quote only wording whose phrasing carries signal. If one author supplies more
than half of promoted core name-level conclusions, rerun independent source
families or state the boundary. Apply the stricter sentiment-panel cap to
Temperature; raw quote-word share is not a quality target.

## 37. Broad Latest crowds out quiet equity specialists

**Symptoms:** A large `from:` OR batch or unfiltered Mag 7/cashtag Latest page is
dominated by one prolific handle, ticker spray, or high-engagement generalists;
missing specialists are treated as inactive.

**Do:** Split by source family, query missing handles in smaller batches, widen
only the quiet family when permitted, and run ticker-constrained allowlist
searches. Ranking starvation is not evidence of silence.

## 38. Root-only search marks a reply-led source inactive

**Symptoms:** `-filter:replies` or root-only discovery returns nothing for a
known specialist, so the source is dropped from the lane or candidate review.

**Do:** Search focused replies, quote-posts, and self-threads; recover the
parent/root edge and identify what the specialist added. Do not count a relay
or reply as independent corroboration of its parent.

## 39. Delta-only gate erases Temperature

**Symptoms:** The macro changes are well summarized, but unchanged, repeated,
casual, defensive, joking, or reluctant equity comments disappear because they
do not change the prior thesis.

**Do:** Build both ledgers. Score Delta and Temperature separately. Retain a
deduplicated repeated or unchanged tell when recurrence, ease, emotional
register, or lack of hedging is the evidence.

## 40. Quote volume masquerades as participant sampling

**Symptoms:** The report contains many blockquotes or reaches a target share of
direct text, but one author/mega-thread dominates and key stocks have no distinct
participant conversation.

**Do:** Remove the quote-share target. Check independent authors, evidence
roles, sleeves, names, conversation clusters, and paraphrase loss. Summarize
long research posts and shorten analyst prose instead of padding quotes.

## 41. Sentiment texture is laundered into a core claim

**Symptoms:** A probationary or off-list post supplies a company conclusion,
"professional consensus," a disputed level, or a market-wide prevalence claim.

**Do:** Reassign it to sentiment sample or context only and narrow the sentence.
Require EQ-A/EQ-B or the appropriate macro allowlist for the core claim. State
recurrence only within the labeled sentiment sample.

## 42. Open texture search becomes a retail firehose

**Symptoms:** Generic fear/greed slogans, ticker spray, memes, victory laps, or
engagement bait overwhelm smaller informed comments.

**Do:** Start with role-separated panel batches, one bounded non-tech harvest,
and one bounded open harvest. Apply the current-post gate, fetch dependencies,
and leave unregistered survivors as isolated context. More emotion is not a
better sentiment sample.

## 43. Latest tail is mistaken for the whole window

**Symptoms:** The final minutes or one prolific author dominate a busy Latest
result; earlier session phrasing and quieter participants vanish.

**Do:** Define one exact shared Pacific window. In Grok-native search, use
timestamped `_PDT`/`_PST` bounds and split a busy interval into adjacent 60-90
minute Pacific slices. Convert to UTC only for API-style exact-time parameters.
On other surfaces, use their supported bounds, split source batches, and
post-filter timestamps. Deduplicate IDs and compare unique-author coverage
before calling a source or register absent.

## 44. Delegated worker writes a report or archive

**Symptoms:** An xgrok/Grok retrieval worker creates `X-RESULTS/MACRO` files or
returns a polished full memo that competes with the parent synthesis.

**Do:** In delegated mode, return only the bounded evidence packet requested by
the parent: no more than six promoted receipts or 1,500 words unless the
parent's `Delegated budget:` line expands it, in one dense table with only
material coverage/gap notes. Create no archive, search diary, or full report.
The parent owns cross-lane analysis and final prose.

## 45. Sentiment is quarantined in Telling asides

**Symptoms:** The bottom line and company sections remain fact-led while the
best mood, action, and conversational clues appear only near the end as curios.

**Do:** Surface Tape temperature and dynamic key-stock conversations directly
after the bottom line/Delta table when the product warrants them. Reserve
Telling asides for genuine orphans.

## 46. Worker summaries flatten the signal

**Symptoms:** A worker returns "bullish," "bearish," or a thesis paraphrase but
omits the exact joke, hesitation, refusal, profanity, correction, or parent edge
that made the post useful.

**Do:** Require complete short text when the wording, action, or conversation
edge is the evidence. Otherwise allow a terse factual summary. Preserve author,
timestamp, ID/URL, dependencies, signal type, evidence role, register,
action/horizon, novelty/recurrence, independence, and paraphrase-loss reason in
a compact row. Unknown fields stay unknown.

## 47. Copied language masquerades as recurrence

**Symptoms:** Quote-posts, relays, self-threads, or replies in one conversation
are counted as independent people converging on the same mood.

**Do:** Trace the underlying post or research input. Count one author as one
voice and one shared information source as one recurrence cluster unless a
participant adds a genuinely independent interpretation or action.

## 48. Long roster-plus-keyword query drops the time bound

**Symptoms:** A query pairing a keyword OR-list with a `from:` roster of more
than four handles returns posts from weeks before `since:`; the leaked posts
enter the packet or the page is counted as coverage.

**Do:** Keep each query to one keyword group plus at most one four-handle
`from:` group, or split roster from keywords. When any returned post is
outside the bound, mark the query bound-failed in the Search log, drop the
leaked posts, do not count the page as coverage, and split the query.

## 49. Registry membership becomes a verdict in a delegated packet

**Symptoms:** A worker writes "off-list, so it does not confirm" or reports a
parent-named handle as "not queried" because the registry lacks it; the parent
loses evidence it asked for before it can weigh it.

**Do:** In delegated mode label provenance (`allowlist`, `panel`, `off-list`,
`parent roster`) and leave weight to the parent. Query every handle the parent
names. The hard-filter rules govern a direct run's synthesis, not retrieval.
