# CVM V1: results

Results for the milestones in [PLAN_V1.md](PLAN_V1.md), added as they land.
V0 results are in [RESULTS_V0.md](RESULTS_V0.md).

## M0: Working-set flag and reference sanity check

**What changed.** `experiments/run_llm.py` now takes:

- **`--max-objects N`:** the CVM working-set size, default 32. It applies to
  the `cvm` condition only; the `agent` baseline keeps an unbounded transcript
  and the runner says so.
- **`--out-dir`:** where the result files go.

It also now:

- rejects conditions other than `cvm` and `agent`;
- records `max_objects` in the result file;
- reports accuracy for whatever task kinds and depths occur, instead of a
  fixed 1–3.

Four new tests cover these.

**Sanity check.** The reference processor, through the runner, with 30 tasks
per cell (the same seeded tasks in both working-set sizes):

| World | Working set | Accuracy | Peak resident objects (mean / max) | Peak prompt tokens (mean / max) | Evictions per task | Thrash rate | Notes written per task | Steps |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,015 | 32 | 1.00 | 9.6 / 13 | 1,771 / 2,247 | 0 | 0.00 | 12.3 | 31.4 |
| 1,015 | **4** | 1.00 | **4.0 / 4** | 1,355 / 1,570 | 5.6 | 0.00 | 12.3 | 31.4 |
| 999,991 | 32 | 1.00 | 9.2 / 13 | 1,766 / 2,298 | 0 | 0.00 | 11.6 | 29.8 |
| 999,991 | **4** | 1.00 | **4.0 / 4** | 1,365 / 1,599 | 5.2 | 0.00 | 11.6 | 29.8 |

Accuracy is 1.00 for every task kind (root cause, owner, claim) and every
depth (1–3) in all four cells. Files:

- `results/llm_m0-reference-ws32.json` and `_traces.jsonl`
- `results/llm_m0-reference-ws4.json` and `_traces.jsonl`

**Reading.**

- **The cap holds exactly.** With 4 objects, residency never goes above 4, and
  objects really are evicted (about 5 per task).
- **Notes carry the state.** With notes, nothing evicted is ever fetched again
  (thrash 0.00), and step counts are identical to the 32-object runs.
- **The prompt shrinks** about 23%, from ~1.77k to ~1.36k peak tokens.

This is the bar for the model baselines. A model that writes notes the way the
reference processor does should lose nothing at 4 objects. V0's DeepSeek runs
averaged about 1 note per task, against about 12 here. That predicts a sharp
drop at 4 objects; the DeepSeek baseline below confirms it.

## M0: Model baseline, DeepSeek-V4.1-Flash at 10⁶ objects

Settings: the same runtime and generic system prompt as V0 (no method hint),
temperature 0, at most 50 steps, 40 tasks per cell. Both cells use the same
seeded tasks. Intervals are 95%. Files:

- `results/llm_m0-deepseek-flash-ws32.json` and `_traces.jsonl`
- `results/llm_m0-deepseek-flash-ws4.json` and `_traces.jsonl`

| | WS = 32 | **WS = 4** | Reference processor, WS = 4 |
|---|---:|---:|---:|
| **Accuracy** | **0.68** ± 0.15 | **0.10** ± 0.09 | 1.00 |
| Root cause / owner / claim | 0.79 / 0.62 / 0.62 | 0.00 / 0.31 / 0.00 | 1.00 / 1.00 / 1.00 |
| Depth 1 / 2 / 3 | 0.67 / 0.67 / 0.70 | 0.07 / 0.07 / 0.20 | 1.00 / 1.00 / 1.00 |
| Peak resident objects (mean / max) | 12.7 / 22 | 3.9 / 4 | 4.0 / 4 |
| Peak prompt tokens (mean / max) | 2,045 / 3,217 | 1,134 / 1,434 | 1,365 / 1,599 |
| Evictions per task | 0 | 22.8 | 5.2 |
| **Thrash rate** (re-fetching evicted objects) | 0.00 | **0.59** | 0.00 |
| **Notes written per task** | 1.0 | **0.95** | 11.6 |
| Faults per task | 18.2 | 31.4 | — |
| Steps per task | 28.9 | 37.7 | 29.8 |
| Hit the 50-step limit | 3 / 40 | **22 / 40** | 0 / 30 |
| Answers rejected by verifier | 27% | 0% (few answers reached) | 0% |
| Capability faults per task | 5.7 | 5.3 | 0 |
| Wrong answers: no answer / decoy / other | 3 / 1 / 9 | 22 / 8 / 6 | — |
| Model tokens per task, input / output | 74k / 55k | 72k / 35k | — |
| Cost | $1.53 | $1.03 | — |

