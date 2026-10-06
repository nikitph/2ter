"""Deterministic synthetic infrastructure world with injected causal chains.

The world is a set of *clusters* (one org unit each) plus a fixed set of shared
platform services. Every cluster contains one active incident whose root cause
is a known change or deployment ``depth`` dependency hops away from the
affected service. Ground truth is recorded in a ``truth`` table.

Structure per cluster k (depth d in {1,2,3}):

    incident://inc-kK  --AFFECTS-->  s0
    s0 -DEPENDS_ON-> s1 -DEPENDS_ON-> ... -> s4        (plus random extra edges)
    s1..sd anomalous (latency), anomaly start strictly earlier the deeper it is
    cause event (change or deploy) TARGETS sd, shortly before sd's anomaly

Distractors (the traps a shortcut reasoner falls into):
  * a change on the affected service s0 minutes before the incident
  * an older event on the root service, and a post-anomaly "mitigation" event
  * a noisy dependency whose anomaly starts *after* the incident
  * shared platform services with in-degree growing linearly with world size
  * a resolved historical incident and a false claim per cluster

Storage is SQLite (objects / relations / FTS5 search index). The graph is the
address space; nothing here is loaded into a model's context wholesale.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
from dataclasses import dataclass

SERVICE_NAMES = [
    "payments", "checkout", "ledger", "auth", "search", "inventory", "pricing",
    "catalog", "orders", "billing", "notify", "profile", "session", "cart",
    "shipping", "fraud", "reco", "media", "gateway", "quota", "tax", "refunds",
    "rates", "geo", "ads", "wallet", "loyalty", "invoices", "support", "audit",
]
PLATFORM = ["platform-dns", "platform-kafka", "platform-vault", "platform-redis"]
CONFIG_FIELDS = {
    "max_connections": (200, 2000),
    "pool_size": (16, 256),
    "timeout_ms": (200, 5000),
    "cache_ttl_s": (30, 3600),
}
MINUTES_30D = 30 * 24 * 60

SCHEMA = """
CREATE TABLE objects(id INTEGER PRIMARY KEY, ref TEXT UNIQUE, type TEXT,
                     label TEXT, attrs TEXT, version INTEGER);
