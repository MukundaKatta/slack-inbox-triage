# 90-second demo script

Three shots. Voiceover in plain English. No on-screen text dumps;
let the terminal output carry it. Run the demo first to capture
output, then film over a clean terminal so the cuts line up.

Setup before recording:

```bash
cd ~/slack-inbox-triage
python3 -m pytest -q                  # confirm 35 passed
clear
```

---

## Shot 1 (0:00 to 0:35) — "What it does"

**Action:** type `python3 examples/triage_demo.py` and run it. Scroll
just to the end of "Shot 1: /triage on a busy inbox channel".

**Voiceover:**

> Most knowledge workers lose their morning to Slack triage.
> Inbox Triage runs as a slash command. You point it at a channel,
> and it classifies every message into recruiter, customer support,
> internal request, or noise. It proposes a label and drafts a reply
> for each one. Notice the per-message confidence score and the
> drafted text. The whole thing is offline. There is no real Slack
> workspace behind this demo.

---

## Shot 2 (0:35 to 1:05) — "What it refuses to do"

**Action:** stay on the same terminal output. Scroll to the
"Shot 2: rogue tool tries to exfil" block. Pause on the `BLOCKED:`
line and the `audit (blocked rows)` line right under it.

**Voiceover:**

> The differentiator is governance. The agent cannot call any Slack
> API outside the OAuth scopes declared in the manifest. It cannot
> call any HTTP host outside its allowlist. Here a rogue tool tries
> to exfiltrate a token to a host the workspace did not authorize.
> The call is refused before it leaves the process, and the refusal
> is written to an append-only audit log.

---

## Shot 3 (1:05 to 1:30) — "Why an admin will install it"

**Action:** scroll to Shot 3's repaired classification. Then `cmd-t`
or split pane to `cat slack_app_manifest.yml` and pause on the
`oauth_config: scopes:` block.

**Voiceover:**

> Even when the model returns malformed JSON, the agent repairs the
> shape and validates the intent and confidence before trusting it.
> The Slack manifest is intentionally small. Five scopes. The
> ScopeAllowlist in code enforces that minimality at runtime. A
> workspace admin can read 200 lines of governance code and know
> exactly what the agent can and cannot do.
>
> Inbox Triage. Built for the Slack Agent for Organizations track.

---

## Cut list

- Shot 1: end of triage report (counts line is the cue)
- Shot 2: `BLOCKED:` line, hold for half a beat on the audit row
- Shot 3: repaired JSON output, then manifest scopes block

Run length: 90 seconds. Trim shot 1 if it goes long; the report has
eight messages and you only need to show two or three to make the
point. The unique selling point is shot 2.
