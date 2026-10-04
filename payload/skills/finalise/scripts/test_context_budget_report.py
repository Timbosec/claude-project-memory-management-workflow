#!/usr/bin/env python3
"""Tests for context_budget_report.py.

This check reads eight mutable paths in production (both CLAUDE.md files, MEMORY.md, the three
other user-scope rule homes, the ledger, and the history CSV) and writes one (the history CSV).
None of these tests may touch the real files -- every test below builds its own fixture text or
its own tmpdir and passes it in explicitly. A test that read the real ~/.claude/CLAUDE.md would
drift red as that file's Provisional-tag count and byte size change (a function grows a repo-data
read and its existing tests start reading live data silently).

Date-dependent logic (candidate age, the history delta) never calls date.today() inside a test
or inside the functions under test without an explicit `today` argument -- fixtures and the
assertions that check them share one pinned reference date, so nothing here can drift as the
calendar advances.
"""
import os
import tempfile
import unittest
from datetime import date

import context_budget_report as cbr


# ---------------------------------------------------------------------------
# split_top_level_bullets / count_marked_bullets
# ---------------------------------------------------------------------------

class TestSplitTopLevelBullets(unittest.TestCase):
    def test_splits_on_column_zero_dash_only(self):
        text = (
            "# Heading\n"
            "\n"
            "- First bullet, line one.\n"
            "  continuation, indented, not a new bullet.\n"
            "- Second bullet.\n"
        )
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 2)
        self.assertIn("continuation, indented", bullets[0])
        self.assertTrue(bullets[1].startswith("- Second bullet."))

    def test_indented_dash_is_not_a_new_bullet(self):
        text = "- Outer bullet.\n  - indented sub-item, not top-level.\n- Next outer bullet.\n"
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 2)
        self.assertIn("indented sub-item", bullets[0])

    def test_no_bullets_returns_empty_list(self):
        self.assertEqual(cbr.split_top_level_bullets("# Just a heading\n\nSome prose.\n"), [])

    def test_text_before_first_bullet_is_dropped(self):
        text = "# Heading\nIntro prose that is not a bullet.\n- Only bullet.\n"
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 1)
        self.assertNotIn("Intro prose", bullets[0])

    def test_bare_dash_without_space_is_not_a_bullet_start(self):
        # A markdown horizontal rule ("---") or a bare "-" line must not be mistaken for a new
        # top-level bullet -- only "- " (dash, then space) starts one.
        text = "- Real bullet, continues here.\n---\nstill part of the same bullet.\n"
        bullets = cbr.split_top_level_bullets(text)
        self.assertEqual(len(bullets), 1)
        self.assertIn("---", bullets[0])
        self.assertIn("still part of the same bullet", bullets[0])


class TestExtractSection(unittest.TestCase):
    def test_extracts_between_heading_and_next_boundary(self):
        text = (
            "# User scope\n"
            "- router bullet, must not be counted\n"
            "\n"
            "# Working rules\n"
            "\n"
            "- rule one\n"
            "- rule two\n"
        )
        section = cbr.extract_section(text, "# Working rules", "# ")
        self.assertNotIn("router bullet", section)
        self.assertIn("rule one", section)
        self.assertIn("rule two", section)

    def test_stops_at_next_matching_boundary_not_eof(self):
        text = "## Checklist\n- kept bullet\n## Origin log\n- excluded bullet\n"
        section = cbr.extract_section(text, "## Checklist", "## ")
        self.assertIn("kept bullet", section)
        self.assertNotIn("excluded bullet", section)

    def test_missing_heading_returns_empty_string(self):
        self.assertEqual(cbr.extract_section("# Something else\n- a bullet\n",
                                              "# Working rules", "# "), "")

    def test_heading_match_is_exact_not_substring(self):
        # A prose line that merely MENTIONS "# Working rules" (e.g. quoting it inside a bullet)
        # must not be mistaken for the real heading line.
        text = (
            "- a bullet that quotes \"# Working rules\" in its own text, decoy\n"
            "\n"
            "# Working rules\n"
            "- the real rule\n"
        )
        section = cbr.extract_section(text, "# Working rules", "# ")
        self.assertIn("the real rule", section)
        self.assertNotIn("decoy", section)


