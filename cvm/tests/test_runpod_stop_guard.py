"""Offline checks for the independent pod billing guard."""
import unittest

from v1.runpod_stop_guard import stop_at_deadline


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
