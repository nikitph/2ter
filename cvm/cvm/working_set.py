"""Bounded resident working set with runtime-owned (LRU) eviction.

The model never manages residency. It can only *request* state (FAULT/READ);
the runtime decides what stays. Notes written by the model (``scratch://``) are
part of the context but are budgeted separately and never evicted silently.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from .objects import Fact, ObjectRef, approx_tokens

RELATION_PREVIEW = 8  # per predicate, in bounded mode


@dataclass
class ResidentObject:
    ref: ObjectRef
    type: str
    label: str
    facts: "OrderedDict[str, Fact]" = field(default_factory=OrderedDict)  # field key -> fact
    inverse_counts: dict[str, int] = field(default_factory=dict)
    inverse_edges: list[tuple[str, ObjectRef]] = field(default_factory=list)  # agent mode only

    def render(self, full: bool = False) -> str:
        lines = [f"{self.ref}  [{self.type}] {self.label}"]
        per_pred: dict[str, int] = {}
        hidden: dict[str, int] = {}
        for f in self.facts.values():
            is_rel = f.field.lstrip("~").replace("_", "").isupper()
            if is_rel and not full:
                per_pred[f.field] = per_pred.get(f.field, 0) + 1
                if per_pred[f.field] > RELATION_PREVIEW:
                    hidden[f.field] = hidden.get(f.field, 0) + 1
                    continue
            lines.append("  " + f.render())
        for p, n in hidden.items():
            lines.append(f"  ({p}: +{n} more, use TRAVERSE)")
        if full:
            for p, src in self.inverse_edges:
                lines.append(f"  {p} <- {src}")
        else:
            for p, n in sorted(self.inverse_counts.items()):
                lines.append(f"  ({p}: {n} refs, use TRAVERSE {p})")
        return "\n".join(lines)


class WorkingSet:
    def __init__(self, max_objects: int = 32, max_tokens: int = 16_000,
                 max_handles: int = 48, full_render: bool = False):
        self.max_objects = max_objects
        self.max_tokens = max_tokens
        self.max_handles = max_handles
        self.full_render = full_render
        self.objects: "OrderedDict[ObjectRef, ResidentObject]" = OrderedDict()
        self.handles: "OrderedDict[ObjectRef, str]" = OrderedDict()
        self.evictions = 0
        self.peak_objects = 0
        self._tok: dict[ObjectRef, int] = {}  # cached rendered size per resident object
        self._total = 0

    # -- residency -----------------------------------------------------
    def is_resident(self, ref: ObjectRef) -> bool:
        return ref in self.objects

    def touch(self, ref: ObjectRef):
        if ref in self.objects:
            self.objects.move_to_end(ref)

    def materialize(self, ref, type_, label, facts: list[Fact], inverse_counts=None,
                    inverse_edges=None) -> list[ObjectRef]:
        ro = self.objects.get(ref)
        if ro is None:
            ro = ResidentObject(ref, type_, label)
            self.objects[ref] = ro
        for f in facts:
            ro.facts[f"{f.field}={f.value}"] = f
        if inverse_counts:
            ro.inverse_counts = dict(inverse_counts)
        if inverse_edges:
            ro.inverse_edges = list(inverse_edges)
        new = approx_tokens(ro.render(self.full_render))
        self._total += new - self._tok.get(ref, 0)
        self._tok[ref] = new
        self.objects.move_to_end(ref)
        evicted = self._enforce(protect=ref)
        self.peak_objects = max(self.peak_objects, len(self.objects))
        return evicted

    def add_handles(self, refs: list[ObjectRef], via: str):
        for r in refs:
            self.handles[r] = via
            self.handles.move_to_end(r)
        while len(self.handles) > self.max_handles:
            self.handles.popitem(last=False)

    def object_tokens(self) -> int:
        return self._total

    def _enforce(self, protect: ObjectRef) -> list[ObjectRef]:
        evicted = []
        while len(self.objects) > self.max_objects or (
                self._total > self.max_tokens and len(self.objects) > 1):
            victim = next(iter(self.objects))  # LRU
            if victim == protect:
                break
            self.objects.pop(victim)
            self._total -= self._tok.pop(victim, 0)
            evicted.append(victim)
            self.evictions += 1
        return evicted

    # -- rendering -----------------------------------------------------
    def render_objects(self) -> str:
        return "\n".join(o.render(self.full_render) for o in self.objects.values())

    def render_handles(self) -> str:
        return "\n".join(f"  {r}   (via {via})" for r, via in self.handles.items())
