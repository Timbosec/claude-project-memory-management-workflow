# Claude Code project memory & session-close workflow

A set of six one-time bootstrap prompts (five core, one optional) that install a cross-project
working-rules and session-close system into any [Claude Code](https://claude.com/claude-code)
setup. Originally built up over months on one personal project, then generalised here so it can
be dropped onto a different machine and reused across every project on it, not just the one it
came from.

**Why this exists:** it applies a few concrete memory-management practices so that a coding
agent's session context stays tight instead of bloating with irrelevant history, while what
actually matters, decisions made, lessons learned, fixes worth remembering, survives past the
end of the session instead of evaporating when the context window clears. It also gives you a
place to notice patterns in how the agent works: which topics it keeps needing something
explained about twice, or where it burned several turns figuring out why something wasn't
working, so that friction gets fixed once instead of relived every session.

## Core benefits and capabilities

- **Nothing important gets lost to `/clear`.** Claude Code's context window resets, but a
  decision, a fix, or a lesson learned mid-session shouldn't; `/finalise` sweeps the conversation
  for anything that only exists in the chat and writes it down before the window closes.
- **A rule earns its place instead of accumulating from one anecdote.** A lesson observed once is
  a candidate, not policy: it waits in a ledger until a second, genuinely different case confirms
  it before becoming a standing rule, so a confident-sounding one-off doesn't quietly calcify
  into an instruction nobody re-examines.
- **The rule set checks itself.** `/memory-audit` periodically walks every rule file, both
  CLAUDE.mds, and accumulated memory against each other, flagging contradictions, duplicates, and
  staleness instead of relying on catching drift by eye.
- **A durable "why," independent of git archaeology.** `decisions.md` keeps the reasoning behind
  a choice queryable on its own; a future session doesn't have to reconstruct intent from commit
  messages and guesswork.
- **Install once, use on every project.** Everything lives at the user level (`~/.claude/...`),
  not per-repo, so there's no re-setup tax each time you start something new.
- **New projects get the same discipline in one command.** `/bootstrap-project` gives a brand-new
  repo the same worklist/decision-log conventions immediately, instead of that structure being
  re-derived from scratch, or skipped because it felt like overhead for something small.
- **Context cost stays visible, not just correctness.** The rule files distinguish what's loaded
  into every session from what's read on demand, and a built-in check reports growth over time,
  so the system doesn't silently get more expensive to run as it accumulates rules.
- **Friction gets diagnosed, not just tolerated.** The evidence ledgers exist specifically to
  capture moments the agent had to be corrected or asked to re-explain something, so a pattern of
  repeated confusion around one topic becomes visible and fixable instead of just annoying.

## What it sets up

Three permanent Claude Code commands/skills, plus the rule files they depend on:

- **`/finalise`**: a session-close ritual. Run it before clearing context and it sweeps the
  conversation for undocumented decisions, fixes, and lessons; routes each one to the right home
  (a memory file, a rule file, a project decision log, or a "wait for a second case" ledger);
  reconciles the project's open worklist; and runs a few deterministic integrity checks (memory
  index consistency, dangling cross-references, context-budget growth).
