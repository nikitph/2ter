"""Experiment harness: tasks, the four architectures, metrics.

A  full     serialize the whole world into the prompt, answer in one shot
B  rag      retrieve top-k objects lexically for the question, answer in one shot
C  agent    conventional tool calling: same ops, but every result stays in the
            transcript and objects come back whole (incl. inverse edges)
D  cvm      bounded working set (LRU), stable refs, explicit faults, notes,
            provenance verifier
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from .context import CognitiveContext, Task, code_agent_capabilities, incident_agent_capabilities
from .objects import approx_tokens
from .resolver import GraphStore, L2Cache
from .runtime import CVMRuntime, RuntimeConfig
from .working_set import WorkingSet

INF = 10**9
CONTEXT_LIMIT = 1_000_000  # tokens; generous (current 1M-context models)


@dataclass
class TaskSpec:
    task: Task
    expected: str
    useful: set
    depth: int


def make_tasks(store: GraphStore, n: int, seed: int = 0,
               domain: str = "incident") -> list[TaskSpec]:
    if domain not in ("incident", "code"):
        raise ValueError(f"unknown task domain: {domain}")
    truth = store.truth()
    rng = random.Random(seed)
    picks = [truth[rng.randrange(len(truth))] for _ in range(n)]
    out = []
    for i, t in enumerate(picks):
        if domain == "code":
            bug = t["bug"]
            task = Task(f"task://{i}", "code_cause",
                        f"Which commit caused {bug}? Trace its failing test through the file "
                        "import chain and compare commits with the first failure time.",
                        bug, [bug])
            out.append(TaskSpec(task, t["cause"], set(t["useful"]), t["depth"]))
            continue
        kind = ("root_cause", "owner", "claim")[i % 3]
        inc = t["incident"]
        useful = set(t["useful"])
        if kind == "root_cause":
            task = Task(f"task://{i}", kind,
                        f"Determine which change or deployment caused {inc}.", inc, [inc])
            exp = t["cause"]
        elif kind == "owner":
            task = Task(f"task://{i}", kind,
                        f"Which team owns the service where {inc} originated (its root-cause service)?",
                        inc, [inc])
            exp = t["owner"]
        else:
            truthful = rng.random() < 0.5
            claim = t["claim_true"] if truthful else t["claim_false"]
            task = Task(f"task://{i}", kind,
                        f"Is {claim} supported by the evidence? Answer SUPPORTED or CONTRADICTED.",
                        claim, [])
            exp = "SUPPORTED" if truthful else "CONTRADICTED"
        out.append(TaskSpec(task, exp, useful, t["depth"]))
    return out


def _metrics(ctx: CognitiveContext, spec: TaskSpec, world_size: int, cond: str,
             io: int, extra: dict | None = None) -> dict:
    mat = set(ctx.materialized)
    useful_mat = mat & spec.useful
    faults = getattr(ctx, "fault_log", [])
    fault_refs = [r for r, _ in faults]
    peak_obj = ctx.working_set.peak_objects
    m = {
        "condition": cond,
        "world_size": world_size,
        "task": spec.task.id,
        "kind": spec.task.kind,
        "depth": spec.depth,
        "correct": int(ctx.answer == spec.expected),
        "answer": ctx.answer,
        "expected": spec.expected,
        "steps": ctx.counters["steps"],
        "peak_resident_objects": peak_obj,
        "peak_prompt_tokens": ctx.peak_resident_tokens,
        "total_prompt_tokens": sum(ctx.prompt_tokens),
        "objects_materialized": len(mat),
        "materializations": ctx.counters["materializations"],
        "faults": ctx.counters["faults"] + ctx.counters["evidence"],
        "searches": ctx.counters["searches"],
        "traversals": ctx.counters["traversals"],
        "writes": ctx.counters["writes"],
        "answers": ctx.counters["answers"],
        "unsupported_answers": ctx.counters["unsupported_answers"],
        "capability_faults": ctx.counters["capability_faults"],
        "external_io": io,
        "latency_ms": ctx.counters["latency_ms"],
        "cognitive_locality": len(useful_mat) / len(mat) if mat else 0.0,
        "fault_precision": (sum(r in spec.useful for r in fault_refs) / len(fault_refs)
                            if fault_refs else 0.0),
        "thrash_rate": (ctx.counters["rematerializations"] / ctx.counters["materializations"]
                        if ctx.counters["materializations"] else 0.0),
        "evictions": ctx.working_set.evictions,
        "step_limit": ctx.counters["step_limit"],
        "context_overflow": ctx.counters["context_overflow"],
        "invalid_ops": ctx.counters["invalid"],
        "aborted": ctx.counters["aborted"],
        "virtualization_ratio": world_size / max(1, peak_obj),
    }
    if extra:
        m.update(extra)
    return m


# ----------------------------------------------------------------------
def run_cvm(store, spec: TaskSpec, processor, world_size: int, max_objects=32,
            max_tokens=16_000, prefetch=False, cache: L2Cache | None = None,
            search=True, write=True, cond="D_cvm", max_steps: int = 80,
            keep_ctx: list | None = None) -> dict:
    rt = CVMRuntime(store, RuntimeConfig(prefetch=prefetch, max_steps=max_steps),
                    cache=cache or L2Cache())
    ops = ("READ", "TRAVERSE", "SEARCH", "FAULT", "EVIDENCE") + (("WRITE",) if write else ())
    ctx = CognitiveContext("agent://incident-debugger", spec.task,
                           (code_agent_capabilities(search=search, write=write)
                            if spec.task.kind == "code_cause" else
                            incident_agent_capabilities(search=search, write=write,
                                                        claims=spec.task.kind == "claim")),
                           WorkingSet(max_objects, max_tokens), available_ops=ops)
    io0 = store.io
    rt.run(ctx, processor)
    if keep_ctx is not None:
        keep_ctx.append(ctx)
    return _metrics(ctx, spec, world_size, cond, store.io - io0)


def run_agent(store, spec: TaskSpec, processor, world_size: int,
              context_limit: int = CONTEXT_LIMIT, max_steps: int = 80,
              keep_ctx: list | None = None) -> dict:
    rt = CVMRuntime(store, RuntimeConfig(agent_mode=True, context_limit=context_limit,
                                         max_steps=max_steps),
                    cache=L2Cache())
    ctx = CognitiveContext("agent://tool-caller", spec.task,
                           (code_agent_capabilities(write=False)
                            if spec.task.kind == "code_cause" else
                            incident_agent_capabilities(write=False,
                                                        claims=spec.task.kind == "claim")),
                           WorkingSet(INF, INF, max_handles=INF, full_render=True),
                           available_ops=("READ", "TRAVERSE", "SEARCH", "FAULT", "EVIDENCE"),
                           trace_window=None)
    io0 = store.io
    rt.run(ctx, processor)
    if keep_ctx is not None:
        keep_ctx.append(ctx)
    return _metrics(ctx, spec, world_size, "C_agent", store.io - io0)


def run_rag(store, spec: TaskSpec, processor, world_size: int, k: int = 24,
            expand_hops: int = 0, budget: int = 64) -> dict:
    """One-shot retrieval. With ``expand_hops`` > 0 this is graph-RAG: seeds are
    expanded breadth-first along outgoing relations up to ``budget`` objects."""
    rt = CVMRuntime(store, RuntimeConfig(), cache=L2Cache())
    ctx = CognitiveContext("agent://rag", spec.task, incident_agent_capabilities(),
                           WorkingSet(INF, INF, max_handles=INF), available_ops=())
    io0 = store.io
    t0 = time.perf_counter()
    frontier = list(dict.fromkeys(store.search("", spec.task.text, k)))
    seen = set()
    for hop in range(expand_hops + 1):
        nxt = []
        for ref in frontier:
            if ref in seen or len(seen) >= budget:
                continue
            seen.add(ref)
            rt._materialize(ctx, ref, None)
            ro = ctx.working_set.objects.get(ref)
            if ro:
                nxt += [f.value for f in ro.facts.values()
                        if f.field.isupper() and f.field not in ("AUTHORED_BY", "RUNS_ON")]
        frontier = nxt
    rt.run(ctx, processor, max_steps=1)
    ctx.counters["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    cond = "B_rag" if not expand_hops else "B2_graph_rag"
    return _metrics(ctx, spec, world_size, cond, store.io - io0)


class FullContext:
    """Condition A. Materializes the entire world into one context (if it fits)."""

    def __init__(self, store: GraphStore, world_size: int, sample: int = 2000,
                 context_limit: int = CONTEXT_LIMIT):
        self.store = store
        self.world_size = world_size
        self.rt = CVMRuntime(store, RuntimeConfig(), cache=L2Cache(enabled=False))
        self.ctx = None
        # estimate serialized size from a sample before deciding to build
        refs = list(store.iter_objects()) if world_size <= 200_000 else None
        if refs is None:
            import sqlite3
            db = sqlite3.connect(store.path)
            try:
                refs_sample = [r for (r,) in db.execute(
                    "SELECT ref FROM objects ORDER BY random() LIMIT ?", (sample,))]
            finally:
                db.close()
        else:
            refs_sample = random.Random(0).sample(refs, min(sample, len(refs)))
        probe = CognitiveContext("probe", Task("t", "x", "", ""), incident_agent_capabilities(),
                                 WorkingSet(INF, INF))
        for r in refs_sample:
            self.rt._materialize(probe, r, None)
        per = probe.working_set.object_tokens() / max(1, len(refs_sample))
        self.est_tokens = int(per * world_size)
        self.feasible = self.est_tokens <= context_limit
        if self.feasible:
            if refs is None:
                refs = store.iter_objects()
            self.ctx = CognitiveContext("agent://full-context", Task("t", "x", "", ""),
                                        incident_agent_capabilities(),
                                        WorkingSet(INF, INF, max_handles=INF), available_ops=())
            for r in refs:
                self.rt._materialize(self.ctx, r, None)
            self.base_prompt_tokens = approx_tokens(self.rt.build_prompt(self.ctx))
            if self.base_prompt_tokens > context_limit:
                self.feasible = False
                self.est_tokens = self.base_prompt_tokens
                self.ctx = None

    def run(self, spec: TaskSpec, processor) -> dict:
        if not self.feasible:
            return {"condition": "A_full", "world_size": self.world_size, "task": spec.task.id,
                    "kind": spec.task.kind, "depth": spec.depth, "correct": 0,
                    "answer": None, "expected": spec.expected, "infeasible": 1,
                    "peak_prompt_tokens": self.est_tokens, "total_prompt_tokens": self.est_tokens,
                    "peak_resident_objects": self.world_size, "steps": 0,
                    "unsupported_answers": 0, "answers": 0}
        ctx = self.ctx
        ctx.task, ctx.state, ctx.answer = spec.task, "RUNNING", None
        ctx.answer_support = []
        ctx.counters.clear(); ctx.prompt_tokens.clear(); ctx.trace.clear()
        ctx.last_result, ctx.peak_resident_tokens = "", 0
        rt = self.rt
        orig = rt.build_prompt
        rt.build_prompt = lambda c: "WORLD: closed (all objects resident)\n" + orig(c)
        try:
            rt.run(ctx, processor, max_steps=1)
        finally:
            rt.build_prompt = orig
        m = _metrics(ctx, spec, self.world_size, "A_full", 0)
        m["peak_resident_objects"] = len(ctx.working_set.objects)
        m["objects_materialized"] = len(ctx.working_set.objects)
        m["infeasible"] = 0
        return m
