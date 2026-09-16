# Bootstrap prompt 3 of 5 — the finalise skill itself (run ONCE per machine)

Run this after prompts 1 and 2. This installs `/finalise` as a **global** skill at
`~/.claude/skills/finalise/` — available in every project on this machine, not just one — plus
its three checker scripts and the git-commit reminder hook wired into the **global**
`~/.claude/settings.json`. You will not need to reinstall this per new project; prompt 4 handles
the per-project piece (a `backlog.md`/`decisions.md` pair).

## Why this isn't a byte-for-byte copy

The source version lived inside one specific project and hardcoded that project's own paths
throughout. Made global, those had to become **derived at run time from whatever project you're
in**, or every project would silently read/write one origin project's own files. That
adaptation is already done in the content below — `SKILL.md` now defines `<project root>` and
`<memory dir>` at its own top and uses them throughout, and the three Python scripts already take
their paths as command-line flags with sensible defaults. Nothing here needs further
substitution; write it as given.

## Instructions for Claude

1. Create `~/.claude/skills/finalise/scripts/` and write into it, verbatim, the four files given
   under "Scripts" below: `check_memory_index.py`, `check_thread_state.py`,
   `context_budget_report.py`, and their three test files.

2. Write `~/.claude/skills/finalise/SKILL.md` using the content under "SKILL.md" below, verbatim
   — it already defines `<project root>` (the current session's repo) and `<memory dir>` (derived
   from that root's path) at its top, and uses them throughout instead of any one hardcoded
   project. Note two things it already handles: step 5's three script calls pass their paths
   explicitly as flags, and steps 5-6 skip gracefully if `backlog.md`/`CLAUDE.md` don't exist yet
   in the current project (i.e. before prompt 4 has been run there).

3. Create `~/.claude/hooks/remind_finalise.py` with the content under "Hook" below — this one
   needs no changes at all, it's already generic (it fires on any Bash command containing both
   `git` and `commit`, regardless of project). Also write its test file.

