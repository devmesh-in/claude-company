#!/usr/bin/env python3
"""PreToolUse (Bash): gate git commit / merge / push commands.

  - push to protected branch (main/master), explicit or bare push while on it:
    BLOCK (owner-only).
  - commit on a protected branch (main/master) while a task is active:
    BLOCK with a task-branch recipe (all work happens on task branches).
    Hotfix tasks are exempt (ALLOW + log BYPASS); a commit with no active
    task is a founding commit and is exempt; merge on main is the owner's
    local integration and is exempt.
  - commit / merge: require a green, fresh, valid gates.status stamp. If
    gates.config is missing, has zero gates, or contains ONLY CONFIGURE-ME
    placeholders (a fresh project with nothing to gate yet), ALLOW + log
    BYPASS - unconfigured gates must not deadlock founding commits, and the
    bypass stays visible in the adherence log. Placeholders still fail loudly
    in run-gates.sh and still block task completion via stop_gate; only the
    commit path treats them as not-yet-configured. If the active task is a
    hotfix, ALLOW + log BYPASS.
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

# DISPLAY truncation for the branch recipe only (FR-MST-30). It never reaches
# a block/allow decision - the gate arms on presence, not on a count.
RECIPE_CAP = 3

# FR-HP-17: the tail is shared by the one-entry and the many-entry recipe, so
# the compound-command warning renders in both.
BRANCH_TAIL = (
    "then retry your commit on that branch.\n"
    "NOTE: run the switch as its OWN command first - this gate judges every "
    "segment of a compound command against the CURRENT branch, so `git "
    "switch -c task/x && git commit` blocks even though the switch comes "
    "first.\n"
    "If this task is finished and you are integrating, use git merge "
    "(allowed on main) - see company/GIT.md."
)


def segments(command):
    parts = re.split(r"&&|\|\||;|\|", command)
    return [p.strip() for p in parts if p.strip()]


# FR-HP-10: global options that carry a SEPARATED argument. Skipping one
# token each leaves the argument to be read as the subcommand, so
# `git -C sub commit` parses as subcommand "sub" and the whole segment goes
# unseen by every Bash-gated check. Attached forms (-Cdir, --git-dir=x) carry
# their argument in the same token and consume one token only.
ARG_OPTS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
            "--exec-path")


def git_subcmd(segment):
    """Return (subcommand, args) for a `git ...` segment, else (None, []).

    Only tokens BEFORE the subcommand are scanned: `git commit -C HEAD~1` is
    --reuse-message, where HEAD~1 is a commit ref and not a path.
    """
    try:
        toks = shlex.split(segment)
    except Exception:
        toks = segment.split()
    if not toks or toks[0] != "git":
        return None, []
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in ARG_OPTS else 1
    if i >= len(toks):
        return None, []
    return toks[i], toks[i + 1:]


def git_cwd(payload, root):
    """Resolve the directory the git command actually runs in (#26).

    The branch checks must reflect the working tree git operates on, not the
    project root. A commit issued from a worktree checkout of a task branch
    must be judged by that worktree's branch, even when CLAUDE_PROJECT_DIR (and
    thus root) points at the main checkout on a protected branch. Prefer the
    payload's cwd when it is present and inside a git work tree; otherwise fall
    back to root.
    """
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        if cwd:
            out = c._git(cwd, ["rev-parse", "--is-inside-work-tree"])
            if out is not None and out.strip() == "true":
                return cwd
    return root


def seg_git_dir(seg, payload, root):
    """The directory whose branch a single git SEGMENT must be judged by.

    FR-HP-11: now that FR-HP-10 makes `git -C <path> commit` visible to this
    gate, it must also be judged by the tree that -C names. A session sitting
    in the main checkout that runs `git -C .claude/worktrees/<slug> commit`
    lands the commit on the worktree's task branch, so judging it by the main
    checkout's branch (main) would be a false block.

    Only tokens BEFORE the subcommand are scanned, for the same reason as
    git_subcmd: `git commit -C HEAD~1` is --reuse-message, not a path. The
    LAST -C wins, which is git's own semantics. A relative path resolves
    against the payload cwd when present, else root.
    """
    try:
        toks = shlex.split(seg)
    except Exception:
        toks = seg.split()
    path = None
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] == "-C" and i + 1 < len(toks):
            path = toks[i + 1]
        elif toks[i].startswith("-C") and len(toks[i]) > 2:
            path = toks[i][2:]
        i += 2 if toks[i] in ARG_OPTS else 1
    if path:
        base = payload.get("cwd") if isinstance(payload, dict) else None
        base = base or root
        cand = path if os.path.isabs(path) else os.path.join(base, path)
        # OQ-HP-12 assumption: accept the candidate only when git itself
        # answers `true` there. Any other answer (missing directory, not a
        # repo, git error) falls through to git_cwd, which falls back to
        # root. Fail open, never fail hard.
        out = c._git(cand, ["rev-parse", "--is-inside-work-tree"])
        if out is not None and out.strip() == "true":
            return cand
    return git_cwd(payload, root)


def push_targets_protected(branch_dir, args):
    non_opt = [a for a in args if not a.startswith("-")]
    # first non-option is the remote; the rest are refspecs
    refspecs = non_opt[1:]
    for ref in refspecs:
        dst = ref.split(":")[-1]
        if dst in PROTECTED:
            return True
    if not refspecs:
        cur = c.current_branch(branch_dir)
        if cur in PROTECTED:
            return True
    return False


def branch_recipe(entries):
    """FR-MST-30: the protected-branch message, naming who caused the block.

    A message that does not say WHICH task caused the block is not a recipe.
    At exactly one entry this renders TODAY'S EXACT TEXT (BR-MST-02); beyond
    one it renders a `git switch -c task/<slug>` line per non-exempt entry.
    """
    head = "BLOCKED: work belongs on a task branch, never directly on main.\n"
    if len(entries) == 1:
        slug = entries[0].get("task") or "<task-slug>"
        return (
            head
            + "Create the isolated task branch and commit there:\n"
            "  git worktree add .claude/worktrees/{slug} -b task/{slug}\n"
            "or, if you are already in the right working tree:\n"
            "  git switch -c task/{slug}\n".format(slug=slug)
            + BRANCH_TAIL
        )
    names = [e.get("task") or "<task-slug>" for e in entries]
    lines = [
        head,
        "{} task entries are in flight. Switch to the branch for the entry "
        "you are committing:\n".format(len(names)),
    ]
    for slug in names[:RECIPE_CAP]:
        lines.append("  git switch -c task/{}\n".format(slug))
    hidden = len(names) - len(names[:RECIPE_CAP])
    if hidden > 0:
        lines.append(
            "  plus {} more in company/state/active-task.json\n".format(hidden)
        )
    lines.append(
        "or create an isolated worktree for it:\n"
        "  git worktree add .claude/worktrees/<slug> -b task/<slug>\n"
    )
    lines.append(BRANCH_TAIL)
    return "".join(lines)


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
            # #26 + FR-HP-11: branch checks must reflect the tree THIS segment
            # runs in, resolved per segment so a -C in one segment cannot
            # mis-judge the others.
            branch_dir = seg_git_dir(seg, payload, root)

            if sub == "push":
                if push_targets_protected(branch_dir, args):
                    c.block(
                        root, HOOK, "git push", "protected branch push",
                        "BLOCKED: push to a protected branch (main/master) is "
                        "owner-only. Open a PR or ask the owner to push.",
                    )
                continue

            if sub in ("commit", "merge"):
                tasks = c.active_tasks(root)

                # All work happens on task branches. A plain commit on a
                # protected branch while a task is active is misplaced work.
                # (merge is the owner's local integration and is exempt; a
                # commit with NO active task is a founding commit and is
                # exempt.) Branch message wins over the gate-stamp checks
                # below. Fail open when the branch is unknown.
                # FR-MST-08: the gate arms on PRESENCE of any entry, and is
                # bypassed by ANY hotfix entry (RISK-MST-01, accepted: a
                # production emergency in flight waives the branch rule for
                # the whole tree, and the bypass names the hotfix in the log).
                if sub == "commit" and tasks:
                    branch = c.current_branch(branch_dir)
                    if branch in PROTECTED:
                        hf = c.hotfix_entry(tasks)
                        if hf is not None:
                            c.log_bypass(
                                root, HOOK, "git commit",
                                c.qualify_reason(
                                    "hotfix commit on protected branch",
                                    tasks, hf,
                                ),
                            )
                            continue
                        # No hotfix here, so every entry is non-exempt.
                        c.block(
                            root, HOOK, "git commit",
                            c.qualify_reason(
                                "commit on protected branch", tasks, tasks
                            ),
                            branch_recipe(tasks),
                        )

                hf = c.hotfix_entry(tasks)
                if hf is not None:
                    c.log_bypass(
                        root, HOOK, "git " + sub,
                        c.qualify_reason("hotfix mode", tasks, hf),
                    )
                    continue
                cfg = c.gates_config(root)
                gates = cfg.get("gates") if isinstance(cfg, dict) else None
                if not gates:
                    c.log_bypass(
                        root, HOOK, "git " + sub, "no gates configured"
                    )
                    continue
                if all(
                    "CONFIGURE ME" in (g.get("command") or "")
                    for g in gates if isinstance(g, dict)
                ):
                    c.log_bypass(
                        root, HOOK, "git " + sub,
                        "gates.config has only CONFIGURE-ME placeholders",
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
