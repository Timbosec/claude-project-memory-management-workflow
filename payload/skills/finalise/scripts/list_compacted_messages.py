#!/usr/bin/env python3
"""List the user messages a compaction took out of context, so /finalise can sweep them.

Claude Code compacts a long session, and afterwards the agent sees only a summary of what the
user said. The full transcript stays on disk as a .jsonl file under
~/.claude/projects/<project folder>/. This script is an INDEX: it finds the compaction(s) since
the previous /finalise and lists every real user message since then, one line each, marked
COMPACTED (before the last compaction, so no longer in context in full) or IN-CONTEXT. The agent
decides which of them are decisions, feedback or lessons; this script decides nothing. With
--around LINE it prints a readable rendering of the records near one file line, so the agent can
read what it wrote and did before a message and how it resolved after.

Usage:
  list_compacted_messages.py [--project-dir DIR] [--session FILE]
  list_compacted_messages.py [--project-dir DIR] [--session FILE] --around LINE
                             [--before N] [--after N]

  --project-dir DIR  folder holding the session files; default ~/.claude/projects/<working
                     directory with every character other than a letter or digit replaced by
                     "-">
  --session FILE     use this transcript instead of the newest top-level *.jsonl in the folder
                     (sub-folders hold sub-agent transcripts and are ignored)
  --around LINE      render the records near file line LINE instead of listing (the first
                     rendered record at or after LINE is the anchor); --before N / --after N
                     give the number of rendered records either side (default 6 and 12)

Run from inside the current /finalise: the LAST /finalise invocation in the file is taken to be
the current run, the one before it (or the start of the file) is where the listing starts.

Exit codes:
  0  nothing to do ("no compaction since the last /finalise (or session start)"), or the listing
     or rendering was printed
  2  no transcript found, or the transcript is not in the format this script understands (the
     message says what was unexpected). The agent then sweeps by hand: a format this script
     cannot read is never reported as "no compaction".

The transcript format is undocumented and may change. The script depends on these fields, and
exits 2 when the first group is missing, rather than guessing:
  required   every line is a JSON object (only a truncated FINAL line is tolerated, since the
             file is live); at least one record has `type`; a `type: "user"` record has a
             `message` object; a `type: "system"`, `subtype: "compact_boundary"` record has
             `timestamp`; an `isCompactSummary` record is preceded by a compact_boundary
  used       `isMeta`, `isCompactSummary`, `toolUseResult` and `origin.kind` (to tell what the
             user did not type); `message.content` (a string, or a list whose `text` blocks are
             the text); `message.model` of assistant records; `timestamp`; `sessionId` and
             `version` (shown on the first output line); the command wrapper text
             `<command-message>finalise</command-message>` /
             `<command-name>/finalise</command-name>` (also `finalize`) at the very start of a
             user record's content, which marks an invocation of /finalise
"""
import argparse
import glob
import json
import os
import re
import sys
import time

PREVIEW_CHARS = 200
RECORD_CAP = 1500
TOOL_INPUT_CAP = 300
RECENT_SECONDS = 30 * 60
DEFAULT_BEFORE, DEFAULT_AFTER = 6, 12
CHANGED = ("The transcript format may have changed; sweep the session by hand instead of "
           "relying on this script.")

NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
WRAPPER_TAG = re.compile(r"\s*<command-(name|message)>(.*?)</command-\1>", re.S)
FINALISE_NAMES = {"finalise", "finalize"}


class FormatError(Exception):
    """The transcript is not in a format this script understands (exit 2)."""


def encode_project_dir(path):
    """The project folder name Claude Code uses: every non-alphanumeric character becomes '-'
    (the same rule as install.py's NOT_ALNUM)."""
    return NOT_ALNUM.sub("-", path)


def default_project_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "projects",
                        encode_project_dir(os.getcwd()))


def newest_transcript(project_dir):
    """(newest top-level *.jsonl or None, other top-level files modified in the last 30 min)."""
    files = [p for p in glob.glob(os.path.join(project_dir, "*.jsonl")) if os.path.isfile(p)]
    if not files:
        return None, []
    files.sort(key=os.path.getmtime)
    newest = files[-1]
    now = time.time()
    recent = [p for p in files[:-1] if now - os.path.getmtime(p) < RECENT_SECONDS]
    return newest, recent


def read_records(path):
    """[(file line number, record dict)] for the whole file, plus whether the last line was
    cut off. Raises FormatError for anything but a truncated final line."""
    with open(path, "rb") as fh:
        raw = fh.read().decode("utf-8", errors="replace").split("\n")
    last = max((i for i, ln in enumerate(raw) if ln.strip()), default=-1)
    records, truncated = [], False
    for i, ln in enumerate(raw):
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            if i == last:
                truncated = True
                continue
            raise FormatError("line %d is not valid JSON" % (i + 1))
        if not isinstance(rec, dict):
            raise FormatError("line %d is JSON but not an object" % (i + 1))
        records.append((i + 1, rec))
    return records, truncated


