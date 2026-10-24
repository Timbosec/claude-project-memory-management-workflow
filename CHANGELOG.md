# Changelog

## 2026-10-24

**Changed**
- When the agent adds or rewords a rule in an instruction file, a skill or a memory note, it now
  checks the rule against each line of the checklist in `writing-standing-docs.md` and shows the
  user the result line by line. The checklist is there to keep rules short, needed, in the right
  place and calmly worded, so each one still gets followed. Fixing a fact or a path needs no check.
  The rule file `rules/standing-docs.md` now also loads for a skill's other markdown files and the
  `writing-*.md` files in `~/.claude`, after the agent first reads, edits or creates one. Why: reading a checklist does not apply it. In a test,
  fresh sessions showed the line-by-line result in five of six runs with the new wording and in
  none of six with the old. On upgrade, the pointer in the user's `CLAUDE.md` is listed as a
  changed rule, and the user decides whether to take it.

## 2026-10-24

**Added**
- A `cold-test` agent, installed into the agents folder. This bundle's workflow requires that a
  new or changed rule be tested, to find out whether it actually does what it was written to do.
  Each test hands an agent the rule and a task and watches what it does. A rule gets several
  tests: some cases where it should apply and some where it should leave things alone, and each
  case is run several times, because a single run can pass or fail by chance. This agent
  performs those tests. Why: an ordinary agent has already read the user's `CLAUDE.md` files, so
  it can do the right thing because some other rule there says to, and a rule that doesn't work
  still appears to pass. This agent starts without those files, so a pass shows the rule did the
  work.

**Changed**
- The rule in `writing-standing-docs.md` for testing a new or changed rule now says to use the
  `cold-test` agent. Where that agent isn't installed, the result should say that the agent had
  already read the user's own rules, so a pass may not prove the rule works.
  `writing-executor-briefs.md`, which guides how a brief for sub-agents is written, now
  specifies that tests of a rule should be run by the `cold-test` agent. Why: a test of a rule
  can only be trusted if the agent running it has nothing but that rule to go on. On upgrade, a
  copy of either file the user has edited is shown to the user, who decides what to keep.
- When the user updates the bundle, `install.py` lists the files they edited that differ from the
  bundle's version, and the agent asks what to do with each. It now adds a note to a file that
  already includes the new version's changes, so the user knows only their own additions are
  left. Why: a change can reach a user's files without going through `install.py`, for example
  when an agent applies it directly, and the file was then listed like any other edit, leaving the
  user to compare it with the bundle's. The note only informs. A file with no note may still
  include the changes, because `install.py` adds no note when it is unsure. `INSTALL.md` now
  tells the agent that, with the note, only the user's own additions need asking about.

## 2026-10-22

**Added**
- `/finalise` now recovers what a compaction took out of the conversation. Claude Code shortens a
  long session by replacing its older part with a summary, so `/finalise` used to sweep only the
  summary and miss decisions and feedback from the part it replaced. A new script lists the user's
  messages since the previous `/finalise` from the transcript saved on disk and marks which ones a
  compaction removed from the agent's view. The agent then reads the transcript around those that
  look like decisions, feedback or lessons and raises only what isn't already recorded.

**Changed**
- When an upgrade asks what to do about a file the user has edited, the agent now shows the user's
  own wording next to the bundle's and explains in plain words what each choice would do to it.
  Why: the agent shouldn't expect the user will remember the wording of a specific rule.

**Fixed**
- An upgrade no longer assumes temporary folders are projects. Why: the installer checks the
  folders Claude Code has been used in for projects that have their own copy of a skill such as
  `/finalise`, and asks before the bundle's version would override one. Temporary folders left
  behind by earlier test runs counted as projects with their own copies, so it asked about
  projects that weren't real.

## 2026-10-19

**Added**
- `/memory-audit` now lists the bundle rules you have edited in place and offers to move each
  addition into a rule of its own. Why: a bundle rule you edited differs from the bundle's wording
  at every upgrade, while a separate rule of yours never does. `INSTALL.md` now recommends
  running `/memory-audit` after an upgrade.

**Changed**
- The reminder to run `/finalise` after a commit now shows the user a notice and tells the agent.
  Why: a hook's plain output goes only to Claude Code's debug log, so it would reach neither the
  user nor the agent. See the [hooks reference](https://code.claude.com/docs/en/hooks).
- `prompt-lessons.md` is now retired. Its rules for writing a brief or prompt are part of
  `writing-executor-briefs.md`, which now also covers prompts the user asks for help with. On
  upgrade, an unedited copy is deleted; an edited one is kept and the user decides.
- `/next` now gives each task's backlog number whenever it mentions one, so the user can refer to
  it.

## 2026-10-11 to 2026-10-18

**Changed**
- Every shipped rule was reviewed against a checklist built from Anthropic's guidance on
  [instruction files and memory](https://code.claude.com/docs/en/memory),
  [Claude Code best practices](https://code.claude.com/docs/en/best-practices) and
  [prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).
  Rules now open by saying when they apply, carry no dates or case notes, and use plain wording
  instead of capitals for emphasis; several that rested on a single incident were cut, and others
  were split so each does one job. Why: every always-loaded line costs context in every session,
  and forceful wording makes a rule fire where it doesn't belong. An upgrade now lists the rules
  that changed and the reason for each.

**Added**
- `writing-standing-docs.md` now holds a checklist that a new or reworded rule must pass.
  `/finalise` applies it before it proposes a rule, and `/memory-audit` applies it when it reviews
  existing ones.
- The `proving-tests-can-fail` skill. It holds the rules for checking that a test can fail (write
  it before the fix, revert the fix and watch it fail, break the code on purpose) and now loads
  when the agent adds or changes tests. Why: those rules sat in a file read only when briefing a
  sub-agent, so a session writing tests never saw them.
- `rule-changes.json` records why each shipped rule and file changed. The installer now prints the
  reason beside each change, and a test keeps the record complete.
- Three new rules: when the agent reports that something isn't there, it says what it searched
  and how; it measures how far a cause reaches before scoping a fix to the reported case; and it
  puts anything the user must read in the text that ends the turn.

## 2026-10-01 to 2026-10-03

**Changed**
- The bundle is now installed from a clone with `install.py`, not from paste-in prompts. Files are
  real files in `payload/`, and an install record remembers the user's decisions. Re-running it
  updates files the user never edited, shows only the bundle's own change to the ones they did, and
  removes files the bundle has dropped. Why: the old whole-file keep-or-replace silently dropped new
  features, and every install retyped the files through the model.
- A skill or command that a project already has its own copy of is now held back, and the user is
  asked before the user-level copy overrides it.
- The installer now runs the shipped tests after every install and stops if one fails.

## 2026-09-29

**Added**
- First public version: `/finalise`, `/bootstrap-project`, `/memory-audit`, `/next`, the
  commit-reminder hook and the rule files they rely on.