4. Edit `~/.claude/settings.json` (create it if it doesn't exist) to add the PostToolUse hook
   entry shown under "settings.json addition" below. If the file already has a `PostToolUse`
   array, add this as one more entry in it rather than replacing the array; if it already has a
   hook matching `Bash` that does something else, keep both.

5. Do NOT commit/push anything in `~/.claude` yet — ask me first, per prompt 1's instruction.

6. Report what you created and ask me to open a fresh Claude Code session in any project
   directory and try `/finalise` (it may not have much to do yet in a brand-new project, but it
   should at least run steps 1-2, report zero candidates, and run the three checks without
   crashing — check_thread_state.py and context_budget_report.py will complain about a missing
   `backlog.md`/`CLAUDE.md` gracefully if prompt 4 hasn't been run yet; if either crashes instead
   of reporting cleanly, tell me rather than papering over it).

---

## Scripts

### File: ~/.claude/skills/finalise/scripts/check_memory_index.py

```python
#!/usr/bin/env python3
"""Memory-index integrity check for /finalise (audit follow-up, 2026-07-09; dangling-[[link]]
check added for backlog task #13 checkpoint 3, 2026-08-09; doc-scope dangling-[[link]] check
added for backlog task #39, 2026-08-22).

Four invariants, all deterministic, all gating (non-zero exit) -- these used to rely on the
writer remembering them:
  1. Every memory file has exactly one MEMORY.md index line (no more, no fewer).
  2. MEMORY.md stays within its session-start load limits (200 lines / 25 KB).
  3. Every `[[link]]` inside a memory file's body resolves to a real memory filename
     (`<name>.md` next to it). Link resolution is an exact invariant, not a heuristic -- a
     wrong call here breaks resolution in every future session, so this gates like the rest of
     this script. One name is a KNOWN, recorded exception (see KNOWN_RETIRED_LINKS below):
     reported separately, never gated on.
  4. Every `[[link]]` inside the repo's Markdown docs (DOCS_ROOT, recursive, `*.md` only)
     resolves the same way. Reference docs, decisions.md and backlog.md cite memories in the
     same `[[name]]` syntax but were never checked (backlog #39) -- a dead citation there is
     load-bearing for whatever claim it was supposed to source. Fenced code blocks and inline
     code spans are stripped first, length-preserving so reported line numbers stay correct: a
     backticked `` `[[link]]` `` is prose ABOUT the syntax, not a citation, and matching it would
     produce false hard failures on a check that is only permitted to gate because link
     resolution is exact. Same KNOWN_RETIRED_LINKS exemption applies.

Exit 0 = all four hold; exit 1 = problems printed (fix them before ending the session, then
re-run). Each check is sequential and stops at the first failure -- fix what's printed and
re-run rather than expecting one run to report all four categories at once.
"""
import os
import re
import sys
from collections import Counter

MD = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/.claude/projects/" + os.getcwd().replace("/", "-") + "/memory")

files = {f for f in os.listdir(MD) if f.endswith(".md") and f != "MEMORY.md"}
with open(os.path.join(MD, "MEMORY.md"), encoding="utf-8") as f:
    pointers = Counter(re.findall(r"\]\(([^)]+\.md)\)", f.read()))

problems = []
for missing in sorted(files - set(pointers)):
    problems.append(f"file with NO index line: {missing}")
for dangling in sorted(set(pointers) - files):
    problems.append(f"index line pointing at MISSING file: {dangling}")
for name, n in sorted(pointers.items()):
    if n > 1 and name in files:
        problems.append(f"file indexed {n} times: {name}")

if problems:
    print(f"MEMORY INDEX OUT OF SYNC ({len(problems)} problem(s)):")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)

print(f"memory index in sync: {len(files)} files <-> {sum(pointers.values())} index lines")

# Load limits (docs: "first 200 lines of MEMORY.md, or the first 25KB, whichever comes first").
# Bytes bind long before lines here -- our index lines are long, so it truncates near ~110 lines.
# v2.1.211+ strips YAML frontmatter and block HTML comments before measuring; mirror that.
LINE_LIMIT, BYTE_LIMIT = 200, 25 * 1024

raw = open(os.path.join(MD, "MEMORY.md"), encoding="utf-8").read()
body = re.sub(r"\A---\n.*?\n---\n", "", raw, flags=re.S)
body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
n_lines = len(body.splitlines())
n_bytes = len(body.encode("utf-8"))

over = False
for label, val, cap in (("lines", n_lines, LINE_LIMIT), ("bytes", n_bytes, BYTE_LIMIT)):
    pct = val / cap * 100
    if val > cap:
        print(f"MEMORY.md OVER its {label} limit: {val}/{cap} ({pct:.0f}%) -- content past "
              f"the limit is DROPPED at session start")
        over = True
    else:
        flag = "  <-- near limit" if pct >= 80 else ""
        print(f"  {label}: {val}/{cap} ({pct:.0f}%){flag}")
if over:
    sys.exit(1)

# Dangling [[link]] check. Every [[link]] inside a memory file's BODY must resolve to a real
# memory filename (<name>.md next to it, or MEMORY.md itself). MEMORY.md's own body is never
# scanned for [[links]] -- it has none today (pure index lines), so adding that complexity
# isn't justified.
#
# A memory whose content moves elsewhere (e.g. into backlog.md) leaves dangling citations to its
# old name behind ON PURPOSE -- repointing them would manufacture references to things that never
# existed in the new location, so they're deliberately left dangling and reported here instead of
# gated on. This project hasn't retired one yet, so the set starts empty; when it happens, add the
# retired name via $KNOWN_RETIRED_LINKS (comma-separated) or edit the default below. The count of
# files still citing a retired name is derived live every run, never hard-coded, since that count
# can drift as unrelated edits touch the citing files.
KNOWN_RETIRED_LINKS = {
    name for name in os.environ.get("KNOWN_RETIRED_LINKS", "").split(",") if name
}

_LINK_RE = re.compile(r"\[\[([^\]|]+)\]\]")

link_problems = []
known_retired_hits = {}
for fname in sorted(files):
    with open(os.path.join(MD, fname), encoding="utf-8") as f:
        body = f.read()
    for m in _LINK_RE.finditer(body):
        target = m.group(1).strip()
        if (target + ".md") in files or (target + ".md") == "MEMORY.md":
            continue
        if target in KNOWN_RETIRED_LINKS:
            known_retired_hits.setdefault(target, []).append(fname)
        else:
            link_problems.append(f"{fname}: dangling [[{target}]] (no {target}.md on disk)")

if known_retired_hits:
    n_citations = sum(len(v) for v in known_retired_hits.values())
    print(f"KNOWN-RETIRED [[links]] ({n_citations} citation(s), expected -- not gated on; see "
          f"backlog.md Records):")
    for name, fnames in sorted(known_retired_hits.items()):
        print(f"  [[{name}]] cited by {len(fnames)} file(s): {', '.join(fnames)}")

if link_problems:
    print(f"DANGLING [[link]] TARGETS ({len(link_problems)} problem(s)):")
    for p in sorted(link_problems):
        print(f"  - {p}")
    sys.exit(1)

print(f"[[link]] check: {len(files)} files scanned, all links resolve (or are known-retired)")

# Doc-scope [[link]] check. Same citation syntax, same slug set (files) and the same
# KNOWN_RETIRED_LINKS allowlist as above, but scanning the repo's Markdown docs instead of the
# memory dir -- reference docs, decisions.md and backlog.md cite memories in [[name]] form too.
# Runs after the memory-file link check above, keeping the same stop-at-first-failure sequencing
# (a failure above exits before this code ever runs).
DOCS_ROOT = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

_FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_SPAN_RE = re.compile(r"`+[^`]*`+")


def _blank(text):
    """Replace every character with a space except newlines, which are kept -- so the string's
    length and every line boundary survive intact, and stripped[:i].count("\\n") + 1 still gives
    the correct 1-based line number after stripping."""
    return "".join(c if c == "\n" else " " for c in text)


def _strip_code(text):
    """Blank out fenced code blocks, then inline code spans (fences first, then spans -- a span
    marker inside an already-blanked fence has nothing left to match). A backticked [[link]] or
    one inside a fenced block is prose about the syntax, not a citation -- see the module
    docstring. Two known limits, not built for because neither is attested in this repo: an
    unterminated fence is not stripped, and `~~~` fences are not handled."""
    text = _FENCE_RE.sub(lambda m: _blank(m.group(0)), text)
    text = _SPAN_RE.sub(lambda m: _blank(m.group(0)), text)
    return text


_SKIP_DIRS = {".git", "__pycache__", "node_modules"}
_MD_ABS = os.path.abspath(MD)
_DOCS_ROOT_ABS = os.path.abspath(DOCS_ROOT)

doc_files = []
for dirpath, dirnames, filenames in os.walk(_DOCS_ROOT_ABS):
    dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
    for fn in filenames:
        if not fn.endswith(".md"):
            continue
        abspath = os.path.join(dirpath, fn)
        if abspath == _MD_ABS or abspath.startswith(_MD_ABS + os.sep):
            continue  # the memory-file check above already owns these
        doc_files.append(abspath)
doc_files.sort()

doc_link_problems = []       # list of (relpath, line, target)
doc_known_retired_hits = {}  # target -> [relpath, ...]
doc_citation_count = 0
doc_files_with_citations = set()

for abspath in doc_files:
    relpath = os.path.relpath(abspath, _DOCS_ROOT_ABS)
    with open(abspath, encoding="utf-8") as f:
        raw = f.read()
    stripped = _strip_code(raw)
    for m in _LINK_RE.finditer(stripped):
        target = m.group(1).strip()
        line = stripped[:m.start()].count("\n") + 1
        doc_citation_count += 1
        doc_files_with_citations.add(relpath)
        if (target + ".md") in files or (target + ".md") == "MEMORY.md":
            continue
        if target in KNOWN_RETIRED_LINKS:
            doc_known_retired_hits.setdefault(target, []).append(relpath)
        else:
            doc_link_problems.append((relpath, line, target))

if doc_known_retired_hits:
    n_citations = sum(len(v) for v in doc_known_retired_hits.values())
    print(f"KNOWN-RETIRED [[links]] IN DOCS ({n_citations} citation(s), expected -- not gated "
          f"on; see backlog.md Records):")
    for name, relpaths in sorted(doc_known_retired_hits.items()):
        print(f"  [[{name}]] cited by {len(relpaths)} file(s): {', '.join(relpaths)}")

if doc_link_problems:
    print(f"DANGLING [[link]] TARGETS IN DOCS ({len(doc_link_problems)} problem(s)):")
    for relpath, line, target in sorted(doc_link_problems):
        print(f"  - {relpath}:{line}: dangling [[{target}]] (no {target}.md on disk)")
    sys.exit(1)

print(f"[[link]] check (docs): {doc_citation_count} citation(s) in "
      f"{len(doc_files_with_citations)} file(s), all resolve (or are known-retired)")

```

### File: ~/.claude/skills/finalise/scripts/test_check_memory_index.py

```python
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

    known_retired_links: names to inject via $KNOWN_RETIRED_LINKS, kept OUT of the process's
    real environment by default -- production ships with an empty set, so any test exercising
    the exemption must supply its own test-specific name(s) rather than depending on a
    hard-coded production value that no longer exists."""
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

    def test_known_retired_name_does_not_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "This came out of the old worklist -- see "
                        "[[project-status-open-threads]] for context.\n",
            })
            result = _run(tmpdir, known_retired_links=["project-status-open-threads"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("KNOWN-RETIRED", result.stdout)
            self.assertIn("project-status-open-threads", result.stdout)

    def test_unconfigured_retired_name_gates_like_any_other_dangling_link(self):
        # With no $KNOWN_RETIRED_LINKS set (production's real default -- a fresh project
        # hasn't retired anything yet), a name that WOULD be exempt if configured is just
        # an ordinary dangling link.
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "see [[project-status-open-threads]] for context.\n",
            })
            result = _run(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("project-status-open-threads", result.stdout)

    def test_a_different_retired_looking_name_still_gates(self):
        # Mutate the VALUE, not just the guard: with one specific name configured as
        # known-retired, a name that looks like a plausible retired memory (same shape,
        # different string) must NOT get the known-retired pass -- only an exact match is
        # exempt. Catches a check that accidentally matches on shape/prefix rather than the
        # exact string.
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "see [[project-status-closed-threads]] for context.\n",
            })
            result = _run(tmpdir, known_retired_links=["project-status-open-threads"])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("project-status-closed-threads", result.stdout)

    def test_known_retired_citation_count_is_derived_not_hardcoded(self):
        # Two fixture files cite the known-retired name; the printed count must
        # reflect the fixture's actual citation count (2), not any hard-coded number
        # (the brief is explicit: "HARD-CODE NO COUNT" -- the real count already
        # drifted from eight to seven within one day once).
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_fixture(tmpdir, {
                "a.md": "see [[project-status-open-threads]] here.\n",
                "b.md": "and again [[project-status-open-threads]] here.\n",
            })
            result = _run(tmpdir, known_retired_links=["project-status-open-threads"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("2 citation(s)", result.stdout)
            self.assertIn("cited by 2 file(s)", result.stdout)

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


class TestDocScopeLinkCheck(unittest.TestCase):
    """The doc-scope [[link]] check (backlog #39, 2026-08-22): same citation syntax, same slug
    set and known-retired allowlist as TestDanglingLinkCheck above, but scanning a second,
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

    def test_doc_known_retired_name_reports_without_gating(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {
                "note.md": "see [[project-status-open-threads]] here.\n",
            })
            result = _run(tmpdir, docs_root, known_retired_links=["project-status-open-threads"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("KNOWN-RETIRED [[links]] IN DOCS", result.stdout)
            self.assertIn("project-status-open-threads", result.stdout)

    def test_doc_nested_subdirectory_citation_is_found(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
                tempfile.TemporaryDirectory() as docs_root:
            _write_fixture(tmpdir, {"a.md": "Nothing links out of here.\n"})
            _write_docs(docs_root, {"nested/deeper/note.md": "See [[a]] for detail.\n"})
            result = _run(tmpdir, docs_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[[link]] check (docs): 1 citation(s) in 1 file(s)", result.stdout)

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


if __name__ == "__main__":
    unittest.main()

```

### File: ~/.claude/skills/finalise/scripts/check_thread_state.py

```python
#!/usr/bin/env python3
"""Thread-state heuristics for /finalise (backlog task #13, 2026-08-09).

Reports -- never gates (exit 0 always, even when it flags things). Unlike
check_memory_index.py's index-sync/size checks, this is a heuristic, not an
invariant: a task can legitimately be referenced by a commit that needed no
backlog.md change. A non-zero exit would cry wolf and train the reader to ignore
it. The forcing function is the /finalise skill step requiring an explicit
per-task response, not the exit code.

Four report sections:
  1. Task refs in recent commits vs. their current backlog.md section, split
     into OUTSTANDING and RECONCILED around the newest commit that actually
     reconciled each task. A commit reconciles
     task N only if all three hold: it references N (guaranteed -- that is
     why it is in this task's commit list), it modified backlog.md, AND it
     modified TASK N's OWN entry specifically (body text or section changed
     between the commit and its parent). Touching the file is not enough --
     the motivating counterexample is a commit that touches
     backlog.md and mentions two unrelated tasks while only adding a new,
     third task's section; treating it as a reconciler for either of the two
     unrelated tasks would have silently cleared their genuinely-outstanding
     references. Walk each task's referencing
     commits NEWEST-FIRST and take the first (i.e. newest) one that modified
     that task's own entry; if a touching commit mentions the task but did
     NOT modify its entry, keep looking at older commits rather than stopping
     -- do not let the newest touching commit win by default. Once found (at
     index i in the newest-first list): every non-touching commit newer than
     it (index < i) is OUTSTANDING; every non-touching commit older than it
     (index > i) is RECONCILED and collapsed to one summary line, never
     silently dropped. No reconciler found -> every non-touching commit is
     OUTSTANDING, unchanged from the original (task #13) behaviour. This
     preserves the original "an earlier miss must not be masked by a later,
     unrelated touch" guarantee, now keyed on "modified THIS task's entry"
     rather than merely "touched the file" -- see
     TestTouchedBacklogFlag.test_an_earlier_miss_is_not_masked_by_a_later_touch
     in test_check_thread_state.py, which is the regression test for both the
     original defect and this revision of it.
  2. Declared blockers: any Open task whose body contains "blocked by #N",
     printed with #N's current section for human review. This is what surfaces a
     blocking task quietly going stale without anyone noticing.
  3. Next-up staleness: the date on backlog.md's "Next up" block and how many
     commits have landed since.
  4. Task-number collisions: any task number defined in backlog.md that is ALSO
     cited in a memory file under this project's auto-memory directory.
     Memories only ever used the retired numbering scheme, so an overlap means a
     citation now resolves to a different, live task. Exact and the highest-value
     check here.
     Split into two buckets so permanent, expected noise doesn't teach the reader
     to skim the one line that matters:
       - LIVE: the colliding number's current backlog.md section is not Closed --
         a live task reusing a retired number for different work. This is the
         real hazard, printed under the original heading.
       - EXPECTED: the colliding number resolves to a Closed stub -- a citation
         to work that's since closed, correctly cited in some other memory
         file. Printed under its own "resolves to a Closed
         stub -- expected" heading, never dropped silently.
     A number with NO section at all (no '### #N' header, no Closed bullet --
     i.e. no stub in backlog.md, like the retired #22) can never reach either
     bucket: find_task_collisions only considers numbers that are keys of
     `sections`, so a number with no stub produces no hit in the first place --
     there is no live task for a citation to collide with. Kept defensive for
     the one other way a key can lack a resolvable section (a task header
     appearing before any '## ' heading, so its section value is literally
     None): that case is bucketed LIVE, not EXPECTED, on purpose -- we can't
     positively confirm it's a harmless Closed stub, and per backlog.md's own
     Records section, "a colliding pointer is worse than a dangling one:
     dangling fails loudly, colliding fails silently" -- the same asymmetry
     argues for over-flagging here, not under-flagging.

Known, deliberate limitation: this checker is reference-based, not
dependency-based. It would NOT catch a blocked task going stale because its
blocker cleared, if no commit mentions that in a way a ref-scan can detect.
Section 2 (declared blockers) surfaces such cases for review but cannot decide
them; that judgement call is a human one, not something this script resolves.

Design constraints:
  - The commit window is a FIXED DAY COUNT (--days, default 14), never "since
    backlog.md last changed" -- a commit that touches backlog.md can arrive
    AFTER the commit that actually mattered for a given task, so a
    since-last-change window can exclude the very commit that mattered. Do
    not "improve" it back to that.
  - A reconciler is always newer than the reference it reconciles, and the
    window is "last N days", so if the stale reference is inside the window
    its reconciler necessarily is too -- no extra lookback beyond the window
    is needed for section 1.
  - Pure functions + I/O at the edges, so tests never read mutable repo data or
    call git: parse_backlog_sections/parse_task_bodies/extract_task_refs/
    find_declared_blockers/find_task_collisions/find_next_up_date/build_report
    all take pre-fetched text, Commit tuples, or (build_report only) an
    injected `did_modify_entry(commit_hash, task_no) -> bool` callable -- never
    git or the filesystem directly. The real, git-backed implementation lives
    in `_git_show`/`make_did_modify_entry` below, used only by main(); tests
    inject a fixture lambda instead, so the suite stays git-free. Edge cases
    `_git_show`/`make_did_modify_entry` must handle, verified empirically
    against a real repo's history rather than guessed:
      * Root commit / no parent: `git show <rev>^:path` fails with "invalid
        object name" for any repo's actual root commit. Treated as "the
        entry did not exist before" -- if it exists after, that counts as
        modified.
      * `backlog.md` absent at a revision (true for any commit before the one
        that first created it): `git show <rev>:backlog.md` fails with
        "exists on disk, but not in <rev>". Same
        treatment as the no-parent case: absent-then-present counts as
        modified.
      * Any OTHER `git show` failure must not crash the run: caught, a
        warning is printed, and the commit is treated as NOT a reconciler --
        the safe direction is to keep warning rather than silently clear a
        reference on an error.
  - Only the run_git_log/read_*/make_did_modify_entry/_git_show functions and
    main() touch git or the filesystem.
  - Offline. Git and backlog.md (plus the memory directory for section 4) only,
    no network.
"""
import argparse
import os
import re
import subprocess
import sys
from collections import namedtuple

DEFAULT_REPO = os.getcwd()
DEFAULT_BACKLOG = os.path.join(DEFAULT_REPO, "backlog.md")
DEFAULT_MEMORY_DIR = os.path.expanduser(
    "~/.claude/projects/" + DEFAULT_REPO.replace("/", "-") + "/memory")
DEFAULT_DAYS = 14

Commit = namedtuple("Commit", "hash date subject body files")

# --- commit-message ref-extraction patterns (section 1: task refs) ------------

_REF_HASH_RE = re.compile(r'#(\d+)')
_REF_TASK_RE = re.compile(
    r'\btasks?\s+(\d+(?:\s*(?:,|and)\s*\d+)*)', re.IGNORECASE)
_NUM_RE = re.compile(r'\d+')

# --- memory-citation pattern (section 4: task-number collisions) --------------
#
# Deliberately NARROWER than the commit patterns above: a bare '#12' inside
# prose that merely MENTIONS an old citation (e.g. a note explaining why a
# number was removed) must not re-trigger the very check it is explaining.
# Verified against a real case: a memory file explaining a past citation fix
# reads 'it cited "#12" under a retired numbering scheme ... now has a
# different live #12' -- neither '#12' is adjacent to 'task'/'thread', so this
# stays silent on it, while still catching the original citation shape (e.g.
# '... see task #12 ...' or '... thread #12 ...').

_MEMORY_CITATION_RE = re.compile(r'\b(?:task|thread)s?\s*#(\d+)', re.IGNORECASE)

# --- backlog.md structure ------------------------------------------------------

_TASK_HEADER_RE = re.compile(r'^###\s+#(\d+)\b')
# Closed one-liners use TWO shapes in practice: '· **#1** ...' (bold) and
# '· #30 ...' (bare) -- both right after the date's middle-dot separator.
_CLOSED_BULLET_RE = re.compile(r'·\s*\*{0,2}#(\d+)')
_BLOCKED_BY_RE = re.compile(r'blocked by #(\d+)', re.IGNORECASE)
_NEXT_UP_DATE_RE = re.compile(
    r'^##\s+Next up\s*—\s*recommended\s+(\d{4}-\d{2}-\d{2})',
    re.MULTILINE)


def extract_numeric_refs(text):
    """Every task-shaped number reference in a COMMIT message: '#N' and
    'task(s) N[, M and P...]'. Used only for section 1 (commit refs) via
    extract_task_refs -- section 4 (memory collisions) uses the stricter
    extract_memory_citations below, on purpose (see that function's
    docstring)."""
    nums = set()
    for m in _REF_HASH_RE.finditer(text):
        nums.add(int(m.group(1)))
    for m in _REF_TASK_RE.finditer(text):
        for n in _NUM_RE.findall(m.group(1)):
            nums.add(int(n))
    return nums


def extract_memory_citations(text):
    """Every 'task #N' / 'thread #N' citation in a MEMORY file's prose (any
    case, singular or plural). Deliberately narrower than extract_numeric_refs
    -- see the _MEMORY_CITATION_RE comment above for why a bare '#N' must NOT
    count here."""
    return {int(m.group(1)) for m in _MEMORY_CITATION_RE.finditer(text)}


def extract_task_refs(commits):
    """commits: iterable of Commit, in the order given (run_git_log returns
    git-log's default newest-first order). Returns {task_no: [Commit, ...]},
    each list in the same (newest-first) order as the input, so callers take
    [0] for "the most recent referencing commit"."""
    refs = {}
    for c in commits:
        for n in extract_numeric_refs(f"{c.subject}\n{c.body}"):
            refs.setdefault(n, []).append(c)
    return refs


def parse_backlog_sections(text):
    """{task_no: section_name} for every task-number marker anywhere in
    backlog.md: '### #N ...' headers (Open and similar sections) and '**#N**'
    bold bullets (Closed one-liners). section_name is the '## ' heading text up
    to the first em-dash, e.g. '## Not backlog — do not resurface' -> 'Not
    backlog'."""
    sections = {}
    current_section = None
    for line in text.splitlines():
        if line.startswith('## '):
            current_section = line[3:].split('—')[0].strip()
            continue
        m = _TASK_HEADER_RE.match(line)
        if m:
            sections[int(m.group(1))] = current_section
            continue
        m = _CLOSED_BULLET_RE.search(line)
        if m:
            sections.setdefault(int(m.group(1)), current_section)
    return sections


def parse_task_bodies(text):
    """{task_no: body_text} for every '### #N ...' task header's body (the
    lines up to the next '###' or '##' header). Closed one-liners have no body
    to speak of -- they're a single bullet, not a header + paragraph -- so they
    never appear here; only Open-shaped tasks do."""
    bodies = {}
    current_num = None
    buf = []
    for line in text.splitlines():
        header_match = _TASK_HEADER_RE.match(line)
        is_boundary = header_match or (line.startswith('## ') and not header_match)
        if is_boundary:
            if current_num is not None:
                bodies[current_num] = '\n'.join(buf)
            buf = []
            current_num = int(header_match.group(1)) if header_match else None
            continue
        if current_num is not None:
            buf.append(line)
    if current_num is not None:
        bodies[current_num] = '\n'.join(buf)
    return bodies


def find_declared_blockers(bodies, sections):
    """[(task_no, task_section, blocker_no, blocker_section), ...], sorted by
    task_no, for every task body containing 'blocked by #N'."""
    out = []
    for num, body in bodies.items():
        m = _BLOCKED_BY_RE.search(body)
        if m:
            blocker = int(m.group(1))
            out.append((num, sections.get(num), blocker, sections.get(blocker)))
    return sorted(out)


def find_next_up_date(backlog_text):
    """The YYYY-MM-DD date on the 'Next up' block's heading, or None if the
    block doesn't exist yet (it's a separate deliverable -- absence is normal
    until that ships)."""
    m = _NEXT_UP_DATE_RE.search(backlog_text)
    return m.group(1) if m else None


def find_task_collisions(sections, memory_texts):
    """sections: {task_no: section_name}, i.e. parse_backlog_sections's output
    -- every task number that has a stub in backlog.md, mapped to the section
    it currently lives in. memory_texts: {filename: text}.

    Returns (live_hits, closed_hits), each a sorted [(task_no, [filename,
    ...]), ...] list, for every backlog task number that is ALSO cited (via
    'task #N' / 'thread #N' -- see extract_memory_citations) inside a memory
    file's body. Memories only ever used the retired numbering scheme, so any
    overlap means the citation now resolves to a different, live task --
    exact, not heuristic.

    A task number with NO stub in backlog.md is not a key of `sections`, so it
    can never produce a hit here at all -- there is no live task for a
    citation to collide with (see the module docstring's section-4 note for
    why, and why that's the right call for a number like the retired #22).

    live_hits = the real hazard: the number's current section is not Closed.
    closed_hits = expected: the number resolves to a Closed stub. A number
    whose section is present-but-None (a malformed-structure edge case, not
    reachable from today's real backlog.md -- see the module docstring) is
    bucketed into live_hits, not closed_hits: unconfirmed is treated as
    unsafe, not as expected."""
    hits = {}
    for fname, text in sorted(memory_texts.items()):
        for n in extract_memory_citations(text):
            if n in sections:
                hits.setdefault(n, []).append(fname)
    live_hits = []
    closed_hits = []
    for num, filenames in sorted(hits.items()):
        if sections.get(num) == "Closed":
            closed_hits.append((num, filenames))
        else:
            live_hits.append((num, filenames))
    return live_hits, closed_hits


# --- I/O at the edges -----------------------------------------------------

_COMMIT_SEP = "\x01COMMIT\x01"
_BODY_SEP = "\x01BODY\x01"
_FILES_SEP = "\x01FILES\x01"


def run_git_log(repo_dir, days):
    """Real commits from `repo_dir`'s history over the last `days` days,
    newest-first (git log's default order), each with its subject, body and
    the list of files it touched."""
    fmt = f"{_COMMIT_SEP}%n%H%n%ad%n%s%n{_BODY_SEP}%n%b%n{_FILES_SEP}"
    proc = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--date=short",
         f"--pretty=format:{fmt}", "--name-only"],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    )
    commits = []
    for chunk in proc.stdout.split(_COMMIT_SEP + "\n")[1:]:
        head, _, rest = chunk.partition(_BODY_SEP + "\n")
        h, date, subject = head.strip("\n").split("\n", 2)
        body, _, files_blob = rest.partition(_FILES_SEP)
        body = body.rstrip("\n")
        files = [f for f in files_blob.strip("\n").splitlines() if f.strip()]
        commits.append(Commit(h, date, subject, body, files))
    return commits


def count_commits_since(repo_dir, date_str):
    """Commits since `date_str` (a bare 'YYYY-MM-DD', as the 'Next up' block
    records it -- no time of day). Pinned to that date's midnight
    (T00:00:00): git's approxidate otherwise fills unspecified time fields
    from the CURRENT clock, so a bare '--since=2026-08-09' means "since
    ~11:15 this morning", not midnight -- demonstrated in this repo:
    '--since=2026-08-09' returned 0 commits the same day '--since=
    2026-08-09T00:00:00' returned 16. Pinning to midnight over-counts within
    the block's own authoring day (it includes commits made earlier that same
    day, before the block was written) -- accepted deliberately: the block
    records a date with no time, so an exact answer isn't available, and
    over-counting fails loudly (an inflated-but-visible number) while
    under-counting fails silently (a staleness count that quietly reads low
    forever). Do not invent a timestamp format for the 'Next up' block to make
    this exact -- out of scope for this fix."""
    proc = subprocess.run(
        ["git", "log", f"--since={date_str}T00:00:00", "--oneline"],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    )
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return len(lines)


def read_memory_texts(memory_dir):
    texts = {}
    for fname in os.listdir(memory_dir):
        if fname.endswith(".md") and fname != "MEMORY.md":
            with open(os.path.join(memory_dir, fname), encoding="utf-8") as f:
                texts[fname] = f.read()
    return texts


# --- did_modify_entry: git-backed, used only by main() (task #32) -----------
#
# build_report needs to know whether a commit modified a SPECIFIC task's own
# backlog.md entry, not just the file. That requires git (diff against the
# parent revision), so it is kept out of build_report entirely and injected
# as a callable -- see the module docstring's "Design constraints" section
# for the edge cases handled here and how each was verified against this
# repo's real history.

_GIT_SHOW_ABSENT_MARKERS = ("exists on disk, but not in", "invalid object name")


def _git_show(repo_dir, rev, path):
    """Text content of `path` at `rev`, or None if it doesn't exist there --
    covers both a missing parent (root commit's `rev^`) and the path not yet
    existing at that revision. Any OTHER failure raises RuntimeError, which
    make_did_modify_entry catches and treats as "not a reconciler" (see module
    docstring)."""
    proc = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return proc.stdout
    if any(marker in proc.stderr for marker in _GIT_SHOW_ABSENT_MARKERS):
        return None
    raise RuntimeError(f"git show {rev}:{path} failed: {proc.stderr.strip()}")


def make_did_modify_entry(repo_dir):
    """Returns a did_modify_entry(commit_hash, task_no) -> bool callable,
    backed by git, memoised per commit_hash (a commit is checked against
    every task it references, so this avoids re-running `git show` twice for
    the same commit). main() supplies this to build_report; tests supply a
    fixture lambda instead -- see module docstring."""
    cache = {}

    def did_modify_entry(commit_hash, task_no):
        if commit_hash not in cache:
            try:
                new_text = _git_show(repo_dir, commit_hash, "backlog.md")
                old_text = _git_show(repo_dir, f"{commit_hash}^", "backlog.md")
                cache[commit_hash] = (
                    parse_backlog_sections(new_text) if new_text is not None else {},
                    parse_task_bodies(new_text) if new_text is not None else {},
                    parse_backlog_sections(old_text) if old_text is not None else {},
                    parse_task_bodies(old_text) if old_text is not None else {},
                    None,
                )
            except RuntimeError as exc:
                cache[commit_hash] = (None, None, None, None, str(exc))

        new_sections, new_bodies, old_sections, old_bodies, error = cache[commit_hash]
        if error is not None:
            print(f"warning: {error} -- treating {commit_hash[:10]} as NOT a "
                  f"reconciler for #{task_no}", file=sys.stderr)
            return False
        return (new_sections.get(task_no) != old_sections.get(task_no)
                or new_bodies.get(task_no) != old_bodies.get(task_no))

    return did_modify_entry


# --- report -----------------------------------------------------------------

def build_report(backlog_text, commits, memory_texts, did_modify_entry):
    """Pure (git-free): assemble the four report sections from already-loaded
    inputs plus an injected did_modify_entry(commit_hash, task_no) -> bool
    (see make_did_modify_entry above; tests supply a fixture lambda). Returns
    a dict; main() decides how to print it. Kept separate from
    build_next_up_section, which additionally needs a commits-since-date count
    that only main() (via count_commits_since) can supply.

    Section 1 partitions each task's commits (task_refs[num], newest-first)
    around the newest RECONCILING commit -- see the module docstring for the
    full three-condition definition. Walking newest-first and taking the
    first touching commit for which did_modify_entry is True means a touching
    commit that did NOT modify the task's own entry is skipped, not treated
    as a reconciler by default -- that is the fix for backlog #32."""
    sections = parse_backlog_sections(backlog_text)
    bodies = parse_task_bodies(backlog_text)
    task_refs = extract_task_refs(commits)

    ref_report = []
    for num in sorted(task_refs):
        commits_for_task = task_refs[num]
        recent = commits_for_task[0]

        reconciler_idx = None
        for idx, c in enumerate(commits_for_task):
            if "backlog.md" in c.files and did_modify_entry(c.hash, num):
                reconciler_idx = idx
                break  # newest-first order -> first hit is the newest reconciler

        if reconciler_idx is not None:
            outstanding = [c for idx, c in enumerate(commits_for_task)
                           if idx < reconciler_idx and "backlog.md" not in c.files]
            reconciled = [c for idx, c in enumerate(commits_for_task)
                          if idx > reconciler_idx and "backlog.md" not in c.files]
            reconciled_by = commits_for_task[reconciler_idx].hash
        else:
            # No commit modified this task's own entry -- every non-touching
            # commit is outstanding, unchanged from the pre-#32 behaviour.
            outstanding = [c for c in commits_for_task if "backlog.md" not in c.files]
            reconciled = []
            reconciled_by = None

        ref_report.append({
            "number": num,
            "section": sections.get(num),
            "commit_hash": recent.hash,
            "commit_date": recent.date,
            "most_recent_touched_backlog": "backlog.md" in recent.files,
            "outstanding_commits": [(c.hash, c.date) for c in outstanding],
            "reconciled_commits": [(c.hash, c.date) for c in reconciled],
            "reconciled_by": reconciled_by,
        })

    blockers = find_declared_blockers(bodies, sections)
    collisions, closed_collisions = find_task_collisions(sections, memory_texts)

    return {
        "task_refs": ref_report,
        "blockers": blockers,
        "collisions": collisions,
        "closed_collisions": closed_collisions,
    }


def print_report(report, next_up_date, commits_since_next_up, days):
    print(f"=== 1. Task refs in the last {days} day(s) vs. backlog.md ===")
    if not report["task_refs"]:
        print("  (no #N / task N references in this window)")
    for row in report["task_refs"]:
        section = row["section"] or "(no section found)"
        outstanding = row["outstanding_commits"]
        reconciled = row["reconciled_commits"]
        print(f"  #{row['number']}: section={section} "
              f"most-recent-ref={row['commit_hash'][:10]} ({row['commit_date']}) "
              f"most-recent-touched-backlog.md={row['most_recent_touched_backlog']}")
        if outstanding:
            print(f"    <-- status may be stale: {len(outstanding)} referencing "
                  f"commit(s) in this window did NOT touch backlog.md:")
            for h, d in outstanding:
                print(f"        {h[:10]} ({d})")
        if reconciled:
            print(f"    ({len(reconciled)} earlier reference(s) reconciled by "
                  f"{row['reconciled_by'][:10]})")

    print()
    print("=== 2. Declared blockers ('blocked by #N') ===")
    if not report["blockers"]:
        print("  (none found)")
    for task_no, task_section, blocker_no, blocker_section in report["blockers"]:
        print(f"  #{task_no} ({task_section}) blocked by #{blocker_no} "
              f"(#{blocker_no} is currently in: {blocker_section}) -- review")

    print()
    print("=== 3. Next-up staleness ===")
    if next_up_date is None:
        print("  No 'Next up' block found in backlog.md.")
    else:
        print(f"  Next up dated {next_up_date}; {commits_since_next_up} "
              f"commit(s) since.")

    print()
    print("=== 4. Task-number collisions (backlog.md vs. retired-scheme memories) ===")
    if not report["collisions"]:
        print("  (none found)")
    for task_no, filenames in report["collisions"]:
        print(f"  #{task_no} is a LIVE backlog task, also cited in: "
              f"{', '.join(filenames)} -- citation may resolve to the wrong task")

    print()
    print("=== 4b. Collisions that resolve to a Closed stub -- expected ===")
    if not report["closed_collisions"]:
        print("  (none found)")
    for task_no, filenames in report["closed_collisions"]:
        print(f"  #{task_no} resolves to a Closed stub, also cited in: "
              f"{', '.join(filenames)} -- expected, no action needed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                         help=f"commit window in days (default {DEFAULT_DAYS})")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--backlog", default=DEFAULT_BACKLOG)
    parser.add_argument("--memory-dir", default=DEFAULT_MEMORY_DIR)
    args = parser.parse_args()

    with open(args.backlog, encoding="utf-8") as f:
        backlog_text = f.read()

    commits = run_git_log(args.repo, args.days)
    memory_texts = read_memory_texts(args.memory_dir)
    did_modify_entry = make_did_modify_entry(args.repo)

    report = build_report(backlog_text, commits, memory_texts, did_modify_entry)

    next_up_date = find_next_up_date(backlog_text)
    commits_since = (count_commits_since(args.repo, next_up_date)
                      if next_up_date else None)

    print_report(report, next_up_date, commits_since, args.days)

    # Reports, never gates -- see module docstring.
    sys.exit(0)


if __name__ == "__main__":
    main()

```

### File: ~/.claude/skills/finalise/scripts/test_check_thread_state.py

```python
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
            "https://claude.ai/code/session_01DyggXnDTYC8chKuycjLFFw",
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


class TestFindNextUpDate(unittest.TestCase):
    def test_date_parsed(self):
        text = "## Next up — recommended 2026-08-09\n\nsome content\n"
        self.assertEqual(cts.find_next_up_date(text), "2026-08-09")

    def test_absent_returns_none(self):
        self.assertIsNone(cts.find_next_up_date(BACKLOG_FIXTURE))


if __name__ == "__main__":
    unittest.main()

```

### File: ~/.claude/skills/finalise/scripts/context_budget_report.py

```python
#!/usr/bin/env python3
"""Context-budget growth report for /finalise (checkpoint 5, context-budget-relocation-and-
lesson-ledger plan, 2026-08-18).

Reports -- never gates (exit 0 always, same convention as check_thread_state.py). The problem
this watches is growth: the always-loaded global CLAUDE.md went 6,738 -> 25,804 bytes in three
weeks, 2.8x of that in the last eight days alone, before the relocation and ledger passes this
checkpoint closes out. There is exactly ONE threshold anywhere in this file, and it is not new:
MEMORY.md's 200-line / 25,600-byte load limit, already enforced by check_memory_index.py.
Everything else here is a bare figure or a delta against logged history -- never an invented
budget. An earlier draft of the plan this implements specified a flat 20,000-byte flag on the
combined total; that figure had no derivation, and against the actual post-relocation total
(~37,300 bytes) it would have gone red on its first run and stayed red every run after.
Permanently-red checks get ignored, which is worse than no check -- so this prints numbers and
leaves picking a line to the user, once the log has a few weeks of real observations in it.

Four things printed:
  1. Lesson candidates in lesson-candidates.md awaiting a second case -- count and the oldest
     one's age in days. A candidate entry is identified by carrying a "First observed:" field
     (the Candidate schema requires it; the Origin log schema has "Home:"/"Promoted:" instead),
     so this counts by field signature, not by which "##" section heading happens to exist yet
     -- the real file today has zero "## Candidates" entries and no such heading at all, and
     that must read as a genuine zero, not the default a broken parser would also print. See
     TestCountCandidatesAwaiting for the populated-fixture case that guards against exactly that.
  2. Rules across the four user-scope homes (~/.claude/CLAUDE.md's Working rules section,
     prompt-lessons.md's Checklist section, writing-standing-docs.md, writing-executor-briefs.md
     in full) still carrying a "Provisional" single-case marker anywhere in their body. A
     top-level bullet with several internal Provisional tags (one per sub-rule) still counts
     once.
  3. Per-file and total bytes of the three always-loaded surfaces: ~/.claude/CLAUDE.md,
     the current project's CLAUDE.md, MEMORY.md.
  4. The delta on that total since the previous logged reading, with its date -- from
     the project's context_budget_log.csv (created lazily on first run; its absence is normal,
     not a fault). The delta is computed against the PRE-write history, so a same-day re-run
     compares against yesterday's row, not against the row this run is about to write.

Run:  PYTHONPATH=~/.claude/skills/finalise/scripts python3 context_budget_report.py
"""
import argparse
import csv
import os
import re
import shutil
import sys
import tempfile
from datetime import date


def atomic_write_csv(path, fieldnames, rows):
    """Write a CSV atomically: back up any existing file to <path>.bak, write to a
    temp file in the same directory, then os.replace() it into place. An interrupted
    write leaves the original (or its .bak) intact rather than a truncated file."""
    path = os.path.abspath(path)
    directory = os.path.dirname(path) or '.'
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            shutil.copy2(path, path + '.bak')
        except OSError:
            pass
    fd, tmp = tempfile.mkstemp(dir=directory, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


DEFAULT_GLOBAL_CLAUDE = os.path.expanduser("~/.claude/CLAUDE.md")
DEFAULT_PROJECT_CLAUDE = os.path.join(os.getcwd(), "CLAUDE.md")
DEFAULT_MEMORY_INDEX = os.path.expanduser(
    "~/.claude/projects/" + os.getcwd().replace("/", "-") + "/memory/MEMORY.md")
DEFAULT_PROMPT_LESSONS = os.path.expanduser("~/.claude/prompt-lessons.md")
DEFAULT_WRITING_STANDING_DOCS = os.path.expanduser("~/.claude/writing-standing-docs.md")
DEFAULT_WRITING_EXECUTOR_BRIEFS = os.path.expanduser("~/.claude/writing-executor-briefs.md")
DEFAULT_LEDGER = os.path.expanduser("~/.claude/lesson-candidates.md")
DEFAULT_HISTORY = os.path.join(os.getcwd(), "context_budget_log.csv")

HISTORY_FIELDS = ["date", "global_claude_bytes", "project_claude_bytes",
                   "memory_index_bytes", "total_bytes", "global_claude_lines"]

MARKER = "Provisional"


def read_text(path):
    """UTF-8 file text, or '' if the file doesn't exist yet. The ledger and the history log are
    both created lazily on first run -- absence is normal here, not a fault."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def split_top_level_bullets(text):
    """Top-level bullet bodies: each starts at column 0 with '- '; anything indented (a
    sub-clause, a continuation line, a nested list) belongs to the current bullet, not a new
    one. Lines before the first top-level bullet (headers, intro prose) are dropped."""
    bullets, current = [], None
    for line in text.splitlines():
        if line.startswith("- "):
            if current is not None:
                bullets.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        bullets.append("\n".join(current))
    return bullets


def extract_section(text, heading_line, boundary_prefix):
    """Text strictly between a line equal to heading_line and the next line starting with
    boundary_prefix, or EOF. Returns '' if heading_line never appears -- callers treat that as
    zero bullets to scan there, not an error: a home file with no matching section genuinely
    has nothing to count in it."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line == heading_line:
            start = i + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith(boundary_prefix):
            end = i
            break
    return "\n".join(lines[start:end])


def count_marked_bullets(text, marker=MARKER):
    """(total top-level bullets, how many contain `marker` anywhere in their body)."""
    bullets = split_top_level_bullets(text)
    marked = sum(1 for b in bullets if marker in b)
    return len(bullets), marked


def split_h3_entries(text):
    """[(heading, body)] for every '### ' entry at column 0. A schema-template example line
    like '    ### <one-line claim, imperative>' is indented four spaces (it renders as a
    markdown code block), so it never starts a line at column 0 and is never picked up here --
    real entries and template documentation are separated structurally, not by a heuristic
    guess at which text is "real"."""
    entries, heading, body = [], None, []
    for line in text.splitlines():
        if line.startswith("### "):
            if heading is not None:
                entries.append((heading, "\n".join(body)))
            heading, body = line[4:].strip(), []
        elif line.startswith("## "):
            if heading is not None:
                entries.append((heading, "\n".join(body)))
            heading, body = None, []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        entries.append((heading, "\n".join(body)))
    return entries


_FIRST_OBSERVED_RE = re.compile(r"First observed:\s*(\d{4}-\d{2}-\d{2})")


def count_candidates_awaiting(ledger_text, today):
    """(count, oldest_age_days_or_None). A candidate entry is identified by carrying a
    '- First observed: <date>' field -- the field the Candidate schema requires and the Origin
    log schema does not have -- so this counts by field signature, not by section-heading
    presence. `today` is an explicit date passed in (never date.today() read internally), so a
    test can pin it to whatever date its fixture's "First observed:" values were written
    against; production wiring is the only caller that passes the real date."""
    dates = []
    for _heading, body in split_h3_entries(ledger_text):
        m = _FIRST_OBSERVED_RE.search(body)
        if m:
            dates.append(date.fromisoformat(m.group(1)))
    if not dates:
        return 0, None
    oldest = min(dates)
    return len(dates), (today - oldest).days


def read_history(path):
    """All logged rows, or [] if the history log doesn't exist yet (created lazily on first
    run -- absence is normal)."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def previous_reading(rows, today_str):
    """Most recent row dated strictly before today_str, or None. Compared by the 'date' string
    (ISO format sorts lexicographically) rather than list position, so this is correct even if
    the log is ever hand-edited out of order."""
    earlier = [r for r in rows if r.get("date", "") < today_str]
    if not earlier:
        return None
    return max(earlier, key=lambda r: r["date"])


def upsert_reading(path, row):
    """Idempotent upsert keyed on date -- the same convention any other date-keyed log in
    this project should use: a rerun on the same day replaces that day's row instead of
    duplicating it; a new day appends. Atomic write via the project's single shared CSV writer."""
    rows = read_history(path)
    index = {r.get("date"): i for i, r in enumerate(rows)}
    if row["date"] in index:
        rows[index[row["date"]]] = row
    else:
        rows.append(row)
    atomic_write_csv(path, HISTORY_FIELDS, rows)


def build_report(paths, today):
    """paths: dict with keys global_claude, project_claude, memory_index, prompt_lessons,
    writing_standing_docs, writing_executor_briefs, ledger, history -- every one of them a path,
    always read through read_text/read_history, never assumed to exist. Returns a dict of every
    computed figure so main() (printing) and tests (asserting) share one computation, and a dict
    for the history row this reading should upsert."""
    global_text = read_text(paths["global_claude"])
    project_text = read_text(paths["project_claude"])
    memory_text = read_text(paths["memory_index"])
    prompt_lessons_text = read_text(paths["prompt_lessons"])
    writing_standing_docs_text = read_text(paths["writing_standing_docs"])
    writing_executor_briefs_text = read_text(paths["writing_executor_briefs"])
    ledger_text = read_text(paths["ledger"])

    global_bytes = len(global_text.encode("utf-8"))
    project_bytes = len(project_text.encode("utf-8"))
    memory_bytes = len(memory_text.encode("utf-8"))
    total_bytes = global_bytes + project_bytes + memory_bytes
    global_lines = len(global_text.splitlines())

    n_candidates, oldest_age_days = count_candidates_awaiting(ledger_text, today)

    homes = [
        ("~/.claude/CLAUDE.md § Working rules",
         extract_section(global_text, "# Working rules", "# ")),
        ("prompt-lessons.md § Checklist",
         extract_section(prompt_lessons_text, "## Checklist", "## ")),
        ("writing-standing-docs.md", writing_standing_docs_text),
        ("writing-executor-briefs.md", writing_executor_briefs_text),
    ]
    home_counts = []
    total_rules, total_marked = 0, 0
    for label, section_text in homes:
        n_rules, n_marked = count_marked_bullets(section_text)
        home_counts.append((label, n_rules, n_marked))
        total_rules += n_rules
        total_marked += n_marked

    today_str = today.isoformat()
    history_rows = read_history(paths["history"])
    prev = previous_reading(history_rows, today_str)

    history_row = {
        "date": today_str,
        "global_claude_bytes": str(global_bytes),
        "project_claude_bytes": str(project_bytes),
        "memory_index_bytes": str(memory_bytes),
        "total_bytes": str(total_bytes),
        "global_claude_lines": str(global_lines),
    }

    return {
        "global_bytes": global_bytes,
        "project_bytes": project_bytes,
        "memory_bytes": memory_bytes,
        "total_bytes": total_bytes,
        "global_lines": global_lines,
        "n_candidates": n_candidates,
        "oldest_age_days": oldest_age_days,
        "home_counts": home_counts,
        "total_rules": total_rules,
        "total_marked": total_marked,
        "previous_reading": prev,
        "history_row": history_row,
    }


def format_report(report):
    lines = []
    lines.append("Lesson candidates awaiting a second case:")
    if report["n_candidates"] == 0:
        lines.append("  0 candidates")
    else:
        lines.append(f"  {report['n_candidates']} candidate(s), "
                      f"oldest {report['oldest_age_days']} day(s) old")

    lines.append("")
    lines.append("Rules still carrying a single-case (\"Provisional\") marker:")
    for label, n_rules, n_marked in report["home_counts"]:
        lines.append(f"  {label}: {n_marked}/{n_rules}")
    lines.append(f"  total: {report['total_marked']}/{report['total_rules']}")

    lines.append("")
    lines.append("Always-loaded surfaces:")
    lines.append(f"  ~/.claude/CLAUDE.md:  {report['global_bytes']:,} bytes "
                 f"({report['global_lines']} lines)")
    lines.append(f"  project CLAUDE.md:    {report['project_bytes']:,} bytes")
    lines.append(f"  MEMORY.md:            {report['memory_bytes']:,} bytes")
    prev = report["previous_reading"]
    if prev is None:
        lines.append(f"  total: {report['total_bytes']:,} bytes (no previous reading logged)")
    else:
        delta = report["total_bytes"] - int(prev["total_bytes"])
        sign = "+" if delta >= 0 else ""
        lines.append(f"  total: {report['total_bytes']:,} bytes "
                     f"({sign}{delta:,} since {prev['date']})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-claude", default=DEFAULT_GLOBAL_CLAUDE)
    parser.add_argument("--project-claude", default=DEFAULT_PROJECT_CLAUDE)
    parser.add_argument("--memory-index", default=DEFAULT_MEMORY_INDEX)
    parser.add_argument("--prompt-lessons", default=DEFAULT_PROMPT_LESSONS)
    parser.add_argument("--writing-standing-docs", default=DEFAULT_WRITING_STANDING_DOCS)
    parser.add_argument("--writing-executor-briefs", default=DEFAULT_WRITING_EXECUTOR_BRIEFS)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--history", default=DEFAULT_HISTORY)
    parser.add_argument("--today", default=None,
                         help="ISO date to treat as 'today' (default: the real date). Tests "
                              "pin this so age/delta math never drifts with the wall clock.")
    parser.add_argument("--no-write", action="store_true",
                         help="Print the report but don't upsert the history log.")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()

    paths = {
        "global_claude": args.global_claude,
        "project_claude": args.project_claude,
        "memory_index": args.memory_index,
        "prompt_lessons": args.prompt_lessons,
        "writing_standing_docs": args.writing_standing_docs,
        "writing_executor_briefs": args.writing_executor_briefs,
        "ledger": args.ledger,
        "history": args.history,
    }

    report = build_report(paths, today)
    print(format_report(report))

    if not args.no_write:
        upsert_reading(args.history, report["history_row"])

    # Reports, never gates -- see module docstring.
    sys.exit(0)


if __name__ == "__main__":
    main()

```

### File: ~/.claude/skills/finalise/scripts/test_context_budget_report.py

```python
#!/usr/bin/env python3
"""Tests for context_budget_report.py (checkpoint 5, context-budget-relocation-and-lesson-ledger
plan, 2026-08-18).

This check reads eight mutable paths in production (both CLAUDE.md files, MEMORY.md, the three
other user-scope rule homes, the ledger, and the history CSV) and writes one (the history CSV).
`run_tests.sh` runs this suite at every turn-end, in the supervisor's session as much as the
executor's, so none of it may touch the real files -- every test below builds its own fixture
text or its own tmpdir and passes it in explicitly. A test that read the real ~/.claude/CLAUDE.md
would drift red as that file's Provisional-tag count and byte size change, exactly the failure
mode the project convention warns about (a function grows a repo-data read and its existing tests
start reading live data silently).

Date-dependent logic (candidate age, the history delta) never calls date.today() inside a test
or inside the functions under test without an explicit `today` argument -- fixtures and the
assertions that check them share one pinned reference date, so nothing here can drift as the
calendar advances (see feedback-test-fixtures-share-a-clock).
"""
import os
import tempfile
import unittest
from datetime import date

import context_budget_report as cbr


# ---------------------------------------------------------------------------
# split_top_level_bullets / count_marked_bullets
# ---------------------------------------------------------------------------

class TestSplitTopLevelBullets(unittest.TestCase):
    def test_splits_on_column_zero_dash_only(self):
        text = (
            "# Heading\n"
            "\n"
            "- First bullet, line one.\n"
            "  continuation, indented, not a new bullet.\n"
            "- Second bullet.\n"
        )
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 2)
        self.assertIn("continuation, indented", bullets[0])
        self.assertTrue(bullets[1].startswith("- Second bullet."))

    def test_indented_dash_is_not_a_new_bullet(self):
        text = "- Outer bullet.\n  - indented sub-item, not top-level.\n- Next outer bullet.\n"
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 2)
        self.assertIn("indented sub-item", bullets[0])

    def test_no_bullets_returns_empty_list(self):
        self.assertEqual(cbr.split_top_level_bullets("# Just a heading\n\nSome prose.\n"), [])

    def test_text_before_first_bullet_is_dropped(self):
        text = "# Heading\nIntro prose that is not a bullet.\n- Only bullet.\n"
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 1)
        self.assertNotIn("Intro prose", bullets[0])

    def test_bare_dash_without_space_is_not_a_bullet_start(self):
        # A markdown horizontal rule ("---") or a bare "-" line must not be mistaken for a new
        # top-level bullet -- only "- " (dash, then space) starts one.
        text = "- Real bullet, continues here.\n---\nstill part of the same bullet.\n"
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 1)
        self.assertIn("---", bullets[0])
        self.assertIn("still part of the same bullet", bullets[0])


class TestExtractSection(unittest.TestCase):
    def test_extracts_between_heading_and_next_boundary(self):
        text = (
            "# User scope\n"
            "- router bullet, must not be counted\n"
            "\n"
            "# Working rules\n"
            "\n"
            "- rule one\n"
            "- rule two\n"
        )
        section = cbr.extract_section(text, "# Working rules", "# ")
        self.assertNotIn("router bullet", section)
        self.assertIn("rule one", section)
        self.assertIn("rule two", section)

    def test_stops_at_next_matching_boundary_not_eof(self):
        text = "## Checklist\n- kept bullet\n## Origin log\n- excluded bullet\n"
        section = cbr.extract_section(text, "## Checklist", "## ")
        self.assertIn("kept bullet", section)
        self.assertNotIn("excluded bullet", section)

    def test_missing_heading_returns_empty_string(self):
        self.assertEqual(cbr.extract_section("# Something else\n- a bullet\n",
                                              "# Working rules", "# "), "")

    def test_heading_match_is_exact_not_substring(self):
        # A prose line that merely MENTIONS "# Working rules" (e.g. quoting it inside a bullet)
        # must not be mistaken for the real heading line.
        text = (
            "- a bullet that quotes \"# Working rules\" in its own text, decoy\n"
            "\n"
            "# Working rules\n"
            "- the real rule\n"
        )
        section = cbr.extract_section(text, "# Working rules", "# ")
        self.assertIn("the real rule", section)
        self.assertNotIn("decoy", section)


class TestCountMarkedBullets(unittest.TestCase):
    def test_counts_bullets_containing_marker(self):
        text = (
            "- Clean rule, no marker at all.\n"
            "- Tagged rule. (2026-08-01: a case. Provisional -- one case.)\n"
        )
        n_rules, n_marked = cbr.count_marked_bullets(text)
        self.assertEqual(n_rules, 2)
        self.assertEqual(n_marked, 1)

    def test_bullet_with_several_internal_markers_counts_once(self):
        text = (
            "- Multi-part rule.\n"
            "  **Sub-rule A.** (Provisional -- case A.)\n"
            "  **Sub-rule B.** (Provisional -- case B.)\n"
            "  **Sub-rule C.** (Provisional -- case C.)\n"
        )
        n_rules, n_marked = cbr.count_marked_bullets(text)
        self.assertEqual(n_rules, 1)
        self.assertEqual(n_marked, 1)

    def test_empty_text_counts_zero_of_zero(self):
        self.assertEqual(cbr.count_marked_bullets(""), (0, 0))


# ---------------------------------------------------------------------------
# split_h3_entries / count_candidates_awaiting
# ---------------------------------------------------------------------------

class TestSplitH3Entries(unittest.TestCase):
    def test_column_zero_h3_is_an_entry(self):
        text = "## Origin logs\n\n### Rule opening words\n\n- Home: somewhere\n"
        entries = cbr.split_h3_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "Rule opening words")
        self.assertIn("Home: somewhere", entries[0][1])

    def test_indented_schema_template_is_not_an_entry(self):
        # Mirrors the real file's "## Schema" block: template lines are indented four spaces,
        # so they render as a markdown code block and must never be mistaken for a real entry.
        text = (
            "## Schema\n\n"
            "### Candidate\n\n"
            "    ### <one-line claim, imperative>\n"
            "    - First observed: <absolute date> - <project/task>\n"
        )
        entries = cbr.split_h3_entries(text)
        # Only the real (column-0) "### Candidate" heading is an entry; the indented template
        # line inside its body is not a second entry.
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "Candidate")

    def test_h2_boundary_closes_an_open_entry(self):
        text = "### Entry one\n- Home: x\n## Next section\nsome prose, not an entry body\n"
        entries = cbr.split_h3_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("Next section", entries[0][1])
        self.assertNotIn("some prose", entries[0][1])


