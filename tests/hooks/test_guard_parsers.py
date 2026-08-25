#!/usr/bin/env python3
"""Tests for the git command parsers in guard_commit.py and guard_secrets.py.

Two layers, both needed:

  - in-process unit tests over `guard_commit.git_subcmd`,
    `guard_commit.seg_git_dir`, `guard_commit.branch_recipe` and
    `guard_secrets.has_commit` (fast, exact-value assertions), and
  - subprocess end-to-end tests reusing the harness idiom from
    test_guard_secrets.py: a throwaway fixture project with a real `git init`
    (and a real `git worktree add` where the branch rule is under test),
    CLAUDE_PROJECT_DIR pointed at it, a synthetic Bash payload on stdin, and
    assertions on exit code / stderr.

FR-HP-10: a global option carrying a SEPARATED argument (`git -C sub commit`)
used to leave its argument to be read as the subcommand, so the whole segment
was invisible to every Bash-gated check.
FR-HP-11: seeing those segments means judging them by the right directory.
FR-HP-12: guard_secrets delegates to guard_commit instead of duplicating.
FR-HP-17: the block message names the compound-command behavior.

Positive secret fixtures stage FAKE values in a NON-test path - the scanner
deliberately skips `tests/` and `fixtures/` path segments.

Run: python3 -m unittest tests.hooks.test_guard_parsers
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
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

import _common  # noqa: E402
import guard_commit  # noqa: E402
import guard_secrets  # noqa: E402


def hook_path(name):
    return os.path.join(HOOKS_DIR, name)


def run_hook(hook, payload, root, raw_stdin=None):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, hook_path(hook)],
        input=stdin,
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


BRANCH_MSG = "work belongs on a task branch"
STAMP_MSG = "requires green, fresh gates"
PUSH_MSG = "push to a protected branch"

# A realistic-but-FAKE AWS key, no secret-ok: marker.
FAKE_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


class Base(unittest.TestCase):
    """A throwaway project with a real git repo pinned to `main`."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-parsers-")
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

    def init_git(self):
        git(self.root, "init")
        # Local identity: the fixture must commit on machines with no global
        # git config.
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        git(self.root, "commit", "--allow-empty", "-m", "init")
        # init lands on the host git default branch (main or master), so pin
        # it explicitly - the branch rule is what is under test.
        git(self.root, "checkout", "-B", "main")

    def add_worktree(self, rel, branch):
        """Real `git worktree add <rel> -b <branch>`; returns its abs path."""
        path = os.path.join(self.root, rel)
        r = git(self.root, "worktree", "add", path, "-b", branch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        self.addCleanup(lambda: git(self.root, "worktree", "prune"))
        return path

    def configure_gates(self, tree=None):
        """One REAL gate, so the gate-stamp check is armed (not bypassed).

        `tree` defaults to the project root. Pass a worktree when the segment
        under test acts on one: the commit gate reads gates.config and
        gates.status from the ACTING tree, so a config that exists only in the
        main checkout leaves a worktree segment unarmed.
        """
        tree = tree or self.root
        path = os.path.join(tree, "company", "gates.config")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(json.dumps(
                {"gates": [{"name": "tests", "command": "true",
                            "blocking": True}]}))

    def stamp(self, tree=None):
        """A green, fresh gates.status for `tree`, via the real gate_stamp CLI.

        Stamp LAST for a given tree: the work hash covers that tree's
        untracked files, so anything written afterwards stales it.
        """
        tree = tree or self.root
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = tree
        r = subprocess.run(
            [sys.executable, hook_path("gate_stamp.py"), "--results",
             json.dumps({"gates": [{"name": "tests", "ok": True}]})],
            capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def set_tasks(self, *entries):
        self.write("company/state/active-task.json",
                   json.dumps({"version": 2, "tasks": list(entries)}))

    def payload(self, command, cwd=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command},
                "cwd": cwd if cwd is not None else self.root}

    def commit_guard(self, command, cwd=None):
        return run_hook("guard_commit.py", self.payload(command, cwd),
                        self.root)

    def secrets_guard(self, command, cwd=None):
        return run_hook("guard_secrets.py", self.payload(command, cwd),
                        self.root)

    def stage(self, rel, content):
        self.write(rel, content)
        r = git(self.root, "add", rel)
        self.assertEqual(r.returncode, 0, r.stderr)

    def adherence(self):
        path = os.path.join(self.root, "company", "state", "adherence.log")
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()


# --- FR-HP-10: git_subcmd consumes separated-argument globals --------------
class TestGitSubcmd(unittest.TestCase):
    """Exact-value ACs for guard_commit.git_subcmd."""

    def test_dash_c_path_before_commit(self):
        self.assertEqual(guard_commit.git_subcmd("git -C sub commit -m x"),
                         ("commit", ["-m", "x"]))

    def test_lowercase_c_config_before_commit(self):
        self.assertEqual(guard_commit.git_subcmd("git -c user.name=x commit"),
                         ("commit", []))

    def test_dash_c_path_before_push(self):
        self.assertEqual(guard_commit.git_subcmd("git -C x push origin main"),
                         ("push", ["origin", "main"]))

    def test_attached_git_dir_consumes_one_token(self):
        self.assertEqual(guard_commit.git_subcmd("git --git-dir=/tmp/g commit"),
                         ("commit", []))

    def test_attached_dash_c_consumes_one_token(self):
        self.assertEqual(guard_commit.git_subcmd("git -Cdir commit"),
                         ("commit", []))

    def test_dash_c_with_no_subcommand(self):
        self.assertEqual(guard_commit.git_subcmd("git -C x"), (None, []))

    def test_dash_c_after_subcommand_is_reuse_message(self):
        # `git commit -C HEAD~1` is --reuse-message: HEAD~1 is a commit ref,
        # not a path, and only tokens BEFORE the subcommand may be scanned.
        self.assertEqual(guard_commit.git_subcmd("git commit -C HEAD~1"),
                         ("commit", ["-C", "HEAD~1"]))

    def test_plain_commit_unchanged(self):
        self.assertEqual(guard_commit.git_subcmd("git commit -m x"),
                         ("commit", ["-m", "x"]))

    def test_non_git_command_unchanged(self):
        self.assertEqual(guard_commit.git_subcmd("npm test"), (None, []))

    def test_switch_dash_c_is_not_a_global(self):
        # `git switch -c task/x`: the -c sits AFTER the subcommand, so the
        # option loop must never reach it.
        self.assertEqual(guard_commit.git_subcmd("git switch -c task/x"),
                         ("switch", ["-c", "task/x"]))

    def test_work_tree_separated_argument(self):
        self.assertEqual(
            guard_commit.git_subcmd("git --work-tree /tmp/w commit -m x"),
            ("commit", ["-m", "x"]))


# --- FR-HP-11: -C-aware branch resolution ---------------------------------
class TestSegGitDirUnit(Base):
    """Direct unit coverage for the segment -> judged-directory function."""

    def test_last_dash_c_wins(self):
        first = self.add_worktree(".claude/worktrees/a", "task/a")
        second = self.add_worktree(".claude/worktrees/b", "task/b")
        self.assertTrue(os.path.isdir(first))
        seg = "git -C .claude/worktrees/a -C .claude/worktrees/b commit -m y"
        got = guard_commit.seg_git_dir(seg, self.payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(second))

    def test_attached_dash_c_resolves(self):
        wt = self.add_worktree(".claude/worktrees/x", "task/x")
        seg = "git -C.claude/worktrees/x commit -m y"
        got = guard_commit.seg_git_dir(seg, self.payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(wt))

    def test_absolute_dash_c_resolves(self):
        wt = self.add_worktree(".claude/worktrees/x", "task/x")
        seg = "git -C {} commit -m y".format(wt)
        got = guard_commit.seg_git_dir(seg, self.payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(wt))

    def test_unresolvable_path_falls_back_to_payload_cwd(self):
        seg = "git -C /nonexistent/path commit -m y"
        got = guard_commit.seg_git_dir(seg, self.payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))

    def test_no_dash_c_falls_back_to_payload_cwd(self):
        wt = self.add_worktree(".claude/worktrees/x", "task/x")
        seg = "git commit -m y"
        got = guard_commit.seg_git_dir(seg, self.payload(seg, cwd=wt),
                                       self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(wt))

    def test_dash_c_after_subcommand_is_not_a_path(self):
        # `git commit -C HEAD~1`: HEAD~1 must never be treated as a directory.
        seg = "git commit -C HEAD~1"
        got = guard_commit.seg_git_dir(seg, self.payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))

    def test_path_outside_any_repo_falls_back(self):
        # A real directory that is not inside a work tree: rev-parse fails, so
        # the candidate is refused and the payload cwd decides.
        plain = tempfile.mkdtemp(prefix="cc-parsers-plain-")
        self.addCleanup(shutil.rmtree, plain, ignore_errors=True)
        seg = "git -C {} commit -m y".format(plain)
        got = guard_commit.seg_git_dir(seg, self.payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))


