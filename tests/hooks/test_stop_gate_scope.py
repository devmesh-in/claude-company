#!/usr/bin/env python3
"""FR-HP-50: the stop_gate block is scoped to one gating entry.

stop_gate reads every active entry but checks ONE tree-wide gates.status
stamp. With several sessions in flight that made any one session's red tree
block every other session at every turn end, and the recipe told the wrong
session to fix work it does not own.

The scoped rule under test here:

  * exactly ONE gating entry + a bad stamp -> BLOCK, byte-identical to the
    pre-FR-HP-50 hook. The literals in BLOCK_STDOUT and STALE_LOG /
    MISSING_LOG were recorded by running the OLD hook against a fixture
    before the change, so they are a real regression oracle rather than a
    transcription of the new code.
  * MORE THAN ONE gating entry + a bad stamp -> no block decision at all,
    and exactly one WARN line naming EVERY gating slug.
  * a green fresh stamp, or no gating entries, stays silent either way.

Every decision is driven through a real hook subprocess.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Same-dir sibling import: works under `unittest discover -s tests/hooks` and
# under `-m unittest tests.hooks.test_stop_gate_scope` - mirror the hooks'
# own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, run_hook  # noqa: E402

# Recorded from the pre-FR-HP-50 hook, one entry {"task": "feat-x",
# "type": "feature"}. Trailing newline included: print() emitted it.
BLOCK_STDOUT = (
    '{"decision": "block", "reason": "Active task \'feat-x\' has red or '
    'stale gates. Run the gate suite (/gates) and make it green, or close '
    'YOUR entry in company/state/active-task.json with a targeted Edit, '
    'before finishing."}\n'
)
BLOCK_REASON = (
    "Active task 'feat-x' has red or stale gates. Run the gate suite "
    "(/gates) and make it green, or close YOUR entry in "
    "company/state/active-task.json with a targeted Edit, before finishing."
)
REPO_HOOKS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".claude", "hooks")
STALE = "gates.status is stale (work changed since gates ran)"
MISSING = "no gates.status stamp (gates have not been run)"
STALE_LOG = "stop_gate | BLOCK | feat-x | " + STALE
MISSING_LOG = "stop_gate | BLOCK | feat-x | " + MISSING


class StopScopeBase(Base):
    def setUp(self):
        Base.setUp(self)
        self.init_git()
        self.extra = tempfile.mkdtemp(prefix="cc-hooks-wt-")
        self.addCleanup(shutil.rmtree, self.extra, ignore_errors=True)

    def log_path(self):
        return os.path.join(self.root, "company", "state", "adherence.log")

    def log_lines(self):
        """adherence.log with the leading timestamp field stripped."""
        if not os.path.exists(self.log_path()):
            return []
        with open(self.log_path()) as f:
            raw = f.read().splitlines()
        return [ln.split(" | ", 1)[1] if " | " in ln else ln for ln in raw]

    def stop_payload(self, stop_hook_active=False):
        return {"hook_event_name": "Stop",
                "stop_hook_active": stop_hook_active, "cwd": self.root}

    def green_stamp(self):
        """Stamp the tree green and fresh."""
        self.write("company/gates.config",
                   json.dumps({"gates": [{"name": "tests"}]}))
        self.stamp({"gates": [{"name": "tests", "ok": True}]})

    def go_stale(self):
        """Dirty the tree so the stamped work_hash no longer matches.

        company/state is excluded from work_hash, so the edit has to land
        outside it or the stamp would stay fresh.
        """
        self.write("src/app.py", "print(1)\n")

    def run_stop(self, stop_hook_active=False):
        return run_hook("stop_gate.py",
                        self.stop_payload(stop_hook_active), self.root)

    def add_worktree(self, slug):
        """A REAL `git worktree add` on the canon branch name task/<slug>.

        Created outside self.root so the fixture's own work_hash is not
        perturbed by the worktree's files, and torn down with it.
        """
        path = os.path.join(self.extra, slug)
        proc = subprocess.run(
            ["git", "-C", self.root, "worktree", "add", "-q", path,
             "-b", "task/" + slug],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(proc.returncode, 0,
                         proc.stdout.decode("utf-8", "replace"))
        return path


class SingleGatingEntryIsUnchanged(StopScopeBase):
    """FR-HP-50: at one gating entry the hook must not have moved at all."""

    def test_one_entry_stale_stamp_is_byte_identical_to_the_old_hook(self):
        """FR-HP-50 regression oracle: the single-session block is the whole
        reason stop_gate exists, and scoping must not have shaved a byte off
        it. stdout is compared against the literal recorded from the old
        hook, not against a substring.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertEqual(decision["reason"], BLOCK_REASON)
        self.assertEqual(self.log_lines(), [STALE_LOG])

    def test_one_entry_missing_stamp_blocks_and_logs_the_stamp_cause(self):
        """FR-HP-50: a tree that never ran gates is a distinct failure from a
        stale one. The block text is deliberately the same either way, so the
        cause has to survive in the adherence line - that is the only place a
        reader can tell "never ran" from "ran and went stale".
        """
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        self.assertEqual(json.loads(r.stdout)["reason"], BLOCK_REASON)
        self.assertEqual(self.log_lines(), [MISSING_LOG])

    def test_one_entry_green_fresh_stamp_is_silent(self):
        """FR-HP-50: a green fresh stamp exits 0 with no decision and no log
        line. If the scoping had reordered the stamp check after the entry
        count, a green tree would start emitting records for nothing.
        """
        self.set_tasks({"task": "feat-x", "type": "feature"})
        self.green_stamp()
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_quick_plus_feature_still_blocks_and_names_only_the_feature(self):
        """FR-HP-50 keeps FR-MST-09: quick exempts ITSELF, not the tree. The
        quick entry drops out of `gating`, which leaves exactly one gating
        entry - so this is a BLOCK, not a WARN, and it must blame feat-x
        alone or the recipe goes to the wrong desk.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertNotIn("'q'", decision["reason"])
        self.assertEqual(self.log_lines(), [STALE_LOG])

    def test_quick_and_hotfix_only_exits_zero_silently(self):
        """FR-HP-50: with no gating entry left there is nothing to block and
        nothing to warn about, even on a stale tree.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "hf", "type": "hotfix"})
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])


