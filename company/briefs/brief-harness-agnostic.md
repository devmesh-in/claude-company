# BRIEF: harness-agnostic

_Type: feature. Spec: `company/specs/spec-harness-agnostic.md`.
Lead: direct-developer (sole, owner-directed). Date: 2026-08-23. Tracking: #133._

## Mission

Make the company run on opencode as well as Claude Code, from one install,
with the same enforcement verdicts. `.claude/` stays the sole source of truth
and is never regenerated; `.opencode/` becomes a generated view of it. Success
is an opencode session where a frozen-surface edit, a slop violation, and a
staged secret each block exactly as they do on Claude Code - including from
inside a subagent.

The hard constraint, from the owner and non-negotiable: **the Claude Code
outcome does not change.** How we get there is free; where we end up is not.

## Read first (in order)

1. `CLAUDE.md`, `company/METHOD.md`
2. `company/specs/spec-harness-agnostic.md` - all FR-HA IDs
3. `.claude/settings.json` - the wiring the adapter must mirror
4. `.claude/hooks/_common.py` - `git_cwd`, `acting_tree`, `seg_git_dir`
5. `.claude/hooks/guard_models.py` - `EXPECTED_WIRING`, unchanged by this work
6. `DevMesh/.opencode/plugins/company-harness.ts` on branch
   `task/opencode-shim` - the prior attempt. Read it for the payload
   translation shape and for what NOT to repeat.

## You own

- `lib/` (the renderer), `.opencode/` (generated output), `tests/harness/`
- targeted edits to `install.sh`, `update.sh`, `bin/claude-company.js`,
  `lib/install-tui.js`, `lib/payload_paths.sh`, `package.json`, `docs/`
- `CLAUDE.md` and `.github/workflows/ci.yml`, for the suite list and the new
  CI job. ADDED 2026-08-23 after an audit found both edited outside the
  original list: a sixth blocking suite that CLAUDE.md does not name is the
  exact drift CLAUDE.md exists to prevent, and a suite CI does not run is
  W-030 again.

Nothing else. `.claude/hooks/*.py`, `.claude/agents/*.md`,
`.claude/skills/**` and `.claude/settings.json` are READ-ONLY to this task -
touching them is how the Claude side regresses.

## Invariants in play

- Hooks stay Python 3.8 stdlib and fail open on internal error. The ADAPTER
  is not a hook: it fails CLOSED (FR-HA-10, FR-HA-11).
- `no_slop` applies to all writing, generated files included.
- The tracked `company/gates.config` keeps its `CONFIGURE ME` placeholders.
- `company/` ships verbatim and must stay generic.

## Frozen surfaces nearby

None touched. Do not add `.opencode/` paths to the registry in this task; if
generated output turns out to need freezing, that is a separate CR.

## Scope (ordered)

1. Renderer in `lib/`, dependency-free Node: agents (FR-HA-02), commands
   (FR-HA-03), adapter chains derived from `settings.json` (FR-HA-04).
2. The adapter, `.opencode/plugin/company-harness.js`, plain ESM (FR-HA-06
   through FR-HA-15). Every one of the five departures from the DevMesh shim
   is a named FR; none is optional.
3. Generated `.opencode/` committed, drift gate wired (FR-HA-05).
4. `tests/harness/`: renderer units, the golden payload corpus (FR-HA-20), and
   the real-binary registration suite (FR-HA-19).
5. Install and update harness selection (FR-HA-16 through FR-HA-18).
6. Docs, and the capability table.

## Integration seams

- The adapter guarantees the guards receive a payload indistinguishable from
  Claude Code's; it may assume the guards are unchanged.
- `arm-risk-band` is in flight on `guard_provenance.py` and its tests. That is
  file-disjoint from everything here. Do not touch it.

## Definition of Done

Universal DoD, plus:

- [ ] `git diff` touches ZERO files under `.claude/` - the Claude guarantee is
      shown by the diff, not argued
- [ ] All five existing suites green, plus the new harness suite
- [ ] `guard_models.py --check` exit 0, `EXPECTED_WIRING` unmodified
- [ ] Regenerating `.opencode/` produces no diff
- [ ] A live opencode session blocks on a frozen-surface edit from inside a
      subagent, captured as evidence
- [ ] An auditor pass before this lands (the one delegation the owner allowed)

## Fallback assumptions

- OQ-HA-01: opencode does not enumerate its tools headlessly. FALLBACK: ship
  `known-tools.json`, assert the adapter classifies every entry, refresh on
  version bump. Tag `// OQ-HA-01 assumption`.
- OQ-HA-02: skills placement for an opencode-only install. FALLBACK:
  `.claude/skills/` only, since `.claude/` installs regardless.
- OQ-HA-03 REVISED 2026-08-23 after audit: there is no `patch` tool. opencode
  registers `apply_patch`, whose only argument is `patchText` - no file path,
  no content. The original fallback (classify as a write tool, run the Edit
  chain) would have handed the guards an empty path and an empty string, so
  they would inspect nothing and pass: a bypass that looks like enforcement.
  DECIDED: refuse it, with a message naming the reason. `edit` and `write` do
  the same job and are fully guarded.

## Out of scope

- Cost tracking (removed under #134, landed first).
- Per-role model tiering on opencode - roles inherit, full stop.
- A third harness.
- Any change to guard logic, skill bodies, or role bodies.

## Report back

Paths changed, the pasted six-suite ladder, the FR-HA checklist, the
`git diff --stat` proving `.claude/` is untouched, the live-session block
evidence, the auditor verdict, deviations, and worries.
