#!/usr/bin/env python3
"""PostToolUse hook: remind to run /finalise after any git commit."""
import json, re, sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")
if not (re.search(r'\bgit\b', cmd) and re.search(r'\bcommit\b', cmd)):
    sys.exit(0)

# Plain stdout from a PostToolUse hook reaches neither the user nor Claude, so emit JSON:
# systemMessage is shown to the user, additionalContext is added to Claude's context.
msg = "REMINDER: run /finalise before clearing this session to capture any undocumented decisions."
print(json.dumps({
    "systemMessage": msg,
    "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg},
}))

