# LLM-as-OS Architectures and Virtual Context / Memory Paging for LLM Agents (prior work relevant to CVM novelty)

Research date: 2026-10-06. Primary sources were read in full text (arXiv HTML) unless marked "snippet only".

## Q1. What do MemGPT and Letta actually do? Who controls paging/eviction? Do they measure context size vs external-store size? Stable handles?

### Takeaway
MemGPT (Oct 2023) is the origin of the "LLM as OS / virtual context management" framing, but its paging is **model-directed** (the LLM calls functions to search, insert and edit memory), and the runtime's only role in eviction is a FIFO queue flush with recursive summarization once tokens pass a threshold. It does not use a bounded object-count working set, does not hand the model stable object handles, and does not measure resident-context size against a growing external store. Letta (MemGPT's productization) adds persisted, labeled memory blocks with a `block_id`, sleep-time agents, and a filesystem whose open files reportedly use LRU eviction. That last feature is the closest Letta comes to CVM's runtime-owned LRU, but it covers only files, is not framed as a working set, and is not measured.

### Cited Findings
- MemGPT, "Towards LLMs as Operating Systems" (Packer, Wooders, Lin, Fang, Patil, Stoica, Gonzalez; UC Berkeley). Versions: v1 12 Oct 2023, v2 12 Feb 2024. It proposes "virtual context management, a technique drawing inspiration from hierarchical memory systems in traditional operating systems which provide the illusion of an extended virtual memory via paging between physical memory and disk." — [arXiv 2310.08560](https://arxiv.org/abs/2310.08560)
- MemGPT main context has three parts: read-only system instructions, a "working context" ("a fixed-size read/write block of unstructured text, writeable only via MemGPT function calls" that stores key facts and preferences), and a FIFO queue of messages whose first entry is a recursive summary of evicted messages. — [arXiv 2310.08560 §2.1](https://arxiv.org/html/2310.08560)
- How eviction works in MemGPT: when prompt tokens pass a "warning token count" (for example 70% of the window), the queue manager inserts a "memory pressure" system message so the LLM can save important information to working context or archival storage. At the "flush token count" (100%), the queue manager evicts a fixed fraction of messages (for example 50% of the window) and regenerates the recursive summary. Evicted messages stay in recall storage and can be read back through function calls. — [arXiv 2310.08560 §2.2](https://arxiv.org/html/2310.08560)
- "Memory edits and retrieval are entirely self-directed: MemGPT autonomously updates and searches through its own memory … it can decide when to move items between contexts." Results, including errors such as trying to add to main context when it is full, are fed back to the model. — [arXiv 2310.08560 §2.3](https://arxiv.org/html/2310.08560)
- MemGPT evaluations are task accuracy only: deep memory retrieval and a conversation-opener task on Multi-Session Chat, multi-document QA, and nested key-value retrieval. No residency, working-set or thrash metrics are reported. — [arXiv 2310.08560 §3](https://arxiv.org/html/2310.08560)
- ClawVM's authors characterize MemGPT as "the closest predecessor, explicitly framing context management as OS-style virtual memory with model-driven paging", and say MemGPT and Memory-as-Action "leave residency and writeback to model discretion." — [ClawVM, arXiv 2604.10352 §6](https://arxiv.org/html/2604.10352)
- Letta memory blocks (blog dated May 14, 2025): a block has a label, a string value, a size limit and an optional description. "The block value can be edited by the agent via memory tools … unless they are read-only: in which case, only the developer can modify them." Blocks are "individually persisted in the DB, with a unique block_id." — [Letta blog: Memory Blocks](https://www.letta.com/blog/memory-blocks)
- Letta context hierarchy (docs): memory blocks are in-context (recommended under 50k characters and under 20 blocks) and edited with memory_rethink, memory_replace and memory_insert. Files are read-only and "partial" in context ("files can be opened/closed"; tools: open, close, semantic_search, grep). Archival memory is not in context and is accessed with archival_memory_insert and archival_memory_search. — [Letta docs: Context hierarchy](https://docs.letta.com/guides/agents/context-hierarchy/)
- Letta Filesystem gives agents the tools grep, open ("Read specific files (and close others) with line-level precision") and semantic_search. "As it works on its tasks, it will automatically open and close files, but you also have the option to manually override what is in-context … or explicitly evict no longer relevant files." — [Letta blog: Introducing Letta Filesystem](https://www.letta.com/blog/letta-filesystem/)
- (Secondary source, snippet only.) Letta's FileAgentManager "enforces the max_files_open limit using LRU eviction … the least recently accessed file is closed," and opening a file returns the names of files closed by LRU eviction. — [DeepWiki: letta-ai/letta](https://deepwiki.com/letta-ai/letta/2.3-tool-system). I could not verify this in Letta source code; the GitHub raw-file grep returned nothing at the paths I tried.
- Sleep-time compute (Lin, Snell, Wang, Packer, Wooders, Stoica, Gonzalez; Letta/UC Berkeley; arXiv 17 Apr 2025): models "think" offline about a context before queries arrive. It reports Pareto gains on Stateful GSM-Symbolic and Stateful AIME and amortization across related queries. This is about test-time compute, not paging. — [arXiv 2504.13171](https://arxiv.org/abs/2504.13171)
- Letta's "MemGPT 2.0: sleep-time agents": a background agent rewrites shared memory blocks ("learned context") during idle periods. — [Letta blog: Sleep-time Compute](https://www.letta.com/blog/sleep-time-compute); [Letta blog: Memory Blocks](https://www.letta.com/blog/memory-blocks)

### Inferences
- **Eviction control.** MemGPT's model can move data in and out, and the runtime only flushes the FIFO message queue by token threshold, so control is mixed and mostly model-driven. CVM's claim that the "runtime owns eviction, the model cannot control it" is a deliberate inversion of MemGPT's self-directed design. Letta's file LRU, if accurate, is a partial precedent for runtime-owned LRU over discrete objects.
- **Notes area.** MemGPT's "working context" and Letta's memory blocks are direct precedents for CVM's small model-writable notes area. CVM's novelty there is not the notes area itself but the ablation showing that bounded residency without notes thrashes and fails while with notes it succeeds at 2 resident objects. I found no MemGPT or Letta result that ablates the notes area against a bounded resident set.
- **Handles.** Letta block IDs and file names are stable identifiers, but they are developer/API handles. The model mostly receives serialized content (an opened file's text, or search results). I found no evidence that MemGPT or Letta exposes URI-style object handles that the model dereferences with typed operations.
- **Scaling measurement.** Neither MemGPT nor Letta reports resident context size as a function of external-store size, such as a 1e3 to 1e6 sweep.

### Gaps
- I could not access docs.letta.com through WebFetch, though curl worked for some pages. I could not confirm the exact Letta source code for LRU file eviction or its date of introduction.
- I did not check whether Letta's 2026 releases (for example "context repositories" or newer agent architectures) add runtime-owned residency.

## Q2. AIOS and other "LLM OS" / memory-OS systems: what do they implement and measure?

### Takeaway
AIOS is an agent-serving kernel. Its "context switching" is snapshot and restore of LLM generation state for preemptive scheduling, and its memory manager does LRU-K swapping of per-agent memory items between RAM and disk at an 80% threshold. Its evaluation measures throughput and latency. MemoryOS and MemOS use OS vocabulary (paging, scheduler, MemCube, governance) for long-term conversational memory, and they evaluate QA accuracy on LoCoMo-style benchmarks. **ClawVM (EuroMLSys '26, April 2026) is the closest prior work to CVM found.** It is a harness-managed (runtime-owned) virtual memory with typed pages carrying stable identifiers and provenance, a "pointer" representation level, observable faults (including refetch faults), a Denning-derived thrash index, and an LRU baseline.

### Cited Findings
- **AIOS** (Mei et al., Rutgers; arXiv v1 25 Mar 2024, v5 12 Aug 2025; "Published as a full paper at COLM 2025"). The kernel provides "scheduling, context management, memory management, storage management, access control" for agents. — [arXiv 2403.16971](https://arxiv.org/abs/2403.16971)
- AIOS context manager: "To support LLM context switching, we implement a context manager with snapshot and restoration capabilities." It is used to interrupt and resume long LLM calls under round-robin scheduling, and has two modes: text-based (saving decoded output) and logits-based (saving the beam search tree). — [arXiv 2403.16971 §3.4](https://arxiv.org/html/2403.16971)
- AIOS memory manager: "When an agent's memory usage exceeds its block limit (e.g., 80% of allocation), the memory manager initiates a K-Least Recently Used (LRU-K) eviction policy, transferring items from RAM to disk via the storage manager." — [arXiv 2403.16971 §3.5](https://arxiv.org/html/2403.16971)
- AIOS access manager: "privilege-based access control" that maps agent IDs to privilege groups, plus user-intervention protocols for irreversible operations. — [arXiv 2403.16971 §3.8](https://arxiv.org/html/2403.16971)
- AIOS headline result: "up to [2.1x] faster execution for serving agents built by various agent frameworks" (the multiplier was stripped in the HTML; the abstract reports a speedup). The evaluation is about serving efficiency. — [arXiv 2403.16971](https://arxiv.org/abs/2403.16971)
- **MemoryOS** ("Memory OS of AI Agent", Kang et al., BUPT/Tencent; arXiv 30 May 2025). Three tiers (short-term, mid-term, long-term personal memory). Short-to-mid uses "dialogue-chain-based FIFO" and mid-to-long uses "segmented page organization" with heat-based updating. Evaluated on LoCoMo (+49.11% F1, +46.18% BLEU-1 on GPT-4o-mini). — [arXiv 2506.06326](https://arxiv.org/abs/2506.06326)
- **MemOS** (Li et al., MemTensor/SJTU et al.; short version arXiv 28 May 2025, long version arXiv 4 Jul 2025, v4 3 Dec 2025). A "memory operating system" over parametric, activation and plaintext memory, with the MemCube abstraction, MemScheduler, and Memory Governance ("access control, versioning, provenance auditing"). Its Table 2 maps OS components to MemOS modules. — [arXiv 2505.22101](https://arxiv.org/abs/2505.22101); [arXiv 2507.03724](https://arxiv.org/abs/2507.03724)
- **A-MEM** (Xu et al., Rutgers; NeurIPS 2025). Zettelkasten-style memory notes with keywords, tags and links, plus "memory evolution". It is long-term memory organization, not prompt-time paging. — [arXiv 2502.12110](https://arxiv.org/abs/2502.12110); characterization in [ClawVM §6](https://arxiv.org/html/2604.10352)
- **ClawVM** ("Harness-Managed Virtual Memory for Stateful Tool-Using LLM Agents", Rafique and Bindschaedler (MPI-SWS); EuroMLSys '26, Apr 27–30 2026, DOI 10.1145/3805621.3807648; arXiv 11 Apr 2026):
  - "the context window is physical memory, durable stores are disk", and "every prompt-assembly decision … is a page-replacement decision." — [arXiv 2604.10352 §2](https://arxiv.org/html/2604.10352)
  - Design requirement: "Capture and recall are policy, not discretion. For designated state, the harness drives capture and recall instead of relying on the model to flush or search." — [§2](https://arxiv.org/html/2604.10352)
  - "A page is a typed record with a stable identifier, scope, provenance, and a minimum-fidelity invariant." There are six page types (Bootstrap/Policy, Constraint, Plan, Preference, Evidence, Conversation Segment) and four residency levels: full, compressed, structured, and **pointer ("a resolvable handle plus minimal metadata")**. — [§3](https://arxiv.org/html/2604.10352)
  - Fault model: "Unlike OS page faults, which the kernel resolves transparently from disk, agent faults are silent." Defined faults include refetch faults ("a tool result re-retrieved after eviction"), duplicate-tool faults, pinned-invariant misses, post-compaction bootstrap faults, silent-recall faults and flush-miss faults. — [§3](https://arxiv.org/html/2604.10352)
  - "We quantify instability with the thrash index: the ratio of paging events to hits over the run …, adapting the classical thrashing ratio (Denning, 1968); high values signal a working-set/budget mismatch." — [§3, App. A](https://arxiv.org/html/2604.10352)
  - The budget is in tokens, not object count. Selection is a "multi-choice knapsack" with a deterministic two-phase policy. An LRU variant "achieves zero explicit faults and identical thrash to ClawVM." — [§3, §5.2](https://arxiv.org/html/2604.10352)
  - Validated writeback: staged (field, op, value, scope, evidence_ref) updates are checked for schema, **provenance ("evidence_ref resolves; dangling provenance rejected")**, scope, non-destructiveness and policy. — [App. A](https://arxiv.org/html/2604.10352)
  - Results: faults drop from 67.8 (retrieval baseline) and 1.5 (compaction plus retrieval) to zero per workload-budget configuration; "paging instability" falls by 77.4% and 11.4%; 12 real Claude Code session traces; evaluation is offline/replay-based with no live-model end-to-end task quality ("we leave to future work"). — [§1, §5.2](https://arxiv.org/html/2604.10352)
- **VISTA** ("LLM Agents Are Latent Context Managers", Xu et al., CUHK; v5 31 Jul 2026). It represents working memory "as typed addressable blocks" with a dashboard of token usage, recency, archive status and remaining budget. Archived blocks "are replaced by compact handles and summaries" and remain recoverable. The harness enforces the budget and requires "every actionable unit must have a stable block ID or handle". **The agent decides what to archive.** LOCA-Bench with Gemini-3-Flash goes from 22.7% to 50.7%. — [arXiv 2606.30005](https://arxiv.org/html/2606.30005)
- **Context Window Lifecycle (CWL)** ("Beyond Compaction: Structured Context Eviction", Semenov and Dorofeev; arXiv 1 May 2026). "The agent annotates its trajectory as typed, dependency-linked episodes … and a deterministic, LLM-free policy evicts content in priority order." This keeps "active context near a stable ceiling". One session completed 89 sequential tasks across 80M tokens with no measurable accuracy loss. — [arXiv 2606.11213](https://arxiv.org/abs/2606.11213)
- **Ledger** ("Turning Interaction History into Execution State", Wang et al.; arXiv 1 Aug 2026). A deterministic runtime layer tracks what has been observed, modified and attempted, returns "still-valid earlier results in place of re-execution", and flags "likely-redundant repetition". SWE-bench Verified Pass@1 rises from 56.2% to 64.2% (GPT-5 mini) with 28.9% lower cost. — [arXiv 2608.00808](https://arxiv.org/abs/2608.00808)
- **Karpathy "LLM OS"** (Nov 2023 tweet, as reported by secondary sources): "LLM: OpenAI GPT-4 Turbo 256 core (batch size) processor @ 20Hz (tok/s) — RAM: 128Ktok". The context window is RAM and the LLM is "the kernel process of a new Operating System." — [MindStudio summary](https://www.mindstudio.ai/blog/software-3-0-explained-karpathy-context-window-ram-model-weights-cpu); [frenxt summary](https://www.frenxt.com/cables/claude-code/karpathy-02-llm-os) (secondary; the original tweet was not retrieved)

### Inferences
- **The OS/virtual-memory framing is not novel.** It has been standard since MemGPT (2023) and Karpathy (2023), and was implemented in AIOS (2024–25), MemoryOS and MemOS (2025), and ClawVM (2026).
- **Runtime-owned eviction is not novel either.** AIOS LRU-K (over agent memory items, not prompt context), ClawVM (harness-owned prompt residency, explicitly contrasted with MemGPT's model-driven paging) and CWL (LLM-free deterministic eviction) all have it.
- **Persistent contexts with suspend/resume have precedent.** AIOS's snapshot and restore is context switching for scheduling LLM calls. CVM's persistent contexts that can be suspended and resumed are closer to session persistence (Letta agents are persisted in a DB), so the precise difference needs stating.
- **Remaining differentiators for CVM, versus ClawVM:**
  - an object-count resident set (about 32 objects) rather than a token budget;
  - a model-issued instruction set (READ / TRAVERSE / SEARCH / FAULT / EVIDENCE / WRITE) over URI handles to a large external *world* graph, rather than agent-session state (plans, preferences, tool outputs);
  - scaling experiments where the world grows from 1e3 to 1e6 objects;
  - live-model end-to-end evidence that notes are necessary under bounded residency.
- ClawVM already claims "observable faults", refetch faults, a Denning-derived thrash index, pointer handles, provenance-checked writeback and an LRU comparison. A CVM paper must cite and differentiate from it.

### Gaps
- I did not read AIOS's appendix A.5 for exact memory-manager semantics, or its precise speedup figure (the HTML stripped the number).
- I did not survey "Memory-as-Action" (Zhang et al. 2025), Text2Mem or SagaLLM directly; they are cited only via ClawVM's related work ([§6](https://arxiv.org/html/2604.10352)).
- EfficientAgent ([arXiv 2609.33762](https://arxiv.org/html/2609.33762)) reportedly applies Denning load control to KV-cache offloading for concurrent agents. I saw this as a search snippet only. It is the serving layer, not semantic context.

## Q3. Has anyone measured "thrashing" / repeated re-retrieval in LLM agents, or applied Denning working-set theory to LLM context?

### Takeaway
Yes, partially, and recently. ClawVM defines a thrash index (paging events / hits) explicitly adapted from Denning 1968, and counts refetch and duplicate-tool faults. VideoLoop (Sep 2026) names "semantic thrashing" after Denning, but measures it indirectly through a blind-judge answerability test. Ledger and TraceLab quantify redundant re-execution and re-prefill. CVM's "re-materialization rate" therefore has close conceptual precedent, chiefly ClawVM's refetch faults and thrash index. I found no work that relates measured thrash to a working-set size swept against world size, or that shows a notes-versus-no-notes phase change under fixed residency.

### Cited Findings
- ClawVM "thrash index: the ratio of paging events to hits over the run … adapting the classical thrashing ratio (Denning, 1968)". Paging events "explicit faults plus duplicate-signature alerts". Across all utility-weight configurations, thrash was identical at 0.901, at budget 180. — [arXiv 2604.10352 §3, App. A, §5.2](https://arxiv.org/html/2604.10352)
- ClawVM refetch fault: "a tool result re-retrieved after eviction". This is effectively a re-materialization event. — [arXiv 2604.10352 §3](https://arxiv.org/html/2604.10352)
- VideoLoop (Huang et al., Rochester/Microsoft; arXiv 29 Sep 2026): "semantic thrashing, in analogy to OS thrashing (Denning, 1968b): the agent expends increasing computational effort while its grounding on prior findings degrades". It argues append-only memory cannot remove noise "without a rewrite operator", and proposes a bounded, rewritten working memory plus an unbounded filesystem of past observations. The thrash diagnostic is a symmetric-difference "state divergence", described as "a conceptual diagnostic rather than a theorem-like reduction". The empirical proxy is a blind judge reading only the context (81.1% vs 60.9% on the hardest quarter of VideoMME-long). — [arXiv 2609.38119](https://arxiv.org/html/2609.38119v1)
- Ledger: agents "re-execute work whose results are still valid". The layer returns cached results and flags redundant repetition. — [arXiv 2608.00808](https://arxiv.org/abs/2608.00808)
- TraceLab (coding-agent traces, about 4,300 sessions from Claude Code and Codex): it reports that about 81% of append tokens are "redundant" prefills caused by KV-cache eviction. This is serving-level re-materialization, not semantic. — [TraceLab paper](https://tracelab.cs.washington.edu/paper.pdf) (search snippet only; not read in full)
- Cooperative Memory Paging (Liu et al., arXiv 14 Apr 2026, **withdrawn** 24 May 2026 over authorship). Evicted segments are replaced by keyword bookmarks `[pN:keywords]` and the model gets a `recall()` tool. It ablates eviction policies ("FIFO best on synthetic, LFU on LoCoMo"). "The model triggers recall() 96% of the time but selects the correct page only 57%." — [arXiv 2604.12376](https://arxiv.org/abs/2604.12376)
- The two surveys checked full-text (Context Engineering 2507.13334; Memory for Autonomous LLM Agents 2603.07670) contain zero occurrences of "thrash", "working set", "page fault" or "Denning". Neither does the Root Theorem paper (2604.20874). — [arXiv 2507.13334](https://arxiv.org/abs/2507.13334); [arXiv 2603.07670](https://arxiv.org/abs/2603.07670); [arXiv 2604.20874](https://arxiv.org/abs/2604.20874)

### Inferences
- "Thrashing" as a named, measured quantity for LLM agent context exists as of April 2026 (ClawVM) and September 2026 (VideoLoop). CVM cannot claim to introduce the concept. It could still claim:
  - a specific operationalization (re-materialization rate over a URI-addressed world);
  - a demonstration that thrash causes task failure under a fixed object-count working set;
  - remediation through model-written notes.
- CVM's result that notes plus 2 resident objects suffice resembles VideoLoop's finding that a rewritten bounded working memory beats append-only. VideoLoop's setting is video, its memory is rewritten by an inner LLM loop, and it has no runtime LRU.

### Gaps
- I did not read TraceLab or "Agentic AI Workload Characteristics" ([arXiv 2605.26297](https://arxiv.org/pdf/2605.26297)) in full; they surfaced via search only.
- I found no paper sweeping working-set size against external-store size from 1e3 to 1e6 objects for an LLM agent.

## Q4. Context-engineering and memory surveys: what taxonomy do they give, and do they name anything matching CVM?

### Takeaway
The surveys classify MemGPT-style paging as "hierarchical memory / virtual context management" and classify control as heuristic, prompted self-control, or learned. None names a runtime-owned bounded working set, a page-fault primitive, handle-based dereferencing, or thrashing. The Root Theorem paper argues for bounded "homeostatic" memory with external verification, but in information-theoretic terms with a single-author engineering demonstration.

### Cited Findings
- "A Survey of Context Engineering for LLMs" (Mei et al., ICT/CAS; arXiv v2 21 Jul 2025; over 1,400 papers). The taxonomy has two layers:
  - Components: (1) Context Retrieval and Generation, (2) Context Processing, (3) Context Management ("memory hierarchies, compression, and optimization").
  - System implementations: RAG, Memory Systems, Tool-Integrated Reasoning, Multi-Agent Systems.
  — [arXiv 2507.13334](https://arxiv.org/abs/2507.13334)
- The same survey, §4.3.2: "OS-inspired hierarchical memory systems implement virtual memory management concepts, with MemGPT exemplifying this approach … with memory management through function-calling capabilities enabling autonomous paging decisions." It groups PagedAttention (KV cache) under the same heading. — [arXiv 2507.13334](https://arxiv.org/html/2507.13334)
- "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers" (Pengfei Du; arXiv 8 Mar 2026):
  - It formalizes memory as a "write–manage–read loop" and uses a three-dimensional taxonomy (temporal scope, representational substrate, control policy).
  - It reviews five mechanism families: context-resident compression, retrieval-augmented stores, reflective self-improvement, hierarchical virtual context, and policy-learned management.
  - — [arXiv 2603.07670](https://arxiv.org/abs/2603.07670)
- The same survey's "control policy" dimension, called "the most consequential—and least discussed": "who decides what to store, what to retrieve, and what to discard". It has three values:
  - heuristic control (hard-coded rules);
  - prompted self-control ("MemGPT's core_memory_append and archival_memory_search are canonical");
  - learned control (AgeMem, trained with reinforcement learning).
  — [arXiv 2603.07670 §3](https://arxiv.org/html/2603.07670)
- The same survey on hierarchical memory: "The Achilles' heel of hierarchical memory is orchestration. Page the wrong things in and you waste precious context tokens; archive too aggressively …" — [arXiv 2603.07670 §4.4](https://arxiv.org/html/2603.07670)
- "The Root Theorem of Context Engineering" (Odriozola Schick, independent; arXiv [cs.CC] dated 29 Mar 2026, v2.5):
  - Principle: "maximize signal-to-token ratio within bounded, lossy channels".
  - Consequences include a gate "triggered by fidelity thresholds, not capacity limits", "homeostatic persistence—accumulate, compress, rewrite, shed", and the need for "an external verification gate".
  - "Append-only systems necessarily exceed their effective window in finite time."
  - Engineering proof: "a 60+-session persistent architecture demonstrating stable memory footprint."
  - It calls MemGPT/Letta "the most architecturally serious attempt."
  — [arXiv 2604.20874](https://arxiv.org/abs/2604.20874)
- "Context Cartography" (Wu, NVIDIA, et al.; arXiv 21 Mar 2026). It has three zones: black fog (unobserved), gray fog (stored memory) and visible field (active reasoning surface). It defines seven operators (reconnaissance, selection, simplification, aggregation, projection, displacement, layering), analyzes Claude Code, Letta, MemOS and OpenViking, and proposes rather than runs a benchmark. — [arXiv 2603.20578](https://arxiv.org/abs/2603.20578)

### Inferences
- In the Du survey's taxonomy, CVM's runtime LRU eviction combined with model-issued dereference and notes is a hybrid: heuristic control of eviction, prompted self-control of fetch and notes. That hybrid is not singled out as a category, which is a framing opportunity, but ClawVM and CWL already occupy it empirically.
- The Root Theorem's "stable memory footprint" and the "visible field vs gray fog" of Context Cartography are conceptual cousins of CVM's bounded working set. Neither measures footprint against world size.

### Gaps
- I did not check whether any survey published after August 2026 cites ClawVM, VISTA or CWL as a "runtime-managed residency" category.

## Q5. Is "page fault" as an explicit, model-issued primitive (distinct from search) present in prior work?

### Takeaway
I found no prior system with a model-issued instruction literally named FAULT, as distinct from SEARCH, that dereferences a known handle. The nearest equivalents:
- ClawVM's pointer pages ("resolvable handle") with harness-observed faults; the faults are detected and logged by the runtime, not issued by the model.
- VISTA's archived blocks replaced by "compact handles", which the agent recovers with recovery tools.
- The withdrawn Cooperative Paging paper's `recall()` over bookmark IDs.
- Letta's open/close of files by name.
- MemGPT's archival and recall search functions, which are search, not dereference.

### Cited Findings
- ClawVM: faults are observed by the harness ("the system raises observable faults that make the failure diagnosable and replayable"), and pointer representations are "a resolvable handle plus minimal metadata" that "preserve enough to reconstruct the full page on demand." — [arXiv 2604.10352 §1, §3](https://arxiv.org/html/2604.10352)
- VISTA: "archived blocks are replaced by compact handles and summaries, while their original bytes" remain recoverable. "Every actionable unit must have a stable block ID or handle." Ablations confirm "the dashboard matters beyond archive and recovery tools". — [arXiv 2606.30005 §2](https://arxiv.org/html/2606.30005)
- Cooperative paging: evicted segments become `[pN:keywords]` bookmarks and the model calls `recall()` to fetch by page. The bottleneck is "bookmark discrimination" (correct page only 57% of the time). Withdrawn. — [arXiv 2604.12376](https://arxiv.org/abs/2604.12376)
- MemGPT: data movement happens via LLM-generated function calls such as archival_memory_search and core_memory_append. Retrieved recall messages are "append[ed] … to the back of the queue to reinsert them into the LLM's context window". — [arXiv 2310.08560 §2.2–2.3](https://arxiv.org/html/2310.08560); [arXiv 2603.07670 §4.4](https://arxiv.org/html/2603.07670)
- Letta Files: `open` reads specific files by name and closes others. — [Letta Filesystem blog](https://www.letta.com/blog/letta-filesystem/)

### Inferences
- **"Dereference a handle to an evicted object" is not new as a capability.** ClawVM pointers, VISTA handles, cooperative-paging bookmarks and Letta file open all do it.
- **Defensible narrower claims for CVM:**
  - a typed instruction set where FAULT (re-materialize a known URI) is distinguished from SEARCH (discover unknown URIs) and from TRAVERSE (follow graph edges);
  - the fault rate is instrumented as the thrash signal.
- **Precise contrast with ClawVM.** In ClawVM a fault is a *failure the harness detects*; in CVM a fault is *a legitimate model action whose frequency is the thrash metric*.

### Gaps
- I did not exhaustively search the 2026 agent-harness literature, for example Claude Code or Codex internal docs, or "memory as action" papers, for a tool literally called "fault" or "page_in".

## Q6. Per-element closest prior work (synthesis map)

### Takeaway
Every individual CVM element has prior art, and ClawVM (Apr 2026) covers the largest number of elements in a single system. CVM's defensible novelty is in the combination and in the empirical claims:
- a constant object-count working set while a URI-addressed world grows from 1e3 to 1e6;
- re-materialization rate as the thrash measure in a live-model loop;
- the notes ablation (bounded residency without notes fails, and with notes works at 2 resident objects);
- capabilities and a provenance verifier on the same instruction set.

### Cited Findings
- **OS/virtual-memory framing.** Prior art: MemGPT (2023), Karpathy LLM OS (2023), AIOS (COLM 2025), MemoryOS (2025), MemOS (2025), ClawVM (2026). — [2310.08560](https://arxiv.org/abs/2310.08560); [2403.16971](https://arxiv.org/abs/2403.16971); [2506.06326](https://arxiv.org/abs/2506.06326); [2507.03724](https://arxiv.org/abs/2507.03724); [2604.10352](https://arxiv.org/abs/2604.10352)
- **Page-fault primitive and handles.**
  - ClawVM pointer pages and fault taxonomy — [2604.10352](https://arxiv.org/html/2604.10352)
  - VISTA handles — [2606.30005](https://arxiv.org/html/2606.30005)
  - Cooperative paging recall() (withdrawn) — [2604.12376](https://arxiv.org/abs/2604.12376)
- **Runtime-owned vs model-owned eviction.**
  - Model-owned: MemGPT ([2310.08560](https://arxiv.org/html/2310.08560)), VISTA ([2606.30005](https://arxiv.org/html/2606.30005)).
  - Runtime-owned: ClawVM (harness knapsack; LRU variant tested) ([2604.10352](https://arxiv.org/html/2604.10352)), CWL (LLM-free eviction over agent-annotated episodes) ([2606.11213](https://arxiv.org/abs/2606.11213)), AIOS LRU-K for agent memory items ([2403.16971](https://arxiv.org/html/2403.16971)).
  - Letta file LRU (secondary source) ([DeepWiki](https://deepwiki.com/letta-ai/letta/2.3-tool-system)).
- **Working set (Denning).**
  - ClawVM thrash index — [2604.10352](https://arxiv.org/html/2604.10352)
  - VideoLoop semantic thrashing — [2609.38119](https://arxiv.org/html/2609.38119v1)
- **Persistent contexts / context switching.**
  - AIOS snapshot/restore for interrupting LLM calls — [2403.16971 §3.4](https://arxiv.org/html/2403.16971)
  - Letta persisted agents and blocks — [Letta blog](https://www.letta.com/blog/memory-blocks)
  - ClawVM lifecycle-complete writeback at reset/compaction — [2604.10352](https://arxiv.org/html/2604.10352)
- **Notes/scratchpad.**
  - MemGPT working context — [2310.08560 §2.1](https://arxiv.org/html/2310.08560)
  - Letta memory blocks — [Letta blog](https://www.letta.com/blog/memory-blocks)
  - A-MEM notes (long-term, not a scratchpad) — [2502.12110](https://arxiv.org/abs/2502.12110)
  - VideoLoop rewritten bounded working memory — [2609.38119](https://arxiv.org/html/2609.38119v1)
- **Thrashing as a measured quantity.**
  - ClawVM thrash index and refetch faults — [2604.10352](https://arxiv.org/html/2604.10352)
  - Ledger redundant re-execution — [2608.00808](https://arxiv.org/abs/2608.00808)
  - TraceLab redundant prefill (KV level, snippet only) — [TraceLab](https://tracelab.cs.washington.edu/paper.pdf)
- **Capabilities / access control.**
  - AIOS access manager (privilege groups) — [2403.16971 §3.8](https://arxiv.org/html/2403.16971)
  - MemOS governance — [2507.03724](https://arxiv.org/abs/2507.03724)
  - ClawVM scope checks — [2604.10352 App. A](https://arxiv.org/html/2604.10352)
- **Provenance verification.**
  - ClawVM rejects writeback with dangling evidence_ref — [2604.10352 App. A](https://arxiv.org/html/2604.10352)
  - MemOS "provenance auditing" — [2507.03724](https://arxiv.org/abs/2507.03724)
- **Bounded-footprint claims.**
  - CWL "stable ceiling" over 80M tokens — [2606.11213](https://arxiv.org/abs/2606.11213)
  - Root Theorem "stable memory footprint" over 60+ sessions — [2604.20874](https://arxiv.org/abs/2604.20874)

### Inferences
- **Risk.** A reviewer aware of ClawVM could see CVM's "runtime-owned residency, faults, thrash, LRU, handles, provenance" as incremental. CVM must explicitly position against ClawVM (EuroMLSys '26), VISTA (Jul 2026) and CWL (May 2026), in addition to MemGPT and AIOS.
- **Strongest differentiators, if CVM's evidence holds:**
  - (a) world-scale invariance: a constant resident set of about 12 objects (about 2k tokens) across a 1000x world growth. None of the above report a world-size sweep.
  - (b) the notes ablation, a causal result on *why* bounded residency works or fails.
  - (c) the model cannot evict at all: stricter than ClawVM (which still selects by utility) and the opposite of MemGPT and VISTA.
  - (d) a unified instruction set that separates FAULT from SEARCH and TRAVERSE over a world graph rather than over session transcripts.
- On the notes ablation: MemGPT's design already assumes a model-writable working context, but it never tested residency without it.

### Gaps
- I did not verify whether ClawVM's live-hook or end-to-end follow-up work (if any, after Apr 2026) adds model-in-the-loop task results that would narrow CVM's claim (b).
- The Letta LRU file-eviction detail rests on a DeepWiki summary, not primary code or docs.
