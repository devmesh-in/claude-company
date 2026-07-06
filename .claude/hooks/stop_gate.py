#!/usr/bin/env python3
"""Stop hook: refuse to finish a real task on red or stale gates.

Loop protection: if stop_hook_active is true, exit 0 immediately. Otherwise, if
an active task exists whose type is not quick/hotfix and the gates.status is
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
        task = c.active_task(root)
        if not isinstance(task, dict):
            sys.exit(0)
        if task.get("type") in ("quick", "hotfix"):
            sys.exit(0)

        ok, reason = c.check_stamp(root)
        if ok:
            sys.exit(0)

        slug = task.get("task", "(unknown)")
        c.adherence_log(root, HOOK, "BLOCK", slug, reason)
        decision = {
            "decision": "block",
            "reason": (
                "Active task '{}' has red or stale gates. Run the gate suite "
                "(/gates) and make it green, or close the task in "
                "company/state/active-task.json, before finishing.".format(slug)
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
