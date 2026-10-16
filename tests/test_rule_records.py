"""Tests for the per-rule decisions in install.py: the record, record-rule, rules, and the
refusal of `record CLAUDE.md` while a rule is undecided.

Each test builds a small target by hand (a CLAUDE.md, a base copy and an install record) and
runs install.py's subcommands against it with --target, which is quick because the subcommands
do not run the installed tests. Run from the repo root:
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_rule_records
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(REPO, "install.py")
SHIPPED = os.path.join(REPO, "payload", "user-CLAUDE.md")

_spec = importlib.util.spec_from_file_location("install_under_test", INSTALL)
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def fixture(name):
    return read(os.path.join(REPO, "tests", "fixtures", name))


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RuleRecordCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self._tmp.name, "claude")
        os.makedirs(self.target)
        self.shipped = read(SHIPPED)

    def tearDown(self):
        self._tmp.cleanup()

    def t(self, rel):
        return os.path.join(self.target, rel)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(self.t(rel)), exist_ok=True)
        with open(self.t(rel), "w", encoding="utf-8") as f:
            f.write(text)

    def start(self, base_text, mine="# My rules\n\n- be brief\n", fmt=install.RECORD_FORMAT,
              base_hash=None, rules=None):
        """A target whose last-installed bundle version is `base_text` and whose CLAUDE.md the
        user has edited to `mine`."""
        self.write("CLAUDE.md", mine)
        self.write("workflow-bundle/base/CLAUDE.md.base", base_text)
        record = {"format": fmt, "components": {}, "settings_added": [],
                  "project_overrides": {}, "retired_kept": {},
                  "files": {"CLAUDE.md": {
                      "kind": "shared", "bundle_sha256": base_hash or sha(base_text),
                      "current_sha256": sha(mine), "decision": "kept", "bundle_commit": None,
                      "date": "2026-10-01", "base": "workflow-bundle/base/CLAUDE.md.base"}}}
        if rules is not None:
            record["rules"] = rules
        self.write("workflow-bundle/install-record.json", json.dumps(record))

    def record(self):
        return json.loads(read(self.t("workflow-bundle/install-record.json")))

    def run_install(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, INSTALL, "--target", self.target, *args],
                              capture_output=True, text=True, env=env)

    def ok(self, *args):
        r = self.run_install(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def refused(self, *args):
        r = self.run_install(*args)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        return r

    def rule_body(self, rule_id):
        return dict((i, b) for i, b in install.split_rules(self.shipped))[rule_id]


class RecordFormatTest(RuleRecordCase):

    def test_a_format_3_record_loads_and_is_saved_as_format_4(self):
        self.start(self.shipped, fmt=3)
        self.assertNotIn("rules", self.record())
        r = self.ok("rules")
        self.assertIn("Recorded rule decisions: 0", r.stdout)
        self.assertEqual(self.record()["format"], 3)  # listing writes nothing
        self.ok("record-rule", "search-silence", "--decision", "taken")
        saved = self.record()
        self.assertEqual(saved["format"], 4)
        self.assertEqual(list(saved["rules"]), ["search-silence"])
        self.assertIn("CLAUDE.md", saved["files"])

    def test_a_record_with_a_rules_list_is_refused(self):
        self.start(self.shipped, rules=["not", "an", "object"])
        r = self.refused("rules")
        self.assertIn("'rules' is not an object", r.stderr)

    def test_a_record_with_a_higher_format_is_still_refused(self):
        self.start(self.shipped, fmt=5)
        r = self.refused("rules")
        self.assertIn("newer install.py", r.stderr)


class RecordRuleTest(RuleRecordCase):

    def test_stores_the_decision_against_the_current_body(self):
        self.start(self.shipped)
        self.ok("record-rule", "search-silence", "--decision", "dropped",
                "--reason", "conflicts with my own rule")
        entry = self.record()["rules"]["search-silence"]
        self.assertEqual(entry["decision"], "dropped")
        self.assertEqual(entry["reason"], "conflicts with my own rule")
        self.assertEqual(entry["body_sha256"],
                         install.body_sha256(self.rule_body("search-silence")))
        self.assertRegex(entry["date"], r"^\d{4}-\d\d-\d\d$")
        self.assertIn("bundle_commit", entry)

    def test_a_missing_reason_is_stored_as_declined_for_dropped_and_empty_otherwise(self):
        self.start(self.shipped)
        self.ok("record-rule", "search-silence", "--decision", "dropped")
        self.ok("record-rule", "lesson-routing", "--decision", "taken")
        self.ok("record-rule", "existence-vs-magnitude", "--decision", "merged", "--reason", "  ")
        rules = self.record()["rules"]
        self.assertEqual(rules["search-silence"]["reason"], "declined, no reason given")
        self.assertEqual(rules["lesson-routing"]["reason"], "")
        self.assertEqual(rules["existence-vs-magnitude"]["reason"], "")

    def test_recording_again_overwrites_which_reverses_a_decision(self):
        self.start(self.shipped)
        self.ok("record-rule", "search-silence", "--decision", "dropped", "--reason", "no")
        self.ok("record-rule", "search-silence", "--decision", "taken")
        entry = self.record()["rules"]["search-silence"]
        self.assertEqual((entry["decision"], entry["reason"]), ("taken", ""))

    def test_an_id_the_bundle_does_not_have_is_refused_and_nothing_is_written(self):
        self.start(self.shipped)
        before = read(self.t("workflow-bundle/install-record.json"))
        r = self.refused("record-rule", "no-such-rule", "--decision", "taken")
        self.assertIn("no rule with the ID no-such-rule", r.stderr)
        self.assertIn("search-silence", r.stderr)
        self.assertEqual(read(self.t("workflow-bundle/install-record.json")), before)

    def test_an_unknown_decision_is_a_usage_error(self):
        self.start(self.shipped)
        self.assertEqual(self.run_install("record-rule", "search-silence", "--decision",
                                          "kept").returncode, 2)


class RecordFileRefusalTest(RuleRecordCase):
    """`record CLAUDE.md` is refused, with any decision, while a rule is undecided."""

    def test_every_label_is_refused_while_a_new_rule_is_undecided(self):
        base = fixture("user-CLAUDE-a6c5979.md")  # lacks the shipped-text rule
        for decision in ("kept", "merged", "replaced"):
            with self.subTest(decision=decision):
                # replaced is checked against the file, so give it the bundle version
                self.start(base, mine=self.shipped if decision == "replaced"
                           else "# My rules\n\n- be brief\n")
                before = read(self.t("workflow-bundle/install-record.json"))
                r = self.refused("record", "CLAUDE.md", "--decision", decision)
                self.assertIn("write-for-readers", r.stderr)
                self.assertNotIn("high-level-answers", r.stderr)
                self.assertEqual(read(self.t("workflow-bundle/install-record.json")), before)
                self.assertEqual(read(self.t("workflow-bundle/base/CLAUDE.md.base")), base)

    def test_allowed_once_each_rule_is_recorded_and_then_refreshes_the_base(self):
        self.start(fixture("user-CLAUDE-a6c5979.md"))
        self.ok("record-rule", "executor-briefs-home", "--decision", "taken")
        self.ok("record-rule", "lesson-routing", "--decision", "taken")
        self.ok("record-rule", "end-of-turn-text", "--decision", "taken")
        self.ok("record-rule", "write-for-readers", "--decision", "taken")
        for rid in ("search-silence", "self-carrying-sentences", "observable-vs-inferred",
                    "second-real-example", "existence-vs-magnitude"):
            self.ok("record-rule", rid, "--decision", "taken")
        r = self.ok("record", "CLAUDE.md", "--decision", "merged")
        self.assertNotIn("until it is edited again", r.stdout)
        self.assertIn("editing the file does not list it again", r.stdout)
        entry = self.record()["files"]["CLAUDE.md"]
        self.assertEqual(entry["decision"], "merged")
        self.assertEqual(entry["bundle_sha256"], sha(self.shipped))
        self.assertEqual(read(self.t("workflow-bundle/base/CLAUDE.md.base")), self.shipped)
        self.ok("record", "CLAUDE.md", "--decision", "kept")  # nothing left to decide

    def test_a_changed_rule_with_only_a_decision_on_its_old_body_is_still_undecided(self):
        self.start(fixture("user-CLAUDE-f596cd7.md"))
        self.ok("record-rule", "write-for-readers", "--decision", "taken")
        old = {"decision": "taken", "reason": "", "body_sha256": "0" * 64}
        rules = self.record()["rules"]
        rules["self-carrying-sentences"] = old
        self.write_rules(rules)
        r = self.refused("record", "CLAUDE.md", "--decision", "merged")
        self.assertIn("self-carrying-sentences", r.stderr)
        self.assertNotIn("write-for-readers", r.stderr)

    def test_a_dropped_changed_rule_does_not_block(self):
        self.start(fixture("user-CLAUDE-f596cd7.md"))
        self.ok("record-rule", "executor-briefs-home", "--decision", "taken")
        self.ok("record-rule", "lesson-routing", "--decision", "taken")
        self.ok("record-rule", "end-of-turn-text", "--decision", "taken")
        self.ok("record-rule", "write-for-readers", "--decision", "taken")
        for rid in ("search-silence", "observable-vs-inferred", "second-real-example",
                    "existence-vs-magnitude"):
            self.ok("record-rule", rid, "--decision", "taken")
        rules = self.record()["rules"]
        rules["self-carrying-sentences"] = {"decision": "dropped", "reason": "too wordy",
                                            "body_sha256": "0" * 64}
        self.write_rules(rules)
        self.ok("record", "CLAUDE.md", "--decision", "merged")

    def test_a_base_that_is_not_the_recorded_version_means_the_full_pass(self):
        # No usable base: every rule is undecided, as on a first install.
        self.start(self.shipped, base_hash="0" * 64)
        r = self.refused("record", "CLAUDE.md", "--decision", "merged")
        for rule_id, _body in install.split_rules(self.shipped):
            self.assertIn(rule_id, r.stderr)

    def test_a_missing_base_copy_means_the_full_pass_and_recording_every_rule_ends_it(self):
        self.start(self.shipped)
        os.remove(self.t("workflow-bundle/base/CLAUDE.md.base"))
        self.refused("record", "CLAUDE.md", "--decision", "merged")
        for rule_id, _body in install.split_rules(self.shipped):
            self.ok("record-rule", rule_id, "--decision", "taken")
        self.ok("record", "CLAUDE.md", "--decision", "merged")

    def test_an_unchanged_bundle_needs_no_rule_decisions(self):
        # The core complaint in #27: the user edited their file, the bundle did not change.
        self.start(self.shipped)
        self.ok("record", "CLAUDE.md", "--decision", "kept")

    def test_a_base_without_ids_that_matches_the_bundle_needs_no_rule_decisions(self):
        # The shipped file as a bundle from before rule IDs would have written it.
        self.start(install.RULE_ID.sub("", self.shipped))
        self.ok("record", "CLAUDE.md", "--decision", "kept")

    def test_other_files_are_not_affected(self):
        self.start(self.shipped)
        self.write("prompt-lessons.md", "mine\n")
        r = self.ok("record", "prompt-lessons.md", "--decision", "kept")
        self.assertIn("skip it until it is edited again", r.stdout)

    def write_rules(self, rules):
        record = self.record()
        record["rules"] = rules
        self.write("workflow-bundle/install-record.json", json.dumps(record))


class RulesListingTest(RuleRecordCase):

    def test_lists_each_decision_with_reason_date_and_whether_the_bundle_changed_it(self):
        self.start(self.shipped, rules={
            "search-silence": {"decision": "dropped", "reason": "conflicts with mine",
                               "body_sha256": install.body_sha256(
                                   self.rule_body("search-silence")), "date": "2026-10-01"},
            "lesson-routing": {"decision": "taken", "reason": "",
                               "body_sha256": "0" * 64, "date": "2026-10-02"},
            "gone-rule": {"decision": "merged", "reason": "", "body_sha256": "1" * 64,
                          "date": "2026-10-03"}})
        out = self.ok("rules").stdout
        self.assertIn("Recorded rule decisions: 3", out)
        self.assertIn("  search-silence: dropped, 2026-10-01 (decided on the current wording)", out)
        self.assertIn("    reason: conflicts with mine", out)
        self.assertIn("  lesson-routing: taken, 2026-10-02 (the bundle has reworded it since)", out)
        self.assertIn("  gone-rule: merged, 2026-10-03 (no longer in the bundle)", out)
        self.assertEqual(out.count("reason:"), 1)

    def test_lists_what_was_just_recorded(self):
        self.start(self.shipped)
        self.ok("record-rule", "search-silence", "--decision", "dropped", "--reason", "nope")
        out = self.ok("rules").stdout
        self.assertIn("Recorded rule decisions: 1", out)
        self.assertIn("  search-silence: dropped,", out)
        self.assertIn("(decided on the current wording)", out)
        self.assertIn("    reason: nope", out)


if __name__ == "__main__":
    unittest.main()
