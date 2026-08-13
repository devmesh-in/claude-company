#!/usr/bin/env python3
"""Which test suites can THIS change break.

Every lane in this repo runs all five suites, usually twice, because prose has
failed twice in opposite directions: "the two suites that actually gate THIS
repo" was wrong and cost a lane a red branch, and "all five, always" is right
and costs about 15 minutes a run. `tests/install/test_update.sh` alone is over
600 seconds of installer-rollout tests that no hook change can reach.

Which suites a change can break is a FACT about this repo, so it lives here
instead of in a third sentence that every agent has to interpret.

Two rules make it safe to trust:

  * The suite list is DERIVED from `.github/workflows/ci.yml`. A second list
    of the suites would be exactly the canon drift the repo's own `canon` CI
    job exists to catch. Add a suite to the workflow and this tool reports it
    without being edited.
  * Unknown fails safe. A path no rule recognises asks for EVERY suite, a
    mapping rule that no longer resolves to a real suite asks for every suite,
    and a suite no rule claims runs on every change. Over-running costs
    minutes; under-running costs a red branch, which this repo has paid.

This scopes LOCAL verification only. CI still runs everything across six
platforms and remains the backstop - that is the whole reason scoping the
local run is safe.

Usage:
  scripts/affected-suites.py                 # the current branch's changes
  scripts/affected-suites.py PATH [PATH ...] # explicit paths
  scripts/affected-suites.py --since main    # committed changes vs a ref
  scripts/affected-suites.py --commands      # bare commands, one per line
  scripts/affected-suites.py --json          # machine-readable
"""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_WORKFLOW = os.path.join(".github", "workflows", "ci.yml")

# A suite invocation in the workflow is a command whose first word is an
# interpreter and whose arguments carry a tests/ path. Same shape the `canon`
# CI job uses, and for the same reason: it keeps the tests/ strings that live
# inside grep patterns and for loops (the slop and pack jobs) out of the list.
# The two parsers are not shared because the canon job's body is an inline
# heredoc in the workflow, and changing what CI runs is out of scope here.
INTERPRETERS = ("bash", "sh", "zsh", "python", "python3", "node")


class Suite(object):
    """One suite CI runs, as the workflow spells it."""

    def __init__(self, path, command, step):
        self.path = path
        self.command = command
        self.step = step

    def __repr__(self):
        return "Suite(%r)" % self.path


# Selectors name a suite by a stable fragment of its path. A selector is a
# POINTER into the derived list, never a copy of it: if the workflow renames or
# drops the suite a selector points at, the selector resolves to nothing and
# this tool falls back to running everything rather than silently dropping
# coverage.
SELECTORS = (
    ("hooks", "tests/hooks/"),
    ("cli", "tests/cli/"),
    ("installer", "tests/install/run_tests.sh"),
    ("tui", "tests/install/test_tui.sh"),
    ("update", "tests/install/test_update.sh"),
)

ALL = "ALL"

# Always, whatever changed. Not a rule about paths - a rule about these two
# suites.
BASELINE = (
    ("hooks", "always - the cheapest suite and the oracle for the rest"),
    ("cli", "always - its pack manifest section reads the whole repo tree "
            "through the package.json allowlist"),
)


class Rule(object):
    def __init__(self, patterns, suites, why):
        self.patterns = patterns
        self.suites = suites
        self.why = why