def check_format(records):
    if not any(isinstance(rec.get("type"), str) for _, rec in records):
        raise FormatError("no record has a `type` field")
    seen_boundary = False
    for n, rec in records:
        typ = rec.get("type")
        if typ == "user" and not isinstance(rec.get("message"), dict):
            raise FormatError("user record at line %d has no `message` object" % n)
        if typ == "system" and rec.get("subtype") == "compact_boundary":
            seen_boundary = True
            if not rec.get("timestamp"):
                raise FormatError("compact_boundary record at line %d has no `timestamp`" % n)
        if rec.get("isCompactSummary") and not seen_boundary:
            raise FormatError("compact summary at line %d has no compact_boundary record "
                              "before it" % n)


def content_text(rec):
    """(text, has_tool_result_block) of a user record's message content."""
    content = rec["message"].get("content")
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        texts, tool = [], False
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    texts.append(block["text"])
                elif block.get("type") == "tool_result":
                    tool = True
        return "\n".join(texts), tool
    raise FormatError("a user record's message.content is neither text nor a list")


def command_wrapper(text):
    """(name, message, args) when the text STARTS with a slash-command wrapper, else None. The
    wrapper tags are read from the start of the text only, so a message that merely quotes
    them mid-text is not one."""
    pos, parts = 0, {}
    while True:
        m = WRAPPER_TAG.match(text, pos)
        if not m or m.group(1) in parts:
            break
        parts[m.group(1)] = m.group(2).strip()
        pos = m.end()
    if not parts:
        return None
    args = re.match(r"\s*<command-args>(.*?)</command-args>", text[pos:], re.S)
    return parts.get("name", ""), parts.get("message", ""), args.group(1).strip() if args else ""


def is_finalise_invocation(rec):
    if rec.get("type") != "user" or not isinstance(rec.get("message"), dict):
        return False
    if rec.get("isMeta") or rec.get("toolUseResult") is not None:
        return False
    text, _ = content_text(rec)
    wrapper = command_wrapper(text)
    return bool(wrapper) and (wrapper[0].lstrip("/").lower() in FINALISE_NAMES
                              or wrapper[1].lower() in FINALISE_NAMES)


def flatten(text):
    return " ".join(text.split())


def classify(rec):
    """('kind', None) for a user record the user did not type, else (None, text to show)."""
    if rec.get("isCompactSummary"):
        return "compact summary", None
    if rec.get("toolUseResult") is not None:
        return "tool result", None
    origin = rec.get("origin")
    if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
        return "origin %s" % origin["kind"], None
    text, tool_result_block = content_text(rec)
    if tool_result_block and not text.strip():
        return "tool result", None
    head = text.lstrip()
    if head.startswith(("<local-command-caveat>", "<local-command-stdout>",
                        "<local-command-stderr>")):
        return "local-command output", None
    if head.startswith(("<bash-input>", "<bash-stdout>", "<bash-stderr>")):
        return "bash-mode input/output", None
    if head.startswith("<task-notification>"):
        return "task notification", None
    wrapper = command_wrapper(text)
    if wrapper:
        if is_finalise_invocation(rec):
            return "finalise invocation", None
        name, message, args = wrapper
        if not args:
            return "slash command (no args)", None
        return None, "%s %s" % (name or "/" + message, args)
    if rec.get("isMeta"):
        return "meta", None
    if head.startswith("[Request interrupted by user"):
        return "interrupt marker", None
    shown = SYSTEM_REMINDER.sub(" ", text)
    if not shown.strip():
        return ("system-reminder only" if text.strip() else "empty"), None
    return None, shown


def next_assistant_model(records, index):
    for _, rec in records[index + 1:]:
        if rec.get("type") == "assistant":
            model = (rec.get("message") or {}).get("model") if isinstance(
                rec.get("message"), dict) else None
            return model or "?"
    return "?"


def header_line(path, records):
    session = next((r["sessionId"] for _, r in records if isinstance(r.get("sessionId"), str)),
                   os.path.splitext(os.path.basename(path))[0])
    versions = [r["version"] for _, r in records if isinstance(r.get("version"), str)]
    if not versions:
        version = "unknown"
    elif versions[0] == versions[-1]:
        version = versions[0]
    else:
        version = "%s .. %s" % (versions[0], versions[-1])
    return "transcript: %s  session: %s  claude code version: %s" % (path, session, version)


def list_messages(path, records, truncated, warning):
    out = [header_line(path, records)]
    if warning:
        out.append(warning)
    if truncated:
        out.append("note: the last line of the file is truncated (the session is live) and "
                   "was ignored")
    invocations = [n for n, rec in records if is_finalise_invocation(rec)]
    since = invocations[-2] if len(invocations) >= 2 else 0
    boundaries = [n for n, rec in records
                  if n > since and rec.get("type") == "system"
                  and rec.get("subtype") == "compact_boundary"]
    where = ("after the /finalise at line %d" % since) if since else "since the start of the file"
    if not boundaries:
        out.append("no compaction since the last /finalise (or session start)")
        return out
    last_boundary = boundaries[-1]
    out.append("%d compaction%s %s; last compact_boundary at line %d" % (
        len(boundaries), "" if len(boundaries) == 1 else "s", where, last_boundary))
    excluded, ordinal = {}, 0
    for i, (n, rec) in enumerate(records):
        if n <= since or rec.get("type") != "user":
            continue
        kind, text = classify(rec)
        if kind:
            excluded[kind] = excluded.get(kind, 0) + 1
            continue
        ordinal += 1
        status = "COMPACTED" if n < last_boundary else "IN-CONTEXT"
        text = flatten(text)
        if len(text) > PREVIEW_CHARS:
            text = text[:PREVIEW_CHARS] + "..."
        out.append("#%d L%d %s %s %s | %s" % (ordinal, n, rec.get("timestamp", "?"), status,
                                              next_assistant_model(records, i), text))
    out.append("excluded (not typed by the user, not listed):")
    if excluded:
        out.extend("  %s: %d" % (k, v) for k, v in sorted(excluded.items()))
    else:
        out.append("  none")
    return out


