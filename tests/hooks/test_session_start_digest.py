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


class TestGateAlertLine(SessionDigestBase):
    """DECISIONS #20: the fact the deleted Stop-time gate blocked on, said
    once at session start instead.

    Every case drives a real subprocess and asserts BOTH halves - the line is
    worthless if it does not appear when the ladder is owed, and worse than
    worthless if it appears when it is not. The block path is asserted absent
    everywhere: this hook prints and exits 0, and a Stop-shaped decision
    reaching stdout would be the deleted gate growing back in a new file.
    """

    def setUp(self):
        SessionDigestBase.setUp(self)
        self.init_git()
        self.write("company/state/RESUME.md", "resume state\n")
        self.set_manifest()

    def green_stamp(self):
        self.write("company/gates.config",
                   json.dumps({"gates": [{"name": "tests"}]}))
        self.stamp({"gates": [{"name": "tests", "ok": True}]})

    def digest(self):
        r = run_hook(HOOK, self.session_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"decision"', r.stdout,
                         "session_start must never emit a block decision")
        return r.stdout

    def test_a_missing_stamp_with_a_feature_entry_says_so(self):
        """The tree has never run the ladder and real work is in flight. This
        is the moment the session can still do something about it.
        """
        self.feature_task()
        out = self.digest()
        self.assertIn("gates: no gates.status stamp", out)
        self.assertIn("feat-x", out)
        self.assertIn("/gates", out)

    def test_a_stale_stamp_says_stale_and_names_every_gating_entry(self):
        """Named, not counted: this line is the only place a session learns
        its own slug is implicated, so slug_list's default cap of 3 would drop
        the fourth session out of the one record that mentions it.
        """
        self.green_stamp()
        self.write("src/app.py", "print(1)\n")  # dirty the work_hash
        self.set_tasks(*[{"task": "t%d" % i, "type": "feature"}
                         for i in range(4)])
        out = self.digest()
        line = [ln for ln in out.splitlines() if ln.startswith("gates: ")]
        self.assertEqual(len(line), 1, out)
        self.assertIn("gates.status is stale", line[0])
        for slug in ("t0", "t1", "t2", "t3"):
            self.assertIn(slug, line[0])
        # DIGEST_CAP truncates the per-entry PAIRS below; this line must not
        # inherit that cap, or the fourth session never sees its own slug.
        self.assertNotIn("more", line[0])

    def test_a_red_stamp_says_red(self):
        self.write("company/gates.config",
                   json.dumps({"gates": [{"name": "tests"}]}))
        self.stamp({"gates": [{"name": "tests", "ok": False}]})
        self.feature_task()
        self.assertIn("gates: gates are red", self.digest())

    def test_a_green_fresh_stamp_is_silent(self):
        """The control. Without it the tests above would pass for a hook that
        printed the line unconditionally.
        """
        self.feature_task()
        self.green_stamp()
        self.assertNotIn("gates:", self.digest())

    def test_quick_and_hotfix_entries_alone_stay_silent(self):
        """Same per-entry exemption the deleted gate honored: quick and hotfix
        exempt THEMSELVES. With nothing else in flight there is no ladder owed
        and nothing to say.
        """
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "hf", "type": "hotfix"})
        self.assertNotIn("gates:", self.digest())

    def test_a_quick_entry_beside_a_feature_still_arms_the_line(self):
        """...and the exemption is not contagious. The feature entry is real
        work on a tree with no stamp, so the line appears and blames it alone.
        """
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "feat-x", "type": "feature"})
        out = self.digest()
        self.assertIn("gates: no gates.status stamp", out)
        self.assertIn("feat-x", out)
        self.assertNotIn("in flight: q", out)

    def test_no_entries_at_all_stays_silent(self):
        """An idle tree with a bad stamp is the normal state of most sessions
        and must not be nagged.
        """
        self.assertNotIn("gates:", self.digest())

    def test_a_brief_edit_does_not_arm_the_line(self):
        """FR-HP-06 end to end, through the surviving consumer of check_stamp.
        Paperwork is a build INPUT: company/briefs and company/specs are in
        HASH_EXCLUDES, so writing a brief on a green tree leaves it green. The
        old end-to-end proof of this ran through the deleted Stop hook.
        """
        self.feature_task()
        self.green_stamp()
        self.write("company/briefs/brief-feat-x.md", "# BRIEF\n\nmission\n")
        self.assertNotIn("gates:", self.digest())

    def test_the_line_survives_a_saturated_resume_and_status(self):
        """Placement is the whole delivery. RESUME's 40 lines plus STATUS's 20
        plus their headers already exceed MAX_LINES, so a line appended after
        them is truncated away and never reaches anybody - which is how this
        repo's real RESUME.md is shaped today.
        """
        self.write("company/state/RESUME.md",
                   "".join("resume %d\n" % i for i in range(300)))
        self.write("company/state/STATUS.md",
                   "".join("status %d\n" % i for i in range(300)))
        self.feature_task()
        self.assertIn("gates: no gates.status stamp", self.digest())

    def test_an_unreadable_stamp_loses_the_line_not_the_digest(self):
        """Fail-silent, in the direction that matters. The advisory is
        advisory; the digest is the hook's actual job, and a malformed stamp
        must not cost the session its RESUME summary.
        """
        self.feature_task()
        self.write("company/state/gates.status", "{not json at all")
        out = self.digest()
        self.assertIn("state digest", out)
        self.assertIn("resume state", out)


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
