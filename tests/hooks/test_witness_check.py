#!/usr/bin/env python3
"""Subprocess-driven tests for witness_check.py.

Standalone module reusing the harness idiom from test_hooks.py /
test_guard_secrets.py: each test builds a throwaway fixture project, points
CLAUDE_PROJECT_DIR at it, writes source files that contain (or lack) markers,
seeds the registry through the CLI's own --add (so the checksum is always
correct), then runs --check / --remove and asserts on exit code and the
WITNESS_JSON machine line.

These tests do NOT depend on the real repo files - every marker file is written
into the fixture. Run: python3 -m unittest tests.hooks.test_witness_check
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
HOOK = "witness_check.py"


def hook_path(name):
    return os.path.join(HOOKS_DIR, name)


def run_cli(args, root):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    return subprocess.run(
        [sys.executable, hook_path(HOOK)] + args,
        capture_output=True,
        text=True,
        env=env,
    )


def parse_witness_json(stdout):
    """Return the parsed dict from the LAST WITNESS_JSON line, or None."""
    lines = [ln for ln in stdout.splitlines()
             if ln.startswith("WITNESS_JSON: ")]
    if not lines:
        return None
    return json.loads(lines[-1][len("WITNESS_JSON: "):])


def last_stdout_line(stdout):
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-witness-")
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def registry_path(self):
        return os.path.join(self.root, "company", "witnesses.json")

    def read_registry(self):
        with open(self.registry_path()) as f:
            return json.load(f)

    def write_registry(self, obj):
        with open(self.registry_path(), "w") as f:
            json.dump(obj, f, indent=2)

    def add(self, file, contains, why, task="t", regex=False):
        args = ["--add", "--file", file, "--contains", contains,
                "--task", task, "--why", why]
        if regex:
            args.append("--regex")
        r = run_cli(args, self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r


class TestCheckPasses(Base):
    def test_all_markers_present_green(self):
        self.write("src/a.py", "load bearing MARKER_ONE here\n")
        self.add("src/a.py", "MARKER_ONE", "a must keep marker one")
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_witness_json(r.stdout)
        self.assertEqual(data, {"ok": True, "failed": [], "count": 1})

    def test_default_mode_is_check(self):
        # No --check flag: still validates.
        self.write("src/a.py", "keeps MARKER here\n")
        self.add("src/a.py", "MARKER", "why")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(parse_witness_json(r.stdout)["ok"])

    def test_witness_json_is_last_line(self):
        self.write("src/a.py", "MARKER_ONE\n")
        self.write("src/b.py", "MARKER_TWO\n")
        self.add("src/a.py", "MARKER_ONE", "one")
        self.add("src/b.py", "MARKER_TWO", "two")
        r = run_cli(["--check"], self.root)
        self.assertTrue(last_stdout_line(r.stdout).startswith("WITNESS_JSON: "),
                        "WITNESS_JSON must be the last stdout line:\n"
                        + r.stdout)


class TestChecksumTamper(Base):
    def test_hand_edit_field_fails_loudly(self):
        self.write("src/a.py", "MARKER here\n")
        self.add("src/a.py", "MARKER", "keep it")
        # Corrupt a field on disk WITHOUT recomputing the checksum.
        reg = self.read_registry()
        reg["witnesses"][0]["why"] = "tampered reason"
        self.write_registry(reg)
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        blob = (r.stdout + r.stderr).lower()
        self.assertIn("checksum", blob)
        self.assertIn("hand-edit", blob)
        # Tamper short-circuits: no per-witness WITNESS_JSON line is emitted.
        self.assertIsNone(parse_witness_json(r.stdout))

    def test_appended_witness_by_hand_fails(self):
        self.write("src/a.py", "MARKER\n")
        self.add("src/a.py", "MARKER", "keep")
        reg = self.read_registry()
        reg["witnesses"].append({
            "id": "W-999", "task": "t", "file": "src/a.py",
            "must_contain": "MARKER", "regex": False, "why": "snuck in",
            "added_at": "2026-01-01T00:00:00Z"})
        self.write_registry(reg)  # stale checksum
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("checksum", (r.stdout + r.stderr).lower())


class TestMissingMarker(Base):
    def test_marker_absent_fails_and_lists_id(self):
        self.write("src/a.py", "this file does NOT hold the canary\n")
        self.add("src/a.py", "MARKER_GONE", "should be present")
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = parse_witness_json(r.stdout)
        self.assertFalse(data["ok"])
        self.assertIn("W-001", data["failed"])
        self.assertEqual(data["count"], 1)

    def test_missing_file_fails(self):
        # Witness points at a file that was never created.
        self.write("src/a.py", "placeholder\n")
        self.add("src/nope.py", "ANYTHING", "file should exist")
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("W-001", parse_witness_json(r.stdout)["failed"])
        self.assertIn("file missing", r.stdout)

    def test_mixed_pass_and_fail(self):
        self.write("src/a.py", "MARKER_ONE present\n")
        self.write("src/b.py", "MARKER_TWO absent here\n")
        self.add("src/a.py", "MARKER_ONE", "keep one")
        self.add("src/b.py", "MARKER_MISSING", "keep two")
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1)
        data = parse_witness_json(r.stdout)
        self.assertEqual(data["failed"], ["W-002"])
        self.assertEqual(data["count"], 2)


class TestRegexMode(Base):
    def test_regex_match_passes(self):
        self.write("src/a.py", "def frobnicate_v3(x):\n")
        self.add("src/a.py", r"frobnicate_v\d", "versioned fn must survive",
                 regex=True)
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(parse_witness_json(r.stdout)["ok"])

    def test_regex_no_match_fails(self):
        self.write("src/a.py", "def frobnicate(x):\n")  # no digit
        self.add("src/a.py", r"frobnicate_v\d", "versioned fn required",
                 regex=True)
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("W-001", parse_witness_json(r.stdout)["failed"])

    def test_literal_metachar_not_treated_as_regex(self):
        # regex=false: dots and parens are literal, not wildcards.
        self.write("src/a.py", "value = max(0, x - y)\n")
        self.add("src/a.py", "max(0, x - y)", "literal clamp")
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(parse_witness_json(r.stdout)["ok"])


class TestEmptyRegistry(Base):
    def test_empty_valid_registry_passes(self):
        # Build an empty registry through the CLI: add then remove leaves a
        # zero-witness registry with a valid checksum.
        self.write("src/a.py", "MARKER\n")
        self.add("src/a.py", "MARKER", "temp")
        r = run_cli(["--remove", "W-001", "--why", "no longer needed"],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_witness_json(r.stdout)
        self.assertEqual(data, {"ok": True, "failed": [], "count": 0})
        self.assertIn("no witnesses registered", r.stdout)


class TestMissingRegistry(Base):
    def test_no_registry_fails(self):
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no registry", (r.stdout + r.stderr).lower())


class TestAddRemoveRecompute(Base):
    def test_add_keeps_checksum_valid_then_remove(self):
        self.write("src/a.py", "MARKER_ONE\n")
        self.write("src/b.py", "MARKER_TWO\n")
        self.add("src/a.py", "MARKER_ONE", "one")
        # After first add, --check is green (checksum valid).
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(parse_witness_json(r.stdout)["count"], 1)

        # Add a second: checksum stays valid, count rises, ids sequential.
        self.add("src/b.py", "MARKER_TWO", "two")
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(parse_witness_json(r.stdout)["count"], 2)
        ids = [w["id"] for w in self.read_registry()["witnesses"]]
        self.assertEqual(ids, ["W-001", "W-002"])

        # Remove the first: checksum stays valid, count drops, id is gone.
        r = run_cli(["--remove", "W-001", "--why", "obsolete"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("removed W-001", r.stdout)
        r = run_cli(["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_witness_json(r.stdout)
        self.assertEqual(data["count"], 1)
        ids = [w["id"] for w in self.read_registry()["witnesses"]]
        self.assertEqual(ids, ["W-002"])

    def test_remove_absent_id_errors(self):
        self.write("src/a.py", "MARKER\n")
        self.add("src/a.py", "MARKER", "keep")
        r = run_cli(["--remove", "W-404", "--why", "nope"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_add_logs_adherence(self):
        self.write("src/a.py", "MARKER\n")
        self.add("src/a.py", "MARKER", "keep")
        log = os.path.join(self.root, "company", "state", "adherence.log")
        contents = open(log).read()
        self.assertIn("witness_check", contents)
        self.assertIn("INFO", contents)
        self.assertIn("W-001", contents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
