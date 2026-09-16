# Bootstrap prompt 5 of 5 — /memory-audit (run ONCE per machine)

Run this after prompt 3 (it invokes the global finalise scripts prompt 3 installs, so it depends
on that having run first). Like `/finalise`, this is a **global** command — one file, used across
every project on this machine — not something you reinstall per project.

## Why this one matters

`/finalise` writes to `lesson-candidates.md` but explicitly does NOT age it — its own header says
"`/finalise` step 2 does the pairing... `/memory-audit` Part 2.6 does the aging... neither assumes
the other ran." Skip this prompt and that half of the system never runs: candidates that could be
promoted or retired just accumulate forever, and a rule marked "Provisional — single case" is
never revisited to check whether a second case has since turned up. This command is also the only
thing that periodically checks the rule homes, both CLAUDE.mds, and memory against each other for
contradictions and duplication — none of the other four bootstrap prompts do that.

## What changed from the source version, and why

Unlike `/finalise`'s `SKILL.md`, this file was already written to be cross-project (it lives at
`~/.claude/commands/`, not inside any one project's own `.claude/`, and its own Scope section
already says "discover all auto-memory dirs... ask which project(s) to audit — don't assume").
Only a handful of spots still hardcoded one specific project's path where the rest of the file
already used a generic `<repo>` placeholder — those are fixed below. Also fixed: the closing
section assumed both repos' pushes were pre-authorized (a decision that doesn't exist on a new
machine — changed to ask first), and Part 4's example verification probes were the source
project's own domain questions — replaced with an instruction to substitute real questions from
whatever project is actually being audited.

