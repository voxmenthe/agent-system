# Source seeds and role routing for `/dlresearch`

These are **discovery priors, not an allowlist and not endorsements of every
post**. The goal is to learn useful vocabulary and find original roots, then
promote sources by the contribution in the fetched conversation.

Seeds are selected for two traits: they **regularly post** substantive
technical material, and they **engage in research-grade discussion** in
replies to others and in self-threads - not for fame or affiliation alone.

Maintain a handle as a durable seed only after a bounded own-feed check finds at
least two distinct substantive root conversations. Multiple nodes in one
self-thread count as one source event. A strong reply, graph adjacency, fame,
or an employer affiliation creates a candidate, not a seed.

Prefer evidence across multiple months - roughly one qualifying research event
per month over the account's recent active window. This is a guideline, not a
hard cutoff: unusually valuable lower-cadence specialists belong in the
lower-cadence table, while a dense one-month launch burst remains a candidate.

## Curated seeds - core research conversation

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| stochasticchasm | Close match - independent technical explainer | Long paper-breakdown self-threads, quantitative result anatomy, and observations on recent research directions | Always run `filter:self_threads`; root-only search can miss the load-bearing anatomy |
| kalomaze | Close match - training, architecture, and optimization critic | Architecture and optimizer comparisons, numerical scrutiny, and compact technical self-threads | Much of the signal is reply-shaped; verify the exact root relationship and demote short reactions without method detail. Query `from:kalomaze` in one-day bounds and add a `filter:replies` lane |
| aimalysheva | Close match - independent technical experimenter and explainer | Controlled representation or hidden-state experiments, explicit conditions, operational definitions, and confounds | Quote follow-ups or several nodes in one topic thread remain one source event |
| cwolferesearch | Close match - independent method explainer | Training-objective and algorithm anatomy, code-backed synthesis, iterative data methods, and contamination or failure analysis | Synthesis is not an independent reproduction or verification of the underlying paper |
| JJitsev | Complementary - evaluation and methodology critic | Benchmark confounds, contamination, baseline choice, metric construction, and open-stack comparisons | Politics and advocacy are mixed into the feed; route narrowly to technical evaluation critique |
| nrehiew_ | Close match - frontier-lab watcher and release-signal tracker (the handle previously seeded as "wh") | Early model-release signals, lab movements, and research commentary with receipts | Mixes scene signals and rumors with technical content; apply the full substance gate and keep rumor provenance explicit |
| _jasonwei | Close match - frontier researcher discussing methods and research practice (Meta Superintelligence Labs; prev OpenAI, Google) | Emergence/reasoning threads, research-process insights, substantive reply exchanges | Meta-commentary and career advice mixed in; route narrowly to technical content |
| stellaathena | Close match - open-research practitioner (EleutherAI) | LLM evaluation methodology, licensing/data analysis, dense reply-thread debates | Strong opinions delivered casually; extract the technical claim, not the tone |
| rasbt | Adjacent - structured paper breakdowns and LLM-method summaries | Multi-post paper anatomies with conditions and limitations | Explainer, not originator; treat as interpretation unless he shows his own experiment |
| BlackHC | Complementary - Bayesian deep learning, active learning, continual learning (Andreas Kirsch) | Theory-flavored explainers, sample-efficient continual learning discussion, paper follow-ups | Theory register; separate proposal from measured result |
| HeMuyu0327 | Close match - training-dynamics experimenter (Muyu He) | Unpublished observations, gated/residual-stream experiments, mechanism-first follow-ups | Work-in-progress framing; conditions may be preliminary |
| huskydogewoof | Close match - loop-model experimenter and independent replicator | Matched-compute recurrent-model ablations, full-test-set reruns, bootstrap intervals, and protocol or benchmark audits | Interested source on his own loop-model work; culture posts are mixed in, and a later rerun may revise an earlier interpretation |
| 0xjasper | Complementary - representation-learning and interpretability researcher (Jasper Gilley) | Forward self-models, hierarchical feature learning, controlled-grammar tests, and RL-induced representation changes | Some claims are prospective or blog-first; require the completed experiment or artifact before treating a mechanism thesis as a finding |
| giffmana | Complementary - literature-memory and methodology critic (Lucas Beyer) | Baseline hygiene, architecture sensitivity, older vision/SSL precedents, and corrections to paper genealogy | Technical signal is buried under social and product posts; literature context is not a new experiment or independent replication |
| a1zhang | Complementary - agent-harness and learned-system architecture researcher (Alex Zhang) | Trained harnesses as non-differentiable architectures, model-harness co-adaptation, and general-purpose versus task-specific scaffolds | Added from a surfaced harness discussion at user direction; own-feed recurrence was not re-audited, so require a substantive current root before weighting |

