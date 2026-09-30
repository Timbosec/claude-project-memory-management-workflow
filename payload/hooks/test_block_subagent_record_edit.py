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