class TestCountMarkedBullets(unittest.TestCase):
    def test_counts_bullets_containing_marker(self):
        text = (
            "- Clean rule, no marker at all.\n"
            "- Tagged rule. (2026-08-01: a case. Provisional -- one case.)\n"
        )
        n_rules, n_marked = cbr.count_marked_bullets(text)
        self.assertEqual(n_rules, 2)
        self.assertEqual(n_marked, 1)

    def test_bullet_with_several_internal_markers_counts_once(self):
        text = (
            "- Multi-part rule.\n"
            "  **Sub-rule A.** (Provisional -- case A.)\n"
            "  **Sub-rule B.** (Provisional -- case B.)\n"
            "  **Sub-rule C.** (Provisional -- case C.)\n"
        )
        n_rules, n_marked = cbr.count_marked_bullets(text)
        self.assertEqual(n_rules, 1)
        self.assertEqual(n_marked, 1)

    def test_empty_text_counts_zero_of_zero(self):
        self.assertEqual(cbr.count_marked_bullets(""), (0, 0))


# ---------------------------------------------------------------------------
# split_h3_entries / count_candidates_awaiting
# ---------------------------------------------------------------------------

class TestSplitH3Entries(unittest.TestCase):
    def test_column_zero_h3_is_an_entry(self):
        text = "## Origin logs\n\n### Rule opening words\n\n- Home: somewhere\n"
        entries = cbr.split_h3_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "Rule opening words")
        self.assertIn("Home: somewhere", entries[0][1])

    def test_indented_schema_template_is_not_an_entry(self):
        # Mirrors the ledger's "## Schema" block: template lines are indented four spaces,
        # so they render as a markdown code block and must never be mistaken for a real entry.
        text = (
            "## Schema\n\n"
            "### Candidate\n\n"
            "    ### <one-line claim, imperative>\n"
            "    - First observed: <absolute date> - <project/task>\n"
        )
        entries = cbr.split_h3_entries(text)
        # Only the real (column-0) "### Candidate" heading is an entry; the indented template
        # line inside its body is not a second entry.
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "Candidate")

    def test_h2_boundary_closes_an_open_entry(self):
        text = "### Entry one\n- Home: x\n## Next section\nsome prose, not an entry body\n"
        entries = cbr.split_h3_entries(text)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("Next section", entries[0][1])
        self.assertNotIn("some prose", entries[0][1])


