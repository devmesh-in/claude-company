# SPEC: claude-company update self-updates the CLI first

_Type: feature. Author: product-manager. Date: 2026-07-15._
_Status: SPEC-READY._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

Extends the shipped `spec-cli-update.md` (the `update` subcommand + provenance
manifest + disposition engine). Reuses its vocabulary; does NOT re-spec the
engine, the matrix, the manifest, or the `.new` / backup behavior - all of that
is unchanged. This feature adds one layer in front of the existing flow.

## Part 1 - Product requirements

### Problem

`claude-company update <project>` refreshes an installed project to the payload
that THIS running copy of the CLI ships. But the running copy is often not the
newest published one, for two field-common reasons:

1. **npx serves a stale cache.** `npx claude-company update .` does not always
   fetch the latest published version; npx may run a previously cached copy. The
   user believes they are pulling the newest hooks and canon, and silently get
   an older payload.
2. **A global install goes stale.** A developer who ran `npm install -g
   claude-company` months ago has an old binary; `claude-company update` refreshes
   the project only to that old binary's payload.

So the command whose entire job is "get current" can hand back stale files while
reporting success. The owner ruled (2026-07-15) that this makes no sense: if the
running CLI is out of date, `update` must get the CLI current FIRST, then refresh
the project with the new version. The shipped spec put npm self-update out of
scope (`spec-cli-update.md`, Scope > Out); the owner overrode that ruling for
`update` specifically. Tracked as issue #59.

### Goal and success metrics

A user runs `claude-company update <project>` and, if a newer claude-company is
published, the project is refreshed by that newer version - transparently, with
one line announcing the handoff - and if not, the run behaves exactly as it does
today. The command never bricks itself on a network problem: an unreachable
registry means "proceed with what I have", never "fail".

Binary success signals (all must hold):

- `SM-SU-1`: with a resolved latest strictly newer than the running version and
  self-update enabled, `update` re-execs exactly once via
  `npx -y claude-company@<latest> update <original args>`, and the parent returns
  the child's exit code verbatim.
- `SM-SU-2`: with resolved latest equal to the running version, no re-exec
  occurs and the run is byte-for-byte the pre-feature behavior (preflight ->
  target validation -> engine).
- `SM-SU-3`: with the registry unreachable (and no injected latest), `update`
  prints one WARN line and completes the normal update; the currency check alone
  never causes a nonzero exit.
- `SM-SU-4`: `--no-self-update` makes zero registry requests and never re-execs,
  even when a newer version is available.
- `SM-SU-5`: `update --check` against a newer-available registry prints a
  staleness line, writes nothing to the target, never re-execs, and exits 0.
- `SM-SU-6`: `npm test` and the engine suites (`tests/install/test_update.sh`,
  `run_tests.sh`) stay green; `update.sh` and manifest determinism are untouched.

### Users and personas

- **npx updater (primary).** Runs `npx claude-company update .`, expecting the
  newest payload, unaware npx may be serving a cached older CLI.
- **Global-install updater.** Ran `npm install -g claude-company` once; the
  global binary has drifted behind the registry.
- **CI / pinned automation.** Runs update non-interactively, sometimes against a
  deliberately pinned version (`npx claude-company@1.2.3 update .`) and does not
  want a surprise upgrade. Needs a deterministic, offline, no-upgrade path.

No new privilege surface. The one new capability is a single optional outbound
HTTPS GET to the public npm registry.

### User stories and acceptance criteria

- **US-SU-1**: As an npx updater on a cached older CLI, I get the newest payload
  without knowing anything went stale.
  - AC: given the resolved latest is newer than the running version, when I run
    `claude-company update .`, then the CLI prints one handoff line, re-execs
    `npx -y claude-company@<latest> update .`, and my project is refreshed by the
    newer version; the parent exits with the child's code.

- **US-SU-2**: As any updater who is already current, I see no change from today.
  - AC: given the resolved latest equals the running version, when I run update,
    then no network re-exec happens and the normal preflight/engine flow runs.

