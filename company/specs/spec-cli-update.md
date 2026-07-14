# SPEC: claude-company update subcommand

_Type: feature. Author: product-manager. Date: 2026-07-15._
_Status: SPEC-READY._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

## Part 1 - Product requirements

### Problem

A project installs claude-company once, then the package keeps shipping new
hooks, skills, agents, and canon docs. Today the only way to pull those in is to
re-run `install`, whose `copy_tree_overwrite` blindly overwrites every payload
file in place. That is fine for a pristine install and destructive for a real
one: agent and skill prompt files, `run-gates.sh`, and canon docs are exactly
the files a team edits to fit their project, and a blind overwrite silently
erases those edits with no warning, no backup, and no record of what changed.

Two structural gaps make a safe update impossible right now:

1. **No provenance.** Nothing written at install time records which version was
   installed or what the shipped files hashed to. So an updater cannot tell a
   pristine file from an older version (safe to overwrite) apart from a file the
   user customized (must not clobber).
2. **No update path at all.** `install` and its TUI are the only entry points;
   there is no `update` verb, no dry run, no report of what an upgrade would do.

The cost is concrete: a user who tuned three agent prompts and re-runs the
installer to get a new hook loses the three prompts with no way to notice or
recover. The owner has stated blind overwrite is unacceptable. The team needs a
first-class `update` that refreshes the shipped payload while treating every
file the user may have touched as sacred until proven pristine.

### Goal and success metrics

A user runs `claude-company update <project>` and:

- Every payload file they never touched is refreshed to the packaged version.
- Every payload file they modified is left exactly as-is, with the new upstream
  version placed beside it for review, and named in an end-of-run report.
- Nothing they own (gate config, specs, briefs, state) is overwritten.
- A backup of every file the update replaced exists for rollback.

Binary success signals (all must hold):

- `SM-1`: On a pristine install, update overwrites 100% of payload files to the
  packaged content and writes zero `.new` files.
- `SM-2`: On an install with a modified agent prompt, that file's bytes are
  unchanged after update, and exactly one `<file>.new` exists with the packaged
  content.
- `SM-3`: On a pre-manifest (bootstrapping) install, update overwrites zero
  files whose provenance it cannot prove, and clobbers nothing.
- `SM-4`: `update --check` writes zero bytes to the target and prints the same
  disposition it would apply.
- `SM-5`: `npm test` stays green, including the existing bin-vs-bare install
  parity test (the new manifest is byte-identical across two installs).

### Users and personas

- **Updater (primary).** A developer who already ran install in their project
  and wants the latest hooks/skills/agents/canon. Runs the CLI from a shell with
  write access to the project. No claude-company internals knowledge assumed.
- **Customizer.** An updater who has edited one or more payload files (an agent
  prompt, `run-gates.sh`, a canon doc) and needs those edits preserved.
- **CI / automation.** A non-interactive caller that runs update with `--yes`
  or `--plain` and reads the exit code and printed report. No TTY, no prompts.

All three operate on their own project tree with normal filesystem permissions.
No new privilege surface is introduced.

### User stories and acceptance criteria

- **US-UPD-1**: As an updater with an untouched install, I can run
  `claude-company update .` and get every shipped file refreshed with no prompts.
  - AC: given a target whose payload files all match the recorded manifest
    hashes, when I run update, then every such file is overwritten with the
    packaged version, the report shows them under "updated", and no `.new` file
    is written.

- **US-UPD-2**: As a customizer, I can run update and keep my edited files.
  - AC: given `.claude/agents/tech-lead.md` was edited after install (its hash
    differs from the manifest baseline and from the packaged version), when I run
    update, then `tech-lead.md` bytes are unchanged, `tech-lead.md.new` is created
    with the packaged content, and the report lists `tech-lead.md` under
    "preserved (review .new)".

- **US-UPD-3**: As a cautious updater, I can preview an update before applying.
  - AC: given any install state, when I run `claude-company update . --check`,
    then the target tree is byte-for-byte unchanged (no writes, no `.new`, no
    backup dir), and the printed plan lists the disposition each file would get.

