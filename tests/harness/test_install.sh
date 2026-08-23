#!/usr/bin/env bash
# tests/harness/test_install.sh - harness selection in install and update.
#
# FR-HA-16, FR-HA-17, FR-HA-18. These shipped untested in the first pass: the
# installer's 97 and the TUI's 22 are pre-existing counts that prove the OLD
# paths still work, which is not the same as proving the new ones do.
#
# The first assertion is the one that matters most. The owner's hard constraint
# is that the Claude side does not change, and the cheapest way to break it is
# a default that quietly stopped being "claude".
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${REPO_OVERRIDE:-$(cd "$TEST_DIR/../.." && pwd)}"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
check() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }
refute() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then fail "$d"; else pass "$d"; fi; }

WORK="$(mktemp -d -t ccharnessinstall.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# --- the overwrite set, which drives both copying and the manifest ----------
printf '\nthe overwrite set is harness-scoped (FR-HA-16)\n'
# shellcheck source=/dev/null
. "$REPO/lib/payload_paths.sh"

DEFAULT_SET="$WORK/default.txt"
CLAUDE_SET="$WORK/claude.txt"
BOTH_SET="$WORK/both.txt"
cc_overwrite_relpaths "$REPO"                 > "$DEFAULT_SET"
cc_overwrite_relpaths "$REPO" claude          > "$CLAUDE_SET"
cc_overwrite_relpaths "$REPO" claude,opencode > "$BOTH_SET"

# The legacy single-argument call must be byte-identical to the explicit
# claude one, or every existing scripted install changes shape silently.
check "the default argument-less call equals an explicit claude selection" \
  cmp -s "$DEFAULT_SET" "$CLAUDE_SET"
refute "a claude-only set names no .opencode path" grep -q opencode "$CLAUDE_SET"
check "selecting opencode adds the adapter" grep -q '\.opencode/plugin/company-harness\.js' "$BOTH_SET"
check "selecting opencode adds the pure logic" grep -q '\.opencode/lib/harness-core\.js' "$BOTH_SET"
check "selecting opencode adds generated agents" grep -q '\.opencode/agent/developer\.md' "$BOTH_SET"
check "selecting opencode adds generated commands" grep -q '\.opencode/command/gates\.md' "$BOTH_SET"
# MODULE.md is repo wayfinding, not payload; shipping it would point users at
# a lib/ directory they do not have.
refute "the opencode MODULE.md is not payload" grep -q '\.opencode/MODULE\.md' "$BOTH_SET"

# --- install ---------------------------------------------------------------
printf '\ninstall honours the selection (FR-HA-17)\n'

T_DEFAULT="$WORK/t-default"; mkdir -p "$T_DEFAULT"
T_BOTH="$WORK/t-both";       mkdir -p "$T_BOTH"
T_ONLY="$WORK/t-only";       mkdir -p "$T_ONLY"
bash "$REPO/install.sh" "$T_DEFAULT" >/dev/null 2>&1
bash "$REPO/install.sh" --harness=claude,opencode "$T_BOTH" >/dev/null 2>&1
bash "$REPO/install.sh" --harness=opencode "$T_ONLY" >/dev/null 2>&1

refute "a default install writes no .opencode" test -d "$T_DEFAULT/.opencode"
check  "a default install still writes .claude/hooks" test -d "$T_DEFAULT/.claude/hooks"
check  "an opencode install writes the adapter" test -f "$T_BOTH/.opencode/plugin/company-harness.js"
check  "an opencode install writes the pure logic" test -f "$T_BOTH/.opencode/lib/harness-core.js"

# .claude is NOT optional on any harness: the adapter shells out to those
# guards, and opencode reads those skills directly.
check "--harness=opencode still installs the guards" test -d "$T_ONLY/.claude/hooks"
check "--harness=opencode still installs the skills" test -d "$T_ONLY/.claude/skills"
check "--harness=opencode still installs the adapter" test -f "$T_ONLY/.opencode/plugin/company-harness.js"

printf '\nbad selections are refused, not guessed at\n'
T_BAD="$WORK/t-bad"; mkdir -p "$T_BAD"
refute "an unknown harness exits non-zero" bash "$REPO/install.sh" --harness=emacs "$T_BAD"
refute "and installs nothing" test -d "$T_BAD/.claude"

# --- the manifest describes what was actually installed --------------------
printf '\nthe manifest matches the install (FR-HA-16)\n'
M_DEFAULT="$T_DEFAULT/company/state/install-manifest.json"
M_BOTH="$T_BOTH/company/state/install-manifest.json"
check "a default install wrote a manifest" test -s "$M_DEFAULT"
# A manifest naming files the install never placed puts `update` into safe mode
# for paths that were never meant to be there.
refute "a default manifest names no .opencode file" grep -q '\.opencode/' "$M_DEFAULT"
check "an opencode manifest names the adapter" grep -q 'company-harness\.js' "$M_BOTH"

# --- AGENTS.md collision (FR-HA-18) ----------------------------------------
printf '\nthe AGENTS.md collision is surfaced (FR-HA-18)\n'
T_AGENTS="$WORK/t-agents"; mkdir -p "$T_AGENTS"
printf '# agents\n' > "$T_AGENTS/AGENTS.md"
OUT="$(bash "$REPO/install.sh" --harness=claude,opencode "$T_AGENTS" 2>&1)"
# opencode reads CLAUDE.md ONLY when no AGENTS.md exists. Silently installing
# canon that will never be read looks exactly like a working install.
check "installing over an AGENTS.md warns that CLAUDE.md will be ignored" \
  bash -c "printf '%s' \"\$1\" | grep -qi 'AGENTS.md'" _ "$OUT"
T_NOAGENTS="$WORK/t-noagents"; mkdir -p "$T_NOAGENTS"
OUT2="$(bash "$REPO/install.sh" --harness=claude,opencode "$T_NOAGENTS" 2>&1)"
refute "and stays quiet when there is no AGENTS.md" \
  bash -c "printf '%s' \"\$1\" | grep -qi 'will IGNORE CLAUDE.md'" _ "$OUT2"

# --- update detects, never selects (W-020) ---------------------------------
printf '\nupdate refreshes what is there and adds nothing (FR-HA-17)\n'
bash "$REPO/update.sh" "$T_DEFAULT" >/dev/null 2>&1
refute "update does not ADD opencode to a claude-only project" \
  test -d "$T_DEFAULT/.opencode"
bash "$REPO/update.sh" "$T_BOTH" >/dev/null 2>&1
check "update keeps the adapter in a project that has it" \
  test -f "$T_BOTH/.opencode/plugin/company-harness.js"

printf '\n================ SUMMARY ================\n'
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then printf 'ALL GREEN\n'; exit 0; else printf 'RED\n'; exit 1; fi
