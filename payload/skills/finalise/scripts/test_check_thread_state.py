#!/usr/bin/env python3
"""Tests for check_thread_state.py.

Pure-function fixtures only -- no git, no file reads. Project rule: a script
that grows a repo-data read silently turns its existing tests into live-data
tests, so every case here feeds pre-built text/Commit fixtures straight into
the pure functions and never touches run_git_log/read_memory_texts/main.

One exception: TestCountCommitsSince mocks subprocess.run to assert on the
constructed `git log` argv rather than running real git. That's deliberate,
not a slip -- the bug it regression-tests (a bare '--since=<date>' silently
borrows time-of-day from the CURRENT clock) only reproduces at certain times
of day against a real repo, so asserting on real git's live output here would
make the test's pass/fail depend on the wall clock the suite happens to run
at. The observable bug lived in the exact string built for --since, so that's
the layer this asserts at. Still git-free: no subprocess is ever spawned.

build_report (backlog #32, 2026-08-09) takes a did_modify_entry(commit_hash,
task_no) -> bool callable. Every test below supplies a plain lambda/function
fixture -- never the real git-backed make_did_modify_entry -- so build_report
stays exercised git-free here too; make_did_modify_entry/_git_show's real
git-diffing behaviour is verified separately, live, against this repo's real
history (see the checkpoint 2 report, not this file).
"""
import os
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import check_thread_state as cts

Commit = cts.Commit


BACKLOG_FIXTURE = """\
## Open

### #2 — Some open thread

Some open work, no blocker mentioned here.

### #9 — Another open thread

Blocked by #2 until the pilot ships.

## Not backlog — do not resurface

Prose mentioning #5, but no header or bullet marks it as a real task.

## Closed

- 2026-08-08 · **#1** something shipped (`abc123`) -> decisions.md
- 2026-07-21 · #25 a bare (non-bold) closed stub, same shape as the real file
- 2026-08-08 · no task number in this bullet at all

## Records

Nothing task-shaped here.
"""


class TestParseBacklogSections(unittest.TestCase):
    def test_open_closed_not_backlog(self):
        sections = cts.parse_backlog_sections(BACKLOG_FIXTURE)
        self.assertEqual(sections[2], "Open")
        self.assertEqual(sections[9], "Open")
        self.assertEqual(sections[1], "Closed")
        # A bare digit mentioned in "Not backlog" prose (#5) is not a task
        # marker (no ### header, no closed-bullet marker) and must not appear.
        self.assertNotIn(5, sections)

    def test_bare_closed_bullet_without_bold_is_parsed(self):
        # Regression for the real 2026-08-09 miss: #25/#30/#31 use the BARE
        # '· #N' shape, not '· **#N**' -- both must resolve to Closed.
        sections = cts.parse_backlog_sections(BACKLOG_FIXTURE)
        self.assertEqual(sections[25], "Closed")

    def test_only_real_markers_produce_entries(self):
        sections = cts.parse_backlog_sections(BACKLOG_FIXTURE)
        self.assertEqual(set(sections), {1, 2, 9, 25})


class TestParseTaskBodies(unittest.TestCase):
    def test_bodies_scoped_to_own_header(self):
        bodies = cts.parse_task_bodies(BACKLOG_FIXTURE)
        self.assertIn("no blocker mentioned", bodies[2])
        self.assertNotIn("Blocked by #2", bodies[2])
        self.assertIn("Blocked by #2", bodies[9])


class TestFindDeclaredBlockers(unittest.TestCase):
    def test_blocked_by_detected_and_scoped_to_the_right_task(self):
        sections = cts.parse_backlog_sections(BACKLOG_FIXTURE)
        bodies = cts.parse_task_bodies(BACKLOG_FIXTURE)
        blockers = cts.find_declared_blockers(bodies, sections)
        # #9 declares the blocker; #2 (which #9's text merely mentions) must
        # NOT also show up as blocked -- this is what would have surfaced
        # backlog #9 in the real 2026-08-09 case.
        self.assertEqual(blockers, [(9, "Open", 2, "Open")])


