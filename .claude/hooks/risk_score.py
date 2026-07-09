#!/usr/bin/env python3
"""risk_score.py (#19) - advisory diff-risk scorer. ALWAYS exits 0.

CLI (not a hook):
  python3 .claude/hooks/risk_score.py [--base <ref>] [--brief <path>] [--json]

Scores the diff `base...HEAD` across six signals, sums them into a band
(low/medium/high) and prints a human table plus exactly one machine line last:
  RISK_JSON: {"score": N, "band": "...", "signals": {...}, "recommendation": ...}

This is a USER-INSTALL advisory tool: it never blocks. Every internal error
fails OPEN (the offending signal scores 0 with a note) and the process ALWAYS
exits 0 - even on a missing brief, a broken base ref, or no git at all.

Python 3.8 stdlib only.

Signal points (summed):
  size 0-15, out_of_ownership 10/path, frozen_proximity 15 direct / 5 sibling,
  test_ratio 0-15, sensitive_paths flat 10, secrets 25.
Bands: score < 25 low; 25-49 medium; >= 50 high.
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "risk_score"


# --- root / git helpers ---------------------------------------------------
def resolve_root():
    """CLAUDE_PROJECT_DIR else cwd (these CLIs carry no stdin payload)."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def default_base(root):
    """merge-base of main and HEAD, or None when there is no main / no git."""
    out = c._git(root, ["merge-base", "main", "HEAD"])
    if out is None:
        return None
    out = out.strip()
    return out or None


def numstat(root, base):
    """Rows of (added, deleted, path) for `git diff --numstat base...HEAD`.

    OQ-W2-01 assumption: binary files render added/deleted as "-"; count them
    as 0 changed lines.
    """
    out = c._git(root, ["diff", "--numstat", base + "...HEAD"])
    if not out:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        added = int(a) if a.isdigit() else 0
        deleted = int(d) if d.isdigit() else 0
        rows.append((added, deleted, path))
    return rows


def changed_paths(root, base):
    out = c._git(root, ["diff", "--name-only", base + "...HEAD"])
    if not out:
        return []
    return [p for p in out.splitlines() if p.strip()]


# --- classification -------------------------------------------------------
def is_test_path(path):
    """test = under a tests/ dir, or basename test_* / *_test.* / *.test.* /
    *.spec.* (same rule the trace checker uses)."""
    if "tests" in path.split("/"):
        return True
    base = os.path.basename(path)
    if base.startswith("test_"):
        return True
    for pat in ("*_test.*", "*.test.*", "*.spec.*"):
        if fnmatch.fnmatch(base, pat):
            return True
    return False


def is_sensitive(path):
    if "migrations" in path.split("/"):
        return True
    if path.startswith(".claude/hooks/"):
        return True
    if path == "company/gates.config":
        return True
    if path == ".claude/settings.json":
        return True
    return False


# --- ownership parse (OQ-W2-02) -------------------------------------------
def parse_owned(brief_text):
    """Collect backticked tokens from list items under the '## You own'
    heading, up to the next '## ' heading."""
    owned = []
    in_section = False
    for line in brief_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            if stripped[3:].strip().lower().startswith("you own"):
                in_section = True
            continue
        if in_section and (stripped.startswith("-") or stripped.startswith("*")):
            token = ""
            in_tick = False
            for ch in line:
                if ch == "`":
                    if in_tick and token.strip():
                        owned.append(token.strip())
                    token = ""
                    in_tick = not in_tick
                elif in_tick:
                    token += ch
    return owned


def is_owned(path, owned):
    """OQ-W2-02 assumption: a trailing-slash token is a directory PREFIX match
    (path == token-without-slash, or path startswith token). A bare token
    matches an exact path, or a prefix at a '/' boundary (token + '/')."""
    for entry in owned:
        if entry.endswith("/"):
            if path == entry[:-1] or path.startswith(entry):
                return True
        else:
            if path == entry or path.startswith(entry + "/"):
                return True
    return False


# --- frozen proximity -----------------------------------------------------
def load_frozen_patterns(root):
    """surfaces[].pattern globs plus the 'always' globs from
    company/frozen-surfaces.json. Missing/malformed file -> no patterns."""
    cfg = c.read_json_file(
        os.path.join(root, "company", "frozen-surfaces.json")
    )
    patterns = []
    if isinstance(cfg, dict):
        for s in cfg.get("surfaces") or []:
            if isinstance(s, dict) and s.get("pattern"):
                patterns.append(s["pattern"])
        for pat in cfg.get("always") or []:
            if isinstance(pat, str):
                patterns.append(pat)
    return patterns