- **`/memory-audit`**: the periodic consistency pass `/finalise` explicitly does not do itself.
  Checks the rule files, both CLAUDE.mds, and accumulated memory against each other for
  contradictions, duplication, and staleness; ages the "waiting for a second case" ledger
  (promoting entries that now have one, retiring ones that don't hold up); extracts durable
  decisions out of memory into a project decision log.
- **`/bootstrap-project`**: sets up a new (or very basic existing) project to work with the two
  commands above: a `backlog.md`/`decisions.md` pair with the conventions that make them useful
  (stable task numbers, an append-only decision log, a dated "what's next" summary that gets
  replaced rather than appended to), plus a `CLAUDE.md` pointer so a fresh session actually knows
  these files exist.

Underneath those three, a small set of always-loaded and on-demand rule files: a routing header
that decides which file a new lesson belongs in, checklists for writing a prompt, editing a
standing doc, or briefing a sub-agent, and two evidence ledgers that hold single observations
until a second, contrasting one arrives to justify promoting them into an actual rule.

One more, optional piece, not part of `/finalise` or `/memory-audit`: a `PreToolUse` hook that
denies a delegated sub-agent from editing any of the project-record files this whole system
depends on (`CLAUDE.md`, `backlog.md`, `decisions.md`, a skill file outside its own `scripts/`
directory, or a memory file). A sub-agent should only ever touch the source/test files named in
its own brief; this makes that structural instead of just something you have to remember to say
in every brief.

## Setup

Everything below installs into `~/.claude/...` (global, not per-project) and only needs doing
once per machine. **After that**, starting a new project is just: open Claude Code inside the
repo and run `/bootstrap-project`. Nothing in this repository gets touched again.

**Quickest way:** open `00-run-all.md` and copy everything from its marked line down (the file
itself has a short human-only explanation above that line, don't paste that part). One paste,
but not one uninterrupted pass: the agent stops and reports after each of the five steps and
waits for you to say "continue" before starting the next, so a problem at one step gets caught
before the rest build on it. Every individual step's own "stop and ask" instructions still apply
on top of that.

**Step-by-step way**, if you'd rather review each install before moving to the next, or you're
resuming after stopping partway through: paste each file below as its own message, in order:

| Order | File | Installs |
|---|---|---|
| 1 | `01-global-rules-bootstrap.md` | `~/.claude/CLAUDE.md` (routing header + working rules), `prompt-lessons.md`, `writing-standing-docs.md`, `writing-executor-briefs.md`, `doc-test-probes.md` |
| 2 | `02-empty-ledgers-bootstrap.md` | `lesson-candidates.md`, `under-explained-cases.md` |
| 3 | `03-finalise-skill-bootstrap.md` | the `/finalise` skill, its three checker scripts, and the git-commit reminder hook |
| 4 | `04-new-project-backlog-bootstrap.md` | the `/bootstrap-project` command |
| 5 | `05-memory-audit-bootstrap.md` | the `/memory-audit` command |
| 6 *(optional)* | `06-subagent-record-guard-bootstrap.md` | a `PreToolUse` hook that blocks a delegated sub-agent from editing project-record files |

Order mostly doesn't matter, except that 3 should run before 4 (the `/bootstrap-project`
command's own `CLAUDE.md` template references `/finalise` by name). Prompt 6 is independent of
the others and only worth running if you delegate work to sub-agents via the `Agent` tool; it's
not included in `00-run-all.md`, since unlike 1-5 it isn't something everyone using this bundle
wants.

Either way, they're idempotent-ish but not blind: each step reads before it writes and stops to
show you anything it would overwrite or that conflicts with content already there.

## What's deliberately not included

- No actual historical content: no logged lessons, no ledger entries, no decisions, no backlog
  tasks. Every accumulating file starts genuinely empty, only the schema/mechanics ported. A
  lesson ledger entry needs a *second, contrasting* case to ever get promoted, and a case from an
  unrelated origin project can never be that.
- No git push authorization. Whether these files get committed/pushed anywhere is left for you to
  decide per machine; nothing here assumes a trust level that hasn't been explicitly granted.
- Two things are referenced in passing but not installed by this bundle: a skill that measures
  where trimming a rule file actually reclaims always-loaded context budget, and a hook that
  nudges periodic re-evaluation of the under-explained-cases ledger. Both references have a
  documented fallback, so their absence doesn't break anything, they're just not automated here.

## What was fixed while removing origin-specific content

Scrubbing every mention of the original project and its user turned up two real bugs, not just
naming, that would otherwise have broken quietly on a different machine:

- `context_budget_report.py` imported a CSV-writing helper from a shared script library that
  wasn't part of this bundle. It's now a small inlined function with no external dependency.
- The hook test suite hardcoded an absolute path to the hook file on the original machine. It now
  resolves the hook's path relative to the test file itself, so it works wherever the two files
  are installed together.
- `check_memory_index.py`'s known-retired-link exemption shipped with one real name from the
  original project's history baked in as production configuration, not test data. It's now
  configurable via `$KNOWN_RETIRED_LINKS` and empty by default, since a fresh project hasn't
  retired anything yet; the tests that verify the exact-match logic now inject their own
  test-specific name instead of depending on that value being present.
- The optional sub-agent guard hook (prompt 6) derived its notion of "the project" from one
  hardcoded absolute path. It now reads the calling session's actual working directory from the
  hook's own payload, so it works correctly across every project on the machine, not just one.

An independent audit (a separate, unprimed pass over the published repo, checking file contents
*and* full commit history) later caught a category the first pass missed entirely: real git
commit hashes from the original project's history, cited in `check_thread_state.py`'s docstring
and test fixtures as "verified against this repo's real history." A full SHA is effectively a
fingerprint of a specific repository's history, unrelated to whether the surrounding prose reads
as generic. Those citations, one real memory filename cited as evidence of a working case, one
literal system username in an example path, and a few residual real filenames used as test
fixtures, are now replaced with synthetic values throughout.

Everything else was text: project name, personal name, and domain-specific example content
(store names, filenames) replaced with generic placeholders, and dated case narratives stripped
from the rule files down to their operative statements.

## Verifying it worked

In a scratch/throwaway repo:

1. Run `/bootstrap-project`. It should produce a clean, empty `backlog.md`, `decisions.md`, and
   `CLAUDE.md` pointer, nothing referencing the origin project.
2. Run `/finalise`. It should complete without crashing even against the nearly-empty backlog it
   just created, and report zero candidates on a session that did no real work.
3. Run `/memory-audit`. It should discover the project's memory directory, audit the (mostly
   empty) rule homes without erroring, and stop to show a proposed change plan before touching
   anything.
