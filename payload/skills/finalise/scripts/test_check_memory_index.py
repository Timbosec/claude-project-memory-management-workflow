#!/usr/bin/env python3
"""Tests for check_memory_index.py's dangling-[[link]] check (backlog task #13
checkpoint 3, 2026-08-09).

check_memory_index.py is a top-level script, not an importable module -- it reads
sys.argv[1] and acts at import time, no `if __name__ == "__main__":` guard. So these
tests build a tmpdir fixture and invoke it via subprocess, per the plan and the
coordinator's brief. That keeps this offline and independent of the real, mutable
memory directory: a test that read the real directory live would drift as memory
files churn, and the Stop hook runs this suite every turn-end.

Only the NEW dangling-[[link]] check is exercised here. The two pre-existing checks
(index-sync, load-limits) are exercised only incidentally -- every fixture below must
satisfy both to reach the link check at all, which is itself asserted directly by
test_dangling_link_check_does_not_run_when_index_is_out_of_sync.

Live-data pass/fail is NOT re-asserted here on purpose -- see the module docstring's
note above about mutable data. It was verified manually against the real memory
directory (`python3 check_memory_index.py`, no argv override) as part of this
checkpoint's own review; see the checkpoint report, not this file.
"""
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "check_memory_index.py")


def _write_fixture(tmpdir, memory_files):
    """memory_files: {filename: body_text}. Writes each file plus a MEMORY.md whose
    index carries exactly one matching link line per filename, so the pre-existing
    index-sync check stays clean and every fixture reaches the link check."""
    index_lines = "\n".join(f"- [{name}]({name})" for name in sorted(memory_files))
    with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as f:
        f.write("# Memory index\n\n" + index_lines + "\n")
    for name, body in memory_files.items():
        with open(os.path.join(tmpdir, name), "w", encoding="utf-8") as f:
            f.write(body)


