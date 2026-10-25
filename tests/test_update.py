"""Tests for `install.py update`: bring a git clone of the bundle up to the published version,
saving anything the clone holds of its own to a backup branch first.

Every test uses real git in throwaway directories under the system temp dir, with git's own
configuration switched off so the user's identity, pull.rebase and hooks cannot change a result.
update_clone() resets the working tree hard, so run_update() refuses any path outside the temp dir.
"""
import contextlib
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


def ok_result(args):
    return subprocess.CompletedProcess(["git"] + list(args), 0, "", "")


def failed_result(args):
    return subprocess.CompletedProcess(["git"] + list(args), 1, "", "injected failure")


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

    @contextlib.contextmanager
    def intercept(self, fake):
        """Replace install.run_git: `fake(args)` returns a result to use instead of running git,
        or None to let the real command run."""
        real = install.run_git

        def wrapper(path, args, *a, **kw):
            args = list(args)
            self.calls.append((args, kw))
            result = fake(args)
            return result if result is not None else real(path, args, *a, **kw)
        self.calls = []
        with mock.patch.object(install, "run_git", wrapper):
            yield


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

    def test_a_backup_name_already_taken_gets_the_next_free_number(self):
        self.make_clone()
        self.git(self.clone, "branch", BACKUP)
        self.git(self.clone, "branch", BACKUP + "-2")
        taken = {n: self.git(self.clone, "rev-parse", n) for n in (BACKUP, BACKUP + "-2")}
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        mine = self.head()
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.publish("bundle.txt", "two\n", "second")
        text = self.run_update()
        self.assertEqual(self.backups(), [BACKUP, BACKUP + "-2", BACKUP + "-3"])
        for name, sha in taken.items():
            self.assertEqual(self.git(self.clone, "rev-parse", name), sha, name)
        self.assertTrue(self.is_ancestor(mine, BACKUP + "-3"))
        self.assertEqual(self.git(self.clone, "show", BACKUP + "-3:bundle.txt"), "my edit")
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(self.status(), "")
        self.assertIn("saved in the branch %s-3." % BACKUP, text)

    def test_two_updates_in_the_same_minute_make_two_backups(self):
        self.make_clone()
        self.write(self.clone, "bundle.txt", "first edit\n")
        self.run_update()
        self.write(self.clone, "bundle.txt", "second edit\n")
        text = self.run_update()
        self.assertEqual(self.backups(), [BACKUP, BACKUP + "-2"])
        self.assertEqual(self.git(self.clone, "show", BACKUP + ":bundle.txt"), "first edit")
        self.assertEqual(self.git(self.clone, "show", BACKUP + "-2:bundle.txt"), "second edit")
        self.assertIn("saved in the branch %s-2." % BACKUP, text)

    def test_all_numbers_taken_stops_before_anything_changes(self):
        self.make_clone()
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.publish("bundle.txt", "two\n", "second")
        before = self.snapshot()
        asked = []

        def every_name_exists(args):
            if args[:3] == ["rev-parse", "--verify", "-q"]:
                asked.append(args[3])
                return ok_result(args)
            return None
        with self.intercept(every_name_exists):
            with self.assertRaises(install.UpdateError) as caught:
                install.update_clone(self.clone, NOW)
        self.assertIn("not changed", str(caught.exception))
        self.assertEqual(asked[0], "refs/heads/" + BACKUP)
        self.assertEqual(asked[-1], "refs/heads/%s-99" % BACKUP)
        self.assertEqual(len(asked), 99)
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


