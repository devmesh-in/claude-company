# BRIEF: arm the risk band

_Derived from `company/specs/spec-arm-risk-band.md`. One seam, one builder._

**THE SPEC IS `_Status: HALT_`.** OQ-ARB-05 is open and needs an owner
decision; this brief is not buildable to completion until it is answered. Read
the spec's BLOCKER section first.

## Mission

Make DECISIONS #19 (b)'s compensating control real: a `high` risk band must
mechanically demand a fresh independent audit before work integrates. Today the
band exists only as a runbook line and `risk_score.py` has zero callers in any
hook.

## Read first

- `company/specs/spec-arm-risk-band.md` - the FRs, the decided fallbacks, and
  the calibration table this rests on.
- `.claude/hooks/risk_score.py` - `band_of`, `build_report`, `collect_committed`,
  `collect_worktree`, `default_base`. Consume these; change none of them.
- `.claude/hooks/guard_provenance.py` - modes A, B-pre, B-post, C, and the note
  above `main()`'s dispatch about the two deleted modes.
- `.claude/hooks/_common.py` - `segments`, `tokens`, `git_subcmd`, `block`,
  `adherence_log`, `hotfix_entry`.

## Owned paths

- `.claude/hooks/guard_provenance.py`
- `tests/hooks/test_arm_risk_band.py` (new)
- `.claude/hooks/context_pin.py` and `tests/hooks/test_context_pin.py` - added
  to the brief after the fact, which is the wrong order. The idle line fired on
  a deliberate `execution: "self"` with no dispatches, which is the correct end
  state for one-seam work; it was fixed alongside this task rather than
  separately, and an audit correctly called that an unscoped rider.

## Invariants in play

- Hooks are Python 3.8 stdlib only and fail OPEN on internal error.
- The risk arithmetic is frozen (BR-ARB-02). Band cuts stay 25 / 50.
- No new magic numbers (BR-ARB-03). The threshold IS the existing `high` band.
- Monotonicity (BR-ARB-01): this may only convert ALLOWs into BLOCKs.

## Frozen surfaces nearby

`company/state/gates.status` and the rest of the `always` list. This work
touches none of them.

## Ordered scope

1. `risk_band(tree, ref)` helper - FR-ARB-01, FR-ARB-02. **The subject is the
   INTEGRAND**, `merge-base(main, ref)...ref`, NOT the tree the integrating
   session stands in. OQ-ARB-03 was RE-DECIDED after an audit HALT: the first
   build scored the local tree, so a CEO integrating a lane from a clean `main`
   checkout scored an empty diff, band `low`, and the gate was silent on
   exactly the delegated build this exists to catch. If you are reading this
   brief to rebuild the feature, that is the mistake to avoid.
2. `integration_refs(seg, tree)` - resolves WHAT is being integrated, ALL of
   it. Skip only options that take a SEPARATE next token (`-m`, `--message`,
   `-F`, `--file`, `-s`, `--strategy`, `-X`, `--strategy-option`,
   `--into-name`, `--cleanup`). Do NOT list `-S`, `--gpg-sign` or `--log`:
   git gives those an OPTIONAL ATTACHED value, and listing them made
   `git merge --no-ff -S task/x` swallow the ref and allow a high-band merge.
   That regression was introduced by the fix for the previous one - check this
   line against `git-merge(1)` rather than trusting it. Validate every
   candidate with `rev-parse --verify` and return them all: an octopus merge
   brings in several, and scoring only the first scored `main` against itself,
   band low, silent.
3. `quoted_segments(command)` - split on shell operators by scanning
   CHARACTERS with quote state. Not `_common.segments` (a regex split, blind
   to quotes, so a `;` in a merge message tears the command). Not a split of
   shlex TOKENS either: shlex only emits a bare `;` when it has whitespace on
   both sides, so `git fetch; git merge ...` never split and the gate went
   silent with no log line. Both of those were shipped and both were caught by
   audit.
4. `integration_segment(seg)` recognizer - FR-ARB-04, FR-ARB-05. Do NOT widen
   `git_subcmd`; three gates consume it.
5. The gate itself on PreToolUse Bash, ordered BEFORE mode C so a blocked
   integration leaves no commit telemetry - FR-ARB-03, FR-ARB-06 to FR-ARB-14.
   Resolve the tree through `_common.acting_tree` and normalise it to a
   checkout root (FR-ARB-12); do NOT write a second copy of that resolution.
6. Tests covering: high blocks, low/medium silent, fresh audit satisfies,
   hotfix bypasses, unscorable allows, `gh pr merge` recognized, `git merge`
   recognized, merge conclusion/cancel never arms, a fault cannot disarm mode
   C, and a non-integration Bash segment is untouched. A test that cannot KILL
   the removal of the thing it covers is not coverage: the tree-resolution
   tests need a fixture scored on root-relative signals, because `size` and
   `sensitive_paths` give the same answer from any directory.

## Definition of Done

All FRs met, ALL FIVE gating suites green (hooks, CLI, installer, TUI, update
- CLAUDE.md names five and `npm test` is the CLI suite alone), and the new test
file asserting each FR by ID. A test that cannot KILL the removal of the thing
it covers does not count toward this.

## Out of scope

Re-tuning risk_score; widening `git_subcmd`; commit-time arming; fixing
`guard_commit`'s own blindness to `gh pr merge` (RISK-ARB-02, recorded, owed
its own change).
