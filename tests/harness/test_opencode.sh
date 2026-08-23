#!/usr/bin/env bash
# tests/harness/test_opencode.sh - assertions against the REAL opencode binary.
#
# WHY THIS EXISTS SEPARATELY FROM test_core.mjs: that suite proves the adapter
# decides correctly. It cannot prove opencode still CALLS the adapter, still
# reads .claude/skills, still names its directories the same way, or still
# accepts the frontmatter the renderer emits. All of that is opencode's
# behavior, not ours, and every one of those facts was true on 1.18.16 and can
# change in a version bump.
#
# It caught a real one already. The adapter first shipped exporting its helper
# functions for testability; opencode calls EVERY export as a plugin factory
# and failed the whole file with "Plugin export is not a function", logged only
# under --print-logs. Every logic test passed while enforcement did nothing.
#
# NO SKIP PATH. A missing opencode binary is a FAILURE, not a skip. Contributors
# install opencode the same way they install Claude Code. A suite that skips
# itself when the thing it tests is absent reports green for a machine where
# nothing was tested.
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${REPO_OVERRIDE:-$(cd "$TEST_DIR/../.." && pwd)}"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
check() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }

printf '\nopencode binary\n'
if ! command -v opencode >/dev/null 2>&1; then
  fail "opencode is on PATH (install it: https://opencode.ai - this suite does not skip)"
  printf '\n================ SUMMARY ================\n'
  printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
  printf 'RED\n'
  exit 1
fi
pass "opencode is on PATH ($(opencode --version 2>/dev/null | head -1))"

WORK="$(mktemp -d -t ccharness.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

CFG="$WORK/config.json"
AGENTS="$WORK/agents.txt"
SKILLS="$WORK/skills.json"
LOGS="$WORK/logs.txt"
TRACE="$WORK/trace.jsonl"

cd "$REPO" || exit 1
opencode debug config           >"$CFG"    2>/dev/null
opencode agent list             >"$AGENTS" 2>/dev/null
opencode debug skill            >"$SKILLS" 2>/dev/null
COMPANY_HARNESS_DEBUG="$TRACE" opencode debug config >/dev/null 2>"$LOGS"
COMPANY_HARNESS_DEBUG="$TRACE" opencode debug config --print-logs >/dev/null 2>>"$LOGS"

# --- the plugin actually loads --------------------------------------------
printf '\nthe adapter loads (FR-HA-06)\n'

# The failure this pins: any non-function export, or any import error, makes
# opencode skip the file. Enforcement then does nothing and looks fine.
if grep -q "failed to load plugin" "$LOGS" 2>/dev/null; then
  fail "no plugin load errors"
  grep "failed to load plugin" "$LOGS" | head -3 | sed 's/^/       /'
else
  pass "no plugin load errors"
fi

check "the adapter reached its load path" test -s "$TRACE"

# Derived from .claude/settings.json, not hardcoded here - if a hook binding is
# added or removed, this reflects it with no edit to the adapter.
for ev in PreToolUse PostToolUse UserPromptSubmit Stop SessionStart; do
  check "wiring derived for $ev" grep -q "\"$ev\"" "$TRACE"
done

# --- everything the renderer generated is registered -----------------------
printf '\ngenerated agents register (FR-HA-02, FR-HA-19)\n'
for f in "$REPO"/.claude/agents/*.md; do
  name="$(basename "$f" .md)"
  check "agent '$name' is registered" grep -qE "^${name} \(subagent\)" "$AGENTS"
done

printf '\ngenerated commands register (FR-HA-03, FR-HA-19)\n'
for d in "$REPO"/.claude/skills/*/; do
  name="$(basename "$d")"
  [ -f "$d/SKILL.md" ] || continue
  check "command /$name is registered" \
    python3 -c "import json,sys; sys.exit(0 if '$name' in (json.load(open('$CFG')).get('command') or {}) else 1)"
done

# --- skills are read from .claude, not copied ------------------------------
printf '\nskills are discovered in place (OQ-HA-02)\n'
for d in "$REPO"/.claude/skills/*/; do
  name="$(basename "$d")"
  [ -f "$d/SKILL.md" ] || continue
  check "skill '$name' is discovered from .claude/skills" \
    python3 -c "
import json,sys
want='$REPO/.claude/skills/$name/SKILL.md'
sys.exit(0 if any(s.get('location')==want for s in json.load(open('$SKILLS'))) else 1)"
done

# A second copy under .opencode would register every skill twice, and the
# duplicate would drift the moment one copy is edited.
check "skills are NOT duplicated under .opencode" \
  test ! -d "$REPO/.opencode/skill" -a ! -d "$REPO/.opencode/skills"

# --- model routing ---------------------------------------------------------
printf '\nroles inherit the session model (FR-HA-15)\n'
check "no company agent pins a model" python3 -c "
import json,sys
cfg=json.load(open('$CFG'))
pinned={k:v.get('model') for k,v in (cfg.get('agent') or {}).items() if v.get('model')}
print(pinned) if pinned else None
sys.exit(1 if pinned else 0)"

check "tech-lead may spawn only developer and qa-engineer" python3 -c "
import json,sys
p=(json.load(open('$CFG')).get('agent') or {}).get('tech-lead',{}).get('permission') or {}
sys.exit(0 if p.get('task')=={'*':'deny','developer':'allow','qa-engineer':'allow'} else 1)"

check "the auditor cannot write" python3 -c "
import json,sys
p=(json.load(open('$CFG')).get('agent') or {}).get('auditor',{}).get('permission') or {}
sys.exit(0 if p.get('edit')=='deny' and p.get('write')=='deny' else 1)"

# --- canon reaches opencode ------------------------------------------------
printf '\nproject canon (FR-HA-18)\n'
check "CLAUDE.md is wired as an instruction file" python3 -c "
import json,sys
sys.exit(0 if 'CLAUDE.md' in (json.load(open('$CFG')).get('instructions') or []) else 1)"

printf '\n================ SUMMARY ================\n'
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then printf 'ALL GREEN\n'; exit 0; else printf 'RED\n'; exit 1; fi
