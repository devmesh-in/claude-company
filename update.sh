#!/usr/bin/env bash
# update.sh - file-disposition engine for `claude-company update`. Refreshes
# the shipped payload in an already-installed project while NEVER overwriting a
# file the user customized. Every uncertainty resolves toward PRESERVING user
# work: unknown provenance, missing manifest, or any doubt writes a `.new`
# sibling and keeps the user's file untouched.
#
# OQ-UPD-01 assumption: this engine deliberately reuses install.sh's helper
# shape (set -euo pipefail, the color block, info/ok/skip/warn, cp helpers) and
# the shared lib/manifest.py + lib/payload_paths.sh so install and update agree
# byte-for-byte on the overwrite set and on file hashing.
#
# Usage: bash update.sh TARGET [--check] [--force]
#
# Works on macOS bash 3.2 (no associative arrays, no readarray / mapfile).
set -euo pipefail

# --- colors ---------------------------------------------------------------
if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_BOLD=''; C_RESET=''
fi
info()  { printf '%s\n' "${C_BLUE}${C_BOLD}==>${C_RESET} $*"; }
ok()    { printf '%s\n' "  ${C_GREEN}ok${C_RESET} $*"; }
skip()  { printf '%s\n' "  ${C_YELLOW}keep${C_RESET} $*"; }
warn()  { printf '%s\n' "${C_YELLOW}warning:${C_RESET} $*" >&2; }

usage() {
  cat >&2 <<USAGE
Usage: bash update.sh TARGET [--check] [--force]

Refreshes the claude-company payload in an installed project without ever
overwriting a file the user customized. The target directory must exist and
must already contain a claude-company install.

  --check   dry run - print the full per-file plan, write nothing
  --force   proceed even if the installed version is newer than this package
USAGE
  exit 2
}

# Bad-target / usage errors exit 2; hard write failures exit 3; downgrade
# refusal exits 4. There is deliberately no exit-1 path.
die2()  { printf '%s\n' "${C_RED}error:${C_RESET} $*" >&2; exit 2; }
die3()  { printf '%s\n' "${C_RED}error:${C_RESET} $*" >&2; exit 3; }
die4()  { printf '%s\n' "${C_RED}error:${C_RESET} $*" >&2; exit 4; }

safe_mkdir() { mkdir -p "$1" || die3 "cannot create directory: $1"; }
safe_cp()    { cp "$1" "$2" || die3 "write failed: $2"; }
safe_mv()    { mv "$1" "$2" || die3 "write failed: $2"; }

# --- resolve source (this package's root), independent of cwd -------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR"

# --- parse arguments ------------------------------------------------------
TARGET_ARG=""
CHECK=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --force) FORCE=1 ;;
    --*)     usage ;;              # unknown flag
    *)
      if [ -z "$TARGET_ARG" ]; then
        TARGET_ARG="$arg"
      else
        usage                      # second positional
      fi
      ;;
  esac
done
[ -n "$TARGET_ARG" ] || usage
[ -d "$TARGET_ARG" ] || die2 "target directory does not exist: $TARGET_ARG"
TARGET="$(cd "$TARGET_ARG" && pwd)"

# --- refuse to update the claude-company repo itself ----------------------
if [ "$TARGET" = "$SRC" ]; then
  die2 "refusing to update the claude-company repo itself ($SRC)"
fi

# --- wire the shared helpers ----------------------------------------------
MANIFEST_HELPER="$SRC/lib/manifest.py"
MANIFEST_ENUM="$SRC/lib/payload_paths.sh"
[ -f "$MANIFEST_HELPER" ] || die2 "missing helper: $MANIFEST_HELPER"
[ -f "$MANIFEST_ENUM" ]   || die2 "missing helper: $MANIFEST_ENUM"
# shellcheck source=/dev/null
. "$MANIFEST_ENUM"

MANIFEST="$TARGET/company/state/install-manifest.json"

PKG_VERSION="$(python3 "$MANIFEST_HELPER" pkgversion "$SRC/package.json" 2>/dev/null || true)"
[ -n "$PKG_VERSION" ] || PKG_VERSION="unknown"

