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
     this script.
  4. Every `[[link]]` inside the repo's Markdown docs (DOCS_ROOT, recursive, `*.md` only)
     resolves the same way. Reference docs, decisions.md and backlog.md cite memories in the
     same `[[name]]` syntax but were never checked (backlog #39) -- a dead citation there is
     load-bearing for whatever claim it was supposed to source. Fenced code blocks and inline
     code spans are stripped first, length-preserving so reported line numbers stay correct: a
     backticked `` `[[link]]` `` is prose ABOUT the syntax, not a citation, and matching it would
     produce false hard failures on a check that is only permitted to gate because link
     resolution is exact.

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

# A project with no prior Claude Code session here yet -- e.g. right after
# /bootstrap-project, before /finalise has ever run -- has no memory dir at all. That's
# normal, not a fault: nothing to index yet, so there is nothing this check can fail on.
if not os.path.isdir(MD) or not os.path.isfile(os.path.join(MD, "MEMORY.md")):
    print(f"no memory index yet at {MD} -- skipping memory-index check "
          f"(normal before the first /finalise run in this project)")
    sys.exit(0)

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
# There is no exemption for a retired memory's name: when a memory is removed, links to it are
# resolved at the time (made plain text, or repointed where the content really moved).

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


_LINK_RE = re.compile(r"\[\[([A-Za-z0-9][A-Za-z0-9_.-]*)\]\]")
# A real citation target is an identifier-shaped slug (kebab-case, always -- see the memory
# system's own naming convention). Requiring that shape, rather than "any run of non-]/|
# characters", is what excludes unfenced bash test syntax like `[[ -f "$x" ]]` from being read
# as a citation: it starts with a space, not a word character, so it never matches at all.
# (Confirmed live: the old pattern captured ' -f "$x" ' as a dangling-link target from a doc
# containing that exact bash snippet outside a code fence.)

link_problems = []
for fname in sorted(files):
    with open(os.path.join(MD, fname), encoding="utf-8") as f:
        raw = f.read()
    body = _strip_code(raw)
    for m in _LINK_RE.finditer(body):
        target = m.group(1).strip()
        if (target + ".md") in files or (target + ".md") == "MEMORY.md":
            continue
        link_problems.append(f"{fname}: dangling [[{target}]] (no {target}.md on disk)")

if link_problems:
    print(f"DANGLING [[link]] TARGETS ({len(link_problems)} problem(s)):")
    for p in sorted(link_problems):
        print(f"  - {p}")
    sys.exit(1)

print(f"[[link]] check: {len(files)} files scanned, all links resolve")

# Doc-scope [[link]] check. Same citation syntax and same slug set (files) as above, but scanning the repo's Markdown docs instead of the
# memory dir -- reference docs, decisions.md and backlog.md cite memories in [[name]] form too.
# Runs after the memory-file link check above, keeping the same stop-at-first-failure sequencing
# (a failure above exits before this code ever runs).
DOCS_ROOT = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules",
    # Common vendored/build-output directory names across ecosystems (Python virtualenvs,
    # Go/PHP/Ruby vendor dirs, JS/Rust/Java build output, Python packaging metadata) -- a big
    # vendored tree's own .md files (READMEs etc, using unrelated double-bracket syntax) can trip
    # this check on files that were never this project's own. Deliberately a fixed,
    # dependency-free name list rather than deriving exclusions from .gitignore: many projects
    # using this script won't have git set up yet -- running this workflow is often what prompts
    # setting git up in the first place -- so a git-dependent check would silently do nothing in
    # exactly that case, the opposite of a safe fallback.
    "vendor", "venv", ".venv", "dist", "build", "site-packages", "__pypackages__",
}
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

doc_link_problems = []  # list of (relpath, line, target)
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
        doc_link_problems.append((relpath, line, target))

if doc_link_problems:
    print(f"DANGLING [[link]] TARGETS IN DOCS ({len(doc_link_problems)} problem(s)):")
    for relpath, line, target in sorted(doc_link_problems):
        print(f"  - {relpath}:{line}: dangling [[{target}]] (no {target}.md on disk)")
    sys.exit(1)

print(f"[[link]] check (docs): {doc_citation_count} citation(s) in "
      f"{len(doc_files_with_citations)} file(s), all resolve")

