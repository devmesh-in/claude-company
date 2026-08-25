# Brief: lean-prompts

Mission: cut prompted ceremony in the shipped harness. Rename the CEO
runbook and door to Company, drop the extra slash commands, keep
`/brainstorm`, and make update retire leftover field-install skills.
`--override` replaces shipped files with no backups. Default update still
preserves user edits.

## You own

- `.claude/skills/`, `.claude/agents/` (prompt text only)
- `COMPANY.md`, `ORCHESTRATOR.md` (rename)
- `company/METHOD.md`, `company/GATES.md`, `company/RELEASE.md`, templates
- `install.sh`, `update.sh`, `lib/`, `package.json`, docs, tests that pin
  the above
- `company/witnesses.json` via `witness_check.py` only

## Do not

- Commit this repo's real `company/gates.config`
- Delete hook enforcement (frozen surfaces, CRs, gates, auditor)
- Slim `/brainstorm`, `IDEATION.md`, or ideation-strategist except the
  `/orchestrator` -> `/company` flow line

## Done when

- Four skills ship: `/company`, `/lean-company`, `/company-init`, `/brainstorm`
- Field update deletes retired skills; `--override` overwrites payload
- Six suites green; version 0.4.1
