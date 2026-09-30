# Lesson candidates & origin logs

Two things live here, both out of always-loaded context:

1. **Candidates** — a lesson observed once. One real case is a candidate, not a rule. It waits
   here until a second, contrasting case arrives, and costs nothing while it waits.
2. **Origin logs** — the case narratives behind rules that have been promoted. The rule states
   the claim in its own home; the cases that justify it and mark its boundary live here.

**Why this file exists.** The second-real-case gate in `~/.claude/CLAUDE.md` says a lesson must
be validated against a second real, contrasting case before it becomes a standing rule. In
practice a first case was written up as a rule anyway and annotated "provisional" — 11 of 19
rules carried such a tag on 2026-08-17. A disclaimer costs the same bytes as a rule and gates
nothing. Giving a first case somewhere to go makes the gate a place rather than something to
remember.

**Not auto-loaded, deliberately.** This grows without bound and only matters when a lesson is
being routed or a rule re-evaluated. `~/.claude/CLAUDE.md` carries no pointer to it, for the
same reason `under-explained-cases.md` carries none: both consumers are commands that know
where to look. Follows the precedent that file set.

**Two consumers, two questions** (assigned 2026-08-19; neither assumes the other ran):
`/finalise` step 2 does the **pairing** — is today's case the second, contrasting case for
something already parked here? That is checked at the moment the new case is in hand.
`/memory-audit` Part 2.6 does the **aging** — which candidates have waited long enough to be
promoted on evidence since accumulated, or retired, and which rules still carry a single-case
"Provisional" marker. That needs the corpus view a single session doesn't have.

## Capture

Written by `/finalise` step 1 when routing a lesson candidate, or appended the moment a case is
noticed — a session-end sweep may run after compaction has destroyed the verbatim detail.

Capture of a *candidate* needs no approval; it records an observation, not an instruction.
*Promotion* to a rule is a normal `/finalise` candidate and goes through the approval flow.

## Schema

### Candidate

    ### <one-line claim, imperative>
    - First observed: <absolute date> · <project/task>
    - Case: <what happened, what was concluded, what was actually true>
    - How to test it: <only where a test genuinely exists — see below. Otherwise write
      "no test — settled by a second real case" and stop.>
    - What a second case would need to show: <including the opposite direction, which
      bounds the claim rather than supporting it>
    - Would live in: <prompt-lessons | writing-standing-docs | writing-executor-briefs |
      CLAUDE.md Working rules>  (per the actor test)
    - Status: awaiting a second contrasting case

**Most candidates have no test, and that is normal.** They are settled by a second real case
arriving, not by running anything. Of the five parked on 2026-08-22, one was testable: the rest
were analytical claims with nothing to run them against, and one is held un-promoted precisely
*because* cold readers do not reproduce its failure. Do not invent a test to fill the field — an
invented one costs what a real one costs and gates nothing, which is the failure the
"provisional" tags already demonstrated.

**What a test looks like where one does exist.** A fixed setup that puts the claim in front of
something able to prove it wrong, written down before the answer is known. The worked example is
the one used on the clarity rule — see the entry headed "A description locates nothing":

    - a prompt template composed BEFORE any case had been collected, so a later author who
      has read the answers cannot shape it around them;
    - filled with three things only — the rule as it currently stands, the background facts
      the agent actually held at the time, and the sentence that failed;
    - run from a neutral directory against a fresh `claude --print --setting-sources project`,
      which loads neither CLAUDE.md, so the rule reaches the reader only via the prompt;
    - with the answer key withheld from that prompt — the user's real complaint, and the repair
      that eventually worked — then used to grade afterwards;
    - run at least twice per case, alongside control sentences the rule must leave ALONE;
    - graded against criteria written down before any output was read.

The shape generalises past wording rules: fix the setup, withhold the answer, include cases that
should NOT trigger, repeat each run, and decide what counts as a pass in advance. What varies is
what plays the part of the cold reader. (2026-08-22.)

### Origin log

    ### <the rule's opening words, verbatim, so it can be matched to its home>
    - Home: <file> § <section>
    - Promoted: <absolute date>
    - Cases: <full narratives, one per case, dated — moved verbatim from the rule>
    - Boundary: <what the opposite-direction case fixes, where one exists>


