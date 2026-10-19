# Writing & editing standing docs

Operative rules for instruction files, skills, CLAUDE.md and memory bodies.
Consult before any such edit. Each rule's cases and rationale are logged in the
origin logs of `~/.claude/lesson-candidates.md`; the tag after a rule names its entry
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
- **When you test a rule, hand it to a fresh agent (a cold test) and include cases the rule must
  leave alone, not only ones where it should apply.** A test that only checks whether the rule
  applies proves half of it: applying it where it doesn't belong goes unseen, and that is how a
  rule turns into padding. Run each case more than once; single runs mislead. **Ask the agent to
  act on the rule, never whether the rule is clear:** that question invites a yes.
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
  the fact from the code, cut the rule or, if it must hold every time, make it a hook. Check
  this by running a real session without the rule on the case that prompted it, not by
  judgement.
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
- **Its wording is calm and concrete.** Write it as a plain instruction ("Use this tool
  when…"), not a forceful one ("CRITICAL: you MUST use this tool…"), and leave out catch-all
  nudges such as "if in doubt, do X": forceful wording makes Claude apply a rule where it
  doesn't belong. Emphasis (capitals, bold on a single word, or words like CRITICAL, MUST or
  IMPORTANT) is a fix for one rule that sessions show being skipped: add it to that line alone,
  since emphasis on many lines makes none stand out. A rule that must hold every time goes in a
  hook, where code can check it. An abstract phrase gets a plain word or a short example. The
  cold test below won't catch this, since an agent can often work out a phrase a person would
  stumble on.

Then give a fresh agent only the rule and ask it when the rule applies and what it would do, as
the cold-test rule above describes. An answer that misses the situation or the action means the
opening or a term needs work.
