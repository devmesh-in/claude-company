# DECISIONS - owner escalations and outcomes

_Questions only the owner may answer (money, invariants, deploys, scope,
business policy), with what was decided and when. Agents run on tagged
fallbacks until a row lands here._

| # | Date | Question | Decision | Affects |
|---|---|---|---|---|
| 1 | 2026-07-09 | Adopt model tiering (developer/QA to sonnet)? | VETOED - every role stays opus | models.json |
| 2 | 2026-07-09 | Program scope from the framework research | Hard-gate-fitting features only; lessons loop + loop workers DEFERRED | program plan |
| 3 | 2026-07-10 | Adoption program delivery (waves 1-3, PRs 27/33/34/32/35) | ACCEPTED - owner authorized end-to-end merge; CEO merged and verified integrated main | whole repo |
| 4 | 2026-07-10 | delegation-enforcement delivery (5 layers + tracking gate, PR #49, issues #42-#47) | ACCEPTED - owner: "merge everything and close out"; merged f9e5dae, integrated main verified (213+31 green), witnesses W-011..W-013 | hooks, doctrine, settings |
| 5 | 2026-07-10 | Enforcement design direction | Owner REJECTED budgets/role bans twice; approved principle-derived gates (mechanism 5 + written-record consistency) and demanded low-token injection + GitHub tracking gate | all future gate design |
| 6 | 2026-07-15 | cli-update delivery (update subcommand + provenance manifest, PR #57, issues #54-#56) | ACCEPTED - owner: "test it, the merge it to main"; CEO re-tested end-to-end (edit kept, .new written, deleted file restored, config untouched), merged 7726c99, integrated main verified (213 hooks + 40 CLI + 56 engine green), witnesses W-014..W-016 | CLI, installer, frozen registry |
| 7 | 2026-07-15 | cli-self-update delivery (update refreshes the CLI first via npx handoff, PR #60, issue #59) | ACCEPTED - owner: "push to main, then to npm"; merged a09b463, integrated main verified (213 + 57 green), witnesses W-017..W-018 | CLI driver |
| 8 | 2026-07-15 | Release v0.2.0 to npm (tag v0.2.0 at 5913374; notes: PR #57/#60 bodies) | PUBLISHED 2026-07-15 by the OWNER manually from the clean tag clone (link-based npm 2FA - publishes are always owner-manual or git-CI, never agent-run). Registry verified: dist-tags.latest 0.2.0. Semver minor | npm registry |
