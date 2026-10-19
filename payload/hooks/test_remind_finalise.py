#!/usr/bin/env python3
import json, os, subprocess, sys, unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remind_finalise.py")

def _run(cmd):
    payload = json.dumps({"tool_input": {"command": cmd}})
    r = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode

def _json(out):
    return json.loads(out)

class TestRemindFinalise(unittest.TestCase):
    def test_fires_on_git_commit(self):
        out, code = _run("git -C /some/project commit -F /tmp/msg.txt")
        self.assertIn("/finalise", out)
        self.assertEqual(code, 0)

    def test_commit_reminder_reaches_user_and_claude(self):
        # Plain stdout from a PostToolUse hook goes only to the debug log. The user sees
        # systemMessage; Claude sees hookSpecificOutput.additionalContext.
        out, _ = _run("git commit -m x")
        data = _json(out)
        self.assertIn("/finalise", data["systemMessage"])
        specific = data["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PostToolUse")
        self.assertIn("/finalise", specific["additionalContext"])

    def test_silent_on_git_push(self):
        out, code = _run("git -C /some/project push")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_silent_on_python(self):
        out, code = _run("python3 /some/project/scripts/run_report.py")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_silent_on_grep(self):
        out, code = _run("grep -n 'TODO' /some/project/scripts/run_report.py")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

if __name__ == "__main__":
    unittest.main()

