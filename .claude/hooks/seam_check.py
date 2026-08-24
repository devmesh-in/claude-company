#!/usr/bin/env python3
"""Mechanical brief-ownership disjointness check. FR-ASR-13.

Parses `## You own` globs from company/briefs/*.md (not shipped/) and exits
1 if any two briefs share a glob or one glob is a prefix of another.

  python3 .claude/hooks/seam_check.py [--briefs-dir PATH]

Missing or empty briefs dir -> exit 0 (nothing to check). Python 3.8 stdlib.
"""

import argparse
import os
import sys

def resolve_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def parse_you_own(text):
    """Globs listed as `- `path`` under a 'You own' heading."""
    globs = []
    in_section = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            in_section = heading.startswith("you own")
            continue
        if not in_section:
            continue
        if not stripped.startswith("-"):
            continue
        rest = stripped[1:].strip()
        if rest.startswith("`") and "`" in rest[1:]:
            globs.append(rest[1:].split("`")[0].strip())
        elif rest:
            token = rest.split()[0].strip(".,;")
            if token:
                globs.append(token)
    return globs


def overlaps(a, b):
    """True if two ownership globs are not directory-disjoint."""
    if not a or not b:
        return False
    if a == b:
        return True
    na = a.rstrip("*").rstrip("/")
    nb = b.rstrip("*").rstrip("/")
    if not na or not nb:
        return True
    return na == nb or na.startswith(nb + "/") or nb.startswith(na + "/")


def brief_files(briefs_dir):
    out = []
    try:
        for fn in sorted(os.listdir(briefs_dir)):
            if not fn.endswith(".md"):
                continue
            if fn.startswith("."):
                continue
            path = os.path.join(briefs_dir, fn)
            if os.path.isfile(path):
                out.append(path)
    except Exception:
        return []
    return out


def main(argv):
    parser = argparse.ArgumentParser(description="brief ownership disjointness")
    parser.add_argument("--briefs-dir")
    args = parser.parse_args(argv[1:])
    root = resolve_root()
    briefs_dir = args.briefs_dir or os.path.join(root, "company", "briefs")
    if not os.path.isdir(briefs_dir):
        print("seam_check: no briefs dir")
        return 0

    owned = []
    for path in brief_files(briefs_dir):
        try:
            with open(path) as f:
                text = f.read()
        except Exception:
            continue
        globs = parse_you_own(text)
        if globs:
            owned.append((os.path.relpath(path, root), globs))

    hits = []
    for i, (pa, ga) in enumerate(owned):
        for pb, gb in owned[i + 1:]:
            for a in ga:
                for b in gb:
                    if overlaps(a, b):
                        hits.append((pa, a, pb, b))
    if not hits:
        print("seam_check: {} briefs, disjoint".format(len(owned)))
        return 0
    print("seam_check: OVERLAP")
    for pa, a, pb, b in hits:
        print("  {} {}  overlaps  {} {}".format(pa, a, pb, b))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print("seam_check internal error: {}".format(exc), file=sys.stderr)
        sys.exit(0)
