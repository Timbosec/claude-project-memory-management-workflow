# Prompt Lessons — best-practice rules for writing prompts & briefs

**Purpose:** a quick-reference checklist for **authoring** a prompt or brief, consulted when the
user asks for help writing or reviewing one. Rules are distilled from real discussions where a
sharper approach emerged than the original prompt asked for.

**Scope:** this file is about text the user commissions. Rules for *editing* standing docs, skills
and memory bodies live in `~/.claude/writing-standing-docs.md`; rules governing the agent's own
conduct at any moment live in `~/.claude/CLAUDE.md` § Working rules. The **origin log below is
where each rule's cases and rationale are logged**, including rules stated in full in another file
— those files carry the operative clause and point back here.

**Write rules:** update ONLY at the user's explicit instruction ("save that as a prompt lesson"). Claude may
*suggest* a candidate rule, never write one unprompted. New rule = one checklist line + one
origin-log entry. Append-only in the log; checklist lines may be sharpened in place.

---

## Checklist

### What to write down (instructions, memory, CLAUDE.md, briefs)
- Operative rules for **editing** standing docs live in `~/.claude/writing-standing-docs.md`
  (contract-vs-snapshot, non-derivable nuance, staleness triage, canonical-plus-pointers,
  replace-not-join, audience-referent). When a brief asks an agent to document a system, fix stale
  docs, update a standing document or de-personalise a file, spell the relevant rule out in the
  brief — a cold executor won't infer it. → [contract-vs-snapshot], [canonical-plus-pointers],
  [replace-not-join], [audience-referent]

### Scoping briefs
- **Scope exclusions to claims, not territory.** When a brief fences off an area as "already
  covered by X", exclude X's specific claims/findings — not the whole file or section — and
  state that new or post-dating defects in that area are IN scope, flagged with a note on why
  they're not X. → [exclusions-scope-claims]

### Making rules stick
- **A rule an LLM must remember to apply is not a fix.** The rule itself is in
  `~/.claude/CLAUDE.md` § Working rules, since it applies at any moment, not only while writing
  prompts. For briefs: a prompt that says "fix it and add a note" produces the note; if the
  correction is computable, spec the deterministic enforcement instead. → [rule-into-code]

### Validating fixes before encoding them
- **Test against a second real, contrasting example first.** The rule itself is in
  `~/.claude/CLAUDE.md` § Working rules. For briefs: any brief that says "fix it and record the
  lesson" must mandate the second-example validation explicitly, or the agent ships the first
  plausible mitigation. → [second-real-example]

### Presenting results & decisions
- **Options and decisions come to the user one at a time, with tiered delivery.** The rule itself
  (tiers 1–3, the two-turn split phrasing, and the blocking-panel hard rule) is in
  `~/.claude/CLAUDE.md` § Working rules, since it governs every interaction, not only prompts.
  For briefs: any brief whose output is a set of findings or choices should specify the
  presentation protocol explicitly, or the agent defaults to a wall of parallel questions,
  decides silently, or asks for decisions on context the user never saw.
  → [one-decision-at-a-time]

---

## Origin log

No entries yet. The checklist rules above have no logged cases, so none is marked as tested
against a second, contrasting case: treat them as ungraded until entries exist here.

New entries follow this shape:

    ### <the rule's opening words, verbatim, so it can be matched to its checklist line>
    - Date: <absolute date> · Origin: <project/task identifier>
    - The discussion: <what prompted the rule, in enough detail a cold reader could re-derive it>
    - Prompt-writing consequence: <what a future brief should say differently because of this>

