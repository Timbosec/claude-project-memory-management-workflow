# Bootstrap prompt 6 of 6 — sub-agent record-file guard (run ONCE per machine)

This one is a different category from the other five: it's not part of `/finalise` or
`/memory-audit` at all. It's a hardening step for whenever you delegate work to a sub-agent (via
the `Agent` tool) on a project that also uses this bundle. Skip it if you never delegate to
sub-agents; nothing else here depends on it.

## What it does and why it's worth having

A sub-agent working a checkpoint should only touch the source/test files named in its brief. It
should never edit the project's `CLAUDE.md`, `backlog.md`, `decisions.md`, anything under
`.claude/skills/` outside a `scripts/` directory, or the auto-memory directory, because those are
exactly the files this whole bundle's discipline depends on, and a sub-agent editing them removes
a check rather than moving it (a sub-agent can't load `writing-standing-docs.md`, so it has no
way to edit one of these files *correctly* even if asked to).

A rule saying "don't do that" in a prompt is advice a sub-agent can still get wrong under
pressure. This hook makes it structural: a `PreToolUse` hook that denies `Edit`/`Write`/`MultiEdit`
calls against those specific locations, but only when the call carries the marker that identifies
it as coming from inside a sub-agent (an `agent_id` field in the hook payload, absent for your own,
main-session edits). Your own edits to these files are never touched by this hook.

## What changed from the source version

The source hook hardcoded one specific project's absolute path and a memory directory baked from
that machine's exact layout, overridable only via two env vars for tests. Rewritten below to
derive both from the calling session's actual working directory (available in the hook's own
payload as `cwd`) using the same `/`-to-`-` derivation the other bootstrap prompts use for the
memory directory, still overridable via env vars, renamed to not reference the origin project.
The denial message also quoted the origin project's own CLAUDE.md section by name; replaced with
a generic explanation of the same policy.

## Instructions for Claude

1. Create `~/.claude/hooks/block_subagent_record_edit.py` with the content below.
2. Create `~/.claude/hooks/test_block_subagent_record_edit.py` with the content below.
3. Run the test suite to confirm it works before wiring it in:
   `PYTHONPATH=~/.claude/hooks python3 -m unittest test_block_subagent_record_edit`
4. Edit `~/.claude/settings.json` to add the entry below to the `PreToolUse` array (create the
   array, or the whole file, if it doesn't exist yet; if a `PreToolUse` array already exists, add
   this as one more entry rather than replacing it).
5. Do NOT commit/push — same reasoning as the earlier prompts.

---

### File: ~/.claude/hooks/block_subagent_record_edit.py

```python
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
```

---

### File: ~/.claude/hooks/test_block_subagent_record_edit.py

