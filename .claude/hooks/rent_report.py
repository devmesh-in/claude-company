#!/usr/bin/env python3
"""Enforcement rent report. FR-ASR-12 / OQ-ASR-06 assumption.

Reads company/state/adherence.log and prints, per hook, BLOCK/WARN counts
in a window versus the hook's declared falsifiable claim. Unrecoverable-class
guards are rent-exempt (BR-ASR-12).

  python3 .claude/hooks/rent_report.py [--days N]

Python 3.8 stdlib only. Missing log -> empty table, exit 0 (fail open).
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

# Falsifiable claim per surviving guard. Unrecoverable-class: rent-exempt.
CLAIMS = {
    "guard_secrets": (
        "never let a secret reach a commit", True),
    "guard_frozen": (
        "unrecoverable artifacts (.env, evidence, ADRs) stay immutable", True),
    "guard_commit": (
        "no protected-branch commit mid-task; green fresh stamp at "
        "merge onto main; undeclared frozen drift", False),
    "guard_tests": (
        "builders do not edit the tests that judge them without a grant",
        False),
    "guard_models": (
        "spawn/frontmatter model matches the pin", False),
    "guard_spec": (
        "no source edit without an active brief", False),
    "no_slop": (
        "no slop glyphs in writes", False),
    "witness_check": (
        "load-bearing markers stay present", True),
    "trace_check": (
        "no orphan FR/BR at close-out", True),
}


def resolve_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def parse_ts(stamp):
    try:
        return datetime.datetime.strptime(
            stamp, "%Y-%m-%dT%H:%M:%SZ"
        )
    except Exception:
        return None


def main(argv):
    parser = argparse.ArgumentParser(description="enforcement rent report")
    parser.add_argument("--days", type=int, default=0,
                        help="window in days; 0 = whole log")
    args = parser.parse_args(argv[1:])
    root = resolve_root()
    path = c.adherence_log_path(root)
    cutoff = None
    if args.days and args.days > 0:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(
            days=args.days
        )

    counts = {}
    try:
        with open(path) as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 3:
                    continue
                ts, hook, action = parts[0], parts[1], parts[2]
                if cutoff is not None:
                    parsed = parse_ts(ts)
                    if parsed is None or parsed < cutoff:
                        continue
                slot = counts.setdefault(hook, {"BLOCK": 0, "WARN": 0})
                if action in slot:
                    slot[action] += 1
    except Exception:
        pass

    window = "all" if not args.days else "{}d".format(args.days)
    print("enforcement rent (window={})".format(window))
    print("{:<18} {:>7} {:>7} {:<8} {}".format(
        "HOOK", "BLOCKS", "WARNS", "RENT", "CLAIM"))
    print("-" * 78)
    names = sorted(set(list(CLAIMS) + list(counts)))
    for hook in names:
        claim, exempt = CLAIMS.get(hook, ("(undeclared)", False))
        slot = counts.get(hook, {"BLOCK": 0, "WARN": 0})
        rent = "exempt" if exempt else (
            "pays" if slot["BLOCK"] or slot["WARN"] else "idle"
        )
        print("{:<18} {:>7} {:>7} {:<8} {}".format(
            hook, slot["BLOCK"], slot["WARN"], rent, claim))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print("rent_report internal error: {}".format(exc), file=sys.stderr)
        sys.exit(0)