class TestCountCandidatesAwaiting(unittest.TestCase):
    TODAY = date(2026, 8, 18)

    def test_populated_ledger_returns_nonzero_count_and_oldest_age(self):
        # The load-bearing case the checkpoint brief calls out: a parser that silently returns
        # 0 on every input would pass the empty-ledger test below but must fail THIS one.
        text = (
            "## Candidates\n\n"
            "### First claim\n"
            "- First observed: 2026-08-01 - example-project\n"
            "- Case: something happened\n"
            "- Would live in: CLAUDE.md Working rules\n"
            "- Status: awaiting a second contrasting case\n\n"
            "### Second claim\n"
            "- First observed: 2026-08-10 - example-project\n"
            "- Case: something else happened\n"
            "- Would live in: prompt-lessons\n"
            "- Status: awaiting a second contrasting case\n"
        )
        count, oldest_age = cbr.count_candidates_awaiting(text, self.TODAY)
        self.assertEqual(count, 2)
        # Oldest is 2026-08-01; 17 days before 2026-08-18.
        self.assertEqual(oldest_age, 17)

    def test_empty_ledger_returns_zero_and_no_age(self):
        count, oldest_age = cbr.count_candidates_awaiting("", self.TODAY)
        self.assertEqual(count, 0)
        self.assertIsNone(oldest_age)

    def test_ledger_with_only_origin_logs_returns_zero(self):
        # This is the shape of the REAL file today: two origin logs, zero candidates. An
        # origin-log entry has "Home:"/"Promoted:" fields, never "First observed:", so it must
        # not be miscounted as a candidate.
        text = (
            "## Origin logs\n\n"
            "### A rule's opening words\n"
            "- Home: `~/.claude/CLAUDE.md` section Working rules\n"
            "- Promoted: pre-dates the ledger (externalised 2026-08-18)\n"
            "- Cases:\n"
            "  - a narrative\n"
            "- Boundary: not recorded\n"
        )
        count, oldest_age = cbr.count_candidates_awaiting(text, self.TODAY)
        self.assertEqual(count, 0)
        self.assertIsNone(oldest_age)

    def test_origin_log_with_a_bare_promoted_date_is_still_not_a_candidate(self):
        # A REAL future promotion's "Promoted:" field is a bare date (unlike the two pre-dates-
        # the-ledger entries today), so this is not a contrived edge case -- a detector keyed on
        # "any field with a date" rather than specifically "First observed:" would wrongly count
        # every future origin log as a candidate too.
        text = (
            "### A promoted rule's opening words\n"
            "- Home: somewhere\n"
            "- Promoted: 2026-09-01\n"
            "- Cases: a narrative\n"
        )
        count, oldest_age = cbr.count_candidates_awaiting(text, self.TODAY)
        self.assertEqual(count, 0)
        self.assertIsNone(oldest_age)

    def test_age_is_computed_against_the_injected_today_not_the_real_clock(self):
        text = "### Claim\n- First observed: 2026-01-01 - example-project\n- Status: awaiting\n"
        count, age_far = cbr.count_candidates_awaiting(text, date(2026, 1, 11))
        self.assertEqual((count, age_far), (1, 10))
        count, age_near = cbr.count_candidates_awaiting(text, date(2026, 1, 2))
        self.assertEqual((count, age_near), (1, 1))


