#!/usr/bin/env python3
"""Provenance manifest helper for claude-company.

This is the shared hashing / read-write CLI behind the install-manifest and
the future `update` command. The one hard contract here is DETERMINISM: the
manifest emitted by `build` must be byte-identical across two installs of the
same source. To guarantee that, we never write a timestamp or any
environment-varying field, and we serialise with exactly:

    json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\\n"

Anything that breaks byte-for-byte reproducibility breaks `update`'s ability
to prove a file pristine, so keep this module free of clocks, hostnames, and
dict-ordering assumptions.

Python 3.8 stdlib only - no third-party dependencies.
"""

import hashlib
import json
import sys


def _sha256_of_file(path):
    """Return the sha256 hex digest of a file's bytes, or None if unreadable."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _dump(obj):
    """The one canonical serialisation. See the determinism contract above."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load_json(path):
    """Load JSON from a path, or return None on any read / parse failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cmd_hash(argv):
    # hash FILE -> print sha256 hex + newline; exit 1 if unreadable.
    if len(argv) != 1:
        return _usage()
    digest = _sha256_of_file(argv[0])
    if digest is None:
        return 1
    sys.stdout.write(digest + "\n")
    return 0


def cmd_build(argv):
    # build --version V --root DIR ; relpaths come from STDIN, newline-delimited.
    version = None
    root = None
    i = 0
    while i < len(argv):
        if argv[i] == "--version" and i + 1 < len(argv):
            version = argv[i + 1]
            i += 2
        elif argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        else:
            return _usage()
    if version is None or root is None:
        return _usage()

    files = {}
    for line in sys.stdin:
        rel = line.rstrip("\n")
        if rel == "":
            continue
        digest = _sha256_of_file(_join(root, rel))
        if digest is None:
            sys.stderr.write("warning: skipped unreadable path: " + rel + "\n")
            continue
        files[rel] = digest

    obj = {"version": version, "files": files}
    sys.stdout.write(_dump(obj))
    return 0


def cmd_version(argv):
    # version FILE -> print the manifest's "version"; silent on any failure.
    if len(argv) != 1:
        return _usage()
    obj = _load_json(argv[0])
    if isinstance(obj, dict) and "version" in obj:
        sys.stdout.write(str(obj["version"]) + "\n")
    return 0


def cmd_get(argv):
    # get FILE RELPATH -> print the sha for RELPATH from the files map.
    if len(argv) != 2:
        return _usage()
    obj = _load_json(argv[0])
    if isinstance(obj, dict):
        files = obj.get("files")
        if isinstance(files, dict):
            sha = files.get(argv[1])
            if isinstance(sha, str):
                sys.stdout.write(sha + "\n")
    return 0


def cmd_vercmp(argv):
    # vercmp A B -> -1 / 0 / 1 by dotted-version comparison.
    if len(argv) != 2:
        return _usage()
    result = _vercmp(argv[0], argv[1])
    sys.stdout.write(str(result) + "\n")
    return 0


def cmd_pkgversion(argv):
    # pkgversion FILE -> print a package.json's "version"; silent on failure.
    if len(argv) != 1:
        return _usage()
    obj = _load_json(argv[0])
    if isinstance(obj, dict) and "version" in obj:
        sys.stdout.write(str(obj["version"]) + "\n")
    return 0


def _vercmp(a, b):
    """Compare two dotted version strings field by field.

    Numeric where both fields are ints, else lexical; missing fields count as
    0. Returns -1, 0, or 1.
    """
    fields_a = a.split(".")
    fields_b = b.split(".")
    n = max(len(fields_a), len(fields_b))
    for i in range(n):
        fa = fields_a[i] if i < len(fields_a) else "0"
        fb = fields_b[i] if i < len(fields_b) else "0"
        if _is_int(fa) and _is_int(fb):
            va, vb = int(fa), int(fb)
        else:
            va, vb = fa, fb
        if va < vb:
            return -1
        if va > vb:
            return 1
    return 0


def _is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def _join(root, rel):
    """Join root and a relpath with a single separator, os-agnostically."""
    if root.endswith("/"):
        return root + rel
    return root + "/" + rel


def _usage():
    sys.stderr.write(
        "usage: manifest.py "
        "{hash FILE | build --version V --root DIR | version FILE | "
        "get FILE RELPATH | vercmp A B | pkgversion FILE}\n"
    )
    return 2


_COMMANDS = {
    "hash": cmd_hash,
    "build": cmd_build,
    "version": cmd_version,
    "get": cmd_get,
    "vercmp": cmd_vercmp,
    "pkgversion": cmd_pkgversion,
}


def main(argv):
    if len(argv) < 1:
        return _usage()
    handler = _COMMANDS.get(argv[0])
    if handler is None:
        return _usage()
    return handler(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
