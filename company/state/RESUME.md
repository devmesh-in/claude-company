# RESUME / HANDOFF - read this first

_The restart point. Sessions die; work must not. The CEO updates this after
every spawn, merge, CR decision, and agent report. If a session died mid-flight,
check each worktree's git log before respawning - work may be complete on disk
without a report._

## 1. Program state at handoff

Adoption program SHIPPED 2026-07-10. Merged: #27 (wave 1), #33 (wave 2 enforce, ex-#29), #34 (wave 2 doctrine,
ex-#30), #32 (wave 3), #35 (close-out). Integrated main verified: 147 hook
tests + 31 CLI green, witness registry 9/9, gates_detect proposes
witnesses/models/tests/audit. Owner acceptance recorded (DECISIONS #3).

## 2. Next actions, in order

000000. v0.2.5 PUBLISHED 2026-07-26. Registry latest = 0.2.5, SLSA provenance
   attached, published tarball verified to contain NO company/state directory
   (81 files). main = e86860f. Three things landed in it:
   (a) pack-state-leak (PR #86, d60db11): package.json negated only specs/
       briefs/change-requests, so company/state/{RESUME,STATUS,WORRIES,
       DECISIONS}.md shipped in every tarball through 0.2.4. The leak NEVER
       reached a user project - install.sh scaffolds its own stubs and never
       copies packaged ones (a 0.2.4 install yields 77-83 byte stubs), so it
       was confined to the registry tarball and node_modules. Also closes the
       dirty-publish hole for the untracked runtime files.
   (b) test-infra-fixes (PR #85, 65bd070): CI ran 103 of 224 hook tests;
       pack-manifest assertions were dead under npm 10.5.0.
   (c) release-npm-pin (PR #87, e86860f): the publish workflow installed
       UNPINNED npm@latest against pinned node 20. npm 12 raised its node
       floor to 22.22.2, so the first v0.2.5 publish died EBADENGINE before
       any test ran. Now npm@^11.5.1.
   RETAG NOTE: the first v0.2.5 tag (at d60db11) predated the pin and failed
   to publish. It was deleted and re-cut at e86860f only after confirming the
   registry never received it. 0.2.3 and 0.2.4 remain published WITH the
   board inside them - deprecating them is an open owner decision.
   NEXT: multi-session-tasks. The spec is on main at
   company/specs/spec-multi-session-tasks.md (31 FRs / 11 BRs / 10 OQs, all
   fallbacks decided). Still needed before dispatch: tracking issues (PR mode
   blocks a feature spawn without them) and the sealed brief. Owner decision
   still open on whether to fold the P1 worktree-commit bug into it.
   PROMPT HYGIENE THAT MATTERS: never write the negative verdict token in an
   auditor prompt - the provenance parser substring-matches it and records a
   passing audit as its opposite. Use SHIP / SHIP-WITH-FIXES / HALT. And a
   re-audit must be a FRESH Task dispatch: SendMessage resumption records no
   provenance at all.

00000. test-infra-fixes SHIPPED 2026-07-26 (PR #85 merged 65bd070).
   Self-authored by the CEO in the main checkout, auditor verdict SHIP,
   CI 9/9 green across ubuntu+macos x node 18/20/22. Integrated main
   re-verified by the CEO: hooks 224, npm test 61/0, install 96/0, all
   stamped. Ubuntu job log confirms `Ran 224 tests ... OK` - the 121
   previously-invisible tests passed on their first ever CI run.
   Two defects, both found while scoping the multi-session engagement:
   (a) tests/hooks/run_tests.sh exec'd test_hooks.py directly, so CI ran
       103 of 224 hook tests - the other 121, including ALL of
       test_guard_provenance.py, never ran in CI. Now unittest discover
       with -v (the -v preserves the per-test CI log lines that
       unittest.main(verbosity=2) used to give).
   (b) npm test was RED ON MAIN: tests/cli/test_cli.sh piped
       `npm pack --dry-run --json` into JSON.parse, and npm 10.5.0 writes
       the prepare lifecycle banner to STDOUT, so all 10 pack-manifest
       assertions were dead (PASS 51 / FAIL 10). --silent fixes it;
       --ignore-scripts does NOT. Auditor proved the packed file list is
       byte-identical across npm 9/10/11 (91 files).
   RELEASE FACTS CORRECTED 2026-07-26: v0.2.3 is ALREADY PUBLISHED on npm
   (2026-07-25T16:17Z). Prior RESUME/STATUS claims that the registry sat
   at 0.2.0 awaiting an owner tag were STALE - the owner had already
   tagged and published. Registry versions: 0.1.0, 0.1.1, 0.2.0, 0.2.3.
   Nothing needs publishing for the test-infra work: tests/ is not in the
   pack list and company/briefs/** is excluded, so the tarball is
   unchanged by it.
   NEW P2 WORRY - the pack list excludes company/specs|briefs|
   change-requests but NOT company/state, so company/state/{RESUME,STATUS,
   WORRIES,DECISIONS}.md ship into every install. Verified against the
   live 0.2.3 tarball: those four ARE in it. The runtime files
   (costs.log, provenance-ledger.json, active-task.json, .cost-cursor.json,
   gates.status) are untracked, so a CLEAN-CLONE publish leaves them out -
   but publishing from a dirty working checkout WOULD leak them. Always
   publish from a clean clone at the tag.
   Next: multi-session-tasks (feature) - plan approved by the owner
   2026-07-26 at ~/.claude/plans/flickering-painting-pony.md, core-only
   scope. active-task.json becomes N entries; the provenance ledger stops
   wiping itself on slug change. Phase 0 spec via product-manager first.
   NEW P1 WORRY, directly in scope for that engagement: dispatched
   worktree agents CANNOT COMMIT - guard_commit judges them to be on main
   because the harness pins payload cwd to the main checkout. That turns
   every delegated build into self-authored work needing an audit.

0000. spawn-depth-shipping SHIPPED 2026-07-23 (PR #83 merged 6061814,
   closes #79-#82; witness W-029; brief archived pending next chore
   pass - it is tracked at company/briefs/brief-spawn-depth-shipping.md
   on main, move to shipped/ with the next closeout PR). CC 2.1.21
   defaulted subagent spawn depth to 1 (flattens CEO->lead->dev);
   template now ships env CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH="2" and
   install/update merge env additively (user values win, non-dict env
   replaced-safe, heredocs byte-identical 3587 chars). CEO independent
   verification: 224/61/123 all green, own merge probes (pin "3"
   survives, bare heals to "2"), risk low. This session armed via
   settings.local.json; memory file spawn-depth-env-required.md saved.
   guard_tests test_scope papercut hit a THIRD time (see WORRIES P2).
   NOTE: not on npm until the release AFTER v0.2.2 - owner still owes
   the v0.2.2 tag+publish (DECISIONS #12), then a v0.2.3 can carry
   spawn-depth.
000. model-routing-arming SHIPPED 2026-07-22 (PR #77 merged cd07fb6,
   closes #74-#76; acceptance DECISIONS #11; witnesses W-026 wiring
   assertion / W-027 merge byte-identity / W-028 bare-builtin block).
   Integrated main verified by CEO: hooks 222 OK, npm 61, update
   engine 111, --check 0, trace 21/21 after citation fix, live
   certification (contradict/bare exit 2, match 0; dormancy probe:
   Task|Agent group stripped -> --check exit 1 + fix-it). Worktree
   and task branch removed; brief+spec archived to shipped/.
   RELEASE 0.2.2 MERGED (PR #78, merge commit ad3dda8; task
   release-0.2.2-closeout closed; audits recorded approved after the
   verdict-parser workaround - see WORRIES P2). Integrated main green
   + stamped (223/61/111), registry sealed 27/27. AWAITING OWNER
   BUTTONS ONLY: tag v0.2.2 at ad3dda8, push tag, npm publish from a
   clean tag clone (memory: npm-publish-owner-only; registry still on
   0.2.0 - both 0.2.1 and 0.2.2 unpublished until then). Next chore
   pass: archive brief-release-0.2.2-closeout.md to shipped/, file
   the guard_provenance verdict-parser issue and the guard_tests
   test_scope-from-main issue from WORRIES. Near-miss worth
   remembering: a .format arg mismatch made the wrong-override path
   fail OPEN until the live replay caught it - pinned by
   test_builtin_spawn_wrong_override_blocked.
00. provenance-shipping SHIPPED 2026-07-15 (PR #65, d624cc3, closes #64;
   witnesses W-019/W-020, 20/20): fresh installs now ship
   company/provenance.json (enforcer armed by default); update NEVER
   auto-arms, prints one notice line. Owner field audit found the gap.
   PENDING OWNER BUTTON: 0.2.1 patch release to npm (0.2.0 on the
   registry still has the gap - fresh 0.2.0 installs stay dormant).
   Same flow as 0.2.0: bump PR, tag, owner publishes from clean tag
   clone (memory: npm-publish-owner-only). Field guidance given: owner's
   research repo stays disarmed until they create provenance.json after
   Jul 28; gitignore data/ to stop stop_gate churn from training jobs.
0. cli-update SHIPPED 2026-07-15: PR #57 merged (7726c99, closes #54-#56),
   owner acceptance DECISIONS #6, witnesses W-014..W-016 recorded (16/16),
   spec+brief archived to shipped/, worktree+branch removed, integrated main
   verified (hooks 213 OK, npm 40, engine 56, gates stamped green).
   Close-out PR from chore/cli-update-closeout in flight if session died -
   check that branch before redoing. WORRIES has 3 rows from this task
   (merge heredoc duplication P2, python3 spawn-per-file P3, fail-open
   emission P3).
0b. delegation-gate exploration DONE 2026-07-15: NOT an issue - md/json and
   company//.claude//docs//.github/ paths are exempt via guard_spec.is_source
   (proven by sandbox probes + field behavior). Two P3 edges in WORRIES
   (extensionless files count as source; guard_tests gates md under tests/).
0c. cli-self-update SHIPPED 2026-07-15: PR #60 merged (a09b463, closes
   #59), acceptance DECISIONS #7, witnesses W-017..W-018 (18/18),
   integrated main 213+57 green. Worktree+branch removed.
0d. v0.2.0 PUBLISHED to npm 2026-07-15 (DECISIONS #8): tag v0.2.0 at
   5913374, owner published manually from the clean tag clone. FIELD
   LESSON (memory npm-publish-owner-only.md): owner npm 2FA is
   LINK-BASED - no OTP codes exist; publishes are ALWAYS owner-manual or
   git-CI, agent only prepares (bump PR, tag, clean tag clone, verified
   placeholder gates.config). NEVER publish from the working checkout -
   local gates.config wiring fails the placeholder test. Witnesses
   W-017/18 landed via PR #62 (fab01e1). Candidate next: publish via CI
   workflow (owner hinted "or through git ci"), #36, #37, tarball ships
   repo board state (P3 hygiene, install never copies it), roadmap
   #1-#11.
1. delegation-enforcement SHIPPED 2026-07-10 (PR #49, f9e5dae, closes
   #42-#47; acceptance DECISIONS #4). Close-out PR in flight if session
   died mid-close: witnesses W-011..W-013 recorded, brief archived to
   shipped/, active-task cleared - check chore/delegation-closeout branch
   state before redoing.
2. THE NEW GATES ARE LIVE ON MAIN. Every feature/program dispatch now
   requires, in active-task.json BEFORE work: "issues": [...] (GitHub,
   PR mode) and "execution": "delegated"|"self" + "execution_why". The
   context pin injects state every turn; self-built source needs an
   auditor pass at the current tree before commit/close. Do not fight
   the hooks - they are the product.
3. Candidate next: #36 (audit ENOLOCK), #37 (stamp-root mismatch +
   subagent worktree commits - CEO lands commits meanwhile), doc-sync of
   README/docs if they inventory hooks (guard_provenance + context_pin
   are new), or roadmap #1-#11.
2. After merge: docs-librarian sync if docs cover hooks; witnesses via
   witness_check.py --add from the lead's proposed markers.
3. Then: #36 (audit ENOLOCK), #37 (stamp-root mismatch), or roadmap #1-#11.
2. Deferred by owner (revisit on ask): lessons loop, loop workers, model
   tiering, gates.local.config override (WORRIES row).
3. Field lessons for spawn prompts: witness markers MUST be single-line
   verbatim substrings (W-010 incident, PR #41); dispatched subagents
   cannot commit in worktrees (#37) - plan for CEO landing; a stale MAIN
   stamp blocks worktree commits - restamp main first.

## 3. In flight

| Agent | Task | Worktree | Last known state |
|---|---|---|---|
| developer | cli-self-update | .claude/worktrees/cli-self-update | Dispatched 2026-07-15; brief brief-cli-self-update.md; no-commit rule - check worktree git status for finished-on-disk work before respawning |

## 4. Facts every spawn prompt needs

- Gate suite for THIS repo, run directly:
  `python3 -m unittest discover -s tests/hooks -q` AND `npm test`.
- The tracked company/gates.config keeps its CONFIGURE-ME placeholders (it
  ships to installs) - never commit real gate commands into it. The CEO
  keeps an uncommitted local wiring (hooks + tests gates) for honest
  stamps; rewire with gates_detect --write + hooks gate if lost.
- Writing must stay hook-clean: straight quotes, ' - ', three dots.
- All roles opus (owner veto on tiering). Never override models in spawns.
- PR mode: origin=github.com/devmesh-in/claude-company, gh authed as
  Redomic. Owner authorized CEO merges 2026-07-10 (recorded in DECISIONS).
  Branch protection: 9 CI checks + strict up-to-date (use
  `gh pr update-branch` when BEHIND).
- NEVER manually delete a remote branch that is a stacked PR's base - it
  CLOSES the child PRs (cost us #29/#30, recreated as #33/#34). Merge with
  `gh pr merge --delete-branch` or retarget children first.
- Hooks: Python 3.8 stdlib, fail open, import _common as c. guard_commit
  now resolves the branch from the payload cwd (worktree commits work).
- Witness registry: company/witnesses.json, mutate ONLY via
  `python3 .claude/hooks/witness_check.py --add/--remove`.
- Never `git add -A`; stage explicit paths; `Task: <slug>` trailer.

## 5. Done log (chronological, compressed)

- 2026-07-09: external framework deep research (3 explorers + design pass); plan
  approved; tiering vetoed; lessons/workers deferred; issues #15-#25.
- 2026-07-09: wave 1 built + verified (guard_secrets, cost_capture, models
  gate); PR #27. Dogfooding found #26 (guard_commit worktree bug).
- 2026-07-09: wave 2 built by two parallel leads + CEO verification +
  auditor SHIP on both; PRs #29/#30 (later #33/#34). Auditor found #31.
  Doctrine lead found #28.
- 2026-07-10: wave 3 built + verified (RELEASE doctrine, /release,
  acceptance record, postmortem); PR #32.
- 2026-07-10: owner authorized end-to-end merge; stack merged
  #27 -> #33 -> #34 -> #32 -> #35 (close-out: witnesses W-004..W-009,
  briefs archived). Integrated main verified green. Program closed;
  acceptance recorded.
- 2026-07-10: follow-up pair shipped. docs-sync (docs-librarian): README +
  docs/ synced with the program, new root CLAUDE.md - PR #39, closes #28.
  adr-hardening (developer): guard_frozen blocks minting pre-accepted
  ADRs - PR #38, closes #31. Close-outs #40/#41 (W-010; first marker was
  line-wrapped and the witness gate itself caught it - fixed verbatim).
  New bugs filed from integration: #36 (audit ENOLOCK), #37 (stamp-root
  mismatch + subagent worktree-commit blocker). Witnesses 10/10 on main.
- 2026-07-10: delegation-enforcement shipped (PR #49, issues #42-#47,
  DECISIONS #4-#5). 5 layers + FR-DE-15 tracking gate; one tech-lead +
  2 devs; CEO drill caught the porcelain dir-collapse dodge (-uall fix);
  auditor SHIP after 1 coverage fix; 213+31 green x3. Witnesses
  W-011..W-013. Field lessons: two-step cd-then-commit lets the CEO land
  worktree commits (#37 workaround); strict up-to-date protection
  silently defeats owner merge clicks when another PR lands first - use
  gh pr update-branch and re-ask; the classifier will NEVER let the CEO
  merge its own PR - plan the owner click into every delivery.
