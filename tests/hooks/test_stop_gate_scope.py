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

import ast
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


class CeremonyDoctrineMatchesTheGuard(StopScopeBase):
    """Canon and mechanism are pinned to each other, which is the whole point
    of this lane. DECISIONS #19 (a) authorized "a quick entry needs no brief";
    the clause is deliberately NOT in the doctrine because guard_spec exempts
    only hotfix, and doctrine the hooks contradict is worse than no doctrine.
    """

    def test_quick_needs_a_brief_in_the_code_and_in_the_prose_together(self):
        """Reproduction, CEO-verified 2026-08-13: a briefless quick entry
        blocks a source edit made by a SIBLING session whose own brief is
        fine, because the check is an ALL over non-hotfix entries and blocks
        the edit rather than the offending entry.

        When L4 lands the quick exemption in guard_spec, this test fails - and
        the failure is the instruction to restore the doctrine clause in the
        same wave, instead of discovering the divergence a third time.
        """
        self.write("company/briefs/brief-feat-a.md", "a brief\n")
        self.set_tasks(
            {"task": "feat-a", "type": "feature",
             "brief": "company/briefs/brief-feat-a.md"},
            {"task": "quick-b", "type": "quick"},
        )
        r = run_hook("guard_spec.py",
                     self.edit_payload("Edit", "src/app.py", "x"), self.root)
        guard_requires_a_brief = r.returncode == 2
        prose = doc("company/METHOD.md") + doc("ORCHESTRATOR.md")
        doctrine_says_no_brief_needed = "need no brief" in prose \
            or "needs no brief" in prose
        self.assertEqual(
            guard_requires_a_brief, not doctrine_says_no_brief_needed,
            "guard_spec and the ceremony doctrine disagree about whether a "
            "quick entry needs a brief. guard_spec blocks the edit: {}. The "
            "doctrine says no brief is needed: {}. Make them agree - if the "
            "guard now exempts quick, restore the clause to METHOD.md's "
            "ceremony table and ORCHESTRATOR's classify step; if it does not, "
            "the clause stays out.".format(
                guard_requires_a_brief, doctrine_says_no_brief_needed))


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


