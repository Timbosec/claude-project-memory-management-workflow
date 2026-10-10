# Installing the workflow bundle

You follow these steps when the user asks you to install this bundle. `install.py` does the
copying, the `settings.json` changes and the tests. Your part is the decisions it leaves to the
user, which you take with them one at a time.

For every decision you raise, whether that's a file, a rule in `CLAUDE.md` or a component, give
the user the options available, the pros and cons of each for that specific case, and which one
you recommend and why. Then wait for their choice before acting on it.

Run every command from the clone root, the directory holding this file. The install always goes
into `~/.claude`. `--target DIR` exists only for testing in a scratch directory: the hook
commands it writes still run files under `~/.claude/hooks/`.

To upgrade an existing install, run `git pull` in the clone first, then follow these same steps.
The script works out from its install record what the bundle has changed since.

Install bundle files as they are. Don't generalise, adapt or add to them, and don't edit files
in this clone. The script updates a file the user never edited to the bundle's newer version on
its own, and lists it under "Updated". It deletes a file the bundle no longer ships if the user
never edited it, and lists it under "Removed". Any other file changes only where the user decides
it does, on a file the summary lists.

If you find a bug in the bundle during an install, don't fix it in this clone. Write it up for the
user (the file, what goes wrong, the evidence and a suggested fix) and tell them they can open an
issue on the repository they cloned from. Name it with
`git remote get-url origin | sed -E 's#://[^/@]*@#://#'`, which removes any user name or token
an HTTPS clone URL can carry; don't print the remote URL without that filter. Fixes arrive
through `git pull`.

## 1. Run the script

Run `python3 install.py` and show the user its summary. If it exits non-zero, show the user the
output (failing tests are printed under `Tests:`) and stop. The tests run against the files as
they are on disk, so if any files are listed under "Needs a decision", tell the user that a pass
covers their own copies of those, not the bundle's.

## 2. Resolve each listed file

The summary lists, under "Needs a decision", each existing file that differs from the bundle
version, by its path under the config directory, and lists any rules in the user-level
`CLAUDE.md` that need a decision in a section of their own. It has left them all as they are.
To find the
bundle version, look that path up as a `target` in `manifest.json`: its `source` is the bundle
file, relative to the clone root. The user-level `CLAUDE.md` is stored as
`payload/user-CLAUDE.md`, so that it doesn't load as instructions into this session.

Take the files one at a time. Finish one, including its `record` command, before raising the
next.

A listed file may end with `bundle change: <path>`. That diff holds only what the bundle changed
since the version the user last had, never the user's own edits. Work from it rather than from
the whole files: show the user each change and carry the ones they agree to into their file. A
file listed without one has no earlier bundle version to compare against, so compare the whole
files as below. `CLAUDE.md` never carries one; it has its own procedure below.

**`CLAUDE.md`** (kind `shared`). This file holds the user's own rules as well as the bundle's, so
the script never compares it as a whole. It compares the bundle's rules one at a time, by the ID
each one ends with (such as `→ [one-decision-at-a-time]`), against the bundle version the user
last had and the decisions recorded on earlier upgrades. Editing the file never lists it again;
only a bundle change to one of its rules can.

*When the summary lists "Rules in CLAUDE.md that need a decision"*, each line names a rule and
what happened to it, and the path printed under them is a file holding each rule's old and new
wording exactly as the bundle writes it. Take the rules one at a time:
- **new** or **changed**: find what the user's file says about the same situation, under any
  heading. For a changed rule, show the user what the bundle changed between the two wordings.
  Raise it with the options in item 4 of the full pass below. Then draft a one-line reason from
  the conflict you raised (or, with no conflict, from what the rule adds) and have the user
  confirm or correct it; they never have to write one. Record it:
  `python3 install.py record-rule ID --decision taken|merged|dropped --reason "TEXT"`. Taken
  means the bundle's wording went in as it is; merged means a wording agreed with the user,
  including keeping both with the bundle rule as an exception; dropped means it was left out.
  If the user declines without a reason, leave `--reason` off. A rule taken or merged into the
  file keeps its ID tag, which helps whoever runs a later upgrade find it in the file. The script
  never reads the user's `CLAUDE.md`, so a missing tag changes nothing it lists; don't present
  tagging as a reason to choose one option over another.
