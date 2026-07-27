#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit|Bash): anti-reward-hacking on tests.

Tests are the oracle. Editing or deleting them is out of scope unless the
active brief explicitly opened test scope (active-task.json "test_scope": true).

  - Edit/Write/MultiEdit on a test file: allow only when test_scope is true.
  - Bash `rm` / `git rm` of a test path: block unless test_scope is true.

Fails open on any internal error.
"""

import fnmatch
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_tests"

TEST_DIR_SEGMENTS = {"tests", "test", "__tests__", "e2e"}
OUT_OF_SCOPE = (
    "BLOCKED: editing tests is out of scope for this brief. Tests are the "
    "oracle; changing them to pass is reward-hacking.\n"
    "Fix, only if the brief calls for test work: set \"test_scope\": true on "
    "YOUR entry in company/state/active-task.json with a targeted Edit of "
    "that entry - other sessions own the other entries, so never rewrite the "
    "whole file."
)


def is_test_path(path):
    norm = (path or "").replace("\\", "/")
    segs = [s for s in norm.split("/") if s]
    if not segs:
        return False
    base = segs[-1]
    if any(s in TEST_DIR_SEGMENTS for s in segs[:-1]):
        return True
    if re.match(r"test_.*\.py$", base):
        return True
    if fnmatch.fnmatch(base, "*_test.*"):
        return True
    if fnmatch.fnmatch(base, "*.test.*"):
        return True
    if fnmatch.fnmatch(base, "*.spec.*"):
        return True
    return False


def test_scope_open(root, target):
    """True iff ANY entry has "test_scope": true (FR-MST-06 / RISK-MST-02).

    This is the ONE accepted BLOCK-to-ALLOW weakening of the multi-entry work:
    a second entry can open test scope for the whole tree, because glob-scoped
    grants were scoped out. It is therefore logged BY NAME the moment more than
    one entry is in flight - at N == 1 nothing is logged, which is what keeps
    the single-entry path byte-identical (BR-MST-02).
    """
    tasks = c.active_tasks(root)
    granting = None
    for entry in tasks:
        if entry.get("test_scope") is True:
            granting = entry
            break
    if granting is None:
        return False
    if len(tasks) > 1:
        c.adherence_log(
            root, HOOK, "GRANT", target,
            "test scope open (" + c.slug_list([granting]) + ")",
        )
    return True


def segments(command):
    parts = re.split(r"&&|\|\||;|\|", command)
    return [p.strip() for p in parts if p.strip()]


def rm_targets(segment):
    """Paths a segment tries to remove via rm or git rm, else []."""
    try:
        toks = shlex.split(segment)
    except Exception:
        toks = segment.split()
    if not toks:
        return []
    if toks[0] == "rm":
        rest = toks[1:]
    elif len(toks) >= 2 and toks[0] == "git" and toks[1] == "rm":
        rest = toks[2:]
    else:
        return []
    return [t for t in rest if not t.startswith("-")]


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    tool = payload.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit", "Bash"):
        sys.exit(0)

    root = c.project_root(payload)
    tool_input = payload.get("tool_input") or {}

    try:
        if tool == "Bash":
            command = tool_input.get("command") or ""
            for seg in segments(command):
                for target in rm_targets(seg):
                    if is_test_path(target):
                        # Scope is resolved only once a test path is actually
                        # at stake, so the GRANT line can name what it allowed.
                        if test_scope_open(root, target):
                            sys.exit(0)
                        c.block(
                            root, HOOK, target, "rm of test file",
                            "BLOCKED: removing test file '{}'. {}".format(
                                target, OUT_OF_SCOPE
                            ),
                        )
            sys.exit(0)

        file_path = tool_input.get("file_path") or ""
        if not file_path:
            sys.exit(0)
        rel = c.rel_path(root, file_path)
        if not is_test_path(rel):
            sys.exit(0)
        if test_scope_open(root, rel):
            sys.exit(0)
        c.block(root, HOOK, rel, "test edit out of scope", OUT_OF_SCOPE)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
