"""Export prompt/action supervision from the real CVM runtime.

The reference policy sees only ``CVMRuntime.build_prompt`` output. Injected bad
steps are retained for replay but never used as training targets; the *next*
valid policy step is labelled as recovery. Train and validation worlds use
separate generator seeds.

    python3 experiments/export_trajectories.py --tasks 10000 --out data/v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cvm.context import CognitiveContext, incident_agent_capabilities  # noqa: E402
from cvm.experiment import TaskSpec, make_tasks  # noqa: E402
from cvm.objects import approx_tokens  # noqa: E402
from cvm.processors import ReferenceReasoner, SYSTEM_OPENAI, first_json_object, normalize_action  # noqa: E402
from cvm.resolver import GraphStore  # noqa: E402
from cvm.runtime import CVMRuntime, RuntimeConfig  # noqa: E402
from cvm.synthetic_world import build_world  # noqa: E402
from cvm.working_set import WorkingSet  # noqa: E402

WORLD_SIZES = (100, 1000, 10000)
WORKING_SETS = (4, 8, 16, 32)
RECOVERY_SCENARIOS = ("bad_answer", "denied", "useless_fault", "eviction")
MAX_STEPS = 90


@dataclass
class Trajectory:
    context_id: str
    spec: TaskSpec
    answer: str | None
    steps: list[tuple[str, dict]]  # all executed actions, including perturbations
    samples: list[dict]            # only correct oracle targets
    injected: bool


def _reason(action: dict) -> str:
    """Keep the reference policy's field-level purpose and name its target."""
    ref = action["ref"]
    why = action.get("reason", "need its facts").rstrip(" .")
    return f"{why} from {ref}"


def _injected_action(scenario: str, action: dict, task_kind: str) -> dict | None:
    if scenario == "bad_answer" and action["op"] == "ANSWER":
        return {"op": "ANSWER", "value": "change://unsupported", "support": []}
    if scenario == "denied" and action["op"] == "FAULT":
        if task_kind == "claim":
            return {"op": "SEARCH", "namespace": "person://", "query": "oncall"}
        return {"op": "EVIDENCE", "ref": "claim://denied"}
    if scenario == "useless_fault" and action["op"] == "FAULT":
        ref = "service://platform-dns"
        if action.get("ref") == ref:
            ref = "service://platform-kafka"
        return {"op": "FAULT", "ref": ref, "reason": "extra off-path check"}
    return None


def run_trajectory(store: GraphStore, spec: TaskSpec, *, world_seed: int,
                   world_size: int, max_objects: int, search: bool,
                   scenario: str | None = None, max_steps: int = MAX_STEPS) -> Trajectory:
    """Run one real task, recording exact prompts and the actions sent to runtime."""
    if scenario not in (None, *RECOVERY_SCENARIOS):
        raise ValueError(f"unknown recovery scenario: {scenario}")
    rt = CVMRuntime(store, RuntimeConfig(max_steps=max_steps))
    ctx = CognitiveContext(
        "agent://incident-debugger", spec.task,
        incident_agent_capabilities(search=search, claims=spec.task.kind == "claim"),
        WorkingSet(max_objects),
    )
    oracle = ReferenceReasoner()
    steps: list[tuple[str, dict]] = []
    samples: list[dict] = []
    injected = False
    pending_recovery: str | None = None

    def processor(prompt: str) -> dict:
        nonlocal injected, pending_recovery
        action = normalize_action(oracle.step(prompt))
        if action["op"] == "FAULT":
            action["reason"] = _reason(action)
        if scenario in ("bad_answer", "denied", "useless_fault") and not injected:
            perturbation = _injected_action(scenario, action, spec.task.kind)
            if perturbation is not None:
                injected = True
                pending_recovery = scenario
                steps.append((prompt, perturbation))
                return perturbation
        last = ctx.last_result
        recovery_from = pending_recovery
        if recovery_from is None and scenario == "eviction" and "evicted " in last:
            recovery_from = "eviction"
            injected = True
        pending_recovery = None
        action_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        sample = {
            "messages": [
                {"role": "system", "content": SYSTEM_OPENAI},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": action_json},
            ],
            "meta": {
                "world_seed": world_seed,
                "world_size": world_size,
                "task_kind": spec.task.kind,
                "depth": spec.depth,
                "max_objects": max_objects,
                "search": search,
                "step": ctx.counters["steps"] + 1,
                "kind": "recovery" if recovery_from else "normal",
            },
        }
        if recovery_from:
            sample["meta"]["recovery_from"] = recovery_from
        samples.append(sample)
        steps.append((prompt, action))
        return action

    rt.run(ctx, processor)
    if ctx.answer != spec.expected or ctx.counters["step_limit"]:
        raise RuntimeError(f"reference failed {spec.task.text}: {ctx.answer!r} != {spec.expected!r}")
    if scenario and not injected:
        raise RuntimeError(f"scenario {scenario} did not create a recovery step")
    return Trajectory(ctx.id, spec, ctx.answer, steps, samples, injected)


