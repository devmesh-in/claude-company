#!/usr/bin/env python3
"""scripts/affected-suites.py - the suite scoper.

Not a hook, but it lives in this suite for the same reason
test_doctrine_canon.py does: the hooks suite is the cheapest one and the one
every lane runs, so a repo mechanism that nothing else covers belongs where it
cannot be skipped.

What is asserted here is the tool's two safety properties and the mapping
lines the brief named, each as a claim that can fail:

  * derivation - the suite list comes out of .github/workflows/ci.yml, so
    adding a suite there changes the tool's answer without the tool being
    edited. Driven against a doctored COPY of the workflow, never the real one.
  * fail-safe - an unrecognised path, a mapping selector that no longer
    resolves, and a suite no rule claims each widen the run rather than
    narrow it.
  * the pairing - company/run-gates.sh asks for the installer suite. That is
    the 2026-08-13 regression: a lane changed the gate runner, ran what it
    thought covered it, and CI turned 13 tests red.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
TOOL = os.path.join(REPO, "scripts", "affected-suites.py")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "ci.yml")


def run(args):
    return subprocess.run([sys.executable, TOOL] + args,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)


def plan(paths, workflow=None):
    """The tool's answer as JSON. Text output is for humans; tests read this."""
    args = ["--json"]
    if workflow:
        args += ["--workflow", workflow]
    result = run(args + list(paths))
    if result.returncode != 0:
        raise AssertionError("affected-suites exited %d: %s"
                             % (result.returncode, result.stderr))
    return json.loads(result.stdout)


def suite_named(plan_obj, fragment, key="run"):
    return [p for p in plan_obj[key] if fragment in p]


