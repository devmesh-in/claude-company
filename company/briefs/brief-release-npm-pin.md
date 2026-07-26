# Brief: release-npm-pin

Task slug: `release-npm-pin`
Class: quick

## Read first

- `.github/workflows/release.yml` lines 15-40
- The failed run: actions/runs/30215720848, step "Upgrade npm for trusted publishing"

## Context

The v0.2.5 release workflow failed and nothing was published. The registry is
still on 0.2.4.

`release.yml:22-24` pins `node-version: 20`, then `:29` runs
`npm install -g npm@latest`. npm@latest is now 12.0.1, which declares
`engines.node ^22.22.2 || ^24.15.0 || >=26.0.0`. On node 20.20.2 that install
fails EBADENGINE and the job dies before the tests, the tag check, or publish.

This is unpinned-dependency drift, not a defect in the released code. It would
break EVERY release from now on, and it broke silently the moment npm 12
shipped - nothing in this repo changed.

The step exists because trusted publishing needs npm >= 11.5.1 and node 20
bundles an older npm (10.8.2). That requirement is satisfied by any npm 11.x,
which supports node 20.

## You own

- `.github/workflows/release.yml`

## Scope

1. Pin the upgrade to a major that is compatible with the pinned node:
   `npm install -g npm@^11.5.1 && npm --version`
2. Update the adjacent comment to say WHY it is pinned - an unpinned
   `npm@latest` re-breaks the release the next time npm raises its node floor.

## Definition of Done

- The resolved npm satisfies `>= 11.5.1` and installs cleanly on node 20.
- No other workflow step changes.
- `npm test`, `bash tests/hooks/run_tests.sh`, `bash tests/install/run_tests.sh`
  all still green (they do not touch this file, so this is a no-regression
  check).

## Invariants in play

- Never publish red: the four test steps must keep running before publish.
- The tag-versus-package.json version check stays exactly as it is.
- Publishing stays OIDC trusted publishing with no token.

## Fallbacks

- If npm 11.x ever stops satisfying trusted publishing, raise `node-version` to
  24 and pin the npm major to match, changing BOTH together and saying so in
  the comment. Never leave one floating against the other.

## Out of scope

- The CI workflow (`ci.yml`) - it does not upgrade npm.
- Re-publishing 0.2.3 or 0.2.4.
- Any change to what is packaged.