# ---------------------------------------------------------------------------
# history CSV: read / previous_reading / upsert
# ---------------------------------------------------------------------------

class TestHistoryCsv(unittest.TestCase):
    def test_read_history_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cbr.read_history(os.path.join(tmp, "nope.csv")), [])

    def test_upsert_creates_file_on_first_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.csv")
            row = {"date": "2026-08-18", "global_claude_bytes": "100",
                   "project_claude_bytes": "200", "memory_index_bytes": "300",
                   "total_bytes": "600", "global_claude_lines": "10"}
            cbr.upsert_reading(path, row)
            rows = cbr.read_history(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-08-18")
            self.assertEqual(rows[0]["total_bytes"], "600")

    def test_same_day_rerun_replaces_not_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.csv")
            row1 = {"date": "2026-08-18", "global_claude_bytes": "100",
                    "project_claude_bytes": "200", "memory_index_bytes": "300",
                    "total_bytes": "600", "global_claude_lines": "10"}
            row2 = dict(row1, total_bytes="700", global_claude_bytes="200")
            cbr.upsert_reading(path, row1)
            cbr.upsert_reading(path, row2)
            rows = cbr.read_history(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["total_bytes"], "700")

    def test_new_day_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.csv")
            row1 = {"date": "2026-08-17", "global_claude_bytes": "100",
                    "project_claude_bytes": "200", "memory_index_bytes": "300",
                    "total_bytes": "600", "global_claude_lines": "10"}
            row2 = dict(row1, date="2026-08-18", total_bytes="650")
            cbr.upsert_reading(path, row1)
            cbr.upsert_reading(path, row2)
            rows = cbr.read_history(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["date"] for r in rows}, {"2026-08-17", "2026-08-18"})


