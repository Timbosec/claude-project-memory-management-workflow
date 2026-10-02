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