CREATE TABLE relations(src TEXT, pred TEXT, dst TEXT);
CREATE TABLE truth(cluster INTEGER PRIMARY KEY, incident TEXT, depth INTEGER,
                   affected TEXT, root TEXT, cause TEXT, owner TEXT,
                   claim_true TEXT, claim_false TEXT, useful TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE search USING fts5(ns UNINDEXED, body,
    tokenize="unicode61 tokenchars '-_'");
"""

OBJECTS_PER_CLUSTER = 43  # approximate; used only to size the world


@dataclass
class WorldInfo:
    path: str
    n_objects: int
    n_relations: int
    n_clusters: int


class _Builder:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.objs: list[tuple] = []
        self.rels: list[tuple] = []
        self.fts: list[tuple] = []
        self.next_id = 1

    def obj(self, ref, type_, label, attrs, rels=(), text=""):
        oid = self.next_id
        self.next_id += 1
        self.objs.append((oid, ref, type_, label, json.dumps(attrs, sort_keys=True), 1))
        for pred, dst in rels:
            self.rels.append((ref, pred, dst))
        if text:
            self.fts.append((oid, ref.split("://")[0] + "://", f"{ref} {label} {text}"))

    def flush(self):
        self.db.executemany("INSERT INTO objects VALUES(?,?,?,?,?,?)", self.objs)
        self.db.executemany("INSERT INTO relations VALUES(?,?,?)", self.rels)
        self.db.executemany("INSERT INTO search(rowid, ns, body) VALUES(?,?,?)", self.fts)
        self.objs, self.rels, self.fts = [], [], []


def _event(b: _Builder, rng: random.Random, ref, kind, svc, cfg, author, at, cfg_change=None):
    if kind == "change":
        fld, old, new = cfg_change or _random_cfg_change(rng)
        summary = f"config change {fld} {old} -> {new} on {svc}"
        attrs = {"at": iso_(at), "field": fld, "old": old, "new": new, "summary": summary}
        rels = [("TARGETS", svc), ("MODIFIES", cfg), ("AUTHORED_BY", author)]
    else:
        ver = f"v{rng.randint(1, 9)}.{rng.randint(0, 40)}.{rng.randint(0, 9)}"
        summary = f"deploy {ver} of {svc}"
        attrs = {"at": iso_(at), "version": ver, "summary": summary}
        rels = [("TARGETS", svc), ("AUTHORED_BY", author)]
    b.obj(ref, kind, summary, attrs, rels, text=f"{kind} {summary} by {author}")


def _random_cfg_change(rng: random.Random):
    fld = rng.choice(list(CONFIG_FIELDS))
    lo, hi = CONFIG_FIELDS[fld]
    old = rng.randint(lo, hi)
    new = rng.randint(lo, hi)
    return fld, old, new


def _metrics(b, ref, svc, baseline, anomaly_start=None, peak=None):
    attrs = {
        "metric": "latency_p99_ms",
        "baseline": baseline,
        "status": "anomalous" if anomaly_start is not None else "normal",
        "anomaly_start": anomaly_start,
        "peak": peak,
    }
    b.obj(ref, "metrics", f"latency for {svc}", attrs, [("OF", svc)])


def _build_platform(b: _Builder, rng: random.Random):
    b.obj("team://platform", "team", "platform team", {"oncall": "person://platform-oncall"},
          text="team platform infrastructure")
    b.obj("person://platform-oncall", "person", "platform oncall", {"role": "sre"})
    for name in PLATFORM:
        svc = f"service://{name}"
        b.obj(svc, "service", name, {"tier": 0, "status": "healthy"},
              [("OWNED_BY", "team://platform"), ("RUNS_ON", f"host://{name}-01"),
               ("HAS_CONFIG", f"config://{name}"), ("HAS_METRICS", f"metrics://{name}")],
              text=f"service {name} shared platform")
        b.obj(f"host://{name}-01", "host", f"{name}-01", {"region": "us-east-1"})
        b.obj(f"config://{name}", "config", f"{name} config",
              {f: rng.randint(*r) for f, r in CONFIG_FIELDS.items()}, [("OF", svc)])
        _metrics(b, f"metrics://{name}", svc, rng.randint(2, 15))
        for j in range(2):
            kind = "change" if j == 0 else "deploy"
            _event(b, rng, f"{kind}://{name}-{j}", kind, svc, f"config://{name}",
                   "person://platform-oncall", rng.randint(0, MINUTES_30D))


def _build_cluster(b: _Builder, rng: random.Random, k: int):
    depth = 1 + (k % 3)
    names = rng.sample(SERVICE_NAMES, 5)
    svcs = [f"service://{n}-k{k}" for n in names]
    teams = [f"team://t{k}a", f"team://t{k}b"]
    people = [f"person://u{k}-{i}" for i in range(3)]
    for t in teams:
        b.obj(t, "team", t.split("//")[1], {"oncall": rng.choice(people)},
              text=f"team {t}")
    for p in people:
        b.obj(p, "person", p.split("//")[1], {"role": rng.choice(["swe", "sre"])})

    T = rng.randint(3 * 24 * 60, MINUTES_30D - 24 * 60)  # incident start
    # anomaly start times along the chain (s0 degrades at T)
    starts = {0: T}
    for i in range(1, depth + 1):
        starts[i] = starts[i - 1] - rng.randint(4, 12)
    root = depth

    owners = [rng.choice(teams) for _ in svcs]
    deps: dict[int, list[str]] = {i: [] for i in range(5)}
    for i in range(4):
        deps[i].append(svcs[i + 1])
        for j in range(i + 2, 5):
            if rng.random() < 0.3:
                deps[i].append(svcs[j])
    for i in range(5):
        if rng.random() < 0.5:
            deps[i].append(f"service://{rng.choice(PLATFORM)}")
    # A noisy dependency: anomaly that begins *after* the incident (retry storm).
    noisy = None
    if depth < 4 and rng.random() < 0.6:
        candidates = [i for i in range(depth + 1, 5)]
        if candidates:
            noisy = rng.choice(candidates)

    for i, svc in enumerate(svcs):
        n = names[i]
        cfg, met = f"config://{n}-k{k}", f"metrics://{n}-k{k}"
        status = "degraded" if 0 < i <= depth or i == 0 else "healthy"
        rels = [("OWNED_BY", owners[i]), ("RUNS_ON", f"host://h{k}-{i}"),
                ("HAS_CONFIG", cfg), ("HAS_METRICS", met)]
        rels += [("DEPENDS_ON", d) for d in deps[i]]
        b.obj(svc, "service", f"{n}-k{k}", {"tier": 1 + i // 2, "status": status}, rels,
              text=f"service {n}-k{k}")
        b.obj(f"host://h{k}-{i}", "host", f"h{k}-{i}", {"region": rng.choice(["us-east-1", "eu-west-1"])})
        b.obj(cfg, "config", f"{n}-k{k} config",
              {f: rng.randint(*r) for f, r in CONFIG_FIELDS.items()}, [("OF", svc)])
        base = rng.randint(20, 80)
        if i <= depth:
            _metrics(b, met, svc, base, iso_(starts[i]), base * rng.randint(8, 30))
        elif i == noisy:
            _metrics(b, met, svc, base, iso_(T + rng.randint(2, 20)), base * 3)
        else:
            _metrics(b, met, svc, base)
        # background events, far from the incident
        for j, kind in enumerate(("change", "deploy")):
            at = T + rng.choice([-1, 1]) * rng.randint(6 * 60, 3 * 24 * 60)
            _event(b, rng, f"{kind}://{n}-k{k}-{j}", kind, svc, cfg, rng.choice(people), at)

    rn = names[root]
    root_svc, root_cfg = svcs[root], f"config://{rn}-k{k}"
    a_root = starts[root]
    cause_kind = "change" if rng.random() < 0.5 else "deploy"
    cause = f"{cause_kind}://{rn}-k{k}-cause"
    if cause_kind == "change":
        fld = rng.choice(["max_connections", "pool_size"])
        lo, hi = CONFIG_FIELDS[fld]
        old = rng.randint((lo + hi) // 2, hi)
        cfg_change = (fld, old, max(lo // 4, old // rng.randint(4, 10)))
    else:
        cfg_change = None
    _event(b, rng, cause, cause_kind, root_svc, root_cfg, rng.choice(people),
           a_root - rng.randint(5, 25), cfg_change)
    # root distractors: an older event and a post-anomaly mitigation attempt
    _event(b, rng, f"change://{rn}-k{k}-old", "change", root_svc, root_cfg,
           rng.choice(people), a_root - rng.randint(180, 2000))
    _event(b, rng, f"deploy://{rn}-k{k}-mitigation", "deploy", root_svc, root_cfg,
           rng.choice(people), a_root + rng.randint(3, 60))
    # affected-service trap: a change minutes before the incident
    n0 = names[0]
    trap = f"change://{n0}-k{k}-trap"
    _event(b, rng, trap, "change", svcs[0], f"config://{n0}-k{k}", rng.choice(people),
           rng.randint(starts[root] + 1, T - 1) if T - starts[root] > 2 else T - 1)

    inc = f"incident://inc-k{k}"
    b.obj(inc, "incident", f"elevated errors on {names[0]}-k{k}",
          {"started_at": iso_(T), "severity": rng.choice(["SEV1", "SEV2"]),
           "status": "open", "symptom": f"error rate and latency on {names[0]}-k{k}"},
          [("AFFECTS", svcs[0])], text=f"incident inc-k{k} errors {names[0]}-k{k}")
    old_svc = rng.choice(svcs)
    b.obj(f"incident://inc-k{k}-old", "incident", f"resolved incident on {old_svc}",
          {"started_at": iso_(T - rng.randint(5, 20) * 24 * 60), "severity": "SEV3",
           "status": "resolved", "symptom": "transient errors"},
          [("AFFECTS", old_svc)], text=f"incident inc-k{k}-old resolved")
    c_true, c_false = f"claim://k{k}-h1", f"claim://k{k}-h2"
    # Claim ids are shuffled so the id does not leak the verdict.
    if rng.random() < 0.5:
        c_true, c_false = c_false, c_true
    for c, subj in ((c_true, cause), (c_false, trap)):
        b.obj(c, "claim", f"{subj} caused {inc}",
              {"statement": f"{subj} caused {inc}", "status": "unverified"},
              [("ABOUT", subj), ("ABOUT", inc)], text=f"claim {subj} caused {inc}")

    chain = svcs[: depth + 1]
    useful = [inc, cause, teams[0] if owners[root] == teams[0] else teams[1]]
    useful += [f"metrics://{names[i]}-k{k}" for i in range(1, depth + 1)]
    useful += chain + [c_true, c_false]
    b.db.execute("INSERT INTO truth VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (k, inc, depth, svcs[0], root_svc, cause, owners[root], c_true, c_false,
                  json.dumps(useful)))


def iso_(m: int) -> str:
    from .objects import iso
    return iso(m)


def build_world(n_objects: int, seed: int = 7, cache_dir: str | None = None) -> WorldInfo:
    """Build (or reuse) a world with approximately ``n_objects`` objects."""
    cache_dir = cache_dir or os.environ.get("CVM_CACHE", os.path.join(os.path.dirname(__file__), "..", ".cache"))
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"world_n{n_objects}_s{seed}.sqlite")
    if os.path.exists(path):
        return world_info(path)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    rng = random.Random(seed)
    b = _Builder(db)
    _build_platform(b, rng)
    platform_objs = b.next_id - 1
    n_clusters = max(1, round((n_objects - platform_objs) / OBJECTS_PER_CLUSTER))
    for k in range(n_clusters):
        _build_cluster(b, random.Random(f"{seed}-{k}"), k)
        if len(b.objs) > 50_000:
            b.flush()
    b.flush()
    db.execute("CREATE INDEX rel_src ON relations(src, pred)")
    db.execute("CREATE INDEX rel_dst ON relations(dst, pred)")
    db.execute("INSERT INTO meta VALUES('n_clusters', ?)", (str(n_clusters),))
    db.commit()
    db.close()
    os.replace(tmp, path)
    return world_info(path)


def world_info(path: str) -> WorldInfo:
    db = sqlite3.connect(path)
    n_obj = db.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    n_rel = db.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    n_cl = int(db.execute("SELECT value FROM meta WHERE key='n_clusters'").fetchone()[0])
    db.close()
    return WorldInfo(path, n_obj, n_rel, n_cl)
