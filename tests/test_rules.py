"""Tests for the rule IDs in payload/user-CLAUDE.md and install.py's split_rules.

Run from the repo root: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_rules
Every run of install.py passes --target explicitly: its default target is the real ~/.claude.
"""
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = os.path.join(REPO, "payload", "user-CLAUDE.md")

_spec = importlib.util.spec_from_file_location("install_under_test",
                                               os.path.join(REPO, "install.py"))
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)

# The three tags the rules carried before every rule had one. Other payload files cite them
# by name, so they must keep these names.
KEPT_TAGS = {"one-decision-at-a-time", "rule-into-code", "second-real-example"}


FIXTURES = os.path.join(REPO, "tests", "fixtures")


def fixture_text(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def shipped_text():
    with open(SHIPPED, encoding="utf-8") as f:
        return f.read()


class SplitRulesTest(unittest.TestCase):

    def test_shipped_file_parses_to_18_rules_with_18_unique_ids(self):
        rules = install.split_rules(shipped_text())
        self.assertEqual(len(rules), 18)
        ids = [rule_id for rule_id, _body in rules]
        self.assertNotIn(None, ids)
        self.assertEqual(len(set(ids)), 18)
        self.assertTrue(KEPT_TAGS <= set(ids))

    def test_shipped_bodies_hold_no_id_tag_and_no_extra_whitespace(self):
        for rule_id, body in install.split_rules(shipped_text()):
            self.assertNotIn("`[%s]`" % rule_id, body)
            self.assertEqual(body, " ".join(body.split()))
            self.assertNotIn("# Working rules", body)

    def test_rewrapping_a_rule_leaves_its_body_unchanged(self):
        wide = "- A rule that runs on for a while.\n  Second line of it, with more words.\n"
        narrow = ("- A rule that runs on\n  for a while. Second line\n"
                  "  of it,   with more\n  words.\n")
        a = install.split_rules(wide + "  → `[some-rule]`\n")
        b = install.split_rules(narrow + "  → `[some-rule]`\n")
        self.assertEqual(a, b)
        self.assertEqual(a, [("some-rule", "- A rule that runs on for a while. Second line of "
                                           "it, with more words.")])

    def test_a_heading_ends_a_bullet_and_is_not_part_of_it(self):
        text = ("preamble\n\n# Section\n\n- first\n  → `[one]`\n\n# Next section\n\n"
                "- second\n  → `[two]`\n")
        self.assertEqual(install.split_rules(text), [("one", "- first"), ("two", "- second")])

    def test_a_heading_without_a_tag_does_not_leak_into_the_bullet_before_it(self):
        text = "- last of the section\n\n# Next section\n\n- other\n  → `[b]`\n"
        self.assertEqual(install.split_rules(text),
                         [(None, "- last of the section"), ("b", "- other")])

    def test_a_blank_line_inside_a_bullet_does_not_end_it(self):
        text = "- first part\n\n  second part\n  → `[a]`\n"
        self.assertEqual(install.split_rules(text), [("a", "- first part second part")])

    def test_an_arrow_mid_text_is_not_an_id(self):
        text = "- route a → b, then c → `[not-an-id]` in the middle of a line\n  more text\n"
        self.assertEqual(install.split_rules(text), [(None, " ".join(text.split()))])

    def test_a_tag_ending_the_first_paragraph_is_the_id_and_leaves_the_rest_in_the_body(self):
        text = "- first paragraph. → `[mid]`\n  second paragraph.\n"
        self.assertEqual(install.split_rules(text),
                         [("mid", "- first paragraph. second paragraph.")])

    def test_text_before_the_first_bullet_is_not_a_rule(self):
        self.assertEqual(install.split_rules("just prose\n\n# Heading\n"), [])


class CheckRuleIdsTest(unittest.TestCase):

    def test_missing_id_is_refused_naming_the_rule(self):
        with self.assertRaises(ValueError) as cm:
            install.check_rule_ids("- has one\n  → `[a]`\n- lacks one\n  text\n", "f.md")
        self.assertIn("no ID", str(cm.exception))
        self.assertIn("- lacks one", str(cm.exception))

    def test_duplicate_id_is_refused_naming_the_rule(self):
        with self.assertRaises(ValueError) as cm:
            install.check_rule_ids("- first\n  → `[a]`\n- second\n  → `[a]`\n", "f.md")
        self.assertIn("[a]", str(cm.exception))
        self.assertIn("- second", str(cm.exception))

    def test_two_tags_in_one_rule_are_refused(self):
        with self.assertRaises(ValueError) as cm:
            install.check_rule_ids("- one. → `[a]`\n  two. → `[b]`\n", "f.md")
        self.assertIn("more than one", str(cm.exception))
        self.assertIn("- one.", str(cm.exception))

    def test_the_shipped_file_passes(self):
        install.check_rule_ids(shipped_text(), "payload/user-CLAUDE.md")


def rule(rule_id, body):
    """A one-bullet rules file; `body` is the bullet's text, including its leading "- "."""
    return "%s\n  → `[%s]`\n" % (body, rule_id)


def record(decision, body_text, reason=""):
    return {"decision": decision, "reason": reason,
            "body_sha256": install.body_sha256(install.split_rules(body_text)[0][1])}


def raised(base, bundle, records=None):
    return [(i["id"], i["status"]) for i in install.rules_to_raise(base, bundle, records or {})]


class BodyHashTest(unittest.TestCase):

    def test_hash_is_sha256_of_the_collapsed_body_as_utf_8(self):
        (rule_id, body), = install.split_rules("- caf\u00e9   rule\n  text\n  \u2192 `[a]`\n")
        self.assertEqual(body, "- caf\u00e9 rule text")
        self.assertEqual(install.body_sha256(body),
                         hashlib.sha256("- caf\u00e9 rule text".encode("utf-8")).hexdigest())


class RealRulesToRaiseTest(unittest.TestCase):
    """The two real bundle versions an install can hold, against the shipped file."""

    def test_the_base_a_real_install_holds_raises_only_the_rules_changed_since(self):
        # 4ac01a8 has no IDs, and its second-real-example tag sits mid-bullet. Since then the
        # routing rule gained its exception, the executor-briefs pointer lost a demoted rule, and
        # the panel-after-prose and broken-instrument rules were removed. The panel rule came back
        # reworded as end-of-turn-text; its first line differs, so it pairs with nothing and shows
        # as new beside the old bullet's removal. Five rules were since trimmed to their
        # instructions; their first lines are unchanged, so each pairs with its old bullet. The
        # self-carrying-sentences, observable-vs-inferred and search-silence rules were then
        # reworded from their first lines, so each shows as new beside its old bullet's removal,
        # like the panel rule.
        base = fixture_text("user-CLAUDE-4ac01a8.md")
        self.assertEqual({rid for rid, _ in install.split_rules(base)} - {None},
                         {"one-decision-at-a-time", "rule-into-code", "second-real-example"})
        items = install.rules_to_raise(base, shipped_text(), {})
        self.assertEqual([(i["id"], i["status"]) for i in items],
                         [("executor-briefs-home", "changed"), ("lesson-routing", "changed"),
                          ("search-silence", "new"), ("say-what-you-searched", "new"),
                          ("end-of-turn-text", "new"), ("self-carrying-sentences", "new"),
                          ("observable-vs-inferred", "new"),
                          ("second-real-example", "changed"),
                          ("existence-vs-magnitude", "changed"),
                          ("measure-reach", "new"),
                          (None, "removed"), (None, "removed"), (None, "removed"),
                          (None, "removed"), (None, "removed")])
        self.assertTrue(items[10]["old"].startswith("- **A search that turns up nothing"))
        self.assertTrue(items[11]["old"].startswith("- Never call a blocking-panel tool"))
        self.assertTrue(items[12]["old"].startswith("- **Write the sentence so it carries"))
        self.assertTrue(items[13]["old"].startswith("- When introspecting on your own behaviour"))
        self.assertTrue(items[14]["old"].startswith("- **A broken instrument's reading"))

    def test_the_version_before_the_shipped_text_rule_raises_exactly_that_rule(self):
        items = install.rules_to_raise(fixture_text("user-CLAUDE-a6c5979.md"),
                                       shipped_text(), {})
        self.assertEqual([(i["id"], i["status"]) for i in items],
                         [("executor-briefs-home", "changed"), ("lesson-routing", "changed"),
                          ("search-silence", "new"), ("say-what-you-searched", "new"),
                          ("end-of-turn-text", "new"), ("self-carrying-sentences", "new"),
                          ("observable-vs-inferred", "new"),
                          ("second-real-example", "changed"),
                          ("existence-vs-magnitude", "changed"),
                          ("measure-reach", "new"),
                          ("write-for-readers", "new"), (None, "removed"), (None, "removed"),
                          (None, "removed"), (None, "removed"), (None, "removed")])
        self.assertIsNone(items[10]["old"])
        self.assertTrue(items[10]["new"].startswith("- **Write shipped text for the people"))
        self.assertTrue(items[10]["first_line"].startswith("- **Write shipped text"))
        self.assertIsNone(items[10]["reason"])


class RulesToRaiseTest(unittest.TestCase):

    OLD = "- the rule as first worded"
    NEW = "- the rule, reworded since"

    def test_changed_with_no_record(self):
        items = install.rules_to_raise(rule("a", self.OLD), rule("a", self.NEW), {})
        self.assertEqual(items, [{"id": "a", "status": "changed", "old": self.OLD,
                                  "new": self.NEW, "reason": None, "first_line": self.NEW,
                                  "old_text": self.OLD + "\n  \u2192 `[a]`",
                                  "new_text": self.NEW + "\n  \u2192 `[a]`"}])

    def test_same_body_raises_nothing_even_when_rewrapped(self):
        self.assertEqual(raised(rule("a", "- one two three"),
                                "- one\n  two\n  three\n  → `[a]`\n"), [])

    def test_taken_record_on_an_old_body_does_not_silence_the_change(self):
        for decision in ("taken", "merged"):
            with self.subTest(decision=decision):
                records = {"a": record(decision, rule("a", self.OLD))}
                self.assertEqual(raised(rule("a", self.OLD), rule("a", self.NEW), records),
                                 [("a", "changed")])

    def test_dropped_record_on_an_old_body_is_dropped_changed_with_its_reason(self):
        records = {"a": record("dropped", rule("a", self.OLD), "conflicts with my own rule")}
        (item,) = install.rules_to_raise(rule("a", self.OLD), rule("a", self.NEW), records)
        self.assertEqual((item["status"], item["reason"], item["old"], item["new"]),
                         ("dropped-changed", "conflicts with my own rule", self.OLD, self.NEW))

    def test_a_record_on_the_current_body_raises_nothing(self):
        for decision in ("dropped", "taken", "merged"):
            with self.subTest(decision=decision):
                records = {"a": record(decision, rule("a", self.NEW))}
                self.assertEqual(raised(rule("a", self.OLD), rule("a", self.NEW), records), [])

    def test_a_new_rule_is_new_until_it_is_decided(self):
        base = rule("a", "- first")
        bundle = rule("a", "- first") + rule("b", "- second")
        self.assertEqual(raised(base, bundle), [("b", "new")])
        self.assertEqual(raised(base, bundle, {"b": record("taken", rule("b", "- second"))}), [])

    def test_removed_with_an_id(self):
        items = install.rules_to_raise(rule("a", "- first") + rule("b", "- second"),
                                       rule("a", "- first"), {})
        self.assertEqual(items, [{"id": "b", "status": "removed", "old": "- second",
                                  "new": None, "reason": None, "first_line": "- second",
                                  "old_text": "- second\n  \u2192 `[b]`", "new_text": None}])

    def test_removed_from_a_base_without_ids(self):
        base = "- first\n- second rule\n  runs on\n"
        bundle = rule("a", "- first")
        items = install.rules_to_raise(base, bundle, {})
        self.assertEqual(items, [{"id": None, "status": "removed", "old": "- second rule runs on",
                                  "new": None, "reason": None, "first_line": "- second rule",
                                  "old_text": "- second rule\n  runs on", "new_text": None}])

    def test_base_without_ids_matches_by_body_and_the_rest_is_new(self):
        base = "- first\n- second\n"
        bundle = rule("a", "- first") + rule("b", "- second reworded")
        self.assertEqual([(i["id"], i["status"])
                          for i in install.rules_to_raise(base, bundle, {})],
                         [("b", "new"), (None, "removed")])

    def test_no_base_makes_every_rule_new(self):
        bundle = rule("a", "- first") + rule("b", "- second")
        self.assertEqual(raised(None, bundle), [("a", "new"), ("b", "new")])
        self.assertEqual(raised(None, shipped_text()),
                         [(rid, "new") for rid, _ in install.split_rules(shipped_text())])

    def test_no_base_with_every_rule_recorded_raises_nothing(self):
        # The first-install pass ends by recording each rule; it must then count as decided.
        records = {rid: {"decision": "taken", "reason": "", "body_sha256":
                         install.body_sha256(body)}
                   for rid, body in install.split_rules(shipped_text())}
        self.assertEqual(install.rules_to_raise(None, shipped_text(), records), [])

    def test_items_come_in_bundle_order_then_removed_in_base_order(self):
        base = rule("x", "- gone") + rule("a", "- one") + rule("y", "- also gone")
        bundle = rule("b", "- two") + rule("a", "- one changed")
        self.assertEqual(raised(base, bundle), [("b", "new"), ("a", "changed"),
                                                ("x", "removed"), ("y", "removed")])

    def test_a_bundle_rule_without_an_id_is_refused(self):
        with self.assertRaises(ValueError):
            install.rules_to_raise(None, "- no tag here\n", {})


class IdlessBaseTest(unittest.TestCase):
    """A base from before rules had IDs: reworded rules pair with their earlier version."""

    def test_a_reworded_rule_pairs_with_its_earlier_version_in_the_real_old_base(self):
        # f596cd7 predates the shipped-text rule and the current wording of the
        # second-real-example rule, whose first line is unchanged, so it pairs as changed.
        # The search-silence, self-carrying-sentences and observable-vs-inferred rules' first
        # lines changed, so each shows as new beside its old bullet's removal.
        base = fixture_text("user-CLAUDE-f596cd7.md")
        items = install.rules_to_raise(base, shipped_text(), {})
        self.assertEqual([(i["id"], i["status"]) for i in items],
                         [("executor-briefs-home", "changed"), ("lesson-routing", "changed"),
                          ("search-silence", "new"), ("say-what-you-searched", "new"),
                          ("end-of-turn-text", "new"), ("self-carrying-sentences", "new"),
                          ("observable-vs-inferred", "new"),
                          ("second-real-example", "changed"),
                          ("existence-vs-magnitude", "changed"),
                          ("measure-reach", "new"),
                          ("write-for-readers", "new"), (None, "removed"), (None, "removed"),
                          (None, "removed"), (None, "removed"), (None, "removed")])
        changed = items[7]
        self.assertEqual(changed["id"], "second-real-example")
        self.assertTrue(changed["old"].startswith("- Before a fix or lesson becomes a standing"))
        self.assertNotEqual(changed["old"], changed["new"])
        self.assertIsNone(items[6]["old"])
        self.assertTrue(items[11]["old"].startswith("- **A search that turns up nothing"))
        self.assertTrue(items[14]["old"].startswith("- When introspecting on your own behaviour"))
        self.assertIsNone(items[10]["old"])

    def test_pairing_is_by_first_line_with_the_id_tag_stripped(self):
        base = "- the same first line\n  old second line\n"
        bundle = "- the same first line\n  new second line\n  \u2192 `[a]`\n"
        (item,) = install.rules_to_raise(base, bundle, {})
        self.assertEqual((item["id"], item["status"], item["old"]),
                         ("a", "changed", "- the same first line old second line"))
        tagged = "- the same first line \u2192 `[a]`\n  new second line\n"
        self.assertEqual(raised(base, tagged), [("a", "changed")])

    def test_an_old_bullet_whose_first_line_matches_no_rule_stays_removed(self):
        base = "- kept as is\n- a rule since deleted\n  with a second line\n"
        bundle = rule("a", "- kept as is") + rule("b", "- a different rule")
        items = install.rules_to_raise(base, bundle, {})
        self.assertEqual([(i["id"], i["status"]) for i in items],
                         [("b", "new"), (None, "removed")])
        self.assertEqual(items[1]["first_line"], "- a rule since deleted")

    def test_one_old_bullet_pairs_with_one_rule_only(self):
        base = "- shared first line\n  old\n"
        bundle = ("- shared first line\n  one\n  \u2192 `[a]`\n"
                  "- shared first line\n  two\n  \u2192 `[b]`\n")
        self.assertEqual(raised(base, bundle), [("a", "changed"), ("b", "new")])

    def test_a_decided_rule_still_uses_up_its_equal_old_bullet(self):
        base = "- same\n"
        records = {"a": {"decision": "taken", "reason": "",
                         "body_sha256": install.body_sha256("- same")}}
        self.assertEqual(install.rules_to_raise(base, rule("a", "- same"), records), [])

    def test_a_reworded_dropped_rule_pairs_and_is_dropped_changed(self):
        base = "- first line\n  old\n"
        bundle = "- first line\n  new\n  \u2192 `[a]`\n"
        records = {"a": record("dropped", rule("a", "- first line old"), "no thanks")}
        (item,) = install.rules_to_raise(base, bundle, records)
        self.assertEqual((item["status"], item["reason"]), ("dropped-changed", "no thanks"))


class RemovedRuleTest(unittest.TestCase):

    def test_a_removed_rule_the_user_dropped_is_not_reported(self):
        base = rule("a", "- one") + rule("b", "- two")
        records = {"b": record("dropped", rule("b", "- two"), "never wanted")}
        self.assertEqual(raised(base, rule("a", "- one"), records), [])

    def test_a_removed_rule_the_user_took_is_still_reported(self):
        base = rule("a", "- one") + rule("b", "- two")
        for decision in ("taken", "merged"):
            with self.subTest(decision=decision):
                records = {"b": record(decision, rule("b", "- two"))}
                self.assertEqual(raised(base, rule("a", "- one"), records), [("b", "removed")])


class PayloadTagsTest(unittest.TestCase):

    def test_no_new_id_equals_a_tag_used_in_another_payload_file(self):
        """The install steps search all of payload/ for a tag's name, so a new ID that is
        also another file's tag would turn up citations that are not about the rule."""
        ids = {rule_id for rule_id, _ in install.split_rules(shipped_text())} - KEPT_TAGS
        tag = re.compile(r"\[([a-z0-9]+(?:-[a-z0-9]+)+)\]")
        clashes = []
        for root, _dirs, files in os.walk(os.path.join(REPO, "payload")):
            for name in files:
                path = os.path.join(root, name)
                if path == SHIPPED or not name.endswith(".md"):
                    continue
                with open(path, encoding="utf-8") as f:
                    used = set(tag.findall(f.read()))
                clashes += [(os.path.relpath(path, REPO), i) for i in sorted(ids & used)]
        self.assertEqual(clashes, [])


class LoadManifestRefusalTest(unittest.TestCase):
    """install.py refuses a shared payload file whose rules lack IDs, through its own front door."""

    def run_with_payload(self, edit):
        with tempfile.TemporaryDirectory() as tmp:
            clone = os.path.join(tmp, "clone")
            os.makedirs(clone)
            shutil.copy(os.path.join(REPO, "install.py"), clone)
            shutil.copy(os.path.join(REPO, "manifest.json"), clone)
            shutil.copytree(os.path.join(REPO, "payload"), os.path.join(clone, "payload"),
                            ignore=shutil.ignore_patterns("__pycache__"))
            path = os.path.join(clone, "payload", "user-CLAUDE.md")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(edit(text))
            target = os.path.join(tmp, "claude")
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            r = subprocess.run([sys.executable, os.path.join(clone, "install.py"),
                                "--target", target, "--dry-run"],
                               capture_output=True, text=True, env=env)
            return r, os.path.exists(target)

    def test_unedited_copy_is_accepted(self):
        r, _ = self.run_with_payload(lambda text: text)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_rule_without_an_id_stops_the_install(self):
        r, written = self.run_with_payload(
            lambda text: text.replace("  → `[search-silence]`\n", "", 1))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Nothing was written", r.stderr)
        self.assertIn("this rule has no ID", r.stderr)
        self.assertIn("Before weighing whether to remove an established behaviour", r.stderr)
        self.assertFalse(written)

    def test_a_repeated_id_stops_the_install(self):
        r, written = self.run_with_payload(
            lambda text: text.replace("`[search-silence]`", "`[rule-into-code]`", 1))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("[rule-into-code] is used twice", r.stderr)
        self.assertFalse(written)


if __name__ == "__main__":
    unittest.main()