# --around -------------------------------------------------------------------------------------

def cap(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit] + " [... truncated, %d more characters]" % (len(text) - limit)


def render_block(block):
    if not isinstance(block, dict):
        return cap(str(block), TOOL_INPUT_CAP)
    kind = block.get("type")
    if kind == "text":
        return str(block.get("text", ""))
    if kind == "tool_use":
        shown = cap(json.dumps(block.get("input"), ensure_ascii=False, sort_keys=True),
                    TOOL_INPUT_CAP)
        return "TOOL_USE %s %s" % (block.get("name", "?"), shown)
    if kind == "tool_result":
        inner = block.get("content")
        if isinstance(inner, list):
            inner = "\n".join(b.get("text", "") if isinstance(b, dict) else str(b)
                              for b in inner)
        return "TOOL_RESULT %s" % (inner if isinstance(inner, str) else
                                   json.dumps(inner, ensure_ascii=False))
    if kind == "thinking":
        return "[thinking omitted]"
    return "[%s block]" % kind


def render_record(n, rec, anchor):
    typ = rec.get("type")
    message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
    if typ == "system":
        role, body = "system", "COMPACT BOUNDARY (everything above is summarised)"
    else:
        role = typ
        content = message.get("content")
        if isinstance(content, str):
            body = content
        elif isinstance(content, list):
            body = "\n".join(render_block(b) for b in content)
        else:
            body = ""
        if rec.get("isCompactSummary"):
            role += " (compact summary)"
        elif rec.get("isMeta"):
            role += " (meta)"
    model = (" " + message["model"]) if typ == "assistant" and message.get("model") else ""
    head = "%sL%d %s %s%s" % (">> " if anchor else "", n, rec.get("timestamp", "?"), role, model)
    return head + "\n" + cap(body.strip(), RECORD_CAP)


def is_renderable(rec):
    if rec.get("type") in ("user", "assistant"):
        return True
    return rec.get("type") == "system" and rec.get("subtype") == "compact_boundary"


def render_around(path, records, line, before, after):
    shown = [(n, rec) for n, rec in records if is_renderable(rec)]
    if not shown:
        raise FormatError("no user or assistant records to show")
    anchor = next((i for i, (n, _) in enumerate(shown) if n >= line), len(shown) - 1)
    lo, hi = max(0, anchor - before), min(len(shown), anchor + after + 1)
    out = [header_line(path, records)]
    for i in range(lo, hi):
        out.append(render_record(shown[i][0], shown[i][1], i == anchor))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="List the user messages a compaction took out of context.",
        epilog="Exit codes: 0 = nothing to do, or the listing was printed; 2 = no transcript "
               "found or its format was not recognised (sweep by hand).")
    ap.add_argument("--project-dir", help="folder holding the session files (default: "
                    "~/.claude/projects/<working directory, non-alphanumerics as '-'>)")
    ap.add_argument("--session", help="use this transcript instead of the newest top-level "
                    "*.jsonl in the project folder")
    ap.add_argument("--around", type=int, metavar="LINE",
                    help="render the records near this file line instead of listing")
    ap.add_argument("--before", type=int, default=DEFAULT_BEFORE,
                    help="records to show before the anchor (default %(default)s)")
    ap.add_argument("--after", type=int, default=DEFAULT_AFTER,
                    help="records to show after the anchor (default %(default)s)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    warning = None
    if args.session:
        path = args.session
        if not os.path.isfile(path):
            print("no transcript found: %s is not a file" % path, file=sys.stderr)
            return 2
    else:
        project_dir = args.project_dir or default_project_dir()
        path, recent = newest_transcript(project_dir)
        if path is None:
            print("no transcript found: no top-level *.jsonl in %s (use --project-dir or "
                  "--session)" % project_dir, file=sys.stderr)
            return 2
        if recent:
            warning = ("WARNING: %s was also modified in the last 30 minutes; the newest file "
                       "may be a different live session (use --session to choose)"
                       % ", ".join(recent))
    try:
        records, truncated = read_records(path)
        check_format(records)
        if args.around is not None:
            lines = render_around(path, records, args.around, args.before, args.after)
        else:
            lines = list_messages(path, records, truncated, warning)
    except FormatError as exc:
        print("unexpected transcript format in %s: %s. %s" % (path, exc, CHANGED),
              file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
