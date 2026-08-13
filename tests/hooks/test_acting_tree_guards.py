#!/usr/bin/env python3
"""The acting-tree rule for guard_tests and guard_spec.

Both hooks resolved everything they judge from CLAUDE_PROJECT_DIR, which the
harness pins to the MAIN checkout, while every delegated agent works in a
linked worktree. Three defects came out of that, and this module holds one
class per defect plus the two directions each of them moves:

  1. guard_tests parsed `git rm` by hand (`toks[1] == "rm"`), so a git global
     option carrying a separated argument shifted the subcommand and
     `git -C <worktree> rm tests/foo.py` was INVISIBLE to the gate. Anyone
     could delete a test file by prefixing -C. ALLOW to BLOCK.
  2. Both hooks read company/state/active-task.json from the main checkout
     only. A worktree that keeps its own task state now governs itself, and
     one that does not still falls back to the main checkout, which is what
     keeps today's behavior intact in this repo.
  3. guard_spec had no out-of-tree exemption. c.rel_path strips the leading
     slash for a path outside the project, so a write to the scratchpad every
     agent is instructed to use arrived as `private/tmp/.../foo.py`, was
     classified as source, and was BLOCKED. BLOCK to ALLOW, scoped to paths
     outside the project root and nothing wider.

Fixtures build a REAL `git worktree add`, never a faked
`.claude/worktrees/<slug>` directory: a linked worktree carries a `.git` FILE
that `owning_checkout` and `seg_git_dir` both derive from, so a directory that
merely looks like one resolves differently and would prove nothing.

Run: python3 -m unittest tests.hooks.test_acting_tree_guards
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

STATE_REL = os.path.join("company", "state", "active-task.json")


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


class Base(unittest.TestCase):
    """A throwaway main checkout on `main`, plus real linked worktrees."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-actguard-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)
        self.init_git()

    def init_git(self):
        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        git(self.root, "commit", "--allow-empty", "-m", "init")
        git(self.root, "checkout", "-B", "main")

    # -- fixture building --------------------------------------------------

    def write(self, rel, content, base=None):
        path = os.path.join(base or self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def add_worktree(self, rel, branch):
        """A REAL linked worktree at <root>/<rel>. Absolute path."""
        path = os.path.join(self.root, rel)
        r = git(self.root, "worktree", "add", "-b", branch, path)
        if r.returncode != 0:
            self.skipTest("git worktree add unavailable: " + r.stderr)
        self.addCleanup(git, self.root, "worktree", "prune")
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def add_external_worktree(self, branch):
        """A real worktree OUTSIDE the project root, on no naming convention.

        `git worktree add` accepts any path, so a check that recognizes a
        worktree by the literal string `.claude/worktrees/` is a convention
        dependency and not a derivation.
        """
        parent = tempfile.mkdtemp(prefix="cc-actguard-ext-")
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        path = os.path.join(parent, "elsewhere")
        r = git(self.root, "worktree", "add", "-b", branch, path)
        if r.returncode != 0:
            self.skipTest("git worktree add unavailable: " + r.stderr)
        self.addCleanup(git, self.root, "worktree", "prune")
        return path

    def set_tasks(self, *entries, **kwargs):
        """Write active-task.json into `base` (default: the main checkout)."""
        base = kwargs.get("base") or self.root
        return self.write(STATE_REL,
                          json.dumps({"version": 2, "tasks": list(entries)}),
                          base=base)

    def state_path(self, base=None):
        return os.path.join(base or self.root, STATE_REL)

    def adherence(self, base=None):
        path = os.path.join(base or self.root, "company", "state",
                            "adherence.log")
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()

    # -- payloads ----------------------------------------------------------

    def edit_payload(self, file_path, cwd=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                "tool_input": {"file_path": file_path, "old_string": "x",
                               "new_string": "y"},
                "cwd": cwd if cwd is not None else self.root}

    def bash_payload(self, command, cwd=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command},
                "cwd": cwd if cwd is not None else self.root}

    # -- drivers -----------------------------------------------------------

    def guard_tests_bash(self, command, cwd=None):
        return run_hook("guard_tests.py", self.bash_payload(command, cwd),
                        self.root)

    def guard_tests_edit(self, file_path, cwd=None):
        return run_hook("guard_tests.py", self.edit_payload(file_path, cwd),
                        self.root)

    def guard_spec_edit(self, file_path, cwd=None):
        return run_hook("guard_spec.py", self.edit_payload(file_path, cwd),
                        self.root)

    # -- shared assertion --------------------------------------------------

    def assert_names_state_file(self, stderr, expected_path):
        """The recipe must name the ABSOLUTE state file the hook read.

        A relative `company/state/active-task.json` names nothing from a
        worktree cwd, so the recipe sends the reader to create a second,
        ignored task file. The path must also EXIST - a recipe pointing at a
        file that is not there is the same dead end one step later.
        """
        self.assertTrue(os.path.isabs(expected_path), expected_path)
        self.assertIn(expected_path, stderr)
        self.assertTrue(os.path.exists(expected_path), expected_path)