# Ordered, FIRST match wins. Each rule names the suites a matching path needs
# BEYOND the baseline, and cites the evidence that put them there. Evidence is
# a line in the suite itself: a suite is sensitive to a repo file only if it
# reads that file from the real repo.
RULES = (
    Rule((".github/workflows/ci.yml",), ALL,
         "the workflow defines the suite list this tool derives"),

    # tests/install/run_tests.sh builds a SYNTHETIC source tree and writes STUB
    # hooks into it (run_tests.sh, build_source), so it never executes a real
    # hook. test_update.sh drives update.sh over file dispositions, not hook
    # behavior. The CLI suite does read hook paths - its pack manifest asserts
    # .claude/hooks/guard_commit.py ships - and the CLI suite is baseline.
    Rule((".claude/hooks/**",), (),
         "the installer suite stubs hooks; the pack manifest that names them "
         "is in the baseline CLI suite"),

    # test_update.sh byte-compares the packaged .claude/agents/developer.md
    # against the file it wrote into a target.
    Rule((".claude/agents/**",), ("installer", "update"),
         "the update suite byte-compares a packaged agent file"),

    # run_tests.sh copies the real .mcp.json and the real settings into its
    # fixtures; test_update.sh drives settings merge behavior at length.
    Rule((".claude/settings.json",), ("installer", "update"),
         "both install and update merge this file for real"),
    Rule((".mcp.json",), ("installer",),
         "run_tests.sh copies the real .mcp.json into its fixture"),
    Rule((".claude/**",), ("installer",),
         "payload the installer copies"),

    # THE pairing this tool exists for. run_tests.sh's make_gates_fixture does
    # `cp "$REPO/company/run-gates.sh"` and then EXECUTES it against four gate
    # configs. On 2026-08-13 a lane changed the gate runner, ran the suites it
    # thought covered it, and CI turned 13 tests red.
    Rule(("company/run-gates.sh",), ("installer",),
         "run_tests.sh copies the REAL gate runner and executes it - this is "
         "the pairing that would have caught the 2026-08-13 red branch"),

    Rule(("company/gates.config",), ("installer", "tui", "update"),
         "run_tests.sh and test_tui.sh both read the real gates.config, and "
         "update disposes of it"),
    Rule(("company/models.json",), ("update",),
         "test_update.sh reads the packaged models.json to check injection"),
    Rule(("company/provenance.json",), ("installer", "update"),
         "install ships it copy_if_absent and update disposes of it"),

    # Not shipped: package.json excludes company/state and the record trees,
    # and the baseline CLI suite asserts that exclusion in the pack manifest.
    Rule(("company/state/**", "company/specs/**", "company/briefs/**",
          "company/change-requests/**"), (),
         "excluded from the tarball; the baseline CLI suite asserts the "
         "exclusion"),

    Rule(("company/**",), ("installer",),
         "payload the installer copies"),

    Rule(("install.sh", "install"), ("installer", "tui", "update"),
         "all three install suites run the real installer"),
    Rule(("update.sh",), ("update",),
         "test_update.sh drives the real update.sh throughout"),
    Rule(("lib/**",), ("installer", "tui", "update"),
         "run_tests.sh reads manifest.py and payload_paths.sh, test_tui.sh "
         "runs install-tui.js, test_update.sh reads manifest.py"),
    Rule(("bin/**",), ("tui",),
         "test_tui.sh drives the Node CLI; the baseline CLI suite is the rest"),
    Rule(("package.json",), ("installer", "tui", "update"),
         "the pack allowlist and the version both reach the install engines"),
    Rule(("ORCHESTRATOR.md",), ("installer",),
         "payload the installer copies"),

    Rule(("tests/install/run_tests.sh",), ("installer",), "the suite itself"),
    Rule(("tests/install/test_tui.sh",), ("tui",), "the suite itself"),
    Rule(("tests/install/test_update.sh",), ("update",), "the suite itself"),
    Rule(("tests/hooks/**", "tests/cli/**"), (),
         "covered by the baseline suites"),
    Rule(("tests/**",), ALL,
         "a test file no suite rule claims - coverage unknown"),

    Rule(("scripts/**",), (),
         "repo-local tooling, not packed; its tests live in the hooks suite"),

    Rule(("CLAUDE.md",), (),
         "doctrine: covered locally by tests/hooks/test_doctrine_canon.py, and "
         "in CI by the canon job"),
    Rule((".github/**",), (),
         "CI config other than the workflow this tool derives from"),
    Rule(("docs/**", "README.md", "LICENSE", ".gitignore", ".vscode/**",
          ".assets/**", ".mailmap", ".editorconfig"), (),
         "no local suite reads these; CI's readme and slop jobs do"),
)


def glob_to_regex(pattern):
    """fnmatch-style glob where ** crosses directories and * does not."""
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(out) + "$")


_REGEX_CACHE = {}


def matches(pattern, path):
    rx = _REGEX_CACHE.get(pattern)
    if rx is None:
        rx = _REGEX_CACHE[pattern] = glob_to_regex(pattern)
    return rx.match(path) is not None


