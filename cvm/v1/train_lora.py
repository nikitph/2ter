"""LoRA SFT for CVM's prompt/action trajectories.

Local preflight (no ML dependencies):
    python3 v1/train_lora.py --dry-run --train-examples 512 --val-examples 64

A100 pilot:
    python3 v1/train_lora.py --train-examples 512 --val-examples 64 \
      --max-steps 2 --grad-accum 4 --eval-steps 1 --eval-generation-examples 16
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.processors import first_json_object, normalize_action  # noqa: E402

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
CHECKPOINT_FILES = ("trainer_state.json", "optimizer.pt", "scheduler.pt",
                    "rng_state.pth", "adapter_model.safetensors")


def checkpoint_complete(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in CHECKPOINT_FILES)


def resolve_checkpoint(output_dir: Path, value: str | None) -> str | None:
    """Resolve an explicit checkpoint or the newest complete Trainer checkpoint."""
    if value is None:
        return None
    if value != "auto":
        checkpoint = Path(value)
        if not checkpoint_complete(checkpoint):
            raise ValueError(f"incomplete checkpoint: {checkpoint}")
        return str(checkpoint)
    root = output_dir / "checkpoints"
    checkpoints = sorted(
        (p for p in root.glob("checkpoint-*") if checkpoint_complete(p)),
        key=lambda p: int(p.name.rsplit("-", 1)[-1]),
    )
    if not checkpoints:
        raise ValueError(f"no complete checkpoint to resume in {root}")
    return str(checkpoints[-1])


def load_examples(path: Path, limit: int = 0,
                  ops: set[str] | None = None) -> tuple[list[dict], set[int]]:
    """Convert chat JSONL to conversational prompt/completion rows for TRL."""
    rows: list[dict] = []
    seeds: set[int] = set()
    with path.open() as source:
        for line in source:
            item = json.loads(line)
            messages = item["messages"]
            if [m["role"] for m in messages] != ["system", "user", "assistant"]:
                raise ValueError(f"unexpected chat roles in {path}")
            action = first_json_object(messages[2]["content"])
            if action is None or normalize_action(action) != action:
                raise ValueError(f"invalid action in {path}")
            if item["meta"]["task_kind"] == "code_cause":
                raise ValueError("domain2 must stay held out of training")
            if ops is not None and action["op"] not in ops:
                continue
            seeds.add(int(item["meta"]["world_seed"]))
            rows.append({"prompt": messages[:2], "completion": messages[2:]})
            if limit and len(rows) >= limit:
                break
    if not rows:
        raise ValueError(f"no examples in {path}")
    return rows, seeds


def evaluate_actions(model, tokenizer, rows: list[dict], limit: int,
                     max_length: int) -> dict:
    """Generate one operation per held-out prompt and score JSON/op accuracy."""
    import torch

    model.eval()
    device = next(model.parameters()).device
    results = {"examples": 0, "json_valid": 0, "op_correct": 0,
               "action_exact": 0, "by_expected_op": {}}
    for row in rows[:limit or None]:
        expected = first_json_object(row["completion"][0]["content"])
        op = expected["op"]
        bucket = results["by_expected_op"].setdefault(
            op, {"examples": 0, "json_valid": 0, "op_correct": 0,
                 "action_exact": 0})
        bucket["examples"] += 1
        prompt = tokenizer.apply_chat_template(row["prompt"], tokenize=False,
                                               add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True,
                           max_length=max_length - 256).to(device)
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=256, do_sample=False,
                                    pad_token_id=tokenizer.eos_token_id)
        generated = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:],
                                     skip_special_tokens=True)
        predicted = first_json_object(generated)
        results["examples"] += 1
        if predicted is None:
            continue
        results["json_valid"] += 1
        bucket["json_valid"] += 1
        predicted = normalize_action(predicted)
        if predicted.get("op") == expected.get("op"):
            results["op_correct"] += 1
            bucket["op_correct"] += 1
        if predicted == expected:
            results["action_exact"] += 1
            bucket["action_exact"] += 1
    n = results["examples"]
    for key in ("json_valid", "op_correct", "action_exact"):
        results[key + "_rate"] = results[key] / n if n else 0.0
    for bucket in results["by_expected_op"].values():
        for key in ("json_valid", "op_correct", "action_exact"):
            bucket[key + "_rate"] = bucket[key] / bucket["examples"]
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", type=Path, default=Path("data/v1/train.jsonl"))
    ap.add_argument("--val", type=Path, default=Path("data/v1/val.jsonl"))
    ap.add_argument("--base-model", default=DEFAULT_MODEL)
    ap.add_argument("--output-dir", type=Path, default=Path("data/v1/adapter"))
    ap.add_argument("--train-examples", type=int, default=100_000,
                    help="0 uses the entire training split")
    ap.add_argument("--val-examples", type=int, default=2048,
                    help="0 uses the entire validation split")
    ap.add_argument("--eval-generation-examples", type=int, default=64)
    ap.add_argument("--max-steps", type=int, default=-1,
                    help="positive for a short sanity trial; -1 trains one epoch")
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=64)
    ap.add_argument("--eval-steps", type=int, default=100)
    ap.add_argument("--save-steps", type=int, default=0,
                    help="checkpoint interval; 0 uses --eval-steps")
    ap.add_argument("--resume-from-checkpoint", default=None,
                    help="checkpoint path or 'auto' for latest complete checkpoint")
    ap.add_argument("--time-limit-minutes", type=float, default=0,
                    help="finish the current optimizer step, save, and exit after this long")
    ap.add_argument("--max-length", type=int, default=4096)
    ap.add_argument("--learning-rate", type=float, default=1.5e-4)
    ap.add_argument("--lora-r", type=int, default=32)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if min(args.batch_size, args.grad_accum, args.eval_steps, args.max_length,
           args.lora_r) < 1 or args.train_examples < 0 or args.val_examples < 0:
        ap.error("batch, accumulation, evaluation, length and LoRA rank must be positive")
    if args.save_steps < 0:
        ap.error("save-steps must be nonnegative")
    if args.time_limit_minutes < 0:
        ap.error("time-limit-minutes must be nonnegative")
    save_steps = args.save_steps or args.eval_steps
    train_rows, train_seeds = load_examples(args.train, args.train_examples)
    val_rows, val_seeds = load_examples(args.val, args.val_examples)
    if not train_seeds.isdisjoint(val_seeds):
        raise ValueError("training and validation world seeds overlap")
    preflight = {"train_examples": len(train_rows), "val_examples": len(val_rows),
                 "train_seeds": sorted(train_seeds), "val_seeds": sorted(val_seeds),
                 "base_model": args.base_model}
    print(json.dumps(preflight, indent=2), flush=True)
    if args.dry_run:
        return preflight

    resume_checkpoint = resolve_checkpoint(args.output_dir, args.resume_from_checkpoint)

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for LoRA training")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.base_model, torch_dtype=torch.bfloat16,
                                                attn_implementation="sdpa")
    model.config.use_cache = False
    args.output_dir.mkdir(parents=True, exist_ok=True)
    load_best = save_steps % args.eval_steps == 0
    config = SFTConfig(
        output_dir=str(args.output_dir / "checkpoints"),
        max_length=args.max_length,
        completion_only_loss=True,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        per_device_eval_batch_size=1,
        max_steps=args.max_steps,
        num_train_epochs=1,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        bf16=True,
        gradient_checkpointing=True,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=save_steps,
        save_total_limit=3,
        load_best_model_at_end=load_best,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=1,
        report_to="none",
        seed=7,
    )
    lora = LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r,
                      lora_dropout=0.05, target_modules="all-linear",
                      bias="none", task_type="CAUSAL_LM")
    class TimeLimitCallback(TrainerCallback):
        def __init__(self, minutes: float):
            self.deadline = time.monotonic() + minutes * 60

        def on_step_end(self, args, state, control, **kwargs):
            if time.monotonic() >= self.deadline:
                control.should_save = True
                control.should_training_stop = True
                print(f"TIME_LIMIT_CHECKPOINT step={state.global_step}", flush=True)
            return control

    callbacks = ([TimeLimitCallback(args.time_limit_minutes)]
                 if args.time_limit_minutes else [])
    trainer = SFTTrainer(model=model, args=config,
                         train_dataset=Dataset.from_list(train_rows),
                         eval_dataset=Dataset.from_list(val_rows),
                         peft_config=lora, processing_class=tokenizer,
                         callbacks=callbacks)
    trainer.train(resume_from_checkpoint=resume_checkpoint)
    adapter_dir = args.output_dir / "adapter"
    trainer.model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    metrics = evaluate_actions(trainer.model, tokenizer, val_rows,
                               args.eval_generation_examples, args.max_length)
    metrics.update(preflight)
    metrics["resumed_from_checkpoint"] = resume_checkpoint
    metrics["global_step"] = trainer.state.global_step
    metrics["max_steps"] = trainer.state.max_steps
    metrics["time_limit_minutes"] = args.time_limit_minutes
    metrics["best_model_checkpoint"] = trainer.state.best_model_checkpoint
    (args.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print("TRAIN_DONE", json.dumps(metrics), flush=True)
    return metrics


if __name__ == "__main__":
    main()