- **US-UPD-4**: As an updater on an install made before manifests existed, my
  first update never clobbers a file it cannot prove pristine.
  - AC: given a target with no `company/state/install-manifest.json`, when I run
    update, then any payload file whose hash does not equal the packaged hash is
    preserved with a `.new` sibling, and only files already at the packaged hash
    are treated as up to date.

- **US-UPD-5**: As an updater, I can recover the prior files after a bad update.
  - AC: given update overwrote or replaced N files, when it finishes, then a
    directory `company/state/.update-backups/<UTC-timestamp>/` contains the prior
    content of exactly those N files at their original relative paths, and the
    report prints that directory path.

### Functional requirements

Stable IDs. Every FR is later implemented, tested, or explicitly deferred - the
traceability gate checks these IDs against the PR.

- **FR-UPD-01**: The CLI (`bin/claude-company.js`) gains an `update` subcommand
  alongside `install` / `help` / `--version`, invoked as
  `claude-company update [target] [flags]`. It reuses the install Windows guard:
  on `win32` it prints the same WSL guidance and exits 2.
- **FR-UPD-02**: `install` writes a manifest at
  `company/state/install-manifest.json` recording the package version and the
  sha256 of every payload file the installer overwrites in place (the
  `copy_overwrite` / `copy_tree_overwrite` set: `.claude/agents`,
  `.claude/hooks` `*.py`, `.claude/skills`, `ORCHESTRATOR.md`, the `company/*.md`
  canon docs, `company/run-gates.sh`, `company/templates`). The manifest is
  byte-deterministic: package version plus a path-sorted map of relpath to
  sha256, and no wall-clock or environment-varying field.
- **FR-UPD-03**: `update` reads the packaged version, reads the target manifest
  if present, hashes the corresponding target files, and applies the per-file
  disposition matrix (BR-UPD-01 through BR-UPD-08).
- **FR-UPD-04**: A payload file that is pristine (target hash equals the manifest
  baseline hash) or missing at the target is overwritten / restored to the
  packaged version.
- **FR-UPD-05**: A payload file that is user-modified (hash differs from both the
  manifest baseline and the packaged version) is preserved in place, and the
  packaged version is written beside it as `<path>.new`. A pre-existing `.new`
  from an earlier update is overwritten by the newer packaged content.
- **FR-UPD-06**: A payload file already at the packaged hash is left unchanged
  and counted as "unchanged" (no write, no `.new`, no backup entry).
- **FR-UPD-07**: The `copy_if_absent` set (`company/gates.config`,
  `company/frozen-surfaces.json`, `company/models.json`) and all user work and
  state (`company/specs`, `company/briefs`, `company/change-requests`,
  `company/state/STATUS.md`, `RESUME.md`, `WORRIES.md`, `DECISIONS.md`, the logs)
  are never overwritten by update. A missing scaffold from that set may be
  restored (write-if-absent), matching install semantics.
- **FR-UPD-08**: `update` re-runs the same idempotent merges install uses for
  `.claude/settings.json` (hook and permission-deny union), `.mcp.json` (server
  union), and the `CLAUDE.md` claude-company marked block (replace-in-place).
  These paths never produce a `.new` file.
- **FR-UPD-09**: Before overwriting or replacing any file (including merge-path
  files it rewrites and pristine files it overwrites), update copies the prior
  target content into `company/state/.update-backups/<UTC-timestamp>/<relpath>`.
  Files it leaves untouched are not backed up.
- **FR-UPD-10**: After a successful apply, update rewrites
  `company/state/install-manifest.json` to the packaged version and the packaged
  file hashes, so the next update has a correct baseline.
- **FR-UPD-11**: `update --check` computes and prints the full plan (disposition
  per file) and writes nothing to the target - no file overwrite, no `.new`, no
  backup dir, no manifest rewrite. Exit 0.
- **FR-UPD-12**: When the target has no manifest, update runs safe mode
  (BR-UPD-06): files already at the packaged hash are unchanged; every other
  payload file is treated as modified (preserved, `.new` written).
- **FR-UPD-13**: When the target manifest version is greater than the packaged
  version (a downgrade), update refuses and exits non-zero with an explanatory
  message unless `--force` is passed (BR-UPD-07). With `--force`, it still only
  overwrites pristine files and writes `.new` for modified ones.
