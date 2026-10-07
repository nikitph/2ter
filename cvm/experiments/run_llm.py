"""Run CVM (and optionally the tool-calling baseline) with a real LLM processor.

    DEEPSEEK_API_KEY=... python experiments/run_llm.py --provider deepseek \\
        --sizes 1000,1000000 --tasks 30 --conditions cvm,agent --workers 8

Each CVM step is one stateless API call: the prompt is the whole state.
Writes <out-dir>/llm_<tag>.json (summary + per-run metrics),
<out-dir>/llm_<tag>_traces.jsonl (operation traces), and a durable per-task
progress journal. Pass --resume with the same tag and run settings after an
interruption. --max-objects sets the CVM working-set size (default 32).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.experiment import FullContext, make_tasks, run_agent, run_cvm  # noqa: E402
from cvm.resolver import GraphStore  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402

from experiments.run_scale import RESULTS, summarize  # noqa: E402
from experiments.v1_splits import SPLITS, build_cell, cells_for  # noqa: E402


def make_processor(args, domain="incident"):
    if args.provider in ("deepseek", "openai-compatible"):
        from cvm.processors import ChatCompletionsProcessor
        from cvm.processors import CODE_METHOD_HINT, METHOD_HINT
        return ChatCompletionsProcessor(model=args.model or "deepseek-chat",
                                        base_url=args.base_url, api_key_env=args.api_key_env,
                                        system_extra=(CODE_METHOD_HINT if domain == "code" else METHOD_HINT)
                                        if args.hint else "")
    if args.provider == "claude":
        from cvm.processors import ClaudeProcessor
        return ClaudeProcessor(model=args.model or "claude-opus-5-5", effort=args.effort)
    if args.provider == "reference":
        from cvm.processors import CodeReferenceReasoner, ReferenceReasoner
        p = CodeReferenceReasoner() if domain == "code" else ReferenceReasoner()
        p.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "errors": 0}
        return p
    raise SystemExit(f"unknown provider {args.provider}")


def accuracy_by(runs: list[dict], key: str) -> dict:
    """Accuracy per value of ``key`` (e.g. kind, depth), for whatever values occur."""
    out = {}
    for v in sorted({r[key] for r in runs}, key=str):
        group = [r for r in runs if r[key] == v]
        out[v] = sum(r["correct"] for r in group) / len(group)
    return out


def load_progress(path: Path, config: dict) -> dict[tuple[int, str, int], dict]:
    """Read complete journal records, discarding only a torn final line."""
    records = {}
    with path.open("r+b") as source:
        header = source.readline()
        if not header.endswith(b"\n") or json.loads(header) != {"schema": 1, "config": config}:
            raise ValueError(f"progress settings differ or header is damaged: {path}")
        while True:
            offset = source.tell()
            line = source.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                source.truncate(offset)
                break
            record = json.loads(line)
            key = (record["cell_index"], record["condition"], record["task_index"])
            if key in records:
                raise ValueError(f"duplicate progress record {key} in {path}")
            records[key] = record
    return records


def append_progress(path: Path, record: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(record, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--sizes", default="1000,1000000")
    ap.add_argument("--split", choices=list(SPLITS), default=None,
                    help="held-out V1 split; overrides --sizes and selects the domain/world variant")
    ap.add_argument("--tasks", type=int, default=30)
    ap.add_argument("--conditions", default="cvm")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--max-objects", type=int, default=32,
                    help="CVM working-set size (resident objects); applies to the cvm condition only")
    ap.add_argument("--out-dir", default=RESULTS, help="where llm_<tag>.json and traces are written")
    ap.add_argument("--agent-context-limit", type=int, default=120_000,
                    help="tokens; requests above this are not sent (model window)")
    ap.add_argument("--full-context-limit", type=int, default=128_000,
                    help="model window for the one-step full-context baseline")
    ap.add_argument("--tag", default="")
    ap.add_argument("--resume", action="store_true",
                    help="continue a run from its per-task progress journal")
    ap.add_argument("--hint", action="store_true", help="add the investigation-method hint")
    ap.add_argument("--base-url", default="https://api.deepseek.com",
                    help="OpenAI-compatible endpoint, e.g. http://localhost:8000/v1 for vLLM")
    ap.add_argument("--api-key-env", default="DEEPSEEK_API_KEY",
                    help="name of the env var holding the API key (any non-empty value for local vLLM)")
    args = ap.parse_args(argv)
    model = args.model or {"deepseek": "deepseek-chat", "claude": "claude-opus-5-5"}.get(
        args.provider, args.provider)
    tag = args.tag or model
    if args.max_objects < 1:
        ap.error("--max-objects must be >= 1")
    conditions = args.conditions.split(",")
    unknown = [c for c in conditions if c not in ("cvm", "agent", "full")]
    if unknown:
        ap.error(f"unsupported condition(s) {unknown}; run_llm.py supports cvm, agent and full")
    if "agent" in conditions and args.max_objects != 32:
        print("note: --max-objects applies to the cvm condition only; "
              "the agent baseline keeps an unbounded transcript", file=sys.stderr)
    report = {"provider": args.provider, "model": model, "method_hint": args.hint,
              "tasks_per_size": args.tasks, "max_steps": args.max_steps,
              "max_objects": args.max_objects, "split": args.split, "sizes": []}
    os.makedirs(args.out_dir, exist_ok=True)
    progress_path = Path(args.out_dir) / f"llm_{tag}_progress.jsonl"
    config = {key: value for key, value in vars(args).items()
              if key not in ("workers", "out_dir", "tag", "resume")}
    if args.resume:
        if not progress_path.is_file():
            ap.error(f"no progress journal to resume: {progress_path}")
        completed = load_progress(progress_path, config)
    else:
        if progress_path.exists():
            ap.error(f"progress journal already exists: {progress_path}; use --resume or a new --tag")
        completed = {}
        progress_path.touch()
        append_progress(progress_path, {"schema": 1, "config": config})
    traces_path = Path(args.out_dir) / f"llm_{tag}_traces.jsonl"
    traces_path.write_text("")
    cells = cells_for(args.split) if args.split else (None,) * len(args.sizes.split(","))
    sizes = [int(x) for x in args.sizes.split(",")] if not args.split else []
    for i, cell in enumerate(cells):
        if cell:
            w, store, tasks = build_cell(cell, args.tasks)
            domain = cell.domain
            max_objects = cell.max_objects if cell.split == "tight" else args.max_objects
        else:
            n = sizes[i]
            w = build_world(n)
            store = GraphStore(w.path)
            tasks = make_tasks(store, args.tasks, seed=n)
            domain = "incident"
            max_objects = args.max_objects
        entry = {"world_objects": w.n_objects, "conditions": {},
                 "split": cell.split if cell else None, "domain": domain,
                 "max_objects": max_objects}
        for cond in conditions:
            t0 = time.time()
            full = FullContext(store, w.n_objects, context_limit=args.full_context_limit) if cond == "full" else None

            for j, spec in enumerate(tasks):
                saved = completed.get((i, cond, j))
                if saved and (saved["task"] != spec.task.text or
                              saved["expected"] != spec.expected):
                    raise ValueError(f"progress task mismatch at cell {i}, {cond}, task {j}")

            def one(spec):
                proc = make_processor(args, domain)
                ctxs = []
                if cond == "cvm":
                    m = run_cvm(store, spec, proc, w.n_objects, max_steps=args.max_steps,
                                max_objects=max_objects, keep_ctx=ctxs)
                elif cond == "agent":
                    m = run_agent(store, spec, proc, w.n_objects,
                                  context_limit=args.agent_context_limit,
                                  max_steps=args.max_steps, keep_ctx=ctxs)
                else:
                    m = full.run(spec, proc)
                m["llm_input_tokens"] = proc.usage["input_tokens"]
                m["llm_output_tokens"] = proc.usage["output_tokens"]
                m["llm_calls"] = proc.usage["calls"]
                m["llm_errors"] = proc.usage.get("errors", 0)
                c = ctxs[0] if ctxs else full.ctx
                print(f"  [{cond}] {spec.task.kind:<10} d={spec.depth} correct={m['correct']} "
                      f"steps={m['steps']} answer={m['answer']}", flush=True)
                return m, {"world_objects": w.n_objects, "condition": cond,
                           "task": spec.task.text, "expected": spec.expected,
                           "answer": m["answer"], "support": list(c.answer_support) if c else [],
                           "trace": list(c.trace) if c else [], "notes": dict(c.notes) if c else {}}

            missing = [(j, spec) for j, spec in enumerate(tasks)
                       if (i, cond, j) not in completed]
            errors = []
            with ThreadPoolExecutor(1 if cond == "full" else args.workers) as ex:
                futures = {ex.submit(one, spec): (j, spec) for j, spec in missing}
                for future in as_completed(futures):
                    j, spec = futures[future]
                    try:
                        metrics, trace = future.result()
                    except Exception as exc:
                        errors.append(exc)
                        continue
                    record = {"cell_index": i, "condition": cond, "task_index": j,
                              "task": spec.task.text, "expected": spec.expected,
                              "metrics": metrics, "trace": trace}
                    append_progress(progress_path, record)
                    completed[(i, cond, j)] = record
            if errors:
                raise errors[0]
            records = [completed[(i, cond, j)] for j in range(len(tasks))]
            results = [(record["metrics"], record["trace"]) for record in records]
            runs = [m for m, _ in results]
            with traces_path.open("a") as traces:
                for _, tr in results:
                    traces.write(json.dumps(tr) + "\n")
            s = summarize(runs)
            s.update({
                "llm_input_tokens_mean": sum(r["llm_input_tokens"] for r in runs) / len(runs),
                "llm_output_tokens_mean": sum(r["llm_output_tokens"] for r in runs) / len(runs),
                "llm_calls_mean": sum(r["llm_calls"] for r in runs) / len(runs),
                "llm_errors": sum(r["llm_errors"] for r in runs),
                "invalid_ops_mean": sum(r.get("invalid_ops", 0) for r in runs) / len(runs),
                "aborted": sum(r.get("aborted", 0) for r in runs),
                "abstained": sum(1 for r in runs if r["answer"] in (None, "UNKNOWN")),
                "accuracy_by_kind": accuracy_by(runs, "kind"),
                "accuracy_by_depth": accuracy_by(runs, "depth"),
                "wall_seconds": round(time.time() - t0, 1),
            })
            entry["conditions"][cond] = s
            if full:
                s["full_context_est_tokens"] = full.est_tokens
                s["full_context_limit"] = args.full_context_limit
            entry.setdefault("runs", []).extend(runs)
            print(f"N={w.n_objects:>8} {cond:<6} acc={s['accuracy']:.2f} "
                  f"peakObj={s['peak_resident_objects_mean']:.1f} "
                  f"peakTok={s['peak_prompt_tokens_mean']:.0f} steps={s['steps_mean']:.1f} "
                  f"unsupported={s['unsupported_claim_rate']:.2f} thrash={s['thrash_rate_mean'] or 0:.2f} "
                  f"faultPrec={s['fault_precision_mean'] or 0:.2f} invalid={s['invalid_ops_mean']:.1f} "
                  f"stepLimit={s['step_limit']} aborted={s['aborted']} overflow={s['context_overflow']} "
                  f"in_tok={s['llm_input_tokens_mean']:.0f} ({s['wall_seconds']}s)", flush=True)
        report["sizes"].append(entry)
        report_path = Path(args.out_dir) / f"llm_{tag}.json"
        temp_path = report_path.with_suffix(".json.tmp")
        with temp_path.open("w") as f:
            json.dump(report, f, indent=1, default=str)
        os.replace(temp_path, report_path)
        store.db.close()


if __name__ == "__main__":
    main()
