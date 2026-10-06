# Graph/Environment-Navigating LLM Agents and Environment-Size Scaling Studies (CVM novelty check)

Research note scope: prior work on LLM agents navigating large graphs/environments, and whether any work (a) runs an LLM agent on environments of up to ~1e6 nodes, (b) sweeps environment size over orders of magnitude while holding task complexity fixed, (c) reports context/working-set size as a function of environment size. Compiled 2026-10-06. Caveat: arxiv.org and alphaxiv.org were blocked for direct page fetches in this session, so findings below come from search-result abstracts/snippets of primary sources (arXiv abstract pages, OpenReview, GitHub, ICLR proceedings) and some secondary summaries (flagged). Numbers should be spot-checked against the PDFs before being quoted in a paper.

## Q1: KG/graph-reasoning agents (ToG 1/2/3, StructGPT, KG-Agent, RoG, Graph-CoT, GraphAgent-Reasoner, GraphRAG/LightRAG): what graph sizes, what scaling measurements?

### Takeaway
KG-navigating agents (ToG, StructGPT, KG-Agent) already run LLM agents over web-scale KGs (Freebase/Wikidata, far beyond 1e6 nodes) using bounded, hop-by-hop exploration, but they report accuracy on fixed benchmarks and LLM-call counts, not a sweep of KG size with fixed task complexity, and not resident context vs. KG size. Graph-algorithm agents (GraphAgent-Reasoner, GTA, GABench) do vary graph size, but the tasks are whole-graph algorithms whose complexity grows with the graph, so they are not "fixed task complexity" sweeps.

