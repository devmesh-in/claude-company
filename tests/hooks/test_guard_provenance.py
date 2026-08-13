#!/usr/bin/env python3
"""Subprocess-driven tests for guard_provenance.py.

Each test builds a throwaway fixture (manifest, active-task, and git where the
work_hash / dirty tree matters), then drives the hook through run_hook with the
correct hook_event_name. Ledger state (dispatches, audits, self_authored) is
only ever seeded by driving REAL Mode A / Mode B-pre / Mode B-post payloads,
never by hand-writing the ledger, so the machinery under test is the machinery
that produced the state. write_raw_ledger stays reserved for the malformed and
legacy shapes the hook can no longer produce, and tamper_checksum for the
corruption the seal exists to detect.

FR-HP-44/45 narrowed what ARMS the audit demand in Mode C and Mode D. It is no
longer every dirty source path: it is a dirty path the ledger records as
self-authored, or a ledger whose history cannot be trusted, or a diff
risk_score bands high. The decision table for that is
TestModeCDecisionTable / TestModeDDecisionTable, one test per row per mode, and
the two fixture helpers that carry it are stage_source (drives the real Mode A
event, so the path IS recorded self-authored) and bash_written_source (never
fires one, so it is not).
"""

import json
import os
import subprocess
import sys

# Same-dir sibling import: works under `unittest discover -s tests/hooks`
# (which seeds sys.path) and under `-m unittest tests.hooks.test_guard_provenance`
# (which does not) - mirror the hooks' own sys.path insert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook  # noqa: E402
from test_hooks import HOOKS_DIR, hook_path  # noqa: E402

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

    def stage_source(self, rel="src/app.py", content="x = 1", stage=True):
        """Source the CEO wrote through the Write tool, recorded as such.

        FR-HP-44 narrows the audit demand to dirty paths the ledger RECORDS
        as self-authored, and self_authored is populated ONLY by a real Mode A
        PostToolUse event. Writing the file straight to disk therefore records
        nothing, and the gate correctly allows. Driving the real event here is
        what makes every Mode C / Mode D fixture below mean what it says: this
        path was authored in the main checkout by the context that is now
        asking to integrate it.

        Set stage=False for a file that must stay untracked (the new-directory
        backstop needs one).
        """
        self.write(rel, content)
        r = run_hook(HOOK, self.postedit_payload(rel), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        if stage:
            git(self.root, "add", rel)
        return rel

    def bash_written_source(self, rel="src/app.py", content="x = 1",
                            stage=True):
        """Source that never fired a PostToolUse Edit event - a heredoc, sed,
        or a script.

        git sees it exactly as it sees any other dirty source file; the hooks
        never saw it being written, so nothing records who authored it. This
        is the fixture for every narrowing row (self = no) and for the
        OQ-HP-05 characterization.
        """
        self.write(rel, content)
        if stage:
            git(self.root, "add", rel)
        return rel

    def trusted_ledger(self):
        """A ledger the HOOK wrote: valid checksum, open generation, and a
        self_authored record that does NOT intersect the dirty tree.

        `trusted` has to mean something other than `absent` for the narrowing
        rows - an absent ledger is its own row (20) and is deliberately not
        untrusted. A real Mode A event is the only thing that writes a
        self_authored record, so this drives one and then removes the file
        again: the record stays, the path leaves the dirty set.

        Call it AFTER the task entries are set - Mode A keys the ledger on
        the entries in flight, and prune_tasks writes a record per active key.
        """
        rel = "src/seeded.py"
        path = self.write(rel, "seeded = 1")
        r = run_hook(HOOK, self.postedit_payload(rel), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        os.remove(path)
        recorded = [e.get("path")
                    for e in self.read_ledger_raw()["self_authored"]]
        self.assertIn(rel, recorded)
        return rel

    def tamper_checksum(self):
        """Break the ledger's seal by hand: history that cannot be verified.

        Hand-editing is the point - the checksum exists to detect exactly
        this, so the fixture has to do the thing the seal guards against.
        """
        data = self.read_ledger_raw()
        data["checksum"] = "deadbeef"
        with open(self.ledger_file(), "w") as f:
            json.dump(data, f)

    def make_worktree(self, rel=".claude/worktrees/wt", branch="wt"):
        """A REAL linked worktree. The exemption is derived from a .git entry
        now, not from the path spelling, so a bare directory is not a checkout
        and must not be treated as one."""
        path = os.path.join(self.root, rel)
        r = git(self.root, "worktree", "add", "-b", branch, path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(path, ".git")), path)
        return path

    def init_git_with_main(self):
        """init_git, then force the initial branch to `main` and leave HEAD on
        a task branch, so risk_score has a base to diff against."""
        self.init_git()
        r = git(self.root, "branch", "-M", "main")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = git(self.root, "checkout", "-b", "task/x")
        self.assertEqual(r.returncode, 0, r.stderr)

    def commit_high_band(self):
        """Commit a diff risk_score bands HIGH, using only its EXISTING
        signals: 1000 changed lines, a .claude/hooks/ path, zero test lines
        over that change, and two paths outside the brief's ownership.

        No point value is restated here. The band this actually produces is
        asserted against risk_score itself in the guard test below, because a
        helper that quietly slid into `medium` would leave the whole risk half
        of the decision table testing nothing.
        """
        self.write("company/briefs/b.md",
                   "# brief\n\n## You own\n\n- `nothing/`\n")
        self.write(".claude/hooks/big1.py",
                   "".join("v{} = {}\n".format(i, i) for i in range(900)))
        self.write(".claude/hooks/big2.py",
                   "".join("w{} = {}\n".format(i, i) for i in range(100)))
        git(self.root, "add", ".claude/hooks/big1.py",
            ".claude/hooks/big2.py")
        r = git(self.root, "commit", "-m", "big")
        self.assertEqual(r.returncode, 0, r.stderr)

    def commit_medium_band(self):
        """Commit a diff risk_score bands MEDIUM - proves only `high` arms.

        Same size and test-thinness as the high fixture, but every changed
        path is owned and none is sensitive, so the two signals that carry it
        over the high threshold are the ones that drop out.
        """
        self.write("company/briefs/b.md",
                   "# brief\n\n## You own\n\n- `src/`\n")
        self.write("src/big.py",
                   "".join("v{} = {}\n".format(i, i) for i in range(900)))
        git(self.root, "add", "src/big.py")
        r = git(self.root, "commit", "-m", "big")
        self.assertEqual(r.returncode, 0, r.stderr)

    def risk_json(self):
        """risk_score's OWN verdict on this fixture, from its frozen
        RISK_JSON line. Never inspects or restates its internal points."""
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = self.root
        out = subprocess.run(
            [sys.executable, hook_path("risk_score.py"), "--json"],
            capture_output=True, text=True, env=env, cwd=self.root,
        )
        lines = [ln for ln in out.stdout.splitlines()
                 if ln.startswith("RISK_JSON: ")]
        self.assertTrue(lines, out.stdout + out.stderr)
        return json.loads(lines[-1][len("RISK_JSON: "):])

    def assert_ledger_intact(self):
        """The on-disk ledger still recomputes its own checksum and reads back
        trusted. Without this a run that corrupted the file would sail past
        every count assertion the race tests make.
        """
        raw = self.read_ledger_raw()
        self.assertEqual(
            raw.get("checksum"),
            _common.stamp_checksum(
                {k: v for k, v in raw.items() if k != "checksum"}
            ),
            "the ledger no longer verifies against its own checksum",
        )
        self.assertFalse(gp.read_ledger(self.root).get("_untrusted"),
                         "read_ledger had to discard the ledger")

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
        self.init_git()
        self.set_manifest()
        self.feature_task()  # undecided would block in the main checkout
        self.make_worktree()
        r = run_hook(
            HOOK,
            self.edit_payload("Write", ".claude/worktrees/wt/src/app.py", "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_worktree_cwd_allows(self):
        # A subagent editing inside its own worktree: file_path is under the
        # worktree checkout and the payload cwd is that worktree.
        self.init_git()
        self.set_manifest()
        self.feature_task()
        wt = self.make_worktree()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": os.path.join(wt, "src/app.py"),
                                  "content": "x"},
                   "cwd": wt}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_worktree_outside_the_conventional_path_is_exempt(self):
        """The exemption is DERIVED from a .git entry, so a checkout that
        happens to live nowhere near .claude/worktrees/ is still a checkout.

        The literal string match this replaces gated every such worktree as
        main-checkout work - `git worktree add` accepts any path, and a lead
        who put one at build/elsewhere got blocked for delegating correctly.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task()  # undecided: this blocks in the main checkout
        wt = self.make_worktree("build/elsewhere/wt2", "wt2")
        r = run_hook(
            HOOK,
            self.edit_payload("Write", os.path.join(wt, "src/app.py"), "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # Control: the same edit in the main checkout DOES block, so the allow
        # above is the worktree exemption and not an inert fixture.
        main = run_hook(HOOK,
                        self.edit_payload("Write", "src/app.py", "x"),
                        self.root)
        self.assertEqual(main.returncode, 2, main.stderr)

    def test_a_bare_directory_named_like_a_worktree_is_not_one(self):
        """The deliberate tightening: a directory spelled like a worktree with
        no checkout in it is main-checkout work and is gated as such.

        Under the literal string match anyone could exempt an edit by putting
        it under a hand-made .claude/worktrees/<anything>/ directory - no
        branch, no isolation, no verification inside the hierarchy, just a
        path that read as delegated. Deriving the exemption from a real .git
        entry closes that.

        The path here is deliberately the SAME path as
        test_worktree_outside_the_conventional_path_is_exempt, minus the
        `git worktree add`. The two tests differ in exactly one bit - whether
        a `.git` entry exists - which is the whole claim of scope item 8, and
        neither of them mentions `.claude/worktrees` at all.

        `.claude/worktrees/<x>/src/app.py` would be the more literal mirror of
        the old string match, but Mode E cannot see it either way:
        guard_spec.is_source anchors EXEMPT_DIRS at segment zero (FR-HP-13),
        and segment zero there is `.claude`, so the gate exits as "not source"
        before the execution decision is read. That path is pinned at Mode C
        instead, where the cwd reaches a verdict, by TestCommitGate
        .test_a_bare_worktree_directory_as_cwd_does_not_exempt_a_commit.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task()  # undecided: blocks in the main checkout
        bare = os.path.join(self.root, "build", "elsewhere", "wt2")
        os.makedirs(bare)
        self.assertFalse(os.path.exists(os.path.join(bare, ".git")))
        r = run_hook(
            HOOK,
            self.edit_payload("Write", os.path.join(bare, "src/app.py"), "x"),
            self.root,
        )
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("execution", r.stderr)

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
        #
        # It also goes through the real Mode A event (see stage_source), so
        # the ledger records it self-authored and it ARMS the demand under
        # FR-HP-44. A file written straight to disk arms nothing, which is the
        # accepted OQ-HP-05 hole and has its own test.
        return self.stage_source(rel, content, stage=stage)

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
        wt = self.make_worktree()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m wip"}, "cwd": wt}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_bare_worktree_directory_as_cwd_does_not_exempt_a_commit(self):
        """The same tightening TestExecutionGate pins at Mode E, pinned here
        at Mode C, where the old literal match was load bearing: a cwd
        spelled `.claude/worktrees/<x>` with no checkout in it used to exempt
        the commit outright while the tree it commits is the MAIN checkout.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.dirty_source()
        bare = os.path.join(self.root, ".claude", "worktrees", "wt")
        os.makedirs(bare, exist_ok=True)
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m wip"},
                   "cwd": bare}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("Self-authored paths:", r.stderr)

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
        wt = self.make_worktree(".claude/worktrees/x", "x")
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
        self.init_git()
        self.set_manifest()
        self.self_task()
        self.make_worktree()
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
        # brand-new directory, never `git add`ed, and authored through the
        # real Mode A event so FR-HP-44 arms on it
        self.stage_source(self.NEWSRC, "x = 1", stage=False)
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
        self.stage_source(self.NEWSRC, "x = 1", stage=False)
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


# --------------------------------------------------------------------------
# FR-HP-44/45 - what ARMS the audit demand, as a decision table.
#
# The demand used to be armed by EVERY dirty source path in the tree, which is
# why an umbrella checkout with 71 dirty paths and nothing authored by the
# company blocked every commit. It is now armed by three things, any one
# sufficient:
#
#   A1. a dirty path the ledger RECORDS as self-authored
#   A2. a ledger whose authorship history cannot be trusted (then every dirty
#       path arms it - fail closed)
#   A3. a diff risk_score bands high
#
# and satisfied, as before, by a fresh audit at the current work_hash.
#
# The gate order the rows below are read against:
#
#   dp = dirty source paths
#   if not dp                    -> ALLOW
#   if fresh audit               -> ALLOW
#   if ledger untrusted          -> BLOCK "untrusted"
#   armed = dp INTERSECT self_authored
#   if armed                     -> BLOCK "self-authored"
#   band = risk_band()             (computed ONLY here)
#   if band == "high"            -> BLOCK "risk"
#   if delegated_with_dispatches -> ALLOW + logged BYPASS
#                                -> ALLOW (silent)
#
# One fixture method per row, shared by the Mode C and the Mode D class, so
# both gates are judged against the SAME tree. Each mode then asserts the
# verdict AND which of the three blocks it was: an exit code alone would let
# a gate block for the wrong reason and still read green.
# --------------------------------------------------------------------------
class DecisionTable(ProvBase):
    SELF = {"execution": "self", "execution_why": "glue only"}
    DELEGATED = {"execution": "delegated", "execution_why": "lead owns"}

    def entry(self, slug, **extra):
        obj = {"task": slug, "type": "feature",
               "brief": "company/briefs/b.md"}
        obj.update(extra)
        return obj

    def mixed_entries(self):
        """One self entry and one delegated entry with a dispatch of its own.

        `mixed` in the table means the gated entries do NOT agree on how they
        execute, which is precisely what stops delegated_with_dispatches from
        applying: one entry's delegation cannot vouch for another entry's
        self-authored work.
        """
        self.set_tasks(self.entry("feat-a", **self.SELF),
                       self.entry("feat-b", **self.DELEGATED))
        self.seed_dispatch("tech-lead", slug="feat-b")

    # --- the rows ---------------------------------------------------------

    def fixture_1(self):
        """No dirty source at all."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)

    def fixture_2(self):
        """Self-authored dirty source, covered by a fresh audit."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.stage_source()
        self.seed_audit()

    def fixture_3(self):
        """Self-authored dirty source, no audit."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.stage_source()

    def fixture_4(self):
        """Delegated with a dispatch, but the dirty path is self-authored."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.seed_dispatch("tech-lead")
        self.stage_source()

    def fixture_5(self):
        """Delegated with NO dispatch, dirty path self-authored."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.stage_source()

    def fixture_6(self):
        """Mixed entries, a dispatch, dirty path self-authored."""
        self.init_git()
        self.set_manifest()
        self.mixed_entries()
        self.stage_source()

    def fixture_7(self):
        """Bash-written dirty source, trusted ledger, low band."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_8(self):
        """Bash-written dirty source, trusted ledger, MEDIUM band."""
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.commit_medium_band()
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_9(self):
        """Bash-written dirty source, trusted ledger, HIGH band."""
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.commit_high_band()
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_10(self):
        """Delegated with a dispatch, nothing self-authored, low band."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.seed_dispatch("tech-lead")
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_11(self):
        """Delegated with a dispatch, nothing self-authored, HIGH band."""
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.commit_high_band()
        self.seed_dispatch("tech-lead")
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_12(self):
        """Delegated with NO dispatch, nothing self-authored, low band."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_13(self):
        """Delegated with NO dispatch, nothing self-authored, HIGH band."""
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.commit_high_band()
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_14(self):
        """No execution decision at all, nothing self-authored, low band."""
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_15(self):
        """No execution decision at all, nothing self-authored, HIGH band."""
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task()
        self.commit_high_band()
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_16(self):
        """Mixed entries with a dispatch, nothing self-authored, low band."""
        self.init_git()
        self.set_manifest()
        self.mixed_entries()
        self.trusted_ledger()
        self.bash_written_source()

    def fixture_17(self):
        """Self-authored dirty source AND a fresh audit, delegated entry."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.DELEGATED)
        self.seed_dispatch("tech-lead")
        self.stage_source()
        self.seed_audit()

    def fixture_18(self):
        """Bash-written dirty source, ledger seal broken, no audit."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.trusted_ledger()
        self.tamper_checksum()
        self.bash_written_source()

    def fixture_19(self):
        """Ledger seal broken, then a REAL audit recorded over the reset.

        Order is the whole fixture. A reset destroys the audits along with the
        self_authored record, so an audit seeded BEFORE the tamper would be
        gone by the time the gate reads the ledger and this row would be
        row 18 wearing a different name. Driving Mode B-post AFTER the tamper
        writes a fresh, valid ledger whose one audit covers this tree - which
        is what the row asserts an untrusted ledger can still be rescued by.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.trusted_ledger()
        self.tamper_checksum()
        self.bash_written_source()
        self.seed_audit()

    def fixture_20(self):
        """No ledger on disk at all, bash-written dirty source, low band."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.bash_written_source()
        self.assertFalse(os.path.exists(self.ledger_file()))

    def fixture_21(self):
        """No ledger on disk at all, bash-written dirty source, HIGH band."""
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.commit_high_band()
        self.bash_written_source()
        self.assertFalse(os.path.exists(self.ledger_file()))


class TestRiskBandFixtures(DecisionTable):
    """The band a fixture builds is asserted against risk_score itself.

    If commit_high_band quietly stopped banding high, every `BLOCK risk` row
    below would pass for the wrong reason and every `ALLOW` row it neighbours
    would prove nothing. These three tests are what stop that, and they are
    the ONLY place in this file that talks to risk_score - no test restates
    its internal point values.
    """

    def test_the_plain_fixture_bands_low(self):
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.assertEqual(self.risk_json()["band"], "low")

    def test_commit_medium_band_really_bands_medium(self):
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.commit_medium_band()
        self.trusted_ledger()
        self.assertEqual(self.risk_json()["band"], "medium")

    def test_commit_high_band_really_bands_high(self):
        self.init_git_with_main()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.commit_high_band()
        # Both compositions the table uses: rows 9/11/13/15 seed a trusted
        # ledger on top of this and rows 20/21 do not, so both are pinned.
        self.assertEqual(self.risk_json()["band"], "high")
        self.trusted_ledger()
        self.assertEqual(self.risk_json()["band"], "high")


class TestModeCDecisionTable(DecisionTable):
    """FR-HP-44/45 at the commit gate. One test per row."""

    # The distinguishing substring of each of the three blocks. Asserting the
    # one that fired AND the absence of the other two is the difference
    # between "it blocked" and "it blocked for the stated reason".
    REASONS = {
        "self": "Self-authored paths:",
        "untrusted": "no verifiable record",
        "risk": "bands HIGH",
    }

    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def assert_allows(self):
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def assert_blocks(self, which):
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(self.REASONS[which], r.stderr)
        for name, needle in self.REASONS.items():
            if name != which:
                self.assertNotIn(needle, r.stderr)
        return r

    def assert_no_delegation_bypass(self):
        self.assertNotIn("delegated execution with recorded dispatches",
                         self.adherence())

    def test_row_01_no_dirty_source_allows(self):
        """ALLOW: nothing to verify. Not a hole - an audit of an unchanged
        tree would assert nothing about anything."""
        self.fixture_1()
        self.assert_allows()

    def test_row_02_self_authored_with_fresh_audit_allows(self):
        """ALLOW: the audit is the thing the demand asks for, and it covers
        this exact work_hash. Not a hole - it is the gate being satisfied."""
        self.fixture_2()
        self.assert_allows()

    def test_row_03_self_authored_no_audit_blocks(self):
        """BLOCK self-authored: the CEO wrote it in the main checkout and no
        independent context has looked at it."""
        self.fixture_3()
        self.assert_blocks("self")

    def test_row_04_delegated_with_dispatch_but_self_authored_blocks(self):
        """BLOCK self-authored: a dispatch does not retroactively make work
        that the CEO typed into the main checkout delegated. The self-authored
        check runs BEFORE the delegated route for exactly this."""
        self.fixture_4()
        self.assert_blocks("self")

    def test_row_05_delegated_no_dispatch_and_self_authored_blocks(self):
        """BLOCK self-authored: the record says delegated, the ledger says the
        CEO wrote it, and nobody was dispatched. Every reading blocks."""
        self.fixture_5()
        self.assert_blocks("self")

    def test_row_06_mixed_entries_with_self_authored_path_blocks(self):
        """BLOCK self-authored: one delegated entry with a dispatch beside a
        self entry cannot vouch for the tree they share."""
        self.fixture_6()
        self.assert_blocks("self")

    def test_row_07_bash_written_low_band_allows(self):
        """ALLOW, the narrowing itself: the ledger is trusted and records
        nothing about this path, so the company did not author it. Not a hole
        - the risk band is what covers foreign source that matters, and this
        diff is low. OQ-HP-05, accepted."""
        self.fixture_7()
        self.assert_allows()

    def test_row_08_bash_written_medium_band_allows(self):
        """ALLOW: only `high` arms. Not a hole - medium is the band that asks
        for extra spot-reads, and turning it into a block would put the gate
        back where it started, blocking on the shape of the tree."""
        self.fixture_8()
        self.assert_allows()

    def test_row_09_bash_written_high_band_blocks(self):
        """BLOCK risk: nothing is recorded self-authored, but the diff is big,
        untested, sensitive and out of ownership. A3 is the backstop that
        stops the narrowing from being a free pass."""
        self.fixture_9()
        self.assert_blocks("risk")

    def test_row_10_delegated_with_dispatch_low_band_allows(self):
        """ALLOW with a logged BYPASS: every gated entry is delegated, each
        has a recorded dispatch, and no dirty path is recorded self-authored.
        Not a hole - the work was verified inside the hierarchy, and the
        bypass is written down rather than silent."""
        self.fixture_10()
        self.assert_allows()
        self.assertIn("delegated execution with recorded dispatches",
                      self.adherence())

    def test_row_11_delegated_with_dispatch_high_band_blocks(self):
        """BLOCK risk: the band is computed BEFORE the delegated route, so a
        recorded dispatch cannot wave a high-risk diff through."""
        self.fixture_11()
        self.assert_blocks("risk")

    def test_row_12_delegated_no_dispatch_low_band_allows(self):
        """ALLOW silently, through the path-shaped narrowing and NOT through
        the entry-shaped delegated route - there is no dispatch to route on.
        The absent BYPASS line is what proves the two are distinct paths."""
        self.fixture_12()
        self.assert_allows()
        self.assert_no_delegation_bypass()

    def test_row_13_delegated_no_dispatch_high_band_blocks(self):
        """BLOCK risk: no dispatch, nothing self-authored, high band."""
        self.fixture_13()
        self.assert_blocks("risk")

    def test_row_14_undecided_low_band_allows(self):
        """ALLOW: Mode C does not police execution decisions - Mode E does,
        at the edit. Not a hole; it is the other gate's job."""
        self.fixture_14()
        self.assert_allows()

    def test_row_15_undecided_high_band_blocks(self):
        """BLOCK risk: an undecided entry gets no dispensation from A3."""
        self.fixture_15()
        self.assert_blocks("risk")

    def test_row_16_mixed_entries_low_band_allows(self):
        """ALLOW silently, through the narrowing. The delegated route needs
        EVERY gated entry delegated, and one of these is self, so the absent
        BYPASS line is the proof of which path allowed it."""
        self.fixture_16()
        self.assert_allows()
        self.assert_no_delegation_bypass()

    def test_row_17_self_authored_with_audit_allows_whatever_the_entry_says(
            self):
        """ALLOW: a fresh audit satisfies the demand no matter how the entry
        executes. Not a hole - the audit is independent of the entry."""
        self.fixture_17()
        self.assert_allows()

    def test_row_18_untrusted_ledger_blocks(self):
        """BLOCK untrusted: the ledger cannot say who wrote what, so the
        narrowing has no input and every dirty path arms the demand. Failing
        closed here is what stops a tampered ledger from being an unlock."""
        self.fixture_18()
        self.assert_blocks("untrusted")

    def test_row_19_untrusted_ledger_with_fresh_audit_allows(self):
        """ALLOW: a fresh audit is checked before trust, and an audit covering
        this work_hash means an independent context read this exact tree. Not
        a hole - the audit does not depend on the ledger's authorship history
        being intact, only on the tree being the audited one."""
        self.fixture_19()
        self.assert_allows()

    def test_row_20_absent_ledger_low_band_allows(self):
        """ALLOW, and the case the whole narrowing exists for: an ABSENT
        ledger is not an untrusted one - it means nothing was ever authored
        through the hooks. The polyrepo park-note measured this exactly: 71
        dirty umbrella paths, zero of them authored by the company, and every
        commit blocked. Not a hole - nothing here was produced by the context
        asking to integrate it."""
        self.fixture_20()
        self.assert_allows()

    def test_row_21_absent_ledger_high_band_blocks(self):
        """BLOCK risk: an absent ledger allows on its own, but A3 is computed
        from the diff and not from the ledger, so a high-risk tree still
        stops."""
        self.fixture_21()
        self.assert_blocks("risk")

    # --- Mode C only ------------------------------------------------------

    def test_row_22a_commit_from_a_real_nested_checkout_allows(self):
        """ALLOW: the commit lands in another checkout, so this tree's
        provenance is not what it integrates. Not a hole - that checkout's own
        session carries its own gate, and the exemption is derived from a real
        .git entry rather than from how the path is spelled."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.stage_source()
        wt = self.make_worktree()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git commit -m wip"}, "cwd": wt}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_row_22b_git_dash_c_into_a_real_worktree_allows(self):
        """ALLOW: `git -C <worktree> commit` from the main checkout commits
        the WORKTREE's tree, so the main checkout's self-authored dirt is not
        what is being integrated. Not a hole - the control below shows the
        same session, same dirt, without the -C, still blocks."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.stage_source()
        wt = self.make_worktree()
        r = run_hook(HOOK,
                     self.bash_payload("git -C {} commit -m wip".format(wt)),
                     self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        control = self.commit()
        self.assertEqual(control.returncode, 2, control.stderr)
        self.assertIn(self.REASONS["self"], control.stderr)

    def test_row_23_merge_head_allows_and_logs_bypass(self):
        """ALLOW with a logged BYPASS: a merge commit concludes work that was
        already gated on its own branch, and blocking it would strand the
        checkout mid-merge. Not a hole - it is written down."""
        self.init_git()
        self.set_manifest()
        self.feature_task(**self.SELF)
        self.stage_source()
        self.write(".git/MERGE_HEAD", "deadbeef\n")
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("merge conclusion", self.adherence())

    def test_row_24_any_hotfix_entry_allows_and_logs_bypass(self):
        """ALLOW with a logged BYPASS: RISK-MST-01, accepted. One commit
        writes one tree, so holding a declared production emergency behind an
        unrelated entry is the worse failure. Not a hole - the waiver is
        declared in advance, logged, and named."""
        self.init_git()
        self.set_manifest()
        self.set_tasks(self.entry("feat-a", **self.SELF),
                       {"task": "hf", "type": "hotfix"})
        self.stage_source()
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BYPASS", self.adherence())


class TestModeDDecisionTable(DecisionTable):
    """FR-HP-44/45 at the close gate. The SAME fixtures as Mode C.

    Mode D never blocks the process; it prints a Stop block decision. An ALLOW
    is therefore an EMPTY stdout, which every allow row asserts - a decision
    printed for the wrong row would otherwise be invisible.
    """

    REASONS = {
        "self": "Self-authored dirty paths",
        "untrusted": "no verifiable record of who authored",
        "risk": "bands this diff high",
    }

    def stop(self):
        return run_hook(HOOK, self.stop_payload(), self.root)

    def assert_allows(self):
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        return r

    def assert_blocks(self, which, slugs=("feat-x",)):
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        decision = json.loads(r.stdout)
        self.assertEqual(decision["decision"], "block")
        reason = decision["reason"]
        self.assertIn(self.REASONS[which], reason)
        for name, needle in self.REASONS.items():
            if name != which:
                self.assertNotIn(needle, reason)
        # Every one of the three reasons names the entry it is about and the
        # role that clears it; a block the reader cannot act on is noise.
        for slug in slugs:
            self.assertIn(slug, reason)
        self.assertIn("auditor", reason)
        return r

    def assert_no_delegation_bypass(self):
        self.assertNotIn("delegated execution with recorded dispatches",
                         self.adherence())

    def test_row_01_no_dirty_source_allows(self):
        """ALLOW: nothing to verify at close either."""
        self.fixture_1()
        self.assert_allows()

    def test_row_02_self_authored_with_fresh_audit_allows(self):
        """ALLOW: the audit covers this work_hash."""
        self.fixture_2()
        self.assert_allows()

    def test_row_03_self_authored_no_audit_blocks(self):
        """BLOCK self-authored: closing the task would leave unverified
        main-checkout work behind."""
        self.fixture_3()
        self.assert_blocks("self")

    def test_row_04_delegated_with_dispatch_but_self_authored_blocks(self):
        """BLOCK self-authored: same rule as Mode C, same order."""
        self.fixture_4()
        self.assert_blocks("self")

    def test_row_05_delegated_no_dispatch_and_self_authored_blocks(self):
        """BLOCK self-authored."""
        self.fixture_5()
        self.assert_blocks("self")

    def test_row_06_mixed_entries_with_self_authored_path_blocks(self):
        """BLOCK self-authored, naming both gated entries."""
        self.fixture_6()
        self.assert_blocks("self", slugs=("feat-a", "feat-b"))

    def test_row_07_bash_written_low_band_allows(self):
        """ALLOW, the narrowing: the trusted ledger records nothing about this
        path. Not a hole - OQ-HP-05, accepted, and the band covers the
        high-risk subset."""
        self.fixture_7()
        self.assert_allows()

    def test_row_08_bash_written_medium_band_allows(self):
        """ALLOW: only `high` arms."""
        self.fixture_8()
        self.assert_allows()

    def test_row_09_bash_written_high_band_blocks(self):
        """BLOCK risk."""
        self.fixture_9()
        self.assert_blocks("risk")

    def test_row_10_delegated_with_dispatch_low_band_allows(self):
        """ALLOW with a logged BYPASS: delegated work is verified inside the
        hierarchy. Not a hole - the bypass is recorded."""
        self.fixture_10()
        self.assert_allows()
        self.assertIn("delegated execution with recorded dispatches",
                      self.adherence())

    def test_row_11_delegated_with_dispatch_high_band_blocks(self):
        """BLOCK risk: the band is computed before the delegated route."""
        self.fixture_11()
        self.assert_blocks("risk")

    def test_row_12_delegated_no_dispatch_low_band_allows(self):
        """ALLOW silently through the narrowing, not through the delegated
        route - the absent BYPASS line proves which."""
        self.fixture_12()
        self.assert_allows()
        self.assert_no_delegation_bypass()

    def test_row_13_delegated_no_dispatch_high_band_blocks(self):
        """BLOCK risk."""
        self.fixture_13()
        self.assert_blocks("risk")

    def test_row_14_undecided_low_band_allows(self):
        """ALLOW: the execution decision is Mode E's gate, not this one."""
        self.fixture_14()
        self.assert_allows()

    def test_row_15_undecided_high_band_blocks(self):
        """BLOCK risk."""
        self.fixture_15()
        self.assert_blocks("risk")

    def test_row_16_mixed_entries_low_band_allows(self):
        """ALLOW silently through the narrowing; the delegated route needs
        every gated entry delegated."""
        self.fixture_16()
        self.assert_allows()
        self.assert_no_delegation_bypass()

    def test_row_17_self_authored_with_audit_allows_whatever_the_entry_says(
            self):
        """ALLOW: a fresh audit satisfies the demand however the entry
        executes."""
        self.fixture_17()
        self.assert_allows()

    def test_row_18_untrusted_ledger_blocks(self):
        """BLOCK untrusted: fail closed while authorship is unverifiable."""
        self.fixture_18()
        self.assert_blocks("untrusted")

    def test_row_19_untrusted_ledger_with_fresh_audit_allows(self):
        """ALLOW: the audit is checked before trust and covers this tree."""
        self.fixture_19()
        self.assert_allows()

    def test_row_20_absent_ledger_low_band_allows(self):
        """ALLOW: an absent ledger means nothing was authored through the
        hooks. The polyrepo park-note case - 71 dirty umbrella paths, zero
        authored by the company - and not a hole for that reason."""
        self.fixture_20()
        self.assert_allows()

    def test_row_21_absent_ledger_high_band_blocks(self):
        """BLOCK risk: A3 is computed from the diff, not from the ledger."""
        self.fixture_21()
        self.assert_blocks("risk")

    # --- Mode D only ------------------------------------------------------

    def test_row_25_all_entries_quick_or_hotfix_allows_silently(self):
        """ALLOW, silent: quick and hotfix are exemption TYPES and FR-MST-23
        makes exemptions PER ENTRY, so a tree carrying nothing but exempt
        entries has no gated entry to block for. Not a hole - the moment a
        feature entry joins them the gate evaluates it (that is the
        [quick, feature] case covered in the multi-task suite)."""
        self.init_git()
        self.set_manifest()
        self.set_tasks({"task": "q", "type": "quick"},
                       {"task": "hf", "type": "hotfix"})
        self.stage_source()
        self.assert_allows()


# --------------------------------------------------------------------------
# FR-HP-40/41/42 - every ledger read-modify-write is serialized.
#
# The children here are hook SUBPROCESSES, and threads would prove nothing
# about an flock, which is held per open file description. Each child is a
# real process that prints READY once its interpreter is up, blocks on a line
# from the parent, and only then runs the hook - so the parent releases all six
# at an instant when the expensive, load-sensitive part (interpreter startup)
# is already done for every one of them. That is arranging contention rather
# than hoping for it.
#
# Each test also carries the negative control the kernel suite uses: a run that
# silently corrupted the ledger while producing the right counts must not pass,
# so the ledger has to still verify against its own checksum at the end.
# --------------------------------------------------------------------------
RACE_CHILD = '''
import json, os, subprocess, sys
hook, root, payload = sys.argv[1], sys.argv[2], sys.argv[3]
sys.stdout.write("READY\\n")
sys.stdout.flush()
sys.stdin.readline()
env = os.environ.copy()
env["CLAUDE_PROJECT_DIR"] = root
done = subprocess.run([sys.executable, hook], input=payload,
                      capture_output=True, text=True, env=env)
print(json.dumps({"rc": done.returncode, "err": done.stderr[-400:]}))
'''


class TestLedgerRaces(ProvBase):
    N = 6  # the cap: these are subprocess-heavy and six already contends

    def child_script(self):
        # company/state is excluded from the dirty-path scan, so the harness
        # script cannot become a dirty source path and change what it measures.
        return self.write("company/state/race_child.py", RACE_CHILD)

    def race(self, payloads):
        script = self.child_script()
        procs = [
            subprocess.Popen(
                [sys.executable, script, hook_path(HOOK), self.root,
                 json.dumps(p)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            for p in payloads
        ]
        for proc in procs:
            self.assertEqual(proc.stdout.readline().strip(), "READY")
        for proc in procs:
            proc.stdin.write("go\n")
            proc.stdin.flush()
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err)
            result = json.loads(out.strip())
            self.assertEqual(result["rc"], 0, result["err"])

    def test_mode_a_concurrent_edits_record_every_path(self):
        """FR-HP-40: six PostToolUse Write events, six different paths, one
        ledger. Unlocked, the read-modify-write cycles interleave and the
        losers' paths never reach disk, so a missing path here is a lost
        update and not a flaky assertion.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task()
        paths = ["src/mod{}.py".format(i) for i in range(self.N)]
        self.race([self.postedit_payload(p) for p in paths])
        recorded = {e.get("path")
                    for e in self.read_ledger_raw()["self_authored"]}
        for path in paths:
            self.assertIn(path, recorded)
        self.assert_ledger_intact()

    def test_mode_b_pre_concurrent_dispatches_all_land(self):
        """FR-HP-41: six builder spawns naming the same slug append to the
        same per-slug list. Exactly six, not at least six - a duplicate would
        mean the record was written twice from one read."""
        self.init_git()
        self.set_manifest()
        self.feature_task(slug="feat-x")
        self.race([self.dispatch_payload("developer", "feat-x")
                   for _ in range(self.N)])
        self.assertEqual(len(self.record("feat-x")["dispatches"]), self.N)
        self.assert_ledger_intact()

    def test_mode_b_post_concurrent_audits_all_land(self):
        """FR-HP-42: six verifier completions, six audit records."""
        self.init_git()
        self.set_manifest()
        self.feature_task(slug="feat-x")
        self.race([self.audit_payload() for _ in range(self.N)])
        self.assertEqual(len(self.read_ledger_raw()["audits"]), self.N)
        self.assert_ledger_intact()


# --------------------------------------------------------------------------
# FR-HP-43 - a dispatch fired while the task file cannot be read.
#
# An unreadable active-task.json is not an absent one. Reading [] from a torn
# or corrupt file silently drops the dispatch credit, and the delegated entry
# it belonged to then looks like it never dispatched. Recording the dispatch as
# UNATTRIBUTED keeps the fact and makes the gap diagnosable.
# --------------------------------------------------------------------------
class TestUnattributedDispatch(ProvBase):
    def dispatch_log_lines(self):
        return [ln for ln in self.adherence().splitlines() if "DISPATCH" in ln]

    def unattributed(self):
        if not os.path.exists(self.ledger_file()):
            return []
        return self.read_ledger_raw().get("unattributed_dispatches") or []

    def test_unreadable_task_file_records_an_unattributed_dispatch(self):
        self.init_git()
        self.set_manifest()
        self.write("company/state/active-task.json", "{not json at all")
        r = run_hook(HOOK, self.dispatch_payload("developer"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        recorded = self.unattributed()
        self.assertEqual(len(recorded), 1, recorded)
        self.assertEqual(recorded[0].get("role"), "developer")
        lines = self.dispatch_log_lines()
        self.assertTrue(
            any("no readable task entries" in ln for ln in lines), lines
        )

    def test_absent_task_file_records_nothing(self):
        """Absence of a task is not an unreadable task. Nothing is in flight,
        so there is no attribution to have lost and nothing to record."""
        self.init_git()
        self.set_manifest()
        self.assertFalse(
            os.path.exists(os.path.join(self.root, "company", "state",
                                        "active-task.json")))
        r = run_hook(HOOK, self.dispatch_payload("developer"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.unattributed(), [])

    def test_task_file_with_zero_entries_records_nothing(self):
        """A file that parses to an empty list is readable and says, exactly,
        that nothing is in flight. Same reason as the absent case."""
        self.init_git()
        self.set_manifest()
        self.write("company/state/active-task.json",
                   json.dumps({"version": 2, "tasks": []}))
        r = run_hook(HOOK, self.dispatch_payload("developer"), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.unattributed(), [])


# --------------------------------------------------------------------------
# FR-HP-46 - the accepted hole, characterized rather than wished away.
# --------------------------------------------------------------------------
class TestAcceptedHole(ProvBase):
    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def test_bash_written_source_never_arms_the_demand(self):
        """OQ-HP-05 assumption, ACCEPTED HOLE - characterization, not a wish.

        Source written through Bash - a heredoc, sed, a script - never fires
        the PostToolUse Edit event, so guard_provenance never records it in
        self_authored and it therefore stops arming the audit demand. This
        test ASSERTS that allow so the limitation is a known, named, tested
        property rather than a surprise. It is recorded in ADR-0003. If this
        test ever starts failing, the hole closed and the ADR needs
        superseding.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task(execution="self", execution_why="glue only")
        self.trusted_ledger()
        rel = self.bash_written_source()

        self.assertEqual(self.commit().returncode, 0)
        stop = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertEqual(stop.stdout.strip(), "")

        # The same tree, the same path, the same band - the ONLY thing that
        # changes is that the hook now saw the write. Both gates block. That
        # is what makes the allow above a measurement of the hole and not of a
        # fixture that could never have blocked.
        r = run_hook(HOOK, self.postedit_payload(rel), self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        blocked = self.commit()
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertIn("Self-authored paths:", blocked.stderr)
        stop = run_hook(HOOK, self.stop_payload(), self.root)
        self.assertEqual(json.loads(stop.stdout)["decision"], "block")


# --------------------------------------------------------------------------
# FR-HP-44 - the three trust states of the ledger, at the commit gate.
#
# UNTRUSTED means read_ledger had to DISCARD history: the file exists and does
# not parse, its checksum does not recompute, or its task generation closed.
# ABSENT is not untrusted - it means nothing was ever authored through the
# hooks, which is the ordinary state of a checkout the company did not build.
# --------------------------------------------------------------------------
class TestLedgerTrustStates(ProvBase):
    def commit(self):
        return run_hook(HOOK, self.bash_payload("git commit -m wip"),
                        self.root)

    def test_tampered_checksum_blocks_even_bash_written_source(self):
        """The seal is broken, so the narrowing has no trustworthy input and
        EVERY dirty path arms the demand again. Fail closed: a ledger that can
        be edited into saying nothing was self-authored would otherwise be the
        cheapest unlock in the system.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task(execution="self", execution_why="glue only")
        self.trusted_ledger()
        self.tamper_checksum()
        self.bash_written_source()
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("no verifiable record", r.stderr)

    def test_slug_turnover_blocks_even_bash_written_source(self):
        """A closed generation is discarded history too. The ledger belonged
        to work that has finished, so it says nothing about who authored this
        tree, and the same fail-closed rule applies.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task(slug="feat-a", execution="self",
                          execution_why="glue only")
        self.trusted_ledger()
        self.feature_task(slug="feat-b", execution="self",
                          execution_why="glue only")
        self.bash_written_source()
        r = self.commit()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("no verifiable record", r.stderr)

    def test_absent_ledger_allows_bash_written_source(self):
        """The case the whole narrowing exists for.

        The polyrepo park-note measured it: an umbrella checkout with 71 dirty
        source paths, ZERO of them authored by the company, and every commit
        blocked on a demand no auditor pass could honestly satisfy. An absent
        ledger is not discarded history - nothing was ever recorded because
        nothing was ever authored through the hooks - so it allows, and A3
        keeps the high-risk subset covered.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task(execution="self", execution_why="glue only")
        self.bash_written_source()
        self.assertFalse(os.path.exists(self.ledger_file()))
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_tampered_checksum_with_a_fresh_audit_allows(self):
        """A fresh audit is checked BEFORE trust, so it rescues a reset
        ledger - but only an audit recorded AFTER the tamper, because the
        reset destroys the audits along with everything else. Seeding it
        through a real Mode B-post event is what puts it in the rewritten
        ledger; a hand-written one would be testing the fixture.
        """
        self.init_git()
        self.set_manifest()
        self.feature_task(execution="self", execution_why="glue only")
        self.trusted_ledger()
        self.tamper_checksum()
        self.bash_written_source()
        self.seed_audit()
        self.assertEqual(len(self.read_ledger_raw()["audits"]), 1)
        r = self.commit()
        self.assertEqual(r.returncode, 0, r.stderr)


# --------------------------------------------------------------------------
# The seeding itself, asserted once. Every Mode C / Mode D fixture above
# depends on stage_source really recording authorship; if it stopped, the
# whole self-authored half of the table would go green by allowing.
# --------------------------------------------------------------------------
class TestSelfAuthorshipSeeding(ProvBase):
    def test_stage_source_records_the_path_in_the_on_disk_ledger(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.stage_source("src/app.py")
        recorded = [e.get("path")
                    for e in self.read_ledger_raw()["self_authored"]]
        self.assertIn("src/app.py", recorded)

    def test_bash_written_source_records_nothing(self):
        self.init_git()
        self.set_manifest()
        self.feature_task()
        self.bash_written_source("src/app.py")
        self.assertFalse(os.path.exists(self.ledger_file()))


if __name__ == "__main__":
    import unittest
    unittest.main()
