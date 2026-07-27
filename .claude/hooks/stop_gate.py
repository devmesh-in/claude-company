#!/usr/bin/env python3
"""Stop hook: refuse to finish a real task on red or stale gates.

Loop protection: if stop_hook_active is true, exit 0 immediately. Otherwise, if
ANY active entry has a type that is not quick/hotfix and the gates.status is
missing/red/stale, emit the Stop-hook block decision as JSON on stdout and exit
0. Anything else exits 0 silently. Fails open.
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

        if len(gating) == 1:
            slug = gating[0].get("task", "(unknown)")
        else:
            slug = c.slug_list(gating)
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
