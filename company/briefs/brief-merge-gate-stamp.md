# BRIEF: merge-gate-stamp

_Type: feature. Spec: lite (owner-confirmed plan; DECISIONS #25).
Lead: direct (CEO self-build). Date: 2026-08-25._

> Frozen `surfaces[]` are judged at commit: `guard_commit` BLOCKs an
> UNDECLARED change to a matching path (the path matches AND no file in
> `company/change-requests/` names it). Unrecoverable `always[]` artifacts
> (.env, evidence, witnesses, accepted ADRs) stay hard-BLOCK mid-flight.
> Do not hand-edit `company/witnesses.json`.

## Mission

Parallel sessions can commit their own work while a sibling's tests keep the
shared suite red. `git merge` onto main/master still requires a green, fresh
acting-tree stamp. The stamp stays a sensor; it stops being a commit lock.

## Read first (in order)
1. `CLAUDE.md`
2. `company/METHOD.md` (law 2, mechanism 4)
3. `.claude/hooks/guard_commit.py`
4. DECISIONS #21 and #25

## You own
- `.claude/hooks/guard_commit.py`
- `.claude/hooks/session_start.py`
- `.claude/hooks/rent_report.py`
- `tests/hooks/test_hooks.py`
- `tests/hooks/test_acting_tree_commit.py`
- `tests/hooks/test_v1_v2_parity.py`
- `tests/hooks/test_guard_parsers.py`
- `tests/hooks/test_multi_task_gates.py`
- `tests/hooks/test_asr_rework.py`
- `tests/hooks/test_doctrine_canon.py`
- `tests/hooks/test_session_start_digest.py`
- `company/METHOD.md`
- `company/GATES.md`
- `COMPANY.md`
- `company/state/DECISIONS.md`
- `company/state/harness-port-checklist.md`
- `company/specs/spec-ai-sdlc-rework.md`
- `company/RELEASE.md`
- `docs/how-it-works.md`
- `docs/getting-started.md`
- `docs/glossary.md`
- `README.md`

Nothing else.

## Invariants in play (must not break)
- Secrets, undeclared frozen drift, and the task-branch rule still gate commit.
- Acting-tree stamp resolution (CR-HP-2) still describes the tree being merged.
- A hotfix still logs BYPASS rather than silently skipping.

## Frozen surfaces nearby (CR, never edit)
- `company/state/gates.status` (always[]) - runner writes it, not this task.
- `company/witnesses.json` - mutate only via witness_check.py.

## Scope (ordered)
1. Stamp check in `guard_commit` fires only when `sub == "merge"` and
   `current_branch` is main/master. Oracle: commit with no stamp ALLOW;
   merge on main with no stamp BLOCK; merge on task branch with no stamp ALLOW.
2. `stamp_message` names merge-onto-main. Oracle: stderr contains
   "merge onto a protected branch".
3. Canon (METHOD mechanism 4, GATES.md, field docs) matches the hook.
   Oracle: `test_doctrine_canon.py` DECISIONS-25 clauses.
4. Invert commit-requires-stamp tests; keep hotfix merge BYPASS.
   Oracle: hooks suite green.

## Integration seams
- CI remains the PR-mode ladder (`gh pr merge` never hits this hook).
- Session-start digest informs when the tree is red; it does not block.

## Definition of Done
- [x] Commit with no/red/stale stamp ALLOW (other commit checks still fire)
- [x] Merge on main with no/red/stale stamp BLOCK
- [x] Merge on a task branch with no stamp ALLOW
- [x] Hotfix merge on main BYPASS + log
- [x] Six suites green
- [ ] Commits follow `company/GIT.md` with `Task: merge-gate-stamp`

## Fallback assumptions
- OQ-MGS-01: unknown branch on merge -> FALLBACK: treat as not protected
  (fail open), same as the commit branch rule. Tag `# OQ-MGS-01 assumption`.

## Out of scope
- Affected-suites / smoke tier (RESUME outstanding, CPU not deadlock)
- Deleting `run-gates.sh` / `gates.status` / freshness hashing
- Splitting the ladder into worktree vs integration rungs (P4)

## Report back
What changed, hooks suite output, FR/decision checklist, ownership diff.
