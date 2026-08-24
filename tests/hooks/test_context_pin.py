#!/usr/bin/env python3
"""Subprocess-driven tests for context_pin.py (the UserPromptSubmit pin).

Ledger counts are seeded via dispatch_feed.write_sealed_ledger (FR-ASR-03),
never by driving deleted provenance modes. Every fixture that exercises
exec/iss writes its own company/provenance.json (the manifest is the rollout
switch the feed helpers consult).
"""

import json
import os
import sys

# Same-dir sibling import: works under `unittest discover -s tests/hooks`
# (which seeds sys.path) and under `-m unittest tests.hooks.test_context_pin`
# (which does not) - mirror the hooks' own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, HOOKS_DIR, git, run_hook  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import dispatch_feed as df  # noqa: E402

HOOK = "context_pin.py"
BUDGET = 160

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor", "security-reviewer"],
    "builder_roles": ["tech-lead", "developer", "qa-engineer"],
}


class PinBase(Base):
    def set_manifest(self):
        self.write("company/provenance.json", json.dumps(MANIFEST))

    def feature_task(self, slug="feat-x", **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        self.set_task(obj)

    def prompt_payload(self):
        return {"hook_event_name": "UserPromptSubmit", "cwd": self.root}

    def pin(self, raw_stdin=None):
        return run_hook(HOOK, self.prompt_payload(), self.root,
                        raw_stdin=raw_stdin)

    def add_origin(self):
        git(self.root, "remote", "add", "origin",
            "https://example.com/x.git")

    def seed_dispatch(self, role="developer"):
        ledger = df.read_ledger(self.root)
        slug = ""
        try:
            raw = json.load(open(os.path.join(
                self.root, "company", "state", "active-task.json")))
            if isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
                slug = (raw["tasks"][0] or {}).get("task") or ""
            elif isinstance(raw, dict):
                slug = raw.get("task") or ""
        except Exception:
            slug = ""
        rec = df.task_record(ledger, slug)
        rec["dispatches"].append({"role": role, "at": "2026-01-01T00:00:00Z"})
        df.write_sealed_ledger(self.root, ledger)

    def seed_self_authored(self, rel):
        ledger = df.read_ledger(self.root)
        ledger.setdefault("self_authored", []).append(rel)
        df.write_sealed_ledger(self.root, ledger)

    def lines(self, stdout):
        s = stdout.strip("\n")
        return s.split("\n") if s else []

    def assertBudget(self, stdout):
        for line in self.lines(stdout):
            self.assertLess(len(line), BUDGET, line)


class TestContextPin(PinBase):
    def test_no_active_task_empty(self):
        self.set_manifest()  # manifest present, but no active task
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_feature_undecided_two_lines_idle(self):
        self.set_manifest()
        self.feature_task()  # no execution field -> undecided
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 2, r.stdout)
        self.assertIn("exec=undecided", lines[0])
        self.assertIn("team idle", lines[1])
        self.assertBudget(r.stdout)

    def test_feature_delegated_one_dispatch_single_line(self):
        self.set_manifest()  # no git -> local mode, no iss segment
        self.feature_task(execution="delegated",
                          execution_why="tech-lead owns")
        self.seed_dispatch("developer")
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 1, r.stdout)
        self.assertIn("disp=1", lines[0])
        self.assertNotIn("team idle", r.stdout)
        self.assertBudget(r.stdout)

    def test_quick_task_no_exec_segment(self):
        self.set_manifest()
        self.set_task({"task": "q", "type": "quick"})
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 1, r.stdout)
        self.assertNotIn("exec=", lines[0])
        self.assertNotIn("iss=", lines[0])
        self.assertBudget(r.stdout)

    def test_counts_reflect_seeded_ledger(self):
        self.set_manifest()  # local mode -> no iss noise
        self.feature_task(execution="delegated",
                          execution_why="tech-lead owns")
        self.seed_dispatch("developer")
        self.seed_dispatch("qa-engineer")
        self.seed_self_authored("src/a.py")
        self.seed_self_authored("src/b.py")
        self.seed_self_authored("src/c.py")
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("disp=2 self=3", r.stdout)
        self.assertBudget(r.stdout)

    def test_pr_mode_untracked_shows_iss0(self):
        self.init_git()
        self.add_origin()
        self.set_manifest()
        self.feature_task()  # no issues recorded
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("iss=0", r.stdout)
        self.assertBudget(r.stdout)

    def test_pr_mode_tracked_no_iss(self):
        self.init_git()
        self.add_origin()
        self.set_manifest()
        self.feature_task(issues=[7])
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("iss=", r.stdout)
        self.assertBudget(r.stdout)

    def test_local_mode_untracked_no_iss(self):
        # No origin remote -> pr_mode off -> the gate is not armed, no drift.
        self.init_git()
        self.set_manifest()
        self.feature_task()  # no issues, but local mode
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("iss=", r.stdout)
        self.assertBudget(r.stdout)

    def test_garbage_stdin_exits_zero(self):
        self.set_manifest()
        self.feature_task()
        r = self.pin(raw_stdin="not json")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    import unittest
    unittest.main()
