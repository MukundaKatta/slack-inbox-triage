"""Tests for the EgressAllowlist guard."""

from __future__ import annotations

import pytest

from slack_inbox_triage.governance import (
    AuditTrail,
    EgressAllowlist,
    EgressBlocked,
)


def test_allowlist_passes_known_host():
    trail = AuditTrail()
    gate = EgressAllowlist(hosts=["api.slack.com", "api.anthropic.com"], audit=trail)
    gate.check("https://api.slack.com/api/conversations.history")
    assert trail.filter("egress.ok")
    assert not trail.blocked()


def test_allowlist_blocks_unknown_host_with_audit():
    trail = AuditTrail()
    gate = EgressAllowlist(hosts=["api.slack.com"], audit=trail)
    with pytest.raises(EgressBlocked):
        gate.check("https://evil.example.com/exfil")
    blocked = trail.blocked()
    assert len(blocked) == 1
    assert blocked[0].detail["host"] == "evil.example.com"


def test_allowlist_wildcard_matches_one_level():
    gate = EgressAllowlist(hosts=["*.slack.com"])
    gate.check("https://api.slack.com/x")
    with pytest.raises(EgressBlocked):
        # two levels deeper should not match a one-level wildcard
        gate.check("https://deep.api.slack.com/x")


def test_allowlist_wrap_intercepts_url_arg():
    trail = AuditTrail()
    gate = EgressAllowlist(hosts=["api.allowed.com"], audit=trail)
    calls: list[str] = []

    def fake_http(url, **_):
        calls.append(url)
        return {"ok": True}

    guarded = gate.wrap(fake_http)
    guarded("https://api.allowed.com/hello")
    with pytest.raises(EgressBlocked):
        guarded("https://api.blocked.com/leak")
    assert calls == ["https://api.allowed.com/hello"]
    assert any(e.kind == "egress.blocked" for e in trail.events)


def test_allowlist_rejects_url_without_host():
    gate = EgressAllowlist(hosts=["api.allowed.com"])
    with pytest.raises(EgressBlocked):
        gate.check("not-a-url")
