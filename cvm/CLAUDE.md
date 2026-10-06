# CLAUDE.md: handoff notes for CVM

Read this first. It is the state of the project as of 2026-10-06, written by
the session that built V0, so that the next session can pick it up cold.

## What this is

CVM (Cognitive Virtual Memory) is a runtime that lets an LLM work over a huge
external world while it only ever sees a small, bounded *resident view*:

- The model emits one operation per step: READ / TRAVERSE / SEARCH / FAULT /
  EVIDENCE / WRITE / ANSWER.
- It works over stable URI references.
- The runtime owns eviction.
- Answers must cite materialized facts.
- Capabilities are enforced by the runtime.

The original spec is in `docs/SPEC.md`; user-facing docs are in `README.md`.

**Status: V0 is done and validated. V1 (training a model to fault instead of
guess) is planned in `PLAN_V1.md`. M0 is done for DeepSeek-V4.1-Flash
(see `RESULTS_V1.md`):

- WS=32: accuracy 0.68.
- WS=4: accuracy **0.10**, thrash 0.59. The model writes ~1 note per task, so
  evicted state is lost.
- The reference processor scores 1.00 at WS=4.

Teaching the notes habit is V1's clearest target. Still pending: a baseline
for the open model chosen for fine-tuning, which needs vLLM.**

- Repo: `nikitph/2ter`. V0 was merged to `master` via
  https://github.com/nikitph/2ter/pull/2. Do follow-up work on a new branch
  from `master`.
- The rest of the `2ter` repo (skorer, truckx, …) is unrelated. Stay inside `cvm/`.

## Headline results (details in RESULTS_V0.md; don't restate numbers elsewhere without re-checking)

**Reference processor**, 90 tasks per size, 10²–10⁶ objects:

- accuracy 1.00;
- peak ~9 resident objects / ~1.8k tokens, flat across sizes;
- full context is infeasible past ~10⁴ objects;
- whole-object tool calling grows from 1.5k to 116k tokens;
- RAG scores 0.12–0.38.

**DeepSeek-V4.1-Flash, live:**

- 10³ objects (n=15): accuracy 0.53;
- 10⁶ objects (n=30): accuracy 0.70;
- residency ~12 objects / ~2k tokens at both sizes;
- root-cause accuracy 0.40;
- verifier rejected 18–26% of answers; 0 unsupported answers were accepted.

**Ablations at 10⁶ objects:**

- without notes, small working sets thrash (96% re-fetch, accuracy 0); with
  notes, tasks solve with 2 resident objects;
- verifier rejected 9,600 of 9,600 fabricated answers;
- capability faults hold; context switching is exact.

## The owner's preferences

- They are a practitioner, not an academic. They want things that work and can
  be introduced and used. They don't want research-methodology detours. Keep
  the framing practical, but stay honest about limits: one line, not a lecture.
- Their framing: CVM is about cracking the **context wall**. If a model's
  useful capability no longer depends on fitting the world into context, the
  capability frontier (especially of small models) needs reassessing. V0
  supports "context volume isn't the driver; processing is". The next
  questions are M0b and M6.
- They want V1 runnable locally with Claude Code. `PLAN_V1.md` §4 has the
  prompt sequence.
- They asked for a **public repo** for CVM. The GitHub integration could not
  create one (403), so the owner has to create an empty repo first. Then
  publish just this folder with something like:
  - `git subtree split --prefix cvm -b cvm-public`
  - push `cvm-public` to the new repo's `main`.

  **No license has been chosen yet; ask before publishing.**

## Layout

```
cvm/objects.py          ObjectRef (str), CVMObject, Relation, Fact; iso(); approx_tokens() = chars/4
cvm/context.py          CognitiveContext (state, notes, ledger, counters), Capability, spawn(),
                        incident_agent_capabilities(search, write, claims)
cvm/working_set.py      WorkingSet: LRU over objects (max_objects, max_tokens), handles buffer, render
cvm/resolver.py         GraphStore (SQLite+FTS5), Resolver subclasses, L2Cache, MountTable, default_mounts
cvm/runtime.py          CVMRuntime: build_prompt, run/step/dispatch, _op_* handlers, verify(); RuntimeConfig
cvm/synthetic_world.py  build_world(n, seed) -> cached SQLite; clusters with causal chains + truth table
cvm/processors.py       parse_prompt(), ReferenceReasoner (_Policy), Hallucinator, ClaudeProcessor,
                        ChatCompletionsProcessor, SYSTEM/SYSTEM_OPENAI, METHOD_HINT, first_json_object
cvm/experiment.py       make_tasks, run_cvm / run_agent / run_rag / FullContext, _metrics
experiments/            run_scale.py, run_ablations.py, run_llm.py, show_trace.py, plot.py
examples/custom_store.py  how to plug in your own data (tested)
tests/test_cvm.py       24 tests: python -m unittest tests.test_cvm
results/                committed outputs (see RESULTS_V0.md "Files in results/")
docs/                   SPEC.md, literature-review.md, research-notes/
```

