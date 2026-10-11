# Briefing an executor & verifying its work

Operative rules for authoring a plan or brief for a sub-agent, and for accepting its
checkpoints. Consult before writing either, and before approving a checkpoint.

This file is not auto-loaded, so its length is paid only when it is read.

- **A delegated build will be interrupted mid-flight; size and commit the work so that costs
  little.** Session limits kill sub-agents routinely, leaving an unreported, partly-applied
  tree. Keep each checkpoint small enough to lose, and commit a verified one before starting
  the next rather than batching. At that same moment, append one line to the backlog item —
  the commit hash and the plan file's path, not a restated checkpoint number or summary that
  could drift out of sync with the plan itself. When one dies, establish where it stopped from
  the tree and the test suite, not by asking the agent — the pointer only shortens the search
  for which plan and commit apply, it doesn't replace verifying against ground truth. Resuming
  the same agent after the reset preserves context a fresh one would re-derive — but scope the
  resume to the single remaining step and say what to leave alone, because it returns with the
  whole build still in mind.
- Before an executor changes a shared symbol, make it report every caller as its own checkpoint
  — an audit, not a gate; what a plan omits is where the surprises are. **Verify the remedy
  separately from the findings** — run the proposed fix against the failing case; correct facts
  routinely carry a fix that misses them.
  **A caller audit finds what INVOKES a symbol; it cannot find what depends on what the symbol's
  answers MEAN.** Scope by where the fact is expressed or re-derived, not by what calls it: a site
  that reconstructs a value's significance is a consumer even when it never names your symbol. The
  question that finds them is "what does this change make newly true, and who already answers that
  question for themselves?" (The boundary: caller scope answers reach, never meaning.)
- A regression test that never went red proves nothing: **revert the fix and confirm it
  fails**, assert at the layer the bug lived at, and mutate the *value* not just the guard —
  a test bounded by the thing it checks agrees with it whatever it says, and a revert that
  hangs is not a pass.
  **When the fix changed a SIGNATURE, a bare revert proves nothing either** — the tests fail
  with TypeError/AttributeError on the call, which shows the signature moved, not that the
  behaviour did. Restore the PRE-FIX SEMANTICS against the NEW signature instead (accept the
  new parameter, ignore it), so the only thing that can fail is the behaviour under test.
  Kept on one case: an executor applies it at every checkpoint, so waiting for a second case
  costs more than the rule does.
  **The same trap without a signature change: the pre-fix code reaches the SAME coarse outcome
  by a different route.** A test asserting only that outcome stays green on revert and proves
  nothing — it agrees with the code whatever the code says. Assert a finer field the new path
  ALONE can produce (a diagnostic string, a count), not just the status.
  **Revert only the change under test, not the whole file.** A blanket stash undoes every edit in
  the checkpoint at once, so a red result cannot say which one caused it — and a test that would
  also fail for an unrelated reverted reason reads as proof. Restore just the stage the claim is
  about, leave the rest in place, and the failure has one possible cause.
  Kept on one case: an executor applies it at every checkpoint, so waiting for a second case
  costs more than the rule does.
  **When there is no fix to revert — the tests are new coverage over code that already works —
  mutate instead.** A test that has never been red is not evidence until you have watched it fail.
  Change the production line it targets, one change at a time, reverting each before the next, and
  require every new test to go red under at least one; a test that survives all of them is
  asserting something other than what it claims. **Record which tests went red under which
  mutation, not a count** — the mapping is what shows each test is anchored to the behaviour it
  names, and a bare total hides a test that is riding on someone else's assertion.
  Kept on one case: an executor applies it at every checkpoint, so waiting for a second case
  costs more than the rule does.
  **The mutation is an instrument; the tests it did NOT target are how you check it.** Running
  only the targeted tests cannot distinguish a valid perturbation from one that could never have
  worked — an invalid one often passes its targets for free, because breaking the correct case
  produces exactly what a negative test asserts. Untargeted tests staying green is the instrument
  reading clean; a wide spillover means the mutation is coarser than it was described as, which
  changes what its red result proves.
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

