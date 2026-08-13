#!/usr/bin/env python3
"""Witnesses for the three provenance facts that have never been proven here.

1. `c.state_lock` had ZERO call sites: the concurrency layer existed and the
   ledger it protects was read-modify-written unlocked from every session,
   while several sessions against one working tree is the normal operating
   mode. TestLedgerRace is a MUTANT - the locked and unlocked arms run the
   same work and differ only in whether the lock wraps it - and the unlocked
   arm is asserted to LOSE a row. An arm that only checks the locked side
   proves nothing, because it passes just as well when the lock is a no-op.
2. Winning the race proves the lock works, not that guard_provenance takes
   it. TestShippedPathTakesTheLock carries two independent witnesses for that,
   one static and one behavioral.
3. `dirty_source_paths` read an unanswered `git status` as a clean tree, so
   Mode C silently disarmed whenever git was slow. TestModeCGitSilence pins
   silent-blocks against refused-allows, which are OPPOSITE facts that shared
   one falsy value.

Written against the frozen seam contract (C1, C2, C3, C5), not against
whatever the hook does today.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook  # noqa: E402
from test_hooks import HOOKS_DIR  # noqa: E402
from test_guard_provenance import ProvBase  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import _common as c  # noqa: E402

HOOK = "guard_provenance.py"


def run_hook_with_env(name, payload, root, extra_env):
    """Drive a hook with a MODIFIED environment.

    `run_hook` in test_hooks.py copies os.environ and offers no hook for
    changing it, and the whole point of the silence tests is to change one
    variable (PATH). sys.executable is absolute, so the interpreter still
    starts after PATH has been emptied - only the hook's own `git` lookup
    fails, which is the condition under test.
    """
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


# --------------------------------------------------------------------------
# A - the two-process race, deterministic in both arms
# --------------------------------------------------------------------------

# One racer. Deliberately NOT a test: it is the work unit the mutant runs
# twice, once wrapped in the lock and once not.
RACE_DRIVER = r'''"""One racer in the provenance ledger race.

Usage: racer.py <hooks_dir> <root> <slug> <a|b> <locked|unlocked>
                <stagger> <hold> <lock_timeout>

