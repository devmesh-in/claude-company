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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402


def resolve_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


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
    with open(os.path.join(state_dir, "gates.status"), "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
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
