# BRIEF: hp-provenance

_Type: program-workstream (L5 of the harness-port program). THE HIGHEST-RISK
LANE IN THIS PROGRAM.
Spec: `company/specs/spec-harness-port.md` - read the FR-HP-40 through FR-HP-47
blocks and OQ-HP-05 and OQ-HP-08. Two items are NEWER than the spec and marked.
Lead: tech-lead. Date: 2026-08-13. Tracking issue: #101._

> Anything in `company/frozen-surfaces.json` is FROZEN - consume it exactly as
> shipped; any change goes through `company/change-requests/`, never a local edit.

## Mission

`guard_provenance` is the hook that makes "never let the producer grade itself"
mechanical rather than aspirational. It has three problems. Its ledger
read-modify-writes are unlocked, so concurrent sessions lose dispatch credits
and produce false "delegated but no dispatch" blocks. Its audit demand is armed
by EVERY dirty source path in the tree rather than by the paths this company
actually authored, so unrelated dirty files - another session's, the owner's -
block a clean commit. And the mandatory-audit rule is triggered by
self-authorship alone, so a large fully-delegated diff can integrate with no
independent read at all, which has already happened here on a 4,791-line change
touching every enforcement hook.

Success is a ledger that survives concurrency, an audit demand scoped to what
the company authored, and an audit requirement that scales with RISK rather
than only with authorship.

**Read this twice: this lane converts BLOCKs into ALLOWs.** That is the exact
monotonicity class the multi-session work was built to protect. An independent
auditor pass is a MERGE CONDITION for this lane, not a nicety.

## Read first (in order)

1. `CLAUDE.md`. The real suite list is in the DoD below - five, not two.
2. `company/METHOD.md` - mechanism 5 is what this hook enforces. Read it
   carefully; your changes must implement its sentence, not weaken it.
3. `.claude/hooks/guard_provenance.py` (whole file - you own it)
4. `.claude/hooks/risk_score.py` (read-only reference for the band logic, plus
   scope item 6)
5. `company/state/WORRIES.md` - three rows are directly yours: the
   umbrella-scoped dirty check, the clean-delegated-build-gets-no-audit row,
   and the worktree-commit-stamp row.
6. `company/specs/spec-repo-scoped-enforcement.md` - **the PARK NOTE at the top
   only, roughly 40 lines.** It independently identified the dirty-intersected-
   with-self-authored fix as the cheaper and more principled one, and it names
   the hole that fix leaves. Do not read the rest of that spec.
7. `/Users/redomic/Documents/Projects/DevMesh/.claude/hooks/guard_provenance.py`
   - the reference. Ignore everything polyrepo in it: `commit_repo_root`,
   `repo_tree_hashes`, per-repo `fresh_audit`, the `.{repo}-wt` conventions.

## You own

- `.claude/hooks/guard_provenance.py`
- `company/adr/ADR-0003-self-authored-audit-scope.md` (new, `Status: accepted`)
- `tests/hooks/test_guard_provenance.py` (extend the existing file - do not
  create a parallel one)

Nothing else. `risk_score.py` is READ-ONLY to you: if scope item 6 needs a
change there, file a CR.

## Invariants in play

- **METHOD mechanism 5.** Nothing self-authored integrates unaudited. You are
  changing what "self-authored" MEANS, never whether the rule applies.
- Hooks fail OPEN; the ledger is checksum-sealed and written only by this hook.
- A hand-edited ledger resets the checksum and wipes the audit history. Never
  write a repair path that hand-edits it.
- Stored verdict values must not change - old ledgers keep working.
- Python 3.8, stdlib only.

## Scope (ordered)

1. **FR-HP-40 to FR-HP-42 - lock the ledger.** Every read-modify-write - mode A,
   mode B-pre, mode B-post - wrapped in L1's `state_lock`. Two-process race
   tests per mode.
2. **FR-HP-43 - unattributed dispatches.** A builder spawn whose task file is
   unreadable records an UNATTRIBUTED dispatch instead of silently vanishing.
   A vanished dispatch is what produces the false "delegated but no dispatch"
   block later.
3. **FR-HP-44 and FR-HP-45 - scope the audit demand.** The demand is armed by
   dirty paths INTERSECTED WITH the ledger's `self_authored` list, not by every
   dirty path. Plus `delegated_with_dispatches`: an entry-shape route to the
   exemption mechanism 5 ALREADY grants delegated work, requiring ALL of - every
   gated entry declares `execution: delegated`, each has at least one
   HOOK-RECORDED credited dispatch, and no dirty path appears in the
   hook-recorded `self_authored` list. Note that the declaration alone unlocks
   nothing; the two load-bearing conditions are both written by hooks.
   Test this as a DECISION TABLE - the cross product of dirty paths, self
   authored, execution decision, dispatch count and audit freshness, for mode C
   and mode D, each row with its expected verdict.
