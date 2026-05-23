"""Tests for the classify module: heuristic + LLM repair."""

from __future__ import annotations

import pytest

from slack_inbox_triage.classify import (
    Intent,
    cast_json,
    classify_message,
    validate_tool_args,
)


def test_heuristic_recognizes_recruiter():
    text = "Hi! I'm a recruiter from Acme. We have a remote principal eng opportunity. Open to a call?"
    out = classify_message(text)
    assert out.intent == Intent.RECRUITER
    assert out.confidence >= 0.6


def test_heuristic_recognizes_support():
    text = "the export-to-csv button is throwing a 500 error. steps to repro: open Reports."
    out = classify_message(text)
    assert out.intent == Intent.CUSTOMER_SUPPORT


def test_heuristic_recognizes_noise():
    out = classify_message("brb coffee")
    assert out.intent == Intent.NOISE


def test_heuristic_unknown_when_empty_signal():
    out = classify_message("hello there friend")
    assert out.intent == Intent.UNKNOWN
    assert out.confidence == 0.2


def test_llm_path_clean_json():
    def fake_llm(_):
        return '{"intent": "recruiter", "confidence": 0.91, "rationale": "model said so"}'

    out = classify_message("anything", llm=fake_llm)
    assert out.intent == Intent.RECRUITER
    assert 0.9 <= out.confidence <= 0.95


def test_llm_path_with_fenced_json_and_trailing_comma():
    """cast_json should repair fenced + trailing-comma output."""

    def fake_llm(_):
        return (
            "Sure! Here is the answer:\n"
            "```json\n"
            '{"intent": "customer_support", "confidence": 0.8, "rationale": "user reported 500",}\n'
            "```"
        )

    out = classify_message("err 500", llm=fake_llm)
    assert out.intent == Intent.CUSTOMER_SUPPORT
    assert out.confidence == pytest.approx(0.8)


def test_llm_path_invalid_falls_back_to_heuristic():
    def fake_llm(_):
        return "I don't know how to do JSON, sorry."

    out = classify_message("brb coffee", llm=fake_llm)
    # heuristic should still tag it noise
    assert out.intent == Intent.NOISE
    assert "llm_output_unparseable" in out.rationale or "heuristic" in out.rationale


def test_llm_path_raising_exception_falls_back():
    def angry_llm(_):
        raise RuntimeError("boom")

    out = classify_message("brb coffee", llm=angry_llm)
    assert out.intent == Intent.NOISE
    assert "llm_error" in out.rationale


def test_llm_confidence_clamps_out_of_range():
    def overconfident(_):
        return '{"intent": "recruiter", "confidence": 5.0, "rationale": "very sure"}'

    out = classify_message("recruiter pitch", llm=overconfident)
    assert out.confidence == 1.0


def test_llm_synonym_map():
    def synonym(_):
        return '{"intent": "bug", "confidence": 0.7, "rationale": "support synonym"}'

    out = classify_message("err", llm=synonym)
    assert out.intent == Intent.CUSTOMER_SUPPORT


def test_cast_json_handles_no_json():
    assert cast_json("nothing useful here") is None


def test_validate_tool_args_post_message():
    validate_tool_args("chat.postMessage", {"channel": "C1", "text": "hi"})
    with pytest.raises(ValueError):
        validate_tool_args("chat.postMessage", {"channel": "", "text": "hi"})
    with pytest.raises(ValueError):
        validate_tool_args("chat.postMessage", {"channel": "C1", "text": ""})


def test_validate_tool_args_history_limit():
    validate_tool_args("conversations.history", {"channel": "C1", "limit": 50})
    with pytest.raises(ValueError):
        validate_tool_args("conversations.history", {"channel": "C1", "limit": 10_000})
