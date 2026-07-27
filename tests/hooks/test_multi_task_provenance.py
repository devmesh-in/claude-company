#!/usr/bin/env python3
"""Multi-entry (N > 1) semantics for guard_provenance.py.

active-task.json holds N entries because the owner runs several Claude Code
sessions from one checkout. These tests pin the four things that band could
get wrong:

  - attribution: a dispatch counts for the entries the spawn prompt NAMES,
    and for nobody else (FR-MST-18)
  - the hotfix split (FR-MST-23): Mode C and Mode E take an ANY-hotfix waiver
    (RISK-MST-01, accepted); Mode D takes a PER-ENTRY exemption and still
    blocks while a non-exempt entry is in flight
  - ALL semantics in Mode E: a second entry can only make the gate block MORE
  - BR-MST-02: at N == 1 every mode is byte-identical to the single-task hook

Ledger state is only ever seeded by driving REAL Mode B payloads, never by
hand-writing the ledger, so the machinery under test is the machinery that
produced the state.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import HOOKS_DIR, git, run_hook  # noqa: E402
from test_guard_provenance import HOOK, ProvBase  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import guard_provenance as gp  # noqa: E402


class MultiBase(ProvBase):
    # --- fixtures ---------------------------------------------------------
    def entry(self, slug, **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        return obj

    def delegated(self, slug, **extra):
        return self.entry(slug, execution="delegated",
                          execution_why="lead owns", **extra)

    def selfbuilt(self, slug, **extra):
        return self.entry(slug, execution="self", execution_why="glue only",
                          **extra)

    def hotfix(self, slug):
        return {"task": slug, "type": "hotfix"}

    def quick(self, slug):
        return {"task": slug, "type": "quick"}

    # --- drivers ----------------------------------------------------------
    def spawn_payload(self, prompt, role="tech-lead", description=None):
        ti = {"subagent_type": role, "prompt": prompt}
        if description is not None:
            ti["description"] = description
        return {"hook_event_name": "PreToolUse", "tool_name": "Task",
                "tool_input": ti, "cwd": self.root}

    def dispatch(self, prompt, role="tech-lead", description=None):
        r = run_hook(HOOK, self.spawn_payload(prompt, role, description),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def source_edit(self):
        return run_hook(
            HOOK, self.edit_payload("Write", "src/app.py", "x = 1"), self.root
        )

    def post_edit(self):
        return run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)

    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def stop(self):
        return run_hook(HOOK, self.stop_payload(), self.root)

    # --- adherence --------------------------------------------------------
    def adherence_lines(self, action):
        marker = " | {} | ".format(action)
        return [ln for ln in self.adherence().splitlines() if marker in ln]

    def last_line(self, action):
        lines = self.adherence_lines(action)
        self.assertTrue(lines, "no {} line in adherence.log".format(action))
        return lines[-1]


# --------------------------------------------------------------------------
# FR-MST-18 / FR-MST-22 step 7 - per-slug dispatch attribution
# --------------------------------------------------------------------------
class TestPerSlugAttribution(MultiBase):
    def test_a_dispatch_naming_only_b_leaves_a_blocked(self):
        """The proof that attribution is per slug.

        Two delegated entries, ONE dispatch whose spawn prompt names only
        task/feat-b. A main-checkout source edit must still block, and the
        block must name feat-a - the entry that has no dispatch of its own.
        A whole-ledger dispatch count would allow this edit, which is the
        exact regression this test exists to catch.
        """
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.delegated("feat-a"), self.delegated("feat-b"))
        self.dispatch("take task/feat-b into a worktree and build it")

        ledger = gp.read_ledger(self.root)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-b")), 1)
        self.assertEqual(gp.dispatches_for(ledger, "feat-a"), [])

        r = self.source_edit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("feat-a", r.stderr)
        self.assertNotIn("feat-b", r.stderr)
        line = self.last_line("BLOCK")
        self.assertIn("feat-a", line)
        self.assertNotIn("feat-b", line)

        # A gets a dispatch of its own and the same edit flows.
        self.dispatch("take task/feat-a into a worktree and build it")
        self.assertEqual(len(gp.dispatches_for(gp.read_ledger(self.root),
                                               "feat-a")), 1)
        r = self.source_edit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_second_delegated_entry_without_a_dispatch_blocks(self):
        # Mode E step 7 is per entry: feat-a is satisfied, feat-b is not, and
        # one unsatisfied entry blocks the tree.
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.delegated("feat-a"), self.delegated("feat-b"))
        self.dispatch("build task/feat-a")
        r = self.source_edit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("feat-b", r.stderr)
        self.assertNotIn("feat-a", r.stderr)

    def test_a_dispatch_naming_no_active_slug_credits_nobody(self):
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.delegated("feat-a"), self.delegated("feat-b"))
        self.dispatch("go and do the needful")

        raw = self.read_ledger_raw()
        self.assertEqual(len(raw["unattributed_dispatches"]), 1)
        self.assertEqual(raw["tasks"]["feat-a"]["dispatches"], [])
        self.assertEqual(raw["tasks"]["feat-b"]["dispatches"], [])
        # the false negative is diagnosable from the log ...
        self.assertIn("no active task", self.last_line("DISPATCH"))
        # ... and it satisfies neither entry
        self.assertEqual(self.source_edit().returncode, 2)

    def test_description_field_also_attributes(self):
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.delegated("feat-a"), self.delegated("feat-b"))
        self.dispatch("build it", description="task/feat-a and task/feat-b")
        ledger = gp.read_ledger(self.root)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-a")), 1)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-b")), 1)
        self.assertEqual(self.source_edit().returncode, 0)

    def test_single_entry_attributes_unconditionally(self):
        """N == 1 does no prompt matching at all - today's behaviour."""
        self.init_git()
        self.set_manifest()
        self.set_task(self.delegated("feat-a"))
        self.dispatch("go and do the needful")  # names nothing
        self.assertEqual(len(self.record("feat-a")["dispatches"]), 1)
        self.assertEqual(self.read_ledger_raw()["unattributed_dispatches"], [])
        self.assertEqual(self.source_edit().returncode, 0)

    def test_slugless_delegated_entry_blocks_at_n_over_one(self):
        """OQ-MST-03, fail-closed: attribution needs a slug in the spawn
        prompt, so a slugless delegated entry can never be credited a dispatch
        and keeps blocking until it is given a slug.
        """
        self.init_git()
        self.set_manifest()
        slugless = {"type": "feature", "brief": "company/briefs/b.md",
                    "execution": "delegated", "execution_why": "lead owns"}
        self.set_tasks(self.delegated("feat-a"), slugless)
        self.dispatch("build task/feat-a")
        r = self.source_edit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("<task-slug>", r.stderr)


