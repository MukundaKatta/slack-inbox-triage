"""Tests for the TriageScheduler with a fake clock."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.scheduler import TriageScheduler
from slack_inbox_triage.slack_client import build_demo_provider
from slack_inbox_triage.triage import TriageAgent


class SchedulerTests(unittest.TestCase):
    def test_scheduler_runs_n_iterations(self):
        fp = build_demo_provider()
        agent = TriageAgent(client=fp)
        sched = TriageScheduler(agent=agent, channels=["C_INBOX"], interval_s=10)

        now = [1000.0]
        sleeps: list[float] = []

        def clock():
            return now[0]

        def sleep(s):
            sleeps.append(s)
            now[0] += s

        results = list(sched.run(max_iterations=3, clock=clock, sleep=sleep))
        self.assertEqual(len(results), 3)
        # exactly three sleeps (one after each iteration), each ~10s
        self.assertEqual(len(sleeps), 3)
        for s in sleeps:
            self.assertAlmostEqual(s, 10.0)

    def test_scheduler_multiple_channels_yield_per_channel(self):
        """Each iteration yields one result per channel."""

        fp = build_demo_provider()
        agent = TriageAgent(client=fp)
        sched = TriageScheduler(
            agent=agent, channels=["C_INBOX", "C_INBOX"], interval_s=0
        )
        results = list(
            sched.run(max_iterations=2, clock=lambda: 0.0, sleep=lambda _: None)
        )
        # 2 iterations x 2 channels.
        self.assertEqual(len(results), 4)

    def test_scheduler_zero_iterations_yields_nothing(self):
        fp = build_demo_provider()
        agent = TriageAgent(client=fp)
        sched = TriageScheduler(agent=agent, channels=["C_INBOX"], interval_s=10)
        results = list(
            sched.run(max_iterations=0, clock=lambda: 0.0, sleep=lambda _: None)
        )
        self.assertEqual(results, [])

    def test_scheduler_rejects_negative_iterations(self):
        fp = build_demo_provider()
        agent = TriageAgent(client=fp)
        sched = TriageScheduler(agent=agent, channels=["C_INBOX"], interval_s=10)
        with self.assertRaises(ValueError):
            list(
                sched.run(
                    max_iterations=-1, clock=lambda: 0.0, sleep=lambda _: None
                )
            )

    def test_scheduler_rejects_negative_interval(self):
        fp = build_demo_provider()
        agent = TriageAgent(client=fp)
        sched = TriageScheduler(agent=agent, channels=["C_INBOX"], interval_s=-1)
        with self.assertRaises(ValueError):
            list(
                sched.run(
                    max_iterations=1, clock=lambda: 0.0, sleep=lambda _: None
                )
            )


if __name__ == "__main__":
    unittest.main()
