"""Optional pytest fixtures for slack-inbox-triage tests.

The suite is written against the standard-library ``unittest`` runner and
needs no third-party dependency::

    python3 -m unittest discover -s tests

This file is only consulted when the suite is run under pytest, which some
contributors prefer. It mirrors the builders in ``tests/helpers.py`` as
fixtures and ensures the ``src`` layout is importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def audit_trail():
    from slack_inbox_triage.governance import AuditTrail

    return AuditTrail()


@pytest.fixture
def demo_provider(audit_trail):
    from slack_inbox_triage.governance import ScopeAllowlist
    from slack_inbox_triage.slack_client import build_demo_provider

    scope = ScopeAllowlist(
        granted=[
            "channels:history",
            "channels:read",
            "chat:write",
            "reactions:write",
        ],
        audit=audit_trail,
    )
    return build_demo_provider(scope_gate=scope)