def _write_docs(docs_root, doc_files):
    """doc_files: {relpath: body_text}. Writes each file under docs_root, creating any
    subdirectories relpath implies -- used to exercise the doc-scope [[link]] check
    independently of the memory-file fixture above."""
    for relpath, body in doc_files.items():
        full_path = os.path.join(docs_root, relpath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(body)


def _run(tmpdir, docs_root=None, known_retired_links=None):
    """docs_root: the doc-scope check's second argv. Every existing (memory-only) test omits
    it, so it must default to an EMPTY tmpdir of its own -- never falling through to the
    script's real current-directory default, which would resolve the doc check against
    whatever real, mutable Markdown files happen to be there and drift as they churn.

    known_retired_links: names to set in $KNOWN_RETIRED_LINKS, which the script used to read as
    an exemption list and no longer does. Kept OUT of the process's real environment by default;
    only the tests proving the variable is now ignored set it."""
    env = dict(os.environ)
    if known_retired_links is None:
        env.pop("KNOWN_RETIRED_LINKS", None)
    else:
        env["KNOWN_RETIRED_LINKS"] = ",".join(known_retired_links)
    if docs_root is None:
        with tempfile.TemporaryDirectory() as empty_docs_root:
            return subprocess.run([sys.executable, SCRIPT, tmpdir, empty_docs_root],
                                   capture_output=True, text=True, env=env)
    return subprocess.run([sys.executable, SCRIPT, tmpdir, docs_root],
                           capture_output=True, text=True, env=env)


class TestDanglingLinkCheck(unittest.TestCase):
    def test_all_links_resolve_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "See [[b]] for detail.\n",
                "b.md": "Nothing links out of here.\n",
            })
            result = _run(tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("all links resolve", result.stdout)

    def test_genuinely_dangling_link_gates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "See [[nonexistent-file]] for detail.\n",
            })
            result = _run(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dangling", result.stdout.lower())
            self.assertIn("nonexistent-file", result.stdout)

    def test_retired_links_variable_no_longer_exempts_a_name(self):
        # The $KNOWN_RETIRED_LINKS exemption was removed. A value left set in
        # someone's shell must not quietly bring it back: the named link gates like any other.
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "see [[project-status-open-threads]] for context.\n",
            })
            result = _run(tmpdir, known_retired_links=["project-status-open-threads"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dangling [[project-status-open-threads]]", result.stdout)

    def test_dangling_link_check_does_not_run_when_index_is_out_of_sync(self):
        # An earlier check (index-sync) failing must stop the script before the link
        # check runs, same sequential-gate behaviour the two pre-existing checks
        # already had. A memory file present on disk with NO MEMORY.md index line at
        # all is an index-sync problem, so this fixture never reaches the link check
        # -- even though its dangling link would otherwise be a second, independent
        # reason to fail.
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write("# Memory index\n\n(no index lines at all)\n")
            with open(os.path.join(tmpdir, "a.md"), "w", encoding="utf-8") as f:
                f.write("see [[nonexistent-file]] here.\n")
            result = _run(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("NO index line", result.stdout)
            self.assertNotIn("dangling", result.stdout.lower())

    def test_backticked_mention_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "The syntax is `[[nonexistent-thing]]` -- prose, not a citation.\n",
            })
            result = _run(tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("nonexistent-thing", result.stdout)
            self.assertIn("all links resolve", result.stdout)

    def test_unfenced_dangling_link_still_gates_alongside_backticked_mention(self):
        # Companion to the test above: proves the fix strips backticked mentions
        # without disabling the check entirely -- a genuine, unfenced dangling link
        # in the same file must still gate, while the backticked mention still doesn't.
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "The syntax is `[[nonexistent-thing]]` -- prose. "
                        "See [[also-missing]] for detail.\n",
            })
            result = _run(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("also-missing", result.stdout)
            self.assertNotIn("nonexistent-thing", result.stdout)


class TestDocScopeLinkCheck(unittest.TestCase):
    """The doc-scope [[link]] check (backlog #39, 2026-08-22): same citation syntax, same slug
    set as TestDanglingLinkCheck above, but scanning a second,
    independent docs-root tree instead of the memory dir. Every fixture here gives the memory
    side a single trivial file (`a.md`, no outgoing links) purely to clear the two earlier
    gates and reach the doc check -- the memory-side content itself is not under test."""

    def test_doc_resolving_citation_passes_and_is_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {"note.md": "See [[a]] for detail.\n"})
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[[link]] check (docs): 1 citation(s) in 1 file(s)", result.stdout)

    def test_doc_dangling_citation_gates_at_the_correct_line(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "note.md": "line one\nline two\nSee [[nonexistent-thing]] here.\n",
            })
            result = _run(tmpdir, docs_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DANGLING [[link]] TARGETS IN DOCS", result.stdout)
            self.assertIn("note.md:3: dangling [[nonexistent-thing]]", result.stdout)

    def test_doc_backticked_mention_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "note.md": "The syntax is `[[nonexistent-thing]]` -- prose, not a citation.\n",
            })
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("nonexistent-thing", result.stdout)
            self.assertIn("[[link]] check (docs): 0 citation(s) in 0 file(s)", result.stdout)

    def test_doc_fenced_block_mention_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "note.md": "Example:\n```\nSee [[nonexistent-thing]] here.\n```\nDone.\n",
            })
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("nonexistent-thing", result.stdout)
            self.assertIn("[[link]] check (docs): 0 citation(s) in 0 file(s)", result.stdout)

    def test_doc_retired_links_variable_no_longer_exempts_a_name(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "note.md": "see [[project-status-open-threads]] here.\n",
            })
            result = _run(tmpdir, docs_root, known_retired_links=["project-status-open-threads"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dangling [[project-status-open-threads]]", result.stdout)

    def test_doc_nested_subdirectory_citation_is_found(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {"nested/deeper/note.md": "See [[a]] for detail.\n"})
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[[link]] check (docs): 1 citation(s) in 1 file(s)", result.stdout)

    def test_doc_vendored_directory_is_skipped(self):
        # A vendored/build-output directory (see _SKIP_DIRS) can carry its own .md files --
        # e.g. an installed library's README -- using unrelated double-bracket syntax that was
        # never meant as a citation into this project's memory. Proves such a file is never even
        # read: its bogus link isn't counted, let alone flagged.
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "vendor/some-lib/README.md": "See [[unrelated-wiki-page]] in their docs.\n",
            })
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[[link]] check (docs): 0 citation(s) in 0 file(s)", result.stdout)

    def test_doc_real_citation_still_gates_alongside_vendored_directory(self):
        # Companion to the test above: proves skipping vendor/ doesn't disable the check
        # entirely -- a genuine dangling link elsewhere in docs_root must still gate, while the
        # vendored directory's bogus link stays silently ignored.
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "vendor/some-lib/README.md": "See [[unrelated-wiki-page]] in their docs.\n",
                "note.md": "See [[also-missing]] for detail.\n",
            })
            result = _run(tmpdir, docs_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("also-missing", result.stdout)
            self.assertNotIn("unrelated-wiki-page", result.stdout)

    def test_doc_empty_docs_root_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[[link]] check (docs): 0 citation(s) in 0 file(s)", result.stdout)

    def test_doc_check_does_not_run_when_memory_link_check_already_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "See [[nonexistent-file]] for detail.\n"})
            _write_docs(docs_root, {"note.md": "See [[also-nonexistent]] here.\n"})
            result = _run(tmpdir, docs_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nonexistent-file", result.stdout)
            self.assertNotIn("also-nonexistent", result.stdout)
            self.assertNotIn("(docs)", result.stdout)

    def test_doc_unfenced_bash_test_syntax_not_read_as_a_citation(self):
        # Confirmed live before this fix: '[[ -f "$x" ]]' outside a code fence matched
        # _LINK_RE (any run of non-]/| characters) and was reported as a dangling citation
        # to a file named ' -f "$x" '.md. A real citation target is always an
        # identifier-shaped slug, which this bash snippet is not -- it starts with a space,
        # not a word character, so the tightened pattern never matches it at all.
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "note.md": 'Run a check like: if [[ -f "$x" ]]; then echo ok; fi\n',
            })
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[[link]] check (docs): 0 citation(s) in 0 file(s)", result.stdout)

    def test_doc_real_citation_still_gates_alongside_bash_syntax(self):
        # Companion to the case above: tightening the pattern to reject bash test syntax
        # must not also reject genuine kebab-case citation targets sitting in the same repo.
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "bash-snippet.md": 'if [[ -f "$x" ]]; then echo ok; fi\n',
                "real-citation.md": "see [[nonexistent-real-citation]] for detail.\n",
            })
            result = _run(tmpdir, docs_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nonexistent-real-citation", result.stdout)


class TestMissingMemoryDir(unittest.TestCase):
    """A project with no prior Claude Code session has no memory dir at all yet -- exactly
    what /bootstrap-project leaves behind before the first /finalise run. Confirmed live
    before this fix: os.listdir(MD) raised FileNotFoundError, uncaught."""

    def test_nonexistent_memory_dir_skips_cleanly_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as parent:
            missing_md = os.path.join(parent, "memory")  # never created
            result = subprocess.run([sys.executable, SCRIPT, missing_md, parent],
                                     capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no memory index yet", result.stdout)

    def test_memory_dir_present_but_no_memory_md_also_skips_cleanly(self):
        with tempfile.TemporaryDirectory() as parent:
            md = os.path.join(parent, "memory")
            os.makedirs(md)  # dir exists, but MEMORY.md itself was never written
            result = subprocess.run([sys.executable, SCRIPT, md, parent],
                                     capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no memory index yet", result.stdout)

    def test_empty_but_valid_memory_dir_still_runs_the_checks(self):
        # The bounding case, and the one that proves the guard is not over-broad: a dir with a
        # MEMORY.md and zero topic files is a VALID, checkable state, so it must reach the real
        # checks and report 0 <-> 0 rather than short-circuiting on the absence path above.
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {})
            result = _run(tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("memory index in sync: 0 files", result.stdout)
            self.assertNotIn("no memory index yet", result.stdout)


if __name__ == "__main__":
    unittest.main()

