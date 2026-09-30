"""Tests for install.py. Each test runs the script as a subprocess against a temp target.

Run from the repo root: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests
Every run passes --target explicitly: the script's default target is the real ~/.claude.
"""
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


class InstallTest(unittest.TestCase):
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
            self.assertEqual(read_bytes(self.t("workflow-bundle/base/" + e["target"])),
                             read_bytes(os.path.join(REPO, e["source"])))

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


if __name__ == "__main__":
    unittest.main()
