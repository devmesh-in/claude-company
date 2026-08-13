#!/usr/bin/env python3
"""risk_score.py (#19) - advisory diff-risk scorer. ALWAYS exits 0.

CLI (not a hook):
  python3 .claude/hooks/risk_score.py [--base <ref>] [--brief <path>] [--json]

Scores a change across six signals, sums them into a band (low/medium/high)
and prints a human table plus exactly one machine line last:
  RISK_JSON: {"score": N, "band": "...", "signals": {...}, "recommendation": ...}

WHAT GETS SCORED - the subject
  "How risky is this change" means the tree as it stands, not whatever
  happens to be in git yet. Two subjects exist:
    committed     the diff `base...HEAD` - what is committed
    working tree  the same fork point against the files on disk - tracked
                  edits, staged or not, plus untracked files
  A default run (no --base) scores BOTH and the HIGHER total is the answer.
  Higher rather than a merged diff: a working tree that reverts committed
  work produces a smaller diff, and unfinished undo must not lower the bar
  for what is already in the branch.
  An explicit `--base <ref>` is the committed-only comparison and prints
  byte-for-byte what this tool printed before working-tree scoring existed.

This is a USER-INSTALL advisory tool: it never blocks. Every internal error
fails OPEN (the offending signal scores 0 with a note) and the process ALWAYS
exits 0 - even on a missing brief, a broken base ref, or no git at all.

Python 3.8 stdlib only.

Signal points (summed):
  size 0-15, out_of_ownership 10/path, frozen_proximity 15 direct / 5 sibling,
  test_ratio 0-15, sensitive_paths 10 + 0/8/15 PER sensitive path, secrets 25.
Bands: score < 25 low; 25-49 medium; >= 50 high.

The band cuts and the per-signal points are the calibration this tool was
accepted with. Change WHAT IS MEASURED, never the arithmetic - with ONE
recorded exception, #122 (task risk-scale). `sensitive_paths` used to award a
flat 10 for any number of sensitive paths at any size, so a 717-line rewrite
of the hook that decides whether anything gets audited scored exactly what a
one-line comment fix in a canon file scored. It now scales with blast radius;
the derivation and the reason no new number was invented are in
`score_sensitive` below. Band cuts 25/50 are untouched, and no other signal
changed.
"""

import argparse
import collections
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


def parse_numstat(out):
    """Rows of (added, deleted, path) from `git diff --numstat` output.

    OQ-W2-01 assumption: binary files render added/deleted as "-"; count them
    as 0 changed lines.
    """
    rows = []
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        added = int(a) if a.isdigit() else 0
        deleted = int(d) if d.isdigit() else 0
        rows.append((added, deleted, path))
    return rows


def parse_names(out):
    return [p for p in (out or "").splitlines() if p.strip()]


def numstat(root, base):
    """Rows for `git diff --numstat base...HEAD` (the committed subject)."""
    return parse_numstat(c._git(root, ["diff", "--numstat", base + "...HEAD"]))


def changed_paths(root, base):
    return parse_names(c._git(root, ["diff", "--name-only", base + "...HEAD"]))


# --- subjects: WHAT gets scored -------------------------------------------
# A subject is a set of changed lines and paths plus the way its secrets are
# counted. `secret_hits` is a callable so the scan only runs for the subject
# that is actually reported on.
Subject = collections.namedtuple("Subject", "name rows paths secret_hits")

EMPTY_SUBJECT = Subject("committed", [], [], lambda: None)


def fork_point(root, base):
    """What `base...HEAD` really diffs against: merge-base(base, HEAD).

    The working-tree subject measures from the SAME point, so the two answers
    are comparable line for line. Falls back to `base` on any git doubt.
    """
    out = c._git(root, ["merge-base", base, "HEAD"])
    if out is None:
        return base
    return out.strip() or base


def untracked_entries(root):
    """[(path, [line, ...])] for every untracked, non-ignored file.

    Untracked files are the ones `git diff` cannot see at all, and the first
    change on a branch is usually made of them - the case this scorer used to
    read as an empty diff. OQ-RWT-01 assumption: a file holding a NUL byte is
    binary and counts as 0 lines, matching the numstat binary rule above.
    """
    entries = []
    for path in parse_names(
            c._git(root, ["ls-files", "--others", "--exclude-standard"])):
        try:
            with open(os.path.join(root, path), "rb") as f:
                data = f.read()
        except Exception:
            continue  # unreadable file: fail open, score nothing for it
        if b"\x00" in data:
            entries.append((path, []))
        else:
            text = data.decode("utf-8", "replace")
            entries.append((path, text.splitlines()))
    return entries


def collect_committed(root, base):
    """Today's subject: what is in git."""
    return Subject(
        "committed", numstat(root, base), changed_paths(root, base),
        lambda: run_secret_scan(base),
    )


