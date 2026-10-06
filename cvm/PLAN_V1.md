# CVM V1 plan: train a model to fault instead of guess

V0 showed the substrate works. A live model operated over a 10⁶-object world
with about 2k tokens of resident context, and accuracy did not drop as the
world grew. It also showed where the remaining gap is: **the model's habits
inside the substrate.** DeepSeek-V4.1-Flash:

- takes the decoy on root-cause tasks;
- rarely writes notes;
- keeps retrying denied namespaces;
- gets its answers rejected by the verifier 18–26% of the time.

V1 trains those habits into a small open model (spec §35). The target
invariant is **uncertainty about the world → dereference**, not uncertainty →
prediction.

This document is meant to be executed step by step, mostly by Claude Code in
this repo. Each milestone lists the files to create, the commands to run and
what "done" means. Read [`CLAUDE.md`](CLAUDE.md) first for conventions and
gotchas.

---

## 0. Baseline to beat (from V0)

| Metric | DeepSeek-V4.1-Flash, 10⁶ objects, n=30 | Reference processor |
|---|---:|---:|
| Accuracy (all tasks) | 0.70 | 1.00 |
| Root-cause accuracy | 0.40 | 1.00 |
| Answers rejected by verifier | 26% | 0% |
| WRITEs (notes) per task | 0.8 | ~12 |
| Capability faults per task (denied retries) | 5.4 | 0 |
| Hit step limit | 4 / 30 | 0 |
| Peak resident objects / tokens | 12.3 / 1,970 | 9.3 / 1,793 |

The notes ablation predicts what happens when the working set is tight: with
4 resident objects and no notes, accuracy falls to about 0. The live model
rarely writes notes, so it should collapse at small working sets. **Measuring
that is the first thing V1 does (M0).**

## 1. Success criteria for V1

A fine-tuned open model, compared with its own base model on **held-out**
splits (see M2), should reach:

| Criterion | Target |
|---|---|
| Accuracy at 10⁶ objects, in-distribution tasks | ≥ 0.90 (base model and DeepSeek-Flash as reference points) |
| Root-cause accuracy | ≥ 0.75 |
| Accuracy with a **4-object** working set | ≥ 0.80 (shows it learned to use notes) |
| Answers rejected by verifier, *before* retry | ≤ 5% |
| Capability faults per task | ≤ 1 |
| Held-out depth 4–5 chains | ≥ base + 20 points |
| Held-out **second domain** (never trained on) | ≥ base + 15 points |
| Peak resident context | still ≤ 32 objects / ~2–3k tokens; unchanged by training |

The last two rows matter most. They show the model learned the *habit*, not
the reference solver's incident-debugging algorithm.

## 2. Milestones

### M0: Baselines on more models (cheap, do first)

Goal: know how strong untrained models are before training anything.

1. Run the base model you plan to fine-tune, served locally with vLLM (see M4
   for serving), at 10⁶ objects with 32 and 4 resident objects.
2. Optionally also run Claude (`--provider claude`), `deepseek-v4-pro` and
   `--hint` variants.
3. Use ≥100 tasks per cell if the budget allows (n=30 gives ±0.17 at 95%).

```bash
# local vLLM (or any OpenAI-compatible endpoint)
for ws in 32 4; do
  python experiments/run_llm.py --provider openai-compatible --base-url http://localhost:8000/v1 \
     --api-key-env VLLM_KEY --model <served-model-name> --sizes 1000000 --tasks 100 --conditions cvm \
     --max-objects $ws --tag base-<model>-ws$ws
done
```

**Status:**

- **Done:** the `--max-objects` flag in `run_llm.py`, with tests. It applies to
  the `cvm` condition only.
- **Done:** the reference sanity check through the runner. Results are in
  `RESULTS_V1.md` §M0.
- **Pending:** model baselines. These need a served endpoint (a local vLLM or
  a hosted API key); the machine that did M0 had neither.

Done when: `results/llm_base-*.json` exist for WS=32 and WS=4.

### M0b: Does the method lift small models? (no training; do right after M0)

The question: **is CVM plus the method enough to make a small model perform
far above its normal capability?** If so, the context wall is not the limit we
assume it is, and small models are underestimated.

Run 1.5–3B and 7–8B open models through CVM at 10⁶ objects, each in four
cells:

| Cell | Flags | What it isolates |
|---|---|---|
| plain | (none) | raw processing ability inside the substrate |
| hint | `--hint` (`METHOD_HINT` in the system prompt) | how much knowing the method adds |
| plain, WS=4 | `--max-objects 4` | does it keep notes under pressure? |
| hint, WS=4 | `--hint --max-objects 4` | both |

