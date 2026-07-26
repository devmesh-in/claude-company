# Brief: test-infra-fixes

Task slug: `test-infra-fixes`
Class: quick
Branch: `task/test-infra-fixes`

## Read first

- `CLAUDE.md`
- `tests/hooks/run_tests.sh`, `tests/cli/test_cli.sh`
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`

## Context

Two independent defects in this repo's own test infrastructure, both found on
2026-07-26 while scoping the multi-session work. Neither is a product bug; both
make the suites lie about coverage, and the second is a hard blocker on every
commit in this repo.

**1. CI runs 103 of 224 hook tests.** `tests/hooks/run_tests.sh` execs
`test_hooks.py` directly. CI calls that script (`ci.yml:37`, `release.yml:39`),
so the 121 tests in `test_guard_provenance.py`, `test_context_pin.py`,
`test_cost_capture.py`, `test_session_start_digest.py`, `test_risk_score.py`,
`test_trace_check.py`, `test_witness_check.py`, and `test_guard_secrets.py`
have never run in CI. They run only through the local `gates.config` gate,
which is uncommitted by design here. Any NEW test file is invisible to CI.

**2. `npm test` is red on main.** `tests/cli/test_cli.sh:108` pipes
`npm pack --dry-run --json 2>/dev/null` into `JSON.parse`. On npm 10.5.0 the
`prepare` lifecycle banner is written to STDOUT, so the parse throws and all 10
pack-manifest assertions fail as `pack MISSING`. Verified on main with no local
changes: `PASS: 51  FAIL: 10`. `--ignore-scripts` does NOT suppress the banner;
`--silent` does. CI passes today because its npm build emits no banner, which
is exactly why this went unnoticed.

## You own

- `tests/hooks/run_tests.sh`
- `tests/cli/test_cli.sh`

Nothing else.

## Scope, ordered

1. `tests/cli/test_cli.sh:108` - add `--silent` to the `npm pack` invocation so
   the JSON is parseable regardless of lifecycle banners. Fix this FIRST: while
   it is red, no gate stamp can go green and nothing in this repo can commit.
2. `tests/hooks/run_tests.sh` - replace the direct `exec` of `test_hooks.py`
   with unittest discovery rooted at the suite directory:
   `exec python3 -m unittest discover -s "$HERE" -t "$HERE" -v "$@"`
   Keep `-v`: `test_hooks.py` ran `unittest.main(verbosity=2)`, so without it
   CI loses the per-test names and 224 tests collapse to dots.
3. Confirm the runner still passes arguments through and still exits non-zero
   when a test fails.

## Definition of Done

- `npm test` reports `FAIL: 0` and exits 0.
- `bash tests/hooks/run_tests.sh` reports 224 tests, matching
  `python3 -m unittest discover -s tests/hooks -q`, and exits 0.
- No file outside the two owned paths is modified. This brief lands with the
  task, as every shipped brief does; it is added, not modified.

## Invariants in play

- Hooks and their runner are Python 3.8 stdlib only; the runner stays stdlib
  `unittest`.
- `tests/hooks/run_tests.sh` keeps `set -euo pipefail` and its `HERE` resolution.
- The pack-manifest assertions themselves do not change - only how the JSON is
  obtained. The packed file list must stay exactly as it is.

## Fallbacks

- If `--silent` ever stops suppressing the banner, slice the payload from the
  first `[` rather than adding a second npm flag; tag the reason in a comment.
- If discovery double-counts, keep `-t "$HERE"` and do NOT add `sys.path`
  manipulation.
- If discovery reveals a failing test, that is a real finding: report it, do not
  silence it.

## Out of scope

- Changing any hook or any test assertion.
- Changing the CI workflows.
- The `ResourceWarning: unclosed file` in `test_witness_check.py:273`.
- Positional-argument selection for the hook runner. All three callers of the
  script (`ci.yml:37`, `release.yml:39`, `docs/customizing.md:112`) pass no
  arguments, and `-k` covers real use. Note the local `gates.config` gate
  invokes bare `discover`, not this script, so it does not exercise `-v`.