### Cited Findings
- Think-on-Graph (ICLR 2024) casts the LLM as an agent doing beam search over the KG (relation exploration with depth 1 and width N per step, then entity exploration, then reasoning), using Freebase as the KG environment. — [ToG arXiv 2307.07697](https://arxiv.org/abs/2307.07697); [ToG GitHub](https://github.com/GasolSun36/ToG)
- ToG's cost is reported as LLM calls: at most 2ND + D + 1 calls per question (N = beam width, D = depth), i.e., a function of search width/depth, not KG size; another paper reports ToG making 4 to 25 requests per question depending on depth/width limits. — [ToG ICLR proceedings PDF](https://proceedings.iclr.cc/paper_files/paper/2024/file/10a6bdcabbd5a3d36b760daa295f63c1-Paper-Conference.pdf); [ToG arXiv HTML](https://arxiv.org/html/2307.07697)
- Think-on-Graph 2.0 is a hybrid RAG that alternates knowledge-guided text retrieval and context-enhanced graph search, with the LLM deciding whether to keep exploring. — [GraphWalker paper describing ToG-2](https://arxiv.org/pdf/2603.28533)
- Think-on-Graph 3.0 (Sept 2025) introduces a Chunk-Triplets-Community heterogeneous graph and MACER (Multi-Agent Context Evolution and Retrieval) with Evolving Query and Evolving Sub-Graph, using Reflector/Constructor/Retriever/Responser agents; its framing is efficiency with lightweight LLMs, not environment-size scaling. — [ToG-3 arXiv 2509.21710](https://arxiv.org/abs/2509.21710); [HF paper page](https://huggingface.co/papers/2509.21710)
- StructGPT defines interfaces to KG data that implement "knowledge access and filtering with finite quantity", with the LLM repeatedly invoking them for planning; KG-Agent provides extraction, semantic, and logic tools over Freebase/Wikidata, and reports 9.7% and 8.5% relative zero-shot gains on WQ-Freebase and TQ-Wiki, and outperforms StructGPT on WebQSP, CWQ, GrailQA. — [KG-Agent arXiv 2402.11163](https://arxiv.org/html/2402.11163)
- Some KG agents use a Search action that returns an exact entity's one-hop subgraph (i.e., returns all neighbors), the analogue of CVM's "conventional tool calling returns whole objects" baseline. — [KG-Agent / related search summary](https://arxiv.org/html/2402.11163); [Generate-on-Graph](https://arxiv.org/html/2404.14741v3)
- GraphAgent-Reasoner ("Scalable and Accurate Graph Reasoning with LLM-based Multi-Agents", arXiv 2410.05130; AAAI 2026 per paper notes) creates one agent per node and solves graph algorithms by message passing; it "can efficiently scale to accommodate larger graphs with over 1,000 nodes". On GraphInstruct (graphs up to 100 nodes, 400 cases/task) it averages ~98% on six polynomial-time tasks. — [arXiv 2410.05130](https://arxiv.org/abs/2410.05130); [OpenReview](https://openreview.net/forum?id=ZMtq9pYw5e); [AAAI 2026 paper note](https://en.papernotes.org/AAAI2026/multi_agent/scalable_and_accurate_graph_reasoning_with_llm-based_multi-agents/)
- A secondary summary states GraphAgent-Reasoner attains 100% accuracy on graphs of 100, 200, and 500 nodes and 90% at 1,000 nodes (webpage-importance / PageRank-style task). Note: its cost scales with node count because agent count = node count. — [Moonlight literature review (secondary)](https://www.themoonlight.io/en/review/scalable-and-accurate-graph-reasoning-with-llm-based-multi-agents)
- GraphDC (arXiv 2605.06671, May 2026) is a divide-and-conquer multi-agent system for "scalable graph algorithm reasoning" (follow-up line to GraphAgent-Reasoner). — [GraphDC arXiv](https://arxiv.org/html/2605.06671)
- GTA (Graph Theory Agent, arXiv 2609.12265) generates graphs of increasing size (nodes/edges) to study LLM scalability, splitting Easy/Hard subsets as graph size grows. — [GTA arXiv](https://arxiv.org/pdf/2609.12265)
- GABench (arXiv 2608.01684, Aug 2026) evaluates LLM agents (OpenClaw harness, shared toolset) on graph-analysis tasks over 13 real datasets ranging from 26 to >3.7 million nodes and up to 123.6 million edges, and reports token consumption and token efficiency by model and task category (node classification, link prediction, graph classification). — [GABench arXiv HTML](https://arxiv.org/html/2608.01684v1)
- LightRAG/GraphRAG cost scaling: "BM25 Wins at Scale" (arXiv 2607.26497) finds LightRAG indexing is super-linear (exponent b = 1.36), fails to complete at 2,826 documents, extrapolating to 102B tokens; MS-GraphRAG used 190M tokens at 10.6M corpus tokens (~7.9B at full scale); HippoRAG 2 is ~linear (b = 1.01). — [BM25 Wins at Scale arXiv HTML](https://arxiv.org/html/2607.26497v3)
- Per-query retrieval cost for graph RAG is in the ~10k-16k token range: LightRAG ~15,837 and PathRAG ~13,318 tokens per question in one study; LightRAG 9,974 tokens/query in another. — [search summary of PathRAG/LinearRAG/related](https://arxiv.org/pdf/2502.14902); [LinearRAG](https://arxiv.org/pdf/2510.10114)

### Inferences
- (a) is NOT novel per se: ToG/StructGPT/KG-Agent run LLM agents on Freebase/Wikidata-scale KGs (orders of magnitude beyond 1e6 entities), and GABench runs agents on graphs up to 3.7M nodes. CVM cannot claim "first LLM agent on 1e6-node environments".
- (b)+(c) together appear unclaimed in the KG-agent line: none of the KGQA agent papers found sweeps KG size with fixed hop count and reports peak resident context vs. KG size. Their efficiency metrics are LLM calls (a function of width/depth) and accuracy on fixed benchmarks.
- GraphAgent-Reasoner/GTA/GABench sweep graph size, but task complexity scales with size (whole-graph algorithms or ML tasks), so they are not fixed-complexity sweeps; GraphAgent-Reasoner's cost is explicitly O(nodes) agents, the opposite of CVM's claim.
- ToG's bounded beam exploration is conceptually the closest KG analogue of a bounded working set; CVM should cite it and differentiate on (i) explicit paging/eviction with stable references, (ii) hub-node handling (ToG still lists all candidate relations of an entity), (iii) the explicit size sweep.

### Gaps
- Could not fetch exact Freebase entity/triple counts used by ToG in this session (commonly cited as tens of millions of entities / billions of triples, but not verified here).
- Reasoning on Graphs (RoG) and Graph Chain-of-Thought (Graph-CoT) were not individually verified this session; from general knowledge, RoG is plan-retrieve-reason over Freebase (WebQSP/CWQ) and Graph-CoT (GRBench) uses domain graphs, and neither is known to sweep graph size, but no source was retrieved to confirm.
- GABench's token-vs-graph-size relationship (whether it reports tokens as a function of node count) could not be confirmed from snippets; worth checking the PDF directly since it is the closest "agent on 1e6+ node graph with token reporting" work.

## Q2: Text-to-SQL / database agents on large schemas (Spider 2.0, BIRD): do any sweep DB size?

### Takeaway
Spider 2.0 pushes schema size to enterprise scale (avg ~812 columns, max 23,067 columns, schemas up to ~20M tokens with samples) and motivates agentic schema exploration, but it is a fixed benchmark with naturally varying schema size, not a controlled size sweep with fixed task complexity, and it does not report agent context vs. DB size.

### Cited Findings
- Spider 2.0 has 632 enterprise text-to-SQL workflow tasks; databases average 812 columns; Spider 2.0-lite has max 23,067 columns, median 228, 95th percentile 3,910. — [Spider 2.0 arXiv 2411.07763](https://arxiv.org/html/2411.07763v2); [ICLR 2025 PDF](https://proceedings.iclr.cc/paper_files/paper/2025/file/46c10f6c8ea5aa6f267bcdabcb123f97-Paper-Conference.pdf)
- With sample rows and column descriptions, a schema can reach 77MB (~20 million tokens), far beyond LLM context. — [Spider 2.0](https://arxiv.org/html/2411.07763v2)
- Spider 2.0-lite averages >755 columns per DB vs ~54 in BIRD; column-linking errors are 16.6% (another analysis: 27.6% of SQL errors with naive linking). — [Emergent Mind Spider 2.0 summary (secondary)](https://www.emergentmind.com/topics/spider-2-0-benchmark); [ReFoRCE arXiv 2502.00675](https://arxiv.org/pdf/2502.00675)
- "Scaling Text2SQL via LLM-efficient Schema Filtering" (arXiv 2512.16083) targets large-schema scaling via schema filtering. — [arXiv 2512.16083](https://arxiv.org/pdf/2512.16083)

### Inferences
- The text-to-SQL literature treats schema size as a difficulty factor; it scales schema (metadata), not number of rows/objects with fixed query depth. A CVM-style fixed-complexity sweep over 1e2..1e6 objects is not found here.
- Schema-filtering/linking is analogous to CVM's SEARCH-then-TRAVERSE, and is a relevant comparison for "one-shot retrieval cannot plan".

### Gaps
- Did not find any text-to-SQL paper that holds query complexity fixed and sweeps row count or table count by orders of magnitude while reporting agent context; absence not proven.

## Q3: Benchmarks varying environment size with fixed task difficulty (NIAH, context rot, Lost in the Middle, LongMemEval, BrowseComp-Plus, SWE, tool count)

### Takeaway
The "hold task fixed, grow the haystack" design is well established for long-context models (Chroma Context Rot, NIAH, LongMemEval S/M) and, most relevantly, for retrieval/agentic search over corpora ("BM25 Wins at Scale", 28 nested tiers, ~450x corpus growth, fixed questions). These show performance degrades or agent token cost grows with environment size; none reports an agent whose resident context stays flat across 4 orders of magnitude of environment size.

### Cited Findings
- Chroma "Context Rot" (July 2025; Hong, Troynikov, Huber): 18 models (GPT-4.1, Claude 4, Gemini 2.5, Qwen3...) evaluated holding task complexity constant and varying only input length; all degrade as input grows, with factors like needle-question similarity and distractors mattering. — [ZenML summary of Chroma report](https://www.zenml.io/llmops-database/context-rot-evaluating-llm-performance-degradation-with-increasing-input-tokens); [WinBuzzer coverage](https://winbuzzer.com/2025/07/22/context-rot-new-study-reveals-why-bigger-context-windows-dont-magically-improve-llm-performance-xcxwbn/)
- "BM25 Wins at Scale" (arXiv 2607.26497, July 2026): controlled study of lexical, dense, graph-based, and agentic RAG with corpus size varied over 28 strictly nested tiers (~450-fold), holding questions and a fixed "bedrock" of relevant and adversarial docs unchanged. A File-System Agent leads at small tiers but BM25 overtakes around 10M corpus tokens, with a ~20-point margin at full scale; the agent's sequential exploration costs 39x more query tokens at the bedrock and becomes less effective as the search space grows; graph-based RAG hits "construction walls". — [arXiv abs](https://arxiv.org/abs/2607.26497); [arXiv HTML](https://arxiv.org/html/2607.26497v3); [GitHub](https://github.com/BstWPY/BM25-Wins-at-Scale)
- LongMemEval (ICLR 2025): 500 questions; history length is configurable, with standard settings LongMemEval_S (~115k tokens) and LongMemEval_M (500 sessions, ~1.5M tokens). — [LongMemEval arXiv 2410.10813](https://arxiv.org/html/2410.10813v1); [GitHub](https://github.com/xiaowu0162/longmemeval)
- BrowseComp-Plus: fixed curated corpus of ~100K human-verified documents for reproducible deep-research agent evaluation (fixed size, not a sweep). — [GitHub](https://github.com/texttron/BrowseComp-Plus); [arXiv 2508.06600](https://arxiv.org/pdf/2508.06600)
- Tool-count scaling: on ToolBench, naive all-tools selection accuracy drops from 92.4% at 15 tools to 78.2% at 640 tools; MCP-Zero selects from ~3k candidate tools with 98% token reduction; RAG-MCP reports ~50% token reduction and 3.2x selection accuracy. — [MCP-Zero arXiv 2506.01056](https://arxiv.org/html/2506.01056v3); [RAG-MCP arXiv 2505.03275](https://arxiv.org/html/2505.03275v1)
- SWE-bench repos average ~3,010 non-test files and ~438k lines; codebases are millions of tokens; agents' context grows rapidly as they read code, motivating pruning (SWE-Pruner 38.7-44.2% prompt reduction), minification (~40% fewer tokens, 10-17% performance drop), FastContext (up to 60% main-model token reduction). — [Emergent Mind SWE-bench summary (secondary)](https://www.emergentmind.com/topics/swe-bench); [SWE-Pruner](https://arxiv.org/pdf/2601.16746); [Minification](https://arxiv.org/html/2606.01326v1); [FastContext](https://arxiv.org/html/2606.14066v1)
- MemGPT (2023) is the canonical "virtual memory / paging for LLM context" system: context window as RAM, external recall/archival stores as disk, with function calls to page information in and out, enabling "unbounded context" with finite windows. — [MemGPT arXiv 2310.08560](https://arxiv.org/pdf/2310.08560)

### Inferences
- The experimental design of CVM (fixed task, growing environment) has clear precedent: Context Rot and NIAH for raw context, and "BM25 Wins at Scale" for corpus/agentic search. CVM must cite these and cannot claim the fixed-task size-sweep methodology as new.
- The closest single prior study on design is "BM25 Wins at Scale": controlled nested-size sweep, fixed questions, agentic baseline, token-cost reporting. Difference: unstructured document corpus (~450x range, not 1e4x), no graph/stable-reference traversal, and its finding is the opposite (agent cost/effectiveness worsens with scale), which makes CVM's flat-context result a meaningful contrast rather than a duplicate.
- MemGPT is the closest conceptual ancestor to the name and mechanism ("virtual memory" for LLM context). It pages conversational/archival text, not a structured object graph with stable references, and (to my knowledge) did not sweep external-store size over orders of magnitude while reporting resident context. CVM must position against MemGPT explicitly.
- Tool-count scaling (ToolBench/MCP-Zero) is an analogous "environment grows, task fixed" axis (number of tools rather than objects), again showing naive exposure degrades and on-demand discovery keeps tokens flat; this supports CVM's thesis but limits novelty of the general "fault-in on demand" idea.

### Gaps
- "Lost in the Middle" (Liu et al., 2023, arXiv 2307.03172) is the standard citation for position effects as context grows; not re-verified via search this session.
- No study found where SWE agents are evaluated with codebase size swept over orders of magnitude at fixed task complexity.
- WebArena scaling experiments (environment size sweeps) not found.

## Q4: RCA / AIOps LLM agents over microservice graphs (RCAgent, OpenRCA, ITBench, AIOpsLab, KRCA): environment sizes and context management

### Takeaway
AIOps agent benchmarks use small topologies (11-28 microservices in AIOpsLab) or huge raw telemetry (OpenRCA: 68GB, ~2GB per 30-minute window) handled via code execution; a production system (KRCA) operates on ~200k services. None found sweeps topology size with fixed incident complexity or reports agent context vs. topology size; reported costs are per-incident (e.g., ~220K tokens, 75 API calls).

### Cited Findings
- OpenRCA (ICLR 2025): 335 failures from three enterprise systems (Market, Telecom, Bank) with >68 GB of telemetry; extracting just the relevant half-hour window yields ~2 GB, far beyond context; its agent (RCA-agent) uses Python execution for retrieval/analysis to avoid putting telemetry in context. — [OpenRCA PDF](https://netman.aiops.org/wp-content/uploads/2025/05/13411_OpenRCA_Can_Large_Langua.pdf); [ResearchGate](https://www.researchgate.net/publication/391576800_OpenRCA_Can_Large_Language_Models_Locate_the_Root_Cause_of_Software_Failures)
- AIOpsLab (Microsoft): SocialNetwork app with 28 microservices; Online Boutique with 11 microservices. — [AIOpsLab arXiv 2501.06706](https://arxiv.org/html/2501.06706v1); [GitHub](https://github.com/microsoft/AIOpsLab/)
- ITBench evaluates agents with 128K-token context windows across IT automation scenarios. — [ITBench arXiv 2502.05352](https://arxiv.org/pdf/2502.05352)
- RCAgent: tool-augmented autonomous LLM agents for cloud RCA. — [RCAgent arXiv 2310.16340](https://arxiv.org/pdf/2310.16340)
- KRCA (arXiv 2607.01788, Kuaishou): deployed in a ~200k-service production environment; multi-stage pipeline with API-level drilldown to isolate suspicious services, combining causal constraints with multi-agent reasoning; AC@1 0.88 (service localization) and 0.79 (failure type); 77.3% reduction in diagnosis time over 6 months. — [KRCA arXiv](https://arxiv.org/html/2607.01788v1)
- A production LATS-RCA system reports 60-70% accuracy with ~75 API calls, ~220K tokens, 13 minutes per incident; topology-aware work (GALA+: 74.44% AC@1 OnlineBoutique, 73.33% TrainTicket) argues unconstrained agents search the whole service space without topology grounding. — [Graph-Augmented LLM Agents for RCA arXiv 2608.08968](https://arxiv.org/pdf/2608.08968); [TopoEvo arXiv 2605.15611](https://arxiv.org/pdf/2605.15611)
- "Rethinking Tool Design for Agentic RCA: A Controlled Empirical Study" (arXiv 2610.05009, submitted Oct 4 2026): 375 failure cases, 3 systems, 24 structured tools at levels L1 (raw metric access), L2 (evidence analysis), L3 (diagnosis) vs a Python reference L0; L3 gets 82.8% top-1 localization vs 85.4% for L0 at under half the time per case; tool-level rankings change with model and system. — [arXiv HTML](https://arxiv.org/html/2610.05009)

### Inferences
- The AIOps literature confirms the problem CVM targets (raw telemetry/topology far exceeding context) and uses code execution or topology pruning to cope, but evaluates on fixed small topologies or a single huge production system; no controlled size sweep found.
- 2610.05009 is the closest "controlled study of tool interface granularity" in RCA and complements CVM's "tool calling returning whole objects" baseline; it varies tool abstraction level, not environment size.
- KRCA proves agents can operate at 2e5 services in production (so "1e6-scale environment" is not unprecedented in practice) but it relies on a pre-pipeline drilldown rather than reporting bounded working-set behavior.

### Gaps
- AIOpsLab/ITBench per-episode token counts and whether any of them vary the number of services were not confirmed.
- No synthetic infrastructure KG benchmark with tunable size (like CVM's world generator) was found in the AIOps literature.

## Q5: Any "virtualization ratio"-like metric (environment size / context size)?

### Takeaway
No prior work found reports an explicit ratio of environment size to resident context size (or to working-set size) as a metric. Related quantities exist only implicitly: "% token reduction" vs. full-context baselines (MCP-Zero 98%, Anthropic Tool Search 85%), "query tokens per question" (BM25 Wins at Scale, 39x agent overhead), and MemGPT's conceptual main-context vs external-store split.

### Cited Findings
- MCP-Zero reports 98% token reduction selecting from ~3k tools; RAG-MCP ~50% token reduction. — [MCP-Zero](https://arxiv.org/html/2506.01056v3); [RAG-MCP](https://arxiv.org/html/2505.03275v1)
- Vendor claim: Anthropic's Tool Search Tool gives ~85% token reduction and accuracy 49% -> 74% in internal testing (vendor/secondary reporting). — [Maxim article (secondary)](https://www.getmaxim.ai/articles/best-mcp-gateway-for-scaling-ai-agents-to-500-tools/)
- At 500 MCP tools, tool definitions alone can consume >1.1M tokens (secondary industry claim). — [Maxim article (secondary)](https://www.getmaxim.ai/articles/best-mcp-gateway-for-scaling-ai-agents-to-500-tools/)
- "BM25 Wins at Scale" reports agent query tokens relative to baselines (39x more than BM25 at the bedrock tier). — [arXiv 2607.26497](https://arxiv.org/html/2607.26497v3)
- MemGPT frames the context window as RAM and external stores as disk, but the search did not surface a quantitative ratio metric. — [MemGPT](https://arxiv.org/pdf/2310.08560)

### Inferences
- A metric like "virtualization ratio = environment objects (or tokens) / peak resident objects (or tokens)" appears new as an explicitly named, reported metric. For CVM: at 1e6 objects with ~12 resident objects, ratio ~8e4 by objects; full-context baseline fails beyond ~1e4 objects / 1M tokens, implying the world at 1e6 objects is ~1e8 tokens vs ~2k resident, ratio ~5e4 by tokens (inferred from CVM's own numbers, not from external sources).
- Overall novelty assessment: (a) alone is not novel (ToG on Freebase; GABench up to 3.7M nodes; KRCA at 200k services). (b) alone is not novel (Context Rot; BM25 Wins at Scale nested 450x sweep; LongMemEval S/M; GraphAgent-Reasoner/GTA graph-size sweeps). (c) is partially present (BM25 Wins at Scale reports query tokens across tiers; GABench reports token consumption). The combination (a)+(b)+(c) for an LLM agent over a structured graph, 4 orders of magnitude (1e2..1e6), fixed dereference depth, with peak resident context reported flat, and contrasted with a whole-object tool-calling baseline whose context grows due to hubs, was not found in any single prior work. Closest prior works: "BM25 Wins at Scale" (methodology), MemGPT (mechanism/concept), ToG/KG-Agent (bounded KG exploration), GABench (agent on multi-million-node graphs with token reporting).
- Risk to novelty claim: CVM's small n (15-30 per scale) and the fact that the deterministic reference processor gets 1.00 suggests reviewers will compare against ToG-style beam search on the same synthetic KG; a ToG-like baseline would strengthen the claim.

### Gaps
- Did not verify whether GABench plots token consumption as a function of graph size (vs. per model/task); if it does, it is the strongest counterexample for (c) on graphs.
- Did not find or verify any paper using the term "virtualization ratio"; absence in search is not proof of absence.
