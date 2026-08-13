#!/usr/bin/env python3
"""FR-HP-50: the stop_gate block is scoped to one gating entry.

stop_gate reads every active entry but checks ONE tree-wide gates.status
stamp. With several sessions in flight that made any one session's red tree
block every other session at every turn end, and the recipe told the wrong
session to fix work it does not own.

The scoped rule under test here:

  * exactly ONE gating entry + a bad stamp -> BLOCK, byte-identical to the
    pre-FR-HP-50 hook. The literals in BLOCK_STDOUT and STALE_LOG /
    MISSING_LOG were recorded by running the OLD hook against a fixture
    before the change, so they are a real regression oracle rather than a
    transcription of the new code.
  * MORE THAN ONE gating entry + a bad stamp -> no block decision at all,
    and exactly one WARN line naming EVERY gating slug.
  * a green fresh stamp, or no gating entries, stays silent either way.

Every decision is driven through a real hook subprocess.
"""

import json
import os
import sys
import unittest

# Same-dir sibling import: works under `unittest discover -s tests/hooks` and
# under `-m unittest tests.hooks.test_stop_gate_scope` - mirror the hooks'
# own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, run_hook  # noqa: E402

# Recorded from the pre-FR-HP-50 hook, one entry {"task": "feat-x",
# "type": "feature"}. Trailing newline included: print() emitted it.
BLOCK_STDOUT = (
    '{"decision": "block", "reason": "Active task \'feat-x\' has red or '
    'stale gates. Run the gate suite (/gates) and make it green, or close '
    'YOUR entry in company/state/active-task.json with a targeted Edit, '
    'before finishing."}\n'
)
BLOCK_REASON = (
    "Active task 'feat-x' has red or stale gates. Run the gate suite "
    "(/gates) and make it green, or close YOUR entry in "
    "company/state/active-task.json with a targeted Edit, before finishing."
)
STALE = "gates.status is stale (work changed since gates ran)"
MISSING = "no gates.status stamp (gates have not been run)"
STALE_LOG = "stop_gate | BLOCK | feat-x | " + STALE
MISSING_LOG = "stop_gate | BLOCK | feat-x | " + MISSING


class StopScopeBase(Base):
    def setUp(self):
        Base.setUp(self)
        self.init_git()

    def log_path(self):
        return os.path.join(self.root, "company", "state", "adherence.log")

    def log_lines(self):
        """adherence.log with the leading timestamp field stripped."""
        if not os.path.exists(self.log_path()):
            return []
        with open(self.log_path()) as f:
            raw = f.read().splitlines()
        return [ln.split(" | ", 1)[1] if " | " in ln else ln for ln in raw]

    def stop_payload(self, stop_hook_active=False):
        return {"hook_event_name": "Stop",
                "stop_hook_active": stop_hook_active, "cwd": self.root}

    def green_stamp(self):
        """Stamp the tree green and fresh."""
        self.write("company/gates.config",
                   json.dumps({"gates": [{"name": "tests"}]}))
        self.stamp({"gates": [{"name": "tests", "ok": True}]})

    def go_stale(self):
        """Dirty the tree so the stamped work_hash no longer matches.

        company/state is excluded from work_hash, so the edit has to land
        outside it or the stamp would stay fresh.
        """
        self.write("src/app.py", "print(1)\n")

    def run_stop(self, stop_hook_active=False):
        return run_hook("stop_gate.py",
                        self.stop_payload(stop_hook_active), self.root)


