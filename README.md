# slack-inbox-triage

A governed inbox-triage agent for Slack workspaces. Classifies messages, drafts replies, and proposes labels. Refuses to call Slack APIs outside its declared OAuth scopes, and blocks outbound HTTP to hosts not on its allowlist.

Built for the [Slack Agent Builder Challenge](https://slackhack.devpost.com/) (Slack Agent for Organizations track).

## What it does

- `/triage` classifies a channel backlog into recruiter, customer support, internal request, or noise, with a confidence score and a drafted reply for each message.
- Governance is baked in: every Slack call routes through a scope allowlist, every outbound HTTP call routes through a host allowlist, every decision is recorded in an append-only audit trail.
- Comes with a `FakeSlackProvider` so the agent, tests, and the demo run with no real workspace.

## Quickstart

```bash
git clone https://github.com/MukundaKatta/slack-inbox-triage
cd slack-inbox-triage
python3 -m pytest -q                  # 35 tests, runs in under a second
python3 examples/triage_demo.py       # 90-second offline demo, no network
```

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
