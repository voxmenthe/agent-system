# AI participant allowlist for `/convo`

This file is the **hard conversation-eligibility source of truth**. A
conversation qualifies only when at least one substantive root, reply in the
exact conversation, or exactly linked quote post is authored by a handle below.
It applies only to the **AI** topic area selected by `SKILL.md`.
Promotion as a best conversation still requires at least two substantive,
exactly linked nodes under the shared `/convo` contract.

Normalize a returned author by stripping a leading `@` and comparing the handle
case-insensitively. Do not fuzzy-match, infer renamed accounts, or treat a
mention as participation.

## Allowlisted participants

| Handle | Research signal to keep | Post-level caution |
|--------|-------------------------|--------------------|
| stochasticchasm | Deep-learning paper anatomy, quantitative results, research directions | Search replies and self-threads; keep method/result/boundary content |
| kalomaze | Training, architecture, optimization, and numerical scrutiny | Much of the signal is reply-shaped; drop short reactions without technical content |
| aimalysheva | Controlled representation or hidden-state experiments, conditions, confounds | Several nodes in one self-thread remain one source chain |
| cwolferesearch | Training objectives, algorithms, code-backed synthesis, contamination and failure analysis | Synthesis is interpretation unless an independent reproduction is shown |
| elliotarledge | CUDA, RL, systems implementation, measured throughput, reward-hacking audits | Broader build feed is noisy; keep experiments with setup, result, or boundary |
| JJitsev | Evaluation, benchmark confounds, contamination, baselines, open-stack comparisons | Politics and advocacy are mixed into the feed; keep AI/research content only |
| nrehiew_ | Deep-learning research discussion and technical conversation discovery | Apply the full topic and substance gate; do not promote vague reactions |
| lateinteraction | Deep-learning research & agents discussions | tbd |
| HamelHusain | evals and agentic workflows | tbd |
| dexhorthy | agentic workflows | tbd |
| willccbb | RL research and techniques | Does a lot of shitposting and promotional stuff so needs heavy filtering |
| dwarkesh_sp | conversations on AI futurism and development | posts about a lot of other stuff too so needs heavy filtering |
| swyx | extensive conversations about a variety of topics - filter to just ai / agents / llm and further filter to substantive and insightful conversations |
| dlbydq | anything ai-related | don't filter too heavily |
| 1a3orn | anything ai-related | tbd |
| YouJiacheng | research-focused conversations | tbd |

## Eligibility semantics

**Qualifies:**

- allowlisted account starts an on-topic root
- off-list account starts a root and an allowlisted account posts a substantive
  on-topic reply in its exact conversation
- an allowlisted self-reply materially continues an on-topic thread
- an allowlisted substantive quote post has an exact returned link to its
  on-topic quoted root and the relation is labeled `quote`

**Does not qualify:**

- the root merely mentions or tags an allowlisted account
- an allowlisted account liked, reposted, or followed the author
- the only allowlisted node is `lol`, an emoji, generic praise, a tag, or
  another noise-only reaction
- the relationship is guessed from topical similarity rather than verified
  with returned root/conversation metadata

Once eligibility is established, substantive off-list roots and replies may be
summarized or quoted as labeled context. The allowlist gates the conversation;
it does not erase the rest of the exchange or certify any participant's claim.

## Maintenance

- Prefer a short, explicit list over dynamic expansion.
- A handle named by the user for one run is a labeled temporary exception.
- Change this file only when the user asks to persist an addition, removal, or
  correction.
- When a handle appears renamed or empty, use one `x_user_search` to diagnose
  the current run and report the gap. Do not silently rewrite the allowlist.
