"""Processors: anything that maps a prompt string to one CVM operation.

``ReferenceReasoner``  deterministic, *stateless* policy that parses the
                       rendered prompt text and nothing else. It stands in for
                       an ideal fault-issuing model so the substrate can be
                       measured without LLM noise. It never reads the store.
``Hallucinator``       answers from priors without dereferencing; used to show
                       the provenance verifier rejecting unsupported claims.
``ClaudeProcessor``    the same contract served by a Claude model via the
                       Anthropic SDK (structured JSON output, one op per call,
                       no conversation history: the prompt IS the state).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

FACT_RE = re.compile(r"^\s+\[(fact:\d+)\] (\S+) (=|->) (.*)$")
HANDLE_RE = re.compile(r"^\s+(\S+://\S+)\s+\(via (.*)\)$")
REF_RE = re.compile(r"[a-z]+://[A-Za-z0-9_\-./]+")


# ----------------------------------------------------------------------
# prompt parsing
# ----------------------------------------------------------------------
@dataclass
class KB:
    task_kind: str = ""
    task_text: str = ""
    target: str = ""
    closed_world: bool = False
    objects: dict = field(default_factory=dict)   # ref -> {"type", field -> [(value, fid)]}
    truncated: set = field(default_factory=set)   # (ref, pred) with hidden relations
    handles: list = field(default_factory=list)   # (ref, via)
    notes: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    last_result: str = ""
    ops: set = field(default_factory=set)

    def fields(self, ref):
        return self.objects.get(ref, {}).get("fields", {})


def parse_prompt(prompt: str) -> KB:
    kb = KB()
    section = None
    cur = None
    lines = prompt.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("TASK "):
            m = re.search(r"\[(\w+)\]", line)
            kb.task_kind = m.group(1) if m else ""
            kb.task_text = lines[i + 1].strip() if i + 1 < len(lines) else ""
            refs = REF_RE.findall(kb.task_text)
            kb.target = refs[0].rstrip(".?") if refs else ""
            section = None
            continue
        if line.startswith("WORLD: closed"):
            kb.closed_world = True
            continue
        if line.startswith("RESIDENT OBJECTS"):
            section = "objects"; continue
        if line.startswith("HANDLES"):
            section = "handles"; continue
        if line.startswith("NOTES"):
            section = "notes"; continue
        if line.startswith("RECENT OPERATIONS"):
            section = "trace"; continue
        if line.startswith("LAST RESULT"):
            section = "last"; continue
        if line.startswith("AVAILABLE OPERATIONS"):
            section = "ops"; continue
        if line.startswith("RULES"):
            section = None; continue
        if not line.strip() or line.strip() == "(none)":
            continue
        if section == "objects":
            if not line.startswith(" "):
                parts = line.split()
                cur = parts[0]
                typ = parts[1].strip("[]") if len(parts) > 1 else ""
                kb.objects[cur] = {"type": typ, "fields": {}}
                continue
            m = FACT_RE.match(line)
            if m and cur:
                fid, fld, _, val = m.groups()
                kb.objects[cur]["fields"].setdefault(fld, []).append((val, fid))
                continue
            m = re.match(r"^\s+\((\S+): \+\d+ more", line)
            if m and cur:
                kb.truncated.add((cur, m.group(1)))
        elif section == "handles":
            m = HANDLE_RE.match(line)
            if m:
                kb.handles.append((m.group(1), m.group(2)))
        elif section == "notes":
            k, _, v = line.strip().partition(" = ")
            kb.notes[k] = v
        elif section == "trace":
            kb.trace.append(line.strip())
        elif section == "last":
            kb.last_result = line.strip()
        elif section == "ops":
            kb.ops.add(line.strip().split("(")[0])
    return kb


# ----------------------------------------------------------------------
# reference reasoner
# ----------------------------------------------------------------------
class Need(Exception):
    def __init__(self, action: dict):
        self.action = action


class _Policy:
    def __init__(self, kb: KB):
        self.kb = kb
        self.support: list[str] = []
        self.writes: dict[str, str] = {}

    # -- notes ---------------------------------------------------------
    def note(self, key):
        v = self.writes.get(key) or self.kb.notes.get(key)
        if v is None:
            return None
        val, _, fids = v.partition("|")
        return val.strip(), [f.strip() for f in fids.split(",") if f.strip()]

    def remember(self, key, val, fids):
        if key not in self.kb.notes and "WRITE" in self.kb.ops:
            self.writes[key] = f"{val} | {','.join(fids)}" if fids else str(val)

    # -- primitive lookups (resident -> notes -> Need) ----------------
    def attr(self, ref, fld, why):
        fs = self.kb.fields(ref).get(fld)
        if fs:
            return fs[0][0], [fs[0][1]]
        raise Need({"op": "FAULT", "ref": ref, "reason": why})

    def rel(self, ref, pred, why, persist=False):
        key = f"{ref}.{pred}"
        n = self.note(key)
        if n:
            return [r for r in n[0].split(",") if r], n[1]
        fs = self.kb.fields(ref).get(pred)
        if fs is not None and (ref, pred) not in self.kb.truncated:
            vals, fids = [v for v, _ in fs], [f for _, f in fs]
        else:
            hs = [(r, via.split()[0]) for r, via in self.kb.handles
                  if via.endswith(f" {ref} {pred}")]
            done = any(f"TRAVERSE {ref} {pred} ->" in t for t in self.kb.trace)
            if not hs and not done:
                if self.kb.closed_world:
                    return [], []
                raise Need({"op": "TRAVERSE", "ref": ref, "relation": pred})
            vals, fids = [r for r, _ in hs], [f for _, f in hs]
        if persist:
            self.remember(key, ",".join(vals), fids)
        return vals, fids

    # -- domain derivations --------------------------------------------
    def incident(self, inc):
        n = self.note(f"{inc}.facts")
        if n:
            start, affected = n[0].split(" ")
            return start, affected, n[1]
        start, f1 = self.attr(inc, "started_at", "need incident start time")
        aff, f2 = self.rel(inc, "AFFECTS", "need affected service")
        self.remember(f"{inc}.facts", f"{start} {aff[0]}", f1 + f2[:1])
        return start, aff[0], f1 + f2[:1]

    def status(self, svc):
        """('anomalous', start) | ('normal', None), with supporting fact ids."""
        n = self.note(f"status:{svc}")
        if n:
            st, _, at = n[0].partition("@")
            return st, (at or None), n[1]
        mets, fm = self.rel(svc, "HAS_METRICS", "need metrics handle")
        if not mets:
            return "normal", None, []
        m = mets[0]
        st, f1 = self.attr(m, "status",
                           f"need latency status of {svc} to test whether it degraded first")
        fids = fm + f1
        at = None
        if st == "anomalous":
            at, f2 = self.attr(m, "anomaly_start", "need anomaly onset")
            fids += f2
        self.remember(f"status:{svc}", f"{st}@{at}" if at else st, fids)
        return st, at, fids

    def root_service(self, affected, start, base_fids):
        """Walk the dependency graph following anomalies that started earlier."""
        frontier, fstart = affected, start
        support = list(base_fids)
        for _ in range(12):
            deps, fd = self.rel(frontier, "DEPENDS_ON", "need dependencies", persist=True)
            best = None
            for d in deps:
                st, at, fids = self.status(d)
                if st == "anomalous" and at and at < fstart and (best is None or at < best[1]):
                    best = (d, at, fids, fd[deps.index(d)] if deps.index(d) < len(fd) else None)
            if best is None:
                return frontier, fstart, support
            frontier, fstart = best[0], best[1]
            support += best[2] + ([best[3]] if best[3] else [])
        return frontier, fstart, support

    def search_done(self, ns, q):
        return any(t.split(" ", 1)[1].startswith(f"SEARCH {ns} '{q}' -> ok") for t in self.kb.trace
                   if " " in t)

    def search_denied(self, ns):
        return any(f"SEARCH {ns}" in t and "CAPABILITY_FAULT" in t for t in self.kb.trace)

    def events_of(self, root):
        n = self.note(f"events:{root}")
        if n:
            return [r for r in n[0].split(",") if r]
        if self.kb.closed_world:
            return [r for r, o in self.kb.objects.items()
                    if o["type"] in ("change", "deploy")
                    and any(v == root for v, _ in o["fields"].get("TARGETS", []))]
        refs: list[str] = []
        for ns in ("change://", "deploy://"):
            if self.search_denied(ns) or "SEARCH" not in self.kb.ops:
                continue
            q = root
            hs = [r for r, via in self.kb.handles if via == f"SEARCH {ns} '{q}'"]
            if not hs and not self.search_done(ns, q):
                raise Need({"op": "SEARCH", "namespace": ns, "query": q})
            refs += hs
        if self.search_denied("change://") or "SEARCH" not in self.kb.ops:
            inv, _ = self.rel(root, "~TARGETS", "find events targeting root")
            refs += inv
        refs = list(dict.fromkeys(refs))
        self.remember(f"events:{root}", ",".join(refs), [])
        return refs

    def event(self, ev):
        n = self.note(f"event:{ev}")
        if n:
            tgt, at = n[0].split(" ")
            return tgt, at, n[1]
        at, f1 = self.attr(ev, "at", "need event time to order it against anomaly onset")
        tgt, f2 = self.rel(ev, "TARGETS", "need event target")
        from .objects import iso
        at_iso = iso(int(at)) if at.lstrip("-").isdigit() else at
        self.remember(f"event:{ev}", f"{tgt[0]} {at_iso}", f1 + f2[:1])
        return tgt[0], at_iso, f1 + f2[:1]

    def cause(self, inc):
        start, affected, f_inc = self.incident(inc)
        root, rstart, f_chain = self.root_service(affected, start, f_inc)
        best = None
        for ev in self.events_of(root):
            tgt, at, fids = self.event(ev)
            if tgt == root and at < rstart and (best is None or at > best[1]):
                best = (ev, at, fids)
        if best is None:
            return None, root, f_chain
        return best[0], root, f_chain + best[2]

    def claim_parts(self, claim):
        n = self.note(f"claim:{claim}")
        if n:
            subj, inc = n[0].split(" ")
            return subj, inc, n[1]
        if claim not in self.kb.objects:
            raise Need({"op": "EVIDENCE", "ref": claim})
        about = self.kb.fields(claim).get("ABOUT", [])
        subj = [(v, f) for v, f in about if not v.startswith("incident://")]
        inc = [(v, f) for v, f in about if v.startswith("incident://")]
        fids = [subj[0][1], inc[0][1]]
        self.remember(f"claim:{claim}", f"{subj[0][0]} {inc[0][0]}", fids)
        return subj[0][0], inc[0][0], fids

    # -- top level -----------------------------------------------------
    def solve(self):
        kind, tgt = self.kb.task_kind, self.kb.target
        if kind == "root_cause":
            ev, _, fids = self.cause(tgt)
            return (ev or "UNKNOWN"), fids
        if kind == "owner":
            start, affected, f_inc = self.incident(tgt)
            root, _, f_chain = self.root_service(affected, start, f_inc)
            owner, fo = self.rel(root, "OWNED_BY", "need owner of root service")
            return owner[0], f_chain + fo[:1]
        if kind == "claim":
            subj, inc, f_claim = self.claim_parts(tgt)
            ev, _, fids = self.cause(inc)
            verdict = "SUPPORTED" if ev == subj else "CONTRADICTED"
            return verdict, f_claim + fids
        return "UNKNOWN", []

    def guess(self):
        """Best effort when dereferencing is impossible (one-shot conditions)."""
        kb = self.kb
        inc = kb.target
        if kb.task_kind == "claim":
            about = kb.fields(inc).get("ABOUT", [])
            subj = next(((v, f) for v, f in about if not v.startswith("incident://")), None)
            incs = [v for v, _ in about if v.startswith("incident://")]
            inc = incs[0] if incs else ""
        start = (kb.fields(inc).get("started_at") or [("9999", None)])[0]
        cands = []
        for r, o in kb.objects.items():
            if o["type"] in ("change", "deploy") and "at" in o["fields"]:
                from .objects import iso
                at, fid = o["fields"]["at"][0]
                at = iso(int(at)) if at.lstrip("-").isdigit() else at
                if at < start[0]:
                    cands.append((at, r, fid))
        cands.sort()
        if kb.task_kind == "root_cause":
            if cands:
                return cands[-1][1], [cands[-1][2]]
            return "UNKNOWN", []
        if kb.task_kind == "owner":
            aff = kb.fields(inc).get("AFFECTS", [])
            if aff:
                own = kb.fields(aff[0][0]).get("OWNED_BY", [])
                if own:
                    return own[0][0], [own[0][1]]
            return "UNKNOWN", []
        if kb.task_kind == "claim" and subj:
            latest = cands[-1][1] if cands else None
            v = "SUPPORTED" if latest == subj[0] else "CONTRADICTED"
            return v, [subj[1]]
        return "UNKNOWN", []

    def decide(self) -> dict:
        try:
            value, support = self.solve()
        except Need as n:
            if self.writes:
                return {"op": "WRITE", "entries": self.writes}
            if n.action["op"] in self.kb.ops:
                return n.action
            value, support = self.guess()
            return {"op": "ANSWER", "value": value, "support": support}
        return {"op": "ANSWER", "value": value,
                "support": list(dict.fromkeys(f for f in support if f))}


class ReferenceReasoner:
    """Stateless: ``step`` is a pure function of the prompt text."""

    def step(self, prompt: str) -> dict:
        return _Policy(parse_prompt(prompt)).decide()


class _CodePolicy:
    """Prompt-only reference policy for the held-out code-repository domain."""

    def __init__(self, kb: KB):
        self.kb = kb
        self.writes: dict[str, str] = {}

    def fields(self, ref: str, field: str) -> tuple[list[str], list[str]]:
        key = f"code:{ref}.{field}"
        note = self.kb.notes.get(key)
        if note is not None:
            values, _, ids = note.partition("|")
            values = values.strip()
            return ([] if values == "-" else values.split(",")), [x.strip() for x in ids.split(",") if x.strip()]
        if ref not in self.kb.objects:
            raise Need({"op": "FAULT", "ref": ref, "reason": f"need {field} from {ref}"})
        pairs = self.kb.fields(ref).get(field, [])
        values = [v for v, _ in pairs]
        ids = [fid for _, fid in pairs]
        if "WRITE" in self.kb.ops:
            self.writes[key] = f"{','.join(values) if values else '-'} | {','.join(ids)}"
        return values, ids

    def solve(self) -> tuple[str, list[str]]:
        bug = self.kb.target
        failures, f0 = self.fields(bug, "first_failure")
        tests, f1 = self.fields(bug, "FAILING_TEST")
        if not failures or not tests:
            return "UNKNOWN", f0 + f1
        files, f2 = self.fields(tests[0], "COVERS")
        if not files:
            return "UNKNOWN", f0 + f1 + f2
        support = f0 + f1 + f2
        file = files[0]
        for _ in range(12):
            imported, ids = self.fields(file, "IMPORTS")
            support += ids
            if not imported:
                break
            file = imported[0]
        else:
            return "UNKNOWN", support
        commits, ids = self.fields(file, "CHANGED_IN")
        support += ids
        best: tuple[str, str, list[str]] | None = None
        for commit in commits:
            times, time_ids = self.fields(commit, "at")
            if times and times[0] < failures[0] and (best is None or times[0] > best[1]):
                best = commit, times[0], time_ids
        if best is None:
            return "UNKNOWN", support
        return best[0], list(dict.fromkeys(support + best[2]))

    def decide(self) -> dict:
        try:
            answer, support = self.solve()
        except Need as needed:
            if self.writes:
                return {"op": "WRITE", "entries": self.writes}
            return needed.action
        if self.writes:
            return {"op": "WRITE", "entries": self.writes}
        return {"op": "ANSWER", "value": answer, "support": support}


class CodeReferenceReasoner:
    """Stateless validator for domain2; excluded from training data export."""

    def step(self, prompt: str) -> dict:
        return _CodePolicy(parse_prompt(prompt)).decide()


class Hallucinator:
    """Asserts a plausible answer immediately, citing nothing (or made-up ids)."""

    def __init__(self, fabricate_ids: bool = True):
        self.fabricate_ids = fabricate_ids

    def step(self, prompt: str) -> dict:
        kb = parse_prompt(prompt)
        name = kb.target.split("://")[1] if kb.target else "x"
        guess = {"root_cause": f"change://{name}-probable-config-change",
                 "owner": "team://platform", "claim": "SUPPORTED"}.get(kb.task_kind, "UNKNOWN")
        return {"op": "ANSWER", "value": guess,
                "support": ["fact:99999"] if self.fabricate_ids else []}


# ----------------------------------------------------------------------
# Claude
# ----------------------------------------------------------------------
SYSTEM = """You are the processor in a Cognitive Virtual Memory runtime.
You do not carry the world in your context: you operate inside an address space
managed by the runtime. Each turn you are shown ONLY the current resident view of
your context (resident objects, handles, notes, recent operations). You have no
other memory between turns, so WRITE any conclusion you will need later, with
the fact ids that support it.

