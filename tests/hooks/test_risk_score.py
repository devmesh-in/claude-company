#!/usr/bin/env python3
"""Subprocess-driven tests for risk_score.py (#19).

Standalone module reusing the harness idiom from test_guard_secrets.py: each
test builds a throwaway git repo, points CLAUDE_PROJECT_DIR at it, makes a base
commit and a HEAD commit, then runs the advisory CLI with --base <base-sha> and
asserts on the RISK_JSON line and exit code. Every case must exit 0 (advisory
tool). Fake secret VALUES only.

Run: python3 -m unittest tests.hooks.test_risk_score
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
HOOK = "risk_score.py"

# Fake AWS key value (split so this test file itself is not a secret hit).
FAKE_SECRET = "AKIA" + "IOSFODNN7EXAMPLE"


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


def parse_risk(stdout):
    lines = [ln for ln in stdout.splitlines()
             if ln.startswith("RISK_JSON: ")]
    assert lines, "no RISK_JSON line in output:\n" + stdout
    return json.loads(lines[-1][len("RISK_JSON: "):])


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-risk-")
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
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def base_commit(self):
        self.write("README.md", "hello\n")
        return self.commit_all("base")


class TestLowBand(Base):
    def test_tiny_clean_diff_is_low(self):
        base = self.base_commit()
        self.write("src/util.py", "def add(a, b):\n    return a + b\n")
        self.commit_all("small change")
        r = run_cli(["--base", base], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertEqual(data["band"], "low")
        self.assertEqual(data["recommendation"], "standard verification")
        self.assertLess(data["score"], 25)


class TestHighBand(Base):
    def test_big_sensitive_secret_diff_is_high(self):
        base = self.base_commit()
        # brief owns src/ only; the change lands under .claude/hooks/ (out of
        # ownership + sensitive), is >=800 lines (size 15), and carries a fake
        # secret (secrets 25) -> comfortably >= 50.
        self.write("company/briefs/task.md",
                   "# BRIEF\n\n## You own\n- `src/`\n\n## Scope\n1. x\n")
        body = "".join("x_{} = {}\n".format(i, i) for i in range(850))
        self.write(".claude/hooks/bighook.py",
                   "key = \"" + FAKE_SECRET + "\"\n" + body)
        self.commit_all("big sensitive change with secret")
        r = run_cli(
            ["--base", base, "--brief", "company/briefs/task.md"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertEqual(data["band"], "high", r.stdout)
        self.assertEqual(data["recommendation"], "auditor dispatch mandatory")
        self.assertGreaterEqual(data["score"], 50)
        self.assertEqual(data["signals"]["secrets"], 25)
        self.assertEqual(data["signals"]["sensitive_paths"], 10)
        self.assertEqual(data["signals"]["size"], 15)


class TestOwnershipParse(Base):
    def test_out_of_ownership_scored_per_offending_path(self):
        # Brief lives in the base commit so it is NOT part of base...HEAD.
        self.write("README.md", "hello\n")
        self.write("company/briefs/task.md",
                   "# BRIEF\n\n## You own\n- `src/`\n\n## Next\n- other\n")
        base = self.commit_all("base with brief")
        self.write("src/inside.py", "a = 1\n")     # owned -> 0
        self.write("other/outside.py", "b = 2\n")  # not owned -> +10
        self.commit_all("mixed ownership change")
        r = run_cli(
            ["--base", base, "--brief", "company/briefs/task.md"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertEqual(data["signals"]["out_of_ownership"], 10, r.stdout)

    def test_owned_path_scores_zero(self):
        self.write("README.md", "hello\n")
        self.write("company/briefs/task.md",
                   "# BRIEF\n\n## You own\n- `src/`\n")
        base = self.commit_all("base with brief")
        self.write("src/only.py", "a = 1\n")
        self.commit_all("in-ownership only")
        r = run_cli(
            ["--base", base, "--brief", "company/briefs/task.md"], self.root)
        data = parse_risk(r.stdout)
        self.assertEqual(data["signals"]["out_of_ownership"], 0, r.stdout)


class TestMissingBrief(Base):
    def test_no_brief_skips_ownership_signal(self):
        base = self.base_commit()
        self.write("other/outside.py", "b = 2\n")
        self.commit_all("change without brief")
        r = run_cli(["--base", base], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        # Skipped, not scored, even though the path is "out of ownership".
        self.assertEqual(data["signals"]["out_of_ownership"], 0)
        self.assertIn("no brief", r.stdout)


class TestAlwaysExitZero(Base):
    def test_broken_base_ref_still_exits_zero(self):
        self.base_commit()
        r = run_cli(["--base", "no-such-ref-xyz"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertIn("band", data)
        self.assertIn("score", data)

    def test_json_flag_suppresses_table_but_keeps_machine_line(self):
        base = self.base_commit()
        self.write("src/util.py", "x = 1\n")
        self.commit_all("c")
        r = run_cli(["--base", base, "--json"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("SIGNAL", r.stdout)
        self.assertIn("RISK_JSON: ", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