- **FR-UPD-14**: On completion, update prints a report containing: the version
  transition (`<from> -> <to>`, or `unknown -> <to>` in bootstrapping); counts of
  updated / preserved / restored / unchanged; the list of `.new` conflict paths;
  and the backup directory path (or a note that nothing was backed up).
- **FR-UPD-15**: `claude-company update --help` documents the subcommand and its
  flags, and the top-level help text lists `update`.
- **FR-UPD-16**: `update` runs non-interactively (a plain report, no animated
  TUI). It honors `--target DIR`, `-y/--yes`, `--plain`, `--no-color`, `--check`,
  and `--force`. It exits 0 on any successful update - including when `.new`
  conflict files were written - and non-zero only on usage error, target/preflight
  failure, or a hard write failure. It reuses the installer preflight (python3,
  git, bash are hard-required) and target validation.

### Business rules and validations

The disposition matrix is the heart of update. It is applied per payload file in
the manifest-covered set. `baseline` = the file's sha256 recorded in the target
manifest; `packaged` = the sha256 of the file this package version ships;
`target` = the current sha256 of the file on disk.

- **BR-UPD-01**: target file missing -> restore (write packaged; back up nothing;
  count "restored").
- **BR-UPD-02**: `target == packaged` -> unchanged (no write; count "unchanged").
- **BR-UPD-03**: `target == baseline` and `target != packaged` -> pristine ->
  back up the file, overwrite with packaged (count "updated").
- **BR-UPD-04**: `target != baseline` and `target != packaged` -> user-modified
  -> keep the file, write `<path>.new` with packaged content (count "preserved").
- **BR-UPD-05**: `copy_if_absent` files and user work/state files are never
  overwritten by update: present -> keep untouched; absent -> write-if-absent
  (restore scaffold). These are not in the manifest and never get a `.new`.
- **BR-UPD-06**: no manifest baseline available (bootstrapping, or a path absent
  from the manifest): if `target == packaged` apply BR-UPD-02, else apply
  BR-UPD-04. Never overwrite in this state.
- **BR-UPD-07**: `manifest.version > package.version` -> refuse the whole update
  and exit non-zero unless `--force` is set.
- **BR-UPD-08**: `.claude/settings.json`, `.mcp.json`, and the `CLAUDE.md`
  marked block always take the idempotent merge/replace path (FR-UPD-08); they
  are never subject to the hash matrix and never produce a `.new`. They are
  backed up before rewrite per FR-UPD-09.

Validation notes: hashing is sha256 computed with python3 stdlib (`hashlib`),
consistent between the install-time writer and the update-time reader so a
pristine file always matches. The manifest is JSON parsed defensively - a
missing, empty, or unparseable manifest is treated as "no baseline"
(bootstrapping), never as an error that aborts.

### Scope

**In:**
- A new `update` subcommand that refreshes the shipped payload provenance-aware.
- An install-time manifest (path + sha256 + version) written by `install`, and
  rewritten by `update`.
- The disposition matrix, `.new` siblings, backups, `--check`, `--force`, the
  downgrade guard, the bootstrapping safe mode, and the end-of-run report.
- Re-running the settings.json / .mcp.json / CLAUDE.md merges on update.
- Tests covering every FR and the parity-preserving determinism of the manifest.

**Out:**
- **Three-way text merge** of a user's edits with upstream changes. Modified
  files get a `.new` for manual reconciliation; update never merges prose or code.
- **Self-update of the npm package itself** (`npm i -g claude-company@latest`).
  npm owns that; update only refreshes an already-installed project's payload.
- **An interactive/animated TUI for update.** v1 is a plain report. The install
  TUI is untouched.
- **Gate auto-detection on update.** update never reads or writes
  `gates.config`; gate config stays user-owned (OQ-UPD-08).
- **Auto-pruning of backups.** Backups accumulate under
  `company/state/.update-backups/`; the user prunes them (OQ-UPD-07).
- **Native Windows.** Same WSL-only posture as install.
- **Migrating or transforming user content** (rewriting old specs/state to new
  formats). update refreshes shipped files only; it does not touch user artifacts.

### UX notes

- **Ready / applied state.** Plain, line-per-disposition output in install's
  house style, ending in the report block: version transition, four counts, the
  `.new` list (each with its path so the user can `diff` it against the kept
  file), and the backup dir path.
