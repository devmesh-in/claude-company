# BRIEF: risk-working-tree

_Type: feature. Lean path. Spec: none - this brief is the spec.
Lead: direct-developer. Date: 2026-08-13. Tracking issue: #115._

## Mission

`risk_score.py` is 454 lines that never block and are blind exactly when
needed. It is the compensating control the owner traded for when the audit
demand was narrowed, and it does not fire in the case it was adopted for. Make
it score what is actually at risk.

## The three defects, all measured

1. **It scores `base...HEAD`, so it only sees COMMITTED work** (CR-HP-4, filed
   by the provenance lane). A branch's first commit is scored against an empty
   diff, bands `low`, and arms nothing. Verified: identical content bands `low`
   uncommitted and `high` committed.
2. **A change to the enforcement layer itself is not "sensitive".**
   `is_sensitive` covers migrations, auth and billing. It does not cover
   `.claude/hooks/**`. So the 2426-line change to `guard_provenance.py` - the
   hook that decides whether anything gets audited - scored **25 of 50, band
   `medium`**, below the threshold of its own compensating control. A change to
   the enforcer has the highest blast radius in the repo by construction: if it
   is wrong, every later judgment is wrong.
3. It is invoked by hand. Nothing calls it on a path where its answer changes
   an outcome except one unmerged lane.

## Scope

1. **Score the working tree.** The subject becomes committed work UNION
   uncommitted work - the tree as it stands, which is what "how risky is this
   change" actually means. Keep `--base` for the committed-only comparison; do
   not remove it. If the two answers differ, the higher one wins, because the
   question is "how hard should this be verified", not "what is in git".
2. **Add the enforcement layer to the sensitive set.** `.claude/hooks/**` and
   `company/*.md` canon. Derive it, do not hardcode a list of filenames -
   the rule is "changes to the machinery that judges other changes", and say
   that in the code so nobody trims it later.
3. **Do NOT invent new thresholds.** The band cuts (25 / 50) and the per-signal
   points stay exactly as they are. The owner has twice vetoed enforcement
   built on arbitrary numbers, and re-tuning constants to make one case come
   out right is precisely that. You are changing WHAT IS MEASURED, never the
   arithmetic. If after your change the motivating case still bands below
   `high`, report that as a finding rather than tuning until it passes.

## Definition of Done

- [ ] The motivating case is re-scored and the result REPORTED, whatever it is:
      `git diff 9df86e4..1b957f6` on branch `task/hp-provenance` (2426 insertions
      touching `guard_provenance.py`). State its band before and after.
- [ ] Uncommitted work is scored. Prove it: identical content, one run before
      committing and one after, same band.
- [ ] `--base` still produces today's committed-only answer, byte-identical
- [ ] Tests in `tests/hooks/test_risk_score.py` (extend it, do not create a
      parallel file) covering both directions and the new sensitive rule
- [ ] All five suites from your worktree root, pasted
- [ ] Conventional commit, `Task: risk-working-tree` trailer, explicit paths

## Out of scope

- `guard_provenance.py`. It is owned by open PR #112 and it has its own half of
  this bug: both modes return BEFORE computing the band when the dirty set is
  empty, so a clean committed tree is never scored at all. Report it; do not
  fix it here.
- Changing band thresholds or signal weights. See scope item 3.
- Making `risk_score` block anything. It stays advisory.

## Report back

What changed, the before-and-after band on the motivating case, the five
suites, anything #112 needs from you, and 1-3 witness candidates.