## Curated seeds - high-signal, lower-cadence researchers

These handles cleared the two-event bar but did not show the regular multi-month
cadence preferred above. Route them when the topic matches instead of spending
open-scan budget on every handle.

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| evangelinejy99 | Researcher | discussions about research papers | TBD |
| JessicaRumbelow | Lower-cadence interpretability method researcher | Exemplar partitioning, activation-space submanifolds, steerable paths, and compute comparisons with SAEs | Recent evidence is two events in one research program; interested author, not an independent comparison |
| klindt_david | Lower-cadence theory and identifiability researcher (David Klindt) | JEPA identifiability, dictionary-learning and SAE theory, compressed-sensing arguments, and formally checked results | Academic announcements and broader science commentary are mixed in; theory claims still require the paper |
| KuangYilun | Lower-cadence JEPA and world-model researcher (Yilun Kuang) | Sparse latent dynamics, distributional regularization, predictor-capacity comparisons, and planning boundaries | Widely spaced own-paper launches; treat X results as interested author claims |
| ChengsongH31219 | Lower-cadence RL-environment and feedback-method author | G-Zero hint-leakage controls, EnvHarness environment wrappers, reward construction, and environment scaling | Launch rhetoric and collaborator amplification are common; count each paper thread once and seek independent evaluation |
| AryaTschand | Lower-cadence kernel-codegen and agent-evaluation researcher | JAXBench, Hawkeye kernel search, hardware-native primitive use, and harness/evaluation design | Social and sports-agent posts are mixed in; recover missing root text before weighting self-thread numbers |
| qubitium | Lower-cadence quantization and inference implementer | KLD-vs-task-accuracy failures, low-bit recovery limits, CPU/GPU kernel comparisons, and MoE compatibility breakage | High non-research and release-note volume; interested source on GPT-QModel, and implementation evidence is not paper verification |

## Curated seeds - frontier labs, post-training, and RL

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| natolambert | Post-training and RLHF analyst (Interconnects) | Technical release dissections, preference/RL method comparisons, eval critiques | Newsletter promotion mixed in; separate analysis from announcement |
| Grad62304977 | Close match - RL and post-training researcher (Prime Intellect) | Paper dissection of RL recipes (PPO/GRPO variants, IcePop/DIS), trainer-system tradeoffs, dense self-reply continuations | Much signal lives in replies and continuations; recover full conversation context |
| willccbb | RL and post-training research (verifiers, GRPO-style work) | Measured RL experiments, reward design, open recipes | Heavy shitposting and promo; filter aggressively |
| YouJiacheng | Training, data, and RL recipe observations | Scaling observations, objective details, reproduction notes | Often reply-shaped; recover the root context |
| ArthurConmy | Mechanistic interpretability moving into post-training (Anthropic) | Circuit-analysis results, latent-CoT interpretation, alignment-relevant findings | Interested-party perspective on his lab's work |
| Tim_Dettmers | Efficient training and quantization researcher | Bit-precision analysis, memory/throughput tradeoffs, hardware-aware method critiques | Lower posting volume; check whether claims carry numbers |
| OfirPress | Long-context and evaluation researcher | Context-length methods, benchmark construction, position-encoding work | Academic-announcement mode around his own papers |
| QPHutu | Close match - critic/value-method and long-horizon RL researcher (Penghui Qi) | DPPO/BPCO implementation ablations, privileged-critic inputs, PPO-vs-GRPO variance arguments, and rollout-efficiency comparisons | Interested author on his own methods; apparent changes of view may concern different failure regimes, so preserve chronology and conditions |
| DevShaheen1 | Complementary - RLVR experimenter and representation-analysis author | Small-model GRPO runs with exact setup, response-length dynamics, PPO anatomy, and post-RL decodability or geometry changes | Career and explainer posts are mixed in; several updates on one run remain one event |
| jaseweston | Close match - lab author on agent memory, self-improvement, and evals (Meta FAIR) | Numbered harness and memory comparisons; discover-then-distill recipes; author threads with ablation-style result posts | Lab launch threads are interested-author claims; charts carry numbers; the feed mixes reposts, so use `-filter:nativeretweets` |
| mefatemi | Close match - lab author on RL reward design (Snorkel) | Zero-advantage diagnostics, gated or partial-credit GRPO, numbered self-threads that link a blog | The two qualifying events are one research line; blog-linked claims are unchecked lab claims; `filter:self_threads` can miss the root, so also run `-filter:nativeretweets` |
| hyuncho_1905 | Candidate-strength lab researcher on rubric RL, reward hacking, and trained reviewers | Component ablations, grader swaps, scale checks | Numbers are mostly image-carried; the FORK root states no number in text |

