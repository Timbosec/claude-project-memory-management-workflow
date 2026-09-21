# Bootstrap prompt 4 of 5 — installs the `/bootstrap-project` command (run ONCE per machine)

This one changed shape from earlier drafts of this bundle. It used to be a prompt you'd paste
into every new project by hand. That's fragile — it means keeping track of a saved file and
remembering it exists, months from now, for the fifth new project you start. Instead, this prompt
installs a **permanent, global command** — `~/.claude/commands/bootstrap-project.md` — the same
way `/memory-audit` is installed (prompt 5). From then on, setting up a new project is just:
open Claude Code inside the new repo and type `/bootstrap-project`. No file to find.

Run this once per machine, any time relative to prompts 1/2/5 — but ideally after prompt 3, since
the command's own CLAUDE.md template tells the new project to run `/finalise`, and that reference
only means something once prompt 3 has installed it.

## Instructions for Claude

1. Create `~/.claude/commands/bootstrap-project.md` with exactly the content given below.
2. Do NOT commit/push — same reasoning as the earlier prompts.
3. Report the file's byte size so I can sanity-check nothing got truncated.
4. Once created, tell me I can test it immediately: open a fresh Claude Code session in any repo
   (a scratch/throwaway one is fine for a first try) and type `/bootstrap-project`.

---

### Before writing anything

**Check whether `~/.claude/commands/bootstrap-project.md` already exists.** If it does, read it in
full, diff it against the content below, and show me the differences before overwriting — same
discipline as every other install step in this bundle. If it doesn't exist yet, create it with
exactly the content below.

### File: ~/.claude/commands/bootstrap-project.md

````markdown
## Bootstrap this project's backlog / decisions / CLAUDE.md scaffolding

Goal: set up `backlog.md`, `decisions.md`, and a `CLAUDE.md` pointer in the CURRENT project, so it
can use `/finalise` and `/memory-audit` the way any other project on this machine does. This is
new content, not a port of another project's real backlog — it starts genuinely empty every time.

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

### What to do

1. Confirm the current directory is the project's repo root (check for `.git`; if there isn't one
   yet, ask whether to `git init` before proceeding — a backlog file with no version history
   defeats half its purpose). If you do initialise one, pin the branch name explicitly
   (`git init -b main`) rather than accepting whatever the local git config defaults to — left
   unpinned, this produces a different default branch name on different machines depending on
   each one's own `init.defaultBranch` setting.
2. Determine `<PROJECT NAME>` from the repo directory name. If the name is generic (`repo`,
   `project`, `src`, `app`, or similar) or you're unsure, ask rather than guessing.
3. Check whether `backlog.md`, `decisions.md`, and/or `lesson-candidates.md` already exist at the
   repo root. If any does, stop and show its content before overwriting — don't assume this is the
   first run here.
4. Create `backlog.md` with the content under "File: backlog.md" below, with `<PROJECT NAME>`
   substituted. **`<DATE>` in the "Next up" heading is also a placeholder** — substitute today's
   date in ISO 8601 (`YYYY-MM-DD`) form, the same format `decisions.md` uses. This isn't cosmetic:
   `/finalise`'s `check_thread_state.py` parses this field with a `YYYY-MM-DD` pattern to report
   staleness, so a different date format silently breaks that check.
5. Create `decisions.md` with the content under "File: decisions.md" below, same substitution.
6. Create `lesson-candidates.md` with the content under "File: lesson-candidates.md" below, same
   substitution. This is the project-scoped sibling of `~/.claude/lesson-candidates.md` — see that
   file's own header for the schema and mechanics, which this one shares in full; the only
   difference is scope (this ledger's "second case" gate is satisfied by a second occurrence
   *within this project*, and its candidates promote to *this project's* `CLAUDE.md` rather than a
   global home). `/finalise`'s routing test (its own SKILL.md, step 1) decides when a candidate
   belongs here rather than in the global ledger or in `decisions.md`.
7. **Check whether this project already has a `CLAUDE.md` at its repo root, and read the whole
   thing if it does** — don't just check whether it exists.
   - If it does NOT exist: create it with the content under "File: CLAUDE.md" below.
   - If it DOES exist: check whether it already points anywhere to an open-worklist or
     decision-log convention (any name, any heading — not just files literally called
     `backlog.md`/`decisions.md`). If it does, show both and ask how to reconcile before writing
     anything — don't silently end up with two competing worklist conventions in one project. If
     it has no such pointer, append the content under "File: CLAUDE.md" below as a new section,
     separated by a blank line, rather than overwriting anything already there.
8. Don't invent any task entries or decisions to seed `backlog.md`/`decisions.md`/`lesson-
   candidates.md` with — they start genuinely empty. Leave the "## Open" section with no entries
   and the "Next up" block as the placeholder shown.
9. **Mention, don't silently absorb, `context_budget_log.csv`.** The first time `/finalise` runs
   in this project it will create this file at the repo root (a growth log for the always-loaded
   CLAUDE.md/MEMORY.md surfaces — see that script's own docstring). It isn't created by this
   command, so there's nothing to write here, but flag to the user now that it will appear later
   and that whether to git-track it is a one-time call worth making deliberately rather than
   letting a later `git add -A` sweep it into an unrelated commit unannounced.
10. Ask before committing — first commit of a new convention is worth a quick look, not an
    auto-commit.

---

### File: backlog.md

```markdown
# <PROJECT NAME> backlog

