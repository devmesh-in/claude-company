# CR-HPD-1: CLAUDE.md gate block must name all five suites before hp-doctrine merges

_Requesting agent/task: tech-lead, task/hp-doctrine (L6, issue #102). Date: 2026-08-13._
_Status: APPLIED_

## Surface affected

`CLAUDE.md` - the "dual-nature rule" gate block, lines 13-21 on `main` as of
55cf436. Not a frozen-registry surface; it is outside this lane's "You own"
list, which is why this is a CR and not a local edit.

## Why (cite the requirement)

Brief `brief-hp-doctrine.md` scope item 8, authorized by DECISIONS #19: add a CI
step asserting that every test suite `ci.yml` runs is NAMED in `CLAUDE.md`, and
make the disagreement a RED gate.

The check is the requirement, and on `task/hp-doctrine` it is correctly red:
`ci.yml` runs five suites (`tests/cli/test_cli.sh`, `tests/install/test_tui.sh`,
`tests/install/run_tests.sh`, `tests/install/test_update.sh`,
`tests/hooks/run_tests.sh`) while the branch's `CLAUDE.md` names exactly ONE of
them by a path the check can verify - the hooks suite. Its `npm test` line reads
`# CLI + install + pack manifest`, which names no path and additionally claims
`npm test` covers install, which it does not. Four of five go red. That
disagreement is the exact defect the step exists to catch - it reached three
sealed briefs and cost a lane a red branch - so the step must not be weakened,
special-cased, or pointed at a different file to make the branch green.

## Exact proposed change

Nothing about the check changes. One of these two, CEO's choice:

**(a) Preferred - the CEO commits the fix it already wrote.** The corrected gate
block exists in the main checkout right now, uncommitted (`git diff CLAUDE.md`
there shows it: five suite lines plus the "npm test is the CLI suite alone"
paragraph). Commit it to `main`, then `task/hp-doctrine` rebases and the `canon`
job goes green with no edit from this lane.

**(b) Grant this lane the gate block.** Extend hp-doctrine's "You own" list with
`CLAUDE.md`, gate-block lines only, and this lane applies the same five-line
correction on the branch. This costs a second writer on a file the CEO is
already editing in the main checkout, so it is the worse option unless (a)
cannot happen before integration.

## Blast radius

- (a): none beyond `main` gaining the correct canon one commit early. Every
  lane that rebases picks up a `CLAUDE.md` that finally matches CI.
- (b): two writers on `CLAUDE.md` (this branch and the main checkout) with a
  near-certain conflict on the same lines at merge.
- Gates re-run either way: the `canon` job, plus the no-slop scan over
  `CLAUDE.md`.

## Owner sign-off needed?

No. Not money, not an invariant, not a frozen surface - a CEO scope call.

## Workaround if rejected

There is none that keeps the requirement honest. If neither (a) nor (b) happens,
`task/hp-doctrine` merges with a red `canon` job, and the first thing the new
canon gate would prove is that the company ships red gates. Deleting or
softening the check to dodge that is out of scope for this lane and would
reintroduce the defect the check exists to stop.

---
_CEO decision and remarks:_

APPROVED and APPLIED by the CEO, 2026-08-13, via option (a): the
CLAUDE.md suite-list fix merged to main as PR #106 (85a4313). This lane
rebased onto it and the `canon` job runs green on the real tree - all five
suites named, exit 0. No edit to CLAUDE.md was made by this lane.
