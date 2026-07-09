#!/usr/bin/env python3
"""Subprocess-driven tests for guard_provenance.py.

Each test builds a throwaway fixture (manifest, active-task, and git where the
work_hash / dirty tree matters), then drives the hook through run_hook with the
correct hook_event_name. Ledger state (dispatches, audits) is only ever seeded
by driving REAL Mode B-pre / Mode B-post payloads, never by hand-writing the
ledger, so the machinery under test is the machinery that produced the state.
"""

import json
import os
import sys

# Same-dir sibling import: works under `unittest discover -s tests/hooks`
# (which seeds sys.path) and under `-m unittest tests.hooks.test_guard_provenance`
# (which does not) - mirror the hooks' own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook  # noqa: E402

HOOK = "guard_provenance.py"

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor", "security-reviewer"],
    "builder_roles": ["tech-lead", "developer", "qa-engineer"],
}


class ProvBase(Base):
    def set_manifest(self, obj=None):
        self.write(
            "company/provenance.json",
            json.dumps(MANIFEST if obj is None else obj),
        )

    def feature_task(self, slug="feat-x", **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        self.set_task(obj)

    def postedit_payload(self, file_path, cwd=None):
        return {"hook_event_name": "PostToolUse", "tool_name": "Write",
                "tool_input": {"file_path": file_path, "content": "code"},
                "cwd": cwd or self.root}

    def dispatch_payload(self, role="tech-lead"):
        return {"hook_event_name": "PreToolUse", "tool_name": "Task",
                "tool_input": {"subagent_type": role}, "cwd": self.root}

    def audit_payload(self, resp="audit complete, ship it", role="auditor",
                      cwd=None):
        return {"hook_event_name": "PostToolUse", "tool_name": "Task",
                "tool_input": {"subagent_type": role},
                "tool_response": resp, "cwd": cwd or self.root}

    def stage_source(self, rel="src/app.py", content="x = 1"):
        self.write(rel, content)
        git(self.root, "add", rel)

    def stop_payload(self, active=False):
        return {"hook_event_name": "Stop", "stop_hook_active": active,
                "cwd": self.root}

    def read_ledger(self):
        p = os.path.join(self.root, "company", "state",
                         "provenance-ledger.json")
        return json.load(open(p))

    def adherence(self):
        p = os.path.join(self.root, "company", "state", "adherence.log")
        return open(p).read() if os.path.exists(p) else ""

    def seed_dispatch(self, role="tech-lead"):
        r = run_hook(HOOK, self.dispatch_payload(role), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def seed_audit(self, resp="audit complete, ship it"):
        r = run_hook(HOOK, self.audit_payload(resp), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


# --------------------------------------------------------------------------
# Mode E - the execution gate (PreToolUse Edit|Write|MultiEdit)
# --------------------------------------------------------------------------
class TestExecutionGate(ProvBase):
    def test_no_decision_blocks_with_roster(self):
        self.set_manifest()
        self.feature_task()
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("execution", r.stderr)
        # roster is drawn from the manifest roles at minimum
        self.assertIn("tech-lead", r.stderr)

    def test_self_with_why_allows(self):
        self.set_manifest()
        self.feature_task(execution="self", execution_why="glue only")
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_self_without_why_blocks(self):
        self.set_manifest()
        self.feature_task(execution="self")
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("execution", r.stderr)

    def test_delegated_no_dispatch_blocks(self):
        self.set_manifest()
        self.feature_task(execution="delegated", execution_why="tech-lead owns")
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("contradicts", r.stderr)

    def test_delegated_after_dispatch_allows(self):
        self.set_manifest()
        self.feature_task(execution="delegated", execution_why="tech-lead owns")
        self.seed_dispatch("tech-lead")
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_worktree_file_path_allows(self):
        self.set_manifest()
        self.feature_task()  # undecided would block in the main checkout
        r = run_hook(
            HOOK,
            self.edit_payload("Write", ".claude/worktrees/wt/src/app.py", "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_worktree_cwd_allows(self):
        # A subagent editing inside its own worktree: file_path is under the
        # worktree checkout and the payload cwd is that worktree.
        self.set_manifest()
        self.feature_task()
        wt = os.path.join(self.root, ".claude", "worktrees", "wt")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": os.path.join(wt, "src/app.py"),
                                  "content": "x"},
                   "cwd": wt}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_quick_task_allows(self):
        self.set_manifest()
        self.set_task({"task": "q", "type": "quick"})
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_hotfix_allows_and_logs_bypass(self):
        self.set_manifest()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BYPASS", self.adherence())

    def test_markdown_target_allows(self):
        self.set_manifest()
        self.feature_task()  # undecided; a .md is never source
        r = run_hook(HOOK, self.edit_payload("Write", "src/README.md", "# hi"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_manifest_allows(self):
        self.feature_task()  # undecided but no manifest -> rollout off
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_active_task_allows(self):
        self.set_manifest()
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_garbage_stdin_allows(self):
        self.set_manifest()
        self.feature_task()
        r = run_hook(HOOK, None, self.root, raw_stdin="not json")
        self.assertEqual(r.returncode, 0, r.stderr)


# --------------------------------------------------------------------------
# Mode C - the commit gate (PreToolUse Bash)
# --------------------------------------------------------------------------
class TestCommitGate(ProvBase):
    def dirty_source(self, rel="src/app.py", content="x = 1", stage=True):
        # Stage the file: at a real commit/close gate source is `git add`ed,
        # so porcelain reports it file-by-file (a wholly-untracked new
        # directory would otherwise collapse to just the directory name under
        # the sealed `git status --porcelain` command).
        self.write(rel, content)
        if stage:
            git(self.root, "add", rel)

    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def test_dirty_no_audit_blocks(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("auditor", r.stderr)
        self.assertIn("src/app.py", r.stderr)

    def test_fresh_audit_allows(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        self.seed_audit()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_edit_after_audit_stales_and_blocks(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        self.seed_audit()
        # tree changes after the audit -> work_hash moves -> audit is stale
        self.dirty_source(content="x = 2")
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("stale", r.stderr.lower())

    def test_clean_tree_allows(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_dirty_non_source_only_allows(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.write("docs/notes.md", "notes")
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_manifest_allows(self):
        self.init_git()
        self.feature_task()
        self.dirty_source()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_task_allows(self):
        self.init_git()
        self.set_manifest()
        self.dirty_source()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_hotfix_allows_and_logs_bypass(self):
        self.init_git()
        self.set_manifest()
        self.set_task({"task": "hf", "type": "hotfix"})
        self.dirty_source()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BYPASS", self.adherence())

    def test_worktree_cwd_allows_despite_dirty_main(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        wt = os.path.join(self.root, ".claude", "worktrees", "wt")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m wip"}, "cwd": wt}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_merge_head_allows(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        self.write(".git/MERGE_HEAD", "deadbeef\n")
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("merge conclusion", self.adherence())

    def test_do_not_ship_audit_records_but_does_not_unblock(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        self.seed_audit(resp="findings: DO-NOT-SHIP - broken migration")
        # the audit is on record ...
        audits = self.read_ledger()["audits"]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["verdict"], "do-not-ship")
        # ... but a do-not-ship verdict does not count as a fresh pass
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("DO-NOT-SHIP", r.stderr)

    def test_verifier_completion_in_worktree_records_nothing(self):
        # FR-DE-05: a lead's internal reviewer completing inside a worktree is
        # not the integrator's audit - Mode B-post must record NO audit when
        # the payload cwd is under .claude/worktrees/.
        self.init_git()
        self.set_manifest()
        self.feature_task()
        wt = os.path.join(self.root, ".claude", "worktrees", "x")
        r = run_hook(HOOK, self.audit_payload(cwd=wt), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = os.path.join(self.root, "company", "state",
                         "provenance-ledger.json")
        audits = json.load(open(p))["audits"] if os.path.exists(p) else []
        self.assertEqual(audits, [])

    def test_tampered_ledger_blocks(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        self.seed_audit()
        # hand-corrupt the checksum: unverifiable history reads as no audit
        p = os.path.join(self.root, "company", "state",
                         "provenance-ledger.json")
        data = json.load(open(p))
        data["checksum"] = "deadbeef"
        json.dump(data, open(p, "w"))
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_slug_change_resets_ledger(self):
        self.init_git()
        self.set_manifest()
        self.feature_task(slug="feat-a")
        self.dirty_source()
        self.seed_audit()
        # the audited slug allows; a new slug is a fresh ledger
        self.assertEqual(self.commit().returncode, 0)
        self.feature_task(slug="feat-b")
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)


# --------------------------------------------------------------------------
# Mode D - the close gate (Stop)
# --------------------------------------------------------------------------
class TestStopGate(ProvBase):
    def test_dirty_no_audit_emits_block(self):
        self.init_git()
        self.set_manifest()
        self.feature_task(slug="feat-x")
        self.stage_source()
        r = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("feat-x", decision["reason"])
        self.assertIn("auditor", decision["reason"])

    def test_fresh_audit_silent(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.write("src/app.py", "x = 1")
        self.seed_audit()
        r = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_quick_task_silent(self):
        self.init_git()
        self.set_manifest()
        self.set_task({"task": "q", "type": "quick"})
        self.stage_source()
        r = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(r.stdout.strip(), "")

    def test_loop_protection_silent(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.stage_source()
        r = run_hook(HOOK, self.stop_payload(active=True), self.root)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


# --------------------------------------------------------------------------
# Mode A - the drift nudge (PostToolUse Edit|Write|MultiEdit)
# --------------------------------------------------------------------------
class TestDriftNudge(ProvBase):
    def self_task(self, slug="feat-x"):
        self.feature_task(slug=slug, execution="self",
                          execution_why="glue only")

    def test_first_self_idle_edit_nudges(self):
        self.set_manifest()
        self.self_task()
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("auditor", ctx)
        self.assertEqual(
            self.read_ledger()["nudge_state"]["fingerprint"], "self-idle"
        )

    def test_second_identical_edit_silent(self):
        self.set_manifest()
        self.self_task()
        run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_dispatch_clears_nudge_state(self):
        self.set_manifest()
        self.self_task()
        # arm the nudge, then a real dispatch retires the idle state
        run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.seed_dispatch("tech-lead")
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIsNone(self.read_ledger()["nudge_state"])

    def test_slug_change_rearms(self):
        self.set_manifest()
        self.self_task(slug="feat-a")
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertIn("additionalContext", r.stdout)
        # a new slug is a fresh ledger, so the once-per-state nudge fires again
        self.self_task(slug="feat-b")
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("auditor", ctx)

    def test_worktree_edit_silent(self):
        self.set_manifest()
        self.self_task()
        r = run_hook(
            HOOK,
            self.postedit_payload(".claude/worktrees/wt/src/app.py"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_delegated_task_silent(self):
        self.set_manifest()
        self.feature_task(execution="delegated", execution_why="lead owns")
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_quick_task_silent(self):
        self.set_manifest()
        self.set_task({"task": "q", "type": "quick"})
        r = run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")


# --------------------------------------------------------------------------
# FR-DE-15 - the tracking gate (Mode B-pre spawn + Mode E first edit)
# --------------------------------------------------------------------------
class TestTrackingGate(ProvBase):
    def add_origin(self):
        git(self.root, "remote", "add", "origin",
            "https://example.com/x.git")

    def pr_mode(self):
        # PR mode = an 'origin' remote exists; the gate is only live here.
        self.init_git()
        self.add_origin()
        self.set_manifest()

    def builder_spawn(self, role="developer"):
        return run_hook(HOOK, self.dispatch_payload(role), self.root)

    def test_builder_spawn_untracked_feature_blocks(self):
        self.pr_mode()
        self.feature_task()  # no issues recorded
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("gh issue create", r.stderr)

    def test_builder_spawn_tracked_feature_allows_and_records(self):
        self.pr_mode()
        self.feature_task(issues=[42])
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 0, r.stderr)
        dispatches = self.read_ledger()["dispatches"]
        self.assertTrue(
            any(d.get("role") == "developer" for d in dispatches),
            dispatches,
        )

    def test_verifier_spawn_never_tracking_blocked(self):
        # B-pre does not touch verifier roles, tracked or not.
        self.pr_mode()
        self.feature_task()
        r = run_hook(HOOK, self.dispatch_payload("auditor"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_quick_task_builder_spawn_allows(self):
        self.pr_mode()
        self.set_task({"task": "q", "type": "quick"})
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_origin_builder_spawn_allows(self):
        # No remote -> local mode -> gate off (fail open).
        self.init_git()
        self.set_manifest()
        self.feature_task()
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_mode_e_tracking_fires_before_execution_decision(self):
        # Missing BOTH tracking and an execution decision -> tracking first.
        self.pr_mode()
        self.feature_task()
        r = run_hook(HOOK, self.edit_payload("Write", "src/app.py", "x = 1"),
                     self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("gh issue create", r.stderr)
        self.assertNotIn("execution decision", r.stderr)

    def test_hotfix_builder_spawn_allows_and_logs_bypass(self):
        self.pr_mode()
        self.set_task({"task": "hf", "type": "hotfix"})
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BYPASS", self.adherence())

    def test_valid_issues_rejects_empty_list(self):
        self.pr_mode()
        self.feature_task(issues=[])
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("gh issue create", r.stderr)

    def test_valid_issues_rejects_bool_element(self):
        # True is an int subclass but not a real issue number.
        self.pr_mode()
        self.feature_task(issues=[True])
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_valid_issues_rejects_string_element(self):
        self.pr_mode()
        self.feature_task(issues=["42"])
        r = self.builder_spawn("developer")
        self.assertEqual(r.returncode, 2, r.stderr)


# --------------------------------------------------------------------------
# Backstop against a mkdir dodge: source in a brand-new, never-staged
# directory. Under the plain porcelain command git collapses it to `?? dir/`,
# which is_source rejects, so the gate would silently allow. The gate uses
# --untracked-files=all so a new-directory source file is still self-authored.
# --------------------------------------------------------------------------
class TestUntrackedNewDirBackstop(ProvBase):
    NEWSRC = "pkg/new_mod.py"

    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def test_new_dir_source_blocks_commit_and_close(self):
        self.init_git()
        self.set_manifest()
        self.feature_task(slug="feat-x")
        # brand-new directory, never `git add`ed
        self.write(self.NEWSRC, "x = 1")
        rc = self.commit()
        self.assertEqual(rc.returncode, 2, rc.stderr)
        self.assertIn("auditor", rc.stderr)
        self.assertIn(self.NEWSRC, rc.stderr)
        rs = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(rs.returncode, 0, rs.stderr)
        decision = json.loads(rs.stdout)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("feat-x", decision["reason"])

    def test_new_dir_source_after_audit_allows_both(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.write(self.NEWSRC, "x = 1")
        self.seed_audit()
        self.assertEqual(self.commit().returncode, 0)
        rs = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(rs.returncode, 0, rs.stderr)
        self.assertEqual(rs.stdout.strip(), "")

    def test_untracked_non_source_new_dir_stays_exempt(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        # new directory, but a doc file - never gated
        self.write("docs/new/x.md", "notes")
        self.assertEqual(self.commit().returncode, 0)
        rs = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(rs.returncode, 0, rs.stderr)
        self.assertEqual(rs.stdout.strip(), "")


if __name__ == "__main__":
    import unittest
    unittest.main()
