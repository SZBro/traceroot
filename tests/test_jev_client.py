"""Unit tests for jev_client and the gate decision, with fake Jev answers (no API calls)."""
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from traceroot import config, jev_client, pipeline

ROOT = Path(__file__).resolve().parent.parent


def fake_answer(choice, probs):
    return {"choice": choice, "confidence": probs[choice], "probabilities": probs,
            "input_tokens": 900, "output_tokens": 1}


class JevClientTests(unittest.TestCase):
    def setUp(self):
        jev_client._client, jev_client._disabled_reason = None, None

    def test_no_key_returns_none_with_one_notice(self):
        err = io.StringIO()
        with mock.patch.dict("os.environ", {"TYPESAFE_API_KEY": ""}), redirect_stderr(err):
            self.assertIsNone(jev_client.gate("tb", "code"))
            self.assertIsNone(jev_client.score("tb", "code", [{"id": "c1", "title": "t"}]))
        self.assertEqual(err.getvalue().count("no TYPESAFE_API_KEY"), 1)

    def test_gate_shape(self):
        probs = {c: 0.0 for c in config.CATEGORIES} | {"none_value": 0.9, "other_or_complex": 0.1}
        with mock.patch.object(jev_client, "_ask_choice", return_value=fake_answer("none_value", probs)):
            g = jev_client.gate("tb", "code")
        self.assertEqual((g["category"], g["probability"]), ("none_value", 0.9))

    def test_score_keeps_candidate_order(self):
        cands = [{"id": "c1", "title": "a"}, {"id": "c2", "title": "b"}]
        with mock.patch.object(jev_client, "_ask_choice",
                               return_value=fake_answer("c2", {"c2": 0.7, "c1": 0.3})):
            self.assertEqual(jev_client.score("tb", "code", cands), [0.3, 0.7])

    def test_score_rejects_mismatched_options(self):
        cands = [{"id": "c1", "title": "a"}, {"id": "c2", "title": "b"}]
        with mock.patch.object(jev_client, "_ask_choice", return_value=fake_answer("c1", {"c1": 1.0})), \
                redirect_stderr(io.StringIO()):
            self.assertIsNone(jev_client.score("tb", "code", cands))


TRACE = (ROOT / "tests/fixtures/tracebacks/easy_typo_name.txt").read_text()


class GateDecisionTests(unittest.TestCase):
    """pipeline.analyze: confident gate -> no Claude call; unsure or other_or_complex -> Claude."""

    def run_with_gate(self, category, p):
        gate = {"category": category, "probability": p, "confidence": p, "probabilities": {category: p}}
        claude = mock.Mock(return_value={"candidates": [{"id": "c1", "title": "from claude", "claude_rank": 1}]})
        with mock.patch.object(jev_client, "gate", return_value=gate), \
                mock.patch.object(jev_client, "score", return_value=None), \
                mock.patch.object(pipeline.claude_client, "ask_claude", claude), \
                mock.patch.object(pipeline.store, "save"), \
                mock.patch.object(config, "PROJECT_ROOT", ROOT):
            return pipeline.analyze(TRACE), claude.called

    def test_confident_gate_skips_claude(self):
        result, called = self.run_with_gate("undefined_name_or_typo", 0.95)
        self.assertEqual((result["source"], called), ("jev_gate", False))
        self.assertEqual(result["causes"][0]["line"], 5)

    def test_low_probability_goes_to_claude(self):
        result, called = self.run_with_gate("undefined_name_or_typo", 0.6)
        self.assertEqual((result["source"], called), ("full", True))

    def test_other_or_complex_always_goes_to_claude(self):
        result, called = self.run_with_gate("other_or_complex", 0.99)
        self.assertEqual((result["source"], called), ("full", True))


if __name__ == "__main__":
    unittest.main()
