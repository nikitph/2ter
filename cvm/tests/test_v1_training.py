"""Dataset preflight for the optional GPU training stack."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v1.eval_adapter import tokenizer_source
from v1.train_lora import load_examples, main


def example(seed: int, kind: str = "root_cause") -> dict:
    return {"messages": [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "TASK task://0 [root_cause]\n question"},
        {"role": "assistant", "content": '{"op":"FAULT","ref":"incident://x","reason":"need facts"}'},
    ], "meta": {"world_seed": seed, "task_kind": kind}}


class TrainingPreflightTests(unittest.TestCase):
    def test_prompt_completion_and_disjoint_seeds(self):
        with tempfile.TemporaryDirectory() as root:
            train, val = Path(root) / "train.jsonl", Path(root) / "val.jsonl"
            train.write_text(json.dumps(example(1000)) + "\n")
            val.write_text(json.dumps(example(2000)) + "\n")
            rows, seeds = load_examples(train)
            self.assertEqual(seeds, {1000})
            self.assertEqual([m["role"] for m in rows[0]["prompt"]], ["system", "user"])
            self.assertEqual(rows[0]["completion"][0]["role"], "assistant")
            result = main(["--train", str(train), "--val", str(val), "--dry-run"])
            self.assertEqual(result["train_examples"], 1)
            self.assertEqual(result["val_seeds"], [2000])
            val.write_text(json.dumps(example(1000)) + "\n")
            with self.assertRaises(ValueError):
                main(["--train", str(train), "--val", str(val), "--dry-run"])

    def test_domain2_is_rejected_from_training(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "data.jsonl"
            path.write_text(json.dumps(example(4000, "code_cause")) + "\n")
            with self.assertRaises(ValueError):
                load_examples(path)

    def test_checkpoint_adapter_uses_recorded_base_tokenizer(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = Path(root)
            (adapter / "adapter_config.json").write_text(
                json.dumps({"base_model_name_or_path": "Qwen/Qwen2.5-7B-Instruct"}))
            (adapter / "adapter_model.safetensors").write_bytes(b"test weights")
            self.assertEqual(tokenizer_source(adapter), "Qwen/Qwen2.5-7B-Instruct")
            (adapter / "tokenizer_config.json").write_text("{}")
            self.assertEqual(tokenizer_source(adapter), str(adapter))
            (adapter / "adapter_model.safetensors").unlink()
            with self.assertRaisesRegex(ValueError, "weights missing"):
                tokenizer_source(adapter)


if __name__ == "__main__":
    unittest.main()