class TestPreviousReading(unittest.TestCase):
    ROWS = [
        {"date": "2026-08-10", "total_bytes": "500"},
        {"date": "2026-08-15", "total_bytes": "550"},
        {"date": "2026-08-16", "total_bytes": "560"},
    ]

    def test_returns_most_recent_row_before_today(self):
        prev = cbr.previous_reading(self.ROWS, "2026-08-18")
        self.assertEqual(prev["date"], "2026-08-16")

    def test_ignores_a_row_dated_today_itself(self):
        rows = self.ROWS + [{"date": "2026-08-18", "total_bytes": "999"}]
        prev = cbr.previous_reading(rows, "2026-08-18")
        self.assertEqual(prev["date"], "2026-08-16")

    def test_no_rows_returns_none(self):
        self.assertIsNone(cbr.previous_reading([], "2026-08-18"))

    def test_all_rows_on_or_after_today_returns_none(self):
        rows = [{"date": "2026-08-18", "total_bytes": "1"},
                {"date": "2026-08-19", "total_bytes": "2"}]
        self.assertIsNone(cbr.previous_reading(rows, "2026-08-18"))

    def test_out_of_order_rows_still_pick_the_latest(self):
        rows = [{"date": "2026-08-16", "total_bytes": "1"},
                {"date": "2026-08-05", "total_bytes": "2"},
                {"date": "2026-08-12", "total_bytes": "3"}]
        prev = cbr.previous_reading(rows, "2026-08-18")
        self.assertEqual(prev["date"], "2026-08-16")


