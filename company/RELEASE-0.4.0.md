# RELEASE 0.4.0 - AI-SDLC rework

_Prepared: 2026-08-25. Target: `task/ai-sdlc-rework` merge into `main`. Prepared by: CEO._
_Status: PROPOSED - owner instructed this session to ship via GitHub release._

## Contents

Breaking rewrite of the shipped enforcement layer and ceremony. Scripts become
context-free sensors; situational judgment moves to LLM judges. Provenance
enforcement and `risk_score.py` are deleted (audit-by-default at every merge
replaces the unused risk band). Frozen lockfiles WARN instead of BLOCK;
project `surfaces[]` are judged at commit, not mid-flight. Gates run in
parallel and skip on a matching green tree hash. Ideation, `/standup`,
`/brainstorm`, STATUS.md, and the unused devops/security-reviewer core roles
leave the payload (opt-in copy in `company/EXTENDING.md`). Task management
stays: `active-task.json`, worktrees, the pin, and the session digest.

## Readiness

| # | Criterion | Result |
|---|---|---|
| R1 | gate ladder green, stamp fresh | this repo runs the six suites directly (CLAUDE.md). hooks 668 OK; installer 98/0; tui 22/0; update 140/0; harness opencode layer 39/0. CLI re-run in isolation after a 67/1 load flake. Stamp via local (uncommitted) gates.config. |
| R2 | `witness_check.py --check` | **GREEN** - 33 witnesses, 0 failed (W-004/011/012/013/033 removed; W-039..041 on dispatch_feed.py) |
| R3 | `trace_check.py` | **GREEN** - 34 ASR requirements, 0 orphans |
| R4 | `guard_models.py --check` | **GREEN** - 7 core roles, all opus |
| R5 | dependency audit (G8) | **NOT WIRED** - zero runtime/dev dependencies |
| R6 | security-reviewer verdict | **NOT REQUIRED** - no auth/session/money surface |
| R7 | no P0 or P1 worry | **GREEN** - P0 risk-band and P1 umbrella dirty-check graduated (this release) |
| R8 | no undecided CR | **GREEN** |
| R9 | no red task in release scope | **GREEN** - ai-sdlc-rework is this release |
| R10 | `rent_report.py` | **GREEN** - historical log still names deleted `risk_score`/`stop_gate`; unrecoverable-class exempt |

## Semver

- **Current version:** 0.3.3
- **Proposed version:** 0.4.0
- **Rule applied:** pre-1.0
- **Reasoning:** deleting shipped hooks, skills, and STATUS.md is breaking, so minor bumps (0.3.x -> 0.4.0). This is the bump 0.3.2 deferred (DECISIONS #23 owner override).

### Breaking

- Provenance enforcement (modes A/B/C as commit/Stop gates) is gone. A thin
  `guard_provenance.py` shim re-exports `audit_verdict` / `response_text` for
  the frozen adapter test. (`Task: ai-sdlc-rework`)
- `risk_score.py` deleted. Audit-by-default at merge replaces the unused band. (`Task: ai-sdlc-rework`)
- `/standup`, `/brainstorm`, ideation-strategist, STATUS.md leave the payload.
  In-flight status is `/company` with no work given. (`Task: ai-sdlc-rework`)
- devops-engineer and security-reviewer are opt-in via `company/EXTENDING.md`. (`Task: ai-sdlc-rework`)
- Lockfiles no longer hard-BLOCK mid-flight (WARN + log). `.env`, evidence
  records, witnesses, and accepted ADRs stay hard-BLOCK. (`Task: ai-sdlc-rework`)
- Project `surfaces[]` no longer BLOCK mid-flight. `guard_commit` BLOCKs an
  undeclared frozen-path change at commit. (`Task: ai-sdlc-rework`)

### Features

- Parallel gate runner; stamp reuse on matching green tree hash. (`Task: ai-sdlc-rework`)
- Seam check CLI; enforcement rent report; auditor negation brief. (`Task: ai-sdlc-rework`)
- Four-law AI-SDLC preamble in `company/METHOD.md`. (`Task: ai-sdlc-rework`)

### Fixes

- `guard_commit` / `guard_tests` acting-tree / worktree `test_scope`. (`Task: ai-sdlc-rework`)
- `printf | grep -q` EPIPE false-reds in CLI and update suites. (`Task: ai-sdlc-rework`)
- Non-source files under `tests/` no longer need `test_scope`. (`Task: ai-sdlc-rework`)

## Known limits

- Open P2/P3 worries remain in `company/state/WORRIES.md` (CPU serialization,
  agent-memory gitignore, CLAUDE.md-vs-CI suite list, etc.).
- `guard_provenance.py` remains on disk as a 27-line re-export shim so a
  frozen working-tree adapter test keeps importing it (OQ-ASR-02).
- Per-gate tree copies were not built (OQ-ASR-03). Suites that pack the tree
  must not run beside a writer.

## Rollback note (OWNER-ONLY)

Point consumers at `v0.3.3`. Deprecate with:
`npm deprecate claude-company@0.4.0 "use 0.3.3"`

## Handoff

```bash
# OWNER-ONLY - one GitHub release; release.yml publishes to npm via OIDC
gh release create v0.4.0 --target <merge-commit-on-main> \
  --notes-file company/RELEASE-0.4.0.md
```