# --------------------------------------------------------------------------
# RISK-MST-01 - the ANY-hotfix waiver, accepted at Mode C and Mode E ONLY
# --------------------------------------------------------------------------
class TestHotfixWaiver(MultiBase):
    def test_mode_c_any_hotfix_bypasses_the_commit_gate(self):
        """The weakening is deliberate and must actually happen: one commit
        writes one tree, and blocking a declared production emergency behind
        an unrelated entry is the worse failure. It is never silent.
        """
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feature-a"), self.hotfix("hotfix-b"))
        self.stage_source()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hotfix-b", self.last_line("BYPASS"))

    def test_mode_c_without_the_hotfix_entry_blocks(self):
        # the counterfactual for the test above: the waiver is what allowed it
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feature-a"))
        self.stage_source()
        self.assertEqual(self.commit().returncode, 2)

    def test_mode_e_any_hotfix_bypasses_the_execution_gate(self):
        self.init_git()
        self.set_manifest()
        # feature-a has no execution decision, so it would block on its own
        self.set_tasks(self.entry("feature-a"), self.hotfix("hotfix-b"))
        r = self.source_edit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hotfix-b", self.last_line("BYPASS"))

    def test_mode_e_without_the_hotfix_entry_blocks(self):
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.entry("feature-a"))
        self.assertEqual(self.source_edit().returncode, 2)


