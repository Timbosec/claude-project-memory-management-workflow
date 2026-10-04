#!/usr/bin/env python3
"""Thread-state heuristics for /finalise.

Reports -- never gates (exit 0 always, even when it flags things). Unlike
check_memory_index.py's index-sync/size checks, this is a heuristic, not an
invariant: a task can legitimately be referenced by a commit that needed no
backlog.md change. A non-zero exit would cry wolf and train the reader to ignore
it. The forcing function is the /finalise skill step requiring an explicit
per-task response, not the exit code.

Three report sections:
  1. Task refs in recent commits vs. their current backlog.md section, split
     into OUTSTANDING and RECONCILED around the newest commit that actually
     reconciled each task. A commit reconciles task N only if all three hold:
     it references N (guaranteed -- that is why it is in this task's commit
     list), it modified backlog.md, AND it modified TASK N's OWN entry
     specifically (body text or section changed between the commit and its
     parent). Touching the file is not enough: a commit can touch backlog.md
     and mention two tasks while only adding a new, third task's section, and
     treating it as a reconciler for either of the two would silently clear
     their genuinely-outstanding references. Walk each task's referencing
     commits NEWEST-FIRST and take the first (i.e. newest) one that modified
     that task's own entry; if a touching commit mentions the task but did NOT
     modify its entry, keep looking at older commits rather than stopping --
     do not let the newest touching commit win by default. Once found (at
     index i in the newest-first list): every non-touching commit newer than
     it (index < i) is OUTSTANDING; every non-touching commit older than it
     (index > i) is RECONCILED and collapsed to one summary line, never
     silently dropped. No reconciler found -> every non-touching commit is
     OUTSTANDING. An earlier miss is never masked by a later, unrelated touch
     -- see
     TestTouchedBacklogFlag.test_an_earlier_miss_is_not_masked_by_a_later_touch
     in test_check_thread_state.py.
  2. Declared blockers: any Open task whose body contains "blocked by #N",
     printed with #N's current section for human review. This is what surfaces a
     blocking task quietly going stale without anyone noticing.
  3. Next-up staleness: how many commits have landed since backlog.md's "Next up"
     block was written. Counted after the commit its basis line names ("Basis:
     commits through `<hash>`"), not counting commits that only rewrote the block
     itself -- the basis can never name the commit that writes the block, so
     without that exclusion the count would never read 0. Falls back to counting
     from midnight of the block's date when the basis line names no commit, or
     names one this repo's history doesn't have.

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
    find_declared_blockers/find_next_up_date/
    find_next_up_basis/is_next_up_only_rewrite/build_report
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
  - Offline. Git and backlog.md only, no network.
"""
import argparse
import os
import re
import subprocess
import sys
from collections import namedtuple

DEFAULT_REPO = os.getcwd()
DEFAULT_BACKLOG = os.path.join(DEFAULT_REPO, "backlog.md")
DEFAULT_DAYS = 14

Commit = namedtuple("Commit", "hash date subject body files")

# --- commit-message ref-extraction patterns (section 1: task refs) ------------

_REF_HASH_RE = re.compile(r'#(\d+)')
_REF_TASK_RE = re.compile(
    r'\btasks?\s+(\d+(?:\s*(?:,|and)\s*\d+)*)', re.IGNORECASE)
_NUM_RE = re.compile(r'\d+')

# --- backlog.md structure ------------------------------------------------------

_TASK_HEADER_RE = re.compile(r'^###\s+#(\d+)\b')
# Closed one-liners use TWO shapes in practice: '· **#1** ...' (bold) and
# '· #30 ...' (bare) -- both right after the date's middle-dot separator.
_CLOSED_BULLET_RE = re.compile(r'·\s*\*{0,2}#(\d+)')
_BLOCKED_BY_RE = re.compile(r'blocked by #(\d+)', re.IGNORECASE)
_NEXT_UP_DATE_RE = re.compile(
    r'^##\s+Next up\s*—\s*recommended\s+(\d{4}-\d{2}-\d{2})',
    re.MULTILINE)
_NEXT_UP_BASIS_RE = re.compile(r'Basis:\s*commits through\s*`([0-9a-f]{7,40})`')


def extract_numeric_refs(text):
    """Every task-shaped number reference in a COMMIT message: '#N' and
    'task(s) N[, M and P...]'. Used for section 1 (commit refs) via
    extract_task_refs."""
    nums = set()
    for m in _REF_HASH_RE.finditer(text):
        nums.add(int(m.group(1)))
    for m in _REF_TASK_RE.finditer(text):
        for n in _NUM_RE.findall(m.group(1)):
            nums.add(int(n))
    return nums


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
    """The YYYY-MM-DD date on the 'Next up' block's heading, or None if there
    is no block."""
    m = _NEXT_UP_DATE_RE.search(backlog_text)
    return m.group(1) if m else None


