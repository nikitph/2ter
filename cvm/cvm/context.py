"""Cognitive contexts: the process / address-space abstraction.

A context owns identity, task, namespace mounts, capabilities, a bounded
working set, model-written notes, a provenance ledger and execution state.
The model never chooses its context; the runtime creates and schedules them.
"""
from __future__ import annotations

import itertools
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .objects import Fact, ObjectRef, approx_tokens, namespace_of
from .working_set import WorkingSet

OPS = ("READ", "TRAVERSE", "SEARCH", "FAULT", "EVIDENCE", "WRITE")


@dataclass(frozen=True)
class Capability:
    namespace: str          # e.g. "service://*", "change://*", "*"
    operations: tuple[str, ...]
    deny: bool = False

    def matches(self, op: str, ref_or_ns: str) -> bool:
        if op not in self.operations and "*" not in self.operations:
            return False
        pat = self.namespace
        if pat == "*":
            return True
        if pat.endswith("*"):
            return ref_or_ns.startswith(pat[:-1])
        return ref_or_ns == pat


@dataclass
class Task:
    id: str
    kind: str      # root_cause | owner | claim
    text: str
    target: ObjectRef
    seed_refs: list[ObjectRef] = field(default_factory=list)


_ctx_ids = itertools.count(1)


@dataclass
class CognitiveContext:
    principal: str
    task: Task
    capabilities: list[Capability]
    working_set: WorkingSet
    available_ops: tuple[str, ...] = OPS
    max_notes: int = 48
    trace_window: int | None = 6   # None = keep entire transcript in prompt
    parent: str | None = None
    id: str = ""

    # execution state
    state: str = "READY"           # READY | RUNNING | SUSPENDED | DONE
    notes: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    trace: list[str] = field(default_factory=list)
    last_result: str = ""
    answer: Any = None
    answer_support: list[str] = field(default_factory=list)

    # provenance ledger: every fact ever materialized in this context
    facts_by_key: dict[tuple, Fact] = field(default_factory=dict)
    facts_by_id: dict[str, Fact] = field(default_factory=dict)

    # accounting
    materialized: Counter = field(default_factory=Counter)  # ref -> times materialized
    evicted_once: set = field(default_factory=set)
    counters: Counter = field(default_factory=Counter)
    prompt_tokens: list[int] = field(default_factory=list)
    peak_resident_tokens: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = f"ctx://{next(_ctx_ids):04d}"

    # -- capabilities --------------------------------------------------
    def can(self, op: str, ref: str) -> bool:
        target = ref if "://" in ref else ref
        allowed = False
        for c in self.capabilities:
            if c.matches(op, target):
                if c.deny:
                    return False
                allowed = True
        return allowed

    # -- provenance ----------------------------------------------------
    def fact(self, ref: ObjectRef, field_: str, value: Any, version: int, source: str) -> Fact:
        key = (ref, field_, repr(value), version)
        f = self.facts_by_key.get(key)
        if f is None:
            f = Fact(f"fact:{len(self.facts_by_id) + 1}", ref, field_, value, version, source)
            self.facts_by_key[key] = f
            self.facts_by_id[f.id] = f
        return f

    # -- notes (model-written registers, budgeted, never evicted) ------
    def write_notes(self, entries: dict[str, Any]) -> str:
        for k, v in entries.items():
            if v is None or v == "":
                self.notes.pop(k, None)
                continue
            if k not in self.notes and len(self.notes) >= self.max_notes:
                return "WRITE_FAULT notes full"
            self.notes[k] = str(v)
        return f"ok ({len(self.notes)}/{self.max_notes} notes)"

    def notes_tokens(self) -> int:
        return sum(approx_tokens(f"{k} = {v}") for k, v in self.notes.items())

    # -- spawning ------------------------------------------------------
    def spawn(self, task: Task, capabilities: list[Capability] | None = None,
              working_set: WorkingSet | None = None) -> "CognitiveContext":
        """Child contexts inherit mounts and a *subset* of capabilities; not memory."""
        caps = capabilities if capabilities is not None else list(self.capabilities)
        caps = [c for c in caps if self._covers(c)] + [c for c in self.capabilities if c.deny]
        return CognitiveContext(
            principal=f"{self.principal}/child", task=task, capabilities=caps,
            working_set=working_set or WorkingSet(self.working_set.max_objects,
                                                  self.working_set.max_tokens),
            available_ops=self.available_ops, parent=self.id)

    def _covers(self, cap: Capability) -> bool:
        """A child capability is kept only if the parent holds it for every op."""
        if cap.deny:
            return True
        probe = cap.namespace.rstrip("*") or "*"
        return all(self.can(op, probe if probe != "*" else "x://") for op in cap.operations)


def incident_agent_capabilities(search: bool = True, write: bool = True,
                                claims: bool = True) -> list[Capability]:
    caps = [
        Capability("service://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("host://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("config://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("metrics://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("team://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("person://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("incident://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("change://*", ("READ", "TRAVERSE", "FAULT")),
        Capability("deploy://*", ("READ", "TRAVERSE", "FAULT")),
    ]
    if claims:  # hypotheses about an incident are only visible to claim-verification tasks
        caps.append(Capability("claim://*", ("READ", "TRAVERSE", "FAULT", "EVIDENCE")))
    if search:
        caps += [Capability("change://*", ("SEARCH",)), Capability("deploy://*", ("SEARCH",))]
    if write:
        caps += [Capability("scratch://*", ("WRITE",))]
    caps += [Capability("*", ("WRITE",), deny=True)] if not write else [
        Capability("service://*", ("WRITE",), deny=True)]
    return caps
