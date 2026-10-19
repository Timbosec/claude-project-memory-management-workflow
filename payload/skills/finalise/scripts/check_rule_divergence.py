#!/usr/bin/env python3
"""Rule-divergence report for /memory-audit.

Compares each bundle rule in the user's `~/.claude/CLAUDE.md` with the bundle's own wording of it,
which the installer keeps as `~/.claude/workflow-bundle/base/CLAUDE.md.base`. A rule the user has
edited in place collides with the bundle's wording on every upgrade; this lists those rules, with
the edit shown inline, so /memory-audit can offer to move each addition into a rule of its own.

For every rule in the base file it prints one of:
  identical    the user's rule says the same thing (rewrapping and the ID tag are ignored)
  EDITED       the user's rule differs; the difference is shown as [-removed-] and {+added+}
  NO TAG       the user's file has no `-> [id]` tag for it, but an untagged rule of near-identical
               wording; reported as identical or edited like the others
  MISSING      nothing in the user's file matches it
Rules in the user's file that match no base rule are the user's own and are only counted.

This script only reports; it always exits 0. Deciding what an edit means is /memory-audit's job.
Skips with a message (exit 0) when the install record's base copy doesn't exist, which is the case
before the first install and for a file the installer doesn't compare.

Rule splitting mirrors install.py's `split_rules` (a bundle copy can't import it);
tests/test_rule_divergence_parser.py in the bundle repo checks the two agree.

Usage: check_rule_divergence.py [--claude-md PATH] [--base PATH]
"""
import argparse
import difflib
import os
import re
import sys

HEADING = re.compile(r"^#{1,6}\s")
RULE_ID = re.compile(r"[ \t]*→[ \t]*`\[([a-z0-9]+(?:-[a-z0-9]+)*)\]`[ \t]*$", re.M)
# Below this word-level similarity an untagged rule is not taken for a copy of a base rule.
UNTAGGED_MATCH = 0.6


def split_rules(text):
    """Each top-level bullet as (id or None, body); the body has the tag removed and all
    whitespace collapsed, so rewrapping a rule changes nothing."""
    blocks, current = [], None
    for line in text.splitlines():
        if line.startswith("- "):
            current = [line]
            blocks.append(current)
        elif HEADING.match(line):
            current = None
        elif current is not None:
            current.append(line)
    rules = []
    for b in blocks:
        block = "\n".join(b).strip()
        ids = RULE_ID.findall(block)
        rules.append((ids[-1] if ids else None, " ".join(RULE_ID.sub(" ", block).split())))
    return rules


def word_diff(base, mine):
    """The two bodies as one string: [-words only in the bundle's-] {+words only in yours+}."""
    a, b = base.split(), mine.split()
    out = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(" ".join(a[a1:a2]))
            continue
        if a2 > a1:
            out.append("[-" + " ".join(a[a1:a2]) + "-]")
        if b2 > b1:
            out.append("{+" + " ".join(b[b1:b2]) + "+}")
    return " ".join(out)


def similarity(x, y):
    return difflib.SequenceMatcher(None, x.split(), y.split(), autojunk=False).ratio()


def main():
    here = os.path.expanduser("~/.claude")
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-md", default=os.path.join(here, "CLAUDE.md"))
    ap.add_argument("--base", default=os.path.join(here, "workflow-bundle", "base", "CLAUDE.md.base"))
    args = ap.parse_args()

    if not os.path.isfile(args.base) or not os.path.isfile(args.claude_md):
        print("no bundle base copy of CLAUDE.md or no CLAUDE.md here -- skipping the rule-divergence "
              "check (normal before the first install)")
        return 0
    with open(args.base, encoding="utf-8") as f:
        base = [r for r in split_rules(f.read()) if r[0]]
    with open(args.claude_md, encoding="utf-8") as f:
        mine = split_rules(f.read())

    tagged = {i: body for i, body in mine if i}
    untagged = [body for i, body in mine if not i]
    claimed = set()
    lines, identical = [], 0
    for rid, bundle_body in base:
        label = None
        if rid in tagged:
            body = tagged[rid]
        else:
            best = max(untagged, key=lambda u: similarity(bundle_body, u), default=None)
            if best is not None and similarity(bundle_body, best) >= UNTAGGED_MATCH:
                body, label = best, "NO TAG"
                claimed.add(best)
            else:
                lines.append("MISSING  [%s]: nothing in your file matches it" % rid)
                continue
        if body == bundle_body:
            if label:
                lines.append("NO TAG   [%s]: identical to the bundle's, but your copy has no "
                             "`→ [%s]` tag" % (rid, rid))
            else:
                identical += 1
            continue
        head = "EDITED   [%s]" % rid if not label else "NO TAG   [%s]: no tag in your file; edited" % rid
        lines.append(head + ":\n    " + word_diff(bundle_body, body))

    base_ids = {i for i, _ in base}
    local = sum(1 for i, body in mine if (i and i not in base_ids) or (not i and body not in claimed))
    print("rule divergence: %d bundle rules identical" % identical)
    for line in lines:
        print(line)
    print("rules only in your file (yours, not compared): %d" % local)
    return 0


if __name__ == "__main__":
    sys.exit(main())
