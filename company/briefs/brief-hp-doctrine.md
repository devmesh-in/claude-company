# BRIEF: hp-doctrine

_Type: program-workstream (L6 of the harness-port program).
Spec: `company/specs/spec-harness-port.md` - read ONLY the FR-HP-50 through
FR-HP-65 blocks and OQ-HP-01 and OQ-HP-13. Two items in this brief are NEWER
than the spec and are marked so.
Lead: tech-lead. Date: 2026-08-13. Tracking issue: #102._

> Anything in `company/frozen-surfaces.json` is FROZEN - consume it exactly as
> shipped; any change goes through `company/change-requests/`, never a local edit.

## Mission

Two jobs. First, fix a live P1: `stop_gate` reads EVERY active task entry but
checks ONE global stamp, so with several concurrent sessions any session's stale
tree blocks every other session at every turn end, and the block recipe tells
the wrong session to fix work it does not own. This is not theoretical - it
fired three times on the CEO in a single session today and cost 1283 seconds
(21 minutes) of ladder runs proving things that were already proven. Second,
bring the doctrine and agent definitions in line with what this program
actually changed, plus one new mechanical check that stops canon drifting from
reality again.

The hard constraint: **stop_gate must not be deleted or un-wired.** A downstream
fork did exactly that and it is the wrong answer here. It is the only check on
three paths `guard_commit` cannot see - a session that edits and never commits,
a session that commits green then edits more, and an entry closed with red
gates. The owner settled this in DECISIONS #18: scope it, do not remove it.

## Read first (in order)

1. `CLAUDE.md` (project canon). **Note: the copy on your branch is STALE.** It
   says two suites gate this repo. That is wrong and is fixed in the main
   checkout but uncommitted. See Definition of Done for the real list.
2. `company/METHOD.md`, `company/GATES.md`, `ORCHESTRATOR.md` - you are editing
   all three.
3. `.claude/hooks/stop_gate.py` (whole file - it is short) and
   `.claude/hooks/_common.py` `active_tasks` / `check_stamp`.
4. `company/state/DECISIONS.md` entries 18 and 19 - the two owner rulings this
   lane implements.
5. `company/state/WORRIES.md` - the stop_gate row carries the reproduction and
   the measured cost. Cite it; do not re-derive it.
6. `company/specs/spec-harness-port.md`, FR-HP-50 through FR-HP-65, OQ-HP-01,
   OQ-HP-13.
7. `/Users/redomic/Documents/Projects/DevMesh/` - the reference fork, for the
   doctrine prose only (its ORCHESTRATOR parallel-discipline and
   don't-fight-the-harness sections). Its `settings.json` is NOT a reference:
   it un-wired stop_gate, which is the thing we are refusing to copy.

## You own

- `.claude/hooks/stop_gate.py`
- `ORCHESTRATOR.md`
- `company/METHOD.md`, `company/GATES.md`
- `company/templates/BRIEF-TEMPLATE.md`
- `.claude/agents/auditor.md`, `docs-librarian.md`, `qa-engineer.md`,
  `tech-lead.md`
- `.github/workflows/ci.yml` (for scope item 8 only)
- `tests/hooks/test_stop_gate_scope.py` (new file, yours to create)

Nothing else. Four lanes are building concurrently and I have verified none of
them touches a single file above. Do NOT touch `_common.py`, any `guard_*.py`,
`run-gates.sh`, `gate_stamp.py`, `frozen-surfaces.json`, `.gitignore` or
`company/gates.config`.

## Invariants in play

- Hooks fail OPEN. `stop_gate` already exits 0 on any internal error and on
  `stop_hook_active`; keep both.
- `quick` and `hotfix` entries exempt THEMSELVES, not the tree (FR-MST-09).
  Whatever scoping you choose must preserve that exactly.
- Doctrine files ship verbatim into installs and must stay generic. No
  claude-company-repo-specific commands in `company/`.
- Accepted ADRs are immutable.
- Python 3.8, stdlib only.

## Scope (ordered)

1. **FR-HP-50 - scope the stop_gate block.** The spec's decided fallback
   (OQ-HP-01) is the single-gating-entry rule: with exactly one gating entry
   behave BYTE-IDENTICALLY to today; with more than one, log a WARN to
   `adherence.log` and do not block. Implement that unless reading the code
   shows something better. I want your judgment on one point, stated in your
   report: the alternative is attributing the block to the session's own work,
   which needs session-keyed state that the multi-session spec deliberately
   scoped out. If you find a cheap honest attribution signal, say so rather
   than silently choosing it.
   Be explicit in the block message about WHICH entries armed it, so a blocked
   session can tell whose tree is red.
2. **FR-HP-51 to FR-HP-65 - doctrine sync.** GATES.md and METHOD.md document
   the runner changes L3 built (quiet-pass, `gates.log`, worktree root
   resolution). ORCHESTRATOR gains the parallel-discipline section (dispatch a
   wave in ONE message, never idle while lanes build, integrate per-lane rather
   than barrier-waiting, CRs are interrupt-priority) and the
   don't-fight-the-harness rules (the block message is the recipe,
   twice-blocked is an escalation, never edit a guard).
3. **Right-sized paperwork.** State-file caps around 300 lines with overflow
   archived VERBATIM to `company/state/archive/`; QA evidence is four states per
   CHANGED screen with full sweeps on demand only; docs-librarian dispatched
   BATCHED once per delivery. That last one requires editing
   `.claude/agents/docs-librarian.md` itself - the fork changed the doctrine and
   left its agent definition contradicting it, which is the exact mistake to
   avoid.
