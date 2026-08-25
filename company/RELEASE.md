# RELEASE.md - PREPARED by the company and SHIPPED by the owner

The company prepares notes if asked. The owner ships. Direct in-session
owner instruction to ship authorizes `gh release create` for that release
only (DECISIONS #17). `.github/workflows/release.yml` re-runs the suites and
publishes to npm via OIDC. There is no local `npm publish`. There is no
local ten-rung readiness list. CI is the ladder.

```text
company                               owner
  changelog + notes (if asked)   ->   gh release create vX.Y.Z
  version bump on main                release.yml publishes to npm
```

## If the owner said ship

1. Confirm `package.json` version and that `main` is the target SHA.
2. If notes do not exist, write `company/RELEASE-<version>.md` from the
   changelog since the last tag (conventional commits, `Task:` slugs).
3. Run:

```bash
gh release create v<version> --target <sha> \
  --notes-file company/RELEASE-<version>.md
```

The tag must equal `v` plus `package.json`'s version or `release.yml` exits
before publish.

A version-bump commit still needs a green fresh stamp (`guard_commit`).
Confirm `python3 .claude/hooks/gate_stamp.py --check`. Run this project's
real suites (the ones `CLAUDE.md` names, not placeholder `run-gates.sh`)
only if the stamp cannot support the commit. Do not re-run because you
wrote the notes file after a green stamp: bump, stamp if needed, commit,
then write notes, or exclude notes from the hash by committing them with
the bump in one shot after the suites.

## Semver

- **Pre-1.0:** breaking bumps MINOR; feat or fix bumps PATCH.
- **Post-1.0:** standard semver.

## Changelog range

```bash
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
git log --no-merges --pretty='%s%n%b' "${LAST_TAG:+$LAST_TAG..}HEAD"
```

No tag means first release; say so in the notes.

## Barred

No skill, agent, or hook runs `git tag`, `npm publish`, or `gh release create`
on its own initiative. Owner-said-ship is the exception for `gh release create`.
Rollback is also the owner's (`npm deprecate`, retag).
