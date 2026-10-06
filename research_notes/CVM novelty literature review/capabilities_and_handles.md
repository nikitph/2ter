# Capabilities and Handles: Prior Work Relevant to CVM (Cognitive Virtual Memory)

Research note scope: (a) capability-based / runtime-enforced security for LLM agents, and (b) passing opaque references/handles to LLMs instead of serialized content. Current as of 2026-10-06. Caveat: arxiv.org, huggingface.co, alphaxiv.org and simonwillison.net were blocked for direct fetching from this environment, so most arXiv claims below rely on search-engine snippets of the abstract/HTML pages (URLs given) rather than full-text reads. Claims that need full-text confirmation are flagged.

## Q1. Do CaMeL, Dual LLM, FIDES, IsolateGPT/SecGPT, f-secure, Progent, MELON, Design Patterns, AgentDojo use per-context/per-process capabilities and capability inheritance for sub-agents?

### Takeaway
Runtime (non-prompt) enforcement is well established (CaMeL, FIDES, f-secure, Progent, IsolateGPT), but these mostly attach "capabilities" or labels to **data values** (provenance/IFC) or to **tool-call policies**, not to a process-like address space with namespace-scoped verbs (READ/SEARCH/WRITE over URI globs) that children inherit as subsets. The closest match to CVM's "context = process with explicit capabilities" framing is **Agent libOS (arXiv 2606.03895, June 2026)**, and the closest to monotonic sub-agent attenuation are several 2026 delegation papers. CVM is therefore not novel in "runtime-enforced capabilities for agents" per se; its distinctiveness must rest on the combination (URI-namespace capabilities + handle-only traversal + fault semantics + empirical side-channel/retry observations).

