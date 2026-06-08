# slack-inbox-triage

A governed inbox-triage agent for Slack workspaces. Classifies messages, drafts replies, and proposes labels. Refuses to call Slack APIs outside its declared OAuth scopes, and blocks outbound HTTP to hosts not on its allowlist.

Built for the [Slack Agent Builder Challenge](https://slackhack.devpost.com/) (Slack Agent for Organizations track).

## What it does

- `/triage` classifies a channel backlog into recruiter, customer support, internal request, or noise, with a confidence score and a drafted reply for each message.
- Governance is baked in: every Slack call routes through a scope allowlist, every outbound HTTP call routes through a host allowlist, every decision is recorded in an append-only audit trail.
- Comes with a `FakeSlackProvider` so the agent, tests, and the demo run with no real workspace.

## Quickstart

The package has **no runtime dependencies** and the test suite uses only the
Python standard library, so there is nothing to install to try it:

```bash
git clone https://github.com/MukundaKatta/slack-inbox-triage
cd slack-inbox-triage
python3 -m unittest discover -s tests   # 53 tests, runs in under a second
python3 examples/triage_demo.py         # offline demo, no network
```

`pytest` is supported too if you prefer it (`pip install -e ".[dev]" && pytest -q`),
but it is optional — the suite is written against `unittest` and ships
fixtures in `tests/conftest.py` for pytest users.

## Library usage

```python
from slack_inbox_triage import TriageAgent, AuditTrail
from slack_inbox_triage.governance import ScopeAllowlist
from slack_inbox_triage.slack_client import build_demo_provider

# Wire a scope guard that mirrors the manifest, then a deterministic
# offline Slack provider (swap in a real SlackClient in production).
audit = AuditTrail()
scope = ScopeAllowlist(
    granted=["channels:history", "channels:read", "chat:write", "reactions:write"],
    audit=audit,
)
provider = build_demo_provider(scope_gate=scope)

agent = TriageAgent(client=provider, audit=audit)
result = agent.triage_channel("C_INBOX")

print(result.counts())          # {'recruiter': 2, 'customer_support': 2, ...}
print(result.to_markdown())     # Slack-friendly report

# Every governance decision is on the audit trail:
print(len(audit.filter("scope.ok")), "allowed Slack calls")
print(len(audit.blocked()), "refused calls")
```

To classify a single message (with or without an LLM):

```python
from slack_inbox_triage import classify_message, Intent

out = classify_message("the export button is throwing a 500 error")
assert out.intent is Intent.CUSTOMER_SUPPORT

# Pass any callable as the model. Malformed output is repaired and validated;
# if it is unsalvageable the deterministic heuristic takes over.
out = classify_message("...", llm=lambda text: my_model(text))
```

## API reference

| Symbol | Where | What it is |
| --- | --- | --- |
| `TriageAgent` | `triage.py` | Orchestrator: read a channel, classify, draft replies, propose labels. `triage_channel(channel, *, limit, skip_users)` and `post_summary(result, channel)`. |
| `TriageResult` | `triage.py` | Result of a run. `counts()`, `by_intent(intent)`, `to_dict()`, `to_markdown()`. |
| `MessageVerdict` | `triage.py` | One classified message plus the suggested label and drafted reply. |
| `classify_message` | `classify.py` | `classify_message(text, *, llm=None) -> ClassifyOutput`. Heuristic by default; repairs and validates LLM output when `llm` is given. |
| `Intent` | `classify.py` | Closed enum: `RECRUITER`, `CUSTOMER_SUPPORT`, `INTERNAL_REQUEST`, `NOISE`, `UNKNOWN`. |
| `validate_tool_args` | `classify.py` | Raises a plain-English `ValueError` for malformed Slack method args. |
| `ScopeAllowlist` | `governance.py` | `check(method)` raises `ScopeDenied` if the method's required OAuth scope is not granted. |
| `EgressAllowlist` | `governance.py` | `check(url)` / `wrap(http_call)` raise `EgressBlocked` for non-allowlisted hosts. |
| `AuditTrail` | `governance.py` | Append-only log. In-memory by default; pass `path=` to also write JSONL. |
| `SlackClient` | `slack_client.py` | Real adapter around a `call_fn` you provide (no hard `slack-sdk` dependency). |
| `FakeSlackProvider` | `slack_client.py` | Deterministic offline Slack stand-in for tests and demos. |
| `TriageScheduler` | `scheduler.py` | Drive the agent on a fixed interval; you inject the clock and sleep. |

## Governance, at a glance

| Layer | What it does | File |
| --- | --- | --- |
| Scope allowlist | Refuses any Slack API call whose required scope is not in the manifest | `src/slack_inbox_triage/governance.py` |
| Egress allowlist | Refuses any outbound HTTP host that is not on the allowlist; writes a blocked row to the audit trail | `src/slack_inbox_triage/governance.py` |
| Tool-arg validation | Rejects malformed `chat.postMessage`, `conversations.history`, and `reactions.add` arguments with LLM-friendly error messages | `src/slack_inbox_triage/classify.py` |
| Output schema repair | Parses noisy model output (fenced blocks, trailing commas) and validates the intent + confidence shape before trusting it | `src/slack_inbox_triage/classify.py` |
| Audit trail | Append-only JSONL of every governance decision, ready for security review | `src/slack_inbox_triage/governance.py` |

## Sample `/triage` output

```
*Triage report for `C_INBOX`*
_customer_support: 2, internal_request: 2, noise: 2, recruiter: 2_

- *recruiter* (conf 0.95, label `recruiter`)
  > Hi! I'm Amy from Stripe's recruiting team. Saw your profile and wanted to chat about a Staff Engineer role. Free this week?
  Drafted reply:
  ```
  Thanks for reaching out. I am not actively interviewing right now, but happy to keep your details on file. If the role is remote and open about comp band, send a one-pager and I will get back to you.
  ```
- *customer_support* (conf 0.95, label `support`)
  > Hey, the export-to-csv button on the dashboard is throwing a 500. Steps to repro: open Reports > click Export. Error ID: req_19xz.
  Drafted reply:
  ```
  Sorry you hit this. I have logged the issue and pulled the error ID. Can you confirm the affected account or workspace and the time you saw the failure? I will follow up with a fix or a workaround today.
  ```
```

## How to ship to the Slack Marketplace

1. Open `slack_app_manifest.yml` in this repo. It lists only the scopes the agent actually uses (`channels:history`, `channels:read`, `chat:write`, `reactions:write`, `commands`).
2. Go to api.slack.com -> Your Apps -> Create New App -> From an app manifest, and paste the manifest.
3. Install the app to your workspace and copy the bot token. Pass it into `SlackClient(call_fn=...)` (see `docs/DEPLOY.md` for a working `slack-sdk` snippet).
4. Wire the `/triage` slash command to your handler. The handler should construct a `TriageAgent` per workspace and call `agent.triage_channel(channel_id)`.
5. Submit the app for Marketplace review. Use the App ID in your Devpost submission for the Slack Agent for Organizations track.

Full deployment notes, including the `app_mentioned` handler, scheduled run setup, and workspace install flow, live in [docs/DEPLOY.md](docs/DEPLOY.md).

## Wedge

This is the only entry in the challenge that treats governance as a first-class feature of the agent, not an afterthought. A workspace admin can read `src/slack_inbox_triage/governance.py` and `slack_app_manifest.yml` in five minutes and know exactly what the agent can and cannot do, even if the underlying model misbehaves.

## License

MIT.
