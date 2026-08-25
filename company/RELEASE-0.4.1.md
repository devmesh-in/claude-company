# RELEASE 0.4.1 - lean the company door

_Prepared: 2026-08-25. Target: `task/lean-prompts` merge into `main`._
_Status: owner instructed this session to ship via GitHub release._

The owner ships with `gh release create`. CI is the ladder.

## Contents

Cut the extra slash-command set and the local release ritual. The CEO door
is `/company` and the runbook is `COMPANY.md`. Field installs that still
have `/orchestrator`, `/release`, `/gates`, and the rest lose those files
on update. `--override` replaces shipped files outright (no backups, no
`.new`). User gates, specs, briefs, and `company/state` stay theirs.

`/brainstorm` stays. `/company-init` founds or adopts. `/lean-company`
stays the fast door.

## Semver

- **Current:** 0.4.0
- **Proposed:** 0.4.1
- **Rule:** pre-1.0, owner named the patch
- **Why:** ceremony cut and a rename, not a new enforcement layer

### Breaking

- `/orchestrator`, `/feature`, `/onboard`, `/gates`, `/cr`, `/release`,
  `/autopilot` are no longer shipped. `/orchestrator` still matches
  `/company`. Update deletes the leftover skill files. (`Task: lean-prompts`)
- `ORCHESTRATOR.md` is now `COMPANY.md`. Update removes the old file.
  (`Task: lean-prompts`)
- There is no local `/release` R1-R10 list. Owner-said-ship is
  `gh release create`. CI publishes to npm. (`Task: lean-prompts`)

### Features

- `/company` is the CEO door. Classify and staff to the work. (`Task: lean-prompts`)
- `/company-init` founds a new repo or adopts an existing one. (`Task: lean-prompts`)
- `/brainstorm` and ideation-strategist ship again. (`Task: lean-prompts`)
- `claude-company update --override` replaces shipped payload and deletes
  retired files with no backups. Default update still preserves edits
  with `.new`. (`Task: lean-prompts`)

### Fixes

- Confirm a green fresh stamp before re-running gates. (`Task: lean-prompts`)
- Install/update no longer advertise `/onboard` as a separate door.
  (`Task: lean-prompts`)

## Known limits

- Frozen surfaces and CRs are unchanged. They still serialize a lane that
  touches a protected path.
- Default `update` leaves a customized shipped file in place and writes
  `.new`. Use `--override` when you want this package's prompts on disk.
- Open P2/P3 worries remain in `company/state/WORRIES.md`.
- Witnesses: `python3 .claude/hooks/witness_check.py --check` must be green
  on the SHA you ship.

## Ship

```bash
gh release create v0.4.1 --target <sha> \
  --notes-file company/RELEASE-0.4.1.md
```
