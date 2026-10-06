"""Print one CVM run: the operation trace and the largest prompt the processor saw.

    python experiments/show_trace.py [--size 1000000] [--task 0] [--max-objects 32]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.context import CognitiveContext, incident_agent_capabilities  # noqa: E402
from cvm.experiment import make_tasks  # noqa: E402
from cvm.objects import approx_tokens  # noqa: E402
from cvm.processors import ReferenceReasoner  # noqa: E402
from cvm.resolver import GraphStore  # noqa: E402
from cvm.runtime import CVMRuntime  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402
from cvm.working_set import WorkingSet  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=1_000_000)
    ap.add_argument("--task", type=int, default=0)
    ap.add_argument("--max-objects", type=int, default=32)
    args = ap.parse_args()
    w = build_world(args.size)
    store = GraphStore(w.path)
    spec = make_tasks(store, args.task + 1, seed=7)[args.task]
    rt = CVMRuntime(store)
    ctx = CognitiveContext("agent://incident-debugger", spec.task, incident_agent_capabilities(),
                           WorkingSet(args.max_objects))
    proc = ReferenceReasoner()
    biggest = ("", 0)

    def spy(prompt):
        nonlocal biggest
        if approx_tokens(prompt) > biggest[1]:
            biggest = (prompt, approx_tokens(prompt))
        return proc.step(prompt)

    rt.run(ctx, spy)
    print(f"# world: {w.n_objects:,} objects, {w.n_relations:,} relations")
    print(f"# task: {spec.task.text}   expected: {spec.expected}   depth: {spec.depth}")
    print(f"# answer: {ctx.answer}   support: {', '.join(ctx.answer_support)}")
    print(f"# steps: {ctx.counters['steps']}   peak resident objects: "
          f"{ctx.working_set.peak_objects}   peak prompt tokens: {biggest[1]}\n")
    print("## operation trace")
    print("\n".join(ctx.trace))
    print(f"\n## largest prompt shown to the processor ({biggest[1]} tokens)\n")
    print(biggest[0])


if __name__ == "__main__":
    main()
