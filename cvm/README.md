# CVM: Cognitive Virtual Memory

**Let an LLM work over a million-object world while it only ever sees about 2,000 tokens of it.**

Most LLM systems serialize the world into the prompt (`Model(instruction +
world)`). That breaks as the world grows: the context fills up, costs climb, and
the model starts asserting things it never looked at.

CVM runs the model inside a persistent, runtime-managed **address space**
instead:

- The model sees a small **resident working set** (at most 32 objects).
- Everything else is addressed by stable references: `service://payments`,
  `commit://a8f92d`, `file://shop/tax.py`.
- When the model needs state that isn't resident, it issues an explicit
  **FAULT** and the runtime loads it, the way an OS handles a page fault.
- What stays resident is the runtime's call, not the model's.
- Answers must cite the facts they rest on, and access is enforced by
  capabilities rather than prompt instructions.

| World size | Resident objects | Peak prompt | Accuracy (reference processor) | Accuracy (DeepSeek-V4.1-Flash) |
|---:|---:|---:|---:|---:|
| 1,015 objects | ~9–12 | ~1.8–1.9k tokens | 1.00 | 0.53 (n=15) |
| 999,991 objects | ~9–12 | ~1.8–2.0k tokens | 1.00 | 0.70 (n=30) |

The world grew 1,000× and the model's view didn't. On the same tasks:

- **Full context** can't run past about 10⁴ objects (778k tokens at 10⁴).
- **Conventional tool calling** grows from 1.5k to 116k tokens.
- **One-shot RAG** scores 0.12–0.38.

![peak prompt tokens vs world size](results/context_vs_world_size.svg)

Full numbers, ablations and the live-LLM runs are in **[RESULTS_V0.md](RESULTS_V0.md)**.
The next phase, training a model to fault instead of guess, is planned in
**[PLAN_V1.md](PLAN_V1.md)**.

---

## Contents

- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Use it on your own data](#use-it-on-your-own-data)
- [Run it with an LLM](#run-it-with-an-llm)
- [Running it with Claude Code locally](#running-it-with-claude-code-locally)
- [Reproduce the results](#reproduce-the-results)
- [Repository layout](#repository-layout)
- [Limitations](#limitations)
- [Related work](#related-work)

---

## How it works

```
             task / instruction
                    │
                    ▼
           ┌──────────────────┐   one operation per step, as JSON
           │   LLM processor  │ ─────────────────────────────────┐
           └──────────────────┘                                  │
                    ▲  resident view (bounded, ~2k tokens)       ▼
           ┌────────┴─────────────────────────────────────────────────┐
           │ CVM runtime                                              │
           │  context: task, capabilities, working set (LRU), notes,  │
           │           provenance ledger, execution state             │
           │  resolver mount table:  service:// → infra graph         │
           │                         change://  → change log  ...     │
           │  verifier: answers must cite materialized facts          │
           └────────┬─────────────────────────────────────────────────┘
                    ▼
        graph · databases · git · logs · APIs   (the actual world)
```

### The six objects

| Concept | What it is | Code |
|---|---|---|
| **Context** | A process-like address space: task, principal, capabilities, working set, notes, provenance ledger and execution state. Created by the runtime, never chosen by the model. Can be suspended, resumed and spawned (children get a *subset* of the parent's capabilities). | `cvm/context.py` |
| **Object / Reference** | Every addressable thing has a stable URI. References are handles, not serialized objects: `service://redis-prod` might stand for gigabytes of state, and the model holds only the handle until it dereferences it. | `cvm/objects.py` |
| **Working set** | The bounded set of resident objects (default 32 objects / 16k tokens), evicted LRU by the runtime. | `cvm/working_set.py` |
| **Capability** | `(namespace pattern, operations)`, e.g. `READ service://*` or `SEARCH change://*`. An unauthorized operation returns `CAPABILITY_FAULT` from the runtime. | `cvm/context.py` |
| **Resolver** | The "MMU". It maps a namespace to a backend and materializes `(context, ref, operation)` into citable facts. An L2 cache and prefetch hints sit here. | `cvm/resolver.py` |
| **Evidence / Fact** | Every materialized value gets a stable `[fact:N]` id in the context's ledger. Answers cite fact ids; the verifier rejects anything citing a fact this context never materialized. | `cvm/runtime.py` |

### The instruction set

| Operation | Meaning | Returns |
|---|---|---|
| `READ(ref, field)` | Materialize one field of a known object | facts become resident |
| `TRAVERSE(ref, relation, page)` | Follow a relation (`~REL` for inverse) | **handles**, paginated, not objects |
| `SEARCH(namespace, query)` | Discover references you don't know yet (fuzzy, costly) | handles |
| `FAULT(ref, field?, reason)` | "I know what I need and it isn't resident": make it resident | facts become resident |
| `EVIDENCE(claim)` | Materialize a claim object and its evidence links | facts and handles |
| `WRITE(entries)` | Persist conclusions in the context's `scratch://` notes | survives eviction |
| `ANSWER(value, support=[fact ids])` | Finish; checked by the provenance verifier | accepted or `VERIFIER_REJECT` |

SEARCH and FAULT are deliberately different. Discovery is fuzzy; dereferencing
a known reference is exact. You go from semantic discovery to a stable
identity to a deterministic dereference.

### What the model actually sees

The prompt is rebuilt from the context every step. The model keeps no
conversation history: **the prompt is the state.** Here is a real one from
the 10⁶-object world (full run in
[`results/example_trace_1e6.txt`](results/example_trace_1e6.txt)):

```
CONTEXT ctx://0001   PRINCIPAL agent://incident-debugger
TASK task://0 [root_cause]
  Determine which change or deployment caused incident://inc-k10611.

RESIDENT OBJECTS (8/32 objects, 690/16000 tokens)
incident://inc-k10611  [incident] elevated errors on ads-k10611
  [fact:2] started_at = 2026-03-27T23:49Z
  [fact:5] AFFECTS -> service://ads-k10611
  (~ABOUT: 2 refs, use TRAVERSE ~ABOUT)
metrics://ledger-k10611  [metrics] latency for service://ledger-k10611
  [fact:8] anomaly_start = 2026-03-27T23:37Z
  [fact:12] status = anomalous
...
NOTES (scratch://0001, 9/48)
  status:service://ledger-k10611 = anomalous@2026-03-27T23:37Z | fact:7,fact:12,fact:8
...
AVAILABLE OPERATIONS
  READ(ref, field) / TRAVERSE(ref, relation, page=0) / SEARCH(namespace, query) /
  FAULT(ref, field?, reason) / EVIDENCE(ref) / WRITE(entries={key: value}, ref?) /
  ANSWER(value, support=[fact ids])

RULES
  Do not assert external state that is not resident. If you need it, FAULT it.
  ANSWER must cite the fact ids that support it; unsupported answers are rejected.
```

### Three design rules that turned out to matter

1. **Return handles, not objects.** Conventional tools that return whole
   objects blew up to 116k tokens at 10⁶ objects: one shared service carries
   about 14k dependents. TRAVERSE returns paginated references instead.
2. **The runtime owns eviction; the model owns notes.** Bounded residency on
   its own *fails*. Without notes, small working sets thrash (96% re-fetch,
   accuracy 0). With a small model-written notes area that is budgeted and
   never silently evicted, a task solves with 2 resident objects.
3. **Enforce in the runtime, not the prompt.** A live model found a side
   channel (incident → claims that name candidate causes). A capability rule
   closed it; a prompt rule would not have. Likewise, citations are checked,
   not requested.

---

## Quickstart

You need Python 3.10 or later. **No third-party dependencies**: SQLite + FTS5
from the standard library hold the synthetic world.

```bash
git clone <this repo> && cd 2ter/cvm
python -m unittest tests.test_cvm           # 20 tests, ~1 s
python examples/custom_store.py             # prints the resident view for a tiny code-repo world
python experiments/show_trace.py --size 1000  # one full reference run, step by step
```

`show_trace.py --size 1000000` builds the million-object world first (~35 s,
~570 MB, cached in `cvm/.cache/`, which git ignores) and then runs on it.

---

## Use it on your own data

The runtime talks to your data through a **store** with five methods, and
through a **mount table** that maps namespaces to resolvers.
[`examples/custom_store.py`](examples/custom_store.py) is a complete working
example over a tiny code-repo world (repo, files, commits, teams, bugs).

```python
class MyStore:
    io = 0                                         # backend touches (reported as external I/O)
    def get(self, ref) -> CVMObject | None: ...    # ref -> object (attributes + outgoing relations)
    def traverse(self, ref, pred, limit, offset=0) -> list[str]: ...   # outgoing refs
    def inverse(self, ref, pred, limit, offset=0) -> list[str]: ...    # incoming refs (~PRED)
    def inverse_all(self, ref) -> list[tuple[str, str]]: ...           # only for the tool-calling baseline
    def search(self, namespace, query, k) -> list[str]: ...            # discovery

store = MyStore()
cache = L2Cache()
mounts = MountTable([NamespaceMount("service://", Resolver(store, cache)),
                     NamespaceMount("commit://",  Resolver(store, cache))])
rt = CVMRuntime(store, RuntimeConfig(), cache=cache, mounts=mounts)

caps = [Capability("service://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("commit://*",  ("READ", "FAULT", "SEARCH")),
        Capability("scratch://*", ("WRITE",))]
ctx = CognitiveContext("agent://me", Task("task://1", "investigate", "Why is X broken?",
                       "service://x", seed_refs=["service://x"]), caps, WorkingSet(32))
rt.run(ctx, processor)          # any processor: see below
print(ctx.answer, ctx.answer_support, ctx.trace)
```

Some practical notes:

- **Per-namespace views.** Subclass `Resolver` and override `view(ctx, obj)`
  to return a context-dependent projection, e.g. redacting fields a context
  shouldn't see (`PeopleResolver` does this).
- **Backends can be anything.** Different namespaces can be served by
  different backends (git, a database, an HTTP API): give each mount its own
  `Resolver` and store.
- **Writes.** V0 resolvers are read-only. `WRITE` only goes to the context's
  own `scratch://` notes.
- **Task text.** `Task.kind` is free text for your own tasks. The built-in
  `ReferenceReasoner` only knows the synthetic incident tasks; use an LLM
  processor for anything else.

---

## Run it with an LLM

A **processor** is anything with `step(prompt: str) -> dict` that returns one
operation. Each call is stateless.

| Processor | Use | Status |
|---|---|---|
| `ChatCompletionsProcessor` | DeepSeek or any OpenAI-compatible endpoint (JSON mode). The key is read from an env var (default `DEEPSEEK_API_KEY`) | **Run live** with DeepSeek-V4.1-Flash; results in RESULTS_V0 |
| `ClaudeProcessor` | Anthropic Messages API, structured JSON output, `pip install anthropic`, `ANTHROPIC_API_KEY` | Tested against a mocked client only; **not yet run live** |
| `ReferenceReasoner` | Deterministic solver for the synthetic incident tasks; parses the prompt text only | Used for all scale results |
| `Hallucinator` | Answers without looking anything up; used to test the verifier | |

```bash
# live LLM experiment on the synthetic world (writes results/llm_<tag>.json + _traces.jsonl)
DEEPSEEK_API_KEY=... python experiments/run_llm.py --provider deepseek --model deepseek-flash \
    --sizes 1000,1000000 --tasks 30 --conditions cvm --workers 8 --max-steps 50

ANTHROPIC_API_KEY=... python experiments/run_llm.py --provider claude --model claude-opus-5-5 \
    --sizes 1000000 --tasks 30 --conditions cvm

# add --hint to give the model the investigation method (separates "can't reason" from "wasn't told how")
# add --conditions cvm,agent to also run conventional tool calling (expensive at 1e6: ~100k-token prompts)
```

Cost reference: DeepSeek-V4.1-Flash took about $1.27 for 30 tasks at 10⁶
objects, or about $0.04 per task (~75k input and ~63k output tokens per task,
including reasoning).

---

## Running it with Claude Code locally

```bash
git clone https://github.com/nikitph/2ter && cd 2ter
git checkout claude/cvm-core-thesis-3azicg     # until PR #2 is merged
cd cvm && claude
```

Claude Code picks up [`cvm/CLAUDE.md`](CLAUDE.md), which holds the full
handoff notes: current state, conventions, gotchas and the next tasks. Good
first prompts:

- *"Run the tests and the reference scale experiment at 1e3 and 1e4 and confirm the numbers match RESULTS_V0."*
- *"Start V1 step 1 from PLAN_V1.md: build the trajectory dataset exporter."*
- *"Run the Claude processor on 10 tasks at 1e6 with my ANTHROPIC_API_KEY and compare against the DeepSeek results."*

Keep API keys in environment variables (`export DEEPSEEK_API_KEY=...`) and
never write them into files. The scripts only read them from the environment.

---

## Reproduce the results

| Command | What | Time |
|---|---|---|
| `python -m unittest tests.test_cvm` | 20 tests | ~1 s |
| `python experiments/run_scale.py` | Headline: 5 conditions × 10²…10⁶ objects × 90 tasks → `results/scale.json` | ~2–3 min (first run builds worlds, ~35 s for 10⁶) |
| `python experiments/run_ablations.py` | Working-set/notes sweep, cache/prefetch, verifier, capabilities, context switching at 10⁶ → `results/ablations.json` | ~20 s |
| `python experiments/plot.py` | Regenerates the two SVG charts from `scale.json` | <1 s |
| `python experiments/show_trace.py --size 1000000` | One annotated reference run, plus the largest prompt it saw | ~1 s after the world exists |
| `python experiments/run_llm.py ...` | Live LLM runs (see above) | ~10–20 min per 30 tasks |

Everything is deterministic (seeded worlds and tasks) except the live LLM runs.

---

## Repository layout

```
cvm/
  objects.py          refs, objects, relations, facts
  context.py          CognitiveContext, Capability, notes, provenance ledger, spawn()
  working_set.py      bounded resident set, runtime-owned LRU eviction
  resolver.py         GraphStore (SQLite), mount table, resolvers, L2 cache, prefetch hints
  runtime.py          step loop, instruction set, capability faults, provenance verifier
  synthetic_world.py  deterministic world generator with injected causal chains + ground truth
  processors.py       ReferenceReasoner, Hallucinator, ClaudeProcessor, ChatCompletionsProcessor
  experiment.py       tasks, conditions A/B/B2/C/D, metrics
experiments/          run_scale, run_ablations, run_llm, show_trace, plot
examples/             custom_store.py: plug in your own data
tests/                test_cvm.py (20 tests)
results/              all raw results and charts (see RESULTS_V0.md)
docs/                 SPEC.md (the original v0.1 spec), literature-review.md, research-notes/
README.md             this file
RESULTS_V0.md         full results
PLAN_V1.md            next phase: training a model to fault instead of guess
CLAUDE.md             handoff notes for the next Claude Code session
```

---

## Limitations

- **The synthetic world** is an infrastructure graph with tasks local to one
  cluster plus shared hubs. Real graphs may have longer-range dependencies.
- **Live-LLM evidence** comes from one model and 45 tasks. Root-cause accuracy
  is 0.40, because the model takes the decoy or runs out of steps. The
  substrate bounds what the model sees, not how well it reasons; V1 targets that.
- **Grounded is not correct.** The verifier guarantees answers rest on
  materialized facts, not that the inference from them is right.
- **Token counts** are chars/4 estimates.
- **`ClaudeProcessor`** has not been run against the live API yet.
- **Not built** (deliberately, per the spec): multi-agent orchestration,
  embeddings, summarization, a UI, connectors, writable resolvers.

## Related work

The building blocks have precedents. The closest is ClawVM (EuroMLSys '26,
runtime-managed paging of agent session state). Others are MemGPT/Letta
(model-driven paging), AIOS, Scroll and MEM1 (bounded or stateless agent
context), CaMeL and Agent libOS (runtime capabilities), and citation
verification work.

What CVM adds is virtual memory for the **external world**, with the model
issuing explicit faults over stable references. It also adds two measurements
with no precedent in our search:

- context that stays flat while the world grows 1,000× with a live model;
- the notes ablation showing that notes are what make a tiny working set work.

Details and citations are in [`docs/literature-review.md`](docs/literature-review.md).
