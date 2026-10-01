"""Tests for install.py. Each test runs the script as a subprocess against a temp target.

Run from the repo root: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests
Every run passes --target explicitly: the script's default target is the real ~/.claude.
"""
import copy
import hashlib
import json
import os
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


def run_install(target, *extra, script=INSTALL):
    assert target, "every run must pass --target"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
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

    # --- review fixes -------------------------------------------------------

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
        r = self.install_ok()
        self.assertIn("Installed: 1\n", r.stdout)
        self.assertIn("Unchanged: %d\n" % (len(CORE_FILES) - 4), r.stdout)
        self.assertIn("Left as you have them: 2 (seed ledgers kept: 1; "
                      "skipped by an earlier decision: 1)", r.stdout)
        self.assertIn("Needs a decision (existing file differs, left as it is): 1", r.stdout)


def sha256(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


if __name__ == "__main__":
    unittest.main()