**Reading.**

1. **The 32-object baseline reproduces V0.** Accuracy was 0.68, against 0.70
   in V0, with ~12.7 resident objects and ~2k peak tokens. The headline
   holds on a fresh set of tasks. Per-kind numbers moved (root cause 0.79
   here vs 0.40 in V0) but those cells hold only 13–14 tasks each, so read the
   overall figure, not the split.
2. **A small working set collapses an untrained model, exactly as predicted.**
   At 4 objects:
   - accuracy falls to **0.10**;
   - 59% of materializations re-fetch something it already had and lost;
   - more than half the tasks run out of steps.

   The reference processor, in the same 4-object cell on the same world,
   scores 1.00 with zero thrash. The live model wrote about 1 note per task
   whether it had 32 objects or 4. Underusing notes is a strong explanation
   for repeated fetches, but this comparison does not isolate notes: the
   reference processor also differs in planning and answer selection. A
   controlled notes intervention on the same model is needed to measure the
   causal contribution.
3. **This is the clearest target for V1.** The repeated fetches point to a
   missing habit: write down what you'll need before it's evicted. The
   reference processor demonstrates that a policy using notes can solve these
   tasks at 4 objects. M1 teaches that policy, and M2's `tight` split checks
   whether the trained model improves. The improvement must still be measured
   against the same model and task seeds.
4. **Thrash is worse than it looks.** The model faulted more (31 vs 18 per
   task) and fetched mostly relevant objects (fault precision 0.54). It knew
   what it needed, kept losing it, and fetched it again. That matches the
   spec's description of cognitive thrashing.

Remaining DeepSeek balance after M0: about $2.43.

**Still pending:** the untrained baseline for the open model selected for M3.

## M1: Trajectory exporter

`python3 experiments/export_trajectories.py --tasks 10000 --out data/v1`
completed locally. It ran 10,000 reference tasks through `CVMRuntime` with
100% correct answers and no step limits, then wrote 254,147 training and
50,897 validation examples. The splits use 20 training world seeds (1000–1019)
and four distinct validation seeds (2000–2003). Both contain world sizes near
10², 10³ and 10⁴ objects, all three task kinds, depths 1–3, SEARCH enabled and
disabled, and working sets of 4, 8, 16 and 32 objects. Eviction recovery tasks
also use a 2-object working set.

The 305,044 examples include 6,427 recovery targets: 625 each after an
unsupported answer, a denied operation and a useless fault, plus 4,552 after
an eviction. The exporter deduplicated exact prompt/action pairs (none in this
run), shuffled each split, and estimated 326 million prompt tokens. All
exported assistant messages passed `first_json_object` and `normalize_action`
in a streaming validation. Unit tests replay each recovery trajectory through
the runtime, check the answer, and verify exported actions and split seeds.

The generated `data/v1/` files are ignored by Git (about 1.9 GB). They can be
regenerated with the command above. This dataset is ready for model training. The open-model baseline remains pending.

## M2: Held-out split reference checks

`python3 experiments/v1_splits.py --tasks 100` passed all cells. The machine-
readable output is `results/v1_reference_splits.json`.

| Split | World objects | Working set | Correct | Step limits |
|---|---:|---:|---:|---:|
| iid (10³) | 1,015 | 32 | 100/100 | 0 |
| iid (10⁶) | 999,991 | 32 | 100/100 | 0 |
| scale | 999,991 | 32 | 100/100 | 0 |
| deep (depth 4–5) | 1,219 | 32 | 100/100 | 0 |
| traps | 1,103 | 32 | 100/100 | 0 |
| tight | 999,991 | 4 | 100/100 | 0 |
| domain2 (code repositories) | 999 | 32 | 100/100 | 0 |

The code-repository world has a separate prompt-only `CodeReferenceReasoner`
for this solvability check. It is never used to create M1 training examples.
The `full` condition in `run_llm.py` also passed a three-task reference smoke
test at 10³ objects (one step each), and marked all three tasks infeasible
when its model-window limit was set below the estimated prompt length.

## M3: A100 training sanity check

On a Runpod A100 SXM4 80 GB in EU-RO-1, the Qwen2.5-7B-Instruct LoRA script
completed two optimizer steps, saved checkpoints, evaluated held-out prompts,
and resumed from checkpoint 2 to complete step 4. The first evaluation
generated valid JSON on 16/16 prompts and chose the right operation on 4/16;
the resumed evaluation generated valid JSON on 4/4 and chose the right
operation on 1/4. These tiny, partially trained evaluations check the
pipeline only; they are not model performance estimates.