# ---------------------------------------------------------------------------
# Defect 1: the hand-rolled `git rm` parse. ALLOW to BLOCK.
# ---------------------------------------------------------------------------
class TestGitRmParse(Base):
    """`git -C <path> rm <test>` must be seen, in every -C spelling."""

    def setUp(self):
        super(TestGitRmParse, self).setUp()
        self.wt = self.add_worktree(".claude/worktrees/lane", "task/lane")
        self.set_tasks({"task": "lane", "type": "feature",
                        "test_scope": False})

    def test_dash_c_absolute_rm_of_a_test_is_blocked(self):
        """THE hole: separated -C shifted the subcommand, so this segment was
        never recognized as a `git rm` at all and exited 0.
        """
        r = self.guard_tests_bash("git -C {} rm tests/foo.py".format(self.wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("oracle", r.stderr.lower())
        self.assertIn("tests/foo.py", r.stderr)

    def test_dash_c_attached_rm_of_a_test_is_blocked(self):
        """The attached spelling carries its argument in the same token."""
        r = self.guard_tests_bash("git -C{} rm tests/foo.py".format(self.wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_other_separated_global_options_do_not_hide_the_rm(self):
        r = self.guard_tests_bash(
            "git -c user.name=x --git-dir {}/.git rm tests/foo.py".format(
                self.wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_plain_git_rm_of_a_test_is_blocked(self):
        """The form that always worked, kept as the control's other half."""
        r = self.guard_tests_bash("git rm tests/foo.py")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_plain_rm_of_a_test_is_blocked(self):
        """`rm` is not a git command, so the git parser must not swallow it."""
        r = self.guard_tests_bash("rm tests/foo.py")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_dash_c_rm_is_allowed_with_test_scope(self):
        """The other direction: the fix must not make test_scope a dead grant.

        Every lane in flight removes and rewrites tests inside a worktree.
        """
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True})
        r = self.guard_tests_bash("git -C {} rm tests/foo.py".format(self.wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_git_status_in_a_worktree_is_untouched(self):
        r = self.guard_tests_bash("git -C {} status".format(self.wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_git_rm_of_a_non_test_path_is_untouched(self):
        r = self.guard_tests_bash("git -C {} rm src/app.py".format(self.wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_git_commit_dash_c_reuse_message_is_not_an_rm(self):
        """`git commit -C HEAD~1` is --reuse-message: -C AFTER the subcommand
        is not a global option, and the shared parser only scans before it.
        """
        r = self.guard_tests_bash("git commit -C HEAD~1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_compound_command_is_judged_segment_by_segment(self):
        r = self.guard_tests_bash(
            "git -C {} status && git -C {} rm tests/foo.py".format(
                self.wt, self.wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Defect 2: task state read from the acting tree.
# ---------------------------------------------------------------------------
class TestTestScopeFromTheActingTree(Base):
    """WORRIES row 33: test_scope was resolved from the main checkout only."""

    def setUp(self):
        super(TestTestScopeFromTheActingTree, self).setUp()
        self.wt = self.add_worktree(".claude/worktrees/lane", "task/lane")
        self.wt_test = os.path.join(self.wt, "tests", "hooks", "test_x.py")

    def test_worktree_state_grants_when_the_main_checkout_does_not(self):
        """The lane-blocking case: the CEO's file says no, the worktree's own
        file says yes, and the edit happens in the worktree.
        """
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True},
                       base=self.wt)
        r = self.guard_tests_edit(self.wt_test)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_worktree_state_denies_when_the_main_checkout_grants(self):
        """The converse, so the grant is proved to come from the worktree and
        not from an OR over both files.
        """
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": True})
        self.set_tasks({"task": "lane", "type": "feature",
                        "test_scope": False}, base=self.wt)
        r = self.guard_tests_edit(self.wt_test)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path(self.wt))

    def test_no_worktree_state_falls_back_to_the_main_grant(self):
        """Today's behavior, unchanged. In this repo active-task.json is
        untracked, so only the main checkout has one and every worktree lands
        here - which is what makes the fallback the load-bearing half.
        """
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True})
        self.assertFalse(os.path.exists(self.state_path(self.wt)))
        r = self.guard_tests_edit(self.wt_test)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_worktree_state_falls_back_to_the_main_denial(self):
        self.set_tasks({"task": "lane", "type": "feature",
                        "test_scope": False})
        r = self.guard_tests_edit(self.wt_test)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path())

    def test_an_empty_worktree_state_file_is_a_statement_not_a_fallback(self):
        """Presence decides, not content: a worktree holding an EMPTY task
        list is saying no task is in flight there, and that statement is the
        acting tree's to make even when main grants scope.
        """
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": True})
        self.set_tasks(base=self.wt)
        r = self.guard_tests_edit(self.wt_test)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_the_main_checkout_still_judges_its_own_files(self):
        """The control: a test edit in the main checkout is unaffected."""
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True},
                       base=self.wt)
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        r = self.guard_tests_edit(
            os.path.join(self.root, "tests", "test_x.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_the_rm_path_reads_the_tree_the_minus_c_names(self):
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True},
                       base=self.wt)
        r = self.guard_tests_bash("git -C {} rm tests/foo.py".format(self.wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_rm_path_blocks_when_the_named_tree_denies(self):
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": True})
        self.set_tasks({"task": "lane", "type": "feature",
                        "test_scope": False}, base=self.wt)
        r = self.guard_tests_bash("git -C {} rm tests/foo.py".format(self.wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path(self.wt))

    def test_a_directory_that_merely_looks_like_a_worktree_does_not_govern(
            self):
        """No false positive: a plain directory named like a worktree is a
        project directory, not a checkout, so its task file governs nothing.

        This is the case a string match on `.claude/worktrees` would get wrong
        in the other direction - it would hand any directory under that name
        the power to grant itself test scope.
        """
        fake = os.path.join(self.root, ".claude", "worktrees", "notacheckout")
        os.makedirs(fake, exist_ok=True)
        self.set_tasks({"task": "fake", "type": "feature", "test_scope": True},
                       base=fake)
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        r = self.guard_tests_edit(os.path.join(fake, "tests", "test_x.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path())

    def test_the_block_is_logged_to_the_project_not_the_acting_tree(self):
        """Settled by the lead: the DECISION comes from the acting tree, the
        LOG LINE always goes to the project.

        A worktree is gitignored and pruned at task close, so a block recorded
        only inside one is evidence that deletes itself - and `adherence.log`
        is the company's proof that enforcement happened. One project, one
        audit trail. The message still names the absolute state file the
        decision was read from, so the two stories still reconcile; they just
        do not have to live in the same directory.
        """
        self.set_tasks({"task": "lane", "type": "feature",
                        "test_scope": False}, base=self.wt)
        r = self.guard_tests_edit(self.wt_test)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("guard_tests | BLOCK", self.adherence())
        self.assertFalse(os.path.exists(os.path.join(
            self.wt, "company", "state", "adherence.log")))
        # ... and the recipe still points at the file that actually decided.
        self.assertIn(
            os.path.join(self.wt, "company", "state", "active-task.json"),
            r.stderr)


class TestGuardSpecStateFromTheActingTree(Base):
    """guard_spec reads its entries, and resolves their briefs, per tree."""

    def setUp(self):
        super(TestGuardSpecStateFromTheActingTree, self).setUp()
        self.wt = self.add_worktree(".claude/worktrees/lane", "task/lane")
        self.wt_src = os.path.join(self.wt, "src", "app.py")

    def test_a_brief_in_the_worktree_satisfies_the_worktrees_own_entry(self):
        """A brief pointer is relative to the checkout whose task list names
        it. Resolved against the main checkout instead, this brief does not
        exist and a correctly declared lane is blocked.
        """
        self.write("company/briefs/brief-lane.md", "# brief\n", base=self.wt)
        self.set_tasks({"task": "lane", "type": "feature",
                        "brief": "company/briefs/brief-lane.md"},
                       base=self.wt)
        r = self.guard_spec_edit(self.wt_src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_brief_that_exists_only_in_the_main_checkout_is_no_use(self):
        """The converse, which is what proves the resolution base moved."""
        self.write("company/briefs/brief-lane.md", "# brief\n")
        self.set_tasks({"task": "lane", "type": "feature",
                        "brief": "company/briefs/brief-lane.md"},
                       base=self.wt)
        r = self.guard_spec_edit(self.wt_src)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("company/briefs/brief-lane.md", r.stderr)

    def test_main_state_and_main_brief_still_cover_a_worktree_write(self):
        """The fallback, and today's actual arrangement in this repo."""
        self.write("company/briefs/brief-lane.md", "# brief\n")
        self.set_tasks({"task": "lane", "type": "feature",
                        "brief": "company/briefs/brief-lane.md"})
        self.assertFalse(os.path.exists(self.state_path(self.wt)))
        r = self.guard_spec_edit(self.wt_src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_block_names_the_state_file_it_read(self):
        self.set_tasks({"task": "lane", "type": "feature"}, base=self.wt)
        r = self.guard_spec_edit(self.wt_src)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path(self.wt))
        self.assertIn("no active brief", r.stderr.lower())

    def test_the_fallback_block_names_the_main_state_file(self):
        self.set_tasks({"task": "lane", "type": "feature"})
        r = self.guard_spec_edit(self.wt_src)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path())


# ---------------------------------------------------------------------------
# Defect 3: paths outside the project. BLOCK to ALLOW, narrowly.
# ---------------------------------------------------------------------------
class TestGuardSpecOutOfTree(Base):
    """Only OUTSIDE the project root becomes exempt. Nothing wider."""

    def scratch_file(self, name="foo.py"):
        """A `.py` file outside the project: otherwise it is source."""
        parent = tempfile.mkdtemp(prefix="cc-actguard-scratch-")
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        path = os.path.join(parent, name)
        with open(path, "w") as f:
            f.write("print(1)\n")
        return path

    def test_a_scratchpad_write_is_allowed_with_no_active_task_at_all(self):
        """The reported break: c.rel_path strips the leading slash outside the
        project, so `/private/tmp/.../foo.py` arrived as
        `private/tmp/.../foo.py`, segment zero was `private`, the extension
        was a source extension, and the hook blocked the scratchpad every
        agent is instructed to use.
        """
        self.assertFalse(os.path.exists(self.state_path()))
        r = self.guard_spec_edit(self.scratch_file())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_exemption_does_not_depend_on_the_tool(self):
        target = self.scratch_file()
        for tool in ("Edit", "Write", "MultiEdit"):
            payload = self.edit_payload(target)
            payload["tool_name"] = tool
            r = run_hook("guard_spec.py", payload, self.root)
            self.assertEqual(r.returncode, 0, tool + ": " + r.stderr)

    def test_a_source_write_inside_the_project_still_blocks(self):
        """The control. Without this, an exemption that swallowed everything
        would look like a pass.
        """
        r = self.guard_spec_edit(os.path.join(self.root, "src", "app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_a_source_write_inside_a_linked_worktree_still_blocks(self):
        """The guard against over-exempting, stated explicitly.

        A linked worktree is where every delegated build happens. Exempting it
        along with the scratchpad would disarm spec-before-code exactly where
        it does its work, which is a far larger weakening than the reported
        break asks for.
        """
        wt = self.add_worktree(".claude/worktrees/lane", "task/lane")
        r = self.guard_spec_edit(os.path.join(wt, "src", "app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("brief", r.stderr.lower())

    def test_a_source_write_in_an_off_convention_worktree_blocks(self):
        """Derivation, not convention: a worktree that lives nowhere near
        `.claude/worktrees/` is still inside the project and still gated.
        """
        wt = self.add_worktree(os.path.join("build", "elsewhere", "wt2"),
                               "task/other")
        r = self.guard_spec_edit(os.path.join(wt, "src", "app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_a_worktree_outside_the_project_root_is_still_project_source(self):
        """Closed by the lead: `outside` means "no checkout of this repository
        owns it", NOT "outside the root directory".

        `git worktree add` accepts any path, so an exemption keyed on
        directory position would let any lane buy unbriefed, ungated source
        writes just by putting its worktree in /tmp. The line that survives
        that is the shared object store (c.same_repository), which is the same
        derivation the rest of this lane uses.
        """
        wt = self.add_external_worktree("task/elsewhere")
        r = self.guard_spec_edit(os.path.join(wt, "src", "app.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no active brief", r.stderr)

    def test_a_checkout_of_a_DIFFERENT_repository_is_exempt(self):
        """The other side of that line: some unrelated repo on this machine is
        not this project's source and never needed this project's brief.
        """
        other = tempfile.mkdtemp(prefix="cc-guards-otherrepo-")
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        subprocess.run(["git", "-C", other, "init"],
                       capture_output=True, text=True)
        r = self.guard_spec_edit(os.path.join(other, "src", "app.py"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_non_source_write_outside_the_project_is_still_allowed(self):
        r = self.guard_spec_edit(self.scratch_file("notes.md"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Convention independence for the Bash path, which resolves through git.
# ---------------------------------------------------------------------------
class TestUnconventionalWorktreePaths(Base):
    """Nothing may key on the `.claude/worktrees` naming."""

    def test_an_external_worktrees_own_state_governs_its_rm(self):
        wt = self.add_external_worktree("task/elsewhere")
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        self.set_tasks({"task": "ext", "type": "feature", "test_scope": True},
                       base=wt)
        r = self.guard_tests_bash("git -C {} rm tests/foo.py".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_an_external_worktree_denying_scope_blocks_the_rm(self):
        wt = self.add_external_worktree("task/elsewhere")
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": True})
        self.set_tasks({"task": "ext", "type": "feature",
                        "test_scope": False}, base=wt)
        r = self.guard_tests_bash("git -C {} rm tests/foo.py".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_names_state_file(r.stderr, self.state_path(wt))

    def test_an_in_root_worktree_off_convention_behaves_identically(self):
        wt = self.add_worktree(os.path.join("build", "elsewhere", "wt2"),
                               "task/other")
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        self.set_tasks({"task": "other", "type": "feature",
                        "test_scope": True}, base=wt)
        self.assertEqual(
            self.guard_tests_edit(
                os.path.join(wt, "tests", "test_x.py")).returncode, 0)
        self.assertEqual(
            self.guard_tests_bash(
                "git -C {} rm tests/foo.py".format(wt)).returncode, 0)

    def test_a_relative_minus_c_resolves_against_the_payload_cwd(self):
        wt = self.add_worktree(".claude/worktrees/lane", "task/lane")
        self.set_tasks({"task": "main-lane", "type": "feature",
                        "test_scope": False})
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True},
                       base=wt)
        r = self.guard_tests_bash(
            "git -C .claude/worktrees/lane rm tests/foo.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Fail-open. Enforcement never bricks a session.
# ---------------------------------------------------------------------------
class TestFailOpen(Base):
    """Every hook here fails OPEN: an internal problem allows the action."""

    HOOKS = ("guard_tests.py", "guard_spec.py")

    def assert_clean_allow(self, result, label):
        self.assertEqual(result.returncode, 0, label + ": " + result.stderr)
        self.assertNotIn("Traceback", result.stderr, label)

    def test_malformed_stdin(self):
        for hook in self.HOOKS:
            self.assert_clean_allow(
                run_hook(hook, None, self.root, raw_stdin="}{ not json"), hook)

    def test_empty_stdin(self):
        for hook in self.HOOKS:
            self.assert_clean_allow(
                run_hook(hook, None, self.root, raw_stdin=""), hook)

    def test_unknown_tool_name(self):
        payload = self.edit_payload(os.path.join(self.root, "tests",
                                                 "test_x.py"))
        payload["tool_name"] = "WebFetch"
        for hook in self.HOOKS:
            self.assert_clean_allow(run_hook(hook, payload, self.root), hook)

    def test_empty_file_path(self):
        payload = self.edit_payload("")
        for hook in self.HOOKS:
            self.assert_clean_allow(run_hook(hook, payload, self.root), hook)

    def test_missing_tool_input(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                   "cwd": self.root}
        for hook in self.HOOKS:
            self.assert_clean_allow(run_hook(hook, payload, self.root), hook)

    def test_missing_state_dir(self):
        """No company/state at all: an allowable action is still allowed and
        nothing crashes. A blockable one still blocks - the absent file is the
        no-task state, which is what these gates exist to catch.
        """
        shutil.rmtree(os.path.join(self.root, "company"), ignore_errors=True)
        self.assert_clean_allow(
            self.guard_tests_bash("rm README.md"), "guard_tests rm")
        self.assert_clean_allow(
            self.guard_spec_edit(os.path.join(self.root, "README.md")),
            "guard_spec")
        blocked = self.guard_spec_edit(
            os.path.join(self.root, "src", "app.py"))
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertNotIn("Traceback", blocked.stderr)

    def test_unbalanced_quotes_in_a_bash_command(self):
        """The tokenizer degrades to a whitespace split rather than raising."""
        self.set_tasks({"task": "lane", "type": "feature", "test_scope": True})
        self.assert_clean_allow(
            self.guard_tests_bash('git -C \'/no/such rm src/app.py'),
            "unbalanced")

    def test_a_torn_state_file_does_not_crash_the_bash_path(self):
        self.write(STATE_REL, '{"version": 2, "tasks": [')
        r = self.guard_tests_bash("rm src/app.py")
        self.assert_clean_allow(r, "torn state")


if __name__ == "__main__":
    unittest.main(verbosity=2)
