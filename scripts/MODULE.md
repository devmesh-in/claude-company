# scripts/ - repo-local developer tooling

Tools that support work ON claude-company. Nothing here is packed into the npm
tarball (the `files` allowlist in `package.json` does not name `scripts/`), so
the dual-nature rule does not apply: these may know this repo's exact layout.
That is the point - `company/` cannot, and this is where repo-specific facts
are allowed to live.

| What | Where |
|---|---|
| Brief | `company/briefs/brief-affected-suites.md` (issue #121) |
| Tests | `tests/hooks/test_affected_suites.py` |
| Derives from | `.github/workflows/ci.yml` |

## Files

| File | Role |
|---|---|
| `affected-suites.py` | python3 3.8 stdlib. Prints which of this repo's test suites a set of changed paths can break, so a lane stops paying for coverage it cannot affect. Reads paths from argv, or derives them from git (merge base with `origin/main`, plus the working tree). `--commands` for a runnable list, `--json` for machines, `--workflow` to point at a doctored copy of CI. |

## What must not drift

- **The suite list is derived, never kept.** `affected-suites.py` parses
  `.github/workflows/ci.yml` for commands whose first word is an interpreter
  and whose arguments carry a `tests/` path - the same shape the `canon` CI job
  uses. A second hand-kept list of the suites would be exactly the canon drift
  that job exists to catch. The two parsers are separate only because the canon
  job's body is an inline heredoc inside the workflow.
- **Unknown widens the run, always.** Three fail-safes, each proved by a test:
  a path no rule matches asks for every suite; a mapping selector that no
  longer resolves to a real suite asks for every suite; a suite no rule claims
  runs on every change. Over-running costs minutes. Under-running cost this
  repo a red branch on 2026-08-13, which is why the tool exists.
- **`RULES` is a fact table, not a judgment.** Every rule cites the line in the
  suite that justifies it - a suite is sensitive to a repo file only when it
  reads that file from the real repo. If you change a rule, change the evidence
  comment with it or the next reader has no way to check you.
- **The load-bearing pairing:** `company/run-gates.sh` asks for
  `tests/install/run_tests.sh`, which copies the REAL gate runner into a
  fixture and executes it. It is the only suite that does, nobody runs it by
  habit, and on 2026-08-13 that gap turned 13 tests red in CI.
- **It scopes LOCAL verification only.** CI keeps running everything across six
  platforms; that backstop is the only reason narrowing the local run is safe.
  Nothing here may be used to narrow what CI runs.

## Seams

- Upstream: `.github/workflows/ci.yml` (the suite list), `package.json`
  (the `npm test` alias is read from `scripts.test`, never hardcoded).
- Downstream: `company/templates/BRIEF-TEMPLATE.md` names the command in its
  DoD. Agents run it; nothing imports it.

## Changelog

- 2026-08-13 Directory created with `affected-suites.py` (task
  `affected-suites`, issue #121).
