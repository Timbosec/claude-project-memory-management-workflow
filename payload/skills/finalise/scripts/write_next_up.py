#!/usr/bin/env python3
"""Replace the 'Next up' block of a backlog.md with new text read from stdin.

Usage: python3 write_next_up.py --backlog PATH < new_block.txt

The block is found by check_thread_state.split_next_up: from the heading line
up to, not including, the next line that starts with '## '. The new text must
be the whole block, heading included, and must end the way the old block does
(the '---' separator), so a block written without it cannot silently delete it.

The file is rewritten only when every check passes, atomically (temp file in
the same directory, then os.replace). On success one line goes to stdout and the
exit code is 0. On refusal 'refused: <reason>' goes to stderr, the exit code is
1 and the file is left byte-identical.
"""
import argparse
import os
import sys
import tempfile

from check_thread_state import _NEXT_UP_DATE_RE, split_next_up


class Refused(Exception):
    pass


def _heading_count(text):
    return len(_NEXT_UP_DATE_RE.findall(text))


def _last_nonblank_line(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ""


def build_result(old_text, new_block):
    """The backlog text with its Next up block replaced by new_block, or
    Refused (with the reason as its message) if any check fails."""
    if _heading_count(old_text) != 1:
        raise Refused("the current file must contain exactly one Next up "
                      "heading, found %d" % _heading_count(old_text))
    if not new_block.strip():
        raise Refused("the new block is empty")
    if not _NEXT_UP_DATE_RE.match(new_block):
        raise Refused("the new block must start, at its first character, with "
                      "a '## Next up — recommended YYYY-MM-DD' heading line")
    for line in new_block.splitlines()[1:]:
        if line.startswith("## "):
            raise Refused("the new block contains another line starting with "
                          "'## ': %r" % line)
    old_block, old_rest = split_next_up(old_text)
    if _last_nonblank_line(new_block) != _last_nonblank_line(old_block):
        raise Refused("the new block must end with the same last non-blank "
                      "line as the old block (%r), found %r"
                      % (_last_nonblank_line(old_block),
                         _last_nonblank_line(new_block)))
    old_tail = old_block[len(old_block.rstrip()):]
    block = new_block.rstrip() + old_tail
    start = _NEXT_UP_DATE_RE.search(old_text).start()
    result = old_text[:start] + block + old_text[start + len(old_block):]
    if _heading_count(result) != 1:
        raise Refused("the result would contain %d Next up headings, not "
                      "exactly one" % _heading_count(result))
    if split_next_up(result)[1] != old_rest:
        raise Refused("the result would change text outside the Next up block")
    return result


def _write_atomic(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".next_up_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backlog", required=True, help="path to backlog.md")
    args = ap.parse_args(argv)
    new_block = sys.stdin.buffer.read().decode("utf-8")
    try:
        with open(args.backlog, encoding="utf-8", newline="") as fh:
            old_text = fh.read()
        result = build_result(old_text, new_block)
    except Refused as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1
    _write_atomic(args.backlog, result)
    print("replaced the Next up block in %s" % args.backlog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
