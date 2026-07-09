# RELEASE: <proposed tag, e.g. v0.2.0>

_Prepared by: <devops-engineer/CEO>. Target commit: <sha>. Date: <YYYY-MM-DD>._

The company PREPARES this; the owner SHIPS. Tag, publish, and deploy are owner
buttons - never a step an agent runs. This filled checklist is the evidence the
owner reads before shipping. See `company/RELEASE.md` for the doctrine.

## Readiness (ALL rows green before anything below is filled)

Readiness is a fact, not a vibe: one command per row, one expected result. Fill
the Result column with the pasted output or verdict. **Every row must be green
before the changelog, semver, and notes are filled. A red row is a STOP** -
report what is red and prepare nothing further.

| Criterion | Command | Result |
|---|---|---|
| R1 - Full gate ladder green on integrated `main`, fresh stamp | `bash company/run-gates.sh` | <paste table; green = all green, stamp fresh with no tracked edit since> |
| R2 - Every shipped change pinned to witnesses | `python3 .claude/hooks/witness_check.py --check` | <exit code; green = exit 0, no unpinned change> |
| R3 - Requirement traceability (G6) clean | `python3 .claude/hooks/trace_check.py` | <exit code; green = exit 0, no orphan FR> |
| R4 - Model routing (G7) clean | `python3 .claude/hooks/guard_models.py --check` | <exit code; green = exit 0, no frontmatter drift> |
| R5 - Dependency / CVE audit (G8) green where wired | the G8 command in `company/gates.config` | <exit code; green = exit 0, no known-vulnerable dependency. If G8 is not yet wired, record "not wired" here, do not skip silently> |
| R6 - Security pass for sensitive releases | security-reviewer verdict on the diff | <required only if the release touches auth, session, or money; green = verdict is pass. If not sensitive, record "n/a - no auth/session/money"> |
| R7 - Zero open P0/P1 rows | read `company/state/WORRIES.md` | <green = no row with `P0` or `P1` in the P column> |
| R8 - Zero undecided change requests | list `company/change-requests/` | <green = no CR still awaiting a decision> |
| R9 - No red task in release scope | read `company/state/STATUS.md` | <green = no task in scope shows red> |

R1 - R5 are the same gate-ladder commands the CEO re-runs at integration (G0
witnesses, G6 trace, G7 models, G8 audit per `company/GATES.md`), not new
checks. A rung a project has not wired yet is recorded as "not wired" in its
Result cell, never quietly passed.

## Changelog

Derived from conventional commit subjects and their `Task:` trailers since the
last tag. Group by type; attribute every line to its `Task:` slug so each entry
traces to a work order. Drop a group heading that has no entries.

### Breaking
- <subject> (`Task: <slug>`) - <what breaks and what the consumer does instead>

### Features
- <subject> (`Task: <slug>`)

### Fixes
- <subject> (`Task: <slug>`)

## Semver proposal

- **Current version:** <e.g. 0.4.2>
- **Proposed version:** <e.g. 0.5.0>
- **Rule applied:** <pre-1.0 | post-1.0>
- **Reasoning (one line):** <e.g. a Breaking entry under pre-1.0 forces the minor bump>

The two rules, so the right one is picked:
- **Pre-1.0 (major is 0):** a breaking change bumps the MINOR (`0.4.x` ->
  `0.5.0`); a `feat` or `fix` bumps the PATCH (`0.4.2` -> `0.4.3`).
- **Post-1.0:** standard semver - breaking bumps MAJOR, `feat` bumps MINOR,
  `fix` bumps PATCH.

## Known limits

What a user should know is not there yet. Facts, not a highlights reel.
- Open worries (P2/P3): <row from `company/state/WORRIES.md`, or "none">
- Deferred FRs: <FR-XX-NN - deferred because <reason>, or "none">
- Other gaps: <what does not work / is not wired yet, or "none">

## Rollback note (OWNER-ONLY - descriptive, not a script)

If this release turns out bad, reverting it is an owner action. The company can
prepare a fix release through this same doctrine; it cannot unpublish or roll
back on its own. What the owner does:
- Point consumers back at the previous good tag: <previous good tag, e.g. v0.4.2>.
- Deprecate the bad version with a message pointing at the good one:
  `npm deprecate <pkg>@<bad-version> "use <good-version>"` - run by the OWNER.

## Handoff

The company's last act is a proposal, not an action. The CEO records one dated
entry in `company/state/DECISIONS.md` (the owner-written seam): Question names
the decision (`Release <tag> - accept and ship?`), Decision carries the proposed
tag name, the target commit these notes were built from, and this notes path;
Affects is `release`. Until the owner answers, the row reads
`proposed - awaiting owner`. Silence is not acceptance.

The owner then runs the ship commands themselves. These are documentation of
what the owner runs, never a script an agent invokes:

```bash
# OWNER-ONLY - the company never runs these
git tag -a <tag> <target-commit> -m "<tag>"
git push origin <tag>
npm publish            # or the project's publish/deploy step
```
