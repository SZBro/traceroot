"""Tests for agent setup: the packaged skill, `install-skill`, and `check` (no model calls)."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from traceroot import cli

ROOT = Path(__file__).resolve().parent.parent


class SkillTests(unittest.TestCase):
    def test_repo_skill_matches_packaged_skill(self):
        self.assertEqual((ROOT / ".claude/skills/traceroot/SKILL.md").read_text(encoding="utf-8"),
                         cli.SKILL_SOURCE.read_text(encoding="utf-8"))

    def test_skill_has_frontmatter(self):
        text = cli.SKILL_SOURCE.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: traceroot\ndescription: "))

    def test_install_skill_user_and_project(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as proj, \
                mock.patch.object(Path, "home", return_value=Path(home)), \
                mock.patch.object(Path, "cwd", return_value=Path(proj)), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["install-skill"]), 0)
            self.assertTrue((Path(home) / ".claude/skills/traceroot/SKILL.md").exists())
            self.assertEqual(cli.main(["install-skill", "--project"]), 0)
            dest = Path(proj) / ".claude/skills/traceroot/SKILL.md"
            self.assertTrue(dest.exists())
            dest.write_text("my own edits")
            self.assertEqual(cli.main(["install-skill", "--project"]), 1)       # won't clobber edits
            self.assertEqual(dest.read_text(), "my own edits")
            self.assertEqual(cli.main(["install-skill", "--project", "--force"]), 0)
            self.assertNotEqual(dest.read_text(), "my own edits")


class CheckTests(unittest.TestCase):
    def test_check_reports_without_printing_the_key(self):
        out = io.StringIO()
        with mock.patch.dict("os.environ", {"TYPESAFE_API_KEY": "secret-value-123"}), redirect_stdout(out):
            cli.main(["check"])
        text = out.getvalue()
        self.assertIn("TYPESAFE_API_KEY: set", text)
        self.assertNotIn("secret-value-123", text)
        self.assertIn("traceback parser", text)


if __name__ == "__main__":
    unittest.main()