# ---------------------------------------------------------------------------
# End-to-end: build_report / main, entirely on injected tmpdir fixtures
# ---------------------------------------------------------------------------

class TestBuildReportEndToEnd(unittest.TestCase):
    def _write(self, tmp, name, text):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_full_report_over_injected_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            global_claude = self._write(tmp, "global.md", (
                "# User scope\n"
                "- a router bullet\n"
                "\n"
                "# Working rules\n"
                "- clean rule\n"
                "- tagged rule (Provisional -- one case.)\n"
            ))
            project_claude = self._write(tmp, "project.md", "# Example Project\nsome project text\n")
            memory_index = self._write(tmp, "MEMORY.md", "# Memory index\n- one line\n")
            prompt_lessons = self._write(tmp, "prompt-lessons.md", (
                "## Checklist\n"
                "- checklist rule, no marker\n"
                "## Origin log\n"
                "- Date: 2026-07-01 Provisional -- must not be counted, wrong section\n"
            ))
            writing_standing_docs = self._write(tmp, "wsd.md", "- one clean rule\n")
            writing_executor_briefs = self._write(tmp, "web.md", (
                "- rule one (Provisional -- case.)\n- rule two\n"
            ))
            ledger = self._write(tmp, "ledger.md", (
                "## Candidates\n\n### Only claim\n"
                "- First observed: 2026-08-08 - example-project\n"
                "- Status: awaiting a second contrasting case\n"
            ))
            history = os.path.join(tmp, "history.csv")
            existing_row = {"date": "2026-08-16",
                             "global_claude_bytes": "10",
                             "project_claude_bytes": "10",
                             "memory_index_bytes": "10",
                             "total_bytes": "30",
                             "global_claude_lines": "3"}
            cbr.upsert_reading(history, existing_row)

            paths = {
                "global_claude": global_claude,
                "project_claude": project_claude,
                "memory_index": memory_index,
                "prompt_lessons": prompt_lessons,
                "writing_standing_docs": writing_standing_docs,
                "writing_executor_briefs": writing_executor_briefs,
                "ledger": ledger,
                "history": history,
            }
            report = cbr.build_report(paths, date(2026, 8, 18))

            # Candidates: one entry, 10 days old (2026-08-08 -> 2026-08-18).
            self.assertEqual(report["n_candidates"], 1)
            self.assertEqual(report["oldest_age_days"], 10)

            # Marker counts: global (1/2 in Working rules, router bullet excluded),
            # prompt-lessons (0/1 -- the Origin log section's Provisional must not count),
            # writing-standing-docs (0/1), writing-executor-briefs (1/2). Total 2/6.
            self.assertEqual(report["total_rules"], 6)
            self.assertEqual(report["total_marked"], 2)
            counts_by_label = {label: (n, m) for label, n, m in report["home_counts"]}
            self.assertEqual(counts_by_label["~/.claude/CLAUDE.md § Working rules"], (2, 1))
            self.assertEqual(counts_by_label["prompt-lessons.md § Checklist"], (1, 0))

            # Bytes: computed from the actual fixture file contents, not hardcoded.
            with open(global_claude, encoding="utf-8") as f:
                expected_global_bytes = len(f.read().encode("utf-8"))
            self.assertEqual(report["global_bytes"], expected_global_bytes)
            self.assertEqual(
                report["total_bytes"],
                report["global_bytes"] + report["project_bytes"] + report["memory_bytes"])

            # Delta against the pre-seeded 2026-08-16 row.
            self.assertIsNotNone(report["previous_reading"])
            self.assertEqual(report["previous_reading"]["date"], "2026-08-16")

            text_report = cbr.format_report(report)
            self.assertIn("2026-08-16", text_report)
            self.assertIn("1 candidate(s), oldest 10 day(s) old", text_report)
            # Delta must be CURRENT minus PREVIOUS (growth is positive), not the other way
            # round -- the previous reading's total_bytes was seeded at 30, well below any
            # real file's size, so the sign is unambiguous.
            expected_delta = report["total_bytes"] - 30
            self.assertGreater(expected_delta, 0)
            self.assertIn(f"+{expected_delta:,} since 2026-08-16", text_report)

    def test_missing_ledger_and_history_are_treated_as_empty_not_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            global_claude = self._write(tmp, "global.md", "# Working rules\n- a rule\n")
            paths = {
                "global_claude": global_claude,
                "project_claude": os.path.join(tmp, "does-not-exist-project.md"),
                "memory_index": os.path.join(tmp, "does-not-exist-memory.md"),
                "prompt_lessons": os.path.join(tmp, "does-not-exist-pl.md"),
                "writing_standing_docs": os.path.join(tmp, "does-not-exist-wsd.md"),
                "writing_executor_briefs": os.path.join(tmp, "does-not-exist-web.md"),
                "ledger": os.path.join(tmp, "does-not-exist-ledger.md"),
                "history": os.path.join(tmp, "does-not-exist-history.csv"),
            }
            report = cbr.build_report(paths, date(2026, 8, 18))
            self.assertEqual(report["n_candidates"], 0)
            self.assertIsNone(report["oldest_age_days"])
            self.assertIsNone(report["previous_reading"])
            self.assertEqual(report["project_bytes"], 0)
            # Must not raise -- absence of the ledger/history is normal, not a fault.
            cbr.format_report(report)

    def test_main_writes_history_and_exits_zero_even_when_marked_rules_exist(self):
        # Exercises main()'s own argv wiring and confirms the report-never-gates contract: a
        # nonzero Provisional count must not turn into a nonzero exit code.
        with tempfile.TemporaryDirectory() as tmp:
            global_claude = self._write(tmp, "global.md", (
                "# Working rules\n- tagged rule (Provisional -- one case.)\n"))
            project_claude = self._write(tmp, "project.md", "text\n")
            memory_index = self._write(tmp, "mem.md", "text\n")
            prompt_lessons = self._write(tmp, "pl.md", "## Checklist\n- rule\n")
            wsd = self._write(tmp, "wsd.md", "- rule\n")
            web = self._write(tmp, "web.md", "- rule\n")
            ledger = self._write(tmp, "ledger.md", "")
            history = os.path.join(tmp, "history.csv")

            argv = [
                "context_budget_report.py",
                "--global-claude", global_claude,
                "--project-claude", project_claude,
                "--memory-index", memory_index,
                "--prompt-lessons", prompt_lessons,
                "--writing-standing-docs", wsd,
                "--writing-executor-briefs", web,
                "--ledger", ledger,
                "--history", history,
                "--today", "2026-08-18",
            ]
            old_argv = cbr.sys.argv
            cbr.sys.argv = argv
            try:
                with self.assertRaises(SystemExit) as ctx:
                    cbr.main()
                self.assertEqual(ctx.exception.code, 0)
            finally:
                cbr.sys.argv = old_argv

            rows = cbr.read_history(history)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-08-18")


