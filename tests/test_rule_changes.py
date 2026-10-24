"""Tests for the reasons install.py prints beside a changed rule or file, from rule-changes.json.

These call main() in-process against a scratch --target, with the installed tests stubbed out
and the path of rule-changes.json pointed at a small fixture written by each test (the real
file is not under test here). Run from the repo root:
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_rule_changes
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = os.path.join(REPO, "payload", "user-CLAUDE.md")

_spec = importlib.util.spec_from_file_location("install_under_test", os.path.join(REPO,
                                                                                  "install.py"))
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)
install.run_tests = lambda target, test_files: []

NEEDS = "Needs a decision (existing file differs, left as it is): "
WHY = "Why the bundle changed it:"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ChangesCase(unittest.TestCase):

    SEARCH = "Before weighing whether to remove an established behaviour"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self._tmp.name, "claude")
        self.changes_path = os.path.join(self._tmp.name, "rule-changes.json")
        patch = mock.patch.object(install, "RULE_CHANGES_PATH", self.changes_path)
        patch.start()
        self.addCleanup(patch.stop)
        self.shipped = read(SHIPPED)
        self.run_install()  # a fresh install: every file is the bundle's, base copies saved

    def tearDown(self):
        self._tmp.cleanup()

    def t(self, rel):
        return os.path.join(self.target, rel)

    def run_install(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install.main(["--target", self.target, *args])
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

    def write_changes(self, data):
        with open(self.changes_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def user_edits(self, rel="CLAUDE.md", text="\n- a rule of my own\n"):
        with open(self.t(rel), "a", encoding="utf-8") as f:
            f.write(text)

    def last_had(self, old_text):
        """Make `old_text` the bundle version of CLAUDE.md the user last had."""
        with open(self.t("workflow-bundle/base/CLAUDE.md.base"), "w", encoding="utf-8") as f:
            f.write(old_text)
        record = self.record()
        record["files"]["CLAUDE.md"]["bundle_sha256"] = sha(old_text)
        self.save_record(record)

    def rules_file(self):
        return read(self.t("workflow-bundle/changes/CLAUDE.md.rules"))

    def section(self, rule_id):
        """The part of the rules file about one rule."""
        text = self.rules_file()
        start = text.index("== %s " % rule_id)
        nxt = text.find("\n== ", start + 1)
        return text[start:] if nxt == -1 else text[start:nxt]


class RuleNotesTest(ChangesCase):
    """search-silence is published in three wordings: v0, v1 and the current one."""

    def setUp(self):
        super().setUp()
        self.versions = [self.shipped.replace(self.SEARCH, self.SEARCH + " less" + str(n), 1)
                         for n in (0, 1)]
        self.bodies = [dict(install.split_rules(v))["search-silence"] for v in self.versions]
        self.current = dict(install.split_rules(self.shipped))["search-silence"]
        self.write_changes({"rules": {"search-silence": [
            {"sha256": sha(self.bodies[0]), "note": ""},
            {"sha256": sha(self.bodies[1]), "note": "Cut the second sentence."},
            {"sha256": sha(self.current), "note": "Reworded to name the sample."}]}})
        self.user_edits()

    def test_a_base_at_the_first_entry_shows_every_later_note_in_order(self):
        self.last_had(self.versions[0])
        self.ok()
        self.assertIn("Status: changed\n" + WHY + "\n  Cut the second sentence.\n"
                      "  Reworded to name the sample.\nOld wording:\n",
                      self.section("search-silence"))

    def test_a_base_at_the_middle_entry_shows_only_the_later_notes(self):
        self.last_had(self.versions[1])
        self.ok()
        text = self.section("search-silence")
        self.assertIn("Status: changed\n" + WHY + "\n  Reworded to name the sample.\nOld wording:\n",
                      text)
        self.assertNotIn("Cut the second sentence.", text)

    def test_a_base_not_in_the_list_shows_every_non_empty_note(self):
        self.last_had(self.shipped.replace(self.SEARCH, self.SEARCH + " by some other wording", 1))
        self.ok()
        self.assertIn("Status: changed\n" + WHY + "\n  Cut the second sentence.\n"
                      "  Reworded to name the sample.\nOld wording:\n",
                      self.section("search-silence"))

    def test_a_new_rule_shows_every_note(self):
        rules = install.rule_blocks(self.shipped)
        ids = [rid for rid, _body in install.split_rules(self.shipped)]
        raw = rules[ids.index("search-silence")][1]
        self.assertIn(raw, self.shipped)
        self.last_had(self.shipped.replace(raw, "", 1))
        self.ok()
        text = self.section("search-silence")
        self.assertIn("Status: new\n" + WHY + "\n  Cut the second sentence.\n"
                      "  Reworded to name the sample.\nOld wording:\n", text)

    def test_a_rule_with_no_notes_gets_no_heading(self):
        self.write_changes({"rules": {}, "files": {}})
        self.last_had(self.versions[0])
        self.ok()
        self.assertNotIn(WHY, self.rules_file())

    def test_the_summary_line_for_the_rule_is_unchanged(self):
        self.last_had(self.versions[0])
        out = self.ok()
        self.assertIn("Rules in CLAUDE.md that need a decision: 1\n  search-silence (changed)\n",
                      out)
        self.assertNotIn("why:", out)


class RemovedRuleTest(ChangesCase):

    def setUp(self):
        super().setUp()
        self.user_edits()

    def test_a_removed_rule_with_an_id_shows_its_removal_note(self):
        extra = "- a rule the bundle later deleted\n  with a second line\n  → `[gone-rule]`\n"
        self.last_had(self.shipped + extra)
        body = dict(install.split_rules(self.shipped + extra))["gone-rule"]
        # the user had its second wording, so the note on the way to that one is not shown
        self.write_changes({"rules": {"gone-rule": [
            {"sha256": sha("its first wording"), "note": ""},
            {"sha256": sha(body), "note": "Reworded before it went."},
            {"removed": True, "note": "Superseded by the search rule."}]}})
        self.ok()
        text = self.section("gone-rule")
        self.assertIn("== gone-rule (removed from the bundle) ==\nStatus: removed\n" + WHY +
                      "\n  Superseded by the search rule.\nOld wording:\n", text)
        self.assertNotIn("Reworded before it went.", text)

    def idless_removed(self):
        """A rule in a real copy from before rules had IDs that the bundle has since dropped."""
        old = read(os.path.join(REPO, "tests", "fixtures", "user-CLAUDE-f596cd7.md"))
        gone = [i for i in install.rules_to_raise(old, self.shipped, {})
                if i["status"] == install.RULE_REMOVED and i["id"] is None]
        self.assertTrue(gone, "the fixture no longer has a removed rule without an ID")
        return old, gone[0]

    def test_a_removed_rule_with_no_id_is_found_by_its_fingerprint(self):
        old, item = self.idless_removed()
        self.last_had(old)
        # the list's key is unrelated to anything in the base: only the fingerprint finds it
        self.write_changes({"rules": {
            "some-other-rule": [{"sha256": "0" * 64, "note": "Not this one."}],
            "retired-rule": [{"sha256": sha("its first wording"), "note": ""},
                             {"sha256": sha(item["old"]), "note": "Reworded before it went."},
                             {"removed": True, "note": "Cut because it was never used."}]}})
        self.ok()
        text = self.section("(no ID) " + item["first_line"])
        self.assertIn("Status: removed\n" + WHY + "\n  Cut because it was never used.\nOld "
                      "wording:\n", text)
        self.assertNotIn("Not this one.", self.rules_file())
        self.assertNotIn("Reworded before it went.", text)

    def test_a_removed_rule_with_no_id_that_no_list_holds_gets_no_notes(self):
        old, item = self.idless_removed()
        self.last_had(old)
        self.write_changes({"rules": {
            "some-other-rule": [{"sha256": "0" * 64, "note": "Not this one."}]}})
        self.ok()
        self.assertIn("== (no ID) " + item["first_line"], self.rules_file())
        self.assertNotIn(WHY, self.rules_file())


class FileNotesTest(ChangesCase):

    OLD = "an earlier version of the file\n"

    def setUp(self):
        super().setUp()
        self.rel = "writing-executor-briefs.md"
        self.current = sha(read(os.path.join(REPO, "payload", self.rel)))
        self.write_changes({"files": {self.rel: [
            {"sha256": sha(self.OLD), "note": ""},
            {"sha256": sha(self.OLD + "v1"), "note": "Added the routing rule."},
            {"sha256": self.current, "note": "Trimmed the examples."}]}})

    def had(self, version_sha, base_text=None):
        """The user edited the file after installing the bundle version `version_sha`."""
        self.user_edits(self.rel)
        record = self.record()
        record["files"][self.rel]["bundle_sha256"] = version_sha
        self.save_record(record)
        if base_text is not None:
            with open(self.t("workflow-bundle/base/%s.base" % self.rel), "w",
                      encoding="utf-8") as f:
                f.write(base_text)

    def test_a_listed_file_prints_every_note_since_its_recorded_version(self):
        self.had(sha(self.OLD))
        out = self.ok()
        self.assertIn(NEEDS + "1\n  writing-executor-briefs.md (owned)\n"
                      "    why: Added the routing rule.\n    why: Trimmed the examples.\n", out)

    def test_a_file_recorded_at_the_middle_version_prints_only_the_later_note(self):
        self.had(sha(self.OLD + "v1"))
        out = self.ok()
        self.assertIn("  writing-executor-briefs.md (owned)\n    why: Trimmed the examples.\n", out)
        self.assertNotIn("Added the routing rule.", out)

    def test_notes_follow_the_file_line_when_there_is_a_diff_and_the_diff_stays_pure(self):
        self.had(sha(self.OLD), base_text=self.OLD)
        out = self.ok()
        diff = self.t("workflow-bundle/changes/writing-executor-briefs.md.diff")
        # The file here is the bundle's own text plus the user's line, so the listing also
        # carries the note that the copy already holds the bundle's changes.
        self.assertIn("  writing-executor-briefs.md (owned) (your copy already holds every bundle "
                      "change since your recorded version; it differs only by your own "
                      "additions), bundle change: %s\n    why: Added the routing rule.\n" % diff,
                      out)
        self.assertNotIn("routing rule", read(diff))
        self.assertNotIn("why:", read(diff))

    def test_a_file_updated_silently_prints_nothing(self):
        rel = "writing-standing-docs.md"
        with open(self.t(rel), "w", encoding="utf-8") as f:
            f.write(self.OLD)
        record = self.record()
        record["files"][rel]["bundle_sha256"] = record["files"][rel]["current_sha256"] = \
            sha(self.OLD)
        self.save_record(record)
        self.write_changes({"files": {rel: [
            {"sha256": sha(self.OLD), "note": ""},
            {"sha256": sha(read(os.path.join(REPO, "payload", rel))),
             "note": "Should never be shown."}]}})
        out = self.ok()
        self.assertIn("Updated: 1\n  %s\n" % rel, out)
        self.assertNotIn("why:", out)
        self.assertNotIn("Should never be shown.", out)

    def test_a_listed_file_with_no_record_of_a_version_prints_every_note(self):
        self.user_edits(self.rel)
        record = self.record()
        del record["files"][self.rel]
        self.save_record(record)
        out = self.ok()
        self.assertIn("  writing-executor-briefs.md (owned)\n    why: Added the routing rule.\n"
                      "    why: Trimmed the examples.\n", out)

    def test_a_listed_file_with_no_entry_prints_no_why(self):
        self.write_changes({"files": {}})
        self.had(sha(self.OLD))
        out = self.ok()
        self.assertIn(NEEDS + "1\n  writing-executor-briefs.md (owned)\n", out)
        self.assertNotIn("why:", out)


class UnusableFileTest(ChangesCase):

    def check_warns(self):
        self.user_edits()
        self.last_had(self.shipped.replace(self.SEARCH, self.SEARCH + " less", 1))
        code, out, err = self.run_install()
        self.assertEqual(code, 0, out + err)
        warnings = [line for line in out.splitlines() if line.startswith("Warning")]
        self.assertEqual(len(warnings), 1, out)
        self.assertIn("rule-changes.json", warnings[0])
        self.assertIn("without", warnings[0])
        # the install carried on: the rule is still raised, just with no reasons
        self.assertIn("search-silence (changed)", out)
        self.assertNotIn(WHY, self.rules_file())

    def test_a_missing_file_warns_and_the_install_completes(self):
        self.assertFalse(os.path.exists(self.changes_path))
        self.check_warns()

    def test_a_file_that_is_not_json_warns_and_the_install_completes(self):
        with open(self.changes_path, "w", encoding="utf-8") as f:
            f.write("{ not json")
        self.check_warns()

    def test_json_of_the_wrong_shape_warns_and_the_install_completes(self):
        for bad in ([], {"rules": []}, {"rules": {"a": "text"}},
                    {"files": {"a": [{"note": 3}]}}):
            self.write_changes(bad)
            self.check_warns()

    def test_a_usable_file_does_not_warn(self):
        self.write_changes({"rules": {}, "files": {}})
        self.assertNotIn("Warning", self.ok())

    def test_a_dry_run_warns_too(self):
        self.assertIn("Warning", self.ok("--dry-run"))


class NotesSinceTest(unittest.TestCase):

    ENTRIES = [{"sha256": "a", "note": ""}, {"sha256": "b", "note": "one"},
               {"sha256": "c", "note": "two"}, {"removed": True, "note": "three"}]

    def test_an_unknown_fingerprint_gets_every_non_empty_note(self):
        self.assertEqual(install.notes_since(self.ENTRIES, None), ["one", "two", "three"])

    def test_a_fingerprint_not_in_the_list_gets_every_non_empty_note(self):
        self.assertEqual(install.notes_since(self.ENTRIES, "z"), ["one", "two", "three"])

    def test_the_notes_after_the_matching_entry_only(self):
        self.assertEqual(install.notes_since(self.ENTRIES, "b"), ["two", "three"])
        self.assertEqual(install.notes_since(self.ENTRIES, "c"), ["three"])

    def test_nothing_after_the_last_entry(self):
        self.assertEqual(install.notes_since(self.ENTRIES[:3], "c"), [])

    def test_an_entry_with_no_fingerprint_is_never_matched(self):
        entries = [{"sha256": "a", "note": "one"}, {"removed": True, "note": "two"}]
        self.assertEqual(install.notes_since(entries, None), ["one", "two"])


REAL = os.path.join(REPO, "rule-changes.json")
PLACEHOLDER = "<say in one line why this differs from the version before it>"


def paste_entry(key, entry):
    """What to add to the list for `key` (a rule ID or a file path), ready to paste."""
    return "  %s: append %s" % (json.dumps(key), json.dumps(entry))


def current_entry(fingerprint):
    return {"sha256": fingerprint, "note": PLACEHOLDER}


class RealFileTest(unittest.TestCase):
    """rule-changes.json as shipped: it has to stay in step with the rules and files it covers.

    A failure prints the entry to add. Whoever changes a rule or a file adds an entry to its list
    with the new fingerprint and a note saying why. (Editing the last entry in place is fine for
    a change that has not been pushed yet.)
    """

    @classmethod
    def setUpClass(cls):
        cls.changes, problem = install.load_rule_changes(REAL)
        if problem:
            raise AssertionError("rule-changes.json can't be used: %s" % problem)
        cls.rules = dict(install.split_rules(read(SHIPPED)))
        manifest = json.loads(read(os.path.join(REPO, "manifest.json")))
        # the shared CLAUDE.md is covered by its rules
        cls.files = {e["target"]: install.sha256_of(os.path.join(REPO, e["source"]))
                     for e in manifest["files"] if e["kind"] != "shared"}

    def lists(self):
        for section in ("rules", "files"):
            for key, entries in self.changes[section].items():
                yield section, key, entries

    def check(self, problems):
        if problems:
            self.fail("rule-changes.json is out of step with the bundle:\n" +
                      "\n".join(problems))

    def test_every_current_rule_ends_with_its_current_wording(self):
        problems = []
        for rule_id, body in self.rules.items():
            fingerprint = install.body_sha256(body)
            entries = self.changes["rules"].get(rule_id)
            if not entries:
                problems.append("rule [%s] has no list; add under \"rules\":\n%s"
                                % (rule_id, paste_entry(rule_id, current_entry(fingerprint))))
            elif entries[-1].get("sha256") != fingerprint:
                problems.append("rule [%s] was reworded; its last entry is not the current "
                                "wording:\n%s" % (rule_id, paste_entry(
                                    rule_id, current_entry(fingerprint))))
        self.check(problems)

    def test_every_current_file_ends_with_its_current_hash(self):
        problems = []
        for target, fingerprint in self.files.items():
            entries = self.changes["files"].get(target)
            if not entries:
                problems.append("file %s has no list; add under \"files\":\n%s"
                                % (target, paste_entry(target, current_entry(fingerprint))))
            elif entries[-1].get("sha256") != fingerprint:
                problems.append("file %s changed; its last entry is not the current "
                                "file:\n%s" % (target, paste_entry(
                                    target, current_entry(fingerprint))))
        self.check(problems)

    def test_a_rule_no_longer_in_the_bundle_ends_with_a_removed_entry(self):
        removed = {"removed": True, "note": PLACEHOLDER}
        problems = ["rule [%s] is no longer in the bundle:\n%s" % (k, paste_entry(k, removed))
                    for k, entries in self.changes["rules"].items()
                    if k not in self.rules and not (entries and entries[-1].get("removed"))]
        self.check(problems)

    def test_a_file_no_longer_in_the_bundle_ends_with_a_removed_entry(self):
        removed = {"removed": True, "note": PLACEHOLDER}
        problems = ["file %s is no longer in the bundle:\n%s" % (k, paste_entry(k, removed))
                    for k, entries in self.changes["files"].items()
                    if k not in self.files and not (entries and entries[-1].get("removed"))]
        self.check(problems)

    def test_a_removed_entry_is_last_and_belongs_to_nothing_still_shipped(self):
        problems = []
        for section, key, entries in self.lists():
            shipped = self.rules if section == "rules" else self.files
            if any(e.get("removed") for e in entries[:-1]):
                problems.append("%s: a removed entry that is not the last" % key)
            if entries and entries[-1].get("removed") and key in shipped:
                problems.append("%s: ends as removed but the bundle still ships it" % key)
        self.check(problems)

    def test_only_the_first_entry_of_a_list_may_have_an_empty_note(self):
        problems = ["%s: entry %d has no note; replace %s" % (key, i + 1, json.dumps(e))
                    for _section, key, entries in self.lists()
                    for i, e in enumerate(entries) if i > 0 and not e.get("note", "").strip()]
        self.check(problems)

    def test_every_entry_has_a_fingerprint_or_is_a_removal(self):
        problems = ["%s: the list has no entries" % key
                    for _section, key, entries in self.lists() if not entries]
        problems += ["%s: entry %d has neither sha256 nor removed" % (key, i + 1)
                     for _section, key, entries in self.lists()
                     for i, e in enumerate(entries) if not e.get("sha256") and not e.get("removed")]
        self.check(problems)

    def test_notes_are_for_strangers_so_no_task_numbers_or_commit_hashes(self):
        problems = []
        for _section, key, entries in self.lists():
            for e in entries:
                note = e.get("note", "")
                if re.search(r"#\d", note) or re.search(r"\b[0-9a-f]{7,40}\b", note, re.I):
                    problems.append("%s: a note carries a task number or a hash: %s" % (key, note))
        self.check(problems)


if __name__ == "__main__":
    unittest.main()
