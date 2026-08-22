# BRIEF: acting-tree

_Type: feature. Spec: none - this brief is the spec. Lead: tech-lead.
Date: 2026-08-13. Tracking issue: #114._

## Mission

Every hook in this repo resolves the tree it judges from `CLAUDE_PROJECT_DIR`,
which is always the MAIN checkout. Every delegated agent works in a worktree.
That single mismatch produced roughly two hours of false blocks in one session
AND left the most important guard in the system completely inert.

Fix the class, not the instances: **a hook judges the tree that contains the
thing being acted on.**

The one hard constraint: this changes what BLOCKS. Some of these fixes turn
ALLOWs into BLOCKs, which is the correct direction and is the point. Every such
transition needs a test and a line in your report.

## The P0, do this first

`guard_secrets` reads `c._git(root, ["diff", "--cached", "-U0"])` at
`guard_secrets.py:202`, where root is the main checkout. A developer staging and
committing inside `.claude/worktrees/<slug>` has its diff scanned against MAIN's
index, which is almost always empty, so the hook exits at :204 and the commit is
never scanned. **Every delegated commit in this repo's history went unscanned
for secrets.** Zero `guard_secrets` lines in 324 log entries over five weeks -
consistent with a hook that has never had anything to look at.

It adopted `guard_commit`'s PARSER under FR-HP-12 and did not adopt its TREE
RESOLUTION. Fix that: resolve per commit segment, the way `guard_commit` already
does with `git_cwd` / `seg_git_dir`. Lift those into `_common` rather than
copying them - a second implementation of tree resolution is how this class of
bug returns. Prove it with a staged secret in a real worktree, blocked.

## The rest, same class

1. **`guard_commit.py:288`** - `check_stamp(root)` reads MAIN's stamp, so a lane
   that gated its own tree green is still blocked and only someone else can
   clear it. Filed independently by three lanes as CR-HP-2. Use the acting
   tree's stamp. This is the single largest source of friction in the log: 23
   stale-stamp blocks.
2. **`guard_tests.py:94`** - hand-rolled `toks[1] == "rm"` parse, so
   `git -C <dir> rm tests/foo.py` is invisible. Exactly the defect FR-HP-10
   closed in `guard_commit`. Delegate to the shared parser. Also resolve
   `test_scope` from the acting tree (WORRIES row 37, open, has blocked five
   lanes).
3. **`guard_spec.py`** - no worktree or out-of-tree exemption at all, unlike
   `guard_provenance` mode E which calls `in_worktree_or_out_of_tree` first.
   Consequence in the log: it blocked a write to the SCRATCHPAD directory that
   the system prompt instructs every agent to use, because `rel_path` fell back
   to stripping the leading slash and `segs[0]` became `private`. Adopt the
   exemption and stop gating paths outside the project.
4. **`guard_provenance.py:233`** - `in_worktree_or_out_of_tree` hardcodes
   `/.claude/worktrees/` while `_common._enclosing_checkout` is deliberately
   convention-free. A worktree anywhere else is treated as main-checkout source.
   Use the derivation. NOTE: `guard_provenance.py` is owned by an open PR
   (#112) - do NOT edit it. Report this one and I will route it.
5. **Block messages that are not recipes.** `guard_commit`'s branch recipe says
   `git switch -c task/<slug>` to a tree already on that branch, because
   `seg_git_dir` cannot resolve `git -C "$VAR"` (raw command text, variable
   unexpanded). Say so in the message. `guard_spec` and `guard_tests` both tell
   the reader to edit `company/state/active-task.json` with a RELATIVE path
   that, from a worktree cwd, names a file that does not exist there.

## You own

`.claude/hooks/guard_secrets.py`, `.claude/hooks/guard_commit.py`,
`.claude/hooks/guard_tests.py`, `.claude/hooks/guard_spec.py`,
`.claude/hooks/_common.py`, and tests under `tests/hooks/`.

NOT `guard_provenance.py` (PR #112) and NOT `stop_gate.py` (PR #113). Both are
open PRs. Report anything they need.

## Definition of Done

- [ ] A staged secret committed from inside a real `git worktree` is BLOCKED.
      That test is the point of this lane; write it first and watch it fail.
- [ ] A lane that runs its own gates green in its own worktree can commit
      without anyone else acting
- [ ] `git -C <dir> rm tests/foo.py` is gated
- [ ] A write to a path outside the project is not treated as project source
- [ ] Tree resolution exists ONCE, in `_common`, and every caller uses it
- [ ] Every ALLOW-to-BLOCK transition has a test and a report line
- [ ] All five suites from your worktree root, pasted. `bash tests/install/run_tests.sh`
      matters most here - it drives the runner and the installer.
- [ ] Conventional commits, `Task: acting-tree` trailer, explicit staged paths

## Out of scope

Cutting or demoting any hook - that is an owner decision in flight. Do not
touch `stop_gate.py`, `guard_provenance.py`, `risk_score.py`, or `no_slop.py`.

## Report back

What changed, five suites pasted, the ALLOW-to-BLOCK list, what the two open
PRs need from you, worries, 1-3 witness candidates.
