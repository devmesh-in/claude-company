# lib/ - the claude-company CLI runtime

Zero-dependency Node (>= 16, stdlib only) plus python3/bash helpers that back the
`claude-company` CLI. This directory is packed into the npm tarball; it is
machinery, not `company/` canon (the dual-nature rule does not apply here).

## Files

| File | Role |
|---|---|
| `install-tui.js` | The `install` subcommand: interactive TUI + plain driver. A front end over `install.sh` (the engine). Exports `run`, `helpText`, and `_shared` (preflight `PROBES`, `validateTarget`, `expandUser`, exit codes) reused by `update.js`. |
| `update.js` | The `update` subcommand driver: preflight + target validation (reused from `install-tui._shared`) + win32 guard + flag parsing, then execs `../update.sh`. Owns the CLI contract (flags, exit codes, report framing); the engine owns file dispositions. |
| `manifest.py` | python3 3.8 stdlib. Single sha256 hashing / manifest read-write authority. Shared by `install.sh` (emit `company/state/install-manifest.json`) and `update.sh` (read baseline, rebuild post-apply). No timestamp or env-varying field - the manifest must be byte-identical across two installs (the bin-vs-bare parity tripwire). |
| `payload_paths.sh` | bash 3.2. `cc_overwrite_relpaths <SRC_ROOT>` prints the project-relative paths of the overwrite set - exactly what `install.sh` copies in place. The single enumeration both install emission and update planning consume, so they can never drift. |

## Contracts that must not drift

- `payload_paths.sh` must list exactly the files `install.sh` copies via
  `copy_overwrite` / `copy_tree_overwrite`. A file listed here but not copied by
  install would be "restored" by update into a tree install never placed; a file
  copied by install but missing here would fall outside provenance. The
  `update --check` after a fresh install asserting all-`unchanged` is the tripwire.
- The manifest is deterministic: `json.dumps(obj, indent=2, sort_keys=True) + "\n"`,
  no timestamp. A `generated_at` field breaks the parity suite.
- `update` never forks install's preflight/target logic - it imports `_shared`.

## Changelog

- Added `update.js`, `manifest.py`, `payload_paths.sh`; exported `_shared` from
  `install-tui.js` for the `update` subcommand (workstream cli-update).
