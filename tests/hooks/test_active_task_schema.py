#!/usr/bin/env python3
"""Schema tests for the multi-entry active-task file.

Drives every row of the normalization table through `_common.active_tasks`,
proves `_common.active_task` is gone (not shimmed), and covers the six shared
helpers that keep ANY/ALL logic out of the individual hooks.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".claude", "hooks")
)

# The residual check from FR-MST-03. `active_tasks(` cannot match: the `s`
# sits between `active_task` and the paren.
LEGACY_CALL = re.compile(r"\bactive_task\s*\(")


def load_common():
    """Import _common.py straight off disk, independent of sys.path order."""
    spec = importlib.util.spec_from_file_location(
        "_common_schema_probe", os.path.join(HOOKS_DIR, "_common.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


c = load_common()


def run_hook(name, payload, root):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = root
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


class FixtureBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-schema-")
        os.makedirs(os.path.join(self.root, "company", "state"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def task_path(self):
        return os.path.join(self.root, "company", "state", "active-task.json")

    def write_raw(self, text):
        with open(self.task_path(), "w") as f:
            f.write(text)

    def write_json(self, obj):
        self.write_raw(json.dumps(obj))

    def tasks(self):
        return c.active_tasks(self.root)


class NormalizationTable(FixtureBase):
    """One test per row of the normalization table (BR-MST-01)."""

    def test_missing_file_is_empty(self):
        self.assertFalse(os.path.exists(self.task_path()))
        self.assertEqual(self.tasks(), [])

    def test_unreadable_file_is_empty(self):
        # A directory where the file belongs: open() raises, read_json_file
        # returns None, and the normalizer must still not raise.
        os.makedirs(self.task_path())
        self.assertEqual(self.tasks(), [])

    def test_invalid_json_is_empty(self):
        self.write_raw("{not json at all")
        self.assertEqual(self.tasks(), [])

    def test_scalar_json_is_empty(self):
        for raw in ("null", "\"x\"", "3", "true"):
            with self.subTest(raw=raw):
                self.write_raw(raw)
                self.assertEqual(self.tasks(), [])

    def test_v2_envelope_returns_entries(self):
        a = {"task": "alpha", "type": "feature"}
        b = {"task": "beta", "type": "quick"}
        self.write_json({"version": 2, "tasks": [a, b]})
        self.assertEqual(self.tasks(), [a, b])

    def test_v2_envelope_drops_non_dict_members(self):
        a = {"task": "alpha"}
        self.write_json({"version": 2, "tasks": [a, "x", None, 3, ["y"]]})
        self.assertEqual(self.tasks(), [a])

    def test_v2_envelope_empty_list(self):
        self.write_json({"version": 2, "tasks": []})
        self.assertEqual(self.tasks(), [])

    def test_tasks_list_wins_over_legacy_dict_rule(self):
        # No version key, but a `tasks` LIST: still the envelope shape.
        self.write_json({"tasks": []})
        self.assertEqual(self.tasks(), [])

    def test_v1_single_object(self):
        obj = {"task": "x", "type": "feature", "test_scope": False}
        self.write_json(obj)
        self.assertEqual(self.tasks(), [obj])

    def test_empty_object_is_one_task(self):
        # "A task exists" - this is what preserves guard_commit behavior
        # on a bare {}.
        self.write_json({})
        self.assertEqual(self.tasks(), [{}])

    def test_bare_list(self):
        a = {"task": "alpha"}
        b = {"task": "beta"}
        self.write_json([a, b])
        self.assertEqual(self.tasks(), [a, b])

    def test_bare_list_drops_non_dict_members(self):
        a = {"task": "alpha"}
        self.write_json([a, "x", None, 7])
        self.assertEqual(self.tasks(), [a])

    def test_tasks_dict_falls_through_to_legacy_rule(self):
        obj = {"tasks": {"task": "alpha"}}
        self.write_json(obj)
        self.assertEqual(self.tasks(), [obj])


class Indistinguishability(FixtureBase):
    """No-task-in-flight states must be one single state, everywhere."""

    EMPTY_STATES = (
        None,  # file missing
        {"version": 2, "tasks": []},
        {"tasks": []},
    )

    def apply_state(self, state):
        if state is None:
            if os.path.exists(self.task_path()):
                os.unlink(self.task_path())
            return
        self.write_json(state)

    def test_normalizer_cannot_tell_them_apart(self):
        for state in self.EMPTY_STATES:
            with self.subTest(state=state):
                self.apply_state(state)
                self.assertEqual(self.tasks(), [])
                self.assertFalse(c.has_active_task(self.tasks()))

    def observe(self, name, payload):
        results = []
        for state in self.EMPTY_STATES:
            self.apply_state(state)
            r = run_hook(name, payload, self.root)
            results.append((r.returncode, r.stdout, r.stderr))
        return results

    def test_guard_spec_reacts_identically(self):
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": os.path.join(self.root, "src", "app.py"),
                "content": "x = 1\n",
            },
            "cwd": self.root,
        }
        seen = self.observe("guard_spec.py", payload)
        self.assertEqual(seen[0][0], 2, "expected the no-brief block")
        for other in seen[1:]:
            self.assertEqual(seen[0], other)


class LegacyRemoval(unittest.TestCase):
    """FR-MST-03: removed outright, never shimmed."""

    def test_active_task_attribute_is_gone(self):
        self.assertFalse(hasattr(c, "active_task"))
        self.assertTrue(hasattr(c, "active_tasks"))

    def test_no_hook_calls_the_legacy_helper(self):
        offenders = []
        for dirpath, _dirnames, filenames in os.walk(HOOKS_DIR):
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if LEGACY_CALL.search(line):
                            offenders.append(
                                "{}:{}: {}".format(path, lineno, line.strip())
                            )
        self.assertEqual(offenders, [], "residual active_task( call sites")

    def test_residual_regex_matches_the_legacy_form_only(self):
        # Guards the guard: the regex must fire on the old call and stay
        # silent on the new one and on has_active_task.
        self.assertTrue(LEGACY_CALL.search("task = c.active_task(root)"))
        self.assertIsNone(LEGACY_CALL.search("tasks = c.active_tasks(root)"))
        self.assertIsNone(LEGACY_CALL.search("def has_active_task(tasks):"))


class Helpers(unittest.TestCase):
    A = {"task": "alpha", "type": "feature"}
    B = {"task": "beta", "type": "quick"}
    H = {"task": "gamma", "type": "hotfix"}
    H2 = {"task": "delta", "type": "hotfix"}
    NAMELESS = {"type": "feature"}

    def test_has_active_task(self):
        self.assertFalse(c.has_active_task([]))
        self.assertTrue(c.has_active_task([{}]))
        self.assertTrue(c.has_active_task([self.A, self.B]))

    def test_hotfix_entry_returns_the_first_match(self):
        self.assertIsNone(c.hotfix_entry([]))
        self.assertIsNone(c.hotfix_entry([self.A, self.B]))
        self.assertEqual(c.hotfix_entry([self.A, self.H, self.H2]), self.H)

    def test_hotfix_entry_ignores_non_dict_members(self):
        self.assertEqual(c.hotfix_entry(["x", None, self.H]), self.H)

    def test_entries_of_type_accepts_a_string(self):
        self.assertEqual(
            c.entries_of_type([self.A, self.B, self.H], "feature"), [self.A]
        )

    def test_entries_of_type_accepts_an_iterable(self):
        self.assertEqual(
            c.entries_of_type([self.A, self.B, self.H], ("feature", "quick")),
            [self.A, self.B],
        )

    def test_entries_of_type_empty_cases(self):
        self.assertEqual(c.entries_of_type([], "feature"), [])
        self.assertEqual(c.entries_of_type([self.A], ()), [])
        self.assertEqual(c.entries_of_type([self.A], "program"), [])

    def test_slugs_keeps_order_and_drops_falsy(self):
        self.assertEqual(c.slugs([]), [])
        self.assertEqual(c.slugs([self.A, self.B]), ["alpha", "beta"])
        self.assertEqual(
            c.slugs([self.A, self.NAMELESS, {"task": ""}, self.B]),
            ["alpha", "beta"],
        )

    def test_slug_list_empty(self):
        self.assertEqual(c.slug_list([]), "")

    def test_slug_list_joins_entries(self):
        self.assertEqual(c.slug_list([self.A, self.B]), "alpha, beta")

    def test_slug_list_renders_a_slugless_entry(self):
        self.assertEqual(
            c.slug_list([self.A, self.NAMELESS]), "alpha, <task-slug>"
        )
        self.assertEqual(c.slug_list([{}]), "<task-slug>")

    def test_slug_list_truncates_beyond_the_cap(self):
        entries = [
            {"task": "a"}, {"task": "b"}, {"task": "c"}, {"task": "d"},
            {"task": "e"},
        ]
        self.assertEqual(c.slug_list(entries), "a, b, c and 2 more")
        self.assertEqual(c.slug_list(entries, cap=1), "a and 4 more")
        self.assertEqual(
            c.slug_list(entries, cap=len(entries)), "a, b, c, d, e"
        )

    def test_qualify_reason_is_byte_identical_below_two_entries(self):
        reason = "hotfix mode"
        self.assertEqual(c.qualify_reason(reason, [], self.A), reason)
        self.assertEqual(c.qualify_reason(reason, [self.A], self.A), reason)

    def test_qualify_reason_names_a_single_responsible_entry(self):
        self.assertEqual(
            c.qualify_reason("hotfix mode", [self.A, self.H], self.H),
            "hotfix mode (gamma)",
        )

    def test_qualify_reason_accepts_a_list_of_responsible_entries(self):
        self.assertEqual(
            c.qualify_reason("no active brief", [self.A, self.B],
                             [self.A, self.B]),
            "no active brief (alpha, beta)",
        )


if __name__ == "__main__":
    unittest.main()
