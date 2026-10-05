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
**Either may not be a git repo.** Where `<project root>` or `~/.claude` isn't one, its writes are
saved to disk but not committed: say so once and carry on. Never offer to initialise a repo.

**`<memory dir>` is never committed**, even where `~/.claude` is a git repo: auto-memory stays
local. Every memory write this skill makes (a new memory file, an edited one, a `MEMORY.md` index
line) persists to disk only; skip the commit for those and don't report them as committed in
step 7. If a memory file shows up as untracked in `~/.claude`'s `git status`, leave it untracked.

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
     a reusable rule, not a one-off fact. Routing test, three-way:
     (a) **generalises across projects/disciplines?** — append to `~/.claude/lesson-candidates.md`,
     gated on a second, contrasting case from anywhere; promotes to one of the four global
     user-scope homes below.
     (b) **recurs within this project, and is genuinely rule-shaped** — something you'd want
     enforced every time this project is worked on, not just known about? — append to `<project
     root>/lesson-candidates.md` instead (same schema and mechanics as the global ledger, gate
     scoped down to a second occurrence WITHIN this project); promotes to `<project
     root>/CLAUDE.md`, not a global home. `/memory-audit` separately scans every project's ledger
     together as one pool (its Part 2.6) — a case that looks project-specific from inside a single
     session can still turn out to match a case sitting in a *different* project's ledger, which
     promotes it globally instead. That's `/memory-audit`'s job, not this step's: from inside one
     project, route on what this session can actually see.
     (c) **a one-off fact or decision, not instructing future behaviour** — memory or
     `decisions.md`, ungated: it records what happened, not a rule to apply going forward.
     For (a) and (b) alike, **is it a rule yet?** — one real case is a candidate, not a rule: write
     it to the ledger the test above picked, commit it (see the commit note above), and write
     nothing to a rule file yet. Only a candidate whose second, contrasting case has arrived is
     promoted, and the promotion writes the rule to its home with both cases logged in the ledger.
     **An amendment that sharpens an existing rule needs its own second case** — it does not
     inherit the base rule's maturity.
     **Write `Case:` and `What a second case would need to show:` to name the actual mechanism,
     not just the symptom.** `/memory-audit` compares a project-level candidate against other
     projects' ledgers, potentially in a very different discipline — a vague symptom description
     risks a false match on wording alone where the two cases don't actually share a mechanism.
     Name what's actually going on.
     For (a) only, **who's the actor?** — four user-scope homes (`/memory-audit` applies this
     test from here, so it holds whatever the user's `CLAUDE.md` says): the user authoring a
     prompt/brief → `prompt-lessons.md`; the agent editing a standing doc or memory →
     `~/.claude/writing-standing-docs.md`; the agent briefing an executor or verifying its
     checkpoint → `~/.claude/writing-executor-briefs.md`; the agent at any other moment →
     `~/.claude/CLAUDE.md` § Working rules. An amendment re-derives its home
     rather than inheriting the home of the rule it extends.
     **Split, don't dual-write** — a candidate can have BOTH a rule-shaped core (global or
     project-level) AND a one-off residue; if (and only if) the residue isn't already recorded in
     the repo, route each part to its own home: the rule to whichever ledger it belongs in, the
     residue to memory/decisions.md with a one-way reference naming the lesson tag (e.g.
     "generalised as prompt-lessons [tag]", or "recorded as a project rule, see CLAUDE.md").
     prompt-lessons.md carries no links to *project* files — its origin log names the project as
     prose — but it does point to the other three user-scope homes when a rule's operative clause
     lives there, with the origin log staying canonical for rationale. Never write the full
     candidate in two homes — that's the restatement-drift the canonical-plus-pointers lesson
     exists to prevent.

2. **Cross-check each against the existing docs:**
   - `~/.claude/lesson-candidates.md` (bucket (a) candidates) or `<project root>/lesson-
     candidates.md` (bucket (b) candidates) — **check the ledger the routing test picked first,
     and check it for every candidate.** A first case is already parked here for many of them; if
     today's case is the *second, contrasting* one, the outcome is a promotion, not a new entry.
     Nothing else performs this within-session match, so skipping it leaves the pair unnoticed and
     the gate never opens. A bucket (b) candidate is checked only against THIS project's own
     ledger here — a match sitting in a different project's ledger is `/memory-audit`'s job, not
     this step's, since this session has no visibility into other projects' files. Aging of
     long-waiting candidates is not this step's job either way — `/memory-audit` owns that.
   - `<project root>/decisions.md` — any architectural/workflow decision with a rationale
   - `<memory dir>/MEMORY.md` — index of all memories
   - Relevant individual memory files (read them if the index entry suggests a match)
   - `~/.claude/prompt-lessons.md` — for prompt-lesson candidates: skip anything an existing
     checklist rule already covers; a candidate that *sharpens* an existing rule proposes an
     amendment to it, not a duplicate entry
   - `~/.claude/writing-standing-docs.md` — **read before writing any approved candidate**;
     it carries the operative rules for editing standing docs and memory bodies
     (contract-vs-snapshot, canonical-plus-pointers, replace-not-join, audience-referent)

