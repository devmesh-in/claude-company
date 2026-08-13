#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit|Bash): anti-reward-hacking on tests.

Tests are the oracle. Editing or deleting them is out of scope unless the
active brief explicitly opened test scope (active-task.json "test_scope": true).

  - Edit/Write/MultiEdit on a test file: allow only when test_scope is true.
  - Bash `rm` / `git rm` of a test path: block unless test_scope is true.

The grant is read from the tree being ACTED ON, not from CLAUDE_PROJECT_DIR:
the harness pins that variable to the main checkout while every delegated
agent works in a linked worktree, so a worktree that keeps its own
active-task.json governs itself and one that does not falls back to the main
checkout (c.task_state_root).

The DECISION comes from the acting tree; the LOG LINE always goes to the
project root. A worktree is gitignored and gets pruned at task close, so a
block recorded only inside one is evidence that deletes itself. One project,
one adherence.log.

Fails open on any internal error.
"""

import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_tests"

TEST_DIR_SEGMENTS = {"tests", "test", "__tests__", "e2e"}

# The token OUT_OF_SCOPE carries where the state file belongs. out_of_scope()
# swaps it for the ABSOLUTE path of the file the hook actually read.
STATE_FILE = "company/state/active-task.json"

OUT_OF_SCOPE = (
    "BLOCKED: editing tests is out of scope for this brief. Tests are the "
    "oracle; changing them to pass is reward-hacking.\n"
    "Fix, only if the brief calls for test work: set \"test_scope\": true on "
    "YOUR entry in " + STATE_FILE + " with a targeted Edit of "
    "that entry - other sessions own the other entries, so never rewrite the "
    "whole file."
)


def out_of_scope(state_path):
    """OUT_OF_SCOPE naming the state file this decision was read from.

    The reader is almost always sitting in a linked worktree, where the
    relative path names a file that does not exist. Following that recipe
    creates a SECOND task file that no hook reads, so the reader "fixes" the
    grant and stays blocked. The absolute path is the same file the hook read
    and the same file the BLOCK line was logged next to.
    """
    return OUT_OF_SCOPE.replace(STATE_FILE, state_path)


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


GRANT_REASON = "test scope open"


def grant_already_logged(root, reason):
    """True when this exact grant already has a GRANT line on record.

    Fails toward LOGGING: an unreadable log yields False, because a duplicate
    line is a much cheaper mistake than a missing audit record.
    """
    try:
        marker = "| {} | GRANT |".format(HOOK)
        with open(c.adherence_log_path(root)) as f:
            for line in f:
                if marker in line and reason in line:
                    return True
    except Exception:
        return False
    return False


def test_scope_open(root, state_root, target):
    """True iff ANY entry has "test_scope": true (FR-MST-06 / RISK-MST-02).

    `state_root` is the checkout whose active-task.json governs the tree being
    acted on, not CLAUDE_PROJECT_DIR - see c.task_state_root. `root` is where
    the line is LOGGED, which is always the project, never the acting tree: a
    worktree is gitignored and pruned at task close, so a record written only
    inside one deletes itself.

    This is the ONE accepted BLOCK-to-ALLOW weakening of the multi-entry work:
    a second entry can open test scope for the whole tree, because glob-scoped
    grants were scoped out. It is therefore logged BY NAME the moment more than
    one entry is in flight - at N == 1 nothing is logged, which is what keeps
    the single-entry path byte-identical (BR-MST-02).

    Logged ONCE PER GRANTING ENTRY, not once per write. What RISK-MST-02 needs
    on record is that a grant was EXERCISED and by whom - a durable fact, since
    active-task.json is untracked and an entry can open scope, take its edits
    and close it again leaving no trace. That fact is worth one line. Repeating
    it on every allowed write buried the log: 107 of 431 lines in one five-week
    sample were this one line, which is how a signal stops being read.
    """
    tasks = c.active_tasks(state_root)
    granting = None
    for entry in tasks:
        if entry.get("test_scope") is True:
            granting = entry
            break
    if granting is None:
        return False
    if len(tasks) > 1:
        reason = "{} ({})".format(GRANT_REASON, c.slug_list([granting]))
        if not grant_already_logged(root, reason):
            c.adherence_log(root, HOOK, "GRANT", target, reason)
    return True


# One splitter, one behavior. The alias keeps the module-level name for any
# caller that reads it while the implementation stays in _common.
segments = c.segments


def rm_targets(segment):
    """Paths a segment tries to remove via rm or git rm, else [].

    The git form goes through the SHARED subcommand parser. The hand-rolled
    `toks[1] == "rm"` test this replaces is the defect FR-HP-10 closed in
    guard_commit: a git global option carrying a separated argument shifts the
    subcommand, so `git -C <worktree> rm tests/foo.py` parsed as subcommand
    `-C` and the segment was invisible to this gate - anyone could delete a
    test file by prefixing -C.

    Plain `rm` is not a git command, so the git parser does not apply to it;
    it is tokenized with the shared tokenizer and read directly.
    """
    sub, args = c.git_subcmd(segment)
    if sub == "rm":
        rest = args
    else:
        toks = c.tokens(segment)
        if not toks or toks[0] != "rm":
            return []
        rest = toks[1:]
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
                # Per SEGMENT: a -C in one segment decides that segment only,
                # so two removals in one compound command can be judged by two
                # different trees.
                state_root = None
                for target in rm_targets(seg):
                    if not is_test_path(target):
                        continue
                    # Scope is resolved only once a test path is actually at
                    # stake, so the GRANT line can name what it allowed and a
                    # command that removes no test file logs nothing.
                    if state_root is None:
                        state_root = c.task_state_root(
                            root, c.seg_git_dir(seg, payload, root)
                        )
                    if test_scope_open(root, state_root, target):
                        continue
                    c.block(
                        root, HOOK, target, "rm of test file",
                        "BLOCKED: removing test file '{}'. {}".format(
                            target,
                            out_of_scope(c.active_tasks_path(state_root)),
                        ),
                    )
            sys.exit(0)

        file_path = tool_input.get("file_path") or ""
        if not file_path:
            sys.exit(0)
        rel = c.rel_path(root, file_path)
        if not is_test_path(rel):
            sys.exit(0)
        # path_checkout, not owning_checkout: a worktree created OUTSIDE the
        # project root is still a checkout of this repository and still
        # governed by its own task state. `outside` (no checkout of this
        # project owns the path) falls back to the project's state.
        tree, outside = c.path_checkout(root, file_path)
        state_root = c.task_state_root(root, root if outside else tree)
        if test_scope_open(root, state_root, rel):
            sys.exit(0)
        c.block(
            root, HOOK, rel, "test edit out of scope",
            out_of_scope(c.active_tasks_path(state_root)),
        )
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
