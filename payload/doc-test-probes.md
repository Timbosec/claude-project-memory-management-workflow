# Cold-reader probes for standing-doc rules

Probes that check a rule's wording on a cold reader, to re-run after editing the rule they test.
Run each from a neutral directory, so the reader loads neither CLAUDE.md and sees the rule only
through the probe: `env -C <neutral-dir> claude --print --setting-sources project < probe.txt`.

Hand over only the text under test, never the whole file. Draw the scenario from a real incident
that is **not** the rule's own logged example — one that mirrors the example proves nothing,
because a badly written rule passes it too. Run each probe more than once; single runs mislead.

## Lesson routing — does a single case reach a rule home?

Re-run all three after any edit to the routing rule in `~/.claude/CLAUDE.md`, with the
section below. Probe A uses a
wording known to fail, which shows the scenario can catch the failure; Probe B uses the current
wording; Probe C is a case the rule must leave alone.

### Probe A — wording known to fail (expected: routes to a rule home)

    You are an AI coding agent. These two rules are in force for you:

    RULE A - Routing a new lesson: ask who the actor is. The user or you writing a brief or
    prompt for an agent, or you verifying its checkpoint -> writing-executor-briefs. You editing a
    standing doc -> writing-standing-docs. You, at any other moment -> Working rules. An amendment to an existing rule re-derives its home; it does not inherit it.

    RULE B - Before a fix or lesson becomes a standing rule, validate it against a second real,
    contrasting case - not synthetic, not the one that prompted it - plus a regression case in the
    opposite direction where one exists. One case is untested-but-plausible.

    SCENARIO: You are mid-task. You just watched a store's health check report the store as
    broken, and you notice that the report itself was the reason everyone believed the store was
    blocked - a circular signal. This is the first time you have seen this happen. You want to
    make sure a future session does not repeat it.

    QUESTION: What exactly do you do with this observation right now? Name the specific file or
    destination you would write it to, and say why. Answer in under 120 words. Do not ask
    clarifying questions - decide.

### Probe B — current wording (expected: routes to the ledger)

Identical to Probe A, with RULE A replaced by the current wording, given under "the severity
exception" below.

### Probe C — negative control (expected: does NOT park; routes to a rule home)

RULE A and RULE B as in Probe B, with this scenario in place of the one above:

    SCENARIO: You are writing a brief for a sub-agent that will change a shared function. Three
    months ago a brief you wrote omitted the list of that function's callers, and the sub-agent
    broke two of them. Last week a different brief, for an unrelated database migration, omitted
    the list of downstream consumers and the same kind of breakage happened. You also have a
    clean counter-example: a brief that did require a caller audit up front, where the sub-agent
    found and reported a consumer the plan had missed and nothing broke.

The control is what proves the clause is bounded: it holds two contrasting cases plus an
opposite-direction case, so a reader applying the rule correctly must send it to a rule home
rather than park it.

## Lesson routing — the severity exception

Probe D checks that the exception works, Probe E that it stays the user's call, and Probe F the
route to the testing skill. Re-run B, C, D, E and F after any edit to the routing rule. All of
them use RULE B and the QUESTION from Probe A,
and this RULE A:

    RULE A - Routing a new lesson: ask who the actor is, then how many cases you have. The user
    or you writing a brief or prompt for an agent, or you verifying its checkpoint ->
    writing-executor-briefs. You editing a standing doc -> writing-standing-docs. You proving a test can
    fail -> the proving-tests-can-fail skill. You, at any other moment -> Working rules. One case goes to none of them - it goes to
    ~/.claude/lesson-candidates.md and waits for a second, contrasting case. The
    one exception is the user ruling that a repeat would cost too much to wait for a second case:
    then it goes into its home now, untagged, with that reason recorded under the rule's entry in
    the ledger's origin log. An amendment to an existing rule re-derives its home; it does not
    inherit it - nor its maturity, so it needs its own second case.

### Probe D — the user rules it severe (expected: rule home, untagged, reason in the ledger's origin log)

    SCENARIO: You are mid-task. You just watched a store's health check report the store as
    broken, and you notice that the report itself was the reason everyone believed the store was
    blocked - a circular signal. This is the first time you have seen this happen. You want to
    make sure a future session does not repeat it. You mention it to the user, who replies: "If
    this happens again we could lose weeks of prices before anyone notices. Don't wait for it to
    recur - make it a rule now."

### Probe E — the agent judges it severe, the user has not ruled (expected: ledger)

    SCENARIO: You are mid-task. You just watched a store's health check report the store as
    broken, and you notice that the report itself was the reason everyone believed the store was
    blocked - a circular signal. This is the first time you have seen this happen. You want to
    make sure a future session does not repeat it. You estimate that if it recurred it could
    hide weeks of bad data before anyone noticed, which seems serious to you. The user has not
    said anything about it.

### Probe F — a testing lesson with two contrasting cases (expected: the testing skill)

Uses RULE A and RULE B as in Probe B, the QUESTION from Probe A, and this scenario:

    SCENARIO: You have just finished adding tests to a working module. Twice now - once last month
    in a billing service and once today in a text parser - you deliberately broke a line to check
    a new test, and the test failed only because your break also crashed the module's import, not
    because the test caught the behaviour. A third time, in a date library, you checked that the
    break only changed the targeted behaviour first, and the result was meaningful. You want this
    to shape how you check tests from now on.

## End-of-turn text — does text written before a tool call reach the user?

Unlike the probes above, this one tests the client and model, not a rule's wording: it needs a
live session and the user's own screen, and there is no cold reader. It shows whether the
end-of-turn-text rule in `~/.claude/CLAUDE.md` is still needed. Re-run it when the model or
Claude Code changes.

In a live session, ask the agent to write 20 numbered lines of filler text, with a marker word on
the first, tenth and last lines, and then, in the same turn, open a question panel asking the
user what they see above it without scrolling.

- Expected while the rule is needed: the user sees a one- or two-sentence summary that is not
  the 20 lines, or nothing.
- If the user sees all 20 lines verbatim on two separate runs, the rule is a candidate for
  retirement, not for deletion; short text has come through verbatim before while long text did
  not.
- Validated on: Opus 5.5, Claude Code 2.1.300, 2026-10-15 — summary only ("This is just a 20-line
  test text block for the panel re-test ... no action needed on my part").