def frozen_direct(path, patterns):
    """Match like guard_frozen: fnmatch against the rel path AND the basename."""
    base = os.path.basename(path)
    for pat in patterns:
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat):
            return True
    return False


def frozen_sibling_dirs(root, patterns):
    """OQ-W2-04: dirnames of every HEAD-tracked file that matches a frozen
    pattern; a changed path in one of these dirs is a 'sibling'."""
    out = c._git(root, ["ls-files"])
    dirs = set()
    if not out:
        return dirs
    for f in out.splitlines():
        if f.strip() and frozen_direct(f, patterns):
            dirs.add(os.path.dirname(f))
    return dirs


# --- secrets (shell out to guard_secrets) ---------------------------------
def run_secret_scan(base):
    """Run guard_secrets.py --scan-branch <base> (a sibling hook) and parse the
    FROZEN last SECRETS_JSON line. Returns hit count, or None on any error."""
    scanner = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "guard_secrets.py"
    )
    try:
        result = subprocess.run(
            [sys.executable, scanner, "--scan-branch", base],
            capture_output=True, text=True, timeout=30, env=os.environ.copy(),
        )
    except Exception:
        return None
    lines = [
        ln for ln in result.stdout.splitlines()
        if ln.startswith("SECRETS_JSON: ")
    ]
    if not lines:
        return None
    try:
        data = json.loads(lines[-1][len("SECRETS_JSON: "):])
    except Exception:
        return None
    hits = data.get("hits")
    return len(hits) if isinstance(hits, list) else None


