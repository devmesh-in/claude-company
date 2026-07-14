# BRIEF: cli-update

_Type: feature. Spec: company/specs/spec-cli-update.md (do not read it - this
brief is your sealed work order). Lead: tech-lead. Date: 2026-07-15._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Give claude-company a first-class `claude-company update [target]` subcommand
that refreshes the shipped payload (hooks, skills, agents, canon docs) in a
project that already ran `install` - while NEVER overwriting a file the user
customized. The hard constraint: every uncertainty resolves toward preserving
user work (preserve + write a `.new` sibling), never toward overwriting. The
enabler is a provenance manifest that `install` starts writing (path -> sha256
+ package version) so `update` can prove a file pristine before touching it.

## Read first (in order)

1. `CLAUDE.md` (project canon - note the dual-nature rule and the two real gate
   suites)
2. `company/METHOD.md` (how the team works)
3. `install.sh` (the copy engine you mirror: copy_overwrite /
   copy_tree_overwrite / copy_if_absent semantics, the settings.json merge)
4. `bin/claude-company.js` (subcommand parse, Windows guard, help text)
5. `lib/install-tui.js` - study the `runPlain`, `parseArgs`, `PROBES`, and
   `validateTarget` surfaces; reuse them, do not fork their logic
6. `tests/cli/test_cli.sh` and `tests/install/run_tests.sh` (test style and the
   bin-vs-bare parity test you must keep green)

## You own

- `bin/claude-company.js` (add the `update` route + top-level help line only)
- `lib/` (new update driver, e.g. `lib/update.js`; new shared `lib/manifest.py`)
- `install.sh` (additive only: emit the manifest after copying)
- `update.sh` (new file, repo root)
- `tests/cli/` and `tests/install/` (new coverage)
- `docs/` (document the subcommand where install is documented)
- `package.json` (ONLY: add `update.sh` to `files`, add update tests to
  `prepublishOnly` if they are a new script)

Nothing else. Anything not listed is read-only to you. If the fix you need
lives outside these paths, report it; do not make it.
`company/frozen-surfaces.json` is CEO-applied per CR-UPD-1 - do NOT edit it.

## Invariants in play (must not break)

- Zero third-party dependency: Node stdlib + bash + python3 stdlib only.
- python3 must run on 3.8 stdlib; bash must run on macOS bash 3.2 (no
  associative arrays, no `readarray`) - match install.sh's style.
- Determinism of install output: the bin-vs-bare parity test does a raw
  `diff -r` of two installed trees (excluding only `adherence.log`). The
  manifest must be byte-identical across two installs: package version plus a
  path-sorted relpath -> sha256 map, NO timestamp and NO environment-varying
  field. A `generated_at` field breaks the suite - this is the tripwire.
- Fail SAFE, not fail open: unknown provenance, unreadable/missing manifest,
  any doubt -> preserve the user file and write `.new`; never overwrite.
- Existing `install` behavior is unchanged except the added manifest write;
  `install` / `help` / `--version` contracts stay intact.
- Dual-nature rule: this is CLI machinery (bin/, lib/, install.sh, update.sh),
  not `company/` canon. No real gate commands enter `company/`.
- All writing hook-clean: straight quotes, ' - ' never em dashes, three dots
  '...' never the ellipsis glyph, no stock AI filler.

## Frozen surfaces nearby (CR, never edit)

- `company/frozen-surfaces.json`: CR-UPD-1 (approved) adds
  `company/state/install-manifest.json` and
  `company/state/.update-backups/**` to the `always` list. The CEO applies
  that edit; you do not touch the registry.
- `company/state/*` in this repo (gates.status, adherence.log, costs.log,
  provenance-ledger.json) are frozen - your engines write manifest/backups in
  TARGET projects at runtime, never in this repo's own company/state/.
- Lockfiles / .env are always frozen.

## Scope (ordered)

1. `lib/manifest.py` (python3 3.8 stdlib): compute sha256 for a file list,
   read/write the manifest JSON
   `{"version": "<pkg>", "files": {"<relpath>": "<sha256>", ...}}` with
   path-sorted keys and deterministic bytes. Shared by install.sh and
   update.sh. (FR-UPD-02)
