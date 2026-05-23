"""Slack client adapter and a deterministic FakeSlackProvider.

The agent does not call slack-sdk directly. It calls a small protocol
defined here. Two implementations:

* SlackClient        - real, wraps a callable you provide (so the
                       library has no hard slack-sdk dependency)
* FakeSlackProvider  - offline harness used by tests and the demo

Every call routes through ScopeAllowlist first so the manifest stays
honest. See governance.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

from .governance import ScopeAllowlist


@dataclass(frozen=True)
class SlackMessage:
    """A normalized Slack message."""

    ts: str
    user: str
    channel: str
    text: str
    thread_ts: Optional[str] = None
    is_dm: bool = False


class SlackClientProtocol(Protocol):
    """Minimal Slack surface the triage agent needs.

    Designed so a fake implementation can be swapped in for tests.
    """

    def call(self, method: str, **params: Any) -> dict:
        ...

    def channel_history(self, channel: str, limit: int = 50) -> list[SlackMessage]:
        ...

    def post_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> dict:
        ...

    def add_reaction(self, channel: str, ts: str, name: str) -> dict:
        ...


@dataclass
class SlackClient:
    """Real Slack client adapter.

    Provide a `call_fn` that performs the actual HTTP request (so the
    library does not pin slack-sdk). Every method call routes through
    ScopeAllowlist first.

        client = SlackClient(
            call_fn=my_slack_sdk_caller,
            scope_gate=ScopeAllowlist(granted=["channels:history", "chat:write"]),
        )
    """

    call_fn: Callable[..., dict]
    scope_gate: ScopeAllowlist

    def call(self, method: str, **params: Any) -> dict:
        self.scope_gate.check(method)
        return self.call_fn(method, **params)

    def channel_history(self, channel: str, limit: int = 50) -> list[SlackMessage]:
        raw = self.call("conversations.history", channel=channel, limit=limit)
        msgs: list[SlackMessage] = []
        for m in raw.get("messages", []):
            msgs.append(
                SlackMessage(
                    ts=m["ts"],
                    user=m.get("user", "U_UNKNOWN"),
                    channel=channel,
                    text=m.get("text", ""),
                    thread_ts=m.get("thread_ts"),
                    is_dm=False,
                )
            )
        return msgs

    def post_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts
        return self.call("chat.postMessage", **payload)

    def add_reaction(self, channel: str, ts: str, name: str) -> dict:
        return self.call("reactions.add", channel=channel, timestamp=ts, name=name)


@dataclass
class FakeSlackProvider:
    """Deterministic in-memory Slack stand-in for tests and demos.

    Seeded with channels and messages. All write operations are
    recorded so tests can assert what the agent did.

    Use SlackClient with `FakeSlackProvider().call` as the call_fn
    when you want the scope guard to still run, or use FakeSlackProvider
    directly when you want to skip the guard (rare).
    """

    channels: dict[str, list[SlackMessage]] = field(default_factory=dict)
    posted: list[dict] = field(default_factory=list)
    reactions: list[dict] = field(default_factory=list)
    scope_gate: Optional[ScopeAllowlist] = None

    @classmethod
    def with_seed(cls, channels: dict[str, list[SlackMessage]],
                  scope_gate: Optional[ScopeAllowlist] = None) -> "FakeSlackProvider":
        return cls(channels=dict(channels), scope_gate=scope_gate)

    def _gate(self, method: str) -> None:
        if self.scope_gate is not None:
            self.scope_gate.check(method)

    def call(self, method: str, **params: Any) -> dict:
        """Generic call shim. Useful when wiring FakeSlackProvider into SlackClient."""

        self._gate(method)
        if method == "conversations.history":
            ch = params["channel"]
            msgs = self.channels.get(ch, [])
            return {
                "ok": True,
                "messages": [
                    {
                        "ts": m.ts,
                        "user": m.user,
                        "text": m.text,
                        "thread_ts": m.thread_ts,
                    }
                    for m in msgs[: params.get("limit", 50)]
                ],
            }
        if method == "chat.postMessage":
            self.posted.append(dict(params))
            return {"ok": True, "ts": f"posted-{len(self.posted)}"}
        if method == "reactions.add":
            self.reactions.append(dict(params))
            return {"ok": True}
        return {"ok": True, "method": method, "params": params}

    def channel_history(self, channel: str, limit: int = 50) -> list[SlackMessage]:
        self._gate("conversations.history")
        return list(self.channels.get(channel, []))[:limit]

    def post_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> dict:
        self._gate("chat.postMessage")
        self.posted.append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return {"ok": True, "ts": f"posted-{len(self.posted)}"}

    def add_reaction(self, channel: str, ts: str, name: str) -> dict:
        self._gate("reactions.add")
        self.reactions.append({"channel": channel, "ts": ts, "name": name})
        return {"ok": True}


def build_demo_provider(scope_gate: Optional[ScopeAllowlist] = None) -> FakeSlackProvider:
    """Return a FakeSlackProvider preloaded with a mixed-intent channel.

    Used by examples/triage_demo.py and tests that want a realistic
    backlog without writing fixtures inline.
    """

    msgs = [
        SlackMessage(
            ts="1716470000.000100",
            user="U_RECRUITER_AMY",
            channel="C_INBOX",
            text=(
                "Hi! I'm Amy from Stripe's recruiting team. Saw your profile "
                "and wanted to chat about a Staff Engineer role. Free this week?"
            ),
        ),
        SlackMessage(
            ts="1716470100.000200",
            user="U_CUSTOMER_BEN",
            channel="C_INBOX",
            text=(
                "Hey, the export-to-csv button on the dashboard is throwing a 500. "
                "Steps to repro: open Reports > click Export. Error ID: req_19xz."
            ),
        ),
        SlackMessage(
            ts="1716470200.000300",
            user="U_TEAMMATE_CARLA",
            channel="C_INBOX",
            text=(
                "Can you review my PR #482 today? It blocks the Q3 release "
                "and needs a second pair of eyes on the auth path."
            ),
        ),
        SlackMessage(
            ts="1716470300.000400",
            user="U_NOISE_DAVE",
            channel="C_INBOX",
            text="lol that meme channel is gold today",
        ),
        SlackMessage(
            ts="1716470400.000500",
            user="U_CUSTOMER_EVE",
            channel="C_INBOX",
            text=(
                "Following up on my last message: still seeing the 429 on the "
                "billing API after the 'fix'. This is blocking our launch."
            ),
        ),
        SlackMessage(
            ts="1716470500.000600",
            user="U_RECRUITER_FRED",
            channel="C_INBOX",
            text=(
                "Hello, I'm a senior recruiter at Acme. We have a remote "
                "principal eng opportunity that pays $400k+. Open to a call?"
            ),
        ),
        SlackMessage(
            ts="1716470600.000700",
            user="U_TEAMMATE_GINA",
            channel="C_INBOX",
            text=(
                "Quick request: can you push the deploy doc update to main "
                "before EOD? I'll add the screenshots after."
            ),
        ),
        SlackMessage(
            ts="1716470700.000800",
            user="U_NOISE_HENRY",
            channel="C_INBOX",
            text="brb coffee",
        ),
    ]
    return FakeSlackProvider.with_seed({"C_INBOX": msgs}, scope_gate=scope_gate)


def _required_scopes_for(seq: Iterable[str]) -> list[str]:
    """Helper: minimum scopes needed to support these Slack methods."""

    mapping = ScopeAllowlist(granted=[]).METHOD_SCOPES
    return sorted({mapping[m] for m in seq if m in mapping})