- **Empty state (nothing to do).** When the target is already at the packaged
  version with no drift, update prints "already up to date at <version>" and exits
  0 without writing a backup dir.
- **Check state.** `--check` prints the same plan with a "would " prefix and a
  header stating no changes were written.
- **Refused state (downgrade).** A single clear line: the installed version is
  newer than the package; re-run with `--force` to proceed, or upgrade the
  package. Exit non-zero.
- **Conflict microcopy.** For preserved files: "kept your <path>; packaged
  version written to <path>.new - review and reconcile." No claim that anything
  was merged.

## Part 2 - Build readiness (the bridge from PRD to buildable)

- **Owned directories / files:** `bin/` (add the `update` route + top-level
  help line), `lib/` (new update driver, e.g. `lib/update.js`; new shared
  `lib/manifest.py` python3 helper for hashing and manifest read/write),
  `install.sh` (emit the manifest after copying), a new engine `update.sh` at
  repo root (mirrors install.sh helper shape, applies the matrix), `tests/cli/`
  and `tests/install/` (new coverage), `docs/` (document the subcommand),
  `package.json` (add `update.sh` to the `files` pack list; add the update tests
  to `prepublishOnly`). One workstream, one tech lead - directory-disjoint from
  any other in-flight work (STATUS shows no active tasks).

- **Invariants in play:**
  - Zero third-party dependency - Node stdlib + bash + python3 stdlib only.
  - python3 3.8 stdlib only for any python; bash must run on macOS bash 3.2 (no
    associative arrays, no `readarray`), matching install.sh.
  - **Determinism of install output** - the bin-vs-bare parity test does a raw
    `diff -r` of two installed trees (excluding only `adherence.log`). The
    manifest must be byte-identical across two installs, so it carries no
    timestamp or environment-varying field (FR-UPD-02).
  - **Fail safe, not fail open** - unlike the enforcement hooks, the updater
    resolves every uncertainty toward preserving user work: unknown provenance,
    unreadable manifest, or any doubt -> preserve + `.new`, never overwrite.
  - Dual-nature rule - this is CLI/installer machinery (`bin/`, `lib/`,
    `install.sh`, `update.sh`), not `company/` canon; it ships in the npm package,
    not as generic project payload. No real gate commands enter `company/`.

- **Frozen surfaces touched:** The repo's `frozen-surfaces.json` `surfaces` list
  is empty; the `always` list does not currently match the new manifest or backup
  paths, so no hook blocks the build. One registry change is proposed and gated:
  **CR-UPD-1** - add `company/state/install-manifest.json` and
  `company/state/.update-backups/**` to the `always` frozen list, so these
  machine-written files are edit-guarded (only install/update may write them),
  matching how `gates.status` and `provenance-ledger.json` are already frozen.
  The CR is filed in `company/change-requests/` and applied by the CEO in the
  build PR. `install.sh` and the CLI arg parser are not in the registry but are
  load-bearing, parity-tested surfaces - the build must preserve their existing
  contracts (existing install behavior unchanged except the added manifest write).

- **Data model impact:** One new forward-only JSON artifact,
  `company/state/install-manifest.json`, schema:
  `{ "version": "<pkg version>", "files": { "<relpath>": "<sha256>", ... } }`
  with `files` keys path-sorted. Written by install (new) and update. New backup
  tree `company/state/.update-backups/<UTC-timestamp>/`. No existing schema
  changes; no migration of prior data (absence of the manifest is a valid,
  handled state).

- **Contracts impact:**
  - New CLI subcommand `update` (additive; `install`/`help`/`--version`
    unchanged in behavior, only the top-level help text gains a line).
  - New flags on update: `--check`, `--force`, plus reused `--target`, `-y/--yes`,
    `--plain`, `--no-color`.
  - New shipped file `update.sh` must be added to `package.json` `files` (like
    `install.sh`) or it will not be packed. `lib/manifest.py` ships under the
    already-listed `lib/`.
  - `install.sh` behavior is additive (it now also writes the manifest); the
    bin-vs-bare parity test must remain green (both paths write the same bytes).

