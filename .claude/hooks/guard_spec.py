#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): enforce spec-before-code.

Writing SOURCE CODE requires an active brief. Non-source files (docs, config,
data, dotfiles, and anything under company/, .claude/, docs/, .github/) are
exempt. quick and hotfix entries exempt THEMSELVES from the check (logged);
every other entry in flight is still evaluated, and one unusable brief blocks.
An existing-but-unparseable task file is a torn read and allows the edit.
Fails open on error.
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
    # FR-HP-13: the exempt names are the MACHINERY directories at the
    # REPOSITORY ROOT, so the test anchors at segment zero. Matching any
    # segment exempted product code the moment a directory happened to be
    # called company/ or docs/ - app/company/billing.py needed no brief, no
    # execution decision, and never counted as dirty source for the audit
    # demand. Anchoring here is what makes that code gated again.
    if segs and segs[0] in EXEMPT_DIRS:
        return False
    ext = os.path.splitext(base)[1].lower()
    if ext in NON_SOURCE_EXT:
        return False
    return True


def exempt_reason(exempt):
    """The bypass reason for a set of entries that are ALL exemption types.

    Derived from the types actually present, never fixed: a hotfix-only set
    must keep logging the literal "hotfix mode" it logged before quick became
    an exemption type, because that string is what the adherence log has
    always carried for that case and what reads back out of it.

    The type pair here is the same pair as the gating predicate in main() and
    is only ever asked about entries that predicate already excluded, so it
    stays fixed in that order: quick, then hotfix, both when both are present.
    """
    present = set(e.get("type") for e in exempt)
    names = [t for t in ("quick", "hotfix") if t in present]
    return "/".join(names) + " mode"


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

        # FR-HP-32: a torn read is not an absent task file. active-task.json
        # is written whole by several sessions, so a reader can catch its
        # truncated middle - and blocking work that HAS a good brief because
        # another session was mid-write is a wrong block. Fail open on it.
        #
        # THE ORDER HERE IS LOAD-BEARING. c.active_tasks() already retries a
        # torn read internally before giving up; c.active_tasks_unreadable()
        # does NOT retry. Probing unreadable first would throw that retry away
        # and fail open on every transient blip, which loses real enforcement.
        # Ask active_tasks() first, consult unreadable only on its empty
        # answer. Do not reorder.
        if not tasks and c.active_tasks_unreadable(root):
            c.log_bypass(root, HOOK, rel, "task file unreadable")
            sys.exit(0)

        # FR-MST-05 step (a). THE EMPTY CHECK MUST STAY FIRST of the task
        # checks. The brief check below is an ALL over the gating entries, and
        # an ALL is vacuously TRUE on an empty list - so evaluating it before
        # this guard would silently flip the gate from BLOCK to ALLOW exactly
        # when NO task is active, which is the case it exists to catch. Do not
        # reorder. An ABSENT file still lands here and blocks; only the
        # unreadable probe above lets an empty answer through.
        if not tasks:
            c.block(root, HOOK, rel, "no active brief", NO_BRIEF_MSG)

        # (b) quick and hotfix are per-entry EXEMPTION types, never an ANY
        # waiver: each removes its OWN entry from the check and nothing else.
        # Only when EVERY entry in flight is quick or hotfix does the whole
        # gate step aside. One briefless quick entry beside a feature entry
        # must still leave the feature entry blocking - otherwise a single
        # briefless quick entry bricks source edits for every concurrent
        # session against this working tree.
        gating = [e for e in tasks if e.get("type") not in ("quick", "hotfix")]
        if not gating:
            c.log_bypass(
                root, HOOK, rel,
                c.qualify_reason(exempt_reason(tasks), tasks, tasks),
            )
            sys.exit(0)

        # (c) ALL over the gating entries: one unusable brief blocks.
        offenders = []  # (entry, brief-or-None)
        for entry in gating:
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
