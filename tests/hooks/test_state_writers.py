#!/usr/bin/env python3
"""Concurrency tests for the two state writers: witness_check and cost_capture.

FR-HP-30 (witness registry), FR-HP-31 (cost cursor), FR-HP-33 (no non-atomic
JSON write left behind).

Every race here is a REAL two-process race driven through subprocess. Threads
inside one interpreter never exercise flock between processes, so a threaded
version of these tests would pass against completely unlocked code and prove
nothing.

Each race runs an A/B against a throwaway COPY of .claude/hooks that lives in
the fixture root - the repo's own hooks and its checksum-sealed
company/witnesses.json are never executed against or written to. Both arms get
the SAME widened read-modify-write window (a sleep patched into the copied
source between the read and the write); the UNLOCKED arm additionally neuters
state_lock in the copied _common.py. The locked arm must keep both writes; the
unlocked arm must LOSE one. If the unlocked arm ever stops losing, these tests
are no longer evidence and they say so out loud instead of passing quietly.

Run: python3 -m unittest tests.hooks.test_state_writers -v
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOKS_DIR = os.path.join(REPO_ROOT, ".claude", "hooks")
REAL_REGISTRY = os.path.join(REPO_ROOT, "company", "witnesses.json")

# TEST fixture constant only - no production code gains a number from this
# lane. It is the artificial read-modify-write window both A/B arms get, wide
# enough to swamp interpreter startup jitter and well under state_lock's own
# 2.0s fail-open wait so the locked arm never degrades to unlocked.
WIDEN_SECONDS = 0.4

# Neutered state_lock for the UNLOCKED arm. A generator that yields and then
# returns is a context manager that takes no lock at all; everything after the
# return is the real body, now unreachable.
NEUTERED_LOCK = (
    'def state_lock(root, timeout=2.0):\n'
    '    yield\n'
    '    return\n'
)
LOCK_DEF = 'def state_lock(root, timeout=2.0):  # OQ-HP-11 assumption\n'

WITNESS_WIDEN_ANCHOR = "        witnesses.append(witness)\n"
CURSOR_WIDEN_ANCHOR = "            cursor = c.read_json_file(cursor_path)\n"


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def patch_once(path, anchor, replacement):
    """Replace `anchor` with `replacement` in `path`, exactly once. Loud."""
    src = read_text(path)
    if src.count(anchor) != 1:
        raise AssertionError(
            "fixture patch anchor is not unique in {} (found {}):\n{!r}\n"
            "The race tests widen the copied hook's read-modify-write window "
            "by patching this anchor. If it moves, the A/B silently stops "
            "being a race - repair the anchor, never delete the assertion."
            .format(path, src.count(anchor), anchor))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src.replace(anchor, replacement, 1))


def build_hooks_copy(root, widen_anchor=None, unlock=False):
    """Copy .claude/hooks into the fixture root and optionally sabotage it.

    Returns the fixture hooks directory. Nothing outside `root` is touched.
    """
    dest = os.path.join(root, ".claude", "hooks")
    shutil.copytree(HOOKS_DIR, dest,
                    ignore=shutil.ignore_patterns("__pycache__"))
    if widen_anchor is not None:
        target, anchor = widen_anchor
        sleep_line = "{}__import__('time').sleep({})\n".format(
            anchor[:len(anchor) - len(anchor.lstrip())], WIDEN_SECONDS)
        patch_once(os.path.join(dest, target), anchor, anchor + sleep_line)
    if unlock:
        patch_once(os.path.join(dest, "_common.py"), LOCK_DEF, NEUTERED_LOCK)
    return dest


def fixture_env(root):
    """Subprocess env pinned to the fixture root.

    CLAUDE_PROJECT_DIR is popped first and then set: project_root() and
    witness_check.resolve_root() both prefer it, so an inherited value from the
    developer's own shell would silently aim these tests at the real repo.
    """
    env = os.environ.copy()
    env.pop("CLAUDE_PROJECT_DIR", None)
    env["CLAUDE_PROJECT_DIR"] = root
    return env


def run_cli(hooks_dir, args, root):
    return subprocess.run(
        [sys.executable, os.path.join(hooks_dir, "witness_check.py")] + args,
        capture_output=True, text=True, env=fixture_env(root))


def assistant_line(model, tin, tout):
    return json.dumps({
        "type": "assistant",
        "message": {"model": model,
                    "usage": {"input_tokens": tin, "output_tokens": tout}},
    })


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-statewriter-")
        os.makedirs(os.path.join(self.root, "company", "state"), exist_ok=True)
        self.real_registry_digest = sha256(REAL_REGISTRY)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def assert_real_registry_untouched(self):
        self.assertEqual(
            sha256(REAL_REGISTRY), self.real_registry_digest,
            "a test mutated the repo's own checksum-sealed "
            "company/witnesses.json - fixtures must stay inside the temp root")

    def registry(self):
        with open(os.path.join(self.root, "company", "witnesses.json")) as f:
            return json.load(f)

    def write(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def adherence(self):
        path = os.path.join(self.root, "company", "state", "adherence.log")
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()


# --- FR-HP-30: the registry race ----------------------------------------
class TestRegistryRace(FixtureCase):
    """Delete this class and two concurrent --add processes go back to reading
    the same list, computing the same W-NNN, and clobbering each other."""

    def race(self, unlock):
        hooks = build_hooks_copy(
            self.root,
            widen_anchor=("witness_check.py", WITNESS_WIDEN_ANCHOR),
            unlock=unlock)
        cli = os.path.join(hooks, "witness_check.py")
        env = fixture_env(self.root)
        procs = []
        for name in ("MARKER_A", "MARKER_B"):
            procs.append(subprocess.Popen(
                [sys.executable, cli, "--add",
                 "--file", "src/{}.py".format(name.lower()),
                 "--contains", name, "--task", "race",
                 "--why", "race arm {}".format(name)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env=env))
        outs = [p.communicate() for p in procs]
        codes = [p.returncode for p in procs]
        return self.registry()["witnesses"], codes, outs

    def test_locked_arm_keeps_both_rows_and_distinct_ids(self):
        # What breaks without this: concurrent --add loses a witness row.
        witnesses, codes, outs = self.race(unlock=False)
        self.assertEqual(codes, [0, 0], outs)
        self.assertEqual(len(witnesses), 2, witnesses)
        ids = sorted(w["id"] for w in witnesses)
        self.assertEqual(ids, ["W-001", "W-002"], witnesses)
        self.assertEqual(sorted(w["must_contain"] for w in witnesses),
                         ["MARKER_A", "MARKER_B"], witnesses)
        self.assert_real_registry_untouched()

    def test_unlocked_arm_actually_loses_a_row(self):
        # The negative control. If this ever passes cleanly, the locked arm
        # above proves nothing and this assertion must be the thing that says
        # so - do not weaken it into a skip.
        witnesses, codes, outs = self.race(unlock=True)
        self.assertEqual(codes, [0, 0], outs)
        ids = set(w["id"] for w in witnesses)
        self.assertTrue(
            len(witnesses) < 2 or len(ids) < 2,
            "UNLOCKED arm kept both rows with distinct ids ({}): the race "
            "window did not open, so the locked arm is not evidence of "
            "anything".format(witnesses))
        self.assert_real_registry_untouched()


# --- FR-HP-31: the cursor race ------------------------------------------
class TestCursorRace(FixtureCase):
    """Delete this class and two sessions stopping at once go back to dropping
    each other's cursor entry, which double-counts the loser's next delta."""

    MODEL = "claude-opus-4-20250101"

    def race(self, unlock):
        hooks = build_hooks_copy(
            self.root,
            widen_anchor=("cost_capture.py", CURSOR_WIDEN_ANCHOR),
            unlock=unlock)
        hook = os.path.join(hooks, "cost_capture.py")
        env = fixture_env(self.root)
        sessions = ["aaaaaaaa-1111-2222-3333-444444444444",
                    "bbbbbbbb-5555-6666-7777-888888888888"]
        procs = []
        handles = []
        for i, session in enumerate(sessions):
            transcript = self.write(
                "t{}.jsonl".format(i),
                assistant_line(self.MODEL, 100 * (i + 1), 200) + "\n")
            payload = {"hook_event_name": "Stop", "cwd": self.root,
                       "transcript_path": transcript, "session_id": session}
            # Payload on a file handle rather than a PIPE: both processes must
            # be running before either is waited on, or there is no race.
            stdin_file = self.write("p{}.json".format(i), json.dumps(payload))
            handle = open(stdin_file)
            handles.append(handle)
            procs.append(subprocess.Popen(
                [sys.executable, hook], stdin=handle,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env=env))
        outs = [p.communicate() for p in procs]
        codes = [p.returncode for p in procs]
        for handle in handles:
            handle.close()
        cursor_path = os.path.join(self.root, "company", "state",
                                   ".cost-cursor.json")
        with open(cursor_path) as f:
            return json.load(f), codes, outs, sessions

    def test_locked_arm_keeps_both_session_keys(self):
        # What breaks without this: one session's byte offset is lost, so its
        # whole transcript is re-counted on the next stop.
        cursor, codes, outs, sessions = self.race(unlock=False)
        self.assertEqual(codes, [0, 0], outs)
        self.assertEqual(sorted(cursor.keys()), sorted(sessions), cursor)
        for session in sessions:
            self.assertGreater(cursor[session]["offset"], 0, cursor)
        self.assert_real_registry_untouched()

    def test_unlocked_arm_actually_loses_a_session_key(self):
        # The negative control for the cursor. Same rule as the registry one:
        # if this stops failing, say so rather than deleting it.
        cursor, codes, outs, sessions = self.race(unlock=True)
        self.assertEqual(codes, [0, 0], outs)
        self.assertLess(
            len(cursor), 2,
            "UNLOCKED arm kept both session keys ({}): the race window did "
            "not open, so the locked arm is not evidence".format(cursor))


class TestCursorWriteFailureLogsNoLine(FixtureCase):
    """Delete this and a failed cursor write starts double-counting.

    costs.log is appended AFTER the locked section, so it is only safe to
    append when the cursor actually moved. While the cursor write was a bare
    open() a failure RAISED and the outer except swallowed it before any line
    was written; write_json_atomic reports failure by returning False instead,
    so the hook has to check it. Without that check the line is appended while
    the cursor stays put, and the next stop re-reads the same byte range and
    appends the identical delta again - the exact double-count this module's
    docstring calls its hard invariant.
    """

    MODEL = "claude-opus-4-20250101"
    SESSION = "cccccccc-9999-0000-1111-222222222222"

    def run_hook(self):
        hooks = build_hooks_copy(self.root)
        transcript = self.write(
            "t.jsonl", assistant_line(self.MODEL, 500, 700) + "\n")
        payload = {"hook_event_name": "Stop", "cwd": self.root,
                   "transcript_path": transcript, "session_id": self.SESSION}
        return subprocess.run(
            [sys.executable, os.path.join(hooks, "cost_capture.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env=fixture_env(self.root))

    def costs_log(self):
        path = os.path.join(self.root, "company", "state", "costs.log")
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()

    def test_control_a_writable_cursor_does_log_a_line(self):
        # The control. Without it, the assertion below would also pass if the
        # hook had simply stopped logging altogether.
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.MODEL, self.costs_log())

    def test_a_failed_cursor_write_appends_no_costs_line(self):
        # Sabotage: the cursor path is a DIRECTORY, so the atomic replace at
        # the end of the locked section cannot land and returns False. The
        # makedirs and the lock both still succeed, which is what isolates the
        # failure to the write itself.
        os.makedirs(
            os.path.join(self.root, "company", "state", ".cost-cursor.json"))
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.costs_log(), "",
            "a costs.log line was appended although the cursor never moved - "
            "the next stop will append the same delta again")


# --- FR-HP-30: behaviour identity ---------------------------------------
class TestCheckUnchanged(FixtureCase):
    """Delete this and --check's stdout contract (the WITNESS_JSON line last)
    can drift under a refactor of the writers without anything going red."""

    def test_check_stdout_is_byte_identical(self):
        # Pinned against the pre-lock output captured from HEAD: --check is a
        # pure reader and this lane must not have altered one byte of it.
        self.write("src/a.py", "load bearing MARKER here\n")
        self.write("src/bb.py", "second MARKER_TWO\n")
        r = run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                                "MARKER", "--task", "t", "--why",
                                "keep the marker"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_cli(HOOKS_DIR, ["--add", "--file", "src/bb.py", "--contains",
                                "MARKER_TWO", "--task", "t", "--why", "two"],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        r = run_cli(HOOKS_DIR, ["--check"], self.root)
        expected = (
            'ID     FILE       STATUS  WHY / REASON\n'
            'W-001  src/a.py   pass    keep the marker\n'
            'W-002  src/bb.py  pass    two\n'
            'WITNESS_JSON: {"count": 2, "failed": [], "ok": true}\n'
        )
        self.assertEqual(r.stdout, expected)
        self.assertEqual(r.stderr, "")
        self.assertEqual(r.returncode, 0)
        self.assert_real_registry_untouched()


class TestAddRemoveIdentity(FixtureCase):
    """Delete this and the writers' stdout, exit codes and adherence lines can
    change shape under the lock without a single test noticing."""

    def test_add_stdout_exit_and_adherence(self):
        # Exact strings: skills and humans grep these.
        self.write("src/a.py", "MARKER\n")
        r = run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                                "MARKER", "--task", "t", "--why", "keep"],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(
            r.stdout,
            "added W-001 -> src/a.py (must_contain: 'MARKER', regex=False)\n")
        self.assertEqual(r.stderr, "")
        log = self.adherence()
        self.assertIn(
            "| witness_check | INFO | W-001 | added witness for src/a.py", log)

    def test_remove_stdout_exit_and_adherence(self):
        self.write("src/a.py", "MARKER\n")
        run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                            "MARKER", "--task", "t", "--why", "keep"],
                self.root)
        r = run_cli(HOOKS_DIR, ["--remove", "W-001", "--why", "obsolete"],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout,
                         "removed W-001 (0 witnesses remain): obsolete\n")
        self.assertEqual(r.stderr, "")
        self.assertIn("| witness_check | INFO | W-001 | removed: obsolete",
                      self.adherence())

    def test_remove_unknown_id_keeps_exit_1_and_message(self):
        # The early-return error paths must survive being moved inside the
        # lock, exit code and stderr string unchanged.
        self.write("src/a.py", "MARKER\n")
        run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                            "MARKER", "--task", "t", "--why", "keep"],
                self.root)
        r = run_cli(HOOKS_DIR, ["--remove", "W-404", "--why", "nope"],
                    self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no witness with id W-404 - nothing removed", r.stderr)
        self.assertEqual(len(self.registry()["witnesses"]), 1)

    def test_add_missing_args_keeps_exit_2(self):
        r = run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py"], self.root)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("requires --file, --contains, --task, --why", r.stderr)

    def test_written_registry_parses_and_check_passes(self):
        # The atomic replace must land a whole, checksum-valid registry.
        self.write("src/a.py", "MARKER\n")
        run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                            "MARKER", "--task", "t", "--why", "keep"],
                self.root)
        reg = self.registry()
        self.assertEqual(reg["witnesses"][0]["id"], "W-001")
        self.assertTrue(reg["checksum"])
        r = run_cli(HOOKS_DIR, ["--check"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --- the fail-open constraint -------------------------------------------
class TestLockFailsOpen(FixtureCase):
    """Delete this and a state dir the lock cannot use turns --add from
    'slightly racy' into 'permanently broken', which is strictly worse than
    the bug this lane fixes."""

    def test_add_completes_when_state_dir_cannot_hold_a_lock(self):
        # company/state is a FILE, so state_lock's makedirs and its os.open
        # both fail. The lock must yield unlocked and --add must still land.
        shutil.rmtree(os.path.join(self.root, "company", "state"))
        self.write("company/state", "not a directory\n")
        self.write("src/a.py", "MARKER\n")
        r = run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                                "MARKER", "--task", "t", "--why", "keep"],
                    self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("added W-001", r.stdout)
        self.assertEqual(len(self.registry()["witnesses"]), 1)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root ignores the directory mode this test relies on")
    def test_add_completes_when_state_dir_is_unwritable(self):
        # Same constraint through the likelier field cause: a state dir the
        # process cannot create the lock file in.
        state_dir = os.path.join(self.root, "company", "state")
        self.write("src/a.py", "MARKER\n")
        os.chmod(state_dir, 0o500)
        try:
            r = run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py",
                                    "--contains", "MARKER", "--task", "t",
                                    "--why", "keep"], self.root)
        finally:
            os.chmod(state_dir, 0o700)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("added W-001", r.stdout)
        self.assertEqual(len(self.registry()["witnesses"]), 1)

    def test_add_reports_a_failed_write_instead_of_claiming_success(self):
        # write_json_atomic returns False rather than raising. company/ is a
        # FILE here so the replace cannot happen; --add must be LOUD and
        # non-zero, never print 'added' over a write that never landed.
        shutil.rmtree(os.path.join(self.root, "company"))
        self.write("company", "not a directory\n")
        r = run_cli(HOOKS_DIR, ["--add", "--file", "src/a.py", "--contains",
                                "MARKER", "--task", "t", "--why", "keep"],
                    self.root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("witness NOT added", r.stderr)
        self.assertNotIn("added W-", r.stdout)


# --- FR-HP-31 / FR-HP-33: source assertions -----------------------------
class TestSourceShape(unittest.TestCase):
    """Delete this and the two patterns this lane exists to remove can walk
    straight back in on the next refactor."""

    WRITE_OPEN = re.compile(r"""open\s*\([^)]*["']w""")
    JSON_DUMP = re.compile(r"json\.dump\s*\(")

    def scan(self, filename):
        path = os.path.join(HOOKS_DIR, filename)
        offenders = []
        for lineno, line in enumerate(read_text(path).splitlines(), 1):
            if self.WRITE_OPEN.search(line) or self.JSON_DUMP.search(line):
                offenders.append("{}:{}: {}".format(path, lineno, line.strip()))
        return offenders

    def test_no_non_atomic_json_write_remains(self):
        # FR-HP-33. A whole-file open(...,"w") + json.dump pair is exactly the
        # torn read another session sees mid-write.
        for filename in ("witness_check.py", "cost_capture.py"):
            offenders = self.scan(filename)
            self.assertEqual(
                offenders, [],
                "non-atomic JSON write still present - route it through "
                "c.write_json_atomic:\n" + "\n".join(offenders))

    def test_cost_capture_never_enters_the_lock_by_hand(self):
        # FR-HP-31. The reference implementation this was ported from called
        # state_lock's __enter__ / __exit__ by hand and leaked the file
        # descriptor whenever the body raised. Only a real `with` block
        # releases in a finally, so a manual __enter__ is banned outright.
        src = read_text(os.path.join(HOOKS_DIR, "cost_capture.py"))
        self.assertNotIn("__enter__", src)
        self.assertNotIn("__exit__", src)
        self.assertIn("with c.state_lock(root):", src)

    def test_witness_writer_is_locked_and_atomic(self):
        # --add and --remove each hold one lock; --check is a pure reader and
        # must stay outside it.
        src = read_text(os.path.join(HOOKS_DIR, "witness_check.py"))
        self.assertNotIn("__enter__", src)
        self.assertEqual(src.count("with c.state_lock(root):"), 2, src)
        self.assertIn("c.write_json_atomic(path, registry, indent=2)", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