if __name__ == "__main__":
    unittest.main()

```

---

## SKILL.md

### File: ~/.claude/skills/finalise/SKILL.md

Apply the path/authorization substitutions from the instructions above while writing this out —
the text below is the SOURCE version, shown so nothing is lost, not the literal target content.

```markdown
---
name: finalise
description: Session-close doc review — captures decisions, fixes and lessons into decisions.md and memory before context clears.
disable-model-invocation: true
---

# /finalise — session close doc-review

Run this at the end of any session to capture decisions and record any doc/memory
updates that are needed before clearing context.

## Paths used in this skill

- `<project root>` — the repo this session is working in (its git top-level directory).
- `<memory dir>` — this project's auto-memory directory: take `<project root>`'s absolute path
  and replace every `/` with `-`; the directory is `~/.claude/projects/<that string>/memory/`.

## What to do

**Every file this skill writes gets committed immediately, not batched at the end — write and
commit together, at each step below that writes something.** Two repos are in play: `<project
root>` (decisions.md, backlog.md) and `~/.claude` (CLAUDE.md, prompt-lessons.md,
writing-standing-docs.md, writing-executor-briefs.md, lesson-candidates.md,
under-explained-cases.md). Commit in whichever repo the file lives in. **Ask before pushing
either repo** — don't assume push is pre-authorized; that's a per-machine decision the user makes
explicitly, not a default. A push can't be scoped to one subdirectory either (it sends the whole
branch), which is a second reason to confirm rather than assume before pushing `~/.claude`.

**`<memory dir>` is never committed — confirm this before assuming otherwise, don't re-derive
it.** `~/.claude`'s own `.gitignore` blanket-excludes everything under `projects/` (transcripts +
auto-memory), with no exception carved out for the memory directory the way one exists for
`lesson-candidates.md` or `under-explained-cases.md`. `git add` on a memory file fails loudly
(`ignored by one of your .gitignore files... Use -f if you really want to add them`) rather than
silently no-op-ing. So every memory write this skill makes (a new memory file, an edited one, a
`MEMORY.md` index line) persists to disk only; skip the commit for those and don't report them as
committed in step 7.

1. **Sweep the session conversation** for any of the following:
   - Architectural or workflow decisions (why X was chosen over Y, tradeoffs accepted)
   - Resolved bugs or surprising fixes (root cause + fix approach worth remembering)
   - New patterns, tools, or behaviours discovered
   - Anything that contradicts or supersedes an existing memory
   - Feedback the user gave about approach, tone, or process
   - **Thread state** — did this session close or advance a thread? Open threads live in
     `<project root>/backlog.md` (canonical, git-tracked; task numbers are stable and cited by
     `decisions.md`, so never renumber). The bullets above are all knowledge-shaped, so
     completed work otherwise produces no candidate. If a thread is done, replace its Open
     entry with a **one-liner** under that file's Closed section (date, task number, title,
     commit, `decisions.md` pointer if it has rationale) — the stub is what keeps
     `decisions.md`'s task-number citations resolvable. If a thread was **advanced but not
     closed**, update its entry **in place** — name what shipped (with the commit) and what is
     left. A thread whose scope or blocker changed is advanced, not untouched. Don't leave the
     build narrative filed under either heading, and don't re-narrate it in memory.
   - **Under-explained moments** — any point where the user had to ask what something meant
     because a sentence leaned on a code symbol they'd have needed to open a file to decode.
     Append each to `~/.claude/under-explained-cases.md` (that file carries the schema and the
     evaluation protocol), then commit it (see the commit note above). **This capture is
     automatic — do NOT route it through step 3's approval flow**; an entry records what was
     said, not what should be instructed. Any *rule change* derived from the corpus is a normal
     candidate and does go through step 3.
     **Under-count deliberately.** A user probing mechanics constantly is them working, not a
     failure: "tell me more about X" is not a case, "what is X?" after it was used as though they
     already knew it is. Flag only the unambiguous ones. A few real cases are worth more for
     tuning the rule than many noisy ones, and a noisy corpus would drive changes off bad
     evidence. When the file reaches ~10 entries, propose a re-evaluation of the
     `~/.claude/CLAUDE.md` § Working rules bullet it serves.
   - **Prompt-lesson opportunities**: moments where discussion arrived at a sharper,
     *generalisable* approach than the original prompt asked for or than was done intuitively —
     a reusable rule, not a project-specific fact. Routing test:
     (a) generalisable? — if it only makes sense in this project, it's a memory or decisions.md
     candidate instead; (a2) **is it a rule yet?** — one real case is a candidate, not a rule:
     append it to `~/.claude/lesson-candidates.md`, commit it (see the commit note above), and
     write nothing to a rules file. Only a
     candidate whose second, contrasting case has now arrived is promoted, and the promotion
     writes the rule to its home with both cases logged in the ledger. **An amendment that
     sharpens an existing rule needs its own second case** — it does not inherit the base
     rule's maturity; (b) who's the actor? — four user-scope homes, per the routing test in
     `~/.claude/CLAUDE.md`'s header: the user authoring a prompt/brief → `prompt-lessons.md`; the
     agent editing a standing doc or memory → `~/.claude/writing-standing-docs.md`; the agent
     briefing an executor or verifying its checkpoint →
     `~/.claude/writing-executor-briefs.md`; the agent at
     any other moment → `~/.claude/CLAUDE.md` § Working rules. An amendment re-derives its home
     rather than inheriting the home of the rule it extends; (c) split, don't dual-write — a
     candidate can have BOTH a generalisable core and a project-specific residue; if (and only
     if) the residue isn't already recorded in the repo, route each part to its own home: the
     general rule to its user-scope home, the residue to memory/decisions.md with a one-way
     reference naming the lesson tag (e.g. "generalised as prompt-lessons [tag]").
     prompt-lessons.md carries no links to *project* files — its origin log names the project as
     prose — but it does point to the other three user-scope homes when a rule's operative clause
     lives there, with the origin log staying canonical for rationale. Never write the full
     candidate in two homes — that's the restatement-drift the canonical-plus-pointers lesson
     exists to prevent.

2. **Cross-check each against the existing docs:**
   - `~/.claude/lesson-candidates.md` — **check this first, and check it for every candidate.**
     A first case is already parked here for many of them; if today's case is the *second,
     contrasting* one, the outcome is a promotion, not a new entry. Nothing else performs this
     match, so skipping it leaves the pair unnoticed and the gate never opens. Aging of
     long-waiting candidates is not this step's job — `/memory-audit` owns that.
   - `<project root>/decisions.md` — any architectural/workflow decision with a rationale
   - `<memory dir>/MEMORY.md` — index of all memories
   - Relevant individual memory files (read them if the index entry suggests a match)
   - `~/.claude/prompt-lessons.md` — for prompt-lesson candidates: skip anything an existing
     checklist rule already covers; a candidate that *sharpens* an existing rule proposes an
     amendment to it, not a duplicate entry
   - `~/.claude/writing-standing-docs.md` — **read before writing any approved candidate**;
     it carries the operative rules for editing standing docs and memory bodies
     (contract-vs-snapshot, canonical-plus-pointers, replace-not-join, audience-referent)

