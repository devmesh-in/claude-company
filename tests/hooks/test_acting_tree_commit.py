#!/usr/bin/env python3
"""guard_commit judges the ACTING TREE's gate stamp, not the main checkout's.

The rule: a hook judges the tree that contains the thing being acted on. The
branch half of it shipped under FR-HP-11; the STAMP half did not, so
`git -C .claude/worktrees/<slug> commit` read `company/state/gates.status`
from the main checkout. A lane could be green-lit by a sibling lane's gate
run, or blocked by a sibling lane's drift, and had no way to fix either from
its own tree.

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
        # BLOCK -> ALLOW. The main checkout is red; the acting tree is green.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt)
        self.configure_gates(self.root)
        self.stamp(self.root, ok=False)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_worktree_missing_stamp_blocks_though_main_is_green(self):
        # ALLOW -> BLOCK. The worktree never ran its own ladder.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("no gates.status stamp", r.stderr)

    def test_worktree_stale_stamp_blocks_though_main_is_green(self):
        # ALLOW -> BLOCK. The worktree drifted after its own green run.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stale_stamp(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("stale", r.stderr)

    def test_worktree_red_stamp_blocks_though_main_is_green(self):
        # ALLOW -> BLOCK. The worktree's own ladder failed.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.stamp(wt, ok=False)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("red", r.stderr)

    def test_cwd_in_worktree_without_dash_c_uses_the_worktree_stamp(self):
        # The other way into a worktree: no -C, the session simply sits there.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git commit -m y", cwd=wt)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.stamp(wt)
        r = self.commit_guard("git commit -m y", cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- the main checkout's own path is untouched -----------------------------
class TestMainCheckoutUnchanged(Base):
    """No worktree in sight: root IS the acting tree, as it always was."""

    def test_green_stamp_allows(self):
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_stale_stamp_blocks(self):
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("stale", r.stderr)

    def test_red_stamp_blocks(self):
        self.configure_gates(self.root)
        self.stamp(self.root, ok=False)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("red", r.stderr)

    def test_missing_stamp_blocks(self):
        self.configure_gates(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)

    def test_merge_is_gated_by_the_root_stamp_too(self):
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- the placeholder bypass, in the acting tree ----------------------------
class TestPlaceholderGatesInTheActingTree(Base):
    def test_worktree_placeholders_bypass_and_log(self):
        # This is what keeps THIS repo working: the tracked gates.config holds
        # CONFIGURE-ME placeholders on purpose, so a worktree inherits them and
        # can never produce a green stamp. The commit is allowed and the bypass
        # is visible in the log, exactly as a fresh install gets before
        # onboarding. The main checkout is deliberately real-and-stale, so an
        # allow here can only come from the worktree's own config.
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_placeholder_gates(wt)
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.adherence()
        self.assertIn("BYPASS", log)
        self.assertIn(PLACEHOLDER_REASON, log)

    def test_worktree_without_any_gates_config_bypasses_and_logs(self):
        # A worktree that inherits no gates.config at all (untracked in the
        # main checkout, so the worktree never sees it) is "nothing to gate
        # yet", not "blocked forever".
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(self.root)
        self.stale_stamp(self.root)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no gates configured", self.adherence())


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
    def test_worktree_block_names_an_absolute_runner_path(self):
        wt = self.add_worktree()
        self.set_tasks({"task": "x", "type": "feature"})
        self.configure_gates(wt)
        r = self.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn(JUDGED_LINE, r.stderr)
        self.assertIn("bash {}/company/run-gates.sh".format(wt), r.stderr)

    def test_main_checkout_block_keeps_the_plain_recipe(self):
        self.configure_gates(self.root)
        r = self.commit_guard("git commit -m y")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("bash company/run-gates.sh", r.stderr)
        self.assertNotIn(JUDGED_LINE, r.stderr)


# --- per-segment isolation survives the change -----------------------------
class TestPerSegmentIsolation(Base):
    def test_worktree_segment_does_not_decide_the_next_segments_stamp(self):
        # Segment 1 acts on the worktree and passes on the worktree's own
        # green stamp. Segment 2 has no -C, so it is judged by the root - which
        # has real gates and no stamp - and blocks. A hoisted single
        # resolution would have let segment 2 ride the worktree's stamp.
        wt = self.add_worktree()
        self.configure_gates(wt)
        self.stamp(wt)
        self.configure_gates(self.root)
        r = self.commit_guard(
            "git -C {} commit -m y && git commit -m y".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertNotIn(JUDGED_LINE, r.stderr)

    def test_root_segment_does_not_decide_a_later_worktree_stamp(self):
        # The other direction: the root is green, the worktree is not, and the
        # later -C segment must still be judged by the worktree.
        wt = self.add_worktree()
        self.configure_gates(wt)
        self.configure_gates(self.root)
        self.stamp(self.root)
        r = self.commit_guard(
            "git commit -m y && git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(STAMP_MSG, r.stderr)
        self.assertIn("bash {}/company/run-gates.sh".format(wt), r.stderr)

    def test_two_worktrees_are_judged_separately(self):
        first = self.add_worktree(".claude/worktrees/a", "task/a")
        second = self.add_worktree(".claude/worktrees/b", "task/b")
        self.configure_gates(first)
        self.stamp(first)
        self.configure_gates(second)
        r = self.commit_guard(
            "git -C {} commit -m y && git -C {} commit -m y".format(
                first, second))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("bash {}/company/run-gates.sh".format(second), r.stderr)
        self.assertNotIn("bash {}/company/run-gates.sh".format(first),
                         r.stderr)


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
