# STATUS - the current-truth board

_Maintained by the CEO. Updated after every dispatch, merge, and CR decision._
_Red stays red until proven green. Never average a status._

_Last updated: 2026-07-15 - cli-update SHIPPED (PR #57 merged 7726c99, acceptance DECISIONS #6)._

## Active tasks

| Task | Class | Lead/Agent | State | Gates | Notes |
|---|---|---|---|---|---|
| delegation-gate-md-writes | exploration | CEO (read-only) | INVESTIGATING | n/a | Owner question: does the compulsory delegation gate wrongly block non-code agents (PM, docs-librarian, auditor) from writing md/state json? No code - findings report only. |

## Wave position (programs only)

| Wave | Workstreams | State | Exit criteria status |
|---|---|---|---|
| adoption program 1-3 | all | SHIPPED 2026-07-10 | PRs 27/33/34/32/35 merged; acceptance DECISIONS #3 |
| follow-up pair | docs-sync + adr-hardening | SHIPPED 2026-07-10 | PRs 38/39/40/41 merged; #28 + #31 closed; witnesses 10/10 on main |
| cli-update | single workstream | SHIPPED 2026-07-15 | PR #57 merged (7726c99, closes #54-#56); integrated main 213+40+56 green; witnesses W-014..W-016; acceptance DECISIONS #6 |

## Open CRs

_Next free CR number: CR-2._

| CR | Surface | Status | Disposition |
|---|---|---|---|
| CR-UPD-1 | frozen-surfaces.json `always` list | APPROVED | Freeze install-manifest.json + .update-backups/**; CEO applies in the cli-update build PR (issue #56) |

## Risks / decisions needed (owner-facing)

1. Two bugs found while integrating, filed and open: #36 (audit gate
   proposal fails ENOLOCK on lockfile-less repos) and #37 (guard_commit
   stamp check reads the main checkout, not the commit's work tree - also
   documents that dispatched subagents cannot commit in worktrees at all;
   the CEO landed both commits this round). Both are small, scoped, and
   good next tasks.
2. Deferred by owner: lessons loop, loop workers, model tiering.
   Pre-existing roadmap issues #1-#11 untouched.
