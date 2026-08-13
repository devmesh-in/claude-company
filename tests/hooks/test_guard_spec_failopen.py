#!/usr/bin/env python3
"""guard_spec: quick exempts PER ENTRY, and a torn task file fails OPEN.

Two hazards are pinned here, both of which used to stop honest work:

  1. DECISIONS #19 makes quick and hotfix per-entry EXEMPTION types, but
     guard_spec implemented hotfix only. With [feature(briefed), quick(no
     brief)] in flight the brief check - an ALL over the non-exempt entries -
     found the quick entry briefless and blocked the EDIT rather than the
     entry, so one briefless quick entry bricked source edits for EVERY
     concurrent session against the working tree.
  2. FR-HP-32: company/state/active-task.json is written whole by several
     sessions, so a reader can catch its truncated middle. A torn read used to
     read back as "no task in flight" and BLOCK, stopping work that had a
     perfectly good brief. Hooks fail open; this one failed closed on a
     transient condition.

The other direction matters just as much and is asserted alongside each: an
exempt entry must never shield a non-exempt one, and an ABSENT task file must
still block byte-identically to what it has always produced.

Every decision is driven through a real hook subprocess. run_hook pins
CLAUDE_PROJECT_DIR at the fixture root, so an ambient CLAUDE_PROJECT_DIR in the
developer's shell cannot leak in and point the hook at the real repo.
"""

import os
import sys
import unittest

# Same-dir sibling import: works under `unittest discover -s tests/hooks` and
# under `-m unittest tests.hooks.test_guard_spec_failopen` - mirror the hooks'
# own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, run_hook  # noqa: E402
from test_hooks import HOOKS_DIR  # noqa: E402

# Pinned by identity, not by substring, so a reworded recipe cannot quietly
# stop being the no-brief message.
sys.path.insert(0, HOOKS_DIR)
import _common as c  # noqa: E402
import guard_spec  # noqa: E402

# The byte anchors for the two identity cases (c and j), captured by running
# guard_spec.py against a fixture BEFORE either change landed. The full stderr
# is pinned by identity to NO_BRIEF_MSG above; these two literals are what
# would have to change for that identity pin to be silently satisfied by a
# different message.
BLOCK_LINE = "guard_spec | BLOCK | src/app.py | no active brief"
BLOCK_FIRST_LINE = "BLOCKED: no active brief. Self-serve fix:"


class GuardSpecBase(Base):
    def log_path(self):
        return os.path.join(self.root, "company", "state", "adherence.log")

    def log_lines(self):
        """adherence.log with the leading timestamp field stripped."""
        if not os.path.exists(self.log_path()):
            return []
        with open(self.log_path()) as f:
            raw = f.read().splitlines()
        return [ln.split(" | ", 1)[1] if " | " in ln else ln for ln in raw]

    def raw_tasks(self, text):
        """Write active-task.json verbatim - including unparseable bytes."""
        self.write("company/state/active-task.json", text)

    def run_src(self):
        """One Write to src/app.py, the gated path."""
        return run_hook("guard_spec.py",
                        self.edit_payload("Write", "src/app.py", "x"),
                        self.root)


