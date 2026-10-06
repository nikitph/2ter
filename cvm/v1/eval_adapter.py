"""Evaluate a saved LoRA adapter on held-out action prompts.

    python3 v1/eval_adapter.py --adapter-dir data/v1/adapter/adapter \
      --val data/v1/val.jsonl --examples 256 --out results/adapter_val.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from v1.train_lora import evaluate_actions, load_examples


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter-dir", type=Path, required=True)
    ap.add_argument("--val", type=Path, required=True)
    ap.add_argument("--examples", type=int, default=256)
    ap.add_argument("--ops", default="",
                    help="optional comma-separated expected operations, e.g. SEARCH,ANSWER")
    ap.add_argument("--max-length", type=int, default=4096)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.examples < 1 or args.max_length < 257:
        ap.error("examples must be positive and max-length must exceed 256")
    if not (args.adapter_dir / "adapter_config.json").is_file():
        ap.error("adapter-dir must contain adapter_config.json")
    ops = {op.strip().upper() for op in args.ops.split(",") if op.strip()}
    rows, seeds = load_examples(args.val, args.examples, ops or None)

    import torch
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for adapter evaluation")
    tokenizer = AutoTokenizer.from_pretrained(args.adapter_dir)
    model = AutoPeftModelForCausalLM.from_pretrained(
        args.adapter_dir, torch_dtype=torch.bfloat16, device_map="cuda")
    metrics = evaluate_actions(model, tokenizer, rows, args.examples,
                               args.max_length)
    metrics.update({"adapter_dir": str(args.adapter_dir),
                    "validation_world_seeds": sorted(seeds),
                    "expected_ops_filter": sorted(ops) if ops else None})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2), flush=True)
    return metrics


if __name__ == "__main__":
    main()