```bash
for m in <small-model> <7-8b-model>; do
  for ws in 32 4; do
    for hint in "" "--hint"; do
      python experiments/run_llm.py --provider openai-compatible --base-url http://localhost:8000/v1 \
         --api-key-env VLLM_KEY --model $m --sizes 1000000 --tasks 100 --conditions cvm \
         --max-objects $ws $hint --tag m0b-$m-ws$ws${hint:+-hint}
    done
  done
done
```

Reference points:

- DeepSeek-V4.1-Flash, plain: 0.70 accuracy, 0.40 on root cause.
- Reference processor (a script with zero intelligence): 1.00.

To make the "above its capability" claim concrete, also run the **same small
model without CVM**. The headline result would be: *small model + CVM + method
at 10⁶ ≥ the same model without CVM at 10³.*

- The tool-calling baseline already works: `--conditions agent` at 10³–10⁴.
- **The full-context comparison needs new wiring.** `run_llm.py` only supports
  the `cvm` and `agent` conditions and rejects anything else.
  `experiment.FullContext` exists, but only the scale experiment uses it, with
  the reference processor. To run it with an LLM, add a `full` condition to
  `run_llm.py` that:
  - builds one `FullContext` per world (it materializes everything and adds
    the `WORLD: closed` line);
  - skips sizes whose estimated prompt exceeds the served model's window
    (`--full-context-limit`), recording them as infeasible like `run_scale.py`
    does;
  - allows one step only, since the model answers from the dump.

  At 10³ the prompt is ~77k tokens, so the served model needs at least a 128k
  window; small models may need 10² instead. Optionally add `rag` the same
  way via `experiment.run_rag`.

How to read the outcomes:

- **Hinted small model ≈ DeepSeek-Flash or better:** the method carries most
  of the work, and V1 fine-tuning on a small model is the main bet.
- **Hint helps a lot but stays well below:** fine-tuning (M3) should close
  the gap; prioritize recovery examples.
- **Hint barely helps:** the bottleneck is per-step reasoning. Prioritize M6
  (recursion), which breaks hard steps into smaller ones.

**Code needed:**

- the `full` condition above;
- `--max-objects` (done in M0).

`METHOD_HINT` is domain-specific (incident debugging). For `domain2`, write the
equivalent hint for code repos so the comparison is fair.

Done when: a table of accuracy, root-cause accuracy, notes per task,
verifier-rejection rate and capability faults, for each model × cell, is
added to `RESULTS_V1.md`.

### M1: Trajectory dataset exporter

Create `experiments/export_trajectories.py`. It runs the `ReferenceReasoner`
through the real runtime and records **every step** as a chat example:

```json
{"messages": [
  {"role": "system", "content": "<SYSTEM_OPENAI from cvm/processors.py>"},
  {"role": "user", "content": "<the exact resident-view prompt the runtime rendered>"},
  {"role": "assistant", "content": "{\"op\":\"FAULT\",\"ref\":\"metrics://...\",\"reason\":\"...\"}"}
 ],
 "meta": {"world_seed": 7, "world_size": 10000, "task_kind": "root_cause", "depth": 2,
          "max_objects": 8, "step": 5, "kind": "normal|recovery"}}
```

Requirements:

- **Same system prompt and prompt format as evaluation.** Use
  `SYSTEM_OPENAI` and `CVMRuntime.build_prompt`, so training and serving can't
  drift. Never hand-write prompts.
- **Wrap the processor** to capture `(prompt, action)` pairs, as
  `experiments/show_trace.py` does with its `spy`. Serialize the action exactly
  as the model must emit it, with JSON keys from `SYSTEM_OPENAI`'s examples.
  WRITE entries are a dict.
- **Reasons.** The reference reasoner's `reason` strings are generic. Add
  short, specific templated reasons, e.g. "need anomaly onset of
  service://x to compare with frontier onset 14:20Z". The model then learns
  *why* to fault, not just what.
- **Vary everything:**
  - world seeds: train ≥ 20 seeds, held-out seeds separate;
  - world sizes 10²–10⁴ (training never sees 10⁶);
  - depth 1–3;
  - working-set size in {4, 8, 16, 32}, which makes notes necessary;
  - task kinds, with and without `SEARCH`.
