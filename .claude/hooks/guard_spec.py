#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): enforce spec-before-code.

Writing SOURCE CODE requires an active brief. Non-source files (docs, config,
data, dotfiles, and anything under company/, .claude/, docs/, .github/) are
exempt. A hotfix task bypasses the check (logged). Fails open on error.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_spec"

NON_SOURCE_EXT = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
}
EXEMPT_DIRS = {"company", ".claude", "docs", ".github"}

NO_BRIEF_MSG = (
    "BLOCKED: no active brief. The CEO dispatches work via briefs "
    "(company/briefs/). Set company/state/active-task.json to point at an "
    "existing brief, or use hotfix mode (\"type\": \"hotfix\")."
)


def is_source(rel, base):
    if not base:
        return False
    if base.startswith("."):
        return False
    segs = rel.split("/")
    if any(s in EXEMPT_DIRS for s in segs[:-1]):
        return False
    ext = os.path.splitext(base)[1].lower()
    if ext in NON_SOURCE_EXT:
        return False
    return True


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    root = c.project_root(payload)
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        sys.exit(0)

    try:
        rel = c.rel_path(root, file_path)
        base = os.path.basename(rel) or os.path.basename(file_path)
        if not is_source(rel, base):
            sys.exit(0)

        task = c.active_task(root)
        if isinstance(task, dict) and task.get("type") == "hotfix":
            c.log_bypass(root, HOOK, rel, "hotfix mode")
            sys.exit(0)

        brief = task.get("brief") if isinstance(task, dict) else None
        if not brief:
            c.block(root, HOOK, rel, "no active brief", NO_BRIEF_MSG)

        brief_path = brief
        if not os.path.isabs(brief_path):
            brief_path = os.path.join(root, brief)
        if not os.path.exists(brief_path):
            c.block(
                root, HOOK, rel, "brief file missing: " + str(brief),
                "BLOCKED: active brief '{}' does not exist. {}".format(
                    brief, NO_BRIEF_MSG
                ),
            )
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
