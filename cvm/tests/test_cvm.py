import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.context import Capability, CognitiveContext, Task, incident_agent_capabilities  # noqa: E402
from cvm.experiment import FullContext, make_tasks, run_agent, run_cvm  # noqa: E402
from cvm.objects import Fact  # noqa: E402
from cvm.processors import (Hallucinator, ReferenceReasoner, normalize_action,  # noqa: E402
                            parse_prompt)
from cvm.resolver import GraphStore  # noqa: E402
from cvm.runtime import CVMRuntime  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402
from cvm.working_set import WorkingSet  # noqa: E402

TMP = tempfile.mkdtemp(prefix="cvm-test-")
WORLD = build_world(600, seed=3, cache_dir=TMP)
STORE = GraphStore(WORLD.path)
TASKS = make_tasks(STORE, 30, seed=1)


def fact(i, ref="service://a", field="status", value="ok"):
    return Fact(f"fact:{i}", ref, field, value, 1, "test")


class WorkingSetTests(unittest.TestCase):
    def test_lru_bound_on_objects(self):
        ws = WorkingSet(max_objects=3)
        for i in range(5):
            ws.materialize(f"service://s{i}", "service", "s", [fact(i, f"service://s{i}")])
        self.assertEqual(list(ws.objects), ["service://s2", "service://s3", "service://s4"])
        self.assertEqual(ws.evictions, 2)
        self.assertEqual(ws.peak_objects, 3)

    def test_touch_protects_from_eviction(self):
        ws = WorkingSet(max_objects=2)
        ws.materialize("service://a", "service", "a", [fact(1, "service://a")])
        ws.materialize("service://b", "service", "b", [fact(2, "service://b")])
        ws.touch("service://a")
        ws.materialize("service://c", "service", "c", [fact(3, "service://c")])
        self.assertIn("service://a", ws.objects)
        self.assertNotIn("service://b", ws.objects)

    def test_token_budget(self):
        ws = WorkingSet(max_objects=100, max_tokens=60)
        for i in range(6):
            ws.materialize(f"service://s{i}", "service", "s",
                           [fact(i, f"service://s{i}", "note", "x" * 80)])
        self.assertLessEqual(len(ws.objects), 2)


class WorldTests(unittest.TestCase):
    def test_deterministic(self):
        other = build_world(600, seed=3, cache_dir=tempfile.mkdtemp())
        self.assertEqual(GraphStore(other.path).truth(), STORE.truth())

    def test_ground_truth_is_resolvable(self):
        for t in STORE.truth():
            cause = STORE.get(t["cause"])
            self.assertIn(("TARGETS", t["root"]),
                          [(r.predicate, r.target) for r in cause.relations])


class ReasonerTests(unittest.TestCase):
    def test_stateless_pure_function_of_prompt(self):
        rt = CVMRuntime(STORE)
        ctx = CognitiveContext("agent://t", TASKS[0].task, incident_agent_capabilities(), WorkingSet())
        rt.seed(ctx)
        prompt = rt.build_prompt(ctx)
        self.assertEqual(ReferenceReasoner().step(prompt), ReferenceReasoner().step(prompt))

    def test_parse_prompt(self):
        rt = CVMRuntime(STORE)
        ctx = CognitiveContext("agent://t", TASKS[0].task, incident_agent_capabilities(), WorkingSet())
        rt.seed(ctx)
        kb = parse_prompt(rt.build_prompt(ctx))
        self.assertEqual(kb.task_kind, "root_cause")
        self.assertIn(TASKS[0].task.target, kb.objects)
        self.assertIn("FAULT", kb.ops)

    def test_cvm_solves_all_tasks_with_bounded_residency(self):
        for sp in TASKS:
            m = run_cvm(STORE, sp, ReferenceReasoner(), WORLD.n_objects)
            self.assertEqual(m["correct"], 1, (sp.task.text, m))
            self.assertLessEqual(m["peak_resident_objects"], 32)
            self.assertEqual(m["unsupported_answers"], 0)

    def test_small_working_set_with_notes_still_solves(self):
        for sp in TASKS[:9]:
            m = run_cvm(STORE, sp, ReferenceReasoner(), WORLD.n_objects, max_objects=3)
            self.assertEqual(m["correct"], 1)
            self.assertLessEqual(m["peak_resident_objects"], 3)

    def test_agent_and_full_context_agree(self):
        full = FullContext(STORE, WORLD.n_objects)
        self.assertTrue(full.feasible)
        for sp in TASKS[:6]:
            self.assertEqual(run_agent(STORE, sp, ReferenceReasoner(), WORLD.n_objects)["correct"], 1)
            self.assertEqual(full.run(sp, ReferenceReasoner())["correct"], 1)


