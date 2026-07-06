#!/usr/bin/env python3
"""SessionStart hook: print a compact claude-company state digest.

If company/state/RESUME.md or STATUS.md exist, emit a plain-text digest (<= 60
lines): the first 40 lines of RESUME.md, the first 20 of STATUS.md, and one
line for the active task. Always exits 0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

MAX_LINES = 60


def head_lines(path, n):
    try:
        with open(path) as f:
            out = []
            for _ in range(n):
                line = f.readline()
                if not line:
                    break
                out.append(line.rstrip("\n"))
            return out
    except Exception:
        return []


def main():
    payload = c.read_stdin_json() or {}
    try:
        root = c.project_root(payload)
        state = os.path.join(root, "company", "state")
        resume = os.path.join(state, "RESUME.md")
        status = os.path.join(state, "STATUS.md")
        if not (os.path.exists(resume) or os.path.exists(status)):
            sys.exit(0)

        out = ["claude-company state digest"]
        if os.path.exists(resume):
            out.append("-- RESUME.md --")
            out.extend(head_lines(resume, 40))
        if os.path.exists(status):
            out.append("-- STATUS.md --")
            out.extend(head_lines(status, 20))
        task = c.active_task(root)
        if isinstance(task, dict):
            out.append(
                "active-task: {} ({}) brief={}".format(
                    task.get("task"), task.get("type"), task.get("brief")
                )
            )
        print("\n".join(out[:MAX_LINES]))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
