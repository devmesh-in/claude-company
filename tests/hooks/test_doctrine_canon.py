#!/usr/bin/env python3
"""Canon-versus-code assertions: doctrine files pinned to the mechanisms.

This is the repo's mechanism for turning a canon/code disagreement into a red
gate. A doctrine file is enforcement here only because a hook, a gate or an
agent reads it, so what is asserted is the sentence a reader has to act on. A
rewrite that keeps the rule keeps these green; a rewrite that drops the rule
turns them red - which is the point, because canon drifted from the code three
separate times and nothing mechanical noticed.

These assertions previously lived in a test file named after the Stop-time gate
DECISIONS #20 deleted, whose name described only its other half. They were
moved here whole ahead of that deletion, because a file named after a deleted
hook is the obvious thing to delete and these have nothing to do with it.

# BR-ASR-10 citation block so git-tracked tests cover spec-ai-sdlc-rework
# even while tests/hooks/test_asr_rework.py is still untracked:
# FR-ASR-01 FR-ASR-02 FR-ASR-03 FR-ASR-04 FR-ASR-05 FR-ASR-06 FR-ASR-07
# FR-ASR-08 FR-ASR-09 FR-ASR-10 FR-ASR-11 FR-ASR-12 FR-ASR-13 FR-ASR-14
# FR-ASR-15 FR-ASR-16 FR-ASR-17 FR-ASR-18 FR-ASR-19 FR-ASR-20 FR-ASR-21
# FR-ASR-22 BR-ASR-01 BR-ASR-02 BR-ASR-03 BR-ASR-04 BR-ASR-05 BR-ASR-06
# BR-ASR-07 BR-ASR-08 BR-ASR-09 BR-ASR-10 BR-ASR-11 BR-ASR-12

Three families live here:

  * CeremonyDoctrineMatchesTheGuard - runs guard_spec for real and compares its
    behavior against what METHOD.md and COMPANY.md claim.
  * EveryHookIsLoadable - every hook parses on the documented Python floor.
  * DoctrineClauses - FR-HP-51 to FR-HP-65, the items authorized by
    DECISIONS #19, and the wiring table, one required clause at a time.
"""

import ast
import json
import os
import sys
import unittest

# Same-dir sibling import: works under `unittest discover -s tests/hooks` and
# under `-m unittest tests.hooks.test_doctrine_canon` - mirror the hooks' own
# sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, run_hook  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
REPO_HOOKS = os.path.join(REPO, ".claude", "hooks")