- **Open questions and chosen fallbacks:**
  - **OQ-UPD-01**: Engine mechanism - a new `update.sh` bash engine, or a
    `--mode update` flag added to `install.sh`? FALLBACK: a **new `update.sh`**
    that reuses install.sh's helper shape, plus a shared `lib/manifest.py`
    (python3 stdlib) called by both `install.sh` and `update.sh` for hashing and
    manifest read/write. Keeps the well-tested install.sh contract intact.
    Tag sites `// OQ-UPD-01 assumption` / `# OQ-UPD-01 assumption`.
  - **OQ-UPD-02**: Bootstrapping disposition when no manifest exists. FALLBACK:
    **safe mode** (BR-UPD-06) - files at the packaged hash are no-ops, all others
    are preserved with a `.new`; never overwrite. (Strongest rejected refinement:
    a cumulative historical-hashes manifest shipped in the package to recognize
    pristine files from any prior release - see Options considered.)
  - **OQ-UPD-03**: Modified-file disposition - `.new` sibling, prompt, or
    overwrite-with-backup? FALLBACK: **write `<path>.new`, keep the user file**
    (the pacman/dpkg pattern); no prompt, so it works under `--yes` and in CI.
  - **OQ-UPD-04**: Downgrade handling (`manifest.version > package.version`).
    FALLBACK: **refuse unless `--force`**; with `--force`, pristine files are
    overwritten and modified files still get `.new`.
  - **OQ-UPD-05**: Interactive TUI vs plain report for v1. FALLBACK: **plain
    non-interactive report only**; the animated TUI is out of scope.
  - **OQ-UPD-06**: Exit code when `.new` conflicts were written. FALLBACK:
    **exit 0**; the conflict count and paths live in the report text (and
    `--check` output). No new conflict-specific exit code in v1.
  - **OQ-UPD-07**: Backup retention. FALLBACK: **keep all backups** under
    `company/state/.update-backups/<UTC-timestamp>/`; no auto-pruning in v1; the
    report names the dir and the user deletes when done.
  - **OQ-UPD-08**: Does update run gate auto-detection like install? FALLBACK:
    **no** - update never reads or writes `gates.config`; gate config stays exactly
    as the user left it.
  - None of these are money, pricing, legal, or go-live questions, so none is an
    owner-escalation. Every fallback is safe to build on now; the owner may veto
    any later via `DECISIONS.md`.

- **Verification plan:** Bash tests in `tests/install/` and `tests/cli/`
  (matching the existing `run_tests.sh` / `test_cli.sh` style), run by `npm test`:
  - FR-UPD-01/15/16: `update` subcommand exists, `--help` documents it, top-level
    help lists it, unknown flags rejected, exit codes correct.
  - FR-UPD-02 + determinism: install writes a manifest; two independent installs
    produce byte-identical manifests (the existing `diff -r` parity test stays
    green with no new exclusion). Assert manifest schema and that `files` covers
    the overwrite set and excludes copy_if_absent/state files.
  - FR-UPD-04 / BR-UPD-03 (pristine): install, run update against an unchanged
    tree, assert files overwritten to packaged content, zero `.new`, report shows
    "updated".
  - FR-UPD-05 / BR-UPD-04 (modified): install, edit an agent prompt, run update,
    assert the edit survives byte-for-byte and `<file>.new` holds packaged content
    and is listed under "preserved".
  - FR-UPD-06 / BR-UPD-02 (up to date): run update twice; the second run reports
    all "unchanged" and writes no backup dir.
  - FR-UPD-04 / BR-UPD-01 (missing): delete a payload file, run update, assert it
    is restored and reported "restored".
  - FR-UPD-07 / BR-UPD-05: edit `gates.config` and a spec file, run update, assert
    both are untouched and no `.new` is created for them.
  - FR-UPD-08 / BR-UPD-08: add a user hook to settings.json, run update, assert
    the user hook survives and the company hooks are present (merge, not clobber).
  - FR-UPD-09: after an update that overwrote/restored files, assert the backup
    dir contains exactly those prior files at their relpaths.
  - FR-UPD-10: after update, assert the manifest version and hashes equal the
    packaged version's.
  - FR-UPD-11 (check): snapshot the tree, run `--check`, assert the tree is
    byte-identical afterward and the plan lists dispositions.
  - FR-UPD-12 / BR-UPD-06 (bootstrap): install, delete the manifest, edit one
    file, run update, assert the edited file is preserved with `.new` and an
    at-packaged-hash file is a no-op, and nothing is clobbered.
  - FR-UPD-13 / BR-UPD-07 (downgrade): craft a manifest with a higher version,
    run update, assert refusal + non-zero exit; re-run with `--force` and assert
    it proceeds with pristine-only overwrites.
  - FR-UPD-14: assert the report contains the version transition, four counts,
    the `.new` list, and the backup path.