class TestCountCandidatesAwaiting(unittest.TestCase):
    TODAY = date(2026, 8, 18)

    def test_populated_ledger_returns_nonzero_count_and_oldest_age(self):
        # The load-bearing case: a parser that silently returns
        # 0 on every input would pass the empty-ledger test below but must fail THIS one.
        text = (
            "## Candidates\n\n"
            "### First claim\n"
            "- First observed: 2026-08-01 - example-project\n"
            "- Case: something happened\n"
            "- Would live in: CLAUDE.md Working rules\n"
            "- Status: awaiting a second contrasting case\n\n"
            "### Second claim\n"
            "- First observed: 2026-08-10 - example-project\n"
            "- Case: something else happened\n"
            "- Would live in: prompt-lessons\n"
            "- Status: awaiting a second contrasting case\n"
        )
        count, oldest_age = cbr.count_candidates_awaiting(text, self.TODAY)
        self.assertEqual(count, 2)
        # Oldest is 2026-08-01; 17 days before 2026-08-18.
        self.assertEqual(oldest_age, 17)

    def test_empty_ledger_returns_zero_and_no_age(self):
        count, oldest_age = cbr.count_candidates_awaiting("", self.TODAY)
        self.assertEqual(count, 0)
        self.assertIsNone(oldest_age)

    def test_ledger_with_only_origin_logs_returns_zero(self):
        # A ledger holding two origin logs and no candidates. An
        # origin-log entry has "Home:"/"Promoted:" fields, never "First observed:", so it must
        # not be miscounted as a candidate.
        text = (
            "## Origin logs\n\n"
            "### A rule's opening words\n"
            "- Home: `~/.claude/CLAUDE.md` section Working rules\n"
            "- Promoted: pre-dates the ledger (externalised 2026-08-18)\n"
            "- Cases:\n"
            "  - a narrative\n"
            "- Boundary: not recorded\n"
        )
        count, oldest_age = cbr.count_candidates_awaiting(text, self.TODAY)
        self.assertEqual(count, 0)
        self.assertIsNone(oldest_age)

    def test_origin_log_with_a_bare_promoted_date_is_still_not_a_candidate(self):
        # A promotion's "Promoted:" field is usually a bare date, so this is not a contrived
        # edge case -- a detector keyed on
        # "any field with a date" rather than specifically "First observed:" would wrongly count
        # every future origin log as a candidate too.
        text = (
            "### A promoted rule's opening words\n"
            "- Home: somewhere\n"
            "- Promoted: 2026-09-01\n"
            "- Cases: a narrative\n"
        )
        count, oldest_age = cbr.count_candidates_awaiting(text, self.TODAY)
        self.assertEqual(count, 0)
        self.assertIsNone(oldest_age)

    def test_age_is_computed_against_the_injected_today_not_the_real_clock(self):
        text = "### Claim\n- First observed: 2026-01-01 - example-project\n- Status: awaiting\n"
        count, age_far = cbr.count_candidates_awaiting(text, date(2026, 1, 11))
        self.assertEqual((count, age_far), (1, 10))
        count, age_near = cbr.count_candidates_awaiting(text, date(2026, 1, 2))
        self.assertEqual((count, age_near), (1, 1))


# ---------------------------------------------------------------------------
# history CSV: read / previous_reading / upsert
# ---------------------------------------------------------------------------

class TestHistoryCsv(unittest.TestCase):
    def test_read_history_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cbr.read_history(os.path.join(tmp, "nope.csv")), [])

    def test_upsert_creates_file_on_first_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.csv")
            row = {"date": "2026-08-18", "global_claude_bytes": "100",
                   "project_claude_bytes": "200", "memory_index_bytes": "300",
                   "total_bytes": "600", "global_claude_lines": "10"}
            cbr.upsert_reading(path, row)
            rows = cbr.read_history(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-08-18")
            self.assertEqual(rows[0]["total_bytes"], "600")

    def test_same_day_rerun_replaces_not_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.csv")
            row1 = {"date": "2026-08-18", "global_claude_bytes": "100",
                    "project_claude_bytes": "200", "memory_index_bytes": "300",
                    "total_bytes": "600", "global_claude_lines": "10"}
            row2 = dict(row1, total_bytes="700", global_claude_bytes="200")
            cbr.upsert_reading(path, row1)
            cbr.upsert_reading(path, row2)
            rows = cbr.read_history(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["total_bytes"], "700")

    def test_new_day_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log.csv")
            row1 = {"date": "2026-08-17", "global_claude_bytes": "100",
                    "project_claude_bytes": "200", "memory_index_bytes": "300",
                    "total_bytes": "600", "global_claude_lines": "10"}
            row2 = dict(row1, date="2026-08-18", total_bytes="650")
            cbr.upsert_reading(path, row1)
            cbr.upsert_reading(path, row2)
            rows = cbr.read_history(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["date"] for r in rows}, {"2026-08-17", "2026-08-18"})


