#!/usr/bin/env python3
"""Stop hook: refuse to finish a real task on red or stale gates.

Loop protection: if stop_hook_active is true, exit 0 immediately. Otherwise
collect the gating entries - active entries whose type is not quick/hotfix -
and check the one tree-wide gates.status stamp. No gating entries, or a green
fresh stamp, exits 0 silently.

FR-HP-50 scopes what happens on a missing/red/stale stamp, in two steps.

First, ATTRIBUTION. An entry whose work lives in its own worktree cannot be the
cause of THIS tree's dirty work_hash, so it is filtered out. Git's own record
is the source (`git worktree list --porcelain`); no session-keyed state and no
new field on the entry. Filtering is fail-SAFE in both directions: anything the
lookup cannot resolve counts as in-tree, so a repo with no worktrees, a git
that is missing, and an entry whose branch does not exist all behave exactly as
they did before this change.

Then the SINGLE-GATING-ENTRY rule over what survives. Exactly one attributable
entry means the stamp names that session's own tree, so the block is actionable
and is emitted unchanged. More than one, or none at all, means this hook cannot
name whose edit dirtied the tree, so it records one WARN line instead of
stopping a session that has nothing to fix.

Fails open.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "stop_gate"


def worktrees_by_branch(root):
    """Git's own record of which branch is checked out where.

    Returns {"refs/heads/<branch>": "<abs path>"}, and {} on ANY failure - no
    git, not a repo, a git too old for `worktree list`, unparseable output.
    Empty means nothing gets filtered, which is the pre-FR-HP-50 behavior, so
    every failure mode of this lookup lands on the safe side.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", root, "worktree", "list", "--porcelain"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            return {}
        text = proc.stdout.decode("utf-8", "replace")
    except Exception:
        return {}
    trees = {}
    path = None
    for line in text.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
        elif line.startswith("branch ") and path:
            trees[line[len("branch "):].strip()] = path
    return trees


def in_this_tree(entry, trees, root):
    """False only when git PROVES this entry's work is somewhere else.

    The slug-to-branch link is `task/<slug>`, which is canon in
    company/GIT.md ("one branch per workstream, created WITH its worktree") and
    is what makes this attribution possible without adding a field to the
    entry. If that convention is ever broken the lookup simply misses, the
    entry counts as in-tree, and the gate stays armed - the failure is a false
    block, never a false pass, which is the direction a gate may fail in.

    Note the coupling this creates with integration cleanup: once a merged
    lane's worktree is removed, its entry - if it was left in active-task.json
    - counts as in-tree again. That is the honest answer, because the lane's
    code IS in this tree after the merge, but it means pruning a merged entry
    is what keeps the gating set describing work actually in flight.
    """
    slug = entry.get("task")
    if not slug:
        return True
    path = trees.get("refs/heads/task/{}".format(slug))
    if not path:
        return True
    try:
        return os.path.realpath(path) == os.path.realpath(root)
    except Exception:
        return True


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    if payload.get("stop_hook_active"):
        sys.exit(0)

    try:
        root = c.project_root(payload)
        tasks = c.active_tasks(root)
        if not tasks:
            sys.exit(0)
        # FR-MST-09: quick/hotfix exempt THEMSELVES, not the tree. Any other
        # entry still in flight keeps the gate armed - the tree is red with
        # real work on it, and the exemption belongs to the exempt entry only.
        gating = [
            e for e in tasks if e.get("type") not in ("quick", "hotfix")
        ]
        if not gating:
            sys.exit(0)

        ok, reason = c.check_stamp(root)
        if ok:
            sys.exit(0)

        # OQ-HP-01 assumption, as amended by the CEO ruling of 2026-08-13:
        # attribution first, then the single-gating-entry rule over what it
        # leaves. The lookup runs only here, after the stamp has already come
        # back bad, so a green tree never pays for a subprocess.
        trees = worktrees_by_branch(root)
        attributable = [e for e in gating if in_this_tree(e, trees, root)]

        if len(attributable) != 1:
            # Name whoever this hook holds responsible: the entries that could
            # have dirtied this tree, or - when attribution cleared every one
            # of them - all the gating entries, qualified so the log says why
            # nothing was blocked. The cap must cover them all: slug_list
            # truncates at 3 by default, and a truncated WARN would hide a
            # session's name from the only record that mentions it.
            named = attributable or gating
            target = c.slug_list(named, cap=max(len(named), 1))
            if not attributable:
                target += " (all in other worktrees)"
            c.adherence_log(root, HOOK, "WARN", target, reason)
            sys.exit(0)

        slug = attributable[0].get("task", "(unknown)")
        c.adherence_log(root, HOOK, "BLOCK", slug, reason)
        decision = {
            "decision": "block",
            "reason": (
                "Active task '{}' has red or stale gates. Run the gate suite "
                "(/gates) and make it green, or close YOUR entry in "
                "company/state/active-task.json with a targeted Edit, before "
                "finishing.".format(slug)
            ),
        }
        print(json.dumps(decision))
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
