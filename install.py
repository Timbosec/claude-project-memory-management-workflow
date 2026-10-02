#!/usr/bin/env python3
"""Install the workflow bundle into a Claude Code config directory (default ~/.claude).

Usage:
  python3 install.py [--target DIR] [--dry-run] [--with-subagent-guard]
  python3 install.py [--target DIR] decline subagent-guard
  python3 install.py [--target DIR] record PATH --decision kept|merged|replaced|removed
  python3 install.py [--target DIR] project-override PATH --decision install|hold

Reads manifest.json and payload/ from this script's own directory.

Install (no subcommand): for each file in the selected components it copies the file if
missing, skips it if identical, and updates it to the bundle version if the install record
proves the user never edited it (the file still is the bundle version last installed or
decided on). Otherwise it leaves the existing file alone: a seed ledger is kept silently, a file
whose recorded decision still holds is skipped, and any other file is listed as needing a
decision. When the bundle has changed since the version recorded for a listed file, that change
alone (recorded version to current bundle version) is written as a diff under
workflow-bundle/changes/ and its path printed with the file. A file the bundle no longer
ships (the manifest's "retired" list) is deleted if the install record proves the user never
edited it, dropped from the record silently if it is already gone, and otherwise listed and
left. A skill or command that a project already has its own copy of
is held back, because the user-level one would override it, unless a recorded decision says to
install it; one already installed is reported as overriding the project's copy. It adds the bundle's hook entries to settings.json, runs the
installed tests and prints a short summary. An optional component is selected when its
--with-... flag is given or when the install record shows it installed earlier.

decline: records that the user doesn't want an optional component, so the summary stops
offering it.

record: the agent calls this after resolving a listed file with the user. It records the
decision (kept, merged or replaced) so that later runs skip the file until it is edited again
or the bundle changes. For a file the bundle no longer ships it takes only kept, which leaves
the file alone until it is edited again, or removed, once the file has been deleted, which
stops tracking it.

project-override: the agent calls this after asking the user about a held-back skill or
command. install puts it in at user level on the next run; hold keeps it out. Either holds until
another project turns up with its own copy.

It never overwrites a file the user has edited, and never changes a settings.json hook entry
that already exists.

Exit codes: 0 when all is well (files needing a decision count as fine), 1 when an installed
test fails, 2 when the manifest, the payload, the install record or settings.json can't be
read, or a subcommand's arguments are wrong.
"""
import argparse
import copy
import datetime
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = "core"
RECORD_DIR = "workflow-bundle"
RECORD_FILE = "install-record.json"
RECORD_FORMAT = 3
BASE_SUFFIX = ".base"
# Each real run's bundle changes for files the user edited; emptied at the start of the run.
CHANGES_DIR = "changes"
CHANGE_SUFFIX = ".diff"
SETTINGS_FILE = "settings.json"
DECISIONS = ("kept", "merged", "replaced")
# The only decisions on a file the bundle no longer ships.
RETIRED_DECISIONS = ("kept", "removed")
OVERRIDE_DECISIONS = ("install", "hold")
PROJECTS_DIR = "projects"
SKILL_FILE = re.compile(r"^skills/([^/]+)/SKILL\.md$")
COMMAND_FILE = re.compile(r"^commands/([^/]+)\.md$")
NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")
SESSION_LINES_READ = 50