# version FILE is silent (empty) when the manifest is missing or unreadable.
MANIFEST_VERSION="$(python3 "$MANIFEST_HELPER" version "$MANIFEST" 2>/dev/null || true)"

# --- backup bookkeeping (lazy - one dir per run) --------------------------
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$TARGET/company/state/.update-backups/$TS"
ensure_backup_dir() { [ -d "$BACKUP_DIR" ] || safe_mkdir "$BACKUP_DIR"; }
backup_file() {
  # Copy the PRIOR target content of rel into the run's backup dir.
  local rel="$1"
  ensure_backup_dir
  safe_mkdir "$BACKUP_DIR/$(dirname "$rel")"
  safe_cp "$TARGET/$rel" "$BACKUP_DIR/$rel"
}

# --- plan / counters ------------------------------------------------------
n_updated=0
n_preserved=0
n_restored=0
n_unchanged=0
merged_changed=0
preserved_list=""
provenance_notice=0  # issue-64: set when provenance.json is absent at target

plan() {
  # Per-file plan line - printed only in --check mode.
  if [ "$CHECK" = "1" ]; then
    printf '  %-9s %s\n' "$1" "$2"
  fi
}

# --- header ---------------------------------------------------------------
if [ "$CHECK" = "1" ]; then
  info "claude-company update [dry run - nothing written]"
else
  info "claude-company update"
fi
echo "  target: $TARGET"
if [ -n "$MANIFEST_VERSION" ]; then
  echo "  version: $MANIFEST_VERSION -> $PKG_VERSION"
else
  echo "  version: unknown -> $PKG_VERSION"
fi

# --- downgrade guard (FR-UPD-13) ------------------------------------------
# OQ-UPD-04 assumption: only a manifest that is provably newer than this
# package is a downgrade; an empty / unreadable manifest version is never a
# downgrade (it drops into safe mode below instead). --check always continues
# to print the plan; a bare run refuses; --force proceeds (the matrix only
# overwrites provably-pristine files, so --force stays safe).
if [ -n "$MANIFEST_VERSION" ]; then
  vc="$(python3 "$MANIFEST_HELPER" vercmp "$MANIFEST_VERSION" "$PKG_VERSION" 2>/dev/null || echo 0)"
  if [ "$vc" = "1" ]; then
    if [ "$CHECK" = "1" ]; then
      echo "  note: downgrade detected ($MANIFEST_VERSION is newer than $PKG_VERSION)"
    elif [ "$FORCE" = "1" ]; then
      warn "downgrade forced: $MANIFEST_VERSION -> $PKG_VERSION"
    else
      die4 "refusing to downgrade $MANIFEST_VERSION -> $PKG_VERSION; re-run with --force to override"
    fi
  fi
fi

if [ "$CHECK" = "1" ]; then
  echo
  echo "  plan:"
fi

# --- disposition matrix (BR-UPD-01..08 / FR-UPD-03..07 / FR-UPD-12) --------
# For every file in the overwrite set, decide RESTORED / UNCHANGED / UPDATED /
# PRESERVED from three hashes: pkg (packaged), tgt (target now), base (the
# hash the manifest recorded at install time). Process substitution keeps the
# loop in this shell so the counters below persist (a pipe would subshell it).
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  pkg="$(python3 "$MANIFEST_HELPER" hash "$SRC/$rel" 2>/dev/null || true)"
  if [ -z "$pkg" ]; then
    warn "source unreadable, skipped: $rel"
    continue
  fi
  if [ -f "$TARGET/$rel" ]; then
    tgt="$(python3 "$MANIFEST_HELPER" hash "$TARGET/$rel" 2>/dev/null || true)"
  else
    tgt=""
  fi
  base="$(python3 "$MANIFEST_HELPER" get "$MANIFEST" "$rel" 2>/dev/null || true)"

  if [ -z "$tgt" ]; then
    # Target file absent - restore it from the package.
    plan RESTORED "$rel"
    n_restored=$((n_restored + 1))
    if [ "$CHECK" != "1" ]; then
      safe_mkdir "$(dirname "$TARGET/$rel")"
      safe_cp "$SRC/$rel" "$TARGET/$rel"
    fi
  elif [ "$tgt" = "$pkg" ]; then
    # Already exactly the packaged bytes - nothing to do.
    plan UNCHANGED "$rel"
    n_unchanged=$((n_unchanged + 1))
  elif [ -n "$base" ] && [ "$tgt" = "$base" ]; then
    # Pristine since install (matches the recorded baseline) - safe to update.
    plan UPDATED "$rel"
    n_updated=$((n_updated + 1))
    if [ "$CHECK" != "1" ]; then
      backup_file "$rel"
      safe_cp "$SRC/$rel" "$TARGET/$rel"
    fi
  else
    # OQ-UPD-02 assumption: with no manifest, base is always "" so every
    # drifted file lands here - the bootstrap safe mode where only exact-hash
    # matches count as UNCHANGED and everything else is preserved.
    # OQ-UPD-03 assumption: user drift is sacred - keep their file untouched
    # and drop the packaged content beside it as `<rel>.new` for manual merge.
    plan PRESERVED "$rel"
    n_preserved=$((n_preserved + 1))
    preserved_list="${preserved_list}${rel}.new
