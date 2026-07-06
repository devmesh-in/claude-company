#!/usr/bin/env python3
"""Subprocess-driven tests for the claude-company enforcement hooks.

Each test builds a throwaway fixture project (some with a real `git init`),
points CLAUDE_PROJECT_DIR at it, feeds a synthetic hook JSON payload on stdin,
and asserts on exit code / stderr / stdout. Run: python3 test_hooks.py
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


def run_cli(name, args, root):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    return subprocess.run(
        [sys.executable, hook_path(name)] + args,
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
        self.root = tempfile.mkdtemp(prefix="cc-hooks-")
        os.makedirs(os.path.join(self.root, "company", "state"), exist_ok=True)

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

    def edit_payload(self, tool, file_path, text):
        if tool == "Write":
            ti = {"file_path": file_path, "content": text}
        elif tool == "Edit":
            ti = {"file_path": file_path, "old_string": "x", "new_string": text}
        else:
            ti = {"file_path": file_path, "edits": [{"old_string": "x",
                                                     "new_string": text}]}
        return {"hook_event_name": "PreToolUse", "tool_name": tool,
                "tool_input": ti, "cwd": self.root}

    def bash_payload(self, command):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command}, "cwd": self.root}

    def stamp(self, results):
        r = run_cli("gate_stamp.py", ["--results", json.dumps(results)],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestGuardFrozen(Base):
    def test_always_list_env_block(self):
        self.set_task({"type": "hotfix"})
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Write", ".env", "SECRET=1"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("frozen", r.stderr.lower())

    def test_lockfile_block(self):
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Write", "package-lock.json", "{}"),
                     self.root)
        self.assertEqual(r.returncode, 2)

    def test_env_example_allowed(self):
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Write", ".env.example", "SECRET="),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_declared_surface_block_with_reason(self):
        self.write("company/frozen-surfaces.json", json.dumps({
            "version": 1,
            "surfaces": [{"pattern": "src/core/transitions.*",
                          "why": "single writer of state", "change_via": "CR"}],
            "always": [],
        }))
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Edit", "src/core/transitions.py", "x"),
                     self.root)
        self.assertEqual(r.returncode, 2)
        self.assertIn("single writer of state", r.stderr)

    def test_normal_source_allowed(self):
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Write", "src/util.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_tracked_migration_blocked(self):
        self.init_git()
        self.write("migrations/0001_init.py", "old")
        git(self.root, "add", "migrations/0001_init.py")
        git(self.root, "commit", "-m", "add migration")
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Edit", "migrations/0001_init.py", "new"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("migration", r.stderr.lower())

    def test_untracked_migration_allowed(self):
        self.init_git()
        path = "alembic/versions/0002_new.py"
        self.write(path, "fresh")
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Edit", path, "more"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fail_open_garbage(self):
        r = run_hook("guard_frozen.py", None, self.root, raw_stdin="not json{")
        self.assertEqual(r.returncode, 0)


class TestGuardSpec(Base):
    def test_no_brief_blocks_source(self):
        r = run_hook("guard_spec.py",
                     self.edit_payload("Write", "src/app.py", "print(1)"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("brief", r.stderr.lower())

    def test_valid_brief_allows(self):
        self.write("company/briefs/brief-x.md", "# brief")
        self.set_task({"task": "x", "type": "feature",
                       "brief": "company/briefs/brief-x.md"})
        r = run_hook("guard_spec.py",
                     self.edit_payload("Write", "src/app.py", "print(1)"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_brief_file_blocks(self):
        self.set_task({"task": "x", "type": "feature",
                       "brief": "company/briefs/nope.md"})
        r = run_hook("guard_spec.py",
                     self.edit_payload("Write", "src/app.py", "x"), self.root)
        self.assertEqual(r.returncode, 2)

    def test_hotfix_bypass(self):
        self.set_task({"task": "hf", "type": "hotfix"})
        r = run_hook("guard_spec.py",
                     self.edit_payload("Write", "src/app.py", "x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = os.path.join(self.root, "company", "state", "adherence.log")
        self.assertIn("BYPASS", open(log).read())

    def test_non_source_allowed_without_brief(self):
        for path in ["README.md", "docs/guide.py", "config.yaml",
                     ".gitignore", "company/notes.py"]:
            r = run_hook("guard_spec.py",
                         self.edit_payload("Write", path, "x"), self.root)
            self.assertEqual(r.returncode, 0, "%s: %s" % (path, r.stderr))


class TestGuardTests(Base):
    def test_edit_test_blocked_without_scope(self):
        self.set_task({"task": "x", "type": "feature", "test_scope": False})
        r = run_hook("guard_tests.py",
                     self.edit_payload("Write", "tests/test_x.py", "x"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("oracle", r.stderr.lower())

    def test_edit_test_allowed_with_scope(self):
        self.set_task({"task": "x", "type": "feature", "test_scope": True})
        r = run_hook("guard_tests.py",
                     self.edit_payload("Write", "tests/test_x.py", "x"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_file_variants_blocked(self):
        self.set_task({"task": "x", "type": "feature"})
        for path in ["src/foo.test.ts", "pkg/foo_test.go",
                     "e2e/flow.spec.js"]:
            r = run_hook("guard_tests.py",
                         self.edit_payload("Write", path, "x"), self.root)
            self.assertEqual(r.returncode, 2, "%s allowed" % path)

    def test_non_test_source_allowed(self):
        r = run_hook("guard_tests.py",
                     self.edit_payload("Write", "src/app.py", "x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bash_rm_test_blocked(self):
        self.set_task({"task": "x", "type": "feature"})
        r = run_hook("guard_tests.py",
                     self.bash_payload("rm tests/test_x.py"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_bash_rm_test_allowed_with_scope(self):
        self.set_task({"task": "x", "type": "feature", "test_scope": True})
        r = run_hook("guard_tests.py",
                     self.bash_payload("rm tests/test_x.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bash_rm_nontest_allowed(self):
        r = run_hook("guard_tests.py",
                     self.bash_payload("rm src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fail_open_garbage(self):
        r = run_hook("guard_tests.py", None, self.root, raw_stdin="}{")
        self.assertEqual(r.returncode, 0)


class TestNoSlop(Base):
    def test_em_dash_blocked(self):
        text = "This is great — really great."
        r = run_hook("no_slop.py",
                     self.edit_payload("Write", "docs/x.md", text), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_phrase_blocked(self):
        r = run_hook("no_slop.py",
                     self.edit_payload("Write", "docs/x.md",
                                       "This is a paradigm shift for us."),
                     self.root)
        self.assertEqual(r.returncode, 2)

    def test_clean_allowed(self):
        r = run_hook("no_slop.py",
                     self.edit_payload("Write", "src/app.py",
                                       "x = 1  # plain ascii only"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_state_path_skipped(self):
        text = "log line — with em dash"
        r = run_hook("no_slop.py",
                     self.edit_payload("Write",
                                       "company/state/adherence.log", text),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fail_open_garbage(self):
        r = run_hook("no_slop.py", None, self.root, raw_stdin="nope")
        self.assertEqual(r.returncode, 0)


class TestGateStampAndCommit(Base):
    def configure_gates(self):
        self.write("company/gates.config", json.dumps(
            {"gates": [{"name": "tests"}]}))

    def test_stamp_green_check_passes(self):
        self.init_git()
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        r = run_cli("gate_stamp.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_stamp_red_check_fails(self):
        self.init_git()
        self.stamp({"gates": [{"name": "tests", "ok": False}]})
        r = run_cli("gate_stamp.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 1)

    def test_stale_stamp_detected(self):
        self.init_git()
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        # mutate the working tree after stamping -> work hash changes
        self.write("newfile.py", "print(1)")
        git(self.root, "add", "newfile.py")
        r = run_cli("gate_stamp.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale", r.stdout.lower())

    def test_commit_blocked_when_no_stamp(self):
        self.init_git()
        self.configure_gates()
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m wip"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_commit_allowed_when_green(self):
        self.init_git()
        self.configure_gates()
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m done"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commit_bypass_no_gates_config(self):
        self.init_git()
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = os.path.join(self.root, "company", "state", "adherence.log")
        self.assertIn("BYPASS", open(log).read())

    def test_commit_bypass_hotfix(self):
        self.init_git()
        self.configure_gates()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_push_to_main_blocked(self):
        self.init_git()
        r = run_hook("guard_commit.py",
                     self.bash_payload("git push origin main"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("protected", r.stderr.lower())

    def test_push_to_feature_allowed(self):
        self.init_git()
        r = run_hook("guard_commit.py",
                     self.bash_payload("git push origin feature/x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_checksum_tamper_detected(self):
        self.init_git()
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        path = os.path.join(self.root, "company", "state", "gates.status")
        data = json.load(open(path))
        data["status"] = "green"
        data["gates"] = [{"name": "tests", "ok": True, "detail": "forged"}]
        json.dump(data, open(path, "w"))
        r = run_cli("gate_stamp.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("checksum", r.stdout.lower())


class TestStopGate(Base):
    def test_loop_protection(self):
        self.set_task({"task": "x", "type": "feature"})
        payload = {"hook_event_name": "Stop", "stop_hook_active": True,
                   "cwd": self.root}
        r = run_hook("stop_gate.py", payload, self.root)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_blocks_on_stale_gates(self):
        self.init_git()
        self.set_task({"task": "feat-x", "type": "feature"})
        payload = {"hook_event_name": "Stop", "stop_hook_active": False,
                   "cwd": self.root}
        r = run_hook("stop_gate.py", payload, self.root)
        self.assertEqual(r.returncode, 0)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("feat-x", decision["reason"])

    def test_quick_task_not_blocked(self):
        self.set_task({"task": "q", "type": "quick"})
        payload = {"hook_event_name": "Stop", "stop_hook_active": False,
                   "cwd": self.root}
        r = run_hook("stop_gate.py", payload, self.root)
        self.assertEqual(r.stdout.strip(), "")

    def test_green_gates_not_blocked(self):
        self.init_git()
        self.set_task({"task": "x", "type": "feature"})
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        payload = {"hook_event_name": "Stop", "stop_hook_active": False,
                   "cwd": self.root}
        r = run_hook("stop_gate.py", payload, self.root)
        self.assertEqual(r.stdout.strip(), "")


class TestSessionStart(Base):
    def test_digest_emitted(self):
        self.write("company/state/RESUME.md", "resume line one\nline two")
        self.write("company/state/STATUS.md", "status here")
        self.set_task({"task": "x", "type": "feature",
                       "brief": "company/briefs/b.md"})
        payload = {"hook_event_name": "SessionStart", "cwd": self.root}
        r = run_hook("session_start.py", payload, self.root)
        self.assertEqual(r.returncode, 0)
        self.assertIn("state digest", r.stdout)
        self.assertIn("resume line one", r.stdout)
        self.assertIn("active-task", r.stdout)

    def test_silent_when_no_state(self):
        payload = {"hook_event_name": "SessionStart", "cwd": self.root}
        r = run_hook("session_start.py", payload, self.root)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
