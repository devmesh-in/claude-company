#!/usr/bin/env python3
"""trace_check.py (#22) - requirement traceability gate.

CLI (not a hook): python3 .claude/hooks/trace_check.py [--spec <path>]

Extracts requirement IDs (FR-/BR-) from a spec, then for each id checks that it
is referenced in at least one TEST file AND at least one non-test SOURCE file
among the git-tracked files. An id missing from either side (or absent
entirely) is an ORPHAN.

Prints a human matrix and exactly one machine line last:
  TRACE_JSON: {"total": N, "orphans": [...], "ok": <bool>}

Exit 1 ONLY when there is at least one orphan; otherwise exit 0. The no-spec
case exits 0. Any internal error fails OPEN (diagnostic to stderr, exit 0).

Python 3.8 stdlib only.
"""

import argparse
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "trace_check"

# FR-AUTH-01 / BR-PAY-3 (two dashes) and the bare FR-03 form (one dash).
ID_RE_SEGMENTED = re.compile(r"\b(?:FR|BR)-[A-Z0-9]+-\d+\b")
ID_RE_BARE_FR = re.compile(r"\bFR-\d+\b")


def resolve_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def extract_ids(text):
    ids = set()
    ids.update(ID_RE_SEGMENTED.findall(text))
    ids.update(ID_RE_BARE_FR.findall(text))
    return ids


def spec_has_fr(text):
    return any(i.startswith("FR-") for i in extract_ids(text))


def find_spec(root):
    """Newest .md (by mtime) under company/specs/ that contains an FR- id."""
    specs_dir = os.path.join(root, "company", "specs")
    if not os.path.isdir(specs_dir):
        return None
    candidates = []
    for dirpath, _dirs, files in os.walk(specs_dir):
        for fn in files:
            if fn.endswith(".md"):
                candidates.append(os.path.join(dirpath, fn))
    try:
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    except Exception:
        pass
    for p in candidates:
        if spec_has_fr(read_text(p)):
            return p
    return None


def is_test_file(path):
    """test = under a tests/ dir, or basename test_* / *_test.* / *.test.* /
    *.spec.* (same rule the risk scorer uses)."""
    if "tests" in path.split("/"):
        return True
    base = os.path.basename(path)
    if base.startswith("test_"):
        return True
    for pat in ("*_test.*", "*.test.*", "*.spec.*"):
        if fnmatch.fnmatch(base, pat):
            return True
    return False


def tracked_files(root):
    out = c._git(root, ["ls-files"])
    if not out:
        return []
    return [f for f in out.splitlines() if f.strip()]


def classify_files(root):
    """Return (test_texts, source_texts): lists of file contents by class."""
    test_texts = []
    source_texts = []
    for rel in tracked_files(root):
        text = read_text(os.path.join(root, rel))
        if is_test_file(rel):
            test_texts.append(text)
        else:
            source_texts.append(text)
    return test_texts, source_texts


def print_matrix(rows):
    header = "{:<16} {:<9} {:<9} {}".format(
        "ID", "IN TEST?", "IN SRC?", "TRACEABLE?")
    print(header)
    print("-" * len(header))
    for rid, in_test, in_src, ok in rows:
        print("{:<16} {:<9} {:<9} {}".format(
            rid,
            "yes" if in_test else "no",
            "yes" if in_src else "no",
            "yes" if ok else "NO"))
    print("")


def run(root, spec_arg):
    if spec_arg:
        spec = spec_arg if os.path.isabs(spec_arg) else os.path.join(
            root, spec_arg)
        if not os.path.exists(spec):
            print("no spec with FR IDs")
            print("TRACE_JSON: " + json.dumps(
                {"total": 0, "orphans": [], "ok": True}, sort_keys=True))
            c.adherence_log(root, HOOK, "INFO", "0 orphans", "no spec")
            return 0
    else:
        spec = find_spec(root)

    if spec is None:
        print("no spec with FR IDs")
        print("TRACE_JSON: " + json.dumps(
            {"total": 0, "orphans": [], "ok": True}, sort_keys=True))
        c.adherence_log(root, HOOK, "INFO", "0 orphans", "no spec")
        return 0

    ids = sorted(extract_ids(read_text(spec)))
    if not ids:
        print("no spec with FR IDs")
        print("TRACE_JSON: " + json.dumps(
            {"total": 0, "orphans": [], "ok": True}, sort_keys=True))
        c.adherence_log(root, HOOK, "INFO", "0 orphans", "spec has no ids")
        return 0

    test_texts, source_texts = classify_files(root)

    rows = []
    orphans = []
    for rid in ids:
        in_test = any(rid in t for t in test_texts)
        in_src = any(rid in t for t in source_texts)
        ok = in_test and in_src
        rows.append((rid, in_test, in_src, ok))
        if not ok:
            orphans.append(rid)

    print("spec: {}".format(os.path.relpath(spec, root)))
    print("")
    print_matrix(rows)

    orphans = sorted(orphans)
    print("TRACE_JSON: " + json.dumps(
        {"total": len(ids), "orphans": orphans, "ok": not orphans},
        sort_keys=True))

    c.adherence_log(
        root, HOOK, "INFO", "{} orphans".format(len(orphans)),
        "total={}".format(len(ids)))

    return 1 if orphans else 0


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--spec")
    args = parser.parse_args(argv[1:])
    root = resolve_root()
    return run(root, args.spec)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as exc:
        # Fail open: never brick a session on a traceability bug.
        print("trace_check internal error: {}".format(exc), file=sys.stderr)
        sys.exit(0)