- **dropped earlier**: the user declined this rule on an earlier upgrade, for the reason shown,
  and the bundle has reworded it since. It stays dropped. Tell the user in one line that it
  changed. Raise it again only if the new wording plausibly answers their reason; if it does and
  they decide, record that as above. Recording nothing keeps it dropped.
- **removed from the bundle**: if the user's file still holds the rule, ask whether to keep it
  or delete it. There is nothing to record.

For `CLAUDE.md`, each rule's `record-rule` is what finishes that rule; record the file once, after
the last rule: `python3 install.py record CLAUDE.md --decision merged`. It refuses, naming the
rules, while a new or changed rule has no decision.

*When the summary lists `CLAUDE.md` under "Needs a decision" with "no earlier bundle version to
compare against: full pass"*, there are no earlier decisions to work from, so go through the
whole file:
1. Read the whole existing file, not just its headings. A rule can cover the same ground under a
   different heading or as an unheaded paragraph.
2. Go through the bundle version bullet by bullet. For each, check whether the existing file
   already says something about the same situation. Look hardest at confirmation before acting,
   verbosity, presenting options and decisions, when to ask and when to proceed, and tool and
   permission use. Those are where an existing file, often an employer's default, most often
   differs.
3. List every overlap or contradiction, quoting the existing text and the bundle text side by
   side. If the list is empty, tell the user so.
4. Raise the items one at a time. Get a decision on each before raising the next:
   - keep the existing text: leave the bundle rule out;
   - take the bundle's: drop the existing text and keep the bundle rule;
   - merge them into one rule, worded with the user;
   - keep both, with the bundle rule worded as an explicit exception.
5. For a bundle rule left out, search `payload/` for its ID without brackets
   (`one-decision-at-a-time`). Most IDs are cited nowhere else; where another installed file
   cites it, tell the user which, since that citation will now point at nothing. If the rule
   left out is the paragraph on routing a new lesson, or the rule that a lesson needs a second
   real case before it becomes a rule, tell the user that `/finalise` and `/memory-audit` carry
   their own copy and still route lessons that way.
6. Append the bundle content, adjusted by those decisions, as new top-level sections after a
   blank line, keeping each rule's ID tag. Delete or change existing content only where the user
   has said so for that specific content.
7. Record every bundle rule with `record-rule` as above: a rule appended as it is, with nothing
   in the user's file to weigh it against, is taken, with a reason such as "no existing rule on
   this". Then record `CLAUDE.md` as `merged`, whatever the individual decisions were; it refuses
   until every rule has a decision.

**Any other file** (kind `owned`): with a bundle change, work from the diff as above. Without
one, read both versions in full and show the user the specific differences, not just that the
file differs. Ask whether to keep theirs, take the bundle's or merge. For a merge, agree each
difference with the user, then write the result to the target.

Then record the decision:
- kept theirs: `python3 install.py record PATH --decision kept`
- took the bundle's: copy the `source` file over the target first, then
  `python3 install.py record PATH --decision replaced` (it refuses unless the file now equals
  the bundle version)
- merged: `python3 install.py record PATH --decision merged`

`PATH` is the path as the summary lists it. A recorded file isn't listed again until it is
edited or the bundle version changes. `CLAUDE.md` is the exception: editing it never lists it
again, and a bundle change lists only the rules it changed.

`python3 install.py rules` lists every recorded rule decision with its reason. To reverse one,
record the rule again with the new decision.

If the summary lists `settings.json` entries that differ from the bundle's, show the user both
and change an entry only if they say so.