"
    if [ "$CHECK" != "1" ]; then
      safe_mkdir "$(dirname "$TARGET/$rel")"
      safe_cp "$SRC/$rel" "$TARGET/$rel.new"
    fi
  fi
done < <(cc_overwrite_relpaths "$SRC")

# --- copy_if_absent config (FR-UPD-07) ------------------------------------
# gates.config, frozen-surfaces.json, models.json: restore only if the target
# lacks them; never overwrite, never back up.
# OQ-UPD-08 assumption: update never reads or writes gate detection or gate
# results - it only ships the config file itself when absent, and never touches
# user state (STATUS.md, specs, briefs, change-requests, logs, gate status).
config_if_absent() {
  local rel="$1"
  if [ ! -f "$SRC/$rel" ]; then
    warn "source missing, skipped: $rel"
    return 0
  fi
  if [ -f "$TARGET/$rel" ]; then
    plan UNCHANGED "$rel"
    n_unchanged=$((n_unchanged + 1))
    return 0
  fi
  plan RESTORED "$rel"
  n_restored=$((n_restored + 1))
  if [ "$CHECK" != "1" ]; then
    safe_mkdir "$(dirname "$TARGET/$rel")"
    safe_cp "$SRC/$rel" "$TARGET/$rel"
  fi
}
config_if_absent "company/gates.config"
config_if_absent "company/frozen-surfaces.json"
config_if_absent "company/models.json"

# issue-64: provenance.json is copy_if_absent for INSTALL only. update must
# NEVER create it - an update must not switch a project's enforcement regime
# (owner rule 2026-07-15). Present -> untouched, counted unchanged; absent ->
# NOT restored, one notice line printed (stdout, once, both --check and apply),
# counted as nothing.
config_present_or_notice() {
  local rel="$1"
  if [ ! -f "$SRC/$rel" ]; then
    warn "source missing, skipped: $rel"
    return 0
  fi
  if [ -f "$TARGET/$rel" ]; then
    plan UNCHANGED "$rel"
    n_unchanged=$((n_unchanged + 1))
    return 0
  fi
  provenance_notice=1
}
config_present_or_notice "company/provenance.json"

# --- scaffold record dirs (issue-68) --------------------------------------
# specs/briefs/change-requests are the trees a target project WRITES into.
# install ships them EMPTY; update only ensures they still exist and NEVER
# copies this package's own records (spec-*.md, brief-*.md, CR-*.md, shipped/**)
# into a target - that copy was the pack-leak bug. Structural mkdir only, like
# the company/state scaffold below; --check writes nothing.
if [ "$CHECK" != "1" ]; then
  for record_dir in \
    company/specs company/specs/shipped \
    company/briefs company/briefs/shipped \
    company/change-requests
  do
    [ -d "$TARGET/$record_dir" ] || safe_mkdir "$TARGET/$record_dir"
  done
fi