def collect_worktree(root, base):
    """The tree as it stands: tracked edits (staged or not) plus untracked
    files, measured from the committed subject's fork point."""
    fork = fork_point(root, base)
    rows = parse_numstat(c._git(root, ["diff", "--numstat", fork]))
    paths = parse_names(c._git(root, ["diff", "--name-only", fork]))
    untracked = untracked_entries(root)
    rows.extend((len(lines), 0, path) for path, lines in untracked)
    paths.extend(path for path, _ in untracked)
    return Subject(
        "working tree", rows, paths,
        lambda: worktree_secret_hits(root, fork, untracked),
    )


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


def is_enforcement_path(path):
    """True when `path` is part of the machinery that JUDGES other changes.

    This is a RULE, not a list of interesting filenames, and it is written
    down here so nobody trims it back to one. A change to the machinery that
    decides whether other changes are audited, blocked or accepted has the
    largest blast radius in the repository by construction: if the judge is
    wrong, every judgment made after it is wrong - including the judgment on
    the change that broke the judge. So the set is everything that decides,
    configures, or states how a change gets judged:

      - the enforcement code itself           .claude/hooks/**
      - what wires it and what it runs        .claude/settings.json,
                                              company/gates.config
      - the registries it reads               company/*.json (frozen
                                              surfaces, witnesses, the
                                              provenance manifest)
      - the canon it enforces                 company/*.md, company/adr/*.md
                                              (settled decisions), CLAUDE.md

    Anything a future edit adds under those roots is covered without being
    named. Per-task paperwork (company/briefs/**, company/specs/**) and
    running state (company/state/**) are NOT here: they record judgments,
    they do not make them.
    """
    parts = path.split("/")
    if path.startswith(".claude/hooks/"):
        return True
    if path in (".claude/settings.json", "company/gates.config", "CLAUDE.md"):
        return True
    if len(parts) == 2 and parts[0] == "company" and (
            path.endswith(".md") or path.endswith(".json")):
        return True
    if len(parts) == 3 and parts[0] == "company" and parts[1] == "adr" \
            and path.endswith(".md"):
        return True
    return False


def is_sensitive(path):
    # Two different principles land in one signal. Irreversibility: a
    # migration cannot be taken back by a revert.
    if "migrations" in path.split("/"):
        return True
    # Blast radius: see is_enforcement_path.
    return is_enforcement_path(path)


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


def load_secret_scanner():
    """guard_secrets as a module, or None on any import trouble.

    Its --scan-branch CLI scans `base...HEAD` only and its JSON line is a
    frozen contract, so the working-tree subject reuses that hook's pure
    matching functions rather than a second copy of the patterns. Importing
    is the whole change; guard_secrets itself is untouched.
    """
    try:
        import guard_secrets
        return guard_secrets
    except Exception:
        return None


def worktree_secret_hits(root, fork, untracked):
    """Secret hits in the tree as it stands, or None (fail open).

    Tracked edits go through the scanner's own diff reader; an untracked file
    has no diff, so each of its lines is an added line by definition.
    """
    gs = load_secret_scanner()
    if gs is None:
        return None
    try:
        hits, _ = gs.scan_diff(c._git(root, ["diff", "-U0", fork]) or "")
        count = len(hits)
        for path, lines in untracked:
            for text in lines:
                if gs.skip_line(path, text):
                    continue
                if gs.match_pattern(text) is not None:
                    count += 1
        return count
    except Exception:
        return None


# --- brief loading --------------------------------------------------------
def load_brief(root, brief_arg):
    """Return (text, note). text is None (with a note) when there is no brief."""
    path = brief_arg
    if not path:
        tasks = c.active_tasks(root)
        # OQ-MST-06 assumption: with several entries in flight there is no
        # honest default brief. Scoring one entry's ownership section against
        # a diff that mixes every entry's work would invent a signal, which is
        # worse than none - so name the count and ask for --brief. This is
        # advisory: the ownership signal scores 0 and the exit code is
        # unchanged at every N.
        if len(tasks) > 1:
            return None, (
                "{} active task entries - pass --brief to score "
                "ownership".format(len(tasks))
            )
        if tasks:
            path = tasks[0].get("brief")
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
def amount_of_change_points(total_lines):
    """The tool's accepted amount-of-change ladder: how much is in play.

    Monotonic mapping: <200 -> 0 ; 200-799 -> 8 ; >=800 -> 15. This is the
    calibration `size` shipped with; it is named here rather than inlined
    because `score_sensitive` reuses it on a different subject (see there).
    """
    if total_lines >= 800:
        return 15
    if total_lines >= 200:
        return 8
    return 0


def score_size(rows):
    total = sum(a + d for a, d, _ in rows)
    return amount_of_change_points(total), "{} changed line(s)".format(total)


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


SENSITIVE_PRESENCE = 10
"""Points for one sensitive path being in play at all, at any size.

Not a new number: it is the flat 10 this signal was accepted with (#19), kept
as the FLOOR so the scale below can only add. That is what makes it a scale
and not an offset - a one-line comment fix in a canon file scores exactly what
it scored before.
"""