Emit exactly ONE operation per turn as JSON. Never assert external state that is
not resident: if you need it, FAULT it (or TRAVERSE/SEARCH to discover refs).
Your final ANSWER must cite the fact ids ([fact:N]) that support it; the runtime
rejects answers whose support was never materialized in this context.

Field usage by op (leave unused fields as "" / [] / {}):
  READ      ref, field
  TRAVERSE  ref, relation (e.g. DEPENDS_ON, HAS_METRICS, ~TARGETS), page
  SEARCH    namespace (e.g. "change://"), query
  FAULT     ref, field (optional), reason
  EVIDENCE  ref
  WRITE     entries: list of {key, value}
  ANSWER    value (a ref, or SUPPORTED / CONTRADICTED, or UNKNOWN), support"""

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string",
               "enum": ["READ", "TRAVERSE", "SEARCH", "FAULT", "EVIDENCE", "WRITE", "ANSWER"]},
        "ref": {"type": "string"},
        "field": {"type": "string"},
        "relation": {"type": "string"},
        "page": {"type": "integer"},
        "namespace": {"type": "string"},
        "query": {"type": "string"},
        "reason": {"type": "string"},
        "entries": {"type": "array", "items": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"], "additionalProperties": False}},
        "value": {"type": "string"},
        "support": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["op", "ref", "field", "relation", "page", "namespace", "query", "reason",
                 "entries", "value", "support"],
    "additionalProperties": False,
}


class ClaudeProcessor:
    """One stateless Messages API call per CVM step (requires ANTHROPIC_API_KEY)."""

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "low", client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def step(self, prompt: str) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": ACTION_SCHEMA}},
        )
        self.usage["calls"] += 1
        self.usage["input_tokens"] += resp.usage.input_tokens
        self.usage["output_tokens"] += resp.usage.output_tokens
        if resp.stop_reason == "refusal":
            return {"op": "ANSWER", "value": "UNKNOWN", "support": []}
        text = next(b.text for b in resp.content if b.type == "text")
        return normalize_action(json.loads(text))


def normalize_action(a: dict) -> dict:
    """Map the flat structured-output record onto the runtime's action dict."""
    out = {k: v for k, v in a.items() if v not in ("", [], {}, None)}
    out["op"] = a.get("op", "")
    if isinstance(a.get("entries"), list):
        out["entries"] = {e["key"]: e["value"] for e in a["entries"]
                          if isinstance(e, dict) and "key" in e}
    if isinstance(out.get("op"), str):
        out["op"] = out["op"].upper()
    if out["op"] == "ANSWER":
        out.setdefault("support", [])
        out["support"] = [str(s).strip("[] ") for s in out["support"]]
        if out.get("value") is not None:
            out["value"] = str(out["value"]).strip()
    return out


