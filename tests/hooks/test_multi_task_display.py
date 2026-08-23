#!/usr/bin/env python3
"""Multi-entry rendering for the display/telemetry hooks (FR-MST-10..13,
less the cost_capture leg, removed with the cost ledger in #134).

context_pin, session_start and risk_score are the hooks that only READ the
task list: none of them gates anything, and none may start.
These tests pin two things at once - that every entry in flight is rendered,
and that the single-entry path stayed byte-identical (BR-MST-02).

Ledger counts are only ever seeded by driving REAL guard_provenance payloads
(Mode B-pre for a dispatch, Mode A for a self-authored path), and always while
exactly ONE entry is in flight, so the seeding itself rides the frozen N == 1
path and cannot drift with the gate work happening in parallel.
"""

import json
import os
import sys

# Same-dir sibling import: works under `unittest discover -s tests/hooks`
# (which seeds sys.path) and under `-m unittest tests.hooks.<mod>` (which does
# not) - mirror the hooks' own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_cli, run_hook  # noqa: E402

PIN = "context_pin.py"
SESSION = "session_start.py"
RISK = "risk_score.py"
PROV = "guard_provenance.py"

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor", "security-reviewer"],
    "builder_roles": ["tech-lead", "developer", "qa-engineer"],
}



def parse_risk(stdout):
    lines = [ln for ln in stdout.splitlines() if ln.startswith("RISK_JSON: ")]
    assert lines, "no RISK_JSON line in output:\n" + stdout
    return json.loads(lines[-1][len("RISK_JSON: "):])


