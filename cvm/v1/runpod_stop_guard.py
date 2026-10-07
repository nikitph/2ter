"""Independent local deadline guard for a billable Runpod pod.

Run this on a computer that stays awake, using an authenticated runpodctl.
Start and verify the guard before starting a long training process. It stops
the named pod after the specified number of minutes even if Codex disconnects.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

ACTIVE = {"RUNNING", "STARTING", "PROVISIONING", "INITIALIZING"}
STOPPED = {"EXITED", "STOPPED", "ERROR", "TERMINATED"}


class RunpodCli:
    def __init__(self, binary: Path):
        self.binary = binary

    def call(self, *args: str) -> str:
        command = [str(self.binary), *args]
        result = subprocess.run(command, text=True, capture_output=True,
                                timeout=45, check=False)
        if result.returncode:
            try:
                error = json.loads(result.stderr.splitlines()[0])
            except (IndexError, ValueError):
                error = {"code": "cli_error", "error": result.stderr[:200]}
            raise RuntimeError(f"runpodctl {args[0]} {args[1]} failed: "
                               f"{error.get('code')}: {error.get('error')}")
        return result.stdout

    def status(self, pod_id: str) -> str:
        # `pod get` may print a table. `pod list --all` is documented as JSON
        # and includes stopped pods so the stop can be verified afterwards.
        output = self.call("pod", "list", "--all", "--output", "json")
        try:
            listing = json.loads(output)
        except ValueError as exc:
            raise RuntimeError("runpodctl pod list returned non-JSON output") from exc
        pods = listing if isinstance(listing, list) else listing.get("pods")
        if not isinstance(pods, list):
            raise RuntimeError("runpodctl pod list returned an unknown JSON shape")
        pod = next((item for item in pods if item.get("id") == pod_id), None)
        if pod is None:
            raise RuntimeError(f"pod {pod_id} is absent from runpodctl pod list --all")
        runtime = str(pod.get("runtimeStatus") or "").upper()
        desired = str(pod.get("desiredStatus") or pod.get("status") or "").upper()
        # The two Runpod surfaces may briefly disagree. A desired RUNNING pod
        # still needs a stop request even if runtime telemetry says stopped.
        if desired == "RUNNING" and runtime in STOPPED:
            return "INITIALIZING"
        return runtime if runtime and runtime != "UNKNOWN" else desired

    def stop(self, pod_id: str) -> None:
        self.call("pod", "stop", pod_id)


def stop_at_deadline(client, pod_id: str, minutes: float, interval: float,
                     clock=time.monotonic, sleep=time.sleep) -> str:
    status = client.status(pod_id)
    if status not in ACTIVE:
        raise RuntimeError(f"guard requires an active pod, got {status!r}")
    deadline = clock() + minutes * 60
    print(f"GUARD_READY pod={pod_id} status={status} stop_after_minutes={minutes}",
          flush=True)
    while clock() < deadline:
        sleep(min(interval, deadline - clock()))
    for attempt in range(20):
        try:
            status = client.status(pod_id)
            if status in STOPPED:
                print(f"GUARD_DONE pod={pod_id} status={status}", flush=True)
                return status
            if status not in ACTIVE:
                raise RuntimeError(f"unknown pod status {status!r}")
            client.stop(pod_id)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"GUARD_RETRY attempt={attempt + 1} error={exc}", flush=True)
        sleep(interval)
    raise RuntimeError(f"could not verify that pod {pod_id} stopped")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pod-id", required=True)
    ap.add_argument("--after-minutes", type=float, required=True)
    ap.add_argument("--interval-seconds", type=float, default=30)
    ap.add_argument("--runpodctl", type=Path,
                    default=Path.home() / ".local/bin/runpodctl")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args(argv)
    if args.after_minutes <= 0 or args.interval_seconds <= 0:
        ap.error("after-minutes and interval-seconds must be positive")
    if not args.runpodctl.is_file():
        ap.error(f"runpodctl not found: {args.runpodctl}")
    client = RunpodCli(args.runpodctl)
    if args.preflight_only:
        status = client.status(args.pod_id)
        if status not in ACTIVE:
            raise SystemExit(f"pod is not active: {status}")
        print(f"GUARD_PREFLIGHT_OK pod={args.pod_id} status={status}")
        return
    stop_at_deadline(client, args.pod_id, args.after_minutes,
                     args.interval_seconds)


if __name__ == "__main__":
    main()