# --------------------------------------------------------------------------
# Doctrine assertions - FR-HP-51 to FR-HP-65, plus the two items authorized by
# DECISIONS #19. Each doctrine file is read and its required clause asserted.
#
# These are deliberately clause-level rather than word-level: a doctrine file
# is enforcement here only because a hook, a gate or an agent reads it, so what
# is asserted is the sentence a reader has to act on. A rewrite that keeps the
# rule keeps these green; a rewrite that drops the rule turns them red, which
# is the whole point - this program exists because canon drifted from the code
# three separate times and nothing mechanical noticed.
# --------------------------------------------------------------------------

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def doc(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


class EveryHookIsLoadable(unittest.TestCase):
    """A hook with a syntax error does not fail loudly - it fails ABSENT.

    Hooks fail open by design, but a SyntaxError never reaches that design:
    python exits 1, and only exit 2 blocks, so the guarded action proceeds
    with nothing in the session saying enforcement stopped existing. The CI
    job `hooks` is the real gate (it survives a test suite this defect would
    also break); this is the same assertion where a developer meets it first,
    seconds after the edit instead of minutes after the push.
    """

    def test_every_hook_parses_on_the_documented_python_floor(self):
        """ast.parse, never import: importing runs module-level code and
        several hooks read stdin. feature_version pins the 3.8 floor CLAUDE.md
        documents, so syntax newer than the floor fails here rather than on
        the machine of whoever installed this.
        """
        names = sorted(n for n in os.listdir(REPO_HOOKS) if n.endswith(".py"))
        self.assertTrue(names, "no hooks found under " + REPO_HOOKS)
        failures = []
        for name in names:
            path = os.path.join(REPO_HOOKS, name)
            with open(path, "rb") as fh:
                source = fh.read()
            try:
                ast.parse(source, filename=path, feature_version=(3, 8))
            except SyntaxError as exc:
                failures.append("{} line {}: {}".format(name, exc.lineno,
                                                        exc.msg))
        self.assertEqual(
            failures, [],
            "these hooks do not parse, so they enforce nothing and say so to "
            "nobody: " + "; ".join(failures))


class DoctrineClauses(unittest.TestCase):
    def assertClauses(self, rel, fr, clauses):
        text = doc(rel)
        for clause in clauses:
            self.assertIn(
                clause, text,
                "{}: {} lost its required clause: {!r}".format(rel, fr,
                                                               clause))

    # -- ORCHESTRATOR.md ---------------------------------------------------

    def test_fr_hp_55_parallel_discipline(self):
        """FR-HP-55: a wave dispatched one lane per turn serializes the wave.
        The four habits are the difference between structural parallelism and
        realized parallelism.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-55", [
            "## Parallel discipline",
            "in ONE message",
            "never idle while lanes build",
            "per-lane",
            "interrupt-priority",
        ])

    def test_fr_hp_56_dont_fight_the_harness(self):
        """FR-HP-56: every rule here was paid for by a session that decoded a
        guard instead of following its recipe.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-56", [
            "## Don't fight the harness",
            "the block message is the recipe",
            "stales the audit",
            "blocking twice on the same cause",
            "never edit, disable, or tunnel around a guard",
        ])

    def test_fr_hp_64_lost_dispatch_credit_repair(self):
        """FR-HP-64: the ledger is checksum-sealed, so a hand edit does not
        just risk a wrong record - it wipes the audit history. The procedure
        has to name the lock and the REPAIR line or it is not reproducible.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-64", [
            "state_lock",
            "REPAIR line",
            "resets the checksum",
        ])

    def test_fr_hp_65_advisory_in_both_files(self):
        """FR-HP-65: the advisory distinguishes BUILDING from INTEGRATING.
        Collapsing the two would either ban concurrency the lock layer exists
        to support, or permit the one collision it cannot make safe.
        """
        for rel in ("ORCHESTRATOR.md", "company/METHOD.md"):
            self.assertClauses(rel, "FR-HP-65", [
                "one integrating session per repository",
                "index.lock",
            ])
            text = doc(rel)
            self.assertTrue(
                "BUILDING" in text or "building" in text,
                "{}: FR-HP-65 advisory must distinguish building from "
                "integrating".format(rel))

    def test_fr_hp_57_archive_procedure_in_both_files(self):
        """FR-HP-57 / OQ-HP-13: the cap is prose with an archive procedure
        attached. Archiving VERBATIM is the load-bearing half - a summarized
        archive is a lossy edit of the record.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-57", [
            "company/state/archive/",
            "VERBATIM",
        ])
        self.assertClauses("company/METHOD.md", "FR-HP-57", [
            "company/state/archive/",
            "no hook and no gate enforces",
        ])

    def test_fr_hp_57_no_line_count_constant_in_any_hook(self):
        """FR-HP-57 / OQ-HP-13 negative space: DECISIONS #5 rejected numeric
        fences as an enforcement shape. This is the assertion that keeps the
        300 from migrating out of prose and into a guard later.
        """
        hooks = os.path.join(REPO, ".claude", "hooks")
        for name in sorted(os.listdir(hooks)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(hooks, name), encoding="utf-8") as f:
                for num, line in enumerate(f, 1):
                    if "300" not in line:
                        continue
                    self.assertNotIn(
                        "RESUME", line,
                        "{}:{} looks like a line-count fence".format(name, num))
                    self.assertNotIn(
                        "DECISIONS", line,
                        "{}:{} looks like a line-count fence".format(name, num))

    def test_decisions_19_spec_lite_rung(self):
        """DECISIONS #19 (a): the rung is chosen on objective conditions, and
        the escape upward is ONE-WAY. Without the one-way clause a task could
        ride a lite spec back down after touching a frozen surface, which is
        exactly the case a full spec exists for.
        """
        self.assertClauses("ORCHESTRATOR.md", "DECISIONS-19", [
            "spec-lite",
            "ONE-WAY",
            '"spec": "lite:',
        ])
        self.assertClauses("company/METHOD.md", "DECISIONS-19", [
            "spec-lite",
            "ONE-WAY",
        ])

    def test_brief_grant_exception_is_resolved_one_way(self):
        """Brief scope item 9: ORCHESTRATOR said the CEO applies frozen-surface
        changes itself while a sealed brief had granted a frozen file to a lane
        outright. The doctrine now names the exception instead of leaving two
        rules that contradict each other.
        """
        self.assertClauses("ORCHESTRATOR.md", "CR-2-reconciliation", [
            "brief-grant exception",
            "exactly one lane",
        ])

    # -- company/METHOD.md -------------------------------------------------

    def test_fr_hp_63_state_table_and_content_freshness(self):
        """FR-HP-63: gates.log and gate-output/ are state the company keeps,
        with the runner as their only writer. The negative half matters more:
        no sentence may claim a commit stales a green stamp, because freshness
        is content-based and that false claim costs a rerun per commit.
        """
        self.assertClauses("company/METHOD.md", "FR-HP-63", [
            "gates.log",
            "gate-output/",
        ])
        for num, line in enumerate(doc("company/METHOD.md").splitlines(), 1):
            if "commit" in line and "stales" in line:
                self.fail("company/METHOD.md:{} claims a commit stales the "
                          "stamp: {!r}".format(num, line.strip()))

    # -- company/GATES.md --------------------------------------------------

    def test_fr_hp_62_runner_contract(self):
        """FR-HP-62: quiet-pass output, the gates.log history and its single
        writer, and G7 grown to the full wiring assertion.
        """
        self.assertClauses("company/GATES.md", "FR-HP-62", [
            "gate-output/",
            "gates.log",
            "full wiring",
        ])

    def test_fr_hp_28_root_resolution_is_documented_from_the_script(self):
        """FR-HP-28 as SHIPPED (coordinator correction of 2026-08-13, which
        supersedes the spec text): the runner resolves its root from the
        runner's own location, never from git. The earlier git rev-parse rule
        gated the wrong tree when the installer suite ran the runner by
        absolute path against a non-git fixture, and it cost 13 CI failures.
        """
        text = doc("company/GATES.md")
        self.assertIn("RUNNER'S OWN LOCATION", text)
        self.assertIn("Git is never consulted", text)
        self.assertNotIn("rev-parse", text)
        self.assertIn("stamps THAT worktree", text)

    def test_fr_hp_58_changed_screen_evidence_in_both_files(self):
        """FR-HP-58: four states per CHANGED screen. A full sweep on every task
        is the ceremony this decision removed, so the on-demand exception has
        to be written down or the sweep creeps back.
        """
        for rel in ("company/GATES.md", ".claude/agents/qa-engineer.md"):
            self.assertClauses(rel, "FR-HP-58", [
                "CHANGED screen",
                "full-surface sweep",
            ])

    # -- company/templates/BRIEF-TEMPLATE.md -------------------------------

    def test_fr_hp_60_test_quality_dod(self):
        """FR-HP-60: the four test-quality clauses. The deletion clause is the
        one that keeps a rework diff honest - accreted dead tests read as
        coverage of behavior that no longer exists.
        """
        self.assertClauses("company/templates/BRIEF-TEMPLATE.md", "FR-HP-60", [
            "falsifiable",
            "restating-implementation",
            "extend the existing test file",
            "accreting dead tests is a defect",
        ])

    # -- .claude/agents/ ---------------------------------------------------

    def test_fr_hp_51_auditor_verifies_the_stamp(self):
        """FR-HP-51: the auditor checking the stamp instead of re-running the
        ladder the CEO runs in parallel is what makes an audit cheap enough to
        be mandatory in the high band.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-51", [
            "gate_stamp.py --check",
            "missing, red, or stale",
        ])

    def test_fr_hp_52_delta_scoped_re_audit(self):
        """FR-HP-52: a re-audit is a FRESH DISPATCH. A SendMessage resume fires
        no PostToolUse event, so the ledger records nothing and the tree reads
        as un-audited no matter what the auditor concluded.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-52", [
            "FRESH DISPATCH",
            "never a SendMessage resume",
            "PostToolUse",
        ])

    def test_fr_hp_53_auditor_grades_test_value(self):
        """FR-HP-53: on a rework diff the deleted tests are the correct ones.
        Grading volume rewards exactly the padding this clause calls a finding.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-53", [
            "test VALUE",
            "tautological",
            "deleted together with the behavior",
        ])

    def test_fr_hp_54_verdict_vocabulary_cannot_poison_the_ledger(self):
        """FR-HP-54: guard_provenance classifies an audit response by naive
        substring match on the negative token, so an auditor that quotes its
        own vocabulary records a refusal against a passing tree. The file may
        name the token on exactly ONE line - the line forbidding it.
        """
        text = doc(".claude/agents/auditor.md")
        hits = [ln for ln in text.splitlines() if "DO-NOT-SHIP" in ln]
        self.assertEqual(
            len(hits), 1,
            "auditor.md must name the forbidden token on exactly one line, "
            "found {}: {!r}".format(len(hits), hits))
        # The forbidding sentence wraps, so match on the reflowed paragraph
        # rather than the line: what matters is that the one mention is the
        # prohibition, not where the line break falls.
        flat = " ".join(text.split())
        self.assertIn("Never emit the token `DO-NOT-SHIP` in your prose", flat,
                      "the single DO-NOT-SHIP mention must be the sentence "
                      "forbidding it, got: {!r}".format(hits[0]))
        for token in ("SHIP", "SHIP-WITH-FIXES", "HALT"):
            self.assertIn(token, text)
        verdict = text.split("## Verdict", 1)
        self.assertEqual(len(verdict), 2, "auditor.md lost its Verdict section")
        self.assertNotIn("DO-NOT-SHIP", verdict[1])

    def test_fr_hp_54_the_verdict_section_survives_the_real_parser(self):
        """FR-HP-54 second AC, unblocked by L2's audit_verdict landing on main
        (BR-HP-04). Two directions, and both matter:

        the auditor's own Verdict section, fed to the shipping parser, must NOT
        record as a rejection - that is the trap that cost four blocked commits
        against four passing audits;

        and a real HALT report must STILL record as one, because swapping the
        vocabulary would otherwise disarm the provenance gate rather than fix
        it. fresh_audit accepts every verdict except do-not-ship, so a HALT
        that parsed as unknown would let a rejected tree commit.
        """
        sys.path.insert(0, REPO_HOOKS)
        import guard_provenance  # noqa: E402

        section = doc(".claude/agents/auditor.md").split("## Verdict", 1)[1]
        self.assertNotEqual(guard_provenance.audit_verdict(section),
                            "do-not-ship")
        self.assertEqual(guard_provenance.audit_verdict("Verdict: HALT"),
                         "do-not-ship")

    def test_fr_hp_59_docs_librarian_is_batched(self):
        """FR-HP-59: the fork changed the doctrine and left the agent
        definition contradicting it. The description is what the dispatcher
        reads, so the fix is not done until "after any merge" is gone from it.
        """
        text = doc(".claude/agents/docs-librarian.md")
        self.assertIn("BATCHED", text)
        self.assertIn("once per delivery", text)
        self.assertNotIn("after any merge", text)
        description = text.split("---", 2)[1]
        self.assertIn("BATCHED", description,
                      "the BATCHED rule must be in the description "
                      "frontmatter, which is what the dispatcher reads")

    def test_fr_hp_61_tech_lead_rules(self):
        """FR-HP-61: spawn all developers in one message, QA the first finished
        surface, scale the review to risk.
        """
        self.assertClauses(".claude/agents/tech-lead.md", "FR-HP-61", [
            "in ONE message",
            "FIRST finished surface",
            "Scale the review to risk",
        ])

    # -- wiring ------------------------------------------------------------

    def test_stop_gate_is_still_wired_into_settings(self):
        """FR-HP-50 AC: scoping is not un-wiring. A downstream fork removed the
        Stop binding entirely; DECISIONS #18 refused that, because stop_gate is
        the only check on three paths guard_commit cannot see.
        """
        settings = doc(".claude/settings.json")
        self.assertIn("stop_gate.py", settings)
        data = json.loads(settings)
        stop = data["hooks"]["Stop"]
        commands = [h.get("command", "")
                    for group in stop for h in group.get("hooks", [])]
        self.assertTrue(
            any("stop_gate.py" in cmd for cmd in commands),
            "stop_gate.py must stay bound to the Stop event: {}".format(
                commands))


if __name__ == "__main__":
    unittest.main()
