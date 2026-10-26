"""Unit tests for trace_parser. Run: python -m unittest discover tests"""
import sys
import tempfile
import unittest
from pathlib import Path

from traceroot import trace_parser as tp

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

CHAINED = """Traceback (most recent call last):
  File "a.py", line 3, in <module>
    int("x")
ValueError: invalid literal for int() with base 10: 'x'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "b.py", line 9, in handler
    raise RuntimeError("boom")
RuntimeError: boom
"""

SYNTAX = """  File "c.py", line 2
    def f(:
          ^
SyntaxError: invalid syntax
"""

CUSTOM = """Traceback (most recent call last):
  File "d.py", line 5, in pay
    raise CartEmpty("no items")
CartEmpty: no items
"""


class ParseTests(unittest.TestCase):
    def test_none_cart_fixture(self):
        _, err = tp.run_command(f'"{sys.executable}" tests/fixtures/medium_none_cart.py', root=ROOT)
        p = tp.parse(err, root=ROOT)
        self.assertEqual(p.exc_type, "TypeError")
        self.assertEqual(p.message, "'NoneType' object is not iterable")
        self.assertEqual(len(p.frames), 4)
        self.assertEqual([f.func for f in p.project_frames], ["checkout", "subtotal", "price_items"])
        self.assertEqual(p.project_frames[-1].code, "return [prices[i] for i in items]")
        # all three frames are in one short file -> one merged slice, every frame line marked
        self.assertEqual(len(p.slices), 1)
        s = p.slices[0]
        self.assertEqual(s.file, "tests/fixtures/medium_none_cart.py")
        self.assertEqual(s.marks, [11, 15, 20])
        self.assertEqual(s.error_line, 11)
        self.assertIn(">> 11 | ", s.text)
        self.assertIn("items = None", s.text)          # the real cause is inside the window

    def test_every_fixture_crashes_and_parses(self):
        for script in sorted(FIXTURES.glob("[emh]*_*.py")):
            with self.subTest(script=script.name):
                code, err = tp.run_command(f'"{sys.executable}" "{script}"', root=ROOT)
                self.assertNotEqual(code, 0)
                p = tp.parse(err, root=ROOT)
                self.assertTrue(p.exc_type)
                self.assertTrue(1 <= len(p.project_frames) <= 3)
                self.assertTrue(1 <= len(p.slices) <= len(p.project_frames))
                self.assertNotIn("bug", err.lower() + "".join(s.text.lower() for s in p.slices))

    def test_chained_uses_last_traceback(self):
        p = tp.parse_traceback(CHAINED)
        self.assertEqual((p.exc_type, p.message), ("RuntimeError", "boom"))
        self.assertEqual([f.file for f in p.frames], ["b.py"])

    def test_syntax_error_without_func(self):
        p = tp.parse_traceback(SYNTAX)
        self.assertEqual(p.exc_type, "SyntaxError")
        self.assertEqual((p.frames[0].file, p.frames[0].line, p.frames[0].func), ("c.py", 2, None))

    def test_custom_exception_name(self):
        p = tp.parse_traceback(CUSTOM)
        self.assertEqual((p.exc_type, p.message), ("CartEmpty", "no items"))

    def test_non_python_error(self):
        p = tp.parse_traceback("npm ERR! missing script: build")
        self.assertFalse(p.is_python)
        self.assertEqual(p.error_line, "npm ERR! missing script: build")


class SliceMergeTests(unittest.TestCase):
    def test_far_apart_lines_stay_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            f = root / "long.py"
            f.write_text("\n".join(f"x{i} = {i}" for i in range(1, 201)) + "\n")
            slices = tp.read_slices(f, [10, 25, 150], radius=5, root=root)
            self.assertEqual([(s.start, s.end) for s in slices], [(5, 15), (20, 30), (145, 155)])
            slices = tp.read_slices(f, [10, 18], radius=5, root=root)   # 5-15 and 13-23 overlap
            self.assertEqual([(s.start, s.end, s.marks) for s in slices], [(5, 23, [10, 18])])


class RelatedDefinitionTests(unittest.TestCase):
    """One-hop definitions: imported project functions, module constants, module-alias attributes."""

    FILES = {
        "app/__init__.py": "",
        "app/loader.py": "def load(path):\n    rows = []\n    rows.append(None)\n    return rows\n",
        "app/util.py": "def helper(x):\n    return x\n",
        "app/core.py": (
            "from . import util\n"
            "from .loader import load\n"
            "import json\n"
            "\n"
            "LIMITS = {'a': 1}\n"
            "class Box:\n    size: int = 0\n\n    def grow(self):\n        return self.size + 1\n"
            + "\n" * 40 +
            "def run():\n"
            "    rows = load('x')\n"
            "    util.helper(rows)\n"
            "    b = Box()\n"
            "    return LIMITS['b'] + len(json.dumps(rows))\n"
        ),
        "main.py": "from app.core import run\n\nrun()\n",
    }

    def test_follows_imports_constants_and_aliases(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            for rel, text in self.FILES.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            crash = self.FILES["app/core.py"].splitlines().index("    return LIMITS['b'] + len(json.dumps(rows))") + 1
            trace = (f'Traceback (most recent call last):\n  File "{root / "main.py"}", line 3, in <module>\n'
                     f'  File "{root / "app" / "core.py"}", line {crash}, in run\nKeyError: \'b\'\n')
            p = tp.parse(trace, root)
            labels = {s.label.split(",")[0]: (s.file, s.start, s.end) for s in p.slices if s.label}
        self.assertEqual(labels["definition of load"], ("app/loader.py", 1, 4))      # other file
        self.assertEqual(labels["definition of helper"], ("app/util.py", 1, 2))      # module alias attr
        self.assertEqual(labels["definition of LIMITS"], ("app/core.py", 5, 5))      # far constant
        self.assertEqual(labels["definition of Box"], ("app/core.py", 6, 8))         # fields, not methods
        self.assertNotIn("definition of json", labels)                               # stdlib skipped
        self.assertNotIn("definition of run", labels)                                # not itself


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        for rel in ["app.py", ".env", "secret.pem", "id.key", ".git/config",
                    ".venv/Lib/site-packages/lib.py"]:
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x = 1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_allows_project_file(self):
        self.assertIsNotNone(tp.resolve_in_project("app.py", self.root))

    def test_blocks_secrets_git_and_packages(self):
        for rel in [".env", "secret.pem", "id.key", ".git/config", ".venv/Lib/site-packages/lib.py"]:
            with self.subTest(rel=rel):
                self.assertIsNone(tp.resolve_in_project(rel, self.root))

    def test_blocks_outside_root(self):
        self.assertIsNone(tp.resolve_in_project(str(ROOT / "README.md"), self.root))
        self.assertIsNone(tp.resolve_in_project("../outside.py", self.root))

    def test_blocks_stdlib(self):
        import json
        self.assertIsNone(tp.resolve_in_project(json.__file__, Path(sys.base_prefix)))


if __name__ == "__main__":
    unittest.main()