class TestExtractTaskRefs(unittest.TestCase):
    """Section 1 (commit refs) intentionally stays permissive on bare '#N' --
    real commit messages use it constantly ('backlog #2, re-scoped...'). Only
    section 4 (memory citations, see TestFindTaskCollisions) is narrowed."""

    def test_hash_task_and_plural_forms(self):
        commits = [
            Commit("h1", "2026-08-01", "fix: reference #2", "", ["a.py"]),
            Commit("h2", "2026-08-02", "chore: bump", "task 12 needs a look",
                   ["b.py"]),
            Commit("h3", "2026-08-03", "docs: cleanup",
                   "handles tasks 2 and 9 together", ["c.py"]),
        ]
        refs = cts.extract_task_refs(commits)
        self.assertEqual({c.hash for c in refs[2]}, {"h1", "h3"})
        self.assertEqual({c.hash for c in refs[12]}, {"h2"})
        self.assertEqual({c.hash for c in refs[9]}, {"h3"})

    def test_claude_session_trailer_produces_no_false_ref(self):
        trailer_only = Commit(
            "h4", "2026-08-04", "misc: trailer only",
            "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n"
            "Claude-Session: "
            "https://example.invalid/session_00000000000000000000000000",
            [],
        )
        refs = cts.extract_task_refs([trailer_only])
        self.assertEqual(refs, {})


class TestTouchedBacklogFlag(unittest.TestCase):
    """Fixture-based stand-in for a real acceptance scenario: a task
    referenced by a commit that never touches backlog.md at all, which real
    live history moves past too quickly to keep reproducible on demand.

    did_modify_entry is a plain lambda in every case here -- see the module
    docstring."""

    def test_sole_ref_without_backlog_touch_is_flagged(self):
        commits = [
            Commit("aaaa", "2026-08-09",
                   "store-a: answer probes from the collection catalogue",
                   "backlog #2, re-scoped to store-a only.",
                   ["widget_probe.py", "test_widget_probe.py"]),
        ]
        # No commit here touches backlog.md at all, so did_modify_entry is
        # never even called for this fixture -- its return value is moot.
        report = cts.build_report(BACKLOG_FIXTURE, commits, {},
                                   lambda h, n: False)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["outstanding_commits"], [("aaaa", "2026-08-09")])
        self.assertEqual(row["reconciled_commits"], [])
        self.assertIsNone(row["reconciled_by"])

    def test_clean_when_sole_ref_touches_backlog_and_modifies_the_entry(self):
        commits = [
            Commit("bbbb", "2026-08-10", "backlog: update task 2",
                   "task 2's box updated for the shipped pilot.",
                   ["backlog.md"]),
        ]
        report = cts.build_report(BACKLOG_FIXTURE, commits, {},
                                   lambda h, n: True)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["outstanding_commits"], [])
        self.assertEqual(row["reconciled_commits"], [])
        self.assertTrue(row["most_recent_touched_backlog"])
        self.assertEqual(row["reconciled_by"], "bbbb")

    def test_most_recent_commit_hash_is_index_zero_not_last(self):
        # Newest-first input order (git log's default): "most recent" display
        # fields must reflect index 0, not whichever element happens to touch
        # backlog.md.
        newer = Commit("new1", "2026-08-09", "x", "references #2", ["x.py"])
        older = Commit("old1", "2026-08-01", "y", "references #2",
                        ["backlog.md"])
        report = cts.build_report(BACKLOG_FIXTURE, [newer, older], {},
                                   lambda h, n: False)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["commit_hash"], "new1")

    def test_an_earlier_miss_is_not_masked_by_a_later_touch(self):
        # The exact defect found in review, and its later revision: a
        # later commit that TOUCHES backlog.md but does NOT modify #2's own
        # entry (it only adds an unrelated task's section) must
        # not become a reconciler and must not mask an earlier commit that
        # referenced #2 without touching the file at all. Under the rejected
        # "touching the file is enough" rule this would have shown clean;
        # under the rejected "did_modify_entry always True" cheap rule it
        # would ALSO show clean (the touch would wrongly reconcile). Only the
        # correct three-condition rule surfaces the earlier miss here.
        commit_a_older_no_touch = Commit(
            "aaaa", "2026-08-01", "a: mentions #2 in passing",
            "touches on #2 but not the backlog entry", ["widget_probe.py"])
        commit_b_newer_touch_no_modify = Commit(
            "bbbb", "2026-08-05", "backlog: unrelated #2 mention",
            "housekeeping; also references #2", ["backlog.md"])
        # newest-first order, as git log provides it. Nothing in this
        # fixture ever modified #2's entry.
        report = cts.build_report(
            BACKLOG_FIXTURE,
            [commit_b_newer_touch_no_modify, commit_a_older_no_touch],
            {}, lambda h, n: False)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        # The most-recent commit alone looks clean (it touched the file)...
        self.assertTrue(row["most_recent_touched_backlog"])
        # ...but since it did not modify #2's own entry, it is not a
        # reconciler, and the earlier miss must still surface as outstanding.
        self.assertEqual(row["outstanding_commits"], [("aaaa", "2026-08-01")])
        self.assertEqual(row["reconciled_commits"], [])
        self.assertIsNone(row["reconciled_by"])


