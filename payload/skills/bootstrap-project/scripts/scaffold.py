#!/usr/bin/env python3
"""Write /bootstrap-project's starting files into a project, never touching one that exists.

    python3 scaffold.py <project root> <project name> [--dry-run] [--date YYYY-MM-DD]

Each template in ../templates/ is written to the project root with `<PROJECT NAME>` and `<DATE>`
filled in, unless a file of that name is already there. `project-CLAUDE.md` is written as
`CLAUDE.md`; it is stored under another name so that Claude Code never loads the template itself
as instructions. Prints one line per file, `created` or `exists`, so the agent running the skill
knows which existing files to show the user and whether an existing CLAUDE.md needs reconciling.
`--dry-run` prints the same lines (`would create` in place of `created`) and writes nothing.

It refuses, writing nothing, when the root holds `install.py` and `manifest.json`: that is a clone
of the workflow bundle, which agents run installs from and so can mistake for a project.

The date is today's, in YYYY-MM-DD form, because /finalise's check_thread_state.py parses the
"Next up" heading with that pattern. `--date` exists for tests.
"""
import argparse
import datetime
import os
import re
import sys

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "templates")

# template filename -> filename written in the project
FILES = [
    ("backlog.md", "backlog.md"),
    ("decisions.md", "decisions.md"),
    ("lesson-candidates.md", "lesson-candidates.md"),
    ("project-CLAUDE.md", "CLAUDE.md"),
]

# Files at the root of a clone of the workflow bundle itself, which is never a project to scaffold.
BUNDLE_CLONE_MARKERS = ("install.py", "manifest.json")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fill(text, name, date):
    return text.replace("<PROJECT NAME>", name).replace("<DATE>", date)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", help="the project's repo root")
    parser.add_argument("name", help="the project name for the files' headings")
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    parser.add_argument("--date", default=datetime.date.today().isoformat(),
                        help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args(argv)

    name = args.name.strip()
    if not name:
        parser.error("the project name is empty")
    if not _DATE_RE.match(args.date):
        parser.error(f"--date must be YYYY-MM-DD, got {args.date!r}")
    if not os.path.isdir(args.root):
        parser.error(f"not a directory: {args.root}")
    if all(os.path.isfile(os.path.join(args.root, f)) for f in BUNDLE_CLONE_MARKERS):
        print(f"refused: {args.root} is a clone of the workflow bundle (it has "
              f"{' and '.join(BUNDLE_CLONE_MARKERS)} at its root), not a project. The bundle is "
              "installed from this clone, so a CLAUDE.md here would load into every later install "
              "session, and project files committed here would leave the clone out of step with "
              "the bundle it pulls updates from. Run /bootstrap-project in the project you want "
              "to work on instead.", file=sys.stderr)
        return 1

    for template, target in FILES:
        dst = os.path.join(args.root, target)
        if os.path.lexists(dst):
            print(f"exists   {target}")
            continue
        if args.dry_run:
            print(f"would create  {target}")
            continue
        with open(os.path.join(TEMPLATES, template), encoding="utf-8") as f:
            text = fill(f.read(), name, args.date)
        with open(dst, "x", encoding="utf-8") as f:
            f.write(text)
        print(f"created  {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
