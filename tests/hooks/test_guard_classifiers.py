#!/usr/bin/env python3
"""Tests for the two classifiers the guards decide on.

FR-HP-13 anchors guard_spec.is_source at the FIRST path segment, so product
code under a nested company/ or docs/ directory stops being invisible to every
source gate. FR-HP-14 and FR-HP-15 replace the DO-NOT-SHIP substring test in
guard_provenance Mode B-post with a labeled-verdict parser over a flattened
tool_response. FR-HP-16 makes the Mode D block name the paths that armed it.

The classifiers are pure functions, so they are called directly; every gate
decision they feed is still driven end to end through a real hook subprocess
against a throwaway fixture project, the way the rest of tests/hooks works.
"""

import json
import os
import sys
import unittest

# Same-dir sibling import: works under `unittest discover -s tests/hooks`
# (which seeds sys.path) and under `-m unittest tests.hooks...` (which does
# not) - mirror the hooks' own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook  # noqa: E402
from test_hooks import HOOKS_DIR  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import guard_provenance as gp  # noqa: E402
import guard_spec  # noqa: E402

HOOK = "guard_provenance.py"
SPEC_HOOK = "guard_spec.py"

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor", "security-reviewer"],
    "builder_roles": ["tech-lead", "developer", "qa-engineer"],
}

# A report that NAMES the verdict vocabulary and then states its own verdict.
# This is the shape that cost four blocked commits against four passing
# audits: the substring test saw DO-NOT-SHIP in the enumeration.
VOCAB_PASS = (
    "Audit complete over the current tree.\n"
    "The auditor protocol returns SHIP / SHIP-WITH-FIXES / DO-NOT-SHIP.\n"
    "Verdict: SHIP\n"
    "No blocking findings.\n"
)

# The real Task tool_response shape: a list of content blocks whose text
# carries real newlines only after it is flattened.
BLOCKS = [
    {"type": "text",
     "text": "Verdict: SHIP\n"
             "Findings: none. The protocol also allows SHIP-WITH-FIXES.\n"},
]


