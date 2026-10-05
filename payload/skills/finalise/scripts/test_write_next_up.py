#!/usr/bin/env python3
"""Tests for write_next_up.py. Fixture text and temp files only."""
import os
import subprocess
import sys
import tempfile
import unittest

import write_next_up as wnu

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "write_next_up.py")
TEMPLATE = os.path.join(HERE, "..", "..", "bootstrap-project", "templates",
                        "backlog.md")

HEAD = "# Backlog\n\nIntro line.\n\n---\n\n"
OLD_BLOCK = (
    "## Next up — recommended 2026-01-01\n"
    "\n"
    "Re-check this against `## Open` before acting on it.\n"
    "\n"
    "1. **#1**: OLDUNIQUE sentence about a task that is now closed.\n"
    "\n"
    "---\n"
    "\n"
)
TAIL = "## Open\n\n### #2 — Something open\n\nBody.\n\n## Closed\n\n- done\n"
OLD = HEAD + OLD_BLOCK + TAIL

NEW_BLOCK = (
    "## Next up — recommended 2026-02-02\n"
    "\n"
    "1. **#2**: NEWUNIQUE do the open thing.\n"
    "\n"
    "---\n"
)


def run(path, stdin):
    p = subprocess.run([sys.executable, SCRIPT, "--backlog", path],
                       input=stdin.encode("utf-8"), capture_output=True)
    return p.returncode, p.stdout.decode(), p.stderr.decode()


class WriteNextUpTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "backlog.md")

    def put(self, text):
        with open(self.path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def read(self):
        with open(self.path, encoding="utf-8", newline="") as fh:
            return fh.read()

    def assertRefused(self, old, new, fragment):
        self.put(old)
        before = self.read()
        code, out, err = run(self.path, new)
        self.assertEqual(code, 1, err)
        self.assertTrue(err.startswith("refused: "), err)
        self.assertIn(fragment, err)
        self.assertEqual(out, "")
        self.assertEqual(self.read(), before)

    def test_happy_path(self):
        self.put(OLD)
        code, out, err = run(self.path, NEW_BLOCK)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertEqual(self.read(), HEAD + NEW_BLOCK + "\n" + TAIL)

    def test_block_with_open_heading_text_mid_sentence_fully_replaced(self):
        self.assertIn("`## Open`", OLD_BLOCK)
        self.put(OLD)
        code, _, err = run(self.path, NEW_BLOCK)
        self.assertEqual(code, 0, err)
        result = self.read()
        self.assertNotIn("OLDUNIQUE", result)
        self.assertNotIn("Re-check this against", result)
        self.assertEqual(result, HEAD + NEW_BLOCK + "\n" + TAIL)

    def test_trailing_whitespace_before_next_heading_preserved(self):
        old = HEAD + OLD_BLOCK.rstrip("\n") + "\n\n\n\n" + TAIL
        self.put(old)
        code, _, err = run(self.path, NEW_BLOCK + "\n\n\n\n\n\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read(),
                         HEAD + NEW_BLOCK.rstrip("\n") + "\n\n\n\n" + TAIL)

    def test_refuses_zero_or_two_headings_in_current_file(self):
        self.assertRefused(HEAD + TAIL, NEW_BLOCK, "exactly one Next up")
        self.assertRefused(OLD + "\n" + OLD_BLOCK, NEW_BLOCK,
                           "exactly one Next up")

    def test_refuses_block_not_starting_with_heading(self):
        self.assertRefused(OLD, "\n" + NEW_BLOCK, "at its first character")
        self.assertRefused(OLD, "Intro\n" + NEW_BLOCK, "at its first character")

    def test_refuses_empty_stdin(self):
        self.assertRefused(OLD, "", "empty")

    def test_refuses_other_level_two_heading(self):
        new = NEW_BLOCK.replace("1. **#2**", "## Open\n\n1. **#2**")
        self.assertRefused(OLD, new, "another line starting with")

    def test_refuses_missing_separator(self):
        new = NEW_BLOCK.replace("---\n", "")
        self.assertRefused(OLD, new, "same last non-blank line")

    def test_result_with_two_headings_is_refused(self):
        # Unreachable through the CLI while checks 2 and 3 hold, so drive the
        # post-condition by making the counter report two headings once the
        # result is counted (the first call counts the current file).
        real = wnu._heading_count
        calls = []

        def counter(text):
            calls.append(1)
            return 1 if len(calls) == 1 else 2

        wnu._heading_count = counter
        try:
            with self.assertRaises(wnu.Refused) as cm:
                wnu.build_result(OLD, NEW_BLOCK)
        finally:
            wnu._heading_count = real
        self.assertIn("result would contain 2 Next up headings",
                      str(cm.exception))

    def test_outside_text_check_refuses_when_rest_would_change(self):
        # Drive the post-condition directly: a splitter that disagrees about
        # where the block ends must be refused rather than written.
        real = wnu.split_next_up
        calls = []

        def skewed(text):
            block, rest = real(text)
            calls.append(1)
            if len(calls) > 1:
                rest = rest + "extra"
            return block, rest

        wnu.split_next_up = skewed
        try:
            with self.assertRaises(wnu.Refused) as cm:
                wnu.build_result(OLD, NEW_BLOCK)
        finally:
            wnu.split_next_up = real
        self.assertIn("outside the Next up block", str(cm.exception))

    def test_bootstrap_template_block_can_be_replaced(self):
        with open(TEMPLATE, encoding="utf-8") as fh:
            text = fh.read().replace("<DATE>", "2026-03-03")
        self.put(text)
        new = ("## Next up — recommended 2026-03-04\n\n1. **#1**: first.\n\n"
               "---\n")
        code, _, err = run(self.path, new)
        self.assertEqual(code, 0, err)
        result = self.read()
        self.assertNotIn("Nothing opened yet", result)
        self.assertIn("1. **#1**: first.", result)
        self.assertIn("---\n\n## Open\n", result)


if __name__ == "__main__":
    unittest.main()
