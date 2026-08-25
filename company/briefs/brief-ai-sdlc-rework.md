# BRIEF: ai-sdlc-rework

_Type: program-workstream. Spec: company/specs/spec-ai-sdlc-rework.md.
Lead: direct-developer. Date: 2026-08-25._

> Frozen `surfaces[]` are judged at commit (`guard_commit` undeclared-drift
> BLOCK), not mid-flight. `always[]` unrecoverable artifacts stay hard-BLOCK
> via `guard_frozen`. Do not hand-edit `company/witnesses.json`.

Implement company/specs/spec-ai-sdlc-rework.md end to end. Do not commit or
branch. Do not touch company/gates.config, company/specs/spec-harness-agnostic.md,
tests/harness/test_adapter.mjs, or company/state/.state.lock.

## Mission

Ship the AI-SDLC rework: prune hooks that fought the work, convert recoverable
mid-flight BLOCKs to WARN/ALLOW with named decision-table tests, run gates in
parallel with stamp reuse, add rent/seam/falsification mechanisms, align
prompts, cut unused payload, and leave a working tree whose six CLAUDE.md
suites and trace_check (zero orphan ASR IDs) can be audited independently.

Hard constraint: dual-nature company/ stays generic; tracked gates.config
keeps CONFIGURE ME placeholders. Writing is hook-clean (straight quotes,
" - ", three dots).

## Read first (in order)
1. CLAUDE.md
2. company/METHOD.md
3. company/specs/spec-ai-sdlc-rework.md
4. .claude/hooks/_common.py, guard_frozen.py, guard_commit.py, guard_tests.py,
   guard_models.py, dispatch_feed.py, guard_provenance.py (shim)
5. company/run-gates.sh

## You own
- `.claude/hooks/`
- `.claude/agents/`
- `.claude/skills/`
- `company/`
- `lib/`
- `install.sh`
- `update.sh`
- `package.json`
- `tests/hooks/`
- `tests/install/`
- `tests/cli/`
- `tests/harness/` (except `tests/harness/test_adapter.mjs`)

Nothing else. `.opencode/` is regenerated only via `node lib/render-opencode.js`.

## Invariants in play (must not break)
- Dual-nature company/; fail-open hooks; checksum-sealed witnesses via CLI only
- Accepted ADR immutability; content-based freshness (ADR-0002)
- CLAUDE.md six suites; no_slop; DECISIONS #1 no model tiering
- Frozen test_adapter.mjs still imports guard_provenance.audit_verdict

## Frozen surfaces nearby (CR, never edit)
- company/witnesses.json: mutate only via witness_check.py --add/--remove
- company/state/adherence.log and gate artifacts: do not truncate
- surfaces[] is empty in this repo; always[] unrecoverable set stays BLOCK

## Scope (ordered)
1. Finish hook deletions and _common sweep (FR-ASR-02, FR-ASR-03, FR-ASR-04).
   Oracle: `rg risk_score` over live hooks/skills/agents/company/*.md is empty
   of load-bearing refs; settings.json has zero guard_provenance commands.
2. Finish hook fixes (FR-ASR-05..08) with BR-ASR-01..05 decision-table rows.
   Oracle: named tests in tests/hooks fail if an ALLOW cell re-BLOCKs.
3. Gate runner parallel + early-exit + pipefail (FR-ASR-09..11, BR-ASR-06).
   Oracle: test_update.sh and test_cli.sh contain zero `printf | grep -q`;
   BR-ASR-06 table covers skip vs RUN.
4. rent_report.py and seam_check.py (FR-ASR-12, FR-ASR-13). Oracle: CLI tests
   plus RELEASE.md / gates skill mention rent_report.
5. Auditor rewrite, prompt alignment, METHOD/COMPANY, templates
   (FR-ASR-14..18). Oracle: rg over live agents/skills for STATUS.md, ideation,
   standup, risk_score, stop_gate as live runbook refs returns none.
6. Payload cuts (FR-ASR-19): delete IDEATION, ideation-strategist, brainstorm,
   standup, devops-engineer, security-reviewer, STATUS.md; add EXTENDING.md;
   update payload lists, models.json, install scaffolding.
   Oracle: install/CLI tests want_absent those paths; session_start digests
   RESUME only.
7. Tests, witnesses via CLI, opencode regen, six suites, trace_check
   (FR-ASR-20..22, BR-ASR-10..11). Oracle: six suites pasted; trace_check zero
   orphan ASR IDs; witness_check green.

## Integration seams
- Frozen adapter test: keep thin guard_provenance.py shim (OQ-ASR-02).
- Install/update tests: rewrite provenance fanout and STATUS scaffolding
  expectations; do not heal-restore provenance as a hook.

## Definition of Done
- [ ] Every FR-ASR implemented, tested, or deferred with reason
- [ ] Six CLAUDE.md suites run; results pasted honestly
- [ ] trace_check.py --spec company/specs/spec-ai-sdlc-rework.md zero orphans
- [ ] BR-ASR-01..06 named decision-table methods exist
- [ ] Tests of deleted behavior deleted
- [ ] No commit, no branch
- [ ] Witnesses only via witness_check.py

## Fallback assumptions
- OQ-ASR-01: dispatch feed in dispatch_feed.py not _common.py.
- OQ-ASR-02: thin guard_provenance.py re-export shim; no hook wiring.
- OQ-ASR-03: no per-gate tree copies; isolate stdout/logs only.
- OQ-ASR-04: CR names a path if any file under company/change-requests/
  contains the project-relative path as a substring.
- OQ-ASR-05: early-exit does not rewrite the stamp; gates.log reused=1.
- OQ-ASR-06: rent_report window default is whole log; optional --days N.
- OQ-ASR-07: CEO restart after three lead reports or when losing the plot.
- OQ-ASR-08: auditor attempt budget is three, then report what remains.
- OQ-ASR-09: omit empty Stop/PostToolUse groups from settings.json.
- OQ-ASR-10: leave user STATUS.md on disk; do not scaffold; session_start
  ignores it.

## Out of scope
- Committing or branching
- Touching the four frozen uncommitted files from the other session
- Model tiering, deleting qa-engineer, rebuilding provenance enforcement
- Per-gate full-tree copies

## Report back
Paths changed grouped by work item; six suite results pasted; trace_check;
every BR test row (BR ID -> test name); witnesses updated; deviations;
anything the plan got wrong.
