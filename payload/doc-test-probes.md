# Cold-reader probes for standing-doc rules

Probes that check a rule's wording on a cold reader, to re-run after editing the rule they test.
Run each from a neutral directory, so the reader loads neither CLAUDE.md and sees the rule only
through the probe: `env -C <neutral-dir> claude --print --setting-sources project < probe.txt`.

Hand over only the text under test, never the whole file. Draw the scenario from a real incident
that is **not** the rule's own logged example — one that mirrors the example proves nothing,
because a badly written rule passes it too. Run each probe more than once; single runs mislead.

## Lesson routing — does a single case reach a rule home?

Re-run all three after any edit to the routing rule in `~/.claude/CLAUDE.md`. Probe A uses a
wording known to fail, which shows the scenario can catch the failure; Probe B uses the current
wording; Probe C is a case the rule must leave alone.

### Probe A — wording known to fail (expected: routes to a rule home)

    You are an AI coding agent. These two rules are in force for you:

    RULE A - Routing a new lesson: ask who the actor is. The user authoring a prompt or brief ->
    prompt-lessons. You editing a standing doc -> writing-standing-docs. You briefing an executor
    or verifying its checkpoint -> writing-executor-briefs. You, at any other moment -> Working
    rules. An amendment to an existing rule re-derives its home; it does not inherit it.

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

Identical to Probe A, with RULE A replaced by the current wording:

    RULE A - Routing a new lesson: ask who the actor is, then how many cases you have. The user
    authoring a prompt or brief -> prompt-lessons. You editing a standing doc ->
    writing-standing-docs. You briefing an executor or verifying its checkpoint ->
    writing-executor-briefs. You, at any other moment -> Working rules. One case goes to none of
    them - it goes to ~/.claude/lesson-candidates.md and waits for a second, contrasting case.
    Writing it into a home under a "provisional" tag is the failure this replaces: the tag costs
    what a rule costs and gates nothing. An amendment to an existing rule re-derives its home; it
    does not inherit it - nor its maturity, so it needs its own second case.

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

