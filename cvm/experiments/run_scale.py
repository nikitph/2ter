"""Headline experiment: does working-set size become independent of world size?

Runs identical tasks under A (full context), B (RAG), C (tool calling) and
D (CVM) for worlds of 1e2 .. 1e6 objects and writes results/scale.json.

    python -m experiments.run_scale [--tasks 90] [--sizes 100,1000,...]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.experiment import FullContext, make_tasks, run_agent, run_cvm, run_rag  # noqa: E402
from cvm.processors import ReferenceReasoner  # noqa: E402
from cvm.resolver import GraphStore  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def summarize(runs: list[dict]) -> dict:
    def mean(k):
        xs = [r[k] for r in runs if k in r]
        return round(st.fmean(xs), 4) if xs else None

    def mx(k):
        xs = [r[k] for r in runs if k in r]
        return max(xs) if xs else None

    answers = sum(r.get("answers", 0) for r in runs)
    return {
        "n": len(runs),
        "accuracy": mean("correct"),
        "peak_resident_objects_mean": mean("peak_resident_objects"),
        "peak_resident_objects_max": mx("peak_resident_objects"),
        "peak_prompt_tokens_mean": mean("peak_prompt_tokens"),
        "peak_prompt_tokens_max": mx("peak_prompt_tokens"),
        "total_prompt_tokens_mean": mean("total_prompt_tokens"),
        "steps_mean": mean("steps"),
        "objects_materialized_mean": mean("objects_materialized"),
        "faults_mean": mean("faults"),
        "searches_mean": mean("searches"),
        "traversals_mean": mean("traversals"),
        "writes_mean": mean("writes"),
        "unsupported_claim_rate": (round(sum(r.get("unsupported_answers", 0) for r in runs)
                                         / answers, 4) if answers else 0.0),
        "external_io_mean": mean("external_io"),
        "latency_ms_mean": mean("latency_ms"),
        "cognitive_locality_mean": mean("cognitive_locality"),
        "fault_precision_mean": mean("fault_precision"),
        "thrash_rate_mean": mean("thrash_rate"),
        "virtualization_ratio_mean": mean("virtualization_ratio"),
        "infeasible": sum(r.get("infeasible", 0) for r in runs),
        "context_overflow": sum(r.get("context_overflow", 0) for r in runs),
        "step_limit": sum(r.get("step_limit", 0) for r in runs),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="100,1000,10000,100000,1000000")
    ap.add_argument("--tasks", type=int, default=90)
    ap.add_argument("--out", default=os.path.join(RESULTS, "scale.json"))
    args = ap.parse_args(argv)
    proc = ReferenceReasoner()
    report = {"tasks_per_size": args.tasks, "sizes": [], "runs": []}
    for n in [int(x) for x in args.sizes.split(",")]:
        t0 = time.time()
        w = build_world(n)
        store = GraphStore(w.path)
        tasks = make_tasks(store, args.tasks, seed=n)
        full = FullContext(store, w.n_objects)
        conds = {
            "A_full": lambda sp: full.run(sp, proc),
            "B_rag": lambda sp: run_rag(store, sp, proc, w.n_objects),
            "B2_graph_rag": lambda sp: run_rag(store, sp, proc, w.n_objects, expand_hops=3),
            "C_agent": lambda sp: run_agent(store, sp, proc, w.n_objects),
            "D_cvm": lambda sp: run_cvm(store, sp, proc, w.n_objects),
        }
        entry = {"target_size": n, "world_objects": w.n_objects, "world_relations": w.n_relations,
                 "clusters": w.n_clusters, "full_context_est_tokens": full.est_tokens,
                 "conditions": {}}
        for name, fn in conds.items():
            runs = [fn(sp) for sp in tasks]
            for r in runs:
                r.pop("answer", None)
            entry["conditions"][name] = summarize(runs)
            if name == "D_cvm":
                entry["cvm_by_depth"] = {
                    d: summarize([r for r in runs if r["depth"] == d]) for d in (1, 2, 3)}
                entry["cvm_by_kind"] = {
                    k: summarize([r for r in runs if r["kind"] == k])
                    for k in ("root_cause", "owner", "claim")}
            report["runs"] += [dict(r, world_objects=w.n_objects) for r in runs]
        entry["seconds"] = round(time.time() - t0, 1)
        report["sizes"].append(entry)
        c = entry["conditions"]
        print(f"N={w.n_objects:>8}  " + "  ".join(
            f"{k}: acc={v['accuracy']:.2f} peakTok={v['peak_prompt_tokens_mean']:.0f}"
            f" peakObj={v['peak_resident_objects_mean']:.1f}" for k, v in c.items()),
            flush=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