- **Recovery examples** (`meta.kind = "recovery"`). Perturb the processor at
  random steps to create states it must recover from:
  - Inject a bad `ANSWER` citing no facts. The next step after
    `VERIFIER_REJECT` is the correct re-cite.
  - Inject a denied operation, e.g. `EVIDENCE claim://...` on a non-claim
    task. The next step after `CAPABILITY_FAULT` is the alternative route,
    *not* a retry.
  - Inject an extra, useless `FAULT` to show the policy continuing correctly.
  - Force early eviction with WS=2–4. The correct next step after eviction is
    to read notes or re-fault.
- **Dedupe** identical (prompt, action) pairs. Shuffle. Write
  `data/v1/train.jsonl`, `data/v1/val.jsonl` and `data/v1/stats.json`, and
  gitignore `data/`.
- Expected scale: ~30 steps per task. 10k tasks give ~300k examples, built in
  minutes on CPU. Prompts are ~1–2.5k tokens, so expect ~0.5B training tokens
  at 300k examples. Start with 50k–100k examples.

Done when:

- `python experiments/export_trajectories.py --tasks 10000 --out data/v1`
  produces the files;
- a unit test checks that every exported action parses with
  `first_json_object` and `normalize_action`, and that replaying the actions
  through the runtime reproduces the recorded answers.

### M2: Held-out evaluation splits

Create `experiments/v1_splits.py`, or extend `make_tasks`, with these splits:

| Split | How |
|---|---|
| `iid` | unseen world seeds, sizes 10³ and 10⁶, depth 1–3 |
| `scale` | 10⁶ objects (train capped at 10⁴) |
| `deep` | depth 4–5 chains. **Code change needed:** `synthetic_world._build_cluster` hard-codes `depth = 1 + (k % 3)` and 5 services per cluster. Add a `depth_range` parameter and grow services per cluster to `depth + 2`. |
| `traps` | new decoy types not in training: a deploy (not a change) on the affected service just before the incident; a change on the root service *after* its anomaly but before the incident; two anomalous siblings with near-identical onsets |
| `tight` | WS=4 with notes enabled |
| `domain2` | **second domain, never trained on.** A code-repo world: `repo:// file:// symbol:// commit:// test:// bug://`. Causal chain: failing test → file → import chain → commit that changed the imported file before the first failure. Distractors: recent commits on the failing file itself, and commits after the first failure. `examples/custom_store.py` is the seed of this. Build it as `cvm/synthetic_code_world.py` with the same `GraphStore` interface and a `truth` table. |

Done when each split has ≥100 tasks and the reference processor scores 1.00
on all of them. If it doesn't, either the generator or the reference policy
has a bug; fix it before training.

Implementation notes:

- **`domain2` needs its own reference policy.** `ReferenceReasoner` only
  handles the incident task kinds (`root_cause` / `owner` / `claim`), and its
  `_Policy` is written around incident relations: `AFFECTS`, `DEPENDS_ON`,
  `HAS_METRICS`, `TARGETS`, `ABOUT`. Write a separate `CodeReferenceReasoner`
  (prompt-only and stateless, same contract) for the code-repo tasks.
  `make_tasks` and the runner must also dispatch on domain, choosing the world
  builder, task generator and reference policy.
- **Its role is validation only.** It proves `domain2` is solvable from the
  bounded prompt (reference = 1.00). It must **not** feed M1's training data,
  or `domain2` stops being held-out.
- **Depth summaries already work for `deep`.** `run_llm.py` used to report
  accuracy only for depths 1–3. M0 changed it to report whatever depths and
  task kinds occur in the runs, so 4–5 show up automatically.

### M3: Fine-tuning

- **Base model.** Choose an open instruct model in the 7–8B class that
  follows JSON reliably. Optionally add a 1.5–3B model to find the smallest one
  that learns the discipline. Check current options at the time; this repo
  doesn't pin one.
- **Method.** LoRA SFT, e.g. with Hugging Face TRL `SFTTrainer`:
  - loss on assistant tokens only;
  - max sequence length 4096;
  - LoRA r=16–64 on all linear layers;
  - LR 1e-4 to 2e-4 with cosine schedule;
  - 1–2 epochs;
  - effective batch size ~64.
  Create `v1/train_lora.py` and `v1/requirements.txt` (torch, transformers,
  trl, peft, datasets, accelerate). Keep these out of the core package, which
  stays dependency-free.
