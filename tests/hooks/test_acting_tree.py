#!/usr/bin/env python3
"""The acting-tree rule: a hook judges the tree that contains the thing acted on.

Every hook in this repo resolved the tree it judges from CLAUDE_PROJECT_DIR,
which the harness pins to the MAIN checkout, while every delegated agent works
in a linked worktree. This module holds the class-level tests for that rule
plus the P0 it produced.

THE P0. guard_secrets read its staged diff from the main checkout
(`c._git(root, ["diff", "--cached", "-U0"])`), so a commit staged inside
`.claude/worktrees/<slug>` was scanned against an index that is almost always
empty. The hook exited before scanning anything, and an inert scanner over a
clean repo is indistinguishable from a working one: zero guard_secrets lines
in 324 adherence-log entries over five weeks. Every delegated commit in this
repo's history went unscanned. TestP0WorktreeSecretIsScanned is that hole,
written to fail against the old code.

The fixtures build a REAL `git worktree add`, never a fake directory tree: a
linked worktree carries a `.git` FILE, its own index, and its own branch, and
none of those are reproducible by mkdir. A fixture that fakes the shape proves
nothing about the mechanism.

Fake secret VALUES only, staged in NON-test paths - the scanner deliberately
skips `tests/` and `fixtures/` segments.

Run: python3 -m unittest tests.hooks.test_acting_tree
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

import _common as c  # noqa: E402


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
        ["git", "-C", root] + list(args), capture_output=True, text=True
    )


# A realistic-but-FAKE AWS key. No secret-ok: marker, non-test path.
FAKE_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
SECRET_LINE = "aws = " + FAKE_AWS_KEY + "\n"


class Base(unittest.TestCase):
    """A throwaway main checkout pinned to `main`, plus real worktrees."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-acting-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)
        self.init_git()

    def init_git(self):
        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        git(self.root, "commit", "--allow-empty", "-m", "init")
        # `git init` lands on the host default branch; the branch rules under
        # test need `main` specifically.
        git(self.root, "checkout", "-B", "main")

    def write(self, rel, content, base=None):
        path = os.path.join(base or self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def add_worktree(self, rel, branch):
        """A REAL linked worktree at <root>/<rel> on <branch>. Abs path."""
        path = os.path.join(self.root, rel)
        r = git(self.root, "worktree", "add", path, "-b", branch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(lambda: git(self.root, "worktree", "prune"))
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def add_external_worktree(self, branch):
        """A real worktree OUTSIDE the project root, on no naming convention.

        `git worktree add` accepts any path, so any check that recognizes a
        worktree by the literal string `.claude/worktrees/` is a convention
        dependency, not a derivation.
        """
        parent = tempfile.mkdtemp(prefix="cc-acting-ext-")
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        path = os.path.join(parent, "elsewhere")
        r = git(self.root, "worktree", "add", path, "-b", branch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(lambda: git(self.root, "worktree", "prune"))
        return path

    def stage(self, rel, content, tree=None):
        """Stage a file in `tree` (default: the main checkout)."""
        tree = tree or self.root
        self.write(rel, content, base=tree)
        r = git(tree, "add", rel)
        self.assertEqual(r.returncode, 0, r.stderr)

    def payload(self, command, cwd=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command},
                "cwd": cwd if cwd is not None else self.root}

    def secrets_guard(self, command, cwd=None):
        return run_hook("guard_secrets.py", self.payload(command, cwd),
                        self.root)

    def set_tasks(self, *entries, **kwargs):
        base = kwargs.get("base") or self.root
        self.write("company/state/active-task.json",
                   json.dumps({"version": 2, "tasks": list(entries)}),
                   base=base)

    def adherence(self, base=None):
        path = os.path.join(base or self.root, "company", "state",
                            "adherence.log")
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()


class TestP0WorktreeSecretIsScanned(Base):
    """THE P0. A secret staged inside a real worktree must block the commit.

    Against the old code every test here exits 0: the scan ran against the
    main checkout's index, which holds nothing.
    """

    def test_secret_staged_in_worktree_blocked_via_absolute_dash_c(self):
        # The exact shape a delegated agent produces: the session cwd is the
        # main checkout, the commit is aimed at the worktree with -C.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)
        self.assertIn("src/config.py", r.stderr)

    def test_secret_staged_in_worktree_blocked_via_relative_dash_c(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard(
            "git -C .claude/worktrees/slug commit -m x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_secret_staged_in_worktree_blocked_when_cwd_is_worktree(self):
        # No -C at all: the payload cwd is the worktree.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard("git commit -m x", cwd=wt)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_secret_in_worktree_outside_project_root_blocked(self):
        # Convention-free: a worktree that lives nowhere near
        # .claude/worktrees/ is still the acting tree.
        wt = self.add_external_worktree("task/elsewhere")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_worktree_secret_blocks_even_with_clean_main_index(self):
        # Explicit statement of the mechanism: main's index is EMPTY, which is
        # exactly the state that made the old hook exit before scanning.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        main_staged = git(self.root, "diff", "--cached", "--name-only").stdout
        self.assertEqual(main_staged.strip(), "",
                         "fixture invalid: main's index must be empty")
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_hotfix_does_not_bypass_the_worktree_scan(self):
        # guard_secrets never yields to hotfix mode, and moving the tree
        # resolution must not quietly introduce a yield.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.set_tasks({"task": "hf", "type": "hotfix"})
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_block_is_logged_to_the_project_adherence_log(self):
        # The log stays in the project's state dir - one audit trail, not one
        # per worktree - which is what makes "zero guard_secrets lines in 324
        # entries" a readable signal in the first place.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("guard_secrets | BLOCK", self.adherence())


class TestP0DoesNotOverBlock(Base):
    """The other direction: the fix must not invent blocks."""

    def test_clean_worktree_commit_allowed(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/util.py", "def add(a, b):\n    return a + b\n",
                   tree=wt)
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_main_checkout_secret_still_blocked(self):
        # Unchanged behavior: the main checkout is a tree like any other.
        self.stage("src/config.py", SECRET_LINE)
        r = self.secrets_guard("git commit -m x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_secret_in_main_does_not_block_a_worktree_commit(self):
        # The mirror of the P0, and the reason resolution must be per segment:
        # a secret staged in MAIN is not in the tree this commit writes to.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE)
        r = self.secrets_guard("git -C {} commit -m x".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_non_commit_command_in_worktree_allowed(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.stage("src/config.py", SECRET_LINE, tree=wt)
        r = self.secrets_guard("git -C {} status".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_commit_segment_scans_its_own_tree(self):
        # Two commits in one compound command against two different trees:
        # the clean one must not launder the dirty one.
        clean = self.add_worktree(".claude/worktrees/clean", "task/clean")
        dirty = self.add_worktree(".claude/worktrees/dirty", "task/dirty")
        self.stage("src/util.py", "x = 1\n", tree=clean)
        self.stage("src/config.py", SECRET_LINE, tree=dirty)
        r = self.secrets_guard(
            "git -C {} commit -m a && git -C {} commit -m b".format(
                clean, dirty))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stderr)

    def test_malformed_stdin_still_fails_open(self):
        r = run_hook("guard_secrets.py", None, self.root,
                     raw_stdin="not json{")
        self.assertEqual(r.returncode, 0)


class TestScanBranchCLIActingTree(Base):
    """`--scan-branch` scans the tree it is RUN IN, not CLAUDE_PROJECT_DIR.

    `<base>...HEAD` is only meaningful against the tree whose HEAD is meant,
    and HEAD is per-worktree. The frozen SECRETS_JSON contract is untouched by
    this - only which tree it describes.
    """

    def run_cli(self, args, cwd):
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = self.root
        return subprocess.run(
            [sys.executable, hook_path("guard_secrets.py")] + args,
            capture_output=True, text=True, env=env, cwd=cwd)

    def _commit(self, tree, rel, content, message):
        self.write(rel, content, base=tree)
        self.assertEqual(git(tree, "add", rel).returncode, 0)
        self.assertEqual(git(tree, "commit", "-m", message).returncode, 0)

    def test_worktree_branch_secret_is_found_from_the_worktree_cwd(self):
        self._commit(self.root, "README.md", "hello\n", "base")
        base = git(self.root, "rev-parse", "HEAD").stdout.strip()
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self._commit(wt, "src/config.py", SECRET_LINE, "leak")
        r = self.run_cli(["--scan-branch", base], cwd=wt)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        line = [ln for ln in r.stdout.splitlines()
                if ln.startswith("SECRETS_JSON: ")][-1]
        data = json.loads(line[len("SECRETS_JSON: "):])
        self.assertEqual(len(data["hits"]), 1)
        self.assertEqual(data["hits"][0]["pattern"], "aws_access_key")

    def test_main_checkout_scan_is_unchanged(self):
        self._commit(self.root, "README.md", "hello\n", "base")
        base = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self._commit(self.root, "src/config.py", SECRET_LINE, "leak")
        r = self.run_cli(["--scan-branch", base], cwd=self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SECRETS_JSON: ", r.stdout)

    def test_clean_worktree_branch_exits_zero(self):
        self._commit(self.root, "README.md", "hello\n", "base")
        base = git(self.root, "rev-parse", "HEAD").stdout.strip()
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self._commit(wt, "src/util.py", "x = 1\n", "clean")
        r = self.run_cli(["--scan-branch", base], cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no secrets found", r.stdout)

    def test_unrelated_repository_cwd_does_not_hijack_the_scan(self):
        # The narrow-redirect rule, and a real regression: the wide version of
        # this change (redirect to ANY git work tree in the cwd) sent a
        # fixture's scan to whatever repository the test runner happened to be
        # standing in, and reported "no secrets found" for a branch that had
        # one. Only another checkout of the SAME repository may redirect.
        self._commit(self.root, "README.md", "hello\n", "base")
        base = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self._commit(self.root, "src/config.py", SECRET_LINE, "leak")
        other = tempfile.mkdtemp(prefix="cc-acting-otherrepo-")
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        git(other, "init")
        git(other, "config", "user.email", "t@example.com")
        git(other, "config", "user.name", "test")
        git(other, "commit", "--allow-empty", "-m", "init")
        r = self.run_cli(["--scan-branch", base], cwd=other)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stdout)

    def test_non_worktree_cwd_falls_back_to_the_project_root(self):
        self._commit(self.root, "README.md", "hello\n", "base")
        base = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self._commit(self.root, "src/config.py", SECRET_LINE, "leak")
        outside = tempfile.mkdtemp(prefix="cc-acting-nonrepo-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        r = self.run_cli(["--scan-branch", base], cwd=outside)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("aws_access_key", r.stdout)


class TestOwningCheckout(Base):
    """The path half of the rule, and the reason it is derived not named."""

    def test_main_checkout_file_owned_by_root(self):
        self.write("src/app.py", "x = 1\n")
        got = c.owning_checkout(self.root, os.path.join(self.root, "src/app.py"))
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))

    def test_worktree_file_owned_by_the_worktree(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.write("src/app.py", "x = 1\n", base=wt)
        got = c.owning_checkout(self.root, os.path.join(wt, "src/app.py"))
        self.assertEqual(os.path.realpath(got), os.path.realpath(wt))

    def test_worktree_at_a_non_convention_path_is_still_a_checkout(self):
        # `git worktree add` takes any path, so recognizing a worktree by the
        # literal string `/.claude/worktrees/` is a convention dependency.
        # This is derived from the `.git` marker instead.
        wt = self.add_worktree("build/scratch/tree", "task/odd")
        self.write("src/app.py", "x = 1\n", base=wt)
        got = c.owning_checkout(self.root, os.path.join(wt, "src/app.py"))
        self.assertEqual(os.path.realpath(got), os.path.realpath(wt))

    def test_path_outside_the_project_is_owned_by_nothing(self):
        # The scratchpad case: None means "not this project's business",
        # never "treat it as project source".
        outside = tempfile.mkdtemp(prefix="cc-acting-outside-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        self.assertIsNone(
            c.owning_checkout(self.root, os.path.join(outside, "note.py")))

    def test_relative_path_resolves_against_the_root(self):
        got = c.owning_checkout(self.root, "src/app.py")
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))

    def test_empty_path_degrades_to_root(self):
        self.assertEqual(c.owning_checkout(self.root, ""), self.root)


class TestPathCheckoutNarrowsTheExemption(Base):
    """`outside` means "no checkout of this repository owns it".

    The lead's gap-fill over `owning_checkout`, which stops at the project
    root. `git worktree add` accepts any path, so exempting by directory
    POSITION would let any lane buy unbriefed, ungated source writes just by
    putting its worktree in /tmp. The line is the shared object store, not the
    path.
    """

    def test_file_in_the_main_checkout_is_not_outside(self):
        tree, outside = c.path_checkout(
            self.root, os.path.join(self.root, "src/app.py"))
        self.assertFalse(outside)
        self.assertEqual(os.path.realpath(tree), os.path.realpath(self.root))

    def test_file_in_an_in_root_worktree_is_not_outside(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        tree, outside = c.path_checkout(
            self.root, os.path.join(wt, "src/app.py"))
        self.assertFalse(outside)
        self.assertEqual(os.path.realpath(tree), os.path.realpath(wt))

    def test_worktree_outside_the_root_is_still_this_project(self):
        # THE GAP. owning_checkout returns None here, which would have made
        # every file in this worktree exempt from guard_spec.
        wt = self.add_external_worktree("task/elsewhere")
        self.assertIsNone(
            c.owning_checkout(self.root, os.path.join(wt, "src/app.py")))
        tree, outside = c.path_checkout(
            self.root, os.path.join(wt, "src/app.py"))
        self.assertFalse(outside)
        self.assertEqual(os.path.realpath(tree), os.path.realpath(wt))

    def test_scratchpad_path_is_outside(self):
        outside_dir = tempfile.mkdtemp(prefix="cc-acting-scratch-")
        self.addCleanup(shutil.rmtree, outside_dir, ignore_errors=True)
        _tree, outside = c.path_checkout(
            self.root, os.path.join(outside_dir, "note.py"))
        self.assertTrue(outside)

    def test_an_unrelated_repository_is_outside(self):
        # A checkout, but not of THIS repository. Its source is not ours.
        other = tempfile.mkdtemp(prefix="cc-acting-otherproj-")
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        git(other, "init")
        _tree, outside = c.path_checkout(
            self.root, os.path.join(other, "src/app.py"))
        self.assertTrue(outside)

    def test_same_repository_is_derived_not_named(self):
        wt = self.add_external_worktree("task/elsewhere")
        other = tempfile.mkdtemp(prefix="cc-acting-otherproj2-")
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        git(other, "init")
        self.assertTrue(c.same_repository(wt, self.root))
        self.assertFalse(c.same_repository(other, self.root))
        self.assertFalse(c.same_repository(tempfile.gettempdir(), self.root))


class TestGuardSpecOutOfTreeEndToEnd(Base):
    """The scratchpad block, and the hole the fix must not open."""

    def spec_guard(self, file_path):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": file_path, "content": "x = 1\n"},
                   "cwd": self.root}
        return run_hook("guard_spec.py", payload, self.root)

    def test_scratchpad_source_write_is_allowed_with_no_task(self):
        scratch = tempfile.mkdtemp(prefix="cc-acting-sp-")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        r = self.spec_guard(os.path.join(scratch, "probe.py"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_source_in_an_external_worktree_still_needs_a_brief(self):
        # The over-exemption guard. This exits 0 without path_checkout.
        wt = self.add_external_worktree("task/elsewhere")
        r = self.spec_guard(os.path.join(wt, "src/app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no active brief", r.stderr)

    def test_source_in_an_in_root_worktree_still_needs_a_brief(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        r = self.spec_guard(os.path.join(wt, "src/app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no active brief", r.stderr)

    def test_the_block_message_names_an_absolute_state_path(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        r = self.spec_guard(os.path.join(wt, "src/app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        expected = os.path.join(self.root, "company", "state",
                                "active-task.json")
        self.assertIn(expected, r.stderr)
        # The relative form is what sent a worktree reader to a file that does
        # not exist there.
        self.assertNotIn("in company/state/active-task.json", r.stderr)

    def test_the_block_lands_in_the_project_log_not_the_worktree(self):
        # One project, one audit trail. A worktree is gitignored and pruned at
        # task close, so a record written only inside one deletes itself.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        r = self.spec_guard(os.path.join(wt, "src/app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("guard_spec | BLOCK", self.adherence())
        self.assertFalse(os.path.exists(
            os.path.join(wt, "company", "state", "adherence.log")))


class TestGrantLineIsLoggedOncePerGrant(Base):
    """RISK-MST-02 stays attributable without burying the log.

    107 of 431 lines in one five-week sample were this single line, which is
    how a signal stops being read. What the risk needs on record is that a
    grant was EXERCISED and by whom - a durable fact worth exactly one line,
    not one per write.
    """

    def run_tests_guard(self, file_path):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": file_path, "content": "x\n"},
                   "cwd": self.root}
        return run_hook("guard_tests.py", payload, self.root)

    def grant_lines(self):
        return [ln for ln in self.adherence().splitlines()
                if "guard_tests | GRANT" in ln]

    def test_repeated_allowed_writes_log_one_grant_line(self):
        self.set_tasks({"task": "a", "type": "feature", "test_scope": True},
                       {"task": "b", "type": "feature"})
        for i in range(5):
            r = self.run_tests_guard(
                os.path.join(self.root, "tests/test_%d.py" % i))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = self.grant_lines()
        self.assertEqual(len(lines), 1, "\n".join(lines))
        self.assertIn("test scope open (a)", lines[0])

    def test_a_second_granting_entry_gets_its_own_line(self):
        # Attribution survives the dedupe: a DIFFERENT granting entry is a
        # different fact and is recorded separately.
        self.set_tasks({"task": "a", "type": "feature", "test_scope": True},
                       {"task": "b", "type": "feature"})
        self.run_tests_guard(os.path.join(self.root, "tests/test_one.py"))
        self.set_tasks({"task": "b", "type": "feature", "test_scope": True},
                       {"task": "c", "type": "feature"})
        self.run_tests_guard(os.path.join(self.root, "tests/test_two.py"))
        lines = self.grant_lines()
        self.assertEqual(len(lines), 2, "\n".join(lines))
        self.assertIn("test scope open (a)", lines[0])
        self.assertIn("test scope open (b)", lines[1])

    def test_single_entry_still_logs_nothing(self):
        # BR-MST-02: at one entry the path stays byte-identical.
        self.set_tasks({"task": "a", "type": "feature", "test_scope": True})
        r = self.run_tests_guard(os.path.join(self.root, "tests/test_one.py"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.grant_lines(), [])

    def test_blocks_are_not_deduped(self):
        # Only the GRANT line is once-per-grant. A refusal is an event.
        self.set_tasks({"task": "a", "type": "feature"},
                       {"task": "b", "type": "feature"})
        for i in range(3):
            r = self.run_tests_guard(
                os.path.join(self.root, "tests/test_%d.py" % i))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        blocks = [ln for ln in self.adherence().splitlines()
                  if "guard_tests | BLOCK" in ln]
        self.assertEqual(len(blocks), 3, "\n".join(blocks))


class TestTaskStateRoot(Base):
    """Presence of active-task.json decides which tree describes the task."""

    def test_worktree_without_state_file_falls_back_to_root(self):
        # Today's shape in this repo: active-task.json is untracked and only
        # the main checkout has one.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.set_tasks({"task": "a", "type": "feature"})
        self.assertEqual(c.task_state_root(self.root, wt), self.root)

    def test_worktree_with_its_own_state_file_wins(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.set_tasks({"task": "a", "type": "feature"})
        self.set_tasks({"task": "b", "type": "feature"}, base=wt)
        self.assertEqual(c.task_state_root(self.root, wt), wt)

    def test_empty_task_list_in_the_acting_tree_is_still_its_statement(self):
        # Presence, not content: a tree that has the file and lists nothing is
        # saying no task is in flight there, and that is its statement to make.
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.set_tasks({"task": "a", "type": "feature"})
        self.set_tasks(base=wt)
        self.assertEqual(c.task_state_root(self.root, wt), wt)
        self.assertEqual(c.active_tasks(c.task_state_root(self.root, wt)), [])

    def test_none_tree_falls_back_to_root(self):
        self.assertEqual(c.task_state_root(self.root, None), self.root)


class TestActingTreeForCommand(Base):
    """The command half: (directory, unresolved) per segment."""

    def _payload(self, seg):
        return self.payload(seg)

    def test_absolute_dash_c_resolves_with_no_note(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        seg = "git -C {} commit -m x".format(wt)
        got, note = c.acting_tree(seg, self._payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(wt))
        self.assertIsNone(note)

    def test_unexpanded_variable_reports_the_target_as_written(self):
        # THE MESSAGE BUG. A hook sees raw command text, so `$WT` is never
        # expanded and no filesystem call can resolve it. Falling back
        # silently is what told a lane to switch to the branch it was on.
        seg = 'git -C "$WT" commit -m x'
        got, note = c.acting_tree(seg, self._payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))
        self.assertEqual(note, "$WT")

    def test_missing_directory_reports_the_target(self):
        seg = "git -C /nonexistent/path commit -m x"
        got, note = c.acting_tree(seg, self._payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))
        self.assertEqual(note, "/nonexistent/path")

    def test_no_dash_c_means_no_note(self):
        seg = "git commit -m x"
        got, note = c.acting_tree(seg, self._payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))
        self.assertIsNone(note)

    def test_dash_c_after_the_subcommand_is_not_a_path(self):
        # `git commit -C HEAD~1` is --reuse-message.
        seg = "git commit -C HEAD~1"
        got, note = c.acting_tree(seg, self._payload(seg), self.root)
        self.assertEqual(os.path.realpath(got), os.path.realpath(self.root))
        self.assertIsNone(note)

    def test_seg_git_dir_is_acting_tree_without_the_note(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        seg = "git -C {} commit -m x".format(wt)
        self.assertEqual(
            c.seg_git_dir(seg, self._payload(seg), self.root),
            c.acting_tree(seg, self._payload(seg), self.root)[0])


class TestGitSilenceIsNotAnAnswer(Base):
    """The P1: `_git` collapsed "git refused" and "git never answered".

    Both returned None, and an empty successful answer returned "", so every
    `if not out` test read three different facts as one. Under CPU contention
    the 5s timeout is reachable in normal parallel operation, so arming
    conditions disarmed silently with nothing in the log.
    """

    def test_answered_empty_is_distinct_from_refused(self):
        # `status --porcelain` on a clean tree: exit 0, empty stdout. A REAL
        # answer meaning "nothing to report".
        status, text = c.git_result(self.root, ["status", "--porcelain"])
        self.assertEqual(status, c.GIT_ANSWERED)
        self.assertEqual(text.strip(), "")
        # A non-repository: git runs and exits non-zero. A real NEGATIVE.
        plain = tempfile.mkdtemp(prefix="cc-acting-plain-")
        self.addCleanup(shutil.rmtree, plain, ignore_errors=True)
        status, _text = c.git_result(plain, ["status", "--porcelain"])
        self.assertEqual(status, c.GIT_REFUSED)

    def test_timeout_reports_silent_not_refused(self):
        # A zero timeout cannot complete, which is the timeout path exactly.
        status, _text = c.git_result(
            self.root, ["status", "--porcelain"], timeout=0.000001)
        self.assertEqual(status, c.GIT_SILENT)

    def test_silence_leaves_a_breadcrumb(self):
        # The breadcrumb goes to CLAUDE_PROJECT_DIR when set, which in a real
        # session is the project - pinned explicitly here so an ambient value
        # in CI cannot send it somewhere else and pass vacuously.
        previous = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.root
        try:
            c.git_result(self.root, ["status", "--porcelain"],
                         timeout=0.000001)
        finally:
            if previous is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = previous
        self.assertIn("GIT-SILENT", self.adherence())

    def test_git_keeps_its_old_contract(self):
        # Existing callers are unchanged: None for refused OR silent.
        plain = tempfile.mkdtemp(prefix="cc-acting-plain2-")
        self.addCleanup(shutil.rmtree, plain, ignore_errors=True)
        self.assertIsNone(c._git(plain, ["status", "--porcelain"]))
        self.assertIsNone(
            c._git(self.root, ["status", "--porcelain"], timeout=0.000001))
        # An ANSWERED-but-empty result is a string, not None: the index is
        # empty and git said so.
        self.assertEqual(c._git(self.root, ["diff", "--cached"]), "")

    def test_same_repository_returns_none_when_git_is_silent(self):
        # None, never False: "cannot tell" is not "different repository".
        # A missing directory is REFUSED (git runs and errors), so silence has
        # to come from the timeout, which is the real-world cause anyway.
        real = c.git_result

        def silent(root, args, timeout=c.GIT_TIMEOUT):
            return c.GIT_SILENT, ""

        c.git_result = silent
        try:
            self.assertIsNone(c.same_repository(self.root, self.root))
        finally:
            c.git_result = real

    def test_a_missing_directory_is_refused_not_silent(self):
        # The distinction in the other direction: git DID answer, negatively.
        status, _text = c.git_result("/nonexistent/xyz/0", ["rev-parse"])
        self.assertEqual(status, c.GIT_REFUSED)
        self.assertIs(c.same_repository("/nonexistent/xyz/0", self.root),
                      False)

    def test_same_repository_is_affirmative_for_a_real_worktree(self):
        wt = self.add_worktree(".claude/worktrees/slug", "task/slug")
        self.assertIs(c.same_repository(wt, self.root), True)

    def test_path_checkout_keeps_gating_when_git_cannot_tell(self):
        # A checkout owns the path but git cannot confirm whose. Exempting on
        # that silence is how project source escapes the brief gate, so the
        # conservative answer is "still ours".
        wt = self.add_external_worktree("task/elsewhere")
        target = os.path.join(wt, "src", "app.py")
        real = c.same_repository

        def silent(_a, _b):
            return None

        c.same_repository = silent
        try:
            _tree, outside = c.path_checkout(self.root, target)
        finally:
            c.same_repository = real
        self.assertFalse(outside, "git silence exempted project source")


class TestUnscannableIndexBlocks(Base):
    """A deliberate inversion of guard_secrets' fail-open posture."""

    def test_message_names_the_tree_and_the_retry(self):
        import guard_secrets
        msg = guard_secrets.unscannable_message("/some/tree")
        self.assertIn("/some/tree", msg)
        self.assertIn("Retry the commit", msg)
        self.assertIn(str(c.GIT_SLOW_TIMEOUT), msg)

    def test_an_unreadable_index_is_not_read_as_clean(self):
        # The whole point: the old code hit `if not diff: continue` and
        # allowed. Drive the real decision path with git forced silent.
        import guard_secrets
        real = c.git_result
        calls = []

        def silent(root, args, timeout=c.GIT_TIMEOUT):
            if args[:1] == ["diff"]:
                calls.append(timeout)
                return c.GIT_SILENT, ""
            return real(root, args, timeout=timeout)

        c.git_result = silent
        try:
            with self.assertRaises(SystemExit) as caught:
                guard_secrets.scan_commit_segments(
                    self.payload("git commit -m x"), self.root,
                    "git commit -m x")
            self.assertEqual(caught.exception.code, 2)
        finally:
            c.git_result = real
        # Retried once at the longer timeout before blocking.
        self.assertEqual(calls, [c.GIT_TIMEOUT, c.GIT_SLOW_TIMEOUT])


class TestOneImplementation(unittest.TestCase):
    """Tree resolution exists ONCE. A second copy is how this class returns.

    guard_secrets adopted guard_commit's parser under FR-HP-12 and not its
    tree resolution, and that omission is the P0 above. These assertions are
    the mechanical version of "do not copy it into a second file".
    """

    HOOKS = ("guard_commit.py", "guard_secrets.py", "guard_tests.py",
             "guard_spec.py")

    def _source(self, name):
        with open(hook_path(name)) as f:
            return f.read()

    def test_no_hook_defines_its_own_resolver(self):
        for name in self.HOOKS:
            source = self._source(name)
            for symbol in ("def git_cwd", "def seg_git_dir",
                           "def acting_tree", "def git_subcmd",
                           "def owning_checkout"):
                # assertFalse, not assertNotIn: a failure must not dump the
                # whole hook source into the run output.
                self.assertFalse(
                    symbol in source,
                    "{} defines its own {} - tree resolution belongs in "
                    "_common only".format(name, symbol.replace("def ", "")))

    def test_no_hook_detects_a_worktree_by_its_path_string(self):
        # `git worktree add` accepts any path, so a guard that RECOGNIZES a
        # worktree by the literal `/.claude/worktrees/` is asserting a
        # convention, not deriving a fact - guard_provenance:233 still does
        # exactly this, which is why the shape is worth pinning here.
        #
        # The leading slash is what separates detection from advice: a recipe
        # that SUGGESTS `git worktree add .claude/worktrees/<slug>` is naming
        # the house convention on purpose and is fine.
        for name in self.HOOKS:
            self.assertFalse(
                "/.claude/worktrees/" in self._source(name),
                "{} detects worktrees by path convention instead of the "
                "shared derivation".format(name))

    def test_common_still_exposes_the_shared_surface(self):
        for symbol in ("segments", "git_subcmd", "git_cwd", "seg_git_dir",
                       "acting_tree", "seg_c_path", "owning_checkout",
                       "task_state_root"):
            self.assertTrue(hasattr(c, symbol),
                            "_common lost {}".format(symbol))


if __name__ == "__main__":
    unittest.main(verbosity=2)