class ManyGatingEntriesWarnInsteadOfBlocking(StopScopeBase):
    """FR-HP-50: past one gating entry the block is unactionable, so it goes
    to the log instead of to a turn that cannot use it.
    """

    def test_two_entries_stale_stamp_warns_and_never_blocks(self):
        """FR-HP-50 reproduction: this is the shape that fired on the CEO
        three times in one day. The session ending its turn cannot know whose
        edit dirtied the shared tree, so stdout must carry no decision at all
        - an empty stdout is the assertion that matters, and the WARN line is
        the record that replaces it.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | feat-a, feat-b | " + STALE],
        )

    def test_two_entries_green_fresh_stamp_writes_no_warn(self):
        """FR-HP-50: the WARN is a report of a bad stamp, not a report of
        concurrency. A green tree with two sessions on it is a normal state
        and must leave the log untouched.
        """
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        self.green_stamp()
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_four_entries_are_all_named_in_the_one_warn_line(self):
        """FR-HP-50 truncation trap: c.slug_list caps display at 3 by default
        and would render "t0, t1, t2 and 1 more". The WARN line is now the
        ONLY record a dropped session appears in, so the cap has to be raised
        at the call site. t3 must be there by name.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks(*[{"task": "t%d" % i, "type": "feature"}
                         for i in range(4)])
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | t0, t1, t2, t3 | " + STALE],
        )


