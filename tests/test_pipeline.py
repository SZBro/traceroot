"""Unit tests for pipeline validation, ranking and output (no model calls)."""
import unittest
from pathlib import Path

from traceroot import pipeline

ROOT = Path(__file__).resolve().parent.parent


class ValidateTests(unittest.TestCase):
    def test_cleans_bad_fields(self):
        raw = [
            {"id": "c1", "title": "real cause", "category": "none_value",
             "file": "tests/fixtures/medium_none_cart.py", "line": 5,
             "claude_rank": 1, "claude_confidence": 0.7},
            {"id": "c1", "title": "invented file", "category": "made_up",
             "file": "nope/ghost.py", "line": 3, "claude_rank": "x", "claude_confidence": 1.7},
            {"id": "c3", "title": "secret", "file": ".env", "line": 1},
            {"title": ""},                        # dropped: no title
            "not a dict",                         # dropped
        ]
        out = pipeline.validate_candidates(raw, ROOT)
        self.assertEqual(len(out), 3)
        a, b, c = out
        self.assertEqual((a["file"], a["line"], a["claude_confidence"]),
                         ("tests/fixtures/medium_none_cart.py", 5, 0.7))
        self.assertNotEqual(b["id"], "c1")                    # duplicate id renamed
        self.assertEqual(b["category"], "other_or_complex")   # unknown category
        self.assertEqual((b["file"], b["line"]), (None, None))  # invented file nulled
        self.assertIsNone(b["claude_confidence"])             # out-of-range probability nulled
        self.assertEqual(b["claude_rank"], 2)                 # bad rank -> position
        self.assertIsNone(c["file"])                          # .env is never referenced

    def test_caps_at_six(self):
        raw = [{"title": f"t{i}"} for i in range(10)]
        self.assertEqual(len(pipeline.validate_candidates(raw, ROOT)), 6)


def cause(cid, rank, conf, jev=None):
    return {"id": cid, "title": cid, "category": "wrong_type", "file": None, "line": None,
            "fix_hint": "f", "claude_rank": rank, "claude_confidence": conf, "jev_p": jev}


class RankTests(unittest.TestCase):
    def test_claude_order_without_jev(self):
        causes, by = pipeline.rank([cause("b", 2, 0.3), cause("a", 1, 0.6)])
        self.assertEqual(([c["id"] for c in causes], by), (["a", "b"], "claude"))
        self.assertEqual([c["final_rank"] for c in causes], [1, 2])

    def test_jev_order_wins_when_complete(self):
        causes, by = pipeline.rank([cause("a", 1, 0.6, jev=0.2), cause("b", 2, 0.3, jev=0.7)])
        self.assertEqual(([c["id"] for c in causes], by), (["b", "a"], "jev"))

    def test_partial_jev_falls_back_to_claude(self):
        causes, by = pipeline.rank([cause("b", 2, 0.3, jev=0.9), cause("a", 1, 0.6)])
        self.assertEqual(([c["id"] for c in causes], by), (["a", "b"], "claude"))


class FormatTests(unittest.TestCase):
    def test_compact_format(self):
        c = cause("x", 1, 0.6) | {"title": "items set to None", "file": "orders.py", "line": 40,
                                 "category": "none_value", "jev_p": 0.82}
        self.assertEqual(pipeline.format_cause(c, 0, 4),
                         "[1/4] none_value (p=0.82) orders.py:40\n"
                         "cause: items set to None\nfix: f\nmore: `traceroot next`")
        self.assertTrue(pipeline.format_cause(c, 3, 4).endswith("more: none (last candidate)"))


if __name__ == "__main__":
    unittest.main()
