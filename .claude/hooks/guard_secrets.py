#!/usr/bin/env python3
"""Secret-scanning enforcement for claude-company.

Two modes in one file, Python 3.8 stdlib only, fail OPEN on internal error.

Mode 1 - PreToolUse (Bash) hook (default, reads JSON on stdin):
  When a Bash command contains a `git commit`, scan the ADDED lines of the
  staged diff (`git diff --cached -U0`) for high-signal secret patterns. On
  the first hit, BLOCK (exit 2) with a file:line locator, the pattern name,
  and a 3-step remediation recipe. No commit segment, nothing staged, or no
  hit -> allow (exit 0).

Mode 2 - `--scan-branch <base>` CLI (wave 2 reuses this):
  Scan the added lines of `git diff -U0 <base>...HEAD`, print a human table of
  hits and exactly one machine line last:
    SECRETS_JSON: {"hits": [{"file":..,"line":..,"pattern":..}, ...], "scanned": N}
  This JSON shape is FROZEN for wave 2. Exit 1 if any hit, else 0. On internal
  error, print a diagnostic to stderr and exit 0 (fail open).

DEVIATION - hotfix does NOT bypass this hook (unlike the other guards). A
leaking secret is worse than a blocked hotfix, so this hook never reads
active-task.json and never honors hotfix mode. This is deliberate.

Fails open on any internal error, consistent with the repo philosophy: a
scanner bug must never brick a session.
"""

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_secrets"

# Hunk header for a -U0 unified diff: capture the new-file start line.
# `+N,M` may appear as just `+N` (M defaults to 1).
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

SKIP_SUFFIXES = (".example", ".sample", ".template")
SKIP_SEGMENTS = {"tests", "fixtures"}
SKIP_MARKER = "secret-ok:"

# Ordered specific-first. anthropic_key MUST precede openai_key so a
# `sk-ant-...` value reports as anthropic. Only generic_secret is IGNORECASE;
# every other pattern is case-sensitive.
PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token",
     re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9-]{20,}")),
    # OQ-W1-02: the {20,} length floor is the false-positive guard; the
    # fixtures/ and secret-ok: escape hatches cover the rest.
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private_key",
     re.compile(r"-----BEGIN( RSA| EC| OPENSSH| PGP)? PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ")),
    ("generic_secret",
     re.compile(
         r"(api[_-]?key|secret|token|passw(or)?d)\s*[:=]\s*"
         r"['\"][A-Za-z0-9_/+=-]{16,}",
         re.IGNORECASE,
     )),
]


# --- command parsing (copied idiom from guard_commit.py) ------------------
def segments(command):
    parts = re.split(r"&&|\|\||;|\|", command)
    return [p.strip() for p in parts if p.strip()]


def git_subcmd(segment):
    """Return (subcommand, args) for a `git ...` segment, else (None, [])."""
    try:
        toks = shlex.split(segment)
    except Exception:
        toks = segment.split()
    if not toks or toks[0] != "git":
        return None, []
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 1
    if i >= len(toks):
        return None, []
    return toks[i], toks[i + 1:]


def has_commit(command):
    for seg in segments(command):
        sub, _ = git_subcmd(seg)
        if sub == "commit":
            return True
    return False


# --- diff parsing + scanning (shared by both modes) -----------------------
def added_lines(diff_text):
    """Yield (file, line_no, text) for each ADDED line in a -U0 unified diff.

    A `+++ b/<path>` header sets the current file (strip `b/`; `/dev/null`
    clears it). A `@@ -a,b +c,d @@` hunk header sets the new-file counter to
    c. Each subsequent `+` line (not `+++`) is an added line at the counter,
    which then advances. `-` and ` ` lines do not advance the new-file
    counter.
    """
    current_file = None
    counter = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            if path == "/dev/null":
                current_file = None
            elif path.startswith("b/"):
                current_file = path[2:]
            else:
                current_file = path
            continue
        if raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m:
                counter = int(m.group(1))
            continue
        if raw.startswith("+++"):
            continue
        if raw.startswith("+"):
            yield current_file, counter, raw[1:]
            counter += 1