def score_sensitive(rows, paths):
    """Sensitivity scales with blast radius (#122, task risk-scale).

    THE PRINCIPLE. Blast radius is how much else is wrong if this change is
    wrong. A change to the machinery that judges other changes is the maximum
    because every later judgment inherits the error (see is_enforcement_path).
    The old flat 10 could not express that: it saturated on presence, so a
    wholesale rewrite of a hook and a typo fix in a canon file were equal.

    THE DERIVATION, in two terms, per sensitive path:

      presence   SENSITIVE_PRESENCE - a judge is in play at all.
      extent     amount_of_change_points(that path's own changed lines) -
                 how much OF that judge is in play. A one-line edit puts a
                 sliver of its behavior at risk; a 900-line edit is a rewrite,
                 so all of it is.

    Summed PER PATH, not over the pooled line count, because two judges break
    two independent sets of later judgments. 900 lines spread across a hook
    and an ADR is not "one judge 900 lines wrong", and pooling would say it
    was. Per-path accumulation is also this tool's accepted grain for distinct
    risky things touched - out_of_ownership charges 10 per path and
    frozen_proximity 15 per path, both unbounded, for the same reason.

    NO NEW NUMBER IS INTRODUCED HERE, and that is deliberate. This tool's
    calibration has been challenged before for resting on hand-picked
    thresholds; a table of per-kind weights (enforcement code 15, canon 10,
    data 5) would have been exactly that, and nothing derives the ratios
    between such tiers - in this repo the canon is READ by the enforcement
    code at run time (frozen-surfaces.json, gates.config, the provenance
    manifest), so an error in canon propagates through the same judgments an
    error in code does. Both terms above are numbers this tool already
    shipped with: the presence 10 of this signal, and the size ladder. What
    changed is which subject the ladder is applied to - the sensitive slice
    of the diff, one path at a time, instead of the whole diff.

    Consequence worth knowing: a change that is entirely inside enforcement
    code is scored by the ladder twice, once as `size` and once here. That is
    the intent, not an accident. `size` asks how much review the change needs;
    this asks how much of the judge is in play. They coincide only when the
    change IS the judge.
    """
    # Deduped: the presence term is charged once per distinct judge, so a
    # path listed twice by a subject cannot charge it twice.
    present = list(dict.fromkeys(p for p in paths if is_sensitive(p)))
    if not present:
        return 0, "none"
    churn = collections.defaultdict(int)
    for added, deleted, path in rows:
        churn[path] += added + deleted
    pts = 0
    shown = []
    for path in present:
        lines = churn.get(path, 0)
        pts += SENSITIVE_PRESENCE + amount_of_change_points(lines)
        if len(shown) < 3:
            shown.append("{} ({} line(s))".format(path, lines))
    note = "{} sensitive path(s): {}".format(len(present), ", ".join(shown))
    if len(present) > len(shown):
        note += ", +{} more".format(len(present) - len(shown))
    return pts, note


def band_of(score):
    if score >= 50:
        return "high", "auditor dispatch mandatory"  # OQ-W2-05
    if score >= 25:
        return "medium", "extra spot-reads"
    return "low", "standard verification"


# --- main -----------------------------------------------------------------
def build_report(root, base, brief_arg, subject):
    """Score one subject: return (signals, notes, base_note).

    Never raises for git/brief issues.
    """
    signals = {}
    notes = {}
    base_note = None

    if base is None:
        base_note = "no base (no main / no git) - diff signals skipped"
    rows = subject.rows
    paths = subject.paths

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
        rows, paths
    )

    # 6. secrets
    if base is None:
        signals["secrets"] = 0
        notes["secrets"] = "skipped - no base ref"
    else:
        count = subject.secret_hits()
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


def print_table(signals, notes, preamble, score, band, rec):
    for line in preamble:
        print(line)
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
        subject_note = None
        if base is None:
            subject = EMPTY_SUBJECT
        else:
            subject = collect_committed(root, base)
        signals, notes, base_note = build_report(root, base, args.brief,
                                                 subject)
        score = sum(signals.values())
        # An explicit --base is the committed-only comparison and stays
        # byte-identical; a default run also scores the tree as it stands and
        # lets the higher answer stand.
        if base is not None and not args.base:
            committed_score = score
            wt = collect_worktree(root, base)
            wt_signals, wt_notes, _ = build_report(root, base, args.brief, wt)
            wt_score = sum(wt_signals.values())
            winner = subject.name
            if wt_score > committed_score:
                signals, notes, score = wt_signals, wt_notes, wt_score
                winner = wt.name
            subject_note = (
                "subject: {} (committed {}, working tree {}) - "
                "higher wins".format(winner, committed_score, wt_score)
            )
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
        preamble = [ln for ln in (subject_note, base_note) if ln]
        print_table(signals, notes, preamble, score, band, rec)

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