class MultiBase(Base):
    # --- fixtures ---------------------------------------------------------
    def set_manifest(self):
        self.write("company/provenance.json", json.dumps(MANIFEST))

    def feature(self, slug, **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        return obj

    def entry(self, slug, ttype):
        return {"task": slug, "type": ttype}

    # --- ledger seeding, always at N == 1 ---------------------------------
    def seed_dispatch(self, role="developer"):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Task",
                   "tool_input": {"subagent_type": role}, "cwd": self.root}
        r = run_hook(PROV, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def seed_self_authored(self, rel):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": rel, "content": "code"},
                   "cwd": self.root}
        r = run_hook(PROV, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def ledger_path(self):
        return os.path.join(self.root, "company", "state",
                            "provenance-ledger.json")

    # --- hook drivers -----------------------------------------------------
    def pin(self):
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": self.root}
        return run_hook(PIN, payload, self.root)

    def digest(self):
        payload = {"hook_event_name": "SessionStart", "cwd": self.root}
        return run_hook(SESSION, payload, self.root)

    def git_history(self):
        """A base commit carrying a brief, then a HEAD commit touching one
        owned path and one un-owned path. Returns the base sha."""
        self.init_git()
        self.write("company/briefs/b.md",
                   "# brief\n\n## You own\n- `src/`\n\n## Scope\n1. x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "base with brief")
        base = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.write("src/owned.py", "a = 1\n")
        self.write("other/outside.py", "b = 2\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "head")
        return base

    # --- assertions -------------------------------------------------------
    def lines(self, stdout):
        s = stdout.strip("\n")
        return s.split("\n") if s else []

    def assertSameRun(self, a, b, label):
        self.assertEqual(a.returncode, b.returncode, label + " returncode")
        self.assertEqual(a.stdout, b.stdout, label + " stdout")
        self.assertEqual(a.stderr, b.stderr, label + " stderr")


class TestSingleEntryParity(MultiBase):
    """BR-MST-02: a v1 single object and a v2 one-element list are the same
    run - identical exit code, stdout and stderr - for all four hooks."""

    def test_context_pin_parity(self):
        self.set_manifest()
        obj = self.feature("feat-x", execution="delegated",
                           execution_why="tech-lead owns")
        self.set_task(obj)
        self.seed_dispatch("developer")
        self.seed_self_authored("src/a.py")
        first = self.pin()
        self.set_tasks(obj)
        second = self.pin()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertSameRun(first, second, "context_pin")
        self.assertIn("self=", first.stdout)

    def test_context_pin_parity_idle_line(self):
        # The standalone IDLE_LINE is part of the frozen single-entry shape.
        self.set_manifest()
        obj = self.feature("feat-x")  # undecided -> drifty
        self.set_task(obj)
        first = self.pin()
        self.set_tasks(obj)
        second = self.pin()
        self.assertSameRun(first, second, "context_pin idle")
        self.assertIn("team idle", first.stdout)
        self.assertEqual(len(self.lines(first.stdout)), 2, first.stdout)

    def test_session_start_parity(self):
        self.write("company/state/RESUME.md", "resume state\n")
        self.set_manifest()
        obj = self.feature("feat-x", execution="delegated",
                           execution_why="tech-lead owns")
        self.set_task(obj)
        self.seed_dispatch("developer")
        first = self.digest()
        self.set_tasks(obj)
        second = self.digest()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertSameRun(first, second, "session_start")
        self.assertIn("active-task: feat-x (feature)", first.stdout)

    def test_risk_score_parity(self):
        base = self.git_history()
        obj = self.feature("feat-x")
        self.set_task(obj)
        first = run_cli(RISK, ["--base", base], self.root)
        self.set_tasks(obj)
        second = run_cli(RISK, ["--base", base], self.root)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertSameRun(first, second, "risk_score")
        # The single entry's own brief was used: one un-owned path scores 10.
        self.assertEqual(parse_risk(first.stdout)["signals"]
                         ["out_of_ownership"], 10, first.stdout)


class TestContextPinMulti(MultiBase):
    def test_two_entries_per_slug_disp_and_shared_tree_line(self):
        self.set_manifest()  # no git -> local mode, no iss segment
        a = self.feature("feat-a", execution="delegated",
                         execution_why="tech-lead owns")
        self.set_task(a)
        self.seed_dispatch("developer")
        self.seed_dispatch("qa-engineer")
        self.seed_self_authored("src/a.py")
        b = self.feature("feat-b", execution="delegated",
                         execution_why="tech-lead owns")
        self.set_tasks(a, b)

        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 3, r.stdout)
        self.assertIn("feat-a feature exec=delegated disp=2", lines[0])
        # PER-SLUG: feat-a's two dispatches do not bleed into feat-b.
        self.assertIn("feat-b feature exec=delegated disp=0", lines[1])
        # self= is a TREE fact and appears ONLY on the tree line.
        self.assertNotIn("self=", lines[0])
        self.assertNotIn("self=", lines[1])
        self.assertEqual(lines[2], "[company] tree: self=1")

    def test_drifty_entry_marks_its_own_line_and_drops_idle_line(self):
        self.set_manifest()
        a = self.feature("feat-a", execution="delegated",
                         execution_why="tech-lead owns")
        self.set_task(a)
        self.seed_dispatch("developer")
        b = self.feature("feat-b")  # no execution decision -> drifty
        self.set_tasks(a, b)

        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 3, r.stdout)
        self.assertNotIn(" idle", lines[0])
        self.assertTrue(lines[1].endswith(" idle"), lines[1])
        self.assertIn("feat-b", lines[1])
        # The standalone team-idle line is gone at N > 1 - that is the point.
        self.assertNotIn("team idle", r.stdout)

    def test_slugless_entry_renders_placeholder(self):
        self.set_manifest()
        self.set_tasks({"task": "feat-a", "type": "quick"},
                       {"type": "quick"})
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertIn("<task-slug>", lines[1])

    def test_ten_entries_capped_at_five_lines(self):
        self.set_manifest()
        entries = [self.entry("t-%d" % i, "quick") for i in range(10)]
        self.set_tasks(*entries)
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 5, r.stdout)
        self.assertIn("t-0", lines[0])
        self.assertIn("t-2", lines[2])
        self.assertEqual(lines[3], "[company] and 7 more")
        self.assertEqual(lines[4], "[company] tree: self=0")

    def test_hotfix_marker_on_its_own_entry_line(self):
        self.set_manifest()
        self.set_tasks(self.entry("q-a", "quick"),
                       self.entry("hf-b", "hotfix"),
                       self.entry("q-c", "quick"))
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 4, r.stdout)
        self.assertTrue(lines[1].endswith(" HOTFIX"), lines[1])
        self.assertIn("hf-b", lines[1])
        # Already visible on an entry line, so the tree line stays clean.
        self.assertNotIn("HOTFIX:", lines[3])

    def test_hotfix_past_the_display_cap_rides_the_tree_line(self):
        self.set_manifest()
        entries = [self.entry("q-%d" % i, "quick") for i in range(4)]
        entries.append(self.entry("hf-late", "hotfix"))
        entries.append(self.entry("q-last", "quick"))
        self.set_tasks(*entries)
        r = self.pin()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self.lines(r.stdout)
        self.assertEqual(len(lines), 5, r.stdout)
        self.assertNotIn("hf-late", "\n".join(lines[:4]))
        self.assertTrue(lines[4].endswith(" HOTFIX:hf-late"), lines[4])
        self.assertIn("tree: self=", lines[4])

    def test_ledger_bytes_and_mtime_untouched(self):
        self.write("company/state/RESUME.md", "resume state\n")
        self.set_manifest()
        a = self.feature("feat-a", execution="delegated",
                         execution_why="tech-lead owns")
        self.set_task(a)
        self.seed_dispatch("developer")
        self.seed_self_authored("src/a.py")
        b = self.feature("feat-b")
        self.set_tasks(a, b)

        path = self.ledger_path()
        with open(path, "rb") as f:
            before_bytes = f.read()
        before_mtime = os.stat(path).st_mtime_ns

        self.assertEqual(self.pin().returncode, 0)
        self.assertEqual(self.digest().returncode, 0)

        with open(path, "rb") as f:
            self.assertEqual(f.read(), before_bytes, "ledger bytes changed")
        self.assertEqual(os.stat(path).st_mtime_ns, before_mtime,
                         "ledger mtime changed - read_ledger wrote")


