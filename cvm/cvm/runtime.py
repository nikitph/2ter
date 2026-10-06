"""CVM runtime: the processor loop, the cognitive instruction set, the verifier.

    while not done:
        prompt = build_resident_view(context)        # bounded
        action = processor.step(prompt)              # model sees ONLY this text
        dispatch(action)                             # runtime does the I/O

The processor is any callable mapping a prompt string to an action dict. It
has no other channel to the world: everything it knows came through a prompt
the runtime rendered from the context's resident state.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .context import CognitiveContext
from .objects import ObjectRef, approx_tokens, is_ref, namespace_of
from .resolver import GraphStore, L2Cache, MountTable, default_mounts

VERDICTS = ("SUPPORTED", "CONTRADICTED")

RULES = """RULES
  Reason freely over RESIDENT OBJECTS, HANDLES and NOTES.
  Do not assert external state that is not resident. If you need it, FAULT it.
  SEARCH discovers references; FAULT/READ materializes state for a known reference.
  Residency is managed by the runtime: objects may be evicted (LRU). Use WRITE to
  keep conclusions you will need later, citing their fact ids.
  ANSWER must cite the fact ids that support it; unsupported answers are rejected."""

OP_DOCS = {
    "READ": "READ(ref, field)                 materialize one field of an object",
    "TRAVERSE": "TRAVERSE(ref, relation, page=0)  follow relation (prefix ~ for inverse); returns handles",
    "SEARCH": "SEARCH(namespace, query)         lexical discovery; returns handles",
    "FAULT": "FAULT(ref, field?, reason)       make an object resident",
    "EVIDENCE": "EVIDENCE(ref)                    materialize a claim and its evidence links",
    "WRITE": "WRITE(entries={key: value}, ref?)  persist notes in scratch:// (value '' deletes)",
    "ANSWER": "ANSWER(value, support=[fact ids])",
}


class Processor(Protocol):
    def step(self, prompt: str) -> dict: ...


@dataclass
class RuntimeConfig:
    traverse_page: int = 16
    search_k: int = 8
    prefetch: bool = False
    agent_mode: bool = False      # condition C: unbounded, full objects incl. inverse edges
    max_steps: int = 80
    context_limit: int | None = None  # tokens; a prompt above this cannot be served


class CVMRuntime:
    def __init__(self, store: GraphStore, config: RuntimeConfig | None = None,
                 cache: L2Cache | None = None, mounts: MountTable | None = None):
        self.store = store
        self.config = config or RuntimeConfig()
        self.cache = cache or L2Cache()
        self.mounts = mounts or default_mounts(store, self.cache)

    # ------------------------------------------------------------------
    # prompt (the model-visible resident view)
    # ------------------------------------------------------------------
    def build_prompt(self, ctx: CognitiveContext) -> str:
        ws = ctx.working_set
        objs = ws.render_objects()
        lim_o = "inf" if ws.max_objects >= 10**9 else ws.max_objects
        lim_t = "inf" if ws.max_tokens >= 10**9 else ws.max_tokens
        parts = [
            f"CONTEXT {ctx.id}   PRINCIPAL {ctx.principal}",
            f"TASK {ctx.task.id} [{ctx.task.kind}]",
            f"  {ctx.task.text}",
            "",
            f"RESIDENT OBJECTS ({len(ws.objects)}/{lim_o} objects, "
            f"{ws.object_tokens()}/{lim_t} tokens)",
            objs or "  (none)",
            "",
            "HANDLES (references discovered by TRAVERSE / SEARCH / EVIDENCE)",
            ws.render_handles() or "  (none)",
            "",
            f"NOTES (scratch://{ctx.id[6:]}, {len(ctx.notes)}/{ctx.max_notes})",
            "\n".join(f"  {k} = {v}" for k, v in ctx.notes.items()) or "  (none)",
            "",
            "RECENT OPERATIONS",
        ]
        trace = ctx.trace if ctx.trace_window is None else ctx.trace[-ctx.trace_window:]
        parts.append("\n".join(f"  {t}" for t in trace) or "  (none)")
        parts += ["", "LAST RESULT", f"  {ctx.last_result or '(none)'}", "",
                  "AVAILABLE OPERATIONS"]
        parts += [f"  {OP_DOCS[o]}" for o in ctx.available_ops + ("ANSWER",)]
        parts += ["", RULES]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------
    def seed(self, ctx: CognitiveContext):
        for ref in ctx.task.seed_refs:
            self._materialize(ctx, ref, None, count=False)

    def run(self, ctx: CognitiveContext, processor: Processor | Callable[[str], dict],
            max_steps: int | None = None) -> CognitiveContext:
        if ctx.state == "READY":
            self.seed(ctx)
        ctx.state = "RUNNING"
        t0 = time.perf_counter()
        steps = max_steps or self.config.max_steps
        while ctx.state == "RUNNING" and ctx.counters["steps"] < steps:
            self.step(ctx, processor)
        if ctx.state == "RUNNING":
            ctx.state = "DONE"
            ctx.counters["step_limit"] += 1
        ctx.counters["latency_ms"] += int((time.perf_counter() - t0) * 1000)
        return ctx

    def step(self, ctx: CognitiveContext, processor) -> None:
        if ctx.state == "READY":
            self.seed(ctx)
            ctx.state = "RUNNING"
        prompt = self.build_prompt(ctx)
        toks = approx_tokens(prompt)
        ctx.prompt_tokens.append(toks)
        ctx.peak_resident_tokens = max(ctx.peak_resident_tokens, toks)
        if self.config.context_limit and toks > self.config.context_limit:
            ctx.counters["context_overflow"] += 1
            ctx.counters["steps"] += 1
            ctx.state = "DONE"
            ctx.last_result = "CONTEXT_OVERFLOW"
            return
        fn = processor.step if hasattr(processor, "step") else processor
        try:
            action = fn(prompt)
        except Exception as e:  # malformed model output is a fault, not a crash
            action = {"op": "INVALID", "error": str(e)}
        ctx.counters["steps"] += 1
        self.dispatch(ctx, action)

    def suspend(self, ctx: CognitiveContext):
        if ctx.state == "RUNNING":
            ctx.state = "SUSPENDED"

    def resume(self, ctx: CognitiveContext):
        if ctx.state == "SUSPENDED":
            ctx.state = "RUNNING"

    # ------------------------------------------------------------------
    def dispatch(self, ctx: CognitiveContext, a: dict) -> None:
        op = str(a.get("op", "")).upper()
        n = ctx.counters["steps"]
        if op != "ANSWER" and op not in ctx.available_ops:
            ctx.last_result = f"INVALID_OPERATION {op or a}"
            ctx.counters["invalid"] += 1
            ctx.trace.append(f"#{n} {op} -> INVALID_OPERATION")
            return
        handler = getattr(self, f"_op_{op.lower()}")
        try:
            result = handler(ctx, a)
        except KeyError as e:
            result = f"INVALID_ARGUMENTS missing {e}"
            ctx.counters["invalid"] += 1
        ctx.last_result = result
        ctx.trace.append(f"#{n} {self._describe(op, a)} -> {result.splitlines()[0][:160]}")

    @staticmethod
    def _describe(op, a):
        if op == "FAULT":
            return f"FAULT {a.get('ref')}{('.' + a['field']) if a.get('field') else ''}"
        if op == "READ":
            return f"READ {a.get('ref')}.{a.get('field')}"
        if op == "TRAVERSE":
            return f"TRAVERSE {a.get('ref')} {a.get('relation')}"
        if op == "SEARCH":
            return f"SEARCH {a.get('namespace')} '{a.get('query')}'"
        if op == "EVIDENCE":
            return f"EVIDENCE {a.get('ref')}"
        if op == "WRITE":
            return f"WRITE {', '.join(a.get('entries', {}))}"
        if op == "ANSWER":
            return f"ANSWER {a.get('value')}"
        return op

    def _capability_fault(self, ctx, op, ref):
        ctx.counters["capability_faults"] += 1
        return f"CAPABILITY_FAULT {op} {ref} not permitted in {ctx.id}"

    def _materialize(self, ctx: CognitiveContext, ref: ObjectRef, field: str | None,
                     op: str = "FAULT", count: bool = True) -> str:
        resolver = self.mounts.resolver_for(ref)
        if resolver is None:
            return f"NO_MOUNT for {namespace_of(ref)}"
        m = resolver.resolve(ctx, ref, op, field)
        if m is None:
            return f"NOT_FOUND {ref}"
        facts = [ctx.fact(ref, f, v, m.obj.version, m.source) for f, v in m.fields]
        inv_edges = None
        if self.config.agent_mode and not field:
            inv_edges = [(f"~{p}", s) for p, s in self.store.inverse_all(ref)]
        if ctx.materialized[ref] and not ctx.working_set.is_resident(ref) and ref in ctx.evicted_once:
            ctx.counters["rematerializations"] += 1
        if count:
            ctx.materialized[ref] += 1
            ctx.counters["materializations"] += 1
        evicted = ctx.working_set.materialize(ref, m.obj.type, m.obj.label, facts,
                                              m.obj.inverse_counts, inv_edges)
        ctx.evicted_once.update(evicted)
        if self.config.prefetch:
            self._prefetch(resolver.prefetch_hints(m.obj))
        ids = [f.id for f in facts]
        span = f"{ids[0]}..{ids[-1]}" if ids else "no facts"
        ev = f"; evicted {', '.join(evicted)}" if evicted else ""
        return f"ok {ref} resident: {len(facts)} facts ({span}){ev}"

    def _prefetch(self, refs):
        """Warm L2 with likely next dereferences. Never touches the working set."""
        for h in refs:
            r2 = self.mounts.resolver_for(h)
            if r2 is not None:
                r2.fetch(h, demand=False)

    def _op_fault(self, ctx, a):
        ref = a["ref"]
        ctx.counters["faults"] += 1
        if not ctx.can("FAULT", ref) and not ctx.can("READ", ref):
            return self._capability_fault(ctx, "FAULT", ref)
        ctx.fault_log = getattr(ctx, "fault_log", [])
        ctx.fault_log.append((ref, a.get("reason", "")))
        return self._materialize(ctx, ref, a.get("field") or None, "FAULT")

    def _op_read(self, ctx, a):
        ref = a["ref"]
        ctx.counters["reads"] += 1
        if not ctx.can("READ", ref):
            return self._capability_fault(ctx, "READ", ref)
        return self._materialize(ctx, ref, a["field"], "READ")

    def _op_traverse(self, ctx, a):
        ref, rel = a["ref"], a["relation"]
        page = int(a.get("page") or 0)
        ctx.counters["traversals"] += 1
        if not ctx.can("TRAVERSE", ref):
            return self._capability_fault(ctx, "TRAVERSE", ref)
        size = self.config.traverse_page
        if rel.startswith("~"):
            refs = self.store.inverse(ref, rel[1:], size + 1, page * size)
        else:
            refs = self.store.traverse(ref, rel, size + 1, page * size)
        more = len(refs) > size
        refs = refs[:size]
        facts = [ctx.fact(ref, rel, r, 1, "GraphTraversal") for r in refs]
        for f in facts:
            ctx.working_set.add_handles([f.value], f"{f.id} {ref} {rel}")
        if self.config.agent_mode:  # conventional tools return whole related objects
            for r in refs:
                self._materialize(ctx, r, None, "TRAVERSE")
        elif self.config.prefetch:  # e.g. DEPENDS_ON -> services: their metrics are next
            for r in refs:
                res = self.mounts.resolver_for(r)
                o = res.fetch(r, demand=False) if res else None
                if o is not None:
                    self._prefetch(res.prefetch_hints(o))
        tail = f" (more: page={page + 1})" if more else ""
        listing = ", ".join(f"{f.value} [{f.id}]" for f in facts)
        return f"ok {len(refs)} refs: {listing}{tail}" if refs else "ok 0 refs"

    def _op_search(self, ctx, a):
        ns, q = a["namespace"], a["query"]
        ctx.counters["searches"] += 1
        if not ctx.can("SEARCH", ns):
            return self._capability_fault(ctx, "SEARCH", ns)
        refs = self.store.search(ns, q, self.config.search_k)
        ctx.working_set.add_handles(refs, f"SEARCH {ns} '{q}'")
        if self.config.agent_mode:  # conventional search returns documents, not handles
            for r in refs:
                self._materialize(ctx, r, None, "SEARCH")
        return f"ok {len(refs)} refs: {', '.join(refs)}" if refs else "ok 0 refs"

    def _op_evidence(self, ctx, a):
        ref = a["ref"]
        ctx.counters["evidence"] += 1
        if not ctx.can("EVIDENCE", ref):
            return self._capability_fault(ctx, "EVIDENCE", ref)
        res = self._materialize(ctx, ref, None, "EVIDENCE")
        ro = ctx.working_set.objects.get(ref)
        links = [f.value for f in ro.facts.values()
                 if f.field in ("ABOUT", "SUPPORTED_BY", "CONTRADICTED_BY")] if ro else []
        ctx.working_set.add_handles(links, f"EVIDENCE {ref}")
        return f"{res}; evidence links: {', '.join(links) or 'none'}"

    def _op_write(self, ctx, a):
        """WRITE targets the context's scratch:// space unless ``ref`` names another object."""
        ctx.counters["writes"] += 1
        target = a.get("ref") or f"scratch://{ctx.id[6:]}"
        if not ctx.can("WRITE", target):
            return self._capability_fault(ctx, "WRITE", target)
        if not target.startswith("scratch://"):
            return f"READ_ONLY_MOUNT {namespace_of(target)} (V0 resolvers do not accept writes)"
        return ctx.write_notes(dict(a["entries"]))

    def _op_answer(self, ctx, a):
        value = a.get("value")
        support = [str(s) for s in (a.get("support") or [])]
        ctx.counters["answers"] += 1
        ok, why = self.verify(ctx, value, support)
        if not ok:
            ctx.counters["unsupported_answers"] += 1
            return f"VERIFIER_REJECT {why}"
        ctx.answer, ctx.answer_support = value, support
        ctx.state = "DONE"
        return "ACCEPTED"

    # ------------------------------------------------------------------
    # provenance verifier
    # ------------------------------------------------------------------
    def verify(self, ctx: CognitiveContext, value: Any, support: list[str]) -> tuple[bool, str]:
        if value in (None, "", "UNKNOWN"):
            return True, "abstain"
        if not support:
            return False, "answer cites no facts"
        unknown = [s for s in support if s not in ctx.facts_by_id]
        if unknown:
            return False, f"cited facts never materialized in {ctx.id}: {unknown[:5]}"
        cited = [ctx.facts_by_id[s] for s in support]
        if is_ref(value):
            if not any(f.ref == value or f.value == value for f in cited):
                return False, f"{value} does not appear in any cited fact"
        elif value in VERDICTS:
            if not any(f.ref == ctx.task.target for f in cited):
                return False, f"verdict cites no fact about {ctx.task.target}"
        else:
            return False, f"answer {value!r} is not a reference or verdict"
        return True, "ok"
