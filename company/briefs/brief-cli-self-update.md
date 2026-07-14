# BRIEF: cli-self-update

_Type: feature. Spec: company/specs/spec-cli-self-update.md (do not read it -
this brief is your sealed work order). Lead: direct-developer. Date: 2026-07-15._

> Schema, contracts, kernel, and anything in `company/frozen-surfaces.json`
> are FROZEN - consume them exactly as shipped; any change goes through
> `company/change-requests/`, never a local edit.

## Mission

Make `claude-company update` get the CLI itself current before it touches the
project: when a newer version of the claude-company package is published, the
driver hands off to it exactly once (covering stale npx caches and stale
global installs), and the NEWER CLI performs the repo refresh. The hard
constraint: the check FAILS OPEN - offline, timeout, bad JSON, missing npx,
anything unexpected prints one WARN line and proceeds with the current
version. An update must never brick or hang because the registry is away.

## Read first (in order)

1. `CLAUDE.md` (project canon - dual-nature rule, the two real gate suites)
2. `company/METHOD.md`
3. `lib/update.js` (the driver you extend - arg parse, preflight reuse, the
   exec of update.sh, exit-code passthrough)
4. `bin/claude-company.js` (update route + help text)
5. `tests/cli/test_cli.sh` (the update block near the end - your new
   assertions join it) and `tests/install/test_update.sh` (style reference)

## You own

- `lib/update.js` (the self-update step + seams)
- `bin/claude-company.js` (help text only: `--no-self-update` in update help
  and any flag list)
- `docs/getting-started.md` (the update section: one short paragraph on
  self-update + the new flag + the network note)
- `tests/cli/test_cli.sh` (new assertions in the existing update block)
- `lib/MODULE.md` (add the self-update contract lines)

Nothing else. `update.sh`, `lib/manifest.py`, `lib/payload_paths.sh`,
`install.sh`, `package.json`, and the disposition engine are READ-ONLY - the
spec explicitly leaves the engine untouched. If you think you need them,
report it; do not edit.

## Invariants in play (must not break)

- Node stdlib only (`https`, `child_process`); zero third-party deps.
- Fail OPEN on every self-update path: any resolution/spawn failure -> one
  WARN line -> proceed with the current CLI. Never a new nonzero exit from
  the check itself.
- Existing behavior byte-stable when: versions equal, latest older,
  registry unresolved, `--no-self-update`, `--check`, `CC_SELFUPDATE_DONE`
  set, or npx absent (FR-SU-08).
- Exit-code contract unchanged (0/1/2/3/4); on re-exec, return the child's
  exit verbatim (FR-SU-03).
- No test may touch the live registry - use the injection seams (FR-SU-12).
- The driver NEVER runs `npm install -g` (OQ-SU-02) - guidance line only.
- Hook-clean writing everywhere: straight quotes, ' - ' never em dashes,
  three dots '...' never the ellipsis glyph.

## Frozen surfaces nearby (CR, never edit)

- `company/state/install-manifest.json` and `company/state/.update-backups/**`
  are frozen (CR-UPD-1) - your code never touches them; they belong to the
  engine.
- Lockfiles / .env always frozen.

## Scope (ordered)

1. Currency check in `lib/update.js` after arg parse, before preflight
   (FR-SU-01): resolve latest via Node `https` GET
   `<CC_REGISTRY_URL || https://registry.npmjs.org>/claude-company/latest`,
   timeout `CC_REGISTRY_TIMEOUT_MS || 2000`, parse `.version` (FR-SU-02,
   OQ-SU-04 - tag the timeout site `// OQ-SU-04 assumption`).
   `CC_LATEST_VERSION` env, when set, bypasses the network entirely and is
   the resolved answer (FR-SU-12).
2. JS version compare mirroring `manifest.py` `_vercmp` semantics - numeric
   dot-segments, missing segments = 0 (OQ-SU-01, tag
   `// OQ-SU-01 assumption`). Strictly newer = re-exec candidate.
3. Re-exec path (FR-SU-03/04/05/09, OQ-SU-05): conditions - newer AND not
   `--no-self-update` AND not `--check` AND `CC_SELFUPDATE_DONE` unset AND
   npx resolvable. Print exactly one handoff line
   (`self-update: handing off to claude-company@<latest> ...`), spawn
   `npx -y claude-company@<latest> update <original args verbatim>` with
   env `CC_SELFUPDATE_DONE=1`, wait, exit with the child's code, do nothing
   else. Spawn failure -> WARN -> fall through to the current CLI.