def skip_line(file_path, text):
    """True when an added line must not be matched (per the skip rules)."""
    if not file_path:
        return True
    if file_path.endswith(SKIP_SUFFIXES):
        return True
    if SKIP_SEGMENTS.intersection(file_path.split("/")):
        return True
    if SKIP_MARKER in text:
        return True
    return False


def match_pattern(text):
    """Return the first matching pattern's name, or None."""
    for name, rx in PATTERNS:
        if rx.search(text):
            return name
    return None


def scan_diff(diff_text):
    """Return (hits, scanned).

    hits: list of {"file":.., "line":.., "pattern":..} in diff order.
    scanned: count of added lines actually pattern-matched (post-skip).
    (OQ-W1 assumption: skipped lines are not counted as scanned.)
    """
    hits = []
    scanned = 0
    for file_path, line_no, text in added_lines(diff_text or ""):
        if skip_line(file_path, text):
            continue
        scanned += 1
        name = match_pattern(text)
        if name is not None:
            hits.append({"file": file_path, "line": line_no,
                         "pattern": name})
    return hits, scanned


# --- mode 1: PreToolUse Bash hook -----------------------------------------
def block_message(hit):
    return (
        "BLOCKED: guard_secrets found a likely {pattern} at {file}:{line} in "
        "your staged diff.\n"
        "A secret must never be committed. To fix:\n"
        "  1. Unstage the file:   git restore --staged {file}\n"
        "  2. Move the value to an environment variable / secret store "
        "(never a tracked file).\n"
        "  3. Commit a placeholder or a .example file instead.\n"
        "If this is a false positive, add the literal `secret-ok:` to the "
        "line, or move the value under a tests/ or fixtures/ path or a "
        ".example/.sample/.template file.".format(
            pattern=hit["pattern"], file=hit["file"], line=hit["line"])
    )


def run_hook():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    root = c.project_root(payload)
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        sys.exit(0)

    try:
        if not has_commit(command):
            sys.exit(0)
        # c._git applies a 5s timeout and returns None on failure/nonzero.
        diff = c._git(root, ["diff", "--cached", "-U0"])
        if not diff:
            sys.exit(0)
        hits, _ = scan_diff(diff)
        if not hits:
            sys.exit(0)
        hit = hits[0]
        # c.block logs the BLOCK line and exits 2.
        c.block(root, HOOK, "{}:{}".format(hit["file"], hit["line"]),
                hit["pattern"], block_message(hit))
    except SystemExit:
        raise
    except Exception:
        # Fail open: a scanner bug must never brick a commit.
        sys.exit(0)

    sys.exit(0)


# --- mode 2: --scan-branch CLI --------------------------------------------
def print_table(hits):
    if not hits:
        print("no secrets found")
        return
    rows = [("FILE", "LINE", "PATTERN")]
    for h in hits:
        rows.append((str(h["file"]), str(h["line"]), str(h["pattern"])))
    wf = max(len(r[0]) for r in rows)
    wl = max(len(r[1]) for r in rows)
    for f, ln, pat in rows:
        print("{}  {}  {}".format(f.ljust(wf), ln.ljust(wl), pat))


def scan_branch(base):
    root = c.project_root(None)
    diff = c._git(root, ["diff", "-U0", base + "...HEAD"])
    if diff is None:
        diff = ""
    hits, scanned = scan_diff(diff)
    print_table(hits)
    # FROZEN wave-2 contract: exactly one machine line, LAST, sorted keys.
    print("SECRETS_JSON: " + json.dumps(
        {"hits": hits, "scanned": scanned}, sort_keys=True))
    sys.exit(1 if hits else 0)


def main():
    if "--scan-branch" in sys.argv:
        try:
            idx = sys.argv.index("--scan-branch")
            base = sys.argv[idx + 1]
        except IndexError:
            print("guard_secrets: --scan-branch requires a <base> argument",
                  file=sys.stderr)
            sys.exit(0)  # fail open
        try:
            scan_branch(base)
        except SystemExit:
            raise
        except Exception as exc:
            # Fail open, consistent with the repo philosophy.
            print("guard_secrets --scan-branch error: {}".format(exc),
                  file=sys.stderr)
            sys.exit(0)
        return
    run_hook()


if __name__ == "__main__":
    main()
