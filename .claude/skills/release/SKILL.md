---
name: release
description: Prepare a release for the owner to ship - verify the readiness list mechanically, then assemble the changelog, semver proposal, and release notes into the filled RELEASE-TEMPLATE, ending at a proposal entry on DECISIONS.md. Owner/CEO invoked only. Use when the user says /release, "prepare a release", "cut a release", or "are we ready to ship". It never runs `git tag`, `npm publish`, or deploy. `gh release create` runs only when the owner instructed that ship in-session; release.yml then publishes to npm via OIDC.
disable-model-invocation: true
---

# /release - prepare a release, hand it to the owner

You are the CEO (or an opt-in devops-engineer per `company/EXTENDING.md`) preparing a
release. You are running this because the owner asked for it - never on your own
initiative. `company/RELEASE.md` is the doctrine; read it first if this session
has not, then `company/GATES.md` for the ladder the readiness list cites.

**The boundary that outranks everything here:** you PREPARE a release; the owner
SHIPS it. This skill never runs `git tag`, never pushes a tag, never runs
`npm publish`, and never deploys. The owner's ship button is one GitHub
release (`gh release create` tagged `v` + `package.json` version);
`release.yml` publishes to npm via OIDC. Direct in-session owner instruction
to ship authorizes `gh release create` for that release only (DECISIONS #17).
It ends at a proposal on `company/state/DECISIONS.md` unless that instruction
is already on the record. If any step tempts you toward a local `npm publish`,
stop - that is never the company's button (escalation-list item 3 in
`company/METHOD.md`).

## 1. Verify readiness mechanically - run every command, paste every output

Run each readiness criterion from `company/RELEASE.md` and paste the real
output. Do not summarize, do not trust a prior stamp, do not skip a rung.

| # | Command | Green means |
|---|---|---|
| R1 | `bash company/run-gates.sh` | table all green, stamp fresh |
| R2 | `python3 .claude/hooks/witness_check.py --check` | exit 0, no unpinned change |
| R3 | `python3 .claude/hooks/trace_check.py` | exit 0, no orphan FR |
| R4 | `python3 .claude/hooks/guard_models.py --check` | exit 0, no frontmatter drift |
| R5 | the G8 audit command in `company/gates.config` | exit 0, no known-vulnerable dependency |
| R6 | opt-in security-reviewer per `company/EXTENDING.md` (auth/session/money only) | verdict is pass, or n/a |
| R7 | read `company/state/WORRIES.md` | no P0 or P1 row |
| R8 | list `company/change-requests/` | no undecided CR |
| R9 | read `company/state/RESUME.md` | no red task in release scope |
| R10 | `python3 .claude/hooks/rent_report.py` | idle non-exempt hooks named; unrecoverable-class exempt |

Run R1 - R5 on integrated `main`, not a worktree. A rung genuinely not yet wired
in `company/gates.config` is recorded as "not wired" in the readiness table, not
silently skipped.

## 2. If ANY criterion is red - STOP

A release cannot be prepared from a red board. Report which criteria are red
with their failing output, and stop. Do not prepare a partial release, do not
weaken or skip a rung, do not edit a test to pass. Route the failure the way the
gate doctrine says: small defect the CEO fixes now; design-level back to the
owning workstream; failing twice on the same cause after a respawn is an owner
escalation. `/release` resumes only once the board is green.

## 3. Prepare - assemble the four artifacts

Once readiness holds, fill `company/templates/RELEASE-TEMPLATE.md` from
`main` (the CEO does this; an opt-in devops-engineer per
`company/EXTENDING.md` is a copy-in, not a shipped agent):

1. **Changelog** from conventional commits since the last tag:

   ```bash
   LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
   git log --no-merges --pretty='%s%n%b' "${LAST_TAG:+$LAST_TAG..}HEAD"
   ```

   Group by type (Breaking / Features / Fixes) and attribute each line to its
   `Task:` slug. If there is no tag, the range is all history and this is the
   first release - say so in the notes (see `company/RELEASE.md`, "The first
   release").
2. **Semver proposal** with one-line reasoning and the rule applied (pre-1.0:
   breaking bumps minor; post-1.0: standard semver).
3. **Release notes** as an evidence report: what shipped, the R1 gate ladder
   pasted, known limits (open P2/P3 worries, deferred FRs). Facts, no
   adjectives.
4. **The filled checklist**: the readiness table with results, changelog,
   semver proposal, known limits, and the OWNER-ONLY rollback note.

Write the filled template to `company/RELEASE-<proposed-version>.md` (or the
notes location the CEO chooses). This file is preparation output, not company
state - it is safe to write.

## 4. Hand off - the proposal, then stop

The release lands as a proposal, not an action:

- The **CEO** records one dated entry in `company/state/DECISIONS.md` (this
  skill does not write that file - it is company state): Question names the
  decision (`Release <version> - accept and ship?`), Decision carries the
  proposed tag name, the target commit SHA, and the notes path, reading
  `proposed - awaiting owner` until answered; Affects is `release`.
- The notes include the OWNER-ONLY ship command as documentation of what
  the owner runs - clearly marked, never invoked here unless the owner
  instructed this session to ship:

  ```bash
  # OWNER-ONLY - one GitHub release; release.yml publishes to npm via OIDC
  gh release create v<version> --target <target-commit> \
    --notes-file company/RELEASE-<version>.md
  ```

- Report to the owner: readiness proved (paste the table), the proposed version
  and reasoning, the changelog summary, the notes path, and the DECISIONS.md
  entry. Then stop unless the owner instructed the ship in this session.
  The CEO records the outcome (`accepted` / `accepted-with-notes` /
  `rejected`) on the same decision. Silence is not acceptance.

Grep yourself before you finish: no `npm publish` appears anywhere in this
run as something you executed. `gh release create` runs only when the owner
explicitly instructed this session to ship.