class TestReconciliationPartition(unittest.TestCase):
    """The newest commit that both touches backlog.md AND
    modifies THIS task's own entry (per an injected did_modify_entry fixture)
    becomes the reconciler; non-touching commits split into outstanding
    (newer than it) and reconciled (older than it), collapsed to one summary
    line each."""

    def test_no_reconciler_every_non_touching_commit_is_outstanding(self):
        # Nothing touches backlog.md at all -- today's (pre-#32) behaviour,
        # unchanged.
        c2 = Commit("c2", "2026-08-09", "x", "references #2", ["a.py"])
        c1 = Commit("c1", "2026-08-05", "y", "references #2", ["b.py"])
        report = cts.build_report(BACKLOG_FIXTURE, [c2, c1], {},
                                   lambda h, n: False)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["outstanding_commits"],
                          [("c2", "2026-08-09"), ("c1", "2026-08-05")])
        self.assertEqual(row["reconciled_commits"], [])
        self.assertIsNone(row["reconciled_by"])

    def test_reconciler_present_partitions_older_reconciled_newer_outstanding(self):
        # newest-first: c5 (no touch) / c4 (touch+modify, the reconciler) /
        # c3 (no touch) / c2 (touch, does NOT modify -- must be skipped, not
        # counted either way) / c1 (no touch, oldest).
        c5 = Commit("c5555", "2026-08-09", "c5", "mentions #2", ["x.py"])
        c4 = Commit("c4444", "2026-08-08", "c4", "mentions #2", ["backlog.md"])
        c3 = Commit("c3333", "2026-08-07", "c3", "mentions #2", ["y.py"])
        c2 = Commit("c2222", "2026-08-06", "c2", "mentions #2", ["backlog.md"])
        c1 = Commit("c1111", "2026-08-05", "c1", "mentions #2", ["z.py"])

        def did_modify_entry(commit_hash, task_no):
            return commit_hash == "c4444" and task_no == 2

        report = cts.build_report(BACKLOG_FIXTURE, [c5, c4, c3, c2, c1], {},
                                   did_modify_entry)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["reconciled_by"], "c4444")
        self.assertEqual(row["outstanding_commits"], [("c5555", "2026-08-09")])
        self.assertEqual(row["reconciled_commits"],
                          [("c3333", "2026-08-07"), ("c1111", "2026-08-05")])

    def test_multiple_modifying_touches_the_newest_wins(self):
        c3 = Commit("newest3", "2026-08-09", "c3", "mentions #2",
                    ["backlog.md"])
        c2 = Commit("mid2", "2026-08-08", "c2", "mentions #2", ["backlog.md"])
        c1 = Commit("old1", "2026-08-07", "c1", "mentions #2", ["backlog.md"])
        report = cts.build_report(BACKLOG_FIXTURE, [c3, c2, c1], {},
                                   lambda h, n: True)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["reconciled_by"], "newest3")
        self.assertEqual(row["outstanding_commits"], [])
        self.assertEqual(row["reconciled_commits"], [])

    def test_non_modifying_touch_falls_through_to_the_older_reconciler(self):
        # A five-commit scenario exercising the full partition logic at once:
        # touch_other_section touches backlog.md and mentions both #2 and
        # #13 but only adds a new, third task's section -- it must not
        # become #2's reconciler. reconciler, older, DID modify #2's entry
        # (recorded the shipped store-a pilot) and is the true reconciler.
        # touch_unrelated_file_a and touch_unrelated_file_b, in between,
        # never touch backlog.md at all and must stay outstanding.
        # reference_only, older than the reconciler, must be reconciled.
        touch_other_section = Commit(
            "eeee1111eeee1111eeee1111eeee1111eeee1111", "2026-08-09",
            "backlog: add a new task, reconciled-reference noise",
            "mentions task 2 and task 13 while only adding the new section",
            ["backlog.md"])
        touch_unrelated_file_a = Commit(
            "ffff2222ffff2222ffff2222ffff2222ffff2222", "2026-08-09",
            "finalise: wire in the thread-state check",
            "tasks 2 and 9 untouched", [".claude/skills/finalise/SKILL.md"])
        touch_unrelated_file_b = Commit(
            "1234abcd1234abcd1234abcd1234abcd1234abcd", "2026-08-09",
            "finalise: add check_thread_state.py",
            "task 2 now surfaces an older commit as a non-touching reference",
            ["check_thread_state.py"])
        reconciler = Commit(
            "5678ef005678ef005678ef005678ef005678ef00", "2026-08-09",
            "backlog: update tasks 2 and 9 for the shipped store-a pilot",
            "Task 2: the store-a arm shipped; what remains is a scoping "
            "decision", ["backlog.md"])
        reference_only = Commit(
            "9abc9abc9abc9abc9abc9abc9abc9abc9abc9abc", "2026-08-09",
            "store-a: answer probes from the collection catalogue",
            "backlog #2, re-scoped to store-a only", ["some_module.py"])

        def did_modify_entry(commit_hash, task_no):
            return commit_hash == reconciler.hash

        report = cts.build_report(
            BACKLOG_FIXTURE,
            [touch_other_section, touch_unrelated_file_a, touch_unrelated_file_b,
             reconciler, reference_only],
            {}, did_modify_entry)
        row = next(r for r in report["task_refs"] if r["number"] == 2)

        self.assertEqual(row["reconciled_by"], reconciler.hash)
        self.assertEqual(
            row["outstanding_commits"],
            [(touch_unrelated_file_a.hash, "2026-08-09"),
             (touch_unrelated_file_b.hash, "2026-08-09")])
        self.assertEqual(row["reconciled_commits"],
                          [(reference_only.hash, "2026-08-09")])

    def test_touching_commit_for_a_different_task_never_reconciles_this_one(self):
        # Regression for a task-masking hazard: a commit that touches
        # backlog.md while working on #3 must never be considered for #2's
        # reconciliation. extract_task_refs only attaches a commit to a
        # task's list if the commit actually mentions that task, so this
        # commit can't even reach #2's commits_for_task -- proven here by
        # setting did_modify_entry to ALWAYS True, which would reconcile #2
        # if the masking hazard existed.
        ref_only_commit = Commit("aaaa", "2026-08-01", "x: mentions #2 only",
                                  "references #2 in passing", ["widget_probe.py"])
        other_task_touch = Commit(
            "bbbb", "2026-08-03", "decisions/backlog: cite commits, not tags",
            "touches backlog.md for task 3 only", ["backlog.md"])
        report = cts.build_report(
            BACKLOG_FIXTURE, [other_task_touch, ref_only_commit], {},
            lambda h, n: True)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertIsNone(row["reconciled_by"])
        self.assertEqual(row["outstanding_commits"], [("aaaa", "2026-08-01")])
        self.assertEqual(row["reconciled_commits"], [])

    def test_only_touching_commits_nothing_outstanding_nothing_reconciled(self):
        c2 = Commit("newest", "2026-08-09", "backlog: #2 note", "...",
                    ["backlog.md"])
        c1 = Commit("older", "2026-08-08", "backlog: #2 note too", "...",
                    ["backlog.md"])
        report = cts.build_report(BACKLOG_FIXTURE, [c2, c1], {},
                                   lambda h, n: False)
        row = next(r for r in report["task_refs"] if r["number"] == 2)
        self.assertEqual(row["outstanding_commits"], [])
        self.assertEqual(row["reconciled_commits"], [])