def split_next_up(backlog_text):
    """(block, rest): the 'Next up' block -- its heading line up to, not
    including, the next '## ' heading -- and the file with that block cut out.
    ('', backlog_text) when there is no block."""
    m = _NEXT_UP_DATE_RE.search(backlog_text)
    if not m:
        return "", backlog_text
    start = m.start()
    nxt = re.search(r'^## ', backlog_text[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(backlog_text)
    return backlog_text[start:end], backlog_text[:start] + backlog_text[end:]


def find_next_up_basis(backlog_text):
    """The commit hash the 'Next up' block's basis line names ("Basis: commits
    through `<hash>`"), or None if there is no block, no basis line, or the
    line names no commit (a new project's template reads `<none yet>`). Only
    the block itself is searched."""
    block, _ = split_next_up(backlog_text)
    m = _NEXT_UP_BASIS_RE.search(block)
    return m.group(1) if m else None


def is_next_up_only_rewrite(files, old_backlog, new_backlog):
    """True if a commit did nothing but rewrite the 'Next up' block: backlog.md
    is the only file it touched and everything outside the block is identical,
    so the block is what changed. Such a commit is the block being written, not
    work that makes it stale. None for either text (backlog.md absent at that
    revision) is never a rewrite."""
    if set(files) != {"backlog.md"} or old_backlog is None or new_backlog is None:
        return False
    return split_next_up(old_backlog)[1] == split_next_up(new_backlog)[1]


# --- I/O at the edges -----------------------------------------------------

_COMMIT_SEP = "\x01COMMIT\x01"
_BODY_SEP = "\x01BODY\x01"
_FILES_SEP = "\x01FILES\x01"


def is_git_repo(repo_dir):
    """True if `repo_dir` is inside a git work tree. A project with no git history at all is a
    supported state (a scratch directory, or a project the user hasn't put under git), and
    sections 1 and 3 are git-derived -- so main() checks this and skips rather than letting
    `git log` raise. Uses git's own answer rather than looking for a `.git` entry, because a
    worktree or submodule has a `.git` FILE, and a subdirectory of a repo has no `.git` at all
    yet is still in the work tree."""
    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def has_commits(repo_dir):
    """True if `repo_dir` has at least one commit reachable from HEAD. Separate from
    is_git_repo on purpose: a freshly `git init`-ed repo IS a work tree, so is_git_repo
    correctly answers True, but `git log` still fails there ("your current branch does not
    have any commits yet") and run_git_log uses check=True. That state is what
    /bootstrap-project leaves behind, since it writes backlog.md/decisions.md/CLAUDE.md and
    then asks before committing -- so the first /finalise in a newly bootstrapped project hits
    it unless the user committed in between."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    return proc.returncode == 0


def run_git_log(repo_dir, days):
    """Real commits from `repo_dir`'s history over the last `days` days,
    newest-first (git log's default order), each with its subject, body and
    the list of files it touched. Callers must have established that repo_dir
    is a git repo with commits (see is_git_repo and has_commits) -- git's own
    failure here is left to raise, since at that point it means something other
    than "no repo" or "no commits yet"."""
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
    from the CURRENT clock, so a bare '--since=2026-08-09' run at 11:15 means
    "since 11:15 that day", not midnight. Pinning to midnight over-counts within
    the block's own authoring day (it includes commits made earlier that same
    day, before the block was written) -- accepted deliberately: the block
    records a date with no time, so an exact answer isn't available, and
    over-counting fails loudly (an inflated-but-visible number) while
    under-counting fails silently (a staleness count that quietly reads low
    forever). Do not invent a timestamp format for the 'Next up' block to make
    this exact. Used only as the fallback when the block's basis line names no
    usable commit -- see count_commits_after_basis."""
    proc = subprocess.run(
        ["git", "log", f"--since={date_str}T00:00:00", "--oneline"],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    )
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return len(lines)


def count_commits_after_basis(repo_dir, basis):
    """(counted, skipped) for commits after `basis` up to HEAD: `skipped` is
    how many only rewrote the 'Next up' block (see is_next_up_only_rewrite)
    and `counted` is the rest. None if `basis` is not a commit in this repo's
    history (a typo, or history rewritten since the block was written), so the
    caller can fall back to the date. A failure reading a commit's backlog.md
    counts that commit rather than skipping it: over-counting shows up,
    under-counting doesn't."""
    proc = subprocess.run(
        ["git", "log", "--format=" + _COMMIT_SEP + "%n%H", "--name-only",
         f"{basis}..HEAD"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    counted = skipped = 0
    for chunk in proc.stdout.split(_COMMIT_SEP)[1:]:
        lines = [l for l in chunk.splitlines() if l.strip()]
        commit_hash, files = lines[0], lines[1:]
        try:
            rewrite = is_next_up_only_rewrite(
                files,
                _git_show(repo_dir, f"{commit_hash}^", "backlog.md"),
                _git_show(repo_dir, commit_hash, "backlog.md"),
            ) if set(files) == {"backlog.md"} else False
        except RuntimeError:
            rewrite = False
        if rewrite:
            skipped += 1
        else:
            counted += 1
    return counted, skipped


# --- did_modify_entry: git-backed, used only by main() ----------------------
#
# build_report needs to know whether a commit modified a SPECIFIC task's own
# backlog.md entry, not just the file. That requires git (diff against the
# parent revision), so it is kept out of build_report entirely and injected
# as a callable -- see the module docstring's "Design constraints" section
# for the edge cases handled here.

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

def build_report(backlog_text, commits, did_modify_entry):
    """Pure (git-free): assemble the report sections from already-loaded
    inputs plus an injected did_modify_entry(commit_hash, task_no) -> bool
    (see make_did_modify_entry above; tests supply a fixture lambda). Returns
    a dict; main() decides how to print it. Section 3 is built separately, by
    next_up_staleness, because it needs git commit counts.

    Section 1 partitions each task's commits (task_refs[num], newest-first)
    around the newest RECONCILING commit -- see the module docstring for the
    full three-condition definition. Walking newest-first and taking the
    first touching commit for which did_modify_entry is True means a touching
    commit that did NOT modify the task's own entry is skipped, not treated
    as a reconciler by default."""
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
            # commit is outstanding.
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

    return {
        "task_refs": ref_report,
        "blockers": blockers,
    }


def print_report(report, next_up_line, days):
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
    print(f"  {next_up_line}")



def next_up_staleness(repo_dir, backlog_text):
    """The one-line section-3 report for backlog_text's 'Next up' block."""
    next_up_date = find_next_up_date(backlog_text)
    if next_up_date is None:
        return "No 'Next up' block found in backlog.md."
    basis = find_next_up_basis(backlog_text)
    if basis is not None:
        after = count_commits_after_basis(repo_dir, basis)
        if after is not None:
            counted, skipped = after
            note = (f" (not counting {skipped} that only rewrote the block)"
                    if skipped else "")
            return (f"Next up dated {next_up_date}, basis `{basis}`; {counted} "
                    f"commit(s) since{note}.")
        reason = f"basis `{basis}` is not in this repo's history"
    else:
        reason = "the basis line names no commit"
    since = count_commits_since(repo_dir, next_up_date)
    return (f"Next up dated {next_up_date}; {reason}, so counting from midnight "
            f"of that date: {since} commit(s) since (includes any made earlier "
            f"that day).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                         help=f"commit window in days (default {DEFAULT_DAYS})")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--backlog", default=DEFAULT_BACKLOG)
    # Accepted and ignored, so a /finalise that still passes it keeps working.
    parser.add_argument("--memory-dir", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # Three absences are normal, not errors -- report and exit 0, since this script reports and
    # never gates and a traceback would break that contract:
    #   - no backlog.md yet (/bootstrap-project hasn't run here): every section needs it.
    #   - not a git repo: sections 1 and 3 are git-derived. Rather than print a half-report
    #     whose empty sections read as clean findings, say which input is missing and stop.
    #   - a git repo with no commits yet: the normal state straight after /bootstrap-project.
    #     Distinct from "not a repo" because the remedy differs: commit, then re-run.
    # Any OTHER git failure is not an absence, and is left to raise.
    if not os.path.exists(args.backlog):
        print(f"no backlog.md yet at {args.backlog} -- skipping thread-state check "
              f"(run /bootstrap-project first)")
        sys.exit(0)
    if not is_git_repo(args.repo):
        print(f"{args.repo} is not a git repository -- skipping thread-state check "
              f"(sections 1 and 3 are derived from commit history)")
        sys.exit(0)
    if not has_commits(args.repo):
        print(f"{args.repo} is a git repository with no commits yet -- skipping "
              f"thread-state check (commit the bootstrapped files and re-run)")
        sys.exit(0)

    commits = run_git_log(args.repo, args.days)

    with open(args.backlog, encoding="utf-8") as f:
        backlog_text = f.read()

    did_modify_entry = make_did_modify_entry(args.repo)

    report = build_report(backlog_text, commits, did_modify_entry)

    print_report(report, next_up_staleness(args.repo, backlog_text), args.days)

    # Reports, never gates -- see module docstring.
    sys.exit(0)


if __name__ == "__main__":
    main()

