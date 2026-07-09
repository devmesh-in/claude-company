#!/usr/bin/env python3
"""Subprocess-driven tests for the session_start.py provenance digest line.

The digest is additive: the existing RESUME/STATUS/active-task lines are left
alone and one execution/dispatches/self-authored/team line is appended inside
the active-task block. Counts come from gp.read_ledger, which returns zeros
when the ledger is missing, so the digest still prints without one.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, run_hook  # noqa: E402

HOOK = "session_start.py"

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor", "security-reviewer"],
    "builder_roles": ["tech-lead", "developer", "qa-engineer"],
}


class SessionDigestBase(Base):
    def set_manifest(self):
        self.write("company/provenance.json", json.dumps(MANIFEST))

    def feature_task(self, slug="feat-x", **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        self.set_task(obj)

    def session_payload(self):
        return {"hook_event_name": "SessionStart", "cwd": self.root}

    def seed_dispatch(self, role="developer"):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Task",
                   "tool_input": {"subagent_type": role}, "cwd": self.root}
        r = run_hook("guard_provenance.py", payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestSessionStartDigest(SessionDigestBase):
    def test_digest_line_present(self):
        self.write("company/state/RESUME.md", "resume state\n")
        self.write("company/state/STATUS.md", "status state\n")
        self.set_manifest()
        self.feature_task(execution="delegated",
                          execution_why="tech-lead owns")
        self.seed_dispatch("developer")
        r = run_hook(HOOK, self.session_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("execution:", r.stdout)
        self.assertIn("dispatches:", r.stdout)
        self.assertIn("team:", r.stdout)
        self.assertIn("dispatches: 1", r.stdout)
        # the pre-existing active-task line is untouched
        self.assertIn("active-task:", r.stdout)

    def test_digest_without_ledger_shows_zero(self):
        self.write("company/state/RESUME.md", "resume state\n")
        self.set_manifest()
        self.feature_task()  # no ledger seeded
        r = run_hook(HOOK, self.session_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("execution:", r.stdout)
        self.assertIn("dispatches: 0", r.stdout)


if __name__ == "__main__":
    import unittest
    unittest.main()
