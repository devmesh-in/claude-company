#!/usr/bin/env python3
"""Subprocess-driven tests for risk_score.py (#19).

Standalone module reusing the harness idiom from test_guard_secrets.py: each
test builds a throwaway git repo, points CLAUDE_PROJECT_DIR at it, makes a base
commit and a HEAD commit, then runs the advisory CLI with --base <base-sha> and
asserts on the RISK_JSON line and exit code. Every case must exit 0 (advisory
tool). Fake secret VALUES only.

Run: python3 -m unittest tests.hooks.test_risk_score
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "hooks")
)
HOOK = "risk_score.py"

# Fake AWS key value (split so this test file itself is not a secret hit).
FAKE_SECRET = "AKIA" + "IOSFODNN7EXAMPLE"


def run_cli(args, root):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, HOOK)] + args,
        capture_output=True, text=True, env=env,
    )


def git(root, *args):
    return subprocess.run(
        ["git", "-C", root] + list(args), capture_output=True, text=True)


def parse_risk(stdout):
    lines = [ln for ln in stdout.splitlines()
             if ln.startswith("RISK_JSON: ")]
    assert lines, "no RISK_JSON line in output:\n" + stdout
    return json.loads(lines[-1][len("RISK_JSON: "):])


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-risk-")
        os.makedirs(os.path.join(self.root, "company", "state"),
                    exist_ok=True)
        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def commit_all(self, msg):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", msg)
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def base_commit(self):
        self.write("README.md", "hello\n")
        return self.commit_all("base")


class TestLowBand(Base):
    def test_tiny_clean_diff_is_low(self):
        base = self.base_commit()
        self.write("src/util.py", "def add(a, b):\n    return a + b\n")
        self.commit_all("small change")
        r = run_cli(["--base", base], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertEqual(data["band"], "low")
        self.assertEqual(data["recommendation"], "standard verification")
        self.assertLess(data["score"], 25)


class TestHighBand(Base):
    def test_big_sensitive_secret_diff_is_high(self):
        base = self.base_commit()
        # brief owns src/ only; the change lands under .claude/hooks/ (out of
        # ownership + sensitive), is >=800 lines (size 15), and carries a fake
        # secret (secrets 25) -> comfortably >= 50.
        self.write("company/briefs/task.md",
                   "# BRIEF\n\n## You own\n- `src/`\n\n## Scope\n1. x\n")
        body = "".join("x_{} = {}\n".format(i, i) for i in range(850))
        self.write(".claude/hooks/bighook.py",
                   "key = \"" + FAKE_SECRET + "\"\n" + body)
        self.commit_all("big sensitive change with secret")
        r = run_cli(
            ["--base", base, "--brief", "company/briefs/task.md"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertEqual(data["band"], "high", r.stdout)
        self.assertEqual(data["recommendation"], "auditor dispatch mandatory")
        self.assertGreaterEqual(data["score"], 50)
        self.assertEqual(data["signals"]["secrets"], 25)
        # 851 lines inside one sensitive path: presence 10 + extent 15 (#122).
        self.assertEqual(data["signals"]["sensitive_paths"], 25)
        self.assertEqual(data["signals"]["size"], 15)


class TestOwnershipParse(Base):
    def test_out_of_ownership_scored_per_offending_path(self):
        # Brief lives in the base commit so it is NOT part of base...HEAD.
        self.write("README.md", "hello\n")
        self.write("company/briefs/task.md",
                   "# BRIEF\n\n## You own\n- `src/`\n\n## Next\n- other\n")
        base = self.commit_all("base with brief")
        self.write("src/inside.py", "a = 1\n")     # owned -> 0
        self.write("other/outside.py", "b = 2\n")  # not owned -> +10
        self.commit_all("mixed ownership change")
        r = run_cli(
            ["--base", base, "--brief", "company/briefs/task.md"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertEqual(data["signals"]["out_of_ownership"], 10, r.stdout)

    def test_owned_path_scores_zero(self):
        self.write("README.md", "hello\n")
        self.write("company/briefs/task.md",
                   "# BRIEF\n\n## You own\n- `src/`\n")
        base = self.commit_all("base with brief")
        self.write("src/only.py", "a = 1\n")
        self.commit_all("in-ownership only")
        r = run_cli(
            ["--base", base, "--brief", "company/briefs/task.md"], self.root)
        data = parse_risk(r.stdout)
        self.assertEqual(data["signals"]["out_of_ownership"], 0, r.stdout)


class TestMissingBrief(Base):
    def test_no_brief_skips_ownership_signal(self):
        base = self.base_commit()
        self.write("other/outside.py", "b = 2\n")
        self.commit_all("change without brief")
        r = run_cli(["--base", base], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        # Skipped, not scored, even though the path is "out of ownership".
        self.assertEqual(data["signals"]["out_of_ownership"], 0)
        self.assertIn("no brief", r.stdout)


class TestAlwaysExitZero(Base):
    def test_broken_base_ref_still_exits_zero(self):
        self.base_commit()
        r = run_cli(["--base", "no-such-ref-xyz"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = parse_risk(r.stdout)
        self.assertIn("band", data)
        self.assertIn("score", data)

    def test_json_flag_suppresses_table_but_keeps_machine_line(self):
        base = self.base_commit()
        self.write("src/util.py", "x = 1\n")
        self.commit_all("c")
        r = run_cli(["--base", base, "--json"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("SIGNAL", r.stdout)
        self.assertIn("RISK_JSON: ", r.stdout)


class WorkTree(Base):
    """Harness for the default (no --base) subject.

    With no --base the tool scores from merge-base(main, HEAD), so these
    cases need a real `main` and a work branch off it.
    """

    def branch_from_main(self):
        base = self.base_commit()
        git(self.root, "branch", "-M", "main")
        git(self.root, "checkout", "-b", "work")
        return base

    def big_body(self):
        """850 lines: over the 800-line cut, so size scores its top 15."""
        return "".join("x_{} = {}\n".format(i, i) for i in range(850))


class TestWorkingTreeSubject(WorkTree):
    """The tree as it stands is the subject, not just what reached git.

    Failure mode this pins (CR-HP-4): the scorer read `base...HEAD` only, so
    a branch whose work was written but not yet committed scored an empty
    diff. Identical content banded `low` uncommitted and `medium`/`high`
    committed - the scorer was blind exactly while the work was in progress.
    """

    def test_identical_content_scores_the_same_before_and_after_commit(self):
        self.branch_from_main()
        self.write(".claude/hooks/bighook.py", self.big_body())
        before = run_cli([], self.root)
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)
        uncommitted = parse_risk(before.stdout)
        self.commit_all("commit the very same content")
        after = run_cli([], self.root)
        committed = parse_risk(after.stdout)
        self.assertEqual(uncommitted["band"], committed["band"],
                         before.stdout + after.stdout)
        self.assertEqual(uncommitted["score"], committed["score"])
        self.assertEqual(uncommitted["signals"]["size"], 15)
        # 850 lines inside one sensitive path: presence 10 + extent 15 (#122).
        self.assertEqual(uncommitted["signals"]["sensitive_paths"], 25)

    def test_untracked_file_is_scored_but_not_under_base(self):
        base = self.branch_from_main()
        self.write("src/big.py", self.big_body())  # never added to the index
        default = run_cli([], self.root)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(parse_risk(default.stdout)["signals"]["size"], 15)
        committed_only = run_cli(["--base", base], self.root)
        self.assertEqual(
            parse_risk(committed_only.stdout)["signals"]["size"], 0)

    def test_committed_answer_wins_when_the_tree_reverts_it(self):
        # The higher of the two answers is the answer: an unfinished undo in
        # the working tree must not lower the bar for what is already in the
        # branch.
        self.write("README.md", "hello\n")
        self.write("src/big.py", "x = 0\n")
        self.commit_all("base")
        git(self.root, "branch", "-M", "main")
        git(self.root, "checkout", "-b", "work")
        self.write("src/big.py", self.big_body())
        self.commit_all("850 lines land on the branch")
        self.write("src/big.py", "x = 0\n")  # reverted, uncommitted
        r = run_cli([], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(parse_risk(r.stdout)["signals"]["size"], 15, r.stdout)
        self.assertIn("subject: committed", r.stdout)

    def test_uncommitted_secret_is_scored(self):
        base = self.branch_from_main()
        self.write("src/config.py", "key = \"" + FAKE_SECRET + "\"\n")
        default = run_cli([], self.root)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(
            parse_risk(default.stdout)["signals"]["secrets"], 25,
            default.stdout)
        # The committed-only comparison cannot see it - guard_secrets
        # --scan-branch scans base...HEAD.
        committed_only = run_cli(["--base", base], self.root)
        self.assertEqual(
            parse_risk(committed_only.stdout)["signals"]["secrets"], 0)


class TestBaseFlagIsCommittedOnly(WorkTree):
    def test_dirty_tree_does_not_change_the_base_answer(self):
        base = self.branch_from_main()
        self.write("src/small.py", "a = 1\n")
        self.commit_all("committed work")
        clean = run_cli(["--base", base], self.root)
        # A big, sensitive, secret-carrying change lands in the tree.
        self.write(".claude/hooks/bighook.py",
                   "key = \"" + FAKE_SECRET + "\"\n" + self.big_body())
        dirty = run_cli(["--base", base], self.root)
        self.assertEqual(clean.returncode, dirty.returncode)
        self.assertEqual(clean.stdout, dirty.stdout, dirty.stdout)


class TestSensitiveRule(Base):
    """The sensitive set is 'the machinery that judges other changes'.

    Each path is scored on its own commit so one match cannot mask another.
    """

    JUDGING = [
        ".claude/hooks/guard_new.py",     # the enforcement code
        ".claude/settings.json",          # what wires the hooks to events
        "company/gates.config",           # what the gate runner executes
        "company/METHOD.md",              # the canon it enforces
        "company/frozen-surfaces.json",   # a registry it reads
        "company/adr/ADR-0099-a-decision.md",
        "CLAUDE.md",
        "db/migrations/0001_init.sql",    # irreversibility, the other rule
    ]

    NOT_JUDGING = [
        "src/app.py",
        "docs/guide.md",
        "company/briefs/brief-x.md",      # paperwork records judgments
        "company/state/adherence.log",    # state, not the judge
        "README.md",
    ]

    def content_for(self, rel):
        return "{}\n" if rel.endswith(".json") else "x = 1\n"

    def score_one(self, rel):
        prev = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.write(rel, self.content_for(rel))
        self.commit_all("add " + rel)
        r = run_cli(["--base", prev], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return parse_risk(r.stdout)["signals"]["sensitive_paths"], r.stdout

    def test_judging_paths_are_sensitive(self):
        self.base_commit()
        for rel in self.JUDGING:
            with self.subTest(path=rel):
                points, out = self.score_one(rel)
                self.assertEqual(points, 10, out)

    def test_ordinary_paths_are_not_sensitive(self):
        self.base_commit()
        for rel in self.NOT_JUDGING:
            with self.subTest(path=rel):
                points, out = self.score_one(rel)
                self.assertEqual(points, 0, out)


class TestSensitivityScalesWithBlastRadius(Base):
    """sensitive_paths scales with blast radius (#122, task risk-scale).

    Failure mode this pins: the signal awarded a FLAT 10 for any number of
    sensitive paths at any size. A 717-line rewrite of guard_provenance.py -
    the hook that decides whether anything gets audited at all - therefore
    scored exactly what a one-line comment fix in company/GIT.md scored, and
    the whole change banded medium, below the arming threshold of its own
    compensating control.

    Each case scores one step against the commit before it, so a step's diff
    holds only that step's files.
    """

    def lines(self, n, start=0):
        return "".join(
            "x_{} = {}\n".format(i, i) for i in range(start, start + n))

    def score_step(self, files):
        """Commit `files` (rel -> content) and score that commit alone."""
        prev = git(self.root, "rev-parse", "HEAD").stdout.strip()
        for rel, content in files.items():
            self.write(rel, content)
        self.commit_all("step")
        r = run_cli(["--base", prev], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return parse_risk(r.stdout), r.stdout

    def test_a_one_line_fix_in_a_judge_still_scores_only_the_floor(self):
        """The deliberate negative: a scale that lifts everything is an
        offset, not a scale. This is the exact case from the brief."""
        self.base_commit()
        data, out = self.score_step({"company/GIT.md": "<!-- typo -->\n"})
        self.assertEqual(data["signals"]["sensitive_paths"], 10, out)
        self.assertEqual(data["band"], "low", out)

    def test_a_rewrite_of_a_judge_outscores_a_one_line_fix_in_one(self):
        self.base_commit()
        small, small_out = self.score_step(
            {".claude/hooks/guard_a.py": self.lines(1)})
        big, big_out = self.score_step(
            {".claude/hooks/guard_b.py": self.lines(850)})
        self.assertEqual(small["signals"]["sensitive_paths"], 10, small_out)
        self.assertEqual(big["signals"]["sensitive_paths"], 25, big_out)

    def test_extent_is_measured_per_path_not_pooled(self):
        """Two judges of 500 lines score 2 x (10 + 8) = 36, not the 10 + 15
        that pooling their 1000 lines into one subject would give. Two judges
        break two independent sets of later judgments."""
        self.base_commit()
        data, out = self.score_step({
            ".claude/hooks/guard_a.py": self.lines(500),
            ".claude/hooks/guard_b.py": self.lines(500),
        })
        self.assertEqual(data["signals"]["sensitive_paths"], 36, out)

    def test_two_judges_outscore_one_at_the_same_churn(self):
        self.base_commit()
        one, one_out = self.score_step(
            {".claude/hooks/guard_a.py": self.lines(1000)})
        two, two_out = self.score_step({
            ".claude/hooks/guard_b.py": self.lines(500),
            ".claude/hooks/guard_c.py": self.lines(500),
        })
        self.assertEqual(one["signals"]["sensitive_paths"], 25, one_out)
        self.assertGreater(two["signals"]["sensitive_paths"],
                           one["signals"]["sensitive_paths"], two_out)

    def test_ordinary_lines_do_not_lift_the_signal(self):
        """The extent term reads the sensitive slice of the diff only - 850
        lines of application code beside a one-line hook edit leave the
        signal at its floor while `size` takes its top points."""
        self.base_commit()
        data, out = self.score_step({
            "src/big.py": self.lines(850),
            ".claude/hooks/guard_a.py": self.lines(1),
        })
        self.assertEqual(data["signals"]["sensitive_paths"], 10, out)
        self.assertEqual(data["signals"]["size"], 15, out)

    def test_the_motivating_shape_reaches_high(self):
        """The shape of 9df86e4..1b957f6: a 717-line hook rewrite plus a
        207-line accepted ADR, carried by healthy tests so test_ratio stays
        0. Scored 25 (medium) under the flat 10; the real diff scores 51."""
        self.base_commit()
        data, out = self.score_step({
            ".claude/hooks/guard_provenance.py": self.lines(717),
            "company/adr/ADR-0003-a-decision.md": self.lines(207),
            "tests/hooks/test_guard_provenance.py": self.lines(1400),
        })
        self.assertEqual(data["signals"]["sensitive_paths"], 36, out)
        self.assertEqual(data["signals"]["test_ratio"], 0, out)
        self.assertEqual(data["band"], "high", out)
        self.assertEqual(data["recommendation"], "auditor dispatch mandatory")


if __name__ == "__main__":
    unittest.main(verbosity=2)
