"""Tests for install.py. Each test runs the script as a subprocess against a temp target.

Run from the repo root: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests
Every run passes --target explicitly: the script's default target is the real ~/.claude.
"""
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(REPO, "install.py")

with open(os.path.join(REPO, "manifest.json"), encoding="utf-8") as _f:
    MANIFEST = json.load(_f)
CORE_FILES = [e for e in MANIFEST["files"] if e["component"] == "core"]
GUARD_FILES = [e for e in MANIFEST["files"] if e["component"] == "subagent-guard"]
CORE_TESTS = [t["file"] for t in MANIFEST["tests"] if t["component"] == "core"]
GUARD_TESTS = [t["file"] for t in MANIFEST["tests"] if t["component"] == "subagent-guard"]


def run_install(target, *extra, script=INSTALL, home=None):
    assert target, "every run must pass --target"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if home:
        env["HOME"] = home
    return subprocess.run([sys.executable, script, "--target", target, *extra],
                          capture_output=True, text=True, env=env)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def snapshot(root):
    """Every file under root with its bytes and mode."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            out[os.path.relpath(p, root)] = (read_bytes(p), os.stat(p).st_mode)
    return out


class TargetCase(unittest.TestCase):
    """A fresh temp target per test, and helpers to install into it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self._tmp.name, "claude")

    def tearDown(self):
        self._tmp.cleanup()

    def t(self, rel):
        return os.path.join(self.target, rel)

    def install(self, *extra):
        return run_install(self.target, *extra)

    def install_ok(self, *extra):
        r = self.install(*extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def assert_tests_passed(self, out, test_files):
        self.assertIn("Tests: %d of %d files passed" % (len(test_files), len(test_files)), out)
        for rel in test_files:
            self.assertRegex(out, r"PASS %s \([1-9]\d* tests\)" % rel.replace(".", r"\."))

    def record(self):
        with open(self.t("workflow-bundle/install-record.json"), encoding="utf-8") as f:
            return json.load(f)


class InstallTest(TargetCase):
    # --- fresh target -------------------------------------------------------

    def test_fresh_target(self):
        r = self.install_ok()
        for e in CORE_FILES:
            self.assertEqual(read_bytes(self.t(e["target"])),
                             read_bytes(os.path.join(REPO, e["source"])), e["target"])
            is_exec = bool(os.stat(self.t(e["target"])).st_mode & stat.S_IXUSR)
            self.assertEqual(is_exec, e["executable"], e["target"])
        for e in GUARD_FILES:
            self.assertFalse(os.path.exists(self.t(e["target"])), e["target"])
        self.assertIn("Installed: %d" % len(CORE_FILES), r.stdout)
        self.assertIn("Unchanged: 0", r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 0", r.stdout)
        self.assert_tests_passed(r.stdout, CORE_TESTS)
        for rel in GUARD_TESTS:
            self.assertNotIn(rel, r.stdout)
        self.assertIn("Optional components not installed: subagent-guard", r.stdout)

    def test_fresh_target_writes_record_and_base_copies(self):
        self.install_ok()
        files = self.record()["files"]
        self.assertEqual(sorted(files), sorted(e["target"] for e in CORE_FILES))
        for e in CORE_FILES:
            rec = files[e["target"]]
            self.assertEqual(rec["decision"], "installed")
            self.assertEqual(rec["kind"], e["kind"])
            self.assertEqual(rec["bundle_sha256"], rec["current_sha256"])
            self.assertEqual(read_bytes(self.t("workflow-bundle/base/" + e["target"] + ".base")),
                             read_bytes(os.path.join(REPO, e["source"])))
            self.assertEqual(rec["base"], "workflow-bundle/base/" + e["target"] + ".base")

    def test_with_subagent_guard(self):
        r = self.install_ok("--with-subagent-guard")
        for e in GUARD_FILES:
            self.assertEqual(read_bytes(self.t(e["target"])),
                             read_bytes(os.path.join(REPO, e["source"])))
            is_exec = bool(os.stat(self.t(e["target"])).st_mode & stat.S_IXUSR)
            self.assertEqual(is_exec, e["executable"], e["target"])
        self.assertIn("Installed: %d" % (len(CORE_FILES) + len(GUARD_FILES)), r.stdout)
        self.assert_tests_passed(r.stdout, CORE_TESTS + GUARD_TESTS)
        self.assertNotIn("Optional components not installed", r.stdout)

    # --- re-run -------------------------------------------------------------

    def test_rerun_over_identical_install(self):
        self.install_ok()
        before = snapshot(self.target)
        r = self.install_ok()
        self.assertIn("Installed: 0", r.stdout)
        self.assertIn("Unchanged: %d" % len(CORE_FILES), r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 0", r.stdout)
        self.assert_tests_passed(r.stdout, CORE_TESTS)
        after = snapshot(self.target)
        installed = {e["target"] for e in CORE_FILES}
        self.assertEqual({k: v for k, v in after.items() if k in installed},
                         {k: v for k, v in before.items() if k in installed})
        self.assertEqual({v["decision"] for v in self.record()["files"].values()},
                         {"identical"})

    # --- existing files that differ -----------------------------------------

    def test_edited_owned_file_is_listed_not_overwritten(self):
        self.install_ok()
        edited = {
            "prompt-lessons.md": b"my own prompt lessons\n",
            "skills/finalise/scripts/check_thread_state.py":
                read_bytes(self.t("skills/finalise/scripts/check_thread_state.py"))
                + b"\n# my local tweak\n",
        }
        for rel, content in edited.items():
            with open(self.t(rel), "wb") as f:
                f.write(content)
        r = self.install_ok()
        self.assertIn("Needs a decision (existing file differs, left as it is): 2", r.stdout)
        for rel, content in edited.items():
            self.assertIn("  %s (owned)" % rel, r.stdout)
            self.assertEqual(read_bytes(self.t(rel)), content)
        self.assertIn("Unchanged: %d" % (len(CORE_FILES) - 2), r.stdout)

    def test_edited_seed_ledger_is_left_alone_and_not_listed(self):
        self.install_ok()
        content = b"# Lesson candidates\n\n- my first candidate\n"
        with open(self.t("lesson-candidates.md"), "wb") as f:
            f.write(content)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t("lesson-candidates.md")), content)
        self.assertNotIn("lesson-candidates.md", r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 0", r.stdout)
        self.assertEqual(self.record()["files"]["lesson-candidates.md"]["decision"], "kept")

    def test_existing_claude_md_is_listed(self):
        os.makedirs(self.target)
        mine = b"# My rules\n\n- be brief\n"
        with open(self.t("CLAUDE.md"), "wb") as f:
            f.write(mine)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t("CLAUDE.md")), mine)
        self.assertIn("Needs a decision (existing file differs, left as it is): 1", r.stdout)
        self.assertIn("  CLAUDE.md (shared)", r.stdout)
        self.assertIn("Installed: %d" % (len(CORE_FILES) - 1), r.stdout)
        self.assertNotIn("CLAUDE.md", self.record()["files"])

    # --- dry run ------------------------------------------------------------

    def test_dry_run_on_fresh_target_writes_nothing(self):
        r = self.install_ok("--dry-run")
        self.assertFalse(os.path.exists(self.target))
        self.assertIn("DRY RUN", r.stdout)
        self.assertIn("Installed: %d" % len(CORE_FILES), r.stdout)
        self.assertIn("Tests: not run (dry run)", r.stdout)

    def test_dry_run_over_partial_install_writes_nothing(self):
        self.install_ok()
        os.remove(self.t("commands/memory-audit.md"))
        with open(self.t("prompt-lessons.md"), "wb") as f:
            f.write(b"mine\n")
        before = snapshot(self.target)
        r = self.install_ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertIn("Installed: 1", r.stdout)
        self.assertIn("  prompt-lessons.md (owned)", r.stdout)

    # --- failures -----------------------------------------------------------

    def test_corrupted_installed_script_fails_tests_nonzero(self):
        self.install_ok()
        script = self.t("skills/finalise/scripts/check_memory_index.py")
        with open(script, "wb") as f:
            f.write(b"import sys\nsys.exit(3)\n")
        r = self.install()
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(read_bytes(script), b"import sys\nsys.exit(3)\n")
        self.assertIn("  skills/finalise/scripts/check_memory_index.py (owned)", r.stdout)
        self.assertIn("FAIL skills/finalise/scripts/test_check_memory_index.py", r.stdout)

    def test_unreadable_manifest_exits_nonzero(self):
        repo_copy = os.path.join(self._tmp.name, "repo")
        os.makedirs(repo_copy)
        shutil.copy(INSTALL, repo_copy)
        with open(os.path.join(repo_copy, "manifest.json"), "w") as f:
            f.write("{ not json")
        r = run_install(self.target, script=os.path.join(repo_copy, "install.py"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("manifest.json", r.stderr)
        self.assertFalse(os.path.exists(self.target))


CORE_SETTINGS = [s for s in MANIFEST["settings"] if s["component"] == "core"]
GUARD_SETTINGS = [s for s in MANIFEST["settings"] if s["component"] == "subagent-guard"]
POST = CORE_SETTINGS[0]["entry"]
PRE = GUARD_SETTINGS[0]["entry"]
USER_BASH_HOOK = {"matcher": "Bash",
                  "hooks": [{"type": "command", "command": "~/bin/my-own-bash-hook.sh"}]}
USER_EDIT_HOOK = {"matcher": "Edit",
                  "hooks": [{"type": "command", "command": "~/bin/my-own-edit-hook.sh"}]}


class SettingsTest(TargetCase):
    def write_settings(self, obj_or_text):
        os.makedirs(self.target, exist_ok=True)
        text = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text)
        with open(self.t("settings.json"), "w", encoding="utf-8") as f:
            f.write(text)

    def settings(self):
        with open(self.t("settings.json"), encoding="utf-8") as f:
            return json.load(f)

    def backups(self):
        return sorted(n for n in os.listdir(self.target) if n.startswith("settings.json.bak-"))

    def test_settings_absent_is_created_with_core_entry(self):
        r = self.install_ok()
        self.assertEqual(self.settings(), {"hooks": {"PostToolUse": [POST]}})
        self.assertEqual(self.backups(), [])
        self.assertIn("settings.json: added PostToolUse hook ~/.claude/hooks/remind_finalise.py",
                      r.stdout)
        self.assertIn("settings.json: created", r.stdout)
        self.assertEqual([(a["event"], a["command"]) for a in self.record()["settings_added"]],
                         [("PostToolUse", "~/.claude/hooks/remind_finalise.py")])

    def test_user_posttooluse_bash_hook_kept_and_not_reported(self):
        original = {"model": "some-model",
                    "hooks": {"PostToolUse": [USER_BASH_HOOK]},
                    "permissions": {"allow": ["Bash(ls:*)"]}}
        self.write_settings(original)
        original_bytes = read_bytes(self.t("settings.json"))
        r = self.install_ok()
        got = self.settings()
        self.assertEqual(got["hooks"]["PostToolUse"], [USER_BASH_HOOK, POST])
        self.assertEqual(got["model"], "some-model")
        self.assertEqual(got["permissions"], original["permissions"])
        self.assertEqual(list(got), ["model", "hooks", "permissions"])
        self.assertNotIn("my-own-bash-hook", r.stdout)
        self.assertNotIn("differ from the bundle", r.stdout)
        self.assertIn("settings.json: rewritten; the previous version is saved as "
                      "settings.json.bak-", r.stdout)
        [bak] = self.backups()
        self.assertEqual(read_bytes(self.t(bak)), original_bytes)
        self.assertEqual([a["command"] for a in self.record()["settings_added"]],
                         ["~/.claude/hooks/remind_finalise.py"])

    def test_hooks_without_posttooluse_gets_the_event_added(self):
        self.write_settings({"hooks": {"PreToolUse": [USER_EDIT_HOOK]}})
        self.install_ok()
        self.assertEqual(self.settings(),
                         {"hooks": {"PreToolUse": [USER_EDIT_HOOK], "PostToolUse": [POST]}})

    def test_rerun_adds_no_duplicate_entries(self):
        self.write_settings({"hooks": {"PostToolUse": [USER_BASH_HOOK]}})
        self.install_ok("--with-subagent-guard")
        after_first = read_bytes(self.t("settings.json"))
        backups = self.backups()
        r = self.install_ok("--with-subagent-guard")
        self.assertEqual(read_bytes(self.t("settings.json")), after_first)
        self.assertEqual(self.backups(), backups)
        self.assertEqual(self.settings()["hooks"],
                         {"PostToolUse": [USER_BASH_HOOK, POST], "PreToolUse": [PRE]})
        self.assertIn("settings.json: already has 2 of the bundle's hook entries", r.stdout)
        self.assertNotIn("settings.json: added", r.stdout)
        self.assertEqual(len(self.record()["settings_added"]), 2)

    def test_bundle_entry_that_differs_is_reported_not_changed(self):
        mine = copy.deepcopy(POST)
        mine["hooks"][0]["timeout"] = 30
        self.write_settings({"hooks": {"PostToolUse": [mine]}})
        before = read_bytes(self.t("settings.json"))
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t("settings.json")), before)
        self.assertEqual(self.backups(), [])
        self.assertIn("settings.json: entries that differ from the bundle's, left as they are: 1",
                      r.stdout)
        self.assertIn("  PostToolUse hook ~/.claude/hooks/remind_finalise.py; the bundle's "
                      "entry is ", r.stdout)
        self.assertEqual(self.record()["settings_added"], [])

    def test_invalid_json_leaves_everything_untouched_and_exits_2(self):
        self.write_settings('{"hooks": {"PostToolUse": [}')
        before = snapshot(self.target)
        r = self.install()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("settings.json", r.stderr)
        self.assertIn("Nothing was written", r.stderr)
        self.assertEqual(snapshot(self.target), before)

    def test_dry_run_reports_settings_addition_and_writes_nothing(self):
        self.write_settings({"hooks": {}})
        before = snapshot(self.target)
        r = self.install_ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertIn("settings.json: would add PostToolUse hook "
                      "~/.claude/hooks/remind_finalise.py", r.stdout)
        self.assertNotIn("settings.json: created", r.stdout)
        self.assertNotIn("rewritten", r.stdout)

    # --- the same hook file written another way ------------------------------

    HOOK_REL = "hooks/remind_finalise.py"

    def entry_with(self, command, **changes):
        e = copy.deepcopy(POST)
        e["hooks"][0]["command"] = command
        e["hooks"][0].update(changes)
        return e

    def equivalent_forms(self, target):
        home = os.path.expanduser("~")
        hook = os.path.join(target, self.HOOK_REL)
        return [
            home + "/.claude/" + self.HOOK_REL,
            "$HOME/.claude/" + self.HOOK_REL,
            "${HOME}/.claude/" + self.HOOK_REL,
            "python3 ~/.claude/" + self.HOOK_REL,
            "/usr/bin/env python3 $HOME/.claude/" + self.HOOK_REL,
            hook,
            "/usr/bin/python3 " + hook,
        ]

    def test_bundle_hook_in_another_path_form_counts_as_present(self):
        root = self.target
        for i in range(len(self.equivalent_forms(root))):
            self.target = os.path.join(root, "t%d" % i)
            command = self.equivalent_forms(self.target)[i]
            with self.subTest(command=command):
                self.write_settings({"hooks": {"PostToolUse": [self.entry_with(command)]}})
                r = self.install_ok("--dry-run")
                self.assertIn("settings.json: already has 1 of the bundle's hook entries",
                              r.stdout)
                self.assertNotIn("would add", r.stdout)
                self.assertNotIn("differ from the bundle", r.stdout)
        self.target = root

    def test_other_path_form_is_not_rewritten_on_a_real_run(self):
        self.write_settings({"hooks": {"PostToolUse": [
            self.entry_with("$HOME/.claude/" + self.HOOK_REL)]}})
        before = read_bytes(self.t("settings.json"))
        self.install_ok()
        self.assertEqual(read_bytes(self.t("settings.json")), before)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.record()["settings_added"], [])

    def test_other_path_form_with_a_different_timeout_is_reported(self):
        self.write_settings({"hooks": {"PostToolUse": [
            self.entry_with("$HOME/.claude/" + self.HOOK_REL, timeout=30)]}})
        r = self.install_ok("--dry-run")
        self.assertIn("settings.json: entries that differ from the bundle's, left as they are: 1",
                      r.stdout)
        self.assertNotIn("would add", r.stdout)

    def test_a_different_command_on_the_same_file_is_not_the_bundle_hook(self):
        root = self.target
        commands = ["~/.claude/" + self.HOOK_REL + " --verbose",
                    "~/.claude/hooks/remind_finalise_v2.py",
                    "bash ~/.claude/" + self.HOOK_REL,
                    "hooks/remind_finalise.py"]
        for i, command in enumerate(commands):
            with self.subTest(command=command):
                self.target = os.path.join(root, "n%d" % i)
                self.write_settings({"hooks": {"PostToolUse": [self.entry_with(command)]}})
                r = self.install_ok("--dry-run")
                self.assertIn("settings.json: would add PostToolUse hook", r.stdout)
                self.assertNotIn("already has", r.stdout)
                self.assertNotIn("differ from the bundle", r.stdout)
        self.target = root

    def test_guard_present_but_not_recorded_is_named_not_offered(self):
        self.install_ok()
        for e in GUARD_FILES:
            shutil.copyfile(os.path.join(REPO, e["source"]), self.t(e["target"]))
        r = self.install_ok("--dry-run")
        self.assertIn("Optional component subagent-guard: its files are present but not in "
                      "the install record; re-running with --with-subagent-guard will start "
                      "tracking it.", r.stdout)
        self.assertNotIn("Optional components not installed", r.stdout)

    # --- the optional hook --------------------------------------------------

    def test_with_guard_adds_pretooluse_entry_and_records_it(self):
        self.install_ok("--with-subagent-guard")
        self.assertEqual(self.settings(), {"hooks": {"PostToolUse": [POST], "PreToolUse": [PRE]}})
        self.assertEqual(self.record()["components"]["subagent-guard"]["state"], "installed")

    def test_installed_guard_stays_installed_without_the_flag(self):
        self.install_ok("--with-subagent-guard")
        guard = "hooks/block_subagent_record_edit.py"
        with open(self.t(guard), "ab") as f:
            f.write(b"\n# my tweak\n")
        r = self.install_ok()
        self.assertNotIn("Optional components not installed", r.stdout)
        self.assertIn("  %s (owned)" % guard, r.stdout)
        self.assertIn("Unchanged: %d" % (len(CORE_FILES) + len(GUARD_FILES) - 1), r.stdout)
        self.assert_tests_passed(r.stdout, CORE_TESTS + GUARD_TESTS)
        self.assertIn("settings.json: already has 2 of the bundle's hook entries", r.stdout)

    def test_decline_then_rerun_does_not_offer_it(self):
        r = self.install_ok("decline", "subagent-guard")
        self.assertIn("declined", r.stdout)
        self.assertEqual(self.record()["components"]["subagent-guard"]["state"], "declined")
        r = self.install_ok()
        self.assertIn("Optional components declined earlier: subagent-guard", r.stdout)
        self.assertNotIn("Optional components not installed", r.stdout)
        self.assertNotIn("--with-subagent-guard", r.stdout)
        for e in GUARD_FILES:
            self.assertFalse(os.path.exists(self.t(e["target"])), e["target"])
        self.assertNotIn("PreToolUse", self.settings()["hooks"])

    def test_flag_after_decline_installs_it(self):
        self.install_ok("decline", "subagent-guard")
        r = self.install_ok("--with-subagent-guard")
        self.assertNotIn("declined earlier", r.stdout)
        self.assertEqual(self.record()["components"]["subagent-guard"]["state"], "installed")
        self.assertIn("PreToolUse", self.settings()["hooks"])

    def test_decline_refused_once_installed(self):
        self.install_ok("--with-subagent-guard")
        r = self.install("decline", "subagent-guard")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already installed", r.stderr)
        self.assertEqual(self.record()["components"]["subagent-guard"]["state"], "installed")

    # --- the record subcommand ----------------------------------------------

    SCRIPT = "skills/finalise/scripts/check_thread_state.py"

    def edit_script(self, suffix):
        with open(self.t(self.SCRIPT), "ab") as f:
            f.write(suffix)

    def test_record_then_rerun_does_not_list_it(self):
        self.install_ok()
        self.edit_script(b"\n# my local tweak\n")
        r = self.install_ok()
        self.assertIn("  %s (owned)" % self.SCRIPT, r.stdout)
        r = self.install_ok("record", self.SCRIPT, "--decision", "kept")
        rec = self.record()["files"][self.SCRIPT]
        self.assertEqual(rec["decision"], "kept")
        self.assertEqual(rec["current_sha256"], sha256(self.t(self.SCRIPT)))
        self.assertNotEqual(rec["bundle_sha256"], rec["current_sha256"])
        r = self.install_ok()
        self.assertNotIn(self.SCRIPT, r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 0", r.stdout)
        self.assertIn("skipped by an earlier decision: 1", r.stdout)

    def test_record_then_edit_again_lists_it(self):
        self.install_ok()
        self.edit_script(b"\n# my local tweak\n")
        self.install_ok("record", self.SCRIPT, "--decision", "merged")
        self.edit_script(b"# another tweak\n")
        r = self.install_ok()
        self.assertIn("  %s (owned)" % self.SCRIPT, r.stdout)
        self.assertIn("skipped by an earlier decision: 0", r.stdout)

    def test_record_rejects_a_path_not_in_the_manifest(self):
        self.install_ok()
        for path in ("settings.json", "skills/finalise/nope.py", "../CLAUDE.md"):
            r = self.install("record", path, "--decision", "kept")
            self.assertEqual(r.returncode, 2, path)
            self.assertIn("not a file this bundle installs", r.stderr, path)

    def test_record_replaced_requires_the_bundle_version(self):
        self.install_ok()
        self.edit_script(b"\n# my local tweak\n")
        r = self.install("record", self.SCRIPT, "--decision", "replaced")
        self.assertEqual(r.returncode, 2)
        self.assertIn("doesn't match the bundle version", r.stderr)
        self.assertEqual(self.record()["files"][self.SCRIPT]["decision"], "installed")
        shutil.copyfile(os.path.join(REPO, "payload", self.SCRIPT), self.t(self.SCRIPT))
        self.install_ok("record", self.SCRIPT, "--decision", "replaced")
        self.assertEqual(self.record()["files"][self.SCRIPT]["decision"], "replaced")

    # --- file modes, base copies and the summary ----------------------------

    HOOK = "hooks/remind_finalise.py"

    def test_identical_hook_that_lost_its_exec_bit_gets_it_back(self):
        self.install_ok()
        os.chmod(self.t(self.HOOK), 0o644)
        r = self.install_ok()
        self.assertTrue(os.stat(self.t(self.HOOK)).st_mode & stat.S_IXUSR)
        self.assertIn("Executable bit restored (content not changed): 1\n  %s" % self.HOOK,
                      r.stdout)
        self.assertIn("Unchanged: %d" % len(CORE_FILES), r.stdout)

    def test_exec_bit_restored_on_a_file_skipped_by_earlier_decision(self):
        self.install_ok()
        with open(self.t(self.HOOK), "ab") as f:
            f.write(b"\n# my tweak\n")
        self.install_ok("record", self.HOOK, "--decision", "kept")
        os.chmod(self.t(self.HOOK), 0o644)
        content = read_bytes(self.t(self.HOOK))
        before = snapshot(self.target)
        r = self.install_ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertIn("Executable bit would be restored", r.stdout)
        r = self.install_ok()
        self.assertTrue(os.stat(self.t(self.HOOK)).st_mode & stat.S_IXUSR)
        self.assertEqual(read_bytes(self.t(self.HOOK)), content)
        self.assertNotIn("  %s (owned)" % self.HOOK, r.stdout)

    def test_base_copies_are_not_named_like_live_files(self):
        self.install_ok("--with-subagent-guard")
        base = self.t("workflow-bundle/base")
        names = [os.path.relpath(os.path.join(d, n), base)
                 for d, _dirs, files in os.walk(base) for n in files]
        self.assertEqual(len(names), len(CORE_FILES) + len(GUARD_FILES))
        for n in names:
            self.assertTrue(n.endswith(".base"), n)
        self.assertFalse(os.path.exists(os.path.join(base, "CLAUDE.md")))

    def test_summary_counts_account_for_every_file(self):
        self.install_ok()
        with open(self.t("lesson-candidates.md"), "ab") as f:
            f.write(b"- a candidate\n")
        self.edit_script(b"\n# tweak\n")
        self.install_ok("record", self.SCRIPT, "--decision", "kept")
        with open(self.t("prompt-lessons.md"), "ab") as f:
            f.write(b"- mine\n")
        os.remove(self.t("commands/memory-audit.md"))
        install_old_version(self, OLD_DOC)
        r = self.install_ok()
        self.assertIn("Installed: 1\n", r.stdout)
        self.assertIn("Unchanged: %d\n" % (len(CORE_FILES) - 5), r.stdout)
        self.assertIn("Updated: 1\n  %s\n" % OLD_DOC, r.stdout)
        self.assertIn("Left as you have them: 2 (seed ledgers kept: 1; "
                      "skipped by an earlier decision: 1)", r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 1", r.stdout)


def sha256(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


# A file no shipped test reads, so an old or edited copy of it doesn't fail the install's tests.
OLD_DOC = "writing-standing-docs.md"
OLD_CONTENT = b"# An older bundle version of this file\n"


def install_old_version(case, rel, decision="installed", now=None, recorded_current=None,
                        old=OLD_CONTENT):
    """Make an installed file look as if an older bundle had installed it.

    The file, its base copy and the record's bundle hash are set to an "old version" that the
    payload no longer matches, so the bundle has changed since. The record's current hash is
    `recorded_current` (default: the old version's), and the file on disk ends up as `now`
    (default: the old version).
    """
    old_sha = hashlib.sha256(old).hexdigest()
    with open(case.t("workflow-bundle/base/" + rel + ".base"), "wb") as f:
        f.write(old)
    with open(case.t(rel), "wb") as f:
        f.write(old if now is None else now)
    path = case.t("workflow-bundle/install-record.json")
    record = case.record()
    record["files"][rel].update({
        "bundle_sha256": old_sha, "decision": decision,
        "current_sha256": (old_sha if recorded_current is None
                           else hashlib.sha256(recorded_current).hexdigest())})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f)


class UpgradeTest(TargetCase):
    """After the bundle changes, a file the user never edited is brought up to date."""

    EDITED = OLD_CONTENT + b"- a rule of my own\n"

    def setUp(self):
        super().setUp()
        self.install_ok()
        self.bundle = read_bytes(os.path.join(REPO, "payload", OLD_DOC))

    def test_untouched_file_is_updated(self):
        install_old_version(self, OLD_DOC)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t(OLD_DOC)), self.bundle)
        rec = self.record()["files"][OLD_DOC]
        self.assertEqual(rec["decision"], "updated")
        self.assertEqual(rec["bundle_sha256"], hashlib.sha256(self.bundle).hexdigest())
        self.assertEqual(rec["current_sha256"], rec["bundle_sha256"])
        self.assertEqual(read_bytes(self.t("workflow-bundle/base/" + OLD_DOC + ".base")),
                         self.bundle)
        self.assertIn("Updated: 1\n  %s\n" % OLD_DOC, r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 0", r.stdout)
        # Settled now: the next run finds it identical.
        r = self.install_ok()
        self.assertIn("Updated: 0\n", r.stdout)
        self.assertIn("Unchanged: %d\n" % len(CORE_FILES), r.stdout)

    def test_file_edited_since_install_is_not_updated(self):
        # Installed by the older bundle, then edited, never recorded: the recorded hashes
        # agree with each other but not with the file.
        install_old_version(self, OLD_DOC, now=self.EDITED)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t(OLD_DOC)), self.EDITED)
        self.assertIn("Updated: 0\n", r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 1", r.stdout)
        self.assertIn("  %s (owned)" % OLD_DOC, r.stdout)

    def test_kept_file_left_alone_since_its_decision_is_not_updated(self):
        # Recorded as kept while it differed from the older bundle, and not touched since:
        # the file matches the recorded current hash, which differs from the recorded bundle.
        install_old_version(self, OLD_DOC, decision="kept", now=self.EDITED,
                            recorded_current=self.EDITED)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t(OLD_DOC)), self.EDITED)
        self.assertIn("Updated: 0\n", r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 1", r.stdout)
        self.assertIn("  %s (owned)" % OLD_DOC, r.stdout)

    def test_dry_run_lists_the_update_and_writes_nothing(self):
        install_old_version(self, OLD_DOC)
        before = snapshot(self.target)
        r = self.install_ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertIn("Would update: 1\n  %s\n" % OLD_DOC, r.stdout)


class BundleChangeTest(TargetCase):
    """A file the user edited is listed with only the bundle's own change, as a diff file."""

    LISTED = "Needs a decision (existing file differs, left as it is): "
    MINE = b"- a rule of my own\n"

    def setUp(self):
        super().setUp()
        self.install_ok()
        lines = read_bytes(os.path.join(REPO, "payload", OLD_DOC)).splitlines(keepends=True)
        # The older bundle lacked one line that the bundle has now.
        self.added = lines[10]
        self.old = b"".join(lines[:10] + lines[11:])
        self.diff = self.t("workflow-bundle/changes/" + OLD_DOC + ".diff")

    def edited_after_old_install(self):
        install_old_version(self, OLD_DOC, old=self.old, now=self.old + self.MINE)

    def stale_change(self):
        stale = self.t("workflow-bundle/changes/from-an-earlier-run.diff")
        os.makedirs(os.path.dirname(stale), exist_ok=True)
        with open(stale, "w", encoding="utf-8") as f:
            f.write("stale\n")
        return stale

    def test_diff_holds_the_bundle_change_and_none_of_the_users_edit(self):
        self.edited_after_old_install()
        r = self.install_ok()
        self.assertIn(self.LISTED + "1", r.stdout)
        self.assertIn("  %s (owned), bundle change: %s\n" % (OLD_DOC, self.diff), r.stdout)
        text = read_bytes(self.diff).decode("utf-8")
        body = [l for l in text.splitlines(keepends=True)
                if not l.startswith(("---", "+++", "@@"))]
        self.assertEqual([l for l in body if l.startswith("+")],
                         ["+" + self.added.decode("utf-8")])
        self.assertEqual([l for l in body if l.startswith("-")], [])
        self.assertNotIn(self.MINE.decode("utf-8").strip(), text)
        self.assertEqual(read_bytes(self.t(OLD_DOC)), self.old + self.MINE)

    def test_no_record_lists_the_file_without_a_diff(self):
        os.remove(self.t("workflow-bundle/install-record.json"))
        with open(self.t(OLD_DOC), "ab") as f:
            f.write(self.MINE)
        r = self.install_ok()
        self.assertIn(self.LISTED + "1", r.stdout)
        self.assertIn("  %s (owned)\n" % OLD_DOC, r.stdout)
        self.assertNotIn("bundle change", r.stdout)
        self.assertFalse(os.path.exists(self.t("workflow-bundle/changes")))

    def test_base_copy_that_is_not_the_recorded_version_gives_no_diff(self):
        self.edited_after_old_install()
        with open(self.t("workflow-bundle/base/" + OLD_DOC + ".base"), "ab") as f:
            f.write(b"- not what the record says was installed\n")
        r = self.install_ok()
        self.assertIn("  %s (owned)\n" % OLD_DOC, r.stdout)
        self.assertNotIn("bundle change", r.stdout)
        self.assertFalse(os.path.exists(self.diff))

    def test_edit_while_the_bundle_is_unchanged_lists_it_without_a_diff(self):
        with open(self.t(OLD_DOC), "ab") as f:
            f.write(self.MINE)
        r = self.install_ok()
        self.assertIn("  %s (owned)\n" % OLD_DOC, r.stdout)
        self.assertNotIn("bundle change", r.stdout)
        self.assertFalse(os.path.exists(self.diff))

    def test_changes_from_an_earlier_run_are_emptied(self):
        stale = self.stale_change()
        self.edited_after_old_install()
        self.install_ok()
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(self.diff))

    def test_dry_run_lists_the_file_without_a_diff_and_writes_nothing(self):
        self.stale_change()
        self.edited_after_old_install()
        before = snapshot(self.target)
        r = self.install_ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)
        self.assertIn("  %s (owned)\n" % OLD_DOC, r.stdout)
        self.assertNotIn("bundle change", r.stdout)

    def test_unreadable_settings_leaves_earlier_changes_in_place(self):
        self.stale_change()
        with open(self.t("settings.json"), "w", encoding="utf-8") as f:
            f.write('{"hooks": [}')
        before = snapshot(self.target)
        r = self.install()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Nothing was written", r.stderr)
        self.assertEqual(snapshot(self.target), before)

    def test_recording_a_decision_refreshes_the_base_so_it_is_not_listed_again(self):
        self.edited_after_old_install()
        self.install_ok()
        self.install_ok("record", OLD_DOC, "--decision", "merged")
        self.assertEqual(read_bytes(self.t("workflow-bundle/base/" + OLD_DOC + ".base")),
                         read_bytes(os.path.join(REPO, "payload", OLD_DOC)))
        r = self.install_ok()
        self.assertNotIn(OLD_DOC, r.stdout)
        self.assertFalse(os.path.exists(self.diff))


