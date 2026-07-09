#!/usr/bin/env python3
"""Subprocess-driven tests for trace_check.py (#22).

Standalone module reusing the harness idiom from test_guard_secrets.py: each
test builds a throwaway git repo, writes a spec plus tracked source/test files,
commits them (so `git ls-files` sees them), points CLAUDE_PROJECT_DIR at the
repo, runs the CLI, and asserts on the TRACE_JSON line and exit code.

Run: python3 -m unittest tests.hooks.test_trace_check
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
HOOK = "trace_check.py"


def run_cli(args, root):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, HOOK)] + args,
        capture_output=True, text=True, env=env,
    )


def git(root, *args):
    return subprocess.run(
        ["git", "-C", root] + list(args), capture_output=True, text=True)


def parse_trace(stdout):
    lines = [ln for ln in stdout.splitlines()
             if ln.startswith("TRACE_JSON: ")]
    assert lines, "no TRACE_JSON line in output:\n" + stdout
    return json.loads(lines[-1][len("TRACE_JSON: "):])


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-trace-")
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)
        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def commit_all(self, msg):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", msg)


class TestOrphan(Base):
    def test_id_only_in_source_is_orphan(self):
        self.write("company/specs/spec.md",
                   "# Spec\n\nFR-X-1 the user can log in.\n")
        self.write("src/impl.py", "# implements FR-X-1\n")
        # no test file references FR-X-1
        self.commit_all("spec + source only")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = parse_trace(r.stdout)
        self.assertIn("FR-X-1", data["orphans"])
        self.assertFalse(data["ok"])

    def test_id_nowhere_but_spec_is_orphan(self):
        self.write("company/specs/spec.md",
                   "# Spec\n\nFR-Y-2 must do a thing.\n")
        self.write("src/other.py", "# unrelated\n")
        self.commit_all("spec only")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = parse_trace(r.stdout)
        self.assertIn("FR-Y-2", data["orphans"])


class TestTraceable(Base):
    def test_id_in_test_and_source_is_ok(self):
        self.write("company/specs/spec.md",
                   "# Spec\n\nFR-X-1 login works.\n")
        self.write("src/impl.py", "# implements FR-X-1\n")
        self.write("tests/test_login.py", "# covers FR-X-1\n")
        self.commit_all("spec + source + test")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_trace(r.stdout)
        self.assertEqual(data["orphans"], [])
        self.assertTrue(data["ok"])
        self.assertEqual(data["total"], 1)

    def test_bare_fr_id_form_is_extracted(self):
        self.write("company/specs/spec.md", "# Spec\n\nFR-03 bare form.\n")
        self.write("src/impl.py", "# FR-03 here\n")
        self.write("tests/test_x.py", "# FR-03 tested\n")
        self.commit_all("bare fr")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_trace(r.stdout)
        self.assertEqual(data["total"], 1)
        self.assertTrue(data["ok"])


class TestNoSpec(Base):
    def test_absent_specs_dir_exits_zero(self):
        self.write("src/impl.py", "x = 1\n")
        self.commit_all("no specs at all")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no spec with FR IDs", r.stdout)

    def test_specs_without_fr_ids_exits_zero(self):
        self.write("company/specs/notes.md", "# Just notes, no ids here.\n")
        self.commit_all("specs without ids")
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no spec with FR IDs", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
