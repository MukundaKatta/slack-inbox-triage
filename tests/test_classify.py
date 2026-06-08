"""Tests for the classify module: heuristic + LLM repair."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from slack_inbox_triage.classify import (
    Intent,
    cast_json,
    classify_message,
    validate_tool_args,
)


class HeuristicTests(unittest.TestCase):
    def test_heuristic_recognizes_recruiter(self):
        text = (
            "Hi! I'm a recruiter from Acme. We have a remote principal eng "
            "opportunity. Open to a call?"
        )
        out = classify_message(text)
        self.assertEqual(out.intent, Intent.RECRUITER)
        self.assertGreaterEqual(out.confidence, 0.6)

    def test_heuristic_recognizes_support(self):
        text = (
            "the export-to-csv button is throwing a 500 error. "
            "steps to repro: open Reports."
        )
        out = classify_message(text)
        self.assertEqual(out.intent, Intent.CUSTOMER_SUPPORT)

    def test_heuristic_recognizes_noise(self):
        out = classify_message("brb coffee")
        self.assertEqual(out.intent, Intent.NOISE)

    def test_heuristic_unknown_when_empty_signal(self):
        out = classify_message("hello there friend")
        self.assertEqual(out.intent, Intent.UNKNOWN)
        self.assertEqual(out.confidence, 0.2)

    def test_heuristic_confidence_saturates(self):
        """Confidence never exceeds the 0.95 ceiling, however many hits."""

        text = (
            "recruiter recruiting opportunity role staff engineer "
            "compensation saw your profile open to a call"
        )
        out = classify_message(text)
        self.assertEqual(out.intent, Intent.RECRUITER)
        self.assertLessEqual(out.confidence, 0.95)


class LLMRepairTests(unittest.TestCase):
    def test_llm_path_clean_json(self):
        def fake_llm(_):
            return (
                '{"intent": "recruiter", "confidence": 0.91, '
                '"rationale": "model said so"}'
            )

        out = classify_message("anything", llm=fake_llm)
        self.assertEqual(out.intent, Intent.RECRUITER)
        self.assertTrue(0.9 <= out.confidence <= 0.95)

    def test_llm_path_with_fenced_json_and_trailing_comma(self):
        """cast_json should repair fenced + trailing-comma output."""

        def fake_llm(_):
            return (
                "Sure! Here is the answer:\n"
                "```json\n"
                '{"intent": "customer_support", "confidence": 0.8, '
                '"rationale": "user reported 500",}\n'
                "```"
            )

        out = classify_message("err 500", llm=fake_llm)
        self.assertEqual(out.intent, Intent.CUSTOMER_SUPPORT)
        self.assertAlmostEqual(out.confidence, 0.8)

    def test_llm_path_invalid_falls_back_to_heuristic(self):
        def fake_llm(_):
            return "I don't know how to do JSON, sorry."

        out = classify_message("brb coffee", llm=fake_llm)
        # heuristic should still tag it noise
        self.assertEqual(out.intent, Intent.NOISE)
        self.assertTrue(
            "llm_output_unparseable" in out.rationale
            or "heuristic" in out.rationale
        )

    def test_llm_path_raising_exception_falls_back(self):
        def angry_llm(_):
            raise RuntimeError("boom")

        out = classify_message("brb coffee", llm=angry_llm)
        self.assertEqual(out.intent, Intent.NOISE)
        self.assertIn("llm_error", out.rationale)

    def test_llm_confidence_clamps_out_of_range(self):
        def overconfident(_):
            return (
                '{"intent": "recruiter", "confidence": 5.0, '
                '"rationale": "very sure"}'
            )

        out = classify_message("recruiter pitch", llm=overconfident)
        self.assertEqual(out.confidence, 1.0)

    def test_llm_confidence_clamps_negative(self):
        def negative(_):
            return '{"intent": "noise", "confidence": -2.0, "rationale": "x"}'

        out = classify_message("brb", llm=negative)
        self.assertEqual(out.confidence, 0.0)

    def test_llm_non_numeric_confidence_defaults(self):
        def weird(_):
            return '{"intent": "noise", "confidence": "very", "rationale": "x"}'

        out = classify_message("brb", llm=weird)
        self.assertEqual(out.confidence, 0.5)

    def test_llm_synonym_map(self):
        def synonym(_):
            return (
                '{"intent": "bug", "confidence": 0.7, '
                '"rationale": "support synonym"}'
            )

        out = classify_message("err", llm=synonym)
        self.assertEqual(out.intent, Intent.CUSTOMER_SUPPORT)

    def test_llm_unknown_intent_falls_back(self):
        """An intent string the repair layer cannot map falls back."""

        def unknown_intent(_):
            return '{"intent": "banana", "confidence": 0.9, "rationale": "x"}'

        out = classify_message("brb coffee", llm=unknown_intent)
        # Heuristic should classify it instead.
        self.assertEqual(out.intent, Intent.NOISE)

    def test_classify_output_to_dict_rounds_confidence(self):
        def fake_llm(_):
            return (
                '{"intent": "recruiter", "confidence": 0.123456, '
                '"rationale": "r"}'
            )

        out = classify_message("x", llm=fake_llm)
        self.assertEqual(out.to_dict()["confidence"], 0.123)
        self.assertEqual(out.to_dict()["intent"], "recruiter")


class CastJsonTests(unittest.TestCase):
    def test_cast_json_handles_no_json(self):
        self.assertIsNone(cast_json("nothing useful here"))

    def test_cast_json_empty_string(self):
        self.assertIsNone(cast_json(""))

    def test_cast_json_extracts_object_from_prose(self):
        parsed = cast_json('prose before {"a": 1} prose after')
        self.assertEqual(parsed, {"a": 1})

    def test_cast_json_rejects_top_level_array(self):
        # The repair layer only accepts JSON objects, not arrays.
        self.assertIsNone(cast_json("[1, 2, 3]"))


class ValidateToolArgsTests(unittest.TestCase):
    def test_validate_tool_args_post_message(self):
        validate_tool_args("chat.postMessage", {"channel": "C1", "text": "hi"})
        with self.assertRaises(ValueError):
            validate_tool_args("chat.postMessage", {"channel": "", "text": "hi"})
        with self.assertRaises(ValueError):
            validate_tool_args("chat.postMessage", {"channel": "C1", "text": ""})

    def test_validate_tool_args_post_message_text_too_long(self):
        with self.assertRaises(ValueError):
            validate_tool_args(
                "chat.postMessage",
                {"channel": "C1", "text": "x" * 40_001},
            )

    def test_validate_tool_args_history_limit(self):
        validate_tool_args(
            "conversations.history", {"channel": "C1", "limit": 50}
        )
        with self.assertRaises(ValueError):
            validate_tool_args(
                "conversations.history", {"channel": "C1", "limit": 10_000}
            )

    def test_validate_tool_args_reactions_add(self):
        validate_tool_args(
            "reactions.add",
            {"channel": "C1", "timestamp": "1.0", "name": "eyes"},
        )
        with self.assertRaises(ValueError):
            validate_tool_args(
                "reactions.add", {"channel": "C1", "timestamp": "1.0"}
            )

    def test_validate_tool_args_unknown_method_passes_through(self):
        # Unknown methods are deferred to the scope guard upstream; this
        # function must not raise on them.
        validate_tool_args("admin.users.delete", {"user": "U1"})


if __name__ == "__main__":
    unittest.main()