**One known soft-dependency, not fixed by this bootstrap:** Part 1 references a script at
`~/.claude/skills/auditing-skill-candidates/scripts/map_surfaces.sh` for measuring where a trim
actually saves always-loaded context budget. That skill isn't part of this bundle. The instruction
already has a fallback for this ("if that script's output doesn't list the rule homes, measure
them directly") — so the audit still works without it, just with a manual measurement step
instead of the script. Port that skill separately if you want the automated version.

## Instructions for Claude

1. Create `~/.claude/commands/memory-audit.md` with exactly the content below — it's already
   adapted, don't make further path substitutions.
2. Do NOT commit/push — same reasoning as the earlier prompts.
3. Report the file's byte size so I can sanity-check nothing got truncated.

---

### File: ~/.claude/commands/memory-audit.md

````markdown
## Memory Audit & Cleanup (auto-memory + CLAUDE.md + rule homes + decisions log)

Goal: remove stale, conflicting, and low-value content from project memory and from the
standing-rule files; archive durable decisions+rationale to a git-tracked decisions log so
they're recallable without polluting task-oriented memory. Verify every claim against the
CURRENT codebase/skills before acting. Do NOT delete anything until I approve the plan.

### Scope — discover, then confirm (don't hardcode paths)
1. Discover all auto-memory dirs: `find ~/.claude/projects -name MEMORY.md`.
   Each dir is keyed off a working directory, so ONE project's memory can be split
   across dirs (e.g. run-from-home vs run-from-repo). List them and ASK which
   project(s) to audit — don't assume, don't touch unrelated projects.
2. Check for fragmentation: the same project's memories scattered across dirs.
   Consolidate into the project repo's dir (move files + reconcile BOTH indexes).
Then, per chosen project, audit:
Auto memory (Claude-written; NOT git-tracked → deletions are unrecoverable):
  - ~/.claude/projects/<dir>/memory/  (MEMORY.md + topic files)
CLAUDE.md (human-written instructions):
  - ~/.claude/CLAUDE.md, ~/CLAUDE.md  (user scope)
  - <repo>/CLAUDE.md                  (project scope)
User-scope rule homes — standing rules, and they go stale like any other doc:
  - ~/.claude/CLAUDE.md § Working rules  (the agent at any other moment)
  - ~/.claude/prompt-lessons.md          (the user authoring a prompt or brief)
  - ~/.claude/writing-standing-docs.md   (the agent editing a standing doc or memory)
  - ~/.claude/writing-executor-briefs.md (the agent briefing an executor or verifying it)
  ~/.claude/CLAUDE.md appears twice on purpose — audited as an instruction file above, and as
  a rule home here. The actor test that assigns a rule to one of these is canonical in that
  file's header; apply it from there, don't re-derive it.
Lesson ledger — NOT a rule home; nothing in it is in force. Audit per Part 2.6, not Part 2:
  - ~/.claude/lesson-candidates.md    (first cases awaiting a second; origin logs of promoted rules)
Evidence logs and repo docs — same directory, not rule homes, easy to miss:
  - ~/.claude/under-explained-cases.md  (real instances of unclear writing; carries its own
    capture + evaluation protocol — read it, don't re-derive)
  - ~/.claude/README.md                 (what the config repo tracks and why, if present)
  **Glob `~/.claude/*.md` and account for every result** rather than trusting this list — it has
  already been wrong once on the source machine: two files post-dated it and went unaudited.
  Anything the glob returns that is not named here is an unaudited standing surface; read it and
  say which category it falls in.
Decisions log (git-tracked, durable):
  - <repo>/decisions.md               (create if absent)
Read but never edit: skills' references/*.md — the "living spec", if the audited project has one.
On any conflict with this project's own docs (memory, decisions.md, project CLAUDE.md) the
reference WINS. Read them to decide whether a memory is still true, and report defects found in
them; editing them would resolve a conflict by rewriting the reference instead of the copy, and
would bypass their own gates (test runs after a constant changes, both-skills completeness).
Out of scope entirely: unrelated projects.
Read files directly with the Read tool. (`/memory` only lists loaded files; it
can't open auto-memory topic files for you.)
Before editing any of the above, read `~/.claude/writing-standing-docs.md` — it carries the
operative rules for this work (contract-vs-snapshot, canonical-plus-pointers, replace-not-join,
audience-referent), including the pronoun check this command's own port originally motivated.
Note: paths starting with `-` (e.g. `-Users-alice-project/...`) break mv/shell commands —
prefix with `./` or use `--`.

### Part 0 — Safety
1. `cp -r` each auto-memory dir to a timestamped backup before any edit. On a
   CONTINUED/resumed run, take a NEW backup of the CURRENT dir — a prior session's
   backup predates its own edits and is not a clean baseline for this run's changes.
2. Produce the full change plan (Output section) and STOP for my approval before
   deleting/editing/committing.
3. Work in batches: apply high-confidence changes first; defer per-file operational
   verification (checking memories against current skill code) to a focused pass —
   ideally a fresh launch from the project repo (cheaper, per the fresh-launch SOP).
   For large dirs, assess from the index and deep-read only suspicious files per pass.
   When you defer, RECORD the exact deferred set in the change-plan output (which
   files, which unverified claims) so a later "continue" run resumes from that list
   deterministically instead of reconstructing the queue from backups/git/mtimes.

### Part 1 — Instruction-file review (both CLAUDE.mds + the other three rule homes)
- Verify every command/path/skill-name actually exists and works (test one).
- Flag rules that contradict the current code or skills.
- Trim persona/vague lines: not "zero effect," but they dilute adherence and cost
  context — keep only concrete, verifiable instructions.
- **Judge a trim by WHERE the file loads, not by its size.** If a script at
  `~/.claude/skills/auditing-skill-candidates/scripts/map_surfaces.sh` exists on this machine, run
  `bash` on it with `<repo>` to class every surface and print the always-loaded subtotal — the
  only budget a trim can reclaim. Bytes cut from an on-demand rule home reclaim none of it, so
  judge those on whether the rule still fires, never on length. That script is not guaranteed to
  be installed on every machine; if it's absent, or its output doesn't list the rule homes above,
  measure them directly instead (byte-count each always-loaded file yourself).
- A rule that duplicates one in another home is the same defect as a duplicate memory —
  resolve to one canonical home and leave a pointer, per canonical-plus-pointers.
- Note empty files.

### Part 2 — Auto-memory audit (MEMORY.md + every topic file)

**Keep/cut test** (mirrors Claude Code's own `/doctor` trim criterion): **cut** what can be
derived from the codebase in one cheap read — directory layouts, dependency lists, architecture
overviews, file counts, "X is currently pending". **Keep** pitfalls, rationale, and conventions
that differ from tool defaults — the things reading the code would actively mislead you about.
A derivable fact is worse than useless in a memory: the code stays correct as it changes, the
copy does not, and nothing announces the drift. If in doubt, ask whether a fresh agent could
recover the fact by reading one file. If yes, cut it.

For each entry classify as one of: TRUE+LIVE / OBSOLETE / DURABLE-DECISION / DUPLICATE.
- Still TRUE vs current code/skills? (e.g. confirm skill names, file paths.)
- Conflicts with another memory? Resolve to the CURRENT TRUTH (verify both — newest
  is not automatically right). Delete the false one.
- OBSOLETE (deleted file / finished task / project moved past it) → delete. Do NOT
  archive obsolete content into the decisions log.
- Relative dates ("recently") → absolute or delete.
- Old mtime/age = re-verify, not auto-delete.
- DUPLICATE → consolidate. NEVER judge duplication from index lines: read BOTH
  bodies first; merge preserving every unique rule; delete a file only if its
  content is an exact subset of the other.
- Body vs metadata drift: a file's own `description:` frontmatter and its MEMORY.md
  index line can lag its body (e.g. the body says a task is DONE while the
  description/index still say "open task"). Reconcile all three to the body's
  CURRENT truth — and prioritise the description + index line, because those
  (not the body) are what actually load into context each session.

### Part 2.5 — Extract durable decisions to <repo>/decisions.md
For entries kept only for their rationale/"why we did X" (DURABLE-DECISION):
- Append to decisions.md (ADR-lite), append-only, dated:
    ## <decision title>
    - Date: <absolute date>
    - Decision: <what was decided>
    - Why: <1–2 lines>
    - Status: Active | Superseded by <entry/date>
- Then thin the auto-memory entry to a one-line pointer to decisions.md (or delete
  it if the live memory carried nothing but the rationale).
- Mark any decision the project has since reversed as Status: Superseded — don't delete it.
- **A generalisable rule is not a durable decision.** decisions.md records why THIS project did
  X. A rule that would transfer to an unrelated project belongs in a user-scope rule home per
  the actor test — or, if only one case supports it, in the ledger until a second arrives.
  Routing a rule into decisions.md buries it where no other project will ever read it.

### Part 2.6 — Lesson ledger: aging review
`~/.claude/lesson-candidates.md` holds first cases awaiting a second contrasting case, plus
origin logs for rules already promoted. **Nothing in it is in force, so the Part 2 keep/cut test
does not apply** — a candidate is not stale for being unused; waiting is what it is for.

Run `python3 ~/.claude/skills/finalise/scripts/context_budget_report.py --project-claude
<repo>/CLAUDE.md --memory-index <memory-dir>/MEMORY.md --ledger ~/.claude/lesson-candidates.md
--prompt-lessons ~/.claude/prompt-lessons.md --writing-standing-docs
~/.claude/writing-standing-docs.md --writing-executor-briefs
~/.claude/writing-executor-briefs.md --history <repo>/context_budget_log.csv` and read its
counts — candidates awaiting a second case with the oldest age in days, and rules still carrying
a single-case "Provisional" marker per home. Consume that output; don't recount by hand.
`<repo>` and `<memory-dir>` are the project root and its derived auto-memory directory for
whichever project this audit run is scoped to (see the derivation rule in the finalise bootstrap:
the project's absolute path with every `/` replaced by `-`).

Propose one outcome per waiting candidate, and ask before writing:
- **Promote** — a second, contrasting case has since arrived. Name it. Then follow the ledger's
  own Promotion section (write the rule to its home, move both narratives to an origin log,
  delete the candidate).
- **Still waiting** — the claim is live and worth keeping parked. Age alone is not a reason to
  act; say so and move on.
- **Retire** — the project has moved past it, or the first case no longer reproduces.

A rule still marked "Provisional" is the inverse case: it is in force but only one case supports
it. Flag it for a second case or for demotion back to a candidate — don't silently drop the
marker, and don't assume why it carries one.

**Scope split, so neither side assumes the other did it:** `/finalise` owns *pairing* — matching
a newly observed case against the waiting candidates at the moment it happens, which is when the
new case is in hand. This audit owns *aging* only, which `/finalise` cannot see from inside one
session.

### Part 3 — Index & link integrity (after every change)
- Every topic file has exactly one pointer line in MEMORY.md; remove dangling
  pointers for deleted files; add missing ones.
- Add a CLAUDE.md pointer in `<repo>/CLAUDE.md`: "Decision history & rationale: decisions.md" —
  only if this project has a project-level CLAUDE.md and the pointer isn't already there.
- Keep the frontmatter FIELDS (name/description/metadata.type) on kept files, but
  UPDATE `description:` whenever it no longer matches the body — a stale description
  is what misleads the next session. Don't leave a wrong one in place as "preserved."
- Fix or remove [[wikilinks]] orphaned by deletions/renames.
- **Run the check rather than eyeballing it:**
  `python3 ~/.claude/skills/finalise/scripts/check_memory_index.py <memory-dir> <repo>`. It
  verifies the every-file↔exactly-one-index-line invariant, resolves [[links]] against the memory
  dir's slugs — inside memory-file bodies and inside every `*.md` in the repo (citations in code
  spans and fenced blocks are ignored) — and prints MEMORY.md against its load limit — the first
  200 lines **or 25,600 bytes, whichever comes first**, is all that loads at session start.
  **Bytes bind first** (long index lines), so watch that percentage rather than the line count.
  Non-zero exit = fix before finishing, not after.
- A dangling citation the check reports — inside a memory file or in the repo's docs — is a
  finding to verify, not an instruction to delete on sight: the claim it supports may be true
  and merely unsourced. Confirm live before removing it; if the mechanism holds, mark the claim
  unsourced in place rather than deleting it.

### Part 4 — Verification with real, on-domain probes
Check the right guidance is recalled for 3-4 real questions drawn from whatever this project
actually does — not hypothetical ones. Pick questions whose correct answer should resolve via a
specific memory, `decisions.md` entry, or the ledger, e.g. in the shape of:
- a question this project's memory demonstrably answers today (confirm it still resolves)
- "Why did we choose <a real past architecture/cost decision>?" (should resolve via decisions.md)
- "I've just noticed <a one-case lesson> — where does it go?" (should resolve to the ledger via
  the actor test, NOT straight into a rule home)
If a probe surfaces wrong/conflicting memory, that entry is a deletion candidate.

### Output — proposed change plan (await approval, then apply)
- Deletions: file/entry + reason + which system
- Decisions extracted: title → decisions.md (+ what was thinned/deleted in auto-memory)
- Consolidations: which entries merged → into what
- Conflicts resolved: which won and why (cite the code/skill checked)
- CLAUDE.md edits (incl. decisions.md pointer)
- Rule-home edits: which home, which rule, and whether it was trimmed, moved or de-duplicated
- Ledger outcomes: each waiting candidate → promoted (naming the second case) / still waiting /
  retired; plus every rule whose "Provisional" marker was resolved or left standing
- Defects found in the living spec: what and where, reported only — never edited here
- Index/link fixes
After I approve: apply, then ask before committing or pushing either repo — don't assume
pre-authorization on this machine the way the source version did.
  - `<repo>` — decisions.md, CLAUDE.md, and any skill file touched
  - `~/.claude` — the rule homes and the ledger, which live in their own repo (if it is one on
    this machine); edits there are lost to the next audit's baseline if left uncommitted
Auto-memory stays local (not committed).
Since auto-memory isn't git-tracked, this report IS its audit trail — be exact.
````