# --- merge paths (FR-UPD-08) ----------------------------------------------
# Re-run the SAME idempotent merges install.sh performs. Each merge computes
# the result into a temp file, then: target absent -> write into place (no
# backup); merged == current -> no-op; merged != current -> back up, then move
# into place. Merges NEVER produce a `.new`.
finalize_merge() {
  # NOTE: assign dst on its own line - a single `local a=$1 b="$X/$a"` would
  # read $a before it is set (bash evaluates all RHS before binding the names).
  local rel="$1" tmp="$2"
  local dst="$TARGET/$rel"
  if [ ! -f "$dst" ]; then
    plan MERGED "$rel"
    merged_changed=$((merged_changed + 1))
    if [ "$CHECK" = "1" ]; then rm -f "$tmp"; return 0; fi
    safe_mkdir "$(dirname "$dst")"
    safe_mv "$tmp" "$dst"
    return 0
  fi
  if cmp -s "$tmp" "$dst"; then
    plan UNCHANGED "$rel"
    n_unchanged=$((n_unchanged + 1))
    rm -f "$tmp"
    return 0
  fi
  plan MERGED "$rel"
  merged_changed=$((merged_changed + 1))
  if [ "$CHECK" = "1" ]; then rm -f "$tmp"; return 0; fi
  backup_file "$rel"
  safe_mv "$tmp" "$dst"
}

# 1. .claude/settings.json - deep-merge hooks + permissions.deny.
SETTINGS_SRC="$SRC/.claude/settings.json"
if [ -f "$SETTINGS_SRC" ]; then
  SETTINGS_TMP="$(mktemp)"
  [ -f "$TARGET/.claude/settings.json" ] && cp "$TARGET/.claude/settings.json" "$SETTINGS_TMP"
  # COUPLING: the heredoc below is copied VERBATIM from install.sh (section 5).
  # Keep it byte-identical; the two must merge the same way. See install.sh.
  python3 - "$SETTINGS_SRC" "$SETTINGS_TMP" <<'PY'
import json, sys

src_path, dst_path = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    ours = json.load(f)
try:
    with open(dst_path) as f:
        theirs = json.load(f)
except (FileNotFoundError, ValueError):
    theirs = {}

# --- merge hooks: append our command entries unless already present -------
# issue-67: dedup key is (matcher, command), not command-per-event. A command
# may legitimately appear under several matcher groups of one event
# (guard_provenance under Edit|Write|MultiEdit AND Task|Agent AND Bash); a
# per-event set dropped every repeat after the first, emptying and then losing
# whole groups. Keying by matcher keeps each group complete.
_NO_MATCHER = object()  # sentinel key for groups that carry no matcher

def commands_by_matcher(groups):
    seen = {}
    for g in groups or []:
        bucket = seen.setdefault(g.get("matcher", _NO_MATCHER), set())
        for h in (g.get("hooks") or []):
            c = h.get("command")
            if c is not None:
                bucket.add(c)
    return seen

our_hooks = ours.get("hooks") or {}
their_hooks = theirs.setdefault("hooks", {}) if isinstance(theirs.get("hooks", {}), dict) else {}
if not isinstance(theirs.get("hooks"), dict):
    theirs["hooks"] = {}
    their_hooks = theirs["hooks"]

for event, our_groups in our_hooks.items():
    existing_groups = their_hooks.get(event)
    if not isinstance(existing_groups, list):
        existing_groups = []
        their_hooks[event] = existing_groups
    have = commands_by_matcher(existing_groups)  # issue-67: dedup per matcher
    for g in (our_groups or []):
        bucket = have.setdefault(g.get("matcher", _NO_MATCHER), set())
        new_hooks = []
        for h in (g.get("hooks") or []):
            c = h.get("command")
            if c is not None and c in bucket:
                continue  # identical command already present under this matcher
            new_hooks.append(h)
            if c is not None:
                bucket.add(c)
        if new_hooks:
            ng = dict(g)
            ng["hooks"] = new_hooks
            existing_groups.append(ng)

# --- merge permissions.deny: union, preserving user's ---------------------
our_perms = ours.get("permissions") or {}
our_deny = our_perms.get("deny") or []
if our_deny:
    their_perms = theirs.get("permissions")
    if not isinstance(their_perms, dict):
        their_perms = {}
        theirs["permissions"] = their_perms
    their_deny = their_perms.get("deny")
    if not isinstance(their_deny, list):
        their_deny = []
        their_perms["deny"] = their_deny
    for entry in our_deny:
        if entry not in their_deny:
            their_deny.append(entry)

