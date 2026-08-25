# RELEASE: <proposed tag, e.g. v0.2.0>

_Target commit: <sha>. Date: <YYYY-MM-DD>._

The owner ships with `gh release create`. CI is the ladder.

## Changelog

```bash
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
git log --no-merges --pretty='%s%n%b' "${LAST_TAG:+$LAST_TAG..}HEAD"
```

### Breaking
- <subject> (`Task: <slug>`)

### Features
- <subject> (`Task: <slug>`)

### Fixes
- <subject> (`Task: <slug>`)

## Semver

- **Current:**
- **Proposed:**
- **Rule:** pre-1.0 (breaking -> minor; feat/fix -> patch) or post-1.0
- **Why (one line):**

## Known limits

- Open P2/P3 worries, deferred FRs, or "none".
- Witnesses: `python3 .claude/hooks/witness_check.py --check` must be green
  on the SHA you ship.

## Ship (OWNER-ONLY unless they said so in-session)

```bash
gh release create <tag> --target <target-commit> \
  --notes-file company/RELEASE-<version>.md
```