- **Compute.**
  - 100k examples × ~2k tokens ≈ 200M tokens per epoch. On 1×H100 with LoRA
    that is roughly a few hours.
  - A 24 GB consumer GPU works with QLoRA, slower.
  - Hosted fine-tuning services that accept chat-JSONL also work: export the
    same files.
- **Checkpoints.** Evaluate on `val.jsonl` (exact-match operation accuracy,
  JSON validity) every N steps, and keep the best.

Done when: a LoRA adapter (or merged model) exists and its operation-level
accuracy on `val.jsonl` is ≥ 95%.

### M4: Serve and evaluate

```bash
pip install vllm
vllm serve <base-model> --enable-lora --lora-modules cvm=<path-to-adapter> --port 8000
export VLLM_KEY=local
for split in iid scale deep traps tight domain2; do
  python experiments/run_llm.py --provider openai-compatible --base-url http://localhost:8000/v1 \
     --api-key-env VLLM_KEY --model cvm --split $split --tasks 100 --tag v1-sft-$split
done
```

**Code needed:** `run_llm.py` needs a `--split` flag wired to M2, plus the
`--max-objects` flag from M0. vLLM supports `response_format: json_object`;
if your version doesn't, use guided JSON decoding.

**Report.** Create `RESULTS_V1.md` with base vs SFT for every split, covering:

- accuracy (overall, by kind, by depth);
- verifier rejections before retry;
- WRITEs per task;
- capability faults per task;
- thrash rate at WS=4;
- fault precision;
- peak resident objects and tokens;
- steps;
- tokens per task.

Plot accuracy vs world size for base vs SFT, with the same chart style as
`experiments/plot.py`.

### M5 (optional): RL refinement

Do this only if SFT plateaus below target, especially on `traps` or `domain2`.

- Use GRPO or a similar method on the live runtime, which is already a
  deterministic environment with ground truth.
- Reward = correct answer − 0.02 × steps − 0.2 × capability faults −
  0.5 × verifier rejection.
- The risk is reward hacking via citation stuffing. The verifier only checks
  that cited facts were materialized, so add a penalty on support-set size.

### M6 (proposed): Recursive contexts, where reasoning becomes a call

**Idea.** A hard reasoning step doesn't have to happen inside one prompt. It
can be another bounded context. The parent issues a `CALL`, and the runtime:

1. spawns a child context with a narrow task, a subset of the parent's
   capabilities and a fresh bounded working set seeded with the handed-over
   refs;
2. runs the same processor on it;
3. verifies the child's answer against the child's own ledger;
4. returns the result to the parent as a single fact, whose provenance points
   at the child context.

The parent's view never grows. The spec already anticipates this (§22, context
inheritance), and `CognitiveContext.spawn()` already does capability
subsetting.

```
CALL(task="Did service://x's anomaly start before 14:20Z?", refs=[service://x],
     expect="YES|NO")                      -> [fact:N] CALL#3 = YES   (provenance: ctx://0042)
```

**Why it matters.** Any task becomes a tree of small steps, each within a small
model's competence. What is left for the model is choosing good decompositions
and getting leaf steps right. Leaf steps such as comparing two timestamps are
trivial once isolated. They can even be routed to a deterministic `COMPUTE`
op.

**What to measure:**

- accuracy vs. recursion depth;
- per-call accuracy, since errors compound (p per step over n steps is roughly
  p^n unless verification catches them);
- total tokens across the tree vs. a flat run;
- whether small models with `CALL` match large models without it.

**Code needed:**

- a `CALL` op in `runtime.py`: depth limit, per-call step and token budget,
  `expect` schema validation, result-as-fact with child provenance;
- capability checks so a child can never gain authority (`spawn()` already
  ensures this);
- a `--recursion` flag in `run_llm.py`;
- tests for depth limits, provenance, and capability narrowing across levels.

Start with depth ≤ 2.

**Done when:** small-model accuracy with and without `CALL` is reported on
`iid`, `deep` and `domain2`.

### M7: System-1 step checker (stopping errors from compounding)

**Problem.** Long chains of steps, and especially M6's recursive calls,
compound errors. If each step is wrong with probability ε, a chain of n steps
succeeds with about (1−ε)ⁿ. With ε = 0.1 and n = 20, that's about 12%.

**Fix.** Add a fast, cheap checker after every step. If it catches a fraction
d of errors and triggers a correction, the per-step error drops to about
ε(1−d). The chain then succeeds with about (1−ε(1−d))ⁿ, about 82% for d = 0.9
in the same example.

The checker doesn't need to be smart. It needs to be fast and cheap, and
**wrong in different ways than the generator**.

