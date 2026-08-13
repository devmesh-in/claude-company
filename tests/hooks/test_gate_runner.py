#!/usr/bin/env python3
"""Acceptance tests for the L3 runner lane (FR-HP-20 through FR-HP-28).

These are written from the brief's acceptance criteria rather than from the
implementations, and they drive real subprocesses: a real `bash run-gates.sh`
against throwaway fixture projects, a real `git worktree` for the root
resolution proof, and the real `guard_models.py --check` CLI against fixture
copies of `.claude/settings.json`.

The three properties worth stating up front, because they are the ones that
were broken:

  1. FR-HP-28: the ladder gates and stamps the tree containing the cwd. The
     harness pins CLAUDE_PROJECT_DIR to the MAIN checkout even for a subagent
     whose cwd is a worktree, so the old precedence handed a lead a green
     stamp for code it did not build. The stamper resolves its own root, so
     the runner has to hand it the resolved one or the same false green comes
     back in a different place.
  2. FR-HP-20/21: a green gate is quiet but its output is PRESERVED. A pointer
     line naming a deleted file is worse than no pointer.
  3. FR-HP-23: the freeze needs all THREE landing spots. ALWAYS_DEFAULTS is the
     only one that reaches an existing install on update, the registry `always`
     list is the only one that reaches a fresh install, and .gitignore is the
     only one that keeps the run log out of git.

Telemetry is never load-bearing: a read-only company/state must not change the
runner's exit code, and that is asserted here rather than assumed.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, HOOKS_DIR, run_cli, run_hook, git  # noqa: E402

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
RUNNER = os.path.join(REPO_ROOT, "company", "run-gates.sh")

# 500 noise lines then three BLANK lines, so "last 3 non-empty lines" is a
# different answer from "last 3 lines" and the test can tell them apart.
LOUD = (
    "awk 'BEGIN{for(i=1;i<=500;i++) print \"noise \" i}'; printf '\\n\\n\\n'"
)
LOUD_FAIL = LOUD + "; exit 1"


def make_project(dst, gates, with_stamper=True):
    """Lay down a minimal project: the runner, gates.config, the stamper."""
    os.makedirs(os.path.join(dst, "company"), exist_ok=True)
    shutil.copy2(RUNNER, os.path.join(dst, "company", "run-gates.sh"))
    if with_stamper:
        hooks = os.path.join(dst, ".claude", "hooks")
        os.makedirs(hooks, exist_ok=True)
        for name in ("gate_stamp.py", "_common.py"):
            shutil.copy2(
                os.path.join(HOOKS_DIR, name), os.path.join(hooks, name)
            )
    with open(os.path.join(dst, "company", "gates.config"), "w") as f:
        json.dump({"gates": gates}, f)


def run_ladder(cwd, project_dir=None, extra_env=None):
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", os.path.join(cwd, "company", "run-gates.sh")],
        cwd=cwd, capture_output=True, text=True, env=env,
    )


def gate_section(stdout, name):
    """Lines the runner printed for one gate, header and separator excluded."""
    lines = stdout.splitlines()
    try:
        start = lines.index("-> gate: %s" % name)
    except ValueError:
        raise AssertionError(
            "no header line for gate %r in:\n%s" % (name, stdout)
        )
    rest = lines[start + 1:]
    for i, line in enumerate(rest):
        if line.startswith("Gate ladder"):
            rest = rest[:i]
            break
    while rest and not rest[-1].strip():
        rest.pop()
    return rest


class RunnerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-runner-")

    def tearDown(self):
        state = os.path.join(self.tmp, "company", "state")
        if os.path.isdir(state):
            os.chmod(state, stat.S_IRWXU)
        shutil.rmtree(self.tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# FR-HP-20 / FR-HP-21 - quiet-pass, proven by line count
# --------------------------------------------------------------------------
class QuietPass(RunnerBase):
    def test_green_gate_prints_tail_and_pointer_only(self):
        make_project(self.tmp, [{"name": "loud", "command": LOUD}])
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        body = gate_section(r.stdout, "loud")
        # 3 tail lines plus exactly one pointer line. OQ-HP-04 assumption:
        # 3 lines and no knob.
        self.assertLessEqual(len(body), 4, "gate body was:\n%s" % "\n".join(body))
        self.assertNotIn("noise 1\n", r.stdout)
        self.assertIn("noise 500", r.stdout)
        self.assertIn("noise 498", r.stdout)
        self.assertNotIn("noise 497", r.stdout)
        self.assertIn("company/state/gate-output/loud.log", r.stdout)

    def test_red_gate_echoes_everything(self):
        make_project(self.tmp, [{"name": "loud", "command": LOUD_FAIL}])
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        body = gate_section(r.stdout, "loud")
        self.assertGreaterEqual(
            len(body), 500, "red gate printed only %d lines" % len(body)
        )
        self.assertIn("noise 1", r.stdout)
        self.assertIn("noise 500", r.stdout)

    def test_full_output_preserved_for_green_and_red(self):
        make_project(self.tmp, [
            {"name": "ok", "command": "printf 'a\\nb\\n'"},
            {"name": "bad", "command": "printf 'x\\ny\\n' >&2; exit 3"},
        ])
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out_dir = os.path.join(self.tmp, "company", "state", "gate-output")
        for name, want in (("ok", "a\nb\n"), ("bad", "x\ny\n")):
            path = os.path.join(out_dir, "%s.log" % name)
            self.assertTrue(os.path.exists(path), "missing %s" % path)
            with open(path) as f:
                self.assertEqual(f.read(), want)

    def test_preserved_output_is_replaced_not_appended(self):
        make_project(self.tmp, [{"name": "ok", "command": "printf 'a\\n'"}])
        run_ladder(self.tmp)
        run_ladder(self.tmp)
        path = os.path.join(
            self.tmp, "company", "state", "gate-output", "ok.log"
        )
        with open(path) as f:
            self.assertEqual(f.read(), "a\n")

    def test_exit_code_contract_unchanged(self):
        make_project(self.tmp, [
            {"name": "a", "command": "true"},
            {"name": "b", "command": "true"},
        ])
        self.assertEqual(run_ladder(self.tmp).returncode, 0)
        make_project(self.tmp, [
            {"name": "a", "command": "true"},
            {"name": "b", "command": "false"},
        ])
        self.assertEqual(run_ladder(self.tmp).returncode, 1)

    def test_no_temp_file_left_behind(self):
        # Private TMPDIR: the shared one is noisy while sibling agents run.
        scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(scratch)
        make_project(self.tmp, [
            {"name": "ok", "command": "printf 'a\\n'"},
            {"name": "bad", "command": "printf 'b\\n'; exit 1"},
        ])
        run_ladder(self.tmp, extra_env={"TMPDIR": scratch})
        strays = [n for n in os.listdir(scratch) if n.startswith("rungates.")]
        self.assertEqual(strays, [], "runner temp files left behind: %s" % strays)


# --------------------------------------------------------------------------
# FR-HP-22 - gates.log, one appended line per ladder run
# --------------------------------------------------------------------------
class GatesLog(RunnerBase):
    def log_lines(self):
        path = os.path.join(self.tmp, "company", "state", "gates.log")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]

    def test_three_runs_three_lines_in_order(self):
        make_project(self.tmp, [
            {"name": "alpha", "command": "true"},
            {"name": "beta", "command": "true"},
        ])
        for _ in range(3):
            run_ladder(self.tmp)
        lines = self.log_lines()
        self.assertEqual(len(lines), 3, "\n".join(lines))
        for line in lines:
            for name in ("alpha", "beta"):
                self.assertRegex(line, r"\b%s:(PASS|FAIL):\d+" % name)
            self.assertRegex(line, r"total=\d+")

    def test_timestamp_is_iso8601_utc(self):
        make_project(self.tmp, [{"name": "alpha", "command": "true"}])
        run_ladder(self.tmp)
        stamp = self.log_lines()[0].split()[0]
        # Raises on anything that is not YYYY-MM-DDTHH:MM:SSZ.
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")

    def test_status_field_tracks_the_ladder(self):
        make_project(self.tmp, [{"name": "alpha", "command": "true"}])
        run_ladder(self.tmp)
        make_project(self.tmp, [{"name": "alpha", "command": "false"}])
        run_ladder(self.tmp)
        lines = self.log_lines()
        self.assertIn("status=green", lines[0])
        self.assertIn("status=red", lines[1])
        self.assertRegex(lines[1], r"\balpha:FAIL:\d+")

    def test_gate_order_matches_ladder_order(self):
        make_project(self.tmp, [
            {"name": "one", "command": "true"},
            {"name": "two", "command": "true"},
            {"name": "three", "command": "true"},
        ])
        run_ladder(self.tmp)
        line = self.log_lines()[0]
        self.assertLess(line.index("one:"), line.index("two:"))
        self.assertLess(line.index("two:"), line.index("three:"))


# --------------------------------------------------------------------------
# Telemetry is never load-bearing
# --------------------------------------------------------------------------
class TelemetryNeverBlocks(RunnerBase):
    def make_state_readonly(self):
        state = os.path.join(self.tmp, "company", "state")
        os.makedirs(state, exist_ok=True)
        os.chmod(state, stat.S_IRUSR | stat.S_IXUSR)

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_readonly_state_preserves_green_exit(self):
        make_project(self.tmp, [{"name": "ok", "command": "printf 'a\\n'"}])
        self.make_state_readonly()
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_readonly_state_preserves_red_exit(self):
        make_project(self.tmp, [{"name": "bad", "command": "exit 2"}])
        self.make_state_readonly()
        r = run_ladder(self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


# --------------------------------------------------------------------------
# FR-HP-28 - root resolution, proven with a real git worktree
# --------------------------------------------------------------------------
class RootResolution(RunnerBase):
    def init_repo(self, path):
        os.makedirs(path, exist_ok=True)
        subprocess.run(["git", "init", "-q", path], check=True,
                       capture_output=True)
        git(path, "config", "user.email", "t@example.com")
        git(path, "config", "user.name", "test")

    def test_worktree_ladder_gates_and_stamps_the_worktree(self):
        main = os.path.join(self.tmp, "main")
        self.init_repo(main)
        make_project(main, [{"name": "ok", "command": "printf 'main\\n'"}])
        git(main, "add", "-A")
        git(main, "commit", "-q", "-m", "init")

        wt = os.path.join(main, ".claude", "worktrees", "x")
        r = git(main, "worktree", "add", "-q", wt, "-b", "task/x")
        self.assertEqual(r.returncode, 0, r.stderr)

        # Make the worktree's content genuinely different, so an equal work
        # hash would be a real failure rather than a coincidence.
        with open(os.path.join(wt, "only-here.txt"), "w") as f:
            f.write("worktree content\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "worktree change")

        # The main checkout's stamp is the thing that must NOT be touched.
        main_state = os.path.join(main, "company", "state")
        os.makedirs(main_state, exist_ok=True)
        main_stamp = os.path.join(main_state, "gates.status")
        with open(main_stamp, "w") as f:
            f.write("{\"sentinel\": true}\n")
        before = open(main_stamp, "rb").read()

        # cwd is the worktree; CLAUDE_PROJECT_DIR points at the main checkout,
        # exactly as the harness pins it for a subagent.
        r = run_ladder(wt, project_dir=main)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(wt, r.stdout)

        wt_stamp = os.path.join(wt, "company", "state", "gates.status")
        self.assertTrue(os.path.exists(wt_stamp),
                        "no stamp in the worktree:\n%s" % r.stdout)
        self.assertEqual(open(main_stamp, "rb").read(), before,
                         "the main checkout's stamp was overwritten")

        sys.path.insert(0, HOOKS_DIR)
        import _common as c  # noqa: E402
        with open(wt_stamp) as f:
            stamp = json.load(f)
        self.assertEqual(stamp["status"], "green")
        self.assertEqual(stamp["work_hash"], c.work_hash(wt))
        self.assertNotEqual(c.work_hash(wt), c.work_hash(main))

        # The gate ran from the worktree, so its preserved output is there.
        self.assertTrue(os.path.exists(os.path.join(
            wt, "company", "state", "gate-output", "ok.log")))

    def test_main_checkout_behaviour_unchanged(self):
        main = os.path.join(self.tmp, "main")
        self.init_repo(main)
        make_project(main, [{"name": "ok", "command": "true"}])
        r = run_ladder(main, project_dir=main)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(main, "company", "state", "gates.status")))

    def test_outside_any_git_tree_falls_back_to_project_dir(self):
        plain = os.path.join(self.tmp, "plain")
        make_project(plain, [{"name": "ok", "command": "true"}])
        elsewhere = os.path.join(self.tmp, "elsewhere")
        make_project(elsewhere, [{"name": "ok", "command": "true"}])
        r = run_ladder(plain, project_dir=elsewhere)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(elsewhere, r.stdout)

    def test_outside_any_git_tree_and_no_project_dir_falls_back_to_pwd(self):
        plain = os.path.join(self.tmp, "plain")
        make_project(plain, [{"name": "ok", "command": "true"}])
        r = run_ladder(plain, project_dir=None)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(plain, "company", "state", "gates.status")))


# --------------------------------------------------------------------------
# FR-HP-24 - the stamp is written atomically
# --------------------------------------------------------------------------
class AtomicStamp(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-stamp-")
        os.makedirs(os.path.join(self.root, "company", "state"))
        sys.path.insert(0, HOOKS_DIR)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_concurrent_reader_never_sees_a_torn_stamp(self):
        import _common as c
        import gate_stamp

        # Deliberately NOT a git repo: work_hash short-circuits to "no-git",
        # so 200 stamps do not become 800 git subprocesses.
        results = json.dumps({"gates": [
            {"name": "g%d" % i, "ok": True, "detail": "x" * 400}
            for i in range(40)
        ]})
        seen = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                ok, reason = c.check_stamp(self.root)
                if reason == "gates.status is malformed":
                    seen.append(reason)

        t = threading.Thread(target=reader)
        t.start()
        try:
            for _ in range(200):
                gate_stamp.write_stamp(self.root, results)
        finally:
            stop.set()
            t.join()
        self.assertEqual(seen, [], "reader saw %d torn stamps" % len(seen))

    def test_failed_write_leaves_destination_and_directory_clean(self):
        import gate_stamp
        state = os.path.join(self.root, "company", "state")
        dest = os.path.join(state, "gates.status")
        gate_stamp.write_stamp(self.root, json.dumps(
            {"gates": [{"name": "a", "ok": True}]}))
        before = open(dest, "rb").read()
        listing_before = sorted(os.listdir(state))

        # os.replace is the commit point of an atomic write, and the spec
        # mandates it, so failing it exercises the real cleanup path whether
        # the writer is the L1 helper or the local fallback.
        real_replace = os.replace

        def boom(*a, **kw):
            raise RuntimeError("disk full")

        os.replace = boom
        try:
            with self.assertRaises(Exception):
                gate_stamp.write_stamp(self.root, json.dumps(
                    {"gates": [{"name": "a", "ok": False}]}))
        finally:
            os.replace = real_replace

        self.assertEqual(open(dest, "rb").read(), before)
        self.assertEqual(sorted(os.listdir(state)), listing_before,
                         "a temp file was left behind")

    def test_stamp_stays_checksum_sealed(self):
        import _common as c
        import gate_stamp
        gate_stamp.write_stamp(self.root, json.dumps(
            {"gates": [{"name": "a", "ok": True}]}))
        with open(os.path.join(
                self.root, "company", "state", "gates.status")) as f:
            stamp = json.load(f)
        # Every non-checksum key is inside the checksum. A key added to the
        # payload without this holding would be a hand-editable field.
        payload = {k: v for k, v in stamp.items() if k != "checksum"}
        self.assertEqual(stamp["checksum"], c.stamp_checksum(payload))
        for key in payload:
            mutated = dict(payload)
            mutated[key] = "tampered"
            self.assertNotEqual(stamp["checksum"], c.stamp_checksum(mutated),
                                "%s sits outside the checksum" % key)


# --------------------------------------------------------------------------
# FR-HP-23 - the freeze needs all three landing spots
# --------------------------------------------------------------------------
NEW_STATE_PATHS = ("company/state/gates.log", "company/state/gate-output/**")


class FreezeAndIgnore(Base):
    def test_always_defaults_carries_both_patterns(self):
        sys.path.insert(0, HOOKS_DIR)
        import guard_frozen
        for pat in NEW_STATE_PATHS:
            self.assertIn(pat, guard_frozen.ALWAYS_DEFAULTS)

    def test_registry_always_list_carries_both_patterns(self):
        with open(os.path.join(
                REPO_ROOT, "company", "frozen-surfaces.json")) as f:
            always = json.load(f)["always"]
        for pat in NEW_STATE_PATHS:
            self.assertIn(pat, always)

    def test_gitignore_carries_both_paths(self):
        with open(os.path.join(REPO_ROOT, ".gitignore")) as f:
            entries = [ln.strip() for ln in f if ln.strip()]
        self.assertIn("company/state/gates.log", entries)
        self.assertIn("company/state/gate-output/", entries)

    def test_run_artifacts_are_git_ignored_for_real(self):
        for rel in ("company/state/gates.log",
                    "company/state/gate-output/tests.log"):
            r = subprocess.run(
                ["git", "-C", REPO_ROOT, "check-ignore", "-q", rel],
                capture_output=True,
            )
            self.assertEqual(r.returncode, 0, "%s is not git-ignored" % rel)

    def block_case(self, rel, with_registry):
        if with_registry:
            self.write("company/frozen-surfaces.json",
                       json.dumps({"version": 1, "surfaces": [],
                                   "always": list(NEW_STATE_PATHS)}))
        r = run_hook("guard_frozen.py",
                     self.edit_payload("Edit",
                                       os.path.join(self.root, rel), "x"),
                     self.root)
        self.assertEqual(r.returncode, 2, "%s allowed (registry=%s): %s"
                         % (rel, with_registry, r.stderr))
        log = os.path.join(self.root, "company", "state", "adherence.log")
        self.assertTrue(os.path.exists(log))
        with open(log) as f:
            self.assertIn(rel, f.read())

    def test_gates_log_blocked_without_registry(self):
        # No frozen-surfaces.json at all: only ALWAYS_DEFAULTS can save this,
        # and ALWAYS_DEFAULTS is the copy that reaches an existing install.
        self.block_case("company/state/gates.log", with_registry=False)

    def test_gates_log_blocked_with_registry(self):
        self.block_case("company/state/gates.log", with_registry=True)

    def test_gate_output_blocked_without_registry(self):
        self.block_case("company/state/gate-output/tests.log",
                        with_registry=False)

    def test_gate_output_blocked_with_registry(self):
        self.block_case("company/state/gate-output/tests.log",
                        with_registry=True)


# --------------------------------------------------------------------------
# FR-HP-25 - the wiring gate
# --------------------------------------------------------------------------
class WiringGate(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-wiring-")
        # A faithful copy of the shipped project: real settings, real hook
        # files, real manifest, real agent frontmatter.
        os.makedirs(os.path.join(self.root, ".claude"))
        shutil.copy2(
            os.path.join(REPO_ROOT, ".claude", "settings.json"),
            os.path.join(self.root, ".claude", "settings.json"),
        )
        shutil.copytree(HOOKS_DIR, os.path.join(self.root, ".claude", "hooks"))
        shutil.copytree(
            os.path.join(REPO_ROOT, ".claude", "agents"),
            os.path.join(self.root, ".claude", "agents"),
        )
        os.makedirs(os.path.join(self.root, "company"))
        shutil.copy2(
            os.path.join(REPO_ROOT, "company", "models.json"),
            os.path.join(self.root, "company", "models.json"),
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def settings(self):
        with open(os.path.join(self.root, ".claude", "settings.json")) as f:
            return json.load(f)

    def save(self, obj):
        with open(os.path.join(self.root, ".claude", "settings.json"), "w") as f:
            json.dump(obj, f)

    def check(self):
        return run_cli("guard_models.py", ["--check"], self.root)

    def test_shipped_settings_pass(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unwiring_stop_gate_fails_naming_event_and_hook(self):
        s = self.settings()
        s["hooks"]["Stop"][0]["hooks"] = [
            h for h in s["hooks"]["Stop"][0]["hooks"]
            if "stop_gate.py" not in h.get("command", "")
        ]
        self.save(s)
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Stop", r.stdout)
        self.assertIn("stop_gate.py", r.stdout)

    def test_removing_the_bash_group_names_all_its_hooks(self):
        s = self.settings()
        s["hooks"]["PreToolUse"] = [
            g for g in s["hooks"]["PreToolUse"] if g.get("matcher") != "Bash"
        ]
        self.save(s)
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        for name in ("guard_commit.py", "guard_secrets.py",
                     "guard_tests.py", "guard_provenance.py"):
            self.assertIn(name, r.stdout)

    def test_absent_hook_file_makes_its_rows_unchecked(self):
        # An older install simply does not have a newer hook. That is not a
        # wiring failure, so its rows drop out entirely.
        os.unlink(os.path.join(self.root, ".claude", "hooks",
                               "guard_tests.py"))
        s = self.settings()
        for group in s["hooks"]["PreToolUse"]:
            group["hooks"] = [
                h for h in group["hooks"]
                if "guard_tests.py" not in h.get("command", "")
            ]
        self.save(s)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_extra_hook_is_allowed(self):
        s = self.settings()
        s["hooks"]["PreToolUse"][0]["hooks"].append(
            {"type": "command", "command": "python3 /somewhere/extra.py"}
        )
        s["hooks"]["PreToolUse"].append(
            {"matcher": "Read", "hooks": [
                {"type": "command", "command": "python3 /somewhere/other.py"}]}
        )
        self.save(s)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_settings_local_json_is_ignored(self):
        s = self.settings()
        stripped = json.loads(json.dumps(s))
        stripped["hooks"]["Stop"][0]["hooks"] = [
            h for h in stripped["hooks"]["Stop"][0]["hooks"]
            if "stop_gate.py" not in h.get("command", "")
        ]
        self.save(stripped)
        with open(os.path.join(self.root, ".claude",
                               "settings.local.json"), "w") as f:
            json.dump(s, f)
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_spawn_wiring_assertion_still_fires(self):
        # Regression on the shipped behaviour this generalizes.
        s = self.settings()
        for group in s["hooks"]["PreToolUse"]:
            if "Task" in (group.get("matcher") or "").split("|"):
                group["hooks"] = [
                    h for h in group["hooks"]
                    if "guard_models.py" not in h.get("command", "")
                ]
        self.save(s)
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("guard_models.py", r.stdout)

    def test_missing_settings_file_is_a_loud_failure(self):
        # --check is a CLI gate, not a hook: a project with hooks on disk and
        # no settings.json IS un-wired, and must not read as agreement.
        os.unlink(os.path.join(self.root, ".claude", "settings.json"))
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)


# --------------------------------------------------------------------------
# Guard against re-adding the refuted design
# --------------------------------------------------------------------------
class RefutedDesignStaysOut(unittest.TestCase):
    """Repo-scoped cached gate skips are a false-green generator here.

    The reference implementation skips a gate when its repo's tree hash is
    unchanged since the last green stamp, and its check returns green
    UNCONDITIONALLY when the tree-hash map is empty - which is every
    single-repo project, i.e. this one. company/specs/spec-repo-scoped-
    enforcement.md is already parked with the evidence refuting the premise.
    These assertions exist so a future port cannot quietly bring it back.
    """

    def test_runner_has_no_cached_skip_path(self):
        with open(RUNNER) as f:
            src = f.read()
        for token in ("tree_hashes", "gate_tree_hashes", "FORCE_ALL",
                      "cached=", "\"SKIP\""):
            self.assertNotIn(token, src,
                             "run-gates.sh re-introduced %r" % token)

    def test_stamp_payload_has_no_tree_hashes(self):
        with open(os.path.join(HOOKS_DIR, "gate_stamp.py")) as f:
            src = f.read()
        self.assertNotIn("tree_hashes", src)
        self.assertNotIn("gate_tree_hashes", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
