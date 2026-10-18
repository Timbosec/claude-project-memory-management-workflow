---
name: proving-tests-can-fail
description: How to check that a test can fail before trusting it - write the test before the fix, revert a fix to watch its regression test fail, or break working code on purpose to check new tests. Use when adding or changing tests, or when checking tests a sub-agent wrote.
---

# Proving a test can fail

- **A passing test shows the code works only if it fails on code that doesn't. Before you trust one,
  run it against a broken version and watch it fail.** Where you can, write the test before the fix
  and watch it fail on the unfixed code; then there is nothing to revert.
- **For a regression test written after the fix, revert the fix and confirm the test fails.** Assert
  at the layer the bug lived at, and break the *value*, not just the guard. A test that takes its
  expected answer, or its limits, from the code it checks agrees with that code whatever the code
  does. A revert that hangs is not a pass.
- **When you revert a fix to check that its test fails, undo only that fix, not the whole file.** A
  blanket stash undoes every other edit in the checkpoint too, so a failure can't say which one
  caused it, and a test that would also fail because of another edit the stash undid reads as proof.
  Leave the rest in place, and the failure has one possible cause.
- **When checking a regression test whose fix changed how the code is called (for example a
  function's inputs, or a renamed method or attribute), a plain revert proves nothing.** The test
  errors on the call (in Python, a TypeError or AttributeError), which shows the interface changed,
  not that the behaviour did. Put back the old behaviour behind the new interface instead (for a new
  input: accept it and ignore it), so the only thing that can fail is the behaviour under test.
- **When checking a regression test where the old code reaches the same overall result by a
  different route, a test asserting only that result stays green on revert** and proves nothing: it
  agrees with the code whatever the code says. Assert a finer detail only the new path produces (a
  diagnostic string, a count), not just the status.
- **When the tests are new coverage over code that already works, break the code yourself.** Make
  one deliberate break at a time in the production line each test targets, undoing each before the
  next, and require every new test to fail under at least one. First check that each break actually
  changes what the code does: one that doesn't can't be caught by any test, so a test surviving it
  proves nothing either way. A test that survives every break that does is asserting something other
  than what it claims. **Record which tests failed under which break, not a count:** the mapping
  shows each test is anchored to the behaviour it names, and a total hides a test riding on another
  test's assertion.
- **When you break code to check tests, the tests you did not aim at are how you check the break.**
  Running only the targeted tests can't tell a valid break from one that could never have worked: a
  bad break often gives the targeted tests the result you expected anyway, because breaking how the
  code handles valid input produces exactly what a test for invalid input expects. For example, a
  break that makes the code reject every input still satisfies a test that expects bad input to be
  rejected. Untargeted tests staying green means the break looks as narrow as you described; if many
  of them fail, it was wider, which changes what its failure proves.
