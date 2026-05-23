"""Tests for the TriageScheduler with a fake clock."""

from __future__ import annotations

import pytest

from slack_inbox_triage.scheduler import TriageScheduler
from slack_inbox_triage.slack_client import build_demo_provider
from slack_inbox_triage.triage import TriageAgent


def test_scheduler_runs_n_iterations():
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
    assert len(results) == 3
    # exactly three sleeps (one after each iteration), each ~10s
    assert len(sleeps) == 3
    for s in sleeps:
        assert s == pytest.approx(10.0)


def test_scheduler_rejects_negative_iterations():
    fp = build_demo_provider()
    agent = TriageAgent(client=fp)
    sched = TriageScheduler(agent=agent, channels=["C_INBOX"], interval_s=10)
    with pytest.raises(ValueError):
        list(sched.run(max_iterations=-1, clock=lambda: 0.0, sleep=lambda _: None))
