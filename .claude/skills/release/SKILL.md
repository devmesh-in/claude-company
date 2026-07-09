---
name: release
description: Prepare a release for the owner to ship - verify the readiness list mechanically, then assemble the changelog, semver proposal, and release notes into the filled RELEASE-TEMPLATE, ending at a proposal entry on DECISIONS.md. Owner/CEO invoked only. Use when the user says /release, "prepare a release", "cut a release", or "are we ready to ship". It NEVER tags, publishes, or deploys - deploy is a manual owner step, always.
disable-model-invocation: true
---

# /release - prepare a release, hand it to the owner

You are the CEO (or the devops-engineer acting under the CEO) preparing a
release. You are running this because the owner asked for it - never on your own
initiative. `company/RELEASE.md` is the doctrine; read it first if this session
has not, then `company/GATES.md` for the ladder the readiness list cites.

**The boundary that outranks everything here:** you PREPARE a release; the owner
SHIPS it. This skill never runs `git tag`, never pushes a tag, never runs
`npm publish`, never deploys, and never instructs an agent to. It ends at a
proposal on `company/state/DECISIONS.md`. If any step tempts you toward a ship
command, stop - that is the owner's button (escalation-list item 3 in
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
| R6 | security-reviewer verdict (only if the release touches auth/session/money) | verdict is pass |
| R7 | read `company/state/WORRIES.md` | no P0 or P1 row |
| R8 | list `company/change-requests/` | no undecided CR |
| R9 | read `company/state/STATUS.md` | no red task in release scope |

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

Once readiness holds, dispatch (or act as) the **devops-engineer** to fill
`company/templates/RELEASE-TEMPLATE.md` from `main`:

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
- The notes include the OWNER-ONLY ship commands as documentation of what the
  owner runs - clearly marked, never invoked here:

  ```bash
  # OWNER-ONLY - the company never runs these
  git tag -a v<version> <target-commit> -m "v<version>"
  git push origin v<version>
  npm publish            # or the project's publish/deploy step
  ```

- Report to the owner: readiness proved (paste the table), the proposed version
  and reasoning, the changelog summary, the notes path, and the DECISIONS.md
  entry. Then stop. The owner tags and publishes; the CEO records the outcome
  (`accepted` / `accepted-with-notes` / `rejected`) on the same decision.
  Silence is not acceptance.

Grep yourself before you finish: no `git tag`, `git push` of a tag, or
`npm publish` appears anywhere in this run as something you executed - only
inside OWNER-ONLY documentation blocks.
