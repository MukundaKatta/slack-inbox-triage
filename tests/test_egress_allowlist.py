"""Tests for the EgressAllowlist guard."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.governance import (
    AuditTrail,
    EgressAllowlist,
    EgressBlocked,
)


class EgressAllowlistTests(unittest.TestCase):
    def test_allowlist_passes_known_host(self):
        trail = AuditTrail()
        gate = EgressAllowlist(
            hosts=["api.slack.com", "api.anthropic.com"], audit=trail
        )
        gate.check("https://api.slack.com/api/conversations.history")
        self.assertTrue(trail.filter("egress.ok"))
        self.assertFalse(trail.blocked())

    def test_allowlist_blocks_unknown_host_with_audit(self):
        trail = AuditTrail()
        gate = EgressAllowlist(hosts=["api.slack.com"], audit=trail)
        with self.assertRaises(EgressBlocked):
            gate.check("https://evil.example.com/exfil")
        blocked = trail.blocked()
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].detail["host"], "evil.example.com")

    def test_allowlist_wildcard_matches_one_level(self):
        gate = EgressAllowlist(hosts=["*.slack.com"])
        gate.check("https://api.slack.com/x")
        with self.assertRaises(EgressBlocked):
            # two levels deeper should not match a one-level wildcard
            gate.check("https://deep.api.slack.com/x")

    def test_allowlist_wrap_intercepts_url_arg(self):
        trail = AuditTrail()
        gate = EgressAllowlist(hosts=["api.allowed.com"], audit=trail)
        calls: list[str] = []

        def fake_http(url, **_):
            calls.append(url)
            return {"ok": True}

        guarded = gate.wrap(fake_http)
        guarded("https://api.allowed.com/hello")
        with self.assertRaises(EgressBlocked):
            guarded("https://api.blocked.com/leak")
        self.assertEqual(calls, ["https://api.allowed.com/hello"])
        self.assertTrue(any(e.kind == "egress.blocked" for e in trail.events))

    def test_allowlist_wrap_intercepts_url_kwarg(self):
        """A URL passed by keyword is inspected just like a positional one."""

        gate = EgressAllowlist(hosts=["api.allowed.com"])

        def fake_http(url=None, **_):
            return {"ok": True, "url": url}

        guarded = gate.wrap(fake_http)
        self.assertEqual(
            guarded(url="https://api.allowed.com/hello")["url"],
            "https://api.allowed.com/hello",
        )
        with self.assertRaises(EgressBlocked):
            guarded(url="https://api.blocked.com/leak")

    def test_allowlist_wrap_without_url_is_blocked(self):
        """Calls with no inspectable URL are refused, not passed through."""

        gate = EgressAllowlist(hosts=["api.allowed.com"])

        def fake_http(*_a, **_k):
            return {"ok": True}

        guarded = gate.wrap(fake_http)
        with self.assertRaises(EgressBlocked):
            guarded(method="POST")

    def test_allowlist_rejects_url_without_host(self):
        gate = EgressAllowlist(hosts=["api.allowed.com"])
        with self.assertRaises(EgressBlocked):
            gate.check("not-a-url")

    def test_allowlist_match_is_case_insensitive(self):
        gate = EgressAllowlist(hosts=["API.Slack.com"])
        # urlparse lowercases the host, and the matcher lowercases the
        # pattern, so mixed case on both sides still matches.
        gate.check("https://api.slack.com/x")


if __name__ == "__main__":
    unittest.main()
