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
