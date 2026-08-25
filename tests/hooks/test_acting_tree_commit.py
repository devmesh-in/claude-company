#!/usr/bin/env python3
"""guard_commit judges the ACTING TREE's gate stamp, not the main checkout's.

The rule: a hook judges the tree that contains the thing being acted on.
DECISIONS #25: the stamp gates `git merge` onto main/master, not `git commit`.
A worktree commit no longer needs a stamp. A merge onto a protected branch
still reads THAT tree's `company/state/gates.status` (CR-HP-2 / FR-ASR-05).

Every fixture here uses a REAL `git worktree add`. A hand-made directory under
.claude/worktrees has no .git entry, no index and no branch, so it proves
nothing about the mechanism under test - `git rev-parse --is-inside-work-tree`
would refuse it and the hook would fall back to the root, which is the very
behavior these tests exist to distinguish from.

Ordering matters in every fixture: a tree's work hash covers its untracked
files, so gates.config is written BEFORE that tree is stamped. The main
checkout and a linked worktree hash independently - a write inside the
worktree does not stale the root's stamp, and vice versa.

Run: python3 -m unittest tests.hooks.test_acting_tree_commit
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

import guard_commit  # noqa: E402


BRANCH_MSG = "work belongs on a task branch"
STAMP_MSG = "requires green, fresh gates"
PLACEHOLDER_REASON = "gates.config has only CONFIGURE-ME placeholders"
LITERAL_FIX = "LITERAL absolute path"
JUDGED_LINE = "Judged: the acting tree"


def hook_path(name):
    return os.path.join(HOOKS_DIR, name)


def git(where, *args):
    return subprocess.run(
        ["git", "-C", where] + list(args), capture_output=True, text=True
    )


class Base(unittest.TestCase):
    """A throwaway project with a real git repo pinned to `main`."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-acting-commit-")
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)
        git(self.root, "init")
        # Local identity: the fixture must commit on a machine with no global
        # git config.
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        git(self.root, "commit", "--allow-empty", "-m", "init")
        # `git init` lands on the host default branch (main or master), so pin
        # it - the protected-branch rule is part of what is under test.
        git(self.root, "checkout", "-B", "main")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # --- fixture builders -------------------------------------------------
    def add_worktree(self, rel=".claude/worktrees/x", branch="task/x"):
        """Real `git worktree add`; returns the worktree's absolute path."""
        path = os.path.join(self.root, rel)
        r = git(self.root, "worktree", "add", path, "-b", branch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        self.addCleanup(lambda: git(self.root, "worktree", "prune"))
        return path

    def add_worktree_of(self, rel, existing_branch):
        """Worktree of an existing branch (not -b). Root must not have it
        checked out.
        """
        path = os.path.join(self.root, rel)
        r = git(self.root, "worktree", "add", path, existing_branch)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        self.addCleanup(lambda: git(self.root, "worktree", "prune"))
        return path

    def write(self, tree, rel, content):
        path = os.path.join(tree, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def configure_gates(self, tree):
        """One REAL gate in `tree`, so its stamp check is armed."""
        self.write(tree, "company/gates.config", json.dumps(
            {"gates": [{"name": "tests", "command": "true",
                        "blocking": True}]}))

    def configure_placeholder_gates(self, tree):
        """The gates.config a fresh install inherits before onboarding."""
        self.write(tree, "company/gates.config", json.dumps(
            {"gates": [{"name": "tests", "command": "CONFIGURE ME",
                        "blocking": True}]}))

    def stamp(self, tree, ok=True):
        """A stamp for `tree` via the real gate_stamp CLI, in that tree."""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = tree
        r = subprocess.run(
            [sys.executable, hook_path("gate_stamp.py"), "--results",
             json.dumps({"gates": [{"name": "tests", "ok": bool(ok)}]})],
            capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def stale_stamp(self, tree):
        """Stamp `tree` green, then change its content so the stamp stales."""
        self.stamp(tree, ok=True)
        self.write(tree, "drift.txt", "changed after the gates ran\n")

    def set_tasks(self, *entries):
        self.write(self.root, "company/state/active-task.json",
                   json.dumps({"version": 2, "tasks": list(entries)}))

    # --- driving the hook -------------------------------------------------
    def payload(self, command, cwd=None, omit_cwd=False):
        p = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": command}}
        if not omit_cwd:
            p["cwd"] = cwd if cwd is not None else self.root
        return p

    def run_hook(self, payload, raw_stdin=None):
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = self.root
        stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
        return subprocess.run(
            [sys.executable, hook_path("guard_commit.py")],
            input=stdin, capture_output=True, text=True, env=env)

    def commit_guard(self, command, cwd=None, omit_cwd=False):
        return self.run_hook(self.payload(command, cwd, omit_cwd))

    def adherence(self):
        path = os.path.join(self.root, "company", "state", "adherence.log")
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()


# --- the DoD: a worktree stands on its own stamp ---------------------------
class TestWorktreeStandsOnItsOwnStamp(Base):
    def test_worktree_commit_allowed_with_no_stamp(self):
        # DECISIONS #25: a worktree commit does not need a stamp.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_worktree_commit_allowed_when_own_stamp_red_and_main_green(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt, ok=False)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_worktree_commit_allowed_when_own_stamp_stale_and_main_green(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stale_stamp(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_worktree_own_green_stamp_allows_with_untouched_main(self):
        # The DoD line. The main checkout gets NOTHING: no gates.config, no
        # gates.status. The worktree gates itself and commits.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # The proof it went through the real stamp check rather than falling
        # into a bypass: the main checkout has no gates.config at all, so the
        # old root-resolved code would have logged "no gates configured".
        self.assertNotIn("no gates configured", self.adherence())

    def test_worktree_green_stamp_beats_a_red_main_stamp(self):
        # Commit still allows; merge onto main is the stamp question, below.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt)
        self.configure_gates(self.root)
        self.stamp(self.root, ok=False)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_merge_on_main_blocked_even_when_worktree_is_green(self):
        # The acting tree for a merge on main is the main checkout.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt)
        self.configure_gates(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("no gates.status stamp", r.stderr)

    def test_merge_on_main_stale_blocks_though_worktree_is_green(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt)
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("stale", r.stderr)

    def test_merge_on_main_red_blocks_though_worktree_is_green(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt)
        self.configure_gates(self.root)
        self.stamp(self.root, ok=False)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("red", r.stderr)

    def test_merge_on_task_branch_in_worktree_allowed_without_stamp(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        r = self.commit_guard("git -C {} merge main".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_cwd_in_worktree_without_dash_c_commit_needs_no_stamp(self):
        # The other way into a worktree: no -C, the session simply sits there.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git commit -m y", cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- the main checkout's own path is untouched -----------------------------
class TestMainCheckoutUnchanged(Base):
    """No worktree in sight: root IS the acting tree, as it always was."""

    def test_green_stamp_allows_commit(self):
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_stale_stamp_allows_commit(self):
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_red_stamp_allows_commit(self):
        self.configure_gates(self.root)
        self.stamp(self.root, ok=False)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_stamp_allows_commit(self):
        self.configure_gates(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_merge_on_main_is_gated_by_the_root_stamp(self):
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_merge_on_main_blocked_when_unstamped(self):
        self.configure_gates(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)


# --- the placeholder bypass, in the acting tree ----------------------------
class TestPlaceholderGatesInTheActingTree(Base):
    def test_worktree_placeholders_allow_commit_without_a_bypass(self):
        # Placeholders used to be the only way a worktree could commit, because
        # the stamp check ran at commit. Commits are not stamp-gated now, so
        # the commit is allowed and no placeholder bypass is owed.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_placeholder_gates(wt)
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_worktree_without_any_gates_config_allows_commit(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_merge_on_main_placeholders_bypass_and_log(self):
        self.configure_placeholder_gates(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.adherence()
        self.assertIn("BYPASS", log)
        self.assertIn(PLACEHOLDER_REASON, log)


# --- the unresolved -C note ------------------------------------------------
class TestUnresolvedDashCNote(Base):
    def entries(self):
        return [{"task": "x", "type": "feature"}]

    def test_unexpanded_variable_names_the_target_and_the_fix(self):
        # A hook sees raw command text, so `$WT` arrives literally. The gate
        # falls back to the tree the command ran in - the main checkout, on
        # main - and blocks on the branch rule, naming a branch that has
        # nothing to do with the tree the author aimed at.
        self.add_worktree()
        self.set_tasks(*self.entries())
        r = self.commit_guard('git -C "$WT" commit -m y')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(BRANCH_MSG, r.stderr)
        self.assertIn("$WT", r.stderr)
        self.assertIn(LITERAL_FIX, r.stderr)

    def test_note_is_appended_and_leaves_the_recipe_byte_identical(self):
        # BR-MST-02 pins the one-entry rendering. The note is appended, so the
        # recipe itself is unchanged to the byte.
        self.set_tasks(*self.entries())
        r = self.commit_guard('git -C "$WT" commit -m y')
        recipe = guard_commit.branch_recipe(self.entries())
        self.assertTrue(r.stderr.startswith(recipe), r.stderr)
        self.assertEqual(
            r.stderr,
            recipe + guard_commit.unresolved_note("$WT") + "\n",
        )

    def test_no_note_when_dash_c_resolves(self):
        # A -C that names a real work tree: the message is today's, exactly.
        self.set_tasks(*self.entries())
        r = self.commit_guard("git -C {} commit -m y".format(self.root))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn(LITERAL_FIX, r.stderr)
        self.assertEqual(
            r.stderr, guard_commit.branch_recipe(self.entries()) + "\n")

    def test_no_note_on_a_bare_commit(self):
        # No -C at all is not an unresolved -C.
        self.set_tasks(*self.entries())
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn(LITERAL_FIX, r.stderr)
        self.assertEqual(
            r.stderr, guard_commit.branch_recipe(self.entries()) + "\n")

    def test_multi_entry_recipe_is_byte_identical_without_the_note(self):
        entries = [{"task": "a"}, {"task": "b"}, {"task": "c"}, {"task": "d"}]
        self.set_tasks(*entries)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr, guard_commit.branch_recipe(entries) + "\n")

    def test_multi_entry_recipe_takes_the_note_too(self):
        entries = [{"task": "a"}, {"task": "b"}]
        self.set_tasks(*entries)
        r = self.commit_guard('git -C "$WT" commit -m y')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(
            r.stderr,
            guard_commit.branch_recipe(entries)
            + guard_commit.unresolved_note("$WT") + "\n",
        )


# --- the stamp message is a runnable recipe --------------------------------
class TestStampMessageNamesTheActingTree(Base):
    def test_worktree_merge_block_names_an_absolute_runner_path(self):
        # Fixture root sits on a task branch so we can put a worktree on main
        # (git refuses two checkouts of the same branch). Merge in that
        # worktree is integration onto a protected branch, judged by the
        # worktree's own stamp, while CLAUDE_PROJECT_DIR is still the root.
        git(self.root, "checkout", "-B", "task/root")
        wt = self.add_worktree_of(".claude/worktrees/main-wt", "main")
        self.configure_gates(wt)
        r = self.commit_guard("git -C {} merge task/root".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn(JUDGED_LINE, r.stderr)
        self.assertIn("bash {}/company/run-gates.sh".format(wt), r.stderr)

    def test_main_checkout_merge_block_keeps_the_plain_recipe(self):
        self.configure_gates(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("bash company/run-gates.sh", r.stderr)
        self.assertNotIn(JUDGED_LINE, r.stderr)


# --- per-segment isolation survives the change -----------------------------
class TestPerSegmentIsolation(Base):
    def test_worktree_commit_does_not_skip_a_later_merge_stamp(self):
        # Segment 1 is a worktree commit (no stamp). Segment 2 is a merge on
        # main with real gates and no stamp, and must still block.
        wt = self.add_worktree()
        self.configure_gates(wt)
        self.configure_gates(self.root)
        r = self.commit_guard(
            "git -C {} commit -m y && git merge task/x".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertNotIn(JUDGED_LINE, r.stderr)

    def test_green_root_merge_does_not_cover_a_later_worktree_on_main(self):
        git(self.root, "checkout", "-B", "task/root")
        wt = self.add_worktree_of(".claude/worktrees/main-wt", "main")
        self.configure_gates(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard(
            "git commit -m y && git -C {} merge task/root".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("bash {}/company/run-gates.sh".format(wt), r.stderr)

    def test_two_worktrees_commits_are_not_stamp_gated(self):
        first = self.add_worktree(".claude/worktrees/a", "task/a")
        second = self.add_worktree(".claude/worktrees/b", "task/b")
        self.configure_gates(first)
        self.configure_gates(second)
        r = self.commit_guard(
            "git -C {} commit -m y && git -C {} commit -m y".format(
                first, second))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- fail open -------------------------------------------------------------
class TestFailsOpen(Base):
    def test_malformed_stdin(self):
        r = self.run_hook(None, raw_stdin="not json{")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_non_bash_tool(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": "x", "content": "y"},
                   "cwd": self.root}
        r = self.run_hook(payload)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_cwd(self):
        # No cwd key at all: the resolution falls back to the project root,
        # which here has nothing to gate, so the commit is allowed.
        r = self.commit_guard("git commit -m y", omit_cwd=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_cwd_with_a_worktree_dash_c(self):
        wt = self.add_worktree()
        self.configure_gates(wt)
        self.stamp(wt)
        r = self.commit_guard("git -C {} commit -m y".format(wt),
                              omit_cwd=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unparseable_segment(self):
        # An unbalanced quote makes shlex raise; the whitespace fallback must
        # keep the hook from bricking the session.
        self.configure_gates(self.root)
        self.set_tasks({"task": "x", "type": "feature"})
        r = self.commit_guard("git -C 'unterminated status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_empty_command(self):
        r = self.commit_guard("")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