3. **Propose each candidate for its own approval — write nothing until the user approves it.**
   Build the list of undocumented decisions/updates from steps 1-2.

   **Then triage it — most of it should not reach the user.** For each candidate, name the future
   moment that goes differently because this was written down. If you can't name one, drop it;
   "they'd be marginally better informed" is not one. **Most sessions produce none, and that is
   the expected outcome rather than a failed sweep. This is a bar, not a quota** — a genuinely
   consequential session can yield several, and dropping a real one to hit a number is the same
   mistake inverted. Having a valid home is not the same as being worth a decision: steps 1-2
   settled *where* a candidate goes, and a candidate can pass that and still fail here.

   Then go through what survives. Each candidate is asked in a question panel, laid out as
   follows:
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
     already said that. One apply/reject decision per candidate.
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
     unsaved work, so propose it exactly as step 3 does, with the text in the preview. **State
     what you checked and what you found, including "nothing outside the backlog" — silence
     here is indistinguishable from not looking.**
     (A skill step rather than a hook because this state is held in the session, not on disk —
     no script can read it. **Deliberately names no tool**: a tool named here can be removed
     from the harness, and the step would then fail on every run without anyone noticing. The
     survives-`/clear` test below is the version that cannot go stale.)
   - Check the session scratchpad directory for work-product rather than throwaway — a plan, a
     measurement, a recovered list. Propose moving it into the repo, or state that it's
     disposable.
   - **Never close a gap by writing a pointer.** "See the task list" / "sub-threads are tracked
     elsewhere" is the failure, not the fix: the durable file must carry the content.
   Applies to any future volatile surface, not just these two — the test is "does this survive
   `/clear`?", asked of anything that records outstanding work.

5. **Run the deterministic checks** — three scripts; one gates, two report:
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/check_memory_index.py <memory dir> <project root>`
     It checks the "every memory file ↔ exactly one MEMORY.md index line" invariant
     deterministically, reports MEMORY.md
     against its load limits — only the first 200 lines **or 25 KB, whichever comes first**, is
     loaded at session start; the rest is silently dropped (**bytes bind first here**, long index
     lines, so watch that percentage, not the line count) — then resolves every `[[link]]`
     citation against the memory dir's filenames: inside memory-file bodies, and inside every
     `*.md` in the repo. Citations inside code spans and fenced blocks are
     ignored, so writing about the syntax never trips it. All of it gates: non-zero exit = fix
     the listed mismatches, over-limit bytes, or dangling citations now, before ending the
     session, then re-run it.
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/check_thread_state.py --repo <project root>
     --backlog <project root>/backlog.md`
     It **reports and never gates — it always exits 0**. It prints three sections: task refs found
     in recent commits against each task's current `backlog.md` section, declared `blocked by #N`
     dependencies for review, and `Next up` block staleness (commits since its basis commit).
     **Every flagged task requires an explicit response — "still correct" is a valid response,
     silence is not.** That requirement is the forcing function here, chosen deliberately instead
     of a non-zero exit: a crying-wolf gate on a heuristic just trains the reader to ignore it.
     Skip this step if `<project root>/backlog.md` doesn't exist yet.
   - `python3 ${CLAUDE_SKILL_DIR}/scripts/context_budget_report.py --project-claude
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
   carry today's date and a basis line that names the latest commit as "Basis: commits through
   `<hash>`" (step 5's staleness check reads exactly that form) and lists the Open threads as of
   today; and **replace the block in full, never append** — appending turns it into the append-only
   ledger this file exists to avoid. Write it with the script, never by editing the file: pipe the
   whole new block, from its `## Next up` heading through its closing `---` line, into
   `python3 ${CLAUDE_SKILL_DIR}/scripts/write_next_up.py --backlog <project root>/backlog.md`,
   using a quoted heredoc (`<<'EOF'`) so the block's backticks reach it unchanged. It finds the
   old block's edges itself, and refuses, leaving the file untouched, unless the result has
   exactly one `Next up` block, ends with the old block's last line and changes nothing outside
   it. On a refusal, fix the block and run it again. Commit it (see the commit note above) — this
   is a `<project root>` write, push included once you've confirmed pushing is wanted. Skip this
   step if `backlog.md` doesn't exist yet.

7. **Report what you did** — list each candidate and its outcome (applied + file touched, or
   rejected), the reconcile result from step 4, the results of all three step-5 checks (the
   index-check result; the thread-state report together with your response to each flagged
   task; and the context-budget report), and the `Next up` block written in step 6. **Confirm every
   non-memory write from this run was committed** (`git status` in each of the two that is a git
   repo, not just recall; for one that isn't, say its writes are saved but not committed), name
   any memory-directory writes as filesystem-only per the commit note above, and state each
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

