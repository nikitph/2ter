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


def tokenizer_source(adapter_dir: Path) -> str:
    """Use the saved tokenizer, or the PEFT checkpoint's recorded base model."""
    config_path = adapter_dir / "adapter_config.json"
    if not config_path.is_file():
        raise ValueError(f"adapter config missing: {config_path}")
    if not any((adapter_dir / name).is_file()
               for name in ("adapter_model.safetensors", "adapter_model.bin")):
        raise ValueError(f"adapter weights missing: {adapter_dir}")
    if (adapter_dir / "tokenizer_config.json").is_file():
        return str(adapter_dir)
    config = json.loads(config_path.read_text())
    source = config.get("base_model_name_or_path")
    if not isinstance(source, str) or not source:
        raise ValueError(f"checkpoint has no tokenizer or base model: {adapter_dir}")
    return source


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
    try:
        token_source = tokenizer_source(args.adapter_dir)
    except ValueError as exc:
        ap.error(str(exc))
    ops = {op.strip().upper() for op in args.ops.split(",") if op.strip()}
    rows, seeds = load_examples(args.val, args.examples, ops or None)

    import torch
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for adapter evaluation")
    tokenizer = AutoTokenizer.from_pretrained(token_source)
    model = AutoPeftModelForCausalLM.from_pretrained(
        args.adapter_dir, torch_dtype=torch.bfloat16, device_map="cuda")
    metrics = evaluate_actions(model, tokenizer, rows, args.examples,
                               args.max_length)
    metrics.update({"adapter_dir": str(args.adapter_dir),
                    "tokenizer_source": token_source,
                    "validation_world_seeds": sorted(seeds),
                    "expected_ops_filter": sorted(ops) if ops else None})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2), flush=True)
    return metrics


if __name__ == "__main__":
    main()