```python
"""Unit tests for the block_subagent_record_edit PreToolUse hook.

Drives the real script via subprocess (PreToolUse JSON on stdin, exactly as the harness invokes
it) so the entry point, JSON parsing, and deny-output shape are all exercised.

Every test points $SUBAGENT_GUARD_REPO_DIR / $SUBAGENT_GUARD_MEMORY_DIR at throwaway tempdirs so
nothing here ever touches any real project's CLAUDE.md/backlog.md/decisions.md/skills/memory.

Run with:

    PYTHONPATH=~/.claude/hooks python3 -m unittest test_block_subagent_record_edit
"""
import json
import os
import subprocess
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "block_subagent_record_edit.py")


def run_hook(payload: dict, repo_dir: str, memory_dir: str):
    proc = subprocess.run(
        ["python3", HOOK], input=json.dumps(payload), capture_output=True, text=True,
        env={
            **os.environ,
            "SUBAGENT_GUARD_DENY_LOG": os.devnull,  # don't pollute the metric log
            "SUBAGENT_GUARD_REPO_DIR": repo_dir,
            "SUBAGENT_GUARD_MEMORY_DIR": memory_dir,
        },
    )
    return proc.stdout.strip()


def is_deny(stdout: str) -> bool:
    if not stdout:
        return False
    return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestBlockSubagentRecordEdit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo_dir = os.path.join(self._tmp.name, "repo")
        self.memory_dir = os.path.join(self._tmp.name, "memory")
        os.makedirs(self.repo_dir)
        os.makedirs(self.memory_dir)

    def _payload(self, tool_name, file_path, has_agent_id=True, multi_edit=False):
        payload = {"tool_name": tool_name, "cwd": self.repo_dir}
        if has_agent_id:
            payload["agent_id"] = "sub-agent-123"
        if multi_edit:
            payload["tool_input"] = {
                "file_path": file_path,
                "edits": [{"old_string": "a", "new_string": "b"}],
            }
        else:
            payload["tool_input"] = {"file_path": file_path}
        return payload

    def assertDenied(self, payload):
        out = run_hook(payload, self.repo_dir, self.memory_dir)
        self.assertTrue(is_deny(out), f"expected DENY for {payload}, got: {out!r}")

    def assertAllowed(self, payload):
        out = run_hook(payload, self.repo_dir, self.memory_dir)
        self.assertEqual("", out, f"expected ALLOW (silent) for {payload}, got: {out!r}")

    # --- ALLOW: main-session call (no agent_id) -------------------------------------------
    def test_main_session_editing_backlog_is_allowed(self):
        payload = self._payload("Edit", os.path.join(self.repo_dir, "backlog.md"),
                                 has_agent_id=False)
        self.assertAllowed(payload)

    # --- DENY: sub-agent editing each top-level record file ------------------------------
    def test_subagent_editing_claude_md_is_denied(self):
        payload = self._payload("Edit", os.path.join(self.repo_dir, "CLAUDE.md"))
        self.assertDenied(payload)

    def test_subagent_editing_backlog_is_denied(self):
        payload = self._payload("Edit", os.path.join(self.repo_dir, "backlog.md"))
        self.assertDenied(payload)

    def test_subagent_editing_decisions_is_denied(self):
        payload = self._payload("Edit", os.path.join(self.repo_dir, "decisions.md"))
        self.assertDenied(payload)

    # --- DENY: sub-agent Write of a brand-new file under .claude/skills/ -------------------
    def test_subagent_writing_new_file_under_skills_is_denied(self):
        new_file = os.path.join(self.repo_dir, ".claude", "skills", "shared", "new_thing.md")
        self.assertFalse(os.path.exists(new_file))  # proves realpath would be wrong here
        payload = self._payload("Write", new_file)
        self.assertDenied(payload)

    # --- ALLOW: sub-agent editing a file under a skill's scripts/ directory ----------------
    def test_subagent_editing_shared_scripts_file_is_allowed(self):
        scripts_file = os.path.join(
            self.repo_dir, ".claude", "skills", "shared", "scripts", "some_module.py"
        )
        payload = self._payload("Edit", scripts_file)
        self.assertAllowed(payload)

    # --- ALLOW: sub-agent Write of a brand-new file under a skill's scripts/ ---------------
    def test_subagent_writing_new_file_under_scripts_is_allowed(self):
        new_file = os.path.join(
            self.repo_dir, ".claude", "skills", "some-skill", "scripts", "new_thing.py"
        )
        self.assertFalse(os.path.exists(new_file))  # proves realpath would be wrong here
        payload = self._payload("Write", new_file)
        self.assertAllowed(payload)

    # --- DENY: sub-agent editing SKILL.md is untouched by the scripts/ exemption -----------
    def test_subagent_editing_skill_md_is_still_denied(self):
        skill_md = os.path.join(
            self.repo_dir, ".claude", "skills", "some-skill", "SKILL.md"
        )
        payload = self._payload("Edit", skill_md)
        self.assertDenied(payload)

    # --- DENY: sub-agent editing references/ is untouched by the scripts/ exemption -------
    def test_subagent_editing_references_file_is_still_denied(self):
        ref_file = os.path.join(
            self.repo_dir, ".claude", "skills", "shared", "references", "objectives.md"
        )
        payload = self._payload("Edit", ref_file)
        self.assertDenied(payload)

    # --- DENY: sub-agent editing a file under the memory directory -------------------------
    def test_subagent_editing_memory_file_is_denied(self):
        mem_file = os.path.join(self.memory_dir, "some-lesson.md")
        payload = self._payload("Edit", mem_file)
        self.assertDenied(payload)

    # --- ALLOW: sub-agent editing an unrelated in-scope file --------------------------------
    def test_subagent_editing_unrelated_file_is_allowed(self):
        unrelated = os.path.join(self.repo_dir, "some_data.csv")
        payload = self._payload("Edit", unrelated)
        self.assertAllowed(payload)

    # --- DENY: MultiEdit's file_path extraction (not just Edit/Write) ----------------------
    def test_subagent_multiedit_on_forbidden_file_is_denied(self):
        payload = self._payload("MultiEdit", os.path.join(self.repo_dir, "decisions.md"),
                                 multi_edit=True)
        self.assertDenied(payload)

    # --- ALLOW: malformed/unparseable stdin (fails open) ------------------------------------
    def test_malformed_stdin_is_allowed(self):
        proc = subprocess.run(
            ["python3", HOOK], input="not valid json{{{", capture_output=True, text=True,
            env={
                **os.environ,
                "SUBAGENT_GUARD_DENY_LOG": os.devnull,
                "SUBAGENT_GUARD_REPO_DIR": self.repo_dir,
                "SUBAGENT_GUARD_MEMORY_DIR": self.memory_dir,
            },
        )
        self.assertEqual("", proc.stdout.strip())

    # --- ALLOW: a tool this hook doesn't police, reaching it directly ----------------------
    def test_unpoliced_tool_is_allowed(self):
        payload = self._payload("Bash", os.path.join(self.repo_dir, "decisions.md"))
        self.assertAllowed(payload)


if __name__ == "__main__":
    unittest.main()
```

---

### settings.json addition

Add this object as an entry inside the top-level `PreToolUse` array in `~/.claude/settings.json`:

```json
{
  "matcher": "Edit|Write|MultiEdit",
  "hooks": [
    {
      "type": "command",
      "command": "~/.claude/hooks/block_subagent_record_edit.py",
      "timeout": 5
    }
  ]
}
```
