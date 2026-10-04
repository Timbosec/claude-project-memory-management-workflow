#!/usr/bin/env python3
"""Context-budget growth report for /finalise.

Reports -- never gates (exit 0 always, same convention as check_thread_state.py). The problem
this watches is growth: the surfaces loaded into every session (both CLAUDE.mds, MEMORY.md) can
balloon unnoticed over weeks of edits, with nothing else tracking it over time. There is exactly
ONE threshold anywhere in this file, and it is not new: MEMORY.md's 200-line / 25,600-byte load
limit, already enforced by check_memory_index.py. Everything else here is a bare figure or a
delta against logged history -- never an invented budget. A flat byte threshold on the combined
total was considered and rejected: picked without being derived from anything, a number like that
risks going red on the very first real run and staying red forever. Permanently-red checks get
ignored, which is worse than no check -- so this prints numbers and leaves picking a line to the
user, once the log has a few weeks of real observations in it.

Four things printed:
  1. Lesson candidates in lesson-candidates.md awaiting a second case -- count and the oldest
     one's age in days. A candidate entry is identified by carrying a "First observed:" field
     (the Candidate schema requires it; the Origin log schema has "Home:"/"Promoted:" instead),
     so this counts by field signature, not by which "##" section heading happens to exist --
     a ledger with no candidates may have no such heading at all, and that must read as a
     genuine zero, not the default a broken parser would also print. See
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
    """Idempotent upsert keyed on date: a rerun on the same day replaces that day's row instead
    of duplicating it; a new day appends. Written atomically via atomic_write_csv."""
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

