"""Tests for the ScopeAllowlist guard."""

from __future__ import annotations

import pytest

from slack_inbox_triage.governance import (
    AuditTrail,
    ScopeAllowlist,
    ScopeDenied,
)


def test_scope_allows_granted_method():
    trail = AuditTrail()
    gate = ScopeAllowlist(granted=["chat:write"], audit=trail)
    gate.check("chat.postMessage")
    assert trail.filter("scope.ok")


def test_scope_denies_when_scope_missing():
    trail = AuditTrail()
    gate = ScopeAllowlist(granted=["chat:write"], audit=trail)
    with pytest.raises(ScopeDenied):
        gate.check("conversations.history")
    denied = trail.blocked()
    assert len(denied) == 1
    assert denied[0].detail["required"] == "channels:history"


def test_scope_denies_unknown_method():
    """Refusing unknown methods is intentional. Be strict, not permissive."""

    trail = AuditTrail()
    gate = ScopeAllowlist(granted=["chat:write"], audit=trail)
    with pytest.raises(ScopeDenied):
        gate.check("admin.users.delete")
    assert trail.blocked()[0].detail["reason"] == "unknown_method"


def test_required_scope_lookup():
    gate = ScopeAllowlist(granted=[])
    assert gate.required_scope("chat.postMessage") == "chat:write"
    assert gate.required_scope("conversations.history") == "channels:history"
    assert gate.required_scope("admin.something") is None