class TestPreviousReading(unittest.TestCase):
    ROWS = [
        {"date": "2026-08-10", "total_bytes": "500"},
        {"date": "2026-08-15", "total_bytes": "550"},
        {"date": "2026-08-16", "total_bytes": "560"},
    ]

    def test_returns_most_recent_row_before_today(self):
        prev = cbr.previous_reading(self.ROWS, "2026-08-18")
        self.assertEqual(prev["date"], "2026-08-16")

    def test_ignores_a_row_dated_today_itself(self):
        rows = self.ROWS + [{"date": "2026-08-18", "total_bytes": "999"}]
        prev = cbr.previous_reading(rows, "2026-08-18")
        self.assertEqual(prev["date"], "2026-08-16")

    def test_no_rows_returns_none(self):
        self.assertIsNone(cbr.previous_reading([], "2026-08-18"))

    def test_all_rows_on_or_after_today_returns_none(self):
        rows = [{"date": "2026-08-18", "total_bytes": "1"},
                {"date": "2026-08-19", "total_bytes": "2"}]
        self.assertIsNone(cbr.previous_reading(rows, "2026-08-18"))

    def test_out_of_order_rows_still_pick_the_latest(self):
        rows = [{"date": "2026-08-16", "total_bytes": "1"},
                {"date": "2026-08-05", "total_bytes": "2"},
                {"date": "2026-08-12", "total_bytes": "3"}]
        prev = cbr.previous_reading(rows, "2026-08-18")
        self.assertEqual(prev["date"], "2026-08-16")


# ---------------------------------------------------------------------------
# End-to-end: build_report / main, entirely on injected tmpdir fixtures
# ---------------------------------------------------------------------------

