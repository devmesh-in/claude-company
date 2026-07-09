#!/usr/bin/env python3
"""Subprocess-driven tests for cost_capture.py.

Mirrors the harness idiom in test_hooks.py: a throwaway fixture project with
company/state/, CLAUDE_PROJECT_DIR pointed at it, a synthetic hook payload on
stdin, and assertions on the resulting costs.log. Adds a synthetic JSONL
transcript builder and a costs.log reader. Run:
  python3 -m unittest tests.hooks.test_cost_capture -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "hooks")
)

# Fixed pricing contract (OQ-W1-01, USD per MTok) - the lead writes the same
# shape into the real company/models.json; the tests synthesize their own.
OPUS_PRICING = {
    "$comment": "OQ-W1-01 estimate only, not billing. USD per MTok.",
    "opus": {"input": 15, "output": 75, "cache_write": 18.75, "cache_read": 1.5},
}

OPUS_MODEL = "claude-opus-4-20250101"


def hook_path(name):
    return os.path.join(HOOKS_DIR, name)


def run_hook(name, payload, root, raw_stdin=None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, hook_path(name)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def assistant_line(model, tin, tout, cache_r, cache_w):
    return json.dumps({
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": tin,
                "output_tokens": tout,
                "cache_creation_input_tokens": cache_w,
                "cache_read_input_tokens": cache_r,
            },
        },
    })


def user_line(text):
    return json.dumps({"type": "user", "message": {"content": text}})


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-cost-")
        os.makedirs(os.path.join(self.root, "company", "state"), exist_ok=True)
        self.session_id = "sess1234-abcd-ef01-2345-6789abcdef01"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def set_task(self, obj):
        self.write("company/state/active-task.json", json.dumps(obj))

    def write_pricing(self, obj):
        self.write("company/models.json", json.dumps(obj))

    def transcript_path(self):
        return os.path.join(self.root, "transcript.jsonl")

    def write_transcript(self, lines):
        with open(self.transcript_path(), "w") as f:
            for ln in lines:
                f.write(ln + "\n")
        return self.transcript_path()

    def append_transcript(self, lines):
        with open(self.transcript_path(), "a") as f:
            for ln in lines:
                f.write(ln + "\n")

    def costs_path(self):
        return os.path.join(self.root, "company", "state", "costs.log")

    def costs_lines(self):
        path = self.costs_path()
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]

    def payload(self, event="Stop", transcript=None, session=None):
        p = {
            "hook_event_name": event,
            "cwd": self.root,
            "transcript_path": (transcript if transcript is not None
                                else self.transcript_path()),
            "session_id": session if session is not None else self.session_id,
        }
        return p

    def invoke(self, event="Stop"):
        return run_hook("cost_capture.py", self.payload(event=event), self.root)


class TestParse(Base):
    def test_two_assistant_lines_one_summed_line_with_est(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        self.write_transcript([
            user_line("hello"),
            assistant_line(OPUS_MODEL, 1000, 2000, 500, 100),
            assistant_line(OPUS_MODEL, 3000, 4000, 1500, 900),
        ])
        r = self.invoke()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.costs_lines()
        self.assertEqual(len(lines), 1, lines)
        line = lines[0]
        # Summed delta across both assistant lines, exact token group.
        self.assertIn("in=4000 out=6000 cache_r=2000 cache_w=1000", line)
        # stop kind + task slug from active-task.
        self.assertIn(" | stop | ", line)
        self.assertIn(" | cost_capture | ", line)
        self.assertIn(OPUS_MODEL, line)
        # est = (4000*15 + 6000*75 + 1000*18.75 + 2000*1.5)/1e6 = 0.53175
        self.assertIn("est=$0.53", line)


class TestCursorDedup(Base):
    def test_second_invocation_logs_only_appended_delta(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        self.write_transcript([
            assistant_line(OPUS_MODEL, 1000, 2000, 500, 100),
            assistant_line(OPUS_MODEL, 3000, 4000, 1500, 900),
        ])
        r1 = self.invoke()
        self.assertEqual(r1.returncode, 0, r1.stderr)
        # Append one more assistant message and re-run.
        self.append_transcript([assistant_line(OPUS_MODEL, 100, 200, 0, 0)])
        r2 = self.invoke()
        self.assertEqual(r2.returncode, 0, r2.stderr)
        lines = self.costs_lines()
        self.assertEqual(len(lines), 2, lines)
        # Second line carries ONLY the appended message, not the earlier tokens.
        self.assertIn("in=100 out=200 cache_r=0 cache_w=0", lines[1])


class TestCompaction(Base):
    def test_compaction_no_double_count(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        self.write_transcript([
            assistant_line(OPUS_MODEL, 1000, 2000, 500, 100),
            assistant_line(OPUS_MODEL, 3000, 4000, 1500, 900),
        ])
        r1 = self.invoke()
        self.assertEqual(r1.returncode, 0, r1.stderr)
        first = self.costs_lines()
        self.assertEqual(len(first), 1, first)
        # Rewrite the transcript SMALLER: fewer bytes than the stored offset,
        # carrying tokens the cursor already counted. This is a compaction.
        self.write_transcript([assistant_line(OPUS_MODEL, 10, 20, 0, 0)])
        self.assertLess(
            os.path.getsize(self.transcript_path()),
            # the pre-compaction transcript was clearly larger; sanity guard
            2000,
        )
        r2 = self.invoke()
        self.assertEqual(r2.returncode, 0, r2.stderr)
        after = self.costs_lines()
        # Compaction run must not emit a double-counted line - already-counted
        # tokens (cum) exceed the shrunk file total, so delta clamps to 0.
        self.assertEqual(len(after), 1, after)
        # The sum of logged tokens never exceeds the true unique total.
        logged_in = sum(self._parse_in(ln) for ln in after)
        self.assertLessEqual(logged_in, 4000)

    @staticmethod
    def _parse_in(line):
        for tok in line.split("|"):
            tok = tok.strip()
            if tok.startswith("in="):
                return int(tok.split()[0].split("=")[1])
        return 0


class TestNoPricing(Base):
    def test_no_pricing_tokens_only(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        # models.json without a pricing map.
        self.write_pricing({"version": 1, "roles": {"developer": "opus"}})
        self.write_transcript([assistant_line(OPUS_MODEL, 100, 200, 0, 0)])
        r = self.invoke()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.costs_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertNotIn("est=$", lines[0])
        self.assertTrue(lines[0].rstrip().endswith("cache_w=0"), lines[0])

    def test_no_models_file_tokens_only(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        # No company/models.json at all.
        self.write_transcript([assistant_line(OPUS_MODEL, 100, 200, 0, 0)])
        r = self.invoke()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.costs_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertNotIn("est=$", lines[0])


class TestSubagentStop(Base):
    def test_subagent_stop_kind_column(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        self.write_transcript([assistant_line(OPUS_MODEL, 100, 200, 0, 0)])
        r = self.invoke(event="SubagentStop")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.costs_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(" | subagent_stop | ", lines[0])


class TestFailOpen(Base):
    def test_raw_non_json_stdin_exits_zero_no_log(self):
        r = run_hook("cost_capture.py", None, self.root, raw_stdin="not json{")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.costs_lines(), [])

    def test_payload_missing_transcript_path_exits_zero_no_log(self):
        p = {"hook_event_name": "Stop", "cwd": self.root,
             "session_id": self.session_id}
        r = run_hook("cost_capture.py", p, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.costs_lines(), [])

    def test_missing_transcript_file_exits_zero_no_line(self):
        self.set_task({"task": "cost_capture", "type": "feature"})
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        # transcript_path points at a file that does not exist.
        p = self.payload(transcript=os.path.join(self.root, "nope.jsonl"))
        r = run_hook("cost_capture.py", p, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.costs_lines(), [])

    def test_missing_session_id_exits_zero_no_line(self):
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        self.write_transcript([assistant_line(OPUS_MODEL, 100, 200, 0, 0)])
        p = {"hook_event_name": "Stop", "cwd": self.root,
             "transcript_path": self.transcript_path()}
        r = run_hook("cost_capture.py", p, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.costs_lines(), [])


class TestEmptyDelta(Base):
    def test_no_assistant_activity_writes_no_line_but_persists_cursor(self):
        self.write_pricing({"version": 1, "pricing": OPUS_PRICING})
        # Only non-assistant lines: no model, no delta -> no costs line.
        self.write_transcript([user_line("a"), user_line("b")])
        r = self.invoke()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.costs_lines(), [])
        # Cursor is still persisted at EOF so future deltas are correct.
        cursor_path = os.path.join(self.root, "company", "state",
                                   ".cost-cursor.json")
        self.assertTrue(os.path.exists(cursor_path))
        with open(cursor_path) as f:
            cursor = json.load(f)
        self.assertIn(self.session_id, cursor)


if __name__ == "__main__":
    unittest.main(verbosity=2)
