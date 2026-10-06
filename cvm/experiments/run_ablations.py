"""Ablations on a fixed large world (default 1e6 objects).

1. working-set size sweep, with and without model-writable notes (thrashing)
2. L2 cache and prefetching (external I/O, demand misses)
3. epistemic invariant: hallucinating processor vs. provenance verifier
4. capabilities: SEARCH revoked; escalation attempts; child-context subsetting
5. context switching: N contexts interleaved one step at a time vs. sequential

    python -m experiments.run_ablations [--size 1000000] [--tasks 60]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.context import Capability, CognitiveContext, Task, incident_agent_capabilities  # noqa: E402
from cvm.experiment import make_tasks, run_cvm  # noqa: E402
from cvm.processors import Hallucinator, ReferenceReasoner  # noqa: E402
from cvm.resolver import GraphStore, L2Cache  # noqa: E402
from cvm.runtime import CVMRuntime, RuntimeConfig  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402
from cvm.working_set import WorkingSet  # noqa: E402

from experiments.run_scale import RESULTS, summarize  # noqa: E402

KEEP = ("accuracy", "peak_resident_objects_mean", "peak_prompt_tokens_mean",
        "total_prompt_tokens_mean", "steps_mean", "faults_mean", "thrash_rate_mean",
        "fault_precision_mean", "cognitive_locality_mean", "unsupported_claim_rate",
        "external_io_mean", "step_limit")


def slim(s):
    return {k: s[k] for k in KEEP}


def ws_sweep(store, tasks, n):
    out = []
    for notes in (True, False):
        for k in (2, 3, 4, 6, 8, 16, 32):
            runs = [run_cvm(store, sp, ReferenceReasoner(), n, max_objects=k, write=notes)
                    for sp in tasks]
            s = slim(summarize(runs))
            s.update(max_objects=k, notes=notes)
            out.append(s)
            print(f"  ws={k:>2} notes={notes!s:<5} acc={s['accuracy']:.2f} "
                  f"thrash={s['thrash_rate_mean']:.2f} steps={s['steps_mean']:.1f}", flush=True)
    return out


def cache_prefetch(store, tasks, n):
    """External I/O under different L2 configurations.

    ``per_task`` caches live for one context; ``shared`` is one runtime-wide L2
    across all tasks. The thrashing configuration (4 resident objects, no
    notes) shows the cache absorbing re-materializations.
    """
    out = {}
    configs = (("no_cache", "off", False, 32, True), ("l2_per_task", "task", False, 32, True),
               ("l2_shared", "shared", False, 32, True),
               ("l2_shared+prefetch", "shared", True, 32, True),
               ("thrashing_no_cache", "off", False, 4, False),
               ("thrashing_l2_shared", "shared", False, 4, False))
    for name, mode, prefetch, ws, notes in configs:
        shared = L2Cache(enabled=True)
        io = misses = hits = pf = acc = 0
        for sp in tasks:
            cache = shared if mode == "shared" else L2Cache(enabled=(mode == "task"))
            h0, m0, p0 = cache.hits, cache.misses, cache.prefetches
            r = run_cvm(store, sp, ReferenceReasoner(), n, cache=cache, prefetch=prefetch,
                        max_objects=ws, write=notes)
            io += r["external_io"]
            misses += cache.misses - m0
            hits += cache.hits - h0
            pf += cache.prefetches - p0
            acc += r["correct"]
        k = len(tasks)
        out[name] = {"accuracy": round(acc / k, 3), "external_io_per_task": round(io / k, 2),
                     "demand_misses_per_task": round(misses / k, 2),
                     "demand_hits_per_task": round(hits / k, 2),
                     "prefetches_per_task": round(pf / k, 2)}
        print(f"  {name:<22} {out[name]}", flush=True)
    return out


def verifier(store, tasks, n):
    out = {}
    for name, proc in (("reference", ReferenceReasoner()),
                       ("hallucinator_fabricated_ids", Hallucinator(True)),
                       ("hallucinator_no_citations", Hallucinator(False))):
        runs = [run_cvm(store, sp, proc, n) for sp in tasks]
        s = summarize(runs)
        answers = sum(r["answers"] for r in runs)
        rejected = sum(r["unsupported_answers"] for r in runs)
        accepted_wrong = sum(1 for r in runs if r["correct"] == 0 and r["step_limit"] == 0
                             and r["unsupported_answers"] < r["answers"])
        out[name] = {"accuracy": s["accuracy"], "answers_emitted": answers,
                     "answers_rejected_by_verifier": rejected,
                     "unsupported_claim_rate_emitted": round(rejected / answers, 4) if answers else 0,
                     "unsupported_claims_accepted": 0 if name == "reference" else
                     answers - rejected,
                     "accepted_but_wrong": accepted_wrong}
        print(f"  {name:<28} {out[name]}", flush=True)
    return out


ESCALATION_ATTEMPTS = [
    {"op": "WRITE", "ref": "service://payments-k1", "entries": {"status": "healthy"}},
    {"op": "SEARCH", "namespace": "person://", "query": "oncall"},
    {"op": "FAULT", "ref": "secret://prod-db-password", "reason": "curious"},
]


def capabilities(store, tasks, n):
    out = {}
    runs = [run_cvm(store, sp, ReferenceReasoner(), n, search=False) for sp in tasks]
    s = summarize(runs)
    out["search_revoked"] = {"accuracy": s["accuracy"], "searches_mean": s["searches_mean"],
                             "capability_faults_mean": sum(r["capability_faults"] for r in runs) / len(runs),
                             "traversals_mean": s["traversals_mean"]}
    print("  search revoked:", out["search_revoked"], flush=True)

    # escalation: WRITE outside scratch is denied by policy, not by prompt
    rt = CVMRuntime(store)
    ctx = CognitiveContext("agent://escalator", tasks[0].task, incident_agent_capabilities(),
                           WorkingSet())
    ctx.notes["x"] = "y"
    results = []
    for a in ESCALATION_ATTEMPTS:
        rt.dispatch(ctx, a)
        results.append(ctx.last_result.split(" ")[0])
    out["escalation_attempts"] = results

    # child contexts receive a subset of capabilities only
    parent = CognitiveContext("agent://parent", tasks[0].task,
                              [Capability("service://*", ("READ", "TRAVERSE", "FAULT")),
                               Capability("metrics://*", ("READ", "FAULT"))], WorkingSet())
    child = parent.spawn(Task("task://child", "root_cause", "Investigate capacity.", ""),
                         [Capability("service://*", ("READ",)),
                          Capability("change://*", ("SEARCH",)),       # parent lacks it
                          Capability("metrics://*", ("READ", "WRITE"))])  # WRITE not held
    out["child_capabilities"] = [f"{c.namespace}:{'/'.join(c.operations)}" for c in child.capabilities]
    out["child_can_search_change"] = child.can("SEARCH", "change://")
    print("  escalation:", results, " child caps:", out["child_capabilities"], flush=True)
    return out


def context_switching(store, tasks, n):
    proc = ReferenceReasoner()
    seq = [run_cvm(store, sp, proc, n) for sp in tasks]
    rt = CVMRuntime(store, RuntimeConfig())
    ctxs = [CognitiveContext("agent://incident-debugger", sp.task,
                             incident_agent_capabilities(), WorkingSet()) for sp in tasks]
    io0 = store.io
    switches = 0
    live = list(ctxs)
    while live:
        for c in list(live):
            rt.resume(c)
            rt.step(c, proc)
            if c.state == "DONE" or c.counters["steps"] >= rt.config.max_steps:
                live.remove(c)
            else:
                rt.suspend(c)
                switches += 1
    inter_io = store.io - io0
    same = sum(c.answer == s["expected"] for c, s in zip(ctxs, seq))
    out = {"contexts": len(ctxs), "context_switches": switches,
           "interleaved_accuracy": same / len(ctxs),
           "sequential_accuracy": sum(s["correct"] for s in seq) / len(seq),
           "identical_step_counts": all(c.counters["steps"] == s["steps"] for c, s in zip(ctxs, seq)),
           "rematerializations_after_resume": sum(c.counters["rematerializations"] for c in ctxs),
           "external_io_interleaved": inter_io,
           "external_io_sequential": sum(s["external_io"] for s in seq)}
    print("  context switching:", out, flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=1_000_000)
    ap.add_argument("--tasks", type=int, default=60)
    args = ap.parse_args(argv)
    w = build_world(args.size)
    store = GraphStore(w.path)
    tasks = make_tasks(store, args.tasks, seed=12345)
    n = w.n_objects
    report = {"world_objects": n, "tasks": args.tasks}
    print("working-set sweep"); report["ws_sweep"] = ws_sweep(store, tasks, n)
    print("cache/prefetch"); report["cache_prefetch"] = cache_prefetch(store, tasks, n)
    print("verifier"); report["verifier"] = verifier(store, tasks, n)
    print("capabilities"); report["capabilities"] = capabilities(store, tasks, n)
    print("context switching"); report["context_switching"] = context_switching(store, tasks[:24], n)
    out = os.path.join(RESULTS, "ablations.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