2. `install.sh`: after the copy phase, write
   `company/state/install-manifest.json` covering exactly the overwrite set
   (the copy_overwrite / copy_tree_overwrite paths: `.claude/agents`,
   `.claude/hooks` `*.py`, `.claude/skills`, `ORCHESTRATOR.md`, the
   `company/*.md` canon docs, `company/run-gates.sh`, `company/templates`).
   Parity test stays green with no new exclusion. (FR-UPD-02)
3. `update.sh`: the engine. Reuses install.sh's helper shape. Per payload file
   apply the disposition matrix (BR-UPD-01..08): missing -> restore ("restored");
   target hash == packaged hash -> no-op ("unchanged"); target == manifest
   baseline and != packaged -> back up then overwrite ("updated"); target !=
   baseline and != packaged -> keep the file, write `<path>.new` with packaged
   content ("preserved"; an older `.new` is overwritten by newer packaged
   content). copy_if_absent files (`gates.config`, `frozen-surfaces.json`,
   `models.json`) and user work/state (specs, briefs, change-requests, state
   files, logs) are NEVER overwritten - present is kept, absent may be restored
   write-if-absent. No manifest at target -> bootstrap safe mode: at-packaged
   hash is a no-op, everything else preserved + `.new`; never overwrite.
   (FR-UPD-03..07, FR-UPD-12)
4. Merge paths: re-run the same idempotent merges install uses for
   `.claude/settings.json`, `.mcp.json`, and the CLAUDE.md marked block; these
   never produce `.new`; back them up before rewrite. (FR-UPD-08)
5. Backups: before any overwrite/replace/rewrite, copy prior content to
   `company/state/.update-backups/<UTC-timestamp>/<relpath>` in the TARGET.
   Untouched files are not backed up. After a successful apply, rewrite the
   manifest to the packaged version + hashes. (FR-UPD-09, FR-UPD-10)
6. CLI: `update` subcommand in `bin/claude-company.js` -> new `lib/update.js`
   driver reusing the installer's preflight (python3/git/bash hard-required),
   `validateTarget`, arg parsing, and the win32 WSL guard (exit 2). Flags:
   `--target DIR`, `-y/--yes`, `--plain`, `--no-color`, `--check`, `--force`.
   Plain non-interactive output only - no animated TUI. (FR-UPD-01, FR-UPD-16)
7. `--check`: compute and print the full per-file plan, write NOTHING (no
   backup dir, no `.new`, no manifest rewrite), exit 0. Downgrade guard: if
   manifest version > package version, refuse non-zero unless `--force`; with
   `--force` still only overwrite provably pristine files. (FR-UPD-11,
   FR-UPD-13)
8. Report: version transition (`<from> -> <to>` or `unknown -> <to>`), counts
   of updated / preserved / restored / unchanged, the `.new` path list, backup
   dir path (or "nothing backed up"); "already up to date at <version>" when
   there is no drift. Exit 0 on success even with `.new` conflicts; non-zero
   only on usage error, preflight/target failure, or hard write failure.
   `update --help` documents the flags; top-level help lists `update`.
   (FR-UPD-14, FR-UPD-15)
9. Pack + docs: add `update.sh` to `package.json` `files`; document the
   subcommand alongside install in `docs/`.
10. Tests (bash, existing style, wired into `npm test` coverage): every FR has
    at least one assertion - see DoD checklist below for the mandatory cases.

## Integration seams

- `lib/manifest.py` is the single hashing/read/write authority - install.sh
  and update.sh both shell out to it; neither reimplements hashing.
- `lib/update.js` guarantees the CLI contract (flags, exit codes, report);
  `update.sh` guarantees the file dispositions. Keep the split clean so the
  engine is testable without the CLI.
- You may assume the packaged tree layout matches this repo (`.claude/`,
  `company/`, `ORCHESTRATOR.md` at package root) - install.sh already relies
  on it. update.sh runs from the package like install.sh (it is packed, not
  copied into targets).

## Definition of Done

Universal DoD (every task) plus this task's specifics:

