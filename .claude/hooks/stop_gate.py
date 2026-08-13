#!/usr/bin/env python3
"""Stop hook: refuse to finish a real task on red or stale gates.

Loop protection: if stop_hook_active is true, exit 0 immediately. Otherwise
collect the gating entries - active entries whose type is not quick/hotfix -
and check the one tree-wide gates.status stamp. No gating entries, or a green
fresh stamp, exits 0 silently.

FR-HP-50 scopes what happens on a missing/red/stale stamp by how many gating
entries are in flight. At exactly ONE gating entry the stamp names that
session's own tree, so the block is actionable: log BLOCK and emit the Stop
block decision as JSON on stdout, unchanged. At MORE THAN ONE gating entry the
stamp is a shared fact and this hook cannot tell which session dirtied it, so
blocking would stop a session that has nothing to fix; instead the finding is
recorded as one WARN line naming every gating slug, which is where the CEO
reads it, rather than sent to a turn that cannot act on it.

Fails open.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "stop_gate"


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

        # OQ-HP-01 assumption: the block is scoped to the case where it is
        # actionable. One gating entry means the red stamp belongs to the only
        # session in flight, so it blocks exactly as before. More than one and
        # the stamp is a shared fact with no owner this hook can name, so it
        # warns in the log instead of blocking a session that cannot fix it.
        if len(gating) > 1:
            # cap must cover every gating entry: slug_list truncates at cap=3
            # by default and a truncated WARN would hide a session's name from
            # the only record that mentions it.
            c.adherence_log(
                root, HOOK, "WARN",
                c.slug_list(gating, cap=max(len(gating), 1)), reason,
            )
            sys.exit(0)

        slug = gating[0].get("task", "(unknown)")
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
