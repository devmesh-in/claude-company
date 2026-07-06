#!/usr/bin/env python3
"""PreToolUse (Bash): gate git commit / merge / push commands.

  - push to protected branch (main/master), explicit or bare push while on it:
    BLOCK (owner-only).
  - commit / merge: require a green, fresh, valid gates.status stamp. If
    gates.config is missing or has zero gates, ALLOW + log BYPASS. If the
    active task is a hotfix, ALLOW + log BYPASS.
  - everything else: allow.

Fails open on any internal error.
"""

import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_commit"
PROTECTED = {"main", "master"}


def segments(command):
    parts = re.split(r"&&|\|\||;|\|", command)
    return [p.strip() for p in parts if p.strip()]


def git_subcmd(segment):
    """Return (subcommand, args) for a `git ...` segment, else (None, [])."""
    try:
        toks = shlex.split(segment)
    except Exception:
        toks = segment.split()
    if not toks or toks[0] != "git":
        return None, []
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 1
    if i >= len(toks):
        return None, []
    return toks[i], toks[i + 1:]


def push_targets_protected(root, args):
    non_opt = [a for a in args if not a.startswith("-")]
    # first non-option is the remote; the rest are refspecs
    refspecs = non_opt[1:]
    for ref in refspecs:
        dst = ref.split(":")[-1]
        if dst in PROTECTED:
            return True
    if not refspecs:
        cur = c.current_branch(root)
        if cur in PROTECTED:
            return True
    return False


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    root = c.project_root(payload)
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        sys.exit(0)

    try:
        for seg in segments(command):
            sub, args = git_subcmd(seg)
            if sub is None:
                continue

            if sub == "push":
                if push_targets_protected(root, args):
                    c.block(
                        root, HOOK, "git push", "protected branch push",
                        "BLOCKED: push to a protected branch (main/master) is "
                        "owner-only. Open a PR or ask the owner to push.",
                    )
                continue

            if sub in ("commit", "merge"):
                task = c.active_task(root)
                if isinstance(task, dict) and task.get("type") == "hotfix":
                    c.log_bypass(root, HOOK, "git " + sub, "hotfix mode")
                    continue
                cfg = c.gates_config(root)
                if not isinstance(cfg, dict) or not cfg.get("gates"):
                    c.log_bypass(
                        root, HOOK, "git " + sub, "no gates configured"
                    )
                    continue
                ok, reason = c.check_stamp(root)
                if not ok:
                    c.block(
                        root, HOOK, "git " + sub, reason,
                        "BLOCKED: git {} requires green, fresh gates. {}.\n"
                        "Fix: run `bash company/run-gates.sh` until green, "
                        "then retry.\n"
                        "If company/gates.config still has only CONFIGURE-ME "
                        "placeholders, run `python3 "
                        ".claude/hooks/gates_detect.py --write` first to "
                        "auto-configure real gates, then rerun the "
                        "suite.".format(sub, reason),
                    )
                continue
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
