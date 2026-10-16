# Writing & editing standing docs

Operative rules for instruction files, skills, CLAUDE.md and memory bodies.
Consult before any such edit. Each rule's cases and rationale are logged in the
origin log of `~/.claude/prompt-lessons.md`; the tag after a rule names its entry
there.

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
- **A cold test that only checks whether the rule fires proves half of it.** Include cases
  the rule must leave ALONE — over-application is invisible to a pass-only test, and it is
  how a rule turns into padding. Run each case more than once; single runs mislead. **Test a
  wording by handing it to a fresh agent and asking it to ACT on the rule, never whether the
  rule is clear** — that question invites a yes.
- **In an agent-facing file, "you" is the agent.** The human is "the user", third
  person. De-personalising a file ("make this project-agnostic") can silently invert an
  approval gate — "await your approval" hands a human-in-the-loop check to the agent
  approving itself. After any such pass, verify every second-person pronoun still
  resolves to the agent. → `[audience-referent]`