## Commands

```bash
python -m unittest tests.test_cvm                   # always run before committing; ~1 s
python experiments/run_scale.py                     # ~2–3 min; rewrites results/scale.json
python experiments/run_ablations.py                 # ~20 s; rewrites results/ablations.json
python experiments/plot.py                          # regenerate SVGs from scale.json
python experiments/show_trace.py --size 1000        # see a full run and the prompt
python experiments/run_llm.py --provider reference --sizes 1000 --tasks 6 --tag smoke --out-dir /tmp/smoke   # free LLM-harness smoke test
python experiments/run_llm.py --provider reference --sizes 1000,1000000 --tasks 30 --max-objects 4 --tag m0-reference-ws4   # M0 sanity cell
DEEPSEEK_API_KEY=... python experiments/run_llm.py --provider deepseek --model deepseek-flash \
    --sizes 1000000 --tasks 30 --conditions cvm --workers 10 --max-steps 50 --tag <tag>
```

`run_llm.py` providers:

- `reference` (free)
- `deepseek`
- `openai-compatible` (uses `--base-url` and `--api-key-env`, e.g. a local vLLM at `http://localhost:8000/v1`)
- `claude` (needs `pip install anthropic` and `ANTHROPIC_API_KEY`; never run live yet)

Other flags: `--hint` adds `METHOD_HINT` to the system prompt;
`--conditions cvm,agent` also runs the tool-calling baseline.

## Invariants: don't break these

1. **The processor sees only the prompt string.** No processor may touch the
   store. `ReferenceReasoner` is a pure function of the prompt; there is a
   test for that. This is what makes the results meaningful.
2. **`build_prompt` and `parse_prompt` are coupled.** `parse_prompt` keys on
   section headers (`RESIDENT OBJECTS`, `HANDLES`, `NOTES`,
   `RECENT OPERATIONS`, `LAST RESULT`, `AVAILABLE OPERATIONS`, `RULES`), on
   fact-line format `  [fact:N] field = value` / `-> target`, and on handle
   lines `  ref   (via ...)`. If you change the prompt format, update the
   parser and re-run everything. V1 training data must be regenerated too,
   because the model learns this format.
3. **The runtime owns eviction (LRU).** The model cannot evict. Notes
   (`scratch://`) are budgeted (`max_notes=48`) and never silently evicted.
4. **TRAVERSE and SEARCH return handles, not objects**, except in
   `agent_mode`, the tool-calling baseline that deliberately returns whole
   objects including inverse edges.
5. **Fact ids are stable within a context.** The same (ref, field, value,
   version) gives the same id. The verifier checks against
   `ctx.facts_by_id`.
6. **`claim://` capabilities only go to claim-verification tasks**
   (`claims=spec.task.kind == "claim"`). This closes a side channel a live
   model found: incident → `~ABOUT` → claims naming the true cause and the
   decoy.
7. **Everything except live LLM runs is deterministic** (seeded worlds and
   tasks). If numbers change after a code change, find out why before
   committing new results.
8. **The core package stays standard-library only.** Optional dependencies
   (`anthropic`, V1 training stack) live in separate scripts or a
   `requirements.txt`.

## Gotchas learned the hard way

- **Never write API keys into files or commits.** Read them from env vars only.
  Before every commit run `grep -rE "sk-[0-9a-f]{32}" .` and expect no hits.
  The owner has pasted keys in chat before; they rotate them.
- **DeepSeek JSON mode** sometimes appends stray tool-call markup
  (`<｜DSML｜…>`) after the JSON object. `first_json_object()` handles it. An
  early run lost half its steps to this; don't revert to strict
  `json.loads`.
- **`deepseek-chat` resolves to `deepseek-flash`** (DeepSeek-V4.1-Flash, 1M
  context). Also available: `deepseek-v4-pro`. It is a reasoning model, so
  keep `max_tokens` ≥ 8192 or the content can come back empty.
