#!/usr/bin/env python3
"""Subprocess-driven tests for guard_secrets.py.

Standalone module reusing the harness idiom from test_hooks.py: each test
builds a throwaway fixture project with a real `git init`, points
CLAUDE_PROJECT_DIR at it, stages files, and either feeds a synthetic Bash
hook payload on stdin (mode 1) or runs the --scan-branch CLI (mode 2), then
asserts on exit code / stdout / stderr.

Positive pattern tests stage the secret in a NON-test path (a `tests/` or
`fixtures/` path is deliberately skipped by the scanner - see the skip tests).
Fake secret VALUES only. Run: python3 -m unittest tests.hooks.test_guard_secrets
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
HOOK = "guard_secrets.py"


def hook_path(name):
    return os.path.join(HOOKS_DIR, name)


def run_hook(payload, root, raw_stdin=None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, hook_path(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def run_cli(args, root):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    return subprocess.run(
        [sys.executable, hook_path(HOOK)] + args,
        capture_output=True,
        text=True,
        env=env,
    )


def git(root, *args):
    return subprocess.run(
        ["git", "-C", root] + list(args),
        capture_output=True,
        text=True,
    )


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-secrets-")
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)
        self.init_git()

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

    def init_git(self):
        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        git(self.root, "commit", "--allow-empty", "-m", "init")

    def stage(self, rel, content):
        self.write(rel, content)
        r = git(self.root, "add", rel)
        self.assertEqual(r.returncode, 0, r.stderr)

    def bash_payload(self, command):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command}, "cwd": self.root}

    def commit_hook(self):
        return run_hook(self.bash_payload("git commit -m x"), self.root)


# Realistic-but-FAKE values. None carry a secret-ok: marker.
SECRETS = {
    "aws_access_key": "AKIAIOSFODNN7EXAMPLE",
    "github_ghp": "ghp_" + "a" * 36,
    "github_pat": "github_pat_" + "b" * 30,
    "anthropic_key": "sk-ant-api03-" + "c" * 40,
    "openai_key": "sk-" + "d" * 40,
    "slack_token": "xoxb-" + "1234567890" + "-" + "e" * 12,
    "jwt": "eyJ" + "a" * 30 + ".eyJpc3MiOiJ0ZXN0In0",
}
PRIVATE_KEY_LINE = "-----BEGIN RSA PRIVATE KEY-----"
GENERIC_SECRET_LINE = "api_key = \"" + "A1b2C3d4E5f6G7h8" + "\""


class TestPatternsBlock(Base):
    """Each pattern class blocks (exit 2) on a staged secret with git commit."""

    def _assert_block(self, content, pattern_name, rel="src/config.py"):
        self.stage(rel, content + "\n")
        r = self.commit_hook()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(pattern_name, r.stderr)
        self.assertIn(rel, r.stderr)

    def test_aws_access_key(self):
        self._assert_block("key = " + SECRETS["aws_access_key"],
                           "aws_access_key")

    def test_github_ghp_token(self):
        self._assert_block("tok = " + SECRETS["github_ghp"], "github_token")

    def test_github_pat_token(self):
        self._assert_block("tok = " + SECRETS["github_pat"], "github_token")

    def test_anthropic_key(self):
        # sk-ant-... must report as anthropic, not openai.
        self._assert_block("k = " + SECRETS["anthropic_key"], "anthropic_key")

    def test_openai_key(self):
        self._assert_block("k = " + SECRETS["openai_key"], "openai_key")

    def test_slack_token(self):
        self._assert_block("t = " + SECRETS["slack_token"], "slack_token")

    def test_private_key(self):
        self._assert_block(PRIVATE_KEY_LINE, "private_key")

    def test_jwt(self):
        self._assert_block("token=" + SECRETS["jwt"], "jwt")

    def test_generic_secret(self):
        self._assert_block(GENERIC_SECRET_LINE, "generic_secret",
                           rel="app/keys.txt")


class TestSkipsPass(Base):
    """Secrets in skipped locations must PASS (exit 0)."""

    def test_example_file_skipped(self):
        self.stage("config.py.example",
                   "key = " + SECRETS["aws_access_key"] + "\n")
        r = self.commit_hook()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_tests_path_skipped(self):
        self.stage("tests/data.py",
                   "key = " + SECRETS["aws_access_key"] + "\n")
        r = self.commit_hook()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fixtures_path_skipped(self):
        self.stage("app/fixtures/seed.py",
                   "key = " + SECRETS["openai_key"] + "\n")
        r = self.commit_hook()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_secret_ok_marker_skipped(self):
        self.stage("src/config.py",
                   "key = " + SECRETS["aws_access_key"] + "  # secret-ok:\n")
        r = self.commit_hook()
        self.assertEqual(r.returncode, 0, r.stderr)


class TestNonCommitCommand(Base):
    def test_no_commit_segment_allowed(self):
        # A staged secret, but the command is not a git commit -> exit 0.
        self.stage("src/config.py",
                   "key = " + SECRETS["aws_access_key"] + "\n")
        r = run_hook(self.bash_payload("git status"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestHotfixDoesNotBypass(Base):
    def test_hotfix_still_blocks(self):
        self.set_task({"task": "hf", "type": "hotfix"})
        self.stage("src/config.py",
                   "key = " + SECRETS["aws_access_key"] + "\n")
        r = self.commit_hook()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("aws_access_key", r.stderr)


class TestFailOpen(Base):
    def test_malformed_stdin_exit_zero(self):
        r = run_hook(None, self.root, raw_stdin="not json{")
        self.assertEqual(r.returncode, 0)

    def test_non_bash_tool_exit_zero(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": "x", "content": "y"},
                   "cwd": self.root}
        r = run_hook(payload, self.root)
        self.assertEqual(r.returncode, 0)


class TestScanBranchCLI(Base):
    def _base_commit(self):
        self.write("README.md", "hello\n")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "base")
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def test_scan_branch_finds_secret(self):
        base = self._base_commit()
        self.write("src/config.py",
                   "key = " + SECRETS["aws_access_key"] + "\n")
        git(self.root, "add", "src/config.py")
        git(self.root, "commit", "-m", "add secret")
        r = run_cli(["--scan-branch", base], self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SECRETS_JSON: ", r.stdout)
        line = [ln for ln in r.stdout.splitlines()
                if ln.startswith("SECRETS_JSON: ")][-1]
        data = json.loads(line[len("SECRETS_JSON: "):])
        self.assertGreaterEqual(data["scanned"], 1)
        self.assertEqual(len(data["hits"]), 1)
        hit = data["hits"][0]
        self.assertEqual(hit["file"], "src/config.py")
        self.assertEqual(hit["pattern"], "aws_access_key")
        self.assertIn("line", hit)

    def test_scan_branch_clean_exit_zero(self):
        base = self._base_commit()
        self.write("src/util.py", "def add(a, b):\n    return a + b\n")
        git(self.root, "add", "src/util.py")
        git(self.root, "commit", "-m", "clean change")
        r = run_cli(["--scan-branch", base], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no secrets found", r.stdout)
        line = [ln for ln in r.stdout.splitlines()
                if ln.startswith("SECRETS_JSON: ")][-1]
        data = json.loads(line[len("SECRETS_JSON: "):])
        self.assertEqual(data["hits"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