- **US-SU-3**: As an offline updater, my update still works.
  - AC: given the registry cannot be reached, when I run update, then a single
    WARN line prints ("could not check for a newer claude-company; proceeding
    with <current>") and the normal update completes; exit code reflects the
    engine, not the network.

- **US-SU-4**: As a pinned CI caller, I can forbid the upgrade.
  - AC: given `--no-self-update`, when I run update, then no registry request is
    made and no re-exec occurs, regardless of what is published.

- **US-SU-5**: As a cautious updater, `--check` tells me the CLI is stale without
  changing anything.
  - AC: given the resolved latest is newer, when I run `update . --check`, then
    the plan includes a staleness line, nothing is re-execed or written, and exit
    is 0.

### Functional requirements

Stable IDs. Every FR is later implemented, tested, or explicitly deferred - the
traceability gate checks these IDs against the PR. All new logic lives in the
Node driver `lib/update.js`; the bash engine `update.sh` is unchanged.

- **FR-SU-01**: After argument parse and help handling, and before preflight, the
  driver runs a "CLI currency check": it resolves the latest published version of
  `claude-company` and compares it to the running `PKG.version`.
- **FR-SU-02**: Latest is resolved with Node stdlib `https` GET
  `<registry-base>/claude-company/latest` (default base
  `https://registry.npmjs.org`), reading the `version` field, under a bounded
  timeout. Any failure (offline, timeout, non-200, unparseable body, missing
  `version`) -> print one WARN line and proceed with the current version. The
  check never aborts the run and never changes the exit code by itself.
- **FR-SU-03**: When latest is strictly newer than current AND self-update is
  enabled AND `--check` is not set AND `CC_SELFUPDATE_DONE` is unset AND npx is
  available, the driver self-updates by re-execing
  `npx -y claude-company@<latest> update <original args unchanged>`, with
  `CC_SELFUPDATE_DONE=1` set in the child environment, streaming the child's
  stdio, and returns the child's exit code verbatim. The parent does no further
  work - it does NOT then run its own preflight or engine.
- **FR-SU-04**: The re-exec happens at most once per invocation chain.
  `CC_SELFUPDATE_DONE=1` in the child env makes the child skip its own currency
  check entirely (FR-SU-08), so the child never re-execs again even if the
  registry answer is inconsistent.
- **FR-SU-05**: Before re-execing, the driver prints exactly one line announcing
  the handoff (e.g. "claude-company <current> is out of date; updating to
  <latest> first..."). Beyond that line, the child's normal update output is the
  user's whole experience - the handoff is otherwise transparent.
- **FR-SU-06**: `--no-self-update` skips the entire currency check: no registry
  request, no re-exec, no staleness line. The run proceeds with the current CLI
  directly into preflight/engine.
- **FR-SU-07**: `--check` performs the currency check and reports CLI staleness in
  the plan (a line naming current and the newer latest) but never re-execs and
  never installs. It still forwards `--check` to the engine, so the target tree
  stays byte-for-byte unchanged and exit is 0.
- **FR-SU-08**: When latest equals or is older than current, or is unresolved, or
  npx is unavailable, or `--no-self-update` is set, or `CC_SELFUPDATE_DONE` is
  already set, the driver falls through to today's behavior unchanged: preflight,
  target validation, `update.sh` run, exit code passthrough.
- **FR-SU-09**: The re-exec forwards the user's ORIGINAL args verbatim (positional
  target, `--target`, `--check`, `--force`, `--no-self-update`, style flags), so
  the child runs precisely the update the user asked for.
- **FR-SU-10**: For a global (non-npx) caller who was stale, after the npx re-exec
  refreshes the project the driver prints one guidance line noting that running
  `npm install -g claude-company@latest` makes the upgraded CLI permanent. The
  driver itself never runs `npm install -g` (OQ-SU-02).
- **FR-SU-11**: `update --help` documents `--no-self-update` and the self-update
  behavior; `lib/update.js` `parseArgs` accepts `--no-self-update`; the top-level
  help in `bin/claude-company.js` lists `--no-self-update` in the update flag line.
- **FR-SU-12**: Test/override seams: `CC_REGISTRY_URL` overrides the registry
  base; `CC_REGISTRY_TIMEOUT_MS` overrides the timeout; `CC_LATEST_VERSION`, when
  set, is used as the resolved latest version with NO network call. These let
  tests simulate newer / equal / unreachable deterministically. No test depends on
  live registry state.

### Business rules and validations

- **BR-SU-01**: "stale" means the version compare returns latest strictly newer
  than current. Equal or older -> not stale -> no self-update. (An older-than-
  current registry answer is treated as not stale, never as a downgrade trigger.)
- **BR-SU-02**: Self-update proceeds only when ALL hold: stale; `--no-self-update`
  not set; `--check` not set; `CC_SELFUPDATE_DONE` unset; npx present. Any one
  false -> no re-exec, fall through to FR-SU-08.
- **BR-SU-03**: The currency check fails OPEN. Registry failure of any kind ->
  WARN and proceed with the current version. The check never yields a nonzero
  exit and never aborts the update on its own.
- **BR-SU-04**: A set `CC_SELFUPDATE_DONE` is authoritative: the driver treats
  currency as already handled and skips the check unconditionally. The child
  inherits `CC_SELFUPDATE_DONE=1`.
- **BR-SU-05**: On re-exec, the parent's exit code equals the child's verbatim
  (0 ok even when `.new` files were written, 1 usage, 2 preflight/target, 3 write
  failure, 4 downgrade refused). A child SPAWN failure (npx cannot be launched)
  -> WARN and fall through to running the current CLI's normal update (fail open),
  NOT a hard error.
- **BR-SU-06**: The version compare mirrors `lib/manifest.py` `_vercmp` semantics
  (dotted fields; numeric where both fields are ints, else lexical; missing fields
  count as 0), so the driver and the engine's downgrade guard agree on ordering.
- **BR-SU-07**: None of this behavior is money, pricing, legal, or go-live, so it
  is not an owner escalation. Default is to self-update (the owner's 2026-07-15
  ruling); `--no-self-update` is the documented opt-out.

### Scope

**In:**
- A CLI currency check in `lib/update.js`: resolve latest from the npm registry
  (Node `https`, bounded timeout, fail open) and compare to the running version.
- Self-update-then-re-exec exactly once via `npx -y claude-company@<latest>
  update <original args>`, guarded by `CC_SELFUPDATE_DONE`, parent returns the
  child exit code.
- `--no-self-update` (skip the whole step) and `--check` (report staleness only).
- A guidance line for global-install callers pointing at `npm install -g`.
- Test/override env seams (`CC_REGISTRY_URL`, `CC_REGISTRY_TIMEOUT_MS`,
  `CC_LATEST_VERSION`) and driver-level tests.
- Help + docs updates for the new flag and behavior.

**Out:**
- **Running `npm install -g claude-company@latest`** from the driver. That mutates
  system state outside the target (may need sudo); update stays side-effect-free
  outside the project. Global users get a guidance line only (OQ-SU-02).
- **A standalone `self-update` / `upgrade` subcommand.** The owner folded this into
  `update`; no new verb.
- **Changing the disposition engine.** `update.sh`, the matrix, the manifest, the
  `.new`/backup behavior, and the downgrade guard are untouched. Self-update wraps
  the engine, it does not modify it.
- **Self-update on `install`.** Only `update` gets current; `install` is unchanged.
- **Private registries, scopes, or registry auth** beyond the `CC_REGISTRY_URL`
  base override.
- **Caching or persisting the registry answer** between runs. Each run resolves
  fresh (or skips via `--no-self-update`).
- **Downgrading the CLI.** Self-update only moves forward; it never installs an
  older CLI than the one running.
- **Extra supply-chain verification** of the child package beyond npm's own. No
  signature/integrity check is added in v1.
- **Native Windows.** Same WSL-only posture as `install` / `update`.

### UX notes

- **Stale + self-update (default).** One line: "claude-company <current> is out of
  date; updating to <latest> first..." then the child's normal update output
  (preflight, plan/apply, report). Nothing else from the parent.
- **Current.** No staleness line; identical to today's `update`.
- **Offline / registry down.** One WARN line: "could not check for a newer
  claude-company; proceeding with <current>." Then the normal update.
- **`--check` + stale.** The plan carries a line like "CLI: <current> (a newer
  <latest> is published - re-run update to upgrade first)"; header still states no
  changes were written.
