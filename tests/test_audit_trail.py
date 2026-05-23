"""Tests for the AuditTrail."""

from __future__ import annotations

import json

from slack_inbox_triage.governance import AuditTrail


def test_audit_records_and_filters():
    trail = AuditTrail()
    trail.record("egress.ok", host="a.com")
    trail.record("egress.blocked", host="b.com", reason="denied")
    trail.record("scope.ok", method="chat.postMessage")
    assert len(trail.events) == 3
    assert len(trail.filter("egress.ok")) == 1
    assert len(trail.blocked()) == 1


def test_audit_writes_jsonl_to_disk(tmp_path):
    path = tmp_path / "audit.jsonl"
    trail = AuditTrail(path=path)
    trail.record("egress.ok", host="a.com")
    trail.record("scope.denied", method="x", reason="unknown_method")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "egress.ok"
    assert parsed[1]["detail"]["reason"] == "unknown_method"
