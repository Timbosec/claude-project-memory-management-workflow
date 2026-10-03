#!/usr/bin/env python3
"""PreToolUse(Edit|Write|MultiEdit) hook: deny a sub-agent editing a project-record file.

Why this exists (not just a memory): a sub-agent should only touch the source/test files named
in its checkpoint brief -- it must not edit a project's CLAUDE.md, `references/`, skills, memory
bodies, `backlog.md`, `decisions.md`, or any other project-record file. Those edits are exactly
the ones a "how to edit standing docs" rule home governs, and a sub-agent typically cannot load
that file -- so a sub-agent editing one of them removes the check rather than moving it. A
standing instruction only *advises* against this; it cannot intercept the call. This hook does.

Scope: fires only on tool calls that originate inside a sub-agent spawned via the Agent tool --
identified by the PreToolUse JSON payload carrying an `agent_id` field, which is present only
for sub-agent tool calls and absent for the supervisor's/main session's own calls (per
code.claude.com/docs/en/hooks.md, "Subagent Context Fields"). The supervisor's own edits to
these files are never touched by this hook.

What it detects: an `Edit`, `Write`, or `MultiEdit` call (all three carry the target path at
`tool_input["file_path"]`) whose normalized path either exactly matches one of the top-level
project-record files (`CLAUDE.md`, `backlog.md`, `decisions.md`) or falls under the
`.claude/skills/` directory or the auto-memory directory. A path under `.claude/skills/` is
exempt when any of its path components is literally `scripts` -- that's where each skill's
source and tests live, the normal delegation target. Paths are normalized with
`os.path.abspath`/`os.path.normpath` only -- never `os.path.realpath` -- because a `Write`
targeting a brand-new file under a forbidden directory won't exist yet for symlink resolution,
and none is needed here.

Repo/memory locations default to the calling session's own working directory (from the payload's
`cwd` field) and that project's derived auto-memory directory, and are overridable via
$SUBAGENT_GUARD_REPO_DIR / $SUBAGENT_GUARD_MEMORY_DIR so tests never touch real project files.

Output protocol: emit a PreToolUse `permissionDecision: deny` to block + feed the reason back
to Claude; stay silent (exit 0) to let everything else fall through to normal permission flow.
"""
from __future__ import annotations

import json
import os
import sys

DENY_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".deny_log.csv")

POLICED_TOOLS = ("Edit", "Write", "MultiEdit")


def _log_deny(hook_name, cwd):
    """Best-effort append of one deny event for a hook-firing-rate metric, if one exists.
    Path overridable via $SUBAGENT_GUARD_DENY_LOG (tests point it at os.devnull). Never raises."""
    path = os.environ.get("SUBAGENT_GUARD_DENY_LOG") or DENY_LOG
    try:
        from datetime import datetime
        base = os.path.basename(cwd.rstrip("/")) if cwd else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')},{hook_name},{base}\n")
    except Exception:
        pass


def _repo_dir(payload_cwd: str) -> str:
    return os.environ.get("SUBAGENT_GUARD_REPO_DIR", payload_cwd or os.getcwd())


def _memory_dir(payload_cwd: str) -> str:
    base = payload_cwd or os.getcwd()
    default = os.path.expanduser(
        "~/.claude/projects/" + base.replace("/", "-") + "/memory/"
    )
    return os.environ.get("SUBAGENT_GUARD_MEMORY_DIR", default)


def _normalize(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def forbidden_match(file_path: str, repo_dir: str, memory_dir: str):
    """Return the normalized matched path if file_path hits a protected project-record
    location, else None. `file_path` may be empty (e.g. a malformed tool_input) -- never
    matches."""
    if not file_path:
        return None
    norm = _normalize(file_path)

    exact_files = {
        _normalize(os.path.join(repo_dir, "CLAUDE.md")),
        _normalize(os.path.join(repo_dir, "backlog.md")),
        _normalize(os.path.join(repo_dir, "decisions.md")),
    }
    if norm in exact_files:
        return norm

    skills_prefix = _normalize(os.path.join(repo_dir, ".claude", "skills")) + os.sep
    memory_prefix = _normalize(memory_dir) + os.sep
    if norm.startswith(skills_prefix):
        rel_parts = norm[len(skills_prefix):].split(os.sep)
        if "scripts" not in rel_parts:
            return norm
    elif norm.startswith(memory_prefix):
        return norm

    return None


def should_deny(payload: dict) -> str | None:
    """Return the matched forbidden path if this call should be denied, else None."""
    if "agent_id" not in payload:
        return None
    if payload.get("tool_name", "") not in POLICED_TOOLS:
        return None
    file_path = payload.get("tool_input", {}).get("file_path", "")
    cwd = payload.get("cwd", "")
    return forbidden_match(file_path, _repo_dir(cwd), _memory_dir(cwd))


def _reason(matched_path: str) -> str:
    return (
        f"Blocked: a sub-agent may not edit `{matched_path}` -- it is a project-record file "
        "(CLAUDE.md, backlog.md, decisions.md, a skill file outside its scripts/ directory, or "
        "a memory file). Stop and report this to the supervisor instead of making the edit."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse -> don't interfere
    matched = should_deny(payload)
    if not matched:
        return 0
    _log_deny("block_subagent_record_edit", payload.get("cwd", ""))
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _reason(matched),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
