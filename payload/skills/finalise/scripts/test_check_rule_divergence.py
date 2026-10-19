#!/usr/bin/env python3
"""Tests for check_rule_divergence.py.

The script is a command-line report, so each test writes a base file and a user file into a
tmpdir and runs it by subprocess, then reads what it prints.
"""
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_rule_divergence.py")

RULE_A = ("- **Run it and read the output before accepting it.** A clean diff and a green suite\n"
          "  are evidence the code is consistent.\n"
          "  → `[run-it]`\n")
RULE_B = ("- **Default to a high-level answer**; keep caveats short.\n"
          "  → `[high-level]`\n")


def _run(base_text, mine_text):
    with tempfile.TemporaryDirectory() as d:
        base, mine = os.path.join(d, "base.md"), os.path.join(d, "mine.md")
        if base_text is not None:
            with open(base, "w", encoding="utf-8") as f:
                f.write(base_text)
        if mine_text is not None:
            with open(mine, "w", encoding="utf-8") as f:
                f.write(mine_text)
        r = subprocess.run([sys.executable, SCRIPT, "--claude-md", mine, "--base", base],
                           capture_output=True, text=True)
    return r.stdout, r.returncode


class TestRuleDivergence(unittest.TestCase):
    def test_identical_rules_are_counted_not_listed(self):
        out, code = _run("# T\n\n" + RULE_A + RULE_B, "# T\n\n" + RULE_A + RULE_B)
        self.assertEqual(code, 0)
        self.assertIn("2 bundle rules identical", out)
        self.assertNotIn("EDITED", out)

    def test_rewrapping_a_rule_is_not_an_edit(self):
        rewrapped = ("- **Run it and read the output before accepting it.** A clean diff and a\n"
                     "  green suite are evidence the code is consistent.\n"
                     "  → `[run-it]`\n")
        out, _ = _run(RULE_A, rewrapped)
        self.assertIn("1 bundle rules identical", out)
        self.assertNotIn("EDITED", out)

    def test_an_added_sentence_is_shown_as_added(self):
        edited = RULE_A.replace("  → `[run-it]`", "  Also run it on a Windows box.\n  → `[run-it]`")
        out, _ = _run(RULE_A, edited)
        self.assertIn("EDITED   [run-it]", out)
        self.assertIn("{+Also run it on a Windows box.+}", out)
        self.assertNotIn("[-", out)

    def test_a_deleted_phrase_is_shown_as_removed(self):
        edited = RULE_A.replace(" and a green suite", "")
        out, _ = _run(RULE_A, edited)
        self.assertIn("EDITED   [run-it]", out)
        self.assertIn("[-and a green suite-]", out)

    def test_only_the_edited_rule_is_listed(self):
        edited = RULE_A.replace("consistent", "consistent and right")
        out, _ = _run(RULE_A + RULE_B, edited + RULE_B)
        self.assertIn("EDITED   [run-it]", out)
        self.assertNotIn("[high-level]", out)
        self.assertIn("1 bundle rules identical", out)

    def test_a_rule_absent_from_the_users_file_is_missing(self):
        out, _ = _run(RULE_A + RULE_B, RULE_A)
        self.assertIn("MISSING  [high-level]", out)

    def test_an_untagged_identical_copy_is_found_by_wording(self):
        untagged = RULE_A.replace("  → `[run-it]`\n", "")
        out, _ = _run(RULE_A, untagged)
        self.assertIn("NO TAG   [run-it]: identical", out)
        self.assertNotIn("MISSING", out)
        self.assertIn("not compared): 0", out)

    def test_an_untagged_edited_copy_is_found_and_diffed(self):
        untagged = RULE_A.replace("  → `[run-it]`\n", "").replace("consistent", "consistent mostly")
        out, _ = _run(RULE_A, untagged)
        self.assertIn("NO TAG   [run-it]: no tag in your file; edited", out)
        self.assertIn("{+consistent mostly.+}", out)

    def test_users_own_rules_are_counted_and_never_reported_as_edits(self):
        own_tagged = "- Check the weather.\n  → `[weather]`\n"
        own_plain = "- Always say hello first.\n"
        out, _ = _run(RULE_A, RULE_A + own_tagged + own_plain)
        self.assertNotIn("EDITED", out)
        self.assertNotIn("MISSING", out)
        self.assertIn("not compared): 2", out)

    def test_an_unrelated_untagged_rule_is_not_taken_for_a_missing_bundle_rule(self):
        out, _ = _run(RULE_A, "- Always say hello first.\n")
        self.assertIn("MISSING  [run-it]", out)
        self.assertIn("not compared): 1", out)

    def test_missing_base_file_skips_and_exits_zero(self):
        out, code = _run(None, RULE_A)
        self.assertEqual(code, 0)
        self.assertIn("skipping the rule-divergence check", out)

    def test_exit_is_zero_even_when_rules_differ(self):
        _, code = _run(RULE_A, RULE_B)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