class ClassifierBase(Base):
    """The fixture idiom of test_guard_provenance, trimmed to what is used."""

    def set_manifest(self):
        self.write("company/provenance.json", json.dumps(MANIFEST))

    def feature_task(self, slug="feat-x", **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        self.set_task(obj)

    def postedit_payload(self, file_path):
        return {"hook_event_name": "PostToolUse", "tool_name": "Write",
                "tool_input": {"file_path": file_path, "content": "code"},
                "cwd": self.root}

    def audit_payload(self, resp, role="auditor"):
        return {"hook_event_name": "PostToolUse", "tool_name": "Task",
                "tool_input": {"subagent_type": role},
                "tool_response": resp, "cwd": self.root}

    def stop_payload(self):
        return {"hook_event_name": "Stop", "stop_hook_active": False,
                "cwd": self.root}

    def read_ledger_raw(self):
        return json.load(open(os.path.join(
            self.root, "company", "state", "provenance-ledger.json")))

    def last_verdict(self):
        return self.read_ledger_raw()["audits"][-1]["verdict"]


# --------------------------------------------------------------------------
# FR-HP-13 - is_source anchors the exempt test at the first path segment
# --------------------------------------------------------------------------
class TestIsSourceAnchor(unittest.TestCase):
    def test_nested_company_dir_is_source(self):
        self.assertTrue(
            guard_spec.is_source("app/company/billing.py", "billing.py")
        )

    def test_nested_docs_dir_is_source(self):
        self.assertTrue(
            guard_spec.is_source("src/docs/handler.py", "handler.py")
        )

    def test_nested_dot_claude_dir_is_source(self):
        self.assertTrue(guard_spec.is_source("pkg/.claude/x.py", "x.py"))

    def test_root_machinery_dirs_stay_exempt(self):
        for rel in ("company/state/x.py", ".claude/hooks/x.py",
                    "docs/x.py", ".github/x.py"):
            self.assertFalse(
                guard_spec.is_source(rel, os.path.basename(rel)), rel
            )

    def test_non_source_extension_and_dotfile_stay_exempt(self):
        self.assertFalse(guard_spec.is_source("README.md", "README.md"))
        self.assertFalse(guard_spec.is_source(".env", ".env"))

    def test_root_level_module_is_source(self):
        self.assertTrue(guard_spec.is_source("service.py", "service.py"))

    def test_no_subrepo_depth_two_exemption(self):
        # The polyrepo reference exempts a machinery dir one level under a
        # named sub-repo root. This repo is single-repo, so that rule would
        # re-open exactly the hole FR-HP-13 closes.
        self.assertFalse(hasattr(guard_spec, "_SUBREPOS"))


class TestNestedSourceReachesTheGates(ClassifierBase):
    NESTED = "app/company/billing.py"

    def test_guard_spec_blocks_nested_company_source(self):
        # No active-task.json at all, so no entry carries a usable brief.
        r = run_hook(SPEC_HOOK,
                     self.edit_payload("Edit", self.NESTED, "x = 2"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("brief", r.stderr.lower())

    def test_dirty_source_paths_counts_nested_company_source(self):
        # Deliberate widening of the audit demand: product code under a
        # nested company/ directory now counts as dirty source, so it prices
        # the same audit every other source file prices. Wider gate, on
        # purpose.
        self.init_git()
        self.write(self.NESTED, "x = 1")
        git(self.root, "add", self.NESTED)
        self.assertIn(self.NESTED, gp.dirty_source_paths(self.root))


# --------------------------------------------------------------------------
# FR-HP-14 - the labeled verdict parser
# --------------------------------------------------------------------------
class TestAuditVerdict(unittest.TestCase):
    def test_labeled_ship_beats_a_named_vocabulary(self):
        text = (
            "The auditor protocol returns SHIP / SHIP-WITH-FIXES / HALT.\n"
            "Verdict: SHIP\n"
        )
        self.assertEqual(gp.audit_verdict(text), "ship")

    def test_labeled_ship_beats_a_do_not_ship_in_the_enumeration(self):
        self.assertEqual(gp.audit_verdict(VOCAB_PASS), "ship")

    def test_labeled_halt_records_do_not_ship(self):
        self.assertEqual(gp.audit_verdict("Verdict: HALT"), "do-not-ship")

    def test_labeled_final_verdict_do_not_ship(self):
        self.assertEqual(
            gp.audit_verdict("Final verdict: DO-NOT-SHIP"), "do-not-ship"
        )

    def test_leading_non_word_characters_are_allowed_on_the_label(self):
        self.assertEqual(
            gp.audit_verdict("**Verdict:** SHIP-WITH-FIXES"), "ship-with-fixes"
        )

    def test_a_bare_enumeration_is_unknown(self):
        text = (
            "The auditor protocol returns SHIP / SHIP-WITH-FIXES / HALT / "
            "DO-NOT-SHIP depending on what it finds.\n"
        )
        self.assertEqual(gp.audit_verdict(text), "unknown")

    def test_a_sole_token_counts_without_a_label(self):
        text = "The tree needs work before merge: SHIP-WITH-FIXES.\n"
        self.assertEqual(gp.audit_verdict(text), "ship-with-fixes")

    def test_disagreeing_labels_fail_closed(self):
        text = (
            "Verdict: SHIP\n"
            "On second read the migration is unsafe.\n"
            "Final verdict: DO-NOT-SHIP\n"
        )
        self.assertEqual(gp.audit_verdict(text), "do-not-ship")

    def test_shipping_is_not_a_ship_token(self):
        self.assertEqual(gp.audit_verdict("SHIPPING the release now."),
                         "unknown")

    def test_reship_is_not_a_ship_token(self):
        self.assertEqual(gp.audit_verdict("RESHIP after the fix."), "unknown")

    def test_never_raises_on_any_input(self):
        allowed = ("do-not-ship", "ship-with-fixes", "ship", "unknown")
        for value in (None, 3, [], {}, object(), b"SHIP"):
            self.assertIn(gp.audit_verdict(value), allowed, repr(value))


class TestUnknownIsNotARejection(ClassifierBase):
    def test_fresh_audit_accepts_a_recorded_unknown(self):
        # OQ-HP-09: an ambiguous audit is not a rejection. Asserted, not
        # assumed - the whole fail-open posture of Mode C and Mode D rests
        # on fresh_audit reading "unknown" as passing.
        self.init_git()
        self.set_manifest()
        self.feature_task()
        r = run_hook(HOOK, self.audit_payload("audit complete, no findings"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last_verdict(), "unknown")
        self.assertTrue(gp.fresh_audit(self.root, gp.read_ledger(self.root)))


class TestModeBPostRecordsTheLabeledVerdict(ClassifierBase):
    def test_a_report_naming_the_vocabulary_is_not_a_rejection(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        r = run_hook(HOOK, self.audit_payload(VOCAB_PASS), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(self.last_verdict(), "do-not-ship")
        self.assertEqual(self.last_verdict(), "ship")

    def test_a_content_block_list_response_is_parsed(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        r = run_hook(HOOK, self.audit_payload(BLOCKS), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last_verdict(), "ship")


# --------------------------------------------------------------------------
# FR-HP-15 - response_text
# --------------------------------------------------------------------------
class TestResponseText(unittest.TestCase):
    def test_flattening_restores_the_line_anchor_that_str_destroys(self):
        # The point of the requirement: str() on a list of content blocks
        # renders the newline as backslash plus n, so the labeled-verdict
        # line anchor never matches and a passing audit reads as ambiguous.
        flat = gp.response_text(BLOCKS)
        raw = str(BLOCKS)
        self.assertIn("\n", flat)
        self.assertNotIn("\n", raw)
        self.assertEqual(gp.audit_verdict(flat), "ship")
        self.assertNotEqual(gp.audit_verdict(raw), "ship")

    def test_scalars_and_none(self):
        self.assertEqual(gp.response_text(None), "")
        self.assertEqual(gp.response_text("x"), "x")

    def test_dict_without_any_text_key_falls_back_to_str(self):
        d = {"kind": "report", "body": "Verdict: SHIP"}
        self.assertEqual(gp.response_text(d), str(d))

    def test_nested_containers_flatten_recursively(self):
        resp = {"content": [{"text": "a"}, {"text": "b"}]}
        self.assertEqual(gp.response_text(resp), "a\nb")

    def test_never_raises_on_a_self_referential_response(self):
        loop = []
        loop.append(loop)
        self.assertIsInstance(gp.response_text(loop), str)


# --------------------------------------------------------------------------
# FR-HP-16 - the Mode D block reason names the offending paths
# --------------------------------------------------------------------------
class TestStopReasonNamesPaths(ClassifierBase):
    # FR-HP-16's bare reason - the text with no "Self-authored dirty paths"
    # suffix - is no longer reachable and has been removed from this fixture.
    # Under FR-HP-44 the Mode D self-authored branch only fires when the
    # dirty/self-authored intersection is NON-empty, and that same intersection
    # is what feeds the suffix, so the suffix is now always present on that
    # branch. The case that used to produce the bare reason is the case
    # test_no_self_authored_intersection_no_longer_arms_the_gate covers.

    def test_seven_self_authored_paths_show_five_and_a_count(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        for i in range(7):
            rel = "src/mod{}.py".format(i)
            self.write(rel, "x = {}".format(i))
            git(self.root, "add", rel)
            # Mode A is what records a path as self-authored; seeding it any
            # other way would test a ledger this hook cannot produce.
            r = run_hook(HOOK, self.postedit_payload(rel), self.root)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        reason = decision["reason"]
        for i in range(5):
            self.assertIn("src/mod{}.py".format(i), reason)
        self.assertNotIn("src/mod5.py", reason)
        self.assertNotIn("src/mod6.py", reason)
        self.assertIn("(+2 more)", reason)
        self.assertIn("earlier session", reason)

    def test_no_self_authored_intersection_no_longer_arms_the_gate(self):
        """SUPERSEDED BEHAVIOUR, rewritten deliberately - FR-HP-44.

        This case used to BLOCK and assert a bare reason line. It was the one
        place the old gate's tree-shaped question was visible: dirty source
        that no Mode A event ever recorded still armed the close gate, so a
        session was told it had "self-authored source changes" over files it
        had never touched. Measured against a real polyrepo install that was
        71 unrelated paths against 8 authored ones, and it left no way out
        except faking an audit or deleting another session's work.

        The demand is now armed by dirty paths INTERSECTED WITH the ledger's
        self_authored list, so this exact fixture ALLOWS. The control below is
        what keeps that honest: the identical tree blocks the moment the same
        path is recorded through a real Mode A event, so the allow is the
        narrowing and not an inert fixture.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task()
        # Dirty source exists, but no Mode A edit recorded it, so nothing in
        # the tree is attributable to this company.
        self.write("src/app.py", "x = 1")
        git(self.root, "add", "src/app.py")
        r = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

        # Control: record the SAME path through a real Mode A event.
        rec = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertEqual(rec.returncode, 0, rec.stderr)
        r = run_hook(HOOK, self.stop_payload(), self.root)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("src/app.py", decision["reason"])


if __name__ == "__main__":
    unittest.main()