class TestFindTaskCollisions(unittest.TestCase):
    """find_task_collisions now takes the full {task_no: section} dict (not
    just the bare numbers) and returns (live_hits, closed_hits) -- see the
    module docstring's section-4 note. live_hits is the real hazard (current
    section is not Closed); closed_hits is expected (resolves to a Closed
    stub, e.g. a citation to a task that's since closed)."""

    def test_task_hash_citation_on_an_open_task_flags_in_live_bucket(self):
        # Coordinator's exact acceptance case: backlog defines #12 as Open, a
        # memory cites "task #12" under the retired scheme -> must flag LIVE.
        sections = {1: "Open", 2: "Open", 9: "Open", 12: "Open"}
        memory_texts = {
            "some-old-memory.md":
                "This references task #12 under the old scheme.",
        }
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [(12, ["some-old-memory.md"])])
        self.assertEqual(closed, [])

    def test_task_hash_citation_on_a_closed_task_lands_in_expected_bucket(self):
        # A citation to a task that has since closed is
        # expected, not a hazard, and must NOT land in the live bucket.
        sections = {26: "Closed"}
        memory_texts = {
            "some-other-memory.md":
                "**UPDATE (thread #26):** issue fixed.",
        }
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [])
        self.assertEqual(closed, [(26, ["some-other-memory.md"])])

    def test_thread_hash_citation_also_flags(self):
        sections = {12: "Open"}
        memory_texts = {"m.md": "see thread #12 for the shipping-data work"}
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [(12, ["m.md"])])
        self.assertEqual(closed, [])

    def test_original_citation_shape_flags(self):
        # Approximates the real, now-overwritten original wording (a task
        # citation next to a retired-memory wikilink).
        sections = {12: "Open"}
        memory_texts = {
            "some-topic.md":
                "This came out of the 2026-06 shipping-data worksheet "
                "thread -- see [[project-status-open-threads]] task #12.",
        }
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [(12, ["some-topic.md"])])
        self.assertEqual(closed, [])

    def test_remediation_note_about_a_dropped_citation_does_not_flag(self):
        # The real 2026-08-09 case (verbatim wording): the note EXPLAINS that
        # a "#12" citation was removed. It still contains the bare digits
        # "#12" twice, but neither is adjacent to "task"/"thread", so this
        # must NOT flag -- a bare number match here is the defect that was
        # found in review (it flagged its own fix, forever, since the note
        # never goes away).
        sections = {12: "Open"}
        memory_texts = {
            "some-topic.md":
                '(Task number deliberately dropped 2026-08-09: it cited '
                '"#12" under a retired numbering scheme, and '
                'backlog.md now has a *different* live #12 -- the '
                'citation resolved to the wrong task.)',
        }
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [])
        self.assertEqual(closed, [])

    def test_no_collision_when_memory_cites_a_non_backlog_number(self):
        sections = {1: "Open", 2: "Open", 9: "Open"}
        memory_texts = {"unrelated.md": "See task #999 for context."}
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [])
        self.assertEqual(closed, [])

    def test_number_with_no_stub_never_collides(self):
        # The real #22 shape: no '### #N' header, no Closed bullet -- #22 is
        # simply not a key of `sections`. A memory citation of "task #22"
        # must produce NO hit at all (not live, not closed): there is no live
        # task in backlog.md for the citation to collide with.
        sections = {1: "Open", 30: "Closed", 31: "Closed"}
        memory_texts = {
            "feedback-unavailable-means-no-preorder-either.md":
                "the automated rule (built the same day, see task #22) only "
                "checked elapsed time",
        }
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [])
        self.assertEqual(closed, [])

    def test_present_but_unresolved_section_is_bucketed_live_not_closed(self):
        # Defensive case: a key IS present in `sections` but maps to None (a
        # task header appearing before any '## ' heading -- not reachable
        # from today's real, well-formed backlog.md, but a real code path in
        # parse_backlog_sections). Unconfirmed must be treated as unsafe, so
        # this lands in live_hits, not closed_hits.
        sections = {12: None}
        memory_texts = {"m.md": "see task #12 for the old thread"}
        live, closed = cts.find_task_collisions(sections, memory_texts)
        self.assertEqual(live, [(12, ["m.md"])])
        self.assertEqual(closed, [])