3. **Propose each candidate one at a time — write nothing until the user approves it.**
   Build the list of undocumented decisions/updates from steps 1-2.

   **Then triage it — most of it should not reach the user.** For each candidate, name the future
   moment that goes differently because this was written down. If you can't name one, drop it;
   "they'd be marginally better informed" is not one. **Most sessions produce none, and that is
   the expected outcome rather than a failed sweep. This is a bar, not a quota** — a genuinely
   consequential session can yield several, and dropping a real one to hit a number is the same
   mistake inverted. Having a valid home is not the same as being worth a decision: steps 1-2
   settled *where* a candidate goes, and a candidate can pass that and still fail here.

   Then go through what survives sequentially, one candidate per turn. The entire candidate lives
   INSIDE a single `AskUserQuestion` call — never present it as prose and then ask in the same
   turn (many clients collapse same-turn prose before a question; see prompt-lessons
   `one-decision-at-a-time`):
   - **The question field opens with these labelled lines, in this order, with nothing before
     them:**

         File:     <exact path this candidate would write to>
         Problem:  <what goes wrong, plainly — one or two sentences>
         Proposal: <what the new text would do about it>
         Actor:    <who performs the action this candidate governs> → <that actor's home>
         Evidence: <how many real cases> — rule-shaped candidates only; a single case is
                   written "provisional — single observed case", since once is
                   untested-but-plausible (the second-real-example lesson)

     `File:` leads because the point of the format is that the user never has to go looking for
     where a candidate lands. When `File:` and the actor's home disagree, the routing is wrong
     — settle that before asking. Some candidates are two writes and `File:` names both: a new
     memory needs its own file *and* a `MEMORY.md` index line, and a
     `~/.claude/prompt-lessons.md` entry needs one checklist line *and* one origin-log entry
     ending with a prompt-writing consequence, per that file's own header rules.
   - **Write `Problem:` so it survives having every identifier struck out.** Delete the task
     numbers, keys, filenames, function and column names from your own sentence; if what
     is left no longer says what goes wrong, the identifiers were carrying the meaning and the
     line needs rewriting. Keep them as trailing pointers, never as the subject. **This is
     stricter than `~/.claude/CLAUDE.md`'s general version, which exempts project jargon** —
     that exemption assumes a reader holding the session in mind, and at session close the user
     is triaging a queue drawn from hours of work. Brief and high-level beats precise and dense;
     the exact wording sits in the preview pane either way.

     Worked pass (a fix that corrected how one status label was interpreted):

         File:     <project root>/decisions.md
         Problem:  One data source labels an item with a word our code reads as "not available
                   yet", so we discarded real, valid results under that label for weeks.
         Proposal: Record why the fix was a narrow, source-specific exception rather than a
                   stricter shared rule — a second source uses a near-identical label for a
                   genuinely different state, so tightening the shared pattern would have broken
                   that one.
         Actor:    the agent recording a shipped fix → decisions.md

     The rejected first draft of that `Problem:` line named the specific function, tag string,
     and field it touched — accurate, and it said nothing at all once the identifiers were
     struck out.
   - **`Actor:` is stated as a fact, never argued.** Write who performs the action, not a
     defence of the destination: "who performs the action this rule governs?" has an answer
     that doesn't depend on where you've already decided to file it, whereas "why does this
     belong in X?" takes X as given and invites you to argue for it. **Amendments state it
     too** — an amendment re-derives its home, it does not inherit the home of the rule it
     extends. Omitting the line is not permitted; if the actor is genuinely unclear, say so in
     the line and let the user decide.
   - The apply option's `preview` pane carries the exact text you'd write. Option labels say
     what will happen (apply / reject), not what the candidate is — the question field has
     already said that. One apply/reject question per candidate — never batch candidates.
   - Only if a candidate is too large for a preview pane: two-turn split — full context as
     prose ending the turn, closing with "I'll need your decision on how to proceed. Tell me
     when you're ready.", then the bare question next turn.
   - If applied: write it immediately (append to `decisions.md`, or create/update the memory
     file + index line per the memory-writing convention), commit it if it's not a
     memory-directory write (see the commit note above), then move to the next candidate. When
     updating any standing doc, re-read the
     enclosing section afterwards and remove wording the new text supersedes (prompt-lessons
     `replace-not-join`).
   - If rejected: skip it — don't write it anywhere, don't log the rejection, just move on.
   - If there are zero candidates, say so and skip straight to step 4.

4. **Reconcile work-tracking state that `/clear` will destroy.** Session state is not a save,
   and a doc that *points at* session state saves the pointer, not the content.
   - **If this session tracked any outstanding work outside `<project root>/backlog.md`, move it
     there now.** That means a harness task list, a numbered plan held only in conversation, a
     "still to do" list written into a message — anything a reader could mistake for a record.
     Every item must end up under Open or Closed; anything that exists only in session state is
     unsaved work, so propose it exactly as step 3 does, one candidate per turn with the text in
     the preview. **State what you checked and what you found, including "nothing outside the
     backlog" — silence here is indistinguishable from not looking.**
     (A skill step rather than a hook because this state is held in the session, not on disk —
     no script can read it.)
   - Check the session scratchpad directory for work-product rather than throwaway — a plan, a
     measurement, a recovered list. Propose moving it into the repo, or state that it's
     disposable.
   - **Never close a gap by writing a pointer.** "See the task list" / "sub-threads are tracked
     elsewhere" is the failure, not the fix: the durable file must carry the content.
   Applies to any future volatile surface, not just these two — the test is "does this survive
   `/clear`?", asked of anything that records outstanding work.

5. **Run the deterministic checks** — three scripts; one gates, two report:
   - `python3 ~/.claude/skills/finalise/scripts/check_memory_index.py <memory dir> <project root>`
     It checks the "every memory file ↔ exactly one MEMORY.md index line" invariant
     deterministically (this used to rely on the writer remembering it), reports MEMORY.md
     against its load limits — only the first 200 lines **or 25 KB, whichever comes first**, is
     loaded at session start; the rest is silently dropped (**bytes bind first here**, long index
     lines, so watch that percentage, not the line count) — then resolves every `[[link]]`
     citation against the memory dir's filenames: inside memory-file bodies, and inside every
     `*.md` in the repo. Citations inside code spans and fenced blocks are
     ignored, so writing about the syntax never trips it. All of it gates: non-zero exit = fix
     the listed mismatches, over-limit bytes, or dangling citations now, before ending the
     session, then re-run it.
   - `python3 ~/.claude/skills/finalise/scripts/check_thread_state.py --repo <project root>
     --backlog <project root>/backlog.md --memory-dir <memory dir>`
     It **reports and never gates — it always exits 0**. It prints four sections: task refs found
     in recent commits against each task's current `backlog.md` section, declared `blocked by #N`
     dependencies for review, `Next up` block staleness (date + commits since), and task-number
     collisions with retired-scheme memory citations (split into a live-task bucket that needs a
     decision and a "resolves to a Closed stub — expected" bucket that doesn't). **Every flagged
     task requires an explicit response — "still correct" is a valid response, silence is not.**
     That requirement is the forcing function here, chosen deliberately instead of a non-zero
     exit: a crying-wolf gate on a heuristic just trains the reader to ignore it. Skip this step
     if `<project root>/backlog.md` doesn't exist yet.
   - `python3 ~/.claude/skills/finalise/scripts/context_budget_report.py --project-claude
     <project root>/CLAUDE.md --memory-index <memory dir>/MEMORY.md --ledger
     ~/.claude/lesson-candidates.md --prompt-lessons ~/.claude/prompt-lessons.md
     --writing-standing-docs ~/.claude/writing-standing-docs.md --writing-executor-briefs
     ~/.claude/writing-executor-briefs.md --history <project root>/context_budget_log.csv`
     It **reports and never gates — it always exits 0**, and writes one row to
     `<project root>/context_budget_log.csv` per calendar day. Prints: lesson candidates in
     `~/.claude/lesson-candidates.md` awaiting a second case (count + oldest age in days);
     rules across the four user-scope homes still carrying a "Provisional" single-case marker;
     per-file and total bytes of the three always-loaded surfaces (`~/.claude/CLAUDE.md`,
     `<project root>/CLAUDE.md`, `MEMORY.md`); and the total's delta against the previous logged
     reading. **The only threshold anywhere in this check is MEMORY.md's existing 200-line /
     25,600-byte limit** (enforced above, by `check_memory_index.py` — this script reports its
     bytes but does not re-gate them). Neither CLAUDE.md has a documented cap, so this never
     flags a number against one; it's a growth log, not a budget check, until the user picks a
     line from the observed range.

6. **Write/replace the `Next up` block in `backlog.md`.** The live block at the top of that file
   (after the intro, before `## Open`) is the worked example of the shape — read it rather than
   restating the template here; two copies of one format is a drift site. Requirements: name 1–3
   threads, each with a one-line rationale for why it is next; list decisions awaiting the user;
   carry today's date and a basis line (commits through, Open threads as of); and **replace the
   block in full, never append** — appending turns it into the append-only ledger this file
   exists to avoid. Commit it (see the commit note above) — this is a `<project root>` write,
   push included once you've confirmed pushing is wanted. Skip this step if `backlog.md` doesn't
   exist yet.

7. **Report what you did** — list each candidate and its outcome (applied + file touched, or
   rejected), the reconcile result from step 4, the results of all three step-5 checks (the
   index-check result; the thread-state report together with your response to each flagged
   task; and the context-budget report), and the `Next up` block written in step 6. **Confirm every
   non-memory write from this run was committed** (`git status` in both repos, not just recall),
   name any memory-directory writes as filesystem-only per the commit note above, and state each
   repo's push status — pushed, or left uncommitted/unpushed for the user, per what they said
   this run.

## What NOT to record

- Ephemeral task detail (specifics checked, values found during routine work)
- Things already in decisions.md or memory with no new information
- Code patterns or file structure (derivable from the codebase)
- Git history (already in commits)
- Mis-routed lessons — a prompt-lessons entry must both transfer to unrelated projects AND be
  about **the user authoring** a prompt or brief. Doesn't transfer → memory/decisions.md.
  Transfers but governs the agent editing a standing doc → `~/.claude/writing-standing-docs.md`.
  Transfers but governs the agent briefing an executor or verifying its checkpoint →
  `~/.claude/writing-executor-briefs.md`. Transfers and governs the agent at any other moment →
  `~/.claude/CLAUDE.md` § Working rules. (All four user-scope files are written ONLY on the
  user's explicit approval, same as every other candidate.)

## Scope

Only this session's context — not a full audit of all docs. The goal is to capture
what would otherwise be lost when the context window clears.

```

---

## Hook

### File: ~/.claude/hooks/remind_finalise.py

```python
#!/usr/bin/env python3
"""PostToolUse hook: remind to run /finalise after any git commit."""
import json, re, sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")
if not (re.search(r'\bgit\b', cmd) and re.search(r'\bcommit\b', cmd)):
    sys.exit(0)

print("REMINDER: run /finalise before clearing this session to capture any undocumented decisions.")

```

### File: ~/.claude/hooks/test_remind_finalise.py

```python
#!/usr/bin/env python3
import json, os, subprocess, sys, unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remind_finalise.py")

def _run(cmd):
    payload = json.dumps({"tool_input": {"command": cmd}})
    r = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode

class TestRemindFinalise(unittest.TestCase):
    def test_fires_on_git_commit(self):
        out, code = _run("git -C /some/project commit -F /tmp/msg.txt")
        self.assertIn("/finalise", out)
        self.assertEqual(code, 0)

    def test_silent_on_git_push(self):
        out, code = _run("git -C /some/project push")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_silent_on_python(self):
        out, code = _run("python3 /some/project/scripts/run_report.py")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_silent_on_grep(self):
        out, code = _run("grep -n 'TODO' /some/project/scripts/run_report.py")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

if __name__ == "__main__":
    unittest.main()

```

---

## settings.json addition

Add this object as an entry inside the top-level `PostToolUse` array in `~/.claude/settings.json`
(create the array, or the whole file, if it does not exist yet):

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "type": "command",
      "command": "~/.claude/hooks/remind_finalise.py",
      "timeout": 5
    }
  ]
}
```

Note: expand `~` to the actual home directory path in the written file if this Claude Code
version does not do `~`-expansion in settings.json commands itself — check how other existing
hook entries in the file (if any) reference their own script paths and match that convention.
