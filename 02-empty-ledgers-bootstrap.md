# Bootstrap prompt 2 of 5 — empty ledger files (run ONCE per machine)

These two files are accumulating logs, not rule files — on the source
machine they hold dozens of entries, but every one of those entries is a project-specific
observation (specific tools, task numbers, one-off incidents) that can never find a matching
"second contrasting case" from unrelated future work. Porting the entries would just be noise, so
only the schema and the explanatory front matter comes across — both files start with zero
entries here, exactly as they once did on the source machine before any case had been logged.

*(Reading this file on its own, not as part of `00-run-all.md`? Paste it as a single message,
after prompt 1 has been run.)*

## Instructions for Claude

Create these two files with exactly the content given below. If either already exists, stop and
show me its content before overwriting. Do not commit/push — same reasoning as prompt 1.

**Known gaps, left as-is deliberately, not bugs to fix:** the embedded text below references two
things that are NOT part of this bootstrap and won't exist on this machine yet — a
`/memory-audit` skill (does periodic "aging" review of stale candidates) and a session-start hook
that nudges re-evaluation of `under-explained-cases.md` after ~10 new entries. Until/unless those
are built separately, both files' review timing is manual. Don't invent stand-ins for either.

---

### File: ~/.claude/lesson-candidates.md

Note the four-backtick fence below (not the usual three) — it's wide enough to safely contain
the file's own internal example blocks without them prematurely closing it. Write only what's
between the fence markers as the file's content; don't include the fence lines themselves.

````markdown
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


````

---

### File: ~/.claude/under-explained-cases.md

Same four-backtick note as above — this file's own "Harness template" section contains a
three-backtick example block, which is exactly what the wider fence is protecting against.

````markdown
# Under-explained cases — evidence log

Real instances where the user had to ask what something meant. Evidence for the
`~/.claude/CLAUDE.md` § Working rules bullet **"Write the sentence so it carries its own
meaning; keep the symbol as a trailing pointer, not the carrier of the fact."**

**Why this file exists.** That rule was tuned against seven sentences the agent wrote itself,
to probe a rule the agent wrote itself — so passing the test said little about real use. Two
clauses were added on the strength of that fixture and one of them (a guard against stating a
direction backwards) was cut again once it turned out no such failure had ever actually
happened to the user. Real captured cases are the corpus that evaluation needed.

**Not auto-loaded, deliberately.** This grows without bound and only matters at evaluation
time. `~/.claude/CLAUDE.md` carries no pointer to it for the same reason — the finalise skill
writes to it and will raise re-evaluation when it's worth doing.

## Capture

Written by the `/finalise` skill, or appended the moment the agent notices one, since a
session-end sweep may run after compaction has destroyed the verbatim text.

**Capture is automatic and needs no approval** — an entry records what was said, not what
should be instructed. Any *rule change* derived from this corpus goes through finalise's normal
approve-one-candidate-at-a-time flow.

**Quote verbatim, never paraphrase — especially the offending sentence.** The agent is both the
author of the offending text and the recorder of it, so paraphrasing is where the record would
quietly get kinder to itself. Err toward recording: a borderline case costs a few lines, a
missed one costs a data point that cannot be reconstructed.

## Evaluating

**Wait for ~10 entries since the last evaluation, not ~10 in the corpus overall.** Tuning on one
or two is what produced the over-fitting this file exists to correct. But two things are
learnable before then:

- **The collection rate is itself the metric.** Frequent entries mean the rule is not working.
  Entries drying up means it is. That signal starts at entry 1 and needs no threshold.
- A single entry can still *disprove* a clause — as one did here.

**When an evaluation finishes, record where it stopped.** Add a line to this file reading
`Last evaluated: <date> — through entry <N>`, with `<N>` replaced by the last case number
actually graded — never leave the placeholder itself in the file, since it doesn't parse as a
number and the corpus would then read as never evaluated. On the source machine a session-start
hook (`under_explained_line()` in a `session_health.py` script) finds the highest such line and
stays silent until 10 further entries have landed since it — that hook is NOT part of this
bootstrap, so on this machine evaluation timing is manual until/unless an equivalent is built;
skipping this step still leaves no record that an evaluation happened.

No entries yet, so nothing to evaluate — the first "Last evaluated" line gets added once ~10
entries have accumulated.

**A cold agent does the rewriting — not you.** An earlier version of this file said to "evaluate
blind", attempting the rewrite yourself while disregarding the repair you had just read. That is
not a mechanism; once the file is read the repair is in context and there is no way to un-read
it. (Second instruction in this rule's history to demand an impossible internal state — the
first asked the agent to determine what the user had read.)

Contamination is controlled by **what goes into the cold agent's prompt**, not by what is in
yours — which is why the repair can live safely in this same file. Use the template below
verbatim; it was written before any cases existed precisely so that a later composer, who has
read the repairs, cannot steer it.

The cold agent is given the rule and the offending sentence. It is **not** given the user's query
or the repair: the query names the very thing that needed fixing, so handing it over leaks the
answer and tests nothing. Judge its output against them afterwards — did it fix what the user
actually complained about?

This tests **the rule**, which is the open question. Whether the agent-with-full-context can
write a good sentence is not.

**Outcome is recorded as observed, not concluded.** A second pushback is a reliable negative.
Silence is a weak positive — the user may have been satisfied, or moved on, or had enough of the
topic. So the field says "no further pushback", not "successful", and a later reading draws its
own conclusion.

## Harness template

Written 2026-08-10, before any case had been evaluated, so that a later composer cannot shape it
around answers they have seen. **Use it verbatim.** Fill only the three bracketed blocks, from
the case entry. Run it against a genuinely clean reader — an Agent-tool sub-agent carries a
stale session-start snapshot of the CLAUDE.md files and would not see the current rule:

```
env -C <a-neutral-dir> claude --print --setting-sources project < prompt.txt
```

> You are writing a status summary for a user about work done on their codebase.
>
> One of your standing operating instructions reads:
>
> ---
> [PASTE the current rule bullet from ~/.claude/CLAUDE.md § Working rules, verbatim]
> ---
>
> Below is a draft sentence for the summary. Apply the instruction to it. Output the sentence
> you would actually send the user, then on a new line "CHANGED" or "UNCHANGED". Do not explain
> the instruction back to me. Just apply it.
>
> Context you have available (you have read the code; the user has not):
>
> [PASTE what the symbols in the sentence actually mean — the agent must have the domain facts,
> because in real use it did]
>
> The draft sentence:
>
> [PASTE the offending sentence verbatim, plus its surrounding sentences]

Run each case at least twice: single runs have already produced misleading results here — one
wording looked fixed on one run and inverted on the next.

Include **negative controls** in the same batch — sentences using filenames, project jargon, or
no symbols at all, which the rule should leave alone. Over-application is the failure mode a
pass-only test cannot see, and it is the one users have flagged as their main concern.

---


## Entries

(none yet — entries accumulate here as cases are captured)
````
