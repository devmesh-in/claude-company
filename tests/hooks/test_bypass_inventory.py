#!/usr/bin/env python3
"""The ANY-bypass inventory: which gates a hotfix entry waives, and which it
does not.

FR-MST-23, the hotfix split, is the spine of multi-session safety, and it is
easy to erode one hook at a time. Two DIFFERENT things share the word
"hotfix":

  EXEMPTION types are PER-ENTRY. A gate that skips because the single task's
  type is exempt now evaluates the NON-EXEMPT entries and blocks if any fails.
  Sites: guard_spec and the FR-DE-15 tracking gate in Mode B-pre.
  (guard_tests never honored hotfix at all, and still does not. Two further
  sites are gone: the standalone Stop-time gate with DECISIONS #20, and the
  Mode D close gate with the provenance salvage.)

  WAIVER bypasses are ANY, and exist ONLY where blocking a declared production
  emergency behind an UNRELATED entry is the worse failure.
  Sites: guard_models, guard_commit, Mode C. This is RISK-MST-01, an ACCEPTED
  weakening: with [feature-a, hotfix-b] these three are waived where
  [feature-a] alone would arm them, so unrelated feature work rides the
  emergency waiver. Every one of them logs a BYPASS naming the responsible
  hotfix entry, which is the mitigation. The fourth site was Mode E, and it
  went with the execution gate.

This file is the inventory. It asserts the ANY set is EXACTLY those three and
that the other two still block, so that widening a fourth gate has to be a
conscious edit against a red test rather than silent drift. The tests here
deliberately assert that the accepted weakenings DO happen - do not "fix" them
into blocks.

Fixture throughout: entry A is a feature armed to block, entry B is a hotfix.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v1_v2_parity import ParityBase, git  # noqa: E402

HOTFIX = {"task": "hotfix-b", "type": "hotfix"}


class InventoryBase(ParityBase):
    def arm(self, entry_a):
        """Entry A (armed to block) alongside the hotfix entry B."""
        self.w("company/state/active-task.json",
               json.dumps({"version": 2, "tasks": [entry_a, HOTFIX]}))

    def alone(self, entry_a):
        """The control: entry A on its own, with no hotfix to ride."""
        self.w("company/state/active-task.json",
               json.dumps({"version": 2, "tasks": [entry_a]}))

    def feature(self, **extra):
        e = {"task": "feat-a", "type": "feature",
             "brief": "company/briefs/brief-feat-parity.md"}
        e.update(extra)
        return e


# --------------------------------------------------------------------------
# The three ANY-bypass (waiver) sites. RISK-MST-01 - assert it DOES bypass.
# --------------------------------------------------------------------------
class TestAnyBypassSites(InventoryBase):
    def test_guard_models_is_an_any_site(self):
        payload = self.spawn_payload(model="sonnet")

        self.reset_state()
        self.alone(self.feature())
        self.assertEqual(self.capture("guard_models.py", payload)["rc"], 2,
                         "control: alone, the override must block")

        self.reset_state()
        self.arm(self.feature())
        got = self.capture("guard_models.py", payload)
        self.assertEqual(got["rc"], 0, "RISK-MST-01: ANY hotfix waives")
        self.assertIn("BYPASS", got["adherence"])
        self.assertIn("hotfix-b", got["adherence"],
                      "the BYPASS line must name the responsible entry")

    def test_guard_commit_is_an_any_site(self):
        payload = self.bash_payload("git commit -m x")

        self.reset_state()
        self.alone(self.feature())
        self.assertEqual(self.capture("guard_commit.py", payload)["rc"], 2)

        self.reset_state()
        self.arm(self.feature())
        got = self.capture("guard_commit.py", payload)
        self.assertEqual(got["rc"], 0, "RISK-MST-01: ANY hotfix waives")
        self.assertIn("hotfix-b", got["adherence"])

    def test_mode_c_is_an_any_site(self):
        payload = self.bash_payload("git commit -m x")
        armed = self.feature(execution="self", execution_why="glue")

        self.reset_state()
        self.alone(armed)
        self.assertEqual(
            self.capture("guard_provenance.py", payload)["rc"], 2)

        self.reset_state()
        self.arm(armed)
        got = self.capture("guard_provenance.py", payload)
        self.assertEqual(got["rc"], 0, "RISK-MST-01: ANY hotfix waives")
        self.assertIn("hotfix-b", got["adherence"])


# --------------------------------------------------------------------------
# The two per-entry-exemption sites. A hotfix entry exempts ITSELF and
# nothing else - the non-exempt entry is still evaluated and still blocks.
# --------------------------------------------------------------------------
class TestPerEntryExemptionSites(InventoryBase):
    def test_guard_spec_is_not_an_any_site(self):
        self.reset_state()
        self.arm({"task": "feat-a", "type": "feature"})  # no brief
        got = self.capture("guard_spec.py", self.edit_payload("src/app.py"))
        self.assertEqual(got["rc"], 2,
                         "a hotfix entry must NOT waive spec-before-code "
                         "for an unrelated briefless entry")
        self.assertIn("feat-a", got["stderr"] + got["adherence"],
                      "the block must name which entry caused it")

    def test_guard_tests_never_honors_hotfix(self):
        self.reset_state()
        self.arm(self.feature())  # neither entry opens test_scope
        got = self.capture("guard_tests.py",
                           self.edit_payload("tests/test_x.py"))
        self.assertEqual(got["rc"], 2,
                         "guard_tests never reads hotfix and must still block")

    def test_mode_b_pre_tracking_is_not_an_any_site(self):
        """FR-DE-15 at the spawn: a hotfix entry does not start an unrelated
        untracked feature's work.

        Mode B-pre is the one place the build had to CHOOSE. It sits in the
        same function as an ANY-hotfix bypass log, so making the tracking gate
        ANY too would have been the natural-looking edit - and it would have
        been a fifth waiver site nobody named. The gate runs over the
        feature/program entries and blocks if ANY of them is untracked; the
        hotfix entry is simply not one of the entries it evaluates.
        """
        # PR mode: the FR-DE-15 gate is only live with an origin remote.
        git(self.root, "remote", "add", "origin", "https://example.com/x.git")
        payload = self.spawn_payload(role="developer",
                                     prompt="build task/feat-a per its brief")
        untracked = {"task": "feat-a", "type": "feature"}

        self.reset_state()
        self.alone(untracked)
        self.assertEqual(self.capture("guard_provenance.py", payload)["rc"], 2,
                         "control: alone, the untracked spawn must block")

        self.reset_state()
        self.arm(dict(untracked, issues=[42]))
        self.assertEqual(self.capture("guard_provenance.py", payload)["rc"], 0,
                         "control: the same two entries with feat-a TRACKED "
                         "allow, so the block below is the tracking gate and "
                         "nothing else about this fixture")

        self.reset_state()
        self.arm(untracked)
        got = self.capture("guard_provenance.py", payload)
        self.assertEqual(got["rc"], 2,
                         "a hotfix entry must NOT waive FR-DE-15 tracking for "
                         "an unrelated untracked feature entry")
        self.assertIn("feat-a", got["stderr"] + got["adherence"],
                      "the block must name which entry caused it")


# --------------------------------------------------------------------------
# RISK-MST-02: the ANY test_scope grant. The other accepted weakening.
# --------------------------------------------------------------------------
class TestAnyTestScopeGrant(InventoryBase):
    def test_any_entry_opens_test_scope_and_the_grant_is_logged(self):
        payload = self.edit_payload("tests/test_x.py")

        self.reset_state()
        self.alone(self.feature())
        self.assertEqual(self.capture("guard_tests.py", payload)["rc"], 2,
                         "control: no grant anywhere, the edit blocks")

        self.reset_state()
        self.w("company/state/active-task.json", json.dumps({
            "version": 2,
            "tasks": [self.feature(),
                      {"task": "other-b", "type": "feature",
                       "test_scope": True}]}))
        got = self.capture("guard_tests.py", payload)
        self.assertEqual(got["rc"], 0,
                         "RISK-MST-02: ANY entry's test_scope opens the grant")
        self.assertIn("GRANT", got["adherence"],
                      "the grant must be logged before allowing")
        self.assertIn("other-b", got["adherence"],
                      "the GRANT line must name the GRANTING entry")


if __name__ == "__main__":
    import unittest
    unittest.main()
