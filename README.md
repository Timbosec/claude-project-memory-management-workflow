# Claude Code project memory & session-close workflow

A set of skills, a command, hooks and rule files for [Claude Code](https://claude.com/claude-code),
with an install script. It keeps each session's context tight while making sure what matters,
the decisions made, lessons learned and work still open, is written down before `/clear` throws
the conversation away. Install it once per machine and it works in every project on it.

Nothing historical ships with it: every ledger, log and backlog starts empty.

## How you work once it's installed

1. **When starting a project (or adding this workflow to an existing one).** Open Claude Code in
   the project folder and run `/bootstrap-project`. It creates `backlog.md` (the open worklist),
   `decisions.md` (why things were done) and a project `lesson-candidates.md`, and adds a pointer
   to them in the project's `CLAUDE.md`. If the project's memory already holds open work, it
   offers to move each item into the backlog.
2. **Pick up work.** Run `/next`. It reads the "Next up" recommendation at the top of
   `backlog.md` and stops for you to choose. Once you've picked an item, it drafts a plan or a
   brief for a sub-agent, and waits for your approval before touching any file.
3. **Work as normal.** The rule files in `~/.claude` load into every session and shape how Claude
   plans, briefs sub-agents, edits docs and reports back. If you've installed the optional guard,
   a sub-agent can't edit the project's record files (`CLAUDE.md`, `backlog.md`, `decisions.md`,
   memory). After each `git commit`, a hook reminds Claude to run `/finalise` before the session
   ends.
4. **Close the session.** Run `/finalise` before `/clear`. It sweeps the conversation for
   decisions, fixes and lessons that exist only in the chat and proposes a home for each, one
   approval at a time. It then moves any loose work into `backlog.md`, runs integrity checks, and
   rewrites "Next up" so the next session's `/next` starts from it.
5. **Audit occasionally.** Run `/memory-audit` from time to time. It checks the rule files, both
   `CLAUDE.md`s and memory against each other for contradictions, duplication and staleness. It
   shows you the whole plan before changing anything.

## How a lesson becomes a rule

`~/.claude/CLAUDE.md` and the rule files beside it load into every session on the machine.
Everything else, the backlog, decision log, project `CLAUDE.md`, memory and project ledger, stays
in its own project. A lesson seen once goes into a ledger (the project's, or the global
`~/.claude/lesson-candidates.md`), not into a rule. It becomes a standing rule only when a second,
different case confirms it. `/memory-audit` reads every project's ledger as one pool, so two
cases from unrelated projects can together make a global rule neither project would have
proposed alone.

## Install

You need `python3` (3.9 or later) and `git`.

1. Clone this repository, and keep the clone: you re-run the install from it.
2. Open Claude Code inside the clone and ask it to install the bundle.
3. Claude follows `INSTALL.md` and runs `install.py`. The script copies in every file you
   don't have yet, adds its hooks to `~/.claude/settings.json`, and runs the bundle's tests.
   Where you already have a file that differs from the bundle's, it leaves the file alone, and
   Claude goes through those files with you one at a time. Where one of your projects already
   has its own copy of a bundle skill or command, which a user-level one would override, the
   script holds the bundle's back and Claude asks you whether to install it anyway. Claude also
   asks whether you want the optional sub-agent guard.

Re-running the install is safe. It never overwrites a file you have changed, and it doesn't ask
again about a file you've already decided on unless you edit it or the bundle's version changes.

## Upgrade

Run `git pull` in the clone, then ask Claude to install the bundle again. Files you never edited
are updated, and files the bundle no longer ships are removed. For a file you did edit, Claude
shows you only what the bundle changed and asks which changes to take.

## Found a bug?

Open an issue on this repository rather than fixing it in your clone. Fixes arrive through
`git pull`.

## Verifying it worked

`INSTALL.md` ends by checking the hooks and `/finalise` in a fresh session. Then, in a scratch
repo:

1. Run `/bootstrap-project`. It should create empty `backlog.md`, `decisions.md` and
   `lesson-candidates.md` files, and a `CLAUDE.md` pointer to them.
2. Make a first commit and run `/finalise`. On a session that did no real work it should
   complete and report no candidates.
3. Run `/memory-audit`. It should find the project's memory directory, audit the mostly empty
   rule files without errors, and stop at its proposed plan before changing anything.
