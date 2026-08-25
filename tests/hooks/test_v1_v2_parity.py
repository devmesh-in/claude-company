#!/usr/bin/env python3
"""BR-MST-02, the N==1 identity rule, proved systematically.

active-task.json can be a LEGACY SINGLE OBJECT or the v2 {"version": 2,
"tasks": [...]} envelope. With exactly ONE entry the two files describe the
same world, so every hook must behave identically against both: same exit
code, same stdout, same stderr, and the same line appended to
company/state/adherence.log. Behavior may differ ONLY when a second entry
exists.

What this proves is exactly one thing: the two FILE SHAPES are equivalent.
Every install in the field carries the v1 shape, so this is what says the
normalizer cannot make those installs behave differently from the same task
written the new way.

What it cannot see is a change that moves BOTH runs identically. Both runs are
the same code at N == 1, so a hook that started blocking work it used to allow
would keep every case here green as long as it did so in both shapes. The
oracle for N == 1 against the SHIPPED behaviour is elsewhere: the roughly 45
untouched set_task() call sites in the pre-existing suites, plus
test_active_task_schema.Helpers (the per-entry helpers and the
qualify_reason N <= 1 identity), test_multi_task_gates.SingleEntryParity, and
test_multi_task_display.TestSingleEntryParity (which pin the exact exit
code, stdout and adherence line at one entry). This file is one leg of that
proof, not the whole of it.

Coverage: the surviving consumer hooks. Provenance enforcement modes are
deleted (FR-ASR-03).

Method: ONE fixture root per case. Run against the v1 file, capture, reset the
mutable state that hooks write (adherence log, ledger), rewrite the SAME
entry as v2, run again, compare. A single root is what makes
this honest - work_hash excludes company/state, so swapping the task file does
not perturb the tree fingerprint, and both runs see a byte-identical repo.
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

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor"],
    "builder_roles": ["tech-lead", "developer"],
}

MODELS = {
    "roles": {"developer": "opus", "auditor": "opus", "tech-lead": "opus"},
    "builtins": {"general-purpose": "opus"},
}

SESSION_ID = "sess1234-abcd-ef01-2345-6789abcdef01"

# The one entry under test, expressed once and written in both shapes.
ENTRY = {
    "task": "feat-parity",
    "type": "feature",
    "brief": "company/briefs/brief-feat-parity.md",
    "test_scope": False,
}

# State the hooks WRITE. Cleared between the two runs so the second run sees
# the same starting world as the first.
MUTABLE = [
    "company/state/adherence.log",
    "company/state/provenance-ledger.json",
]


def git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args),
                          capture_output=True, text=True)


def strip_timestamps(text):
    """Drop the leading ISO timestamp from each ' | '-delimited log line."""
    out = []
    for line in (text or "").splitlines():
        parts = line.split(" | ")
        out.append(" | ".join(parts[1:]) if len(parts) > 1 else line)
    return "\n".join(out)


class ParityBase(unittest.TestCase):
    """A fixture rich enough to ARM every hook, so parity is never vacuous."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-parity-")
        self.w("company/state/.keep", "")
        self.w("company/provenance.json", json.dumps(MANIFEST))
        self.w("company/models.json", json.dumps(MODELS))
        self.w("company/briefs/brief-feat-parity.md", "# brief\n")
        self.w("company/gates.config", json.dumps(
            {"gates": [{"name": "unit", "command": "true"}]}))
        self.w("company/state/RESUME.md", "# RESUME\ndone: nothing\n")
        self.w("company/state/STATUS.md", "# STATUS\ngreen\n")
        self.w(".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Task|Agent",
             "hooks": [{"command": "guard_models.py"}]}]}}))

        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        self.w("README.md", "base\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "init")
        self.base_sha = git(
            self.root, "rev-parse", "HEAD").stdout.strip()
        # A dirty, self-authored source path: this is what arms Mode C.
        self.w("src/app.py", "x = 1\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def w(self, rel, content):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    # --- the two shapes under test ---------------------------------------
    def write_v1(self, entry):
        self.w("company/state/active-task.json", json.dumps(entry))

    def write_v2(self, entry):
        self.w("company/state/active-task.json",
               json.dumps({"version": 2, "tasks": [entry]}))

    def reset_state(self):
        for rel in MUTABLE:
            try:
                os.unlink(os.path.join(self.root, rel))
            except OSError:
                pass

    # --- running ----------------------------------------------------------
    def capture(self, hook, payload=None, argv=None):
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = self.root
        cmd = [sys.executable, os.path.join(HOOKS_DIR, hook)] + (argv or [])
        r = subprocess.run(
            cmd,
            input=json.dumps(payload) if payload is not None else "",
            capture_output=True, text=True, env=env,
        )
        return {
            "rc": r.returncode,
            "stdout": r.stdout.replace(self.root, "<ROOT>"),
            "stderr": r.stderr.replace(self.root, "<ROOT>"),
            "adherence": strip_timestamps(self.read("adherence.log")),
        }

    def read(self, name):
        path = os.path.join(self.root, "company", "state", name)
        if not os.path.exists(path):
            return ""
        with open(path) as f:
            return f.read()

    def parity(self, hook, payload=None, argv=None, entry=None, expect=None):
        """Assert v1 and v2 are indistinguishable for one hook invocation.

        `expect` is a callable asserting the run actually DID something. Without
        it a parity test passes trivially when both runs no-op, which would
        prove nothing at all.
        """
        entry = ENTRY if entry is None else entry

        self.reset_state()
        self.write_v1(entry)
        v1 = self.capture(hook, payload, argv)

        self.reset_state()
        self.write_v2(entry)
        v2 = self.capture(hook, payload, argv)

        if expect is not None:
            expect(v1)
        for field in ("rc", "stdout", "stderr", "adherence"):
            self.assertEqual(
                v1[field], v2[field],
                "{} {} differs between the v1 single object and the "
                "equivalent v2 one-entry file:\nv1={!r}\nv2={!r}".format(
                    hook, field, v1[field], v2[field]),
            )
        return v1

    # --- payload builders --------------------------------------------------
    def edit_payload(self, file_path, event="PreToolUse", tool="Write"):
        return {"hook_event_name": event, "tool_name": tool,
                "tool_input": {"file_path": os.path.join(self.root, file_path),
                               "content": "x = 1"},
                "cwd": self.root}

    def bash_payload(self, command):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": command}, "cwd": self.root}

    def spawn_payload(self, event="PreToolUse", role="developer", **ti):
        base = {"subagent_type": role}
        base.update(ti)
        return {"hook_event_name": event, "tool_name": "Task",
                "tool_input": base, "cwd": self.root}


def blocks(v):
    assert v["rc"] == 2, "expected a BLOCK, got rc={} stderr={!r}".format(
        v["rc"], v["stderr"])


def logs(marker):
    def check(v):
        assert marker in v["adherence"], (
            "expected {!r} in the adherence log, got {!r}".format(
                marker, v["adherence"]))
    return check


def prints(v):
    assert v["stdout"].strip(), "expected stdout, got nothing"


# --------------------------------------------------------------------------
# The ten consumer hooks
# --------------------------------------------------------------------------
class TestConsumerHookParity(ParityBase):
    def test_guard_spec_block(self):
        entry = dict(ENTRY)
        del entry["brief"]
        self.parity("guard_spec.py", self.edit_payload("src/app.py"),
                    entry=entry, expect=blocks)

    def test_guard_spec_hotfix_bypass(self):
        self.parity("guard_spec.py", self.edit_payload("src/app.py"),
                    entry={"task": "hf", "type": "hotfix"},
                    expect=logs("BYPASS"))

    def test_guard_spec_allows_with_brief(self):
        v = self.parity("guard_spec.py", self.edit_payload("src/app.py"))
        self.assertEqual(v["rc"], 0)

    def test_guard_tests_block(self):
        self.parity("guard_tests.py", self.edit_payload("tests/test_x.py"),
                    expect=blocks)

    def test_guard_tests_scope_open_allows(self):
        entry = dict(ENTRY)
        entry["test_scope"] = True
        v = self.parity("guard_tests.py",
                        self.edit_payload("tests/test_x.py"), entry=entry)
        self.assertEqual(v["rc"], 0)
        # RISK-MST-02's GRANT line is an N>1 signal only: at one entry the log
        # must stay silent, or N==1 parity with today is already broken.
        self.assertNotIn("GRANT", v["adherence"])

    def test_guard_models_block(self):
        self.parity("guard_models.py",
                    self.spawn_payload(model="sonnet"), expect=blocks)

    def test_guard_models_hotfix_bypass(self):
        self.parity("guard_models.py", self.spawn_payload(model="sonnet"),
                    entry={"task": "hf", "type": "hotfix"},
                    expect=logs("BYPASS"))

    def test_guard_commit_protected_branch_block(self):
        self.parity("guard_commit.py", self.bash_payload("git commit -m x"),
                    expect=blocks)

    def test_guard_commit_hotfix_bypass(self):
        self.parity("guard_commit.py", self.bash_payload("git commit -m x"),
                    entry={"task": "hf", "type": "hotfix"},
                    expect=logs("BYPASS"))

    def test_context_pin(self):
        self.parity("context_pin.py",
                    {"hook_event_name": "UserPromptSubmit", "cwd": self.root},
                    expect=prints)

    def test_session_start_digest(self):
        self.parity("session_start.py",
                    {"hook_event_name": "SessionStart", "cwd": self.root},
                    expect=prints)



# --------------------------------------------------------------------------
# BR-MST-10: three ways of saying "no task" must be indistinguishable.
# This is what makes "remove your entry at close" safe as the LAST removal:
# the final remove must land in exactly the state a fresh install is in.
# --------------------------------------------------------------------------
class TestEmptyStateIndistinguishable(ParityBase):
    STATES = (
        ("missing file", None),
        ("v2 empty list", {"version": 2, "tasks": []}),
        ("bare empty list", {"tasks": []}),
    )

    def run_all(self, hook, payload=None, argv=None):
        seen = []
        for name, content in self.STATES:
            self.reset_state()
            path = os.path.join(self.root, "company", "state",
                                "active-task.json")
            if content is None:
                if os.path.exists(path):
                    os.unlink(path)
            else:
                self.w("company/state/active-task.json", json.dumps(content))
            seen.append((name, self.capture(hook, payload, argv)))
        first_name, first = seen[0]
        for name, got in seen[1:]:
            for field in ("rc", "stdout", "stderr", "adherence"):
                self.assertEqual(
                    first[field], got[field],
                    "{}: {!r} differs from {!r} on {}".format(
                        hook, name, first_name, field))
        return first

    def test_guard_spec_blocks_in_every_empty_state(self):
        # The FR-MST-05 ordering trap. "ALL over non-hotfix entries" is
        # VACUOUSLY TRUE on an empty list, so an ALL check placed before the
        # empty check would silently flip this gate from BLOCK to ALLOW the
        # moment no task is active. It must still block, all three ways.
        first = self.run_all("guard_spec.py", self.edit_payload("src/app.py"))
        self.assertEqual(first["rc"], 2, "empty state must still BLOCK")

    def test_guard_commit_founding_exemption_in_every_empty_state(self):
        first = self.run_all("guard_commit.py",
                             self.bash_payload("git commit -m x"))
        # The founding-commit exemption covers the PROTECTED-BRANCH rule only.
        # The stamp is not a commit lock (DECISIONS #25), so this commit is
        # allowed. Assert the exemption by its message: not the branch recipe.
        self.assertNotIn("work belongs on a task branch", first["stderr"])
        self.assertNotIn("commit on protected branch", first["adherence"])
        self.assertEqual(first["rc"], 0)

    
    def test_context_pin_silent_in_every_empty_state(self):
        first = self.run_all("context_pin.py",
                             {"hook_event_name": "UserPromptSubmit",
                              "cwd": self.root})
        self.assertEqual(first["stdout"].strip(), "")


if __name__ == "__main__":
    unittest.main()
