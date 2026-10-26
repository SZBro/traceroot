"""Unit tests for stats rows and the summary (no model calls)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from traceroot import config, stats


def result(source, causes, gate=None, raw=400, claude=3500, jev=900):
    return {"timestamp": "t", "error_type": "TypeError", "source": source, "gate": gate, "causes": causes,
            "meta": {"raw_tokens": raw, "claude_tokens": claude, "jev_tokens": jev,
                     "latency_ms": 100, "backend": "cli" if claude else None}}


def c(cid, line, rank=None, jev=None):
    return {"id": cid, "file": "a.py", "line": line, "claude_rank": rank, "jev_p": jev}


GATE = {"category": "undefined_name_or_typo", "probability": 0.99}


class StatsTests(unittest.TestCase):
    def test_row_agree_and_disagree(self):
        same = stats.row_for(result("full", [c("c1", 5, 1, 0.9), c("c2", 9, 2, 0.1)]), 40)
        self.assertEqual((same["claude_top"], same["jev_top"], same["agree"]), ("a.py:5", "a.py:5", "yes"))
        diff = stats.row_for(result("full", [c("c1", 5, 1, 0.2), c("c2", 9, 2, 0.8)]), 40)
        self.assertEqual((diff["claude_top"], diff["jev_top"], diff["agree"]), ("a.py:5", "a.py:9", "no"))

    def test_gate_row_has_no_agreement(self):
        row = stats.row_for(result("jev_gate", [c("q1", 5, None, 0.99)], gate=GATE, claude=0), 30)
        self.assertEqual((row["path"], row["gate_p"], row["agree"], row["claude_tokens"]),
                         ("jev_gate", 0.99, "", 0))

    def test_append_and_summarize(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "STATE_DIR", Path(d)):
            stats.append(result("jev_gate", [c("q1", 5, None, 0.99)], gate=GATE, claude=0), "x" * 120)
            stats.append(result("full", [c("c1", 5, 1, 0.9)]), "x" * 160)
            stats.append(result("full", [c("c1", 5, 1, 0.2), c("c2", 9, 2, 0.8)]), "x" * 160)
            rows = stats.load_rows()
            self.assertEqual(len(rows), 3)
            s = stats.summarize(rows)
        self.assertEqual((s["runs"], s["gate_runs"], s["compared"], s["agreed"]), (3, 1, 2, 1))
        self.assertAlmostEqual(s["avg_returned"], (30 + 40 + 40) / 3)
        self.assertAlmostEqual(s["avg_reduction_pct"], 100 * (1 - (30 + 40 + 40) / 3 / 400))
        self.assertEqual((s["claude_tokens"], s["jev_tokens"]), (7000, 2700))
        out = stats.format_summary(s)
        self.assertIn("handled by Jev gate alone: 1/3 (33%)", out)
        self.assertIn("Claude/Jev agree on #1:    1/2 (50%)", out)

    def test_empty(self):
        self.assertIn("no runs logged yet", stats.format_summary(stats.summarize([])))


if __name__ == "__main__":
    unittest.main()
