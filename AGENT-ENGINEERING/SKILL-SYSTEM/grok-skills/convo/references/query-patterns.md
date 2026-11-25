# X query patterns for `/convo`

Discover **allowlisted participation first**, including replies. Recover and
rank exact conversations second. Keep one variable loose per query so it is
clear which lane found a candidate.

## Contents

- Core operators and selected participant batches
- Participation-first pulse and topic lanes
- Root, quote-post, and semantic recovery
- Search logging and stopping rules

## Core operators

| Operator | Use |
|----------|-----|
| `from:{handle}` | Required participant anchor |
| `from:a OR from:b` | Batch exact allowlisted handles |
| `filter:replies` | Find allowlisted participation in off-list roots |
| `filter:self_threads` | Recover technical author continuations |
| `filter:quote` | Find quote-post framing; verify the underlying conversation separately |
| `conversation_id:{root_id}` | Inspect one selected exact conversation |
| `since:` / `until:` | Calendar bounds and local reply time boxes |
| `within_time:Nh` | Exact trailing-hour window when supported |
| `min_faves:N` | Optional late precision comparison, never an eligibility or evidence gate |

If an operator errors, simplify once. Do not invent syntax or retry a rejected
operator repeatedly.

## Selected participant batches

Build expressions from the exact handles in the topic-selected participant
file:

```text
(from:{exact_handle_1} OR from:{exact_handle_2} OR ...)
```

Do not maintain a second handle list in this file. If the expression exceeds a
tool limit, partition it into stable batches and union the results. For
`participants-macro-equities.md`, use its lane labels to select relevant
batches rather than querying every handle. The batches return possible
allowlisted authors, but still verify every returned handle against the exact
topic file selected for that conversation.

## Participation-first pulse

Do not exclude replies:

```text
({participant_batch}) since:{bound}
```

Mode: `Latest`. Start with a modest result limit. Apply topic and noise filters
after retrieval.

Run a reply-specific comparison because reply participation is central:

```text
({participant_batch}) filter:replies since:{bound}
```

An allowlisted reply is a candidate anchor, not yet a grounded conversation.
Use its returned `conversation_id` or `x_thread_fetch` to recover the root.

## Topic lanes

Split broad vocabulary into smaller queries in practice.

### AI - research and methods

```text
({participant_batch}) (paper OR preprint OR method OR training OR inference OR
architecture OR optimizer OR scaling OR distillation OR reasoning OR benchmark
OR evaluation OR ablation OR replication) since:{bound}
```

### AI - interpretability, safety, and agents

```text
({participant_batch}) (interpretability OR mechanistic OR representation OR
alignment OR safety OR agents OR robotics OR multimodal OR reward OR
"test-time compute") since:{bound}
```

### AI - frontier labs and models

```text
({participant_batch}) (OpenAI OR Anthropic OR DeepMind OR xAI OR Meta OR
"frontier lab" OR model OR checkpoint OR release OR launch OR training OR
capability OR eval OR departure OR hired OR leak OR rumor) since:{bound}
```

These terms find candidates, not facts. Apply the gossip/source-status rules
after conversation enrichment.

### Macro - central banks, data, rates, and labor

```text
({participant_batch}) (FOMC OR Fed OR ECB OR "central bank" OR CPI OR PCE OR
payrolls OR inflation OR unemployment OR rates OR yields OR "term premium" OR
Treasury OR curve) since:{bound}
```

### Macro - FX, credit, commodities, and cross-asset transmission

```text
({participant_batch}) (FX OR dollar OR DXY OR EURUSD OR credit OR spreads OR
CDS OR liquidity OR oil OR energy OR commodities OR volatility OR
"financial conditions") since:{bound}
```

### Equities - companies, estimates, earnings, and valuation

```text
({participant_batch}) ("{company_name}" OR ${ticker} OR earnings OR guidance OR
revenue OR margin OR EPS OR estimates OR valuation OR multiple OR catalyst OR
positioning OR capex OR FCF) since:{bound}
```

### Equities - flows, options, and market structure

```text
({participant_batch}) (SPX OR SPY OR QQQ OR flow OR positioning OR gamma OR
vanna OR skew OR volatility OR dispersion OR breadth OR dealer) since:{bound}
```

Markets terms surface candidates, not verified market facts. Keep company and
asset identifiers exact, label proprietary positioning estimates, and apply the
participant file's domain and bias cautions after enrichment.

### Named topic

```text
({participant_batch}) ("{distinctive title, model, lab, method, company,
event, asset, or instrument}" OR
{specific_alias}) since:{bound}
```

Keep the primary entity in every topic lane. Do not use broad `AI`, `AGI`,
`LLM`, `markets`, or `stocks` alone when a precise anchor exists.

## Root and conversation recovery

For a promising allowlisted root or reply:

1. Record the allowlisted node ID, author, URL, timestamp, and returned
   `conversation_id`.
2. Run `x_thread_fetch` on that node.
3. Resolve the root ID and confirm the allowlisted node belongs to it.
4. Run:

```text
conversation_id:{root_id}
```

Mode: `Latest`, floor-free.

5. Recover author continuations when useful:

```text
conversation_id:{root_id} filter:self_threads
```

6. If a known correction falls outside the Latest cap:

```text
conversation_id:{root_id} since:{lower_day} until:{upper_day}
```

7. Use one engagement comparison only after the floor-free lane:

```text
conversation_id:{root_id} min_faves:2
```

8. Use `to:{root_author} filter:replies` only as fallback. Keep only returned
   nodes whose exact `conversation_id` equals the selected root.

A conversation is enriched only after thread fetch plus the floor-free exact
conversation query. Deduplicate candidates by exact conversation/root ID.

## Quote-post lane

An allowlisted quote post can surface an important discussion:

```text
({participant_batch}) filter:quote since:{bound}
```

Treat the quote post and quoted root as a linked branch, not automatically one
reply conversation. The branch qualifies when the allowlisted quote text is
substantive and on-topic; preserve both node IDs/URLs and label the relation
`quote`.

## Semantic lane

Semantic search is not participant-scoped. Use it only as a late recall aid:

1. Search a precise technical, lab/model, macro-event, company, asset, or
   market-mechanism topic.
2. Do not retain a result merely because it resembles an allowlisted view.
3. Ground it to an exact conversation containing a qualifying allowlisted
   node, or drop it.

## Search log

Track:

| Field | Example |
|-------|---------|
| Lane | participant pulse / replies / topic / self-thread / conversation |
| Query or node ID | exact query, allowlisted anchor ID, or root ID |
| Returned | approximate count |
| New conversations | count after root-ID dedupe |
| Kept | candidate or promoted conversation IDs |
| Drop reason | off-topic / noise / no allowlisted edge / duplicate / outside window |

Stop broad discovery when 2-5 strong conversations cover distinct themes and a
new query mostly repeats known root IDs. Stop a conversation when roughly 70%
of returned IDs are duplicates and no new substantive relation appears.
