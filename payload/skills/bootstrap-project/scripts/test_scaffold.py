#!/usr/bin/env python3
"""Tests for scaffold.py. Each runs the script as a subprocess against a temporary project root,
so nothing reads or writes a real project."""
import datetime
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scaffold  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "scaffold.py")
TEMPLATES = os.path.join(HERE, os.pardir, "templates")
WRITTEN = ["backlog.md", "decisions.md", "lesson-candidates.md", "CLAUDE.md"]


def _run(root, *args):
    return subprocess.run([sys.executable, SCRIPT, root, *args], capture_output=True, text=True)


def _touch(root, rel):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestScaffold(unittest.TestCase):
    def test_empty_project_gets_all_four_files_filled_in(self):
        with tempfile.TemporaryDirectory() as root:
            r = _run(root, "widget-shop", "--date", "2026-01-15")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(os.listdir(root)), sorted(WRITTEN))
            for name in WRITTEN:
                self.assertIn(f"created  {name}", r.stdout)
                text = _read(os.path.join(root, name))
                self.assertNotIn("<PROJECT NAME>", text, name)
                self.assertNotIn("<DATE>", text, name)
                self.assertIn("widget-shop", text.splitlines()[0], name)

    def test_next_up_heading_carries_the_date_in_the_form_finalise_parses(self):
        with tempfile.TemporaryDirectory() as root:
            _run(root, "widget-shop", "--date", "2026-01-15")
            self.assertIn("\n## Next up — recommended 2026-01-15 (first revision)\n",
                          _read(os.path.join(root, "backlog.md")))

    def test_date_defaults_to_today(self):
        with tempfile.TemporaryDirectory() as root:
            _run(root, "widget-shop")
            self.assertIn(f"recommended {datetime.date.today().isoformat()} ",
                          _read(os.path.join(root, "backlog.md")))

    def test_claude_md_is_written_from_the_differently_named_template(self):
        with tempfile.TemporaryDirectory() as root:
            _run(root, "widget-shop", "--date", "2026-01-15")
            expected = _read(os.path.join(TEMPLATES, "project-CLAUDE.md")).replace(
                "<PROJECT NAME>", "widget-shop")
            self.assertEqual(_read(os.path.join(root, "CLAUDE.md")), expected)

    def test_existing_files_are_left_byte_for_byte_and_reported(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("backlog.md", "CLAUDE.md"):
                with open(os.path.join(root, name), "w", encoding="utf-8") as f:
                    f.write(f"the project's own {name}\n")
            r = _run(root, "widget-shop", "--date", "2026-01-15")
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("backlog.md", "CLAUDE.md"):
                self.assertEqual(_read(os.path.join(root, name)), f"the project's own {name}\n")
                self.assertIn(f"exists   {name}", r.stdout)
            for name in ("decisions.md", "lesson-candidates.md"):
                self.assertIn(f"created  {name}", r.stdout)

    def test_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "backlog.md"), "w", encoding="utf-8") as f:
                f.write("the project's own backlog\n")
            r = _run(root, "widget-shop", "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.listdir(root), ["backlog.md"])
            self.assertIn("exists   backlog.md", r.stdout)
            self.assertIn("would create  decisions.md", r.stdout)

    def test_bad_date_and_empty_name_write_nothing(self):
        for args in (["widget-shop", "--date", "15/01/2026"], ["  ", "--date", "2026-01-15"]):
            with tempfile.TemporaryDirectory() as root:
                r = _run(root, *args)
                self.assertNotEqual(r.returncode, 0, args)
                self.assertEqual(os.listdir(root), [], args)

    def test_bundle_clone_is_refused_and_left_untouched(self):
        for extra in ([], ["--dry-run"]):
            with tempfile.TemporaryDirectory() as root:
                _touch(root, "payload/skills/bootstrap-project/SKILL.md")
                r = _run(root, "widget-shop", *extra)
                self.assertEqual(r.returncode, 1, extra)
                self.assertIn("clone of the workflow bundle", r.stderr, extra)
                self.assertEqual(r.stdout, "", extra)
                self.assertEqual(os.listdir(root), ["payload"], extra)

    def test_project_with_install_py_and_manifest_json_is_scaffolded(self):
        # Both names are common in real projects (manifest.json especially), so neither, nor
        # the pair, may mark a folder as the bundle's clone.
        with tempfile.TemporaryDirectory() as root:
            for name in ("install.py", "manifest.json"):
                _touch(root, name)
            r = _run(root, "widget-shop", "--date", "2026-01-15")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(os.listdir(root)),
                             sorted(WRITTEN + ["install.py", "manifest.json"]))

    def test_project_with_its_own_copy_of_the_skill_is_scaffolded(self):
        # A project-level install of the skill lives under .claude/, not payload/.
        with tempfile.TemporaryDirectory() as root:
            _touch(root, ".claude/skills/bootstrap-project/SKILL.md")
            r = _run(root, "widget-shop", "--date", "2026-01-15")
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_marker_is_where_the_bundle_keeps_this_skill(self):
        # Ties the marker to the real layout: the path after payload/ must be this skill's own
        # SKILL.md, found the same way in a clone (payload/skills/...) or an install
        # (~/.claude/skills/...). If the bundle's layout changes, this goes red.
        prefix = "payload" + os.sep
        self.assertTrue(scaffold.BUNDLE_CLONE_MARKER.startswith(prefix))
        tail = scaffold.BUNDLE_CLONE_MARKER[len(prefix):]
        skills_parent = os.path.join(HERE, os.pardir, os.pardir, os.pardir)
        self.assertTrue(os.path.isfile(os.path.join(skills_parent, tail)), tail)


if __name__ == "__main__":
    unittest.main()