The project's open worklist and the **canonical home** for it — a memory index or CLAUDE.md may
point here, but the content lives only in this file. `decisions.md` records *why* finished work
was done; this file only ever tracks *what's open and what's next*.

Task numbers are stable and may be cited from `decisions.md` or commit messages — never renumber,
even after a task closes. Closed tasks keep a one-line stub here so those citations stay
resolvable; their detail lives in `decisions.md` and git, never re-narrated here.

Current-state facts (counts, configuration, what currently exists) are deliberately absent from
task bodies — read the actual code/data for those rather than maintaining a copy that goes stale
the moment it's written.

---

## Next up — recommended <DATE> (first revision)

Replaced in full each time this is updated, never appended. A dated snapshot of judgement, not a
fact — re-check it against `## Open` before acting on it. Basis: commits through `<none yet>`.

Nothing opened yet.

Open threads: none.

---

## Open

(no open tasks yet — the first one added here should follow this shape:)

    ### #1 — <one-line title, specific enough to identify the task without opening it>

    Opened <date>: <what's being done and why, in enough detail that a cold reader — including a
    future you — doesn't need to reconstruct it from chat history>. Note decisions still needed,
    dependencies on other tasks (`blocked by #N`), and anything already ruled out and why.

---

## Closed

One line each — rationale in `decisions.md`, mechanics in git. Do not re-narrate the task body
here; if there's nothing worth saying beyond "shipped", the commit hash is enough:

    - <date> · **#N** <one or two sentences: what was actually wrong/needed and how it was
      fixed — enough that the citation means something without opening `decisions.md`>.
      `decisions.md` <date if applicable>. `<commit-hash>`.
```

---

### File: decisions.md

```markdown
# <PROJECT NAME> — Decision Log

Durable decisions and their rationale. Append-only; mark a reversed entry `Status: Superseded`
rather than deleting it — the history of having been wrong is part of what makes this useful.

Only decisions with real rationale belong here: a tradeoff considered, an alternative rejected, a
measurement that settled something. A task that was simply done, with nothing arguable about how,
gets its commit hash in `backlog.md`'s Closed stub and nothing here.

---

<!-- Each entry follows this shape:

## <short title naming the decision, not the task number>
- Date: <date>
- Decision: <what was decided, stated as a fact>
- Why: <the reasoning — what was measured, what alternative was considered and rejected, what
  broke without this>
- Status: Active

-->
```

---

### File: lesson-candidates.md

```markdown
# <PROJECT NAME> — lesson candidates (project-scoped)

The project-level sibling of `~/.claude/lesson-candidates.md` — **same schema, same Candidate/
Origin-log mechanics, see that file's own header for the full explanation.** Only two things
differ here:

- **Scope of the gate.** A candidate here is waiting for a second, *contrasting* case from
  **within this project** — not from anywhere on the machine. `/finalise`'s routing test (its own
  SKILL.md, step 1) is what decides a candidate belongs in this file rather than the global one:
  something that recurs in this project and is genuinely rule-shaped, but doesn't (yet) look like
  it generalises past it.
- **Where a promoted candidate lands.** A pairing found here promotes into *this project's own*
  `CLAUDE.md`, never a global home.

**This project's ledger is not read in isolation, though.** `/memory-audit` (Part 2.6) treats
every project's ledger and the global ledger as **one shared pool** when looking for a second
case — a candidate parked here can still turn out to match one sitting in a *different* project's
ledger, entirely unrelated to this one. When that happens, the match promotes to a global home
instead of this project's `CLAUDE.md`, because the pairing has shown the claim isn't actually
scoped to this project after all. Routing a case in here is what this session could see at the
time, not a permanent verdict.

Starts empty — no entries to port, nothing to seed.

## Entries

(none yet — entries accumulate here as cases are captured)
```

---

### File: CLAUDE.md

If creating fresh, this is the whole file. If appending to an existing one, write only the
`## Where the instructions live` section below (with its heading) as a new section.

```markdown
# <PROJECT NAME>

## Where the instructions live
- Worklist: `backlog.md` — canonical, git-tracked open worklist. Task numbers are stable and
  cited by `decisions.md` — never renumber, even after a task closes. Backlog items go there,
  never in a harness task list (session state — `/clear` destroys it).
- Decision history & rationale: `decisions.md`.
- Lessons specific to this project, awaiting a second case before becoming a project rule:
  `lesson-candidates.md` — see its own header; a promoted candidate lands in this file, in a new
  section named for the rule (not folded into "Where the instructions live").
- Session-close ritual: run `/finalise` before clearing context — it sweeps for undocumented
  decisions/lessons, reconciles `backlog.md`, and runs deterministic integrity checks.
```
````
