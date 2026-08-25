# RELEASE 0.4.2 - stamp is a lock, not a ritual

_Prepared: 2026-08-25. Target: `task/cut-stamp-ceremony` merge into `main`._

The owner ships with `gh release create`. CI is the ladder.

## Contents

The stamp is a lock on `git commit`. It is not a second quality check and
it is not a reason to re-run a project's test suite. Field prompts now say:
run the gates that cover the change; if you already ran them, stamp from
those results; do not treat `--check` as a step; do not re-run because a
prompt, notes file, or README moved.

The auditor does not become the gate runner. A stale stamp is a finding.

## Semver

- **Current:** 0.4.1
- **Proposed:** 0.4.2
- **Rule:** pre-1.0, feat/fix -> patch
- **Why:** prompt and docs cut, no new enforcement

### Fixes

- CEO, lean, auditor, GATES, GIT, RELEASE, METHOD, and the field docs no
  longer teach "stale stamp means re-run the universe." (`Task: cut-stamp-ceremony`)

## Known limits

- `guard_commit` still requires a matching stamp. That is the lock, not
  a quality judgment. `HASH_EXCLUDES` is unchanged.
- Open P2/P3 worries remain in `company/state/WORRIES.md`.

## Ship

```bash
gh release create v0.4.2 --target <sha> \
  --notes-file company/RELEASE-0.4.2.md
```
