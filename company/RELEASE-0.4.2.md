# RELEASE 0.4.2 - stamp gates merge onto main, not commit

_Prepared: 2026-08-25. Target: `task/merge-gate-stamp` merge into `main`._
_Status: owner instructed this session to ship via GitHub release._

The owner ships with `gh release create`. CI is the ladder.

## Contents

Parallel sessions can commit their own work while a sibling's tests keep the
shared suite red. `git merge` onto main/master still needs a green, fresh
acting-tree stamp. The stamp stays the sensor that keeps red off main; it
stops being a commit lock. Merge of main into a task branch is not
stamp-gated (that is the update path).

Secrets, undeclared frozen drift, the task-branch rule, no_slop, guard_tests,
and guard_spec still gate commit. Hotfix and placeholder-only `gates.config`
still log BYPASS on the merge stamp path.

## Semver

- **Current:** 0.4.1
- **Proposed:** 0.4.2
- **Rule:** pre-1.0, feat bumps PATCH
- **Why:** enforcement timing change, not a new layer

### Breaking

None. Field installs keep `run-gates.sh` / `gates.status` / content hashing.

### Features

- `git commit` is not stamp-gated. A lane can land its own work while a
  sibling keeps the shared suite red. (`Task: merge-gate-stamp`)
- `git merge` onto main/master still requires a green, fresh acting-tree
  stamp (CR-HP-2). (`Task: merge-gate-stamp`)
- Merge of main into a task branch is not stamp-gated. (`Task: merge-gate-stamp`)

### Fixes

- Session-start digest and field docs no longer call the stamp a commit
  lock. (`Task: merge-gate-stamp`)

## Known limits

- PR-mode `gh pr merge` never hits this hook. CI is the outer ladder.
- Open P2/P3 worries remain in `company/state/WORRIES.md`.
- Witnesses: `python3 .claude/hooks/witness_check.py --check` must be green
  on the SHA you ship.

## Ship

```bash
gh release create v0.4.2 --target <sha> \
  --notes-file company/RELEASE-0.4.2.md
```
