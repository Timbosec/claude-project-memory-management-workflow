# Under-explained cases — evidence log

Real instances where the user had to ask what something meant. Evidence for the
`~/.claude/CLAUDE.md` § Working rules bullet **"Write the sentence so it carries its own
meaning; keep the symbol as a trailing pointer, not the carrier of the fact."**

**Why this file exists.** A clarity rule tested only against sentences the agent wrote to test
it passes them and says little about real use. These captured cases, real moments where the user
was confused, are the corpus the rule is evaluated against.

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
- A single entry can still *disprove* a clause.

**When an evaluation finishes, record where it stopped.** Add a line to this file reading
`Last evaluated: <date> — through entry <N>`, with `<N>` replaced by the last case number
actually graded — never leave the placeholder itself in the file, since it doesn't parse as a
number and the corpus would then read as never evaluated. Nothing reads this line
automatically: it is how the next evaluation knows where to start counting, and skipping this
step leaves no record that an evaluation happened.

No entries yet, so nothing to evaluate — the first "Last evaluated" line gets added once ~10
entries have accumulated.

**A cold agent does the rewriting — not you.** Once you have read this file, the repair is in
your context and cannot be un-read, so attempting the rewrite yourself "blind" is not possible.

Contamination is controlled by **what goes into the cold agent's prompt**, not by what is in
yours — which is why the repair can live safely in this same file. Use the template below
verbatim: it is fixed in advance so that whoever runs it, having read the repairs, cannot steer
it.

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

**Use it verbatim.** Fill only the three bracketed blocks, from
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

Run each case at least twice: single runs mislead, and the same wording can look fixed on one
run and inverted on the next.

Include **negative controls** in the same batch — sentences using filenames, project jargon, or
no symbols at all, which the rule should leave alone. Over-application is the failure mode a
pass-only test cannot see.

---


## Entries

(none yet — entries accumulate here as cases are captured)
