---
name: bootstrap-project
description: Bootstrap this project's backlog / decisions / CLAUDE.md scaffolding
disable-model-invocation: true
---

## Bootstrap this project's backlog / decisions / CLAUDE.md scaffolding

Goal: set up `backlog.md`, `decisions.md`, and a `CLAUDE.md` pointer in the CURRENT project, so it
can use `/finalise` and `/memory-audit` the way any other project on this machine does. This is
new content, not a port of another project's real backlog: it starts empty apart from any open
work the user chooses to move in from this project's own memory (step 6).

### The process flow, in one paragraph

`backlog.md` is the only place open work lives — never a harness task list (session state,
destroyed on `/clear`), never a plan buried in conversation. Each task gets a **permanent number**
the moment it's opened; numbers are never reused or renumbered, even after the task closes,
because `decisions.md` and old commit messages cite them by number. A task lives under `## Open`
with its number as the entry heading (`### #N — title`) while active. When it's done, its entire
body moves out: a **one-line stub** stays under `## Closed` (date, number, title, commit hash,
and a pointer to `decisions.md` if there's rationale worth keeping), and the *why* — the
reasoning, the alternatives rejected, the measurement that justified it — goes into `decisions.md`
as its own dated entry. `backlog.md` never re-narrates finished work and `decisions.md` never
carries a task's live status. `/finalise` step 4 is what moves stray session-only work into this
file before it's lost, and step 6 is what keeps a dated "Next up" recommendation at the top,
replaced in full each run rather than appended to.

A `backlog.md`/`decisions.md` pair with nothing pointing at it is easy to forget mid-task, so this
also creates or extends a minimal project `CLAUDE.md` naming them — without that pointer, these
two files would only ever get touched when `/finalise` runs at session close, never mid-session
when they'd actually help decide what to work on next.

### Paths used in this skill

- `<project root>` — the repo this session is working in (its git top-level directory).
- `<memory dir>` — this project's auto-memory directory: take `<project root>`'s absolute path
  and replace every `/` with `-`; the directory is `~/.claude/projects/<that string>/memory/`.
- The file templates are in `${CLAUDE_SKILL_DIR}/templates/`. The project `CLAUDE.md` template is
  stored as `project-CLAUDE.md` so it never loads as instructions.

### What to do

1. Confirm the current directory is the project's repo root (check for `.git`; if there isn't one
   yet, ask whether to `git init` before proceeding — a backlog file with no version history
   defeats half its purpose). If you do initialise one, pin the branch name explicitly
   (`git init -b main`) rather than accepting whatever the local git config defaults to — left
   unpinned, this produces a different default branch name on different machines depending on
   each one's own `init.defaultBranch` setting.
2. Determine `<PROJECT NAME>` from the repo directory name. If the name is generic (`repo`,
   `project`, `src`, `app`, or similar) or you're unsure, ask rather than guessing.
3. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/scaffold.py <project root> "<PROJECT NAME>" --dry-run`.
   It writes nothing and prints `exists` or `would create` for `backlog.md`, `decisions.md`,
   `lesson-candidates.md` and `CLAUDE.md`. If any of the first three exists, show the user its
   content and ask how to proceed before going on — don't assume this is the first run here.
   If it prints `refused`, this directory is a clone of the workflow bundle, not a project: stop,
   show the user its message, and write nothing.
4. Run the same command without `--dry-run`. It writes each missing file with the project name and
   today's date filled in, and never changes a file that exists. The files carry no invented
   tasks or decisions.
5. **If `CLAUDE.md` already existed, read the whole thing** — don't just check that it exists.
   Check whether it already points anywhere to an open-worklist or decision-log convention (any
   name, any heading — not just files literally called `backlog.md`/`decisions.md`). If it does,
   show both and ask how to reconcile before writing anything — don't silently end up with two
   competing worklist conventions in one project. If it has no such pointer, append the
   `## Where the instructions live` section of `templates/project-CLAUDE.md` (with its heading,
   without the template's title line) as a new section, separated by a blank line, rather than
   overwriting anything already there.
6. **Offer to move open work out of memory.** Skip this step if `<memory dir>` doesn't exist or
   `backlog.md` already existed in step 3. Otherwise read every memory file in it and list the
   items that describe open work (something still to do, planned, or undecided), as distinct
   from facts that stay true (how something is set up, a preference, why something is the way it
   is). If there are none, say so and move on. Otherwise offer each item as a backlog task, one
   decision per item. For each one accepted:
   - Add it under `## Open` as `### #N — <title>`, numbered from `#1` in the order accepted, with
     an `Opened <today>:` body in the shape the template shows. Replace the template's
     placeholder line and example with the real tasks.
   - Remove it from the memory file, leaving the lasting facts in place, and update that file's
     `MEMORY.md` index line if its description no longer fits.
   - If this leaves a memory file with nothing in it, delete the file and its index line, then
     find `[[<its name>]]` links in the other memory files and the project's Markdown docs. For
     each, ask whether to point the sentence at where the content went (such as the new task
     numbers), remove the sentence, or keep the name as plain text. `/finalise`'s memory check
     fails on any link to a memory that no longer exists.

   If any task was added, replace the "Next up" block's `Nothing opened yet.` and
   `Open threads: none.` lines with the new task numbers and titles.
7. **Mention, don't silently absorb, `context_budget_log.csv`.** The first time `/finalise` runs
   in this project it will create this file at the repo root (a growth log for the always-loaded
   CLAUDE.md/MEMORY.md surfaces — see that script's own docstring). It isn't created by this
   skill, so there's nothing to write here, but flag to the user now that it will appear later
   and that whether to git-track it is a one-time call worth making deliberately rather than
   letting a later `git add -A` sweep it into an unrelated commit unannounced.
8. Ask before committing — first commit of a new convention is worth a quick look, not an
   auto-commit.