class TestCountCommitsSince(unittest.TestCase):
    def test_since_arg_is_pinned_to_midnight_not_left_bare(self):
        # The bug (found running the checker live, 2026-08-09): a bare
        # '--since=2026-08-09' has git's approxidate fill the missing
        # time-of-day from the CURRENT clock, not midnight -- demonstrated in
        # this repo the same day: '--since=2026-08-09' returned 0 commits,
        # '--since=2026-08-09T00:00:00' returned 16, run back to back. The
        # fix pins the time to midnight. Captured argv, not a real git call.
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return types.SimpleNamespace(stdout="")

        with mock.patch.object(cts.subprocess, "run", side_effect=fake_run):
            cts.count_commits_since("/some/repo", "2026-08-09")

        since_args = [a for a in captured["cmd"] if a.startswith("--since=")]
        self.assertEqual(since_args, ["--since=2026-08-09T00:00:00"])


class TestAbsenceGuards(unittest.TestCase):
    """Absence guards: this script promises it reports and never gates (exit 0 always), so a
    missing backlog, repo, commit history or memory directory must not raise.

    These are the only tests in this file that touch the filesystem or invoke git, and only
    because the guards themselves are filesystem/git predicates -- there is no pure-function
    layer at which "this directory is not a repo" can be asserted. They stay hermetic by
    building their own tmpdir and never reading repo data. read_memory_texts's absence path is
    pure enough to test directly.
    """

    def test_read_memory_texts_returns_empty_dict_for_a_missing_dir(self):
        with tempfile.TemporaryDirectory() as parent:
            missing = os.path.join(parent, "no-such-memory-dir")
            self.assertEqual(cts.read_memory_texts(missing), {})

    def test_read_memory_texts_still_reads_a_populated_dir(self):
        # Bounding case: the guard must not swallow a directory that IS present.
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "a.md"), "w", encoding="utf-8") as f:
                f.write("cites task #12 here\n")
            with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write("# index\n")
            texts = cts.read_memory_texts(tmpdir)
            self.assertEqual(set(texts), {"a.md"})  # MEMORY.md itself is excluded
            self.assertIn("task #12", texts["a.md"])

    def test_is_git_repo_false_for_a_plain_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(cts.is_git_repo(tmpdir))

    def test_has_commits_false_for_a_freshly_initialised_repo(self):
        # The state /bootstrap-project actually leaves behind: initialised, files written,
        # nothing committed (step 8 asks before committing). is_git_repo says True here -- see
        # the pairing test below -- so this predicate is what stops `git log` being called.
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init", "-q"], cwd=tmpdir, check=True,
                            capture_output=True)
            self.assertFalse(cts.has_commits(tmpdir))

    def test_has_commits_true_once_a_commit_exists(self):
        # Load-bearing in the other direction: a predicate hard-coded to False would pass the
        # test above and fail this one, and would silently disable the whole check on every
        # real repo.
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init", "-q"], cwd=tmpdir, check=True,
                            capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@e.st"], cwd=tmpdir,
                            check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "T"], cwd=tmpdir,
                            check=True, capture_output=True)
            # A global commit.gpgsign would otherwise make this throwaway commit try to sign.
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmpdir,
                            check=True, capture_output=True)
            with open(os.path.join(tmpdir, "f.txt"), "w", encoding="utf-8") as f:
                f.write("x\n")
            subprocess.run(["git", "add", "f.txt"], cwd=tmpdir, check=True,
                            capture_output=True)
            subprocess.run(["git", "commit", "-qm", "first"], cwd=tmpdir, check=True,
                            capture_output=True)
            self.assertTrue(cts.has_commits(tmpdir))

    def test_a_commitless_repo_is_still_a_repo(self):
        # Why has_commits must exist SEPARATELY from is_git_repo, asserted rather than left as
        # a comment: the two predicates disagree on exactly this state, and checking only
        # is_git_repo would let `git log` run, and raise, in a repo with no commits. If someone
        # later "simplifies" by folding one into the other, this fails.
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init", "-q"], cwd=tmpdir, check=True,
                            capture_output=True)
            self.assertTrue(cts.is_git_repo(tmpdir))
            self.assertFalse(cts.has_commits(tmpdir))

    def test_is_git_repo_true_for_a_real_repo(self):
        # Proves the predicate is load-bearing in BOTH directions -- a function hard-coded to
        # return False would pass the test above and fail this one.
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init", "-q"], cwd=tmpdir, check=True,
                            capture_output=True)
            self.assertTrue(cts.is_git_repo(tmpdir))


