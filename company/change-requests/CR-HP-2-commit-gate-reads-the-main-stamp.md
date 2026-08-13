# CR-HP-2: commit gate reads the main checkout's stamp, never the worktree's

_Requesting agent/task: tech-lead / hp-writers (L4). Date: 2026-08-13._
_Status: PROPOSED_

## Frozen surface affected

`.claude/hooks/guard_commit.py` line 288 - not a registry entry in
`company/frozen-surfaces.json`, but an enforcement hook outside this task's
owned paths, so it is raised rather than patched. `company/state/gates.status`
IS frozen (`always` list), which is a second reason no lane should reach for a
local fix.

## Why (cite the requirement)

FR-HP-11 and FR-HP-28, which disagree with each other on disk.

FR-HP-11 made `guard_commit` judge the BRANCH by the tree git actually operates
on: `git_cwd()` / `seg_git_dir()` prefer the payload cwd or the `-C` path, with
a docstring stating that a commit from a worktree "must be judged by that
worktree's branch, even when CLAUDE_PROJECT_DIR (and thus root) points at the
main checkout".

FR-HP-28 made `company/run-gates.sh` resolve its own root from the script's
location rather than `CLAUDE_PROJECT_DIR`, precisely so a worktree stamps
itself (line 46, and line 221 stamps with `CLAUDE_PROJECT_DIR="$PROJECT_ROOT"`).

The gate-stamp check was not moved with either. Line 288 still reads:

```python
ok, reason = c.check_stamp(root)
```

where `root` is `c.project_root(payload)`, which prefers `CLAUDE_PROJECT_DIR` -
the MAIN checkout. So one hook judges the branch by the worktree and the gate
stamp by the main checkout.

The consequence is not cosmetic. A worktree lane cannot satisfy its own commit
gate by any action available to it:

- Running `company/run-gates.sh` in the worktree writes
  `<worktree>/company/state/gates.status`, which `check_stamp(root)` never
  reads. Running its own gates cannot unblock it.
- `work_hash(root)` fingerprints the MAIN checkout. `.claude/worktrees/` is
  gitignored there (`.gitignore:3`), so a lane's own work provably does not
  contribute to it - verified with `git check-ignore -v`.
- Therefore whether a lane may commit depends entirely on whether some other
  session left the MAIN checkout content-identical to its last gate run.
  Observed live during this task: the main stamp's `work_hash` changed from
  `tree:3aec22f9...` to a different value between two reads minutes apart,
  from sibling-lane activity this lane has no visibility into or control over.

Both failure directions are live:

- FALSE BLOCK (hit by this task): five green suites in the worktree, and the
  commit is refused because an unrelated checkout drifted.
- FALSE PASS (the worse one): a sibling lane running gates in the main checkout
  leaves a fresh green stamp that green-lights a worktree commit whose own
  suites were never run. The gate then certifies nothing.

## Exact proposed change

In `.claude/hooks/guard_commit.py`, judge the stamp by the same directory the
branch is judged by. The resolved directory is already computed for the branch
checks in that block; reuse it rather than `root`:

```python
-                ok, reason = c.check_stamp(root)
+                # The stamp must describe the tree being committed, the same
+                # tree FR-HP-11 judges the branch by. Reading root's stamp lets
+                # an unrelated checkout both block a green worktree and
+                # green-light an ungated one.
+                ok, reason = c.check_stamp(branch_dir)
```

using whichever local in that scope holds the `seg_git_dir(...)` / `git_cwd(...)`
result. `check_stamp` and `work_hash` already take a root argument, so no
kernel change is needed.

Correctness note for whoever implements it: `read_stamp` must then resolve
against the worktree too, and a worktree that has never run gates must report
"no gates.status stamp (gates have not been run)" and BLOCK. That is the
correct answer and is stricter than today's behavior, not looser - it is what
makes the stamp mean "the tree in this commit was gated".

## Blast radius

- Every workstream committing from a worktree, which is every lead in the
  harness-port program. This is the mechanism all of them depend on.
- Hooks suite: the guard_commit gate-stamp cases in `tests/hooks/` will need a
  worktree-rooted fixture. Sibling coverage exists in
  `tests/hooks/test_multi_task_gates.py` and `test_v1_v2_parity.py`.
- No payload or installer change, so the CLI, install, TUI and update suites
  should be unaffected; re-run all five regardless.
- After it lands, every lane must run its OWN five suites (or its own
  `run-gates.sh`) before committing. Lanes that were passing on a borrowed
  stamp will start blocking. That is the point of the change.

## Owner sign-off needed?

No. This restores an existing invariant (gates are the definition of done, and
the stamp must describe the gated tree) rather than weakening one. It touches
no money, determinism or prod schema. It does tighten enforcement, so it is
worth an explicit note on `DECISIONS.md` when applied.

## Workaround if rejected

None available to this lane, and none was taken. hp-writers sat staged and
uncommitted on `task/hp-writers`, with all five suites green, until the CEO
refreshed the main checkout's stamp; it then committed normally. This lane did
not use `--no-verify`, did not edit `company/state/gates.status`
(checksum-sealed, and hand-editing is detected by `check_stamp`), and did not
run `company/run-gates.sh` - which was both forbidden by its dispatch and, per
the analysis above, would not have unblocked it.

Waiting for someone else to refresh an unrelated checkout is not a workaround,
it is the defect. It is also the FALSE PASS in disguise: the stamp that finally
let this lane commit describes the main checkout, and would have let it commit
just as readily with no suites run at all.

## Corroboration and today's proximate cause (added at commit time)

Two other lanes filed this same finding independently on 2026-08-13. The
churn behind the staleness was identified as `.claude/agent-memory/`, untracked
and not ignored, so every agent memory note re-staled the main stamp for every
session; it is gitignored now. That removes one noisy source of drift - it does
NOT address this CR. Any edit in the main checkout still stales every worktree
lane's commit gate, and a green main stamp still certifies nothing about the
tree being committed. The one-line fix below is still open.

---
_CEO decision and remarks:_
