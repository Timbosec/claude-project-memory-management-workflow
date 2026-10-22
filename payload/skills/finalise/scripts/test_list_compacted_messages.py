#!/usr/bin/env python3
"""Tests for list_compacted_messages.py.

Every transcript here is built in the test from small helper functions that copy the *shapes* of
a Claude Code session file; no text, path, id or timestamp comes from a real transcript. The
script is a command-line tool, so each test writes a transcript into a temp dir and runs it by
subprocess, then reads what it prints.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "list_compacted_messages.py")

FIN_MSG_FIRST = ("<command-message>finalise</command-message>\n"
                 "<command-name>/finalise</command-name>")
FIN_NAME_FIRST = ("<command-name>/finalise</command-name>\n"
                  "<command-message>finalise</command-message>\n"
                  "<command-args></command-args>")
FIN_US_MSG_FIRST = ("<command-message>finalize</command-message>\n"
                    "<command-name>/finalize</command-name>")
FIN_US_NAME_FIRST = ("<command-name>/finalize</command-name>\n"
                     "<command-message>finalize</command-message>\n"
                     "<command-args></command-args>")


class Builder:
    """A synthetic transcript: records are appended in order; add() returns the file line."""

    def __init__(self):
        self.records = []
        self.clock = 0

    def _ts(self):
        self.clock += 1
        return "2000-01-01T%02d:%02d:%02d.000Z" % (self.clock // 3600, self.clock // 60 % 60,
                                                   self.clock % 60)

    def add(self, rec):
        self.records.append(rec)
        return len(self.records)

    def _base(self, typ, **extra):
        rec = {"type": typ, "timestamp": self._ts(), "sessionId": "synthetic-session",
               "version": "9.9.1"}
        rec.update(extra)
        return rec

    def user(self, text, version="9.9.1"):
        rec = self._base("user", origin={"kind": "human"},
                         message={"role": "user", "content": text})
        rec["version"] = version
        return self.add(rec)

    def user_blocks(self, text):
        return self.add(self._base("user", message={
            "role": "user", "content": [{"type": "text", "text": text}]}))

    def assistant(self, model="model-a", text="reply"):
        return self.add(self._base("assistant", message={
            "role": "assistant", "model": model,
            "content": [{"type": "text", "text": text}]}))

    def tool_use(self, name="Bash", tool_input=None, model="model-a"):
        return self.add(self._base("assistant", message={
            "role": "assistant", "model": model,
            "content": [{"type": "tool_use", "id": "t1", "name": name,
                         "input": tool_input if tool_input is not None else {"command": "ls"}}]}))

    def tool_result(self, content="result text"):
        return self.add(self._base("user", toolUseResult={"stdout": "x"}, message={
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                         "content": content}]}))

    def meta(self, text):
        return self.add(self._base("user", isMeta=True,
                                   message={"role": "user", "content": text}))

    def summary(self, text="SUMMARY-TOKEN"):
        return self.add(self._base("user", isCompactSummary=True,
                                   message={"role": "user", "content": text}))

    def boundary(self):
        return self.add(self._base("system", subtype="compact_boundary",
                                   content="Conversation compacted"))

    def compaction(self):
        self.boundary()
        self.summary()

    def finalise(self, form=FIN_MSG_FIRST, version="9.9.1"):
        return self.user(form, version=version)

    def bookkeeping(self):
        return self.add({"type": "attachment", "timestamp": self._ts(),
                         "attachment": {"type": "date"}})

    def text(self, trailing=""):
        return "".join(json.dumps(r) + "\n" for r in self.records) + trailing


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def run(*args, env=None, cwd=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, text=True,
                       env=e, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def listing(out):
    return [ln for ln in out.splitlines() if ln.startswith("#")]


def line_for(out, token):
    found = [ln for ln in listing(out) if token in ln]
    return found[0] if found else None


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "proj", "synthetic-session.jsonl")

    def list_session(self, builder, trailing="", *extra):
        write(self.path, builder.text(trailing))
        return run("--session", self.path, *extra)


class TestWhichMessagesAreListed(TranscriptTest):
    def test_no_finalise_before_one_compaction_lists_from_file_start(self):
        b = Builder()
        l1 = b.user("MSG-ONE")
        b.assistant("model-one")
        l2 = b.user("MSG-TWO")
        b.assistant("model-two")
        b.compaction()
        l3 = b.user("MSG-THREE")
        b.assistant("model-three")
        b.finalise()
        code, out, err = self.list_session(b)
        self.assertEqual((code, err), (0, ""))
        one, two, three = (line_for(out, t) for t in ("MSG-ONE", "MSG-TWO", "MSG-THREE"))
        self.assertIn("COMPACTED", one)
        self.assertIn("COMPACTED", two)
        self.assertIn("IN-CONTEXT", three)
        self.assertNotIn("IN-CONTEXT", one)
        self.assertNotIn("COMPACTED", three)
        # ordinal, file line number, timestamp, then the model of the next assistant record
        self.assertRegex(one, r"^#1 L%d 2000-01-01T\S+ COMPACTED model-one " % l1)
        self.assertRegex(two, r"^#2 L%d " % l2)
        self.assertRegex(three, r"^#3 L%d \S+ IN-CONTEXT model-three " % l3)

    def test_earlier_compaction_before_previous_finalise_does_not_leak_in(self):
        b = Builder()
        b.user("MSG-OLD")
        b.compaction()
        b.user("MSG-MIDDLE")
        b.finalise()                      # the previous /finalise
        b.user("MSG-AFTER")
        b.assistant()
        b.finalise()                      # the current run
        code, out, err = self.list_session(b)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("no compaction since the last /finalise (or session start)", out)
        self.assertEqual(listing(out), [])
        for token in ("MSG-OLD", "MSG-MIDDLE", "MSG-AFTER"):
            self.assertNotIn(token, out)

    def test_previous_finalise_before_a_compaction_limits_the_list_to_what_follows(self):
        b = Builder()
        b.user("MSG-BEFORE-PREVIOUS")
        b.finalise()                      # the previous /finalise
        b.user("MSG-ONE")
        b.compaction()
        b.user("MSG-TWO")
        b.finalise()                      # the current run
        code, out, err = self.list_session(b)
        self.assertEqual((code, err), (0, ""))
        self.assertIsNone(line_for(out, "MSG-BEFORE-PREVIOUS"))
        self.assertIn("COMPACTED", line_for(out, "MSG-ONE"))
        self.assertIn("IN-CONTEXT", line_for(out, "MSG-TWO"))
        self.assertTrue(line_for(out, "MSG-ONE").startswith("#1 "))

    def test_with_three_invocations_the_boundary_is_the_one_before_the_last(self):
        b = Builder()
        b.user("MSG-BEFORE-FIRST")
        b.finalise()                      # an old /finalise
        b.user("MSG-BETWEEN-OLD")
        b.compaction()
        b.finalise()                      # the previous /finalise
        b.user("MSG-AFTER-PREVIOUS")
        b.compaction()
        b.finalise()                      # the current run
        code, out, _ = self.list_session(b)
        self.assertEqual(code, 0)
        for token in ("MSG-BEFORE-FIRST", "MSG-BETWEEN-OLD"):
            self.assertIsNone(line_for(out, token), token)
        self.assertIn("COMPACTED", line_for(out, "MSG-AFTER-PREVIOUS"))
        self.assertTrue(line_for(out, "MSG-AFTER-PREVIOUS").startswith("#1 "))

    def test_the_only_finalise_is_the_current_run_so_the_boundary_is_file_start(self):
        b = Builder()
        b.user("MSG-FIRST")
        b.compaction()
        b.user("MSG-SECOND")
        b.finalise()
        code, out, _ = self.list_session(b)
        self.assertEqual(code, 0)
        self.assertIn("COMPACTED", line_for(out, "MSG-FIRST"))
        self.assertNotIn("no compaction since", out)

    def test_every_spelling_and_order_of_a_previous_invocation_is_a_boundary(self):
        for form in (FIN_MSG_FIRST, FIN_NAME_FIRST, FIN_US_MSG_FIRST, FIN_US_NAME_FIRST,
                     "  \n" + FIN_MSG_FIRST):
            with self.subTest(form=form):
                b = Builder()
                b.user("MSG-HIDDEN")
                b.finalise(form)
                b.user("MSG-SHOWN")
                b.compaction()
                b.finalise()
                code, out, _ = self.list_session(b)
                self.assertEqual(code, 0)
                self.assertIsNone(line_for(out, "MSG-HIDDEN"))
                self.assertTrue(line_for(out, "MSG-SHOWN"))

    def test_a_message_quoting_the_wrapper_is_not_an_invocation(self):
        for quoting in ("as in <command-message>finalise</command-message> earlier",
                        "I typed <command-name>/finalise</command-name> yesterday",
                        "quote:\n" + FIN_MSG_FIRST):
            with self.subTest(quoting=quoting):
                b = Builder()
                b.user("MSG-BEFORE " + quoting)
                b.compaction()
                b.user("MSG-AFTER")
                b.finalise()
                code, out, _ = self.list_session(b)
                self.assertEqual(code, 0)
                self.assertTrue(line_for(out, "MSG-BEFORE"), out)
                self.assertIn("COMPACTED", line_for(out, "MSG-BEFORE"))

    def test_another_slash_command_is_not_a_finalise_boundary(self):
        b = Builder()
        b.user("MSG-ONE")
        b.user("<command-name>/finalise-notes</command-name>\n"
               "<command-message>finalise-notes</command-message>\n"
               "<command-args>ARGS-TOKEN</command-args>")
        b.compaction()
        b.finalise()
        code, out, _ = self.list_session(b)
        self.assertEqual(code, 0)
        self.assertTrue(line_for(out, "MSG-ONE"))

    def test_several_compactions_mark_everything_before_the_last_as_compacted(self):
        b = Builder()
        b.user("MSG-A")
        b.compaction()
        b.user("MSG-B")                   # after the first compaction, before the second
        b.compaction()
        b.user("MSG-C")
        b.finalise()
        code, out, _ = self.list_session(b)
        self.assertEqual(code, 0)
        self.assertIn("2 compactions", out)
        self.assertIn("COMPACTED", line_for(out, "MSG-A"))
        self.assertIn("COMPACTED", line_for(out, "MSG-B"))
        self.assertIn("IN-CONTEXT", line_for(out, "MSG-C"))

    def test_text_blocks_of_a_list_content_are_the_message_text(self):
        b = Builder()
        b.user_blocks("MSG-BLOCKS")
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        self.assertIn("COMPACTED", line_for(out, "MSG-BLOCKS"))

    def test_text_is_flattened_to_one_line_and_cut_near_200_characters(self):
        b = Builder()
        b.user("HEAD-TOKEN first\nsecond line\n\nthird " + "z" * 500 + " TAIL-TOKEN")
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        ln = line_for(out, "HEAD-TOKEN")
        self.assertIn("HEAD-TOKEN first second line third", ln)
        self.assertNotIn("TAIL-TOKEN", ln)
        text = ln.split("| ", 1)[1]
        self.assertLessEqual(len(text), 220)
        self.assertGreaterEqual(len(text), 190)

    def test_header_line_names_file_session_and_version(self):
        b = Builder()
        b.user("MSG-ONE", version="9.9.1")
        b.compaction()
        b.user("MSG-TWO", version="9.9.4")
        b.finalise(version="9.9.4")
        code, out, _ = self.list_session(b)
        first = out.splitlines()[0]
        self.assertIn(self.path, first)
        self.assertIn("synthetic-session", first)
        self.assertIn("9.9.1", first)
        self.assertIn("9.9.4", first)

    def test_model_is_that_of_the_next_assistant_record_not_a_tool_result(self):
        b = Builder()
        b.user("MSG-ONE")
        b.tool_result("something")        # not an assistant record
        b.assistant("model-next")
        b.assistant("model-later")
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        self.assertIn(" model-next ", line_for(out, "MSG-ONE"))
        self.assertNotIn("model-later", line_for(out, "MSG-ONE"))


class TestExcludedKinds(TranscriptTest):
    def build(self):
        b = Builder()
        b.user("REAL-ONE")
        b.tool_result("TOOLRES-1")
        b.tool_result("TOOLRES-2")
        b.meta("META-TOKEN")
        b.boundary()
        b.summary("OLDSUMMARY-TOKEN")
        b.user("<local-command-caveat>CAVEAT-TOKEN</local-command-caveat>")
        b.user("<local-command-stdout>STDOUT-TOKEN</local-command-stdout>")
        b.user("<bash-input>BASHIN-TOKEN</bash-input>")
        b.user("<bash-stdout>BASHOUT-TOKEN</bash-stdout>")
        b.user("<task-notification>NOTIF-TOKEN</task-notification>")
        b.add(b._base("user", origin={"kind": "task-notification"},
                      message={"role": "user", "content": "ORIGNOTIF-TOKEN"}))
        b.add(b._base("user", isMeta=True, origin={"kind": "peer"},
                      message={"role": "user", "content": "PEER-TOKEN"}))
        b.add(b._base("user", origin={"kind": "auto-continuation"},
                      message={"role": "user", "content": "AUTOCONT-TOKEN"}))
        b.user("<command-name>/clear</command-name>\n<command-message>clear</command-message>\n"
               "<command-args></command-args>")
        b.user("[Request interrupted by user]")
        b.user("<system-reminder>REMINDER-TOKEN</system-reminder>")
        b.user("   ")
        b.user("REAL-TWO")
        b.boundary()
        b.user("REAL-THREE")
        b.finalise()
        return b

    def test_none_of_the_excluded_kinds_is_listed(self):
        code, out, err = self.list_session(self.build())
        self.assertEqual((code, err), (0, ""))
        listed = "\n".join(listing(out))
        for token in ("TOOLRES", "META-TOKEN", "SUMMARY-TOKEN", "CAVEAT-TOKEN", "STDOUT-TOKEN",
                      "BASHIN-TOKEN", "BASHOUT-TOKEN", "NOTIF-TOKEN", "PEER-TOKEN",
                      "AUTOCONT-TOKEN", "REMINDER-TOKEN", "clear", "interrupted", "finalise"):
            self.assertNotIn(token, listed)
        self.assertEqual(len(listing(out)), 3)
        for token in ("REAL-ONE", "REAL-TWO", "REAL-THREE"):
            self.assertTrue(line_for(out, token))

    def test_each_excluded_kind_is_counted(self):
        _, out, _ = self.list_session(self.build())
        tail = out[out.index("excluded"):]
        for kind, n in (("tool result", 2), ("meta", 1), ("compact summary", 1),
                        ("local-command output", 2), ("bash-mode input/output", 2),
                        ("task notification", 1), ("origin task-notification", 1),
                        ("origin peer", 1), ("origin auto-continuation", 1),
                        ("slash command (no args)", 1), ("finalise invocation", 1),
                        ("interrupt marker", 1), ("system-reminder only", 1), ("empty", 1)):
            self.assertRegex(tail, r"(?m)^\s+%s: %d$" % (re.escape(kind), n))

    def test_a_tool_result_block_without_the_toolUseResult_field_is_still_a_tool_result(self):
        b = Builder()
        b.add(b._base("user", message={"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "BLOCK-RESULT-TOKEN"}]}))
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        self.assertEqual(listing(out), [])
        self.assertRegex(out, r"(?m)^\s+tool result: 1$")

    def test_a_record_with_toolUseResult_is_a_tool_result_whatever_its_content_looks_like(self):
        b = Builder()
        b.add(b._base("user", toolUseResult={"stdout": "x"},
                      message={"role": "user", "content": "PLAIN-LOOKING-TOKEN"}))
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        self.assertEqual(listing(out), [])
        self.assertRegex(out, r"(?m)^\s+tool result: 1$")

    def test_system_reminder_blocks_are_cut_from_a_real_message(self):
        b = Builder()
        b.user("<system-reminder>REMINDER-TOKEN</system-reminder>REAL-TEXT after")
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        ln = line_for(out, "REAL-TEXT")
        self.assertTrue(ln)
        self.assertNotIn("REMINDER-TOKEN", ln)

    def test_a_slash_command_with_arguments_is_listed_because_the_user_typed_them(self):
        b = Builder()
        b.user("<command-name>/other</command-name>\n<command-message>other</command-message>\n"
               "<command-args>ARGS-TOKEN go ahead</command-args>")
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        ln = line_for(out, "ARGS-TOKEN go ahead")
        self.assertTrue(ln)
        self.assertIn("/other", ln)

    def test_messages_before_the_boundary_are_not_counted_as_excluded(self):
        b = Builder()
        b.tool_result("OLD-RESULT")
        b.finalise()
        b.user("MSG-ONE")
        b.compaction()
        b.finalise()
        _, out, _ = self.list_session(b)
        tail = out[out.index("excluded"):]
        self.assertNotRegex(tail, r"tool result: \d")
        self.assertRegex(tail, r"(?m)^\s+compact summary: 1$")


class TestFormatChecks(TranscriptTest):
    def assertFailsLoud(self, code, out, err, fragment):
        self.assertEqual(code, 2, (out, err))
        self.assertIn(fragment, err)
        self.assertIn("format may have changed", err)
        self.assertNotIn("no compaction", out + err)
        self.assertEqual(listing(out), [])

    def good(self):
        b = Builder()
        b.user("MSG-ONE")
        b.compaction()
        b.finalise()
        return b

    def test_a_line_that_is_not_json_in_the_middle_is_an_error(self):
        lines = self.good().text().splitlines()
        lines.insert(1, "this is not json")
        write(self.path, "\n".join(lines) + "\n")
        self.assertFailsLoud(*run("--session", self.path), "line 2")

    def test_a_json_line_that_is_not_an_object_is_an_error(self):
        lines = self.good().text().splitlines()
        lines.insert(1, "[1, 2]")
        write(self.path, "\n".join(lines) + "\n")
        self.assertFailsLoud(*run("--session", self.path), "line 2")

    def test_no_record_with_a_type_is_an_error_and_not_no_compaction(self):
        write(self.path, '{"kind": "a"}\n{"kind": "b"}\n')
        self.assertFailsLoud(*run("--session", self.path), "type")

    def test_an_empty_file_is_an_error_and_not_no_compaction(self):
        write(self.path, "")
        self.assertFailsLoud(*run("--session", self.path), "type")

    def test_a_user_record_without_a_message_is_an_error(self):
        b = self.good()
        b.add({"type": "user", "timestamp": "2000-01-01T00:00:00.000Z"})
        self.assertFailsLoud(*self.list_session(b), "message")

    def test_a_compact_boundary_without_a_timestamp_is_an_error(self):
        b = Builder()
        b.user("MSG-ONE")
        b.add({"type": "system", "subtype": "compact_boundary"})
        b.finalise()
        self.assertFailsLoud(*self.list_session(b), "timestamp")

    def test_a_compact_summary_with_no_boundary_before_it_is_an_error(self):
        b = Builder()
        b.user("MSG-ONE")
        b.summary()
        b.finalise()
        self.assertFailsLoud(*self.list_session(b), "compact_boundary")

    def test_a_truncated_final_line_is_tolerated_and_said_so(self):
        b = self.good()
        code, out, err = self.list_session(b, trailing='{"type": "assistant", "mess')
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(line_for(out, "MSG-ONE"))
        self.assertIn("last line", out)
        self.assertIn("truncated", out)

    def test_a_truncated_line_that_is_not_last_is_an_error(self):
        lines = self.good().text().splitlines()
        lines.insert(1, '{"type": "assistant", "mess')
        write(self.path, "\n".join(lines) + "\n")
        self.assertFailsLoud(*run("--session", self.path), "line 2")

    def test_unknown_record_types_are_ignored_not_errors(self):
        b = self.good()
        b.add({"type": "some-future-type", "x": 1})
        code, out, err = self.list_session(b)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(line_for(out, "MSG-ONE"))


class TestFindingTheTranscript(TranscriptTest):
    def make(self, name, label, age_seconds, subdir=None):
        b = Builder()
        b.user(label)
        b.compaction()
        b.finalise()
        folder = os.path.join(self.tmp.name, "projdir", subdir) if subdir \
            else os.path.join(self.tmp.name, "projdir")
        path = write(os.path.join(folder, name), b.text())
        t = time.time() - age_seconds
        os.utime(path, (t, t))
        return path

    def test_newest_top_level_file_is_chosen(self):
        old = self.make("old.jsonl", "MSG-FROM-OLD", 7200)
        new = self.make("new.jsonl", "MSG-FROM-NEW", 7000)
        code, out, err = run("--project-dir", os.path.dirname(new))
        self.assertEqual((code, err), (0, ""))
        self.assertIn(new, out.splitlines()[0])
        self.assertTrue(line_for(out, "MSG-FROM-NEW"))
        self.assertIsNone(line_for(out, "MSG-FROM-OLD"))
        self.assertNotIn("WARNING", out)

    def test_warns_naming_another_file_touched_in_the_last_30_minutes(self):
        other = self.make("other.jsonl", "MSG-FROM-OTHER", 600)
        newest = self.make("newest.jsonl", "MSG-FROM-NEWEST", 5)
        code, out, _ = run("--project-dir", os.path.dirname(newest))
        self.assertEqual(code, 0)
        self.assertIn(newest, out.splitlines()[0])
        warning = [ln for ln in out.splitlines() if "WARNING" in ln]
        self.assertEqual(len(warning), 1)
        self.assertIn(other, warning[0])
        self.assertNotIn(newest, warning[0])

    def test_no_warning_when_the_other_file_is_older_than_30_minutes(self):
        self.make("other.jsonl", "MSG-FROM-OTHER", 3600)
        newest = self.make("newest.jsonl", "MSG-FROM-NEWEST", 5)
        _, out, _ = run("--project-dir", os.path.dirname(newest))
        self.assertNotIn("WARNING", out)

    def test_files_in_subdirectories_are_ignored(self):
        top = self.make("top.jsonl", "MSG-TOP", 3 * 3600)
        self.make("agent.jsonl", "MSG-SUB", 5, subdir="session-x")
        code, out, _ = run("--project-dir", os.path.dirname(top))
        self.assertEqual(code, 0)
        self.assertIn(top, out.splitlines()[0])
        self.assertTrue(line_for(out, "MSG-TOP"))
        self.assertNotIn("WARNING", out)

    def test_session_flag_overrides_the_newest_file(self):
        old = self.make("old.jsonl", "MSG-FROM-OLD", 7200)
        self.make("new.jsonl", "MSG-FROM-NEW", 5)
        code, out, _ = run("--project-dir", os.path.dirname(old), "--session", old)
        self.assertEqual(code, 0)
        self.assertTrue(line_for(out, "MSG-FROM-OLD"))
        self.assertIsNone(line_for(out, "MSG-FROM-NEW"))

    def test_no_transcript_in_the_directory_is_exit_2(self):
        empty = os.path.join(self.tmp.name, "emptydir")
        os.makedirs(empty)
        code, out, err = run("--project-dir", empty)
        self.assertEqual(code, 2)
        self.assertIn("no transcript", err)
        self.assertNotIn("no compaction", out + err)

    def test_missing_project_directory_and_missing_session_are_exit_2(self):
        code, out, err = run("--project-dir", os.path.join(self.tmp.name, "nope"))
        self.assertEqual(code, 2)
        self.assertIn("no transcript", err)
        code, out, err = run("--session", os.path.join(self.tmp.name, "nope.jsonl"))
        self.assertEqual(code, 2)
        self.assertIn("no transcript", err)

    def test_default_project_dir_is_derived_from_home_and_the_working_directory(self):
        home = os.path.join(self.tmp.name, "home")
        work = os.path.realpath(os.path.join(self.tmp.name, "work_dir.v2", "sub"))
        os.makedirs(work)
        encoded = re.sub(r"[^A-Za-z0-9]", "-", work)
        b = Builder()
        b.user("MSG-DERIVED")
        b.compaction()
        b.finalise()
        write(os.path.join(home, ".claude", "projects", encoded, "s.jsonl"), b.text())
        code, out, err = run(env={"HOME": home, "USERPROFILE": home}, cwd=work)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(line_for(out, "MSG-DERIVED"))


class TestAround(TranscriptTest):
    def build(self):
        b = Builder()
        lines = {}
        for i in range(40):
            if i % 5 == 0:
                b.bookkeeping()
            lines[i] = b.user("REC-%03d" % i) if i % 2 == 0 else b.assistant(text="REC-%03d" % i)
        return b, lines

    def test_default_window_is_six_records_before_and_twelve_after(self):
        b, lines = self.build()
        code, out, err = self.list_session(b, "", "--around", str(lines[20]))
        self.assertEqual((code, err), (0, ""))
        for i in range(14, 33):
            self.assertIn("REC-%03d" % i, out, i)
        for i in (13, 33):
            self.assertNotIn("REC-%03d" % i, out, i)
        self.assertNotIn("attachment", out)           # bookkeeping records are skipped

    def test_before_and_after_flags_change_the_window(self):
        b, lines = self.build()
        _, out, _ = self.list_session(b, "", "--around", str(lines[20]),
                                      "--before", "1", "--after", "2")
        for i in (19, 20, 21, 22):
            self.assertIn("REC-%03d" % i, out)
        for i in (18, 23):
            self.assertNotIn("REC-%03d" % i, out)

    def test_each_record_shows_line_timestamp_role_and_model(self):
        b, lines = self.build()
        _, out, _ = self.list_session(b, "", "--around", str(lines[20]))
        self.assertRegex(out, r"L%d \S*2000-01-01T\S+ user" % lines[20])
        self.assertRegex(out, r"L%d \S+ assistant model-a" % lines[21])

    def test_tool_use_and_tool_result_are_rendered_and_a_huge_result_is_cut(self):
        b = Builder()
        b.user("ASK-TOKEN")
        b.tool_use("Bash", {"command": "echo CMD-TOKEN"})
        l_res = b.tool_result("HUGE-START " + "x" * 50000 + " HUGE-END")
        b.assistant(text="DONE-TOKEN")
        code, out, _ = self.list_session(b, "", "--around", str(l_res))
        self.assertEqual(code, 0)
        self.assertIn("ASK-TOKEN", out)
        self.assertIn("Bash", out)
        self.assertIn("CMD-TOKEN", out)
        self.assertIn("HUGE-START", out)
        self.assertNotIn("HUGE-END", out)
        self.assertIn("truncated", out)
        self.assertIn("DONE-TOKEN", out)
        self.assertLess(len(out), 6000)

    def test_a_short_record_is_not_marked_truncated(self):
        b = Builder()
        b.user("SHORT-TOKEN")
        b.assistant(text="reply")
        _, out, _ = self.list_session(b, "", "--around", "1")
        self.assertIn("SHORT-TOKEN", out)
        self.assertNotIn("truncated", out)

    def test_around_on_an_unrecognised_format_is_exit_2(self):
        write(self.path, '{"kind": "a"}\n')
        code, out, err = run("--session", self.path, "--around", "1")
        self.assertEqual(code, 2)
        self.assertIn("format may have changed", err)


class TestHelp(unittest.TestCase):
    def test_help_states_the_exit_codes(self):
        code, out, _ = run("--help")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?s)exit.*0.*2")


if __name__ == "__main__":
    unittest.main()
