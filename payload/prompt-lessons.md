# Prompt Lessons — best-practice rules for writing prompts & briefs

**Purpose:** a quick-reference checklist for **authoring** a prompt or brief, consulted when the
user asks for help writing or reviewing one. Rules are distilled from real discussions where a
sharper approach emerged than the original prompt asked for.

**Scope:** this file is about text the user commissions. Rules for *editing* standing docs, skills
and memory bodies live in `~/.claude/writing-standing-docs.md`; rules governing the agent's own
conduct at any moment live in `~/.claude/CLAUDE.md` § Working rules. The **origin log below stays
canonical** for every rule's rationale and history, including those whose operative statement now
sits elsewhere — the other homes carry the operative clause and point back here.

**Write rules:** update ONLY at the user's explicit instruction ("save that as a prompt lesson"). Claude may
*suggest* a candidate rule, never write one unprompted. New rule = one checklist line + one
origin-log entry. Append-only in the log; checklist lines may be sharpened in place.

---

## Checklist

### What to write down (instructions, memory, CLAUDE.md, briefs)
- Operative rules for **editing** standing docs live in `~/.claude/writing-standing-docs.md`
  (contract-vs-snapshot, non-derivable nuance, staleness triage, canonical-plus-pointers,
  replace-not-join, audience-referent). Their rationale and prompt-writing consequences stay
  canonical in the origin log below. When a brief asks an agent to document a system, fix stale
  docs, update a standing document or de-personalise a file, spell the relevant rule out in the
  brief — a cold executor won't infer it. → [contract-vs-snapshot], [canonical-plus-pointers],
  [replace-not-join], [audience-referent]

### Scoping briefs
- **Scope exclusions to claims, not territory.** When a brief fences off an area as "already
  covered by X", exclude X's specific claims/findings — not the whole file or section — and
  state that new or post-dating defects in that area are IN scope, flagged with a note on why
  they're not X. → [exclusions-scope-claims]

### Making rules stick
- **A rule an LLM must remember to apply is not a fix.** Operative statement now lives in
  `~/.claude/CLAUDE.md` § Working rules (it fires at any moment, not only while prompt-writing).
  For briefs: a prompt that says "fix it and add a note" produces the note; if the correction is
  computable, spec the deterministic enforcement instead. → [rule-into-code]

### Validating fixes before encoding them
- **Test against a second real, contrasting example first.** Operative statement now in
  `~/.claude/CLAUDE.md` § Working rules. For briefs: any brief that says "fix it and record the
  lesson" must mandate the second-example validation explicitly, or the agent ships the first
  plausible mitigation. → [second-real-example]

### Presenting results & decisions
- **Options and decisions come to the user one at a time, with tiered delivery.** Operative statement
  (tiers 1–3, the two-turn split phrasing, and the blocking-panel hard rule) now lives in
  `~/.claude/CLAUDE.md` § Working rules — it governs every interaction, not only prompt-writing.
  For briefs: any brief whose output is a set of findings or choices should specify the
  presentation protocol explicitly, or the agent defaults to a wall of parallel questions,
  decides silently, or asks for decisions on context the user never saw.
  → [one-decision-at-a-time]

---

## Origin log

Empty on this fork of the ruleset. Every entry the source project had logged here was a dated,
project-specific case narrative — a real incident, named store/file/task identifiers, sometimes a
commit hash — that wouldn't mean anything outside that project, so none of it carried over. The
checklist above lost nothing by this: each rule's operative statement is unchanged, only the case
history that originally justified it is gone. Losing that history does have a real cost worth
naming — the checklist's maturity markers (which rules are provisional vs. tested against a
second contrasting case) were tracked in the entries that just got cut, so treat everything above
as ungraded until this log has its own entries again.

New entries follow this shape:

    ### <the rule's opening words, verbatim, so it can be matched to its checklist line>
    - Date: <absolute date> · Origin: <project/task identifier>
    - The discussion: <what prompted the rule, in enough detail a cold reader could re-derive it>
    - Prompt-writing consequence: <what a future brief should say differently because of this>

