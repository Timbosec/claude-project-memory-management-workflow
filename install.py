#!/usr/bin/env python3
"""Install the workflow bundle into a Claude Code config directory (default ~/.claude).

Usage: python3 install.py [--target DIR] [--dry-run] [--with-subagent-guard]

Reads manifest.json and payload/ from this script's own directory. For each file in the
selected components it copies the file if missing, skips it if identical, and otherwise
leaves the existing file alone: a seed ledger is kept silently, any other file is listed as
needing a decision. It then runs the installed tests and prints a short summary.

It never overwrites an existing file that differs from the bundle.

Exit codes: 0 when all is well (files needing a decision count as fine), 1 when an installed
test fails, 2 when the manifest, the payload or the install record can't be read.
"""
import argparse
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
RECORD_FORMAT = 1


class SetupError(Exception):
    """The manifest, the payload or the install record can't be used."""


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
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise SetupError("can't read %s: %s" % (path, e))
    return manifest


def load_record(target):
    path = os.path.join(target, RECORD_DIR, RECORD_FILE)
    if not os.path.exists(path):
        return {"format": RECORD_FORMAT, "files": {}}
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if not isinstance(record.get("files"), dict):
            raise ValueError("no 'files' object")
    except (OSError, ValueError, AttributeError) as e:
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


def note_in_record(record, target, entry, src, dst, decision, commit, today):
    """Record a decision for one file and keep a base copy of the bundle version."""
    record["files"][entry["target"]] = {
        "kind": entry["kind"],
        "bundle_sha256": sha256_of(src),
        "current_sha256": sha256_of(dst),
        "decision": decision,
        "bundle_commit": commit,
        "date": today,
    }
    base = os.path.join(target, RECORD_DIR, "base", entry["target"])
    os.makedirs(os.path.dirname(base), exist_ok=True)
    shutil.copyfile(src, base)


def previously_decided(record, entry, bundle_sha, current_sha):
    """Call 4: a decision was recorded, the bundle hasn't changed, the file still matches."""
    seen = record["files"].get(entry["target"])
    return (isinstance(seen, dict)
            and seen.get("bundle_sha256") == bundle_sha
            and seen.get("current_sha256") == current_sha)


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install the workflow bundle.")
    parser.add_argument("--target", default=os.path.expanduser("~/.claude"),
                        help="config directory to install into (default: ~/.claude)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the summary and write nothing")
    parser.add_argument("--with-subagent-guard", action="store_true",
                        help="also install the optional sub-agent record guard")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.target)
    write = not args.dry_run
    components = {CORE}
    if args.with_subagent_guard:
        components.add("subagent-guard")

    try:
        manifest = load_manifest()
        record = load_record(target)
    except SetupError as e:
        print("install.py: %s" % e, file=sys.stderr)
        return 2

    commit = bundle_commit()
    today = datetime.date.today().isoformat()
    installed, unchanged, needs_decision = [], [], []

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
            if write:
                note_in_record(record, target, entry, src, dst, "kept", commit, today)
        elif previously_decided(record, entry, bundle_sha, current_sha):
            pass
        else:
            needs_decision.append((entry["target"], entry["kind"]))

    if write:
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
    print("Needs a decision (existing file differs, left as it is): %d" % len(needs_decision))
    for path, kind in needs_decision:
        print("  %s (%s)" % (path, kind))
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
    missing = sorted({e["component"] for e in manifest["files"]} - components)
    if missing:
        print("Optional components not installed: %s" % ", ".join(
            "%s (add with --with-%s)" % (name, name) for name in missing))

    if results is not None and not all(r[1] for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
