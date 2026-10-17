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

## Before a new or reworded rule goes in

Check the rule against each line and fix what fails before proposing it. The same list is what
`/memory-audit` checks existing rules against.

- **Its opening names the situation it covers, not only a fact about it**, so a reader who
  stops after the first sentence knows when it applies. The action can imply the situation
  ("Default to a high-level answer" covers every answer); it needs no "When ..." clause. For a
  skill, the description says what it does and when to use it.
- **Claude wouldn't do it without the rule.** If Claude already behaves this way, or could read
  the fact from the code, cut the rule or, if it must hold every time, make it a hook.
- **It doesn't repeat itself, explain what Claude already knows, or carry bookkeeping.** Dates,
  case notes and maturity tags go to the origin log. A short reason that says what the rule
  protects stays: Claude generalises from it. A clause saying how to carry the rule out is not
  repetition, and a rule that has no reason needs none added.
- **It does one job, in the place that loads when it's needed:** `CLAUDE.md` if it matters in
  most sessions, a `.claude/rules/` file with `paths` if only for some files, a skill if only for
  some tasks, a hook if it must hold every time and code can check it.
- **Nothing in it goes out of date:** no fact about the tool or model that a later version could
  change, and no wording tied to a date or to "now", such as "the new API" or "currently". Where it
  rests on how a model or client behaves, record the model and version it was checked on beside
  its probe in `~/.claude/doc-test-probes.md`, never in the rule.
- **Its standing matches its evidence**, as the routing rule in `~/.claude/CLAUDE.md` sets out.
- **It contradicts no other rule** in `CLAUDE.md` or the rule files, and none of the guidance
  Claude Code adds on its own, such as its commit instructions.
- **Each thing the file names keeps one name throughout:** a defined term, a file, a tool or a
  step. Ordinary words can vary.

Then give a fresh agent only the rule and ask it when the rule applies and what it would do, as
the cold-test rule above describes. An answer that misses the situation or the action means the
opening or a term needs work.