class VerifierTests(unittest.TestCase):
    def test_rejects_hallucinated_answers(self):
        for proc in (Hallucinator(True), Hallucinator(False)):
            m = run_cvm(STORE, TASKS[0], proc, WORLD.n_objects)
            self.assertEqual(m["correct"], 0)
            self.assertEqual(m["unsupported_answers"], m["answers"])
            self.assertGreater(m["answers"], 0)

    def test_rejects_ungrounded_ref(self):
        rt = CVMRuntime(STORE)
        ctx = CognitiveContext("agent://t", TASKS[0].task, incident_agent_capabilities(), WorkingSet())
        rt.seed(ctx)
        ok, _ = rt.verify(ctx, "change://nope", ["fact:1"])
        self.assertFalse(ok)
        ok, _ = rt.verify(ctx, TASKS[0].task.target, ["fact:1"])
        self.assertTrue(ok)


class CapabilityTests(unittest.TestCase):
    def test_capability_fault(self):
        rt = CVMRuntime(STORE)
        ctx = CognitiveContext("agent://t", TASKS[0].task,
                               incident_agent_capabilities(search=False), WorkingSet())
        rt.dispatch(ctx, {"op": "SEARCH", "namespace": "change://", "query": "x"})
        self.assertTrue(ctx.last_result.startswith("CAPABILITY_FAULT"))
        rt.dispatch(ctx, {"op": "WRITE", "entries": {"k": "v"}})
        self.assertTrue(ctx.last_result.startswith("ok"))

    def test_search_revoked_falls_back_to_traversal(self):
        for sp in TASKS[:6]:
            m = run_cvm(STORE, sp, ReferenceReasoner(), WORLD.n_objects, search=False)
            self.assertEqual(m["correct"], 1)

    def test_child_gets_subset(self):
        parent = CognitiveContext("p", TASKS[0].task,
                                  [Capability("service://*", ("READ", "FAULT"))], WorkingSet())
        child = parent.spawn(Task("t", "x", "", ""),
                             [Capability("service://*", ("READ",)),
                              Capability("change://*", ("SEARCH",))])
        self.assertTrue(child.can("READ", "service://a"))
        self.assertFalse(child.can("SEARCH", "change://"))


class ContextSwitchTests(unittest.TestCase):
    def test_interleaved_equals_sequential(self):
        rt = CVMRuntime(STORE)
        proc = ReferenceReasoner()
        ctxs = [CognitiveContext("a", sp.task, incident_agent_capabilities(), WorkingSet())
                for sp in TASKS[:6]]
        live = list(ctxs)
        while live:
            for c in list(live):
                rt.resume(c)
                rt.step(c, proc)
                if c.state == "DONE":
                    live.remove(c)
                else:
                    rt.suspend(c)
        for c, sp in zip(ctxs, TASKS[:6]):
            self.assertEqual(c.answer, sp.expected)


