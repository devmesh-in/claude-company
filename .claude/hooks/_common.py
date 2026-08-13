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
        with open(os.path.join(state_dir, "adherence.log"), "a") as f:
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


def _git(root, args):
    try:
        result = subprocess.run(
            ["git", "-C", root] + args, capture_output=True, timeout=5
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


def current_branch(root):
    """Current branch name, or None on git uncertainty."""
    out = _git(root, ["symbolic-ref", "--short", "HEAD"])
    if out is None:
        return None
    return out.strip() or None


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