class WorktreeAttributionComposition(StopScopeBase):
    """FR-HP-50, CEO ruling 2026-08-13: attribution filters the gating set
    first, then the single-entry rule decides over what is left.

    An entry with its own worktree cannot have dirtied THIS tree, so it is not
    a candidate. Every case below drives a real `git worktree add`, because the
    signal is git's own record and a mocked one would prove nothing about it.
    """

    def test_the_live_reproduction_no_longer_blocks_anyone(self):
        """The 2026-08-13 shape that fired on the CEO three times: four lanes,
        every one of them building in its own worktree, none of their code in
        this tree. Nothing here is attributable, so nothing blocks, and the
        WARN says why rather than leaving a silent gap.
        """
        self.green_stamp()
        self.go_stale()
        slugs = ["hp-kernel", "hp-guards", "hp-runner", "hp-doctrine"]
        for slug in slugs:
            self.add_worktree(slug)
        self.set_tasks(*[{"task": s, "type": "feature"} for s in slugs])
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | " + ", ".join(slugs) +
             " (all in other worktrees) | " + STALE],
        )

    def test_the_one_in_tree_entry_still_blocks_beside_a_worktree_lane(self):
        """This is what the composition buys over the single-entry rule alone.
        Two gating entries, but one builds in its own worktree - so exactly one
        is attributable and the block comes BACK, byte-identical, naming the
        session that can actually act on it. Under the plain single-entry rule
        this case degraded to a WARN and nothing was gated.
        """
        self.green_stamp()
        self.go_stale()
        self.add_worktree("feat-elsewhere")
        self.set_tasks({"task": "feat-elsewhere", "type": "feature"},
                       {"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        self.assertEqual(json.loads(r.stdout)["reason"], BLOCK_REASON)
        self.assertEqual(self.log_lines(), [STALE_LOG])

    def test_two_in_tree_entries_still_warn_with_a_third_elsewhere(self):
        """Attribution narrows the set; it does not collapse it. Two entries
        without worktrees remain unattributable to either session, so the rule
        that applies is still the WARN - and the lane in its own worktree is
        not named, because it is not a candidate.
        """
        self.green_stamp()
        self.go_stale()
        self.add_worktree("feat-elsewhere")
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-elsewhere", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | feat-a, feat-b | " + STALE],
        )

    def test_one_entry_with_its_own_worktree_does_not_block_this_tree(self):
        """The single-entry case is byte-identical ONLY when the entry could
        be the cause. A lone lane building elsewhere is a stamp fact about
        somebody else's tree, and blocking on it is the false block this
        change exists to remove.
        """
        self.green_stamp()
        self.go_stale()
        self.add_worktree("feat-elsewhere")
        self.set_tasks({"task": "feat-elsewhere", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | feat-elsewhere (all in other worktrees) | " +
             STALE],
        )

    def test_a_green_stamp_still_short_circuits_before_any_git_call(self):
        """Attribution runs only after the stamp has already failed. A green
        tree must not pay for a subprocess on every turn end, and the way to
        assert that from outside is that a green tree stays silent even with
        worktrees present.
        """
        self.add_worktree("feat-elsewhere")
        self.set_tasks({"task": "feat-elsewhere", "type": "feature"},
                       {"task": "feat-x", "type": "feature"})
        self.green_stamp()
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_a_branch_that_breaks_the_naming_canon_stays_gated(self):
        """The attribution rides on `task/<slug>` (company/GIT.md). A worktree
        on some other branch name does not match, the entry counts as in-tree,
        and the gate stays armed - fail-safe means a missed filter costs a
        false block, never a false pass.
        """
        self.green_stamp()
        self.go_stale()
        path = os.path.join(self.extra, "oddly-named")
        subprocess.run(["git", "-C", self.root, "worktree", "add", "-q", path,
                        "-b", "wip/feat-x"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        self.assertEqual(self.log_lines(), [STALE_LOG])

    def test_no_git_available_falls_back_to_the_single_entry_rule(self):
        """Fail-safe: with git off the PATH the lookup returns nothing, so
        nothing is filtered and the hook behaves exactly as it did before
        attribution existed. A hook that needed git to decide would stop
        gating the moment git moved.
        """
        self.set_tasks({"task": "feat-x", "type": "feature"})
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = self.root
        env["PATH"] = self.extra  # no git binary in here
        proc = subprocess.run(
            [sys.executable,
             os.path.join(REPO_HOOKS, "stop_gate.py")],
            input=json.dumps(self.stop_payload()),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, BLOCK_STDOUT)
        self.assertEqual(self.log_lines(), [MISSING_LOG])


class LoopProtectionAndFailOpen(StopScopeBase):
    """FR-HP-50 must not have disturbed the two safety properties."""

    def test_stop_hook_active_writes_nothing_at_all(self):
        """FR-HP-50: loop protection runs before any state is read, so a
        re-entrant Stop on a stale multi-entry tree produces no decision AND
        no WARN. A WARN here would append a line on every loop iteration.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        before = len(self.log_lines())
        r = self.run_stop(stop_hook_active=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_malformed_active_task_json_fails_open_but_says_so(self):
        """FR-HP-50 plus the L1 kernel's active_tasks_unreadable. An
        unparseable state file must let the turn finish - a hook that jammed
        every Stop on a corrupt byte would be worse than the red tree it
        guards, and the block recipe ("close YOUR entry") is unfollowable
        against a file that does not parse.

        But it must not pass SILENTLY: unreadable is not "no task in flight",
        and a gate that quietly stops gating is the exact failure this lane
        exists to remove. Exit 0, no decision, one WARN naming the file.
        """
        self.write("company/state/active-task.json", "{not json at all")
        self.green_stamp()
        self.go_stale()
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        lines = self.log_lines()
        self.assertNotIn("BLOCK", "\n".join(lines))
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(
            lines[0].startswith(
                "stop_gate | WARN | company/state/active-task.json | "
                "active-task.json does not parse after retries"),
            lines[0])

    def test_an_absent_state_file_stays_completely_silent(self):
        """The negative half of the case above, and the reason it is a
        separate test: an idle tree with no active-task.json at all is the
        normal state of most sessions. It must produce no WARN, or the log
        fills with noise on every turn of every session that has no task and
        the one line that matters stops being findable.
        """
        self.green_stamp()
        self.go_stale()
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_unreadable_active_task_json_fails_open(self):
        """FR-HP-50: same contract when the file cannot be opened at all, not
        just when its bytes are bad.
        """
        path = self.write("company/state/active-task.json",
                          json.dumps({"version": 2,
                                      "tasks": [{"task": "feat-x",
                                                 "type": "feature"}]}))
        os.chmod(path, 0o000)
        try:
            r = self.run_stop()
        finally:
            os.chmod(path, 0o644)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        lines = self.log_lines()
        self.assertNotIn("BLOCK", "\n".join(lines))
        self.assertTrue(any("does not parse after retries" in ln
                            for ln in lines), lines)


class ContentBasedFreshnessDoesNotArmTheGate(StopScopeBase):
    """The scenario that cost four ladder runs in one day: paperwork edits
    staling a green stamp and blocking the session that made them.

    L1's content-based work_hash excludes company/state, company/briefs and
    company/specs, so writing a brief or a spec is no longer "work changed".
    This asserts it end to end through the Stop hook rather than by reading
    HASH_EXCLUDES, because the constant is not the promise - the gate not
    arming is the promise.
    """

    def test_writing_a_brief_does_not_arm_the_stop_gate(self):
        self.set_tasks({"task": "feat-x", "type": "feature"})
        self.green_stamp()
        self.write("company/briefs/brief-feat-x.md", "# BRIEF\n\nmission\n")
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "", "a brief edit must not block a turn")
        self.assertEqual(self.log_lines()[before:], [])

    def test_writing_a_spec_does_not_arm_the_stop_gate(self):
        self.set_tasks({"task": "feat-x", "type": "feature"})
        self.green_stamp()
        self.write("company/specs/spec-feat-x.md", "# SPEC\n\nFR-1\n")
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_a_source_edit_still_arms_it(self):
        """The control. If everything stopped arming the gate the tests above
        would pass for the wrong reason, and the gate would be decorative.
        """
        self.set_tasks({"task": "feat-x", "type": "feature"})
        self.green_stamp()
        self.write("src/app.py", "print('changed')\n")
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)


if __name__ == "__main__":
    unittest.main()
