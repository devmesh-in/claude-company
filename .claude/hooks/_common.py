#!/usr/bin/env python3
"""Shared helpers for the claude-company enforcement hooks.

Python 3 stdlib only. Everything here fails open: on any internal error the
callers should treat the result as "allow" rather than bricking the session.
The one deliberate exception is git-tracked uncertainty in the immutability
checks, which fail safe (treat as tracked) per the frozen-surface contract.

The concurrency primitives (state_lock, write_json_atomic, the active-task
retry) hold that same line: a lock that cannot be taken proceeds UNLOCKED, an
atomic write that cannot be made returns False, and a hash that cannot be
computed falls back to the legacy digest. None of them ever raise, and none of
them can turn into a block.
"""

import contextlib
import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

# Documented anti-accident salt (not anti-adversary). Bump the suffix only on a
# real stamp-format change.
CHECKSUM_SALT = "claude-company.gates.v1"


def read_stdin_json():
    """Parse the hook JSON payload from stdin. None on any failure."""
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def project_root(payload):
    """Resolve the project root: CLAUDE_PROJECT_DIR, else stdin cwd, else cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        return root
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        if cwd:
            return cwd
    return os.getcwd()


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def adherence_log_path(root):
    """The project's single audit trail.

    Always the PROJECT's, never an acting tree's: a linked worktree is
    gitignored and pruned at task close, so a block recorded only inside one
    is evidence that deletes itself. Hooks decide from the acting tree and log
    here.
    """
    return os.path.join(root, "company", "state", "adherence.log")


def adherence_log(root, hook_name, action, target, reason):
    """Append one line to company/state/adherence.log. Never raises."""
    try:
        state_dir = os.path.join(root, "company", "state")
        os.makedirs(state_dir, exist_ok=True)
        target = (target or "").replace("\n", " ")
        reason = (reason or "").replace("\n", " ")
        line = "{} | {} | {} | {} | {}\n".format(
            iso_now(), hook_name, action, target, reason
        )
        with open(adherence_log_path(root), "a") as f:
            f.write(line)
    except Exception:
        pass


def block(root, hook_name, target, short_reason, message):
    """Log a BLOCK line, print the human message to stderr, exit 2."""
    adherence_log(root, hook_name, "BLOCK", target, short_reason)
    print(message, file=sys.stderr)
    sys.exit(2)


def log_bypass(root, hook_name, target, short_reason):
    adherence_log(root, hook_name, "BYPASS", target, short_reason)


def read_json_file(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


@contextlib.contextmanager
def state_lock(root, timeout=2.0):  # OQ-HP-11 assumption
    """Exclusive flock over company/state/.state.lock, as a context manager.

    Multi-session task entries shipped in v0.2.6, so several Claude Code
    sessions against one working tree is normal, and an unlocked
    read-modify-write cycle on a shared state file silently loses updates.
    Wrap the whole read-modify-write in this manager, never just the write.

    Fail-open in every direction: no fcntl, no state dir, an exception, or a
    timeout all yield WITHOUT the lock rather than raising. Enforcement must
    never brick a session, so a contended state file degrades to exactly
    today's unlocked behavior. The wait is `timeout` seconds on a 0.05s poll
    and then it proceeds unlocked, with no log line at this level (the kernel
    reaches no decision; a caller that cares can say so itself).

    The lock file is untracked repo-local state (OQ-HP-07 fallback: repo-local
    only, no XDG or temp-dir variant). It costs nothing to leave untracked -
    company/state is hash-excluded, so it stales no stamp and no audit.
    """
    fd = None
    try:
        import fcntl
        state_dir = os.path.join(root, "company", "state")
        os.makedirs(state_dir, exist_ok=True)
        fd = os.open(
            os.path.join(state_dir, ".state.lock"), os.O_RDWR | os.O_CREAT
        )
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    break  # proceed UNLOCKED - fail open
                time.sleep(0.05)
    except Exception:
        pass
    try:
        yield
    finally:
        # Closing the descriptor releases any flock held on it, so this
        # finally is the only release path there is - a body that raises
        # cannot leak the descriptor or strand the lock.
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def write_json_atomic(path, data, indent=None):
    """Write `data` to `path` as JSON in one atomic replace. Never raises.

    A whole-file write is not atomic: a reader in another session can catch
    the truncated middle of it. Serializing into a temp file in the SAME
    directory and then os.replace makes the swap a single rename, so a reader
    sees either the old file or the new one and never a torn one.

    Returns True on success and False on ANY failure. Everything that can
    fail - serialization included - happens against the temp file, so a
    failure leaves the destination byte-unchanged and removes the temp file.

    `indent` keeps each caller's on-disk format: pass indent=2 where the file
    is pretty-printed today, and leave the default None for compact.

    The destination's permission bits survive the replace. mkstemp creates
    0600, and os.replace carries the temp file's mode with it, so without this
    every state file would silently tighten the first time its writer adopted
    this helper. A new file gets 0644, which is what open(path, "w") produces
    under a normal umask today.
    """
    tmp = None
    try:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
            f.flush()
        try:
            mode = os.stat(path).st_mode & 0o777
        except Exception:
            mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        tmp = None
        return True
    except Exception:
        return False
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except Exception:
                pass


def active_tasks_path(root):
    return os.path.join(root, "company", "state", "active-task.json")


def active_tasks_unreadable(root):
    """True IFF active-task.json EXISTS and does not parse - almost always a
    concurrent session mid-write, since a whole-file write is not atomic.

    False both when the file is absent and when it parses, which is what lets
    a caller tell "no tasks in flight" from "cannot tell right now" and fail
    open on the second.
    """
    path = active_tasks_path(root)
    return os.path.exists(path) and read_json_file(path) is None


def active_tasks(root):
    """Every task entry in flight in this working tree. Never raises; [] on
    anything unusable (today's fail-open).

    An existing-but-unparseable file is a torn read and is transient, so it is
    retried briefly before giving up. Returning [] for a torn read is not a
    harmless default: it reads as "no task in flight", which drops dispatch
    credits and arms blocks that should never have fired.
    """
    path = active_tasks_path(root)
    raw = read_json_file(path)
    if raw is None and os.path.exists(path):
        # OQ-HP-10 assumption: 3 retries, 0.06s apart. A write takes
        # milliseconds, so this outlasts a torn read while keeping the whole
        # call well under a fifth of a second even when the file is garbage.
        for _ in range(3):
            time.sleep(0.06)
            raw = read_json_file(path)
            if raw is not None:
                break
    try:
        if isinstance(raw, list):
            return [e for e in raw if isinstance(e, dict)]
        if not isinstance(raw, dict):
            return []
        tasks = raw.get("tasks")
        if isinstance(tasks, list):
            return [e for e in tasks if isinstance(e, dict)]
        return [raw]
    except Exception:
        return []


def has_active_task(tasks):
    """True iff at least one entry is in flight."""
    return bool(tasks)


def hotfix_entry(tasks):
    """The FIRST entry with type == "hotfix", else None."""
    for entry in tasks or []:
        if isinstance(entry, dict) and entry.get("type") == "hotfix":
            return entry
    return None


def entries_of_type(tasks, types):
    """Entries whose type is in `types` (a string or an iterable of strings)."""
    wanted = (types,) if isinstance(types, str) else tuple(types or ())
    return [
        entry for entry in tasks or []
        if isinstance(entry, dict) and entry.get("type") in wanted
    ]


def slugs(tasks):
    """Truthy `task` values, order preserved."""
    out = []
    for entry in tasks or []:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("task")
        if slug:
            out.append(slug)
    return out


def slug_list(tasks, cap=3):
    """Display string over ENTRIES (not slugs). A slugless entry renders as
    the literal <task-slug>. Joined with ", "; overflow beyond `cap` appends
    " and <n> more". Empty list -> "".

    `cap` is display truncation only and must never reach a block/allow
    decision.
    """
    names = []
    for entry in tasks or []:
        slug = entry.get("task") if isinstance(entry, dict) else None
        names.append(slug if slug else "<task-slug>")
    if not names:
        return ""
    shown = names[:cap]
    text = ", ".join(shown)
    hidden = len(names) - len(shown)
    if hidden > 0:
        text += " and {} more".format(hidden)
    return text


def qualify_reason(reason, tasks, responsible):
    """`reason` unchanged when len(tasks) <= 1; otherwise
    "<reason> (<slugs>)" where <slugs> is slug_list of `responsible`.
    `responsible` may be a single entry dict or a list of entries.
    This is what keeps adherence.log lines byte-identical at N == 1 while
    still naming the responsible entry at N > 1.
    """
    if len(tasks or []) <= 1:
        return reason
    if isinstance(responsible, dict):
        responsible = [responsible]
    named = slug_list(responsible)
    if not named:
        return reason
    return "{} ({})".format(reason, named)


def gates_config(root):
    return read_json_file(os.path.join(root, "company", "gates.config"))


def _enclosing_checkout(candidate, root_norm):
    """The nearest git working-tree root strictly below root_norm that
    contains `candidate`, or None when there is none.

    This is what makes rel_path see a worktree the way it sees the main
    checkout. A linked worktree lives INSIDE the project root, so a file in
    one IS project-relative-able, and rel_path used to hand back the PREFIXED
    string `.claude/worktrees/<slug>/company/state/gates.status`. That string
    matches no frozen pattern, no test-path rule and no source-path rule, so
    every check keyed on rel_path missed silently - the frozen registry, the
    always-list, accepted-ADR immutability, test scope and source scope, all
    unenforced in the one place where every delegated build actually happens.

    A working-tree root is derived, never assumed: it is exactly a directory
    holding a `.git` entry (a FILE in a linked worktree, a directory in a
    clone). Nothing here depends on worktrees living under `.claude/worktrees`
    or on any other naming convention - `git worktree add` accepts any path.

    Filesystem stats only, deliberately. rel_path runs on every Edit and Write
    through no_slop, guard_frozen, guard_spec, guard_tests and guard_models,
    so shelling out to `git rev-parse --show-toplevel` here would put a
    subprocess in front of every tool call in every session. The walk is
    bounded, and the caller's try/except keeps the whole thing fail-open: on
    any trouble the answer degrades to the old project-relative path rather
    than to a block.
    """
    directory = os.path.dirname(candidate)
    for _ in range(64):
        if not directory.startswith(root_norm + "/"):
            return None
        if os.path.exists(os.path.join(directory, ".git")):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent
    return None


def rel_path(root, file_path):
    """Path for file_path relative to the checkout that OWNS it.

    Usually that is the project root. When file_path sits inside a linked
    worktree (or any nested checkout) under the root, it is relative to THAT
    worktree instead, so `<root>/.claude/worktrees/<slug>/company/state/
    gates.status` reads as `company/state/gates.status` and matches the same
    patterns the main checkout's copy matches.

    Falls back to the input (minus a leading slash) when file_path is outside
    the project tree.
    """
    if not file_path:
        return ""
    norm = file_path.replace("\\", "/")
    try:
        root_norm = os.path.abspath(root).replace("\\", "/").rstrip("/")
        if norm.startswith("/"):
            candidate = norm
        else:
            candidate = root_norm + "/" + norm
        candidate = os.path.normpath(candidate).replace("\\", "/")
        if candidate == root_norm:
            return ""
        if candidate.startswith(root_norm + "/"):
            inner = _enclosing_checkout(candidate, root_norm)
            if inner:
                return candidate[len(inner) + 1:]
            return candidate[len(root_norm) + 1:]
    except Exception:
        pass
    return norm.lstrip("/")


def owning_checkout(root, file_path):
    """The checkout that OWNS file_path, or None when it is outside the tree.

    The path half of the acting-tree rule: a hook judges the tree that
    contains the thing being acted on. For a file in a linked worktree that is
    the worktree; for a file in the main checkout it is `root`; for a path
    that is not under the project at all - a scratchpad under /private/tmp,
    somebody's home directory - it is None, and None means "not this
    project's business", never "treat it as project source".

    Derived from `_enclosing_checkout`, so it is convention-free: a worktree
    is a directory holding a `.git` entry, not a directory whose path happens
    to contain `.claude/worktrees`. `git worktree add` accepts any path.

    Filesystem stats only, and every failure degrades to `root` rather than to
    a block - the same fail-open contract rel_path holds.
    """
    if not file_path:
        return root
    norm = file_path.replace("\\", "/")
    try:
        root_norm = os.path.abspath(root).replace("\\", "/").rstrip("/")
        if norm.startswith("/"):
            candidate = norm
        else:
            candidate = root_norm + "/" + norm
        candidate = os.path.normpath(candidate).replace("\\", "/")
        if candidate == root_norm:
            return root_norm
        if not candidate.startswith(root_norm + "/"):
            return None
        return _enclosing_checkout(candidate, root_norm) or root_norm
    except Exception:
        return root


def _enclosing_checkout_anywhere(candidate):
    """The nearest git working-tree root at or above `candidate`, unbounded by
    any project root, or None. Filesystem stats only, bounded walk.
    """
    directory = os.path.dirname(candidate)
    for _ in range(64):
        if os.path.exists(os.path.join(directory, ".git")):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent
    return None


def path_checkout(root, file_path):
    """(tree, outside) - the checkout that GOVERNS file_path.

    `owning_checkout` stops at the project root, which is the right answer for
    a scratchpad file and the wrong one for a worktree. `git worktree add`
    accepts any path, so a lane building in /tmp/<slug> is writing this
    project's source no less than one building under `.claude/worktrees/` -
    exempting it would hand any lane unbriefed, ungated source writes just by
    choosing where to put its worktree.

    So a path outside the root is checked ONE step further: if some checkout
    encloses it and that checkout shares this repository's object store, it
    governs the file and `outside` is False. `outside` is True only when the
    path belongs to no checkout of this project at all - the scratchpad case,
    which is genuinely none of this project's business.

    The extra work is two git calls, and it runs ONLY for paths outside the
    root. Everything inside stays pure filesystem stats, which matters because
    this sits in front of every Edit and Write.
    """
    tree = owning_checkout(root, file_path)
    if tree is not None:
        return tree, False
    try:
        norm = file_path.replace("\\", "/")
        candidate = os.path.normpath(norm).replace("\\", "/")
        external = _enclosing_checkout_anywhere(candidate)
        # `is not False`: only an AFFIRMATIVE "different repository" exempts a
        # path that some checkout owns. True and None (git did not answer)
        # both keep it gated, because the cost of exempting project source by
        # mistake is unbriefed, ungated writes, and the cost of gating a
        # stranger's file by mistake is one clear, self-serve block.
        if external and same_repository(external, root) is not False:
            return external, False
    except Exception:
        pass
    return root, True


def task_state_root(root, tree):
    """The checkout whose company/state/active-task.json governs `tree`.

    Task state is untracked and lives wherever a session put it. A worktree
    that keeps its OWN active-task.json is self-describing and is read from
    there; a worktree that does not - the common case in this repo, where the
    file is untracked and only the main checkout has one - falls back to
    `root`, which is where the CEO maintains it.

    Presence, not content, decides. A tree that has the file but lists no
    entries is stating that no task is in flight there, and that statement is
    the acting tree's to make.
    """
    try:
        if tree and os.path.exists(active_tasks_path(tree)):
            return tree
    except Exception:
        pass
    return root


# What git said, and whether it said anything at all. THREE outcomes, because
# two of them used to share one return value.
GIT_ANSWERED = "answered"   # exit 0. text is stdout, possibly "" - a real
                            # answer meaning "nothing to report".
GIT_REFUSED = "refused"     # git ran and exited non-zero. A real NEGATIVE
                            # answer: not a repository, no such ref, bad path.
GIT_SILENT = "silent"       # git never answered: timed out, or could not run.

GIT_TIMEOUT = 5             # hot-path calls (rev-parse), unchanged
GIT_SLOW_TIMEOUT = 30       # whole-tree questions worth waiting on


def git_result(root, args, timeout=GIT_TIMEOUT):
    """(status, text) - what git said, and whether it said anything.

    THE DISTINCTION IS LOAD-BEARING. `_git` collapses REFUSED and SILENT to
    None, and an ANSWERED-but-empty to "", so a caller writing `if not out`
    cannot tell "the tree is clean" from "git did not answer in time". Those
    are OPPOSITE facts sharing one falsy value, and every arming condition
    built on the falsy test silently disarmed whenever git was slow - with
    nothing in the log to say why.

    That is reachable in normal operation, not just on a pathological box: on
    this machine a sibling lane running its own ladder took another lane's
    hooks suite from 40 seconds to 217 on pure CPU contention, and the default
    timeout here is 5. A security gate that stops gating under load, quietly,
    is worse than one that never gated.

    Use this wherever the difference decides anything. `_git` stays for the
    calls where a negative answer and an unanswered question lead to the same
    place - `rev-parse --is-inside-work-tree` on a directory that is not a
    work tree, say, where both mean "do not resolve to it".

    A SILENT result leaves one breadcrumb in the project's adherence log. It
    reaches no decision; it just means silence is never invisible again.
    """
    try:
        result = subprocess.run(
            ["git", "-C", root] + args, capture_output=True, timeout=timeout
        )
    except Exception as exc:
        _log_git_silence(root, args, exc)
        return GIT_SILENT, ""
    if result.returncode != 0:
        return GIT_REFUSED, ""
    return GIT_ANSWERED, result.stdout.decode("utf-8", "replace")


def _log_git_silence(root, args, exc):
    """One SILENT line when git does not answer. Never raises, never decides."""
    try:
        target = os.environ.get("CLAUDE_PROJECT_DIR") or root
        adherence_log(
            target, "timing", "GIT-SILENT",
            os.path.basename(os.path.abspath(root)) or str(root),
            "git {} did not answer ({})".format(
                " ".join(args[:2]), type(exc).__name__
            ),
        )
    except Exception:
        pass


def _git(root, args, timeout=GIT_TIMEOUT):
    """stdout on success, None when git refused OR did not answer.

    Kept for callers where those two lead to the same place. When they do
    not - when silence could read as safety - use git_result instead.
    """
    status, text = git_result(root, args, timeout=timeout)
    return text if status == GIT_ANSWERED else None


def current_branch(root):
    """Current branch name, or None on git uncertainty."""
    out = _git(root, ["symbolic-ref", "--short", "HEAD"])
    if out is None:
        return None
    return out.strip() or None


# --- the acting tree, for a Bash command ----------------------------------
# This is THE tree-resolution implementation for command-gated hooks, and it
# lives here so there is exactly one of it. guard_secrets is the cautionary
# tale: under FR-HP-12 it adopted guard_commit's PARSER and not its TREE
# RESOLUTION, kept reading its staged diff from CLAUDE_PROJECT_DIR, and every
# delegated commit in the repo's history went unscanned for secrets. A hook
# that resolves its own tree is how that returns, so callers import from here
# and re-export at most an alias - never a second copy.


# FR-HP-10: global options that carry a SEPARATED argument. Skipping one token
# each leaves the argument to be read as the subcommand, so `git -C sub commit`
# parses as subcommand "sub" and the whole segment goes unseen by every
# Bash-gated check. Attached forms (-Cdir, --git-dir=x) carry their argument in
# the same token and consume one token only.
ARG_OPTS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
            "--exec-path")


def segments(command):
    """A compound shell command split into its individual command segments."""
    parts = re.split(r"&&|\|\||;|\|", command or "")
    return [p.strip() for p in parts if p.strip()]


def tokens(segment):
    """shlex tokens, degrading to a whitespace split on unbalanced quotes.

    Public because guards outside the git parsers need it: guard_tests reads a
    plain `rm` segment, which is not a git command, and a second local shlex
    block there is the same duplication this module exists to end.
    """
    try:
        return shlex.split(segment)
    except Exception:
        return segment.split()


def git_subcmd(segment):
    """Return (subcommand, args) for a `git ...` segment, else (None, []).

    Only tokens BEFORE the subcommand are scanned: `git commit -C HEAD~1` is
    --reuse-message, where HEAD~1 is a commit ref and not a path.
    """
    toks = tokens(segment)
    if not toks or toks[0] != "git":
        return None, []
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in ARG_OPTS else 1
    if i >= len(toks):
        return None, []
    return toks[i], toks[i + 1:]


def seg_c_path(segment):
    """The `-C` argument of a git segment AS WRITTEN, or None.

    Returned unexpanded on purpose. A hook sees raw command text, so
    `git -C "$WT" commit` yields the literal `$WT`, which no filesystem call
    can resolve - and a block message that pretends otherwise sends the reader
    to fix the wrong thing. Callers use this to SAY what they could not
    resolve; they never treat it as a path.
    """
    toks = tokens(segment)
    path = None
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] == "-C" and i + 1 < len(toks):
            path = toks[i + 1]
        elif toks[i].startswith("-C") and len(toks[i]) > 2:
            path = toks[i][2:]
        i += 2 if toks[i] in ARG_OPTS else 1
    return path


def git_cwd(payload, root):
    """The directory a git command without -C actually runs in (#26).

    A commit issued from a worktree checkout of a task branch must be judged
    by that worktree, even when CLAUDE_PROJECT_DIR (and thus root) points at
    the main checkout on a protected branch. Prefer the payload's cwd when it
    is present and inside a git work tree; otherwise fall back to root.
    """
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        if cwd:
            out = _git(cwd, ["rev-parse", "--is-inside-work-tree"])
            if out is not None and out.strip() == "true":
                return cwd
    return root


def _common_dir(directory):
    """(status, absolute shared .git dir). See git_result for the statuses."""
    status, text = git_result(directory, ["rev-parse", "--git-common-dir"])
    if status != GIT_ANSWERED:
        return status, None
    out = text.strip()
    if not out:
        return GIT_REFUSED, None
    if not os.path.isabs(out):
        out = os.path.join(directory, out)
    try:
        return GIT_ANSWERED, os.path.realpath(out)
    except Exception:
        return GIT_REFUSED, None


def git_common_dir(directory):
    """The absolute shared .git directory behind `directory`, or None.

    A main checkout and every linked worktree of it share ONE object store, so
    this value is the identity of the REPOSITORY rather than of the checkout.
    Nothing here reads a path convention.
    """
    return _common_dir(directory)[1]


def same_repository(a, b):
    """True / False / None - are these checkouts of the SAME repository?

    The line run-gates.sh draws for itself, made reusable: a cwd that merely
    happens to sit inside SOME other git repository must not redirect a run,
    while a linked worktree of the project must. Distinguishing the two needs
    the shared object store, not the path.

    THREE-VALUED ON PURPOSE. None means git did not answer, which is not the
    same fact as "different repository" and must never be read as one - that
    collapse is exactly how a gate disarms under load. Callers decide which
    way to lean and say so:

      - a caller REDIRECTING somewhere on the strength of this (scan_branch)
        acts only on True, so silence leaves it where it was.
      - a caller EXEMPTING something on the strength of this (path_checkout)
        acts only on False, so silence keeps the path gated.

    Both stay conservative under silence, in opposite directions, which is
    only possible because the third value exists.
    """
    if not a or not b:
        return False
    status_a, dir_a = _common_dir(a)
    if status_a == GIT_SILENT:
        return None
    status_b, dir_b = _common_dir(b)
    if status_b == GIT_SILENT:
        return None
    if status_a != GIT_ANSWERED or status_b != GIT_ANSWERED:
        return False
    return dir_a == dir_b


def acting_tree(segment, payload, root):
    """(directory, unresolved) - the tree a single git SEGMENT acts on.

    FR-HP-11: `git -C <path> commit` lands the commit on the tree that -C
    names, so that tree is what every check on the segment must be judged by.
    Resolved PER SEGMENT, so a -C in one segment cannot decide another. The
    LAST -C wins, which is git's own semantics. A relative path resolves
    against the payload cwd when present, else root.

    `unresolved` is the -C argument as written when a -C was present and could
    not be confirmed as a work tree, else None. That happens most often
    because the argument is a shell variable the hook never sees expanded, and
    a caller that reports "you are not on a task branch" without saying the -C
    target was unresolvable hands the reader a recipe for a tree it is not
    talking about.

    OQ-HP-12 assumption: accept the candidate only when git itself answers
    `true` there. Any other answer - missing directory, not a repo, git
    error - falls through to git_cwd, which falls back to root. Fail open,
    never fail hard.
    """
    path = seg_c_path(segment)
    if path:
        base = payload.get("cwd") if isinstance(payload, dict) else None
        base = base or root
        cand = path if os.path.isabs(path) else os.path.join(base, path)
        out = _git(cand, ["rev-parse", "--is-inside-work-tree"])
        if out is not None and out.strip() == "true":
            return cand, None
        return git_cwd(payload, root), path
    return git_cwd(payload, root), None


def seg_git_dir(segment, payload, root):
    """The directory a git segment acts on. `acting_tree` without the note."""
    return acting_tree(segment, payload, root)[0]


def is_git_tracked(file_path):
    """True if committed/staged in git (shipped, immutable).

    Returns True on any uncertainty (git missing, not a repo) so immutability
    checks fail safe. Returncode 1 is a real untracked file inside a repo,
    which is the freshly generated artifact we want to leave editable.
    """
    directory = os.path.dirname(file_path) or "."
    try:
        result = subprocess.run(
            ["git", "-C", directory, "ls-files", "--error-unmatch", file_path],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return True
    return result.returncode != 1


def _git_env(root, args, env):
    """_git with an explicit environment, for throwaway-index operations.

    The longer timeout covers a full `add -A` over a cold repo.
    """
    try:
        result = subprocess.run(
            ["git", "-C", root] + args,
            capture_output=True,
            timeout=15,
            env=env,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


# Paths that never participate in the fingerprint. The line this tuple draws is
# INPUTS versus SHIPPED BEHAVIOR, and it will look inconsistent to anyone who
# reads it as "prose in or prose out", so read the distinction before editing:
#
#   - company/state is machine-written OUTPUT: the gate stamp, the adherence
#     log, the ledgers. Leaving it in would self-invalidate the hash the
#     instant a hook wrote a line - the stamp would be stale before it was
#     read.
#   - company/briefs and company/specs are build INPUTS. They say what to
#     build; they are not the thing built, they ship in no install
#     (package.json excludes both), and no hook reads them to reach a verdict.
#     A brief edit invalidating a green gate result is a re-run that proves
#     nothing, and it cost this program two full ladder runs before the
#     exclusion landed (owner-authorized, 2026-08-13).
#
# Everything else stays IN, and that is not an oversight to be tidied up. A
# downstream fork of this kernel drops *.md and *.txt wholesale on the argument
# that prose decides no gate outcome. True there, FALSE here: markdown IS this
# product. ORCHESTRATOR.md, company/METHOD.md, .claude/agents/** and
# .claude/skills/** are executable product, no_slop and trace_check and
# guard_models all gate them, and a shipped install is mostly prose. Excluding
# doctrine would mean a green stamp survives replacing every role in the
# company.
#
# So: adding a path here needs the argument "this is an input to the build",
# not "this is only documentation". If it ships or a hook reads it, it counts.
HASH_EXCLUDES = (
    "company/state",
    "company/briefs",
    "company/specs",
)


def _content_tree_hash(root):
    """The git tree object this working tree would commit as, minus
    HASH_EXCLUDES. None on any git trouble.

    Built in a THROWAWAY index pointed at by GIT_INDEX_FILE: the repo's real
    .git/index is never read for this and never written, which is the whole
    mechanism. Corrupting a developer's index would be far worse than the
    staleness this fixes.
    """
    fd, tmp = tempfile.mkstemp(prefix="cc-hash-index-")
    os.close(fd)
    try:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = tmp
        # Seed from HEAD so deletions register; an unborn HEAD starts empty.
        if _git_env(root, ["rev-parse", "--verify", "-q", "HEAD"], env):
            if _git_env(root, ["read-tree", "HEAD"], env) is None:
                return None
        if _git_env(root, ["add", "-A", "--", "."], env) is None:
            return None
        if HASH_EXCLUDES:
            _git_env(
                root,
                ["rm", "-r", "-q", "--cached", "--ignore-unmatch", "--"]
                + list(HASH_EXCLUDES),
                env,
            )
        out = _git_env(root, ["write-tree"], env)
        return out.strip() if out else None
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


# A content hash slower than this is an anomaly worth a breadcrumb.
SLOW_HASH_SECONDS = 1.5  # OQ-HP-03 assumption


def _log_slow_hash(root, elapsed):
    """One TIMING line for an anomalously slow work_hash. Never raises.

    The log target is CLAUDE_PROJECT_DIR when set, else `root` itself. This is
    a single-repo product - the root IS the project - so falling back to root
    keeps the breadcrumb in the one place a reader would look. A downstream
    fork that hashes sub-repos stays silent without the env var; here silence
    would just make the breadcrumb useless.
    """
    try:
        target = os.environ.get("CLAUDE_PROJECT_DIR") or root
        adherence_log(
            target,
            "timing",
            "SLOW",
            os.path.basename(os.path.abspath(root)) or str(root),
            "work_hash took {:.1f}s (threshold {}s)".format(
                elapsed, SLOW_HASH_SECONDS
            ),
        )
    except Exception:
        pass


def work_hash(root):
    """CONTENT fingerprint of the working tree. Fail-open to 'no-git'.

    The hash is the tree object the working tree would commit as, so two
    states with identical content fingerprint identically no matter where they
    sit in history. Committing audited work, amending, or merging a branch
    that changes no byte therefore stales neither the gate stamp nor an audit,
    which is what the old HEAD+status+diff digest got wrong: it fingerprinted
    history POSITION, so the act of committing green work turned it red.

    Falls back to that legacy digest on any git trouble, and to 'no-git' when
    git answers nothing at all - a broken git degrades to the old, stricter
    behavior rather than disarming freshness checks. See HASH_EXCLUDES for
    what never counts.

    A call slower than SLOW_HASH_SECONDS leaves one TIMING line in the
    project's adherence.log. The breadcrumb reaches no decision and cannot
    change the returned hash.
    """
    start = time.time()
    try:
        return _work_hash_impl(root)
    finally:
        elapsed = time.time() - start
        if elapsed > SLOW_HASH_SECONDS:
            _log_slow_hash(root, elapsed)


def _work_hash_impl(root):
    tree = _content_tree_hash(root)
    if tree:
        return "tree:" + tree
    exclude = ["--", "."] + [":(exclude)" + p for p in HASH_EXCLUDES]
    head = _git(root, ["rev-parse", "HEAD"])
    status = _git(root, ["status", "--porcelain"] + exclude)
    diff = _git(root, ["diff"] + exclude)
    cached = _git(root, ["diff", "--cached"] + exclude)
    if head is None and status is None and diff is None and cached is None:
        return "no-git"
    digest = hashlib.sha256()
    for part in (head, status, diff, cached):
        digest.update((part or "").encode("utf-8", "replace"))
        digest.update(b"\x00")
    return digest.hexdigest()


def stamp_checksum(payload_without_checksum):
    """sha256 of canonical stamp payload plus the salt."""
    canonical = json.dumps(
        payload_without_checksum, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(
        (canonical + CHECKSUM_SALT).encode("utf-8")
    ).hexdigest()


def read_stamp(root):
    return read_json_file(
        os.path.join(root, "company", "state", "gates.status")
    )


def check_stamp(root):
    """Return (ok, reason). ok iff the stamp is green, fresh, and valid."""
    stamp = read_stamp(root)
    if stamp is None:
        return False, "no gates.status stamp (gates have not been run)"
    if not isinstance(stamp, dict):
        return False, "gates.status is malformed"
    stored = stamp.get("checksum")
    payload = {k: v for k, v in stamp.items() if k != "checksum"}
    if stored != stamp_checksum(payload):
        return False, "gates.status checksum invalid (stamp edited by hand)"
    if stamp.get("status") != "green":
        return False, "gates are red (last run had failing gates)"
    if stamp.get("work_hash") != work_hash(root):
        return False, "gates.status is stale (work changed since gates ran)"
    return True, "green"