class TestNextUpBasis(unittest.TestCase):
    BLOCK = ("## Next up — recommended 2026-09-25\n\n"
             "Snapshot. Basis: commits through `c0ffee1`; Open threads as of 2026-09-25.\n\n"
             "1. **#1**: something.\n\n---\n\n")
    REST = "# Backlog\n\nintro\n\n"
    OPEN = "## Open\n\n### #1 — a task\n\nbody\n"

    def _backlog(self, block=None, open_=None):
        return self.REST + (self.BLOCK if block is None else block) + (open_ or self.OPEN)

    def test_basis_hash_found(self):
        self.assertEqual(cts.find_next_up_basis(self._backlog()), "c0ffee1")

    def test_template_placeholder_is_no_basis(self):
        block = self.BLOCK.replace("`c0ffee1`", "`<none yet>`")
        self.assertIsNone(cts.find_next_up_basis(self._backlog(block)))

    def test_basis_line_outside_the_block_is_ignored(self):
        open_ = self.OPEN + "\nBasis: commits through `abcdef0` quoted in a task body.\n"
        block = self.BLOCK.replace("Basis: commits through `c0ffee1`; ", "")
        self.assertIsNone(cts.find_next_up_basis(self._backlog(block, open_)))

    def test_no_block_is_no_basis(self):
        # A basis-shaped line elsewhere in the file must not stand in for a missing block.
        text = self.REST + self.OPEN + "\nBasis: commits through `abcdef0` in a task body.\n"
        self.assertIsNone(cts.find_next_up_basis(text))

    def test_block_ends_at_the_next_heading(self):
        block, rest = cts.split_next_up(self._backlog())
        self.assertTrue(block.startswith("## Next up"))
        self.assertNotIn("## Open", block)
        self.assertEqual(rest, self.REST + self.OPEN)

    def test_pure_block_rewrite_is_skipped(self):
        new = self._backlog(self.BLOCK.replace("c0ffee1", "1234abc").replace("#1", "#2"))
        self.assertTrue(cts.is_next_up_only_rewrite(["backlog.md"], self._backlog(), new))

    def test_rewrite_plus_a_change_outside_the_block_counts(self):
        new = self._backlog(self.BLOCK.replace("c0ffee1", "1234abc"),
                            self.OPEN.replace("body", "body, now closed"))
        self.assertFalse(cts.is_next_up_only_rewrite(["backlog.md"], self._backlog(), new))

    def test_rewrite_plus_another_file_counts(self):
        new = self._backlog(self.BLOCK.replace("c0ffee1", "1234abc"))
        self.assertFalse(cts.is_next_up_only_rewrite(
            ["backlog.md", "decisions.md"], self._backlog(), new))

    def test_change_outside_an_unchanged_block_counts(self):
        new = self._backlog(open_=self.OPEN.replace("body", "other body"))
        self.assertFalse(cts.is_next_up_only_rewrite(["backlog.md"], self._backlog(), new))

    def test_backlog_absent_before_counts(self):
        self.assertFalse(cts.is_next_up_only_rewrite(["backlog.md"], None, self._backlog()))


