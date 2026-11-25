# WSJ Research Playbook

## Broad current-news brief

Use two lenses:

1. **Homepage:** what WSJ editors rank and frame as important.
2. **Latest Headlines:** what has just changed, including smaller market and
   company developments.

Suggested process:

1. Collect 30–50 items from both surfaces. If the window is longer than
   Latest Headlines covers (about a day on weekends), add a section-page sweep
   so Friday-evening and Saturday stories are not missed.
2. Deduplicate canonical URLs.
3. Group into macro/policy, markets, companies, technology, world, and other
   material themes.
4. Note homepage position, recurrence across the two feeds, recency, and whether
   the item is Opinion or live coverage.
5. Read the top two or three stories in each dominant theme plus surprising
   outliers.
6. Produce:
   - the news agenda in one paragraph
   - 3–6 dominant themes
   - important fresh developments
   - contradictions or unresolved questions
   - a short watch list

Do not convert repeated headlines into a false consensus. Several stories can
derive from one event.

## Across-time topic research

### 1. Define the intersection

Translate the request into explicit dimensions. For the example intersection
of AI financing, company listings, demand, and hyperscaler capex:

| Dimension | Example concepts |
|---|---|
| Capital supply | project finance, bonds, private credit, guarantees, joint ventures |
| AI firms | OpenAI, Anthropic, CoreWeave, xAI, Nvidia, data-center developers |
| Public markets | IPO, listing, valuation, shares, debt pricing, investor demand |
| Buyer spend | Microsoft, Meta, Alphabet, Amazon, Oracle, Mag 7, hyperscaler capex |
| Demand evidence | cloud growth, backlog, utilization, inference demand, customer commitments |
| Constraints | power, chips, construction, rates, free cash flow, grid interconnection |

### 2. Build query baskets

Prefer multiple focused searches over one giant query:

- `"AI data center" financing`
- `OpenAI funding data center`
- `CoreWeave debt IPO`
- `AI company listing valuation`
- `Meta Microsoft Alphabet Amazon AI capex`
- `cloud AI demand backlog`
- `AI infrastructure private credit`
- `data center power constraint`

WSJ search appears relevance-oriented and does not guarantee Boolean operators.
Quotation marks can focus vocabulary but should not be treated as a formal
exact-match contract.

### 3. Use staged retrieval

1. **Vocabulary pass:** all time + relevance, two to four pages per query.
2. **Chronology pass:** newest-first or oldest-first with exact date bounds.
3. **Gap pass:** query named companies, financing instruments, or turning points
   missing from the initial timeline.
4. **Contradiction pass:** search for terms such as slowdown, write-down,
   shortage, canceled, delayed, higher costs, excess capacity, or weak demand.

If output says `truncated: true`, increase the page cap or narrow the query. A
relevance-sorted page cap is not an exhaustive historical corpus.

### 4. Select anchor articles

Search summaries are candidate signals. Open articles that:

- introduce a financing mechanism or major transaction
- quantify capex, debt, valuation, revenue, backlog, or power
- mark a change in management guidance or market pricing
- connect two or more dimensions
- contradict the prevailing narrative
- update or correct an earlier story

### 5. Build the evidence matrix

For each material article, capture:

| Field | What to record |
|---|---|
| Date | published and updated timestamps |
| Story | linked title and section |
| Event | what changed |
| Capital | source, structure, amount, price/cost |
| Spender or buyer | entity making the commitment |
| Demand evidence | reported usage, revenue, backlog, customers |
| Constraint | power, chips, rates, construction, cash flow |
| Market signal | valuation, yield, share move, IPO/listing status |
| Confidence | reported fact, attributed forecast, or inference |

Deduplicate by canonical URL. Keep updates in chronological order.

### 6. Synthesize, do not inventory

Answer:

- What changed over time?
- Which capital sources expanded or became more expensive?
- Did demand evidence keep pace with infrastructure commitments?
- How did public-market signals differ from private financing?
- Which companies transferred risk to partners, lenders, or investors?
- Where does WSJ coverage contain tension rather than resolution?

State inferences explicitly. Link claims to the smallest sufficient set of WSJ
articles and keep quotations short.
