# <PROJECT NAME> — Decision Log

Durable decisions and their rationale. Append-only; mark a reversed entry `Status: Superseded`
rather than deleting it — the history of having been wrong is part of what makes this useful.

Only decisions with real rationale belong here: a tradeoff considered, an alternative rejected, a
measurement that settled something. A task that was simply done, with nothing arguable about how,
gets its commit hash in `backlog.md`'s Closed stub and nothing here.

---

<!-- Each entry follows this shape:

## <short title naming the decision, not the task number>
- Date: <date>
- Decision: <what was decided, stated as a fact>
- Why: <the reasoning — what was measured, what alternative was considered and rejected, what
  broke without this>
- Status: Active

-->
