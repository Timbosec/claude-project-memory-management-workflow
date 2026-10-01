# Installing the workflow bundle

You follow these steps when the user asks you to install this bundle. `install.py` does the
copying, the `settings.json` changes and the tests. Your part is the decisions it leaves to the
user, which you take with them one at a time.

Run every command from the clone root, the directory holding this file. The install always goes
into `~/.claude`. `--target DIR` exists only for testing in a scratch directory: the hook
commands it writes still run files under `~/.claude/hooks/`.

Install bundle files as they are. Don't generalise, adapt or add to them, and don't edit files
in this clone. A bundle file changes only where the user decides it does, on a file the summary
lists.

## 1. Run the script

Run `python3 install.py` and show the user its summary. If it exits non-zero, show the user the
output (failing tests are printed under `Tests:`) and stop. The tests run against the files as
they are on disk, so if any files are listed under "Needs a decision", tell the user that a pass
covers their own copies of those, not the bundle's.

## 2. Resolve each listed file

The summary lists, under "Needs a decision", each existing file that differs from the bundle
version, by its path under the config directory. It has left them all as they are. To find the
bundle version, look that path up as a `target` in `manifest.json`: its `source` is the bundle
file, relative to the clone root. The user-level `CLAUDE.md` is stored as
`payload/user-CLAUDE.md`, so that it doesn't load as instructions into this session.

Take the files one at a time. Finish one, including its `record` command, before raising the
next.

**`CLAUDE.md`** (kind `shared`):
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
5. A bundle rule left out may end with a tag such as `→ [one-decision-at-a-time]`. Search
   `payload/` for the tag's name without brackets (`one-decision-at-a-time`) and tell the user
   which installed files cite it, since those citations will now point at nothing.
6. Append the bundle content, adjusted by those decisions, as new top-level sections after a
   blank line. Delete or change existing content only where the user has said so for that
   specific content. Record `CLAUDE.md` as `merged`, whatever the individual decisions were.

**Any other file** (kind `owned`): read both versions in full and show the user the specific
differences, not just that the file differs. Ask whether to keep theirs, take the bundle's or
merge. For a merge, agree each difference with the user, then write the result to the target.

Then record the decision:
- kept theirs: `python3 install.py record PATH --decision kept`
- took the bundle's: copy the `source` file over the target first, then
  `python3 install.py record PATH --decision replaced` (it refuses unless the file now equals
  the bundle version)
- merged: `python3 install.py record PATH --decision merged`

`PATH` is the path as the summary lists it. A recorded file isn't listed again until it is
edited or the bundle version changes.

If the summary lists `settings.json` entries that differ from the bundle's, show the user both
and change an entry only if they say so.

## 3. Ask about the optional sub-agent guard

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

## 4. Verify

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
   - run `/finalise`: each of its three checker scripts should print a one-line skip and exit 0;
   - ask Claude to make a trivial commit: the reminder to run `/finalise` should appear.

   Until the user reports both, don't tell them the install works. The README's "Verifying it
   worked" section has the remaining checks.

## 5. Git

Ask the user before committing anything in `~/.claude` to git.
