"""Held-out code-repository world; never used by the M1 training exporter.

Each bug points to a failing test, which covers an entry file. Following the
file import chain reaches a root file. The cause is the newest commit to that
root file before the first failure. Recent commits on the entry file and
post-failure commits on the root file are decoys.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3

from .synthetic_world import WorldInfo, _Builder, iso_, world_info

SCHEMA = """
CREATE TABLE objects(id INTEGER PRIMARY KEY, ref TEXT UNIQUE, type TEXT,
                     label TEXT, attrs TEXT, version INTEGER);
CREATE TABLE relations(src TEXT, pred TEXT, dst TEXT);
CREATE TABLE truth(cluster INTEGER PRIMARY KEY, bug TEXT, depth INTEGER,
                   entry TEXT, root TEXT, cause TEXT, useful TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE search USING fts5(ns UNINDEXED, body,
    tokenize="unicode61 tokenchars '-_'");
"""
OBJECTS_PER_CLUSTER = 13


def _build_cluster(b: _Builder, seed: int, k: int) -> None:
    rng = random.Random(f"{seed}-{k}")
    depth = 1 + k % 3
    t = rng.randint(3 * 24 * 60, 28 * 24 * 60)
    repo = f"repo://project-k{k}"
    bug = f"bug://k{k}"
    test = f"test://project-k{k}/failure"
    files = [f"file://project-k{k}/{name}.py" for name in
             ["app", *(f"lib{i}" for i in range(1, depth + 1))]]
    symbols = [f"symbol://project-k{k}/{name}" for name in
               ["entry", *(f"helper{i}" for i in range(1, depth + 1))]]
    root = files[-1]
    cause = f"commit://project-k{k}-cause"
    old = f"commit://project-k{k}-old"
    post = f"commit://project-k{k}-post"
    entry_decoy = f"commit://project-k{k}-entry-decoy"

    b.obj(repo, "repo", f"project-k{k}", {"branch": "main"},
          [("CONTAINS", ref) for ref in files], text=f"project-k{k} repository")
    b.obj(bug, "bug", f"failure in project-k{k}",
          {"first_failure": iso_(t), "status": "open"},
          [("FAILING_TEST", test), ("IN_REPO", repo)], text=f"project-k{k} failure")
    b.obj(test, "test", f"test failure project-k{k}", {"status": "failing"},
          [("COVERS", files[0])], text=f"failing test for {files[0]}")
    for i, ref in enumerate(files):
        rels = [("DEFINES", symbols[i])]
        if i < depth:
            rels.append(("IMPORTS", files[i + 1]))
        if i == 0:
            rels.append(("CHANGED_IN", entry_decoy))
        if i == depth:
            rels += [("CHANGED_IN", x) for x in (old, cause, post)]
        b.obj(ref, "file", ref.rsplit("/", 1)[-1], {"language": "python"}, rels,
              text=f"project-k{k} source file")
        b.obj(symbols[i], "symbol", symbols[i].rsplit("/", 1)[-1],
              {"kind": "function"},
              [("DEFINED_IN", ref)] + ([("CALLS", symbols[i + 1])] if i < depth else []),
              text=f"function in {ref}")
    for ref, at, message in (
        (old, t - rng.randint(300, 900), "old root change"),
        (cause, t - rng.randint(10, 30), "root regression"),
        (post, t + rng.randint(3, 30), "post-failure root fix"),
        (entry_decoy, t - rng.randint(1, 5), "recent entry change"),
    ):
        b.obj(ref, "commit", message, {"at": iso_(at), "message": message},
              [("TOUCHES", files[0] if ref == entry_decoy else root)],
              text=f"commit {message} project-k{k}")
    useful = [bug, test, *files, cause, old, post]
    b.db.execute("INSERT INTO truth VALUES(?,?,?,?,?,?,?)",
                 (k, bug, depth, files[0], root, cause, json.dumps(useful)))


def build_code_world(n_objects: int, seed: int = 7,
                     cache_dir: str | None = None) -> WorldInfo:
    if n_objects < 1:
        raise ValueError("n_objects must be positive")
    cache_dir = cache_dir or os.environ.get(
        "CVM_CACHE", os.path.join(os.path.dirname(__file__), "..", ".cache"))
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"code_n{n_objects}_s{seed}.sqlite")
    if os.path.exists(path):
        return world_info(path)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA)
        b = _Builder(db)
        n_clusters = max(1, round(n_objects / OBJECTS_PER_CLUSTER))
        for k in range(n_clusters):
            _build_cluster(b, seed, k)
            if len(b.objs) > 50_000:
                b.flush()
        b.flush()
        db.execute("CREATE INDEX rel_src ON relations(src, pred)")
        db.execute("CREATE INDEX rel_dst ON relations(dst, pred)")
        db.execute("INSERT INTO meta VALUES('n_clusters', ?)", (str(n_clusters),))
        db.commit()
    finally:
        db.close()
    os.replace(tmp, path)
    return world_info(path)