Read the ledger, append one dispatch row, HOLD, write it back. The hold is
inside the critical section, which is what makes the section wide enough that
the outcome is decided by two time.sleep calls rather than by microsecond
scheduling luck.
"""
import os
import sys
import time

hooks_dir, root, slug, racer, mode = sys.argv[1:6]
stagger = float(sys.argv[6])
hold = float(sys.argv[7])
lock_timeout = float(sys.argv[8])

sys.path.insert(0, hooks_dir)
import _common as c
import guard_provenance as gp

STATE = os.path.join(root, "company", "state")
WAIT_CAP = 60.0
POLL = 0.01


def marker(name):
    return os.path.join(STATE, "race-ready-" + name)


def give_up(why):
    """Fail LOUD. A racer that cannot establish its ordering must not fall
    back to running anyway - that is how a race test starts passing for
    reasons nobody asserted."""
    sys.stderr.write("racer {}: {}\n".format(racer, why))
    sys.exit(3)


def rendezvous():
    """Both racers past interpreter startup and imports before either enters
    the critical section.

    Startup is the one term in this race that load can stretch without bound,
    so it is taken out of the timing entirely. After this returns, the only
    clocks that decide anything are the two sleeps below.
    """
    open(marker(racer), "w").close()
    deadline = time.time() + WAIT_CAP
    while time.time() < deadline:
        if os.path.exists(marker("a")) and os.path.exists(marker("b")):
            return
        time.sleep(POLL)
    give_up("rendezvous timed out")


def await_row(role):
    """Block until a dispatch by `role` is visible on disk.

    Racer b uses this so that "b writes AFTER a writes" costs no timing
    margin at all. In the unlocked arm a's row is already there when b wakes;
    in the locked arm b only runs after a released the lock, so it is there
    too. If it is ever NOT there, the ordering this test asserts did not
    happen and the racer dies rather than producing an unasserted outcome.
    """
    deadline = time.time() + WAIT_CAP
    while time.time() < deadline:
        rows = (gp.read_ledger(root).get("tasks", {}).get(slug)
                or {}).get("dispatches") or []
        if any(row.get("role") == role for row in rows):
            return
        time.sleep(POLL)
    give_up("never saw a dispatch by " + role)


def work():
    ledger = gp.read_ledger(root)
    gp.task_record(ledger, slug)["dispatches"].append(
        {"role": racer, "at": c.iso_now()}
    )
    time.sleep(hold)
    if racer == "b":
        await_row("a")
    gp.write_ledger(root, ledger)


rendezvous()
if racer == "b":
    time.sleep(stagger)
if mode == "locked":
    with c.state_lock(root, timeout=lock_timeout):
        work()
else:
    work()
'''


class TestLedgerRace(Base):
    """The mutant. Same work, same fixture, same assertions - one difference.

    Timing, and why it cannot flip under load:

      STAGGER 0.5s  - b's head start for a, measured from the RENDEZVOUS, so
                      interpreter startup jitter (the unbounded term) is
                      already spent when the clock starts.
      HOLD    2.0s  - a's critical section. b must READ before a WRITES, and
                      the margin for that is HOLD - STAGGER = 1.5 seconds
                      with nothing in between but one small JSON read. Both
                      terms are wall-clock time.sleep, which does not dilate
                      under CPU contention; the only load-sensitive work in
                      the window is sub-millisecond. That is roughly three
                      orders of magnitude of headroom.
      write order   - not a timing margin at all. b waits for a's row to
                      appear before writing (see await_row), so the clobber
                      is forced rather than hoped for.
      LOCK_TIMEOUT  - 30s, generous: state_lock fails OPEN on timeout, so a
                      timeout in the locked arm would silently turn it into a
                      second unlocked arm. b waits at most HOLD - STAGGER for
                      the lock.
    """

    SLUG = "race-x"
    STAGGER = 0.5
    HOLD = 2.0
    LOCK_TIMEOUT = 30.0
    JOIN_TIMEOUT = 120

    def setUp(self):
        Base.setUp(self)
        # write_ledger prunes `tasks` to the ACTIVE keys, so the slug the
        # racers append under has to be a live entry or both rows vanish for
        # a reason that has nothing to do with locking.
        self.set_task({"task": self.SLUG, "type": "feature"})
        self.driver = os.path.join(self.root, "company", "state", "racer.py")
        with open(self.driver, "w") as f:
            f.write(RACE_DRIVER)

    def racer(self, name, mode):
        return subprocess.Popen(
            [sys.executable, self.driver, HOOKS_DIR, self.root, self.SLUG,
             name, mode, str(self.STAGGER), str(self.HOLD),
             str(self.LOCK_TIMEOUT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def run_arm(self, mode):
        """Both racers concurrently; returns the dispatch rows left on disk."""
        procs = [self.racer("a", mode), self.racer("b", mode)]
        for proc in procs:
            _, err = proc.communicate(timeout=self.JOIN_TIMEOUT)
            self.assertEqual(
                proc.returncode, 0,
                "a racer did not finish cleanly, so the interleaving this "
                "arm asserts never happened: " + err.decode("utf-8", "replace")
            )
        path = os.path.join(self.root, "company", "state",
                            "provenance-ledger.json")
        with open(path) as f:
            ledger = json.load(f)
        record = (ledger.get("tasks") or {}).get(self.SLUG) or {}
        return record.get("dispatches") or []

    def test_unlocked_arm_loses_a_row(self):
        rows = self.run_arm("unlocked")
        roles = [row.get("role") for row in rows]
        self.assertEqual(
            roles, ["b"],
            "The UNLOCKED arm must lose a row. Two sessions read the ledger, "
            "each appended its own dispatch to a stale copy, and the second "
            "write replaced the first - a's row is gone and only b's "
            "survived. If this arm ever keeps both rows the mutant is dead: "
            "the locked arm's pass would no longer be evidence that the lock "
            "does anything. Got: {}".format(roles)
        )

    def test_locked_arm_keeps_both_rows(self):
        rows = self.run_arm("locked")
        roles = [row.get("role") for row in rows]
        self.assertEqual(
            roles, ["a", "b"],
            "The LOCKED arm runs byte-identical work to the unlocked arm "
            "with c.state_lock wrapped around it, and both dispatches must "
            "survive: b's read happens after a released the lock, so b "
            "appends to a's result instead of to a stale copy. Got: "
            "{}".format(roles)
        )


# --------------------------------------------------------------------------
# B - the shipped path actually takes the lock
# --------------------------------------------------------------------------
class TestShippedPathTakesTheLock(ProvBase):
    """Winning the race proves state_lock works. These prove the hook uses it."""

    def test_single_write_ledger_call_site(self):
        # C3: every ledger MUTATION routes through update_ledger, which is
        # the one place holding the lock.
        # Parsed, not text-matched. A substring scan cannot tell a CALL from
        # the word appearing in a docstring or a comment, so it would go red
        # for the wrong reason the first time someone documents this rule in
        # prose that happens to include the parenthesised form. The AST knows
        # the difference, and the enclosing-function check is what actually
        # pins the contract: one call, and it is inside update_ledger.
        with open(os.path.join(HOOKS_DIR, "guard_provenance.py")) as f:
            tree = ast.parse(f.read())
        sites = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "write_ledger"):
                    sites.append(
                        "{} (line {})".format(node.name, inner.lineno)
                    )
        self.assertEqual(
            [s.split(" (line ")[0] for s in sites], ["update_ledger"],
            "write_ledger must have exactly ONE call site in the module "
            "body, inside update_ledger (contract C3). The rule exists "
            "because update_ledger is the only code that holds "
            "c.state_lock: any OTHER call is a read-modify-write cycle with "
            "no lock over it, and with several Claude Code sessions against "
            "one working tree that cycle silently drops the other session's "
            "dispatch row - the exact loss TestLedgerRace's unlocked arm "
            "demonstrates. Read-only sites keep the bare read_ledger; the "
            "file is replaced atomically, so a read is never torn. Call "
            "sites found: {}".format(sites or "none")
        )

    def test_dispatch_waits_on_a_held_lock_then_proceeds(self):
        # A hook that takes the lock cannot get it while this process holds
        # it, so it waits out state_lock's ~2s timeout and then proceeds
        # UNLOCKED (fail open). A hook that never takes the lock returns
        # immediately. Only the lower bound is asserted: an upper bound would
        # be a timing assertion on a loaded machine, which is not a fact.
        self.set_manifest()
        self.feature_task(slug="feat-x")
        payload = self.dispatch_payload(role="tech-lead", slug="feat-x")
        with c.state_lock(self.root, timeout=5.0):
            started = time.time()
            r = run_hook(HOOK, payload, self.root)
            elapsed = time.time() - started
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreaterEqual(
            elapsed, 1.5,
            "A Mode B-pre dispatch returned in {:.2f}s while this test held "
            "company/state/.state.lock. The ledger mutation therefore never "
            "asked for the lock - state_lock's timeout is ~2s, so anything "
            "that asks waits about that long before failing open, and "
            "nothing that does not ask can spend 1.5s here. The ledger is "
            "being read-modify-written unlocked again.".format(elapsed)
        )
        self.assertEqual(
            len(self.record("feat-x")["dispatches"]), 1,
            "state_lock fails OPEN by contract: a hook that cannot take the "
            "lock proceeds without it rather than hanging or dropping the "
            "write. The dispatch waited and then had to be recorded anyway."
        )


# --------------------------------------------------------------------------
# C - GIT_SILENT fails closed, GIT_REFUSED does not
# --------------------------------------------------------------------------
class TestModeCGitSilence(ProvBase):
    """Silence and refusal are OPPOSITE facts that used to share one value."""

    def commit_payload(self, cwd=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "git commit -m wip"},
                "cwd": cwd or self.root}

    def empty_path_dir(self):
        """A directory with no `git` in it, to be the whole of PATH.

        Silence is driven by making git UNRUNNABLE rather than slow:
        git_result returns GIT_SILENT on any exception out of
        subprocess.run, FileNotFoundError is one, and it arrives instantly
        instead of after the 30s slow-question timeout.
        """
        path = tempfile.mkdtemp(prefix="cc-nogit-")
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_silent_git_on_a_clean_tree_blocks(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        # The tree really is clean. The hook cannot know that, and that is
        # the whole point: before C1/C2 an unanswered `git status` read as a
        # clean tree and let the commit through.
        r = run_hook_with_env(HOOK, self.commit_payload(), self.root,
                              {"PATH": self.empty_path_dir()})
        self.assertEqual(
            r.returncode, 2,
            "Mode C must treat an unanswered tree as DIRTY. git could not "
            "run at all here, so dirty_source_paths returned "
            "answered=False, and an exemption may never be granted on a "
            "question that was never answered. Under CPU contention this is "
            "reachable in normal operation, and the gate that disarms "
            "quietly is worse than the gate that never armed. stderr: "
            + (r.stderr or "<empty>")
        )
        self.assertIn(
            "git did not answer", r.stderr,
            "A blocked agent must be able to tell git silence apart from a "
            "genuinely dirty tree - the two need different fixes. C2 renders "
            "the paths line as the silence itself."
        )
        self.assertIn(
            "treating the tree as dirty", r.stderr,
            "The message has to name the fail-closed choice, not just the "
            "silence (contract C2)."
        )
        self.assertIn(
            "GIT-SILENT", self.adherence(),
            "_common leaves one breadcrumb per silent git call so that "
            "silence is never invisible again. It reaches no decision; it is "
            "how the silent path gets diagnosed after the fact."
        )

    def test_answered_clean_tree_allows(self):
        # The control: same fixture, git on PATH. An affirmative clean answer
        # is a real answer and Mode C stays byte-identical to today.
        self.init_git()
        self.set_manifest()
        self.feature_task()
        r = run_hook(HOOK, self.commit_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refused_git_allows(self):
        # Not a git repository at all: git RUNS and exits non-zero. That is a
        # real negative answer, and an exemption may act on an affirmative
        # negative. This test is what stops a later reader from folding
        # silent and refused back into one falsy branch - they are opposite
        # facts, and only one of them may disarm the gate.
        self.set_manifest()
        self.feature_task()
        self.write("src/app.py", "x = 1")
        r = run_hook(HOOK, self.commit_payload(), self.root)
        self.assertEqual(
            r.returncode, 0,
            "GIT_REFUSED must keep behaving as 'the tree has no dirty "
            "source'. Only GIT_SILENT fails closed. stderr: "
            + (r.stderr or "<empty>")
        )


# --------------------------------------------------------------------------
# D - a real worktree at an arbitrary path keeps its exemption
# --------------------------------------------------------------------------
class TestWorktreeExemptionAnywhere(ProvBase):
    def test_real_worktree_outside_dot_claude_is_exempt(self):
        # C5 moves in_worktree_or_out_of_tree off the literal
        # '/.claude/worktrees/' string onto c.path_checkout, so a worktree
        # created ANYWHERE is exempt. `git worktree add` accepts any path,
        # and a lane building in /tmp is writing this project's source no
        # less than one building under .claude/worktrees/.
        #
        # A REAL worktree, never a faked directory: a linked worktree carries
        # a `.git` FILE and shares the main object store, and fixtures that
        # fake that shape have hidden a live bug in this repo before.
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.write("src/app.py", "x = 1")
        git(self.root, "add", "src/app.py")

        parent = tempfile.mkdtemp(prefix="cc-elsewhere-")
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        worktree = os.path.join(parent, "lane")
        added = git(self.root, "worktree", "add", "-b", "lane", worktree)
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertTrue(
            os.path.exists(os.path.join(worktree, ".git")),
            "a linked worktree must carry its own .git marker"
        )

        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m wip"},
                   "cwd": worktree}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(
            r.returncode, 0,
            "A commit from a real worktree must be exempt even with the MAIN "
            "checkout dirty and unaudited - the worktree is the acting tree "
            "and the main checkout's state is not its business. If this "
            "blocks, suspect the DIRECTORY probe: `cwd` is a directory, and "
            "the derived primitive walks up from a path's PARENT, so a "
            "directory handed over as-is resolves to its PARENT checkout and "
            "answers the exact opposite of the truth. C5 probes a directory "
            "as its own container (join(target, '_')) for that reason. "
            "stderr: " + (r.stderr or "<empty>")
        )


if __name__ == "__main__":
    unittest.main()