4. Skip paths (FR-SU-06/07/08): `--no-self-update` skips the WHOLE step
   including the network call (OQ-SU-06); `--check` performs the resolution
   (unless flagged off) and prints a staleness line in the plan but never
   re-execs; equal/older/unresolved -> today's behavior, with the WARN line
   only on failure, silence on equal.
5. Global-install guidance (FR-SU-10): when the check found a newer version
   and DID re-exec, nothing more; the handoff covers it. When newer was
   found but npx is absent, print one line suggesting
   `npm install -g claude-company@latest` - never run it.
6. Flags and help (FR-SU-11): `--no-self-update` in `parseArgs`, in
   `update --help`, and the bin help flag list.
7. Tests (tests/cli/test_cli.sh update block; FR-SU-12 seams, no live
   registry): newer via `CC_LATEST_VERSION=99.0.0` -> handoff line printed
   (spawn may fail in CI without the published version - assert the
   handoff/WARN sequence and that a guarded child skips: run with BOTH
   `CC_LATEST_VERSION=99.0.0` and `CC_SELFUPDATE_DONE=1` -> no handoff,
   normal update); equal version -> silent, normal update; unreachable
   registry (`CC_REGISTRY_URL=https://127.0.0.1:9` with low timeout) ->
   WARN + normal update completes; `--no-self-update` with
   `CC_LATEST_VERSION=99.0.0` -> no handoff, no staleness line; `--check`
   with newer -> staleness line present, no re-exec, tree unchanged.
8. Docs (`docs/getting-started.md`): self-update default, the flag, and the
   note that update now makes one optional HTTPS request (was fully
   offline).

## Integration seams

- You guarantee: `lib/update.js` still execs `update.sh` unchanged and
  passes exit codes through; all new behavior is driver-side and
  env/flag-gated.
- You may assume: `update.sh`, `manifest.py`, and the engine behave per
  their shipped contracts; `PKG.version` is the running version.

## Definition of Done

- [ ] Every FR-SU-01..12 implemented and tested, or explicitly deferred
      with reason
- [ ] Both real suites green, run yourself: `python3 -m unittest discover
      -s tests/hooks -q` AND `npm test`
- [ ] Manual transcripts: equal-version run (silent), forced-newer run
      (handoff line), unreachable-registry run (WARN + completes),
      `--no-self-update` run (silent, no network)
- [ ] Zero edits outside owned paths; engine untouched
- [ ] Tests never touch the live registry
- [ ] `lib/MODULE.md` updated with the self-update contract
- [ ] Report per `company/templates/REPORT-TEMPLATE.md` with 1-3 proposed
      single-line verbatim witness markers
- [ ] DO NOT COMMIT - leave all work uncommitted in the worktree; the CEO
      stages and lands the commit

## Fallback assumptions

- OQ-SU-01 version compare -> JS-side mirror of _vercmp. Tag
  `// OQ-SU-01 assumption`.
- OQ-SU-02 global installs -> re-exec via npx for everyone; guidance line
  only when npx is absent; NEVER npm i -g from the driver. Tag
  `// OQ-SU-02 assumption`.
- OQ-SU-03 test seams -> `CC_LATEST_VERSION` (bypass network),
  `CC_REGISTRY_URL`, `CC_REGISTRY_TIMEOUT_MS`. No tag needed (structural).
- OQ-SU-04 timeout -> 2000ms default, env-overridable. Tag
  `// OQ-SU-04 assumption`.
- OQ-SU-05 re-exec vehicle -> `npx -y claude-company@<latest> update
  <args>` + `CC_SELFUPDATE_DONE=1`; spawn failure falls through open. Tag
  `// OQ-SU-05 assumption`.
- OQ-SU-06 flag scope -> `--no-self-update` skips the network call too.
  Tag `// OQ-SU-06 assumption`.

## Out of scope

- Running `npm install -g` from the driver
- A standalone self-update/upgrade subcommand
- Any change to update.sh / manifest.py / payload_paths.sh / install.sh /
  package.json
- Self-update on `install`
- Private registries, auth, caching the registry answer
- CLI downgrade paths; native Windows

## Report back

Facts: what changed (paths), both suite outputs pasted, FR-SU checklist,
ownership diff summary, the four manual transcripts, deviations + why, 1-3
proposed single-line verbatim witness markers, worries. Tracking issue: #59.