class TestSegGitDirEndToEnd(Base):
    def test_worktree_commit_not_blocked_by_branch_rule(self):
        # Main checkout on main, worktree on task/x, one non-hotfix entry.
        # The commit lands on task/x, so the protected-branch message must NOT
        # appear. Commits are not stamp-gated (DECISIONS #25), so the segment
        # is allowed. The proof it is no longer invisible is the ABSENCE of
        # the branch string, not a stamp block.
        wt = self.add_worktree(".claude/worktrees/x", "task/x")
        self.configure_gates(wt)
        self.set_tasks({"task": "x", "type": "feature"})
        r = self.commit_guard("git -C .claude/worktrees/x commit -m y")
        self.assertNotIn(BRANCH_MSG, r.stderr)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bare_commit_on_main_still_blocked(self):
        # The unchanged-behavior guard for FR-HP-11.
        self.configure_gates()
        self.set_tasks({"task": "x", "type": "feature"})
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(BRANCH_MSG, r.stderr)

    def test_unresolvable_dash_c_commit_still_blocked(self):
        # Unresolvable -C falls back to the payload cwd (the main checkout on
        # main), so the branch rule still fires.
        self.configure_gates()
        self.set_tasks({"task": "x", "type": "feature"})
        r = self.commit_guard("git -C /nonexistent/path commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(BRANCH_MSG, r.stderr)

    def test_dash_c_push_to_main_blocked(self):
        r = self.commit_guard("git -C x push origin main")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(PUSH_MSG, r.stderr)

    def test_per_segment_dirs_do_not_leak(self):
        # A -C in one segment must not decide the NEXT segment: the worktree
        # commit passes (task/x, its OWN green stamp), and the bare commit
        # that follows is still judged on main and blocks.
        # Each tree carries its own config and its own stamp, which is what
        # the gate reads. The two hash independently - writing into the
        # worktree does not stale the root's stamp - so the order below only
        # has to keep each tree's stamp last within that tree.
        wt = self.add_worktree(".claude/worktrees/x", "task/x")
        self.configure_gates()
        self.configure_gates(wt)
        self.set_tasks({"task": "x", "type": "feature"})
        self.stamp(wt)
        self.stamp()  # last, so root's work hash matches at hook time
        r = self.commit_guard(
            "git -C .claude/worktrees/x commit -m y && git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(BRANCH_MSG, r.stderr)

    def test_later_dash_c_segment_judged_by_its_own_tree(self):
        # The other direction, and the guard against landing FR-HP-10 without
        # FR-HP-11: a hoisted single branch_dir would judge segment 2 by the
        # main checkout (on main) and falsely block a push that targets the
        # worktree's task branch.
        self.add_worktree(".claude/worktrees/x", "task/x")
        r = self.commit_guard(
            "git push origin task/x && git -C .claude/worktrees/x push")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- one implementation: guard_commit re-exports _common's parsers --------
class TestParserAliases(unittest.TestCase):
    """The parsers live in _common. guard_commit keeps the public NAMES.

    guard_secrets and guard_provenance both reach these through guard_commit,
    and the monkeypatch test below depends on the name resolving on this
    module at call time. Deleting an alias as dead code breaks callers in
    other files, so the aliases are pinned here.
    """

    ALIASES = ("ARG_OPTS", "segments", "git_subcmd", "git_cwd", "seg_git_dir")

    def test_aliases_are_the_common_implementations(self):
        for name in self.ALIASES:
            self.assertIs(getattr(guard_commit, name),
                          getattr(_common, name),
                          "guard_commit.{} is not _common.{}".format(
                              name, name))

    def test_guard_commit_defines_no_second_parser(self):
        with open(hook_path("guard_commit.py")) as f:
            source = f.read()
        # assertFalse, not assertNotIn: the failure message must not dump the
        # whole hook source into the run output.
        for name in ("segments", "git_subcmd", "git_cwd", "seg_git_dir"):
            self.assertFalse(
                "def {}(".format(name) in source,
                "guard_commit re-defines {} instead of aliasing".format(name))


# --- FR-HP-12: guard_secrets delegates instead of duplicating -------------
class TestSecretsDelegation(unittest.TestCase):
    def test_no_second_option_skip_loop_in_source(self):
        with open(hook_path("guard_secrets.py")) as f:
            source = f.read()
        # assertFalse, not assertNotIn: the failure message must not dump the
        # whole hook source into the run output.
        self.assertFalse("def git_subcmd" in source,
                         "guard_secrets still defines its own git_subcmd")
        self.assertTrue("guard_commit.git_subcmd" in source,
                        "guard_secrets does not delegate to guard_commit")
        self.assertFalse(hasattr(guard_secrets, "git_subcmd"))

    def test_has_commit_follows_monkeypatched_parser(self):
        # Attribute lookup at call time: patching guard_commit changes what
        # guard_secrets sees. A duplicated copy would ignore the patch.
        original = guard_commit.git_subcmd
        try:
            guard_commit.git_subcmd = lambda seg: (None, [])
            self.assertFalse(guard_secrets.has_commit("git commit -m x"))
            guard_commit.git_subcmd = lambda seg: ("commit", [])
            self.assertTrue(guard_secrets.has_commit("echo hi"))
        finally:
            guard_commit.git_subcmd = original
        self.assertTrue(guard_secrets.has_commit("git commit -m x"))

    def test_has_commit_sees_dash_c_commit(self):
        self.assertTrue(guard_secrets.has_commit("git -C sub commit -m x"))

    def test_has_commit_ignores_non_commit(self):
        self.assertFalse(guard_secrets.has_commit("git -C sub status"))


class TestSecretsEndToEnd(Base):
    def test_dash_c_commit_is_scanned_and_blocked(self):
        # FAKE key, NON-test path (tests/ and fixtures/ are skipped).
        self.stage("src/config.py", "key = " + FAKE_AWS_KEY + "\n")
        r = self.secrets_guard("git -C sub commit -m x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)
        self.assertIn("src/config.py", r.stderr)

    def test_plain_commit_still_blocked(self):
        self.stage("src/config.py", "key = " + FAKE_AWS_KEY + "\n")
        r = self.secrets_guard("git commit -m x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_hotfix_still_does_not_bypass_dash_c_commit(self):
        # The secrets guard never yields: hotfix mode does not reach it.
        self.set_tasks({"task": "hf", "type": "hotfix"})
        self.stage("src/config.py", "key = " + FAKE_AWS_KEY + "\n")
        r = self.secrets_guard("git -C sub commit -m x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_non_commit_dash_c_command_allowed(self):
        self.stage("src/config.py", "key = " + FAKE_AWS_KEY + "\n")
        r = self.secrets_guard("git -C sub status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- FR-HP-17: block-message ergonomics -----------------------------------
COMPOUND_SENTENCE = "run the switch as its OWN command first"
COMPOUND_EXAMPLE = "switch -c task/x && git commit"


class TestBranchRecipeMessage(unittest.TestCase):
    def test_one_entry_names_compound_behavior(self):
        msg = guard_commit.branch_recipe([{"task": "x", "type": "feature"}])
        self.assertIn(COMPOUND_SENTENCE, msg)
        self.assertIn(COMPOUND_EXAMPLE, msg)

    def test_three_entries_name_compound_behavior(self):
        entries = [{"task": "a"}, {"task": "b"}, {"task": "c"}]
        msg = guard_commit.branch_recipe(entries)
        self.assertIn(COMPOUND_SENTENCE, msg)
        self.assertIn(COMPOUND_EXAMPLE, msg)

    def test_sentence_lives_in_the_shared_tail(self):
        self.assertIn(COMPOUND_SENTENCE, guard_commit.BRANCH_TAIL)


class TestCompoundSwitchStillBlocks(Base):
    def test_switch_then_commit_still_blocks(self):
        # Documented, NOT changed: every segment is judged against the CURRENT
        # branch, so the switch that precedes the commit does not save it.
        self.configure_gates()
        self.set_tasks({"task": "x", "type": "feature"})
        r = self.commit_guard("git switch -c task/x && git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(BRANCH_MSG, r.stderr)
        self.assertIn(COMPOUND_SENTENCE, r.stderr)


# --- unchanged-behavior guards --------------------------------------------
class TestProtectedBranchRulesUnchanged(Base):
    def test_commit_on_main_with_active_entry_blocks(self):
        self.configure_gates()
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.commit_guard("git commit -m wip")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(BRANCH_MSG, r.stderr)
        self.assertIn("task/feat-x", r.stderr)

    def test_commit_on_main_with_hotfix_allowed_and_logged(self):
        self.configure_gates()
        self.set_tasks({"task": "hf", "type": "hotfix"})
        r = self.commit_guard("git commit -m x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.adherence()
        self.assertIn("BYPASS", log)
        self.assertIn("hotfix commit on protected branch", log)

    def test_commit_on_main_with_no_active_entry_is_founding(self):
        r = self.commit_guard("git commit -m founding")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(BRANCH_MSG, r.stderr)

    def test_bare_push_on_main_blocks(self):
        r = self.commit_guard("git push")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(PUSH_MSG, r.stderr)

    def test_push_to_feature_branch_allowed(self):
        r = self.commit_guard("git push origin feature/x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_merge_on_main_not_blocked_by_branch_rule(self):
        self.configure_gates()
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.commit_guard("git merge task/feat-x")
        self.assertNotIn(BRANCH_MSG, r.stderr)

    def test_malformed_stdin_fails_open(self):
        r = run_hook("guard_commit.py", None, self.root, raw_stdin="not json{")
        self.assertEqual(r.returncode, 0)

    def test_non_bash_tool_fails_open(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": "x", "content": "y"},
                   "cwd": self.root}
        r = run_hook("guard_commit.py", payload, self.root)
        self.assertEqual(r.returncode, 0)

    def test_unparseable_segment_fails_open(self):
        # An unbalanced quote makes shlex raise; the fallback split must keep
        # the hook from bricking the session.
        self.configure_gates()
        self.set_tasks({"task": "x", "type": "feature"})
        r = self.commit_guard("git -C 'unterminated status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
