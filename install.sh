#!/usr/bin/env bash
# install.sh - drop-in installer for claude-company, a hierarchical SDLC
# system for Claude Code. Copies the company system into a target project,
# idempotently and non-destructively (user state and config always win).
#
# Usage: bash install.sh /path/to/target-project
#
# Works on macOS bash 3.2 (no associative arrays, no readarray).
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
die()   { printf '%s\n' "${C_RED}error:${C_RESET} $*" >&2; exit 1; }

usage() {
  cat >&2 <<USAGE
Usage: bash install.sh /path/to/target-project

Installs the claude-company SDLC system into an existing project directory.
The target directory must already exist.
USAGE
  exit 2
}

# --- resolve source (this script's repo), independent of cwd --------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR"

# --- validate arguments ---------------------------------------------------
[ "$#" -ge 1 ] || usage
TARGET_ARG="$1"
[ -n "$TARGET_ARG" ] || usage
[ -d "$TARGET_ARG" ] || die "target directory does not exist: $TARGET_ARG"
TARGET="$(cd "$TARGET_ARG" && pwd)"

# --- refuse to install into the claude-company repo itself ----------------
if [ "$TARGET" = "$SRC" ]; then
  die "refusing to install into the claude-company repo itself ($SRC)"
fi

info "claude-company installer"
echo "  source: $SRC"
echo "  target: $TARGET"
echo

# --- copy helpers ---------------------------------------------------------

# Overwrite a single file (ours - update in place).
copy_overwrite() {
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then warn "source missing, skipped: ${src#$SRC/}"; return 0; fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  ok "${dst#$TARGET/}"
}

# Copy a single file only if the destination is absent (user wins).
copy_if_absent() {
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then warn "source missing, skipped: ${src#$SRC/}"; return 0; fi
  if [ -e "$dst" ]; then skip "${dst#$TARGET/} (kept existing)"; return 0; fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  ok "${dst#$TARGET/}"
}

# Walk a directory and overwrite every file at the target (ours in place).
# Skips python bytecode caches so we never ship __pycache__/*.pyc artifacts.
copy_tree_overwrite() {
  local src="$1" dst="$2" f rel
  if [ ! -d "$src" ]; then warn "source dir missing, skipped: ${src#$SRC/}/"; return 0; fi
  find "$src" -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -print | while IFS= read -r f; do
    rel="${f#$src/}"
    mkdir -p "$dst/$(dirname "$rel")"
    cp "$f" "$dst/$rel"
  done
  ok "${dst#$TARGET/}/ (updated)"
}

# Walk a directory and copy each file only if absent at target (user wins).
copy_tree_if_absent() {
  local src="$1" dst="$2" f rel
  if [ ! -d "$src" ]; then return 0; fi
  find "$src" -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -print | while IFS= read -r f; do
    rel="${f#$src/}"
    if [ ! -e "$dst/$rel" ]; then
      mkdir -p "$dst/$(dirname "$rel")"
      cp "$f" "$dst/$rel"
    fi
  done
}

# --- 1. agents, hooks, skills (ours - update in place) --------------------
info "Installing agents, hooks, and skills"
copy_tree_overwrite "$SRC/.claude/agents"  "$TARGET/.claude/agents"
copy_tree_overwrite "$SRC/.claude/hooks"   "$TARGET/.claude/hooks"
copy_tree_overwrite "$SRC/.claude/skills"  "$TARGET/.claude/skills"

# --- 2. canon docs and orchestrator (ours - update in place) --------------
info "Installing canon docs"
copy_overwrite "$SRC/ORCHESTRATOR.md"          "$TARGET/ORCHESTRATOR.md"
copy_overwrite "$SRC/company/METHOD.md"        "$TARGET/company/METHOD.md"
copy_overwrite "$SRC/company/GATES.md"         "$TARGET/company/GATES.md"
copy_overwrite "$SRC/company/EXTENDING.md"     "$TARGET/company/EXTENDING.md"
copy_overwrite "$SRC/company/run-gates.sh"     "$TARGET/company/run-gates.sh"
[ -f "$TARGET/company/run-gates.sh" ] && chmod +x "$TARGET/company/run-gates.sh"
copy_tree_overwrite "$SRC/company/templates"   "$TARGET/company/templates"

# --- 3. user config and state (user wins if present) ----------------------
info "Installing project config and state (existing files preserved)"
copy_if_absent "$SRC/company/gates.config"           "$TARGET/company/gates.config"
copy_if_absent "$SRC/company/frozen-surfaces.json"   "$TARGET/company/frozen-surfaces.json"