- **`--no-self-update`.** Silent on currency; goes straight to the normal update.
- **Global-install guidance.** After the re-exec, one line: "tip: `npm install -g
  claude-company@latest` makes this upgrade permanent for the global CLI." Shown
  only when the caller looks like a global install, not npx.

## Part 2 - Build readiness (the bridge from PRD to buildable)

- **Owned directories / files:** `lib/update.js` (the currency check, registry
  resolver, version compare, and re-exec - all new logic lives here);
  `bin/claude-company.js` (add `--no-self-update` to the update flag help line
  only); `tests/cli/test_cli.sh` and a driver-focused block (the network + re-exec
  live in JS, so new coverage is Node-driven, not engine bash - inject via the
  FR-SU-12 env seams); `docs/` (document self-update + `--no-self-update`). No new
  packed file: `update.sh` is unchanged, so `package.json` `files` and
  `prepublishOnly` need no change. One workstream, one tech lead - directory-
  disjoint from other in-flight work (STATUS shows only this spec in flight).

- **Invariants in play:**
  - Zero third-party dependency - Node stdlib `https` and `child_process` only
    for the registry call and re-exec; no fetch polyfill, no semver package.
  - Fail open on the currency check - registry uncertainty resolves toward
    completing the update with the current version, never toward aborting. Note
    the two distinct fail directions in this codebase: the engine `update.sh`
    fails toward PRESERVING user files (unchanged here); the currency check fails
    toward PROCEEDING with the current CLI.
  - Node >= 16 floor - already enforced in `bin/claude-company.js`; `https` and
    `spawnSync` are available there.
  - Determinism of install/manifest output - untouched; self-update writes no
    manifest and no target files (the child engine still does).
  - macOS bash 3.2 / python3 3.8 - unaffected; self-update is pure Node.
  - Dual-nature rule - CLI machinery in `bin/` and `lib/`, not `company/` canon;
    ships in the npm package, no real gate commands enter `company/`.

- **Frozen surfaces touched:** None. `frozen-surfaces.json` `surfaces` is empty
  and the `always` list does not match `lib/update.js` or `bin/claude-company.js`;
  no hook blocks the build. `update.sh` (whose contract the shipped feature
  relies on) is NOT modified. The earlier CR-UPD-1 froze
  `install-manifest.json` + `.update-backups/**` and is unaffected. `lib/update.js`
  and the CLI arg parser are load-bearing, parity-tested surfaces (via
  `tests/cli/test_cli.sh`) - the build must preserve their existing contracts
  (existing `install`/`update` behavior unchanged except the added currency layer
  and the new flag). **No new CR required.**

- **Data model impact:** None. No new files, no manifest schema change. The
  registry response is read once in memory and never persisted.

- **Contracts impact:**
  - New flag `--no-self-update` on `update` (additive; all existing flags and exit
    codes unchanged).
  - New internal loop-guard env var `CC_SELFUPDATE_DONE`, and test/override seams
    `CC_REGISTRY_URL`, `CC_REGISTRY_TIMEOUT_MS`, `CC_LATEST_VERSION` (additive;
    `--no-self-update` is the only user-facing surface, the rest are documented in
    a driver comment and the test file).
  - Exit-code contract unchanged (0/1/2/3/4); on re-exec the code is the child's,
    drawn from the same set.
  - **New outbound network dependency (behavior change):** `update` previously ran
    fully offline; it now makes ONE optional HTTPS GET to the npm registry per run.
    Mitigated by fail-open (BR-SU-03) and `--no-self-update` for offline / pinned
    callers. Call this out in the docs and the delivery report.

- **Open questions and chosen fallbacks:**
  - **OQ-SU-01**: Version compare in JS, or shell out to `lib/manifest.py vercmp`?
    FALLBACK: **JS-side compare in the driver**, mirroring `manifest.py` `_vercmp`
    semantics (BR-SU-06) - keeps the driver self-contained and avoids a python3
    subprocess in the hot path. The engine keeps using `manifest.py vercmp` for its
    own downgrade guard. Tag the site `// OQ-SU-01 assumption`.
  - **OQ-SU-02**: Global-install callers - also run `npm install -g
    claude-company@latest`, or re-exec via npx and guide? FALLBACK: **re-exec via
    `npx -y claude-company@<latest>` for BOTH caller kinds** (uniform, no system
    mutation) and print one `npm install -g` guidance line for global callers; the
    driver never runs `npm install -g` itself. Tag `// OQ-SU-02 assumption`.
  - **OQ-SU-03**: How do tests avoid the live registry? FALLBACK: **`CC_LATEST_VERSION`
    injects a resolved latest with no network call; `CC_REGISTRY_URL` redirects the
    base to a dead/local host to simulate unreachable.** Tests set these; none reads
    live registry state (FR-SU-12). Tag `// OQ-SU-03 assumption`.
  - **OQ-SU-04**: Registry timeout value (a magic number). FALLBACK: **default 2000
    ms, overridable via `CC_REGISTRY_TIMEOUT_MS`**, derived from the fail-open-fast
    principle - the ceiling before an offline user perceives a hang - not an
    arbitrary threshold. On timeout -> WARN + proceed (BR-SU-03). Tag
    `// OQ-SU-04 assumption`.
  - **OQ-SU-05**: What the re-exec spawns. FALLBACK: **`npx -y
    claude-company@<latest> update <original args>`** with `CC_SELFUPDATE_DONE=1` in
    the child env; parent returns the child's code verbatim; npx-absent or spawn
    failure -> WARN + fall through to the current CLI (BR-SU-05). Tag
    `// OQ-SU-05 assumption`.
  - **OQ-SU-06**: `--no-self-update` - skip only the re-exec, or the whole network
    check? FALLBACK: **skip the entire step** (no registry request at all) so CI /
    pinned callers get a fully offline, deterministic path (FR-SU-06). Tag
    `// OQ-SU-06 assumption`.
  - None of these are money, pricing, legal, or go-live questions, so none is an
    owner escalation. Every fallback is safe to build on now; the owner may veto
    any later via `DECISIONS.md`.

- **Verification plan:** Node-driven tests in `tests/cli/test_cli.sh` (the network
  and re-exec live in JS; the engine bash suite stays as-is), run by `npm test`,
  using the FR-SU-12 seams. To assert the re-exec target without a network, the
  test sets `CC_LATEST_VERSION` high and stubs npx on `PATH` with a recording shim
  (a tiny script that echoes its argv and exits 0), so the test can prove the
  child command line and the `CC_SELFUPDATE_DONE` env without hitting the registry.
  - FR-SU-01/03/05/09 + SM-SU-1: `CC_LATEST_VERSION` newer + npx shim -> driver
    prints the handoff line and invokes `npx -y claude-company@<latest> update
    <args>` with `CC_SELFUPDATE_DONE=1`; parent returns the shim's exit code.
  - FR-SU-04/08 + BR-SU-04: with `CC_SELFUPDATE_DONE=1` preset, no currency check
    and no re-exec occur (the shim is never called); the engine path runs.
  - FR-SU-08 + SM-SU-2: `CC_LATEST_VERSION` equal to the running version -> no
    re-exec; normal preflight/engine flow (assert the shim is not called).
  - FR-SU-02 + BR-SU-03 + SM-SU-3: `CC_REGISTRY_URL` at a dead host, no
    `CC_LATEST_VERSION` -> one WARN line, the update still completes, exit reflects
    the engine (against a real temp install).
  - FR-SU-06 + SM-SU-4: `--no-self-update` with `CC_LATEST_VERSION` newer -> shim
    never called and (with a network-observing shim) no registry request made.
  - FR-SU-07 + SM-SU-5: `--check` with `CC_LATEST_VERSION` newer -> staleness line
    printed, shim not called, target byte-identical, exit 0.
  - BR-SU-05: npx removed from `PATH` (or shim exits nonzero on spawn) -> WARN and
    fall through to the current CLI's normal update; a shim that exits 4 -> parent
    exits 4.
  - BR-SU-06 / OQ-SU-01: unit-check the JS version compare on
    equal / newer / older / missing-field cases, matching `manifest.py _vercmp`.
  - FR-SU-11: `update --help` documents `--no-self-update`; top-level help lists it
    in the update flag line; `parseArgs` accepts it and rejects unknown flags.
  - SM-SU-6: `npm test`, `tests/install/test_update.sh`, and `run_tests.sh` stay
    green; assert `update.sh` and `lib/manifest.py` are byte-unchanged by the diff.

## Options considered

Divergence ran 10 candidate directions across four pattern categories (assumption
challenge, SCAMPER, inversion, perspective multiplication). Convergence criteria:
honors the owner's override, zero-dependency fit, fail-open safety, cost to
operate, offline behavior, and reversibility. Survivors:

| # | Option | Reasoning | Production risks | Trade-offs |
|---|---|---|---|---|
| 1 | **Driver currency check + one guarded npx re-exec** (registry GET, compare, re-exec `npx -y claude-company@<latest> update <args>` with a loop-guard env) | Only a runtime registry read can distinguish a stale npx cache / old global binary from a current one; `npx@<latest>` upgrades both caller kinds uniformly; the loop guard bounds it to one hop; fail-open keeps offline users working. Pure Node stdlib. | New outbound network call per run; a pinned invocation upgrades unless opted out. Both mitigated (fail-open + `--no-self-update`). | One HTTPS GET added to a formerly-offline command. |
| 2 | **Unconditional `npx -y claude-company@latest update ...`** re-exec, no registry lookup | Simplest - no `https` code; let npx resolve `@latest`. | Re-execs on EVERY run even when current; breaks offline entirely (npx must reach the registry); adds latency; `--check` cannot report staleness without the version; npx cache can still serve stale under `@latest`. | Less code, much worse to operate and offline-hostile. |
| 3 | **Detect + refuse/warn only** (assumption challenge: does update need to self-update at all?) - print a loud "your CLI is stale, run `npm i -g ...`" and refresh with current bytes | Zero re-exec machinery; user stays in control of their toolchain version. | Fails the owner's explicit ruling: `update` still hands back stale payload. Leaves the core problem unsolved for npx users who have no global to upgrade. | Safest mechanically, but does not do the job the owner asked for. |

**Winner: Option 1.** It is the only survivor that actually gets the CLI current
(the owner's requirement) while staying zero-dependency, fail-open, and bounded to
a single re-exec. Option 3 was the honest assumption-challenge alternative and is
what the shipped spec chose - the owner overrode it. Option 2 fails offline and
wastes a re-exec on every already-current run.

**Strongest rejected option: Option 2 (unconditional npx@latest re-exec).** It
keeps winning on simplicity - no registry client, no version compare. It loses on
cost to operate and fail-open: it turns every `update`, including the common
already-current case, into a network round-trip through npx, and it cannot run
offline at all, whereas Option 1 degrades to today's offline behavior. If the
registry client ever proves flaky enough that the compare is the failure source,
reopen this: gating the re-exec behind `@latest`-with-a-preflight-ping is the
fallback simplification.

## Spec-ready checklist (the Phase 0 gate)

- [x] Every FR has a stable ID and at least one acceptance criterion (FR-SU-01..12
  mapped to US-SU-1..5, SM-SU-1..6, and the verification plan).
- [x] Out-of-scope is explicit (Scope > Out: nine exclusions).
- [x] Every open question has a single decided fallback (OQ-SU-01..06).
- [x] Owned directories are named and disjoint from other in-flight work (STATUS
  shows only cli-self-update in flight).
- [x] Frozen-surface needs are identified: none touched; no CR required
  (CR-UPD-1 unaffected; engine `update.sh` unmodified).
- [x] Data/contract impact stated (no data model change; additive flag + env
  seams; one new outbound network call flagged as a behavior change).
- [x] Verification plan covers every FR (mapping listed under Verification plan;
  network + re-exec asserted via the FR-SU-12 seams and a recording npx shim).

## Part 3 - Brief handoff

Derive the brief with `company/templates/BRIEF-TEMPLATE.md`. The brief links this
spec; it does not embed it. Read-first for the builder: the project `CLAUDE.md`,
`lib/update.js` (the current driver - preflight, target validation, engine
spawn), `bin/claude-company.js` (the `update` route and help text),
`lib/install-tui.js` `_shared` (PROBES incl. the npx probe, `validateTarget`,
EXIT codes), `lib/manifest.py` (`_vercmp` semantics to mirror), `update.sh` (the
engine - read-only context, not modified), `tests/cli/test_cli.sh`. No CR needed;
`update.sh` and the frozen registry stay untouched.
