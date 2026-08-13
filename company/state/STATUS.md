# STATUS - the current-truth board

_Maintained by the CEO. Updated after every dispatch, merge, and CR decision._
_Red stays red until proven green. Never average a status._

_Last updated: 2026-08-13 - harness-port program STARTED (six workstreams, two waves). v0.2.6 remains registry latest._

## Active tasks

| Task | Class | Lead/Agent | State | Gates | Notes |
|---|---|---|---|---|---|
| harness-port | program | CEO + 3 leads (wave 1) | PHASE 0 - spec in progress, wave 1 worktrees cut | baseline green: hooks 393, npm test | Ports the verified changes from the DevMesh fork back upstream. Six workstreams: L1 kernel (#98), L2 guards (#99), L3 runner (#97) in wave 1; L4 state-writers (#100), L5 provenance-scope (#101), L6 stop_gate + doctrine (#102) in wave 2. Source catalog is DevMesh company/harness-changes-2026-08-12.md, but the fork diff found MORE than the catalog lists: four undocumented correctness fixes worth porting (git subcommand parsing escape, secrets parser divergence, is_source exempt-dir over-matching, substring verdict parser) and four changes that must NOT be ported (repo-scoped cached skips, tree_hashes stamp keying, model tiering, the line-count audit waiver). THREE OWNER DECISIONS PARKED, none blocking wave 1: merge-only stamp gating, a risk-scaled audit band, and the Phase 0 spec-lite rung - all three amend METHOD mechanisms rather than fix defects. |
| v0.2.6 release | release | CEO | PUBLISHED 2026-07-29 | release workflow green (re-ran the full suite incl. the update tests); registry latest = 0.2.6; SLSA provenance via OIDC trusted publishing; tag v0.2.6 at 6d2b9b1 | Carries multi-session-tasks (PR #93) plus the CI coverage fix below. Two readiness criteria were RED and the owner ACCEPTED both rather than holding: R7 (two open P1 worries - the guard_commit worktree row and the provenance verdict-parser row) and R3 (trace_check exits 0 but reports 27 orphan MST requirement IDs with no code or test citation). Neither is a defect in what users install; both are recorded rather than waived. |
| ci-update-suite-gap | quick | CEO (self) | SHIPPED with the v0.2.6 close-out | covered by the same ladder run | Found at close-out: neither ci.yml nor release.yml ran tests/install/test_update.sh. Its 139 cases - including the ENTIRE FR-MST-29 legacy field-install rollout proof that multi-session-tasks was verified by - were reachable only through package.json prepublishOnly, so they never ran on a PR. Same class as the W-030 run_tests.sh direct-exec hole, second instance. Both workflows now run it as an explicit step. |
| release-npm-pin | quick | CEO (self) | SHIPPED 2026-07-26 (PR #87 merged e86860f) | CI 9/9; hooks 224 + npm test green, stamped | release.yml pinned node 20 but installed UNPINNED npm@latest. npm 12.0.1 requires node >=22.22.2, so the v0.2.5 publish died EBADENGINE before any test ran. Nothing in the repo changed - npm drift alone broke it, and it would have broken every future release. Now pinned to npm@^11.5.1 (resolves 11.18.0, engine ^20.17.0 || >=22.9.0, above the 11.5.1 trusted-publishing floor). |
| v0.2.5 release | release | CEO | PUBLISHED 2026-07-26 | publish workflow success; registry latest = 0.2.5; SLSA provenance attached | Tag v0.2.5 at e86860f. NOTE: an earlier v0.2.5 tag at d60db11 was cut before the npm pin and failed to publish; it was deleted and re-cut once the registry was confirmed never to have received it. Published tarball verified clean: NO company/state directory, 81 files. |
| pack-state-leak | quick | CEO (self, audited SHIP) | SHIPPED 2026-07-26 (PR #86 merged d60db11); released in v0.2.5 | integrated main green: hooks 224, CLI 62/0, install 96/0, TUI 21/0, update 123/0; CI 9/9 | package.json negated only specs/briefs/change-requests, so company/state/{RESUME,STATUS,WORRIES,DECISIONS}.md shipped in every tarball through 0.2.4. Leak never reached a user project - install.sh scaffolds its own stubs and never copies packaged ones (0.2.4 install yields 77-83 byte stubs), so it was confined to the registry tarball and node_modules. Pack diff vs 0.2.4 is exactly 4 files removed, 85 -> 81. Also closes the dirty-publish hole for the untracked runtime files. Regression assertion proven load-bearing (62/0 -> 61/1 without the negation). |
| test-infra-closeout | quick | CEO | SHIPPED 2026-07-26 (PR #86 merged d60db11) | as above | Witnesses W-029/W-030/W-031 recorded (registry 30/30); all briefs archived to shipped/; spec-multi-session-tasks.md landed on main. |
| test-infra-fixes | quick | CEO (self, audited) | SHIPPED 2026-07-26 (PR #85 merged 65bd070) | 224 hooks + 61 CLI + 96 install green on integrated main and stamped; CI 9/9 across ubuntu+macos x node 18/20/22; ubuntu log confirms "Ran 224 tests OK" | Two one-line test-infra defects. (1) CI ran 103 of 224 hook tests - run_tests.sh exec'd test_hooks.py directly, so 121 tests incl. all of test_guard_provenance never ran in CI. (2) npm test was RED on main - pack-manifest JSON parse broken by the npm 10.5.0 prepare banner on stdout, 10 dead assertions. Blocks everything downstream: a red local gate means no stamp, no commit. |
| multi-session-tasks | feature | tech-lead (1 workstream, own developers) | SHIPPED 2026-07-27 (PR #93 merged 171421f, closes #89-#92); close-out 2026-07-29 | CEO independent re-verification on integrated main 2026-07-29: hooks 393 OK, npm test 62/0, install 96/0, update 139/0; CI 9/9 on the PR; witnesses 32/32; guard_models --check clean | Target release 0.2.6. active-task.json becomes N entries in one file so parallel sessions in one checkout stop overwriting each other; provenance ledger stops wiping itself on slug change. Plan approved by owner 2026-07-26, core-only scope. Phase 0 done: company/specs/spec-multi-session-tasks.md, 31 FRs / 11 BRs / 10 OQs, all fallbacks decided. Tracking issues #89 (normalizer + call-site migration), #90 (ledger v2 - fixes the reported bug alone), #91 (multi-task gate semantics), #92 (doctrine + witnesses + rollout proof). Sealed brief company/briefs/brief-multi-session-tasks.md, execution=delegated. PM caught a real hole in the approved plan: "ALL over non-hotfix entries" is vacuously TRUE on an empty list, which would have silently flipped guard_spec from block to ALLOW when no task is active - FR-MST-05 orders the empty check first. OUTCOME: the pre-empted dispatch hazard did NOT bite - the lead committed both bands from the worktree itself (77ba45f, 4402ee6) and the ledger records self_authored=0, so the work never became self-authored and the mandatory-audit path never armed. That is evidence the P1 guard_commit.git_cwd row may be narrower than recorded; it stays P1 until deliberately re-probed. NO auditor pass was run on this diff - the trigger never fired and the CEO did not dispatch one; verification rests on the CEO's own re-run of all four suites plus CI 9/9. |
| spawn-depth-shipping | quick | developer | SHIPPED 2026-07-23 (PR #83 merged 6061814, closes #79-#82) | 224 hooks + 61 CLI + 123 engine green (dev AND CEO reruns); integrated main stamped | Template ships env CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2; install/update merge env additively (user pin survives - proven); witness W-029. NOT yet on npm - registry still 0.2.0; owner has v0.2.2 tag+publish pending, and this lands in the NEXT release after that. |
| release-0.2.3 | release | CEO | PUBLISHED 2026-07-25 - CLOSED | integrated main green + stamped; CI 9/9 | Registry latest = 0.2.3 (published 2026-07-25T16:17Z); tags v0.2.0-v0.2.3 all on origin. The earlier "AWAITING OWNER TAG" state was stale bookkeeping - verified 2026-07-26 against `npm view claude-company versions`. Published tarball carries company/state/{RESUME,STATUS,WORRIES,DECISIONS}.md but NOT the runtime state files. DECISIONS #12-#14. |

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
