# Briefing an executor & verifying its work

Operative rules for writing a plan, brief or prompt for an agent, whether yours or one the user
asks for help with, and for accepting a sub-agent's checkpoints. Consult before writing any of
these, and before approving a checkpoint.

This file is not auto-loaded, so its length is paid only when it is read.

## What the brief must spell out

- **When a brief asks an agent to edit standing docs, spell out the rules from
  `~/.claude/writing-standing-docs.md` that the edit needs.** A cold agent neither loads nor
  infers them. To document a system or fix stale docs, have it sort each fact into contract,
  snapshot or nuance, and delete snapshots rather than refresh them. To update a doc, ask for the
  section to read as one consistent instruction afterwards, not only "add X". To make a file
  generic, the human becomes "the user", and every "you" must still mean the agent afterwards.
- **When a brief would tell an agent to remember a correction, check whether the correction can
  be computed; if it can, specify the code, hook or validation that makes it.** A brief that says
  "fix it and add a note" produces the note. The rule itself is `[rule-into-code]` in
  `~/.claude/CLAUDE.md`.
- **When a brief says "fix it and record the lesson", make it require checking the lesson against
  a second real, contrasting case first.** Otherwise the agent ships the first plausible fix as a
  rule. The rule itself is `[second-real-example]` in `~/.claude/CLAUDE.md`.
- **When a brief's output is findings or choices for the user, say how they are presented:** one
  at a time, each recorded before the next, with anything the user must read in the text that
  ends the turn, as `[one-decision-at-a-time]` in `~/.claude/CLAUDE.md` and the rule beside it
  set out. Otherwise the agent asks everything at
  once, decides silently, or asks about context the user never saw.

## Running a delegated build and checking its work

- **When you delegate a build, size and commit the work so an interruption costs little.** A usage
  limit can end a sub-agent's run partway, leaving a partly applied tree; Claude is told the run was
  cut off, but not what state the tree is in. Keep each checkpoint small enough to lose, and commit
  a verified one before starting the next rather than batching.
- **When you commit a verified checkpoint of a delegated build, append one line to the backlog item
  before starting the next: the commit hash and the plan file's path.** Not a restated checkpoint
  number or summary, which could drift out of step with the plan itself.
- **When a sub-agent dies mid-build, establish where it stopped from the working tree and the test
  suite, not by asking it.** The backlog line only narrows which plan and commit apply; it doesn't
  replace checking the tree and the tests.
- **When an interrupted sub-agent's build is to continue, prefer resuming that same agent once its
  limit resets, and scope the resume to the single remaining step.** It keeps context a fresh agent
  would have to re-derive, but it returns with the whole build still in mind, so say what to leave
  alone.
- **Before an executor changes a shared symbol, make it report every caller as its own checkpoint.**
  It is an audit, not a gate: what a plan omits is where the surprises are.
- **When findings come with a proposed fix, from an audit, a review or your own investigation,
  verify the fix separately from the findings:** run it against the failing case. Correct findings
  routinely come with a fix that misses them.
- **When a shared symbol changes, also find what depends on what its answers mean; a caller audit
  cannot.** Callers show how far a change reaches, never what it means to the code relying on it.
  Scope this search by where the fact is expressed or re-derived, not by what calls the symbol: a
  site that reconstructs a value's significance is a consumer even when it never names your symbol.
  The question that finds them is "what does this change make newly true, and who already answers
  that question for themselves?"
- **Briefing a sub-agent that will add or change tests, or accepting its tests:** load the
  `proving-tests-can-fail` skill first. It holds the rules on proving a test can fail; spell out
  in the brief the ones the sub-agent must follow, rather than relying on it to load the skill.
- **Copying a working pattern: name what makes it safe at the source, check the target has it.**
  Before reusing a pattern in a new context, name the specific property that made it safe where it
  came from, and check the new target actually has that property — a pattern that looks identical
  can be safe for a reason that doesn't transfer (e.g. relying on a process being short-lived, or
  on a miss being non-authoritative), and copying it unchanged silently drops the protection it
  depended on while looking like a faithful port.
- **When spot-checking a sub-agent's still-uncommitted checkpoint with a temporary revert, use a
  scoped edit for both the revert and the restore — never a repo-level discard command.**
  `git checkout --`/`restore`/`reset` operate at whole-file granularity regardless of how narrow
  the intended change was, and a checkpoint under review is exactly the state where the file
  carries other uncommitted, already-reviewed work riding alongside whatever is being temporarily
  changed — a discard command takes that with it too, not just the probe. Only a string-scoped
  tool (Edit, or a `sed` whose inverse is applied the same way) round-trips symmetrically;
  confirm `git diff --stat` matches the pre-mutation baseline before trusting the revert, rather
  than assuming it worked.