4. **FR-HP-46 - name and test the hole.** Source written through Bash (a
   heredoc, `sed`, a script) never fires the PostToolUse Edit event, so it is
   never recorded self-authored and therefore stops arming the requirement.
   That is a real, accepted, narrow hole. Write a characterization test that
   ASSERTS the allow and names OQ-HP-05, so it is a known limitation rather
   than a surprise. Record it in ADR-0003.
5. **FR-HP-47 - ADR-0003** recording the audit-scope model: what armed the
   demand before, what arms it now, the Bash hole, and why this is mechanism 5
   implemented rather than relaxed.
6. **NEWER THAN THE SPEC, authorized by DECISIONS #19 - risk-scaled audit.**
   The audit requirement scales with `risk_score.py`'s EXISTING bands. A
   `high` band arms a mandatory audit requirement the same way self-authorship
   does, so a large delegated diff can no longer integrate unaudited - that
   closes the worry directly. Do NOT introduce a line-count threshold or any
   new numeric fence; the owner has vetoed that shape twice, and the whole
   point is that the bands are already derived from signals the company holds.
   If this needs a change inside `risk_score.py`, file a CR - you do not own it.
7. **NEWER THAN THE SPEC - the worktree stamp seam.** Mode C's worktree
   exemption keys on the payload cwd, not on the repo the commit actually
   targets, so a commit landing in a worktree can be gated on the main
   checkout's dirty source. Lane L2 built `guard_commit.seg_git_dir`, which
   resolves exactly that; reuse it rather than writing a second resolver. Only
   do this if L3's root-resolution work has merged, because before that a
   worktree cannot produce its own stamp and redirecting would create a new
   false block. Check, and if it has not merged, report and defer.

8. **ADDED 2026-08-13 - the worktree exemption is convention-based and now
   DISAGREES with the kernel.** `guard_provenance` recognizes a worktree by the
   literal string `/.claude/worktrees/`, so a worktree created anywhere else
   loses its delegated exemption. L1 has just replaced the equivalent guess in
   `_common.rel_path` with a DERIVED answer - the nearest ancestor holding a
   `.git` entry, no string match anywhere - and added a test putting a worktree
   at `build/elsewhere/wt2`. Yours is now the last place carrying the guess,
   and the two answering differently is the same class of bug that produced the
   P0 this program just fixed. Use the kernel's derivation rather than a second
   implementation; if the primitive you need is not exposed, report it rather
   than reimplementing it.

## Definition of Done

- [ ] Every FR in scope implemented, tested, or explicitly deferred with reason
- [ ] **All five suites** from your worktree root, pasted:
      `python3 -m unittest discover -s tests/hooks -q`, `npm test`,
      `bash tests/install/run_tests.sh`, `bash tests/install/test_tui.sh`,
      `bash tests/install/test_update.sh`. Do NOT run `company/run-gates.sh`.
- [ ] **An independent auditor pass is a MERGE CONDITION** for this lane. The
      CEO dispatches it; your job is to make the diff auditable and to say in
      your report exactly which behaviors changed from BLOCK to ALLOW. List
      them explicitly - that list is what the auditor reads first.
- [ ] The decision table covers every combination, and each ALLOW row states
      why it is not a hole
- [ ] Two-process race tests for all three ledger modes
- [ ] The Bash hole has a characterization test naming OQ-HP-05
- [ ] No behavior that was a BLOCK becomes an ALLOW without a test row and a
      line in the report
- [ ] Conventional commits, `Task: hp-provenance` trailer, explicit paths
- [ ] Report per `company/templates/REPORT-TEMPLATE.md`, 1-3 witness candidates

## Fallback assumptions

- OQ-HP-05: source written via Bash -> FALLBACK: accepted hole, tested and
  named. Tag `# OQ-HP-05 assumption`.
- OQ-HP-08: whether the delegated exemption applies at commit as well as at
  Stop -> FALLBACK: both.

## Out of scope

- `risk_score.py` itself (read-only; CR if you need it).
- Every polyrepo mechanism in the reference implementation.
- Merge-only stamp gating - still parked; do not assume it.
- `guard_spec.py`, which is L4's this wave.

## Report back

Facts: what changed, all five suites pasted, FR checklist, **the explicit
BLOCK-to-ALLOW list**, the decision table results, ownership diff, CRs filed,
deviations, worries, witness candidates.