# work directories - preserve any existing content
mkdir -p "$TARGET/company/specs" "$TARGET/company/briefs" "$TARGET/company/change-requests"
copy_tree_if_absent "$SRC/company/specs"           "$TARGET/company/specs"
copy_tree_if_absent "$SRC/company/briefs"          "$TARGET/company/briefs"
copy_tree_if_absent "$SRC/company/change-requests" "$TARGET/company/change-requests"

# --- 4. scaffold state stubs (only if absent) -----------------------------
info "Scaffolding company/state"
mkdir -p "$TARGET/company/state"
scaffold_stub() {
  local dst="$1" header="$2"
  if [ -e "$dst" ]; then skip "${dst#$TARGET/} (kept existing)"; return 0; fi
  printf '%s\n' "$header" > "$dst"
  ok "${dst#$TARGET/}"
}
scaffold_stub "$TARGET/company/state/STATUS.md" \
  "# STATUS - maintained by the orchestrator. Red stays red until proven green."
scaffold_stub "$TARGET/company/state/RESUME.md" \
  "# RESUME - maintained by the orchestrator. Where we are and what happens next."
scaffold_stub "$TARGET/company/state/WORRIES.md" \
  "# WORRIES - maintained by the orchestrator. Open risks and unknowns, worst first."
scaffold_stub "$TARGET/company/state/DECISIONS.md" \
  "# DECISIONS - maintained by the orchestrator. Durable choices and their rationale."
if [ ! -e "$TARGET/company/state/adherence.log" ]; then
  touch "$TARGET/company/state/adherence.log"
  ok "company/state/adherence.log"
else
  skip "company/state/adherence.log (kept existing)"
fi

# --- 5. settings.json (copy or deep-merge) --------------------------------
# Always route through the merger so the on-disk formatting is identical
# whether we started from nothing or an existing file (keeps re-runs a no-op).
info "Installing .claude/settings.json"
SETTINGS_SRC="$SRC/.claude/settings.json"
SETTINGS_DST="$TARGET/.claude/settings.json"
if [ ! -f "$SETTINGS_SRC" ]; then
  warn "source .claude/settings.json missing - skipped"
else
  [ -f "$SETTINGS_DST" ] && SETTINGS_VERB="merged" || SETTINGS_VERB="copied"
  mkdir -p "$TARGET/.claude"
  python3 - "$SETTINGS_SRC" "$SETTINGS_DST" <<'PY'
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
def commands_in_event(groups):
    cmds = set()
    for g in groups or []:
        for h in (g.get("hooks") or []):
            c = h.get("command")
            if c is not None:
                cmds.add(c)
    return cmds

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
    have = commands_in_event(existing_groups)
    for g in (our_groups or []):
        new_hooks = []
        for h in (g.get("hooks") or []):
            c = h.get("command")
            if c is not None and c in have:
                continue  # identical command already present
            new_hooks.append(h)
            if c is not None:
                have.add(c)
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
  ok ".claude/settings.json ($SETTINGS_VERB)"
fi

# --- 6. .mcp.json (copy or merge the playwright server) -------------------
info "Installing .mcp.json"
MCP_SRC="$SRC/.mcp.json"
MCP_DST="$TARGET/.mcp.json"
if [ ! -f "$MCP_SRC" ]; then
  warn "source .mcp.json missing - skipped"
else
  [ -f "$MCP_DST" ] && MCP_VERB="merged" || MCP_VERB="copied"
  python3 - "$MCP_SRC" "$MCP_DST" <<'PY'
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
  ok ".mcp.json ($MCP_VERB)"
fi

# --- 7. CLAUDE.md marked block (append or replace) ------------------------
info "Updating CLAUDE.md"
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

CC_BLOCK="$CC_BLOCK" python3 - "$TARGET/CLAUDE.md" <<'PY'
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
ok "CLAUDE.md (claude-company block up to date)"

# --- epilogue -------------------------------------------------------------
echo
info "claude-company installed"
cat <<EPILOGUE

Next steps:
  1. cd "$TARGET"
  2. claude
  3. In Claude Code, run one of:
       /company-init   (new project - scaffold specs and gates)
       /onboard        (existing codebase - map what is already there)
  4. Then start driving the work:
       /orchestrator

Configure your gates in company/gates.config, then verify with:
       bash company/run-gates.sh
EPILOGUE