# --------------------------------------------------------------------------
# Step 1 - quick is a per-entry exemption type
# --------------------------------------------------------------------------
class QuickExemption(GuardSpecBase):
    def test_briefless_quick_beside_briefed_feature_allows(self):
        """Delete this and one briefless quick entry can again brick source
        edits for every other session sharing the working tree."""
        self.write("company/briefs/brief-a.md", "# brief")
        self.set_tasks(
            {"task": "feat-a", "type": "feature",
             "brief": "company/briefs/brief-a.md"},
            {"task": "quick-b", "type": "quick"},
        )
        r = self.run_src()
        self.assertEqual(r.returncode, 0, r.stderr)
        # The quick entry is dropped from the check and the feature entry
        # satisfies it, so the gate is SATISFIED, not bypassed - guard_spec
        # logs nothing on a satisfied gate and must not start now.
        self.assertEqual(self.log_lines(), [])

    def test_quick_does_not_shield_a_briefless_feature(self):
        """Delete this and quick becomes an ANY waiver: one quick entry would
        let every briefless feature entry beside it through unchecked."""
        self.set_tasks(
            {"task": "feat-a", "type": "feature"},
            {"task": "quick-b", "type": "quick"},
        )
        r = self.run_src()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("feat-a", r.stderr)
        # The quick entry is exempt, so it is not an offender and is not named.
        self.assertNotIn("quick-b", r.stderr)
        self.assertEqual(
            self.log_lines(),
            ["guard_spec | BLOCK | src/app.py | no usable brief (feat-a)"],
        )

    def test_lone_briefless_feature_blocks_byte_identically(self):
        """Delete this and the exemption work is free to widen until a plain
        briefless feature entry stops blocking - the point of the gate."""
        self.set_tasks({"task": "alpha", "type": "feature"})
        r = self.run_src()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr, guard_spec.NO_BRIEF_MSG + "\n")
        self.assertEqual(r.stderr.splitlines()[0], BLOCK_FIRST_LINE)
        self.assertEqual(self.log_lines(), [BLOCK_LINE])

    def test_lone_quick_bypasses_and_says_quick_mode(self):
        """Delete this and quick silently stops being an exemption type, or
        starts logging under the hotfix label and misreports the ceremony."""
        self.set_tasks({"task": "q", "type": "quick"})
        r = self.run_src()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            self.log_lines(),
            ["guard_spec | BYPASS | src/app.py | quick mode"],
        )

    def test_lone_hotfix_still_says_hotfix_mode(self):
        """The byte-identity control. Delete this and the reason derivation is
        free to collapse to a single fixed 'quick/hotfix mode' string, which
        rewrites what every hotfix-only line in adherence.log has ever said."""
        self.set_tasks({"task": "hf", "type": "hotfix"})
        r = self.run_src()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            self.log_lines(),
            ["guard_spec | BYPASS | src/app.py | hotfix mode"],
        )

    def test_quick_and_hotfix_together_name_both_types(self):
        """Delete this and a mixed exempt set can log under one type's name,
        hiding from the audit that the other ceremony was in flight at all."""
        self.set_tasks(
            {"task": "q", "type": "quick"},
            {"task": "hf", "type": "hotfix"},
        )
        r = self.run_src()
        self.assertEqual(r.returncode, 0, r.stderr)
        # qualify_reason appends the responsible slugs at N > 1 and leaves the
        # reason bare at N == 1, which is what keeps the two lone cases above
        # byte-identical to what they logged before quick was a type.
        self.assertEqual(
            self.log_lines(),
            ["guard_spec | BYPASS | src/app.py | "
             "quick/hotfix mode (q, hf)"],
        )

    def test_quick_leaves_non_source_paths_alone(self):
        """Delete this and the exemption work could start deciding exempt
        paths, which are settled before any task entry is even read."""
        self.set_tasks({"task": "q", "type": "quick"})
        r = run_hook("guard_spec.py",
                     self.edit_payload("Write", "company/anything.md", "x"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.log_lines(), [])


# --------------------------------------------------------------------------
# Step 2 - FR-HP-32, a torn task file fails OPEN
# --------------------------------------------------------------------------
class TornTaskFileFailsOpen(GuardSpecBase):
    def test_truncated_task_file_allows(self):
        """Delete this and a session that happens to read active-task.json
        mid-write is blocked while holding a perfectly good brief."""
        self.raw_tasks('{"version": 2, "tasks": [')
        r = self.run_src()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            self.log_lines(),
            ["guard_spec | BYPASS | src/app.py | task file unreadable"],
        )

    def test_garbage_task_file_allows(self):
        """Same fail-open, reached without JSON-shaped bytes: the hook must key
        on 'does not parse', not on 'looks half-written'."""
        self.raw_tasks("not json at all")
        r = self.run_src()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            self.log_lines(),
            ["guard_spec | BYPASS | src/app.py | task file unreadable"],
        )

    def test_absent_task_file_blocks_byte_identically(self):
        """The regression that would actually matter. Delete this and the
        fail-open is free to widen from 'cannot read it' to 'do not have one',
        which retires spec-before-code entirely."""
        self.assertFalse(
            os.path.exists(
                os.path.join(self.root, "company", "state",
                             "active-task.json")))
        r = self.run_src()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr, guard_spec.NO_BRIEF_MSG + "\n")
        self.assertEqual(r.stderr.splitlines()[0], BLOCK_FIRST_LINE)
        self.assertEqual(self.log_lines(), [BLOCK_LINE])

    def test_absent_file_is_not_unreadable(self):
        """The kernel fact the absent-file block rests on. Delete this and the
        block above can be broken from _common without anything saying why."""
        self.assertFalse(c.active_tasks_unreadable(self.root))
        self.raw_tasks("not json at all")
        self.assertTrue(c.active_tasks_unreadable(self.root))

    def test_empty_but_valid_task_list_still_blocks(self):
        """Parseable is not unreadable. Delete this and the fail-open swallows
        the empty-state block, which is the FR-MST-05 ordering trap."""
        self.raw_tasks('{"version": 2, "tasks": []}')
        r = self.run_src()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stderr, guard_spec.NO_BRIEF_MSG + "\n")
        self.assertEqual(self.log_lines(), [BLOCK_LINE])


class AbsentAndBrieflessAreIndistinguishable(GuardSpecBase):
    def test_absent_file_and_lone_briefless_entry_render_the_same(self):
        """Both cases have always produced one identical BLOCK. Delete this and
        the two can drift apart, which is how a caller learns to tell them
        apart and starts depending on the difference."""
        self.set_tasks({"task": "alpha", "type": "feature"})
        with_entry = self.run_src()
        entry_log = self.log_lines()
        os.unlink(self.log_path())
        os.unlink(os.path.join(self.root, "company", "state",
                               "active-task.json"))
        absent = self.run_src()
        self.assertEqual(
            (with_entry.returncode, with_entry.stdout, with_entry.stderr),
            (absent.returncode, absent.stdout, absent.stderr),
        )
        self.assertEqual(entry_log, self.log_lines())


if __name__ == "__main__":
    unittest.main()
