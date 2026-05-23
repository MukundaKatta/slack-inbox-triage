"""A tiny in-process scheduler for periodic triage runs.

Slack apps typically schedule via cron, Celery, or a dedicated worker.
This module is a small abstraction so the agent stays portable: you
provide a clock and a sleep function, and the scheduler calls back
into TriageAgent on the interval you ask for.

Intentionally simple: no threading, no async. The host process drives
the loop. That keeps tests deterministic (you pass a fake clock).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from .triage import TriageAgent, TriageResult


Clock = Callable[[], float]
Sleeper = Callable[[float], None]


@dataclass
class TriageScheduler:
    """Drive an agent on a fixed interval across multiple channels.

    Example:

        sched = TriageScheduler(agent=agent, channels=["C_INBOX"], interval_s=900)
        for result in sched.run(max_iterations=4, clock=time.time, sleep=time.sleep):
            print(result.counts())

    The loop yields each TriageResult so the host can decide what to
    do with it (post to Slack, log, store, etc.).
    """

    agent: TriageAgent
    channels: list[str]
    interval_s: float = 900.0  # 15 minutes
    skip_users: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        max_iterations: int,
        clock: Clock,
        sleep: Sleeper,
    ) -> Iterable[TriageResult]:
        """Run up to `max_iterations` triage passes across all channels.

        Each iteration triages every channel once, then sleeps for
        `interval_s` seconds. Yields one TriageResult per channel.
        """

        if max_iterations < 0:
            raise ValueError("max_iterations must be >= 0")
        if self.interval_s < 0:
            raise ValueError("interval_s must be >= 0")

        for _ in range(max_iterations):
            started = clock()
            for ch in self.channels:
                yield self.agent.triage_channel(ch, skip_users=self.skip_users)
            elapsed = clock() - started
            remaining = max(0.0, self.interval_s - elapsed)
            if remaining > 0:
                sleep(remaining)
