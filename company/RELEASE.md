# RELEASE.md - Preparing a release the company can hand off

How this company turns a green, integrated `main` into a release the owner can
ship. Every agent that touches release work follows this page; the CEO enforces
it. The one rule that outranks the rest:

**A release is PREPARED by the company and SHIPPED by the owner, never the
reverse.** The company assembles the evidence, writes the notes, bumps
`package.json`, and lands that commit on `main`. The owner's ship button is
one GitHub release: publishing a release tagged `vX.Y.Z` (matching
`package.json`) runs `.github/workflows/release.yml`, which re-runs the
suites and publishes to npm via OIDC trusted publishing. No npm token lives
in this repo. An agent does not tag, does not `npm publish`, and does not
create the GitHub release unless the owner instructed that ship in-session
(DECISIONS #17 option a).

## The two halves of a release

```text
company (prepared)                     owner (shipped)
  readiness proved                       reviews the proposal
  changelog assembled        ---->       publishes a GitHub release
  semver proposed                          tagged vX.Y.Z matching package.json
  notes written                            release.yml publishes to npm (OIDC)
  version bumped on main                   the release is live
  proposal filed to DECISIONS.md
```

The seam is `company/state/DECISIONS.md`. The company's last act is a
proposal entry plus the version bump on `main`. The owner's first act is
reading it, then creating the GitHub release.

## Release readiness (ALL must hold before preparation starts)

A release cannot be prepared from a red board. Every criterion below is
mechanically checkable - one command, one expected result - so readiness is a
fact, not a vibe. If any criterion is red, `/release` STOPS and reports what is
red; it does not prepare a partial release.

| # | Criterion | Command | Green means |
|---|---|---|---|
| R1 | Full gate ladder green on integrated `main`, fresh stamp | `bash company/run-gates.sh` | table all green; stamp fresh (no tracked edit since) |
| R2 | Every shipped change pinned to witnesses | `python3 .claude/hooks/witness_check.py --check` | exit 0, no unpinned change |
| R3 | Requirement traceability (G6) clean | `python3 .claude/hooks/trace_check.py` | exit 0, no orphan FR |
| R4 | Model routing (G7) clean | `python3 .claude/hooks/guard_models.py --check` | exit 0, no frontmatter drift |
| R5 | Dependency / CVE audit (G8) green where wired | the G8 command in `company/gates.config` | exit 0, no known-vulnerable dependency |
| R6 | Security pass for sensitive releases | opt-in security-reviewer per `company/EXTENDING.md` | required only if the release touches auth, session, or money; verdict is pass |
| R7 | Zero open P0/P1 rows | read `company/state/WORRIES.md` | no row with `P0` or `P1` in the P column |
| R8 | Zero undecided change requests | list `company/change-requests/` | no CR still awaiting a decision |
| R9 | No red task in release scope | read `company/state/RESUME.md` in-flight | no in-flight task in scope shows red |
| R10 | Enforcement still pays rent (FR-ASR-12, BR-ASR-12) | `python3 .claude/hooks/rent_report.py` | idle non-exempt hooks are named; unrecoverable-class stays exempt |

R1 - R5 map to the gate ladder in `company/GATES.md` (G0 witnesses, G6 trace,
G7 models, G8 audit); they are the same commands the CEO re-runs at integration,
not new checks. R2's `witness_check.py --check`, R3's `trace_check.py`, and R4's
`guard_models.py --check` are the wave-2 mechanisms cited by their exact names -
this doctrine consumes them, it does not redefine them. "Where wired" (R5, and
any ladder rung a project has not configured yet) means: if the rung exists in
`company/gates.config`, it must be green; a project grows toward the full ladder
per `company/GATES.md`, and a rung that is genuinely not yet wired is recorded
as such in the readiness table, never silently skipped.

## Release preparation (what /release produces)

Once readiness holds, the CEO (or an opt-in devops-engineer per
`company/EXTENDING.md`) assembles
the release from `main` itself - never from a worktree, never from unmerged
work. Four artifacts, all landing in the filled `RELEASE-TEMPLATE.md`:

1. **Changelog, derived from conventional commits.** Read the commit subjects
   and their `Task:` trailers since the last tag and group them by conventional
   type: `feat` under Features, `fix` under Fixes, anything with a `!` or a
   `BREAKING CHANGE:` body under Breaking. Attribute each line to its `Task:`
   slug so every entry traces to a work order. The range is:

   ```bash
   LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
   git log --no-merges --pretty='%s%n%b' "${LAST_TAG:+$LAST_TAG..}HEAD"
   ```

   If `git describe` finds no tag, the range is the full history since the first
   commit and this is the first release - see "The first release" below.

2. **Semver bump proposal, with reasoning.** State the current version, the
   proposed next version, and why in one line: a Breaking entry forces the
   breaking bump, otherwise any `feat` forces a feature bump, otherwise a
   `fix`-only set is a patch. The semver policy (pre- vs post-1.0) is below.

3. **Release notes, written as an evidence report.** What shipped (the grouped
   changelog), the gate ladder pasted from R1, and the known limits - the
   open P2/P3 worries, the deferred FRs, anything a user should know is not yet
   there. Notes are facts, not marketing: no adjectives, no highlights reel.

4. **The filled checklist.** `RELEASE-TEMPLATE.md` with every readiness row
   showing its command and result, the changelog, the semver proposal and
   reasoning, the known limits, and the rollback note.

## Semver policy

- **Pre-1.0 (major version is 0).** The API is still unstable, so a breaking
  change bumps the MINOR (`0.4.x` -> `0.5.0`); a `feat` or `fix` bumps the PATCH
  (`0.4.2` -> `0.4.3`).
- **Post-1.0.** Standard semver: breaking bumps MAJOR, `feat` bumps MINOR, `fix`
  bumps PATCH.

The proposal states which rule applied, so the owner sees the reasoning, not
just the number.

## The first release

This repository may have no tag history at the point of its first prepared
release. When `git describe --tags --abbrev=0` returns nothing, the changelog
range is the entire history since the first commit, and the release notes say so
plainly ("first release; changelog covers all history to date"). The owner's tag
for that release starts the tag history - every release after it measures its
range from the previous tag. The doctrine does not assume a tag exists; it reads
for one and falls back cleanly when there is none.

## The handoff - the proposal on DECISIONS.md

The prepared release ends as a proposal, not an action. `/release` does not
write `company/state/DECISIONS.md` itself (that file is company state, owned and
written by the CEO); it hands the CEO the material and the CEO records one dated
entry in the DECISIONS table, matching the existing structure, terse:

- **Question** names the decision - e.g. `Release v0.2.0 - accept and ship?`
- **Decision** carries the proposal: proposed tag name, target commit (the
  integrated-`main` SHA the notes were built from), and where the notes live
  (the filled `RELEASE-TEMPLATE.md` path). Until the owner answers, the row
  reads `proposed - awaiting owner`.
- **Affects** is `release`.

The owner reads the entry, then ships with one command. Include it in the
notes marked OWNER-ONLY - documentation of what the owner runs, never a
local `npm publish`:

```bash
# OWNER-ONLY - publishes the GitHub release; release.yml then npm-publishes
gh release create v<version> --target <target-commit> \
  --notes-file company/RELEASE-<version>.md
```

The tag must equal `v` plus `package.json`'s version or `release.yml` exits
before publish. There is no separate `npm publish` step.

When the owner responds, the CEO records the outcome on the same decision
(`accepted` / `accepted-with-notes` / `rejected`) with the date and one line,
per the owner-acceptance rule in `ORCHESTRATOR.md`. Silence is not acceptance.

## Rollback is also the owner's

If a shipped release turns out bad, reverting it is an owner action, described
in the release notes (see the rollback note in `RELEASE-TEMPLATE.md`), never
run by an agent: retag/point consumers at the previous good tag, and
`npm deprecate` the bad version with a message pointing at the good one. The
company can prepare a fix release through this same doctrine; it cannot unpublish
or roll back on its own.

## Where release work is barred

- No skill, agent, hook, or make target the company owns may run `git tag`,
  `git push` of a tag, `npm publish`, `gh release create`, or any deploy
  on its own initiative. Direct in-session owner instruction to ship
  authorizes `gh release create` for that release only, recorded in
  DECISIONS.md. `release.yml` is the only path that runs `npm publish`.
- The changelog and notes are built from `main` after integration, never from a
  task worktree - a worktree's view can miss merged work or carry unmerged work.
- An update is never run mid-task: a mid-turn tree swap can mix hook versions
  for sub-second windows.
- Preparation runs only on a green board. A red readiness criterion is a stop,
  not a footnote.
