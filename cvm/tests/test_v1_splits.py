"""Focused checks for the held-out V1 worlds and runner wiring."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cvm.experiment import make_tasks
from cvm.processors import CodeReferenceReasoner
from cvm.resolver import GraphStore
from cvm.synthetic_code_world import build_code_world
from cvm.synthetic_world import build_world
from experiments import run_llm
from experiments.v1_splits import run_reference


class V1SplitTests(unittest.TestCase):
    def test_reference_solves_held_out_variants(self):
        for split in ("deep", "traps", "domain2"):
            rows = run_reference(split, tasks=12)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["correct"], 12)
            self.assertEqual(rows[0]["step_limits"], 0)

    def test_new_traps_and_code_decoys_are_in_ground_truth_worlds(self):
        with tempfile.TemporaryDirectory() as root:
            incident = GraphStore(build_world(1000, seed=11, cache_dir=root, traps=True).path)
            try:
                t = incident.truth()[0]
                self.assertIsNotNone(incident.get(t["affected"].replace("service://", "deploy://") + "-trap"))
                self.assertIsNotNone(incident.get(t["root"].replace("service://", "change://") + "-post-anomaly"))
            finally:
                incident.db.close()
            code = GraphStore(build_code_world(1000, seed=12, cache_dir=root).path)
            try:
                t = code.truth()[0]
                self.assertIn(make_tasks(code, 1, domain="code")[0].expected,
                              {row["cause"] for row in code.truth()})
                self.assertEqual(len([r for r in code.get(t["root"]).relations
                                      if r.predicate == "CHANGED_IN"]), 3)
            finally:
                code.db.close()

    def test_code_reasoner_is_prompt_only(self):
        with tempfile.TemporaryDirectory() as root:
            store = GraphStore(build_code_world(100, seed=14, cache_dir=root).path)
            try:
                spec = make_tasks(store, 1, domain="code")[0]
                from cvm.context import CognitiveContext, code_agent_capabilities
                from cvm.runtime import CVMRuntime
                from cvm.working_set import WorkingSet
                rt = CVMRuntime(store)
                ctx = CognitiveContext("code", spec.task, code_agent_capabilities(), WorkingSet(4))
                rt.seed(ctx)
                prompt = rt.build_prompt(ctx)
                self.assertEqual(CodeReferenceReasoner().step(prompt),
                                 CodeReferenceReasoner().step(prompt))
            finally:
                store.db.close()

    def test_runner_full_context_and_code_split(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root)
            run_llm.main(["--provider", "reference", "--sizes", "1000", "--tasks", "3",
                          "--conditions", "full", "--full-context-limit", "128000",
                          "--out-dir", str(out), "--tag", "full"])
            full = json.loads((out / "llm_full.json").read_text())["sizes"][0]["conditions"]["full"]
            self.assertEqual(full["accuracy"], 1.0)
            self.assertEqual(full["steps_mean"], 1.0)
            run_llm.main(["--provider", "reference", "--sizes", "1000", "--tasks", "3",
                          "--conditions", "full", "--full-context-limit", "1000",
                          "--out-dir", str(out), "--tag", "infeasible"])
            infeasible = json.loads((out / "llm_infeasible.json").read_text())["sizes"][0]["conditions"]["full"]
            self.assertEqual(infeasible["infeasible"], 3)
            run_llm.main(["--provider", "reference", "--split", "domain2", "--tasks", "9",
                          "--max-objects", "4", "--out-dir", str(out), "--tag", "code"])
            code = json.loads((out / "llm_code.json").read_text())["sizes"][0]["conditions"]["cvm"]
            self.assertEqual(code["accuracy"], 1.0)
            self.assertEqual(code["accuracy_by_kind"], {"code_cause": 1.0})


if __name__ == "__main__":
    unittest.main()
