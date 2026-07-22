# STATUS - the current-truth board

_Maintained by the CEO. Updated after every dispatch, merge, and CR decision._
_Red stays red until proven green. Never average a status._

_Last updated: 2026-07-22 - model-routing-arming SHIPPED (PR #77 merged cd07fb6, acceptance DECISIONS #11); release 0.2.2 prepped._

## Active tasks

| Task | Class | Lead/Agent | State | Gates | Notes |
|---|---|---|---|---|---|
| release-0.2.2 | release | CEO | PREPPED, AWAITING OWNER TAG + PUBLISH | integrated main green (222 hooks + 61 CLI + 111 engine), trace 21/21, witnesses 27/27 | Rolls up unpublished 0.2.1 + #77 (model-routing arming). Owner: tag v0.2.2 at the release-PR merge commit, publish from clean tag clone (link-based 2FA, owner-manual per memory npm-publish-owner-only). Registry still on 0.2.0. |

## Shipped (recent)

| Task | Date | Evidence |
|---|---|---|
| model-routing-arming | 2026-07-22 | PR #77 merged cd07fb6 (closes #74-#76); acceptance DECISIONS #11; witnesses W-026/W-027/W-028; live certification: builtin contradict/bare spawn exit 2, match 0, dormancy probe turns --check red; migration: builtins merge lands on install AND update automatically. |

## Wave position (programs only)

| Wave | Workstreams | State | Exit criteria status |
|---|---|---|---|
| adoption program 1-3 | all | SHIPPED 2026-07-10 | PRs 27/33/34/32/35 merged; acceptance DECISIONS #3 |
| follow-up pair | docs-sync + adr-hardening | SHIPPED 2026-07-10 | PRs 38/39/40/41 merged; #28 + #31 closed; witnesses 10/10 on main |
| cli-update | single workstream | SHIPPED 2026-07-15 | PR #57 merged (7726c99, closes #54-#56); integrated main 213+40+56 green; witnesses W-014..W-016; acceptance DECISIONS #6 |
| cli-self-update | single workstream | SHIPPED 2026-07-15 | PR #60 merged (a09b463, closes #59); integrated main 213+57 green; witnesses W-017..W-018 (landed via PR #62); acceptance DECISIONS #7 |
| v0.2.0 npm release | release | PUBLISHED 2026-07-15 | PR #61 merged, tag v0.2.0 (5913374), owner published manually (link-based 2FA); registry latest=0.2.0; DECISIONS #8 |
| provenance-shipping | quick fix | SHIPPED 2026-07-15 | PR #65 merged (d624cc3, closes #64); fresh installs arm the delegation enforcer, update never auto-arms; witnesses W-019/W-020; NOTE: 0.2.0 on npm still has the gap - 0.2.1 patch release recommended (owner button) |
| settings-merger-fix | quick fix | SHIPPED 2026-07-15 | PR #69 merged (f17c3c4, closes #67); dedup per (matcher, command) in both engines; update HEALS broken field installs (hand-proven); witnesses W-021/W-022. DevMesh hand-patched meanwhile (its c1ecbf7) |
| pack-leak-fix | quick fix | SHIPPED 2026-07-15 | PR #71 merged (d714892, closes #68); record trees scaffold empty + tarball negations; seeded negative test; witnesses W-023/W-024 |
| devmesh-migration | consulting | DELIVERED 2026-07-15 | DevMesh polyrepo migrated to claude-company (its commits b3f0a47/7e08247/c1ecbf7): docs/team ported to company/, frozen registry live (6 surfaces probe-verified), make-gates mirrored, custom agents/skills/memory preserved, 2 upstream bugs found (#67/#68 - both now fixed) |

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
