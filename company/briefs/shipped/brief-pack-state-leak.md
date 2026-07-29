# Brief: pack-state-leak

Task slug: `pack-state-leak`
Class: quick
Branch: `chore/test-infra-closeout` (folded into the open closeout PR #86)

## Read first

- `package.json` (the `files` list)
- `install.sh` lines 169-199, `update.sh` line 554
- `tests/cli/test_cli.sh` section 8 (npm pack manifest)
- `company/briefs/shipped/brief-pack-leak-fix.md` (issue-68, the identical
  earlier fix for specs/briefs/change-requests)

## Context

`package.json` includes `company/` wholesale and negates only
`company/specs/**`, `company/briefs/**`, and `company/change-requests/**`. It
does NOT negate `company/state/**`, so this repo's own working board ships into
every install and onto the public npm registry.

Verified against the live tarballs: `company/state/{RESUME,STATUS,WORRIES,
DECISIONS}.md` are present in published 0.2.3 AND 0.2.4. The 0.2.4 copies carry
this repo's internal notes - harness bug write-ups, release history, spend
observations. This is the same defect class as issue-68, which excluded the
other three record trees for exactly this reason.

The runtime files (`gates.status`, `provenance-ledger.json`, `active-task.json`,
`costs.log`, `.cost-cursor.json`) are untracked, so a clean-clone publish leaves
them out - but a publish from a dirty checkout would leak those too.

Excluding the whole tree is safe: `install.sh:177-199` SCAFFOLDS the four state
stubs itself and never copies them from the payload (`scaffold_stub` no-ops when
the file exists, so upgrades keep a project's real board). `update.sh:554` only
creates the directory. Nothing in either engine reads a packaged state file.

## You own

- `package.json`
- `tests/cli/test_cli.sh`

## Scope, ordered

1. `package.json`: add `"!company/state/**"` to the `files` list, beside the
   existing three negations.
2. `package.json`: bump `version` to `0.2.5`.
3. `tests/cli/test_cli.sh`: add a `want_absent` assertion for `^company/state/`
   in the section 8 pack-manifest block, next to the existing negative
   assertions, so a regression is caught by the suite rather than by a user.

## Definition of Done

- `npm pack --dry-run --json --silent` lists NO path under `company/state/`.
- The packed file list is otherwise unchanged from 0.2.4 (only the state files
  disappear and the version string moves).
- A fresh `install.sh` run into an empty dir still produces
  `company/state/{STATUS,RESUME,WORRIES,DECISIONS}.md` and `adherence.log`.
- An install over an EXISTING project does not overwrite its board.
- `npm test`, `bash tests/hooks/run_tests.sh`, and
  `bash tests/install/run_tests.sh` are all green.

## Invariants in play

- `company/` still ships wholesale apart from the four negated record trees.
- The installer, not the package, is the source of a project's state stubs.
- Existing user state is never overwritten on install or update.

## Fallbacks

- If `!company/state/**` fails to exclude the directory itself on some npm
  version, also negate the bare `company/state` path and tag the reason in a
  comment.
- If the install suite proves any packaged state file IS read at install time,
  stop and report - excluding it would then be a behavior change, not a fix.

## Out of scope

- The untracked runtime state files (already absent from a clean publish).
- Unpublishing or deprecating 0.2.4.
- Any change to what the installer scaffolds.
