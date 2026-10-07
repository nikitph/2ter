"""Offline checks for the independent pod billing guard."""
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

from v1.runpod_stop_guard import RunpodCli, stop_at_deadline


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakePod:
    def __init__(self, status="RUNNING"):
        self.current = status
        self.stops = 0

    def status(self, pod_id):
        return self.current

    def stop(self, pod_id):
        self.stops += 1
        self.current = "EXITED"


class RunpodGuardTest(unittest.TestCase):
    def test_cli_reads_runtime_state_and_accepts_plaintext_stop(self):
        cli = RunpodCli(Path("/usr/local/bin/runpodctl"))
        responses = [
            CompletedProcess([], 0, '[{"id":"pod-1","runtimeStatus":"running","desiredStatus":"RUNNING"}]', ""),
            CompletedProcess([], 0, "pod stopped", ""),
            CompletedProcess([], 0, '{"pods":[{"id":"pod-1","runtimeStatus":"stopped","desiredStatus":"EXITED"}]}', ""),
        ]
        with patch("v1.runpod_stop_guard.subprocess.run", side_effect=responses) as run:
            self.assertEqual(cli.status("pod-1"), "RUNNING")
            cli.stop("pod-1")
            self.assertEqual(cli.status("pod-1"), "STOPPED")
        self.assertEqual(run.call_args_list[0].args[0][1:],
                         ["pod", "list", "--all", "--output", "json"])
        self.assertEqual(run.call_args_list[1].args[0][1:],
                         ["pod", "stop", "pod-1"])

    def test_cli_rejects_missing_pod(self):
        cli = RunpodCli(Path("/usr/local/bin/runpodctl"))
        with patch("v1.runpod_stop_guard.subprocess.run",
                   return_value=CompletedProcess([], 0, "[]", "")):
            with self.assertRaisesRegex(RuntimeError, "absent"):
                cli.status("pod-1")

    def test_stops_only_after_deadline_and_confirms_state(self):
        clock = FakeClock()
        pod = FakePod()
        state = stop_at_deadline(pod, "pod-1", 2, 30,
                                 clock=clock.clock, sleep=clock.sleep)
        self.assertEqual(state, "EXITED")
        self.assertEqual(pod.stops, 1)
        self.assertGreaterEqual(clock.now, 120)

    def test_refuses_to_arm_for_inactive_pod(self):
        clock = FakeClock()
        pod = FakePod("EXITED")
        with self.assertRaisesRegex(RuntimeError, "requires an active pod"):
            stop_at_deadline(pod, "pod-1", 2, 30,
                             clock=clock.clock, sleep=clock.sleep)
        self.assertEqual(pod.stops, 0)


if __name__ == "__main__":
    unittest.main()