The full exported dataset was copied to the persistent volume and all three
file SHA-256 hashes matched the local files. The 100,000-example run saves
every two optimizer steps and evaluates loss every ten steps. Machine-readable
pilot details: `results/v1_a100_sanity.json`.

The first ten full-size optimizer steps took 8 minutes 34 seconds including
one 256-example evaluation (53 seconds). GPU memory reached about 51 GB and
the first held-out loss was 0.704. If this early rate holds, 1,563 steps
(one epoch) would take roughly 22 GPU hours, about $35 at the selected
$1.59/hour rate, plus startup and storage. This is an estimate, not a
completed-run measurement; the initial $10 balance cannot cover an epoch.

**First action-level gate, checkpoint 34.** Held-out loss fell from 0.704 at
step 10 to 0.192 at step 20 and 0.042 at step 30. The training process was
paused after a complete checkpoint 34 to score 256 held-out prompts:

| Metric | Result |
|---|---:|
| Valid JSON | 252/256 (98.4%) |
| Correct operation | 229/256 (89.5%) |
| Exact action | 206/256 (80.5%) |

This is below M3's 95% operation target, so training resumed from checkpoint
34 with the original one-epoch schedule. The exact result is
`results/v1_adapter_val_step34.json`. This gate measures individual actions;
full held-out task accuracy remains unmeasured until M4.

**Second action-level gate, checkpoint 40.** After resuming from 34, held-out
loss fell to 0.012 at step 40. The same 256-prompt validation sample scored
255/256 valid JSON, 244/256 correct operations (**95.3%**), and 233/256 exact
actions (91.0%). The operation breakdown matters:

| Expected operation | Correct operation |
|---|---:|
| WRITE | 110/110 |
| FAULT | 62/63 |
| TRAVERSE | 61/62 |
| EVIDENCE | 3/3 |
| ANSWER | 7/8 |
| SEARCH | **1/10** |

The aggregate M3 operation target is met on this sample, but SEARCH remains
weak, so training resumed from checkpoint 40. The detailed result is
`results/v1_adapter_val_step40.json`. A larger, operation-stratified check
and task-level M4 runs are needed before treating the adapter as ready.

**Runpod budget stop.** At 2026-10-07 01:46 UTC, Runpod reported no pod and
`get_pod` returned 404. The 50 GB network volume still existed in EU-RO-1.
The billing API showed $10.001 GPU, $0.026 pod disk, and $0.029 network
volume charges ($10.056 total). The pod was not stopped before the available
credit was consumed. The last checkpoint inspected over SSH was step 40, and
the last live training step observed was 48. The status of later checkpoints
and the second training segment's final metrics cannot be verified until the
volume is mounted again. No GPU pod was running at the time of this check.
The machine-readable audit is `results/v1_runpod_segment_2026-10-06.json`.
The action evaluator now accepts a complete Trainer checkpoint directly if
the interrupted run did not save a final adapter directory; it loads the
base-model tokenizer recorded in the checkpoint's PEFT config.

**Recovered training result, checkpoint 203.** On 2026-10-07 the retained
volume was remounted. The previous segment had completed step 203 of 1,563
and saved both a complete Trainer checkpoint and a final adapter with identical
weight hashes. Its lowest recorded validation loss was 0.000964 at step 180;
the final 32-prompt diagnostic was 32/32 exact but contained no SEARCH cases.
On the same 256 held-out action prompts used for checkpoint 40, checkpoint
203 produced 255/256 valid JSON, **253/256 correct operations (98.8%)**, and
**252/256 exact actions (98.4%)**. SEARCH improved to 9/10. The raw outputs
are `results/v1_train_step203_metrics.json` and
`results/v1_adapter_val_step203.json`. This is action-level evidence only;
the base-versus-adapter task-level comparison is still in progress.
An operation-stratified check on another 128 held-out prompts scored
**67/69 SEARCH** and **56/59 ANSWER** exactly, with 123/128 operations correct
overall (`results/v1_adapter_val_step203_search_answer.json`).

## M4: Evaluation runner readiness

The runner now writes a durable record after each completed task. An
interrupted reference-provider test resumed the unfinished task without
repeating the three completed tasks, rebuilt all four traces and the summary,
and recovered from a deliberately truncated final journal line. A second
test rejected a resume with changed task settings. The serving preflight also
identified two configuration requirements: the rank-32 adapter needs
`--max-lora-rank 32` (vLLM defaults to 16), and a bounded response allowance
is needed with an 8192-token server window. `run_llm.py` now records and
applies `--max-output-tokens`; the M4 command uses 512. The full local suite
passed 40 tests. Model-level M4 cells are still pending a served base model
and the saved adapter on a GPU.
