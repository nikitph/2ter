# V1 A100 training runbook

The first run uses a Runpod Secure Cloud A100 SXM4 80 GB in EU-RO-1. Its
50 GB persistent network volume is `pxenkl4pyw`, mounted at `/workspace`.
The pod is `kg9fz30agzl7kc` while this training segment is active. A stopped
pod can be restarted; a replacement pod must be in the same data center and
mount the same volume. Stopping a pod stops GPU billing; the volume remains
billed while retained.

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
  --time-limit-minutes 240
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

The first run was started with these options except without
`--resume-from-checkpoint auto`. It saves every two optimizer steps and
evaluates every ten. Early action-level accuracy is a diagnostic only; M3's
target is at least 95% correct operation selection on held-out validation.
