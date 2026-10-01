#!/usr/bin/env python3
"""Install the workflow bundle into a Claude Code config directory (default ~/.claude).

Usage:
  python3 install.py [--target DIR] [--dry-run] [--with-subagent-guard]
  python3 install.py [--target DIR] decline subagent-guard
  python3 install.py [--target DIR] record PATH --decision kept|merged|replaced

Reads manifest.json and payload/ from this script's own directory.

Install (no subcommand): for each file in the selected components it copies the file if
missing, skips it if identical, and otherwise leaves the existing file alone: a seed ledger is
kept silently, a file whose recorded decision still holds is skipped, and any other file is
listed as needing a decision. It adds the bundle's hook entries to settings.json, runs the
installed tests and prints a short summary. An optional component is selected when its
--with-... flag is given or when the install record shows it installed earlier.

decline: records that the user doesn't want an optional component, so the summary stops
offering it.

record: the agent calls this after resolving a listed file with the user. It records the
decision so that later runs skip the file until it is edited again or the bundle changes.

It never overwrites an existing file that differs from the bundle, and never changes a
settings.json hook entry that already exists.

Exit codes: 0 when all is well (files needing a decision count as fine), 1 when an installed
test fails, 2 when the manifest, the payload, the install record or settings.json can't be
read, or a subcommand's arguments are wrong.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = "core"
RECORD_DIR = "workflow-bundle"
RECORD_FILE = "install-record.json"
RECORD_FORMAT = 2
BASE_SUFFIX = ".base"
SETTINGS_FILE = "settings.json"
DECISIONS = ("kept", "merged", "replaced")


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
        return {"format": RECORD_FORMAT, "files": {}, "components": {}, "settings_added": []}
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if not isinstance(record.get("files"), dict):
            raise ValueError("no 'files' object")
        if record.get("format", 1) > RECORD_FORMAT:
            raise ValueError("written by a newer install.py (format %s)" % record["format"])
        record.setdefault("components", {})
        record.setdefault("settings_added", [])
        if not isinstance(record["components"], dict):
            raise ValueError("'components' is not an object")
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


# --- settings.json -------------------------------------------------------------------------

def bundle_commands(entry):
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    if not isinstance(hooks, list):
        return set()
    return {h.get("command") for h in hooks if isinstance(h, dict) and h.get("command")}


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


def plan_settings(settings, entries):
    """Sort the bundle's entries into (to_add, present, differing).

    Only entries holding one of the bundle's own commands are looked at; hooks the user made
    are neither reported nor touched.
    """
    hooks = settings.get("hooks", {})
    to_add, present, differing = [], [], []
    for s in entries:
        existing = hooks.get(s["event"], [])
        if not isinstance(existing, list):
            raise SetupError("can't read %s: 'hooks.%s' is not a list"
                             % (SETTINGS_FILE, s["event"]))
        ours = bundle_commands(s["entry"])
        matches = [e for e in existing if bundle_commands(e) & ours]
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
        settings, [s for s in manifest.get("settings", []) if s["component"] in components])

    installed, unchanged, needs_decision = [], [], []
    seeds_kept, earlier_decision, exec_fixed = [], [], []

    for entry in manifest["files"]:
        if entry["component"] not in components:
            continue
        src = os.path.join(HERE, entry["source"])
        dst = os.path.join(target, entry["target"])
        bundle_sha = sha256_of(src)

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
        else:
            needs_decision.append((entry["target"], entry["kind"]))
            continue

        # A file the bundle's content is settled for: restore a lost executable bit. This
        # changes the mode only, never the content.
        if lacks_exec_bit(entry, dst):
            exec_fixed.append(entry["target"])
            if write:
                os.chmod(dst, os.stat(dst).st_mode | 0o111)

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
    print("Left as you have them: %d (seed ledgers kept: %d; skipped by an earlier decision: %d)"
          % (len(seeds_kept) + len(earlier_decision), len(seeds_kept), len(earlier_decision)))
    print("Needs a decision (existing file differs, left as it is): %d" % len(needs_decision))
    for path, kind in needs_decision:
        print("  %s (%s)" % (path, kind))
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


def manifest_entry_for(manifest, target, path):
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        path = os.path.relpath(path, target)
    rel = os.path.normpath(path).replace(os.sep, "/")
    for entry in manifest["files"]:
        if entry["target"] == rel:
            return entry
    return None


def cmd_record(args, manifest, record, target):
    entry = manifest_entry_for(manifest, target, args.path)
    if entry is None:
        print("install.py: %s is not a file this bundle installs. Use a path as the install "
              "summary lists it, relative to %s." % (args.path, target), file=sys.stderr)
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
    p_record.add_argument("--decision", required=True, choices=DECISIONS)
    p_record.add_argument("--target", default=argparse.SUPPRESS)
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
        return cmd_install(args, manifest, record, target)
    except SetupError as e:
        print("install.py: %s. Nothing was written." % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