CVM's verifier already does the *structural* check: are the cited facts real?
The checker adds a *semantic* check: does this step make sense given the
state?

**Where it plugs in.** A new runtime hook, `RuntimeConfig.checker`. After each
step, and after each child `CALL` in M6, the runtime sends the checker:

- the resident view;
- the operation the model just issued;
- the result.

It gets back typed decisions with probabilities:

| Question | Type | Use |
|---|---|---|
| Is this step on a productive path for the task? | yes/no probability | low → feed back a hint, or retry the step |
| Does this result contradict a conclusion in NOTES? | yes/no probability | high → force a re-check of that conclusion |
| How confident should we be in this ANSWER, given the cited facts? | score | below threshold → reject and continue instead of accepting |
| What next? `accept / retry / reroute / escalate / decompose` | choice | `escalate` = re-run this step on a bigger model; `decompose` = issue a `CALL` (M6) |

The probabilities are the "delta": the size of the surprise. A threshold on
them decides what to do. Keep every intervention visible in the trace so
runs stay auditable.

**Two arms, run in parallel:**

1. **Jev (TypeSafe's System One model), off the shelf.** It takes unstructured
   state plus typed questions and returns calibrated probabilities in one
   parallel pass. It has three answer types:
   - Choice: one of N;
   - Score: a number;
   - Noul: a yes/no probability.

   It doesn't generate text, so it can't return malformed values. Reported
   latency is 70–500 ms, at $0.042 per million input tokens with output free.
   At ~2k tokens per check that's about $0.0001 per step, or ~$0.003 per
   30-step task, against ~$0.04 per task for DeepSeek-Flash in V0.

   Implement as `JevChecker` in `cvm/checkers.py`, reading the key from an env
   var. Check TypeSafe's docs for the current API; a community Claude Code
   integration exists (`FrancoisChastel/jev-code` on GitHub). Jev is in early
   access, so the owner needs a key. In a Claude Code cloud session, its API
   host must also be added to the network allowlist.

2. **Our own critic, trained on CVM's ground truth.** Its training signal comes
   from ground-truth outcomes, not from imitating the generator, so its blind
   spots shouldn't line up with the generator's.
   - Extend M1's exporter to also emit **labelled negative steps**:
     - off-path faults;
     - decoy fetches (e.g. faulting the trap change);
     - premature or wrong answers;
     - retries of denied operations;
     - missing notes before eviction.

     Labels come for free, because the synthetic worlds know the correct path.
   - Train either a small classifier (a ≤1B encoder, or a LoRA head on the M3
     base model) or a JEPA-style predictor. A JEPA-style predictor predicts the
     embedding of the expected result and scores the prediction error.
   - Implement as `TrainedCritic` in `cvm/checkers.py`, behind the same
     interface as `JevChecker`.

**What to measure** (on M2's held-out splits, in combination with M0b's small
models and M6's recursion):

- **catch rate d**: errors flagged ÷ errors made. Report it **separately for
  decoy steps**. A general-purpose checker may find the decoy as plausible as
  the generator does; this is the number that decides whether the idea works;
- **false-alarm rate**: correct steps flagged. These cost extra steps;
- **calibration**: predicted probability vs actual step correctness
  (reliability diagram);
- **chain accuracy vs. depth / steps**, with no checker, with Jev and with the
  trained critic. The target is a curve that stays flat as depth grows;
- **cost and latency overhead** per task;
- **routing**: a small model by default, escalating only flagged steps to a
  bigger model. Measure accuracy and cost against using the big model for
  everything. This is the most direct test of "small models perform far above
  their size".

**Code needed:**

- `cvm/checkers.py` with a `Checker` protocol:
  `check(prompt, action, result) -> {probabilities..., decision}`;
- the runtime hook, with configurable thresholds and actions;
- an `escalate` path that re-runs one step on a second processor;
- exporter negatives (M1);
- `--checker {none,jev,critic}` and `--escalate-to <model>` flags in
  `run_llm.py`;
- tests with a fake checker covering every decision path.

**Done when:** `RESULTS_V1.md` has the chain-accuracy-vs-depth chart for the
three arms, plus decoy catch rates and the routing cost/accuracy table.

## 3. Risks and how the plan handles them

| Risk | Mitigation |
|---|---|
| The model memorizes the reference solver's incident algorithm instead of learning "fault when unsure" | `domain2` and `traps` held-out splits; recovery examples; templated reasons. Report held-out results first |
| Train/serve prompt drift | Exporter uses `SYSTEM_OPENAI` and `build_prompt` directly; one test replays exported actions |
| Overfitting to world size | Train ≤ 10⁴, test at 10⁶ |
| Verifier retry rewards post-hoc citations | Measure rejections *before* retry as the headline. Add a counterfactual check: remove a cited fact and see whether the answer changes |
| Small n | ≥100 tasks per cell; report 95% intervals |
| "Flat by construction" objection | Also sweep task depth and WS size, not just world size, and show the model's accuracy holds at 10⁶ |

## 4. Running V1 with Claude Code locally

```bash
git clone https://github.com/nikitph/2ter && cd 2ter
git checkout claude/cvm-core-thesis-3azicg   # or main once PR #2 is merged
cd cvm && claude
```

Suggested prompt sequence, one milestone per session or per PR:

1. *"Read CLAUDE.md and PLAN_V1.md. Do M0's code change (`--max-objects` in run_llm.py) with a test. Then run the reference processor at WS=4 through run_llm.py's reference provider to sanity-check."*
   Then: *"Run M0b against my local vLLM models and write the table."*
2. *"Implement M1: experiments/export_trajectories.py with the recovery perturbations and a replay test. Generate a 2k-task sample and show me stats."*
3. *"Implement M2: depth_range in synthetic_world, the traps split, and the domain2 code-repo world with ground truth. Verify the reference processor scores 1.00 on every split."*
4. *"Implement M3's v1/train_lora.py and v1/requirements.txt. Don't run training here; give me the exact command for my GPU box."* Then run training on the GPU machine.
5. *"I'm serving the adapter with vLLM at localhost:8000. Run M4's eval matrix and write RESULTS_V1.md."*

CPU-only machines can do M0 (against a hosted API), M1, M2 and the reporting
part of M4. M3, and serving the model in M4, need a GPU or a hosted
fine-tuning service.

## 5. Budget estimate

| Item | Rough cost |
|---|---|
| M0 baselines via hosted API (e.g. DeepSeek-Flash, 100 tasks × 2 WS sizes) | ~$8–10 (V0 measured ~$0.04/task) |
| M1–M2 data generation | $0 (CPU, minutes) |
| M3 LoRA SFT, 7–8B, ~200M tokens, 1×H100 | a few GPU-hours (tens of dollars on rented GPUs) |
| M4 eval, self-hosted vLLM | GPU time only |
| M5 RL (optional) | 5–20× the SFT compute |
| M7 Jev checker | ~$0.003 per 30-step task (at the reported $0.042 per million input tokens) |
| M7 trained critic | small: hours on one GPU, or less for a ≤1B classifier |

## 6. Decisions the owner needs to make

1. **Compute route:** own GPU box, rented GPU, or a hosted fine-tuning API.
2. **Base model:** pick from current open 7–8B instruct models, plus
   optionally a small one.
3. **Second domain (`domain2`):** strongly recommended. It is what makes the
   result more than "the model imitated a script".
4. **Budget cap** for API baselines in M0.
5. **Jev access** for M7: a TypeSafe early-access API key.

## 7. Checklist

- [x] M0 (code): `--max-objects` flag + tests; data-driven depth/kind summaries; reference sanity at WS=32/4 (1.00 everywhere)
- [ ] M0 (models): base model at WS=32 and WS=4 on 10⁶ (n≥100) — needs a served endpoint
- [ ] M0b: `full` condition in `run_llm.py`; small vs 7–8B model × {plain, hint} × {WS=32, WS=4} at 10⁶, plus same small model without CVM at 10³
- [ ] M1: `export_trajectories.py` + replay test + `data/v1/{train,val}.jsonl`
- [ ] M2: `depth_range`, `traps`, `tight`, `domain2` (`synthetic_code_world.py` + `CodeReferenceReasoner`, validation only); reference = 1.00 on all splits
- [ ] M3: `v1/train_lora.py`, `v1/requirements.txt`; adapter with ≥95% op accuracy on val
- [ ] M4: `--split` flag; eval matrix; `RESULTS_V1.md` with charts
- [ ] M5 (optional): RL refinement if SFT plateaus
- [ ] M6 (proposed): `CALL` op for recursive child contexts; small model with/without recursion
- [ ] M7: `checkers.py` (JevChecker + TrainedCritic), runtime hook, exporter negatives, `--checker`/`--escalate-to`; chain accuracy vs depth, decoy catch rate, routing table
