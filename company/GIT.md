# GIT.md - Worktrees, branches, commits, and integration

How this company uses git. Every agent that touches the repository follows
this page; the CEO enforces it at integration. The goal is that parallel
teams cannot collide, every commit traces to a work order, and the repository
tells the truth about what happened.

## The model in one picture

```text
main                          integration branch. Protected: no direct push
                              (hook-enforced), merges by the CEO only.
  task/<slug>                 one branch per workstream, created WITH its
                              worktree. Lives in .claude/worktrees/<slug>.
    (developers)              work INSIDE the lead's worktree, on the
                              disjoint directories their task orders name.
```

One workstream = one worktree = one branch = one accountable tech lead.

## Worktrees

Create (CEO does this at dispatch):

```bash
git worktree add .claude/worktrees/<task-slug> -b task/<task-slug>
```

- **Developers do not get their own worktrees.** A lead's developers share
  the lead's worktree and are kept apart by directory ownership, which their
  task orders name exactly. Separate worktrees per developer would multiply
  dependency installs and stale build artifacts without adding isolation the
  ownership map does not already give.
- **One agent per directory, ever.** If two agents need the same directory,
  the decomposition is wrong; fix the task orders, not the git layout.
- **QA works in the same worktree read-only** and saves screenshots to
  `company/evidence/<task-slug>/`, which is committed with the task: the
  evidence bundle is part of the deliverable.
- Never nest a worktree inside another worktree, and never run two leads in
  one worktree.

## Commits

- **Conventional messages, scoped to the workstream:**
  `feat(waitlist): add signup endpoint`, `fix(api): reject expired tokens`.
  Subject line 72 characters or less, imperative mood.
- **Reference the work order.** Every commit on a task branch carries a
  trailer naming the brief: `Task: <task-slug>`. Cite requirement ids in the
  body when a commit implements them (`Implements: FR-03, FR-04`).
- **Stage explicit paths only.** Never `git add -A` or `git add .` from a
  worktree: symlinked `node_modules` and stray artifacts get staged and can
  destroy the real thing on checkout. Name the files you mean.
- **Commit per coherent step**, not per session. A session must not end with
  uncommitted work unless the report says so and why.
- **Never commit directly on main while a task is active** - work belongs on
  the task branch (hook-enforced: the commit guard blocks it and prints the
  branch recipe). Integration merges on main are the CEO's and are allowed.

## Sync discipline

- **Rebase at session start.** An agent resuming work in an existing
  worktree rebases onto main first: `git rebase main`. Same after the CEO
  applies any change request to a frozen surface.
- **Conflicts have meaning.** A conflict inside your owned directories is
  yours to resolve now. A conflict that crosses an ownership boundary means
  the ownership map is wrong: stop and surface it; do not resolve it by
  judgment.

## Integration (CEO only)

Integrate only after verification (gates rerun on the integrated result,
ownership diff checked, evidence judged - see `ORCHESTRATOR.md`). The
mechanics depend on whether the project has a remote:

**PR mode - when `origin` exists and `gh` is available (the default for any
GitHub-backed project).** The audit record becomes a reviewable pull request
instead of a merge-commit message:

```bash
git push -u origin task/<task-slug>
gh pr create --title "task/<slug>: <mission in one line>" --body-file <evidence>
# after checks are green (branch protection gates the merge):
gh pr merge --merge --delete-branch
```

- The PR body IS the evidence report: the pasted gate ladder, the ownership
  diff summary, FR checklist, QA screenshot references, CRs filed, and the
  `Task: <slug>` trailer. A human (or the owner's branch protection) can now
  review the same evidence the CEO judged.
- Remote branch protection is the outer gate: if the project requires green
  checks, the merge physically waits for them - the same enforcement
  philosophy, applied at the repo boundary.
- The CEO still never pushes main. The task branch is the only thing that
  ever goes up; the PR merge is what lands it.

**Local mode - no remote configured.** The merge commit is the audit record:

```bash
git merge --no-ff task/<task-slug>
```

```text
merge task/waitlist: signup + admin view

Verified: gates green on integrated main, ownership diff clean,
QA evidence judged against acceptance criteria.
Task: waitlist
```

**Both modes:**

- **Dependency order**: the API side merges before the UI that calls it;
  within a program wave, providers before consumers.
- **After every merge**: rerun the gates on the integrated main and stamp,
  then clean up.

## Cleanup

After a task integrates (or is abandoned):

```bash
git worktree remove .claude/worktrees/<task-slug>
git branch -d task/<task-slug>
git worktree prune
```

- Use `-d`, not `-D`. A branch that will not delete cleanly holds unmerged
  work: investigate before forcing, because a "failed" agent may have
  finished on disk without reporting.
- **Session-start hygiene (CEO):** `git worktree list` and compare against
  RESUME.md's in-flight table. A worktree nobody claims is either unreported
  finished work (recover it) or an abandoned task (record the abandonment in
  STATUS, then remove).

## Hazards (learned the hard way)

- `git add -A` in a worktree with symlinked `node_modules` can stage the
  symlink and destroy the real directory. Explicit paths only.
- A dead agent's worktree may contain completed work; a blind respawn
  double-writes. Read the worktree's `git log` first.
- A worktree's green gate stamp proves that worktree only. Stale artifacts
  in worktrees mask contract drift; the integrated-main stamp is the one
  that counts.
- Pushing main is owner territory: no agent pushes to main/master
  (hook-blocked), in either mode. In PR mode the CEO pushes ONLY the task
  branch; in local mode nothing is pushed unless the owner asks.
