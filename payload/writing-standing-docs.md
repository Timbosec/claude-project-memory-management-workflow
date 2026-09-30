# Writing & editing standing docs

Operative rules for instruction files, skills, CLAUDE.md and memory bodies.
Consult before any such edit. Rationale, origin cases and the prompt-writing
consequences of each rule: `~/.claude/prompt-lessons.md` (canonical) — the tags
below are its origin-log entries.

## What to write down

- **Contract or snapshot?** Invariants, allowed vocabularies and write rules must be
  written — data can't be their source of truth. Facts derivable in one cheap read
  (column counts, file lists, "X is pending") should be deleted or de-specified, not
  maintained: correcting a snapshot just re-arms it. → `[contract-vs-snapshot]`
- **Non-derivable nuance earns a line.** If inspecting the system *misleads* without
  the note — "this file is created lazily, absence is normal" — write it. That's the
  opposite of a snapshot. → `[contract-vs-snapshot]`
- **Staleness triage:** risk ∝ how often the fact changes × how silently it drifts.
  High-churn + silent-drift facts don't belong in standing text.
  → `[contract-vs-snapshot]`
- **An exclusion must carry the question it answers.** "Don't use X here", written about one
  situation, reads as universal — the reader cannot recover the original situation from the
  note, so it gets applied to questions it was never about. Write the scope into the exclusion,
  then test it: strike the scope clause, and if the line still reads as a blanket ban it will be
  obeyed as one. Both directions, same corpus: "this service → no direct fetch" carried no scope,
  was written about routine polling, and ruled out a lighter method on a question about state
  that only exists after a heavier process runs — which the lighter method can't reach, at any
  number of attempts. Against it, "drop the fallback model — don't reinstate it without a fresh
  cost decision" names exactly what would reopen the question, so a reader holding new cost
  information knows the note does not bind them. (Provisional — one failure, one exemplar.)

## Where to write it

- **State each rule once; point everywhere else.** Every restatement in a second place
  is a future drift site — designate one canonical home and reduce every other
  occurrence to its operative clause plus a pointer. Copies left to "stay aligned" end
  mutually consistent and all wrong. Exception: cold-start contexts (sub-agent prompt
  templates) can't follow pointers, so those inlines are load-bearing — mark them
  explicitly as rendered-from-canonical so syncs happen.
  → `[canonical-plus-pointers]`

## How to edit

- **Superseding text must replace, not join.** Minimal-diff editing writes new text
  against the insertion point, not the section — so the old, now-contradicted wording
  survives beside it and the doc says both things. After any behavioural edit, re-read
  the **enclosing section** as a future reader and delete or amend whatever the new text
  supersedes. Docs have no test suite; the read-back is the red-test gate. Scope is the
  enclosing section or rule-cluster, not the whole file. → `[replace-not-join]`
- **A rule you can't state in one sentence isn't finished.** Length is paid at every read, and
  a rule buried in its own rationale won't fire. Write the operative clause first, then keep
  only what tells a reader WHEN it applies — trigger conditions earn their space, restated
  rationale doesn't. Condensing usually finds the sharper point rather than losing it. But
  don't cut to a slogan: "verify everything" is shorter than a trigger condition and fires on
  nothing. (Provisional.)
- **An instruction must name an action, not an internal state.** "Don't let X influence
  you", "work out whether the user has already read this", "evaluate blind" — none can be
  executed or checked: the reader either already has the information or cannot obtain it.
  Rewrite as something observable — a test on the text in front of you, or a step that controls
  what another process is given. If you cannot say what the reader would *do* differently, the
  clause is decoration and will read as satisfied while doing nothing.
  (Provisional — two instances, one session, same exercise.)
- **A rule that only shows itself catching something is half-written — include a worked pass.**
  A failure case teaches what to avoid; it does not show what applying the rule produces, so the
  reader cannot tell a clean result from never having run the check. Prefer one example in each
  direction from the same episode: they share context, so the pair costs barely more than the
  catch alone and marks the boundary the catch cannot. (Provisional — one exercise.)
- **A cold test that only checks whether the rule fires proves half of it.** Include cases
  the rule must leave ALONE — over-application is invisible to a pass-only test, and it is
  how a rule turns into padding. Run each case more than once; single runs mislead.
- **In an agent-facing file, "you" is the agent.** The human is "the user", third
  person. De-personalising a file ("make this project-agnostic") can silently invert an
  approval gate — "await your approval" hands a human-in-the-loop check to the agent
  approving itself. After any such pass, verify every second-person pronoun still
  resolves to the agent. → `[audience-referent]`

