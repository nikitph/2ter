"""An interrupted paid evaluation resumes only the unfinished tasks."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments import run_llm


class RunnerResumeTests(unittest.TestCase):
    def test_resume_reuses_completed_tasks_and_rebuilds_results(self):
        with tempfile.TemporaryDirectory() as root:
            args = ["--provider", "reference", "--sizes", "600", "--tasks", "4",
                    "--workers", "1", "--out-dir", root, "--tag", "interrupted"]
            original = run_llm.make_processor
            calls = 0

            def interrupt_once(*a, **kw):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise RuntimeError("simulated transient failure")
                return original(*a, **kw)

            with patch.object(run_llm, "make_processor", side_effect=interrupt_once):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    run_llm.main(args)
            progress = Path(root) / "llm_interrupted_progress.jsonl"
            self.assertEqual(len(progress.read_text().splitlines()), 4)  # header + 3 tasks
            with progress.open("a") as torn:
                torn.write('{"cell_index":')
            with patch.object(run_llm, "make_processor", wraps=original) as resumed:
                run_llm.main([*args, "--resume"])
            self.assertEqual(resumed.call_count, 1)
            report = json.loads((Path(root) / "llm_interrupted.json").read_text())
            self.assertEqual(len(report["sizes"][0]["runs"]), 4)
            self.assertEqual(report["sizes"][0]["conditions"]["cvm"]["accuracy"], 1.0)
            self.assertEqual(len((Path(root) / "llm_interrupted_traces.jsonl").read_text().splitlines()), 4)
            with patch.object(run_llm, "make_processor", side_effect=AssertionError("reran")):
                run_llm.main([*args, "--resume"])

    def test_resume_rejects_changed_run_settings(self):
        with tempfile.TemporaryDirectory() as root:
            args = ["--provider", "reference", "--sizes", "600", "--tasks", "1",
                    "--out-dir", root, "--tag", "settings"]
            run_llm.main(args)
            with self.assertRaisesRegex(ValueError, "settings differ"):
                run_llm.main([*args, "--tasks", "2", "--resume"])


if __name__ == "__main__":
    unittest.main()
