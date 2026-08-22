# BRIEF: tui-clean-source

_Type: quick. Spec: none (quick). Lead: direct-developer. Date: 2026-08-13._

## Mission

`tests/install/test_tui.sh` can never be green in a working checkout of this
repo, and that is now actively harmful. It asserts that a fresh install leaves
`CONFIGURE ME` placeholders in `company/gates.config`, but the installer copies
the WORKING-TREE `gates.config`, which on this repo carries real local gate
commands. So the suite reports 20 pass / 1 fail locally and 21 / 0 only on a
clean copy, and the failure looks like a regression every single time - it has
already been mistaken for one once.

This just stopped being cosmetic. CLAUDE.md now requires all five suites green
before any commit, so a permanently-red suite trains everyone to ignore a red
suite. Success is `bash tests/install/test_tui.sh` exiting 0 in a normal working
checkout with real gate commands in `company/gates.config`, and still failing
honestly if the installer genuinely regresses.

## Read first (in order)

1. `CLAUDE.md` - specifically the dual-nature rule. The tracked `gates.config`
   keeps `CONFIGURE ME` placeholders because that is what a fresh install
   inherits; this repo's real gate commands live only in the working tree and
   must NEVER be committed. That tension is the whole cause of this bug.
2. `tests/install/test_tui.sh` - the failing assertion and how it installs.
3. `tests/install/run_tests.sh` - how the sibling suite builds its fixtures.
   Match its idiom rather than inventing one.
4. `install.sh` - `copy_if_absent` and how `gates.config` reaches a target.

## You own

- `tests/install/test_tui.sh`

Nothing else. Three other lanes are building concurrently on
`.claude/hooks/**`, `company/run-gates.sh` and `company/frozen-surfaces.json`.
Do not touch any of them, do not touch `company/gates.config`, and do not touch
`install.sh`. If the real fix turns out to live outside your one file, STOP and
report that instead of making it.

## Invariants in play

- `company/gates.config` stays placeholder in the tracked tree and keeps its
  real local commands in the working tree. Do not commit real commands, and do
  not "fix" this by changing the tracked file.
- The test must still FAIL if the installer genuinely stops shipping
  placeholders. A test that passes by no longer checking anything is worse than
  the flake - that is the failure mode to avoid here, and it is easy to hit.
- Tests are the oracle and are never edited merely to pass.

## Scope

1. Make the suite install from a CLEAN source rather than the dirty working
   tree. The known-good approach is `git archive HEAD` into a temp directory
   and installing from that, so the fixture sees exactly the tracked bytes.
   Implement that unless reading the code shows something better, in which case
   use your judgment and say why in your report.
2. Keep every existing assertion. Add one that pins the intent: the source the
   fixture installs FROM carries placeholder gates, so a future reader can see
   why the clean-source step exists and does not delete it as indirection.
3. Leave a short comment naming the dual-nature rule as the reason.

## Definition of Done

- [ ] `bash tests/install/test_tui.sh` exits 0 in this working checkout, with
      real gate commands present in `company/gates.config`. Paste the output.
- [ ] Demonstrate it still catches a real regression: temporarily make the
      installed `gates.config` non-placeholder in the fixture, show the suite
      goes red, revert. Paste both. **This is the load-bearing DoD line** - a
      green suite that stopped checking is the exact failure this task must not
      produce.
- [ ] `bash tests/install/run_tests.sh` still green (96 tests) - you are next
      door to it.
- [ ] `git status` clean apart from your one file; `company/gates.config`
      unmodified by you.
- [ ] Conventional commit, `Task: tui-clean-source` trailer, explicit staged
      path, never `git add -A`.
- [ ] Report: what changed, both suites' output, the regression demonstration,
      and 1-3 witness candidates.

## Fallback assumptions

- If `git archive HEAD` cannot work because the fixture needs untracked files
  the installer legitimately ships -> FALLBACK: copy the tree and then
  `git checkout-index` or overwrite `company/gates.config` from `HEAD` before
  installing. Tag the site `# tui-clean-source assumption` and explain in the
  report.

## Out of scope

- The other four suites, all hooks, `install.sh`, `update.sh`,
  `company/gates.config`, and the concurrent lanes' files.
- Any attempt to make `gates.config` dual-mode or add a `gates.local.config`
  override. That is a separate parked idea in WORRIES; do not build it here.

## Report back

Facts: what changed, both suites' output, the regression demonstration proving
the assertion still bites, deviations, worries, witness candidates.