# --------------------------------------------------------------------------
# FR-MST-21 - Mode D exempts per ENTRY and is NOT an ANY-hotfix site
# --------------------------------------------------------------------------
class TestCloseGatePerEntryExemption(MultiBase):
    def test_quick_beside_a_feature_still_blocks(self):
        """The exemption belongs to the quick entry, not to the tree."""
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.quick("quick-a"), self.selfbuilt("feature-b"))
        self.stage_source()
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("feature-b", decision["reason"])
        self.assertNotIn("quick-a", decision["reason"])
        self.assertIn("feature-b", self.last_line("BLOCK"))

    def test_hotfix_beside_a_feature_still_blocks(self):
        # Mode D takes no ANY-hotfix waiver: a hotfix entry does not close a
        # feature entry's audit debt.
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.hotfix("hotfix-a"), self.selfbuilt("feature-b"))
        self.stage_source()
        decision = json.loads(self.stop().stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("feature-b", decision["reason"])

    def test_all_entries_exempt_is_silent(self):
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.quick("quick-a"), self.hotfix("hotfix-b"))
        self.stage_source()
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")


# --------------------------------------------------------------------------
# FR-MST-22 - Mode E is ALL where it gates: more entries can only block MORE
# --------------------------------------------------------------------------
class TestExecutionGateIsAll(MultiBase):
    def test_a_second_undecided_entry_blocks_what_the_first_allowed(self):
        self.init_git()
        self.set_manifest()
        ok = self.selfbuilt("feature-ok")
        undecided = self.entry("feature-undecided")

        self.set_tasks(ok)
        self.assertEqual(self.source_edit().returncode, 0)

        self.set_tasks(ok, undecided)
        r = self.source_edit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("no execution decision", r.stderr)
        self.assertIn("feature-undecided", r.stderr)
        self.assertNotIn("feature-ok", r.stderr)

    def test_tracking_gate_fires_before_the_execution_decision(self):
        # ALL-tracking (step 5) outranks ALL-execution (step 6): an entry
        # missing BOTH is told to track first.
        self.init_git()
        self.set_manifest()
        # PR mode: the tracking gate is only live with an origin remote.
        git(self.root, "remote", "add", "origin", "https://example.com/x.git")
        self.set_tasks(self.selfbuilt("feature-a", issues=[7]),
                       self.entry("feature-b"))
        r = self.source_edit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("gh issue create", r.stderr)
        self.assertIn("feature-b", r.stderr)
        self.assertNotIn("feature-a", r.stderr)


# --------------------------------------------------------------------------
# FR-MST-19 - Mode A: per-entry nudge, at most ONE per invocation
# --------------------------------------------------------------------------
class TestPerEntryNudge(MultiBase):
    def test_one_nudge_per_invocation_and_the_next_fires_after(self):
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))

        first = self.post_edit()
        self.assertEqual(first.returncode, 0, first.stderr)
        ctx = json.loads(first.stdout)["hookSpecificOutput"][
            "additionalContext"]
        self.assertIn("'feat-a'", ctx)
        self.assertNotIn("'feat-b'", ctx)
        self.assertIsNotNone(self.record("feat-a")["nudge_state"])
        self.assertIsNone(self.record("feat-b")["nudge_state"])

        second = self.post_edit()
        ctx = json.loads(second.stdout)["hookSpecificOutput"][
            "additionalContext"]
        self.assertIn("'feat-b'", ctx)
        self.assertIsNotNone(self.record("feat-b")["nudge_state"])

        third = self.post_edit()
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertEqual(third.stdout.strip(), "")

    def test_a_dispatched_entry_never_nudges_and_clears_its_state(self):
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))
        self.post_edit()                       # arms feat-a
        self.dispatch("build task/feat-a")     # feat-a is no longer idle
        r = self.post_edit()
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("'feat-b'", ctx)
        self.assertIsNone(self.record("feat-a")["nudge_state"])

    def test_self_authored_stays_global_and_is_recorded_once(self):
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))
        self.post_edit()
        self.post_edit()
        self.assertEqual(len(self.read_ledger_raw()["self_authored"]), 1)


