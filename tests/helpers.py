"""Shared builders for the unittest suite.

These replace the pytest fixtures in ``conftest.py`` so the tests run under
the standard-library runner with no third-party dependency::

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.governance import AuditTrail, ScopeAllowlist
from slack_inbox_triage.slack_client import FakeSlackProvider, build_demo_provider

# Scopes the demo workspace grants. Mirrors slack_app_manifest.yml.
DEMO_SCOPES = [
    "channels:history",
    "channels:read",
    "chat:write",
    "reactions:write",
]


def make_audit_trail() -> AuditTrail:
    """Return a fresh in-memory audit trail."""

    return AuditTrail()


def make_demo_provider(audit: AuditTrail | None = None) -> FakeSlackProvider:
    """Return a demo provider wired to a scope gate, like the pytest fixture."""

    scope = ScopeAllowlist(granted=list(DEMO_SCOPES), audit=audit)
    return build_demo_provider(scope_gate=scope)