4. **BRIEF-TEMPLATE test-quality DoD**: each test proves a falsifiable claim; no
   restating-implementation tests; extend an existing test file rather than
   creating a parallel one; REWORK DELETES the tests of removed behavior,
   because accreting dead tests is a defect.
5. **auditor.md**: verify the stamp via `gate_stamp.py --check` rather than
   re-running a ladder the CEO runs in parallel; add the delta-scoped re-audit
   mode; add test-VALUE grading where tests deleted with the behavior are
   CORRECT and the ones NOT deleted are the finding. Give it a verdict
   vocabulary that cannot poison the ledger record, and forbid it from emitting
   the negative token in prose.
6. **tech-lead.md**: spawn ALL developers in one message; QA the FIRST finished
   surface; review scaled to risk.
7. **NEWER THAN THE SPEC, authorized by DECISIONS #19 - the Phase 0 spec-lite
   rung.** Feature-class Phase 0 gets two rungs on OBJECTIVE conditions, never
   appetite: spec-lite (ALL of - one repo, nothing frozen, no money, no
   invariant) lets the CEO derive the sealed brief directly and record
   `"spec": "lite: <why>"` on the task entry, with a ONE-WAY escape upward the
   moment the work touches a frozen surface, a second repo, or an invariant.
   The brief itself stays hook-required. Also: `quick` entries need no brief.
   Both go in METHOD.md's ceremony table and ORCHESTRATOR's classify step.
   The spec lists these as parked; the owner unparked them after it was written.
8. **NEWER THAN THE SPEC - a mechanical canon check.** Add a CI step asserting
   that every test suite `ci.yml` runs is NAMED in `CLAUDE.md`. Rationale to
   record in the step: CLAUDE.md claimed two suites gated this repo when CI ran
   five, the error propagated into three sealed briefs, and a lane shipped a
   red branch because nobody ran the suite that caught it. This is the third
   instance of canon and CI disagreeing. Make the disagreement a red gate.
9b. **ADDED - a SECOND instance of the same reconciliation class.** The
   tech-lead brief says a lead never pushes and hands off a green branch plus
   evidence, with the CEO doing the push and the PR. In practice the CEO
   instructed two lanes to push their own task branches this session, and one
   of them flagged the contradiction rather than silently complying - which is
   the correct behavior and the reason it is now visible. Resolve it with the
   same ruling shape as item 9: either the standing brief changes to allow a
   lead to push its OWN task branch (never main, never the PR merge), or the
   CEO stops asking. Note the underlying pattern in your reasoning, because it
   is the actual finding: BOTH instances are the CEO's in-session instruction
   contradicting standing canon, and in both cases the lane followed the
   instruction and reported the conflict. That is the behavior canon should
   reward, so whatever you decide should make the reporting path explicit.
9. **Doctrine reconciliation the CEO owes you** (see CR-2's decision remarks):
   ORCHESTRATOR says the CEO applies approved CRs to frozen surfaces itself,
   but a brief granted a lane a frozen file outright and the lane correctly
   followed its brief. Resolve it one way - either briefs stop granting frozen
   files, or the rule gains an explicit brief-grant exception. Your call; state
   the reasoning.

## Definition of Done

- [ ] Every FR in scope implemented, tested, or explicitly deferred with reason
- [ ] **Run ALL FIVE suites** from your worktree root and paste them. CLAUDE.md
      on your branch is stale and lists two; the real list is:
      `python3 -m unittest discover -s tests/hooks -q`, `npm test`,
      `bash tests/install/run_tests.sh`, `bash tests/install/test_tui.sh`,
      `bash tests/install/test_update.sh`. Do NOT run `company/run-gates.sh` -
      from a worktree it gates the main checkout.
- [ ] Known-flaky, do not chase: `test_tui.sh` reports exactly 20 pass / 1 fail
      in a wired checkout. Exactly that shape is the known issue and a separate
      task is fixing it. Anything else is real.
- [ ] `stop_gate` behavior at ONE gating entry is byte-identical to today -
      assert it, because that is the regression that would matter most
- [ ] The multi-entry case has a test built from the real reproduction: two
      feature entries plus a stale stamp
- [ ] Doctrine assertions: each doctrine file read and the required clause
      asserted present, in `tests/hooks/test_stop_gate_scope.py`
- [ ] The new CI step demonstrated failing: remove a suite name from a COPY of
      CLAUDE.md, show the check goes red, and paste it
- [ ] No edits outside owned files; zero frozen surfaces patched locally
- [ ] Commits follow `company/GIT.md`: conventional, `Task: hp-doctrine`
      trailer, explicit staged paths, never `git add -A`
- [ ] Report per `company/templates/REPORT-TEMPLATE.md` with 1-3 witness
      candidates

## Fallback assumptions

- OQ-HP-01: stop_gate scoping shape -> FALLBACK: the single-gating-entry rule
  above. Tag `# OQ-HP-01 assumption`.
- OQ-HP-13: the 300-line paperwork cap -> FALLBACK: doctrine prose only, NEVER a
  hook. A numeric cap enforced mechanically is exactly the magic-number shape
  this company rejects.

## Out of scope

- Deleting or un-wiring `stop_gate`. Settled, DECISIONS #18.
- Model tiering. Rejected, DECISIONS #1.
- Merge-only stamp gating. Still parked deliberately; do not write doctrine
  that assumes it.
- The risk-scaled audit band - adopted, but it lives in `guard_provenance.py`
  and `risk_score.py`, which belong to L5 in wave 2.
- Every hook except `stop_gate.py`.

## Report back

Facts: what changed, all five suites pasted, the FR checklist, your judgment on
the scoping shape, the CI-step failure demonstration, ownership diff,
deviations, worries, witness candidates.