### Cited Findings
**CaMeL (Debenedetti et al., Google DeepMind, arXiv 2503.18813, Mar 2025)**
- CaMeL = "CApabilities for MachinE Learning"; a privileged LLM (P-LLM) writes pseudo-Python from the trusted user query only; a quarantined LLM (Q-LLM) parses untrusted data without tool access and returns schema-constrained data — [arXiv HTML](https://arxiv.org/html/2503.18813v2); [Simon Willison on CaMeL](https://simonwillison.net/2025/Apr/11/camel/)
- "Capabilities" in CaMeL are metadata attached to **each value**, tracking its sources and allowed recipients; a custom Python interpreter maintains a data-flow graph of every variable and checks policies before tool calls — [arXiv HTML](https://arxiv.org/html/2503.18813v2)
- Reported 0 successful attacks with Claude 3.5 Sonnet on AgentDojo vs. 8 for the next-best defense (tool filter) — search summary of [arXiv HTML](https://arxiv.org/html/2503.18813v2) (verify exact table in full text)
- Follow-up: CaMeLoT adds temporal-logic static verification/liveness to CaMeL — [arXiv 2609.18674](https://arxiv.org/pdf/2609.18674)

**Dual LLM pattern (Simon Willison, Apr 2023)**
- Privileged LLM never sees untrusted content; a quarantined LLM processes it and results are stored by a controller and referred to via symbolic variables (e.g. `$VAR1`) — [simonwillison.net 2023/Apr/25](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/) (page not fetchable here; description consistent with [Design Patterns paper listing Dual LLM](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/) and [CaMeL write-up](https://simonwillison.net/2025/Apr/11/camel/))

**FIDES (Costa, Köpf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Béguelin; Microsoft; arXiv 2505.23643, May 2025)**
- Planner that tracks confidentiality and integrity labels, deterministically enforces policies, and introduces primitives for **selectively hiding information** (variables the planner can reference without seeing) — [arXiv 2505.23643](https://arxiv.org/abs/2505.23643); code [github.com/microsoft/fides](https://github.com/microsoft/fides)
- Labels: integrity (trusted/untrusted) × confidentiality (public/private/user_identity); stops all prompt injections in its benchmark with appropriate policies — [arXiv PDF](https://arxiv.org/pdf/2505.23643)
- A third-party analysis reports forging security labels in FIDES middleware — [APIsec Labs](https://labs.apisec.ai/research/articles/trust-me-bro-forging-security-labels-fides/)

**f-secure LLM system (Wu, Cecchetti, Xiao; arXiv 2409.19091, Sep 2024)**
- IFC-based disaggregation into a context-aware pipeline with dynamically generated structured executable plans; a security monitor filters untrusted input from planning; formal models provided — [arXiv 2409.19091](https://arxiv.org/abs/2409.19091); [code](https://github.com/fzwark/Secure_LLM_System)

**IsolateGPT / SecGPT (Wu et al., NDSS 2025; S&P 2024 poster)**
- Hub-and-spoke: each app runs in an isolated spoke (own LLM instance, memory) in a separate OS process restricted by seccomp/setrlimit; inter-spoke communication only via hub-mediated protocol requiring user permission — [arXiv 2403.04960](https://arxiv.org/pdf/2403.04960v1); [GitHub](https://github.com/llm-platform-security/SecGPT)
- Isolation unit is the **app**, not a task-scoped context with namespace capabilities; no capability subset inheritance described in sources found.

**Progent (Shi, He, Wang, Li, Wu, Guo, Song; arXiv 2504.11703, Apr 2025)**
- Privilege = policy of symbolic rules over tool names and arguments; default-deny; deterministic allow/block at tool-call time — [arXiv 2504.11703](https://arxiv.org/abs/2504.11703); [v3 HTML](https://arxiv.org/html/2504.11703v3)
- LLM generates/updates policy; an SMT solver classifies updates as narrowing (auto-applied) or expansion (needs approval), so the action space can only shrink without approval — [arXiv v3](https://arxiv.org/html/2504.11703v3). This monotonic-narrowing property is the closest analogue among the named papers to CVM's subset-only child capabilities, but it is over time within one agent, not across a parent/child context tree.

**MELON (Zhu et al., ICML 2025, arXiv 2502.05174)**
- Detection, not capabilities: re-executes the trajectory with the user prompt masked and flags tool calls that persist (independent of user intent) as injected — [arXiv 2502.05174](https://arxiv.org/abs/2502.05174); [GitHub](https://github.com/kaijiezhu11/MELON)

**Design Patterns for Securing LLM Agents (Beurer-Kellner, Buesser, Creţu, Debenedetti, ..., Tramèr, Volhejn; arXiv 2506.08837, Jun 2025)**
- Six patterns: Action-Selector, Plan-Then-Execute, LLM Map-Reduce, Dual LLM, Code-Then-Execute, Context-Minimization — [arXiv 2506.08837](https://arxiv.org/abs/2506.08837); [Willison summary](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/)

**Newer, closer work (2026)**
- **Agent libOS (arXiv 2606.03895, June 2026)**: library-OS-inspired runtime; agent = `AgentProcess` with process identity, process-local Object Memory, tool table, child processes, budgets, checkpoints and **explicit capabilities**; "tools are libc-like wrappers and runtime primitives are the authority boundary"; admission = process identity ∧ Task Authority ceiling ∧ typed Capabilities ∧ policy/human approval ∧ budgets — [arXiv HTML](https://arxiv.org/html/2606.03895); [arXiv abs](https://arxiv.org/abs/2606.03895)
  - Per its README (summarized by a fetch tool, verify): capability requirements of images/skills are declarations, **not ambient grants**; children get only what Task Authority manifests, current process capabilities, data-flow policy and budgets authorize — "no automatic propagation down process trees"; denials fail closed before effects and are audited — [GitHub Agent-libOS](https://github.com/yingqi-z20/Agent-libOS)
  - It explicitly does not claim to eliminate prompt injection — [arXiv HTML](https://arxiv.org/html/2606.03895)
- **"LLM Agent Capabilities Should Follow Task Intent and Context Source" (arXiv 2609.14631, Sep 2026)**: deterministic checker enforcing **monotonic narrowing** before side effects, context placement or delegation; each delegation attenuates so a subtask gets capabilities narrower than its parent — [arXiv HTML](https://arxiv.org/html/2609.14631) (from search snippet; full text not read)
- Agent-skill capability model: child skill receives at most the parent's capabilities (PoLA) — [arXiv 2603.00195](https://arxiv.org/pdf/2603.00195) (snippet)
- Further delegation/authorization surveys: [Bounded Agents, 2608.15888](https://arxiv.org/pdf/2608.15888); [Delegation Without Trust, 2609.00267](https://arxiv.org/pdf/2609.00267); [Authorization Architectures for Tool-Using AI Agents, 2609.15906](https://arxiv.org/pdf/2609.15906); [Mandatory Access Control for privilege escalation, 2601.11893](https://arxiv.org/pdf/2601.11893); [AgenticOS workshop @ SOSP 2026](https://os-for-agent.github.io/)

### Inferences
- "Capabilities" is overloaded: CaMeL = per-value provenance tags (IFC-like); Progent = per-agent tool/argument policy; Agent libOS / 2609.14631 = per-process authority with attenuation (classic OS/ocap sense). CVM aligns with the third sense, which is the most recent and least saturated but no longer empty as of mid/late 2026.
- None of the named 2024-2025 systems (CaMeL, FIDES, f-secure, Progent, MELON, IsolateGPT) appear to define capabilities as verb × URI-namespace grants per context with automatic subset inheritance for child contexts; this specific shape seems unclaimed in what I found, but Agent libOS + 2609.14631 together cover most of the conceptual ground.
- CVM's side-channel observation (incident -> claims naming candidate causes) is a concrete instance of the well-known problem that access control on objects does not bound information flow; FIDES/CaMeL/f-secure (IFC) exist precisely for this. CVM should position its fix (scoping) as access control and acknowledge IFC as the principled alternative.

### Gaps
- Could not read CaMeL full text to confirm whether it discusses sub-agents/delegation (I found nothing indicating it does).
- AgentDojo (Debenedetti et al., NeurIPS 2024 D&B) is a benchmark, not a defense; no source fetched this session to cite its details.
- Could not verify whether Agent libOS child processes default to a strict subset of parent capabilities (README summary says explicit grant, bounded by parent); needs full-text check.

## Q2. Handle/reference passing instead of serialized content — and has anyone measured context growth by-value vs by-reference?

### Takeaway
Handle-based data passing is widespread: Dual LLM `$VAR`s and CaMeL/FIDES variables (for security), RLM context-as-REPL-variable, Anthropic programmatic tool calling, MCP `resource_link`, LangChain Deep Agents file offloading, and the "memory pointer" paper (for context efficiency). Token savings have been measured (37% for programmatic tool calling; ~7x for memory pointers; 20M tokens vs 1,234 in one case), but I found no study that scales a **graph/world size** and reports context growth curves for by-value vs by-reference traversal the way CVM's 1.5k->116k vs flat result does. CVM's measurement shape (hub node with ~14k dependents) appears distinctive; the idea itself is not.

### Cited Findings
- **CaMeL**: P-LLM code operates on variables whose values it never sees; Q-LLM returns structured data into them — [arXiv HTML](https://arxiv.org/html/2503.18813v2)
- **FIDES**: primitives for selectively hiding information from the planner (planner references values via variables) — [arXiv 2505.23643](https://arxiv.org/abs/2505.23643)
- **Recursive Language Models (Zhang, Kraska, Khattab; arXiv 2512.24601, Dec 2025)**: the prompt/context is loaded as a string variable in a persistent Python REPL; the model writes code to peek/decompose it and recursively calls itself on sub-prompts; handles inputs beyond GPT-5's 272K window where GPT-5 degrades — [arXiv 2512.24601](https://arxiv.org/pdf/2512.24601); [blog](https://alexzhang13.github.io/blog/2025/rlm/); [code](https://github.com/alexzhang13/rlm)
- **Anthropic programmatic tool calling**: Claude writes code that calls tools in a sandbox; intermediate results stay out of context; average usage on complex research tasks dropped from 43,588 to 27,297 tokens (37%); example: 2,000+ expense line items never enter context. Tool Search Tool claimed 85% token reduction on tool definitions — [Anthropic engineering: advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- **Memory pointers (Labate et al., arXiv 2511.22729, Nov 2025)**: large tool outputs stored outside context; model handles short pointers; each tool mirrored with a wrapper that resolves pointers and stores large outputs; ~7x fewer tokens than the traditional workflow — [arXiv 2511.22729](https://arxiv.org/abs/2511.22729). AWS dev write-up: a materials-science workflow used 20M tokens and failed vs 1,234 tokens and succeeded with pointers — [DEV/AWS](https://dev.to/aws/ai-context-window-overflow-memory-pointer-fix-3akc)
- **LangChain Deep Agents**: ToolMessages over ~2,000 tokens are written to disk and replaced with a path plus 10-line preview; agent re-reads via a file tool — [LangChain docs (context engineering)](https://docs.langchain.com/oss/python/deepagents/context-engineering) (as summarized by search; verify threshold)
- **MCP `resource_link`**: since spec 2025-06-18, tools may return a resource_link content block (uri, name, mimeType, size...) instead of inlining content; recommended for large/reused payloads; client support uneven (e.g. AgentScope dropped them) — [Wix Engineering on MCP resources](https://medium.com/wix-engineering/mcp-resources-all-you-need-to-know-34435249a451); [shopware issue](https://github.com/shopware/shopware/issues/19966); [agentscope bug](https://github.com/agentscope-ai/agentscope/issues/2798)
- **Agent libOS Object Memory**: typed objects, namespaces, ownership, links, `MemoryView` context selection, external references; README summary says the model interacts via tool calls/structured results rather than model-facing handles — [GitHub](https://github.com/yingqi-z20/Agent-libOS) (verify)

### Inferences
- CVM's "TRAVERSE returns references, materialize on FAULT/READ" is effectively demand paging over an object graph; RLM and memory-pointers are the closest efficiency precedents, MCP `resource_link` the closest protocol precedent for URI handles.
- CVM's distinctive combination is that the same URI handle is both the **unit of capability check** and the **unit of materialization** — in CaMeL/FIDES variables serve security; in RLM/pointers they serve context efficiency; I found no source that unifies both with URI-namespace capabilities.
- The 1.5k->116k growth result is a predictable consequence of by-value fan-out; reviewers will likely accept it as an illustration rather than a novel finding unless framed as a scaling curve with baselines (e.g. vs programmatic tool calling, vs pagination/truncation).

### Gaps
- No source found measuring context growth as a function of **world/graph size** for by-value vs by-reference results.
- CodeAct (Wang et al. 2024), Letta/MemGPT memory blocks, and OpenAI/Anthropic "context offloading to filesystem" posts were not fetched this session; not cited.
- Dual LLM `$VAR` details rely on secondary descriptions since Willison's 2023 post could not be fetched.

## Q3. Object-capability (ocap) literature applied to AI agents, and LLM agents persistently retrying denied actions

### Takeaway
Ocap framing for agents is now explicit in 2025-2026 work (possession of reference = authority; attenuable tokens like Macaroons/Biscuits; delegation narrowing). On retry behavior, there is direct empirical work: deny-signal compliance is strongly model-dependent and mid-flight halts are ignored, and engineering discussion of retry loops on denied commands exists — so CVM's "~5 capability faults per task" observation corroborates rather than discovers the phenomenon, though a per-task fault count under a hard runtime boundary is still a useful data point.

### Cited Findings
- Ocap principle stated for agents: possession of a reference grants authority; authority transferred by passing references, not ambient identity; Macaroons/Biscuits allow offline attenuation where holders can add caveats but not widen — [arXiv 2510.25819, Identity Management for Agentic AI](https://arxiv.org/html/2510.25819v1) (snippet)
- Agent libOS: capabilities are typed and explicit, not ambient — [arXiv HTML](https://arxiv.org/html/2606.03895)
- **"Will the Agent Recuse, and Will It Stop?" (arXiv 2606.06460)**: deny-signal compliance at the access door ranges 100% (GPT-4o-mini, Claude) to 55-75% (Gemini, GPT-4o); open-weights agent largely failed to engage; mid-flight halt signals: 0/40 agents stopped; halts embedded in tool output acknowledged 0/20 vs 20/20 as prompt messages — [arXiv HTML v3](https://arxiv.org/html/2606.06460v3)
- MetaPermit (AgentDojo/AgentDyn): after a denial with feedback the agent can retry with request-aligned calls — [arXiv 2609.31039](https://arxiv.org/html/2609.31039)
- Infinite agentic loops defined and studied as a failure mode — [arXiv 2607.01641](https://arxiv.org/html/2607.01641v1)
- Practitioner issue: models spend turns retrying denied commands; proposed bounded retry budgets per canonical operation — [Aether-Agent issue #285](https://github.com/AetherAI3/Aether-Agent/issues/285)
- Related enforcement-gap work: [Stop Means Stop, 2607.14166](https://arxiv.org/pdf/2607.14166); [KAIJU executive kernel, 2604.02375](https://arxiv.org/pdf/2604.02375); [Out-of-Band Policy Enforcement, 2608.27646](https://arxiv.org/pdf/2608.27646)

### Inferences
- CVM's finding that the model kept probing the denied namespace instead of adapting is consistent with 2606.06460's message that signal *delivery channel* matters; CVM could test whether richer CAPABILITY_FAULT messages (e.g. listing granted namespaces) reduce retries — a natural ablation.
- The side-channel-then-retry sequence also resembles "probing policy boundaries" noted for blocked tool calls in conversational loops (search summary; primary source not pinned down).

### Gaps
- No primary source found quantifying "faults per task" under hard capability denial across models; 2606.06460 measures compliance rates, not retry counts.
- Did not find a formal ocap (E-language / Mark Miller lineage) paper specifically about LLM agents in sources reached this session.
