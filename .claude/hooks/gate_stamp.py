#!/usr/bin/env python3
"""Gate stamp CLI (NOT a hook). Called by the gate runner.

  python3 gate_stamp.py --results '{"gates":[{"name":"tests","ok":true}]}'
      Compute overall status (green iff every gate ok), the work hash, and a
      checksum, then write company/state/gates.status.

  python3 gate_stamp.py --check
      Exit 0 if the stamp is green + fresh + valid, else exit 1 with a reason.

Project root comes from CLAUDE_PROJECT_DIR, falling back to the cwd.
"""

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402


def resolve_root():
    # FR-HP-28: deliberately unchanged. The gate runner is now the thing that
    # decides which tree was gated and invokes this CLI with CLAUDE_PROJECT_DIR
    # set to it, so a worktree run stamps the worktree. "Fixing" this fallback
    # to prefer a git root or the harness-pinned dir reopens the false-green.
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _atomic_write_json(path, payload):
    """Write `payload` as JSON to `path` through a same-directory temp file.

    The temp file is created in the DESTINATION directory so os.replace is a
    rename within one filesystem, which is the atomic step. On any failure the
    temp file is removed and `path` is left byte-unchanged.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".gates.status.", dir=directory)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_stamp(root, results_json):
    data = json.loads(results_json)
    gates = data.get("gates", []) or []
    all_ok = all(bool(g.get("ok")) for g in gates)
    status = "green" if all_ok else "red"
    payload = {
        "status": status,
        "ran_at": c.iso_now(),
        "work_hash": c.work_hash(root),
        "gates": gates,
    }
    payload["checksum"] = c.stamp_checksum(
        {k: v for k, v in payload.items() if k != "checksum"}
    )
    state_dir = os.path.join(root, "company", "state")
    os.makedirs(state_dir, exist_ok=True)
    # FR-HP-24: atomic replace, never an in-place rewrite. guard_commit and
    # stop_gate read this file at arbitrary moments; a torn read surfaced to
    # them as a false "gates.status is malformed" merge block.
    #
    # L1 SEAM (FR-HP-02 / FR-HP-24): the kernel lane is landing
    # _common.atomic_write_json(path, payload) this wave, in parallel with
    # this change. Prefer it the moment it exists. Once that lane merges,
    # _atomic_write_json above is dead code and can be deleted deliberately.
    writer = getattr(c, "atomic_write_json", None) or _atomic_write_json
    writer(os.path.join(state_dir, "gates.status"), payload)
    return status


def main():
    ap = argparse.ArgumentParser(description="claude-company gate stamp")
    ap.add_argument("--results", help="JSON gate results")
    ap.add_argument("--check", action="store_true", help="verify stamp")
    args = ap.parse_args()

    root = resolve_root()

    if args.check:
        ok, reason = c.check_stamp(root)
        print(reason)
        sys.exit(0 if ok else 1)

    if args.results:
        try:
            status = write_stamp(root, args.results)
        except Exception as exc:
            print("gate_stamp: failed to write stamp: {}".format(exc),
                  file=sys.stderr)
            sys.exit(1)
        print("wrote gates.status: {}".format(status))
        sys.exit(0)

    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