class _FakeMessages:
    """Stands in for client.messages; replays a scripted run of JSON actions."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.requests = []

    def create(self, **kw):
        import json
        from types import SimpleNamespace as NS
        self.requests.append(kw)
        text = json.dumps(self.actions.pop(0))
        return NS(stop_reason="end_turn", content=[NS(type="text", text=text)],
                  usage=NS(input_tokens=10, output_tokens=5))


class ClaudeAdapterTests(unittest.TestCase):
    def test_stateless_calls_through_runtime(self):
        from types import SimpleNamespace as NS
        from cvm.processors import ClaudeProcessor
        blank = {"ref": "", "field": "", "relation": "", "page": 0, "namespace": "",
                 "query": "", "reason": "", "entries": [], "value": "", "support": []}
        sp = TASKS[1]  # owner task: incident is seeded resident
        inc = sp.task.target
        fake = _FakeMessages([
            dict(blank, op="FAULT", ref=inc, reason="need incident"),
            dict(blank, op="ANSWER", value="team://made-up", support=["fact:999"]),
            dict(blank, op="ANSWER", value=inc, support=["fact:1"]),
        ])
        proc = ClaudeProcessor(client=NS(messages=fake))
        rt = CVMRuntime(STORE)
        ctx = CognitiveContext("agent://claude", sp.task, incident_agent_capabilities(), WorkingSet())
        rt.run(ctx, proc, max_steps=3)
        self.assertEqual(len(fake.requests), 3)
        for req in fake.requests:  # no conversation history: one user turn = the resident view
            self.assertEqual(len(req["messages"]), 1)
            self.assertIn("RESIDENT OBJECTS", req["messages"][0]["content"])
            self.assertEqual(req["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(ctx.counters["unsupported_answers"], 1)  # fabricated citation rejected
        self.assertEqual(ctx.state, "DONE")

    def test_normalize(self):
        a = normalize_action({"op": "WRITE", "ref": "", "field": "", "relation": "", "page": 0,
                              "namespace": "", "query": "", "reason": "",
                              "entries": [{"key": "k", "value": "v"}], "value": "", "support": []})
        self.assertEqual(a, {"op": "WRITE", "entries": {"k": "v"}, "page": 0})
        a = normalize_action({"op": "ANSWER", "value": "team://x", "support": ["[fact:3]"],
                              "ref": "", "entries": []})
        self.assertEqual(a["support"], ["fact:3"])


class ChatCompletionsAdapterTests(unittest.TestCase):
    def test_json_mode_stateless_and_abort(self):
        import json
        from cvm.processors import ChatCompletionsProcessor
        sp = TASKS[1]
        bodies = []
        script = [
            {"op": "fault", "ref": sp.task.target, "reason": "need incident"},
            {"op": "ANSWER", "value": sp.task.target, "support": ["[fact:1]"]},
        ]

        def transport(body):
            bodies.append(body)
            return {"choices": [{"message": {"content": json.dumps(script.pop(0))}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 7}}

        proc = ChatCompletionsProcessor(transport=transport)
        rt = CVMRuntime(STORE)
        ctx = CognitiveContext("agent://ds", sp.task, incident_agent_capabilities(), WorkingSet())
        rt.run(ctx, proc, max_steps=5)
        self.assertEqual(ctx.state, "DONE")
        self.assertEqual(ctx.answer, sp.task.target)
        self.assertEqual(proc.usage["calls"], 2)
        for b in bodies:
            self.assertEqual(b["response_format"], {"type": "json_object"})
            self.assertEqual([m["role"] for m in b["messages"]], ["system", "user"])

        def broken(body):
            import urllib.error
            raise urllib.error.HTTPError("u", 401, "unauthorized", {}, None)

        ctx = CognitiveContext("agent://ds", sp.task, incident_agent_capabilities(), WorkingSet())
        rt.run(ctx, ChatCompletionsProcessor(transport=broken), max_steps=5)
        self.assertEqual(ctx.counters["aborted"], 1)
        self.assertEqual(ctx.counters["steps"], 1)


class CustomStoreExampleTests(unittest.TestCase):
    def test_custom_store_end_to_end(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
        import custom_store as cs
        from cvm.resolver import L2Cache, MountTable, NamespaceMount, Resolver
        store = cs.DictStore(cs.demo_world())
        cache = L2Cache()
        g = Resolver(store, cache)
        ns = ("repo://", "file://", "commit://", "team://", "bug://")
        rt = CVMRuntime(store, cache=cache, mounts=MountTable([NamespaceMount(n, g) for n in ns]))
        caps = [Capability(n + "*", ("READ", "TRAVERSE", "FAULT")) for n in ns]
        caps.append(Capability("commit://*", ("SEARCH",)))
        ctx = CognitiveContext("a", Task("t", "x", "q", "bug://771", ["bug://771"]), caps,
                               WorkingSet(4))
        rt.seed(ctx)
        rt.dispatch(ctx, {"op": "SEARCH", "namespace": "commit://", "query": "tax rounding"})
        rt.dispatch(ctx, {"op": "FAULT", "ref": "commit://a8f92d", "reason": "r"})
        ids = [f.id for f in ctx.facts_by_id.values() if f.ref == "commit://a8f92d"]
        rt.dispatch(ctx, {"op": "ANSWER", "value": "commit://a8f92d", "support": ids[:1]})
        self.assertEqual(ctx.answer, "commit://a8f92d")
        rt2 = CVMRuntime(store, cache=cache, mounts=MountTable([NamespaceMount(n, g) for n in ns]))
        ctx2 = CognitiveContext("b", Task("t", "x", "q", "bug://771", []), caps, WorkingSet(4))
        rt2.dispatch(ctx2, {"op": "SEARCH", "namespace": "team://", "query": "payments"})
        self.assertTrue(ctx2.last_result.startswith("CAPABILITY_FAULT"))


if __name__ == "__main__":
    unittest.main()
