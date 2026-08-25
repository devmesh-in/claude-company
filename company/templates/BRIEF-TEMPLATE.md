# BRIEF: <task-slug>

_Type: quick | feature | program-workstream. Date: YYYY-MM-DD._

**Spec: `company/specs/spec-<slug>.md`** - read it in full. The spec is your
requirement. This file is not a summary of it and never restates it; it only
says which paths are yours.

> Frozen `surfaces[]` are judged at commit: `guard_commit` BLOCKs an
> UNDECLARED change to a matching path (the path matches AND no file in
> `company/change-requests/` names it). Unrecoverable `always[]` artifacts
> (.env, evidence, witnesses, accepted ADRs) stay hard-BLOCK mid-flight.
> Do not hand-edit `company/witnesses.json`.

## You own
- `<dir>/`
- `<dir>/`

Nothing else. Anything not listed is read-only to you. If the fix you need
lives outside these paths, report it; do not make it.

## Done
The FRs that live in your paths are true in the code, and the shared contract
(types, schema, seam tests) still passes unchanged.

Evidence floor, not negotiable:
- `bash company/run-gates.sh` green - run it yourself before reporting
- no edits outside your paths (`git diff --name-only`)
- tests added for the behavior you built
- `MODULE.md` created or updated in each owned directory
- commits per `company/GIT.md`: conventional, `Task: <slug>` trailer,
  explicit paths staged
- report per `company/templates/REPORT-TEMPLATE.md`

## Report back
Facts: what changed (paths), gate results (paste the ladder), which FRs you
made true, ownership diff, screenshots (UI), CRs filed, where you exercised
judgment and why, worries for the CEO.
