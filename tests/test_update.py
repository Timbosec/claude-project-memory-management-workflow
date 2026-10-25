"""Tests for `install.py update`: bring a git clone of the bundle up to the published version,
saving anything the clone holds of its own to a backup branch first.

Every test uses real git in throwaway directories under the system temp dir, with git's own
configuration switched off so the user's identity, pull.rebase and hooks cannot change a result.
update_clone() resets the working tree hard, so run_update() refuses any path outside the temp dir.
"""
import datetime
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(REPO, "install.py")
_spec = importlib.util.spec_from_file_location("install_under_test", INSTALL)
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)

NOW = datetime.datetime(2026, 3, 4, 5, 6)
BACKUP = "backup-20260304-0506"
IDENT = ["-c", "user.name=Test Person", "-c", "user.email=test@example.invalid"]


def assert_throwaway(path):
    """Refuse to touch anything that is not under the system temp dir (or is this repo)."""
    real = os.path.realpath(path)
    tmp = os.path.realpath(tempfile.gettempdir())
    if os.path.commonpath([real, tmp]) != tmp or os.path.commonpath([real, REPO]) == REPO:
        raise AssertionError("refusing to run update on %s: not a throwaway directory" % path)


class GitCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.realpath(self._tmp.name)
        home = os.path.join(self.root, "home")
        os.makedirs(home)
        env = mock.patch.dict(os.environ, {
            "HOME": home, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.origin = os.path.join(self.root, "origin.git")
        self.seed = os.path.join(self.root, "seed")
        self.clone = os.path.join(self.root, "clone")
        self.git(self.root, "init", "-q", "--bare", "-b", "main", self.origin)
        self.git(self.root, "init", "-q", "-b", "main", self.seed)
        self.git(self.seed, "remote", "add", "origin", self.origin)

    def git(self, path, *args):
        r = subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "git %s: %s" % (" ".join(args), r.stderr))
        return r.stdout.strip()

    def write(self, base, name, text):
        with open(os.path.join(base, name), "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, base, name):
        with open(os.path.join(base, name), encoding="utf-8") as f:
            return f.read()

    def commit(self, path, name, text, message):
        self.write(path, name, text)
        self.git(path, "add", name)
        self.git(path, *IDENT, "commit", "-q", "-m", message)

    def publish(self, name, text, message):
        """A new commit on the origin's main, made through the seed repository."""
        self.commit(self.seed, name, text, message)
        self.git(self.seed, "push", "-q", "origin", "main")

    def make_clone(self):
        self.publish("bundle.txt", "one\n", "first")
        self.git(self.root, "clone", "-q", self.origin, self.clone)

    def run_update(self, path=None):
        path = path or self.clone
        assert_throwaway(path)
        return install.update_clone(path, NOW)

    def head(self, path=None):
        return self.git(path or self.clone, "rev-parse", "HEAD")

    def status(self, path=None):
        return self.git(path or self.clone, "status", "--porcelain", "--untracked-files=all")

    def backups(self):
        return self.git(self.clone, "branch", "--list", "backup-*", "--format=%(refname:short)"
                        ).split()

    def is_ancestor(self, ancestor, descendant):
        r = subprocess.run(["git", "-C", self.clone, "merge-base", "--is-ancestor", ancestor,
                            descendant], capture_output=True, text=True)
        return r.returncode == 0

    def snapshot(self):
        return (self.head(), self.status(), self.git(self.clone, "branch", "--list"))


class UpToDateTest(GitCase):
    def test_nothing_changes_and_no_backup(self):
        self.make_clone()
        before = self.snapshot()
        text = self.run_update()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.backups(), [])
        short = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.assertEqual(text, "The bundle is already up to date (at %s)." % short)


class BehindTest(GitCase):
    def test_clean_clone_moves_to_upstream_without_a_backup(self):
        self.make_clone()
        old = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.publish("bundle.txt", "two\n", "second")
        text = self.run_update()
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(self.read(self.clone, "bundle.txt"), "two\n")
        self.assertEqual(self.backups(), [])
        new = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.assertEqual(text, "Updated the bundle from %s to %s." % (old, new))


class SavesOwnChangesTest(GitCase):
    def test_diverged_local_commit_is_kept_on_the_backup_branch(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        mine = self.head()
        self.publish("bundle.txt", "two\n", "second")
        self.publish("bundle.txt", "three\n", "third")  # two behind, one ahead: counts differ
        text = self.run_update()
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(self.backups(), [BACKUP])
        self.assertTrue(self.is_ancestor(mine, BACKUP))
        self.assertFalse(os.path.exists(os.path.join(self.clone, "mine.txt")))
        self.assertEqual(self.git(self.clone, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertIn(BACKUP, text)
        self.assertIn("1 commit)", text)
        self.assertEqual(self.status(), "")

    def test_edited_tracked_file_is_saved_and_the_published_one_restored(self):
        self.make_clone()
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.publish("bundle.txt", "two\n", "second")
        text = self.run_update()
        self.assertEqual(self.read(self.clone, "bundle.txt"), "two\n")
        self.assertEqual(self.git(self.clone, "show", BACKUP + ":bundle.txt"), "my edit")
        self.assertEqual(self.status(), "")
        self.assertIn("1 edited or new file)", text)

    def test_untracked_file_is_saved_and_removed_from_the_tree(self):
        self.make_clone()
        os.makedirs(os.path.join(self.clone, "sub"))
        self.write(self.clone, "sub/notes.txt", "notes\n")
        self.write(self.clone, "sub/more.txt", "more\n")
        self.publish("bundle.txt", "two\n", "second")
        text = self.run_update()
        # git lists a new folder as one line unless told to list every file in it
        self.assertIn("(2 edited or new files)", text)
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(self.git(self.clone, "show", BACKUP + ":sub/notes.txt"), "notes")
        self.assertFalse(os.path.exists(os.path.join(self.clone, "sub", "notes.txt")))
        self.assertEqual(self.status(), "")

    def test_commit_edit_and_untracked_file_together_make_one_backup(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        mine = self.head()
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.write(self.clone, "new.txt", "new\n")
        self.publish("bundle.txt", "two\n", "second")
        text = self.run_update()
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(self.read(self.clone, "bundle.txt"), "two\n")
        self.assertEqual(self.backups(), [BACKUP])
        self.assertTrue(self.is_ancestor(mine, BACKUP))
        snapshot = self.git(self.clone, "log", "-1", "--format=%s", BACKUP)
        self.assertEqual(snapshot, "Saved by install.py update")
        self.assertNotEqual(self.git(self.clone, "rev-parse", BACKUP), mine)
        self.assertEqual(self.git(self.clone, "show", BACKUP + ":bundle.txt"), "my edit")
        self.assertEqual(self.git(self.clone, "show", BACKUP + ":new.txt"), "new")
        self.assertEqual(self.status(), "")
        self.assertIn("(1 commit and 2 edited or new files)", text)

    def test_only_a_dirty_file_and_nothing_new_upstream(self):
        self.make_clone()
        self.write(self.clone, "bundle.txt", "my edit\n")
        head = self.head()
        text = self.run_update()
        self.assertEqual(self.head(), head)
        self.assertEqual(self.read(self.clone, "bundle.txt"), "one\n")
        self.assertEqual(self.git(self.clone, "show", BACKUP + ":bundle.txt"), "my edit")
        self.assertEqual(self.status(), "")
        short = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.assertEqual(text, (
            "The bundle already matches the published version (at %s).\n"
            "Your clone had changes of its own (1 edited or new file). They are saved in the "
            "branch %s. The bundle files are now exactly the published version."
            % (short, BACKUP)))

    def test_full_report_for_a_commit_and_a_file(self):
        self.make_clone()
        old = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.publish("bundle.txt", "two\n", "second")
        self.publish("bundle.txt", "three\n", "third")
        mine = self.git(self.clone, "rev-parse", "--short", "HEAD")
        text = self.run_update()
        new = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.assertEqual(text, (
            "Updated the bundle from %s to %s.\n"
            "Your clone had changes of its own (1 commit and 1 edited or new file). They are "
            "saved in the branch %s. The bundle files are now exactly the published version."
            % (mine, new, BACKUP)))
        self.assertNotEqual(old, new)

    def test_a_backup_name_already_taken_stops_before_anything_changes(self):
        self.make_clone()
        self.git(self.clone, "branch", BACKUP)
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.publish("bundle.txt", "two\n", "second")
        before = self.snapshot()
        with self.assertRaises(install.UpdateError) as caught:
            self.run_update()
        self.assertIn("not changed", str(caught.exception))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.read(self.clone, "bundle.txt"), "my edit\n")


class RefusalTest(GitCase):
    def assert_refused(self, path, message):
        before = self.snapshot() if os.path.isdir(os.path.join(path, ".git")) else None
        with self.assertRaises(install.SetupError) as caught:
            self.run_update(path)
        self.assertIn(message, str(caught.exception))
        if before is not None:
            self.assertEqual(self.snapshot(), before)

    def test_not_a_clone(self):
        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        self.write(plain, "install.py", "x\n")
        self.assert_refused(plain, "isn't a Git clone")
        self.assertEqual(os.listdir(plain), ["install.py"])

    def test_a_folder_inside_a_clone_is_not_the_clone(self):
        self.make_clone()
        inner = os.path.join(self.clone, "inner")
        os.makedirs(inner)
        self.assert_refused(inner, "isn't a Git clone")

    def test_detached_head(self):
        self.make_clone()
        self.git(self.clone, "checkout", "-q", "--detach")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assert_refused(self.clone, "isn't on a branch")
        self.assertEqual(self.read(self.clone, "bundle.txt"), "my edit\n")

    def test_no_upstream(self):
        self.make_clone()
        self.git(self.clone, "checkout", "-q", "-b", "side")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assert_refused(self.clone, "isn't linked to a remote branch")
        self.assertEqual(self.read(self.clone, "bundle.txt"), "my edit\n")

    def test_fetch_fails(self):
        self.make_clone()
        self.git(self.clone, "remote", "set-url", "origin", os.path.join(self.root, "gone.git"))
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assert_refused(self.clone, "couldn't download the latest bundle (")
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.read(self.clone, "bundle.txt"), "my edit\n")


class SafetyGuardTest(unittest.TestCase):
    def test_the_helper_refuses_this_repository(self):
        with self.assertRaises(AssertionError):
            assert_throwaway(REPO)
        with self.assertRaises(AssertionError):
            assert_throwaway(os.path.join(REPO, "payload"))
        with self.assertRaises(AssertionError):
            assert_throwaway("/home")


class CommandTest(GitCase):
    def test_update_runs_from_a_clone_that_holds_only_install_py(self):
        """`update` must run before manifest.json and the install record are read."""
        shutil.copy(INSTALL, os.path.join(self.seed, "install.py"))
        self.git(self.seed, "add", "install.py")
        self.git(self.seed, *IDENT, "commit", "-q", "-m", "install.py alone")
        self.git(self.seed, "push", "-q", "origin", "main")
        self.git(self.root, "clone", "-q", self.origin, self.clone)
        old = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.publish("bundle.txt", "two\n", "second")
        self.assertFalse(os.path.exists(os.path.join(self.clone, "manifest.json")))
        self.assertFalse(os.path.exists(os.path.join(self.clone, "payload")))
        assert_throwaway(self.clone)
        r = subprocess.run([sys.executable, os.path.join(self.clone, "install.py"), "update"],
                           capture_output=True, text=True, cwd=self.root)
        new = self.git(self.clone, "rev-parse", "--short", "HEAD")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "Updated the bundle from %s to %s.\n" % (old, new))
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))

    def test_a_refusal_through_the_command_exits_2_and_says_nothing_was_written(self):
        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        shutil.copy(INSTALL, plain)
        assert_throwaway(plain)
        r = subprocess.run([sys.executable, os.path.join(plain, "install.py"), "update"],
                           capture_output=True, text=True, cwd=self.root)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("install.py: this folder isn't a Git clone", r.stderr)
        self.assertIn("Nothing was written.", r.stderr)

    def test_dry_run_with_update_is_an_error(self):
        # Run a copy in a folder that is not a clone: were the check missing, update would run.
        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        shutil.copy(INSTALL, plain)
        assert_throwaway(plain)
        r = subprocess.run([sys.executable, os.path.join(plain, "install.py"), "--dry-run",
                            "update"], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("apply to an install, not to update", r.stderr)


if __name__ == "__main__":
    unittest.main()
