"""Tests for the AuditTrail."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.governance import AuditTrail


class AuditTrailTests(unittest.TestCase):
    def test_audit_records_and_filters(self):
        trail = AuditTrail()
        trail.record("egress.ok", host="a.com")
        trail.record("egress.blocked", host="b.com", reason="denied")
        trail.record("scope.ok", method="chat.postMessage")
        self.assertEqual(len(trail.events), 3)
        self.assertEqual(len(trail.filter("egress.ok")), 1)
        self.assertEqual(len(trail.blocked()), 1)

    def test_audit_writes_jsonl_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            trail = AuditTrail(path=path)
            trail.record("egress.ok", host="a.com")
            trail.record("scope.denied", method="x", reason="unknown_method")
            lines = path.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            parsed = [json.loads(line) for line in lines]
            self.assertEqual(parsed[0]["kind"], "egress.ok")
            self.assertEqual(parsed[1]["detail"]["reason"], "unknown_method")


if __name__ == "__main__":
    unittest.main()
