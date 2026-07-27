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
from test_hooks import HOOKS_DIR  # noqa: E402

# The v2 ledger is a data structure with its own accessors, so the ledger
# tests call them directly; every gate decision is still driven end to end
# through a real hook subprocess.
sys.path.insert(0, HOOKS_DIR)
import _common  # noqa: E402
import guard_provenance as gp  # noqa: E402

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

    def dispatch_payload(self, role="tech-lead", slug=None):
        """A builder spawn. `slug` names the entry the spawn prompt targets.

        FR-MST-18: at N > 1 a dispatch is credited only to entries whose slug
        appears in the spawn prompt, so a multi-entry fixture MUST name its
        target. A promptless spawn is credited unconditionally at N == 1 and
        to nobody at N > 1, which is the correct fail-closed behavior and is
        exactly why the slug has to be explicit here.
        """
        ti = {"subagent_type": role}
        if slug:
            ti["prompt"] = "build task/{} per its brief".format(slug)
        return {"hook_event_name": "PreToolUse", "tool_name": "Task",
                "tool_input": ti, "cwd": self.root}

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

    def ledger_file(self):
        return os.path.join(self.root, "company", "state",
                            "provenance-ledger.json")

    def read_ledger_raw(self):
        """The ledger EXACTLY as it sits on disk (the v2 shape)."""
        return json.load(open(self.ledger_file()))

    def active_key(self):
        """Ledger key of the FIRST active entry, as the hooks compute it."""
        raw = json.load(
            open(os.path.join(self.root, "company", "state",
                              "active-task.json"))
        )
        if isinstance(raw, dict) and isinstance(raw.get("tasks"), list):
            raw = raw["tasks"]
        entries = raw if isinstance(raw, list) else [raw]
        return (entries[0].get("task") or "") if entries else ""

    def read_ledger(self):
        return self.read_ledger_raw()

    def record(self, slug):
        """The on-disk per-slug record for `slug`, or {} when absent.

        FR-MST-14 moved dispatches and nudge_state under tasks[<slug>], so an
        assertion about one task's dispatches has to NAME that task. Reading
        them through this accessor keeps the per-slug shape visible at every
        call site rather than hiding it inside a shared reader.
        """
        record = (self.read_ledger_raw().get("tasks") or {}).get(slug) or {}
        return {
            "dispatches": record.get("dispatches") or [],
            "nudge_state": record.get("nudge_state") or None,
        }

    def write_raw_ledger(self, body):
        """Hand-build an on-disk ledger and seal it with a real checksum.

        Only for the MALFORMED or LEGACY shapes the hook can no longer
        produce; every other test seeds through real Mode B payloads.
        """
        sealed = dict(body)
        sealed["checksum"] = _common.stamp_checksum(
            {k: v for k, v in sealed.items() if k != "checksum"}
        )
        return self.write("company/state/provenance-ledger.json",
                          json.dumps(sealed))

    def adherence(self):
        p = os.path.join(self.root, "company", "state", "adherence.log")
        return open(p).read() if os.path.exists(p) else ""

    def seed_dispatch(self, role="tech-lead", slug=None):
        r = run_hook(HOOK, self.dispatch_payload(role, slug), self.root)
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
            self.record("feat-x")["nudge_state"]["fingerprint"], "self-idle"
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
        # record() reports nudge_state None for a slug with NO record at all,
        # so pin the record's existence first: the claim is "the state was
        # CLEARED", not "the record went missing".
        self.assertIn("feat-x", self.read_ledger_raw()["tasks"])
        self.assertIsNone(self.record("feat-x")["nudge_state"])

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
        dispatches = self.record("feat-x")["dispatches"]
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


