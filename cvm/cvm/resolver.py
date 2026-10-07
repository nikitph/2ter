"""Resolvers: the software MMU.

``Resolve(context, ref, operation) -> materialized state``.  Each namespace is
mounted on a resolver; resolvers sit in front of a backing store and an L2
materialization cache. Every backend touch is counted as external I/O.

The physical storage for the synthetic world is one SQLite file, but it is
deliberately accessed through several resolvers so the address space spans
"heterogeneous" sources exactly as a real mount table would.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any

from .objects import CVMObject, ObjectRef, Relation, namespace_of


class GraphStore:
    """Thin read-only accessor over the synthetic world database."""

    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.io = 0  # backend queries issued

    def _q(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self.lock:
            self.io += 1
            return self.db.execute(sql, args).fetchall()

    def get(self, ref: ObjectRef) -> CVMObject | None:
        rows = self._q("SELECT type,label,attrs,version FROM objects WHERE ref=?", (ref,))
        if not rows:
            return None
        type_, label, attrs, version = rows[0]
        rels = [Relation(p, d) for p, d in
                self._q("SELECT pred,dst FROM relations WHERE src=?", (ref,))]
        inv = {f"~{p}": n for p, n in
               self._q("SELECT pred,COUNT(*) FROM relations WHERE dst=? GROUP BY pred", (ref,))}
        return CVMObject(ref, type_, label, json.loads(attrs), rels, version, inv)

    def inverse(self, ref: ObjectRef, pred: str, limit: int, offset: int = 0) -> list[ObjectRef]:
        return [r for (r,) in self._q(
            "SELECT src FROM relations WHERE dst=? AND pred=? ORDER BY src LIMIT ? OFFSET ?",
            (ref, pred, limit, offset))]

    def inverse_all(self, ref: ObjectRef) -> list[tuple[str, ObjectRef]]:
        return self._q("SELECT pred, src FROM relations WHERE dst=? ORDER BY pred, src", (ref,))

    def traverse(self, ref: ObjectRef, pred: str, limit: int, offset: int = 0) -> list[ObjectRef]:
        return [r for (r,) in self._q(
            "SELECT dst FROM relations WHERE src=? AND pred=? ORDER BY rowid LIMIT ? OFFSET ?",
            (ref, pred, limit, offset))]

    def search(self, namespace: str, query: str, k: int) -> list[ObjectRef]:
        terms = [t for t in _tokens(query) if t]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        sql = ("SELECT o.ref FROM search s JOIN objects o ON o.id = s.rowid "
               "WHERE search MATCH ? {ns} ORDER BY bm25(search) LIMIT ?")
        if namespace:
            return [r for (r,) in self._q(sql.format(ns="AND s.ns = ?"), (match, namespace, k))]
        return [r for (r,) in self._q(sql.format(ns=""), (match, k))]

    def truth(self) -> list[dict]:
        cols = [row[1] for row in self._q("PRAGMA table_info(truth)")]
        out = []
        for row in self._q("SELECT * FROM truth ORDER BY cluster"):
            d = dict(zip(cols, row))
            d["useful"] = json.loads(d["useful"])
            out.append(d)
        return out

    def iter_objects(self):
        """Stream every object (used only by the full-context baseline)."""
        cur = sqlite3.connect(self.path).execute(
            "SELECT ref FROM objects ORDER BY id")
        for (ref,) in cur:
            yield ref


_STOP = {"the", "a", "an", "of", "to", "or", "and", "what", "which", "is", "did",
         "caused", "cause", "for", "on", "in", "by", "was", "that", "who", "owns"}


def _tokens(q: str) -> list[str]:
    import re
    out = []
    for t in re.split(r"[^A-Za-z0-9_\-]+", q.lower()):
        t = t.strip("-")
        if t and t not in _STOP and t not in ("service", "change", "deploy", "incident",
                                              "claim", "metrics", "config"):
            out.append(t)
    return out


@dataclass
class Materialization:
    obj: CVMObject
    fields: list[tuple[str, Any]]  # (field, value) pairs to become facts
    source: str


class Resolver:
    """Base resolver. ``visibility`` lets contexts see different views."""

    name = "resolver"

    def __init__(self, store: GraphStore, cache: "L2Cache"):
        self.store = store
        self.cache = cache

    def fetch(self, ref: ObjectRef, demand: bool = True) -> CVMObject | None:
        hit = self.cache.get(ref, demand)
        if hit is not None:
            return hit
        if not demand:
            self.cache.prefetches += 1
        obj = self.store.get(ref)
        if obj is not None:
            self.cache.put(ref, obj)
        return obj

    def resolve(self, ctx, ref: ObjectRef, operation: str,
                field: str | None = None) -> Materialization | None:
        obj = self.fetch(ref)
        if obj is None:
            return None
        fields = self.view(ctx, obj)
        if field:
            fields = [(f, v) for f, v in fields if f == field or f.lstrip("~") == field]
        return Materialization(obj, fields, self.name)

    def view(self, ctx, obj: CVMObject) -> list[tuple[str, Any]]:
        """Context-dependent projection of an object into citable fields."""
        fields: list[tuple[str, Any]] = [(k, v) for k, v in sorted(obj.attributes.items())]
        fields += [(r.predicate, r.target) for r in obj.relations]
        return fields

    def prefetch_hints(self, obj: CVMObject) -> list[ObjectRef]:
        return []


class InfrastructureResolver(Resolver):
    name = "InfrastructureGraphResolver"

    def prefetch_hints(self, obj):
        return [r.target for r in obj.relations if r.predicate in ("HAS_METRICS", "HAS_CONFIG")]


class ChangeResolver(Resolver):
    name = "ChangeLogResolver"


class MetricsResolver(Resolver):
    name = "MetricsResolver"


class IncidentResolver(Resolver):
    name = "IncidentResolver"


class EvidenceResolver(Resolver):
    name = "EvidenceGraphResolver"


class PeopleResolver(Resolver):
    name = "DirectoryResolver"

    def view(self, ctx, obj):
        # Example of a context-sensitive view: contexts without the
        # ``person://*`` READ capability scope "pii" get a redacted projection.
        fields = super().view(ctx, obj)
        if ctx is not None and not ctx.can("READ", "pii://"):
            fields = [(f, v) for f, v in fields if f not in ("email", "phone")]
        return fields


class L2Cache:
    """Runtime object cache (L2). Keyed by ref; values carry their version."""

    def __init__(self, enabled: bool = True, capacity: int = 50_000):
        self.enabled = enabled
        self.capacity = capacity
        self.data: dict[ObjectRef, CVMObject] = {}
        self.hits = 0
        self.misses = 0
        self.prefetches = 0

    def get(self, ref, demand: bool = True):
        o = self.data.get(ref) if self.enabled else None
        if demand:  # only demand accesses count; a demand miss is a stall on the backend
            if o is None:
                self.misses += 1
            else:
                self.hits += 1
        return o

    def put(self, ref, obj):
        if not self.enabled:
            return
        if len(self.data) >= self.capacity:
            self.data.pop(next(iter(self.data)))
        self.data[ref] = obj


@dataclass
class NamespaceMount:
    prefix: str
    resolver: Resolver


@dataclass
class MountTable:
    mounts: list[NamespaceMount] = field(default_factory=list)

    def resolver_for(self, ref: ObjectRef) -> Resolver | None:
        ns = namespace_of(ref)
        for m in self.mounts:
            if m.prefix == ns:
                return m.resolver
        return None

    def describe(self) -> list[str]:
        return [f"{m.prefix:<12} {m.resolver.name}" for m in self.mounts]


def default_mounts(store: GraphStore, cache: L2Cache) -> MountTable:
    infra = InfrastructureResolver(store, cache)
    change = ChangeResolver(store, cache)
    return MountTable([
        NamespaceMount("service://", infra),
        NamespaceMount("host://", infra),
        NamespaceMount("config://", infra),
        NamespaceMount("team://", infra),
        NamespaceMount("person://", PeopleResolver(store, cache)),
        NamespaceMount("change://", change),
        NamespaceMount("deploy://", change),
        NamespaceMount("metrics://", MetricsResolver(store, cache)),
        NamespaceMount("incident://", IncidentResolver(store, cache)),
        NamespaceMount("claim://", EvidenceResolver(store, cache)),
        NamespaceMount("repo://", Resolver(store, cache)),
        NamespaceMount("file://", Resolver(store, cache)),
        NamespaceMount("symbol://", Resolver(store, cache)),
        NamespaceMount("commit://", Resolver(store, cache)),
        NamespaceMount("test://", Resolver(store, cache)),
        NamespaceMount("bug://", Resolver(store, cache)),
    ])
