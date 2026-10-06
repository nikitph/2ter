# Provenance-ledger citation verification in CVM: prior work on grounding, attribution and runtime-enforced citation

Scope: the CVM component in which each piece of materialized external state gets a stable `[fact:N]` id in a per-context provenance ledger, the final ANSWER must cite fact ids, and a runtime verifier rejects the answer (forcing a retry, i.e. a FAULT) if the cited ids were never materialized, if the answer entity is in no cited fact, or if a claim verdict cites no fact about the claim. The invariant is "external fact not in working set => cannot assert it; need => FAULT".

Method note: arxiv.org and huggingface.co were blocked for direct fetch in this session (egress proxy). Findings about 2024-2026 arXiv papers come from search-result abstracts and snippets, not full-text reads. Older canonical papers (AIS, AQA, RARR, Self-RAG, FActScore, SAFE, FLARE and others) are cited to their arXiv abstract pages from established knowledge, and I did not re-fetch them this session. The report writer should treat specific numbers from those papers as needing a spot-check. The Anthropic Citations docs were fetched and quoted directly.

## Q1. Per-fact identifiers and citation-required answers (ALCE, AQA, LongCite, Anthropic Citations, span/ID citation)

### Takeaway
Giving retrieved units ids and asking the model to cite them is standard. ALCE uses `[1][2]` passage ids, LongCite uses sentence-level ids, the Anthropic Citations API uses document and chunk indices, and FullCite uses a citation grammar. In all of these the id refers to a retrieved document or passage. None ties the id to a per-context ledger of everything materialized into the working set, as an operating system tracks pages. The closest structural analogues are the Anthropic Citations API (it guarantees that pointers are valid) and constrained decoding over a citation grammar (FullCite). Neither requires the answer to cite, and neither checks that the citation is about the claim.

