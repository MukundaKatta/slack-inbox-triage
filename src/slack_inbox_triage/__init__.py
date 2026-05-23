"""slack-inbox-triage: governed Slack inbox triage agent.

Public API:
    TriageAgent      - main agent orchestrator
    FakeSlackProvider - offline harness for tests and demos
    SlackClient      - real Slack client adapter (BYO token)
    EgressAllowlist  - host allowlist with audit trail
    ScopeAllowlist   - Slack OAuth scope guard
    classify_message - intent classification
"""

from .triage import TriageAgent, TriageResult, MessageVerdict
from .slack_client import FakeSlackProvider, SlackClient, SlackMessage
from .governance import (
    EgressAllowlist,
    ScopeAllowlist,
    EgressBlocked,
    ScopeDenied,
    AuditTrail,
)
from .classify import classify_message, Intent

__version__ = "0.1.0"

__all__ = [
    "TriageAgent",
    "TriageResult",
    "MessageVerdict",
    "FakeSlackProvider",
    "SlackClient",
    "SlackMessage",
    "EgressAllowlist",
    "ScopeAllowlist",
    "EgressBlocked",
    "ScopeDenied",
    "AuditTrail",
    "classify_message",
    "Intent",
]