with open(dst_path, "w") as f:
    json.dump(theirs, f, indent=2, sort_keys=False)
    f.write("\n")
PY
  finalize_merge ".claude/settings.json" "$SETTINGS_TMP"
else
  warn "source .claude/settings.json missing - skipped"
fi

# 2. .mcp.json - merge in our servers without overwriting the user's.
MCP_SRC="$SRC/.mcp.json"
if [ -f "$MCP_SRC" ]; then
  MCP_TMP="$(mktemp)"
  [ -f "$TARGET/.mcp.json" ] && cp "$TARGET/.mcp.json" "$MCP_TMP"
  # COUPLING: heredoc copied VERBATIM from install.sh (section 6). Keep byte-identical.
  python3 - "$MCP_SRC" "$MCP_TMP" <<'PY'
import json, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    ours = json.load(f)
try:
    with open(dst_path) as f:
        theirs = json.load(f)
except (FileNotFoundError, ValueError):
    theirs = {}
our_servers = ours.get("mcpServers") or {}
their_servers = theirs.get("mcpServers")
if not isinstance(their_servers, dict):
    their_servers = {}
    theirs["mcpServers"] = their_servers
for name, cfg in our_servers.items():
    if name not in their_servers:  # never overwrite a user's existing server
        their_servers[name] = cfg
with open(dst_path, "w") as f:
    json.dump(theirs, f, indent=2, sort_keys=False)
    f.write("\n")
PY
  finalize_merge ".mcp.json" "$MCP_TMP"
else
  warn "source .mcp.json missing - skipped"
fi

# 3. CLAUDE.md marked block - append or replace the claude-company block.
# COUPLING: CC_BLOCK and the heredoc below are copied VERBATIM from install.sh
# (section 7). Keep them byte-identical so both tools render the same block.
read -r -d '' CC_BLOCK <<'BLOCK' || true
<!-- claude-company:begin -->
## claude-company

This project runs **claude-company**, a hierarchical SDLC system for Claude Code.

- Main sessions act as CEO: drive the project through `/orchestrator` and `ORCHESTRATOR.md`.
- Subagents obey their brief plus `company/METHOD.md` - the brief is the contract.
- Gates are the definition of done and are hook-enforced. Red stays red until proven green.
- Run gates with `company/run-gates.sh`; configure them in `company/gates.config`.
- Frozen surfaces (`company/frozen-surfaces.json`) change only via a change request in `company/change-requests/`.
- Project state lives in `company/state/` (STATUS, RESUME, WORRIES, DECISIONS).

New to this project? Run `/company-init`. Adopting an existing codebase? Run `/onboard`. Then `/orchestrator`.
<!-- claude-company:end -->
BLOCK

CLAUDE_TMP="$(mktemp)"
[ -f "$TARGET/CLAUDE.md" ] && cp "$TARGET/CLAUDE.md" "$CLAUDE_TMP"
CC_BLOCK="$CC_BLOCK" python3 - "$CLAUDE_TMP" <<'PY'
import os, re, sys
path = sys.argv[1]
block = os.environ["CC_BLOCK"].rstrip("\n")
begin = "<!-- claude-company:begin -->"
end = "<!-- claude-company:end -->"
try:
    with open(path) as f:
        content = f.read()
except FileNotFoundError:
    content = ""
if begin in content and end in content:
    pattern = re.compile(re.escape(begin) + ".*?" + re.escape(end), re.DOTALL)
    content = pattern.sub(lambda m: block, content)
else:
    if content and not content.endswith("\n"):
        content += "\n"
    if content:
        content += "\n"
    content += block + "\n"
with open(path, "w") as f:
    f.write(content)
PY
# A fresh mktemp is empty, which the merge treats as "no marked block yet" and
# appends ours - identical to the CLAUDE.md-absent case. finalize_merge then
# decides create / no-op / backup+replace against the real target.
finalize_merge "CLAUDE.md" "$CLAUDE_TMP"

