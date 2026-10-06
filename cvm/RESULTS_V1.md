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
drop at 4 objects, which the M0 model baselines will measure.

**Still pending: model baselines.** These need a served endpoint, a local vLLM
or a hosted API key; the machine that ran this slice had neither. The commands
are in PLAN_V1.md §M0. Each one adds a row per model × working-set size here.

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
regenerated with the command above. This dataset is ready for the first small
training trial; the model baselines and model training remain pending.

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
