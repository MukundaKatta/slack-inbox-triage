"""Tests for the ScopeAllowlist guard."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.governance import (
    AuditTrail,
    ScopeAllowlist,
    ScopeDenied,
)


class ScopeAllowlistTests(unittest.TestCase):
    def test_scope_allows_granted_method(self):
        trail = AuditTrail()
        gate = ScopeAllowlist(granted=["chat:write"], audit=trail)
        gate.check("chat.postMessage")
        self.assertTrue(trail.filter("scope.ok"))

    def test_scope_denies_when_scope_missing(self):
        trail = AuditTrail()
        gate = ScopeAllowlist(granted=["chat:write"], audit=trail)
        with self.assertRaises(ScopeDenied):
            gate.check("conversations.history")
        denied = trail.blocked()
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].detail["required"], "channels:history")

    def test_scope_denies_unknown_method(self):
        """Refusing unknown methods is intentional. Be strict, not permissive."""

        trail = AuditTrail()
        gate = ScopeAllowlist(granted=["chat:write"], audit=trail)
        with self.assertRaises(ScopeDenied):
            gate.check("admin.users.delete")
        self.assertEqual(trail.blocked()[0].detail["reason"], "unknown_method")

    def test_required_scope_lookup(self):
        gate = ScopeAllowlist(granted=[])
        self.assertEqual(gate.required_scope("chat.postMessage"), "chat:write")
        self.assertEqual(
            gate.required_scope("conversations.history"), "channels:history"
        )
        self.assertIsNone(gate.required_scope("admin.something"))


if __name__ == "__main__":
    unittest.main()
