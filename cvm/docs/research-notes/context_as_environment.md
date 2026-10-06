# Context as Environment: Bounded-Context LLM Systems over Large Inputs/Environments (2024-2026) and Overlap with CVM

Method note: arxiv.org, huggingface.co, alphaxiv.org, alexzhang13.github.io, rlm.md and papers.cool were all blocked by the network egress proxy in this session. Many paper-level details below therefore come from search-engine snippets of the arXiv/proceedings pages (URLs given are the pages the snippets came from) rather than full-text reads. Primary pages fetched in full: github.com/MIT-MI/MEM1 and anthropic.com/engineering/effective-context-engineering-for-ai-agents. Claims drawn from snippets should be checked against the PDFs before being quoted in a final report.

## Q1. Recursive Language Models (RLM, Zhang & Khattab): mechanism, scale, what is measured

### Takeaway
RLM is the best-known "prompt as environment" approach. The long input is stored as a variable in a Python REPL, and the root model writes code to peek at it, chunk it and recursively call sub-LMs. RLM reports accuracy and cost on inputs of 10M+ tokens. It does not appear to claim a fixed bound on the root model's own context, or to measure root-context size against input size the way CVM does (flat ~2k tokens from 1e3 to 1e6 objects).

### Cited Findings
- Authors: Alex L. Zhang and Omar Khattab (MIT). Released as a blog/tweet in Oct 2025, then arXiv 2512.24601 (Dec 2025) — [X post](https://x.com/a1zhang/status/1978469116542337259); [arXiv](https://arxiv.org/pdf/2512.24601)
- Mechanism: an inference-time paradigm that "decouples input length from the model's physical context window." The input is treated as an external variable in a Python REPL, and the model writes code to inspect it, chunk it and recursively query sub-instances of itself — [ArXivIQ summary](https://arxiviq.substack.com/p/recursive-language-models); [hyper.ai](https://hyper.ai/en/papers/2512.24601)
- Scale: "effectively unlimited input lengths (10M+ tokens tested)" — [Maxim blog](https://www.getmaxim.ai/blog/breaking-the-context-window-how-recursive-language-models-handle-infinite-input/)
- OOLONG: RLM(GPT-5-mini) beats GPT-5 by more than 110% on 132k-token inputs and is cheaper per query on average. RLM beats vanilla GPT-5 by 28.4% on the linear-complexity OOLONG task at comparable cost — [Maxim blog](https://www.getmaxim.ai/blog/breaking-the-context-window-how-recursive-language-models-handle-infinite-input/)
- BrowseComp-Plus: with 1,000 documents (~5M+ tokens), RLM(GPT-5) reached 100% accuracy (as reported by the secondary summary) — [Maxim blog](https://www.getmaxim.ai/blog/breaking-the-context-window-how-recursive-language-models-handle-infinite-input/)

### Inferences
- What RLM measures: task accuracy and dollar cost as input length grows (documents or tokens). The independent variable is input size, as in CVM. From the material I could access, the reported dependent variables are accuracy and cost, not peak tokens in the root model's prompt.
- Differences from CVM's design:
  - RLM's root model keeps a growing multi-turn REPL trajectory, so it is not stateless per step.
  - The program state lives in Python variables written by the model. There is no runtime-owned resident set with LRU eviction.
  - Sub-calls fan out recursively instead of the model emitting one op per step.
- Overlap: both treat the external input as an environment that the model queries through code or ops, never loading it whole. On the "context as environment" framing, CVM is not novel; RLM (and Scroll, Q2) got there first.

### Gaps
- I could not open the full RLM paper or blog (blocked), so three things are unverified: whether the root LM context is bounded or truncated, how REPL output is truncated, whether a no-sub-call ablation exists, and the details of the post-trained small RLM model. Flagged as unverified; check the arXiv PDF.
- The "100% on BrowseComp-Plus 1000 docs" figure comes from a secondary blog and should be checked against the paper's tables.

## Q2. Closest prior work: context folding, AgentFold, ReSum, MEM1, InftyThink, ACM, Scroll, and others

### Takeaway
The closest prior work is **Scroll** ("Context as an Environment: Programmatic Context Management for Long-Horizon Agents," arXiv 2608.21690, Aug 2026). It has a budgeted working view, evicts stale spans when the view nears that budget, keeps evicted content recoverable via an "eviction index" tied to exact log addresses, and lets model-written code materialize state. On "bounded resident view + eviction + re-materialization," it overlaps CVM heavily. **MEM1** is the closest on "stateless per step, the prompt is the state, model-written internal state." Most other work (AgentFold, ReSum, ACM, ContextPilot, InftyThink, Anthropic compaction) bounds context through summarization or folding of the agent's *history*, not through paging of a large *environment*.

### Cited Findings
**Scroll (closest overall)**
- Title and authors: Yin Lin, Elaine Ang, Erkang Zhu, Bolin Ding, Jingren Zhou. Submitted Aug 2026 — [arXiv abs](https://arxiv.org/abs/2608.21690)
- It frames long-horizon context management as choosing, at each step, "a working view over a persistent Session Environment" backed by an append-only Event Log and a sandboxed, persistent Python kernel. The model issues `exec` actions to search and expand the log — [arXiv html](https://arxiv.org/html/2608.21690)
- "Only explicitly printed projections enter the model's working view for the next call. As the working view approaches its budget, stale spans are evicted but remain recoverable: an eviction index keeps compact landmarks tied to exact Event Log addresses" — search snippet of [awesomepapers / arXiv](https://arxiv.org/abs/2608.21690)
- Results with Qwen3.8-Max: 94.8% on LongMemEval_S; 73.1% on BEAM_10M (+5.1 points over the best published memory system); 86.7% on LOCA_256K (+37.4 points over the best published long-horizon agent) — same snippet source; code at [GitHub QwenPaw scroll-research branch](https://github.com/niceIrene/QwenPaw/tree/scroll-research)

**MEM1 (closest on stateless-per-step / constant memory)**
- An end-to-end RL framework for constant memory over long multi-turn tasks. At each turn the agent writes an internal state (`<IS>` tags) that merges prior memory with the new observation. It "learns to discard the previous context (except for the prompt and initial query) immediately after generating a new internal state" — [arXiv html v2](https://arxiv.org/html/2506.15841v2); [GitHub](https://github.com/MIT-MI/MEM1)
- What is measured: peak token usage, dependency and inference time against the **number of objectives (2 to 16)**, i.e. horizon length. MEM1's peak tokens stay "almost constant," while baselines grow roughly linearly — [ICLR 2026 paper](https://proceedings.iclr.cc/paper_files/paper/2026/file/5fc8b3bdfbb9167b5144df5d3fae4616-Paper-Conference.pdf); [arXiv](https://arxiv.org/html/2506.15841v2)
- On 16-objective multi-hop QA, MEM1-7B scores 3.5x higher and uses 3.7x less memory than Qwen2.5-14B-Instruct. It was trained on 2-objective tasks and generalizes to 16 — [arXiv abs](https://arxiv.org/abs/2506.15841); [GitHub](https://github.com/MIT-MI/MEM1)
- On WebShop it beats AgentLM with 2.8x better peak token usage, 1.9x better dependency and 1.5x better inference time — [arXiv html v2](https://arxiv.org/html/2506.15841v2)
- Environments: internal retrieval QA, open-domain web QA and WebShop. Accepted at ICLR 2026 — [GitHub](https://github.com/MIT-MI/MEM1); [ICLR poster](https://iclr.cc/virtual/2026/poster/10008961)
- Related follow-up: ABBEL, "Learning Natural-Language Belief States for Memory-Efficient Interaction" (arXiv 2512.20111) — [arXiv](https://arxiv.org/pdf/2512.20111) (only the title was seen)

**History folding and summarization (bounded history, not a paged environment)**
- AgentFold (Tongyi Lab, arXiv 2510.24699, Oct 2025): treats context as "a dynamic cognitive workspace." At each step the model learns a "folding" operation, either a fine-grained condensation or a deep consolidation of whole sub-tasks — [arXiv](https://arxiv.org/abs/2510.24699)
- ReSum (Tongyi Lab, arXiv 2509.13313): periodic context summarization with a dedicated summary model and tailored RL, for "indefinite exploration." +4.5% average absolute over ReAct on web-search benchmarks — [arXiv](https://arxiv.org/abs/2509.13313v1)
- InftyThink (arXiv 2503.06692; ICLR 2026): iterative reasoning with an intermediate summary each round, giving a "sawtooth pattern… unbounded reasoning depth while maintaining a bounded memory footprint." Follow-up InftyThink+ adds RL (arXiv 2602.06960) — [arXiv html](https://arxiv.org/html/2503.06692); [InftyThink+](https://arxiv.org/html/2602.06960v3)
- ACM, Agentic Context Management (CMU and Meta, arXiv 2607.23809, Jul 2026): gives the agent a `manage_context` tool (summarize messages and write the raw content to external storage under a summary ID) and a `query_memory` tool to retrieve archived content. The agent decides when to compress, rather than a token threshold deciding. Evaluated on BrowseComp-Plus, DeepSearchQA and SWE-Bench — [arXiv](https://arxiv.org/html/2607.23809v1); [omarsar0 on X](https://x.com/omarsar0/status/2082105300392542246)
- Other 2025-26 work surfaced by search but not read: ACON (context compression for agents, arXiv 2510.00615), "Context as a Tool" for SWE-agents (arXiv 2512.22087), AgentProg (program-guided context for GUI agents, arXiv 2512.10371), ContextPilot (proactive context management via fine-grained RL, arXiv 2608.28476), "Learning Agent-Compatible Context Management" (arXiv 2605.30785), "Continuous Context Management" (arXiv 2609.35540), "Self-Evolving Context Management Policies" (arXiv 2609.34649) — [AgentFold search results list](https://arxiv.org/abs/2510.24699); [ACON](https://arxiv.org/pdf/2510.00615); [Context as a Tool](https://arxiv.org/pdf/2512.22087); [AgentProg](https://arxiv.org/pdf/2512.10371); [ContextPilot](https://arxiv.org/pdf/2608.28476); [2605.30785](https://arxiv.org/abs/2605.30785); [2609.35540](https://arxiv.org/html/2609.35540); [2609.34649](https://arxiv.org/html/2609.34649)

**Industry: Anthropic, Cognition**
- Anthropic, "Effective context engineering": defines context rot ("as the number of tokens in the context window increases, the model's ability to accurately recall information from that context decreases"). It describes compaction, structured note-taking (Claude playing Pokemon keeps tallies and maps in notes across context resets over "thousands of game steps"), just-in-time retrieval via "lightweight identifiers (file paths, stored queries, web links)," and sub-agents that return 1,000-2,000-token summaries — [Anthropic engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Claude context editing plus the memory tool: context editing automatically clears stale tool calls and results near the limit, and the memory tool is a file directory Claude can create, read, update and delete. In a 100-turn web-search evaluation, context editing cut token use by 84%, and context editing plus memory improved performance by 39% over baseline — [Claude blog: Managing context](https://claude.com/blog/context-management)
- Cognition (Walden Yan), "Don't Build Multi-Agents": recommends single-threaded agents that share full context, with compression of long histories (for example by a dedicated compression model) for longer tasks — [Cognition blog](https://cognition.com/blog/dont-build-multi-agents)

### Inferences (overlap matrix vs CVM)
- **Bounded context guarantee:**
  - Scroll has an explicit working-view budget with eviction, which is the closest match.
  - MEM1 and InftyThink give near-constant or sawtooth context, but as a learned or emergent property, not a hard runtime cap.
  - Compaction, context editing and ACM trigger at thresholds but still accumulate between triggers.
  - CVM's hard ≤32 objects / 16k tokens resident cap enforced by the runtime is closest to Scroll.
- **Stateless per step (the prompt is the state, no history):**
  - MEM1 is the clear precedent: it discards all prior context except the prompt, the query and the latest internal state.
  - InftyThink is similar at the level of reasoning rounds.
  - Scroll keeps a working view with prior projections, so it is not fully stateless.
  - RLM keeps a REPL trajectory.
  - So "stateless per step plus model-written notes" is shared with MEM1. CVM's twist is to pair it with a runtime-rendered resident view of environment objects.
- **Model-written memory/notes:**
  - MEM1 (internal state), Anthropic's NOTES.md and memory tool, ACM's summaries, and AgentFold's folds are all model-written.
  - On its own this is not novel.
- **Eviction ownership:**
  - In CVM the runtime owns eviction (LRU); the model cannot choose.
  - Scroll's description also suggests runtime eviction when the budget nears ("stale spans are evicted"), although I could not verify whether the policy is LRU or model-guided.
  - AgentFold, ACM and ContextPilot deliberately give eviction to the model; Anthropic context editing is a harness rule.
  - The OS-style split (runtime owns residency, model owns notes) is therefore close to Scroll and to MemGPT/Letta (2023, out of the date window and not researched here).
- **Context vs environment-size measurements:**
  - MEM1 measures peak tokens against horizon (objectives 2 to 16), not against environment size.
  - RLM measures accuracy and cost against input size (up to 10M+ tokens).
  - Scroll reports accuracy at fixed scales (LongMemEval_S, BEAM_10M, LOCA_256K).
  - I found no work that plots peak prompt tokens against environment/world size across 3+ orders of magnitude (1e3 to 1e6 objects) with a real LLM. This is a plausible novelty claim for CVM, with the caveat that RLM and Scroll implicitly have bounded root views and reviewers will say "that's obvious by construction."
- **Thrashing / re-materialization measurements:**
  - I found no prior work that reports re-materialization or thrashing rates (CVM: 96% re-materialization and 0 accuracy without notes, versus solving with 2 resident objects with notes).
  - Scroll's eviction index is meant to make re-access cheap, but no thrash metric surfaced.
  - The "notes are necessary under small working sets" ablation, with a working-set-size sweep, looks like CVM's most distinctive empirical contribution.

### Gaps
- Full text of Scroll could not be read, so these are unknown: its eviction policy, who triggers eviction, whether it sweeps context size against session length, and whether it ablates notes or landmarks.
- Full text of AgentFold, ReSum and ACM was not read, so I have no numeric context-size curves for them.
- Memory-R1, ACE (Agentic Context Engineering) and OpenAI Agents SDK sessions were not researched due to the tool-call budget. Their mechanisms are not covered here.
- MemGPT/Letta (2023) is a key "virtual memory for LLMs" precedent that CVM's name invites comparison with. It falls outside the 2024-2026 window and was not researched here; the report writer should make sure another researcher covers it.

## Q3. Long-context vs retrieval studies that sweep input size; training models to dereference instead of guess

### Takeaway
Long-context benchmarks consistently show accuracy falling as input length grows, often sharply by 32k tokens. This motivates CVM's flat-context design but measures the opposite thing: accuracy against context size, not context against environment size. RL-trained search agents (Search-R1, R1-Searcher, ReSum's RL) are the natural precedent for CVM V1 (fine-tuning on fault trajectories). They train *when and what to retrieve*, but none I found trains an explicit "uncertainty → dereference" fault op over a paged object store.

### Cited Findings
- Chroma "Context Rot" (July 2025): 18 models (including GPT-4.1, Claude 4, Gemini 2.5 and Qwen3) all degrade as input length grows. Tests include needle-question similarity, distractors, haystack structure, LongMemEval conversational QA and repeated words. Models did better on shuffled haystacks than on coherent ones — [Chroma research](https://www.trychroma.com/research/context-rot)
- In Chroma's conversational-memory tests, every model degraded on ~113K-token inputs (a secondary-source characterization) — [morphllm summary](https://www.morphllm.com/context-rot)
- NoLiMa: at 32K tokens, 10 models fall below 50% of their short-context baselines. GPT-4o drops from 99.3% to 69.7% — [NoLiMa arXiv](https://arxiv.org/html/2502.05167v3); [GitHub](https://github.com/adobe-research/NoLiMa)
- BABILong (NeurIPS 2024 D&B): 20 reasoning tasks embedded in book text, with splits up to 10M tokens and evaluation up to 50M tokens. Models use only about 10-20% of their context effectively — [NeurIPS proceedings](https://proceedings.neurips.cc/paper_files/paper/2024/file/c0d62e70dbc659cc9bd44cbcf1cb652f-Paper-Datasets_and_Benchmarks_Track.pdf)
- LongMemEval_S and BEAM_10M serve as agent-memory benchmarks in Scroll's evaluation (94.8% and 73.1%) — [Scroll arXiv](https://arxiv.org/abs/2608.21690)
- Search-R1 (arXiv 2503.09516): RL alone teaches an LLM to issue search queries during step-by-step reasoning, with retrieved-token masking. Gains over SOTA baselines: +26% (Qwen2.5-7B), +21% (Qwen2.5-3B), +10% (LLaMA3.2-3B) across 7 QA datasets — [arXiv](https://arxiv.org/abs/2503.09516)
- R1-Searcher (arXiv 2503.05592): RL to incentivize search capability — [arXiv](https://arxiv.org/pdf/2503.05592)
- ReSum trains agents with tailored RL to work from summarized contexts — [arXiv](https://arxiv.org/abs/2509.13313v1)
- MEM1 trains the memory-consolidation behavior itself end-to-end with RL, which is the precedent for training a model to work statelessly with self-written state — [arXiv](https://arxiv.org/html/2506.15841v2)

### Inferences
- For CVM's V1 (fine-tuning on FAULT trajectories), the closest training precedents are:
  - MEM1: RL for constant-memory state writing.
  - Search-R1 / R1-Searcher: RL for issuing retrieval.
  - ContextPilot / ACM: training or tooling for model-driven context operations.
  
  CVM's specific "fault when the needed object is not resident, rather than guess" objective is a narrower framing. I found no paper that labels and trains it as abstain-and-dereference over a paged store, but this is a weak negative: the search was not exhaustive.
- The long-context benchmarks (NoLiMa, BABILong, HELMET, Chroma) supply the motivation: accuracy degrades with context. CVM's flat-context curve is the complementary measurement. To be persuasive, CVM's evaluation could reuse BABILong or LongMemEval-style tasks at increasing scale.

### Gaps
- HELMET and Loong specifics were not verified from primary sources. A snippet reported HELMET RAG falling from 0.689 to 0.304 at 32K, but that came from an unclear aggregator, so it is excluded from the findings.
- DeepResearcher, ReSearch and Toolformer were not checked individually.
- I found no "agentic needle-in-a-haystack" study that sweeps environment size while recording the agent's prompt size.
