# CI workflows

- `ci.yml` (push to main, PRs): runs the four test suites on {ubuntu, macos} x node {18,20,22},
  syntax-checks bin/ and lib/, asserts the npm pack manifest + a 2 MB unpacked-size budget, and
  runs the writing gate (rejects em/en dashes, smart quotes, ellipsis in tracked text).
- `release.yml` (published GitHub release, tag `v*`): reruns the four suites, verifies the tag
  matches package.json version, then publishes to npm via Trusted Publishing (OIDC) - no token
  anywhere, provenance automatic.

Manual setup (one time, after the package first exists on npm): npmjs.com -> claude-company ->
Settings -> Trusted Publisher -> GitHub Actions: org `devmesh-in`, repo `claude-company`,
workflow `release.yml` (allow the publish action). The first-ever publish cannot use trusted
publishing; it is done once locally with `AUTHORIZED=1 npm publish --access public --otp=<code>`.

Release flow: bump `version` in package.json -> commit -> create a GitHub release tagged `vX.Y.Z`
(matching the new version) -> `release.yml` publishes `claude-company@X.Y.Z` with provenance.
