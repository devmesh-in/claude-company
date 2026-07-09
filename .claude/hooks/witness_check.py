#!/usr/bin/env python3
"""Witness manifest CLI (NOT a hook). Integrity checker for load-bearing markers.

A "witness" asserts that a literal substring (or regex) still exists in a named
file. The registry (company/witnesses.json) is a checksum-sealed list of these
canaries: if a marker disappears - because someone refactored a load-bearing
line out - --check FAILS LOUDLY (exit 1). Registry mutations flow ONLY through
--add / --remove; the checksum makes a hand-edit detectable.

  python3 witness_check.py [--check]
      Validate. Verify the checksum FIRST (a mismatch means the file was
      hand-edited -> exit 1 immediately). Then every witness's file must exist
      and contain its marker. Print a table, then a last WITNESS_JSON line.
      Exit 0 if all pass, 1 if any fail.

  python3 witness_check.py --add --file F --contains S --task T --why W [--regex]
      Append a witness (id W-NNN, next free suffix), recompute the checksum,
      write the registry, log an adherence INFO line.

  python3 witness_check.py --remove W-NNN --why W
      Remove a witness by id, recompute the checksum, write, log.

DEVIATION from the repo's fail-open philosophy: this CLI is an integrity
checker. A checksum mismatch or a missing marker must fail LOUDLY (exit 1),
never fail open. Fail-open would defeat the entire point of a canary.

Project root comes from CLAUDE_PROJECT_DIR, falling back to the cwd. Python 3.8
stdlib only.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "witness_check"

DEFAULT_COMMENT = (
    "Checksum-sealed witness registry: load-bearing substrings that must still "
    "exist in named files. Mutate ONLY via witness_check.py --add / --remove."
)


def resolve_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def registry_path(root):
    return os.path.join(root, "company", "witnesses.json")


def compute_checksum(registry):
    """Checksum over the whole object MINUS the checksum key (gate-stamp idiom)."""
    payload = {k: v for k, v in registry.items() if k != "checksum"}
    return c.stamp_checksum(payload)


def empty_registry():
    return {"$comment": DEFAULT_COMMENT, "version": 1, "witnesses": []}


def write_registry(root, registry):
    registry["checksum"] = compute_checksum(registry)
    path = registry_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")


def next_id(witnesses):
    """Next W-NNN: max existing numeric suffix + 1, zero-padded to 3."""
    highest = 0
    for w in witnesses:
        wid = w.get("id", "") if isinstance(w, dict) else ""
        m = re.match(r"^W-(\d+)$", str(wid))
        if m:
            highest = max(highest, int(m.group(1)))
    return "W-%03d" % (highest + 1)


# --- --add ---------------------------------------------------------------
def cmd_add(root, args):
    if not args.file or not args.contains or not args.task or not args.why:
        print("witness_check --add requires --file, --contains, --task, --why",
              file=sys.stderr)
        return 2

    path = registry_path(root)
    if os.path.exists(path):
        registry = c.read_json_file(path)
        if not isinstance(registry, dict) or not isinstance(
                registry.get("witnesses"), list):
            print("witness_check: {} is malformed - cannot add".format(path),
                  file=sys.stderr)
            return 1
    else:
        registry = empty_registry()

    witnesses = registry["witnesses"]
    wid = next_id(witnesses)
    witness = {
        "id": wid,
        "task": args.task,
        "file": args.file,
        "must_contain": args.contains,
        "regex": bool(args.regex),
        "why": args.why,
        # FALLBACK OQ-W2-03: UTC ISO, second precision; determinism not required.
        "added_at": c.iso_now(),
    }
    witnesses.append(witness)
    write_registry(root, registry)
    c.adherence_log(root, HOOK, "INFO", wid,
                    "added witness for {}".format(args.file))
    print("added {} -> {} (must_contain: {!r}, regex={})".format(
        wid, args.file, args.contains, bool(args.regex)))
    return 0


# --- --remove ------------------------------------------------------------
def cmd_remove(root, args):
    wid = args.remove
    if not args.why:
        print("witness_check --remove requires --why", file=sys.stderr)
        return 2

    path = registry_path(root)
    if not os.path.exists(path):
        print("witness_check: no registry at {} - nothing to remove".format(
            path), file=sys.stderr)
        return 1
    registry = c.read_json_file(path)
    if not isinstance(registry, dict) or not isinstance(
            registry.get("witnesses"), list):
        print("witness_check: {} is malformed - cannot remove".format(path),
              file=sys.stderr)
        return 1

    witnesses = registry["witnesses"]
    kept = [w for w in witnesses if w.get("id") != wid]
    if len(kept) == len(witnesses):
        print("witness_check: no witness with id {} - nothing removed".format(
            wid), file=sys.stderr)
        return 1

    registry["witnesses"] = kept
    write_registry(root, registry)
    c.adherence_log(root, HOOK, "INFO", wid, "removed: {}".format(args.why))
    # Removal is never silent.
    print("removed {} ({} witnesses remain): {}".format(
        wid, len(kept), args.why))
    return 0


# --- --check -------------------------------------------------------------
def marker_present(root, witness):
    """(ok, reason). ok iff the witness file exists and holds its marker."""
    rel = witness.get("file") or ""
    marker = witness.get("must_contain")
    if not rel or marker is None:
        return False, "malformed witness (no file/marker)"
    target = os.path.join(root, rel)
    if not os.path.isfile(target):
        return False, "file missing: {}".format(rel)
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        return False, "unreadable: {}".format(exc)

    if witness.get("regex"):
        try:
            found = re.search(marker, content) is not None
        except re.error as exc:
            return False, "bad regex: {}".format(exc)
    else:
        found = marker in content

    if found:
        return True, witness.get("why") or ""
    return False, "marker absent: {!r}".format(marker)


def print_table(rows):
    """rows: list of (id, file, status, detail)."""
    header = ("ID", "FILE", "STATUS", "WHY / REASON")
    allrows = [header] + rows
    w0 = max(len(r[0]) for r in allrows)
    w1 = max(len(r[1]) for r in allrows)
    w2 = max(len(r[2]) for r in allrows)
    for wid, f, status, detail in allrows:
        print("{}  {}  {}  {}".format(
            wid.ljust(w0), f.ljust(w1), status.ljust(w2), detail))


def cmd_check(root):
    path = registry_path(root)
    if not os.path.exists(path):
        print("witness_check: no registry at {} (run --add to seed one)".format(
            path), file=sys.stderr)
        return 1
    registry = c.read_json_file(path)
    if not isinstance(registry, dict):
        print("witness_check: {} is missing or malformed JSON".format(path),
              file=sys.stderr)
        return 1

    stored = registry.get("checksum")
    expected = compute_checksum(registry)
    if stored != expected:
        # LOUD: the checksum only mismatches if the file was hand-edited.
        print("witness_check: CHECKSUM MISMATCH in {}".format(path),
              file=sys.stderr)
        print("The registry was hand-edited. Witness mutations MUST go through "
              "witness_check.py --add / --remove, which recompute the checksum. "
              "Refusing to validate a tampered registry.", file=sys.stderr)
        return 1

    witnesses = registry.get("witnesses")
    if not isinstance(witnesses, list):
        print("witness_check: {} has no witnesses list".format(path),
              file=sys.stderr)
        return 1

    if not witnesses:
        print("no witnesses registered (registry is empty, checksum valid)")
        print("WITNESS_JSON: " + json.dumps(
            {"ok": True, "failed": [], "count": 0}, sort_keys=True))
        return 0

    rows = []
    failed = []
    for w in witnesses:
        wid = w.get("id", "?") if isinstance(w, dict) else "?"
        rel = w.get("file", "?") if isinstance(w, dict) else "?"
        ok, detail = marker_present(root, w if isinstance(w, dict) else {})
        rows.append((str(wid), str(rel), "pass" if ok else "FAIL", detail))
        if not ok:
            failed.append(wid)

    print_table(rows)
    result = {"ok": not failed, "failed": failed, "count": len(witnesses)}
    # The WITNESS_JSON line MUST be the LAST stdout line.
    print("WITNESS_JSON: " + json.dumps(result, sort_keys=True))
    return 0 if not failed else 1


def main():
    ap = argparse.ArgumentParser(
        description="claude-company witness manifest checker")
    ap.add_argument("--check", action="store_true",
                    help="validate the registry (default mode)")
    ap.add_argument("--add", action="store_true", help="append a witness")
    ap.add_argument("--remove", metavar="W-NNN", help="remove a witness by id")
    ap.add_argument("--file", help="witness target file (repo-relative)")
    ap.add_argument("--contains", help="the literal substring (or regex)")
    ap.add_argument("--task", help="task slug the witness belongs to")
    ap.add_argument("--why", help="one-line reason (add) or removal note")
    ap.add_argument("--regex", action="store_true",
                    help="treat --contains as a Python regex")
    args = ap.parse_args()

    root = resolve_root()

    if args.add:
        sys.exit(cmd_add(root, args))
    if args.remove:
        sys.exit(cmd_remove(root, args))
    # Default mode is validation, whether or not --check was passed.
    sys.exit(cmd_check(root))


if __name__ == "__main__":
    main()