# --- brief loading --------------------------------------------------------
def load_brief(root, brief_arg):
    """Return (text, note). text is None (with a note) when there is no brief."""
    path = brief_arg
    if not path:
        task = c.active_task(root)
        if isinstance(task, dict):
            path = task.get("brief")
    if not path:
        return None, "no brief (no --brief, no active-task brief field)"
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    if not os.path.exists(path):
        return None, "brief not found: {}".format(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except Exception:
        return None, "brief unreadable: {}".format(path)


# --- scoring --------------------------------------------------------------
def score_size(rows):
    # Monotonic mapping: <200 -> 0 ; 200-799 -> 8 ; >=800 -> 15.
    total = sum(a + d for a, d, _ in rows)
    if total >= 800:
        pts = 15
    elif total >= 200:
        pts = 8
    else:
        pts = 0
    return pts, "{} changed line(s)".format(total)


def score_test_ratio(rows):
    """Source vs test changed lines. Mapping (monotonic in test thinness):
      source <= 400 -> 0 (change too small to demand tests)
      else: ratio = test/source
        ratio >= 0.10 -> 0 (healthy)
        0.05 <= ratio < 0.10 -> 8 (thin)
        ratio < 0.05 -> 15 (large change, essentially untested)."""
    source = sum(a + d for a, d, p in rows if not is_test_path(p))
    test = sum(a + d for a, d, p in rows if is_test_path(p))
    if source <= 400:
        return 0, "src={} test={} (below 400-line floor)".format(source, test)
    ratio = test / source
    if ratio >= 0.10:
        pts = 0
    elif ratio >= 0.05:
        pts = 8
    else:
        pts = 15
    return pts, "src={} test={} ratio={:.2f}".format(source, test, ratio)


def score_frozen(paths, root, patterns):
    if not patterns:
        return 0, "no frozen surfaces declared"
    sibling_dirs = frozen_sibling_dirs(root, patterns)
    pts = 0
    direct = 0
    sibling = 0
    for p in paths:
        if frozen_direct(p, patterns):
            pts += 15
            direct += 1
        elif os.path.dirname(p) in sibling_dirs:
            pts += 5
            sibling += 1
    return pts, "{} direct, {} sibling".format(direct, sibling)


def score_sensitive(paths):
    present = [p for p in paths if is_sensitive(p)]
    if present:
        return 10, "sensitive path(s): {}".format(", ".join(present[:3]))
    return 0, "none"


def band_of(score):
    if score >= 50:
        return "high", "auditor dispatch mandatory"  # OQ-W2-05
    if score >= 25:
        return "medium", "extra spot-reads"
    return "low", "standard verification"


# --- main -----------------------------------------------------------------
def build_report(root, base, brief_arg):
    """Return (signals, notes, base_note). Never raises for git/brief issues."""
    signals = {}
    notes = {}
    base_note = None

    if base is None:
        base_note = "no base (no main / no git) - diff signals skipped"
        rows = []
        paths = []
    else:
        rows = numstat(root, base)
        paths = changed_paths(root, base)

    # 1. size
    signals["size"], notes["size"] = score_size(rows)

    # 2. out-of-ownership
    brief_text, brief_note = load_brief(root, brief_arg)
    if brief_text is None:
        owned = None
        notes["out_of_ownership"] = "skipped - " + brief_note
    else:
        owned = parse_owned(brief_text)
        if not owned:
            owned = None
            notes["out_of_ownership"] = (
                "skipped - no '## You own' section in brief"
            )
    if owned is None:
        signals["out_of_ownership"] = 0
    else:
        offenders = [p for p in paths if not is_owned(p, owned)]
        signals["out_of_ownership"] = 10 * len(offenders)
        notes["out_of_ownership"] = "{} path(s) outside owned dirs".format(
            len(offenders)
        )

    # 3. frozen proximity
    patterns = load_frozen_patterns(root)
    signals["frozen_proximity"], notes["frozen_proximity"] = score_frozen(
        paths, root, patterns
    )

    # 4. test ratio
    signals["test_ratio"], notes["test_ratio"] = score_test_ratio(rows)

    # 5. sensitive paths
    signals["sensitive_paths"], notes["sensitive_paths"] = score_sensitive(
        paths
    )

    # 6. secrets
    if base is None:
        signals["secrets"] = 0
        notes["secrets"] = "skipped - no base ref"
    else:
        count = run_secret_scan(base)
        if count is None:
            signals["secrets"] = 0
            notes["secrets"] = "fail-open - guard_secrets scan unavailable"
        elif count > 0:
            signals["secrets"] = 25
            notes["secrets"] = "{} secret hit(s)".format(count)
        else:
            signals["secrets"] = 0
            notes["secrets"] = "no secrets"

    return signals, notes, base_note


SIGNAL_ORDER = [
    "size", "out_of_ownership", "frozen_proximity",
    "test_ratio", "sensitive_paths", "secrets",
]


def print_table(signals, notes, base_note, score, band, rec):
    if base_note:
        print(base_note)
        print("")
    header = "{:<18} {:>6}  {}".format("SIGNAL", "POINTS", "NOTE")
    print(header)
    print("-" * len(header))
    for name in SIGNAL_ORDER:
        print("{:<18} {:>6}  {}".format(
            name, signals.get(name, 0), notes.get(name, "")))
    print("-" * len(header))
    print("{:<18} {:>6}".format("TOTAL", score))
    print("")
    print("band: {}  ->  {}".format(band, rec))
    print("")


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--base")
    parser.add_argument("--brief")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])

    root = resolve_root()
    try:
        base = args.base if args.base else default_base(root)
        signals, notes, base_note = build_report(root, base, args.brief)
        score = sum(signals.values())
        band, rec = band_of(score)
    except Exception as exc:
        # Absolute fail-open: emit a minimal well-formed line and exit 0.
        print("risk_score internal error: {}".format(exc), file=sys.stderr)
        score, band, rec = 0, "low", "standard verification"
        signals = {name: 0 for name in SIGNAL_ORDER}
        print("RISK_JSON: " + json.dumps(
            {"score": score, "band": band, "signals": signals,
             "recommendation": rec}, sort_keys=True))
        return 0

    if not args.json:
        print_table(signals, notes, base_note, score, band, rec)

    print("RISK_JSON: " + json.dumps(
        {"score": score, "band": band, "signals": signals,
         "recommendation": rec}, sort_keys=True))

    c.adherence_log(root, HOOK, "INFO", band, "score={}".format(score))
    return 0


if __name__ == "__main__":
    # ALWAYS exit 0 (advisory tool).
    try:
        main(sys.argv)
    except SystemExit as se:
        # argparse may raise SystemExit(2) on bad args; normalise to 0.
        if se.code not in (0, None):
            sys.exit(0)
        raise
    except Exception as exc:
        print("risk_score fatal: {}".format(exc), file=sys.stderr)
    sys.exit(0)