class TestSessionStartMulti(MultiBase):
    def test_two_entries_two_digest_pairs(self):
        self.write("company/state/RESUME.md", "resume state\n")
        self.set_manifest()
        a = self.feature("feat-a", execution="delegated",
                         execution_why="tech-lead owns")
        self.set_task(a)
        self.seed_dispatch("developer")
        self.seed_self_authored("src/a.py")
        self.seed_self_authored("src/b.py")
        b = self.feature("feat-b")
        self.set_tasks(a, b)

        r = self.digest()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.splitlines()
        ident = [ln for ln in out if ln.startswith("active-task:")]
        execs = [ln for ln in out if ln.startswith("execution:")]
        self.assertEqual(len(ident), 2, r.stdout)
        self.assertEqual(len(execs), 2, r.stdout)
        self.assertIn("feat-a", ident[0])
        self.assertIn("feat-b", ident[1])
        # dispatches is PER-SLUG, self-authored is GLOBAL.
        self.assertIn("execution: delegated | dispatches: 1", execs[0])
        self.assertIn("execution: undecided | dispatches: 0", execs[1])
        self.assertIn("self-authored: 2 files", execs[0])
        self.assertIn("self-authored: 2 files", execs[1])

    def test_hotfix_entry_marked_and_overflow_counted(self):
        self.write("company/state/RESUME.md", "resume state\n")
        self.set_manifest()
        entries = [self.entry("q-a", "quick"),
                   self.entry("hf-b", "hotfix"),
                   self.entry("q-c", "quick"),
                   self.entry("q-d", "quick"),
                   self.entry("q-e", "quick")]
        self.set_tasks(*entries)
        r = self.digest()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.splitlines()
        ident = [ln for ln in out if ln.startswith("active-task:")]
        self.assertEqual(len(ident), 3, r.stdout)
        self.assertTrue(ident[1].endswith(" HOTFIX:hf-b"), ident[1])
        self.assertIn("and 2 more", out)


class TestRiskScoreMulti(MultiBase):
    def test_two_entries_no_brief_keeps_exit_code_and_notes_the_count(self):
        base = self.git_history()
        a = self.feature("feat-a")
        b = self.feature("feat-b")

        self.set_tasks(a)
        one = run_cli(RISK, ["--base", base], self.root)
        self.assertEqual(one.returncode, 0, one.stdout + one.stderr)
        # One entry: unchanged - its own brief is loaded and scored.
        self.assertEqual(
            parse_risk(one.stdout)["signals"]["out_of_ownership"], 10,
            one.stdout)
        self.assertNotIn("active task entries", one.stdout)

        self.set_tasks(a, b)
        two = run_cli(RISK, ["--base", base], self.root)
        # Advisory: the exit code is unchanged at every N.
        self.assertEqual(two.returncode, one.returncode)
        self.assertEqual(two.returncode, 0, two.stdout + two.stderr)
        self.assertIn("2 active task entries", two.stdout)
        self.assertIn("--brief", two.stdout)
        # No brief is guessed: the ownership signal is skipped, not invented.
        self.assertEqual(
            parse_risk(two.stdout)["signals"]["out_of_ownership"], 0,
            two.stdout)

    def test_explicit_brief_still_scores_with_two_entries(self):
        base = self.git_history()
        self.set_tasks(self.feature("feat-a"), self.feature("feat-b"))
        r = run_cli(RISK, ["--base", base, "--brief", "company/briefs/b.md"],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            parse_risk(r.stdout)["signals"]["out_of_ownership"], 10, r.stdout)

    def test_no_entries_keeps_todays_note(self):
        base = self.git_history()
        r = run_cli(RISK, ["--base", base], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no brief", r.stdout)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