RETIRED = MANIFEST["retired"][0]["target"]


class RetiredTest(TargetCase):
    """A file the bundle no longer ships is removed if never edited, otherwise raised."""

    OLD = b"# The command the bundle used to ship\n"
    MINE = b"- my own addition\n"
    REMOVED = "Removed (no longer in the bundle): "
    LISTED = "No longer in the bundle, you edited it or it isn't in the record: "

    def setUp(self):
        super().setUp()
        self.install_ok()
        self.base = self.t("workflow-bundle/base/" + RETIRED + ".base")

    def plant(self, now=None, recorded=True):
        """Put the retired file back as an older bundle installed it, and as `now` on disk.

        The record is rewritten without "retired_kept", as an install from before it existed.
        """
        os.makedirs(os.path.dirname(self.t(RETIRED)), exist_ok=True)
        with open(self.t(RETIRED), "wb") as f:
            f.write(self.OLD if now is None else now)
        record = self.record()
        record.pop("retired_kept", None)
        if recorded:
            os.makedirs(os.path.dirname(self.base), exist_ok=True)
            with open(self.base, "wb") as f:
                f.write(self.OLD)
            old_sha = hashlib.sha256(self.OLD).hexdigest()
            record["files"][RETIRED] = {
                "kind": "owned", "bundle_sha256": old_sha, "current_sha256": old_sha,
                "decision": "installed", "bundle_commit": None, "date": "2026-01-01",
                "base": "workflow-bundle/base/" + RETIRED + ".base"}
        with open(self.t("workflow-bundle/install-record.json"), "w", encoding="utf-8") as f:
            json.dump(record, f)

    def test_untouched_retired_file_is_removed_with_its_record_and_base(self):
        self.plant()
        r = self.install_ok()
        self.assertFalse(os.path.exists(self.t(RETIRED)))
        self.assertNotIn(RETIRED, self.record()["files"])
        self.assertFalse(os.path.exists(self.base))
        self.assertIn(self.REMOVED + "1\n  %s\n" % RETIRED, r.stdout)
        self.assertIn(self.LISTED + "0\n", r.stdout)

    def test_edited_retired_file_is_listed_and_left(self):
        self.plant(now=self.OLD + self.MINE)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t(RETIRED)), self.OLD + self.MINE)
        self.assertIn(RETIRED, self.record()["files"])
        self.assertIn(self.REMOVED + "0\n", r.stdout)
        self.assertIn(self.LISTED + "1\n  %s (" % RETIRED, r.stdout)

    def test_retired_file_not_in_the_record_is_listed_and_left(self):
        self.plant(recorded=False)
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t(RETIRED)), self.OLD)
        self.assertIn(self.REMOVED + "0\n", r.stdout)
        self.assertIn(self.LISTED + "1\n  %s (" % RETIRED, r.stdout)

    def test_absent_retired_file_is_dropped_from_the_record_silently(self):
        self.plant()
        os.remove(self.t(RETIRED))
        r = self.install_ok()
        self.assertNotIn(RETIRED, self.record()["files"])
        self.assertFalse(os.path.exists(self.base))
        self.assertNotIn(RETIRED, r.stdout)
        self.assertIn(self.REMOVED + "0\n", r.stdout)

    def test_dry_run_writes_nothing(self):
        self.plant()
        before = snapshot(self.target)
        r = self.install_ok("--dry-run")
        self.assertIn("Would remove (no longer in the bundle): 1\n  %s\n" % RETIRED, r.stdout)
        self.assertEqual(snapshot(self.target), before)
        # Absent: a real run would drop its entry; a dry run leaves the record as it is.
        os.remove(self.t(RETIRED))
        before = snapshot(self.target)
        self.install_ok("--dry-run")
        self.assertEqual(snapshot(self.target), before)

    def test_kept_retired_file_is_left_on_later_runs_even_as_the_old_bundle_version(self):
        # Content equal to the old bundle version would be "untouched" by its hashes alone.
        self.plant()
        r = self.install_ok("record", RETIRED, "--decision", "kept")
        self.assertIn("Recorded: %s kept." % RETIRED, r.stdout)
        self.assertNotIn("bundle version changes", r.stdout)
        record = self.record()
        self.assertNotIn(RETIRED, record["files"])
        self.assertEqual(record["retired_kept"], {RETIRED: sha256(self.t(RETIRED))})
        r = self.install_ok()
        self.assertEqual(read_bytes(self.t(RETIRED)), self.OLD)
        self.assertNotIn(RETIRED, r.stdout)
        self.assertIn("skipped by an earlier decision: 1)", r.stdout)
        # Edited after keeping: raised again, and still never deleted.
        with open(self.t(RETIRED), "ab") as f:
            f.write(self.MINE)
        r = self.install_ok()
        self.assertIn(self.LISTED + "1\n", r.stdout)
        self.assertTrue(os.path.exists(self.t(RETIRED)))

    def test_record_removed_is_refused_while_the_file_exists(self):
        self.plant(now=self.OLD + self.MINE)
        r = self.install("record", RETIRED, "--decision", "removed")
        self.assertEqual(r.returncode, 2)
        self.assertIn("still exists", r.stderr)
        self.assertIn(RETIRED, self.record()["files"])
        self.assertTrue(os.path.exists(self.base))

    def test_record_removed_after_deleting_stops_tracking_it(self):
        self.plant(now=self.OLD + self.MINE)
        os.remove(self.t(RETIRED))
        r = self.install_ok("record", RETIRED, "--decision", "removed")
        self.assertIn("Recorded: %s removed." % RETIRED, r.stdout)
        self.assertNotIn(RETIRED, self.record()["files"])
        self.assertNotIn(RETIRED, self.record()["retired_kept"])
        self.assertFalse(os.path.exists(self.base))

    def test_record_removed_is_refused_for_a_file_the_bundle_still_ships(self):
        r = self.install("record", OLD_DOC, "--decision", "removed")
        self.assertEqual(r.returncode, 2)
        self.assertIn("still in the bundle", r.stderr)
        self.assertTrue(os.path.exists(self.t(OLD_DOC)))
        self.assertIn(OLD_DOC, self.record()["files"])

    def test_record_replaced_or_merged_is_refused_for_a_retired_file(self):
        self.plant(now=self.OLD + self.MINE)
        before = self.record()
        for decision in ("replaced", "merged"):
            r = self.install("record", RETIRED, "--decision", decision)
            self.assertEqual(r.returncode, 2, decision)
            self.assertIn("can only be recorded as kept or removed", r.stderr, decision)
        self.assertEqual(self.record(), before)

    def test_project_override_refuses_a_retired_file(self):
        self.plant()
        r = self.install("project-override", RETIRED, "--decision", "install")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a skill or command this bundle installs", r.stderr)

    def test_retired_target_that_is_also_live_exits_2(self):
        repo_copy = os.path.join(self._tmp.name, "repo")
        os.makedirs(repo_copy)
        shutil.copy(INSTALL, repo_copy)
        shutil.copytree(os.path.join(REPO, "payload"), os.path.join(repo_copy, "payload"))
        manifest = copy.deepcopy(MANIFEST)
        manifest["retired"].append({"target": OLD_DOC, "note": "both"})
        with open(os.path.join(repo_copy, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        before = snapshot(self.target)
        r = run_install(self.target, script=os.path.join(repo_copy, "install.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("both as installed and as retired", r.stderr)
        self.assertEqual(snapshot(self.target), before)


class ProjectOverrideTest(TargetCase):
    """A user-level skill or command overrides a project's own of the same name."""

    SKILL = "skills/finalise/SKILL.md"
    HELD = "Held back, because a project has its own and a user-level copy would override it: "

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self._tmp.name, "home")
        os.makedirs(self.home)

    def project(self, name, own="skill"):
        """A project directory with its own /finalise, known to Claude Code by its folder."""
        d = os.path.realpath(os.path.join(self.home, name))
        os.makedirs(d, exist_ok=True)
        self.give_own(d, own)
        os.makedirs(self.t("projects/" + re.sub(r"[^A-Za-z0-9]", "-", d)), exist_ok=True)
        return d

    def give_own(self, d, own="skill"):
        path = (os.path.join(d, ".claude/skills/finalise/SKILL.md") if own == "skill"
                else os.path.join(d, ".claude/commands/finalise.md"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("the project's own\n")

    def test_project_skill_holds_back_only_the_skill_file(self):
        d = self.project("my.proj_x")
        r = self.install_ok()
        self.assertIn(self.HELD + "1", r.stdout)
        self.assertIn("  %s (/finalise), own copy in: %s" % (self.SKILL, d), r.stdout)
        self.assertFalse(os.path.exists(self.t(self.SKILL)))
        self.assertTrue(os.path.exists(self.t("skills/finalise/scripts/check_memory_index.py")))
        self.assertIn("Installed: %d" % (len(CORE_FILES) - 1), r.stdout)
        self.assert_tests_passed(r.stdout, CORE_TESTS)

    def test_project_command_file_counts_as_its_own(self):
        d = self.project("cmdproj", own="command")
        r = self.install_ok()
        self.assertIn("  %s (/finalise), own copy in: %s" % (self.SKILL, d), r.stdout)

    def test_project_found_from_a_session_log_when_the_folder_name_fits_no_path(self):
        d = os.path.realpath(os.path.join(self.home, "elsewhere"))
        os.makedirs(d)
        self.give_own(d)
        folder = self.t("projects/-no-such-path")
        os.makedirs(folder)
        with open(os.path.join(folder, "s.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "queue-operation"}) + "\n")
            f.write(json.dumps({"type": "user", "cwd": d}) + "\n")
        r = self.install_ok()
        self.assertIn("  %s (/finalise), own copy in: %s" % (self.SKILL, d), r.stdout)

    def test_project_without_its_own_changes_nothing(self):
        d = os.path.realpath(os.path.join(self.home, "plain"))
        os.makedirs(d)
        os.makedirs(self.t("projects/" + re.sub(r"[^A-Za-z0-9]", "-", d)))
        r = self.install_ok()
        self.assertIn(self.HELD + "0", r.stdout)
        self.assertTrue(os.path.exists(self.t(self.SKILL)))

    def test_the_user_level_directory_is_not_taken_for_a_project(self):
        # The home directory's project folder: its .claude is the install target itself.
        self.target = os.path.join(self.home, ".claude")
        self.install_ok()
        os.makedirs(self.t("projects/" + re.sub(r"[^A-Za-z0-9]", "-",
                                                os.path.realpath(self.home))))
        r = self.install_ok()
        self.assertIn(self.HELD + "0", r.stdout)
        self.assertNotIn("overriding", r.stdout)

    def test_the_real_user_level_directory_is_not_taken_for_a_project_either(self):
        # With --target elsewhere, the home directory's .claude is still the user level.
        self.give_own(self.home, own="command")
        os.makedirs(self.t("projects/" + re.sub(r"[^A-Za-z0-9]", "-",
                                                os.path.realpath(self.home))))
        r = run_install(self.target, home=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(self.HELD + "0", r.stdout)

    def test_decision_install_puts_it_in_on_the_next_run(self):
        self.project("p1")
        self.install_ok()
        r = self.install_ok("project-override", self.SKILL, "--decision", "install")
        self.assertIn("Recorded: /finalise goes in at user level", r.stdout)
        r = self.install_ok()
        self.assertIn(self.HELD + "0", r.stdout)
        self.assertNotIn("overriding", r.stdout)
        self.assertEqual(read_bytes(self.t(self.SKILL)),
                         read_bytes(os.path.join(REPO, "payload", self.SKILL)))

    def test_decision_hold_is_kept_until_another_project_gets_its_own(self):
        self.project("p1")
        self.install_ok()
        self.install_ok("project-override", self.SKILL, "--decision", "hold")
        r = self.install_ok()
        self.assertIn(self.HELD + "0", r.stdout)
        self.assertIn("Held back by an earlier decision: 1\n  %s\n" % self.SKILL, r.stdout)
        d2 = self.project("p2")
        r = self.install_ok()
        self.assertIn(self.HELD + "1", r.stdout)
        self.assertIn(d2, r.stdout)
        self.assertFalse(os.path.exists(self.t(self.SKILL)))

    def test_already_installed_copy_is_reported_as_overriding_and_left(self):
        self.install_ok()
        before = read_bytes(self.t(self.SKILL))
        d = self.project("late")
        r = self.install_ok()
        self.assertIn("Installed at user level and overriding a project's own: 1\n"
                      "  %s (/finalise), own copy in: %s" % (self.SKILL, d), r.stdout)
        self.assertEqual(read_bytes(self.t(self.SKILL)), before)

    def test_project_override_refused_when_no_project_has_its_own(self):
        r = self.install("project-override", self.SKILL, "--decision", "install")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no project has its own /finalise", r.stderr)

    def test_project_override_refused_for_a_file_that_is_not_a_skill_or_command(self):
        self.project("p1")
        r = self.install("project-override", "CLAUDE.md", "--decision", "install")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a skill or command this bundle installs", r.stderr)

    def test_dry_run_reports_held_back_and_writes_nothing(self):
        self.project("p1")
        r = self.install_ok("--dry-run")
        self.assertIn(self.HELD + "1", r.stdout)
        self.assertEqual(sorted(os.listdir(self.target)), ["projects"])


if __name__ == "__main__":
    unittest.main()