class TestBuildReportEndToEnd(unittest.TestCase):
    def _write(self, tmp, name, text):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_full_report_over_injected_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            global_claude = self._write(tmp, "global.md", (
                "# User scope\n"
                "- a router bullet\n"
                "\n"
                "# Working rules\n"
                "- clean rule\n"
                "- tagged rule (Provisional -- one case.)\n"
            ))
            project_claude = self._write(tmp, "project.md", "# Example Project\nsome project text\n")
            memory_index = self._write(tmp, "MEMORY.md", "# Memory index\n- one line\n")
            prompt_lessons = self._write(tmp, "prompt-lessons.md", (
                "## Checklist\n"
                "- checklist rule, no marker\n"
                "## Origin log\n"
                "- Date: 2026-07-01 Provisional -- must not be counted, wrong section\n"
            ))
            writing_standing_docs = self._write(tmp, "wsd.md", "- one clean rule\n")
            writing_executor_briefs = self._write(tmp, "web.md", (
                "- rule one (Provisional -- case.)\n- rule two\n"
            ))
            ledger = self._write(tmp, "ledger.md", (
                "## Candidates\n\n### Only claim\n"
                "- First observed: 2026-08-08 - example-project\n"
                "- Status: awaiting a second contrasting case\n"
            ))
            history = os.path.join(tmp, "history.csv")
            existing_row = {"date": "2026-08-16",
                             "global_claude_bytes": "10",
                             "project_claude_bytes": "10",
                             "memory_index_bytes": "10",
                             "total_bytes": "30",
                             "global_claude_lines": "3"}
            cbr.upsert_reading(history, existing_row)

            paths = {
                "global_claude": global_claude,
                "project_claude": project_claude,
                "memory_index": memory_index,
                "prompt_lessons": prompt_lessons,
                "writing_standing_docs": writing_standing_docs,
                "writing_executor_briefs": writing_executor_briefs,
                "ledger": ledger,
                "history": history,
            }
            report = cbr.build_report(paths, date(2026, 8, 18))

            # Candidates: one entry, 10 days old (2026-08-08 -> 2026-08-18).
            self.assertEqual(report["n_candidates"], 1)
            self.assertEqual(report["oldest_age_days"], 10)

            # Marker counts: global (1/2 in Working rules, router bullet excluded),
            # prompt-lessons (0/1 -- the Origin log section's Provisional must not count),
            # writing-standing-docs (0/1), writing-executor-briefs (1/2). Total 2/6.
            self.assertEqual(report["total_rules"], 6)
            self.assertEqual(report["total_marked"], 2)
            counts_by_label = {label: (n, m) for label, n, m in report["home_counts"]}
            self.assertEqual(counts_by_label["~/.claude/CLAUDE.md § Working rules"], (2, 1))
            self.assertEqual(counts_by_label["prompt-lessons.md § Checklist"], (1, 0))

            # Bytes: computed from the actual fixture file contents, not hardcoded.
            with open(global_claude, encoding="utf-8") as f:
                expected_global_bytes = len(f.read().encode("utf-8"))
            self.assertEqual(report["global_bytes"], expected_global_bytes)
            self.assertEqual(
                report["total_bytes"],
                report["global_bytes"] + report["project_bytes"] + report["memory_bytes"])

            # Delta against the pre-seeded 2026-08-16 row.
            self.assertIsNotNone(report["previous_reading"])
            self.assertEqual(report["previous_reading"]["date"], "2026-08-16")

            text_report = cbr.format_report(report)
            self.assertIn("2026-08-16", text_report)
            self.assertIn("1 candidate(s), oldest 10 day(s) old", text_report)
            # Delta must be CURRENT minus PREVIOUS (growth is positive), not the other way
            # round -- the previous reading's total_bytes was seeded at 30, well below any
            # real file's size, so the sign is unambiguous.
            expected_delta = report["total_bytes"] - 30
            self.assertGreater(expected_delta, 0)
            self.assertIn(f"+{expected_delta:,} since 2026-08-16", text_report)

    def test_missing_ledger_and_history_are_treated_as_empty_not_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            global_claude = self._write(tmp, "global.md", "# Working rules\n- a rule\n")
            paths = {
                "global_claude": global_claude,
                "project_claude": os.path.join(tmp, "does-not-exist-project.md"),
                "memory_index": os.path.join(tmp, "does-not-exist-memory.md"),
                "prompt_lessons": os.path.join(tmp, "does-not-exist-pl.md"),
                "writing_standing_docs": os.path.join(tmp, "does-not-exist-wsd.md"),
                "writing_executor_briefs": os.path.join(tmp, "does-not-exist-web.md"),
                "ledger": os.path.join(tmp, "does-not-exist-ledger.md"),
                "history": os.path.join(tmp, "does-not-exist-history.csv"),
            }
            report = cbr.build_report(paths, date(2026, 8, 18))
            self.assertEqual(report["n_candidates"], 0)
            self.assertIsNone(report["oldest_age_days"])
            self.assertIsNone(report["previous_reading"])
            self.assertEqual(report["project_bytes"], 0)
            # Must not raise -- absence of the ledger/history is normal, not a fault.
            cbr.format_report(report)

    def test_main_writes_history_and_exits_zero_even_when_marked_rules_exist(self):
        # Exercises main()'s own argv wiring and confirms the report-never-gates contract: a
        # nonzero Provisional count must not turn into a nonzero exit code.
        with tempfile.TemporaryDirectory() as tmp:
            global_claude = self._write(tmp, "global.md", (
                "# Working rules\n- tagged rule (Provisional -- one case.)\n"))
            project_claude = self._write(tmp, "project.md", "text\n")
            memory_index = self._write(tmp, "mem.md", "text\n")
            prompt_lessons = self._write(tmp, "pl.md", "## Checklist\n- rule\n")
            wsd = self._write(tmp, "wsd.md", "- rule\n")
            web = self._write(tmp, "web.md", "- rule\n")
            ledger = self._write(tmp, "ledger.md", "")
            history = os.path.join(tmp, "history.csv")

            argv = [
                "context_budget_report.py",
                "--global-claude", global_claude,
                "--project-claude", project_claude,
                "--memory-index", memory_index,
                "--prompt-lessons", prompt_lessons,
                "--writing-standing-docs", wsd,
                "--writing-executor-briefs", web,
                "--ledger", ledger,
                "--history", history,
                "--today", "2026-08-18",
            ]
            old_argv = cbr.sys.argv
            cbr.sys.argv = argv
            try:
                with self.assertRaises(SystemExit) as ctx:
                    cbr.main()
                self.assertEqual(ctx.exception.code, 0)
            finally:
                cbr.sys.argv = old_argv

            rows = cbr.read_history(history)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-08-18")


if __name__ == "__main__":
    unittest.main()

