# V1 A100 training runbook

The first run uses a Runpod Secure Cloud A100 SXM4 80 GB in EU-RO-1. Its
50 GB persistent network volume is `pxenkl4pyw`, mounted at `/workspace`.
The first pod was `kg9fz30agzl7kc`. As of 2026-10-07 01:46 UTC it was absent
from Runpod's pod inventory; the volume remained present. A replacement pod
must be in the same data center and mount that volume. Stop the replacement
pod through the Runpod API or console as soon as the training process exits:
`--time-limit-minutes` stops Python training, **not pod billing**. The volume
remains billed while retained, at about $0.00486/hour for 50 GB in this run.

The verified full export is at `/workspace/cvm-v1-full/data/` and the base
model cache is at `/workspace/hf-cache/`. Training output is in
`/workspace/cvm-v1-full/train/`; checkpoints are under `checkpoints/`, the
current adapter under `adapter/`, and action-level metrics in `metrics.json`.
The log is `/workspace/cvm-v1-full/train.log`.

Resume with the same data, model, effective batch, and output directory:

```bash
cd /workspace/2ter/cvm
HF_HOME=/workspace/hf-cache python3 -u v1/train_lora.py \
  --train /workspace/cvm-v1-full/data/train.jsonl \
  --val /workspace/cvm-v1-full/data/val.jsonl \
  --output-dir /workspace/cvm-v1-full/train \
  --train-examples 100000 --val-examples 256 \
  --max-steps -1 --grad-accum 64 --eval-steps 10 --save-steps 2 \
  --eval-generation-examples 32 --resume-from-checkpoint auto \
  --time-limit-minutes 120
```

`auto` selects the highest numbered complete Trainer checkpoint. The time
limit is per invocation and finishes the current optimizer step before
saving and exiting. Checkpoints include optimizer, scheduler, RNG, adapter,
and Trainer state. The script keeps the latest three complete checkpoints.
If an invocation is interrupted between saves, resume from the last complete
checkpoint. Keep the volume until training and downstream evaluation are
finished; deleting the pod alone does not delete the volume.

After a segment exits, check operation selection on a larger validation
sample before deciding whether to resume training:

```bash
cd /workspace/2ter/cvm
HF_HOME=/workspace/hf-cache python3 v1/eval_adapter.py \
  --adapter-dir /workspace/cvm-v1-full/train/adapter \
  --val /workspace/cvm-v1-full/data/val.jsonl --examples 256 \
  --out /workspace/cvm-v1-full/adapter_val_256.json
```

The first run used a four-hour time limit and started without
`--resume-from-checkpoint auto`. The next segment is limited to two training
hours inside a 210-minute pod guard, leaving up to 90 minutes for setup,
validation, and shutdown. If setup takes longer than expected, reduce the
training limit so the process can finish before the guard deadline. Early action-level
accuracy is a diagnostic only; M3's target is at least 95% correct operation
selection on held-out validation.

Before resuming, inspect `checkpoints/` and `metrics.json` on the mounted
volume. Checkpoint 40 is the last one independently verified before the pod
disappeared; a later checkpoint may exist. After starting a replacement pod,
install `v1/requirements.txt` into its PyTorch template and update the repo
checkout. The model cache and exported data are on the volume. Do not start a
new training process while another one is running. The first credit was fully
used; arrange a pod-level stop mechanism before another long segment.

## Independent billing guard for the next pod

Runpod's published CLI page mentions `pod create --stop-after`, but the
installed `runpodctl` 2.14.0 does not expose that flag. The next pod must
therefore have an independent local guard before training begins.
`v1/runpod_stop_guard.py` uses authenticated `runpodctl` to stop a specific
pod at a deadline and confirms the resulting state. It runs on the Mac,
outside the Codex session and GPU container. Configure CLI authentication
locally with `runpodctl doctor` or `RUNPOD_API_KEY`; never put the key in the
repository or chat. Verify `runpodctl user` succeeds first.

Once the replacement pod is RUNNING, from the `cvm/` directory on the Mac:

```bash
python3 v1/runpod_stop_guard.py --pod-id <new-pod-id> \
  --after-minutes 210 --preflight-only
nohup caffeinate -dimsu python3 -u v1/runpod_stop_guard.py \
  --pod-id <new-pod-id> --after-minutes 210 \
  > /tmp/cvm-runpod-guard.log 2>&1 < /dev/null &
```

Confirm the log contains `GUARD_READY` before starting training. The example
uses `--time-limit-minutes 120`, leaving 90 minutes of the 210-minute guard
for setup, checkpoint finalization, validation, and transfer. Count time from
`GUARD_READY`, not from the start of Python training. If training ends
earlier, stop the pod immediately through Runpod and verify it is no longer
RUNNING. The guard is a fallback if the Codex session is interrupted. The
volume persists after the pod stops; retain it until checkpoints are copied
or further training is complete.

## Interrupted model evaluations

The first vLLM attempt installed a CUDA 13 build that could not run on the
CUDA 12.8 pod driver. Use a separate CUDA 12.8 environment and verify it
before serving. The current vLLM 0.11.x documentation supports the CUDA 12.8
PyTorch index; do not reuse an unverified partial installation on the volume.
The adapter has rank 32, above vLLM's default maximum of 16.

```bash
python3 -m venv /workspace/vllm-cu128
/workspace/vllm-cu128/bin/pip install 'vllm==0.11.0' \
  --extra-index-url https://download.pytorch.org/whl/cu128
HF_HOME=/workspace/hf-cache /workspace/vllm-cu128/bin/vllm serve \
  Qwen/Qwen2.5-7B-Instruct --enable-lora --max-lora-rank 32 \
  --lora-modules cvm=/workspace/cvm-v1-full/train/adapter \
  --max-model-len 8192 --host 127.0.0.1 --port 8000
```

Confirm `/v1/models` lists both the base model and `cvm`, then run a
one-task pilot using a unique tag. For full CVM cells, pass
`--max-output-tokens 512` so an action response and its prompt fit the server
window. Train and serve sequentially: both need the A100's memory.

Run `experiments/run_llm.py` with a separate `--tag` for each base or adapter
cell and write `--out-dir` to `/workspace/cvm-v1-full/eval/`. It journals each
completed task to `llm_<tag>_progress.jsonl` with an `fsync`. Rerun an
interrupted cell with the same arguments plus `--resume`; it skips saved tasks
and rebuilds the summary and traces. The runner refuses changed run settings
or accidental overwrite of an existing journal. Copy the final summary and
traces into the repository's `results/` directory and commit them before
deleting the network volume.