## Curated seeds - scaling, evals, and progress analysis

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| sea_snell | Test-time/inference-scaling researcher (Berkeley PhD) | Compute-optimal inference, agent evaluation design, sleep-time/offline compute | Low frequency but load-bearing when active |
| nearcyan | Careful AI-progress and scaling synthesis | Cross-paper progress arguments, compute trends, calibrated uncertainty | Broad takes rather than single-paper anatomy |
| BerenMillidge_ | Deep-learning theory and scaling debate | Loss-of-plasticity, in-context learning theory, scaling-law critiques | Opinionated; verify claims against linked work |

## Curated seeds - interpretability and safety

`@neelNanda5` remains the field anchor, but the working researchers below
usually carry more current detail.

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| can_rager | Close match - independent mechanistic interpretability researcher (ex-NEEL Nanda collaborator circle) | Feature-extraction/SAE results, dictionary-learning anatomy, replication notes | Independent-researcher constraints; artifacts may be early-stage |
| loganriggssmith | Complementary - independent interp researcher (SAE dark-matter co-author) | SAE failure modes, decomposition quality, eval-of-interp-methods threads | Exploratory framing; distinguish hypothesis from finding |
| saprmarks | Close match - interpretability method and evaluation author (Samuel Marks) | NLAs, model-state and behavior explanations, negative eval results, quantitative controls, and limitation-heavy author replies | Interested Anthropic source; author explanation is not independent validation, and quote commentary can be lighter than own-method threads |
| Arnauya | Complementary - weight-level and cross-domain mechanistic interpretability researcher | Per-weight ablation with KL or delta-cross-entropy, describable-weight tests, sparse-vs-dense comparisons, and neuron-to-language work | Own-preprint perspective; neuroscience and language-model work coexist, and reply-shaped claims require their root context |
| zer0int1 | Close match - independent CLIP-circuit experimenter | SAE/transcoder circuits, typographic-attack controls, causal filter ablations, register sinks, and named-paper reproductions | Narrow CLIP focus and informal lab-notebook style; verified activity is recent, so recheck if the feed goes quiet |

