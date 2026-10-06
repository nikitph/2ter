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
   scores 1.00 with zero thrash. The difference is entirely **notes**: the
   model wrote about 1 per task whether it had 32 objects or 4, so evicted
   state was simply lost. This is V0's notes ablation, reproduced with a live
   model.
3. **This is the clearest target for V1.** Collapsing from 0.68 to 0.10 isn't
   a reasoning deficit; it's one missing habit: write down what you'll need
   before it's evicted. The reference processor shows the habit is enough
   by itself (1.00 at 4 objects). That makes it the first thing M1's training
   data must teach, and the `tight` split in M2 is the test that it was
   learned.
4. **Thrash is worse than it looks.** The model faulted more (31 vs 18 per
   task) and fetched mostly relevant objects (fault precision 0.54). It knew
   what it needed, kept losing it, and fetched it again. That matches the
   spec's description of cognitive thrashing.

Remaining DeepSeek balance after M0: about $2.43.
