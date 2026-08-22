# BRIEF: hp-writers

_Type: program-workstream (L4 of the harness-port program).
Spec: `company/specs/spec-harness-port.md` - read ONLY the FR-HP-30 through
FR-HP-33 blocks. Lead: tech-lead. Date: 2026-08-13. Tracking issue: #100._

> Anything in `company/frozen-surfaces.json` is FROZEN - consume it exactly as
> shipped; any change goes through `company/change-requests/`, never a local edit.

## Mission

Three state writers still do read-modify-write with no lock and write their
files in place. With several sessions against one working tree - which shipped
as normal behavior in v0.2.6 - that silently loses updates: witness rows vanish,
`W-NNN` ids collide, and the cost cursor double-counts or rewinds. A torn read
of a state file also currently BLOCKS work that should proceed. Success is that
every one of these writers is serialized and atomic, and that an unreadable task
file fails open with a logged bypass instead of a wrong block.

Hard constraint: **these are all fail-open paths.** You are adding safety, and
if your safety mechanism can itself jam a session you have made things worse.
A lock that cannot be taken proceeds unlocked. That is deliberate.

## Read first (in order)

1. `CLAUDE.md`. NOTE: the copy on your branch may be stale about which suites
   gate this repo - the real list is in the DoD below, and it is five, not two.
2. `company/METHOD.md`
3. `.claude/hooks/_common.py` - specifically `state_lock` and the atomic JSON
   write helper, both delivered by lane L1. **They must already exist on main
   before you start.** If they do not, stop and report.
4. `.claude/hooks/witness_check.py`, `.claude/hooks/cost_capture.py` (whole
   files - you own both)
5. `.claude/hooks/guard_spec.py` - the task-file read path ONLY
6. `/Users/redomic/Documents/Projects/DevMesh/.claude/hooks/` - reference
   implementation. Note its `cost_capture` enters and exits the lock context
   manager BY HAND, which leaks the file descriptor if the body raises. Do not
   copy that; use a real `with` block.

## You own

- `.claude/hooks/witness_check.py`
- `.claude/hooks/cost_capture.py`
- `.claude/hooks/guard_spec.py` - **the torn-read path only.** Lane L2 already
  landed `is_source` in this file; do not touch that function.
- `tests/hooks/test_state_writers.py` (new file, yours to create)

Nothing else.

## Invariants in play

- Hooks fail OPEN; the two integrity CLIs (`witness_check.py`,
  `trace_check.py`) fail LOUD on a real finding. `witness_check.py` is one of
  those two: your locking must not soften its exit codes.
- The witness registry is checksum-sealed and mutated ONLY through
  `--add` / `--remove`. You are changing HOW it is written, never WHAT.
- Append-only logs are already safe under `O_APPEND`; do not convert them to
  read-modify-write in the name of consistency.
- Python 3.8, stdlib only.

## Scope (ordered)

1. **FR-HP-30 - witness registry.** `--add` and `--remove` run under
   `state_lock`; the registry is written through the atomic helper. Prove it
   with a real TWO-PROCESS race (subprocess, not threads) showing both rows
   survive a race that loses one without the lock, and that two concurrent
   adds do not collide on the same `W-NNN`.
2. **FR-HP-31 - cost cursor.** Same treatment, with a real `with` block. Add a
   source assertion that the file contains no manual `__enter__` on the lock,
   so the fork's pattern cannot creep back in.
3. **FR-HP-32 - guard_spec fails OPEN on a torn task file.** When
   `active-task.json` EXISTS but does not parse, log a BYPASS and exit 0
   instead of blocking with NO_BRIEF. A genuinely ABSENT task file must still
   block byte-identically - that is the regression that would matter, so assert
   both.
4. **FR-HP-33** - source scan proving no non-atomic JSON write remains in your
   owned files.
5. **ADDED 2026-08-13, and it is a blocker for another lane - `quick` entries
   are exempt from the brief requirement.** `guard_spec` currently exempts only
   `hotfix`, so the doctrine authorized by DECISIONS #19 is FALSE on disk.
   Worse, and this is why it is urgent: the check is an ALL over non-hotfix
   entries and it blocks the EDIT, not the offending entry. I reproduced it -
   two entries, `feat-a` (feature, good brief) and `quick-b` (quick, no brief),
   one edit to `src/app.py`, exit 2 naming `quick-b`. So one briefless quick
   entry bricks source edits for every concurrent session in the tree,
   including lanes whose briefs are perfectly fine. A CEO following the new
   doctrine literally bricks its own checkout.
   Add `quick` alongside `hotfix` in whatever the brief-gating predicate is,
   with the bypass reason naming both. Requirements: the exemption is
   PER-ENTRY, exactly like `hotfix` - a quick entry exempts ITSELF and never
   the tree, so a feature entry with no brief sitting beside a quick one must
   still block. Assert both directions, and assert that a lone briefless
   feature entry still blocks byte-identically. Lane L6 is holding its
   doctrine clause until this lands; say clearly in your report that it did,
   so I can release that clause.

## Integration seams

- **L1** gives you `state_lock` and the atomic writer. Use them; do not write
  your own. If a signature differs from the spec, report it rather than
  adapting silently - a second implementation of a lock is how this class of
  bug comes back.
- **L2** already owns `is_source` in `guard_spec.py`. Its work is merged before
  you start; rebase cleanly and stay out of that function.

## Definition of Done

- [ ] Every FR in scope implemented, tested, or explicitly deferred with reason
- [ ] **All five suites** from your worktree root, pasted:
      `python3 -m unittest discover -s tests/hooks -q`, `npm test`,
      `bash tests/install/run_tests.sh`, `bash tests/install/test_tui.sh`,
      `bash tests/install/test_update.sh`. Do NOT run `company/run-gates.sh`.
- [ ] Two-process race tests for BOTH the registry and the cursor, each
      demonstrated to fail without the lock
- [ ] `witness_check.py --check` byte-identical behavior on a clean registry
- [ ] No edits outside owned files or outside the one owned path in
      `guard_spec.py`
- [ ] Conventional commits, `Task: hp-writers` trailer, explicit staged paths
- [ ] Report per `company/templates/REPORT-TEMPLATE.md`, 1-3 witness candidates

## Fallback assumptions

- Lock timeout and retry counts come from L1's kernel; do not introduce new
  numbers. If you need one, report it rather than inventing it.

## Out of scope

- `guard_provenance.py` ledger locking - that is L5, same wave, and it is the
  one file you must not touch.
- `is_source` in `guard_spec.py`.
- Any new state file, any new writer.

## Report back

Facts: what changed, all five suites pasted, FR checklist, the two race
demonstrations, ownership diff, deviations, worries, witness candidates.
