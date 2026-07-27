#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): enforce spec-before-code.

Writing SOURCE CODE requires an active brief. Non-source files (docs, config,
data, dotfiles, and anything under company/, .claude/, docs/, .github/) are
exempt. Hotfix entries exempt THEMSELVES from the check (logged); every other
entry in flight is still evaluated, and one unusable brief blocks. Fails open
on error.
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
    "BLOCKED: no active brief. Self-serve fix:\n"
    "1) Write company/briefs/brief-<slug>.md from "
    "company/templates/BRIEF-TEMPLATE.md covering what you are about to build.\n"
    "2) ADD your entry to the tasks list in "
    "company/state/active-task.json with a targeted Edit. Other sessions own "
    "the other entries, so never rewrite the whole file. Your entry:\n"
    "   {\"task\": \"<slug>\", \"type\": \"feature\", "
    "\"brief\": \"company/briefs/brief-<slug>.md\", \"test_scope\": false}\n"
    "   If the file does not exist yet, create it holding only your entry:\n"
    "   {\"version\": 2, \"tasks\": [ {\"task\": \"<slug>\", "
    "\"type\": \"feature\", \"brief\": \"company/briefs/brief-<slug>.md\", "
    "\"test_scope\": false} ]}\n"
    "3) Retry the edit.\n"
    "If you are the CEO handling a production emergency, set type to hotfix "
    "(logged, not silent)."
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


def render_offenders(offenders):
    """FR-MST-30: name every entry at fault and say what is wrong with it.

    Every offender is listed, uncapped: each one needs its own fix, and a
    recipe that hides half the work is not a recipe.
    """
    lines = ["BLOCKED: active task entries without a usable brief:"]
    for entry, brief in offenders:
        name = entry.get("task") or "<task-slug>"
        if brief is None:
            lines.append("  {} - no brief field".format(name))
        else:
            lines.append(
                "  {} - brief '{}' does not exist".format(name, brief)
            )
    lines.append(NO_BRIEF_MSG)
    return "\n".join(lines)


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

        tasks = c.active_tasks(root)

        # FR-MST-05 step (a). THE EMPTY CHECK MUST STAY FIRST. The brief check
        # below is an ALL over the non-hotfix entries, and an ALL is vacuously
        # TRUE on an empty list - so evaluating it before this guard would
        # silently flip the gate from BLOCK to ALLOW exactly when NO task is
        # active, which is the case it exists to catch. Do not reorder.
        if not tasks:
            c.block(root, HOOK, rel, "no active brief", NO_BRIEF_MSG)

        # (b) hotfix is a per-entry EXEMPTION, never an ANY waiver: it removes
        # its own entry from the check and nothing else. Only when EVERY entry
        # is a hotfix does the whole gate step aside.
        non_hotfix = [e for e in tasks if e.get("type") != "hotfix"]
        if not non_hotfix:
            c.log_bypass(
                root, HOOK, rel,
                c.qualify_reason("hotfix mode", tasks, tasks),
            )
            sys.exit(0)

        # (c) ALL over the non-hotfix entries: one unusable brief blocks.
        offenders = []  # (entry, brief-or-None)
        for entry in non_hotfix:
            brief = entry.get("brief")
            if not brief:
                offenders.append((entry, None))
                continue
            brief_path = brief
            if not os.path.isabs(brief_path):
                brief_path = os.path.join(root, brief)
            if not os.path.exists(brief_path):
                offenders.append((entry, brief))

        if offenders:
            if len(tasks) == 1:
                # BR-MST-02: the single-entry rendering is byte-identical to
                # what this hook produced before multi-entry support landed.
                entry, brief = offenders[0]
                if brief is None:
                    c.block(root, HOOK, rel, "no active brief", NO_BRIEF_MSG)
                c.block(
                    root, HOOK, rel, "brief file missing: " + str(brief),
                    "BLOCKED: active brief '{}' does not exist. {}".format(
                        brief, NO_BRIEF_MSG
                    ),
                )
            c.block(
                root, HOOK, rel,
                c.qualify_reason(
                    "no usable brief", tasks, [e for e, _b in offenders]
                ),
                render_offenders(offenders),
            )
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
