#!/usr/bin/env python3
"""The L1 state kernel: locking, atomic writes, torn reads, content hashing.

These are the primitives every hook stands on, so the bar here is different
from the rest of the suite. Three properties are under test and each one has a
way of passing for the wrong reason, so each is pinned by a proof that a broken
implementation cannot satisfy:

  1. state_lock really serializes. Two THREADS would prove nothing about a
     flock, which is held per open file description across processes, so every
     mutual-exclusion case here runs real child processes synchronized on an
     absolute wall-clock barrier so they genuinely contend. The lost-update
     case runs the same read-modify-write body twice, once inside the lock and
     once outside, and asserts the unlocked run LOSES an update. Without that
     negative control a lock that never locked would look green.
  2. write_json_atomic is atomic and total. A reader loop that never sees a
     torn file is the positive half; a forced serialization failure that
     leaves the destination byte-identical is the half that catches a helper
     which truncates first and serializes second.
  3. work_hash fingerprints CONTENT, not history position, and does it without
     touching the repository's real git index. The index assertion is made
     against a fixture repo AND against this actual worktree, because the
     failure mode being guarded is corrupting a developer's index and that
     only shows up against a real one.

Everything in the kernel fails OPEN. No case below may end in an exception
reaching the caller: a lock that cannot be taken proceeds unlocked, a write
that cannot be made returns False, a hash that cannot be computed degrades.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

# Same-dir sibling import: works under `unittest discover -s tests/hooks` and
# under `-s tests/hooks -t tests/hooks` (what the CI runner uses).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook, HOOKS_DIR  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import _common  # noqa: E402

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)


def open_fd_count():
    """Open descriptors held by this process, or None where unknowable."""
    for directory in ("/proc/self/fd", "/dev/fd"):
        if os.path.isdir(directory):
            try:
                return len(os.listdir(directory))
            except OSError:
                return None
    return None


def index_path(root):
    """The real git index for `root`, resolved the way git resolves it.

    A linked worktree keeps its index under .git/worktrees/<name>/, never at
    <root>/.git/index, so assuming the literal path would make the index
    assertions test nothing in exactly the checkout this repo develops in.
    """
    out = subprocess.run(
        ["git", "-C", root, "rev-parse", "--git-path", "index"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    path = out.stdout.strip()
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(root, path)


def index_fingerprint(path):
    """(bytes, size, mtime_ns) - content AND mtime, which is the point."""
    st = os.stat(path)
    with open(path, "rb") as f:
        return f.read(), st.st_size, st.st_mtime_ns


# ---------------------------------------------------------------------------
# Child-process bodies. Every one takes the hooks dir as argv[1] so the child
# imports the same kernel under test.
# ---------------------------------------------------------------------------

# The children announce READY once the interpreter is up and _common is
# imported, then BLOCK on a line from the parent. The parent releases them
# only after every child has reported, so contention is arranged by a real
# synchronization primitive instead of by a wall-clock barrier and a hope
# about scheduling. Interpreter startup - the large, load-sensitive part - is
# finished before the clock starts on anything these tests assert.
CHILD_SERIALIZE = '''
import json, sys, time
sys.path.insert(0, sys.argv[1])
import _common
root, hold = sys.argv[2], float(sys.argv[3])
sys.stdout.write("READY\\n")
sys.stdout.flush()
sys.stdin.readline()
with _common.state_lock(root):
    enter = time.time()
    time.sleep(hold)
    leave = time.time()
print(json.dumps({"enter": enter, "leave": leave}))
'''

CHILD_RMW = '''
import contextlib, json, os, sys, tempfile, time
sys.path.insert(0, sys.argv[1])
import _common
root, path, marker = sys.argv[2], sys.argv[3], sys.argv[4]
pause = float(sys.argv[5])
locked = sys.argv[6] == "lock"
sys.stdout.write("READY\\n")
sys.stdout.flush()
sys.stdin.readline()
ctx = _common.state_lock(root) if locked else contextlib.nullcontext()
with ctx:
    with open(path) as f:
        data = json.load(f)
    time.sleep(pause)
    data["seen"].append(marker)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)
print(json.dumps({"marker": marker}))
'''

CHILD_NO_FCNTL = '''
import sys


class Blocker(object):
    def find_spec(self, name, path=None, target=None):
        if name == "fcntl":
            raise ImportError("fcntl blocked for this test")
        return None


sys.meta_path.insert(0, Blocker())
sys.modules.pop("fcntl", None)
try:
    import fcntl  # noqa: F401
except ImportError:
    print("BLOCKED")
else:
    print("NOT-BLOCKED")
sys.path.insert(0, sys.argv[1])
import _common
ran = []
with _common.state_lock(sys.argv[2]):
    ran.append(1)
print("RAN" if ran else "SKIPPED")
'''

CHILD_HOLD = '''
import sys, time
sys.path.insert(0, sys.argv[1])
import _common
with _common.state_lock(sys.argv[2]):
    sys.stdout.write("HELD\\n")
    sys.stdout.flush()
    time.sleep(float(sys.argv[3]))
'''


class KernelBase(Base):
    """Base plus child-process spawning against the kernel under test."""

    def child_script(self, name, source):
        path = os.path.join(self.root, name)
        with open(path, "w") as f:
            f.write(source)
        return path

    def spawn(self, script, *args):
        return subprocess.Popen(
            [sys.executable, script, HOOKS_DIR] + [str(a) for a in args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )

    def spawn_together(self, script, per_child_args):
        """Start N children and release them only once ALL are ready.

        Each child prints READY after importing the kernel and then blocks
        reading a line, so the parent can wait for genuine readiness instead
        of guessing at a wall-clock instant. This is the difference between
        arranging contention and hoping for it: interpreter startup, which is
        the part a loaded box stretches, is complete for every child before
        any of them proceeds.
        """
        procs = [self.spawn(script, *args) for args in per_child_args]
        for proc in procs:
            self.assertEqual(proc.stdout.readline().strip(), "READY")
        for proc in procs:
            proc.stdin.write("go\n")
            proc.stdin.flush()
        return procs

    def collect(self, procs):
        out = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, stderr)
            out.append(json.loads(stdout.strip()))
        return out

    def state_file(self, name="shared.json", data=None):
        path = os.path.join(self.root, "company", "state", name)
        with open(path, "w") as f:
            json.dump(data if data is not None else {"seen": []}, f)
        return path


# ---------------------------------------------------------------------------
# FR-HP-01  state_lock
# ---------------------------------------------------------------------------


class TestStateLock(KernelBase):
    RMW_PAUSE = 0.3

    def run_rmw_pair(self, mode):
        """Two child processes read-modify-write one file, released together.

        `mode` is "lock" or "nolock". Both children are already running and
        blocked on the parent's go signal before either touches the file, and
        each pauses RMW_PAUSE between its read and its write. The pause is the
        skew tolerance: post-handshake skew is process-scheduling latency, not
        interpreter startup, so 0.3s is orders of magnitude more than it needs
        to be for both children to have read before either writes.
        """
        script = self.child_script("rmw.py", CHILD_RMW)
        path = self.state_file()
        procs = self.spawn_together(script, [
            (self.root, path, marker, self.RMW_PAUSE, mode)
            for marker in ("a", "b")
        ])
        self.collect(procs)
        with open(path) as f:
            return json.load(f)["seen"]

    def test_two_processes_serialize_fr_hp_01(self):
        """Two children holding the lock cannot overlap in time.

        The load-bearing assertion is INTERVAL DISJOINTNESS, which is a
        relational claim about two absolute timestamps and carries no margin
        and no dependence on machine speed: whatever the box does to the
        durations, a genuinely shared lock means one child's critical section
        ends before the other's begins. The span check backs it with a LOWER
        bound only - serialized is 2 x hold, a lost lock is 1 x hold, and a
        loaded box can only push the number up, never down, so it cannot go
        red for being slow.
        """
        hold = 0.2
        script = self.child_script("serialize.py", CHILD_SERIALIZE)
        procs = self.spawn_together(script, [(self.root, hold)] * 2)
        spans = self.collect(procs)
        enters = [s["enter"] for s in spans]
        leaves = [s["leave"] for s in spans]
        self.assertLessEqual(min(leaves), max(enters), spans)
        self.assertGreater(max(leaves) - min(enters), hold * 1.75, spans)

    def test_lock_preserves_both_updates_fr_hp_01(self):
        """The read-modify-write cycle inside the lock loses nothing."""
        self.assertEqual(sorted(self.run_rmw_pair("lock")), ["a", "b"])

    def test_without_the_lock_an_update_is_lost_fr_hp_01(self):
        """The negative control: the identical body unlocked drops a write.

        Without this, a state_lock that silently never locked would leave the
        positive case green and the suite would be certifying nothing.
        """
        self.assertEqual(len(self.run_rmw_pair("nolock")), 1)

    def test_missing_fcntl_still_yields_fr_hp_01(self):
        """No fcntl means no lock, and no lock must still run the body.

        Forced in a child by a meta_path finder that raises on `import fcntl`,
        so nothing shipped is modified to make this reachable. The child
        proves the block is real before it proves the kernel survives it.
        """
        script = self.child_script("nofcntl.py", CHILD_NO_FCNTL)
        proc = self.spawn(script, self.root)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(out.split(), ["BLOCKED", "RAN"], out)

    def test_body_exception_releases_the_lock_fr_hp_01(self):
        """A raising body propagates, releases, and leaks no descriptor.

        The release is proven DIRECTLY rather than inferred from how long a
        later acquisition took: after the exception, this process takes a
        non-blocking exclusive flock on the lock file itself. flock is bound
        to the open file description, so a descriptor the kernel forgot to
        close would still hold the lock and this probe would raise
        BlockingIOError - even from inside the same process. That is the
        actual mechanism, asserted with no clock in the loop at all.
        """
        try:
            import fcntl
        except ImportError:
            self.skipTest("no fcntl on this platform")
        before = open_fd_count()
        if before is None:
            self.skipTest("no /proc/self/fd or /dev/fd on this platform")

        with self.assertRaises(RuntimeError):
            with _common.state_lock(self.root):
                raise RuntimeError("boom")

        self.assertEqual(open_fd_count(), before, "descriptor leaked")
        lock_file = os.path.join(self.root, "company", "state", ".state.lock")
        self.assertTrue(os.path.exists(lock_file), lock_file)
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as exc:
            self.fail("lock was still held after the body raised: %s" % exc)
        finally:
            os.close(fd)

        entered = []
        with _common.state_lock(self.root, timeout=2.0):
            entered.append(1)
        self.assertEqual(entered, [1])

    HOLDER_SECONDS = 30.0

    def test_timeout_proceeds_unlocked_fr_hp_01(self):
        """A contended lock times out and runs the body anyway, never raises.

        Entering the body at all, while another PROCESS demonstrably holds the
        lock, is the whole requirement (OQ-HP-11: proceed unlocked, fail open)
        and it carries no timing margin.

        The two numeric bounds are both mechanism discriminators rather than
        speed limits. The lower bound can only be violated by returning EARLY,
        which means not waiting the timeout - a loaded box pushes it up, never
        down. The upper bound separates "timed out after 0.3s" from "blocked
        until the holder let go", and the holder deliberately keeps the lock
        for 30s so the two outcomes are 100x apart: no amount of scheduling
        noise turns one into the other.
        """
        script = self.child_script("hold.py", CHILD_HOLD)
        proc = self.spawn(script, self.root, self.HOLDER_SECONDS)
        # Cleanups run last-registered-first: kill, reap, then close the pipes.
        self.addCleanup(proc.stderr.close)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.stdin.close)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "HELD")
        entered = []
        started = time.time()
        with _common.state_lock(self.root, timeout=0.3):
            entered.append(1)
        elapsed = time.time() - started
        self.assertEqual(entered, [1])
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertLess(elapsed, self.HOLDER_SECONDS / 3)


# ---------------------------------------------------------------------------
# FR-HP-02  write_json_atomic
# ---------------------------------------------------------------------------


class TestWriteJsonAtomic(KernelBase):
    def dest(self, name="payload.json"):
        return os.path.join(self.root, "company", "state", name)

    def dir_entries(self, path):
        return set(os.listdir(os.path.dirname(path)))

    def big_payload(self, n):
        return {"n": n,
                "rows": [{"i": i, "pad": "x" * 120} for i in range(400)]}

    def test_concurrent_reader_never_sees_a_torn_file_fr_hp_02(self):
        """200 writes of a large payload, read continuously throughout.

        A whole-file write of this size is many kilobytes of truncate-then-
        write, so a non-atomic helper hands the reader an unparseable middle
        within the first few iterations. The reader count is asserted so the
        case cannot pass by never having read anything.
        """
        path = self.dest()
        self.assertTrue(_common.write_json_atomic(path, self.big_payload(0)))
        errors = []
        reads = [0]
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    with open(path) as f:
                        json.load(f)
                    reads[0] += 1
                except Exception as exc:  # torn read or missing file
                    errors.append(repr(exc))

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for n in range(1, 201):
                self.assertTrue(
                    _common.write_json_atomic(path, self.big_payload(n))
                )
        finally:
            stop.set()
            thread.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertGreater(reads[0], 20)
        with open(path) as f:
            self.assertEqual(json.load(f)["n"], 200)

    def test_serialization_failure_leaves_destination_intact_fr_hp_02(self):
        """A failed write returns False and changes nothing on disk.

        Both json.dump and json.dumps are forced to raise so the case tests
        the BEHAVIOUR rather than one internal call: whichever the helper
        reaches, serialization fails, and the pre-existing file must survive
        byte-identical with no temp file stranded beside it.
        """
        path = self.dest()
        self.assertTrue(_common.write_json_atomic(path, {"keep": "me"}))
        with open(path, "rb") as f:
            before_bytes = f.read()
        before_entries = self.dir_entries(path)
        boom = RuntimeError("serialization refused")
        with mock.patch.object(_common.json, "dump", side_effect=boom), \
                mock.patch.object(_common.json, "dumps", side_effect=boom):
            result = _common.write_json_atomic(path, {"new": "data"})
        self.assertIs(result, False)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before_bytes)
        self.assertEqual(self.dir_entries(path), before_entries)

    def test_success_returns_true_and_round_trips_fr_hp_02(self):
        path = self.dest()
        data = {"version": 2, "tasks": [{"task": "a"}, {"task": "b"}]}
        self.assertIs(_common.write_json_atomic(path, data), True)
        with open(path) as f:
            self.assertEqual(json.load(f), data)
        self.assertEqual(self.dir_entries(path), {"payload.json"})

    def test_indent_and_compact_formats_fr_hp_02(self):
        """On-disk formatting is the caller's, not the helper's.

        gate_stamp.py and witness_check.py ship indent=2 files, and the
        helper must also be able to ship a compact one. Other lanes diff
        and eyeball those, so the exact text is part of the contract.
        """
        data = {"b": 1, "a": [1, 2]}
        pretty = self.dest("pretty.json")
        self.assertIs(_common.write_json_atomic(pretty, data, indent=2), True)
        with open(pretty) as f:
            self.assertEqual(f.read(), json.dumps(data, indent=2))
        compact = self.dest("compact.json")
        self.assertIs(_common.write_json_atomic(compact, data), True)
        with open(compact) as f:
            self.assertEqual(f.read(), json.dumps(data))

    def test_creates_missing_parent_directory_fr_hp_02(self):
        path = os.path.join(self.root, "company", "state", "deep", "a.json")
        self.assertIs(_common.write_json_atomic(path, {"ok": 1}), True)
        with open(path) as f:
            self.assertEqual(json.load(f), {"ok": 1})
        self.assertEqual(os.listdir(os.path.dirname(path)), ["a.json"])

    def test_replace_preserves_the_destination_mode_fr_hp_02(self):
        """mkstemp creates 0600 and os.replace carries the temp file's mode
        with it, so without an explicit chmod every state file would silently
        tighten to owner-only the first time its writer adopted this helper.
        Lanes migrate gates.status and witnesses.json onto it next wave; a
        permission change none of them asked for is the kind of thing that
        surfaces as a mystery on someone else's machine.
        """
        path = os.path.join(self.root, "company", "state", "modes.json")
        self.assertIs(_common.write_json_atomic(path, {"n": 1}), True)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o644)
        os.chmod(path, 0o600)
        self.assertIs(_common.write_json_atomic(path, {"n": 2}), True)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        os.chmod(path, 0o664)
        self.assertIs(_common.write_json_atomic(path, {"n": 3}), True)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o664)


# ---------------------------------------------------------------------------
# FR-HP-03 / FR-HP-04  torn reads of active-task.json
# ---------------------------------------------------------------------------


V1 = {"task": "hp-kernel", "type": "feature", "role": "developer"}
V2 = {"version": 2, "tasks": [{"task": "one"}, {"task": "two"}]}


class TestTornReads(KernelBase):
    def path(self):
        return _common.active_tasks_path(self.root)

    def put(self, text):
        with open(self.path(), "w") as f:
            f.write(text)

    def test_active_tasks_path_fr_hp_03(self):
        self.assertEqual(
            _common.active_tasks_path(self.root),
            os.path.join(self.root, "company", "state", "active-task.json"),
        )

    def test_valid_file_parses_fr_hp_03(self):
        self.put(json.dumps(V2))
        self.assertEqual(_common.active_tasks(self.root), V2["tasks"])

    def test_absent_file_is_empty_fr_hp_03(self):
        self.assertFalse(os.path.exists(self.path()))
        self.assertEqual(_common.active_tasks(self.root), [])

    def test_reads_go_through_read_json_file_fr_hp_03(self):
        """The seam the retry hangs on. If this fails, the retry case below
        is testing a patch point the kernel does not use, and that is the
        finding rather than the retry itself."""
        with mock.patch.object(_common, "read_json_file",
                               return_value=V2) as reader:
            self.assertEqual(_common.active_tasks(self.root), V2["tasks"])
        reader.assert_called_with(self.path())

    def test_unparseable_then_valid_returns_entries_fr_hp_03(self):
        """A torn read is transient, so it is retried and the retry wins.

        Returning [] here would read as "no task in flight" and arm blocks
        that should never fire, which is why the retry exists at all. The
        call count is asserted so a kernel that got lucky on read one cannot
        pass this.
        """
        self.put("{ this is half a write")
        with mock.patch.object(_common, "read_json_file",
                               side_effect=[None, V2]) as reader:
            self.assertEqual(_common.active_tasks(self.root), V2["tasks"])
        self.assertGreaterEqual(reader.call_count, 2)

    def test_permanently_unparseable_is_empty_and_bounded_fr_hp_04(self):
        """Garbage that never resolves gives up and fails open, and the RETRY
        BUDGET is what is asserted - not the wall clock.

        The requirement (OQ-HP-10) is "3 retries, 0.06s apart". That is a
        claim about the code path, so it is measured on the code path: the
        read attempts are counted and the sleep durations are captured. The
        earlier version of this test asserted the elapsed time was under 0.5s,
        which is a claim about the MACHINE - it went red on a loaded
        macos-latest runner at 0.55s (PR #107) while the kernel was behaving
        exactly as specified. A test that fails in the harness rather than in
        the product teaches people to re-run reds instead of reading them.
        """
        self.put("not json at all")
        real_read = _common.read_json_file
        reads, sleeps = [], []

        def counting_read(path):
            reads.append(path)
            return real_read(path)

        # The sleeps are recorded and NOT performed: the budget is the claim,
        # so there is no reason to spend it. Patched on the time module the
        # kernel imported, and restored by the context manager.
        with mock.patch.object(_common, "read_json_file", counting_read), \
                mock.patch.object(_common.time, "sleep", sleeps.append):
            self.assertEqual(_common.active_tasks(self.root), [])

        self.assertEqual(len(reads), 4, "one read plus exactly three retries")
        self.assertEqual(sleeps, [0.06, 0.06, 0.06])

    def test_unparseable_read_loop_is_not_unbounded_fr_hp_04(self):
        """The one wall-clock check kept, and it is a sanity ceiling only.

        The intended budget is about 0.18s of sleeping. This ceiling is over a
        hundred times that, so no scheduling noise, cold cache or shared CI
        runner can reach it - only a genuinely unbounded retry loop can, which
        is the single failure this is here to catch.
        """
        self.put("not json at all")
        started = time.time()
        self.assertEqual(_common.active_tasks(self.root), [])
        self.assertLess(time.time() - started, 30)

    def test_unreadable_true_only_for_exists_and_unparseable_fr_hp_04(self):
        """The three states a caller must be able to tell apart."""
        self.assertFalse(os.path.exists(self.path()))
        self.assertIs(_common.active_tasks_unreadable(self.root), False)
        self.put(json.dumps(V1))
        self.assertIs(_common.active_tasks_unreadable(self.root), False)
        self.put("{ torn")
        self.assertIs(_common.active_tasks_unreadable(self.root), True)

    def test_v1_single_object_shape_fr_hp_04(self):
        self.put(json.dumps(V1))
        self.assertEqual(_common.active_tasks(self.root), [V1])

    def test_v2_envelope_shape_fr_hp_04(self):
        self.put(json.dumps(V2))
        self.assertEqual(_common.active_tasks(self.root), V2["tasks"])

    def test_bare_list_shape_drops_non_dicts_fr_hp_04(self):
        self.put(json.dumps([V1, "junk", {"task": "two"}]))
        self.assertEqual(_common.active_tasks(self.root),
                         [V1, {"task": "two"}])


# ---------------------------------------------------------------------------
# FR-HP-05  content-based work_hash
# ---------------------------------------------------------------------------


class HashBase(KernelBase):
    def setUp(self):
        super(HashBase, self).setUp()
        self.init_git()
        self.write("src/app.py", "print('one')\n")
        self.write("ORCHESTRATOR.md", "# Orchestrator\n\nDoctrine.\n")
        self.write(".claude/agents/auditor.md", "# Auditor\n\nRole.\n")
        self.commit("seed")

    def commit(self, message):
        git(self.root, "add", "-A")
        result = git(self.root, "commit", "-m", message)
        return result

    def hash(self):
        return _common.work_hash(self.root)


class TestContentWorkHash(HashBase):
    def test_healthy_repo_returns_tree_oid_fr_hp_05(self):
        value = self.hash()
        self.assertTrue(value.startswith("tree:"), value)
        self.assertRegex(value, r"^tree:[0-9a-f]{40,64}$")

    def test_staging_an_unchanged_file_does_not_move_the_hash_fr_hp_05(self):
        before = self.hash()
        result = git(self.root, "add", "src/app.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hash(), before)

    def test_committing_unchanged_content_does_not_move_hash_fr_hp_05(self):
        """The defect this rewrite exists for.

        The old digest folded HEAD in, so committing work that had just gone
        green through the gates changed the fingerprint and staled its own
        stamp. Content did not move, so the hash must not move.
        """
        self.write("src/app.py", "print('two')\n")
        git(self.root, "add", "src/app.py")
        before = self.hash()
        result = self.commit("commit the staged work")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hash(), before)

    def test_source_edit_moves_the_hash_fr_hp_05(self):
        before = self.hash()
        self.write("src/app.py", "print('changed')\n")
        self.assertNotEqual(self.hash(), before)

    def test_fixture_git_index_is_untouched_fr_hp_05(self):
        """work_hash must never read or write the repository's real index.

        Content AND mtime, because git itself treats an index mtime bump as a
        reason to re-stat the tree; a hash that quietly refreshed the index
        would be invisible until it corrupted one.
        """
        path = index_path(self.root)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path), path)
        before = index_fingerprint(path)
        self.assertTrue(self.hash().startswith("tree:"))
        self.assertEqual(index_fingerprint(path), before)

    def test_no_throwaway_index_left_behind_fr_hp_05(self):
        """The throwaway index is removed however the hash ends.

        tempfile.tempdir is redirected at a private directory for the call so
        the check sees only files this call created, and cannot be confused by
        a concurrent session's temp files.
        """
        private = tempfile.mkdtemp(prefix="cc-kernel-tmp-")
        self.addCleanup(shutil.rmtree, private, True)
        original = tempfile.tempdir
        tempfile.tempdir = private
        try:
            self.hash()
        finally:
            tempfile.tempdir = original
        self.assertEqual(os.listdir(private), [])
        self.assertEqual(
            glob.glob(os.path.join(os.path.dirname(index_path(self.root)),
                                   "cc-hash-index-*")),
            [],
        )

    def test_missing_git_returns_no_git_fr_hp_05(self):
        empty = tempfile.mkdtemp(prefix="cc-nopath-")
        self.addCleanup(shutil.rmtree, empty, True)
        with mock.patch.dict(os.environ, {"PATH": empty}):
            self.assertEqual(self.hash(), "no-git")

    def test_directory_that_is_not_a_repo_returns_no_git_fr_hp_05(self):
        """git present, repository absent - the installer's own fixture shape.

        tests/install/run_tests.sh builds NON-git fixture directories and
        drives the gate runner inside them, so a content hash that assumed a
        repo was always there would surface as a red installer suite rather
        than as anything a hook test would catch. Both the tree path and the
        legacy fallback have to come back empty-handed here, quietly.
        """
        plain = tempfile.mkdtemp(prefix="cc-norepo-")
        self.addCleanup(shutil.rmtree, plain, True)
        with open(os.path.join(plain, "file.txt"), "w") as f:
            f.write("not versioned\n")
        self.assertIsNone(_common._content_tree_hash(plain))
        self.assertEqual(_common.work_hash(plain), "no-git")
        self.assertEqual(sorted(os.listdir(plain)), ["file.txt"])

    def test_legacy_fallback_when_tree_hash_unavailable_fr_hp_05(self):
        """A git that cannot write a tree degrades to the OLD digest.

        The fallback has to stay exactly as strong as today's behavior, so it
        is asserted to be a sha256 hex digest that still moves on a source
        edit. Degrading to a constant would disarm every freshness check in
        the product.
        """
        with mock.patch.object(_common, "_content_tree_hash",
                               return_value=None):
            before = self.hash()
            self.assertRegex(before, r"^[0-9a-f]{64}$")
            self.write("src/app.py", "print('legacy edit')\n")
            after = self.hash()
        self.assertRegex(after, r"^[0-9a-f]{64}$")
        self.assertNotEqual(after, before)

    def test_legacy_fallback_does_not_rewrite_index_content_fr_hp_05(self):
        """The fallback path keeps the index CONTENT intact - mtime is not
        asserted here, and that is a measured limitation, not an oversight.

        `git status --porcelain` refreshes the index stat cache, so the
        fallback branch moves the index mtime. It is exactly what today's
        shipped work_hash already does on every call, so this is not a
        regression the content hash introduced, and a stat-cache refresh
        cannot corrupt staged state. Routing the fallback through a COPY of
        the index was rejected deliberately: the fallback only runs when git
        is already troubled, and adding a copy step there buys a cosmetic
        mtime at the cost of a new failure mode on the degraded path. The
        primary tree path touches neither content nor mtime and is asserted
        on both a fixture repo and this checkout.
        """
        path = index_path(self.root)
        self.assertIsNotNone(path)
        before, _, _ = index_fingerprint(path)
        with mock.patch.object(_common, "_content_tree_hash",
                               return_value=None):
            digest = _common.work_hash(self.root)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        after, _, _ = index_fingerprint(path)
        self.assertEqual(before, after, "legacy fallback rewrote the index")


class TestRealWorktreeIndex(unittest.TestCase):
    """The index assertion against THIS checkout, not a fixture.

    A linked worktree resolves its index outside <root>/.git, and that is the
    layout this repo is developed in, so the fixture case alone would not
    catch a kernel that hard-coded the wrong path and hit the real one.
    """

    def test_real_worktree_index_is_untouched_fr_hp_05(self):
        # No checkout, no index, no evidence to gather - and no failure to
        # report either. The suite runs from a plain directory export in at
        # least one place (the installer fixtures) and inside mutation-testing
        # copies, where asserting an index EXISTS would be a claim about the
        # harness rather than about the kernel. The fixture-repo version of
        # this assertion in TestContentWorkHash always runs, so skipping here
        # never leaves the requirement uncovered.
        path = index_path(REPO_ROOT)
        if path is None or not os.path.exists(path):
            self.skipTest(
                "not a git checkout ({}) - the fixture-repo index assertion "
                "covers this requirement".format(REPO_ROOT)
            )
        # A concurrent session running git in this checkout also rewrites the
        # index, so a single disagreement is retried. A kernel that touches
        # the index fails every attempt.
        last = None
        for _ in range(3):
            before = index_fingerprint(path)
            value = _common.work_hash(REPO_ROOT)
            after = index_fingerprint(path)
            self.assertNotEqual(value, "")
            if after == before:
                return
            last = (before[1:], after[1:])
        self.fail("work_hash moved the real git index: {}".format(last))


# ---------------------------------------------------------------------------
# FR-HP-06  HASH_EXCLUDES
# ---------------------------------------------------------------------------


class TestHashExcludes(HashBase):
    def test_excludes_are_state_and_build_inputs_fr_hp_06(self):
        """Three entries, and the line between them is inputs vs behavior.

        company/state is machine-written output and would self-invalidate the
        hash. company/briefs and company/specs are build INPUTS: they ship in
        no install and no hook reads them for a verdict, so a brief edit
        staling a code gate result is a re-run that proves nothing
        (owner-authorized, 2026-08-13).

        Everything else stays in, and the tests below are the other half of
        this assertion. The kernel this was ported from drops *.md and *.txt
        wholesale on the argument that prose reaches no gate verdict. False
        here: markdown IS this product. ORCHESTRATOR.md, METHOD.md, the agent
        definitions and the skills are executable product, and no_slop,
        trace_check and guard_models all gate them. Widening this tuple toward
        the fork, in either direction, is the failure this asserts against.
        """
        self.assertEqual(
            _common.HASH_EXCLUDES,
            ("company/state", "company/briefs", "company/specs"),
        )

    def test_editing_orchestrator_md_moves_the_hash_fr_hp_06(self):
        before = self.hash()
        self.write("ORCHESTRATOR.md", "# Orchestrator\n\nRewritten.\n")
        self.assertNotEqual(self.hash(), before)

    def test_editing_an_agent_definition_moves_the_hash_fr_hp_06(self):
        before = self.hash()
        self.write(".claude/agents/auditor.md", "# Auditor\n\nRewritten.\n")
        self.assertNotEqual(self.hash(), before)

    def test_editing_doctrine_prose_moves_the_hash_fr_hp_06(self):
        """METHOD.md is doctrine, and doctrine is behavior in this product."""
        self.write("company/METHOD.md", "# Method\n\nRewritten doctrine.\n")
        self.commit("track doctrine")
        before = self.hash()
        self.write("company/METHOD.md", "# Method\n\nRewritten again.\n")
        self.assertNotEqual(self.hash(), before)

    def test_brief_and_spec_edits_do_not_move_the_hash_fr_hp_06(self):
        """The other half: build inputs are outside the fingerprint.

        Asserted for a tracked-then-edited file, a brand-new untracked file
        and a deletion, because `add -A` seeds the throwaway index from HEAD
        and each of those three reaches the index by a different route.
        """
        self.write("company/briefs/brief-thing.md", "# Brief\n\nOriginal.\n")
        self.write("company/specs/spec-thing.md", "# Spec\n\nOriginal.\n")
        self.commit("track a brief and a spec")
        before = self.hash()

        self.write("company/briefs/brief-thing.md", "# Brief\n\nRewritten.\n")
        self.assertEqual(self.hash(), before, "tracked brief edit moved it")

        self.write("company/specs/spec-thing.md", "# Spec\n\nRewritten.\n")
        self.assertEqual(self.hash(), before, "tracked spec edit moved it")

        self.write("company/briefs/brief-new.md", "# New\n\nUntracked.\n")
        self.assertEqual(self.hash(), before, "new brief moved it")

        os.remove(os.path.join(self.root, "company", "specs",
                               "spec-thing.md"))
        self.assertEqual(self.hash(), before, "deleting a spec moved it")

        # The control: same directory tree, a path that is NOT excluded.
        self.write("company/METHOD.md", "# Method\n\nDoctrine.\n")
        self.assertNotEqual(self.hash(), before,
                            "company/ is excluded wholesale - too wide")

    def test_company_state_writes_do_not_move_the_hash_fr_hp_06(self):
        """The stamp and the log live here and must not self-invalidate."""
        self.write("company/state/adherence.log", "seed\n")
        self.commit("track the log")
        before = self.hash()
        with open(os.path.join(self.root, "company", "state",
                               "adherence.log"), "a") as f:
            f.write("a later line\n")
        self.assertEqual(self.hash(), before)
        self.write("company/state/gates.status", '{"status": "green"}')
        self.assertEqual(self.hash(), before)


# ---------------------------------------------------------------------------
# FR-HP-07  slow-hash breadcrumb
# ---------------------------------------------------------------------------


class TestSlowHashBreadcrumb(KernelBase):
    def setUp(self):
        super(TestSlowHashBreadcrumb, self).setUp()
        # The breadcrumb targets CLAUDE_PROJECT_DIR when set. Pin it to the
        # fixture so an ambient value from the surrounding session cannot send
        # the line into the real repo.
        patcher = mock.patch.dict(os.environ,
                                  {"CLAUDE_PROJECT_DIR": self.root})
        patcher.start()
        self.addCleanup(patcher.stop)

    def log_path(self):
        return os.path.join(self.root, "company", "state", "adherence.log")

    def log_lines(self):
        if not os.path.exists(self.log_path()):
            return []
        with open(self.log_path()) as f:
            return f.read().splitlines()

    def slow_lines(self):
        return [ln for ln in self.log_lines() if "timing | SLOW" in ln]

    def test_shipped_threshold_is_one_and_a_half_seconds_fr_hp_07(self):
        """Pinned here so the cases below can shrink it and stay fast."""
        self.assertEqual(_common.SLOW_HASH_SECONDS, 1.5)

    def test_slow_hash_logs_exactly_one_line_fr_hp_07(self):
        """One breadcrumb, naming the elapsed time and the threshold."""
        def slow(root):
            time.sleep(0.3)
            return "tree:deadbeef"

        with mock.patch.object(_common, "SLOW_HASH_SECONDS", 0.05), \
                mock.patch.object(_common, "_work_hash_impl", slow):
            value = _common.work_hash(self.root)
        self.assertEqual(value, "tree:deadbeef")
        lines = self.slow_lines()
        self.assertEqual(len(lines), 1, self.log_lines())
        numbers = [float(n) for n in re.findall(r"\d+\.\d+", lines[0])]
        self.assertIn(0.05, numbers, lines[0])
        self.assertTrue([n for n in numbers if n >= 0.2], lines[0])

    def test_fast_hash_logs_nothing_fr_hp_07(self):
        """The fast path is asserted by OUTCOME - zero appended lines."""
        before = len(self.log_lines())
        with mock.patch.object(_common, "_work_hash_impl",
                               return_value="tree:cafe"):
            self.assertEqual(_common.work_hash(self.root), "tree:cafe")
        self.assertEqual(self.log_lines()[before:], [])
        self.assertEqual(self.slow_lines(), [])

    def test_failing_log_write_does_not_raise_fr_hp_07(self):
        """The breadcrumb reaches no decision, so it may never become one.

        The state directory and any existing log are made read-only, so the
        append genuinely fails at the filesystem instead of at a patched
        function the kernel might not call.
        """
        state = os.path.join(self.root, "company", "state")
        with open(self.log_path(), "w") as f:
            f.write("seed\n")
        os.chmod(self.log_path(), 0o444)
        os.chmod(state, 0o555)
        self.addCleanup(os.chmod, state, 0o755)
        self.addCleanup(os.chmod, self.log_path(), 0o644)
        if os.access(self.log_path(), os.W_OK):
            self.skipTest("running as a user that ignores file permissions")

        def slow(root):
            time.sleep(0.3)
            return "tree:survived"

        with mock.patch.object(_common, "SLOW_HASH_SECONDS", 0.05), \
                mock.patch.object(_common, "_work_hash_impl", slow):
            self.assertEqual(_common.work_hash(self.root), "tree:survived")
        with open(self.log_path()) as f:
            self.assertEqual(f.read(), "seed\n")


# ---------------------------------------------------------------------------
# FR-HP-08  the ADR that records the decision
# ---------------------------------------------------------------------------


class TestFreshnessAdr(unittest.TestCase):
    ADR = os.path.join(REPO_ROOT, "company", "adr",
                       "ADR-0002-content-based-freshness.md")

    def body(self):
        with open(self.ADR) as f:
            return f.read()

    def test_adr_exists_fr_hp_08(self):
        self.assertTrue(os.path.exists(self.ADR), self.ADR)

    def test_adr_status_is_mechanical_and_tracked_fr_hp_08(self):
        """FR-HP-08 asks for `Status: accepted`. ADR-0001 - accepted, and its
        scope IS company/adr/ - reserves that moment to the CEO, and
        guard_frozen blocks a new ADR born accepted. A builder does not pick a
        winner between a brief and an accepted ADR, so ADR-0002 shipped
        `proposed` with CR-HP-1 asking for the flip.

        This asserts both halves of that, and it is not a weakened version of
        the criterion: the status line must be one of the two mechanical forms
        (a typo or `superseded-by` on a brand-new ADR still fails), and while
        it reads `proposed` the CR requesting acceptance must exist and name
        this ADR. The test goes green on the CEO's flip without an edit, and it
        is the mechanical marker that the CR is still open until then.
        """
        status = [ln.strip() for ln in self.body().splitlines()
                  if ln.strip().startswith("Status:")]
        self.assertIn(status[:1], (["Status: proposed"], ["Status: accepted"]),
                      status)
        if status[:1] == ["Status: proposed"]:
            cr = os.path.join(REPO_ROOT, "company", "change-requests",
                              "CR-HP-1-accept-adr-0002.md")
            self.assertTrue(os.path.exists(cr),
                            "ADR-0002 is proposed with no CR asking to accept "
                            "it: " + cr)
            with open(cr) as f:
                body = f.read()
            self.assertIn("ADR-0002-content-based-freshness.md", body)
            self.assertIn("Status: accepted", body)

    def test_adr_cites_the_hash_requirements_fr_hp_08(self):
        """A decision record that does not name what it decided is a stub."""
        body = self.body()
        self.assertIn("FR-HP-05", body)
        self.assertIn("FR-HP-06", body)


# ---------------------------------------------------------------------------
# rel_path inside linked worktrees - the P0
# ---------------------------------------------------------------------------


class TestWorktreeRelPath(Base):
    """rel_path made every guard keyed on it blind inside worktrees.

    A linked worktree lives INSIDE the project root, so rel_path never took
    its outside-the-tree branch. It returned a PREFIXED project-relative path
    - `.claude/worktrees/<slug>/company/state/gates.status` - which matches no
    frozen pattern, no test-path rule and no source-path rule. Every guard
    keyed on rel_path therefore allowed, silently, in the one place where all
    delegated work happens: guard_frozen (registry, always-list, accepted-ADR
    immutability), guard_tests, guard_spec, guard_models, no_slop's log target.

    What held the line was doctrine, not mechanism. These cases exist so the
    mechanism holds it too, and every one of them is asserted through a real
    hook subprocess rather than against rel_path alone, because the bug was
    never in rel_path's own return value - it was in what the guards did with
    it.
    """

    def setUp(self):
        super(TestWorktreeRelPath, self).setUp()
        self.init_git()
        self.wt = os.path.join(self.root, ".claude", "worktrees", "lane")
        result = git(self.root, "worktree", "add", "-b", "task/lane", self.wt)
        if result.returncode != 0:
            self.skipTest("git worktree add unavailable: " + result.stderr)
        self.addCleanup(git, self.root, "worktree", "remove", "--force",
                        self.wt)

    def wt_file(self, rel, content="x\n"):
        """A path inside the linked worktree, with its parents created."""
        path = os.path.join(self.wt, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def edit(self, hook, file_path):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                   "tool_input": {"file_path": file_path,
                                  "old_string": "x", "new_string": "y"},
                   "cwd": self.root}
        return run_hook(hook, payload, self.root)

    # -- the control, both directions -------------------------------------

    def test_frozen_file_blocks_in_main_checkout_fr_hp_09(self):
        """The direction that always worked, kept as the control's other half.

        Without this, a rel_path change that broke main-checkout matching
        would look like a pass on the worktree case alone.
        """
        target = os.path.join(self.root, "company", "state", "gates.status")
        self.write("company/state/gates.status", '{"status": "green"}')
        r = self.edit("guard_frozen.py", target)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("frozen", r.stderr.lower())

    def test_frozen_file_blocks_inside_worktree_fr_hp_09(self):
        """The reported P0: the IDENTICAL edit to the IDENTICAL frozen file,
        allowed with exit 0 purely because the path ran through a worktree.
        """
        target = self.wt_file("company/state/gates.status",
                              '{"status": "green"}')
        r = self.edit("guard_frozen.py", target)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("frozen", r.stderr.lower())

    def test_accepted_adr_is_immutable_inside_worktree_fr_hp_09(self):
        """Accepted-ADR immutability is the same blind spot, and it is the one
        this lane walked past: ADR-0002 was written proposed because doctrine
        said so, not because anything would have stopped it.
        """
        target = self.wt_file(
            "company/adr/ADR-0002-content-based-freshness.md",
            "# ADR-0002\n\nStatus: accepted\nDate: 2026-08-13\n",
        )
        r = self.edit("guard_frozen.py", target)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("accepted ADR", r.stderr)

    # -- the other guards that consume rel_path ---------------------------

    def test_guard_tests_blocks_test_edit_inside_worktree_fr_hp_09(self):
        """guard_tests already held here, and this pins that it still does.

        Measured, not assumed: this case passes against the OLD rel_path too.
        guard_tests keys on path SEGMENTS (`tests` anywhere in the path), not
        on a prefix-anchored pattern, so the worktree prefix never hid it.
        That is exactly why the blind spot was invisible for so long - the
        guards that use rel_path do not all use it the same way, and the two
        segment-based ones kept working while the pattern-based ones did not.
        It is a regression pin, not a proof of the fix.
        """
        self.set_task({"task": "lane", "type": "feature",
                       "brief": "company/briefs/brief-lane.md"})
        self.write("company/briefs/brief-lane.md", "# Brief\n")
        target = self.wt_file("tests/hooks/test_thing.py", "assert True\n")
        r = self.edit("guard_tests.py", target)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("tests", r.stderr.lower())

    def test_guard_tests_still_allows_with_scope_open_inside_worktree(self):
        """The fix must not turn test_scope into a dead grant.

        This one matters more than it looks: every lane in flight edits tests
        inside a worktree, so a fix that made rel_path unrecognizable to
        guard_tests would block all of them at once.
        """
        self.set_task({"task": "lane", "type": "feature",
                       "brief": "company/briefs/brief-lane.md",
                       "test_scope": True})
        self.write("company/briefs/brief-lane.md", "# Brief\n")
        target = self.wt_file("tests/hooks/test_thing.py", "assert True\n")
        r = self.edit("guard_tests.py", target)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_guard_spec_blocks_unbriefed_source_edit_inside_worktree(self):
        """A source edit with no active brief is blocked in the main checkout
        and used to sail through in a worktree, because `.claude` is an exempt
        directory segment and the prefixed path started with it.
        """
        target = self.wt_file("src/app.py", "print('x')\n")
        r = self.edit("guard_spec.py", target)
        self.assertEqual(r.returncode, 2, r.stderr)

    # -- derivation
    # -- derivation, not convention ---------------------------------------

    def test_worktree_at_an_unconventional_path_fr_hp_09(self):
        """Nothing may depend on the `.claude/worktrees` naming.

        `git worktree add` accepts any path, so the rule is derived from the
        `.git` marker that defines a working-tree root. A literal string match
        on our own convention would pass the case above and fail this one.
        """
        odd = os.path.join(self.root, "build", "elsewhere", "wt2")
        result = git(self.root, "worktree", "add", "-b", "task/other", odd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(git, self.root, "worktree", "remove", "--force", odd)
        target = os.path.join(odd, "company", "state", "gates.status")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write("{}")
        self.assertEqual(
            _common.rel_path(self.root, target), "company/state/gates.status")
        r = self.edit("guard_frozen.py", target)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_a_directory_that_merely_looks_like_a_worktree_is_not_one(self):
        """No false positives: a plain directory named like a worktree keeps
        its real project-relative path, because it IS just a project
        directory. This is the case a string match on `.claude/worktrees`
        would get wrong in the other direction.
        """
        path = os.path.join(self.root, ".claude", "worktrees", "notacheckout",
                            "company", "state", "gates.status")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("{}")
        self.assertEqual(
            _common.rel_path(self.root, path),
            ".claude/worktrees/notacheckout/company/state/gates.status")

    # -- rel_path itself, including the fail-open edges --------------------

    def test_rel_path_resolves_to_the_owning_checkout_fr_hp_09(self):
        target = self.wt_file("company/state/gates.status", "{}")
        self.assertEqual(
            _common.rel_path(self.root, target), "company/state/gates.status")

    def test_rel_path_unchanged_for_main_checkout_paths_fr_hp_09(self):
        self.write("company/state/gates.status", "{}")
        target = os.path.join(self.root, "company", "state", "gates.status")
        self.assertEqual(
            _common.rel_path(self.root, target), "company/state/gates.status")
        self.assertEqual(
            _common.rel_path(self.root, "src/app.py"), "src/app.py")
        self.assertEqual(_common.rel_path(self.root, self.root), "")
        self.assertEqual(_common.rel_path(self.root, ""), "")

    def test_rel_path_outside_the_tree_is_unchanged_fr_hp_09(self):
        outside = tempfile.mkdtemp(prefix="cc-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        target = os.path.join(outside, "company", "state", "gates.status")
        self.assertEqual(_common.rel_path(self.root, target),
                         target.lstrip("/"))

    def test_rel_path_fails_open_on_a_broken_root_fr_hp_09(self):
        """Any trouble degrades to the old answer, never to an exception."""
        with mock.patch.object(os.path, "exists",
                               side_effect=OSError("boom")):
            value = _common.rel_path(self.root, "company/state/gates.status")
        self.assertEqual(value, "company/state/gates.status")
        self.assertEqual(_common.rel_path(None, "a/b.py"), "a/b.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