def replay_trajectory(store: GraphStore, trajectory: Trajectory, *, max_objects: int,
                      search: bool, max_steps: int = MAX_STEPS) -> str | None:
    """Check every recorded prompt and action against a fresh runtime context."""
    rt = CVMRuntime(store, RuntimeConfig(max_steps=max_steps))
    ctx = CognitiveContext(
        "agent://incident-debugger", trajectory.spec.task,
        incident_agent_capabilities(search=search, claims=trajectory.spec.task.kind == "claim"),
        WorkingSet(max_objects), id=trajectory.context_id,
    )
    steps = iter(trajectory.steps)
    count = 0

    def scripted(prompt: str) -> dict:
        nonlocal count
        expected_prompt, action = next(steps)
        if prompt != expected_prompt:
            raise AssertionError(f"replay prompt drift at step {count + 1}")
        count += 1
        return action

    rt.run(ctx, scripted)
    if count != len(trajectory.steps) or ctx.answer != trajectory.answer:
        raise AssertionError("replay did not reproduce the recorded answer and step count")
    return ctx.answer


def _jobs(total: int, train_seeds: int, val_seeds: int, sizes: tuple[int, ...]):
    jobs = [("train", 1000 + s, size) for s in range(train_seeds) for size in sizes]
    jobs += [("val", 2000 + s, size) for s in range(val_seeds) for size in sizes]
    if total < len(jobs):
        raise ValueError(f"--tasks must be >= {len(jobs)} to cover every seed and size")
    q, rem = divmod(total, len(jobs))
    for i, (split, seed, size) in enumerate(jobs):
        yield split, seed, size, q + (i < rem)


def export(*, tasks: int, out: Path, train_seeds: int = 20, val_seeds: int = 4,
           sizes: tuple[int, ...] = WORLD_SIZES, recovery_every: int = 4,
           shuffle_seed: int = 7, verify_replay: bool = False) -> dict:
    if tasks < 1 or train_seeds < 1 or val_seeds < 1 or not sizes or any(n < 1 for n in sizes):
        raise ValueError("tasks, seed counts, and world sizes must be positive")
    if recovery_every < 1:
        raise ValueError("recovery_every must be >= 1")
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(shuffle_seed)
    config_rng = random.Random(shuffle_seed + 1)
    stats: dict[str, Any] = {
        "tasks": {"train": 0, "val": 0},
        "examples": {"train": 0, "val": 0},
        "deduplicated": 0,
        "actions": Counter(),
        "recovery_from": Counter(),
        "world_sizes": list(sizes),
        "train_world_seeds": list(range(1000, 1000 + train_seeds)),
        "val_world_seeds": list(range(2000, 2000 + val_seeds)),
        "prompt_tokens_estimated": 0,
    }
    seen: set[bytes] = set()
    offsets: dict[str, list[int]] = {"train": [], "val": []}
    with tempfile.TemporaryFile(mode="w+b") as temp:
        task_index = 0
        for split, seed, size, count in _jobs(tasks, train_seeds, val_seeds, sizes):
            world = build_world(size, seed=seed)
            store = GraphStore(world.path)
            try:
                specs = make_tasks(store, count, seed=seed * 100_000 + size)
                for spec in specs:
                    scenario = None
                    if task_index % recovery_every == 0:
                        scenario = RECOVERY_SCENARIOS[(task_index // recovery_every) % len(RECOVERY_SCENARIOS)]
                    max_objects = 2 if scenario == "eviction" else config_rng.choice(WORKING_SETS)
                    search = bool(config_rng.getrandbits(1))
                    trajectory = run_trajectory(
                        store, spec, world_seed=seed, world_size=world.n_objects,
                        max_objects=max_objects, search=search, scenario=scenario,
                    )
                    if verify_replay:
                        replay_trajectory(store, trajectory, max_objects=max_objects, search=search)
                    stats["tasks"][split] += 1
                    for sample in trajectory.samples:
                        prompt = sample["messages"][1]["content"]
                        action_json = sample["messages"][2]["content"]
                        digest = hashlib.blake2b((prompt + "\0" + action_json).encode(), digest_size=16).digest()
                        if digest in seen:
                            stats["deduplicated"] += 1
                            continue
                        seen.add(digest)
                        offsets[split].append(temp.tell())
                        temp.write((json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
                        stats["examples"][split] += 1
                        stats["actions"][json.loads(action_json)["op"]] += 1
                        if sample["meta"]["kind"] == "recovery":
                            stats["recovery_from"][sample["meta"]["recovery_from"]] += 1
                        stats["prompt_tokens_estimated"] += approx_tokens(prompt)
                    task_index += 1
            finally:
                store.db.close()
            print(f"{split} seed={seed} size={world.n_objects} tasks={count}", flush=True)
        for split in ("train", "val"):
            rng.shuffle(offsets[split])
            with (out / f"{split}.jsonl").open("wb") as target:
                for offset in offsets[split]:
                    temp.seek(offset)
                    target.write(temp.readline())
    stats["actions"] = dict(stats["actions"])
    stats["recovery_from"] = dict(stats["recovery_from"])
    stats["prompt_tokens_estimated"] = int(stats["prompt_tokens_estimated"])
    (out / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", type=int, default=10_000)
    ap.add_argument("--out", type=Path, default=Path("data/v1"))
    ap.add_argument("--train-seeds", type=int, default=20)
    ap.add_argument("--val-seeds", type=int, default=4)
    ap.add_argument("--sizes", default="100,1000,10000")
    ap.add_argument("--recovery-every", type=int, default=4)
    ap.add_argument("--verify-replay", action="store_true")
    args = ap.parse_args(argv)
    sizes = tuple(int(x) for x in args.sizes.split(","))
    try:
        stats = export(tasks=args.tasks, out=args.out, train_seeds=args.train_seeds,
                       val_seeds=args.val_seeds, sizes=sizes, recovery_every=args.recovery_every,
                       verify_replay=args.verify_replay)
    except (ValueError, RuntimeError) as exc:
        ap.error(str(exc))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
