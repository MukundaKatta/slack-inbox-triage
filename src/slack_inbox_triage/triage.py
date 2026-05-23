"""Triage agent: read a channel, classify, draft replies, propose labels.

The agent is intentionally small and synchronous so the demo and tests
stay deterministic. It takes a SlackClientProtocol-shaped object so
it works with both FakeSlackProvider and a real SlackClient.

Public entry:

    agent = TriageAgent(client=fake, audit=AuditTrail())
    result = agent.triage_channel("C_INBOX")
    print(result.to_markdown())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .classify import (
    ClassifyOutput,
    Intent,
    LLMFn,
    classify_message,
)
from .governance import AuditTrail
from .slack_client import SlackClientProtocol, SlackMessage


# Reply templates per intent. Plain English, no AI cliches.
_REPLY_TEMPLATES: dict[Intent, str] = {
    Intent.RECRUITER: (
        "Thanks for reaching out. I am not actively interviewing right now, "
        "but happy to keep your details on file. If the role is remote and "
        "open about comp band, send a one-pager and I will get back to you."
    ),
    Intent.CUSTOMER_SUPPORT: (
        "Sorry you hit this. I have logged the issue and pulled the error ID. "
        "Can you confirm the affected account or workspace and the time you "
        "saw the failure? I will follow up with a fix or a workaround today."
    ),
    Intent.INTERNAL_REQUEST: (
        "Got it. I will pick this up today. If it blocks anything sooner, "
        "ping me here and I will reshuffle."
    ),
    Intent.NOISE: (
        ""  # noise messages do not get a drafted reply
    ),
    Intent.UNKNOWN: (
        "Thanks for the message. Want to tell me a bit more about what you "
        "need? Happy to point you to the right person."
    ),
}

# Suggested label per intent. These map onto Slack reactions or
# bookmark categories on the real workspace.
_LABEL_BY_INTENT: dict[Intent, str] = {
    Intent.RECRUITER: "recruiter",
    Intent.CUSTOMER_SUPPORT: "support",
    Intent.INTERNAL_REQUEST: "team",
    Intent.NOISE: "noise",
    Intent.UNKNOWN: "review",
}


@dataclass
class MessageVerdict:
    """One classified message with the agent's suggested action."""

    message: SlackMessage
    classification: ClassifyOutput
    suggested_label: str
    drafted_reply: str

    @property
    def intent(self) -> Intent:
        return self.classification.intent

    def to_dict(self) -> dict:
        return {
            "ts": self.message.ts,
            "user": self.message.user,
            "channel": self.message.channel,
            "text": self.message.text,
            "intent": self.intent.value,
            "confidence": round(self.classification.confidence, 3),
            "rationale": self.classification.rationale,
            "suggested_label": self.suggested_label,
            "drafted_reply": self.drafted_reply,
        }


@dataclass
class TriageResult:
    """Result of triaging a channel."""

    channel: str
    verdicts: list[MessageVerdict] = field(default_factory=list)

    def by_intent(self, intent: Intent) -> list[MessageVerdict]:
        return [v for v in self.verdicts if v.intent == intent]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.verdicts:
            out[v.intent.value] = out.get(v.intent.value, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "counts": self.counts(),
            "verdicts": [v.to_dict() for v in self.verdicts],
        }

    def to_markdown(self) -> str:
        """Render the result as a Slack-friendly markdown block."""

        lines: list[str] = []
        lines.append(f"*Triage report for `{self.channel}`*")
        counts = self.counts()
        if counts:
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            lines.append(f"_{summary}_")
        lines.append("")
        for v in self.verdicts:
            lines.append(
                f"- *{v.intent.value}* "
                f"(conf {v.classification.confidence:.2f}, label `{v.suggested_label}`)"
            )
            lines.append(f"  > {_one_line(v.message.text)}")
            if v.drafted_reply:
                lines.append("  Drafted reply:")
                lines.append(f"  ```\n  {v.drafted_reply}\n  ```")
        return "\n".join(lines)


def _one_line(s: str, limit: int = 140) -> str:
    flat = " ".join(s.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


@dataclass
class TriageAgent:
    """The main agent.

    Wiring:
        client    - any SlackClientProtocol (FakeSlackProvider, SlackClient, ...)
        audit     - shared audit trail; we record `triage.run` events
        llm       - optional LLM callable for classification
        min_confidence - below this we tag the message UNKNOWN regardless
    """

    client: SlackClientProtocol
    audit: Optional[AuditTrail] = None
    llm: Optional[LLMFn] = None
    min_confidence: float = 0.4

    def triage_channel(
        self,
        channel: str,
        *,
        limit: int = 50,
        skip_users: Iterable[str] = (),
    ) -> TriageResult:
        """Read recent messages and classify each one."""

        messages = self.client.channel_history(channel, limit=limit)
        skip = set(skip_users)
        verdicts: list[MessageVerdict] = []
        for m in messages:
            if m.user in skip:
                continue
            classification = classify_message(m.text, llm=self.llm)
            if classification.confidence < self.min_confidence and classification.intent != Intent.NOISE:
                classification = ClassifyOutput(
                    Intent.UNKNOWN, classification.confidence, "below_min_confidence"
                )
            label = _LABEL_BY_INTENT[classification.intent]
            reply = _REPLY_TEMPLATES[classification.intent]
            verdicts.append(MessageVerdict(m, classification, label, reply))

        result = TriageResult(channel=channel, verdicts=verdicts)
        if self.audit is not None:
            self.audit.record(
                "triage.run",
                channel=channel,
                count=len(verdicts),
                counts=result.counts(),
            )
        return result

    def post_summary(self, result: TriageResult, channel: str) -> dict:
        """Post the triage summary back to Slack as an ephemeral-style message.

        Real deployments should use chat.postEphemeral so the report is
        only visible to the requesting user. The Fake provider treats
        both the same.
        """

        body = result.to_markdown()
        return self.client.post_message(channel=channel, text=body)
