# STATUS - the current-truth board

_Maintained by the CEO. Updated after every dispatch, merge, and CR decision._
_Red stays red until proven green. Never average a status._

_Last updated: 2026-07-10 - delegation-enforcement dispatched (tech-lead)._

## Active tasks

| Task | Class | Lead/Agent | State | Gates | Notes |
|---|---|---|---|---|---|
| - | - | - | - | - | - |

## Wave position (programs only)

| Wave | Workstreams | State | Exit criteria status |
|---|---|---|---|
| adoption program 1-3 | all | SHIPPED 2026-07-10 | PRs 27/33/34/32/35 merged; acceptance DECISIONS #3 |
| follow-up pair | docs-sync + adr-hardening | SHIPPED 2026-07-10 | PRs 38/39/40/41 merged; #28 + #31 closed; witnesses 10/10 on main |

## Open CRs

_Next free CR number: CR-1._

| CR | Surface | Status | Disposition |
|---|---|---|---|
| - | - | - | - |

## Risks / decisions needed (owner-facing)

1. Two bugs found while integrating, filed and open: #36 (audit gate
   proposal fails ENOLOCK on lockfile-less repos) and #37 (guard_commit
   stamp check reads the main checkout, not the commit's work tree - also
   documents that dispatched subagents cannot commit in worktrees at all;
   the CEO landed both commits this round). Both are small, scoped, and
   good next tasks.
2. Deferred by owner: lessons loop, loop workers, model tiering.
   Pre-existing roadmap issues #1-#11 untouched.
