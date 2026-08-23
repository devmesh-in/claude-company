# BRIEF: cost-ledger-removal

_Type: quick. Spec: none (deletion, owner-directed). Lead: direct-developer.
Date: 2026-08-23. Tracking: #134._

## Mission

Remove the cost ledger from the harness outright. Owner call 2026-08-23: it is
not earning its place, and it is the single ugliest thing to carry into a
second harness - the DevMesh opencode shim had to synthesize a fake
Claude-shaped JSONL transcript into `/tmp` purely to feed `cost_capture.py`.
Deleting it now means the second harness never has to model it. Success is a
green five-suite ladder with no cost hook, no cost artifacts, and no dangling
reference anywhere in the tree.

The hard constraint: this lands as its own change, before any harness work, so
that the harness-agnostic feature can be shown to alter no behavior on its own.

## Read first (in order)

1. `CLAUDE.md`
2. `company/METHOD.md`
3. `.claude/hooks/cost_capture.py`, `.claude/settings.json`
4. `.claude/hooks/guard_models.py` (`EXPECTED_WIRING`), `.claude/hooks/guard_frozen.py`
5. `company/frozen-surfaces.json`, `company/change-requests/CR-2-freeze-gate-run-artifacts.md`

## You own

- `.claude/hooks/`, `.claude/settings.json`, `.claude/skills/standup/`
- `tests/hooks/`
- `company/models.json`, `company/frozen-surfaces.json`, `company/witnesses.json`,
  `company/METHOD.md`, `company/change-requests/`
- `docs/`, `.gitignore`

## Invariants in play

- Hooks stay Python 3.8 stdlib and fail open on internal error.
- `no_slop` applies to all writing.
- The witness registry is checksum-sealed and mutated ONLY via
  `witness_check.py --add/--remove`, never by hand.
- Accepted ADRs are immutable.

## Frozen surfaces nearby

`company/frozen-surfaces.json` lists `company/state/costs.log` and
`company/state/.cost-cursor.json`. They were frozen by
`CR-2-freeze-gate-run-artifacts.md`. File a superseding CR and apply it; do not
delete the lines as a plain edit.

## Scope (ordered)

1. File the CR superseding CR-2 for the two cost run-artifact entries.
2. Remove the sealed witness entry via
   `python3 .claude/hooks/witness_check.py --remove .claude/hooks/cost_capture.py`.
3. Delete `.claude/hooks/cost_capture.py` and `tests/hooks/test_cost_capture.py`.
4. Unwire `.claude/settings.json`: drop `cost_capture.py` from `Stop`, and
   delete the `SubagentStop` group entirely - it exists only for this hook.
5. Drop the two `cost_capture.py` rows from `EXPECTED_WIRING` in
   `guard_models.py`, and the two run-artifact paths from `guard_frozen.py`.
6. Drop the `pricing` block from `company/models.json` and the spend section
   from `.claude/skills/standup/SKILL.md`.
7. Clear references in `.gitignore`, `company/METHOD.md`, `docs/customizing.md`,
   `docs/glossary.md`, `docs/how-it-works.md`.
8. Audit the four other test files that mention cost
   (`test_multi_task_display`, `test_state_kernel`, `test_state_writers`,
   `test_v1_v2_parity`) and remove only what asserts on the ledger.
9. Delete the state artifacts `company/state/costs.log` and
   `company/state/.cost-cursor.json` (gitignored; local cleanup).

## Integration seams

None. Nothing consumes the ledger except `/standup`, which loses its spend
section and reports without it.

## Definition of Done

- [ ] All five suites green, pasted in the report
- [ ] `python3 .claude/hooks/guard_models.py --check` exits 0
- [ ] `python3 .claude/hooks/witness_check.py` exits 0 with the entry gone
- [ ] `git grep -i "cost_capture\|costs\.log\|cost-cursor"` returns only
      historical records: shipped briefs, shipped specs, DECISIONS, RESUME,
      WORRIES, and the superseded CR
- [ ] Rework deletes the tests of removed behavior; the report lists them
- [ ] Conventional commit, `Task: cost-ledger-removal` trailer, explicit paths

## Fallback assumptions

- OQ-CLR-01: keep or delete the historical `costs.log` content?
  FALLBACK: delete. It is a gitignored local artifact with no consumer left.
- OQ-CLR-02: does `/standup` keep a token-only report?
  FALLBACK: no. There is no producer once the hook is gone; remove the section
  rather than leave a section that can never populate.

## Out of scope

- Anything under #133 (the harness work).
- Any other change to `settings.json` wiring.

## Report back

What changed by path, the pasted five-suite ladder, the CR filed, the witness
removal output, the test deletions, and any dangling reference deliberately
left as a historical record.
