"""Unit tests for render_html (no model calls)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from traceroot import claude_client, config, render_html

RESULT = {
    "timestamp": "t", "error_type": "TypeError", "error_line": "TypeError: <b>bad</b>", "source": "full",
    "order_by": "jev", "gate": {"category": "other_or_complex", "probability": 0.99},
    "frames": [{"file": "a.py", "line": 20, "func": "checkout"}, {"file": "a.py", "line": 11, "func": "price"}],
    "slices_text": ">> 11 | x = 1", "meta": {"claude_tokens": 10, "jev_tokens": 5},
    "causes": [
        {"id": "c1", "title": "<script>alert(1)</script>", "explanation": "e", "category": "none_value",
         "file": "a.py", "line": 5, "fix_hint": "f", "claude_rank": 1, "claude_confidence": 0.8, "jev_p": 0.9},
        {"id": "c2", "title": "second", "explanation": "e2", "category": "none_value",
         "file": None, "line": None, "fix_hint": "f2", "claude_rank": 2, "claude_confidence": 0.1, "jev_p": 0.1},
    ],
}


class MermaidTests(unittest.TestCase):
    def test_clean_accepts_flowchart_and_adds_class_defs(self):
        m = render_html.clean_mermaid('```mermaid\nflowchart TD\n  A["x"] --> B["y"]:::crash\n```')
        self.assertTrue(m.startswith("flowchart TD"))
        self.assertIn("classDef cause", m)

    def test_clean_rejects_non_flowchart_and_scripts(self):
        for bad in [None, 42, "sequenceDiagram\n A->>B: hi", 'flowchart TD\n A["<script>x</script>"]',
                    'flowchart TD\n A --> B\n click A "javascript:alert(1)"']:
            with self.subTest(bad=bad):
                self.assertIsNone(render_html.clean_mermaid(bad))

    def test_fallback_has_call_path_and_cause(self):
        m = render_html.fallback_mermaid(RESULT, RESULT["causes"][0])
        self.assertIn("F0 --> F1", m)
        self.assertIn(":::crash", m)
        self.assertIn(":::cause", m)
        self.assertNotIn("<script>", m)                 # label characters are neutralized


class PageTests(unittest.TestCase):
    def test_model_text_is_escaped(self):
        page = render_html.build_page(RESULT, 0, "flowchart TD\n A --> B", "claude")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<b>bad</b>", page)
        self.assertEqual(page.count("<script"), 2)       # only the Mermaid tag and its init line
        self.assertIn("cdn.jsdelivr.net/npm/mermaid@", page)

    def test_render_caches_diagram_and_falls_back(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(config, "STATE_DIR", Path(d)):
            (Path(d) / "last.json").write_text(json.dumps(RESULT | {"cursor": 0}))
            good = {"mermaid": 'flowchart TD\n A["c"] --> B["d"]:::crash'}
            with mock.patch.object(claude_client, "ask_claude", return_value=good) as ask:
                render_html.render(1, open_browser=False)
                render_html.render(1, open_browser=False)       # second time: cached
            self.assertEqual(ask.call_count, 1)
            with mock.patch.object(claude_client, "ask_claude",
                                   side_effect=claude_client.ClaudeError("down")), \
                    mock.patch("sys.stderr"):
                out = render_html.render(2, open_browser=False)
            self.assertIn("code-built call path", out.read_text(encoding="utf-8"))
            self.assertIsNone(render_html.render(9, open_browser=False))


if __name__ == "__main__":
    unittest.main()