### Cited Findings
- ALCE (Gao, Yen, Yu, Chen; EMNLP 2023) is "the first benchmark for Automatic LLMs' Citation Evaluation". The system retrieves passages and generates text that cites them. It is scored on fluency, correctness and citation quality (citation recall and precision via NLI). On ELI5, "even the best models lack complete citation support 50% of the time." This is an **evaluation** benchmark: citations are prompted, and support is measured after generation. — [ACL Anthology](https://aclanthology.org/2023.emnlp-main.398/); [arXiv 2305.14627](https://arxiv.org/abs/2305.14627)
- Attributed Question Answering (Bohnet et al., 2022) frames the task as producing an (answer, attribution) pair. It measures attribution with AutoAIS, an NLI model used as an automatic AIS rater, so it is **post-hoc evaluation**. — [arXiv 2212.08037](https://arxiv.org/abs/2212.08037) (not re-fetched this session)
- AIS, "Attributable to Identified Sources" (Rashkin et al.), is a human-annotation **evaluation framework**: is the output's information supported by a specific identified source? — [arXiv 2112.12870](https://arxiv.org/abs/2112.12870) (not re-fetched)
- LongCite (Zhang et al., 2024) trains long-context models to emit sentence-level citations. As I recall, the context is split into numbered sentence chunks and the model cites chunk-index ranges. This is the closest "fine-grained id in context" prompting format. Enforcement is **trained behaviour plus an evaluation benchmark (LongBench-Cite)**, not a runtime gate. — [arXiv 2409.02897](https://arxiv.org/abs/2409.02897) (format detail is from memory; verify)
- Anthropic Citations API: "Because the API parses citations into the response formats … and extracts `cited_text` directly, citations are guaranteed to contain valid pointers to the provided documents." "Internally, the model outputs citations in a standardized format that are then parsed into cited text and document location indices." The guarantee is **pointer validity** (the cited span exists in the supplied docs), which is the analogue of CVM's "cited id was materialized" check. The docs do not claim that every claim is cited, or that the cited span entails the claim. — [Claude Platform Docs: Citations](https://platform.claude.com/docs/en/build-with-claude/citations); [Anthropic announcement](https://www.anthropic.com/news/introducing-citations-api)
- FullCite (Yeginbergen, Wührl, Rogers, Agerri; arXiv June 2026) generates structured inline citations that link each claim to a document and an evidence span. It compares prompt-based generation, **constrained decoding over a citation grammar**, and post-hoc span alignment. Finding: LLMs identify the right documents well "but struggle to identify the precise supporting spans." — [arXiv 2606.07130](https://arxiv.org/abs/2606.07130)
- Locally-attributable grounded text generation (ACL 2024) produces sentence-level citations to concise spans. — [ACL Anthology 2024.acl-long.182](https://aclanthology.org/2024.acl-long.182.pdf)
- Practitioner pattern: "Each retrieved document gets an ID — [SRC-1], [SRC-2], or doc:42 — that the model can reference." Grounded generation "forces an LLM's output to be derivable from a supplied set of retrieved sources." — [ZeroEntropy concept page](https://zeroentropy.dev/concepts/grounded-generation/) (vendor explainer, not peer-reviewed)
- CiteBench (Funkquist et al.) benchmarks *scientific citation text generation*, a different task from attributed QA. Little relevance to CVM. — [arXiv 2212.09577](https://arxiv.org/abs/2212.09577) (not re-fetched)

### Inferences
- `[fact:N]` ids in context are not novel as a prompting format. The possibly novel parts are: (a) the id comes from a per-context provenance ledger of *materialization events* for any external state (tool results, memory pages, files), not from a retrieved-document list; (b) a citation is *mandatory* for the final answer, and its absence or invalidity is a fault, not a lower score.
- The Anthropic Citations API is the strongest commercial precedent for "a citation must point to something actually in context". It enforces this by parsing on the model side. It does not reject an uncited claim.

### Gaps
- I found no source showing a production API that *rejects* an answer which fails to cite. Citation features I saw make citing optional for each claim.
- I could not fetch the LongCite full text to confirm the exact chunk-id format.

## Q2. Runtime or structural enforcement versus post-hoc evaluation

### Takeaway
Most of the attribution literature is evaluation (AIS, AutoAIS, ALCE, AttributionBench, FActScore, SAFE). Inference-time methods are usually *repair* (RARR) or *learned self-critique* (Self-RAG), not hard rejection by a deterministic verifier. From 2025 to 2026 a cluster of agent papers moved toward runtime gates: ProvenanceGuard, Citation-Grounded Code Comprehension, EBTE, and CaMeL for security. These are the closest prior art for CVM's verifier. CaMeL tracks provenance for *security policy*, not truth grounding.

### Cited Findings
**Post-hoc evaluation**
- FActScore splits a generation into atomic facts and scores the fraction supported by a knowledge source. It is an evaluation metric. — [arXiv 2305.14251](https://arxiv.org/abs/2305.14251) (not re-fetched)
- SAFE (Search-Augmented Factuality Evaluator, Wei et al. 2024) uses an LLM plus Google Search to rate long-form factuality. It is an evaluation tool. — [arXiv 2403.18802](https://arxiv.org/abs/2403.18802) (not re-fetched)
- AttributionBench (Li et al. 2024) shows that automatic attribution evaluators, including fine-tuned NLI models and LLMs, struggle to judge whether a source supports a claim. This bears on how reliable any semantic verifier is. — [arXiv 2402.15089](https://arxiv.org/abs/2402.15089) (not re-fetched; check the exact F1 figures)
- "Evaluating Verifiability in Generative Search Engines" (Liu, Zhang, Liang 2023) audited commercial generative search engines: about 51.5% of generated sentences were fully supported by citations, and about 74.5% of citations supported their sentence. This is an audit, not enforcement. — [arXiv 2304.09848](https://arxiv.org/abs/2304.09848) (from memory; verify numbers)

**Inference-time, soft or repair**
- RARR (Gao et al. 2022) does post-hoc "research and revise": it retrieves evidence for a draft and edits unsupported content. It runs at inference time but *repairs* the output instead of rejecting it and forcing the generator to re-cite. — [arXiv 2210.08726](https://arxiv.org/abs/2210.08726) (not re-fetched)
- Self-RAG trains a model to emit reflection tokens (Retrieve, ISREL, ISSUP, ISUSE). ISSUP judges whether the output is supported. Segment-level beam search uses these tokens at inference time. Enforcement is *learned and model-internal*: the generator grades itself, with no external deterministic check. — [Self-RAG, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/25f7be9694d7b32d5cc670927b8091e1-Paper-Conference.pdf); [arXiv 2310.11511](https://arxiv.org/pdf/2310.11511)

**Runtime or structural gates (closest to CVM)**
- ProvenanceGuard (Multiverse Computing, Hugging Face blog) is "a post-generation verification layer that sits on top of a black-box MCP agent". It breaks answers into claims, finds the source for each claim, checks support, and emits per-claim verdicts and "a global allow/block decision". Experts flagged 139 claims that should not pass, and it caught 138. This is a *runtime block* but semantic (LLM or NLI based), and it blocks rather than forcing a retry. — [HF blog via search snippet](https://huggingface.co/blog/MultiverseComputingCAI/getting-the-source-right-not-just-the-fact-source) (fetch blocked; details from snippet only)
- Practitioner pattern (search snippet): "Provenance enforcement makes it structurally impossible for a response containing a figure absent from tool output to reach the user—such responses are blocked before delivery." This is the closest wording to CVM's invariant, applied to numbers. — [GitHub issue PenniLogic/ai-service #6](https://github.com/PenniLogic/ai-service/issues/6) (low-authority source)
- Citation-Grounded Code Comprehension (arXiv 2512.12117) requires LLMs to cite `[file:start-end]` line ranges that must overlap retrieved chunks. It checks this with mechanical interval-overlap verification, which prevents fabricated files and out-of-range lines, and reports "92 percent citation accuracy with zero hallucinations." It is a deterministic, non-semantic check of the "cited id must exist in what was retrieved" kind, and the closest published analogue to CVM's first check. — [arXiv 2512.12117](https://arxiv.org/abs/2512.12117)
- EBTE, Explanation-Bound Tool Execution (Zhu and Wang, arXiv July 2026), turns agent rationales into typed action claims, including "evidence references". A server-side verifier checks them against "server-held intent, policy, payload, tool, risk, provenance, and freshness facts"; "If any hard claim conflicts, the action is denied." This enforces at runtime on *actions*, not answers. — [arXiv 2607.25364](https://arxiv.org/abs/2607.25364v2)
- Actions with Receipts (arXiv 2610.00327, October 2026) binds each claim to its exact source span, source version and ordered execution prefix ("source identifiers, offsets, hashes, quotes"). It detects 1,275 of 1,280 cross-object substitution attacks (0.9961). This is an *audit or replay* contract, not a generation-time rejection loop. — [arXiv 2610.00327](https://arxiv.org/abs/2610.00327)
- LEDGER (arXiv 2608.18398) is a sidecar tracer that builds claim-to-evidence trace graphs with edges such as uses, produces, checked_by and supports, for *post-hoc review* of agent sessions. — [arXiv 2608.18398](https://arxiv.org/abs/2608.18398)
- Survey "From Agent Traces to Trust" (arXiv 2606.04990, June 2026) organizes this area into seven threads, including "evidence attribution, tool-use provenance, runtime guardrails, provenance-bearing memory". This suggests the area was already a named research thread by mid-2026. — [arXiv 2606.04990](https://arxiv.org/abs/2606.04990)
- CaMeL (Debenedetti et al., Google DeepMind, 2025) uses a custom Python interpreter that "maintains a dynamic data flow graph, tracking the provenance and dependencies of every variable". It enforces security policies before each tool call, and solves 77% of AgentDojo tasks with provable security versus 84% undefended. The provenance here serves **capability and security policy** (stopping prompt injection), not checking that answer claims are supported. — [arXiv 2503.18813](https://arxiv.org/abs/2503.18813); [Simon Willison summary](https://simonwillison.net/2025/Apr/11/camel/)

### Inferences
- Taxonomy for the report:
  - **Evaluate after the fact**: AIS, AQA/AutoAIS, ALCE, AttributionBench, FActScore, SAFE, Liu et al. 2023.
  - **Repair at inference time**: RARR.
  - **Learned self-check**: Self-RAG.
  - **Pointer-validity guarantee**: Anthropic Citations, constrained-decoding grammars (FullCite).
  - **Deterministic existence check**: Citation-Grounded Code Comprehension.
  - **Semantic runtime block**: ProvenanceGuard, EBTE for actions.
  - **Security provenance**: CaMeL.
  - **Audit or replay**: Receipts, LEDGER.
- CVM's distinguishing combination looks like this: (1) a ledger that records *materialization into the context window* (closer to an OS page table than a retrieval list); (2) a cheap deterministic check (id ∈ ledger, answer entity ∈ cited fact text); (3) rejection that is a *FAULT followed by a retry loop*, not a block or a repair. Each piece has precedent. I found no single source that combines all three under a virtual-memory framing. That is a combination claim, not a claim of a new primitive.
- CVM's "answer entity appears in a cited fact" check is a crude lexical form of what ALCE and AutoAIS do with NLI. It is weaker semantically but deterministic and cheap.

### Gaps
- I could not verify whether ProvenanceGuard forces regeneration or only blocks (fetch blocked).
- I found no paper that reports rejection rates of a hard citation gate against a deliberately hallucinating generator (CVM's 100% of 9,600). Similar adversarial numbers exist only for substitution attacks (Receipts: 99.6%).

## Q3. The epistemic rule "must dereference rather than predict external state": abstention and adaptive retrieval

### Takeaway
Prior work teaches or prompts models to *decide* when to retrieve (FLARE, Self-Ask, Self-RAG's Retrieve token, Adaptive-RAG, popularity-based adaptive retrieval) or to abstain. These are probabilistic, model-side policies: the model may still answer from parametric memory. CVM moves the decision out of the model: asserting external state without a materialized fact fails verification by construction. The closest structural precedents are CaMeL's interpreter-level data flow (for security) and the "block figures absent from tool output" pattern.

### Cited Findings
- FLARE (Jiang et al. 2023) triggers retrieval when an upcoming generated sentence has low-confidence tokens. — [arXiv 2305.06983](https://arxiv.org/abs/2305.06983) (not re-fetched); described in [Self-RAG paper](https://arxiv.org/pdf/2310.11511)
- Self-RAG's Retrieve reflection token lets the model decide "on-demand" whether to retrieve. — [ICLR 2024 paper](https://proceedings.iclr.cc/paper_files/paper/2024/file/25f7be9694d7b32d5cc670927b8091e1-Paper-Conference.pdf)
- Self-Ask (Press et al. 2022) prompts the model to pose follow-up sub-questions answered by search. — [arXiv 2210.03350](https://arxiv.org/abs/2210.03350) (not re-fetched)
- "When Not to Trust Language Models" (Mallen et al. 2022/ACL 2023) finds parametric memory unreliable for long-tail entities and proposes adaptive retrieval based on entity popularity. — [arXiv 2212.10511](https://arxiv.org/abs/2212.10511) (not re-fetched)
- Adaptive-RAG (Jeong et al. 2024) routes queries by complexity to no-retrieval, single-step or multi-step retrieval. — [arXiv 2403.14403](https://arxiv.org/abs/2403.14403) (not re-fetched)
- "Language Models (Mostly) Know What They Know" (Kadavath et al. 2022) examines self-evaluation and calibration, the basis for abstention policies. — [arXiv 2207.05221](https://arxiv.org/abs/2207.05221) (not re-fetched)
- CaMeL's design keeps a Quarantined LLM that processes untrusted data without tool access. Values flow through an interpreter rather than through model "prediction", which is a structural rather than learned separation. — [arXiv 2503.18813](https://arxiv.org/abs/2503.18813)

### Inferences
- "Must dereference, not predict" matches the adaptive-retrieval goal, but the enforcement point differs. Prior work makes retrieval a *model choice*, while CVM makes un-dereferenced assertion a *verifier failure*. That is the most defensible novelty angle, but only as a system design framing (memory-safety or page-fault analogy), not as a new capability.
- CVM's own data (accepted wrong answers all cite real facts) shows the rule enforces *dereferencing*, not *correct reasoning over* the dereferenced data.

### Gaps
- I found no paper that frames hallucination prevention explicitly as a page fault or demand-paging invariant. This is not proof of absence: the search was limited, and adjacent CVM researchers may cover MemGPT-style work.

## Q4. Attribution or grounding does not imply correctness ("grounded != correct")

### Takeaway
The literature strongly supports the related point that *correct ≠ faithful*: a correct answer with a valid citation may be post-rationalized. ALCE and others also show that citation quality and answer correctness are separate axes. CVM's specific observation, that answers citing real, relevant facts can still be wrong, is the converse direction ("right source, wrong inference"). It agrees with FullCite's span-level finding and with the general separation of the axes, but I found less direct quantitative prior work on it.

### Cited Findings
- "Correctness is not Faithfulness in RAG Attributions" (Wallat et al., arXiv December 2024; ACM ICTIR 2025) separates citation correctness (does the source support the claim?) from faithfulness (did the model actually rely on it?). It identifies post-rationalization and finds "up to 57% of citations lack faithfulness." — [arXiv 2412.18004](https://arxiv.org/pdf/2412.18004); [ACM DL](https://dl.acm.org/doi/pdf/10.1145/3731120.3744592)
- "Attributable Post-Rationalization in RAG Citations" (Khan and Bhuyan, arXiv September 2026) finds that "on Wikipedia-based questions roughly one citation in seven is unfaithful." RLVR training that rewards correct answers "buys nothing in citation faithfulness." — [arXiv 2609.23053](https://arxiv.org/abs/2609.23053)
- ALCE scores fluency, correctness and citation quality as *separate* dimensions, which implies they can come apart. — [ACL Anthology](https://aclanthology.org/2023.emnlp-main.398/)
- FullCite: models pick the right documents but often not the right supporting spans. Document-level grounding therefore overstates support. — [arXiv 2606.07130](https://arxiv.org/abs/2606.07130)
- Actions with Receipts: "A valid citation and a valid trace can therefore remain individually well formed while being transplanted across claims, actions, runs, or source versions." — [arXiv 2610.00327](https://arxiv.org/abs/2610.00327)
- ProvenanceGuard's title framing, "Getting the Source Right, Not Just the Fact", treats source correctness and fact correctness as separable. — [HF blog (snippet)](https://huggingface.co/blog/MultiverseComputingCAI/getting-the-source-right-not-just-the-fact-source)

### Inferences
- CVM's "grounded ≠ correct" finding (100% of accepted wrong answers cited real facts) is consistent with the literature and should be presented as a *confirmation in a new setting*, not as a novel discovery. The direction is the converse of Wallat et al.: grounded but wrong, versus correct but unfaithfully cited.
- CVM's 18-26% rejection rate with a real LLM, mostly verdicts that cite no fact about the claim, followed by acceptance after re-citing, is exposed to the post-rationalization critique. A retry loop that rewards "find a citation that passes the check" may *induce* post-rationalized citations. The 2412.18004 and 2609.23053 findings predict exactly this. The CVM writeup should address it.

### Gaps
- I found no paper giving a quantitative rate of "cited evidence supports the premises but the answer is wrong" (an inference error over correct evidence) in agent settings. Multi-hop QA reasoning-error analyses may have such numbers, but I did not search them.
- I could not read full texts of 2024-2026 arXiv papers (egress block). Numbers come from abstracts or snippets.