# 4. company/models.json - inject the packaged template's builtins when the
# target manifest predates the builtins section. config_if_absent above already
# RESTORED a missing manifest from the template (which carries builtins), so in
# the restore case this block finds builtins present and no-ops. finalize_merge
# then handles it: injecting run -> tmp differs -> backup + move (MERGED);
# builtins already present -> tmp equals target -> UNCHANGED, no backup.
# COUPLING: the heredoc between <<'PY' and PY below is BYTE-IDENTICAL to the
# models.json builtins-injection block in install.sh. Keep them identical.
MODELS_SRC="$SRC/company/models.json"
if [ -f "$MODELS_SRC" ] && [ -f "$TARGET/company/models.json" ]; then
  MODELS_TMP="$(mktemp)"
  cp "$TARGET/company/models.json" "$MODELS_TMP"
  python3 - "$MODELS_SRC" "$MODELS_TMP" <<'PY'
import json, sys

# OQ-MRA-01 assumption: additive builtins injection by canonical
# json.load/json.dump re-serialization on the one injecting run. Inject the
# packaged template's `builtins` only when the target manifest lacks it,
# preserving the VALUES of roles/pricing/version and any user keys. When
# `builtins` is already present, emit the target bytes verbatim (no write) so
# the file stays byte-unchanged.
src_path, dst_path = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    src = json.load(f)
try:
    with open(dst_path) as f:
        tgt = json.load(f)
except (FileNotFoundError, ValueError):
    sys.exit(0)  # nothing to merge into - config-if-absent restores separately
if not isinstance(tgt, dict) or "builtins" in tgt:
    sys.exit(0)  # already armed (or unmergeable) - leave the target untouched
src_builtins = src.get("builtins")
if not isinstance(src_builtins, dict):
    sys.exit(0)  # template carries no builtins - nothing to inject
tgt["builtins"] = src_builtins
with open(dst_path, "w") as f:
    json.dump(tgt, f, indent=2, sort_keys=False)
    f.write("\n")
PY
  finalize_merge "company/models.json" "$MODELS_TMP"
fi

# --- manifest rewrite (FR-UPD-10) -----------------------------------------
# After a successful non-check apply, re-stamp the manifest to the PACKAGED
# hashes + version. This records packaged bytes as the new baseline - never the
# user's current file - which is exactly what keeps a PRESERVED file from being
# clobbered on the next run. Skipped entirely in --check.
if [ "$CHECK" != "1" ]; then
  safe_mkdir "$TARGET/company/state"
  if ! cc_overwrite_relpaths "$SRC" \
      | python3 "$MANIFEST_HELPER" build --version "$PKG_VERSION" --root "$SRC" \
      > "$MANIFEST"; then
    die3 "failed to rewrite manifest: $MANIFEST"
  fi
fi

# --- report (FR-UPD-14) ---------------------------------------------------
total_drift=$((n_restored + n_updated + n_preserved + merged_changed))
echo
# issue-64: one notice line when the delegation enforcer is installed but the
# target has no provenance.json - update never arms it, it only informs.
if [ "$provenance_notice" = "1" ]; then
  echo "note: delegation enforcer installed but disarmed - create company/provenance.json to arm (see company/METHOD.md)"
fi
if [ "$total_drift" -eq 0 ]; then
  echo "  already up to date at $PKG_VERSION"
else
  echo "  updated:   $n_updated"
  echo "  preserved: $n_preserved"
  echo "  restored:  $n_restored"
  echo "  unchanged: $n_unchanged"
  echo "  merged:    $merged_changed"
  if [ "$n_preserved" -gt 0 ]; then
    echo "  new files written (review and merge):"
    printf '%s' "$preserved_list" | while IFS= read -r nf; do
      [ -n "$nf" ] || continue
      printf '    %s\n' "$nf"
    done
  fi
fi
if [ -d "$BACKUP_DIR" ]; then
  echo "  backups: $BACKUP_DIR"
else
  echo "  backups: nothing backed up"
fi

# OQ-UPD-06 assumption: a `.new` conflict is a successful, expected outcome
# (user work preserved), not an error - exit 0 even when files were preserved.
exit 0
