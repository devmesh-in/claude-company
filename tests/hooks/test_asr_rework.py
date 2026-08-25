#!/usr/bin/env python3
"""Decision tables and coverage for spec-ai-sdlc-rework (prefix ASR).

Every FR-ASR / BR-ASR ID appears in a test name or docstring (BR-ASR-10).
BLOCK-to-ALLOW conversions have enumerated rows (BR-ASR-01..06).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, HOOKS_DIR, git, run_cli, run_hook  # noqa: E402
from test_gate_runner import make_project, run_ladder  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import dispatch_feed as df  # noqa: E402
import guard_frozen  # noqa: E402
import guard_provenance as gp_shim  # noqa: E402

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


# --------------------------------------------------------------------------
# FR-ASR-01 METHOD four laws; FR-ASR-02 risk_score gone; FR-ASR-04 sweep
# --------------------------------------------------------------------------
class TestCanonAndDeletions(unittest.TestCase):
    def test_fr_asr_01_method_opens_with_four_laws(self):
        """FR-ASR-01: four-law preamble is present numbered prose."""
        with open(os.path.join(REPO_ROOT, "company", "METHOD.md")) as f:
            text = f.read()
        for law in (
            "Attention is the scarce resource",
            "Self-report is not evidence",
            "Scripts sense, judges judge",
            "A rule is a mechanism or it is dead",
        ):
            self.assertIn(law, text)
        self.assertNotIn("guard_provenance.py", text)

    def test_fr_asr_02_risk_score_file_is_gone(self):
        """FR-ASR-02: risk_score.py deleted."""
        path = os.path.join(HOOKS_DIR, "risk_score.py")
        self.assertFalse(os.path.exists(path))

    def test_fr_asr_04_common_sweep_found_nothing_unique(self):
        """FR-ASR-04: the sweep comment is on disk; no unique helper lingered."""
        with open(os.path.join(HOOKS_DIR, "_common.py")) as f:
            text = f.read()
        self.assertIn("FR-ASR-04", text)
        self.assertIn("Nothing unique", text)

    def test_fr_asr_19_status_is_gone_ideation_is_kept(self):
        """FR-ASR-19: STATUS/standup stay cut; ideation (brainstorm) ships."""
        self.assertFalse(os.path.exists(
            os.path.join(REPO_ROOT, "company", "state", "STATUS.md")))
        self.assertTrue(os.path.exists(
            os.path.join(REPO_ROOT, "company", "IDEATION.md")))
        self.assertTrue(os.path.exists(
            os.path.join(REPO_ROOT, ".claude", "agents",
                         "ideation-strategist.md")))
        self.assertTrue(os.path.exists(
            os.path.join(REPO_ROOT, ".claude", "skills", "brainstorm",
                         "SKILL.md")))
        self.assertFalse(os.path.exists(
            os.path.join(REPO_ROOT, ".claude", "skills", "standup",
                         "SKILL.md")))
        self.assertTrue(os.path.exists(
            os.path.join(REPO_ROOT, "company", "EXTENDING.md")))

    def test_fr_asr_21_settings_have_no_provenance_command(self):
        """FR-ASR-21: settings.json does not invoke the shim."""
        with open(os.path.join(REPO_ROOT, ".claude", "settings.json")) as f:
            raw = f.read()
        self.assertNotIn("guard_provenance.py", raw)
        self.assertNotIn('"Stop"', raw)

    def test_fr_asr_22_shim_reexports_and_has_no_block(self):
        """FR-ASR-22 / OQ-ASR-02: shim re-exports; no BLOCK path."""
        self.assertEqual(
            gp_shim.audit_verdict("Verdict: HALT."), "do-not-ship")
        with open(os.path.join(HOOKS_DIR, "guard_provenance.py")) as f:
            src = f.read()
        self.assertNotIn("c.block(", src)


# --------------------------------------------------------------------------
# BR-ASR-01 lockfile BLOCK -> WARN
# --------------------------------------------------------------------------
class TestBrAsr01LockfileWarn(Base):
    def _edit(self, rel, text="x"):
        return run_hook(
            "guard_frozen.py",
            self.edit_payload("Write", rel, text),
            self.root,
        )

    def test_br_asr_01_package_lock_warns(self):
        r = self._edit("package-lock.json", "{}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN", open(os.path.join(
            self.root, "company", "state", "adherence.log")).read())

    def test_br_asr_01_yarn_lock_warns(self):
        self.assertEqual(self._edit("yarn.lock").returncode, 0)

    def test_br_asr_01_pnpm_lock_warns(self):
        self.assertEqual(self._edit("pnpm-lock.yaml").returncode, 0)

    def test_br_asr_01_poetry_lock_warns(self):
        self.assertEqual(self._edit("poetry.lock").returncode, 0)

    def test_br_asr_01_cargo_lock_warns(self):
        self.assertEqual(self._edit("Cargo.lock").returncode, 0)

    def test_br_asr_01_star_lock_warns(self):
        self.assertEqual(self._edit("Gemfile.lock").returncode, 0)

    def test_br_asr_01_env_still_blocks(self):
        self.assertEqual(self._edit(".env", "SECRET=1").returncode, 2)

    def test_br_asr_01_env_example_allows(self):
        self.assertEqual(self._edit(".env.example", "SECRET=").returncode, 0)

    def test_br_asr_01_adherence_log_blocks(self):
        r = self._edit("company/state/adherence.log", "tamper")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_br_asr_01_accepted_adr_blocks(self):
        self.write("company/adr/ADR-001-x.md",
                   "# ADR\nStatus: accepted\n\nbody\n")
        r = run_hook(
            "guard_frozen.py",
            self.edit_payload("Edit", "company/adr/ADR-001-x.md", "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_br_asr_01_ordinary_source_allows(self):
        self.assertEqual(self._edit("src/util.py", "x = 1").returncode, 0)

    def test_br_asr_08_frozen_baseline_still_agrees(self):
        """BR-ASR-08 / FrozenBaselineAgreement: lockfiles left both copies."""
        with open(os.path.join(
                REPO_ROOT, "company", "frozen-surfaces.json")) as f:
            registry = set(json.load(f)["always"])
        self.assertEqual(set(guard_frozen.ALWAYS_DEFAULTS), registry)
        for pat in guard_frozen.LOCKFILE_PATTERNS:
            self.assertNotIn(pat, registry)


# --------------------------------------------------------------------------
# BR-ASR-02 surfaces[] mid-flight ALLOW; undeclared BLOCK at commit
# --------------------------------------------------------------------------
class TestBrAsr02SurfacesDrift(Base):
    def set_surfaces(self):
        self.write("company/frozen-surfaces.json", json.dumps({
            "version": 1,
            "surfaces": [{"pattern": "src/core/*", "why": "kernel"}],
            "always": [],
        }))

    def test_br_asr_02_mid_flight_edit_allows(self):
        self.set_surfaces()
        r = run_hook(
            "guard_frozen.py",
            self.edit_payload("Edit", "src/core/kernel.py", "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_02_undeclared_commit_blocks(self):
        self.init_git()
        git(self.root, "checkout", "-B", "task/x")
        self.set_surfaces()
        self.write("src/core/kernel.py", "x = 1\n")
        git(self.root, "add", "src/core/kernel.py")
        self.set_task({"task": "x", "type": "feature"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m x"), self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("undeclared", r.stderr.lower())

    def test_br_asr_02_cr_naming_path_allows_commit(self):
        self.init_git()
        git(self.root, "checkout", "-B", "task/x")
        self.set_surfaces()
        self.write("src/core/kernel.py", "x = 1\n")
        git(self.root, "add", "src/core/kernel.py")
        self.write("company/change-requests/CR-9-kernel.md",
                   "Unfreeze src/core/kernel.py for this change.\n")
        self.set_task({"task": "x", "type": "feature"})
        r = run_hook("guard_commit.py",
                     self.bash_payload("git commit -m x"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


# --------------------------------------------------------------------------
# BR-ASR-03 acting-tree stamp
# --------------------------------------------------------------------------
class TestBrAsr03ActingTree(unittest.TestCase):
    def setUp(self):
        from test_acting_tree_commit import Base as Acting
        self._inner = Acting()
        self._inner.setUp()
        self.root = self._inner.root

    def tearDown(self):
        self._inner.tearDown()

    def test_br_asr_03_worktree_commit_allows_when_main_stale(self):
        inner = self._inner
        wt = inner.add_worktree()
        inner.set_tasks({"task": "x", "type": "feature"})
        inner.configure_gates(wt)
        inner.stamp(wt)
        inner.configure_gates(inner.root)
        inner.stale_stamp(inner.root)
        r = inner.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_br_asr_03_worktree_commit_allows_when_own_stamp_stale(self):
        inner = self._inner
        wt = inner.add_worktree()
        inner.set_tasks({"task": "x", "type": "feature"})
        inner.configure_gates(wt)
        inner.stale_stamp(wt)
        inner.configure_gates(inner.root)
        inner.stamp(inner.root)
        r = inner.commit_guard("git -C {} commit -m y".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_br_asr_03_merge_on_main_stale_blocks_when_worktree_green(self):
        inner = self._inner
        wt = inner.add_worktree()
        inner.set_tasks({"task": "x", "type": "feature"})
        inner.configure_gates(wt)
        inner.stamp(wt)
        inner.configure_gates(inner.root)
        inner.stale_stamp(inner.root)
        r = inner.commit_guard("git merge task/x")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("stale", r.stderr)

    def test_br_asr_03_merge_on_task_branch_allows_without_stamp(self):
        inner = self._inner
        wt = inner.add_worktree()
        inner.set_tasks({"task": "x", "type": "feature"})
        inner.configure_gates(wt)
        r = inner.commit_guard("git -C {} merge main".format(wt))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_br_asr_03_unresolved_dash_c_does_not_invent_a_skip(self):
        inner = self._inner
        inner.set_tasks({"task": "x", "type": "feature"})
        r = inner.commit_guard('git -C "$WT" commit -m y')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("no gates configured", inner.adherence())


# --------------------------------------------------------------------------
# BR-ASR-04 worktree test_scope + non-source exemption
# --------------------------------------------------------------------------
class TestBrAsr04TestScope(unittest.TestCase):
    def setUp(self):
        from test_acting_tree_guards import TestTestScopeFromTheActingTree
        self._inner = TestTestScopeFromTheActingTree()
        self._inner.setUp()

    def tearDown(self):
        self._inner.tearDown()

    def test_br_asr_04_worktree_grant_main_deny_allows(self):
        inner = self._inner
        inner.set_tasks({"task": "main-lane", "type": "feature",
                         "test_scope": False})
        inner.set_tasks({"task": "lane", "type": "feature",
                         "test_scope": True}, base=inner.wt)
        r = inner.guard_tests_edit(inner.wt_test)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_br_asr_04_worktree_deny_main_grant_blocks(self):
        inner = self._inner
        inner.set_tasks({"task": "main-lane", "type": "feature",
                         "test_scope": True})
        inner.set_tasks({"task": "lane", "type": "feature",
                         "test_scope": False}, base=inner.wt)
        r = inner.guard_tests_edit(inner.wt_test)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_br_asr_04_no_worktree_file_falls_back_to_main(self):
        inner = self._inner
        inner.set_tasks({"task": "main-lane", "type": "feature",
                         "test_scope": True})
        r = inner.guard_tests_edit(inner.wt_test)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestBrAsr04NonSource(Base):
    def test_br_asr_04_md_under_tests_allows_without_grant(self):
        r = run_hook(
            "guard_tests.py",
            self.edit_payload("Write", "tests/notes.md", "# notes"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_04_json_under_tests_allows_without_grant(self):
        r = run_hook(
            "guard_tests.py",
            self.edit_payload("Write", "tests/fixture.json", "{}"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_04_txt_under_tests_allows_without_grant(self):
        r = run_hook(
            "guard_tests.py",
            self.edit_payload("Write", "tests/readme.txt", "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_04_py_under_tests_blocks_without_grant(self):
        r = run_hook(
            "guard_tests.py",
            self.edit_payload("Write", "tests/test_x.py", "x = 1"),
            self.root,
        )
        self.assertEqual(r.returncode, 2, r.stderr)


# --------------------------------------------------------------------------
# BR-ASR-05 matching builtin override
# --------------------------------------------------------------------------
class TestBrAsr05Models(Base):
    def write_manifest(self, obj=None):
        if obj is None:
            obj = {
                "version": 1,
                "roles": {"developer": "opus"},
                "builtins": {
                    "Explore": "opus",
                    "general-purpose": "opus",
                    "Plan": "opus",
                    "claude": "opus",
                },
            }
        self.write("company/models.json", json.dumps(obj))

    def spawn(self, **ti):
        return run_hook(
            "guard_models.py",
            {"hook_event_name": "PreToolUse", "tool_name": "Task",
             "tool_input": ti, "cwd": self.root},
            self.root,
        )

    def test_br_asr_05_override_equals_pin_allows(self):
        self.write_manifest()
        r = self.spawn(subagent_type="Explore", model="opus")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_05_override_mismatch_blocks(self):
        self.write_manifest()
        r = self.spawn(subagent_type="Explore", model="haiku")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_br_asr_05_missing_override_blocks(self):
        self.write_manifest()
        r = self.spawn(subagent_type="Explore")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_br_asr_05_hotfix_bypasses(self):
        self.write_manifest()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = self.spawn(subagent_type="Explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_05_no_builtins_section_fail_open(self):
        self.write_manifest({"version": 1, "roles": {"developer": "opus"}})
        r = self.spawn(subagent_type="Explore")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_br_asr_05_roles_win_over_builtins(self):
        self.write_manifest({
            "version": 1,
            "roles": {"developer": "opus"},
            "builtins": {"developer": "opus", "Explore": "opus"},
        })
        r = self.spawn(subagent_type="developer")
        self.assertEqual(r.returncode, 0, r.stderr)


# --------------------------------------------------------------------------
# BR-ASR-06 stamp early-exit; FR-ASR-09 parallel
# --------------------------------------------------------------------------
class TestBrAsr06AndParallel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-asr-gates-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git_project(self, gates):
        make_project(self.tmp, gates)
        subprocess.run(["git", "init", "-q", self.tmp], check=True,
                       capture_output=True)
        git(self.tmp, "config", "user.email", "t@example.com")
        git(self.tmp, "config", "user.name", "test")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "init")

    def stamp_bytes(self):
        path = os.path.join(self.tmp, "company", "state", "gates.status")
        with open(path, "rb") as f:
            return f.read()

    def test_br_asr_06_green_matching_hash_skips(self):
        self.git_project([{"name": "ok", "command": "true"}])
        r1 = run_ladder(self.tmp)
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        before = self.stamp_bytes()
        r2 = run_ladder(self.tmp)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("reusing stamp", r2.stdout)
        self.assertEqual(self.stamp_bytes(), before)
        log = open(os.path.join(
            self.tmp, "company", "state", "gates.log")).read()
        self.assertIn("reused=1", log)

    def test_br_asr_06_missing_stamp_runs(self):
        self.git_project([{"name": "ok", "command": "echo ran-once"}])
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("reusing stamp", r.stdout)
        self.assertIn("ran-once", r.stdout)

    def test_br_asr_06_red_stamp_runs(self):
        self.git_project([{"name": "bad", "command": "false"}])
        r1 = run_ladder(self.tmp)
        self.assertEqual(r1.returncode, 1)
        r2 = run_ladder(self.tmp)
        self.assertEqual(r2.returncode, 1)
        self.assertNotIn("reusing stamp", r2.stdout)

    def test_br_asr_06_stale_stamp_runs(self):
        self.git_project([{"name": "ok", "command": "true"}])
        r1 = run_ladder(self.tmp)
        self.assertEqual(r1.returncode, 0)
        with open(os.path.join(self.tmp, "src.py"), "w") as f:
            f.write("x = 1\n")
        r2 = run_ladder(self.tmp)
        self.assertEqual(r2.returncode, 0, r2.stdout)
        self.assertNotIn("reusing stamp", r2.stdout)

    def test_br_asr_06_malformed_stamp_runs(self):
        self.git_project([{"name": "ok", "command": "true"}])
        run_ladder(self.tmp)
        with open(os.path.join(self.tmp, "company", "state",
                               "gates.status"), "w") as f:
            f.write("{not json")
        r = run_ladder(self.tmp)
        self.assertNotIn("reusing stamp", r.stdout)

    def test_br_asr_06_checksum_invalid_runs(self):
        self.git_project([{"name": "ok", "command": "true"}])
        run_ladder(self.tmp)
        path = os.path.join(self.tmp, "company", "state", "gates.status")
        data = json.load(open(path))
        data["status"] = "green"
        data["checksum"] = "0" * 64
        json.dump(data, open(path, "w"))
        r = run_ladder(self.tmp)
        self.assertNotIn("reusing stamp", r.stdout)

    def test_br_asr_06_stamper_absent_runs(self):
        make_project(self.tmp, [{"name": "ok", "command": "echo went"}],
                     with_stamper=False)
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("went", r.stdout)
        self.assertNotIn("reusing stamp", r.stdout)

    def test_br_asr_06_no_git_hash_runs_not_skips(self):
        make_project(self.tmp, [{"name": "ok", "command": "echo first"}])
        r1 = run_ladder(self.tmp)
        self.assertEqual(r1.returncode, 0)
        r2 = run_ladder(self.tmp)
        self.assertNotIn("reusing stamp", r2.stdout)
        self.assertIn("first", r2.stdout)

    def test_fr_asr_09_parallel_preserves_ladder_order(self):
        src = open(os.path.join(REPO_ROOT, "company", "run-gates.sh")).read()
        self.assertIn("run_one_gate \"$INDEX\" \"$NAME\" \"$CMD\" \"$SAFE_NAME\" &", src)
        self.assertIn("\nwait\n", src)
        make_project(self.tmp, [
            {"name": "slow", "command": "sleep 0.4; echo slow-done"},
            {"name": "fast", "command": "echo fast-done"},
        ])
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        ladder = r.stdout.split("Gate ladder", 1)[-1]
        self.assertLess(ladder.find("slow"), ladder.find("fast"))
        self.assertIn("slow-done", r.stdout)
        self.assertIn("fast-done", r.stdout)

    def test_fr_asr_09_red_gate_still_fails_the_runner(self):
        make_project(self.tmp, [
            {"name": "ok", "command": "true"},
            {"name": "bad", "command": "false"},
        ])
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 1)


# --------------------------------------------------------------------------
# FR-ASR-11 pipefail sites; FR-ASR-12 rent; FR-ASR-13 seam
# --------------------------------------------------------------------------
class TestPipefailRentSeam(unittest.TestCase):
    def test_fr_asr_11_no_printf_grep_q_in_update_or_cli(self):
        for rel in ("tests/install/test_update.sh", "tests/cli/test_cli.sh"):
            text = open(os.path.join(REPO_ROOT, rel)).read()
            self.assertNotIn("printf '%s' \"$OUT\" | grep -q", text, rel)
            self.assertNotIn("printf '%s' \"$WIN_OUT\" | grep -q", text, rel)

    def test_fr_asr_12_rent_report_names_guard_commit(self):
        r = subprocess.run(
            [sys.executable,
             os.path.join(HOOKS_DIR, "rent_report.py")],
            cwd=REPO_ROOT,
            capture_output=True, text=True,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=REPO_ROOT),
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("guard_commit", r.stdout)
        self.assertIn("exempt", r.stdout)

    def test_fr_asr_13_overlap_exits_one(self):
        tmp = tempfile.mkdtemp(prefix="cc-seam-")
        try:
            bdir = os.path.join(tmp, "company", "briefs")
            os.makedirs(bdir)
            open(os.path.join(bdir, "a.md"), "w").write(
                "## You own\n- `src/api/`\n")
            open(os.path.join(bdir, "b.md"), "w").write(
                "## You own\n- `src/api/handlers/`\n")
            r = subprocess.run(
                [sys.executable, os.path.join(HOOKS_DIR, "seam_check.py"),
                 "--briefs-dir", bdir],
                cwd=tmp, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("OVERLAP", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fr_asr_13_disjoint_exits_zero(self):
        tmp = tempfile.mkdtemp(prefix="cc-seam-")
        try:
            bdir = os.path.join(tmp, "company", "briefs")
            os.makedirs(bdir)
            open(os.path.join(bdir, "a.md"), "w").write(
                "## You own\n- `src/api/`\n")
            open(os.path.join(bdir, "b.md"), "w").write(
                "## You own\n- `src/web/`\n")
            r = subprocess.run(
                [sys.executable, os.path.join(HOOKS_DIR, "seam_check.py"),
                 "--briefs-dir", bdir],
                cwd=tmp, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fr_asr_13_missing_dir_exits_zero(self):
        tmp = tempfile.mkdtemp(prefix="cc-seam-")
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(HOOKS_DIR, "seam_check.py"),
                 "--briefs-dir", os.path.join(tmp, "nope")],
                cwd=tmp, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestFrAsr05Through18Citations(unittest.TestCase):
    """BR-ASR-10: leftover FR IDs cited in implementing files or this module."""

    def test_fr_ids_appear_in_code_or_this_file(self):
        this = open(__file__).read()
        hooks = ""
        for name in ("guard_commit.py", "guard_tests.py", "guard_models.py",
                     "guard_frozen.py", "dispatch_feed.py", "rent_report.py"):
            hooks += open(os.path.join(HOOKS_DIR, name)).read()
        # FR-ASR-10 lives in company/run-gates.sh; FR-ASR-14..18,20 in prompts.
        extra = open(os.path.join(REPO_ROOT, "company", "run-gates.sh")).read()
        extra += "FR-ASR-14 FR-ASR-15 FR-ASR-16 FR-ASR-17 FR-ASR-18 FR-ASR-20 "
        extra += "BR-ASR-10 BR-ASR-11 "
        # FR-ASR-23..28 are doctrine/prompt requirements (intent replication,
        # outcome DoD, waist-as-code, the product-manager deletion,
        # conditional divergence, architect narrowing).
        extra += "FR-ASR-23 FR-ASR-24 FR-ASR-25 FR-ASR-26 FR-ASR-27 FR-ASR-28"
        blob = this + hooks + extra
        for i in range(1, 29):
            token = "FR-ASR-%02d" % i
            self.assertIn(token, blob, token)
        for i in range(1, 13):
            token = "BR-ASR-%02d" % i
            self.assertIn(token, blob, token)

    def test_br_asr_07_gates_config_keeps_placeholders(self):
        """BR-ASR-07 dual-nature: the committed template keeps CONFIGURE ME.

        This checkout may carry a local-only gates.config (never commit);
        assert against HEAD so the test does not read that file.
        """
        r = subprocess.run(
            ["git", "show", "HEAD:company/gates.config"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        self.assertIn("CONFIGURE ME", r.stdout)

    def test_br_asr_09_new_clis_are_stdlib(self):
        """BR-ASR-09: rent_report and seam_check import only stdlib + _common."""
        for name in ("rent_report.py", "seam_check.py", "dispatch_feed.py"):
            src = open(os.path.join(HOOKS_DIR, name)).read()
            self.assertNotIn("import requests", src)
            self.assertNotIn("import yaml", src)

    def test_br_asr_12_unrecoverable_rent_exempt(self):
        """BR-ASR-12: CLAIMS marks unrecoverable guards rent-exempt."""
        import rent_report
        for hook in ("guard_secrets", "guard_frozen", "witness_check",
                     "trace_check"):
            self.assertTrue(rent_report.CLAIMS[hook][1], hook)


if __name__ == "__main__":
    unittest.main()
