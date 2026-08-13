#!/usr/bin/env python3
"""PreToolUse (Bash): gate git commit / merge / push commands.

  - push to protected branch (main/master), explicit or bare push while on it:
    BLOCK (owner-only).
  - commit on a protected branch (main/master) while a task is active:
    BLOCK with a task-branch recipe (all work happens on task branches).
    Hotfix tasks are exempt (ALLOW + log BYPASS); a commit with no active
    task is a founding commit and is exempt; merge on main is the owner's
    local integration and is exempt.
  - commit / merge: require a green, fresh, valid gates.status stamp - the
    ACTING TREE's own, the tree the segment commits into, which is not the
    main checkout when the segment carries a -C or runs from a worktree. If
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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_commit"
PROTECTED = {"main", "master"}

# Re-exports, not leftovers. The parsers themselves live in _common - there is
# exactly one implementation of them - but three callers reach them through
# THIS module's names and must keep working:
#   - guard_secrets.py calls guard_commit.git_subcmd(seg), and
#     tests/hooks/test_guard_parsers.py asserts that exact string appears in
#     the guard_secrets source (FR-HP-12, one parser and one behavior),
#   - guard_provenance.py calls guard_commit.segments and
#     guard_commit.git_subcmd, and that file is owned by an open PR,
#   - test_guard_parsers.py monkeypatches guard_commit.git_subcmd and asserts
#     guard_secrets follows the patch, which works because the name is looked
#     up on this module at call time.
# Deleting an alias breaks a caller outside this file. Leave them.
ARG_OPTS = c.ARG_OPTS
segments = c.segments
git_subcmd = c.git_subcmd
git_cwd = c.git_cwd
seg_git_dir = c.seg_git_dir

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


# FR-HP-29: appended ONLY when a -C was written and could not be confirmed as
# a work tree. The recipe above then names the FALLBACK tree's branch, and a
# reader who is already on that branch reads a recipe that tells them to
# create the branch they are standing on. Saying so is the difference between
# a message and a recipe. Appended, never woven in: at one entry the recipe is
# byte-pinned by BR-MST-02.
UNRESOLVED_C_NOTE = (
    "\nNOTE: the -C target `{target}` could not be resolved to a git work "
    "tree, so this gate judged the tree the command ran in instead - the "
    "branch named above is THAT tree's branch, not the branch of the tree "
    "you aimed at.\n"
    "A hook sees the RAW command text and never a shell that expanded it, so "
    "a variable is delivered literally and no filesystem call can resolve it. "
    "Fix: pass a LITERAL absolute path to -C.\n"
)


def unresolved_note(target):
    """The note text for an unresolvable -C target, or "" for none."""
    if not target:
        return ""
    return UNRESOLVED_C_NOTE.format(target=target)


def same_tree(a, b):
    """True when two paths name the same directory. False on any doubt."""
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except Exception:
        return False


def stamp_message(sub, reason, branch_dir, root):
    """The gate-stamp block message, naming the tree whose stamp was judged.

    `Fix: run bash company/run-gates.sh` is a correct recipe only from the
    tree that was judged. Run from anywhere else it gates and stamps a
    DIFFERENT tree, so the retry blocks on exactly the same reason and the
    reader has no way to tell why. When the acting tree is not the project
    root, the path is spelled out absolutely and the judged tree is named.
    """
    head = "BLOCKED: git {} requires green, fresh gates. {}.\n".format(
        sub, reason
    )
    placeholder = (
        "If company/gates.config still has only CONFIGURE-ME placeholders, "
        "run `python3 .claude/hooks/gates_detect.py --write` first to "
        "auto-configure real gates, then rerun the suite."
    )
    if same_tree(branch_dir, root):
        return (
            head
            + "Fix: run `bash company/run-gates.sh` until green, then retry.\n"
            + placeholder
        )
    return (
        head
        + "Judged: the acting tree {}. This gate reads THAT tree's own "
        "company/state/gates.status - a green stamp in another checkout does "
        "not stand in for it.\n"
        "Fix: run `bash {}/company/run-gates.sh` until green, then retry. Use "
        "the absolute path: from any other directory the runner gates a "
        "different tree.\n".format(branch_dir, branch_dir)
        + placeholder
    )


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
            # #26 + FR-HP-11: every check must reflect the tree THIS segment
            # runs in, resolved per segment so a -C in one segment cannot
            # mis-judge the others. `unresolved_c` carries the -C argument as
            # written when one was present and could not be confirmed as a
            # work tree, so a block message can say which tree it is really
            # talking about.
            branch_dir, unresolved_c = c.acting_tree(seg, payload, root)

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
                            branch_recipe(tasks) + unresolved_note(
                                unresolved_c),
                        )

                hf = c.hotfix_entry(tasks)
                if hf is not None:
                    c.log_bypass(
                        root, HOOK, "git " + sub,
                        c.qualify_reason("hotfix mode", tasks, hf),
                    )
                    continue
                # The acting-tree rule, applied to the gate stamp: a hook
                # judges the tree that contains the thing being acted on.
                # These two resolutions MUST move together - see below.
                #
                # FR-HP-28 made company/run-gates.sh resolve its root from the
                # runner's own location, so a ladder run inside a worktree
                # gates and stamps THAT worktree. The stamp that describes the
                # acting tree is therefore the acting tree's own. Reading the
                # main checkout's stamp instead let a lane be green-lit by a
                # sibling lane's run, and blocked by a sibling lane's drift,
                # with no self-service fix in either direction. It is the
                # single largest source of friction in the adherence log (23
                # stale-stamp blocks) and three lanes filed it independently
                # as CR-HP-2.
                #
                # Moving check_stamp while leaving gates_config on `root`
                # would DEADLOCK every worktree in THIS repo. Per the
                # dual-nature rule in CLAUDE.md the tracked
                # company/gates.config holds only CONFIGURE-ME placeholders on
                # purpose, and this repo's real gate commands exist only as an
                # untracked modification in the main checkout. A worktree
                # therefore inherits placeholders and can never produce a
                # green stamp, so a split resolution - real gates read from
                # the main checkout, stamp demanded from the worktree - would
                # block every worktree commit permanently with no way out.
                # Resolving both from the acting tree degrades that case to
                # the existing, LOGGED placeholder bypass below, which is the
                # same treatment a fresh install gets before onboarding.
                #
                # In a normal install, where gates.config is committed with
                # real gates, the worktree inherits those real gates and the
                # lane that runs its own ladder in its own worktree satisfies
                # its own stamp. That is the behavior asked for.
                cfg = c.gates_config(branch_dir)
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
                ok, reason = c.check_stamp(branch_dir)
                if not ok:
                    c.block(
                        root, HOOK, "git " + sub, reason,
                        stamp_message(sub, reason, branch_dir, root),
                    )
                continue
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
