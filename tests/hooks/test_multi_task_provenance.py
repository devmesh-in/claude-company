#!/usr/bin/env python3
"""Multi-entry (N > 1) semantics for guard_provenance.py.

active-task.json holds N entries because the owner runs several Claude Code
sessions from one checkout. These tests pin the three things that band could
get wrong:

  - attribution: a dispatch counts for the entries the spawn prompt NAMES,
    and for nobody else (FR-MST-18)
  - the hotfix split (FR-MST-23): Mode C takes an ANY-hotfix waiver
    (RISK-MST-01, accepted), and it is the only waiver site left in this hook
  - BR-MST-02: at N == 1 every mode is byte-identical to the single-task hook

Attribution used to be observed through the execution gate, which blocked a
delegated entry with no dispatch of its own. That gate is gone, and the Mode A
drift nudge is the surviving observable of the same per-slug count: it fires
only for a self-execution entry whose OWN dispatch list is empty, so a
regression to whole-ledger matching silences it. The entries here are
self-execution for that reason.

Ledger state is only ever seeded by driving REAL Mode B payloads, never by
hand-writing the ledger, so the machinery under test is the machinery that
produced the state.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import HOOKS_DIR, run_hook  # noqa: E402
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

    def post_edit(self):
        return run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)

    def nudged(self, result):
        """The slug a Mode A invocation nudged, or None when it was silent."""
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        ctx = json.loads(
            result.stdout)["hookSpecificOutput"]["additionalContext"]
        match = re.search(r"entry '([^']*)'", ctx)
        self.assertIsNotNone(match, ctx)
        return match.group(1)

    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    # --- adherence --------------------------------------------------------
    def adherence_lines(self, action):
        marker = " | {} | ".format(action)
        return [ln for ln in self.adherence().splitlines() if marker in ln]

    def last_line(self, action):
        lines = self.adherence_lines(action)
        self.assertTrue(lines, "no {} line in adherence.log".format(action))
        return lines[-1]


# --------------------------------------------------------------------------
# FR-MST-18 - per-slug dispatch attribution
#
# dispatches_for's own docstring says a regression to whole-ledger matching
# must fail a witness. These are that witness. The observable is the Mode A
# drift nudge, which fires only for a self-execution entry with ZERO
# dispatches OF ITS OWN, so crediting one entry's dispatch to another shows up
# here as a nudge that stops firing or names the wrong slug.
# --------------------------------------------------------------------------
class TestPerSlugAttribution(MultiBase):
    def test_a_dispatch_naming_only_b_leaves_a_uncredited(self):
        """The proof that attribution is per slug.

        Two self-execution entries, ONE dispatch whose spawn prompt names only
        task/feat-b. feat-a is still idle, so the nudge fires and names
        feat-a; a whole-ledger dispatch count would credit feat-a with feat-b's
        dispatch and nothing would fire at all.
        """
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))
        self.dispatch("take task/feat-b into a worktree and build it")

        ledger = gp.read_ledger(self.root)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-b")), 1)
        self.assertEqual(gp.dispatches_for(ledger, "feat-a"), [])

        self.assertEqual(self.nudged(self.post_edit()), "feat-a")
        line = self.last_line("NUDGE")
        self.assertIn("feat-a", line)
        self.assertNotIn("feat-b", line)

        # A gets a dispatch of its own and the team is no longer idle for
        # either entry, so the next edit is silent.
        self.dispatch("take task/feat-a into a worktree and build it")
        self.assertEqual(len(gp.dispatches_for(gp.read_ledger(self.root),
                                               "feat-a")), 1)
        self.assertIsNone(self.nudged(self.post_edit()))

    def test_a_second_entry_without_a_dispatch_of_its_own_is_still_idle(self):
        # The nudge condition is evaluated per entry: feat-a is satisfied and
        # silent, feat-b has no dispatch of its own and is not.
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))
        self.dispatch("build task/feat-a")
        self.assertEqual(self.nudged(self.post_edit()), "feat-b")

    def test_a_dispatch_naming_no_active_slug_credits_nobody(self):
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))
        self.dispatch("go and do the needful")

        raw = self.read_ledger_raw()
        self.assertEqual(len(raw["unattributed_dispatches"]), 1)
        self.assertEqual(raw["tasks"]["feat-a"]["dispatches"], [])
        self.assertEqual(raw["tasks"]["feat-b"]["dispatches"], [])
        # the false negative is diagnosable from the log ...
        self.assertIn("no active task", self.last_line("DISPATCH"))
        # ... and it leaves both entries idle, so the nudge still fires
        self.assertEqual(self.nudged(self.post_edit()), "feat-a")

    def test_description_field_also_attributes(self):
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.selfbuilt("feat-a"), self.selfbuilt("feat-b"))
        self.dispatch("build it", description="task/feat-a and task/feat-b")
        ledger = gp.read_ledger(self.root)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-a")), 1)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-b")), 1)
        self.assertIsNone(self.nudged(self.post_edit()))

    def test_single_entry_attributes_unconditionally(self):
        """N == 1 does no prompt matching at all - today's behaviour."""
        self.init_git()
        self.set_manifest()
        self.set_task(self.selfbuilt("feat-a"))
        self.dispatch("go and do the needful")  # names nothing
        self.assertEqual(len(self.record("feat-a")["dispatches"]), 1)
        self.assertEqual(self.read_ledger_raw()["unattributed_dispatches"], [])
        self.assertIsNone(self.nudged(self.post_edit()))

    def test_a_slugless_entry_is_never_credited_a_dispatch_at_n_over_one(self):
        """OQ-MST-03, fail-closed: attribution needs a slug in the spawn text,
        so a slugless entry can never be credited a dispatch once a second
        entry exists.

        The gate that used to observe this was the execution gate. What
        carries it now is credited_dispatches itself, driven off a ledger this
        hook really wrote: the SAME dispatch that counts for the slugless
        entry alone stops counting the moment it is one of two, even though
        the dispatch is still sitting under its own ledger key.
        """
        self.init_git()
        self.set_manifest()
        slugless = {"type": "feature", "brief": "company/briefs/b.md",
                    "execution": "self", "execution_why": "glue only"}
        self.set_task(slugless)
        self.dispatch("build it")  # N == 1: credited unconditionally

        ledger = gp.read_ledger(self.root)
        self.assertEqual(len(gp.dispatches_for(ledger, "")), 1)
        self.assertEqual(
            len(gp.credited_dispatches(ledger, slugless, [slugless])), 1
        )

        other = self.selfbuilt("feat-a")
        self.assertEqual(
            gp.credited_dispatches(ledger, slugless, [slugless, other]), [],
            "a slugless entry must not be credited a dispatch at N > 1",
        )
        # feat-a is not credited it either - the dispatch named no slug.
        self.assertEqual(
            gp.credited_dispatches(ledger, other, [slugless, other]), []
        )


# --------------------------------------------------------------------------
# RISK-MST-01 - the ANY-hotfix waiver, accepted at Mode C and nowhere else in
# this hook now that the execution gate is gone
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
# BR-MST-02 - the N == 1 identity rule, across all four surviving modes
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

    def both_ways(self, obj, drive):
        seen = []
        for as_list in (False, True):
            self.reset_state()
            if as_list:
                self.set_tasks(obj)
            else:
                self.set_task(obj)
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


if __name__ == "__main__":
    import unittest
    unittest.main()
