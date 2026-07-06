#!/usr/bin/env python3
"""Shared helpers for the claude-company enforcement hooks.

Python 3 stdlib only. Everything here fails open: on any internal error the
callers should treat the result as "allow" rather than bricking the session.
The one deliberate exception is git-tracked uncertainty in the immutability
checks, which fail safe (treat as tracked) per the frozen-surface contract.
"""

import datetime
import hashlib
import json
import os
import subprocess
import sys

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


def active_task(root):
    return read_json_file(
        os.path.join(root, "company", "state", "active-task.json")
    )


def gates_config(root):
    return read_json_file(os.path.join(root, "company", "gates.config"))


def rel_path(root, file_path):
    """Project-relative, forward-slash path for file_path under root.

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


def work_hash(root):
    """Fingerprint the working tree. Fail-open to 'no-git'.

    company/state/ is excluded from the fingerprint: the stamp and adherence
    log live there and would otherwise self-invalidate the hash the moment they
    are written.
    """
    exclude = ["--", ".", ":(exclude)company/state"]
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
