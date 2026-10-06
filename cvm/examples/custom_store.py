"""Plug your own data into CVM.

The runtime talks to a *store* through five methods (get, traverse, inverse,
inverse_all, search) plus an ``io`` counter, and to *resolvers* through a mount
table keyed by namespace. Implement the store over anything you have: a
database, an API, a code index. This example uses an in-memory dict.

    python examples/custom_store.py                  # prints the resident view the model sees
    DEEPSEEK_API_KEY=... python examples/custom_store.py --llm deepseek
    ANTHROPIC_API_KEY=... python examples/custom_store.py --llm claude
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.context import Capability, CognitiveContext, Task  # noqa: E402
from cvm.objects import CVMObject, Relation  # noqa: E402
from cvm.resolver import L2Cache, MountTable, NamespaceMount, Resolver  # noqa: E402
from cvm.runtime import CVMRuntime, RuntimeConfig  # noqa: E402
from cvm.working_set import WorkingSet  # noqa: E402


class DictStore:
    """Minimal store: objects in a dict, relations derived from them."""

    def __init__(self, objects: list[CVMObject]):
        self.objects = {o.ref: o for o in objects}
        self.io = 0  # count backend touches (CVM reports this as external I/O)

    def get(self, ref):
        self.io += 1
        o = self.objects.get(ref)
        if o is None:
            return None
        inv = {}
        for other in self.objects.values():
            for r in other.relations:
                if r.target == ref:
                    inv[f"~{r.predicate}"] = inv.get(f"~{r.predicate}", 0) + 1
        o.inverse_counts = inv
        return o

    def traverse(self, ref, pred, limit, offset=0):
        self.io += 1
        o = self.objects.get(ref)
        hits = [r.target for r in (o.relations if o else []) if r.predicate == pred]
        return hits[offset:offset + limit]

    def inverse(self, ref, pred, limit, offset=0):
        self.io += 1
        hits = sorted(o.ref for o in self.objects.values()
                      if any(r.predicate == pred and r.target == ref for r in o.relations))
        return hits[offset:offset + limit]

    def inverse_all(self, ref):
        return [(r.predicate, o.ref) for o in self.objects.values()
                for r in o.relations if r.target == ref]

    def search(self, namespace, query, k):
        self.io += 1
        words = [w for w in query.lower().split() if len(w) > 2]
        scored = []
        for o in self.objects.values():
            if namespace and not o.ref.startswith(namespace):
                continue
            text = f"{o.ref} {o.label} {o.attributes}".lower()
            score = sum(w in text for w in words)
            if score:
                scored.append((-score, o.ref))
        return [r for _, r in sorted(scored)[:k]]


def demo_world() -> list[CVMObject]:
    O, R = CVMObject, Relation
    return [
        O("repo://shop", "repo", "shop monorepo", {"default_branch": "main"},
          [R("CONTAINS", "file://shop/cart.py"), R("CONTAINS", "file://shop/tax.py")]),
        O("file://shop/cart.py", "file", "cart.py", {"lines": 412},
          [R("IMPORTS", "file://shop/tax.py"), R("OWNED_BY", "team://checkout")]),
        O("file://shop/tax.py", "file", "tax.py", {"lines": 96},
          [R("OWNED_BY", "team://payments"), R("CHANGED_IN", "commit://a8f92d")]),
        O("commit://a8f92d", "commit", "round tax half-even",
          {"author": "alice", "at": "2026-09-30T10:12Z",
           "message": "switch tax rounding to half-even"}, []),
        O("team://payments", "team", "payments", {"oncall": "alice"}, []),
        O("team://checkout", "team", "checkout", {"oncall": "bob"}, []),
        O("bug://771", "bug", "cart totals off by one cent",
          {"opened": "2026-09-30T14:00Z", "status": "open"},
          [R("REPORTED_IN", "file://shop/cart.py")]),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["deepseek", "claude"], default=None)
    args = ap.parse_args()

    store = DictStore(demo_world())
    cache = L2Cache()
    generic = Resolver(store, cache)  # a resolver per namespace; one generic one is fine
    mounts = MountTable([NamespaceMount(ns, generic) for ns in
                         ("repo://", "file://", "commit://", "team://", "bug://")])
    rt = CVMRuntime(store, RuntimeConfig(max_steps=25), cache=cache, mounts=mounts)

    task = Task("task://1", "investigate",
                "Which commit most likely caused bug://771, and which team should own the fix?",
                "bug://771", seed_refs=["bug://771"])
    caps = [Capability(ns + "*", ("READ", "TRAVERSE", "FAULT"))
            for ns in ("repo://", "file://", "commit://", "team://", "bug://")]
    caps += [Capability("commit://*", ("SEARCH",)), Capability("scratch://*", ("WRITE",))]
    ctx = CognitiveContext("agent://debugger", task, caps, WorkingSet(max_objects=8),
                           available_ops=("READ", "TRAVERSE", "SEARCH", "FAULT", "WRITE"))

    if args.llm is None:
        rt.seed(ctx)
        print(rt.build_prompt(ctx))
        print("\n(add --llm deepseek or --llm claude to let a model work this context)")
        return
    if args.llm == "deepseek":
        from cvm.processors import ChatCompletionsProcessor
        proc = ChatCompletionsProcessor(model="deepseek-flash")
    else:
        from cvm.processors import ClaudeProcessor
        proc = ClaudeProcessor()
    rt.run(ctx, proc)
    print("\n".join(ctx.trace))
    print("\nANSWER:", ctx.answer, "support:", ctx.answer_support)


if __name__ == "__main__":
    main()
