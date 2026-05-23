"""Governance layer for the triage agent.

Four layers stacked on top of the model and Slack client:

1. EgressAllowlist  - block outbound HTTP to non-allowlisted hosts.
                      Inspired by agentleash, applied to whatever HTTP
                      callable the model wants to invoke.
2. ScopeAllowlist   - block any Slack API call whose required scope
                      is not in the OAuth scopes we asked for.
                      Keeps the manifest honest.
3. AuditTrail       - append-only JSONL log of every governed event.
                      Replayable for security review and demo.
4. (consumed elsewhere) tool-arg validation in classify.py and
   structured-output enforcement in triage.py.

The point of this module: a Slack workspace admin can read this file
and decide whether to install the app, without reading the model code.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse


class EgressBlocked(RuntimeError):
    """Raised when the agent attempts to call a non-allowlisted host."""


class ScopeDenied(RuntimeError):
    """Raised when the agent attempts a Slack call without the right scope."""


@dataclass
class AuditEvent:
    """One row in the audit trail."""

    ts: float
    kind: str  # "egress.ok" | "egress.blocked" | "scope.ok" | "scope.denied" | "triage.run" | ...
    detail: dict

    def to_json(self) -> str:
        return json.dumps({"ts": self.ts, "kind": self.kind, "detail": self.detail}, sort_keys=True)


@dataclass
class AuditTrail:
    """Append-only log of governance decisions.

    Defaults to in-memory. If `path` is set, also appends to a JSONL file
    so the trail survives the process. Workspace admins can grep this
    for blocked egress or scope denials after a run.
    """

    events: list[AuditEvent] = field(default_factory=list)
    path: Optional[Path] = None

    def record(self, kind: str, **detail: Any) -> AuditEvent:
        ev = AuditEvent(ts=time.time(), kind=kind, detail=detail)
        self.events.append(ev)
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(ev.to_json() + "\n")
        return ev

    def filter(self, kind: str) -> list[AuditEvent]:
        return [e for e in self.events if e.kind == kind]

    def blocked(self) -> list[AuditEvent]:
        return [e for e in self.events if e.kind.endswith(".blocked") or e.kind.endswith(".denied")]


@dataclass
class EgressAllowlist:
    """Reject any HTTP host that is not in the allowlist.

    The check is on the URL's host only, so subdomains must be
    explicitly listed. Use "*.example.com" for a one-level wildcard.

    Workflow:

        gate = EgressAllowlist(hosts=["slack.com", "api.anthropic.com"], audit=trail)
        gate.check("https://api.anthropic.com/v1/messages")  # ok
        gate.check("https://evil.example.com/exfil")          # raises EgressBlocked
    """

    hosts: list[str]
    audit: Optional[AuditTrail] = None

    def _matches(self, host: str) -> bool:
        host = host.lower()
        for pattern in self.hosts:
            pattern = pattern.lower()
            if pattern == host:
                return True
            if pattern.startswith("*."):
                suffix = pattern[1:]  # ".example.com"
                # one-level wildcard: foo.example.com matches, foo.bar.example.com does not
                if host.endswith(suffix) and host.count(".") == pattern.count("."):
                    return True
        return False

    def check(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            self._audit("egress.blocked", url=url, reason="no_host")
            raise EgressBlocked(f"egress blocked: cannot parse host from {url!r}")
        if not self._matches(host):
            self._audit("egress.blocked", url=url, host=host, reason="not_in_allowlist")
            raise EgressBlocked(
                f"egress blocked: host {host!r} not in allowlist {self.hosts!r}"
            )
        self._audit("egress.ok", url=url, host=host)

    def wrap(self, http_call: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap any HTTP callable so it goes through the allowlist first.

        The wrapped callable must accept the URL as its first positional
        argument or as a keyword `url=`.
        """

        def guarded(*args: Any, **kwargs: Any) -> Any:
            url: Optional[str] = None
            if args:
                first = args[0]
                if isinstance(first, str):
                    url = first
            if url is None:
                url = kwargs.get("url")
            if url is None:
                raise EgressBlocked("egress blocked: could not find URL argument to inspect")
            self.check(url)
            return http_call(*args, **kwargs)

        return guarded

    def _audit(self, kind: str, **detail: Any) -> None:
        if self.audit is not None:
            self.audit.record(kind, **detail)


@dataclass
class ScopeAllowlist:
    """Block Slack API calls whose required scope is not in the manifest.

    Slack APIs require named OAuth scopes (`channels:history`,
    `chat:write`, etc.). If the model wants to call an API outside
    the manifest, we refuse and audit. This keeps the manifest
    documented in code and prevents scope creep.

    Mapping is intentionally a small dict that is easy to audit
    instead of a big upstream catalog import. Add entries as you
    need them.
    """

    granted: list[str]
    audit: Optional[AuditTrail] = None

    METHOD_SCOPES: dict[str, str] = field(
        default_factory=lambda: {
            "conversations.history": "channels:history",
            "conversations.list": "channels:read",
            "conversations.members": "channels:read",
            "users.info": "users:read",
            "chat.postMessage": "chat:write",
            "chat.postEphemeral": "chat:write",
            "reactions.add": "reactions:write",
            "pins.add": "pins:write",
            "files.upload": "files:write",
            "im.history": "im:history",
            "im.list": "im:read",
            "search.messages": "search:read",
        }
    )

    def required_scope(self, method: str) -> Optional[str]:
        return self.METHOD_SCOPES.get(method)

    def check(self, method: str) -> None:
        scope = self.required_scope(method)
        if scope is None:
            # We don't know this method. Be strict: refuse and audit.
            self._audit("scope.denied", method=method, reason="unknown_method")
            raise ScopeDenied(
                f"scope denied: unknown Slack method {method!r}; "
                "add it to ScopeAllowlist.METHOD_SCOPES if intended"
            )
        if scope not in self.granted:
            self._audit("scope.denied", method=method, required=scope, granted=self.granted)
            raise ScopeDenied(
                f"scope denied: {method!r} requires {scope!r} but granted {self.granted!r}"
            )
        self._audit("scope.ok", method=method, scope=scope)

    def _audit(self, kind: str, **detail: Any) -> None:
        if self.audit is not None:
            self.audit.record(kind, **detail)


def make_safe_http(allowlist: Iterable[str], audit: Optional[AuditTrail] = None) -> EgressAllowlist:
    """Convenience builder. Returns a configured EgressAllowlist."""

    return EgressAllowlist(hosts=list(allowlist), audit=audit)
