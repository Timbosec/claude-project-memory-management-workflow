"""Tests for how install.py treats the shared CLAUDE.md on an install run: it is compared rule
by rule, so an edit alone never lists it and only undecided rule changes are raised.

These call main() in-process against a scratch --target. The installed tests are not what is
under test here, so run_tests is replaced by a stub (the slow part of a real run). Run from the
repo root: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_rule_install
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = os.path.join(REPO, "payload", "user-CLAUDE.md")

_spec = importlib.util.spec_from_file_location("install_under_test", os.path.join(REPO,
                                                                                  "install.py"))
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)
install.run_tests = lambda target, test_files: []

NEEDS = "Needs a decision (existing file differs, left as it is): "
SECTION = "Rules in CLAUDE.md that need a decision: "


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


class RuleInstallCase(unittest.TestCase):

    SEARCH = "Before weighing whether to remove an established behaviour"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self._tmp.name, "claude")
        self.shipped = read(SHIPPED)
        self.run_install()  # a fresh install: CLAUDE.md is the bundle's, base copy saved

    def tearDown(self):
        self._tmp.cleanup()

    def t(self, rel):
        return os.path.join(self.target, rel)

    def run_install(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = install.main(["--target", self.target, *args])
            except SystemExit as e:  # argparse usage errors
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def ok(self, *args):
        code, out, err = self.run_install(*args)
        self.assertEqual(code, 0, out + err)
        return out

    def record(self):
        return json.loads(read(self.t("workflow-bundle/install-record.json")))

    def save_record(self, record):
        with open(self.t("workflow-bundle/install-record.json"), "w", encoding="utf-8") as f:
            json.dump(record, f)

    def user_edits(self, text="\n- a rule of my own\n"):
        with open(self.t("CLAUDE.md"), "a", encoding="utf-8") as f:
            f.write(text)
        record = self.record()
        # the record still says what was installed; the file has since been edited
        self.assertNotEqual(record["files"]["CLAUDE.md"]["current_sha256"],
                            sha(read(self.t("CLAUDE.md"))))

    def last_had(self, old_text):
        """Make `old_text` the bundle version the user last had."""
        with open(self.t("workflow-bundle/base/CLAUDE.md.base"), "w", encoding="utf-8") as f:
            f.write(old_text)
        record = self.record()
        record["files"]["CLAUDE.md"]["bundle_sha256"] = sha(old_text)
        self.save_record(record)

    def reworded(self):
        old = self.shipped.replace(self.SEARCH, "Before weighing whether to remove a behaviour", 1)
        self.assertNotEqual(old, self.shipped)
        return old


class UnchangedBundleTest(RuleInstallCase):

    def test_an_edited_file_with_an_unchanged_bundle_is_not_listed(self):
        self.user_edits()
        out = self.ok()
        self.assertIn(NEEDS + "0", out)
        self.assertNotIn("CLAUDE.md", out)
        self.assertNotIn(SECTION, out)
        self.assertIn("skipped by an earlier decision: 1", out)
        self.assertFalse(os.path.exists(self.t("workflow-bundle/changes")))
        entry = self.record()["files"]["CLAUDE.md"]
        self.assertEqual(entry["decision"], "kept-rules")
        self.assertEqual(entry["bundle_sha256"], sha(self.shipped))
        self.assertEqual(entry["current_sha256"], sha(read(self.t("CLAUDE.md"))))

    def test_it_stays_unlisted_on_every_later_run_and_after_more_edits(self):
        self.user_edits()
        self.ok()
        self.assertNotIn("CLAUDE.md", self.ok())
        self.user_edits("\n- and another\n")
        out = self.ok()
        self.assertNotIn("CLAUDE.md", out)
        self.assertEqual(self.record()["files"]["CLAUDE.md"]["decision"], "kept-rules")

    def test_the_file_itself_is_never_changed(self):
        self.user_edits()
        before = read(self.t("CLAUDE.md"))
        self.ok()
        self.assertEqual(read(self.t("CLAUDE.md")), before)

    def test_dry_run_counts_it_as_skipped_and_writes_nothing(self):
        self.user_edits()
        before = snapshot(self.target)
        out = self.ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertNotIn("CLAUDE.md", out)
        self.assertIn("skipped by an earlier decision: 1", out)


class BundleChangeTest(RuleInstallCase):

    def setUp(self):
        super().setUp()
        self.user_edits()
        self.last_had(self.reworded())

    def test_only_the_changed_rule_is_raised(self):
        out = self.ok()
        self.assertIn(NEEDS + "0", out)
        self.assertIn(SECTION + "1\n  search-silence (changed)\n", out)
        rules_file = self.t("workflow-bundle/changes/CLAUDE.md.rules")
        self.assertIn("  old and new wording of each: %s\n" % rules_file, out)
        self.assertFalse(os.path.exists(self.t("workflow-bundle/changes/CLAUDE.md.diff")))
        self.assertNotIn("bundle change", out)
        self.assertIn("a rule of my own", read(self.t("CLAUDE.md")))

    def test_the_rules_file_shows_each_rule_with_old_and_new_wording(self):
        self.ok()
        text = read(self.t("workflow-bundle/changes/CLAUDE.md.rules"))
        self.assertIn("== search-silence (changed) ==", text)
        self.assertIn("Status: changed", text)
        old, new = text.index("Old wording:"), text.index("New wording:")
        self.assertLess(old, new)
        self.assertIn("remove a behaviour, whoever", text[old:new])
        self.assertNotIn("remove an established behaviour", text[old:new])
        self.assertIn("remove an established behaviour", text[new:])
        self.assertNotIn("== lesson-routing", text)

    def test_a_dry_run_lists_the_rule_but_writes_nothing_and_prints_no_path(self):
        before = snapshot(self.target)
        out = self.ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertIn(SECTION + "1\n  search-silence (changed)\n", out)
        self.assertNotIn("old and new wording", out)
        self.assertNotIn(".rules", out)

    def test_the_record_is_not_refreshed_until_the_rules_are_decided(self):
        self.ok()
        entry = self.record()["files"]["CLAUDE.md"]
        self.assertEqual(entry["bundle_sha256"], sha(self.reworded()))
        self.assertEqual(entry["decision"], "installed")
        self.assertIn(SECTION, self.ok())  # and it is raised again next time

    def test_recording_the_rule_then_the_file_stops_it_for_good(self):
        self.ok()
        self.ok("record-rule", "search-silence", "--decision", "taken")
        self.ok("record", "CLAUDE.md", "--decision", "merged")
        out = self.ok()
        self.assertNotIn(SECTION, out)
        self.assertNotIn("CLAUDE.md", out)
        self.assertIn(NEEDS + "0", out)
        self.assertIn("skipped by an earlier decision: 1", out)
        self.assertEqual(self.record()["files"]["CLAUDE.md"]["decision"], "merged")
        self.assertNotIn(SECTION, self.ok())

    def test_a_decision_recorded_on_the_current_wording_silences_the_rule_alone(self):
        self.ok("record-rule", "search-silence", "--decision", "dropped", "--reason", "nope")
        out = self.ok()
        self.assertNotIn(SECTION, out)
        self.assertEqual(self.record()["files"]["CLAUDE.md"]["decision"], "kept-rules")
        self.assertFalse(os.path.exists(self.t("workflow-bundle/changes/CLAUDE.md.rules")))

    def test_a_dry_run_with_nothing_left_to_decide_leaves_the_base_copy_alone(self):
        self.ok("record-rule", "search-silence", "--decision", "taken")
        before = snapshot(self.target)
        out = self.ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertNotIn(SECTION, out)
        self.assertEqual(read(self.t("workflow-bundle/base/CLAUDE.md.base")), self.reworded())

    def test_a_dropped_rule_the_bundle_has_changed_shows_its_reason(self):
        record = self.record()
        record["rules"]["search-silence"] = {
            "decision": "dropped", "reason": "it conflicts with my own search rule",
            "body_sha256": "0" * 64, "date": "2026-10-01", "bundle_commit": None}
        self.save_record(record)
        out = self.ok()
        self.assertIn('  search-silence (dropped earlier: "it conflicts with my own search '
                      'rule"; the bundle has changed it since)\n', out)
        text = read(self.t("workflow-bundle/changes/CLAUDE.md.rules"))
        self.assertIn("Status: dropped-changed", text)
        self.assertIn("it conflicts with my own search rule", text)
        # it stays dropped by default: the file can be recorded without a new decision
        self.ok("record", "CLAUDE.md", "--decision", "merged")

    def test_a_stale_rules_file_from_an_earlier_run_is_removed(self):
        self.ok()
        self.ok("record-rule", "search-silence", "--decision", "taken")
        self.ok()  # nothing raised now: the earlier run's file must not linger
        self.assertFalse(os.path.exists(self.t("workflow-bundle/changes/CLAUDE.md.rules")))

    def test_only_removed_rules_are_still_listed(self):
        extra = self.shipped + "- a rule the bundle later deleted\n  with a second line\n" \
                               "  → `[deleted-rule]`\n"
        self.last_had(extra)
        out = self.ok()
        self.assertIn(SECTION + "1\n  deleted-rule (removed from the bundle)\n", out)
        self.ok("record", "CLAUDE.md", "--decision", "merged")  # removed never blocks


def indented(text):
    """What the rules file does to a bullet: four spaces on every non-blank line."""
    return "\n".join(("    " + line) if line.strip() else "" for line in text.split("\n"))


class RulesFileVerbatimTest(RuleInstallCase):
    """The agent copies a rule from the rules file into the user's CLAUDE.md, so the file
    shows each bullet exactly as the bundle writes it."""

    def rules_file(self):
        return read(self.t("workflow-bundle/changes/CLAUDE.md.rules"))

    def bullet(self, first, last):
        """The bullet in the shipped file from its first words to the end of `last`, sliced
        from the text itself and not through the rule parser."""
        start = self.shipped.index(first)
        return self.shipped[start:self.shipped.index(last, start) + len(last)]

    def test_a_new_rule_is_shown_byte_for_byte_with_its_id_tag(self):
        self.user_edits()
        self.last_had(read(os.path.join(REPO, "tests", "fixtures", "user-CLAUDE-f596cd7.md")))
        self.ok()
        bullet = self.bullet("- **Write shipped text for the people", "`[write-for-readers]`")
        self.assertTrue(bullet.endswith("\n  \u2192 `[write-for-readers]`"))
        self.assertIn("New wording:\n" + indented(bullet) + "\n", self.rules_file())
        # the other rule of that upgrade is shown the same way
        self.assertIn(indented(self.bullet("- **In what you tell the user",
                                           "`[self-carrying-sentences]`")), self.rules_file())

    def test_a_mid_bullet_tag_and_the_paragraph_break_after_it_are_kept(self):
        # second-real-example has two paragraphs, and its tag ends the first one
        self.user_edits()
        old = self.shipped.replace("must be validated where it stands ALONE",
                                   "must be checked where it stands ALONE", 1)
        self.assertNotEqual(old, self.shipped)
        self.last_had(old)
        out = self.ok()
        self.assertIn("  second-real-example (changed)\n", out)
        start = self.shipped.index("- Before a fix or lesson becomes a standing rule")
        bullet = self.shipped[start:self.shipped.index("- A defect's")].rstrip()
        text = self.rules_file()
        self.assertIn("New wording:\n" + indented(bullet) + "\n", text)
        self.assertIn("boundary.** \u2192 `[second-real-example]`\n      **A check added as", text)
        old_part = text[text.index("Old wording:"):text.index("New wording:")]
        self.assertIn("must be checked where it stands ALONE", old_part)
        self.assertIn("boundary.** \u2192 `[second-real-example]`\n      **A check added as",
                      old_part)

    def test_blank_lines_inside_a_rule_stay_empty_not_padded(self):
        self.user_edits()
        self.last_had(self.shipped + "- a rule gone\n\n  with a "
                      "blank line inside\n  \u2192 `[gone-rule]`\n")
        self.ok()
        text = self.rules_file()
        self.assertIn("    - a rule gone\n\n      with a blank line inside\n", text)
        self.assertNotIn("    \n", text)


class NoUsableBaseTest(RuleInstallCase):

    FULL = "  CLAUDE.md (shared) (no earlier bundle version to compare against: full pass)\n"

    def test_a_missing_base_copy_lists_the_file_for_a_full_pass(self):
        self.user_edits()
        os.remove(self.t("workflow-bundle/base/CLAUDE.md.base"))
        before = self.record()["files"]["CLAUDE.md"]
        out = self.ok()
        self.assertIn(NEEDS + "1", out)
        self.assertIn(self.FULL, out)
        self.assertNotIn(SECTION, out)
        self.assertFalse(os.path.exists(self.t("workflow-bundle/changes")))
        self.assertEqual(self.record()["files"]["CLAUDE.md"], before)

    def test_a_base_that_no_longer_matches_the_record_does_the_same(self):
        self.user_edits()
        with open(self.t("workflow-bundle/base/CLAUDE.md.base"), "a", encoding="utf-8") as f:
            f.write("- tampered\n")
        out = self.ok()
        self.assertIn(self.FULL, out)
        self.assertNotIn(SECTION, out)

    def test_a_file_with_no_record_entry_does_the_same(self):
        os.remove(self.t("CLAUDE.md"))
        with open(self.t("CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# My rules\n")
        record = self.record()
        del record["files"]["CLAUDE.md"]
        self.save_record(record)
        self.assertIn(self.FULL, self.ok())

    def test_the_full_pass_ends_by_recording_every_rule_then_the_file(self):
        os.remove(self.t("workflow-bundle/base/CLAUDE.md.base"))
        self.user_edits()
        for rule_id, _body in install.split_rules(self.shipped):
            self.ok("record-rule", rule_id, "--decision", "taken")
        self.ok("record", "CLAUDE.md", "--decision", "merged")
        out = self.ok()
        self.assertNotIn("CLAUDE.md", out)
        self.assertIn(NEEDS + "0", out)


class UneditedAndFormatTest(RuleInstallCase):

    def test_a_file_the_user_never_edited_is_still_updated_to_the_new_bundle(self):
        old = self.reworded()
        with open(self.t("CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write(old)
        self.last_had(old)
        record = self.record()
        record["files"]["CLAUDE.md"]["current_sha256"] = sha(old)
        self.save_record(record)
        out = self.ok()
        self.assertIn("Updated: 1\n  CLAUDE.md\n", out)
        self.assertEqual(read(self.t("CLAUDE.md")), self.shipped)
        self.assertNotIn(SECTION, out)

    def test_an_old_format_3_record_is_used_and_saved_as_format_4(self):
        self.user_edits()
        record = self.record()
        record["format"] = 3
        del record["rules"]
        self.save_record(record)
        out = self.ok()
        self.assertNotIn("CLAUDE.md", out)
        saved = self.record()
        self.assertEqual((saved["format"], saved["rules"]), (4, {}))


if __name__ == "__main__":
    unittest.main()