class SetupError(Exception):
    """The manifest, the payload, the install record or settings.json can't be used."""


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest():
    path = os.path.join(HERE, "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        files = manifest["files"]
        tests = manifest.get("tests", [])
        for entry in files:
            for key in ("source", "target", "kind", "component", "executable"):
                entry[key]
            if entry["kind"] not in ("owned", "seed", "shared"):
                raise ValueError("unknown kind %r for %s" % (entry["kind"], entry["target"]))
            if not os.path.isfile(os.path.join(HERE, entry["source"])):
                raise ValueError("payload file missing: %s" % entry["source"])
        live = {entry["target"] for entry in files}
        for entry in manifest.setdefault("retired", []):
            if not isinstance(entry.get("target"), str) or not entry["target"]:
                raise ValueError("retired entry has no target")
            if entry["target"] in live:
                raise ValueError("%s is listed both as installed and as retired"
                                 % entry["target"])
        for entry in tests:
            entry["component"], entry["file"]
        for entry in manifest.get("settings", []):
            entry["component"], entry["event"]
            if not bundle_commands(entry["entry"]):
                raise ValueError("settings entry for %s has no command" % entry["event"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise SetupError("can't read %s: %s" % (path, e))
    return manifest


def optional_components(manifest):
    names = {e["component"] for e in manifest["files"]}
    names |= {e["component"] for e in manifest.get("settings", [])}
    return sorted(names - {CORE})


def load_record(target):
    path = os.path.join(target, RECORD_DIR, RECORD_FILE)
    if not os.path.exists(path):
        return {"format": RECORD_FORMAT, "files": {}, "components": {}, "settings_added": [],
                "project_overrides": {}, "retired_kept": {}}
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if not isinstance(record.get("files"), dict):
            raise ValueError("no 'files' object")
        if record.get("format", 1) > RECORD_FORMAT:
            raise ValueError("written by a newer install.py (format %s)" % record["format"])
        record.setdefault("components", {})
        record.setdefault("settings_added", [])
        record.setdefault("project_overrides", {})
        record.setdefault("retired_kept", {})
        if not isinstance(record["components"], dict):
            raise ValueError("'components' is not an object")
        if not isinstance(record["project_overrides"], dict):
            raise ValueError("'project_overrides' is not an object")
        if not isinstance(record["retired_kept"], dict):
            raise ValueError("'retired_kept' is not an object")
        if not isinstance(record["settings_added"], list):
            raise ValueError("'settings_added' is not a list")
        record["format"] = RECORD_FORMAT
    except (OSError, ValueError, AttributeError, TypeError) as e:
        raise SetupError("can't read install record %s: %s" % (path, e))
    return record


def save_record(target, record):
    path = os.path.join(target, RECORD_DIR, RECORD_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def bundle_commit():
    try:
        out = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def copy_file(src, dst, executable):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    if executable:
        mode = os.stat(dst).st_mode
        os.chmod(dst, mode | 0o111)


def lacks_exec_bit(entry, dst):
    """The manifest says executable but the installed file can't be run directly."""
    return entry["executable"] and not os.stat(dst).st_mode & 0o100


def base_path(target, rel):
    # The suffix keeps a base copy from being taken for a live file: Claude Code auto-loads
    # CLAUDE.md, and tools that scan ~/.claude for Markdown would find the rule copies.
    return os.path.join(target, RECORD_DIR, "base", rel + BASE_SUFFIX)


def note_in_record(record, target, entry, src, dst, decision, commit, today):
    """Record a decision for one file and keep a base copy of the bundle version."""
    base = base_path(target, entry["target"])
    record["files"][entry["target"]] = {
        "kind": entry["kind"],
        "bundle_sha256": sha256_of(src),
        "current_sha256": sha256_of(dst),
        "decision": decision,
        "bundle_commit": commit,
        "date": today,
        "base": os.path.relpath(base, target).replace(os.sep, "/"),
    }
    os.makedirs(os.path.dirname(base), exist_ok=True)
    shutil.copyfile(src, base)


def previously_decided(record, entry, bundle_sha, current_sha):
    """Call 4: a decision was recorded, the bundle hasn't changed, the file still matches."""
    seen = record["files"].get(entry["target"])
    return (isinstance(seen, dict)
            and seen.get("bundle_sha256") == bundle_sha
            and seen.get("current_sha256") == current_sha)


def changes_dir(target):
    return os.path.join(target, RECORD_DIR, CHANGES_DIR)


def bundle_change(record, target, entry, bundle_sha):
    """The bundle's own change since the version the user last had, as unified-diff text.

    None when there is nothing to compare against (no record entry, or its base copy is
    missing or no longer the recorded bundle version) or when the bundle hasn't changed since.
    The diff runs from the base copy to the bundle version and never reads the user's file, so
    it holds none of the user's edits.
    """
    seen = record["files"].get(entry["target"])
    if not isinstance(seen, dict) or seen.get("bundle_sha256") == bundle_sha:
        return None
    base = base_path(target, entry["target"])
    if not os.path.isfile(base) or sha256_of(base) != seen.get("bundle_sha256"):
        return None
    with open(base, encoding="utf-8", errors="replace", newline="") as f:
        old = f.read().splitlines(keepends=True)
    with open(os.path.join(HERE, entry["source"]), encoding="utf-8", errors="replace",
              newline="") as f:
        new = f.read().splitlines(keepends=True)
    rel = entry["target"]
    lines = []
    for line in difflib.unified_diff(old, new, "a/" + rel + " (bundle version you last had)",
                                     "b/" + rel + " (bundle version now)"):
        if not line.endswith("\n"):
            line += "\n\\ No newline at end of file\n"
        lines.append(line)
    return "".join(lines)


def write_change(target, rel, text):
    path = os.path.join(changes_dir(target), rel + CHANGE_SUFFIX)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def drop_tracking(record, target, rel):
    """Forget a file: its record entry, its base copy and any kept-while-retired hash."""
    record["files"].pop(rel, None)
    record["retired_kept"].pop(rel, None)
    base = base_path(target, rel)
    if os.path.isfile(base):
        os.remove(base)


def untouched(record, entry, current_sha):
    """The user had the bundle version exactly when it was last recorded, and still has it.

    Decided by hashes only, never by the recorded decision's label.
    """
    seen = record["files"].get(entry["target"])
    return (isinstance(seen, dict)
            and seen.get("current_sha256") == current_sha
            and seen.get("bundle_sha256") == seen.get("current_sha256"))


# --- projects with their own command -------------------------------------------------------
#
# A user-level skill or command overrides a project's own of the same name, so installing one
# silently replaces it in that project. The projects are found from <target>/projects/, which
# has a folder for each directory Claude Code has been used in.

def slash_name(rel):
    """The /name a skill or command file defines, or None for any other file."""
    m = SKILL_FILE.match(rel) or COMMAND_FILE.match(rel)
    return m.group(1) if m else None


def decode_project_folder(name):
    """Every existing directory Claude Code would name its project folder `name` after.

    Claude Code replaces each character other than a letter or digit with '-', so a name can
    fit more than one path; each one that exists is returned.
    """
    found = []

    def walk(path, rest):
        if not rest:
            found.append(path)
            return
        try:
            entries = os.listdir(path)
        except OSError:
            return
        for entry in entries:
            encoded = "-" + NOT_ALNUM.sub("-", entry)
            if rest == encoded or rest.startswith(encoded + "-"):
                full = os.path.join(path, entry)
                if os.path.isdir(full):
                    walk(full, rest[len(encoded):])

    walk(os.sep, name)
    return found


def session_dirs(folder):
    """The working directories recorded near the top of the folder's session logs."""
    dirs = set()
    try:
        logs = [n for n in os.listdir(folder) if n.endswith(".jsonl")]
    except OSError:
        return dirs
    for log in logs:
        try:
            with open(os.path.join(folder, log), encoding="utf-8", errors="replace") as f:
                for _ in range(SESSION_LINES_READ):
                    line = f.readline()
                    if not line:
                        break
                    try:
                        cwd = json.loads(line).get("cwd")
                    except (ValueError, AttributeError):
                        continue
                    if isinstance(cwd, str) and cwd:
                        dirs.add(cwd)
                        break
        except OSError:
            continue
    return dirs


def project_dirs(target):
    """Directories Claude Code has been used in, as far as <target>/projects/ shows."""
    root = os.path.join(target, PROJECTS_DIR)
    try:
        folders = sorted(os.listdir(root))
    except OSError:
        return []
    dirs = set()
    for name in folders:
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        dirs.update(decode_project_folder(name))
        dirs.update(session_dirs(folder))
    return sorted({os.path.realpath(d) for d in dirs if os.path.isdir(d)})


def projects_with_own(target, names):
    """Map each /name to the projects that have their own skill or command of that name."""
    own = {name: [] for name in names}
    if not own:
        return own
    # The home directory is a project too, and its .claude is the user-level directory: the
    # install target, or the real one when --target points elsewhere.
    user_level = {os.path.realpath(target), os.path.realpath(os.path.expanduser("~/.claude"))}
    for d in project_dirs(target):
        config = os.path.join(d, ".claude")
        if os.path.realpath(config) in user_level:
            continue
        for name in own:
            if (os.path.isfile(os.path.join(config, "skills", name, "SKILL.md"))
                    or os.path.isfile(os.path.join(config, "commands", name + ".md"))):
                own[name].append(d)
    return own


def override_covered(record, rel, decision, projects):
    """A recorded decision for this file covers every project that now has its own."""
    seen = record["project_overrides"].get(rel)
    return (isinstance(seen, dict) and seen.get("decision") == decision
            and isinstance(seen.get("projects"), list)
            and set(projects) <= set(seen["projects"]))


# --- settings.json -------------------------------------------------------------------------

def bundle_commands(entry):
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    if not isinstance(hooks, list):
        return set()
    return {h.get("command") for h in hooks
            if isinstance(h, dict) and isinstance(h.get("command"), str) and h.get("command")}


HOME_CLAUDE = "~/.claude/"
INTERPRETER = re.compile(r"^python[0-9.]*$")


def hook_file(command):
    """The file a hook command runs, as an absolute path, or None.

    Accepts a leading interpreter (python3, /usr/bin/python3, env python3, /usr/bin/env
    python3) and expands ~, $HOME and ${HOME}. Anything else (extra arguments, a relative
    path, unparseable quoting) isn't recognised.
    """
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if len(words) > 1 and os.path.basename(words[0]) == "env":
        words = words[1:]
    if len(words) > 1 and INTERPRETER.match(os.path.basename(words[0])):
        words = words[1:]
    if len(words) != 1:
        return None
    path = words[0]
    home = os.path.expanduser("~")
    for prefix in ("${HOME}", "$HOME"):
        if path == prefix or path.startswith(prefix + "/"):
            path = home + path[len(prefix):]
            break
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        return None
    return os.path.realpath(path)


def command_aliases(entries, target):
    """Map each file a bundle command could be written as to that bundle command.

    The bundle writes ~/.claude/<rel>. The same file is found in two places: <rel> under the
    install target (the file this run installs), and <rel> under the real ~/.claude (what the
    command says, and what an install that expanded ~ by hand would hold). Both count.
    """
    aliases = {}
    for s in entries:
        for command in bundle_commands(s["entry"]):
            path = hook_file(command)
            if path:
                aliases[path] = command
            if command.startswith(HOME_CLAUDE):
                rel = command[len(HOME_CLAUDE):]
                aliases[os.path.realpath(os.path.join(target, rel))] = command
    return aliases


def normalised(entry, aliases):
    """A copy of a settings entry with each command that runs a bundle file written the
    bundle's way, so path form alone never makes two entries differ."""
    if not isinstance(entry, dict):
        return entry
    out = copy.deepcopy(entry)
    if isinstance(out.get("hooks"), list):
        for h in out["hooks"]:
            if isinstance(h, dict) and isinstance(h.get("command"), str):
                h["command"] = aliases.get(hook_file(h["command"]), h["command"])
    return out


def load_settings(target):
    """Return (settings, existed). An absent file counts as {}."""
    path = os.path.join(target, SETTINGS_FILE)
    if not os.path.exists(path):
        return {}, False
    try:
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError) as e:
        raise SetupError("can't read %s: %s" % (path, e))
    if not isinstance(settings, dict):
        raise SetupError("can't read %s: it is not a JSON object" % path)
    if not isinstance(settings.get("hooks", {}), dict):
        raise SetupError("can't read %s: 'hooks' is not an object" % path)
    return settings, True


def plan_settings(settings, entries, target):
    """Sort the bundle's entries into (to_add, present, differing).

    Only entries holding one of the bundle's own commands are looked at; hooks the user made
    are neither reported nor touched. A command counts as the bundle's when it runs the same
    file, whatever form the path is written in (see command_aliases).
    """
    hooks = settings.get("hooks", {})
    aliases = command_aliases(entries, target)
    to_add, present, differing = [], [], []
    for s in entries:
        existing = hooks.get(s["event"], [])
        if not isinstance(existing, list):
            raise SetupError("can't read %s: 'hooks.%s' is not a list"
                             % (SETTINGS_FILE, s["event"]))
        ours = bundle_commands(s["entry"])
        matches = [normalised(e, aliases) for e in existing]
        matches = [e for e in matches if bundle_commands(e) & ours]
        if not matches:
            to_add.append(s)
        elif s["entry"] in matches:
            present.append(s)
        else:
            differing.append(s)
    return to_add, present, differing


def write_settings(target, settings, existed, to_add):
    """Append the new entries, back up the old file, write. Return the backup's name."""
    path = os.path.join(target, SETTINGS_FILE)
    hooks = settings.setdefault("hooks", {})
    for s in to_add:
        hooks.setdefault(s["event"], []).append(copy.deepcopy(s["entry"]))
    backup = None
    os.makedirs(target, exist_ok=True)
    if existed:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = "%s.bak-%s" % (SETTINGS_FILE, stamp)
        n = 1
        while os.path.exists(os.path.join(target, backup)):
            n += 1
            backup = "%s.bak-%s-%d" % (SETTINGS_FILE, stamp, n)
        shutil.copy2(path, os.path.join(target, backup))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if existed:
        shutil.copymode(path, tmp)
    os.replace(tmp, path)
    return backup


def describe(s):
    return "%s hook %s" % (s["event"], ", ".join(sorted(bundle_commands(s["entry"]))))


# --- tests ---------------------------------------------------------------------------------

def run_tests(target, test_files):
    """Run each installed test file; return a list of (path, passed, count, output)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    results = []
    for rel in test_files:
        path = os.path.join(target, rel)
        if not os.path.isfile(path):
            results.append((rel, False, 0, "test file missing: %s" % path))
            continue
        module = os.path.splitext(os.path.basename(rel))[0]
        proc = subprocess.run([sys.executable, "-m", "unittest", module],
                              cwd=os.path.dirname(path), env=env,
                              capture_output=True, text=True)
        ran = re.findall(r"^Ran (\d+) tests? in ", proc.stderr, re.M)
        count = int(ran[-1]) if ran else 0
        results.append((rel, proc.returncode == 0, count, proc.stdout + proc.stderr))
    return results


# --- commands ------------------------------------------------------------------------------

def cmd_install(args, manifest, record, target):
    write = not args.dry_run
    commit = bundle_commit()
    today = datetime.date.today().isoformat()
    optional = optional_components(manifest)
    states = {name: (record["components"].get(name) or {}).get("state") for name in optional}
    components = {CORE}
    requested = set()
    if args.with_subagent_guard:
        requested.add("subagent-guard")
    components |= requested
    components |= {name for name, state in states.items() if state == "installed"}

    # settings.json is read and checked before anything is written, so a file that can't be
    # parsed stops the run with nothing changed.
    settings, settings_existed = load_settings(target)
    to_add, present, differing = plan_settings(
        settings, [s for s in manifest.get("settings", []) if s["component"] in components],
        target)

    # Only after settings.json has passed, so a run that stops on it has written nothing.
    if write and os.path.isdir(changes_dir(target)):
        shutil.rmtree(changes_dir(target))

    installed, unchanged, needs_decision = [], [], []
    seeds_kept, earlier_decision, exec_fixed, updated = [], [], [], []
    held_back, held_earlier, overriding = [], [], []

    selected = [e for e in manifest["files"] if e["component"] in components]
    own = projects_with_own(target, {n for n in map(slash_name, (e["target"] for e in selected))
                                     if n})

    for entry in selected:
        src = os.path.join(HERE, entry["source"])
        dst = os.path.join(target, entry["target"])
        bundle_sha = sha256_of(src)

        name = slash_name(entry["target"])
        projects = own.get(name) or []
        if projects and not override_covered(record, entry["target"], "install", projects):
            if os.path.exists(dst):
                overriding.append((entry["target"], name, projects))
            elif override_covered(record, entry["target"], "hold", projects):
                held_earlier.append(entry["target"])
                continue
            else:
                held_back.append((entry["target"], name, projects))
                continue

        if not os.path.exists(dst):
            installed.append(entry["target"])
            if write:
                copy_file(src, dst, entry["executable"])
                note_in_record(record, target, entry, src, dst, "installed", commit, today)
            continue

        current_sha = sha256_of(dst)
        if current_sha == bundle_sha:
            unchanged.append(entry["target"])
            if write:
                note_in_record(record, target, entry, src, dst, "identical", commit, today)
        elif entry["kind"] == "seed":
            # The user's own ledger: keep it, silently.
            seeds_kept.append(entry["target"])
            if write:
                note_in_record(record, target, entry, src, dst, "kept", commit, today)
            continue
        elif previously_decided(record, entry, bundle_sha, current_sha):
            earlier_decision.append(entry["target"])
        elif untouched(record, entry, current_sha):
            # Reached only when the bundle version differs from the file, so from the
            # recorded one too: the bundle has changed since, and the user never edited it.
            updated.append(entry["target"])
            if write:
                copy_file(src, dst, entry["executable"])
                note_in_record(record, target, entry, src, dst, "updated", commit, today)
            continue
        else:
            change = bundle_change(record, target, entry, bundle_sha) if write else None
            diff = write_change(target, entry["target"], change) if change else None
            needs_decision.append((entry["target"], entry["kind"], diff))
            continue

        # A file the bundle's content is settled for: restore a lost executable bit. This
        # changes the mode only, never the content.
        if lacks_exec_bit(entry, dst):
            exec_fixed.append(entry["target"])
            if write:
                os.chmod(dst, os.stat(dst).st_mode | 0o111)

    # Files the bundle used to install and no longer ships.
    removed, retired_listed = [], []
    for entry in manifest["retired"]:
        rel = entry["target"]
        dst = os.path.join(target, rel)
        if not os.path.isfile(dst):
            # Already gone: stop tracking it, without a word.
            if write:
                drop_tracking(record, target, rel)
            continue
        current_sha = sha256_of(dst)
        if record["retired_kept"].get(rel) == current_sha:
            # The user chose to keep it and hasn't edited it since. The label is honoured
            # here, unlike for a live file: there is no bundle version to bring it up to.
            earlier_decision.append(rel)
        elif untouched(record, entry, current_sha):
            removed.append(rel)
            if write:
                os.remove(dst)
                drop_tracking(record, target, rel)
        else:
            retired_listed.append((rel, entry.get("note")))

    backup = None
    if write:
        if to_add:
            backup = write_settings(target, settings, settings_existed, to_add)
            for s in to_add:
                for command in sorted(bundle_commands(s["entry"])):
                    record["settings_added"].append({
                        "event": s["event"], "command": command,
                        "bundle_commit": commit, "date": today})
        for name in requested:
            record["components"][name] = {"state": "installed", "bundle_commit": commit,
                                          "date": today}
        save_record(target, record)
        test_files = [t["file"] for t in manifest.get("tests", [])
                      if t["component"] in components]
        results = run_tests(target, test_files)
    else:
        results = None

    print("Workflow bundle install into %s%s" % (target, " (DRY RUN: nothing written)"
                                                  if args.dry_run else ""))
    print("Installed: %d" % len(installed))
    print("Unchanged: %d" % len(unchanged))
    print("%s: %d" % ("Would update" if args.dry_run else "Updated", len(updated)))
    for path in updated:
        print("  %s" % path)
    print("Left as you have them: %d (seed ledgers kept: %d; skipped by an earlier decision: %d)"
          % (len(seeds_kept) + len(earlier_decision), len(seeds_kept), len(earlier_decision)))
    print("Needs a decision (existing file differs, left as it is): %d" % len(needs_decision))
    for path, kind, diff in needs_decision:
        print("  %s (%s)%s" % (path, kind, ", bundle change: %s" % diff if diff else ""))
    print("%s (no longer in the bundle): %d" % ("Would remove" if args.dry_run else "Removed",
                                               len(removed)))
    for path in removed:
        print("  %s" % path)
    print("No longer in the bundle, you edited it or it isn't in the record: %d"
          % len(retired_listed))
    for path, note in retired_listed:
        print("  %s%s" % (path, " (%s)" % note if note else ""))
    print("Held back, because a project has its own and a user-level copy would override it: %d"
          % len(held_back))
    for path, name, projects in held_back:
        print("  %s (/%s), own copy in: %s" % (path, name, ", ".join(projects)))
    if held_earlier:
        print("Held back by an earlier decision: %d" % len(held_earlier))
        for path in held_earlier:
            print("  %s" % path)
    if overriding:
        print("Installed at user level and overriding a project's own: %d" % len(overriding))
        for path, name, projects in overriding:
            print("  %s (/%s), own copy in: %s" % (path, name, ", ".join(projects)))
    if exec_fixed:
        print("Executable bit %s (content not changed): %d" % (
            "would be restored" if args.dry_run else "restored", len(exec_fixed)))
        for path in exec_fixed:
            print("  %s" % path)

    verb = "would add" if args.dry_run else "added"
    for s in to_add:
        print("settings.json: %s %s" % (verb, describe(s)))
    if to_add and not args.dry_run:
        if backup:
            print("settings.json: rewritten; the previous version is saved as %s" % backup)
        else:
            print("settings.json: created")
    if present:
        print("settings.json: already has %d of the bundle's hook entries" % len(present))
    if differing:
        print("settings.json: entries that differ from the bundle's, left as they are: %d"
              % len(differing))
        for s in differing:
            print("  %s; the bundle's entry is %s" % (describe(s), json.dumps(s["entry"])))

    if results is None:
        print("Tests: not run (dry run)")
    else:
        passed = sum(1 for r in results if r[1])
        total = sum(r[2] for r in results)
        print("Tests: %d of %d files passed, %d tests run" % (passed, len(results), total))
        for rel, ok, count, output in results:
            print("  %s %s (%d tests)" % ("PASS" if ok else "FAIL", rel, count))
            if not ok:
                for line in output.rstrip().splitlines()[-40:]:
                    print("    | " + line)

    not_selected = [name for name in optional if name not in components]
    declined = [name for name in not_selected if states[name] == "declined"]
    offered = [name for name in not_selected if states[name] != "declined"]
    # Installed by the old prompts, so present but never recorded: say so rather than offer
    # it as if it were absent.
    untracked = [name for name in offered
                 if any(os.path.exists(os.path.join(target, e["target"]))
                        for e in manifest["files"] if e["component"] == name)]
    offered = [name for name in offered if name not in untracked]
    for name in untracked:
        print("Optional component %s: its files are present but not in the install record; "
              "re-running with --with-%s will start tracking it." % (name, name))
    if offered:
        print("Optional components not installed: %s" % ", ".join(
            "%s (add with --with-%s)" % (name, name) for name in offered))
    if declined:
        print("Optional components declined earlier: %s" % ", ".join(declined))

    if results is not None and not all(r[1] for r in results):
        return 1
    return 0


def cmd_decline(args, manifest, record, target):
    name = args.component
    if name not in optional_components(manifest):
        print("install.py: %s is not an optional component" % name, file=sys.stderr)
        return 2
    state = (record["components"].get(name) or {}).get("state")
    if state == "installed":
        print("install.py: %s is already installed, so it can't be declined. Removing it means "
              "deleting its files and its settings.json entry by hand." % name, file=sys.stderr)
        return 2
    record["components"][name] = {"state": "declined", "bundle_commit": bundle_commit(),
                                  "date": datetime.date.today().isoformat()}
    save_record(target, record)
    print("Recorded: %s declined. Later runs won't offer it; add it any time with --with-%s."
          % (name, name))
    return 0


def target_rel(target, path):
    """A path as the user gave it, as a target path relative to the install target."""
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        path = os.path.relpath(path, target)
    return os.path.normpath(path).replace(os.sep, "/")


def manifest_entry_for(manifest, target, path):
    """The entry for a file the bundle installs. Never a retired one: see retired_entry_for."""
    rel = target_rel(target, path)
    for entry in manifest["files"]:
        if entry["target"] == rel:
            return entry
    return None


def retired_entry_for(manifest, target, path):
    """The retired-list entry for a file the bundle no longer ships, or None.

    Kept apart from manifest_entry_for so that project-override, which uses that, never accepts
    a retired file.
    """
    rel = target_rel(target, path)
    for entry in manifest["retired"]:
        if entry["target"] == rel:
            return entry
    return None


def record_retired(args, record, target, entry):
    """record on a file the bundle no longer ships: kept or removed only."""
    rel = entry["target"]
    dst = os.path.join(target, rel)
    if args.decision not in RETIRED_DECISIONS:
        print("install.py: %s is no longer in the bundle, so it can only be recorded as kept or "
              "removed." % rel, file=sys.stderr)
        return 2
    if args.decision == "removed":
        if os.path.lexists(dst):
            print("install.py: %s still exists. Delete it first, once the user has said to, then "
                  "record it as removed." % dst, file=sys.stderr)
            return 2
        drop_tracking(record, target, rel)
        save_record(target, record)
        print("Recorded: %s removed. Later runs no longer track it." % rel)
        return 0
    if not os.path.isfile(dst):
        print("install.py: %s doesn't exist, so there is no decision to record." % dst,
              file=sys.stderr)
        return 2
    # Kept: there is no bundle version to compare with any more, so the file's own hash is all
    # that is recorded, apart from record["files"].
    drop_tracking(record, target, rel)
    record["retired_kept"][rel] = sha256_of(dst)
    save_record(target, record)
    print("Recorded: %s kept. Later runs leave it alone until it is edited again." % rel)
    return 0


def cmd_record(args, manifest, record, target):
    retired = retired_entry_for(manifest, target, args.path)
    if retired is not None:
        return record_retired(args, record, target, retired)
    entry = manifest_entry_for(manifest, target, args.path)
    if entry is None:
        print("install.py: %s is not a file this bundle installs. Use a path as the install "
              "summary lists it, relative to %s." % (args.path, target), file=sys.stderr)
        return 2
    if args.decision == "removed":
        print("install.py: %s is still in the bundle, so it can't be recorded as removed. "
              "Record kept, merged or replaced." % entry["target"], file=sys.stderr)
        return 2
    src = os.path.join(HERE, entry["source"])
    dst = os.path.join(target, entry["target"])
    if not os.path.isfile(dst):
        print("install.py: %s doesn't exist, so there is no decision to record." % dst,
              file=sys.stderr)
        return 2
    if args.decision == "replaced" and sha256_of(dst) != sha256_of(src):
        print("install.py: %s doesn't match the bundle version, so it can't be recorded as "
              "replaced. Copy %s over it first, or record kept or merged."
              % (dst, os.path.join(HERE, entry["source"])), file=sys.stderr)
        return 2
    note_in_record(record, target, entry, src, dst, args.decision, bundle_commit(),
                   datetime.date.today().isoformat())
    save_record(target, record)
    print("Recorded: %s %s. Later runs skip it until it is edited again or the bundle "
          "version changes." % (entry["target"], args.decision))
    return 0


def cmd_project_override(args, manifest, record, target):
    entry = manifest_entry_for(manifest, target, args.path)
    name = slash_name(entry["target"]) if entry else None
    if name is None:
        print("install.py: %s is not a skill or command this bundle installs. Use a path as the "
              "install summary lists it, relative to %s." % (args.path, target), file=sys.stderr)
        return 2
    projects = projects_with_own(target, {name})[name]
    if not projects:
        print("install.py: no project has its own /%s, so there is no decision to record."
              % name, file=sys.stderr)
        return 2
    record["project_overrides"][entry["target"]] = {
        "decision": args.decision, "projects": projects, "bundle_commit": bundle_commit(),
        "date": datetime.date.today().isoformat()}
    save_record(target, record)
    if args.decision == "install":
        print("Recorded: /%s goes in at user level, overriding the copy in %s. Run install.py "
              "again to install it." % (name, ", ".join(projects)))
    else:
        print("Recorded: /%s held back. Later runs skip it until another project gets its own."
              % name)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install the workflow bundle.")
    parser.add_argument("--target", default=os.path.expanduser("~/.claude"),
                        help="config directory to install into (default: ~/.claude)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the summary and write nothing")
    parser.add_argument("--with-subagent-guard", action="store_true",
                        help="also install the optional sub-agent record guard")
    sub = parser.add_subparsers(dest="command")
    # --target is accepted after the subcommand too; SUPPRESS keeps an absent one from
    # overriding the value given before it.
    p_decline = sub.add_parser("decline", help="record that an optional component isn't wanted")
    p_decline.add_argument("component")
    p_decline.add_argument("--target", default=argparse.SUPPRESS)
    p_record = sub.add_parser("record", help="record the decision on a listed file")
    p_record.add_argument("path", help="the file's path as the install summary lists it")
    p_record.add_argument("--decision", required=True, choices=DECISIONS + ("removed",))
    p_record.add_argument("--target", default=argparse.SUPPRESS)
    p_override = sub.add_parser(
        "project-override",
        help="record whether a skill or command a project has its own copy of goes in at "
             "user level")
    p_override.add_argument("path", help="the file's path as the install summary lists it")
    p_override.add_argument("--decision", required=True, choices=OVERRIDE_DECISIONS)
    p_override.add_argument("--target", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.command and (args.dry_run or args.with_subagent_guard):
        parser.error("--dry-run and --with-subagent-guard apply to an install, not to %s"
                     % args.command)

    target = os.path.abspath(os.path.expanduser(args.target))
    try:
        manifest = load_manifest()
        record = load_record(target)
        if args.command == "decline":
            return cmd_decline(args, manifest, record, target)
        if args.command == "record":
            return cmd_record(args, manifest, record, target)
        if args.command == "project-override":
            return cmd_project_override(args, manifest, record, target)
        return cmd_install(args, manifest, record, target)
    except SetupError as e:
        print("install.py: %s. Nothing was written." % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
