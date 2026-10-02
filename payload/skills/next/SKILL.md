---
name: next
description: Surfaces the recommended next backlog item (from backlog.md's "Next up" section) and drafts a checkpoint brief for it. Use when the user asks what's next, wants to pick up backlog work, or asks to plan the next task — does not re-rank the backlog from scratch.
---

# /next — pick up the next backlog item

## What to do

1. Read `backlog.md`'s **"Next up" section** (top of file, before `## Open`) — this IS the triage:
   `/finalise` revises it at the end of each session, and it already says which threads are ready
   to build vs. still need a scoping/ruling pass. Don't re-rank the Open list from scratch — the
   file has no impact/effort scheme to rank against, and a fresh ranking would just compete with
   the one already on the page. Read `decisions.md` only if the Next-up text points at a decision
   you need the rationale for.
2. Summarise what the Next-up section says in <=3 bullets: the recommended item(s), why now (per
   its own text), and any open decision it's waiting on. If the section names no single ready
   item — it sometimes says exactly that — report that plainly rather than manufacturing a pick.
3. Present the recommendation and stop. Do not edit any file or start work until the user picks
   an item — the section may name more than one candidate, or the user may want something else
   off the Open list entirely.
4. Once an item is chosen:
   - **Code-writing work**: read `~/.claude/writing-executor-briefs.md` in full before drafting
     anything — its checkpoint-sizing, caller-audit and proof-of-red rules can change
     independently of this skill, so read it fresh rather than trusting a summary here. If the
     project's `CLAUDE.md` has rules for how hard to verify a change or how execution is
     delegated, follow them. Planning stays in this session.
   - **Standing-doc work** (backlog.md / decisions.md / CLAUDE.md / a memory body): follow
     `~/.claude/writing-standing-docs.md` instead — a sub-agent brief doesn't cover these edits;
     the coordinating session makes them directly.
5. Report what you drafted (the brief, or the doc-edit plan) and wait for approval before
   touching any file.
