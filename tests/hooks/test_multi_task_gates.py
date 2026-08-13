#!/usr/bin/env python3
"""Multi-entry gate semantics for the five task-aware enforcement hooks.

Two properties are under test, and they pull in opposite directions:

  1. Going from one active task to N must never turn a BLOCK into an ALLOW.
     Exactly one weakening is accepted and is asserted here as a REQUIREMENT,
     not tolerated as a bug: RISK-MST-02, the ANY `test_scope` grant in
     guard_tests. RISK-MST-01 (ANY hotfix) is likewise asserted where the
     owner accepted it.
  2. BR-MST-02, the N == 1 identity rule: with exactly one entry every hook
     produces the same exit code, stdout, stderr AND appended adherence.log
     line whether the file holds the v1 single object or the v2 one-element
     list. The parity class at the bottom drives that for all five hooks.

Every decision is driven through a real hook subprocess.
"""

import json
import os
import sys

# Same-dir sibling import: works under `unittest discover -s tests/hooks` and
# under `-m unittest tests.hooks.test_multi_task_gates` - mirror the hooks'
# own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook  # noqa: E402
from test_hooks import HOOKS_DIR  # noqa: E402

# The message constants are pinned by identity, not by substring, so a
# reworded recipe cannot quietly stop being the no-brief message.
sys.path.insert(0, HOOKS_DIR)
import guard_spec  # noqa: E402

MANIFEST = {"version": 1, "roles": {"developer": "opus"}}


class MultiBase(Base):
    def task_path(self):
        return os.path.join(self.root, "company", "state", "active-task.json")

    def log_path(self):
        return os.path.join(self.root, "company", "state", "adherence.log")

    def log_lines(self):
        """adherence.log with the leading timestamp field stripped."""
        if not os.path.exists(self.log_path()):
            return []
        with open(self.log_path()) as f:
            raw = f.read().splitlines()
        return [ln.split(" | ", 1)[1] if " | " in ln else ln for ln in raw]

    def configure_gates(self):
        self.write("company/gates.config",
                   json.dumps({"gates": [{"name": "tests"}]}))

    def set_branch(self, name):
        git(self.root, "checkout", "-B", name)

    def spawn_payload(self, **fields):
        return {"hook_event_name": "PreToolUse", "tool_name": "Task",
                "tool_input": dict(fields), "cwd": self.root}

    def stop_payload(self):
        return {"hook_event_name": "Stop", "stop_hook_active": False,
                "cwd": self.root}