# ----------------------------------------------------------------------
# OpenAI-compatible chat endpoints (DeepSeek and similar)
# ----------------------------------------------------------------------
JSON_FORMAT_NOTE = """
Respond with a single JSON object, for example:
  {"op": "FAULT", "ref": "metrics://x", "reason": "need latency onset"}
  {"op": "TRAVERSE", "ref": "service://x", "relation": "DEPENDS_ON"}
  {"op": "SEARCH", "namespace": "change://", "query": "service://x"}
  {"op": "WRITE", "entries": {"status:service://x": "anomalous@2026-03-01T10:00Z | fact:7,fact:9"}}
  {"op": "ANSWER", "value": "change://y", "support": ["fact:3", "fact:12"]}"""


class ChatCompletionsProcessor:
    """One stateless chat-completions call per CVM step (JSON mode).

    Works with any OpenAI-compatible endpoint; defaults target DeepSeek. The API
    key is read from the environment and never stored elsewhere.
    """

    def __init__(self, model: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com",
                 api_key_env: str = "DEEPSEEK_API_KEY", transport=None,
                 temperature: float = 0.0, max_tokens: int = 8192, retries: int = 4,
                 system_extra: str = ""):
        import os
        self.model = model
        base = base_url.rstrip("/")
        self.url = base + ("/chat/completions" if base.endswith("/v1") or "deepseek" in base
                           else "/v1/chat/completions" if "localhost" in base or "127.0.0.1" in base
                           else "/chat/completions")
        self.key = os.environ.get(api_key_env, "") if transport is None else "test"
        if not self.key:
            raise RuntimeError(f"{api_key_env} is not set")
        self.transport = transport or self._post
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries
        self.system = SYSTEM_OPENAI + (("\n\n" + system_extra) if system_extra else "")
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "errors": 0}

    def _post(self, body: dict) -> dict:
        import urllib.request
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())

    def step(self, prompt: str) -> dict:
        import time
        import urllib.error
        body = {"model": self.model,
                "messages": [{"role": "system", "content": self.system},
                             {"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": self.temperature,
                "max_tokens": self.max_tokens}
        for attempt in range(self.retries + 1):
            try:
                resp = self.transport(body)
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                self.usage["errors"] += 1
                detail = e.read()[:300].decode(errors="replace") if hasattr(e, "read") else ""
                return {"op": "ABORT", "error": f"HTTP {e.code} {detail}"}
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                self.usage["errors"] += 1
                return {"op": "ABORT", "error": f"transport: {e}"}
        self.usage["calls"] += 1
        u = resp.get("usage") or {}
        self.usage["input_tokens"] += u.get("prompt_tokens", 0)
        self.usage["output_tokens"] += u.get("completion_tokens", 0)
        text = resp["choices"][0]["message"].get("content") or ""
        a = first_json_object(text)
        if a is None:
            self.usage["parse_errors"] = self.usage.get("parse_errors", 0) + 1
            return {"op": "INVALID", "error": f"no JSON object in output: {text[:80]!r}"}
        return normalize_action(a)


def first_json_object(text: str):
    """Parse the first JSON object in ``text``; models sometimes append stray tokens."""
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    return None


SYSTEM_OPENAI = SYSTEM.split("Field usage by op")[0] + """Operations and their JSON fields:
  READ      {"op":"READ","ref":...,"field":...}
  TRAVERSE  {"op":"TRAVERSE","ref":...,"relation":...,"page":0}   relation e.g. DEPENDS_ON, HAS_METRICS; prefix ~ for inverse (e.g. ~TARGETS)
  SEARCH    {"op":"SEARCH","namespace":"change://","query":...}
  FAULT     {"op":"FAULT","ref":...,"reason":...}                 makes the object resident
  EVIDENCE  {"op":"EVIDENCE","ref":"claim://..."}
  WRITE     {"op":"WRITE","entries":{key: value}}                persists notes across turns
  ANSWER    {"op":"ANSWER","value":...,"support":["fact:N",...]} value is a ref, SUPPORTED, CONTRADICTED or UNKNOWN
""" + JSON_FORMAT_NOTE


# Optional domain method, used only in the "method-hinted" variant of the LLM
# experiment to separate "cannot reason" from "does not know the procedure".
METHOD_HINT = """Investigation method for incidents:
1. From the incident, note started_at and the AFFECTED service.
2. TRAVERSE the service's DEPENDS_ON. For each dependency, TRAVERSE HAS_METRICS and
   FAULT the metrics object: is it anomalous, and when did the anomaly start?
3. Follow the dependency whose anomaly started EARLIEST and before the current
   service's onset; repeat from it. Anomalies that start later are effects, not causes.
4. The root service is the deepest anomalous service with no earlier-anomalous dependency.
5. SEARCH change:// and deploy:// for the root service ref; FAULT each candidate.
   The cause is the latest change/deploy TARGETING the root service before ITS anomaly
   onset. Changes on other services, or after the onset, are not the cause.
6. WRITE each conclusion (with fact ids) as you go; resident objects may be evicted."""

CODE_METHOD_HINT = """Investigation method for code repositories:
1. FAULT the bug and follow FAILING_TEST to the failing test, then COVERS to its entry file.
2. Follow IMPORTS through the file chain. The terminal imported file is the root.
3. Compare CHANGED_IN commits on that root file with the bug's first_failure time.
   Choose the latest commit before the failure. A recent entry-file commit and a
   post-failure root-file commit are decoys.
4. WRITE conclusions with fact ids before objects are evicted; cite facts in ANSWER."""
