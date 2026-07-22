# BRIEF: release-0.2.2-closeout

_Type: quick. Spec: none (quick). Lead: CEO (self - closeout chore). Date: 2026-07-22._

## Mission

Close out the shipped model-routing-arming task and prepare release 0.2.2.
Make the traceability gate (R3) green honestly: the merged work is implemented
and tested, but the covering tests do not cite the FR/BR IDs, and doctrine FRs
(FR-MRA-11/12) plus the template shape (FR-MRA-01) have no covering test at
all. Add the citations at the exact covering tests, add one real regression
test asserting the shipped models.json template shape and the Workflow
doctrine presence in METHOD.md/ORCHESTRATOR.md, and cite the update-suite IDs
in its section 12 header. Then: archive paperwork, record decisions, bump
version 0.2.1 -> 0.2.2, and land it all in one release PR.

## You own

- `tests/hooks/test_hooks.py` (citations + one new test in TestGuardModelsBuiltins)
- `tests/install/test_update.sh` (section 12 header citations only)
- `package.json` (version bump only)
- `company/state/*` boards, `company/briefs/`, `company/specs/` (archival)

## Definition of Done

- [ ] `python3 .claude/hooks/trace_check.py` exit 0
- [ ] `python3 -m unittest discover -s tests/hooks -q` green
- [ ] `npm test` green
- [ ] Release PR merged; owner handed the tag+publish commands

## Out of scope

- Any behavior change to hooks, installer, or doctrine (citations and
  assertions only).