- [ ] Every FR in scope implemented, tested, or explicitly deferred with reason
- [ ] The two real suites green, run yourself before reporting:
      `python3 -m unittest discover -s tests/hooks -q` AND `npm test`
- [ ] Bin-vs-bare parity test green with NO new exclusion (manifest determinism)
- [ ] Pristine flow: fresh install -> update -> all payload refreshed, zero `.new`
- [ ] Modified flow: edit an agent prompt -> update -> edit survives
      byte-for-byte, `<file>.new` holds packaged content, report says "preserved"
- [ ] Bootstrap flow: delete the manifest, edit one file -> update -> nothing
      clobbered, edited file gets `.new`
- [ ] `--check` leaves the tree byte-for-byte unchanged (assert by snapshot)
- [ ] Second update run reports all "unchanged" and writes no backup dir
- [ ] Downgrade refused non-zero without `--force`
- [ ] gates.config, specs, state files untouched by update (assert)
- [ ] settings.json user hooks survive the merge (assert)
- [ ] No edits outside owned paths; zero frozen surfaces patched locally
- [ ] Tests are the oracle - never edited to pass
- [ ] MODULE.md created/updated in `lib/` (and wherever the repo convention has
      one for touched dirs)
- [ ] Report follows `company/templates/REPORT-TEMPLATE.md` and proposes 1-3
      single-line verbatim witness markers for what shipped
- [ ] DO NOT COMMIT: leave all work uncommitted in the worktree - the CEO
      stages and lands the commit (subagent commits in worktrees are blocked
      by policy; plan for it, do not fight it)

## Fallback assumptions

For every ambiguity, implement THIS stated assumption and tag the site - do
not guess, do not ask the user:

- OQ-UPD-01: engine mechanism -> FALLBACK: new `update.sh` reusing install.sh's
  helper shape + shared `lib/manifest.py`; install.sh's contract stays intact.
  Tag `# OQ-UPD-01 assumption`.
- OQ-UPD-02: no manifest at target -> FALLBACK: safe mode - at-packaged-hash
  files are no-ops, everything else preserved + `.new`; never overwrite. Tag
  `# OQ-UPD-02 assumption`.
- OQ-UPD-03: modified-file disposition -> FALLBACK: write `<path>.new`, keep
  the user file; no prompt (works under `--yes` and CI). Tag
  `# OQ-UPD-03 assumption`.
- OQ-UPD-04: downgrade -> FALLBACK: refuse non-zero unless `--force`; with
  `--force`, pristine-only overwrites still apply. Tag `# OQ-UPD-04 assumption`.
- OQ-UPD-05: TUI -> FALLBACK: plain non-interactive report only. No tag needed
  (structural).
- OQ-UPD-06: exit code with `.new` conflicts -> FALLBACK: exit 0; conflicts
  live in the report text. Tag `// OQ-UPD-06 assumption` at the exit site.
- OQ-UPD-07: backup retention -> FALLBACK: keep all backups; no pruning. No
  tag needed (absence of code).
- OQ-UPD-08: gate auto-detect on update -> FALLBACK: never - update does not
  read or write gates.config. Tag `# OQ-UPD-08 assumption` where the engine
  skips it.

## Out of scope

Explicitly, so nobody "helpfully" expands:

- Three-way text merge of user edits with upstream (`.new` is the
  reconciliation surface)
- Self-update of the npm package (npm owns it)
- Interactive/animated TUI for update; any change to the install TUI flow
- Gate auto-detection on update
- Backup auto-pruning
- Native Windows support
- Migrating/transforming user content (old specs/state formats)
- Editing `company/frozen-surfaces.json` (CEO applies CR-UPD-1)

## Report back

Your report must contain, as facts: what changed (paths), gate results (paste
both suite outputs), FR checklist (FR-UPD-01..16), ownership diff summary
(`git diff --name-only` against main), CRs filed, deviations from this brief
and why, 1-3 proposed single-line verbatim witness markers, worries for the
CEO. Tracking issues: #54 (manifest), #55 (update subcommand), #56 (CR-UPD-1
registry freeze - CEO-applied).