# --------------------------------------------------------------------------
# FR-MST-14/15/16/17 - the v2 ledger: per-slug dispatches and nudge state,
# global audits / self_authored / unattributed_dispatches, in-memory v1
# migration, pruning on write only.
# --------------------------------------------------------------------------
class TestLedgerV2(ProvBase):
    def entry(self, slug, **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md",
               "execution": "delegated", "execution_why": "lead owns"}
        obj.update(extra)
        return obj

    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def stop(self):
        return run_hook(HOOK, self.stop_payload(), self.root)

    def source_edit(self):
        return run_hook(HOOK, self.edit_payload("Write", "src/app.py",
                                                "x = 1"), self.root)

    def ledger(self):
        return gp.read_ledger(self.root)

    def assert_a_is_whole(self, when):
        """A's two dispatches, the audit, and all three gates allowing."""
        ledger = self.ledger()
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-a")), 2, when)
        self.assertEqual(len(ledger["audits"]), 1, when)
        self.assertEqual(self.commit().returncode, 0, when)
        self.assertEqual(self.stop().stdout.strip(), "", when)
        self.assertEqual(self.source_edit().returncode, 0, when)

    def test_a_second_session_entry_does_not_erase_the_first(self):
        """FR-MST-15, the reported bug: session B writing its task must not
        wipe session A's recorded dispatches and audit, which used to leave A
        spuriously blocked at commit, at Stop, and at its next source edit.
        """
        self.init_git()
        self.set_manifest()
        a = self.entry("feat-a")
        self.set_task(a)
        self.stage_source()
        self.seed_dispatch("tech-lead")
        self.seed_dispatch("developer")
        self.seed_audit()
        self.assert_a_is_whole("A alone")

        b = self.entry("feat-b")
        self.set_tasks(a, b)
        # B is delegated too, so it needs a dispatch OF ITS OWN before Mode E
        # can allow. That is FR-MST-22 step 7 doing its job, not the reported
        # bug: A's dispatch must never vacuously satisfy B. Credit B properly,
        # then the remaining question is purely whether A survived B arriving.
        self.seed_dispatch("tech-lead", slug="feat-b")
        self.assert_a_is_whole("A alongside B")

        # The reported trigger: B's entry lands FIRST, so the on-disk slug
        # stopped matching the active slug, and B's own dispatch then wrote
        # the wipe through. A's history must survive both.
        self.set_tasks(b, a)
        self.seed_dispatch("developer", slug="feat-b")
        self.set_task(a)
        self.assert_a_is_whole("B ran ahead of A, then closed")

    def test_dispatches_do_not_bleed_between_slugs(self):
        """A dispatch is recorded against ONE slug and satisfies only that
        slug's delegated decision.
        """
        self.init_git()
        self.set_manifest()
        a, b = self.entry("feat-a"), self.entry("feat-b")
        self.set_tasks(a, b)
        self.seed_dispatch("tech-lead", slug="feat-a")

        ledger = self.ledger()
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-a")), 1)
        self.assertEqual(gp.dispatches_for(ledger, "feat-b"), [])

        # B is delegated with no dispatch of its own, so its source edit still
        # blocks: A's dispatch must not vacuously satisfy it.
        self.set_tasks(b, a)
        r = self.source_edit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("contradicts", r.stderr)

    def test_v2_tampered_checksum_returns_a_fresh_ledger(self):
        self.init_git()
        self.set_manifest()
        self.set_task(self.entry("feat-a"))
        self.stage_source()
        self.seed_audit()
        data = self.read_ledger_raw()
        self.assertEqual(data["version"], 2)
        data["checksum"] = "deadbeef"
        json.dump(data, open(self.ledger_file(), "w"))

        ledger = self.ledger()
        self.assertEqual(ledger["tasks"], {})
        self.assertEqual(ledger["audits"], [])
        self.assertEqual(self.commit().returncode, 2)

    def legacy_v1(self, slug, work_hash):
        return {
            "version": 1,
            "task": slug,
            "self_authored": [{"path": "src/app.py",
                               "at": "2026-01-01T00:00:00Z"}],
            "audits": [{"role": "auditor", "at": "2026-01-01T00:00:00Z",
                        "work_hash": work_hash, "verdict": "unknown"}],
            "dispatches": [{"role": "tech-lead",
                            "at": "2026-01-01T00:00:00Z"}],
            "nudge_state": {"fingerprint": "self-idle",
                            "at": "2026-01-01T00:00:00Z"},
        }

    def test_v1_ledger_for_an_active_slug_migrates_in_memory(self):
        self.init_git()
        self.set_manifest()
        self.set_task(self.entry("feat-a"))
        self.stage_source()
        path = self.write_raw_ledger(
            self.legacy_v1("feat-a", _common.work_hash(self.root))
        )
        before, mtime = open(path, "rb").read(), os.stat(path).st_mtime_ns

        ledger = self.ledger()
        self.assertEqual(ledger["version"], 2)
        self.assertEqual(len(gp.dispatches_for(ledger, "feat-a")), 1)
        self.assertEqual(
            ledger["tasks"]["feat-a"]["nudge_state"]["fingerprint"],
            "self-idle",
        )
        self.assertEqual(len(ledger["self_authored"]), 1)
        self.assertEqual(len(ledger["audits"]), 1)
        # the migrated audit is honoured by the commit gate ...
        self.assertEqual(self.commit().returncode, 0)
        # ... and read_ledger persisted nothing while doing it
        self.assertEqual(open(path, "rb").read(), before)
        self.assertEqual(os.stat(path).st_mtime_ns, mtime)

    def test_v1_ledger_for_a_closed_slug_returns_fresh(self):
        """Today's wipe is deliberately preserved for this one case: carrying
        a closed task's audit forward would newly satisfy Mode C.
        """
        self.init_git()
        self.set_manifest()
        self.set_task(self.entry("feat-b"))
        self.stage_source()
        self.write_raw_ledger(
            self.legacy_v1("feat-a", _common.work_hash(self.root))
        )

        ledger = self.ledger()
        self.assertEqual(ledger["tasks"], {})
        self.assertEqual(ledger["audits"], [])
        self.assertEqual(ledger["self_authored"], [])
        self.assertEqual(self.commit().returncode, 2)

    def test_v1_ledger_with_an_invalid_checksum_returns_fresh(self):
        self.init_git()
        self.set_manifest()
        self.set_task(self.entry("feat-a"))
        self.stage_source()
        body = self.legacy_v1("feat-a", _common.work_hash(self.root))
        body["checksum"] = "deadbeef"
        self.write("company/state/provenance-ledger.json", json.dumps(body))

        ledger = self.ledger()
        self.assertEqual(ledger["tasks"], {})
        self.assertEqual(ledger["audits"], [])
        self.assertEqual(self.commit().returncode, 2)

    def test_write_prunes_a_closed_slug_but_never_the_global_lists(self):
        self.init_git()
        self.set_manifest()
        a, b = self.entry("feat-a"), self.entry("feat-b")
        self.set_tasks(a, b)
        self.seed_dispatch("tech-lead", slug="feat-a")
        self.set_tasks(b, a)
        self.seed_dispatch("developer", slug="feat-b")
        run_hook(HOOK, self.postedit_payload("src/app.py"), self.root)
        self.seed_audit()
        raw = self.read_ledger_raw()
        self.assertEqual(sorted(raw["tasks"]), ["feat-a", "feat-b"])
        self.assertEqual(len(raw["audits"]), 1)
        self.assertEqual(len(raw["self_authored"]), 1)

        # feat-b closes; the next write prunes its record and nothing else
        self.set_task(a)
        self.seed_dispatch("qa-engineer")
        raw = self.read_ledger_raw()
        self.assertEqual(list(raw["tasks"]), ["feat-a"])
        self.assertEqual(len(raw["tasks"]["feat-a"]["dispatches"]), 2)
        self.assertEqual(len(raw["audits"]), 1)
        self.assertEqual(len(raw["self_authored"]), 1)
        self.assertEqual(raw["unattributed_dispatches"], [])

    def test_read_ledger_never_writes(self):
        """context_pin and session_start both read the ledger (a v1 one here,
        so the migration runs) and must leave the file byte-identical.
        """
        self.init_git()
        self.set_manifest()
        self.set_task(self.entry("feat-a"))
        self.write("company/state/STATUS.md", "status\n")
        path = self.write_raw_ledger(
            self.legacy_v1("feat-a", _common.work_hash(self.root))
        )
        before, mtime = open(path, "rb").read(), os.stat(path).st_mtime_ns

        for hook in ("context_pin.py", "session_start.py"):
            payload = {"hook_event_name": "UserPromptSubmit",
                       "cwd": self.root}
            r = run_hook(hook, payload, self.root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("disp", r.stdout.replace("dispatches", "disp"))
            self.assertEqual(open(path, "rb").read(), before, hook)
            self.assertEqual(os.stat(path).st_mtime_ns, mtime, hook)

    def test_slugless_entry_keys_under_the_empty_string(self):
        self.init_git()
        self.set_manifest()
        slugless = {"type": "feature", "brief": "company/briefs/b.md",
                    "execution": "delegated", "execution_why": "lead owns"}
        self.set_task(slugless)
        self.seed_dispatch("tech-lead")

        raw = self.read_ledger_raw()
        self.assertIn("", raw["tasks"])
        self.assertEqual(len(raw["tasks"][""]["dispatches"]), 1)
        self.assertEqual(len(gp.dispatches_for(self.ledger(), "")), 1)

        # round trip: a second write keeps the same key
        self.seed_dispatch("developer")
        self.assertEqual(len(gp.dispatches_for(self.ledger(), "")), 2)
        self.assertEqual(self.source_edit().returncode, 0)

    def test_partial_turnover_keeps_the_ledger_total_turnover_resets_it(self):
        """FR-MST-15 boundary. Entries appearing and closing around a live
        entry never reset the ledger; a ledger whose every recorded slug has
        closed does, because a closed task's audit must not vacuously verify
        the next task's tree.
        """
        self.init_git()
        self.set_manifest()
        a, b = self.entry("feat-a"), self.entry("feat-b")
        self.set_tasks(a, b)
        self.stage_source()
        self.seed_audit()

        self.set_task(b)                      # A closes, B lives on
        self.assertEqual(len(self.ledger()["audits"]), 1)
        self.assertEqual(self.commit().returncode, 0)

        self.set_task(self.entry("feat-c"))   # both recorded slugs closed
        self.assertEqual(self.ledger()["audits"], [])
        self.assertEqual(self.commit().returncode, 2)

    def test_an_empty_recorded_map_never_verifies_a_new_task(self):
        """The third state of the FR-MST-15 boundary: `tasks` is EMPTY.

        write_ledger prunes `tasks` to the active keys, so an empty map means
        the last write landed while nothing was active - a generation no
        ledger write ever claimed - while the global audits list still carries
        what the PREVIOUS generation verified. Reached by: task A audited at
        work_hash H, A's entry removed, a ledger write with zero entries
        active, then task B added while the tree is still at H.

        Treating that as an open generation let B inherit A's audit, and Mode
        C and Mode D both allowed a commit that the single-task hook blocks -
        an unnamed BLOCK-to-ALLOW at N == 1, which no band may do.
        """
        self.init_git()
        self.set_manifest()
        self.set_task(self.entry("feat-b"))
        self.stage_source()
        audit = {"role": "auditor", "at": "2026-01-01T00:00:00Z",
                 "work_hash": _common.work_hash(self.root),
                 "verdict": "unknown"}

        def on_disk(tasks):
            self.write_raw_ledger({
                "version": 2, "tasks": tasks,
                "unattributed_dispatches": [], "self_authored": [],
                "audits": [audit],
            })

        # Control: the SAME audit, recorded against the live entry, does
        # cover this tree and does allow the commit. Without this the block
        # below could just be a work_hash that never matched.
        on_disk({"feat-b": {"dispatches": [], "nudge_state": None}})
        self.assertEqual(len(self.ledger()["audits"]), 1)
        self.assertEqual(self.commit().returncode, 0)

        on_disk({})
        self.assertEqual(self.commit().returncode, 2,
                         "Mode C must not inherit a closed task's audit")
        self.assertEqual(json.loads(self.stop().stdout)["decision"], "block",
                         "Mode D must not inherit it either")
        self.assertEqual(self.ledger()["audits"], [],
                         "an empty recorded map must reset the ledger")


if __name__ == "__main__":
    import unittest
    unittest.main()
