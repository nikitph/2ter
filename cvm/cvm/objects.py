"""Core value types: references, objects, relations, facts.

A reference (``ObjectRef``) is just a stable URI string ``<namespace>://<id>``.
References are handles, not serialized objects: holding one costs a few tokens
regardless of how much state sits behind it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

ObjectRef = str

EPOCH = datetime(2026, 3, 1, tzinfo=timezone.utc)


def namespace_of(ref: ObjectRef) -> str:
    """``service://payments-k1`` -> ``service://``"""
    i = ref.find("://")
    return ref[: i + 3] if i >= 0 else ""


def is_ref(value: Any) -> bool:
    return isinstance(value, str) and "://" in value and " " not in value


def iso(minutes: int) -> str:
    """Synthetic timestamps are integer minutes since EPOCH; render as ISO."""
    return (EPOCH + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%MZ")


def approx_tokens(text: str) -> int:
    """Cheap, model-agnostic token estimate (~4 chars/token)."""
    return (len(text) + 3) // 4


@dataclass(frozen=True)
class Relation:
    predicate: str
    target: ObjectRef


@dataclass
class CVMObject:
    ref: ObjectRef
    type: str
    label: str
    attributes: dict[str, Any]
    relations: list[Relation]
    version: int = 1
    # Inverse edges are part of the logical address space but are never
    # materialized eagerly in CVM mode; we only carry their count.
    inverse_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Fact:
    """One materialized, citable unit of external state.

    ``id`` is stable within a context: re-materializing the same
    (ref, field, value, version) yields the same fact id.
    """
    id: str
    ref: ObjectRef
    field: str
    value: Any
    version: int
    source: str  # resolver that produced it (provenance)

    def render(self) -> str:
        v = self.value
        if isinstance(v, (dict, list)):
            v = json.dumps(v, separators=(",", ":"))
        if self.field.lstrip("~").replace("_", "").isupper():  # relation
            return f"[{self.id}] {self.field} -> {v}"
        return f"[{self.id}] {self.field} = {v}"
