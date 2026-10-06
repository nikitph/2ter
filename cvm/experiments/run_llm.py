"""Run CVM (and optionally the tool-calling baseline) with a real LLM processor.

    DEEPSEEK_API_KEY=... python experiments/run_llm.py --provider deepseek \\
        --sizes 1000,1000000 --tasks 30 --conditions cvm,agent --workers 8

Each CVM step is one stateless API call: the prompt is the whole state.
Writes <out-dir>/llm_<tag>.json (summary + per-run metrics) and
<out-dir>/llm_<tag>_traces.jsonl (operation trace of every run); out-dir defaults
to results/. --max-objects sets the CVM working-set size (default 32).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.experiment import make_tasks, run_agent, run_cvm  # noqa: E402
from cvm.resolver import GraphStore  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402

from experiments.run_scale import RESULTS, summarize  # noqa: E402


def make_processor(args):
    if args.provider in ("deepseek", "openai-compatible"):
        from cvm.processors import ChatCompletionsProcessor
        from cvm.processors import METHOD_HINT
        return ChatCompletionsProcessor(model=args.model or "deepseek-chat",
                                        base_url=args.base_url, api_key_env=args.api_key_env,
                                        system_extra=METHOD_HINT if args.hint else "")
    if args.provider == "claude":
        from cvm.processors import ClaudeProcessor
        return ClaudeProcessor(model=args.model or "claude-opus-5-5", effort=args.effort)
    if args.provider == "reference":
        from cvm.processors import ReferenceReasoner
        p = ReferenceReasoner()
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--sizes", default="1000,1000000")
    ap.add_argument("--tasks", type=int, default=30)
    ap.add_argument("--conditions", default="cvm")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--max-objects", type=int, default=32,
                    help="CVM working-set size (resident objects); applies to the cvm condition only")
    ap.add_argument("--out-dir", default=RESULTS, help="where llm_<tag>.json and traces are written")
    ap.add_argument("--agent-context-limit", type=int, default=120_000,
                    help="tokens; requests above this are not sent (model window)")
    ap.add_argument("--tag", default="")
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
    unknown = [c for c in conditions if c not in ("cvm", "agent")]
    if unknown:
        ap.error(f"unsupported condition(s) {unknown}; run_llm.py supports cvm and agent")
    if "agent" in conditions and args.max_objects != 32:
        print("note: --max-objects applies to the cvm condition only; "
              "the agent baseline keeps an unbounded transcript", file=sys.stderr)
    report = {"provider": args.provider, "model": model, "method_hint": args.hint,
              "tasks_per_size": args.tasks, "max_steps": args.max_steps,
              "max_objects": args.max_objects, "sizes": []}
    os.makedirs(args.out_dir, exist_ok=True)
    traces = open(os.path.join(args.out_dir, f"llm_{tag}_traces.jsonl"), "w")
    for n in [int(x) for x in args.sizes.split(",")]:
        w = build_world(n)
        store = GraphStore(w.path)
        tasks = make_tasks(store, args.tasks, seed=n)
        entry = {"world_objects": w.n_objects, "conditions": {}}
        for cond in conditions:
            t0 = time.time()

            def one(spec):
                proc = make_processor(args)
                ctxs = []
                if cond == "cvm":
                    m = run_cvm(store, spec, proc, w.n_objects, max_steps=args.max_steps,
                                max_objects=args.max_objects, keep_ctx=ctxs)
                else:
                    m = run_agent(store, spec, proc, w.n_objects,
                                  context_limit=args.agent_context_limit,
                                  max_steps=args.max_steps, keep_ctx=ctxs)
                m["llm_input_tokens"] = proc.usage["input_tokens"]
                m["llm_output_tokens"] = proc.usage["output_tokens"]
                m["llm_calls"] = proc.usage["calls"]
                m["llm_errors"] = proc.usage.get("errors", 0)
                c = ctxs[0]
                print(f"  [{cond}] {spec.task.kind:<10} d={spec.depth} correct={m['correct']} "
                      f"steps={m['steps']} answer={c.answer}", flush=True)
                return m, {"world_objects": w.n_objects, "condition": cond,
                           "task": spec.task.text, "expected": spec.expected,
                           "answer": c.answer, "support": c.answer_support,
                           "trace": c.trace, "notes": dict(c.notes)}

            with ThreadPoolExecutor(args.workers) as ex:
                results = list(ex.map(one, tasks))
            runs = [m for m, _ in results]
            for _, tr in results:
                traces.write(json.dumps(tr) + "\n")
            traces.flush()
            s = summarize(runs)
            s.update({
                "llm_input_tokens_mean": sum(r["llm_input_tokens"] for r in runs) / len(runs),
                "llm_output_tokens_mean": sum(r["llm_output_tokens"] for r in runs) / len(runs),
                "llm_calls_mean": sum(r["llm_calls"] for r in runs) / len(runs),
                "llm_errors": sum(r["llm_errors"] for r in runs),
                "invalid_ops_mean": sum(r["invalid_ops"] for r in runs) / len(runs),
                "aborted": sum(r["aborted"] for r in runs),
                "abstained": sum(1 for r in runs if r["answer"] in (None, "UNKNOWN")),
                "accuracy_by_kind": accuracy_by(runs, "kind"),
                "accuracy_by_depth": accuracy_by(runs, "depth"),
                "wall_seconds": round(time.time() - t0, 1),
            })
            entry["conditions"][cond] = s
            entry.setdefault("runs", []).extend(runs)
            print(f"N={w.n_objects:>8} {cond:<6} acc={s['accuracy']:.2f} "
                  f"peakObj={s['peak_resident_objects_mean']:.1f} "
                  f"peakTok={s['peak_prompt_tokens_mean']:.0f} steps={s['steps_mean']:.1f} "
                  f"unsupported={s['unsupported_claim_rate']:.2f} thrash={s['thrash_rate_mean']:.2f} "
                  f"faultPrec={s['fault_precision_mean']:.2f} invalid={s['invalid_ops_mean']:.1f} "
                  f"stepLimit={s['step_limit']} aborted={s['aborted']} overflow={s['context_overflow']} "
                  f"in_tok={s['llm_input_tokens_mean']:.0f} ({s['wall_seconds']}s)", flush=True)
        report["sizes"].append(entry)
        with open(os.path.join(args.out_dir, f"llm_{tag}.json"), "w") as f:
            json.dump(report, f, indent=1, default=str)
    traces.close()


if __name__ == "__main__":
    main()