# --------------------------------------------------------------------------
# BR-MST-02 - the N == 1 identity rule, across all six modes
# --------------------------------------------------------------------------
class TestSingleEntryParity(MultiBase):
    """One entry written as the bare object and as the one-element list must
    produce identical exit code, stdout, stderr and adherence.log lines.
    """

    def setUp(self):
        super(TestSingleEntryParity, self).setUp()
        self.init_git()
        self.set_manifest()
        self.stage_source()

    def reset_state(self):
        for rel in ("company/state/provenance-ledger.json",
                    "company/state/adherence.log"):
            path = os.path.join(self.root, rel)
            if os.path.exists(path):
                os.remove(path)

    def untimed(self, line):
        parts = line.split(" | ")
        return " | ".join(parts[1:]) if len(parts) > 1 else line

    def both_ways(self, obj, drive, seed=None):
        seen = []
        for as_list in (False, True):
            self.reset_state()
            if as_list:
                self.set_tasks(obj)
            else:
                self.set_task(obj)
            if seed is not None:
                seed()
            r = drive()
            seen.append((
                r.returncode, r.stdout, r.stderr,
                [self.untimed(ln) for ln in self.adherence().splitlines()],
            ))
        self.assertEqual(seen[0], seen[1])
        return seen[0]

    def test_mode_a_parity(self):
        rc, stdout, _, log = self.both_ways(
            self.selfbuilt("feat-x"), self.post_edit
        )
        self.assertEqual(rc, 0)
        self.assertIn("additionalContext", stdout)
        self.assertIn("guard_provenance | NUDGE | feat-x | self-idle", log)

    def test_mode_b_pre_parity(self):
        rc, _, _, log = self.both_ways(
            self.delegated("feat-x"),
            lambda: run_hook(HOOK, self.spawn_payload("do it"), self.root),
        )
        self.assertEqual(rc, 0)
        self.assertIn(
            "guard_provenance | DISPATCH | tech-lead | builder spawn", log
        )

    def test_mode_b_post_parity(self):
        rc, _, _, log = self.both_ways(
            self.delegated("feat-x"),
            lambda: run_hook(HOOK, self.audit_payload(), self.root),
        )
        self.assertEqual(rc, 0)
        self.assertIn("guard_provenance | AUDIT | auditor | unknown", log)

    def test_mode_c_parity(self):
        rc, _, stderr, log = self.both_ways(
            self.selfbuilt("feat-x"), self.commit
        )
        self.assertEqual(rc, 2)
        self.assertIn("feat-x", stderr)
        self.assertIn(
            "guard_provenance | BLOCK | git commit | "
            "self-authored, no fresh audit", log
        )

    def test_mode_c_hotfix_bypass_parity(self):
        rc, _, _, log = self.both_ways(self.hotfix("hf"), self.commit)
        self.assertEqual(rc, 0)
        self.assertIn(
            "guard_provenance | BYPASS | git commit | hotfix mode", log
        )

    def test_mode_d_parity(self):
        rc, stdout, _, log = self.both_ways(
            self.selfbuilt("feat-x"), self.stop
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(stdout)["decision"], "block")
        self.assertIn(
            "guard_provenance | BLOCK | feat-x | "
            "self-authored, no fresh audit", log
        )

    def test_mode_d_unknown_slug_parity(self):
        # the two-argument .get is kept verbatim, so {} still renders (unknown)
        rc, stdout, _, log = self.both_ways({}, self.stop)
        self.assertEqual(rc, 0)
        self.assertIn("(unknown)", json.loads(stdout)["reason"])
        self.assertIn(
            "guard_provenance | BLOCK | (unknown) | "
            "self-authored, no fresh audit", log
        )

    def test_mode_e_parity(self):
        rc, _, stderr, log = self.both_ways(
            self.entry("feat-x"), self.source_edit
        )
        self.assertEqual(rc, 2)
        self.assertIn("feat-x", stderr)
        self.assertIn(
            "guard_provenance | BLOCK | src/app.py | no execution decision",
            log,
        )

    def test_mode_e_delegated_parity(self):
        rc, _, stderr, log = self.both_ways(
            self.delegated("feat-x"), self.source_edit
        )
        self.assertEqual(rc, 2)
        self.assertIn("feat-x", stderr)
        self.assertIn(
            "guard_provenance | BLOCK | src/app.py | "
            "delegated but no dispatch", log
        )

    def test_mode_e_hotfix_bypass_parity(self):
        rc, _, _, log = self.both_ways(self.hotfix("hf"), self.source_edit)
        self.assertEqual(rc, 0)
        self.assertIn(
            "guard_provenance | BYPASS | src/app.py | hotfix mode", log
        )

    def test_mode_e_after_dispatch_parity(self):
        self.both_ways(
            self.delegated("feat-x"),
            self.source_edit,
            seed=lambda: self.dispatch("build it"),
        )


if __name__ == "__main__":
    import unittest
    unittest.main()
