# BRIEF: risk-scale

_Type: feature. Lead: direct-developer. Date: 2026-08-13. Issue: #122._

## Mission

`risk_score.sensitive_paths` awards a **flat 10 regardless of how many paths hit
it or what they are**. So a 2426-line change to `guard_provenance.py` - the hook
that decides whether anything gets audited at all - scores the same 10 as a
one-line comment fix in `company/GIT.md`, bands `medium`, and sits below the
arming threshold of its own compensating control.

Make sensitivity scale with blast radius.

## Read this before you touch a number

The owner has TWICE vetoed enforcement built on arbitrary thresholds - once for
glue budgets ("5 files / 200 lines"), once for a 20-line audit waiver. The
previous lane on this file was explicitly forbidden from touching the arithmetic
and correctly reported that the motivating case still banded `medium` rather
than tuning until it passed.

**This brief authorizes changing how sensitivity is COMPUTED. It does not
authorize a table of hand-picked weights.** A scale derived from a stated
principle survives the veto; a lookup table does not. If you find yourself
choosing a number because it makes the motivating case come out right, stop -
that is the thing that was vetoed, and reporting that no principled scale
reaches `high` is worth more to me than a passing test.

## The principle to derive from

Blast radius: **how much else is wrong if this change is wrong.** A change to
the machinery that judges other changes is the maximum, because every later
judgment inherits the error. That is why the enforcement layer sits at the top
and a doc typo sits at the bottom.

Evaluate at least these shapes and say in your report why you rejected the ones
you rejected: count of sensitive paths touched; lines changed WITHIN sensitive
paths (a 2400-line hook change and a one-line hook change are not the same
risk); and tier by kind - enforcement code, then canon it reads, then data.

## Definition of Done

- [ ] Re-score `git diff 9df86e4..1b957f6` from the old hp-provenance work (2426
      insertions in `guard_provenance.py`). Report the band. **If it still does
      not reach `high`, report that** - do not tune.
- [ ] Re-score a deliberate NEGATIVE: a one-line comment fix in
      `company/GIT.md` must NOT climb. A scale that lifts everything is not a
      scale, it is an offset.
- [ ] Re-score a MIDDLE case of your choosing and justify where it lands
- [ ] Band cuts stay at 25 and 50. Untouched.
- [ ] The derivation is written in the code, with its principle, so the next
      reader cannot mistake it for arbitrary constants
- [ ] Extend `tests/hooks/test_risk_score.py`; no parallel file
- [ ] Suites: hooks and `npm test` only. Nothing here reaches the installer.
- [ ] Conventional commit, `Task: risk-scale` trailer, explicit paths

## Out of scope

`guard_provenance.py` and `_common.py` - other lanes are in flight in both.
The band thresholds. What CONSUMES the band (that is a separate open question
about whether the control fires on a clean tree at all).

## Report back

The three re-scores, the shapes you rejected and why, and 1-3 witness
candidates.
