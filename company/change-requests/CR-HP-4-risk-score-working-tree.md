# CR-HP-4: risk-score-working-tree

_Requesting agent/task: tech-lead, task hp-provenance (brief `company/briefs/brief-hp-provenance.md`, issue #101). Date: 2026-08-13._
_Status: PROPOSED_

## Frozen surface affected

`.claude/hooks/risk_score.py`. The hp-provenance brief declares it READ-ONLY to
this lane: "If this needs a change inside `risk_score.py`, file a CR - you do
not own it."

## Why (cite the requirement)

Scope item 6 of the brief, authorized by DECISIONS #19: "The audit requirement
scales with `risk_score.py`'s EXISTING bands. A `high` band arms a mandatory
audit requirement the same way self-authorship does, so a large delegated diff
can no longer integrate unaudited."

That is shipped. It is the compensating control for FR-HP-44's narrowing: the
narrowing opens an ALLOW for dirty source this company did not author, and the
`high` band closes it again over the riskiest subset. It works, and it is
measurably narrower than intended for one reason.

`risk_score` scores exactly one thing: `git diff base...HEAD`, where `base` is
`merge-base(main, HEAD)`. That is COMMITTED work on the branch. Every diff
signal it has - `numstat`, `changed_paths`, and therefore size, ownership,
frozen proximity, test ratio, sensitive paths and the secret scan - is blind to
the working tree.

The consequence, stated plainly:

- Mode C arms only when there are dirty source paths, and it scores a range
  that excludes them. On the FIRST commit of a task branch, `base...HEAD` is
  empty, every signal scores 0, the band is `low`, and the risk arming cannot
  fire no matter how large the pending change is. The band only becomes
  meaningful from the second commit onward, when the first commit's content has
  moved into the scored range.
- Mode D has the same shape at task close: a session holding its whole change
  uncommitted is scored `low`.

So the control catches an accumulating branch, which is the common case for a
long lane, and misses a single large drop, which is the case the worry in
`WORRIES.md` actually describes ("a clean delegated build gets NO independent
audit", the 4,791-line change). It is a real narrowing of a control that was
adopted specifically to close that worry, and it is invisible from the outside.

This is characterized in ADR-0003 as a known limitation and commented at
`guard_provenance.risk_band`. It is filed rather than worked around because the
workaround available to this lane - computing size from `git status` in
`guard_provenance` - would be a second, divergent risk model and a new numeric
fence, which the owner has vetoed twice.

## Exact proposed change

Add an opt-in scope selector; do not change the default, so the advisory CLI
and any existing caller keep today's numbers.

```
python3 .claude/hooks/risk_score.py [--scope branch|worktree] ...
```

- `--scope branch` (default): today's behaviour, `base...HEAD`, byte-identical
  output.
- `--scope worktree`: score `base` against the working tree INCLUDING untracked
  files, so the range covers what a commit is about to write.

Implementation shape, reusing machinery that already exists rather than adding
any:

1. Build the working tree as a real git tree object in a THROWAWAY index, which
   is exactly what `_common._content_tree_hash` already does (`GIT_INDEX_FILE`
   pointed at a temp file, `read-tree HEAD`, `add -A`, `write-tree`). The repo's
   real `.git/index` is never read or written. `_common.HASH_EXCLUDES` should
   NOT be applied here - it exists to stop a stamp self-invalidating, and it is
   the wrong exclusion set for a risk read.
2. Point the two existing readers at `base <tree>` instead of `base...HEAD`:
   `numstat` -> `git diff --numstat <base> <tree>`, `changed_paths` ->
   `git diff --name-only <base> <tree>`.
3. Leave `run_secret_scan` on `--scan-branch <base>` unchanged, or extend
   `guard_secrets` separately; the secrets signal is out of this CR's scope.
4. Fail open exactly as everything else in that file does: any trouble building
   the tree falls back to `base...HEAD` with a note in the table, and the
   process still ALWAYS exits 0.

Then `guard_provenance.risk_band` passes `--scope worktree`, and the comment
naming this CR comes out.

## Blast radius

- `risk_score.py` itself: two functions take a range argument instead of
  building one, plus one new tree builder and one argparse flag. The band
  mapping, the six signals, the point values and the `RISK_JSON` contract are
  untouched - this changes WHAT is scored, never HOW.
- `guard_provenance.risk_band` is the only mechanical consumer and it reads the
  band through the `RISK_JSON` line, which does not change shape.
- Advisory human use of `risk_score` is unaffected while the default stays
  `branch`.
- Gates re-run: `tests/hooks/` in full. `tests/hooks/test_risk_score.py` is the
  suite that covers it today and every case there scores `base...HEAD`, so they
  all keep passing untouched under the default; the new scope needs its own
  cases, including one proving `--scope branch` output is byte-identical to the
  current output.
- `tests/hooks/test_guard_provenance.py` rows 9, 11, 13, 15 and 21 build a high
  band by COMMITTING a large diff and leaving a separate path dirty, precisely
  because the band cannot see uncommitted work. Those five fixtures get simpler
  under `--scope worktree` and must be rebuilt with it.
- Monotonicity: this can only turn ALLOWs into BLOCKs at Mode C and Mode D
  (more content scored, so bands can only rise). It is in the tightening
  direction and needs no new exemption.

## Owner sign-off needed?

no on the mechanism - DECISIONS #19 already authorized risk-scaled audit
arming, and this makes the authorized control measure what it was meant to
measure.

yes on one judgement call the CEO should make explicitly, because it is a
ceremony cost: with `--scope worktree` the FIRST commit of every task branch
becomes scoreable, so a large first drop starts demanding an auditor pass where
today it does not. That is the intent, and it is also a new block on a common
path. Recommend landing it as its own gated change with its own auditor pass,
not folded into another lane.

## Workaround if rejected

Shipped as of this lane: the band arms on committed branch content only. Mode C
and Mode D still block a high-band diff from the second commit onward, and the
self-authorship arming (FR-HP-44) is unaffected at every commit including the
first. The residual is a single large uncommitted drop scoring `low`, and it
stays a `WORRIES.md` row plus the ADR-0003 limitation note. The operational
mitigation is unchanged from today: the CEO dispatches the auditor deliberately
on any large delegated merge.