- **Cost.** DeepSeek-Flash costs about $0.04 per task at 10⁶ (~75k input, ~63k
  output tokens including reasoning). The tool-calling baseline at 10⁶ sends
  ~100k-token prompts per step, so it is ~10× more expensive. Check balance
  with `curl https://api.deepseek.com/user/balance -H "Authorization: Bearer $DEEPSEEK_API_KEY"`.
- **`run_llm.py` writes the traces file at start but fills it only after all
  tasks in a condition finish.** An empty traces file mid-run is normal. In
  the cloud environment, the stop hook complains about uncommitted files
  while a run is in progress; commit results when the run ends.
- **Parallel runs share one `GraphStore`** (thread-locked). `external_io` per
  task is therefore inaccurate in `run_llm.py`; it's exact in single-threaded
  runs.
- **`pkill -f run_llm.py` inside a command line that also contains
  "run_llm.py" kills its own shell.** Use the background task id or a
  narrower pattern.
- **World cache.** `cvm/.cache/world_n{N}_s{seed}.sqlite` is gitignored. The
  10⁶ world takes ~35 s to build and ~570 MB. Change `OBJECTS_PER_CLUSTER` or
  generator logic and you must delete the cache.
- **`FullContext`** materializes the whole world when ≤ 2×10⁵ objects (10⁴ takes
  ~10 s). Above that it estimates tokens from a 2,000-object sample and marks
  itself infeasible past 1M tokens.
- **Token counts are chars/4**, not a real tokenizer. Fine for curves; say so
  when quoting.
- **Cloud network.** In Claude Code cloud sessions the egress allowlist
  blocked `api.deepseek.com` until the owner added it, and arxiv.org was
  blocked for research. Locally this doesn't apply.
- **The reference reasoner is hand-written for the incident tasks.** It can't
  solve custom tasks (e.g. `examples/custom_store.py`); use an LLM processor.

## Known weaknesses and open items (prioritized)

0. **Plan corrections already folded into PLAN_V1.md; keep them in mind:**
   - `run_llm.py` supports only `cvm` and `agent`. M0b's full-context
     comparison needs a new `full` condition.
   - `ReferenceReasoner` handles incident tasks only. `domain2` needs its own
     `CodeReferenceReasoner`, for validation only and never for training data.
   - The runner's depth and kind summaries now follow the data, so they are no
     longer fixed to depths 1–3.

1. **V1**, per `PLAN_V1.md`: M0 baselines → **M0b small-model + method test**
   (the owner's main interest: can CVM plus the method make small models
   perform far above their size?) → M1 exporter → M2 splits (incl. second
   domain) → M3 LoRA → M4 eval → M6 recursive `CALL` contexts (the owner's
   idea: hard reasoning steps become recursive bounded calls) → M7 system-1
   step checker against compounding errors: TypeSafe's **Jev** (a System One
   typed classifier; the owner's suggestion) off the shelf, plus our own
   critic, possibly JEPA-style, trained on CVM ground-truth negatives.
2. **`ClaudeProcessor` has never been run live.** It uses `output_config`
   JSON-schema structured output and is tested only against a mock. The first
   live run may need fixes; check `stop_reason` handling and the schema's
   required fields.
3. **Small live-LLM n** (15 and 30). Get ≥100 per cell before making strong
   accuracy claims.
4. **Untested ideas from V0 analysis:**
   - Richer `CAPABILITY_FAULT` messages that list the granted namespaces
     (would it stop retrying?).
   - Stop advertising `(~ABOUT: n refs)` inverse counts to contexts that can't
     read the target namespace.
   - Batched operations and prompt-prefix caching to cut the per-step resend
     cost.
5. **Reviewer-style gaps from the literature review** (only if the owner
   wants publication-grade claims; they've said they mostly don't):
   - a Think-on-Graph beam-search baseline;
   - a real graph (Wikidata subgraph or microservice topology);
   - checking whether GABench reports tokens against graph size;
   - checking whether ClawVM has published live-model results.

## Positioning (from docs/literature-review.md)

Not novel as architecture:

- ClawVM (EuroMLSys '26) is closest: runtime-owned paging of *session*
  state, refetch faults and a thrash index, evaluated by replay only.
- Also MemGPT/Letta, AIOS, Scroll, MEM1, CaMeL, Agent libOS and citation
  verification.

Novel as far as we found:

1. context flat while the **external world** grows 1,000× with a live model;
2. notes are what make a tiny working set work (thrash ablation).

The pitch is *virtual memory for the external world*, with the model issuing
explicit faults over stable references. Don't claim "first LLM OS", "first
page fault" or "first agent capabilities".
