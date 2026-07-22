# GATES.md - The gate ladder contract

Every gate here is BLOCKING. A red gate means the work is not done, ever - no
"works locally", no waivers, no averaging. `company/run-gates.sh` must be fully
green before any merge, and the `guard_commit` hook blocks `git commit` while
the stamp in `company/state/gates.status` is red, stale, or missing.

## How gates work mechanically

1. Gates are defined per project in `company/gates.config` (JSON). Each gate is
   a name plus a shell command; exit 0 is green.
2. `bash company/run-gates.sh` runs the ladder, prints the table, and stamps
   the result into `company/state/gates.status` together with a work-tree hash.
3. The stamp goes stale the moment tracked files change again - a green stamp
   from before your last edit does not count. Re-run the suite.
4. Only the runner writes the stamp. The stamp file is on the frozen `always`
   list; hand-editing it is blocked and logged.

## The recommended ladder

Configure what your project can support today; grow toward the full ladder.
Order cheap-to-expensive so failures surface fast:

| # | Gate | Proves | Typical command |
|---|---|---|---|
| G0 | Witnesses | Every shipped fix/feature is pinned to 1-3 load-bearing witnesses | `python3 .claude/hooks/witness_check.py` |
| G1 | Boundary / ownership lint | Modules only touch their own directories and the narrow waist | `eslint-plugin-boundaries`, import-linter, or a diff-path check |
| G2 | Typecheck + lint | The code is well-formed and idiomatic | `tsc --noEmit && eslint .` / `mypy && ruff check` |
| G3 | Unit + integration tests | Behavior is correct | `npm test` / `pytest` |
| G4 | Contract conformance | API shapes match the declared contracts | schema-driven supertest / pydantic round-trips |
| G5 | Golden-path e2e | The pieces actually compose | Playwright journey through the primary user flow |
| G6 | Requirement traceability | Every FR in the brief is implemented, tested, or explicitly deferred; mechanical - an orphan FR is red | `python3 .claude/hooks/trace_check.py` |
| G7 | Model routing | Spawn overrides and agent frontmatter match the models manifest | `python3 .claude/hooks/guard_models.py --check` |
| G8 | Dependency / CVE audit | No known-vulnerable dependency ships; last rung, network-bound | dependency/CVE scan |

`run-gates.sh` runs cheap-to-expensive, not table order: the config-cheap
checks (witnesses at G0, model routing at G7) run early so failures surface
fast, while the network-bound dependency audit (G8) always runs last regardless
of where its row sits. The G-number is an identity, not a promise about clock
order.

Two design rules learned the hard way:

- **Test the negative space.** Where a table of allowed transitions/permissions
  exists, generate the complement and assert every non-listed case is rejected.
  Positive-only tests pass while the system silently allows everything.
- **The composition test is integrator-owned.** Each workstream extends the
  golden-path e2e via its report/PR; only the CEO merges changes to it. That
  one test is the proof the workstreams compose.

## The mechanical gates claude-company ships

These rungs are wired for this repo; a project inherits them and adds its own.

- **G0 witnesses (`python3 .claude/hooks/witness_check.py`) - the first rung.**
  Every shipped fix or feature records 1-3 load-bearing witnesses: the exact
  spots that would break first if the change regressed. The registry is
  `company/witnesses.json`, mutated only through the CLI (`--add` / `--remove`,
  IDs of the form `W-NNN`) - never hand-edited. The producer proposes witness
  candidates in its report; the CEO curates and records them at integration.
- **G6 trace (`python3 .claude/hooks/trace_check.py`).** Requirement
  traceability stops being a hand-checked list and becomes mechanical: every FR
  in scope must be implemented, tested, or explicitly deferred, and an orphan FR
  - one with no coverage and no deferral - turns the gate red.
- **G7 models (`python3 .claude/hooks/guard_models.py --check`).** The model
  routing manifest and agent frontmatter must agree: spawn overrides and
  per-agent model declarations match `models.json`, so no agent silently runs
  on the wrong model. It also asserts the Task|Agent spawn hook is wired into
  `.claude/settings.json`, so the enforcement cannot ship as code without teeth.
  (Shipped in wave 1.)
- **G8 audit - the last rung, network-bound.** A dependency and CVE scan: no
  known-vulnerable dependency ships. It runs last because it reaches the
  network; keep it blocking anyway.

## Secrets never commit

`guard_secrets` blocks at commit time: a staged secret stops the commit, full
stop. This one does not yield to `hotfix` - a production emergency is exactly
when a leaked credential does the most damage, so the secrets guard blocks even
while `active-task.json` is `"type": "hotfix"` and other guards only log their
bypass. There is no waiver; scrub the secret and recommit.

## Gates and the hierarchy

- Developers run the gates before reporting. Reporting red gates honestly is
  correct behavior; claiming unverified green is the firing offense.
- Tech leads re-run the gates on the integrated workstream, never trusting a
  developer's numbers from an isolated worktree (stale worktree artifacts mask
  contract drift).
- The CEO re-runs the gates on main after merge. Trust integrated-main gates
  over any worktree self-report.

## UI work has a seventh gate: eyes

Backend correctness is mechanical; UI correctness needs eyes. Any task that
builds or changes a screen is not done until the screen has been driven live
(Playwright MCP) and captured in four states - loaded, empty, error,
after-action - and the screenshots are in the report. The QA engineer captures;
it does not judge. The tech lead and CEO judge the captures against the spec's
acceptance criteria and the project's design language.
