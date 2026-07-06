# CI workflows

- `ci.yml` (push to main, PRs): runs the four test suites on {ubuntu, macos} x node {18,20,22},
  syntax-checks bin/ and lib/, asserts the npm pack manifest + a 2 MB unpacked-size budget, and
  runs the writing gate (rejects em/en dashes, smart quotes, ellipsis in tracked text).
- `release.yml` (published GitHub release, tag `v*`): reruns the four suites, verifies the tag
  matches package.json version, then publishes to npm with provenance.

Manual setup (one time): add an npm Automation token as the `NPM_TOKEN` repo secret
(Settings -> Secrets and variables -> Actions).

Release flow: bump `version` in package.json -> commit -> create a GitHub release tagged `vX.Y.Z`
(matching the new version) -> `release.yml` publishes `claude-company@X.Y.Z` with provenance.
