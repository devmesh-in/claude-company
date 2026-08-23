# RELEASE 0.3.2 - harness-agnostic

_Prepared: 2026-08-23. Target commit: `5679c96` on `main`. Prepared by: CEO._
_Status: PROPOSED - awaiting owner. The company prepares; the owner ships._

## Readiness

Every rung run on integrated `main`, output pasted, nothing skipped.

| # | Criterion | Result |
|---|---|---|
| R1 | gate ladder green, stamp fresh | **GREEN** - see the ladder below; stamp `tree:3326e4e7`, 2026-08-23T17:01:58Z |
| R2 | `witness_check.py --check` | **GREEN** - exit 0, 35 witnesses, 0 failed |
| R3 | `trace_check.py` | **GREEN** - 23 requirements, 0 orphans. Was 4 orphans (`FR-HA-07`, `BR-HA-01..03`): implemented and tested, missing only the citation. Fixed in `5679c96`, comments only |
| R4 | `guard_models.py --check` | **GREEN** - exit 0, all 10 roles agree with the manifest |
| R5 | dependency audit (G8) | **NOT WIRED** - no such gate in `company/gates.config`, and the package declares zero runtime and zero dev dependencies, so the rung has nothing to audit |
| R6 | security-reviewer verdict | **NOT REQUIRED** - no auth, session, or money surface in this release |
| R7 | no P0 or P1 worry | **RED, OWNER-ACCEPTED** - see below |
| R8 | no undecided CR | **GREEN** - all 8 CRs decided (6 APPLIED, 2 APPROVED); CR-3 applied in this release |
| R9 | no red task in release scope | **GREEN for scope, board STALE** - see below |

### R1 ladder, pasted

```
Gate ladder
GATE                     RESULT TIME
------------------------ ------ ------
hooks                    PASS   80s
tests                    PASS   105s

wrote gates.status: green
all gates passed
```

`company/gates.config` wires two of the six suites this repo actually gates
on. The other four were run directly for this release:

```
installer   PASS: 97   FAIL: 0
TUI         PASS: 22   FAIL: 0
update      PASS: 139  FAIL: 0
harness     PASS: 146  FAIL: 0   (43 logic + 16 handler + 19 renderer
                                  + 23 install + 45 real opencode binary)
```

Total 1187 tests. CI on the merge commit: 12/12 green, including the new
`harness` job, which installs the real `opencode` binary and passed in 39s.

### R7 - red, and why it is being accepted

Two open rows in `company/state/WORRIES.md`:

- **P0**: DECISIONS #19's compensating control was never mechanized.
  `risk_score.py` has zero callers and is wired to no hook event; the
  risk-scaled audit band exists only as a runbook instruction in
  `ORCHESTRATOR.md`. OWNER RULING 2026-08-23: the fix is in flight on a
  separate branch and does not gate this release.
- **P1**: `guard_provenance.dirty_source_paths` is umbrella-scoped rather than
  repo-scoped, so in a polyrepo install dirty source anywhere under the
  umbrella counts as this session's unaudited work. Commit-time false block in
  polyrepo installs only. Not folded in: narrowing what counts as dirty
  converts BLOCKs into ALLOWs, which needs a spec and an independent read
  rather than a release-time patch.

Precedent: v0.2.6 shipped with R7 red on two P1 rows, recorded rather than
waived. This follows that precedent, with the P0 tracked elsewhere.

**Stated plainly, because it is the honest read:** the P0 is exactly the
control this release would have exercised. This work touches the enforcement
layer, landed under a hotfix bypass, on an audit that went stale when its own
findings were fixed. An armed risk band is what would have made a second audit
mandatory rather than optional. Shipping is the owner's call; the reasoning
should not be lost.

### R9 - scope green, board stale

No red task in release scope; `active-task.json` is empty and both entries were
closed on integration. But `company/state/STATUS.md` was last updated
2026-08-13 and still says "v0.2.6 remains registry latest" while 0.3.0 and
0.3.1 have both shipped. The board does not describe reality and is owed an
update independently of this release.

## Changelog

Since `v0.3.1`. Two features, both breaking-adjacent, one docs commit.

### Breaking

- **The cost ledger is removed outright** (`cost-ledger-removal`, #134).
  `.claude/hooks/cost_capture.py`, `company/state/costs.log`,
  `.cost-cursor.json`, the `pricing` map in `company/models.json`, and the
  `/standup` Spend line are all gone. The `SubagentStop` hook group is deleted
  entirely - it existed only for this hook. Frozen-surface entries removed
  through CR-3, superseding part of CR-2; witness W-002 removed through the
  CLI.

### Features

- **The company runs on opencode as well as Claude Code** (`harness-agnostic`,
  #133). `.claude/` stays the sole source of truth and is never regenerated;
  `.opencode/` is a generated view of it. Ships the adapter (dependency-free
  ESM, no build step), a renderer, harness selection in `install` and
  `update`, a `claude-company render` subcommand, and a 146-test harness suite
  that runs the real `opencode` binary with no skip path.

### Fixes

- Four requirement IDs cited at their real sites so the traceability matrix
  sees coverage that already existed (`5679c96`). Comments only.

## Semver

**Proposed: 0.3.2. This is an OWNER OVERRIDE of the rule, recorded as such.**

The rule in `/release` and `company/RELEASE.md` is: pre-1.0, a breaking change
bumps the MINOR. The cost-ledger removal is breaking - it deletes shipped
behavior that existing installs use - and its commit is marked `!`. By the
rule the number is **0.4.0**.

The owner directed 0.3.2. Recorded here rather than silently applied, because
a patch number tells users nothing changed for them and something did: anyone
who updates loses cost tracking and the `/standup` Spend line.

## Known limits

- **Update leaves an orphan.** `update.sh` restores payload files but does not
  delete retired ones, so an existing project keeps `cost_capture.py` on disk
  while `settings.json` no longer references it. Inert - nothing invokes it -
  but present.
- **Two harness divergences, neither reachable with the shipped config:**
  non-Python hook commands in `.claude/settings.json` are ignored by the
  opencode adapter, and `Bash(...)` / `WebFetch(...)` deny entries are not
  translated. Both become real the first time a project adds one.
- **MCP tools block on opencode.** An MCP server defines its own argument
  shape, so the guards have no file path or content to judge. Refused with a
  message saying so, rather than fake-guarded.
- **opencode ignores `CLAUDE.md` when `AGENTS.md` exists.** The installer warns;
  it does not rewrite the file.
- R5 not wired, R7 red as above, `STATUS.md` stale as above.

## OWNER-ONLY ship commands

The company does not run these. Documentation of what the owner runs:

```bash
# OWNER-ONLY - the company never runs these
git tag -a v0.3.2 5679c96 -m "v0.3.2"
git push origin v0.3.2
npm publish            # from a clean clone of the tag, AUTHORIZED=1
```

Publishing is owner-manual by standing decision: the account uses link-based
2FA with no OTP, and `package.json`'s `prepare` script refuses any publish
without `AUTHORIZED=1`.

## Rollback (OWNER-ONLY)

```bash
# OWNER-ONLY
npm deprecate claude-company@0.3.2 "superseded - see <reason>"
git push --delete origin v0.3.2     # only if never consumed
```

A published version is never unpublished; it is deprecated and superseded. If
0.3.2 must be pulled after consumption, ship 0.3.3 with the revert rather than
removing 0.3.2 from the registry.
