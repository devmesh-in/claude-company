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


class TestGuardModels(Base):
    MANIFEST = {"version": 1, "roles": {"developer": "opus",
                                        "architect": "opus"}}

    def write_manifest(self, obj=None):
        self.write("company/models.json",
                   json.dumps(obj if obj is not None else self.MANIFEST))

    def spawn_payload(self, tool="Task", **fields):
        return {"hook_event_name": "PreToolUse", "tool_name": tool,
                "tool_input": dict(fields), "cwd": self.root}

    def write_agent(self, role, model):
        self.write(".claude/agents/%s.md" % role,
                   "---\nname: %s\nmodel: %s\n---\nbody\n" % (role, model))

    # --- mode a: spawn override -------------------------------------------
    def test_spawn_override_conflict_blocked(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.spawn_payload(subagent_type="developer",
                                        model="haiku"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("developer", r.stderr)
        self.assertIn("haiku", r.stderr)
        self.assertIn("opus", r.stderr)

    def test_spawn_override_matching_allowed(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.spawn_payload(subagent_type="developer",
                                        model="opus"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spawn_no_override_allowed(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.spawn_payload(subagent_type="developer"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spawn_unknown_type_allowed(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.spawn_payload(subagent_type="random-helper",
                                        model="haiku"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spawn_agent_toolname_and_agent_type_field(self):
        # The Agent tool name plus the agent_type fallback field both work.
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.spawn_payload(tool="Agent", agent_type="architect",
                                        model="sonnet"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_spawn_hotfix_bypass_logs(self):
        self.write_manifest()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = run_hook("guard_models.py",
                     self.spawn_payload(subagent_type="developer",
                                        model="haiku"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = os.path.join(self.root, "company", "state", "adherence.log")
        self.assertIn("BYPASS", open(log).read())

    # --- mode b: frontmatter edit -----------------------------------------
    def test_frontmatter_conflict_blocked(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.edit_payload("Write", ".claude/agents/developer.md",
                                       "---\nname: developer\nmodel: haiku\n"
                                       "---\nbody\n"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("models.json", r.stderr)

    def test_frontmatter_unchanged_allowed(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.edit_payload("Write", ".claude/agents/developer.md",
                                       "---\nname: developer\nmodel: opus\n"
                                       "---\nbody\n"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_frontmatter_non_model_edit_allowed(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.edit_payload("Edit", ".claude/agents/developer.md",
                                       "some prose with no model line"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_frontmatter_role_not_in_manifest_allowed(self):
        self.write_manifest()
        r = run_hook("guard_models.py",
                     self.edit_payload("Write", ".claude/agents/mascot.md",
                                       "---\nmodel: haiku\n---\n"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_frontmatter_unblocks_after_manifest_change(self):
        # Editing models.json first legitimately unblocks the frontmatter edit.
        self.write_manifest({"version": 1, "roles": {"developer": "sonnet"}})
        r = run_hook("guard_models.py",
                     self.edit_payload("Write", ".claude/agents/developer.md",
                                       "---\nmodel: sonnet\n---\n"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_manifest_missing_fail_open(self):
        r = run_hook("guard_models.py",
                     self.spawn_payload(subagent_type="developer",
                                        model="haiku"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fail_open_garbage(self):
        self.write_manifest()
        r = run_hook("guard_models.py", None, self.root, raw_stdin="}{ nope")
        self.assertEqual(r.returncode, 0)

    # --- mode c: --check CLI ----------------------------------------------
    def test_check_agreement_exits_zero(self):
        self.write_manifest()
        self.write_agent("developer", "opus")
        self.write_agent("architect", "opus")
        r = run_cli("guard_models.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_mismatch_exits_one(self):
        self.write_manifest()
        self.write_agent("developer", "haiku")
        self.write_agent("architect", "opus")
        r = run_cli("guard_models.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("developer", r.stdout)

    def test_check_missing_declaration_exits_one(self):
        self.write_manifest()
        # architect present, developer file has no model line
        self.write(".claude/agents/developer.md", "---\nname: developer\n---\n")
        self.write_agent("architect", "opus")
        r = run_cli("guard_models.py", ["--check"], self.root)
        self.assertEqual(r.returncode, 1, r.stdout)


class TestGateStampAndCommit(Base):
    def configure_gates(self):
        self.write("company/gates.config", json.dumps(
            {"gates": [{"name": "tests"}]}))

    def set_branch(self, name):
        # init_git lands on the git-default branch (master or main depending
        # on the host git config), so pin it explicitly for branch-rule tests.
        git(self.root, "checkout", "-B", name)

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

    def test_commit_bypass_placeholder_only_gates(self):
        # A fresh project: gates.config exists but holds only CONFIGURE-ME
        # placeholders. Founding commits must flow (logged BYPASS), not
        # deadlock behind gates that cannot be green yet.
        self.init_git()
        self.write("company/gates.config", json.dumps({"gates": [
            {"name": "tests", "command": "echo 'CONFIGURE ME' && exit 1",
             "blocking": True},
            {"name": "lint", "command": "echo 'CONFIGURE ME' && exit 1",
             "blocking": True},
        ]}))
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m founding"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = os.path.join(self.root, "company", "state", "adherence.log")
        self.assertIn("CONFIGURE-ME placeholders", open(log).read())

    def test_commit_enforced_once_any_real_gate_exists(self):
        # One real gate beside a leftover placeholder: enforcement snaps on.
        self.init_git()
        self.write("company/gates.config", json.dumps({"gates": [
            {"name": "tests", "command": "true", "blocking": True},
            {"name": "lint", "command": "echo 'CONFIGURE ME' && exit 1",
             "blocking": True},
        ]}))
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m wip"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_commit_bypass_hotfix(self):
        self.init_git()
        self.configure_gates()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    # --- all-work-on-task-branches rule ----------------------------------
    def test_commit_on_main_with_task_blocked(self):
        self.init_git()
        self.set_branch("main")
        self.configure_gates()
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        self.set_task({"task": "feat-x", "type": "feature"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m wip"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        # message names the task slug and the task/ branch recipe
        self.assertIn("feat-x", r.stderr)
        self.assertIn("task/feat-x", r.stderr)
        self.assertIn("git worktree add", r.stderr)

    def test_commit_on_main_no_task_allowed_founding(self):
        # No active task: founding commit path, exempt from the branch rule.
        self.init_git()
        self.set_branch("main")
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m founding"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commit_on_task_branch_with_task_allowed(self):
        # On a task branch the branch rule is silent; green stamp isolates it.
        self.init_git()
        self.configure_gates()
        self.set_branch("task/feat-x")
        self.set_task({"task": "feat-x", "type": "feature"})
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m done"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commit_on_main_hotfix_allowed_bypass_logged(self):
        self.init_git()
        self.set_branch("main")
        self.configure_gates()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = os.path.join(self.root, "company", "state", "adherence.log")
        contents = open(log).read()
        self.assertIn("BYPASS", contents)
        self.assertIn("hotfix commit on protected branch", contents)

    def test_merge_on_main_with_task_not_blocked_by_branch_rule(self):
        # merge is the owner's local integration; the branch rule ignores it.
        # Green stamp isolates the branch rule from the gate-stamp check.
        self.init_git()
        self.set_branch("main")
        self.configure_gates()
        self.set_task({"task": "feat-x", "type": "feature"})
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git merge task/feat-x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commit_detached_head_fails_open(self):
        # Detached HEAD -> current_branch is unknown -> branch rule allows.
        # Green stamp isolates it from the gate-stamp check.
        self.init_git()
        self.configure_gates()
        self.set_task({"task": "feat-x", "type": "feature"})
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        head = git(self.root, "rev-parse", "HEAD").stdout.strip()
        git(self.root, "checkout", head)
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m wip"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commit_no_git_fails_open(self):
        # No git repo at all -> branch unknown -> branch rule allows.
        self.set_task({"task": "feat-x", "type": "feature"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m wip"), self.root)
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


class TestGatesDetect(Base):
    """gates_detect.py CLI. Tool presence is environment-dependent, so
    assertions target what is deterministic: parsed output JSON, the
    placeholder-replacement rule, the preserve-real-config rule, and the
    no-stack case. python3 is assumed present (the hooks require it)."""

    def detect_json(self, args):
        r = run_cli("gates_detect.py", args, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        line = None
        for ln in r.stdout.splitlines():
            if ln.startswith("GATES_JSON: "):
                line = ln[len("GATES_JSON: "):]
        self.assertIsNotNone(line, "no GATES_JSON line in:\n" + r.stdout)
        return json.loads(line), r

    def config_path(self):
        return os.path.join(self.root, "company", "gates.config")

    def test_node_project_detected(self):
        self.write("package.json", json.dumps(
            {"scripts": {"test": "jest", "lint": "eslint ."},
             "devDependencies": {"typescript": "^5"}}))
        obj, _ = self.detect_json([])
        self.assertIn("package.json", obj["stacks"])
        self.assertEqual(obj["package_manager"], "npm")
        # tests + lint + typecheck appear across proposed and/or skipped.
        names = {g["name"] for g in obj["proposed"]}
        names |= {g["name"] for g in obj["skipped"]}
        self.assertIn("tests", names)
        self.assertIn("lint", names)
        self.assertIn("typecheck", names)
        # skipped entries carry the missing-tool reason.
        for g in obj["skipped"]:
            self.assertEqual(g["reason"], "detected_but_missing_tool")

    def test_pnpm_lockfile_picks_pnpm(self):
        self.write("pnpm-lock.yaml", "")
        self.write("package.json", json.dumps({"scripts": {"test": "vitest"}}))
        obj, _ = self.detect_json([])
        self.assertEqual(obj["package_manager"], "pnpm")

    def test_python_pytest_proposed(self):
        self.write("pyproject.toml", "[tool.ruff]\n[tool.mypy]\n")
        obj, _ = self.detect_json([])
        self.assertIn("python", obj["stacks"])
        cmds = {g["command"] for g in obj["proposed"]}
        # python3 is invocable, so the pytest gate is always proposed.
        self.assertIn("python3 -m pytest", cmds)

    def test_write_replaces_placeholder_config(self):
        self.write("pyproject.toml", "[project]\nname = 'x'\n")
        self.write("company/gates.config", json.dumps({"gates": [
            {"name": "tests",
             "command": "echo 'CONFIGURE ME' && exit 1", "blocking": True}]}))
        obj, _ = self.detect_json(["--write"])
        self.assertEqual(obj["status"], "wrote")
        self.assertTrue(obj["wrote"])
        cfg = json.load(open(self.config_path()))
        commands = [g["command"] for g in cfg["gates"]]
        self.assertIn("python3 -m pytest", commands)
        for cmd in commands:
            self.assertNotIn("CONFIGURE ME", cmd)

    def test_write_preserves_real_config(self):
        self.write("pyproject.toml", "[project]\nname = 'x'\n")
        real = {"gates": [{"name": "tests",
                           "command": "pytest -q", "blocking": True}]}
        self.write("company/gates.config", json.dumps(real))
        obj, _ = self.detect_json(["--write"])
        self.assertEqual(obj["status"], "preserved_existing")
        self.assertFalse(obj["wrote"])
        cfg = json.load(open(self.config_path()))
        self.assertEqual(cfg["gates"][0]["command"], "pytest -q")

    def test_no_stack_leaves_config_untouched(self):
        obj, r = self.detect_json(["--write"])
        self.assertEqual(obj["status"], "no_stack")
        self.assertFalse(obj["wrote"])
        self.assertIn("no stack detected", r.stdout)
        self.assertFalse(os.path.exists(self.config_path()))

    def test_gates_ordered_cheap_to_expensive(self):
        # A Makefile with lint + test targets: both use `make`, always present
        # is not guaranteed, so assert ordering only when both are proposed.
        self.write("Makefile", "lint:\n\techo l\ntest:\n\techo t\n")
        obj, _ = self.detect_json([])
        names = [g["name"] for g in obj["proposed"]]
        if "lint" in names and "tests" in names:
            self.assertLess(names.index("lint"), names.index("tests"))

    def test_models_gate_proposed_for_node(self):
        # The stack-independent models gate rides in every proposal and is
        # ordered before the test gate.
        self.write("package.json", json.dumps({"scripts": {"test": "jest"}}))
        obj, _ = self.detect_json([])
        names = [g["name"] for g in obj["proposed"]]
        self.assertIn("models", names)
        cmds = {g["command"] for g in obj["proposed"]}
        self.assertIn("python3 .claude/hooks/guard_models.py --check", cmds)
        if "tests" in names:
            self.assertLess(names.index("models"), names.index("tests"))

    def test_models_gate_proposed_for_no_stack(self):
        # No language stack: config stays untouched, but the models gate is
        # still surfaced in the proposal.
        obj, r = self.detect_json(["--write"])
        self.assertEqual(obj["status"], "no_stack")
        self.assertFalse(obj["wrote"])
        names = [g["name"] for g in obj["proposed"]]
        self.assertIn("models", names)
        self.assertFalse(os.path.exists(self.config_path()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
