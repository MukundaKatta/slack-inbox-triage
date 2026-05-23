# slack-inbox-triage: governed inbox triage for Slack workspaces

**Track:** Slack Agent for Organizations
**Hackathon:** Slack Agent Builder Challenge
**Builder:** Mukunda Katta (solo)
**Repo:** https://github.com/MukundaKatta/slack-inbox-triage

## The problem

Most knowledge workers I know live in Slack and lose half their morning to inbox triage. Sales gets pinged by recruiters. Engineers get pinged by customers in shared channels. Managers get pinged by their reports. The pings all live in the same channel list, in roughly the same font, with roughly the same urgency cue. There is no triage layer between Slack and the brain.

An AI agent is the obvious fix. The problem is that every agent demo so far asks workspace admins to give a bot broad scopes (`chat:write`, `channels:read`, `channels:history`, sometimes much more), and to trust that the underlying model will not call out to the wider internet or do something embarrassing under load. That is fine on a personal Slack. It is not fine on a workspace with paying customers, employee data, or any privacy commitments.

slack-inbox-triage is built for that second case: the workspace where the agent is judged not just by what it does, but by what it provably cannot do.

## What it does

The bot exposes one slash command, `/triage`, and an optional scheduled job. Given a channel, it reads the recent backlog, classifies every message into one of four intents (recruiter, customer support, internal request, noise) with a confidence score, proposes a label (a Slack reaction), and drafts a reply you can edit and send. The classifier uses the model if it is available and falls back to a deterministic heuristic if the model is unreachable or returns garbage, so the agent never blocks on the LLM.

The output is rendered as a markdown report and posted ephemerally back to the user who ran the command, so the channel does not get noisy.

## The four governance layers (the wedge)

This is the only entry I have seen where governance is a first-class part of the agent, not a layer that sits on top:

1. **Scope allowlist.** Every Slack API call routes through `ScopeAllowlist.check(method)`, which looks up the OAuth scope the call requires and refuses if the scope is not in the manifest. If the model tries to call `admin.users.delete`, the call is refused before it ever leaves the process. The Slack manifest in this repo is the source of truth, and the allowlist is intentionally a small dict in `governance.py` that any admin can audit in 30 seconds.
2. **Egress allowlist.** Any outbound HTTP host the agent tries to reach is checked against a list before the request is made. A "rogue" tool that tries to exfiltrate to a non-allowlisted host gets `EgressBlocked` and a blocked row in the audit trail. Wildcards (`*.slack.com`) are supported but capped at one level deep.
3. **Tool-arg validation.** Slack method arguments are validated before they are passed downstream: `chat.postMessage` requires non-empty channel and text and caps text at 40,000 chars; `conversations.history` caps the limit at 1000; `reactions.add` requires all three fields. The errors are written in plain English so a model can retry against them on a follow-up turn.
4. **Output schema repair.** The classifier output is a closed `Intent` enum plus a clamped `[0, 1]` confidence plus a 200-char rationale. The model can return JSON inside markdown fences, JSON with a trailing comma, or JSON with synonyms (`"bug"` instead of `"customer_support"`); the repair layer parses, validates, and clamps before any of it reaches the rest of the agent. If the model returns something unsalvageable, the heuristic classifier takes over.

All four layers write to an append-only `AuditTrail`. The trail can be persisted to a JSONL file so a workspace admin or a SIEM can replay every governance decision after the fact. There is no opaque internal state.

## Business case for the Agent for Organizations track

The Slack Marketplace review explicitly cares about scope minimality, predictable behavior, and a clear story for what the agent can and cannot do. This repo is built exactly to that bar:

- The manifest in `slack_app_manifest.yml` asks for five scopes. Not six. Not "just in case."
- The `ScopeAllowlist` makes that minimality enforceable at runtime, not just on paper. A junior engineer who adds a new Slack call cannot ship without also updating the manifest and the scope map; the test suite will fail otherwise.
- The audit trail gives the buyer's security team an artifact they can read. Most agents in this space treat security as a documentation problem; this one treats it as a code problem.

This positioning is what unlocks the "for Organizations" tier: the buyer is not the end user, the buyer is the admin who signs off on the install. The admin's job gets dramatically easier when the install boils down to "read this manifest, read this 200-line governance file, and decide."

## Demo output

Running `python3 examples/triage_demo.py` on the bundled synthetic channel produces:

```
*Triage report for `C_INBOX`*
_customer_support: 2, internal_request: 2, noise: 2, recruiter: 2_

- *recruiter* (conf 0.95, label `recruiter`)
  > Hi! I'm Amy from Stripe's recruiting team. Saw your profile and wanted to chat about a Staff Engineer role. Free this week?
  Drafted reply:
    Thanks for reaching out. I am not actively interviewing right now,
    but happy to keep your details on file. If the role is remote and
    open about comp band, send a one-pager and I will get back to you.
- *customer_support* (conf 0.95, label `support`)
  > Hey, the export-to-csv button on the dashboard is throwing a 500. Steps to repro: open Reports > click Export. Error ID: req_19xz.
  Drafted reply:
    Sorry you hit this. I have logged the issue and pulled the error ID.
    Can you confirm the affected account or workspace and the time you
    saw the failure? I will follow up with a fix or a workaround today.
```

The demo also shows the rogue-egress block and the malformed-JSON repair, in that order.

## How it gets to Slack Marketplace

The path from this repo to a live Marketplace listing is five steps, documented in `docs/DEPLOY.md`:

1. Paste `slack_app_manifest.yml` into api.slack.com -> Create New App -> From an app manifest.
2. Install to a workspace and grab the bot token.
3. Wire `SlackClient` with a `slack-sdk` `WebClient` and your `ScopeAllowlist`.
4. Register `/triage` to call `agent.triage_channel(channel_id)`.
5. Submit for Marketplace review and supply the App ID in the Devpost submission.

The repo also ships a `TriageScheduler` for workspaces that want a 15-minute heartbeat triage instead of an on-demand one. Same agent, same governance.

## What is in the repo

- `src/slack_inbox_triage/triage.py` - the agent orchestrator
- `src/slack_inbox_triage/governance.py` - the four governance primitives
- `src/slack_inbox_triage/slack_client.py` - the `SlackClientProtocol`, the real adapter, and the deterministic `FakeSlackProvider`
- `src/slack_inbox_triage/classify.py` - intent classifier with LLM repair and tool-arg validation
- `src/slack_inbox_triage/scheduler.py` - in-process scheduler for periodic triage
- `tests/` - 35 tests, fully offline, deterministic
- `examples/triage_demo.py` - 90-second offline demo
- `slack_app_manifest.yml` - minimal Slack app manifest, ready to paste
- `docs/DEPLOY.md` - real-workspace deploy guide

## Limitations and what I would build next

The classifier is intentionally small. Real workspaces will want a finer intent taxonomy (escalations, exec asks, vendor outreach, on-call pings, etc.) and probably a per-user style profile for the drafted replies. Both are additive: the `Intent` enum is closed, but extending it is a one-file change, and the reply templates are a dict keyed on intent.

The egress allowlist today operates on hostnames. A production deployment might want IP ranges, methods, and per-tool quotas. Same shape, just more entries.

For the hackathon, the wedge is the governance posture and the fact that the demo runs offline. That is what makes the agent installable in a real org instead of a personal workspace.
