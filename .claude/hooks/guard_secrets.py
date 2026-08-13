#!/usr/bin/env python3
"""Secret-scanning enforcement for claude-company.

Two modes in one file, Python 3.8 stdlib only, fail OPEN on internal error.

Mode 1 - PreToolUse (Bash) hook (default, reads JSON on stdin):
  For each `git commit` segment in a Bash command, scan the ADDED lines of
  THAT SEGMENT'S ACTING TREE staged diff (`git diff --cached -U0`, run in the
  tree the commit writes to) for high-signal secret patterns. On the first
  hit, BLOCK (exit 2) with a file:line locator, the pattern name, and a 3-step
  remediation recipe. No commit segment, nothing staged, or no hit -> allow
  (exit 0).

  The acting tree is resolved by `_common.seg_git_dir`, per segment, exactly
  as guard_commit resolves the branch. Reading the diff from the project root
  instead is what made this hook inert for every delegated commit; see the
  comment in run_hook.

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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402
import guard_commit  # noqa: E402

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


# --- command parsing (shared, never copied) -------------------------------
# FR-HP-12: the subcommand parser lives in _common and is reached through
# guard_commit, which is looked up as a module attribute at call time. A
# byte-identical copy here is what let `git -C sub commit` escape this scan
# after guard_commit was fixed - one parser, one behavior.
segments = c.segments


def commit_segments(command):
    """Every segment of `command` that is a `git commit`, in order.

    The tree resolution below is per SEGMENT, so this returns the segments
    themselves rather than a bare boolean: two commits in one compound command
    can target two different working trees, and a clean one must not launder a
    dirty one.
    """
    found = []
    for seg in segments(command):
        sub, _ = guard_commit.git_subcmd(seg)
        if sub == "commit":
            found.append(seg)
    return found


def has_commit(command):
    """True when any segment of `command` is a `git commit`."""
    return bool(commit_segments(command))


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
def block_message(hit, tree=None, root=None):
    """The block text. `tree` is the acting tree whose index was scanned.

    The unstage step carries an explicit `-C <tree>` whenever the acting tree
    is not the project root, because a recipe run from the reader's own cwd
    would unstage a file in the wrong checkout - or, more often, nothing at
    all - and leave the secret exactly where it was.
    """
    unstage = "git restore --staged {}".format(hit["file"])
    where = ""
    if tree and root and os.path.abspath(tree) != os.path.abspath(root):
        unstage = "git -C {} restore --staged {}".format(tree, hit["file"])
        where = "\nThe secret is staged in {}, not in the project root.".format(
            tree
        )
    return (
        "BLOCKED: guard_secrets found a likely {pattern} at {file}:{line} in "
        "your staged diff.{where}\n"
        "A secret must never be committed. To fix:\n"
        "  1. Unstage the file:   {unstage}\n"
        "  2. Move the value to an environment variable / secret store "
        "(never a tracked file).\n"
        "  3. Commit a placeholder or a .example file instead.\n"
        "If this is a false positive, add the literal `secret-ok:` to the "
        "line, or move the value under a tests/ or fixtures/ path or a "
        ".example/.sample/.template file.".format(
            pattern=hit["pattern"], file=hit["file"], line=hit["line"],
            unstage=unstage, where=where)
    )


def unscannable_message(tree):
    return (
        "BLOCKED: guard_secrets could not read the staged index in {tree} - "
        "git did not answer within {slow}s, so the commit could not be "
        "scanned for secrets.\n"
        "This is almost always CPU contention (a parallel gate ladder), not a "
        "broken repository. To fix:\n"
        "  1. Retry the commit - a second attempt normally answers "
        "immediately.\n"
        "  2. If it keeps timing out, check the tree is healthy:   "
        "git -C {tree} status\n"
        "This guard blocks rather than allows here on purpose: an unscanned "
        "commit is how a credential ships, and 'could not look' must never "
        "read as 'nothing to see'.".format(tree=tree, slow=c.GIT_SLOW_TIMEOUT)
    )


def scan_commit_segments(payload, root, command):
    """Scan each commit segment's ACTING TREE. Exits 2 on the first hit.

    The staged diff must be read from the tree the commit actually writes to,
    resolved per segment the way guard_commit resolves the branch. This hook
    adopted guard_commit's PARSER under FR-HP-12 and did NOT adopt its TREE
    RESOLUTION: it kept reading `git diff --cached` from CLAUDE_PROJECT_DIR,
    which the harness pins to the main checkout, while every delegated commit
    happens in a worktree. Main's index is almost always empty, so the scan
    found nothing and returned before scanning anything - and an inert scanner
    over a clean repo looks exactly like a working one. Zero guard_secrets
    lines in 324 adherence-log entries over five weeks was the only symptom.
    Every delegated commit in this repo's history went unscanned for secrets.

    Separated from the stdin plumbing so the decision path is reachable from a
    test without a subprocess - the git-silence branch below cannot be driven
    any other way.
    """
    for seg in commit_segments(command):
        tree = c.seg_git_dir(seg, payload, root)
        status, diff = c.git_result(tree, ["diff", "--cached", "-U0"])
        if status == c.GIT_SILENT:
            # Git did not answer. "I could not look" must never read as
            # "nothing to see" - that exact collapse is what made this
            # hook inert for five weeks. Give it a longer window first,
            # since the usual cause is CPU contention from a sibling
            # lane's ladder, not a broken repo.
            status, diff = c.git_result(
                tree, ["diff", "--cached", "-U0"],
                timeout=c.GIT_SLOW_TIMEOUT,
            )
        if status == c.GIT_SILENT:
            # DELIBERATE INVERSION of this file's fail-open posture, and
            # the only block in it that is not a found secret. This guard
            # already refuses to yield to hotfix mode because a leaked
            # credential is the worst outcome in the system; an unreadable
            # index is the one state where allowing the commit means
            # shipping unscanned. The block costs a retry and says so.
            c.block(
                root, HOOK, tree, "index unreadable",
                unscannable_message(tree),
            )
        if status != c.GIT_ANSWERED or not diff:
            continue
        hits, _ = scan_diff(diff)
        if not hits:
            continue
        hit = hits[0]
        # The BLOCK line stays in the PROJECT's adherence log, not the
        # acting tree's: one audit trail per project is what makes "zero
        # guard_secrets lines in 324 entries" a readable signal at all.
        c.block(root, HOOK, "{}:{}".format(hit["file"], hit["line"]),
                hit["pattern"], block_message(hit, tree, root))


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
        scan_commit_segments(payload, root, command)
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
    # The acting tree again, in CLI form. `<base>...HEAD` is meaningless
    # except against the tree whose HEAD is meant, and HEAD is per-worktree:
    # resolving from CLAUDE_PROJECT_DIR would scan the main checkout's branch
    # for someone standing in a worktree, silently reporting on code they are
    # not shipping.
    #
    # The redirect is deliberately narrow - ANOTHER CHECKOUT OF THIS SAME
    # REPOSITORY, never just any git work tree. run-gates.sh draws exactly
    # this line for itself (a cwd that merely happens to sit inside some other
    # repository must not redirect the run), and the wide version of this
    # change hijacked a fixture's scan to whatever repo the test runner was
    # standing in.
    root = c.project_root(None)
    try:
        cwd = os.getcwd()
        # `is True` only: a redirect acts on an affirmative answer, so git
        # silence leaves the scan where it already was rather than moving it
        # somewhere on a guess.
        if c.same_repository(cwd, root) is True:
            root = cwd
    except Exception:
        pass
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
