# Briefing an executor & verifying its work

Operative rules for authoring a plan or brief for a sub-agent, and for accepting its
checkpoints. Consult before writing either, and before approving a checkpoint.

This file is not auto-loaded, so its length is paid only when it is read.

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
- Before an executor changes a shared symbol, make it report every caller as its own checkpoint
  — an audit, not a gate; what a plan omits is where the surprises are. **Verify the remedy
  separately from the findings** — run the proposed fix against the failing case; correct facts
  routinely carry a fix that misses them.
  **A caller audit finds what INVOKES a symbol; it cannot find what depends on what the symbol's
  answers MEAN.** Scope by where the fact is expressed or re-derived, not by what calls it: a site
  that reconstructs a value's significance is a consumer even when it never names your symbol. The
  question that finds them is "what does this change make newly true, and who already answers that
  question for themselves?" (The boundary: caller scope answers reach, never meaning.)
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
  carries OTHER uncommitted, already-reviewed work riding alongside whatever is being temporarily
  changed — a discard command takes that with it too, not just the probe. Only a string-scoped
  tool (Edit, or a `sed` whose inverse is applied the same way) round-trips symmetrically;
  confirm `git diff --stat` matches the pre-mutation baseline before trusting the revert, rather
  than assuming it worked.

