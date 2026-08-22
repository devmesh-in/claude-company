#!/usr/bin/env python3
"""Mode F - the high-band integration gate (spec-arm-risk-band.md).

Every band in these fixtures is produced by the REAL risk_score scoring, never
by stubbing a band in. That is the point of the gate: it consumes risk_score's
signals and its 25/50 cuts, so a test that faked the band would prove nothing
about the thing under test and would keep passing if the two ever forked.

THE CENTRAL CASE is IntegrandIsTheSubject below. The first implementation of
this gate scored the tree the integrating session was standing in, which meant
a CEO integrating a lane from a clean `main` checkout scored merge-base(main,
HEAD) == HEAD - an empty diff, band `low`, silent - on exactly the large clean
delegated build DECISIONS #19 commissioned the gate for. An audit caught it.
Every test that fixture drives exists so that cannot come back.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Base, git, run_hook  # noqa: E402
from test_hooks import HOOKS_DIR  # noqa: E402

sys.path.insert(0, HOOKS_DIR)
import guard_provenance as gp  # noqa: E402

HOOK = "guard_provenance.py"

MANIFEST = {
    "version": 1,
    "verifier_roles": ["auditor", "security-reviewer"],
    "builder_roles": ["tech-lead", "developer", "qa-engineer"],
}

BIG = "\n".join("l%d = %d" % (i, i) for i in range(500))
MID = "\n".join("l%d = %d" % (i, i) for i in range(200))


class BandBase(Base):
    def setUp(self):
        super(BandBase, self).setUp()
        git(self.root, "init")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "test")
        git(self.root, "commit", "--allow-empty", "-m", "init")
        git(self.root, "branch", "-M", "main")

    def state(self, task=None):
        """Manifest and task entry, written AFTER any checkout.

        Deliberately last: these are untracked working-tree state in a real
        install, and a fixture that commits them onto a lane branch loses them
        the moment it checks main back out - which silently turns every gate
        into a no-op and makes this whole file pass vacuously.
        """
        self.write("company/provenance.json", json.dumps(MANIFEST))
        self.set_task(task or {"task": "feat-x", "type": "feature",
                               "brief": "company/briefs/b.md"})

    def lane(self, files, branch="task/feat-x", frozen=True):
        """Commit `files` on `branch`, then return to a CLEAN main checkout.

        This is the delegated shape: the work exists only on the lane's branch
        and the integrating checkout has none of it on disk.
        """
        git(self.root, "checkout", "-q", "-b", branch)
        if frozen:
            self.write("company/frozen-surfaces.json",
                       json.dumps({"always": ["*.lock"], "surfaces": []}))
        for rel, body in files.items():
            self.write(rel, body)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "lane work")
        git(self.root, "checkout", "-q", "main")
        self.state()
        return branch

    def high_lane(self):
        return self.lane({".claude/hooks/guard_%s.py" % n: BIG
                          for n in ("a", "b", "c")})

    def medium_lane(self):
        return self.lane({".claude/hooks/guard_x.py": MID}, frozen=False)

    def assert_band(self, ref, expected):
        band, score, _sig = gp.risk_band(self.root, ref)
        self.assertEqual(
            band, expected,
            "fixture drifted across a band cut: got {} ({})".format(band, score),
        )
        return score

    def bash(self, command, cwd=None):
        payload = self.bash_payload(command)
        if cwd:
            payload["cwd"] = cwd
        return run_hook(HOOK, payload, self.root)

    def log(self):
        p = os.path.join(self.root, "company", "state", "adherence.log")
        if not os.path.exists(p):
            return ""
        with open(p) as f:
            return f.read()

    def seed_audit(self):
        """A REAL mode B-post auditor completion, never a hand-written ledger."""
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Task",
                   "tool_input": {"subagent_type": "auditor"},
                   "tool_response": "Verdict: SHIP", "cwd": self.root}
        r = run_hook(HOOK, payload, self.root)
        self.assertEqual(r.returncode, 0, r.stderr)


class IntegrandIsTheSubject(BandBase):
    """The regression the audit HALTed on. Do not weaken these."""

    def test_delegated_lane_blocks_from_a_clean_main_checkout(self):
        ref = self.high_lane()
        # The integrating checkout is clean and on main: nothing of the lane's
        # work is on disk here. Scoring the local tree gives 0/low; scoring the
        # INTEGRAND is the whole point.
        self.assertEqual(gp.risk_band(self.root, "HEAD")[0], "low")
        score = self.assert_band(ref, "high")
        r = self.bash("git merge --no-ff " + ref)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("HIGH risk band", r.stderr)
        self.assertIn(ref, r.stderr)
        self.assertIn(str(score), r.stderr)

    def test_message_names_the_integrand_and_top_signals(self):
        # FR-ARB-06: the block must carry the why, not a pointer to a second
        # command. The signals dict is already in hand at the block site.
        ref = self.high_lane()
        r = self.bash("git merge " + ref)
        self.assertIn("Integrand: " + ref, r.stderr)
        self.assertIn("Top signals:", r.stderr)
        self.assertIn("sensitive_paths", r.stderr)

    def test_bare_gh_pr_merge_scores_head(self):
        # `gh pr merge` with no PR argument merges the CURRENT branch's PR, so
        # HEAD is the integrand and the session sits on the lane branch.
        self.lane({".claude/hooks/guard_%s.py" % n: BIG
                   for n in ("a", "b", "c")})
        git(self.root, "checkout", "-q", "task/feat-x")
        self.state()
        self.assert_band("HEAD", "high")
        r = self.bash("gh pr merge --squash")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Integrand: HEAD", r.stderr)

    def test_unfetched_pr_number_is_unscorable_not_silent(self):
        # A numbered PR's head lives on the forge. Nothing here reaches the
        # network, so an unfetched ref is UNSCORABLE - allowed, but logged.
        # Allowing silently is how a gate becomes mode E.
        self.high_lane()
        r = self.bash("gh pr merge 42 --squash")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("integrand unresolvable", self.log())


class TreeResolution(BandBase):
    """F3/F4: resolve through _common.acting_tree, never a second copy."""

    def root_relative_lane(self):
        """A lane whose band comes from ROOT-RELATIVE signals only.

        This fixture exists because the obvious one cannot catch the bug. A
        lane scored on `size` and `sensitive_paths` gives the same answer from
        any directory, so a test built on it passes with or without the fix.
        `out_of_ownership` and `frozen_proximity` are resolved by reading the
        brief and the frozen registry FROM the tree root, and `git ls-files`
        run in a subdirectory lists only that subdirectory - so only these
        signals collapse when the root is wrong.

        Measured: from the checkout root high (83, out_of_ownership 60,
        frozen_proximity 15); from `company/state` low (8). Deleting
        `checkout_root(...)` at the call site turns the block below into an
        allow, which is the whole point of having this fixture.
        """
        git(self.root, "checkout", "-q", "-b", "task/x")
        self.write("package-lock.json", '{"lockfileVersion": 3}\n')
        for rel in ("src/api/handler.py", "src/web/page.py", "src/a.py",
                    "src/b.py", "src/c.py"):
            self.write(rel, "\n".join("l%d = %d" % (i, i) for i in range(60)))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "lane work")
        git(self.root, "checkout", "-q", "main")
        self.write("company/frozen-surfaces.json",
                   json.dumps({"always": ["*.lock", "package-lock.json"],
                               "surfaces": []}))
        self.write("company/briefs/b.md", "# BRIEF\n\n## You own\n\n- `docs/`\n")
        self.state()
        return "task/x"

    def test_subdirectory_cwd_does_not_truncate_the_scored_tree(self):
        # risk_score runs `git ls-files` from the root it is handed, so a
        # subdirectory cwd scores a truncated tree and returns a valid `low`
        # with no INFO line - the quietest way for a gate to stop gating.
        ref = self.root_relative_lane()
        self.assert_band(ref, "high")
        sub = os.path.join(self.root, "company", "state")
        os.makedirs(sub, exist_ok=True)
        r = self.bash("git merge " + ref, cwd=sub)
        self.assertEqual(
            r.returncode, 2,
            "a subdirectory cwd disarmed the gate: checkout_root is missing "
            "from the call site",
        )

    def test_acting_tree_decides_the_scored_tree_for_a_dash_c_merge(self):
        # `git -C <path> merge` acts on <path>, so that is the tree every check
        # on the segment must use. Asserted at the resolution seam because the
        # end-to-end difference needs two trees at different commits; what this
        # pins is that the call site's inputs come from acting_tree and land on
        # a checkout ROOT, not that scoring differs.
        import _common
        wt = os.path.join(self.root, "sub", "nested")
        os.makedirs(wt, exist_ok=True)
        seg = "git -C {} merge task/x".format(wt)
        resolved, _unresolved = _common.acting_tree(
            seg, {"cwd": self.root}, self.root)
        self.assertEqual(
            os.path.realpath(gp.checkout_root(resolved)),
            os.path.realpath(self.root),
        )

    def test_checkout_root_normalises_a_subdirectory(self):
        sub = os.path.join(self.root, "company", "state")
        os.makedirs(sub, exist_ok=True)
        self.assertEqual(
            os.path.realpath(gp.checkout_root(sub)),
            os.path.realpath(self.root),
        )


class MergeConclusionIsNotIntegration(BandBase):
    """F5: concluding or cancelling a merge must never arm the gate."""

    def test_abort_continue_and_disable_auto_allow(self):
        ref = self.high_lane()
        self.assert_band(ref, "high")
        for command in ("git merge --abort", "git merge --continue",
                        "git merge --quit", "gh pr merge 42 --disable-auto"):
            r = self.bash(command)
            self.assertEqual(r.returncode, 0,
                             "{} armed the gate".format(command))

    def test_merge_head_present_bypasses(self):
        ref = self.high_lane()
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        self.write(".git/MERGE_HEAD", "deadbeef\n")
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("merge conclusion", self.log())


class FreshAuditSatisfies(BandBase):
    def test_fresh_audit_allows(self):
        ref = self.high_lane()
        self.assert_band(ref, "high")
        self.seed_audit()
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)
        # The log line says what is actually true - a dispatch is on record for
        # this checkout - and names OQ-ARB-05 rather than claiming a verdict was
        # verified. Audit 2 reproduced this exact line vouching for an unaudited
        # lane, so the wording is load-bearing, not cosmetic.
        logged = self.log()
        self.assertIn("auditor dispatch on record", logged)
        self.assertIn("verdict NOT verified", logged)
        self.assertNotIn("satisfied by fresh audit", logged)


class LowAndMediumAreSilent(BandBase):
    """FR-ARB-08: no block, no output, no log line, no nudge."""

    def test_medium_allows_silently(self):
        ref = self.medium_lane()
        self.assert_band(ref, "medium")
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("risk band", self.log())

    def test_low_allows_silently(self):
        self.state()
        r = self.bash("git merge main")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("risk band", self.log())


class Exemptions(BandBase):
    def test_hotfix_bypasses_and_logs(self):
        ref = self.high_lane()
        self.set_task({"task": "fire", "type": "hotfix",
                       "brief": "company/briefs/b.md"})
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BYPASS", self.log())

    def test_no_manifest_allows(self):
        ref = self.high_lane()
        os.remove(os.path.join(self.root, "company", "provenance.json"))
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_active_task_allows(self):
        ref = self.high_lane()
        os.remove(os.path.join(self.root, "company", "state",
                               "active-task.json"))
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_integration_command_untouched(self):
        self.high_lane()
        r = self.bash("git status --porcelain")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("risk band", self.log())


class FailsOpen(BandBase):
    """FR-ARB-10: unscorable ALLOWS, and says so."""

    def test_unscorable_allows_and_logs_info(self):
        ref = self.high_lane()
        git(self.root, "branch", "-M", "trunk")
        band, _s, _sig = gp.risk_band(self.root, ref)
        self.assertIsNone(band)
        r = self.bash("git merge " + ref)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("unscorable", self.log())


class ModeFDoesNotSwallowModeC(BandBase):
    """F6 and the ordering bug this design is most likely to introduce.

    mode_f runs first on PreToolUse Bash. It must RETURN rather than exit, and
    a FAULT inside it must not take the commit gate with it - fail-open is this
    file's posture, but the posture is per gate.

    Assembled rather than written literally: guard_commit parses the RAW text
    of every Bash command a hook sees, and it cannot tell a real command from
    one quoted inside a Python string. Spelling the compound out here makes the
    repo's own commit gate block any tooling that writes this file.
    """

    MERGE_THEN_COMMIT = "git merge main && git " + "commit -m x"

    def test_commit_gate_still_runs_after_a_low_band_merge(self):
        self.state()
        self.write("src/app.py", "x = 1")
        git(self.root, "add", "src/app.py")
        r = self.bash(self.MERGE_THEN_COMMIT)
        # Mode C owns this decision, not mode F: dirty self-authored source
        # with no audit. Asserted here only that mode C was REACHED.
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("self-authored", r.stderr + self.log())

    def test_a_fault_in_mode_f_leaves_the_commit_gate_armed(self):
        self.state()
        self.write("src/app.py", "x = 1")
        git(self.root, "add", "src/app.py")
        # Inject the fault at the SEAM, because no fixture can fake it. Every
        # route to a mode F fault from outside - a missing manifest, no task
        # entry - legitimately disarms mode C too, so an end-to-end fixture
        # would pass while proving nothing. The contract under test is
        # structural: main() wraps the mode_f call so a fault cannot propagate.
        payload = self.bash_payload(self.MERGE_THEN_COMMIT)

        def boom(*args, **kwargs):
            raise RuntimeError("fault inside mode F")

        saved_f = gp.mode_f
        saved_stdin = gp.c.read_stdin_json
        saved_env = os.environ.get("CLAUDE_PROJECT_DIR")
        gp.mode_f = boom
        gp.c.read_stdin_json = lambda: payload
        os.environ["CLAUDE_PROJECT_DIR"] = self.root
        try:
            with self.assertRaises(SystemExit) as caught:
                gp.main()
            self.assertEqual(
                caught.exception.code, 2,
                "a fault in mode F disarmed the commit gate",
            )
        finally:
            gp.mode_f = saved_f
            gp.c.read_stdin_json = saved_stdin
            if saved_env is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = saved_env


class RecognizerIsNarrow(BandBase):
    """FR-ARB-05: `git_subcmd` must not have been widened to see `gh`."""

    def test_git_subcmd_still_blind_to_gh(self):
        import guard_commit
        sub, _ = guard_commit.git_subcmd("gh pr merge 42")
        self.assertIsNone(
            sub,
            "git_subcmd was widened; guard_commit and guard_secrets consume "
            "it and would change behavior with it",
        )

    def test_valued_merge_options_do_not_eat_the_ref(self):
        """The doctrine's own integration command must arm the gate.

        ORCHESTRATOR.md prescribes local integration as `git merge --no-ff
        task/<slug>` with the verification evidence IN THE MERGE MESSAGE, and
        a non-interactive agent supplies that only via -m or -F. Taking the
        first non-flag token as the ref read `-m "gates green"` as the ref
        `gates`, scored nothing, and ALLOWED - the gate was defeated by the
        exact command the doctrine asks for.

        The semicolon case is separate and worse: `_common.segments` splits on
        `;` without honouring quotes, so a message containing one is torn in
        half. Covered here because a merge message is prose and prose has
        semicolons.
        """
        ref = self.high_lane()
        self.assert_band(ref, "high")
        for command in (
            "git merge --no-ff {r}",
            'git merge --no-ff -m "gates green" {r}',
            'git merge --no-ff -m "gates green; FRs 1-9 met" {r}',
            "git merge --no-ff -F /tmp/evidence.txt {r}",
            "git merge -X ours {r}",
            "git merge -s recursive {r}",
            "git merge --into-name main {r}",
        ):
            got = self.bash(command.format(r=ref))
            self.assertEqual(
                got.returncode, 2,
                "gate did not arm for: " + command.format(r=ref),
            )

    def test_optional_argument_flags_do_not_eat_the_ref(self):
        """git's `-S[<keyid>]`, `--gpg-sign[=<k>]` and `--log[=<n>]` take an
        OPTIONAL, ATTACHED value.

        Listing them as value-consuming created three fresh bypasses while
        fixing one: `git merge --no-ff -S task/x` swallowed the ref and allowed
        a high-band integration. Signed merges are an ordinary integration
        command, so that regression was live for any repo that uses them. The
        separated form `-S mykey` is git's octopus shape - two refs - which is
        why candidates are validated in order rather than taken first-and-only.
        """
        ref = self.high_lane()
        self.assert_band(ref, "high")
        for command in (
            "git merge --no-ff -S {r}",
            "git merge --no-ff --gpg-sign {r}",
            "git merge --log {r}",
            "git merge --no-ff -S mykey {r}",
            "git merge --no-ff --gpg-sign=mykey {r}",
            "git merge --log=5 {r}",
        ):
            got = self.bash(command.format(r=ref))
            self.assertEqual(
                got.returncode, 2,
                "gate did not arm for: " + command.format(r=ref),
            )

    def test_operators_inside_a_quoted_message_do_not_tear_the_segment(self):
        """`_common.segments` is quote-blind; mode F must not be.

        ORCHESTRATOR.md prescribes putting the verification evidence in the
        merge message. Evidence is prose, and prose carries semicolons and
        pipes - each of which the shared splitter treats as a command operator,
        tearing the merge in half so neither half parses as a ref. The chained
        form matters most: it is what a CEO actually types, and a retry that
        only rescued commands STARTING with `git` never covered it.
        """
        ref = self.high_lane()
        for command in (
            # UNSPACED operators are the point. An earlier splitter worked on
            # shlex TOKENS, which only yields a bare `;` when it has whitespace
            # on both sides - so `git fetch; git merge ...`, the ordinary way
            # anyone writes it, produced one unsplit segment whose subcommand
            # read `fetch;` and the gate never looked. The test that shipped
            # with that splitter wrote `echo starting ; git merge` and passed,
            # while its docstring claimed to cover what a CEO actually types.
            # Every operator below is deliberately unspaced.
            "git fetch; git merge --no-ff {r}",
            "git fetch&&git merge --no-ff {r}",
            'git checkout main && git merge --no-ff -m "gates green; 768 OK" {r}',
            'git merge --no-ff -m "hooks | CLI | installer" {r}',
            "echo 'a;b'; git merge --no-ff {r}",
        ):
            got = self.bash(command.format(r=ref))
            self.assertEqual(
                got.returncode, 2,
                "gate did not arm for: " + command.format(r=ref),
            )

    def test_unspaced_operators_split_for_gh_too(self):
        # Asserted at the splitter rather than end to end: bare `gh pr merge`
        # scores HEAD, and this fixture sits on main, so the correct end-to-end
        # answer is a silent low. What must be proved here is only that the
        # segment is FOUND - an unsplit `echo done; gh pr merge` was invisible.
        segs = gp.quoted_segments("echo done; gh pr merge")
        self.assertTrue(
            any(gp.integration_segment(s) for s in segs),
            "unspaced `;` hid a gh integration: " + repr(segs),
        )

    def test_a_non_ref_candidate_is_unresolvable_not_scored(self):
        # `--into-name main` used to yield `main`, whose diff against itself is
        # empty: band low, allowed, and NO log line at all. Validating the
        # candidate is what turns the quietest failure into a visible one.
        self.high_lane()
        self.assertEqual(
            gp.integration_refs("git merge no-such-ref", self.root), [])

    def test_an_octopus_merge_is_scored_on_its_worst_ref(self):
        """`git merge main task/x` brings in BOTH refs.

        Taking the first resolvable one scored `main` against itself - empty
        diff, band low - and mode F fell through its `band != "high"` branch
        with no block and no log line. A safety gate may only ever round toward
        the worse answer, so every ref is scored and the highest wins.
        """
        ref = self.high_lane()
        for command in ("git merge --no-ff main {r}", "git merge --no-ff {r} main"):
            got = self.bash(command.format(r=ref))
            self.assertEqual(
                got.returncode, 2,
                "octopus merge scored the wrong ref: " + command.format(r=ref),
            )

    def test_recognizer_sees_both_forms(self):
        self.assertTrue(gp.integration_segment("gh pr merge 42 --squash"))
        self.assertTrue(gp.integration_segment("git merge task/x"))
        self.assertFalse(gp.integration_segment("git status"))
        self.assertFalse(gp.integration_segment("gh pr view 42"))
        self.assertFalse(gp.integration_segment("gh pr list"))
        self.assertFalse(gp.integration_segment("git merge-base main HEAD"))
        self.assertFalse(gp.integration_segment("git merge --abort"))


if __name__ == "__main__":
    import unittest
    unittest.main()
