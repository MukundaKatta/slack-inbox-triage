# Deploying slack-inbox-triage to a real Slack workspace

This document describes the path from the offline `FakeSlackProvider`
demo to a working install on a real Slack workspace.

## 1. Create the Slack app

1. Go to <https://api.slack.com/apps> and choose **Create New App ->
   From an app manifest**.
2. Pick the workspace you want to install into (use a dev workspace
   first).
3. Paste the contents of `slack_app_manifest.yml`.

The manifest declares exactly five OAuth scopes:

- `channels:history` - read messages in channels the bot is in
- `channels:read` - list channels (for the slash command target picker)
- `chat:write` - post the triage summary
- `reactions:write` - add a label reaction
- `commands` - register the `/triage` slash command

If you ever add a new Slack API call to the agent, update both the
manifest and `ScopeAllowlist.METHOD_SCOPES` in
`src/slack_inbox_triage/governance.py`. The agent will refuse the call
at runtime if the two do not agree.

## 2. Install the app to your workspace

1. In the app's settings page, click **Install to Workspace**.
2. Approve the requested scopes.
3. Copy the **Bot User OAuth Token** (it starts with `xoxb-`). Keep it
   secret. Store it in a secret manager or your `.env`, never commit it.

## 3. Wire the agent to slack-sdk

`slack-inbox-triage` does not depend on `slack-sdk` directly. You
provide a callable, and the agent uses it. This keeps the library
deployable on Lambda, Fly, Modal, or anywhere Python runs.

```python
from slack_sdk import WebClient
from slack_inbox_triage import (
    SlackClient,
    ScopeAllowlist,
    AuditTrail,
    TriageAgent,
)

slack = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

audit = AuditTrail(path="/var/log/inbox-triage/audit.jsonl")
scope = ScopeAllowlist(
    granted=[
        "channels:history",
        "channels:read",
        "chat:write",
        "reactions:write",
    ],
    audit=audit,
)

def call_fn(method: str, **params):
    # slack-sdk's WebClient maps method names directly.
    return slack.api_call(method, params=params).data

client = SlackClient(call_fn=call_fn, scope_gate=scope)
agent = TriageAgent(client=client, audit=audit)
```

## 4. Handle the `/triage` slash command

Use the Slack Bolt framework or your own HTTP handler. The minimum
shape is:

```python
@app.command("/triage")
def handle_triage(ack, command, respond):
    ack()
    channel = command.get("text", "").strip() or command["channel_id"]
    result = agent.triage_channel(channel)
    respond(result.to_markdown())
```

Use `respond(...)` instead of `chat.postMessage` so the report is
ephemeral by default (only the user who ran `/triage` sees it).

## 5. Optional: scheduled triage

For a heads-up summary every 15 minutes, wire `TriageScheduler` into
your worker:

```python
from slack_inbox_triage.scheduler import TriageScheduler
import time

sched = TriageScheduler(
    agent=agent,
    channels=["C012345678"],
    interval_s=900,
)

for result in sched.run(
    max_iterations=10_000,
    clock=time.time,
    sleep=time.sleep,
):
    if result.counts().get("customer_support", 0) > 0:
        agent.post_summary(result, channel="C_OPS_HEADSUP")
```

## 6. Submit to the Slack Marketplace

1. In your app's settings, go to **Manage Distribution** and complete
   the listing.
2. Submit for review. Save the **App ID** that Slack assigns. The
   Slack Agent Builder Challenge requires it for the
   Slack Agent for Organizations track.
3. Provide a developer sandbox URL in your Devpost submission so the
   judges can install and try the app.

## Operational notes

- The audit trail JSONL is the single source of truth for what the
  agent did. Tail it with `tail -f` during an incident, or ship it to
  your SIEM. Rows are stable, append-only, and one JSON object per
  line.
- If the LLM is unreachable, the heuristic classifier still runs.
  Triage degrades gracefully instead of failing.
- All write operations route through `ScopeAllowlist`. If you forget
  to grant a scope in the manifest, the agent will raise `ScopeDenied`
  in production. Watch for `scope.denied` events in the audit trail
  during canary.