class TestNextUpStalenessLive(unittest.TestCase):
    """Section 3 end to end against a throwaway git repo, since the count is git-derived.
    Hermetic: builds its own tmpdir repo and never reads this project's history."""

    def _git(self, repo, *args):
        # Identity and signing are pinned so the user's global git config can't reach in: a
        # global commit.gpgsign makes every throwaway commit try to sign, and fail unattended.
        return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@e.st",
                               "-c", "commit.gpgsign=false", *args],
                              cwd=repo, check=True, capture_output=True, text=True).stdout.strip()

    def _commit(self, repo, files, msg):
        for name, text in files.items():
            with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
                f.write(text)
        self._git(repo, "add", *files)
        self._git(repo, "commit", "-qm", msg)
        return self._git(repo, "rev-parse", "--short", "HEAD")

    def _backlog(self, basis, open_body="body"):
        return ("# Backlog\n\n## Next up — recommended 2026-09-25\n\n"
                f"Basis: commits through `{basis}`.\n\n---\n\n"
                f"## Open\n\n### #1 — a task\n\n{open_body}\n")

    def test_same_day_block_reads_zero(self):
        # The #8 case: work committed earlier the same day, then the block written naming
        # the latest commit as its basis. Counting from midnight reported those earlier
        # commits as landing after the block; the true figure is 0.
        with tempfile.TemporaryDirectory() as repo:
            self._git(repo, "init", "-q")
            self._commit(repo, {"backlog.md": self._backlog("<none yet>")}, "bootstrap")
            self._commit(repo, {"a.txt": "1\n"}, "earlier work")
            basis = self._commit(repo, {"a.txt": "2\n"}, "more earlier work")
            self._commit(repo, {"backlog.md": self._backlog(basis)}, "write Next up")
            line = cts.next_up_staleness(repo, self._backlog(basis))
            self.assertIn(f"basis `{basis}`; 0 commit(s) since", line)
            self.assertIn("not counting 1 that only rewrote the block", line)

    def test_real_work_after_the_block_is_counted(self):
        with tempfile.TemporaryDirectory() as repo:
            self._git(repo, "init", "-q")
            self._commit(repo, {"backlog.md": self._backlog("<none yet>")}, "bootstrap")
            basis = self._commit(repo, {"a.txt": "1\n"}, "work")
            self._commit(repo, {"backlog.md": self._backlog(basis)}, "write Next up")
            self._commit(repo, {"a.txt": "2\n"}, "later work")
            self._commit(repo, {"backlog.md": self._backlog(basis, "closed")}, "close #1")
            line = cts.next_up_staleness(repo, self._backlog(basis, "closed"))
            self.assertIn("; 2 commit(s) since", line)

    def test_unknown_basis_falls_back_to_the_date(self):
        with tempfile.TemporaryDirectory() as repo:
            self._git(repo, "init", "-q")
            self._commit(repo, {"a.txt": "1\n"}, "work")
            line = cts.next_up_staleness(repo, self._backlog("deadbee"))
            self.assertIn("basis `deadbee` is not in this repo's history", line)
            self.assertIn("counting from midnight", line)

    def test_placeholder_basis_falls_back_to_the_date(self):
        with tempfile.TemporaryDirectory() as repo:
            self._git(repo, "init", "-q")
            self._commit(repo, {"a.txt": "1\n"}, "work")
            line = cts.next_up_staleness(repo, self._backlog("<none yet>"))
            self.assertIn("the basis line names no commit", line)


class TestFindNextUpDate(unittest.TestCase):
    def test_date_parsed(self):
        text = "## Next up — recommended 2026-08-09\n\nsome content\n"
        self.assertEqual(cts.find_next_up_date(text), "2026-08-09")

    def test_absent_returns_none(self):
        self.assertIsNone(cts.find_next_up_date(BACKLOG_FIXTURE))


if __name__ == "__main__":
    unittest.main()

