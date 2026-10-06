"""Held-out V1 evaluation cells and reference sanity runner.

    python3 experiments/v1_splits.py --tasks 100 --out results/v1_reference_splits.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.experiment import make_tasks, run_cvm  # noqa: E402
from cvm.processors import CodeReferenceReasoner, ReferenceReasoner  # noqa: E402
from cvm.resolver import GraphStore  # noqa: E402
from cvm.synthetic_code_world import build_code_world  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402


@dataclass(frozen=True)
class SplitCell:
    split: str
    size: int
    seed: int
    domain: str = "incident"
    depth_range: tuple[int, int] = (1, 3)
    traps: bool = False
    max_objects: int = 32


SPLITS: dict[str, tuple[SplitCell, ...]] = {
    "iid": (SplitCell("iid", 1000, 3000), SplitCell("iid", 1_000_000, 3000)),
    "scale": (SplitCell("scale", 1_000_000, 3001),),
    "deep": (SplitCell("deep", 1000, 3002, depth_range=(4, 5)),),
    "traps": (SplitCell("traps", 1000, 3003, traps=True),),
    "tight": (SplitCell("tight", 1_000_000, 3004, max_objects=4),),
    "domain2": (SplitCell("domain2", 1000, 4000, domain="code"),),
}


def cells_for(split: str) -> tuple[SplitCell, ...]:
    if split == "all":
        return tuple(cell for cells in SPLITS.values() for cell in cells)
    if split not in SPLITS:
        raise ValueError(f"unknown V1 split: {split}")
    return SPLITS[split]


def build_cell(cell: SplitCell, tasks: int):
    if tasks < 1:
        raise ValueError("tasks must be positive")
    if cell.domain == "code":
        world = build_code_world(cell.size, seed=cell.seed)
    else:
        world = build_world(cell.size, seed=cell.seed,
                            depth_range=cell.depth_range, traps=cell.traps)
    store = GraphStore(world.path)
    specs = make_tasks(store, tasks, seed=cell.seed * 100 + cell.size,
                       domain=cell.domain)
    return world, store, specs


def reference_for(cell: SplitCell):
    return CodeReferenceReasoner() if cell.domain == "code" else ReferenceReasoner()


def run_reference(split: str = "all", tasks: int = 100) -> list[dict]:
    rows = []
    for cell in cells_for(split):
        world, store, specs = build_cell(cell, tasks)
        try:
            runs = [run_cvm(store, spec, reference_for(cell), world.n_objects,
                            max_objects=cell.max_objects, max_steps=90) for spec in specs]
        finally:
            store.db.close()
        row = asdict(cell)
        row.update({"world_objects": world.n_objects, "tasks": len(runs),
                    "correct": sum(r["correct"] for r in runs),
                    "step_limits": sum(r["step_limit"] for r in runs),
                    "peak_objects_max": max(r["peak_resident_objects"] for r in runs),
                    "mean_steps": sum(r["steps"] for r in runs) / len(runs)})
        rows.append(row)
        print(f"{cell.split:<7} n={world.n_objects:<8} ws={cell.max_objects:<2} "
              f"correct={row['correct']}/{row['tasks']} limits={row['step_limits']}", flush=True)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["all", *SPLITS], default="all")
    ap.add_argument("--tasks", type=int, default=100)
    ap.add_argument("--out", type=Path, default=Path("results/v1_reference_splits.json"))
    args = ap.parse_args(argv)
    rows = run_reference(args.split, args.tasks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2) + "\n")
    if any(row["correct"] != row["tasks"] or row["step_limits"] for row in rows):
        raise SystemExit("reference sanity failed")


if __name__ == "__main__":
    main()