def derive_suites(workflow_path):
    """The suite list, read out of the workflow. The single source of truth."""
    suites = []
    seen = set()
    step = "(unnamed step)"
    with open(workflow_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            named = re.match(r"^(?:-\s+)?name:\s*(.+)$", line)
            if named:
                step = named.group(1).strip()
            if line.endswith("\\"):
                line = line[:-1].strip()
            run = re.match(r"^(?:-\s+)?run:\s*(.*)$", line)
            cmd = run.group(1) if run else line
            toks = [t.strip("\"'`;,()[]") for t in cmd.split()]
            if not toks or toks[0] not in INTERPRETERS:
                continue
            for tok in toks[1:]:
                if tok.startswith("tests/") and tok not in seen:
                    seen.add(tok)
                    suites.append(Suite(tok, "%s %s" % (toks[0], tok), step))
    return suites


def resolve(selector_key, suites):
    """Selector -> the derived suites it points at. Empty means it drifted."""
    fragment = dict(SELECTORS)[selector_key]
    return [s for s in suites if fragment in s.path]


def rule_for(path):
    for rule in RULES:
        for pattern in rule.patterns:
            if matches(pattern, path):
                return rule
    return None


def plan(paths, suites):
    """Return (selected, reasons, warnings).

    selected: list of Suite, in workflow order.
    reasons:  {suite path: [reason strings]}
    warnings: fail-safe escalations, each of which widened the run.
    """
    reasons = {}
    warnings = []
    chosen = set()

    def take(suite, reason):
        chosen.add(suite.path)
        reasons.setdefault(suite.path, [])
        if reason not in reasons[suite.path]:
            reasons[suite.path].append(reason)

    def take_all(reason):
        for suite in suites:
            take(suite, reason)

    # Every selector a rule can name must resolve to a real suite. One that
    # does not means the workflow renamed or dropped that suite under the
    # mapping, and a rule pointing at nothing would silently drop coverage.
    for key, fragment in SELECTORS:
        if not resolve(key, suites):
            warnings.append(
                "mapping drift: no suite in the workflow matches selector "
                "'%s' (%s). Running everything." % (key, fragment))
    if warnings:
        take_all("fail-safe: the path-to-suite mapping has drifted")

    for key, why in BASELINE:
        for suite in resolve(key, suites):
            take(suite, why)

    # A suite no rule and no selector claims is a suite of unknown coverage.
    claimed = set()
    for key, _fragment in SELECTORS:
        for suite in resolve(key, suites):
            claimed.add(suite.path)
    for suite in suites:
        if suite.path not in claimed:
            take(suite, "unclaimed by any rule - unknown coverage, so it "
                        "always runs (step '%s')" % suite.step)

    for path in paths:
        rule = rule_for(path)
        if rule is None:
            warnings.append(
                "unrecognised path: %s. No rule covers it, so coverage is "
                "unknown. Running everything." % path)
            take_all("fail-safe: %s matches no rule" % path)
            continue
        if rule.suites == ALL:
            take_all("%s - %s" % (path, rule.why))
            continue
        for key in rule.suites:
            for suite in resolve(key, suites):
                take(suite, "%s - %s" % (path, rule.why))

    selected = [s for s in suites if s.path in chosen]
    return selected, reasons, warnings


def npm_test_command(repo_root):
    """The package.json test script, so the CLI suite can be named the way
    CLAUDE.md names it. Read, never hardcoded."""
    try:
        with open(os.path.join(repo_root, "package.json"), encoding="utf-8") as fh:
            return (json.load(fh).get("scripts") or {}).get("test")
    except (IOError, OSError, ValueError):
        return None


def git(repo_root, *args):
    proc = subprocess.run(["git", "-C", repo_root] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def changed_paths(repo_root, since):
    """Paths this branch touches: committed since the base, plus the working
    tree. Both, because a lane verifies before it commits."""
    paths = []

    def add(p):
        p = p.strip()
        if p and p not in paths:
            paths.append(p)

    bases = [since] if since else ["origin/main", "main"]
    for base in bases:
        rc, out = git(repo_root, "merge-base", base, "HEAD")
        if rc != 0:
            continue
        rc, out = git(repo_root, "diff", "--name-only", out.strip(), "HEAD")
        if rc == 0:
            for line in out.splitlines():
                add(line)
        break

    # -uall, not the default: plain --porcelain collapses an untracked
    # directory to one entry ("scripts/"), and a directory is not a path any
    # rule can judge honestly.
    rc, out = git(repo_root, "status", "--porcelain", "-uall")
    if rc == 0:
        for line in out.splitlines():
            entry = line[3:] if len(line) > 3 else ""
            if " -> " in entry:
                entry = entry.split(" -> ", 1)[1]
            add(entry.strip('"'))
    return paths


def repo_root_of(script_path):
    here = os.path.dirname(os.path.abspath(script_path))
    rc, out = git(here, "rev-parse", "--show-toplevel")
    if rc == 0 and out.strip():
        return out.strip()
    return os.path.dirname(here)


def main(argv):
    ap = argparse.ArgumentParser(
        prog="affected-suites.py",
        description="Which test suites can this change break.")
    ap.add_argument("paths", nargs="*",
                    help="changed paths, project-relative. Default: derive "
                         "them from git.")
    ap.add_argument("--since", metavar="REF",
                    help="diff against the merge base with REF "
                         "(default: origin/main, then main)")
    ap.add_argument("--workflow", metavar="PATH",
                    help="workflow to derive the suite list from "
                         "(default: %s). Overridable so the derivation can be "
                         "demonstrated against a doctored COPY." % DEFAULT_WORKFLOW)
    ap.add_argument("--commands", action="store_true",
                    help="print only the commands to run, one per line")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="machine-readable output")
    args = ap.parse_args(argv[1:])

    repo_root = repo_root_of(argv[0])
    workflow = args.workflow or os.path.join(repo_root, DEFAULT_WORKFLOW)
    if not os.path.exists(workflow):
        sys.stderr.write("affected-suites: no workflow at %s\n" % workflow)
        sys.stderr.write("The suite list is derived from it and there is "
                         "nothing to derive. Run every suite.\n")
        return 2

    suites = derive_suites(workflow)
    if not suites:
        sys.stderr.write(
            "affected-suites: found no suite invocations in %s\n" % workflow)
        sys.stderr.write("The parser no longer matches how the workflow runs "
                         "its suites; fix the parser. Run every suite.\n")
        return 2

    paths = args.paths or changed_paths(repo_root, args.since)
    selected, reasons, warnings = plan(paths, suites)

    npm_test = npm_test_command(repo_root)
    aliases = {}
    for suite in suites:
        if npm_test and npm_test.strip() == suite.command:
            aliases[suite.path] = "npm test"

    if args.as_json:
        json.dump({
            "workflow": os.path.relpath(workflow, repo_root),
            "changed_paths": paths,
            "all_suites": [s.path for s in suites],
            "run": [s.path for s in selected],
            "skip": [s.path for s in suites if s not in selected],
            "commands": [aliases.get(s.path, s.command) for s in selected],
            "reasons": reasons,
            "warnings": warnings,
        }, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if args.commands:
        for suite in selected:
            sys.stdout.write("%s\n" % aliases.get(suite.path, suite.command))
        return 0

    out = sys.stdout
    if not paths:
        out.write("affected-suites: no changed paths found. "
                  "Pass paths explicitly or use --since.\n")
    for warning in warnings:
        out.write("WARN  %s\n" % warning)
    if warnings:
        out.write("\n")

    out.write("changed paths: %d\n" % len(paths))
    for path in paths:
        rule = rule_for(path)
        out.write("  %-46s %s\n" % (
            path, "NO RULE - fail safe" if rule is None else rule.why))
    out.write("\n")

    out.write("RUN  %d of %d suites\n" % (len(selected), len(suites)))
    for suite in selected:
        command = aliases.get(suite.path, suite.command)
        out.write("  %-46s %s\n" % (command, reasons[suite.path][0]))
        for extra in reasons[suite.path][1:]:
            out.write("  %-46s %s\n" % ("", extra))

    skipped = [s for s in suites if s not in selected]
    if skipped:
        out.write("\nSKIP %d of %d suites\n" % (len(skipped), len(suites)))
        for suite in skipped:
            out.write("  %s\n" % aliases.get(suite.path, suite.command))

    out.write("\nCI still runs every suite on six platforms. This scopes the "
              "LOCAL run only.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
