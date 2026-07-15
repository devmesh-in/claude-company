# BRIEF: pack-leak-fix

_Type: quick. Spec: none (issue #68 + this brief are the source of truth).
Lead: direct-developer. Date: 2026-07-15._

## Mission

Stop the product repo's own work records (specs, briefs, CRs - including
everything under shipped/) from reaching installed projects. Field impact
(DevMesh migration): a fresh install delivered 10 of OUR shipped briefs, 2
shipped specs, and CR-UPD-1 into the target's company/ tree. Two leak
vectors must BOTH close: (1) installs from a git clone of this repo, (2)
the npm tarball.

Decision already made by the CEO (implement, do not re-litigate): the
installer scaffolds company/specs/, company/briefs/ (+ briefs/shipped/,
specs/shipped/), and company/change-requests/ as EMPTY directories and
never copies record files (CR-*.md, brief-*.md, spec-*.md, shipped/**)
from the source tree. Belt: the npm pack list also stops shipping those
records.

## Read first (in order)

1. CLAUDE.md (dual-nature rule - this bug is a violation of it)
2. install.sh (the copy_tree_if_absent calls for specs/briefs/change-requests)
3. update.sh (its scaffold-restore behavior for the same trees, if any)
4. package.json "files" list + tests/cli/test_cli.sh pack-manifest section
5. tests/install/run_tests.sh

## You own

- install.sh (the three copy_tree_if_absent call sites only)
- update.sh (same trees, if it restores them)
- package.json ("files" entry adjustments only)
- tests/cli/test_cli.sh (pack-manifest assertions)
- tests/install/run_tests.sh and tests/install/test_update.sh (assertions)

Nothing else.

## Invariants in play (must not break)

- A fresh install still gets the three directories (empty), so briefs/specs
  /CRs can be written immediately - scaffold the dirs, not the records.
- company/templates/** keeps shipping (that IS product payload).
- Existing user records in a target are NEVER touched by install or update
  (if-absent semantics stay).
- npm tarball must not contain company/{specs,briefs,change-requests}
  record files; whatever mechanism you choose (files negation patterns or
  .npmignore) must keep every OTHER currently-packed path identical - the
  pack-manifest test proves it.
- bin-vs-bare parity test stays green.
- python3 3.8 stdlib / bash 3.2 / zero deps. Hook-clean writing: straight
  quotes, ' - ' never em dashes, '...' never the ellipsis glyph.

## Scope (ordered)

1. install.sh: replace copy_tree_if_absent for company/specs,
   company/briefs, company/change-requests with directory scaffolding
   (mkdir -p, including briefs/shipped and specs/shipped). Tag `# issue-68`.
2. update.sh: mirror - its scaffold restore for those trees must create
   dirs only, never copy records. Tag `# issue-68`.
3. package.json: stop packing the record files (negation patterns in
   "files" or .npmignore - pick what npm reliably honors; prove with
   `npm pack --dry-run`).
4. Tests: (a) run_tests.sh - fresh install has the three dirs, and ZERO
   files matching CR-*.md / brief-*.md / spec-*.md under them even when
   the SOURCE tree contains such records (seed the synthetic source with a
   fake record to prove the negative); (b) test_cli.sh pack-manifest -
   assert the tarball contains no company record files; (c) test_update.sh -
   update on a project with its own briefs/specs/CRs leaves them untouched
   and still restores missing EMPTY dirs without importing records.

## Out of scope

- Moving this repo's shipped/ archives out of company/ (they stay; the
  engines just stop copying them)
- Any other install/update behavior

## Report back

Facts per REPORT-TEMPLATE.md: paths, all four suite outputs pasted,
`npm pack --dry-run` before/after evidence, deviations, 1-2 proposed
single-line verbatim witness markers, worries. Tracking issue: #68.
DO NOT COMMIT - the CEO lands the commit.