**Files no longer in the bundle.** The summary lists, under "No longer in the bundle, you edited
it or it isn't in the record", each file the bundle used to install and now doesn't, with what
replaced it. Show the user the file and ask whether to remove it or keep it:
- remove: delete only that file once the user has said yes, then
  `python3 install.py record PATH --decision removed`;
- keep: `python3 install.py record PATH --decision kept`. It isn't listed again until it is
  edited.

## 3. Resolve each held-back skill or command

A skill or command installed in `~/.claude` overrides a project's own skill or command of the
same name, in every session in that project. So when a project already has its own copy, the
script doesn't install the bundle's. It lists the file under "Held back", with the projects that
have their own. It finds projects from the folders Claude Code keeps for each directory it has
been used in, so a project never opened in Claude Code isn't checked.

Take the held-back files one at a time. For each, tell the user which projects have their own
copy, and that installing the bundle's means those projects run the bundle's version instead of
their own from then on. Ask whether to install it anyway or leave it out:
- install it: `python3 install.py project-override PATH --decision install`, then run
  `python3 install.py` again and resolve anything it newly lists as in step 2;
- leave it out: `python3 install.py project-override PATH --decision hold`.

Either decision holds until another project turns up with its own copy, when the file is listed
again.

If the summary lists a file under "Installed at user level and overriding a project's own", it
was installed before that project had its own copy, and that project's copy isn't running. Tell
the user, and ask whether to keep the user-level one or remove it. Keep:
`python3 install.py project-override PATH --decision install`. Remove: delete only that one file
from `~/.claude` once the user has said yes, then
`python3 install.py project-override PATH --decision hold`.

## 4. Ask about the optional sub-agent guard

Ask only if the summary lists `subagent-guard` under "Optional components not installed". Tell
the user that it adds a `PreToolUse` hook, which runs on every file edit, and that it stops a
sub-agent editing project-record files: `CLAUDE.md`, `backlog.md`, `decisions.md`, skill files
outside a `scripts/` directory, and memory files. Edits made in the main session are never
blocked. It is only worth having if they delegate work to sub-agents.
- Yes: run `python3 install.py --with-subagent-guard`, then resolve any newly listed file as in
  step 2.
- No: run `python3 install.py decline subagent-guard`.

If instead the summary says the guard's files are present but not in the install record, ask the
user whether to keep tracking it. Yes: run `python3 install.py --with-subagent-guard`. No: run
`python3 install.py decline subagent-guard`, and tell them its files and any `settings.json`
entry stay in place until they remove them.

## 5. Verify

1. Check that the hooks' `python3` runs. Pipe a commit payload into the installed hook
   directly: `echo '{"tool_input":{"command":"git commit"}}' | ~/.claude/hooks/remind_finalise.py`
   (with `--target`, use that directory in place of `~/.claude`). It should print a line
   starting `REMINDER: run /finalise`. On macOS, `/usr/bin/python3` can be an Xcode
   command-line-tools stub that errors before running anything, which leaves the hooks installed
   but never firing. If that happens, find the real interpreter (often
   `/opt/homebrew/bin/python3`) and offer to prefix each bundle hook's `settings.json` command
   with its absolute path.
2. This session's hooks may not include the ones just installed, so the end-to-end checks happen
   in a new session. Ask the user to open a fresh Claude Code session in a new scratch git repo
   with no commits, and there:
   - run `/finalise`: each of its three checker scripts should print a one-line skip and exit 0.
     If `/finalise` was left out at user level in step 3, the scratch repo has no `/finalise`,
     so skip this check and tell the user it wasn't run;
   - ask Claude to make a trivial commit: the reminder to run `/finalise` should appear.

   Until the user reports both, don't tell them the install works. The README's "Verifying it
   worked" section has the remaining checks.

## 6. Git

Ask the user before committing anything in `~/.claude` to git.