## Options considered

Divergence ran 10 candidate directions across four pattern categories
(assumption challenge, SCAMPER, analogical transfer, inversion). Survivors below;
convergence criteria were client value, production risk, cost to build, cost to
operate, reversibility, and zero-dependency fit.

| # | Option | Reasoning | Production risks | Trade-offs |
|---|---|---|---|---|
| 1 | **Install-time provenance manifest + `.new` siblings** (pacman `.pacnew` / dpkg `.dpkg-dist` pattern, ported) | Only a recorded baseline hash can distinguish a pristine older file from a user edit; the `.new` sibling is the proven, non-interactive, CI-safe way to surface upstream changes without merging. Backups make it reversible. | Bootstrapping installs have no baseline; determinism must be preserved for the parity test. Both handled (safe mode; no timestamp in manifest). | Modified files need manual reconciliation; no auto-merge. |
| 2 | Fold provenance into `install`, no new subcommand | One entry point; less surface. | Conflates first-install (user-wins config) with in-place refresh; risks the well-tested install parity; the owner explicitly asked for an `update` verb. | Simpler CLI, muddier mental model. |
| 3 | Git-diff review - write every packaged file and let `git diff` be the review surface | Zero new machinery; the user already has diff tooling. | Assumes a git-tracked target with a clean tree; destroys uncommitted or untracked user edits; no offline pristine detection; useless in non-git installs. | Cheap, but unsafe exactly where safety is the point. |

**Winner: Option 1.** It is the only survivor that preserves user work without a
baseline of trust it cannot obtain, works offline and non-interactively, and
carries a proven industry precedent. Options 2 and 3 both fail the core
requirement (never clobber a customized file) in common real-world states.

**Strongest rejected option: a cumulative historical-hashes manifest** shipped
inside the package - a map of relpath to the set of sha256 across all prior
releases, so a pristine file from any earlier version (not just the last
install) is recognized and safely overwritten, largely dissolving the
bootstrapping problem. It lost on cost to operate: it requires maintaining and
shipping the full hash history of every release for a product at 0.1.1 with a
single release lineage, and the safe-mode fallback (OQ-UPD-02) already prevents
any data loss on pre-manifest installs - it just downgrades some pristine files
to `.new` conflicts. If bootstrapping false-conflicts become a real complaint as
the release count grows, reopen this: it is the right long-term answer.

## Spec-ready checklist (the Phase 0 gate)

- [x] Every FR has a stable ID and at least one acceptance criterion (FR-UPD-01..16
  mapped to US-UPD-1..5 ACs and to the verification plan).
- [x] Out-of-scope is explicit (Scope > Out: seven exclusions).
- [x] Every open question has a single decided fallback (OQ-UPD-01..08).
- [x] Owned directories are named and disjoint from other in-flight work (STATUS
  shows no active tasks).
- [x] Frozen-surface needs are identified and CRs filed (CR-UPD-1 for the
  `frozen-surfaces.json` `always` additions; install.sh/CLI contracts noted).
- [x] Data/contract impact stated (new manifest + backup artifacts; additive CLI
  subcommand and flags; `update.sh` added to the pack list).
- [x] Verification plan covers every FR (mapping listed under Verification plan).

## Part 3 - Brief handoff

Derive the brief with `company/templates/BRIEF-TEMPLATE.md`. The brief links this
spec; it does not embed it. Read-first for the builder: the project `CLAUDE.md`,
`install.sh`, `bin/claude-company.js`, `lib/install-tui.js` (the `runPlain`,
`parseArgs`, `PROBES`, and `validateTarget` surfaces to reuse),
`tests/cli/test_cli.sh`, `tests/install/run_tests.sh`. The CEO files CR-UPD-1
before the frozen-surfaces.json edit lands.