class SingleGatingEntryIsUnchanged(StopScopeBase):
    """FR-HP-50: at one gating entry the hook must not have moved at all."""

    def test_one_entry_stale_stamp_is_byte_identical_to_the_old_hook(self):
        """FR-HP-50 regression oracle: the single-session block is the whole
        reason stop_gate exists, and scoping must not have shaved a byte off
        it. stdout is compared against the literal recorded from the old
        hook, not against a substring.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertEqual(decision["reason"], BLOCK_REASON)
        self.assertEqual(self.log_lines(), [STALE_LOG])

    def test_one_entry_missing_stamp_blocks_and_logs_the_stamp_cause(self):
        """FR-HP-50: a tree that never ran gates is a distinct failure from a
        stale one. The block text is deliberately the same either way, so the
        cause has to survive in the adherence line - that is the only place a
        reader can tell "never ran" from "ran and went stale".
        """
        self.set_tasks({"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        self.assertEqual(json.loads(r.stdout)["reason"], BLOCK_REASON)
        self.assertEqual(self.log_lines(), [MISSING_LOG])

    def test_one_entry_green_fresh_stamp_is_silent(self):
        """FR-HP-50: a green fresh stamp exits 0 with no decision and no log
        line. If the scoping had reordered the stamp check after the entry
        count, a green tree would start emitting records for nothing.
        """
        self.set_tasks({"task": "feat-x", "type": "feature"})
        self.green_stamp()
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_quick_plus_feature_still_blocks_and_names_only_the_feature(self):
        """FR-HP-50 keeps FR-MST-09: quick exempts ITSELF, not the tree. The
        quick entry drops out of `gating`, which leaves exactly one gating
        entry - so this is a BLOCK, not a WARN, and it must blame feat-x
        alone or the recipe goes to the wrong desk.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "feat-x", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, BLOCK_STDOUT)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertNotIn("'q'", decision["reason"])
        self.assertEqual(self.log_lines(), [STALE_LOG])

    def test_quick_and_hotfix_only_exits_zero_silently(self):
        """FR-HP-50: with no gating entry left there is nothing to block and
        nothing to warn about, even on a stale tree.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "hf", "type": "hotfix"})
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])


class ManyGatingEntriesWarnInsteadOfBlocking(StopScopeBase):
    """FR-HP-50: past one gating entry the block is unactionable, so it goes
    to the log instead of to a turn that cannot use it.
    """

    def test_two_entries_stale_stamp_warns_and_never_blocks(self):
        """FR-HP-50 reproduction: this is the shape that fired on the CEO
        three times in one day. The session ending its turn cannot know whose
        edit dirtied the shared tree, so stdout must carry no decision at all
        - an empty stdout is the assertion that matters, and the WARN line is
        the record that replaces it.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | feat-a, feat-b | " + STALE],
        )

    def test_two_entries_green_fresh_stamp_writes_no_warn(self):
        """FR-HP-50: the WARN is a report of a bad stamp, not a report of
        concurrency. A green tree with two sessions on it is a normal state
        and must leave the log untouched.
        """
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        self.green_stamp()
        before = len(self.log_lines())
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_four_entries_are_all_named_in_the_one_warn_line(self):
        """FR-HP-50 truncation trap: c.slug_list caps display at 3 by default
        and would render "t0, t1, t2 and 1 more". The WARN line is now the
        ONLY record a dropped session appears in, so the cap has to be raised
        at the call site. t3 must be there by name.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks(*[{"task": "t%d" % i, "type": "feature"}
                         for i in range(4)])
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(
            self.log_lines(),
            ["stop_gate | WARN | t0, t1, t2, t3 | " + STALE],
        )


class LoopProtectionAndFailOpen(StopScopeBase):
    """FR-HP-50 must not have disturbed the two safety properties."""

    def test_stop_hook_active_writes_nothing_at_all(self):
        """FR-HP-50: loop protection runs before any state is read, so a
        re-entrant Stop on a stale multi-entry tree produces no decision AND
        no WARN. A WARN here would append a line on every loop iteration.
        """
        self.green_stamp()
        self.go_stale()
        self.set_tasks({"task": "feat-a", "type": "feature"},
                       {"task": "feat-b", "type": "feature"})
        before = len(self.log_lines())
        r = self.run_stop(stop_hook_active=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.log_lines()[before:], [])

    def test_malformed_active_task_json_fails_open(self):
        """FR-HP-50: an unparseable state file must let the turn finish. A
        hook that jammed every Stop on a corrupt JSON byte would be worse
        than the red tree it is guarding.
        """
        self.write("company/state/active-task.json", "{not json at all")
        self.green_stamp()
        self.go_stale()
        r = self.run_stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertNotIn("BLOCK", "\n".join(self.log_lines()))

    def test_unreadable_active_task_json_fails_open(self):
        """FR-HP-50: same contract when the file cannot be opened at all, not
        just when its bytes are bad.
        """
        path = self.write("company/state/active-task.json",
                          json.dumps({"version": 2,
                                      "tasks": [{"task": "feat-x",
                                                 "type": "feature"}]}))
        os.chmod(path, 0o000)
        try:
            r = self.run_stop()
        finally:
            os.chmod(path, 0o644)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertNotIn("BLOCK", "\n".join(self.log_lines()))


# --------------------------------------------------------------------------
# Doctrine assertions - FR-HP-51 to FR-HP-65, plus the two items authorized by
# DECISIONS #19. Each doctrine file is read and its required clause asserted.
#
# These are deliberately clause-level rather than word-level: a doctrine file
# is enforcement here only because a hook, a gate or an agent reads it, so what
# is asserted is the sentence a reader has to act on. A rewrite that keeps the
# rule keeps these green; a rewrite that drops the rule turns them red, which
# is the whole point - this program exists because canon drifted from the code
# three separate times and nothing mechanical noticed.
# --------------------------------------------------------------------------

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def doc(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


class DoctrineClauses(unittest.TestCase):
    def assertClauses(self, rel, fr, clauses):
        text = doc(rel)
        for clause in clauses:
            self.assertIn(
                clause, text,
                "{}: {} lost its required clause: {!r}".format(rel, fr,
                                                               clause))

    # -- ORCHESTRATOR.md ---------------------------------------------------

    def test_fr_hp_55_parallel_discipline(self):
        """FR-HP-55: a wave dispatched one lane per turn serializes the wave.
        The four habits are the difference between structural parallelism and
        realized parallelism.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-55", [
            "## Parallel discipline",
            "in ONE message",
            "never idle while lanes build",
            "per-lane",
            "interrupt-priority",
        ])

    def test_fr_hp_56_dont_fight_the_harness(self):
        """FR-HP-56: every rule here was paid for by a session that decoded a
        guard instead of following its recipe.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-56", [
            "## Don't fight the harness",
            "the block message is the recipe",
            "stales the audit",
            "blocking twice on the same cause",
            "never edit, disable, or tunnel around a guard",
        ])

    def test_fr_hp_64_lost_dispatch_credit_repair(self):
        """FR-HP-64: the ledger is checksum-sealed, so a hand edit does not
        just risk a wrong record - it wipes the audit history. The procedure
        has to name the lock and the REPAIR line or it is not reproducible.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-64", [
            "state_lock",
            "REPAIR line",
            "resets the checksum",
        ])

    def test_fr_hp_65_advisory_in_both_files(self):
        """FR-HP-65: the advisory distinguishes BUILDING from INTEGRATING.
        Collapsing the two would either ban concurrency the lock layer exists
        to support, or permit the one collision it cannot make safe.
        """
        for rel in ("ORCHESTRATOR.md", "company/METHOD.md"):
            self.assertClauses(rel, "FR-HP-65", [
                "one integrating session per repository",
                "index.lock",
            ])
            text = doc(rel)
            self.assertTrue(
                "BUILDING" in text or "building" in text,
                "{}: FR-HP-65 advisory must distinguish building from "
                "integrating".format(rel))

    def test_fr_hp_57_archive_procedure_in_both_files(self):
        """FR-HP-57 / OQ-HP-13: the cap is prose with an archive procedure
        attached. Archiving VERBATIM is the load-bearing half - a summarized
        archive is a lossy edit of the record.
        """
        self.assertClauses("ORCHESTRATOR.md", "FR-HP-57", [
            "company/state/archive/",
            "VERBATIM",
        ])
        self.assertClauses("company/METHOD.md", "FR-HP-57", [
            "company/state/archive/",
            "no hook and no gate enforces",
        ])

    def test_fr_hp_57_no_line_count_constant_in_any_hook(self):
        """FR-HP-57 / OQ-HP-13 negative space: DECISIONS #5 rejected numeric
        fences as an enforcement shape. This is the assertion that keeps the
        300 from migrating out of prose and into a guard later.
        """
        hooks = os.path.join(REPO, ".claude", "hooks")
        for name in sorted(os.listdir(hooks)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(hooks, name), encoding="utf-8") as f:
                for num, line in enumerate(f, 1):
                    if "300" not in line:
                        continue
                    self.assertNotIn(
                        "RESUME", line,
                        "{}:{} looks like a line-count fence".format(name, num))
                    self.assertNotIn(
                        "DECISIONS", line,
                        "{}:{} looks like a line-count fence".format(name, num))

    def test_decisions_19_spec_lite_rung(self):
        """DECISIONS #19 (a): the rung is chosen on objective conditions, and
        the escape upward is ONE-WAY. Without the one-way clause a task could
        ride a lite spec back down after touching a frozen surface, which is
        exactly the case a full spec exists for.
        """
        self.assertClauses("ORCHESTRATOR.md", "DECISIONS-19", [
            "spec-lite",
            "ONE-WAY",
            '"spec": "lite:',
        ])
        self.assertClauses("company/METHOD.md", "DECISIONS-19", [
            "spec-lite",
            "ONE-WAY",
        ])

    def test_brief_grant_exception_is_resolved_one_way(self):
        """Brief scope item 9: ORCHESTRATOR said the CEO applies frozen-surface
        changes itself while a sealed brief had granted a frozen file to a lane
        outright. The doctrine now names the exception instead of leaving two
        rules that contradict each other.
        """
        self.assertClauses("ORCHESTRATOR.md", "CR-2-reconciliation", [
            "brief-grant exception",
            "exactly one lane",
        ])

    # -- company/METHOD.md -------------------------------------------------

    def test_fr_hp_63_state_table_and_content_freshness(self):
        """FR-HP-63: gates.log and gate-output/ are state the company keeps,
        with the runner as their only writer. The negative half matters more:
        no sentence may claim a commit stales a green stamp, because freshness
        is content-based and that false claim costs a rerun per commit.
        """
        self.assertClauses("company/METHOD.md", "FR-HP-63", [
            "gates.log",
            "gate-output/",
        ])
        for num, line in enumerate(doc("company/METHOD.md").splitlines(), 1):
            if "commit" in line and "stales" in line:
                self.fail("company/METHOD.md:{} claims a commit stales the "
                          "stamp: {!r}".format(num, line.strip()))

    # -- company/GATES.md --------------------------------------------------

    def test_fr_hp_62_runner_contract(self):
        """FR-HP-62: quiet-pass output, the gates.log history and its single
        writer, and G7 grown to the full wiring assertion.
        """
        self.assertClauses("company/GATES.md", "FR-HP-62", [
            "gate-output/",
            "gates.log",
            "full wiring",
        ])

    def test_fr_hp_28_root_resolution_is_documented_from_the_script(self):
        """FR-HP-28 as SHIPPED (coordinator correction of 2026-08-13, which
        supersedes the spec text): the runner resolves its root from the
        runner's own location, never from git. The earlier git rev-parse rule
        gated the wrong tree when the installer suite ran the runner by
        absolute path against a non-git fixture, and it cost 13 CI failures.
        """
        text = doc("company/GATES.md")
        self.assertIn("RUNNER'S OWN LOCATION", text)
        self.assertIn("Git is never consulted", text)
        self.assertNotIn("rev-parse", text)
        self.assertIn("stamps THAT worktree", text)

    def test_fr_hp_58_changed_screen_evidence_in_both_files(self):
        """FR-HP-58: four states per CHANGED screen. A full sweep on every task
        is the ceremony this decision removed, so the on-demand exception has
        to be written down or the sweep creeps back.
        """
        for rel in ("company/GATES.md", ".claude/agents/qa-engineer.md"):
            self.assertClauses(rel, "FR-HP-58", [
                "CHANGED screen",
                "full-surface sweep",
            ])

    # -- company/templates/BRIEF-TEMPLATE.md -------------------------------

    def test_fr_hp_60_test_quality_dod(self):
        """FR-HP-60: the four test-quality clauses. The deletion clause is the
        one that keeps a rework diff honest - accreted dead tests read as
        coverage of behavior that no longer exists.
        """
        self.assertClauses("company/templates/BRIEF-TEMPLATE.md", "FR-HP-60", [
            "falsifiable",
            "restating-implementation",
            "extend the existing test file",
            "accreting dead tests is a defect",
        ])

    # -- .claude/agents/ ---------------------------------------------------

    def test_fr_hp_51_auditor_verifies_the_stamp(self):
        """FR-HP-51: the auditor checking the stamp instead of re-running the
        ladder the CEO runs in parallel is what makes an audit cheap enough to
        be mandatory in the high band.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-51", [
            "gate_stamp.py --check",
            "missing, red, or stale",
        ])

    def test_fr_hp_52_delta_scoped_re_audit(self):
        """FR-HP-52: a re-audit is a FRESH DISPATCH. A SendMessage resume fires
        no PostToolUse event, so the ledger records nothing and the tree reads
        as un-audited no matter what the auditor concluded.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-52", [
            "FRESH DISPATCH",
            "never a SendMessage resume",
            "PostToolUse",
        ])

    def test_fr_hp_53_auditor_grades_test_value(self):
        """FR-HP-53: on a rework diff the deleted tests are the correct ones.
        Grading volume rewards exactly the padding this clause calls a finding.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-53", [
            "test VALUE",
            "tautological",
            "deleted together with the behavior",
        ])

    def test_fr_hp_54_verdict_vocabulary_cannot_poison_the_ledger(self):
        """FR-HP-54: guard_provenance classifies an audit response by naive
        substring match on the negative token, so an auditor that quotes its
        own vocabulary records a refusal against a passing tree. The file may
        name the token on exactly ONE line - the line forbidding it.
        """
        text = doc(".claude/agents/auditor.md")
        hits = [ln for ln in text.splitlines() if "DO-NOT-SHIP" in ln]
        self.assertEqual(
            len(hits), 1,
            "auditor.md must name the forbidden token on exactly one line, "
            "found {}: {!r}".format(len(hits), hits))
        # The forbidding sentence wraps, so match on the reflowed paragraph
        # rather than the line: what matters is that the one mention is the
        # prohibition, not where the line break falls.
        flat = " ".join(text.split())
        self.assertIn("Never emit the token `DO-NOT-SHIP` in your prose", flat,
                      "the single DO-NOT-SHIP mention must be the sentence "
                      "forbidding it, got: {!r}".format(hits[0]))
        for token in ("SHIP", "SHIP-WITH-FIXES", "HALT"):
            self.assertIn(token, text)
        verdict = text.split("## Verdict", 1)
        self.assertEqual(len(verdict), 2, "auditor.md lost its Verdict section")
        self.assertNotIn("DO-NOT-SHIP", verdict[1])

    def test_fr_hp_59_docs_librarian_is_batched(self):
        """FR-HP-59: the fork changed the doctrine and left the agent
        definition contradicting it. The description is what the dispatcher
        reads, so the fix is not done until "after any merge" is gone from it.
        """
        text = doc(".claude/agents/docs-librarian.md")
        self.assertIn("BATCHED", text)
        self.assertIn("once per delivery", text)
        self.assertNotIn("after any merge", text)
        description = text.split("---", 2)[1]
        self.assertIn("BATCHED", description,
                      "the BATCHED rule must be in the description "
                      "frontmatter, which is what the dispatcher reads")

    def test_fr_hp_61_tech_lead_rules(self):
        """FR-HP-61: spawn all developers in one message, QA the first finished
        surface, scale the review to risk.
        """
        self.assertClauses(".claude/agents/tech-lead.md", "FR-HP-61", [
            "in ONE message",
            "FIRST finished surface",
            "Scale the review to risk",
        ])

    # -- wiring ------------------------------------------------------------

    def test_stop_gate_is_still_wired_into_settings(self):
        """FR-HP-50 AC: scoping is not un-wiring. A downstream fork removed the
        Stop binding entirely; DECISIONS #18 refused that, because stop_gate is
        the only check on three paths guard_commit cannot see.
        """
        settings = doc(".claude/settings.json")
        self.assertIn("stop_gate.py", settings)
        data = json.loads(settings)
        stop = data["hooks"]["Stop"]
        commands = [h.get("command", "")
                    for group in stop for h in group.get("hooks", [])]
        self.assertTrue(
            any("stop_gate.py" in cmd for cmd in commands),
            "stop_gate.py must stay bound to the Stop event: {}".format(
                commands))


if __name__ == "__main__":
    unittest.main()
