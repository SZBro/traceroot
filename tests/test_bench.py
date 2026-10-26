"""Unit tests for the benchmark's case building and scoring (no model calls)."""
import sys
import unittest
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "bench"
sys.path.insert(0, str(BENCH))

import run_bench  # noqa: E402
from cases import PROJECTS  # noqa: E402
from mutate import Case, build  # noqa: E402


def case(**kw):
    base = dict(id="x", project="p", kind="k", distance="d", root=Path("."), cmd="", truth_file="a.py",
                truth_line=10, crash_ok=False, crash_file="b.py", crash_line=40)
    return Case(**(base | kw))


class ScoringTests(unittest.TestCase):
    def test_hit_needs_right_file_and_line_within_one(self):
        c = case()
        self.assertTrue(run_bench.is_hit({"file": "a.py", "line": 11}, c))
        self.assertTrue(run_bench.is_hit({"file": "a.py", "line": 9}, c))
        self.assertFalse(run_bench.is_hit({"file": "a.py", "line": 12}, c))
        self.assertFalse(run_bench.is_hit({"file": "other.py", "line": 10}, c))
        self.assertFalse(run_bench.is_hit({"file": None, "line": None}, c))

    def test_crash_line_counts_only_when_allowed(self):
        self.assertFalse(run_bench.is_hit({"file": "b.py", "line": 40}, case()))
        self.assertTrue(run_bench.is_hit({"file": "b.py", "line": 40}, case(crash_ok=True)))

    def test_first_hit_rank(self):
        causes = [{"file": "z.py", "line": 1}, {"file": "a.py", "line": 10}]
        self.assertEqual(run_bench.first_hit_rank(causes, case()), 2)
        self.assertIsNone(run_bench.first_hit_rank(causes[:1], case()))

    def test_claude_order_ablation(self):
        row = {"truth": "a.py:10", "crash": "b.py:40", "crash_ok": False, "traceroot": {"causes": [
            {"file": "z.py", "line": 1, "claude_rank": 2},          # Jev put this first
            {"file": "a.py", "line": 10, "claude_rank": 1}]}}
        self.assertEqual(run_bench.claude_order_rank(row), 1)


class CaseBuildTests(unittest.TestCase):
    def test_every_mutation_snippet_is_unique_and_ids_are_unique(self):
        ids = []
        for project, spec in PROJECTS.items():
            for m in spec["mutations"]:
                ids.append(m["id"])
                text = (BENCH / "projects" / project / m["file"]).read_text(encoding="utf-8")
                with self.subTest(case=m["id"]):
                    self.assertEqual(text.count(m["find"]), 1)
                    self.assertNotEqual(m["find"], m["replace"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_clean_projects_carry_no_hints(self):
        for p in (BENCH / "projects").rglob("*.py"):
            with self.subTest(file=p.name):
                self.assertNotIn("bug", p.read_text(encoding="utf-8").lower())

    def test_build_applies_mutation_and_records_truth(self):
        spec = PROJECTS["shop"]
        mut = spec["mutations"][0]
        c = build("shop", spec, mut)
        line = (c.root / c.truth_file).read_text(encoding="utf-8").splitlines()[c.truth_line - 1]
        self.assertIn(mut["replace"], line)
        self.assertIn("Traceback", c.stderr)


if __name__ == "__main__":
    unittest.main()
