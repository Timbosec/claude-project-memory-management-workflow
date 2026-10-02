# <PROJECT NAME>

## Where the instructions live
- Worklist: `backlog.md` — canonical, git-tracked open worklist. Task numbers are stable and
  cited by `decisions.md` — never renumber, even after a task closes. Backlog items go there,
  never in a harness task list (session state — `/clear` destroys it).
- Decision history & rationale: `decisions.md`.
- Lessons specific to this project, awaiting a second case before becoming a project rule:
  `lesson-candidates.md` — see its own header; a promoted candidate lands in this file, in a new
  section named for the rule (not folded into "Where the instructions live").
- Session-close ritual: run `/finalise` before clearing context — it sweeps for undocumented
  decisions/lessons, reconciles `backlog.md`, and runs deterministic integrity checks.
