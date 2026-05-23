"""Intent classification with tool-arg validation.

Two layers here:

1. A deterministic heuristic classifier that runs offline. Useful as
   a sanity check and as a fallback when the model is unavailable.
2. A pluggable LLM seam: pass a callable and the agent will use it,
   but the result is validated and repaired before being trusted.

The validate-before-use idea is the agentvet wedge applied to model
output instead of tool arguments: the model is just one more tool,
and its output shape is a "tool arg" that the rest of the agent
will rely on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Intent(str, Enum):
    """Closed set of intents the triage agent recognizes.

    Keeping this closed (no freeform string branching) lets us
    write deterministic routing in triage.py.
    """

    RECRUITER = "recruiter"
    CUSTOMER_SUPPORT = "customer_support"
    INTERNAL_REQUEST = "internal_request"
    NOISE = "noise"
    UNKNOWN = "unknown"


# Heuristic vocabulary. American spelling, lowercased.
_RECRUITER_KEYWORDS = (
    "recruiter",
    "recruiting",
    "opportunity",
    "role",
    "principal eng",
    "staff engineer",
    "principal engineer",
    "senior engineer",
    "compensation",
    "open to a call",
    "open to chatting",
    "saw your profile",
    "we have a remote",
)
_SUPPORT_KEYWORDS = (
    "500",
    "429",
    "error",
    "bug",
    "broken",
    "throwing",
    "steps to repro",
    "blocking our",
    "fix didn",
    "after the 'fix'",
    "still seeing",
    "still broken",
    "the api",
    "dashboard",
    "export",
)
_INTERNAL_KEYWORDS = (
    "can you review",
    "review my pr",
    "blocks the q",
    "needs a second pair",
    "deploy doc",
    "push the deploy",
    "quick request",
    "before eod",
    "code review",
    "ship by",
)
_NOISE_KEYWORDS = (
    "lol",
    "meme",
    "brb",
    "coffee",
    "lunch",
    "fyi this is funny",
    "🤣",
    "😂",
)


@dataclass
class ClassifyOutput:
    """Validated classification output.

    Shape is guaranteed even if the model returns garbage; see
    `_repair_and_validate` below.
    """

    intent: Intent
    confidence: float  # 0.0 to 1.0
    rationale: str

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
        }


# LLM callable type: takes message text, returns whatever string the model produced.
LLMFn = Callable[[str], str]


def classify_message(
    text: str,
    *,
    llm: Optional[LLMFn] = None,
    seed: int = 0,
) -> ClassifyOutput:
    """Classify a message into one Intent.

    If `llm` is provided, the LLM result is parsed and repaired into
    a ClassifyOutput. If the LLM fails or returns malformed output,
    we fall back to the deterministic heuristic.

    `seed` is unused today; kept so callers can plumb a seed through
    without changing the call site later.
    """

    del seed  # kept for forward compatibility
    if llm is not None:
        try:
            raw = llm(text)
        except Exception as exc:  # noqa: BLE001 — defensive: any LLM failure -> fallback
            return _heuristic(text, reason=f"llm_error: {exc}")
        parsed = _repair_and_validate(raw)
        if parsed is not None:
            return parsed
        # Fall through to heuristic if the model output was unsalvageable.
        return _heuristic(text, reason="llm_output_unparseable")
    return _heuristic(text)


def _heuristic(text: str, *, reason: str = "heuristic") -> ClassifyOutput:
    """Deterministic classifier used when the LLM is absent or broken."""

    lowered = text.lower()

    def hits(words: tuple[str, ...]) -> int:
        return sum(1 for w in words if w in lowered)

    rec = hits(_RECRUITER_KEYWORDS)
    sup = hits(_SUPPORT_KEYWORDS)
    intl = hits(_INTERNAL_KEYWORDS)
    noi = hits(_NOISE_KEYWORDS)

    scores = {
        Intent.RECRUITER: rec,
        Intent.CUSTOMER_SUPPORT: sup,
        Intent.INTERNAL_REQUEST: intl,
        Intent.NOISE: noi,
    }
    best = max(scores, key=lambda k: scores[k])
    best_score = scores[best]
    if best_score == 0:
        return ClassifyOutput(Intent.UNKNOWN, 0.2, reason)

    # Convert hit count to confidence. Saturates around 3 hits.
    confidence = min(0.55 + 0.13 * best_score, 0.95)
    return ClassifyOutput(best, confidence, reason)


# Public alias so callers can use `cast_json` style names from the wedge story.
def cast_json(raw: str) -> Optional[dict]:
    """Try to parse JSON out of a possibly-noisy LLM string. Returns None on failure."""

    return _try_parse_json(raw)


def _try_parse_json(raw: str) -> Optional[dict]:
    """Tolerant JSON parser for typical LLM noise.

    Handles: leading prose before the JSON, fenced ```json blocks,
    and trailing commas. This is the same pattern as the llm-json-repair
    crate, narrowed to what classifiers actually need.
    """

    if not raw:
        return None
    text = raw.strip()

    # Strip ```json ... ``` fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    # Find the first balanced { ... } object.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None
    candidate = text[start : end + 1]

    # Drop trailing commas: ",}" -> "}" and ",]" -> "]".
    candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _repair_and_validate(raw: str) -> Optional[ClassifyOutput]:
    """Parse + validate the model output. Returns None if unsalvageable."""

    obj = _try_parse_json(raw)
    if obj is None:
        return None

    intent_str = obj.get("intent")
    if not isinstance(intent_str, str):
        return None
    try:
        intent = Intent(intent_str.strip().lower())
    except ValueError:
        # Allow the model to use synonyms for common buckets.
        synonyms = {
            "support": Intent.CUSTOMER_SUPPORT,
            "customer": Intent.CUSTOMER_SUPPORT,
            "bug": Intent.CUSTOMER_SUPPORT,
            "hiring": Intent.RECRUITER,
            "internal": Intent.INTERNAL_REQUEST,
            "request": Intent.INTERNAL_REQUEST,
            "spam": Intent.NOISE,
        }
        intent = synonyms.get(intent_str.strip().lower())
        if intent is None:
            return None

    conf_raw = obj.get("confidence", 0.5)
    try:
        confidence = float(conf_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    # Clamp to [0, 1]. A model returning 1.5 is wrong; do not propagate.
    confidence = max(0.0, min(1.0, confidence))

    rationale = obj.get("rationale", "model_classification")
    if not isinstance(rationale, str):
        rationale = str(rationale)
    rationale = rationale[:200]

    return ClassifyOutput(intent, confidence, rationale)


def validate_tool_args(method: str, params: dict) -> None:
    """Tool-arg validation for the small set of Slack calls we make.

    Raises ValueError with an LLM-friendly message if the args are
    wrong, so a retry prompt can include the message. This is the
    agentvet pattern, narrowed to Slack methods.
    """

    if method == "chat.postMessage":
        ch = params.get("channel")
        text = params.get("text")
        if not isinstance(ch, str) or not ch:
            raise ValueError("chat.postMessage requires non-empty string 'channel'")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("chat.postMessage requires non-empty string 'text'")
        if len(text) > 40_000:
            raise ValueError("chat.postMessage 'text' exceeds 40000 chars (Slack limit)")
        return
    if method == "reactions.add":
        for key in ("channel", "timestamp", "name"):
            v = params.get(key)
            if not isinstance(v, str) or not v:
                raise ValueError(f"reactions.add requires non-empty string {key!r}")
        return
    if method == "conversations.history":
        if not isinstance(params.get("channel"), str) or not params["channel"]:
            raise ValueError("conversations.history requires non-empty string 'channel'")
        limit = params.get("limit", 50)
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("conversations.history 'limit' must be int in [1, 1000]")
        return
    # Unknown methods pass through; ScopeAllowlist will refuse them upstream.