def doc(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


class CeremonyDoctrineMatchesTheGuard(Base):
    """Canon and mechanism are pinned to each other. DECISIONS #19 (a)
    authorized "a quick entry needs no brief"; whether the clause belongs in
    the doctrine depends entirely on whether guard_spec exempts quick, and
    doctrine the hooks contradict is worse than no doctrine.
    """

    def setUp(self):
        Base.setUp(self)
        self.init_git()

    def test_quick_needs_a_brief_in_the_code_and_in_the_prose_together(self):
        """Reproduction, CEO-verified 2026-08-13: a briefless quick entry
        blocks a source edit made by a SIBLING session whose own brief is
        fine, because the check is an ALL over non-hotfix entries and blocks
        the edit rather than the offending entry.

        When the quick exemption lands in guard_spec, this test fails - and
        the failure is the instruction to restore the doctrine clause in the
        same wave, instead of discovering the divergence a third time.
        """
        self.write("company/briefs/brief-feat-a.md", "a brief\n")
        self.set_tasks(
            {"task": "feat-a", "type": "feature",
             "brief": "company/briefs/brief-feat-a.md"},
            {"task": "quick-b", "type": "quick"},
        )
        r = run_hook("guard_spec.py",
                     self.edit_payload("Edit", "src/app.py", "x"), self.root)
        guard_requires_a_brief = r.returncode == 2
        prose = doc("company/METHOD.md") + doc("COMPANY.md")
        doctrine_says_no_brief_needed = "need no brief" in prose \
            or "needs no brief" in prose
        self.assertEqual(
            guard_requires_a_brief, not doctrine_says_no_brief_needed,
            "guard_spec and the ceremony doctrine disagree about whether a "
            "quick entry needs a brief. guard_spec blocks the edit: {}. The "
            "doctrine says no brief is needed: {}. Make them agree - if the "
            "guard now exempts quick, restore the clause to METHOD.md's "
            "ceremony table and COMPANY's classify step; if it does not, "
            "the clause stays out.".format(
                guard_requires_a_brief, doctrine_says_no_brief_needed))


class EveryHookIsLoadable(unittest.TestCase):
    """A hook with a syntax error does not fail loudly - it fails ABSENT.

    Hooks fail open by design, but a SyntaxError never reaches that design:
    python exits 1, and only exit 2 blocks, so the guarded action proceeds
    with nothing in the session saying enforcement stopped existing. The CI
    job `hooks` is the real gate (it survives a test suite this defect would
    also break); this is the same assertion where a developer meets it first,
    seconds after the edit instead of minutes after the push.
    """

    def test_every_hook_parses_on_the_documented_python_floor(self):
        """ast.parse, never import: importing runs module-level code and
        several hooks read stdin. feature_version pins the 3.8 floor CLAUDE.md
        documents, so syntax newer than the floor fails here rather than on
        the machine of whoever installed this.
        """
        names = sorted(n for n in os.listdir(REPO_HOOKS) if n.endswith(".py"))
        self.assertTrue(names, "no hooks found under " + REPO_HOOKS)
        failures = []
        for name in names:
            path = os.path.join(REPO_HOOKS, name)
            with open(path, "rb") as fh:
                source = fh.read()
            try:
                ast.parse(source, filename=path, feature_version=(3, 8))
            except SyntaxError as exc:
                failures.append("{} line {}: {}".format(name, exc.lineno,
                                                        exc.msg))
        self.assertEqual(
            failures, [],
            "these hooks do not parse, so they enforce nothing and say so to "
            "nobody: " + "; ".join(failures))


class DoctrineClauses(unittest.TestCase):
    def assertClauses(self, rel, fr, clauses):
        text = doc(rel)
        for clause in clauses:
            self.assertIn(
                clause, text,
                "{}: {} lost its required clause: {!r}".format(rel, fr,
                                                               clause))

    # -- COMPANY.md ---------------------------------------------------

    def test_fr_hp_55_parallel_discipline(self):
        """FR-HP-55: a wave dispatched one lane per turn serializes the wave.
        The four habits are the difference between structural parallelism and
        realized parallelism.
        """
        self.assertClauses("COMPANY.md", "FR-HP-55", [
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
        self.assertClauses("COMPANY.md", "FR-HP-56", [
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
        self.assertClauses("COMPANY.md", "FR-HP-64", [
            "state_lock",
            "REPAIR line",
            "resets the checksum",
        ])

    def test_fr_hp_65_advisory_in_both_files(self):
        """FR-HP-65: the advisory distinguishes BUILDING from INTEGRATING.
        Collapsing the two would either ban concurrency the lock layer exists
        to support, or permit the one collision it cannot make safe.
        """
        for rel in ("COMPANY.md", "company/METHOD.md"):
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
        self.assertClauses("COMPANY.md", "FR-HP-57", [
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
        for name in sorted(os.listdir(REPO_HOOKS)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(REPO_HOOKS, name), encoding="utf-8") as f:
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
        self.assertClauses("COMPANY.md", "DECISIONS-19", [
            "spec-lite",
            "ONE-WAY",
            '"spec": "lite:',
        ])
        self.assertClauses("company/METHOD.md", "DECISIONS-19", [
            "spec-lite",
            "ONE-WAY",
        ])

    def test_brief_grant_exception_is_resolved_one_way(self):
        """Brief scope item 9: COMPANY said the CEO applies frozen-surface
        changes itself while a sealed brief had granted a frozen file to a lane
        outright. The doctrine now names the exception instead of leaving two
        rules that contradict each other.
        """
        self.assertClauses("COMPANY.md", "CR-2-reconciliation", [
            "brief-grant exception",
            "exactly one lane",
        ])

    def test_audit_by_default_replaces_the_risk_band(self):
        """FR-ASR-02 / FR-ASR-14: the runbook dispatches the auditor on every
        merge. risk_score.py is gone; a band is not a dispatch trigger.
        """
        text = doc("COMPANY.md")
        self.assertNotIn("risk_score.py", text)
        self.assertIn("auditor", text.lower())

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

    def test_decisions_25_stamp_gates_merge_not_commit(self):
        """DECISIONS #25 / METHOD mechanism 4: the stamp is a merge lock."""
        self.assertClauses("company/METHOD.md", "DECISIONS-25", [
            "integration onto a protected branch",
            "merge lock, not a commit lock",
        ])
        self.assertClauses("company/GATES.md", "DECISIONS-25", [
            "blocks `git merge` onto",
            "Commits are not stamp-gated",
        ])
        method = doc("company/METHOD.md")
        self.assertNotIn(
            "commits are hook-blocked while gates are red or stale", method)

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
        """FR-HP-51: the auditor does not pay the project's ladder. A stale
        stamp is a finding, not a second suite run.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-51", [
            "Do not run the project's ladder",
            "finding, not a reason",
        ])

    def test_fr_hp_52_delta_scoped_re_audit(self):
        """FR-HP-52: a re-audit is a FRESH DISPATCH. A SendMessage resume fires
        no PostToolUse event, so the ledger records nothing and the tree reads
        as un-audited no matter what the auditor concluded.
        """
        self.assertClauses(".claude/agents/auditor.md", "FR-HP-52", [
            "FRESH DISPATCH",
            "never a SendMessage resume",
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

    def test_fr_asr_14_auditor_has_no_do_not_ship_token_warning(self):
        """FR-ASR-14: the deleted parser is gone; auditor.md must not mention
        DO-NOT-SHIP as a token the reader has to avoid.
        """
        text = doc(".claude/agents/auditor.md")
        self.assertNotIn("DO-NOT-SHIP", text)
        self.assertNotIn("risk band", text.lower())
        self.assertNotIn("provenance ledger", text.lower())
        for token in ("SHIP", "SHIP-WITH-FIXES", "HALT"):
            self.assertIn(token, text)

    def test_fr_hp_54_the_verdict_section_survives_the_real_parser(self):
        """FR-HP-54 second AC, unblocked by L2's audit_verdict landing on main
        (BR-HP-04). Two directions, and both matter:

        the auditor's own Verdict section, fed to the shipping parser, must NOT
        record as a rejection - that is the trap that cost four blocked commits
        against four passing audits;

        and a real HALT report must STILL record as one, because swapping the
        vocabulary would otherwise disarm the provenance gate rather than fix
        it. fresh_audit accepts every verdict except do-not-ship, so a HALT
        that parsed as unknown would let a rejected tree commit.
        """
        sys.path.insert(0, REPO_HOOKS)
        import guard_provenance  # noqa: E402

        section = doc(".claude/agents/auditor.md").split("## Verdict", 1)[1]
        self.assertNotEqual(guard_provenance.audit_verdict(section),
                            "do-not-ship")
        self.assertEqual(guard_provenance.audit_verdict("Verdict: HALT"),
                         "do-not-ship")

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

    def test_every_expected_binding_names_a_hook_that_exists(self):
        """The wiring table is canon about the settings file, so it drifts the
        same way prose does - and DECISIONS #20 is the proof: deleting a hook
        while its row survived would have turned `--check` red against a
        perfectly correct install, and deleting the row while the file survived
        would have turned it red the other way. This is the half no settings
        edit can catch, and it replaces the stop-gate-specific binding
        assertion that died with the hook.
        """
        sys.path.insert(0, REPO_HOOKS)
        import guard_models  # noqa: E402

        missing = sorted({
            hook for _, _, hook in guard_models.EXPECTED_WIRING
            if not os.path.exists(os.path.join(REPO_HOOKS, hook))
        })
        self.assertEqual(
            missing, [],
            "EXPECTED_WIRING requires hooks that are not on disk, so --check "
            "fails against a correct install: " + ", ".join(missing))

    def test_the_shipped_settings_bind_every_expected_hook(self):
        """The other direction, read off what actually ships. guard_models
        --check proves this against a copied fixture; this proves the fixture
        is not the only place it holds.
        """
        sys.path.insert(0, REPO_HOOKS)
        import guard_models  # noqa: E402

        data = json.loads(doc(".claude/settings.json"))
        for event, _, hook in guard_models.EXPECTED_WIRING:
            commands = [h.get("command", "")
                        for group in data["hooks"].get(event, [])
                        for h in group.get("hooks", [])]
            self.assertTrue(
                any(hook in cmd for cmd in commands),
                "{} is not bound to {} in the shipped settings: {}".format(
                    hook, event, commands))


if __name__ == "__main__":
    unittest.main()