# --------------------------------------------------------------------------
# guard_spec - ALL over the non-hotfix entries, empty check FIRST
# --------------------------------------------------------------------------
class GuardSpecMultiEntry(MultiBase):
    def src_payload(self):
        return self.edit_payload("Write", "src/app.py", "print(1)\n")

    def test_a_second_briefless_entry_still_blocks(self):
        """A well-briefed entry must not cover for a briefless one."""
        self.write("company/briefs/brief-alpha.md", "# brief")
        self.set_tasks(
            {"task": "alpha", "type": "feature",
             "brief": "company/briefs/brief-alpha.md"},
            {"task": "beta", "type": "feature"},
        )
        r = run_hook("guard_spec.py", self.src_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("beta", r.stderr)
        # alpha is compliant; blaming it would send the fix to the wrong desk.
        self.assertNotIn("alpha", r.stderr)
        self.assertIn("BLOCK", "\n".join(self.log_lines()))

    def test_missing_brief_file_on_a_second_entry_still_blocks(self):
        self.write("company/briefs/brief-alpha.md", "# brief")
        self.set_tasks(
            {"task": "alpha", "type": "feature",
             "brief": "company/briefs/brief-alpha.md"},
            {"task": "beta", "type": "feature",
             "brief": "company/briefs/nope.md"},
        )
        r = run_hook("guard_spec.py", self.src_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("beta", r.stderr)
        self.assertIn("company/briefs/nope.md", r.stderr)

    def test_ordering_trap_no_entries_at_all_still_blocks(self):
        """FR-MST-05(a): the empty check must be evaluated FIRST.

        "ALL non-hotfix entries have a usable brief" is vacuously TRUE on an
        empty list. If the ALL ran before the empty guard, this gate would
        flip from BLOCK to ALLOW in exactly the case it exists for: nobody
        has declared a task at all. All three ways of expressing "no entries"
        must be indistinguishable.
        """
        payload = self.src_payload()
        seen = []
        for state in (None, {"version": 2, "tasks": []}, {"tasks": []}):
            if state is None:
                if os.path.exists(self.task_path()):
                    os.unlink(self.task_path())
            else:
                self.set_task(state)
            r = run_hook("guard_spec.py", payload, self.root)
            seen.append((r.returncode, r.stdout, r.stderr))
        for i, got in enumerate(seen):
            self.assertEqual(got[0], 2, "state %d allowed the write" % i)
            self.assertEqual(got[2].strip(), guard_spec.NO_BRIEF_MSG)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(seen[1], seen[2])

    def test_hotfix_exempts_itself_not_the_other_entries(self):
        """A hotfix entry is a per-entry EXEMPTION, never an ANY waiver."""
        self.set_tasks(
            {"task": "hf", "type": "hotfix"},
            {"task": "beta", "type": "feature"},
        )
        r = run_hook("guard_spec.py", self.src_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("beta", r.stderr)

    def test_all_hotfix_entries_still_bypass(self):
        self.set_tasks(
            {"task": "hf-a", "type": "hotfix"},
            {"task": "hf-b", "type": "hotfix"},
        )
        r = run_hook("guard_spec.py", self.src_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        joined = "\n".join(self.log_lines())
        self.assertIn("BYPASS", joined)
        self.assertIn("hotfix mode (hf-a, hf-b)", joined)

    def test_every_entry_briefed_allows(self):
        self.write("company/briefs/brief-alpha.md", "# brief")
        self.write("company/briefs/brief-beta.md", "# brief")
        self.set_tasks(
            {"task": "alpha", "type": "feature",
             "brief": "company/briefs/brief-alpha.md"},
            {"task": "beta", "type": "feature",
             "brief": "company/briefs/brief-beta.md"},
        )
        r = run_hook("guard_spec.py", self.src_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


# --------------------------------------------------------------------------
# guard_commit - presence arms the branch rule, ANY hotfix bypasses it
# --------------------------------------------------------------------------
class GuardCommitMultiEntry(MultiBase):
    def setUp(self):
        Base.setUp(self)
        self.init_git()
        self.set_branch("main")
        self.configure_gates()

    def commit_payload(self):
        return self.bash_payload("git commit -m wip")

    def test_single_entry_on_main_blocks_and_names_the_slug(self):
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = run_hook("guard_commit.py", self.commit_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("git switch -c task/feat-x", r.stderr)

    def test_two_entries_render_one_switch_line_each(self):
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "feat-b", "type": "feature"},
        )
        r = run_hook("guard_commit.py", self.commit_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("  git switch -c task/feat-a\n", r.stderr)
        self.assertIn("  git switch -c task/feat-b\n", r.stderr)
        self.assertIn("feat-a, feat-b", "\n".join(self.log_lines()))

    def test_recipe_truncates_display_only_beyond_three(self):
        entries = [{"task": "t%d" % i, "type": "feature"} for i in range(5)]
        self.set_tasks(*entries)
        r = run_hook("guard_commit.py", self.commit_payload(), self.root)
        # Still a BLOCK: the cap is display truncation, never a decision.
        self.assertEqual(r.returncode, 2, r.stdout)
        for slug in ("t0", "t1", "t2"):
            self.assertIn("  git switch -c task/%s\n" % slug, r.stderr)
        self.assertIn("plus 2 more", r.stderr)

    def test_risk_mst_01_any_hotfix_bypasses_the_branch_rule(self):
        """Accepted weakening: a hotfix entry waives the branch rule for the
        whole tree. Asserted as a requirement so the bypass stays visible and
        named in the adherence log.
        """
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "hotfix-b", "type": "hotfix"},
        )
        r = run_hook("guard_commit.py", self.commit_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        joined = "\n".join(self.log_lines())
        self.assertIn("BYPASS", joined)
        self.assertIn("hotfix commit on protected branch (hotfix-b)", joined)

    def test_no_entries_keeps_the_founding_commit_exemption(self):
        # Green stamp isolates the branch rule from the gate-stamp check.
        self.stamp({"gates": [{"name": "tests", "ok": True}]})
        self.set_task({"version": 2, "tasks": []})
        r = run_hook("guard_commit.py", self.commit_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_gate_stamp_check_is_still_a_tree_fact(self):
        """A second entry must not disarm the stamp requirement either."""
        self.set_branch("task/feat-a")
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "feat-b", "type": "feature"},
        )
        r = run_hook("guard_commit.py", self.commit_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("green, fresh gates", r.stderr)


# --------------------------------------------------------------------------
# stop_gate - per-entry exempt types, ANY gating entry blocks
# --------------------------------------------------------------------------
class StopGateMultiEntry(MultiBase):
    def setUp(self):
        Base.setUp(self)
        self.init_git()

    def test_quick_plus_feature_blocks_and_names_the_feature(self):
        """The exemption belongs to the quick entry, not to the tree: real
        work is in flight on a red tree, so the gate stays armed.
        """
        self.set_tasks(
            {"task": "q", "type": "quick"},
            {"task": "feat-x", "type": "feature"},
        )
        r = run_hook("stop_gate.py", self.stop_payload(), self.root)
        self.assertEqual(r.returncode, 0)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("feat-x", decision["reason"])
        self.assertNotIn("'q'", decision["reason"])

    def test_quick_plus_hotfix_exits_zero_silently(self):
        self.set_tasks(
            {"task": "q", "type": "quick"},
            {"task": "hf", "type": "hotfix"},
        )
        r = run_hook("stop_gate.py", self.stop_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    # The multi-entry block this class used to assert
    # (test_two_gating_entries_are_both_named) was DELETED with the behavior
    # it proved: FR-HP-50 replaced that block with a WARN line, because one
    # session's stale tree was blocking every other session. The N > 1 cases
    # live in tests/hooks/test_stop_gate_scope.py; duplicating them here would
    # be padding.

    def test_slugless_gating_entry_still_renders_unknown(self):
        self.set_tasks({})
        r = run_hook("stop_gate.py", self.stop_payload(), self.root)
        decision = json.loads(r.stdout)
        self.assertIn("(unknown)", decision["reason"])


# --------------------------------------------------------------------------
# guard_models - ANY hotfix bypasses the routing guard
# --------------------------------------------------------------------------
class GuardModelsMultiEntry(MultiBase):
    def setUp(self):
        Base.setUp(self)
        self.write("company/models.json", json.dumps(MANIFEST))

    def test_risk_mst_01_any_hotfix_bypasses_a_contradicting_override(self):
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "hotfix-b", "type": "hotfix"},
        )
        r = run_hook(
            "guard_models.py",
            self.spawn_payload(subagent_type="developer", model="haiku"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        joined = "\n".join(self.log_lines())
        self.assertIn("BYPASS", joined)
        self.assertIn("hotfix mode (hotfix-b)", joined)

    def test_two_non_hotfix_entries_still_block(self):
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "feat-b", "type": "feature"},
        )
        r = run_hook(
            "guard_models.py",
            self.spawn_payload(subagent_type="developer", model="haiku"),
            self.root,
        )
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_frontmatter_edit_bypassed_by_a_second_hotfix_entry(self):
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "hotfix-b", "type": "hotfix"},
        )
        r = run_hook(
            "guard_models.py",
            self.edit_payload(
                "Write", ".claude/agents/developer.md",
                "---\nname: developer\nmodel: haiku\n---\nbody\n",
            ),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hotfix mode (hotfix-b)", "\n".join(self.log_lines()))


# --------------------------------------------------------------------------
# guard_tests - RISK-MST-02, the one accepted BLOCK-to-ALLOW
# --------------------------------------------------------------------------
class GuardTestsMultiEntry(MultiBase):
    def edit_test_payload(self):
        return self.edit_payload("Write", "tests/test_x.py", "x")

    def test_risk_mst_02_any_entry_can_open_test_scope(self):
        """Accepted weakening, asserted as a requirement. Glob-scoped grants
        were scoped out by the owner, so the grant is tree-wide - which is
        why it must be logged by name.
        """
        self.set_tasks(
            {"task": "alpha", "type": "feature", "test_scope": False},
            {"task": "beta", "type": "feature", "test_scope": True},
        )
        r = run_hook("guard_tests.py", self.edit_test_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        joined = "\n".join(self.log_lines())
        self.assertIn("GRANT", joined)
        self.assertIn("test scope open (beta)", joined)
        self.assertIn("tests/test_x.py", joined)

    def test_grant_names_the_target_on_the_rm_path_too(self):
        self.set_tasks(
            {"task": "alpha", "type": "feature"},
            {"task": "beta", "type": "feature", "test_scope": True},
        )
        r = run_hook("guard_tests.py",
                     self.bash_payload("rm tests/test_x.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        joined = "\n".join(self.log_lines())
        self.assertIn("GRANT", joined)
        self.assertIn("test scope open (beta)", joined)
        self.assertIn("tests/test_x.py", joined)

    def test_no_test_scope_anywhere_still_blocks(self):
        self.set_tasks(
            {"task": "alpha", "type": "feature"},
            {"task": "beta", "type": "feature", "test_scope": False},
        )
        r = run_hook("guard_tests.py", self.edit_test_payload(), self.root)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("oracle", r.stderr.lower())

    def test_no_grant_line_when_nothing_was_at_stake(self):
        """The rm path must not log a GRANT for a command that removes no
        test file - the grant names what it allowed, and nothing was.
        """
        self.set_tasks(
            {"task": "alpha", "type": "feature"},
            {"task": "beta", "type": "feature", "test_scope": True},
        )
        r = run_hook("guard_tests.py",
                     self.bash_payload("rm src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("GRANT", "\n".join(self.log_lines()))


# --------------------------------------------------------------------------
# BR-MST-02 - the N == 1 identity rule, for all five hooks
# --------------------------------------------------------------------------
class SingleEntryParity(MultiBase):
    """The v1 single object and the v2 one-element list are the same state.

    For each hook: exit code, stdout, stderr and the appended adherence.log
    tail must match exactly. Anything that differs here means the multi-entry
    path leaked into the single-entry path.
    """

    def parity(self, hook, payload, entry):
        seen = []
        for as_list in (False, True):
            before = len(self.log_lines())
            if as_list:
                self.set_tasks(entry)
            else:
                self.set_task(entry)
            r = run_hook(hook, payload, self.root)
            appended = self.log_lines()[before:]
            seen.append((r.returncode, r.stdout, r.stderr, appended))
        self.assertEqual(seen[0], seen[1], "v1/v2 divergence in " + hook)
        return seen[0]

    def test_guard_spec_block_parity(self):
        got = self.parity(
            "guard_spec.py",
            self.edit_payload("Write", "src/app.py", "x"),
            {"task": "alpha", "type": "feature"},
        )
        self.assertEqual(got[0], 2)
        self.assertEqual(got[2].strip(), guard_spec.NO_BRIEF_MSG)
        self.assertEqual(got[3], ["guard_spec | BLOCK | src/app.py | "
                                  "no active brief"])

    def test_guard_spec_missing_brief_file_parity(self):
        got = self.parity(
            "guard_spec.py",
            self.edit_payload("Write", "src/app.py", "x"),
            {"task": "alpha", "type": "feature",
             "brief": "company/briefs/nope.md"},
        )
        self.assertEqual(got[0], 2)
        self.assertEqual(
            got[3],
            ["guard_spec | BLOCK | src/app.py | "
             "brief file missing: company/briefs/nope.md"],
        )

    def test_guard_spec_hotfix_bypass_parity(self):
        got = self.parity(
            "guard_spec.py",
            self.edit_payload("Write", "src/app.py", "x"),
            {"task": "hf", "type": "hotfix"},
        )
        self.assertEqual(got[0], 0)
        self.assertEqual(got[3],
                         ["guard_spec | BYPASS | src/app.py | hotfix mode"])

    def test_guard_tests_block_parity(self):
        got = self.parity(
            "guard_tests.py",
            self.edit_payload("Write", "tests/test_x.py", "x"),
            {"task": "alpha", "type": "feature"},
        )
        self.assertEqual(got[0], 2)
        self.assertEqual(
            got[3],
            ["guard_tests | BLOCK | tests/test_x.py | test edit out of scope"],
        )

    def test_guard_tests_grant_writes_nothing_at_one_entry(self):
        got = self.parity(
            "guard_tests.py",
            self.edit_payload("Write", "tests/test_x.py", "x"),
            {"task": "alpha", "type": "feature", "test_scope": True},
        )
        self.assertEqual(got[0], 0)
        self.assertEqual(got[3], [])

    def test_guard_models_bypass_parity(self):
        self.write("company/models.json", json.dumps(MANIFEST))
        got = self.parity(
            "guard_models.py",
            self.spawn_payload(subagent_type="developer", model="haiku"),
            {"task": "hf", "type": "hotfix"},
        )
        self.assertEqual(got[0], 0)
        self.assertEqual(
            got[3], ["guard_models | BYPASS | spawn developer | hotfix mode"]
        )

    def test_guard_models_block_parity(self):
        self.write("company/models.json", json.dumps(MANIFEST))
        got = self.parity(
            "guard_models.py",
            self.spawn_payload(subagent_type="developer", model="haiku"),
            {"task": "alpha", "type": "feature"},
        )
        self.assertEqual(got[0], 2)

    def test_guard_commit_branch_block_parity(self):
        self.init_git()
        self.set_branch("main")
        self.configure_gates()
        got = self.parity(
            "guard_commit.py",
            self.bash_payload("git commit -m wip"),
            {"task": "feat-x", "type": "feature"},
        )
        self.assertEqual(got[0], 2)
        self.assertIn("  git switch -c task/feat-x\n", got[2])
        self.assertEqual(
            got[3],
            ["guard_commit | BLOCK | git commit | commit on protected branch"],
        )

    def test_guard_commit_hotfix_bypass_parity(self):
        self.init_git()
        self.set_branch("main")
        self.configure_gates()
        got = self.parity(
            "guard_commit.py",
            self.bash_payload("git commit -m wip"),
            {"task": "hf", "type": "hotfix"},
        )
        self.assertEqual(got[0], 0)
        self.assertEqual(
            got[3],
            ["guard_commit | BYPASS | git commit | "
             "hotfix commit on protected branch"],
        )

    def test_stop_gate_block_parity(self):
        self.init_git()
        got = self.parity(
            "stop_gate.py", self.stop_payload(),
            {"task": "feat-x", "type": "feature"},
        )
        self.assertEqual(got[0], 0)
        self.assertEqual(json.loads(got[1])["decision"], "block")
        self.assertIn("feat-x", json.loads(got[1])["reason"])
        self.assertEqual(len(got[3]), 1)
        self.assertTrue(got[3][0].startswith("stop_gate | BLOCK | feat-x | "))

    def test_stop_gate_quick_exempt_parity(self):
        self.init_git()
        got = self.parity(
            "stop_gate.py", self.stop_payload(), {"task": "q", "type": "quick"}
        )
        self.assertEqual(got, (0, "", "", []))

    def test_stop_gate_slugless_entry_parity(self):
        # The two-argument .get("task", "(unknown)") must survive: a bare {}
        # still renders (unknown) rather than a slug placeholder.
        self.init_git()
        got = self.parity("stop_gate.py", self.stop_payload(), {})
        self.assertIn("(unknown)", json.loads(got[1])["reason"])
        self.assertEqual(len(got[3]), 1)
        self.assertTrue(got[3][0].startswith("stop_gate | BLOCK | (unknown) |"))


if __name__ == "__main__":
    import unittest
    unittest.main()