## Curated seeds - architecture, systems, and implementation

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| _xjdr | Attention/optimizer internals expert | Long contrarian technical threads on architectures, numerics, and training dynamics | Abrasive style; extract mechanism claims, discard rhetoric |
| main_horse | GPU kernels and performance forensics | Roofline analyses, kernel benchmarks, claimed-speedup audits | Terse posts assume context; recover quoted roots |
| cloneofsimo | Generative-model research engineer | Flow matching, diffusion speedups, sampler math with code | Implementation-first; distinguish measured result from proposal |
| Smerity | Architecture history and data curation | Method genealogies, dataset provenance, sharp methodological critiques | Essay-length; summarize and quote only signal-bearing wording |
| vicenteolea | Distributed-training and HPC performance | Parallelism strategy analysis, communication-overhead measurements | Narrow infra focus; off-domain posts otherwise |
| cHHilleh | GPU performance engineering (NVIDIA stack) | Hardware-behavior explanations, throughput forensics | Industry-benchmark framing; conditions may be vendor-specific |
| sgugger | Paper-to-code implementations (HF) | Training/quantization implementation notes, correctness caveats | Vendor-adjacent; implementation is not independent verification |
| pcuenq | Multimodal and diffusion implementations (HF) | Model-porting notes, numerical-difference investigations | Vendor-adjacent; same caveat as sgugger |
| reach_vb | Training and multimodal engineering | Data-pipeline and training-run observations | Vendor announcements mixed in; filter to substance |
| minimaxir | Measured small-scale LLM experimentation | Controlled prompting/fine-tuning experiments, data work | Applied framing and blog-length posts; summarize long form |
| johnowhitaker | Applied generative-models practitioner | Notebook-style explanations, quick replications, visualizations | Breadth over depth; treat as demonstration, not validation |
| fleetwood___ | Candidate - unknown fit | tbd | **Unverified seed:** web lookup could not confirm this handle maps to the intended account. Before weighting its posts, run one bounded `x_user_search` on `fleetwood___`; if it does not match expectations, report the gap and do not substitute silently |
| dhruv31415 | Close match - optimizer and architecture experimenter | Residual-free Transformers, sparse-computation estimators, optimizer-geometry attribution, causal interventions, and latent recurrence | Personal-blog and small-scale experiments may be preliminary; separate theoretical design arguments from measured results |
| Shiwei_Liu66 | Complementary - optimizer and diffusion-language-model author | Layerwise learning rates, layer-collapse diagnostics, NAP/d-OPSD training methods, and AdamW-vs-Muon conditions | Own/lab paper stream with workshop and travel noise; seek independent replication of claimed speedups or benchmark gains |
| elliotarledge | Close match - GPU RL-environment and kernel-evaluation practitioner | Netherite environment internals, KernelBench-Hard, roofline-relative scores, matched baselines, and agent-generated kernels | Severe joke, travel, and career-post dilution; route narrowly to environment, CUDA, benchmark, and harness terms |
| jackcai1206 | Close match - paper author on distillation and KV compaction | Method threads with a matched-budget baseline, keep ratios, speed measurements | Pair the account's roots with replication lanes: @pratyushmaini reversed one result for pretrained students within a day. Thread bodies were not opened |
| Xinyu2ML | Peer critic and idea author on long-context attention and inference cost | Cost-fairness critiques (prefill vs decode), recursive or logarithmic attention, kernel notes | Original feed is mostly reposts, so use `-filter:nativeretweets`. Both qualifying events fall in one week (2026-11-14 and 11-19); recheck for an event in a later month before treating the cadence as regular |

## Curated seeds - regional and aggregation

| Handle | Fit and seed role | What to look for | Required caution |
|--------|-------------------|------------------|------------------|
| zartbotF | Occasional posts | tbd | |
| ZhihuFrontier | Excellent articles | Sometimes may need the original Mandarin version on the ZhiHu website, which might not be possible | |
| rosinality | Recurring technical curator and compact method explainer | Concise mechanism or benchmark notes across RL environments, evals, optimization, architecture, and MoE systems | Curation is a discovery lane, not original analysis or independent corroboration; trace every claim to the underlying author or paper |

Do not make these handles mandatory sources. They may be quiet, outside the
window, or off-topic. Some legacy handles were curated largely without live X
verification; when a handle appears renamed, empty, or mismatched, use one
`x_user_search` to diagnose and report the gap instead of guessing a
substitute.

## Dynamic source routing

After a candidate paper appears, search for role diversity:

1. **Paper/lab author** - title/method root and author continuation
2. **Independent technical explainer** - mechanism and prior-work context
3. **Peer expert** - specific correction, extension, or field boundary
4. **Replicator/practitioner** - code, setup, measured reproduction, failure
5. **Critic** - confound, leakage, missing baseline/ablation
6. **Aggregator/news account** - discovery only unless it links primary material

Prefer the closest primary role for what the work claims and independent roles
for whether the interpretation survives. A viral explainer can be more visible
than the paper author without becoming stronger evidence.

## High-signal thread traits

Promote roots and continuations that contain several of:

- unambiguous paper/report identity
- concrete method, objective, architecture, data, or training detail
- numeric result with benchmark/condition
- comparison to a serious baseline
- pre-stated expectation or mechanism
- limitation, missing ablation, confound, or falsifying condition
- technical author continuation
- independent correction or reproduction

Low-signal traits:

- title/abstract paraphrase only
- `huge if true` / `game changer` without mechanism
- leaderboard number with no setup
- popularity as proof
- question treated as refutation
- many derivative summaries from the same source chain