class Derivation(unittest.TestCase):
    """The suite list is read out of the workflow, never kept beside it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-affected-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doctor(self, transform):
        with open(WORKFLOW, encoding="utf-8") as fh:
            text = fh.read()
        path = os.path.join(self.tmp, "ci.yml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(transform(text))
        return path

    def test_the_real_workflow_yields_the_suites_the_mapping_names(self):
        """Every selector the mapping can name must point at a real suite in
        the real workflow. If one does not, every mapping line that mentions it
        is dead and the tool has quietly stopped scoping anything.
        """
        found = plan(["src/unknown.ts"])["all_suites"]
        for fragment in ("tests/hooks/", "tests/cli/",
                         "tests/install/run_tests.sh",
                         "tests/install/test_tui.sh",
                         "tests/install/test_update.sh"):
            self.assertTrue([p for p in found if fragment in p],
                            "no suite matching %s in %s" % (fragment, found))

    def test_a_suite_added_to_the_workflow_changes_the_answer(self):
        """The derivation claim, driven end to end: add a suite to a doctored
        COPY of the workflow, touch nothing in the tool, and the answer for an
        unrelated change grows by exactly that suite.
        """
        before = plan([".claude/hooks/guard_frozen.py"])

        added = self.doctor(lambda t: t.replace(
            "      - name: Hook tests\n",
            "      - name: Brand new suite\n"
            "        run: bash tests/perf/test_perf.sh\n"
            "      - name: Hook tests\n", 1))
        after = plan([".claude/hooks/guard_frozen.py"], workflow=added)

        self.assertEqual(len(after["all_suites"]), len(before["all_suites"]) + 1)
        self.assertIn("tests/perf/test_perf.sh", after["all_suites"])
        # Unclaimed coverage is unknown coverage, so it runs.
        self.assertIn("tests/perf/test_perf.sh", after["run"])
        self.assertEqual(set(after["run"]) - set(before["run"]),
                         {"tests/perf/test_perf.sh"})

    def test_a_renamed_suite_makes_the_tool_run_everything(self):
        """Mapping drift, the dangerous direction: the workflow renames a
        suite, so the rule pointing at it resolves to nothing. Silently
        dropping that suite is exactly the failure this tool exists to prevent,
        so it widens to everything and says why.
        """
        renamed = self.doctor(lambda t: t.replace(
            "tests/install/test_update.sh", "tests/install/test_rollout.sh"))
        got = plan([".claude/hooks/guard_frozen.py"], workflow=renamed)

        self.assertEqual(set(got["run"]), set(got["all_suites"]))
        self.assertTrue(any("mapping drift" in w for w in got["warnings"]),
                        got["warnings"])

    def test_a_workflow_with_no_suites_is_a_loud_failure(self):
        """A parser that matches nothing must not read as "nothing to run"."""
        empty = self.doctor(lambda t: t.replace("run: bash tests/", "run: : "))
        result = run(["--workflow", empty, ".claude/hooks/guard_frozen.py"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("no suite invocations", result.stderr)


class TheMapping(unittest.TestCase):
    """The path-to-suite facts the brief named, one assertion each."""

    def test_run_gates_asks_for_the_installer_suite(self):
        """THE regression. 2026-08-13: a lane changed company/run-gates.sh,
        ran the suites it believed covered it, and CI turned 13 tests red.
        tests/install/run_tests.sh copies the REAL gate runner into a fixture
        and executes it against four gate configs - it is the only suite that
        does, and nobody runs it by habit.
        """
        got = plan(["company/run-gates.sh"])
        self.assertTrue(suite_named(got, "tests/install/run_tests.sh"),
                        got["run"])
        reason = " ".join(got["reasons"]["tests/install/run_tests.sh"])
        self.assertIn("company/run-gates.sh", reason)

    def test_a_hooks_only_change_skips_the_expensive_suites(self):
        """The clock case: hooks plus the CLI suite, and NOT the 600-second
        update suite. The installer suite writes stub hooks into a synthetic
        source tree, so no real hook change can reach it.
        """
        got = plan([".claude/hooks/guard_frozen.py"])
        self.assertTrue(suite_named(got, "tests/hooks/"), got["run"])
        self.assertTrue(suite_named(got, "tests/cli/"), got["run"])
        self.assertFalse(suite_named(got, "tests/install/test_update.sh"),
                         got["run"])
        self.assertFalse(suite_named(got, "tests/install/run_tests.sh"),
                         got["run"])

    def test_install_sh_asks_for_installer_update_and_cli(self):
        got = plan(["install.sh"])
        for fragment in ("tests/cli/", "tests/install/run_tests.sh",
                         "tests/install/test_update.sh"):
            self.assertTrue(suite_named(got, fragment),
                            "%s missing from %s" % (fragment, got["run"]))

    def test_the_hooks_suite_runs_whatever_changed(self):
        """It is the cheapest suite and the oracle for the rest."""
        for path in ("README.md", "docs/anything.md", "company/METHOD.md",
                     "update.sh", "bin/claude-company.js"):
            got = plan([path])
            self.assertTrue(suite_named(got, "tests/hooks/"),
                            "%s did not ask for the hooks suite" % path)

    def test_the_workflow_itself_asks_for_everything(self):
        got = plan([".github/workflows/ci.yml"])
        self.assertEqual(set(got["run"]), set(got["all_suites"]))


class FailSafe(unittest.TestCase):
    """Unknown widens the run. Over-running costs minutes; under-running cost
    this repo a red branch on 2026-08-13."""

    def test_an_unrecognised_path_asks_for_everything(self):
        got = plan(["src/api/handlers/orders.ts"])
        self.assertEqual(set(got["run"]), set(got["all_suites"]))
        self.assertTrue(any("unrecognised path" in w for w in got["warnings"]),
                        got["warnings"])

    def test_one_unrecognised_path_widens_a_narrow_batch(self):
        """The batch case: a recognised hooks-only change plus one path nobody
        mapped must not stay narrow just because most of the batch is known.
        """
        got = plan([".claude/hooks/guard_frozen.py", "vendor/thing.go"])
        self.assertEqual(set(got["run"]), set(got["all_suites"]))

    def test_a_new_top_level_directory_is_unrecognised(self):
        """New directories are the realistic way an unmapped path appears, and
        the tool must not guess at their coverage.
        """
        got = plan(["packages/worker/index.js"])
        self.assertEqual(set(got["run"]), set(got["all_suites"]))

    def test_no_paths_at_all_still_runs_the_baseline(self):
        """An empty change set is not a licence to run nothing."""
        got = plan([])
        self.assertTrue(suite_named(got, "tests/hooks/"), got["run"])


class Output(unittest.TestCase):
    def test_commands_mode_prints_runnable_lines_only(self):
        result = run(["--commands", ".claude/hooks/guard_frozen.py"])
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(
                line.startswith(("bash ", "npm ", "python3 ", "node ", "sh ")),
                "not a runnable command: %r" % line)

    def test_the_cli_suite_is_named_the_way_canon_names_it(self):
        """CLAUDE.md calls the CLI suite `npm test`. The alias is READ from
        package.json's test script, so it cannot drift from what npm runs.
        """
        with open(os.path.join(REPO, "package.json"), encoding="utf-8") as fh:
            script = json.load(fh)["scripts"]["test"]
        result = run(["--commands", ".claude/hooks/guard_frozen.py"])
        if script.strip() == "bash tests/cli/test_cli.sh":
            self.assertIn("npm test", result.stdout)
        else:
            self.assertIn(script.strip(), result.stdout)

    def test_the_human_output_names_the_skipped_suites(self):
        """A lane has to be able to see what it is NOT running, or the tool is
        asking for trust instead of giving evidence."""
        result = run([".claude/hooks/guard_frozen.py"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SKIP", result.stdout)
        self.assertIn("tests/install/test_update.sh", result.stdout)
        self.assertIn("CI still runs every suite", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