class SavingFailureTest(GitCase):
    """Make each step of saving fail in turn: nothing the clone had may be lost."""

    FILES = {"bundle.txt": "my edit\n", "mine.txt": "mine\n", "new.txt": "new\n"}

    def setUp(self):
        super().setUp()
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.write(self.clone, "new.txt", "new\n")
        self.publish("bundle.txt", "two\n", "second")
        self.before = self.snapshot()
        self.original_head = self.head()

    def fail_step(self, is_step):
        """Run update with the one git command `is_step(args)` picks failing; return the message."""
        assert_throwaway(self.clone)
        with self.intercept(lambda args: failed_result(args) if is_step(args) else None):
            with self.assertRaises(install.UpdateError) as caught:
                install.update_clone(self.clone, NOW)
        self.assertTrue(any(is_step(args) for args, _ in self.calls), "the step never ran")
        return str(caught.exception)

    def assert_nothing_lost(self):
        branches = self.git(self.clone, "branch", "--format=%(refname:short)").split()
        self.assertTrue(any(self.is_ancestor(self.original_head, b) for b in branches),
                        "the clone's own commit is on no branch")
        backups = self.backups()
        for name, text in self.FILES.items():
            in_tree = os.path.exists(os.path.join(self.clone, name)) and \
                self.read(self.clone, name) == text
            in_backup = any(
                subprocess.run(["git", "-C", self.clone, "show", "%s:%s" % (b, name)],
                               capture_output=True, text=True).stdout == text for b in backups)
            self.assertTrue(in_tree or in_backup, "%s was lost" % name)

    def assert_untouched(self):
        self.assertEqual(self.git(self.clone, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(self.head(), self.original_head)
        self.assertEqual(self.git(self.clone, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.status(), self.before[1])
        for name, text in self.FILES.items():
            self.assertEqual(self.read(self.clone, name), text, name)
        self.assert_nothing_lost()

    def test_checkout_of_the_new_branch_fails(self):
        message = self.fail_step(lambda a: a[:2] == ["checkout", "-b"])
        self.assertIn("so the clone was not changed", message)
        self.assertIn("git checkout -b %s" % BACKUP, message)
        self.assertNotIn("Whatever was saved", message)  # no branch was made
        self.assertEqual(self.backups(), [])
        self.assert_untouched()

    def test_staging_fails(self):
        message = self.fail_step(lambda a: a == ["add", "-A"])
        self.assertIn("so the clone was not changed", message)
        self.assertIn("git add -A", message)
        self.assert_untouched()

    def test_commit_fails_and_nothing_stays_staged(self):
        message = self.fail_step(lambda a: "commit" in a)
        self.assertIn("so the clone was not changed", message)
        self.assertIn("git commit", message)
        self.assertEqual(self.git(self.clone, "status", "--porcelain", "--untracked-files=all"),
                         self.before[1])
        self.assert_untouched()

    def test_check_that_the_branch_exists_fails(self):
        # This step comes after the commit, so the clone's files are already on the backup
        # branch and are not in the working folder any more: they are not "as they were".
        message = self.fail_step(
            lambda a: a == ["rev-parse", "--verify", "refs/heads/" + BACKUP])
        self.assertIn("git rev-parse --verify", message)
        self.assertNotIn("was not changed", message)
        self.assertIn("committed to the branch %s" % BACKUP, message)
        self.assertEqual(self.git(self.clone, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(self.head(), self.original_head)
        self.assertEqual(self.git(self.clone, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.status(), "")
        self.assertEqual(self.backups(), [BACKUP])
        for name, text in self.FILES.items():
            self.assertEqual(self.git(self.clone, "show", "%s:%s" % (BACKUP, name)) + "\n", text)
        self.assert_nothing_lost()

    def test_going_back_to_the_original_branch_fails(self):
        message = self.fail_step(lambda a: a == ["checkout", "main"])
        self.assertIn("your changes are saved in the branch %s," % BACKUP, message)
        self.assertIn("going back to main failed", message)
        self.assertIn("not brought up to date", message)
        self.assertEqual(self.backups(), [BACKUP])
        self.assertEqual(self.git(self.clone, "symbolic-ref", "--short", "HEAD"), BACKUP)
        self.assertTrue(self.is_ancestor(self.original_head, BACKUP))
        self.assert_nothing_lost()

    def test_the_final_reset_fails(self):
        message = self.fail_step(lambda a: a[:2] == ["reset", "--hard"])
        self.assertIn("your changes are saved in the branch %s," % BACKUP, message)
        self.assertIn("making main match the published version failed", message)
        self.assertEqual(self.backups(), [BACKUP])
        self.assertEqual(self.git(self.clone, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertTrue(self.is_ancestor(self.original_head, BACKUP))
        self.assert_nothing_lost()


class MidOperationTest(GitCase):
    def conflicting_clone(self):
        """A clone whose own commit and a published commit change the same line."""
        self.make_clone()
        self.commit(self.clone, "bundle.txt", "local line\n", "my own")
        self.publish("bundle.txt", "upstream line\n", "second")
        self.git(self.clone, "fetch", "-q", "origin")

    def test_a_merge_left_unresolved_is_saved_and_cleared(self):
        self.conflicting_clone()
        mine = self.head()
        merged = subprocess.run(["git", "-C", self.clone] + IDENT + ["merge", "origin/main"],
                                capture_output=True, text=True)
        self.assertEqual(merged.returncode, 1, merged.stdout + merged.stderr)
        merge_head = os.path.join(self.clone, ".git", "MERGE_HEAD")
        self.assertTrue(os.path.exists(merge_head))
        self.assertIn("UU bundle.txt", self.status())
        self.run_update()
        self.assertEqual(self.head(), self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(self.read(self.clone, "bundle.txt"), "upstream line\n")
        self.assertFalse(os.path.exists(merge_head))
        self.assertEqual(self.status(), "")
        self.assertEqual(self.backups(), [BACKUP])
        self.assertTrue(self.is_ancestor(mine, BACKUP))
        saved = self.git(self.clone, "show", BACKUP + ":bundle.txt")
        self.assertIn("<<<<<<<", saved)
        self.assertIn("local line", saved)
        self.assertIn("upstream line", saved)

    def test_a_rebase_in_progress_is_refused_and_left_alone(self):
        self.conflicting_clone()
        rebased = subprocess.run(["git", "-C", self.clone] + IDENT + ["rebase", "origin/main"],
                                 capture_output=True, text=True)
        self.assertEqual(rebased.returncode, 1, rebased.stdout + rebased.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.clone, ".git", "rebase-merge")))
        before = (self.snapshot(), self.read(self.clone, "bundle.txt"),
                  sorted(os.listdir(os.path.join(self.clone, ".git"))))
        with self.assertRaises(install.SetupError) as caught:
            self.run_update()
        self.assertEqual(str(caught.exception), (
            "a rebase is half-finished in this clone; finish it or run `git rebase --abort`, "
            "then run update again"))
        after = (self.snapshot(), self.read(self.clone, "bundle.txt"),
                 sorted(os.listdir(os.path.join(self.clone, ".git"))))
        self.assertEqual(after, before)
        self.assertEqual(self.backups(), [])


class OwnChangesNoteTest(GitCase):
    NOTE = ("Note: this clone has changes of its own (%s). Run `python3 install.py update` to "
            "save them to a backup branch and match the bundle, before the next upgrade.")

    def note(self, path=None):
        path = path or self.clone
        assert_throwaway(path)
        return install.own_changes_note(path)

    def test_clean_clone_says_nothing(self):
        self.make_clone()
        self.assertIsNone(self.note())

    def test_behind_only_says_nothing(self):
        self.make_clone()
        self.publish("bundle.txt", "two\n", "second")
        self.git(self.clone, "fetch", "-q", "origin")
        self.assertIsNone(self.note())

    def test_commits_ahead_only(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.assertEqual(self.note(), self.NOTE % "1 commit")

    def test_dirty_files_only(self):
        self.make_clone()
        self.write(self.clone, "bundle.txt", "my edit\n")
        os.makedirs(os.path.join(self.clone, "sub"))
        self.write(self.clone, "sub/a.txt", "a\n")
        self.write(self.clone, "sub/b.txt", "b\n")
        self.assertEqual(self.note(), self.NOTE % "3 edited or new files")

    def test_commits_and_dirty_files(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.commit(self.clone, "mine2.txt", "mine\n", "my own again")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assertEqual(self.note(), self.NOTE % "2 commits and 1 edited or new file")

    def test_uses_the_same_wording_as_update(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.write(self.clone, "bundle.txt", "my edit\n")
        note = self.note()
        report = self.run_update()
        what = note[len("Note: this clone has changes of its own ("):note.index("). Run")]
        self.assertIn("Your clone had changes of its own (%s)." % what, report)

    def test_no_upstream_says_nothing(self):
        self.make_clone()
        self.git(self.clone, "checkout", "-q", "-b", "side")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assertIsNone(self.note())

    def test_detached_head_says_nothing(self):
        self.make_clone()
        self.git(self.clone, "checkout", "-q", "--detach")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assertIsNone(self.note())

    def test_not_a_clone_says_nothing(self):
        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        self.write(plain, "install.py", "x\n")
        self.assertIsNone(self.note(plain))

    def test_a_folder_inside_a_clone_says_nothing(self):
        self.make_clone()
        inner = os.path.join(self.clone, "inner")
        os.makedirs(inner)
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assertIsNone(self.note(inner))

    def test_a_folder_that_does_not_exist_says_nothing(self):
        self.assertIsNone(self.note(os.path.join(self.root, "nowhere")))

    def test_git_missing_says_nothing(self):
        self.make_clone()
        self.write(self.clone, "bundle.txt", "my edit\n")
        with mock.patch.object(install.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertIsNone(self.note())

    def test_any_git_call_failing_says_nothing(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.write(self.clone, "bundle.txt", "my edit\n")
        self.assertIsNotNone(self.note())
        for step in ("symbolic-ref", "rev-list", "status"):
            with self.intercept(lambda a: failed_result(a) if step in a else None):
                self.assertIsNone(self.note(), step)
            self.assertTrue(any(step in args for args, _ in self.calls), step)

    def test_uses_short_timeouts_and_never_fetches(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        with self.intercept(lambda args: None):
            self.assertIsNotNone(self.note())
        self.assertTrue(self.calls)
        for args, kw in self.calls:
            self.assertLessEqual(kw.get("timeout", 30), 10, args)
            self.assertNotIn(args[0], ("fetch", "pull", "remote", "ls-remote"), args)

    def test_writes_nothing_and_does_not_update_the_remote_reference(self):
        self.make_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        self.publish("bundle.txt", "two\n", "second")  # the clone has not fetched this
        remote_ref = self.git(self.clone, "rev-parse", "origin/main")
        index = os.path.join(self.clone, ".git", "index")
        with open(index, "rb") as f:
            index_before = f.read()
        # a newer timestamp on an unchanged file is what makes `git status` rewrite the index
        os.utime(os.path.join(self.clone, "bundle.txt"), (1, 1))
        self.assertIsNotNone(self.note())
        with open(index, "rb") as f:
            self.assertEqual(f.read(), index_before)
        self.assertEqual(self.git(self.clone, "rev-parse", "origin/main"), remote_ref)


class NoteThroughTheCommandTest(GitCase):
    """The plain install prints the note as its last line; it needs the whole bundle in a clone."""

    NOTE = OwnChangesNoteTest.NOTE

    def make_bundle_clone(self):
        shutil.copy(INSTALL, os.path.join(self.seed, "install.py"))
        for name in ("manifest.json", "rule-changes.json"):
            shutil.copy(os.path.join(REPO, name), self.seed)
        shutil.copytree(os.path.join(REPO, "payload"), os.path.join(self.seed, "payload"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.git(self.seed, "add", "-A")
        self.git(self.seed, *IDENT, "commit", "-q", "-m", "bundle")
        self.git(self.seed, "push", "-q", "origin", "main")
        self.git(self.root, "clone", "-q", self.origin, self.clone)

    def dry_run(self):
        assert_throwaway(self.clone)
        target = os.path.join(self.root, "target")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, os.path.join(self.clone, "install.py"),
                               "--dry-run", "--target", target],
                              capture_output=True, text=True, env=env, cwd=self.root)

    def test_last_line_is_the_note_when_the_clone_has_a_commit_of_its_own(self):
        self.make_bundle_clone()
        self.commit(self.clone, "mine.txt", "mine\n", "my own")
        r = self.dry_run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.endswith("\n" + self.NOTE % "1 commit" + "\n"), r.stdout)
        self.assertEqual(r.stdout.count("Note:"), 1)

    def test_no_note_when_the_clone_is_clean(self):
        self.make_bundle_clone()
        r = self.dry_run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Note:", r.stdout)
        self.assertEqual(self.status(), "")


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
