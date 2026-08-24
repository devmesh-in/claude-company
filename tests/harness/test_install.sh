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

# --- canon reaches opencode regardless of AGENTS.md (FR-HA-18) -------------
printf '\ncanon reaches opencode with or without AGENTS.md (FR-HA-18)\n'
# opencode's AUTOMATIC walk drops CLAUDE.md when AGENTS.md exists. The
# instructions array is combined with AGENTS.md rather than replaced by it, so
# the generated config is what carries the canon. Verified live 2026-08-23 by
# codeword probe in both directions.
#
# An earlier version of this suite asserted the installer WARNED about the
# collision. The warning was false - the config had already solved it - and
# the test passed anyway, because it only checked that the string appeared.
T_AGENTS="$WORK/t-agents"; mkdir -p "$T_AGENTS"
printf '# agents\n' > "$T_AGENTS/AGENTS.md"
bash "$REPO/install.sh" --harness=claude,opencode "$T_AGENTS" >/dev/null 2>&1
check "a project with AGENTS.md still gets the generated config" \
  test -f "$T_AGENTS/.opencode/opencode.json"
check "and that config names CLAUDE.md in instructions" python3 -c "
import json,sys
cfg=json.load(open('$T_AGENTS/.opencode/opencode.json'))
sys.exit(0 if 'CLAUDE.md' in (cfg.get('instructions') or []) else 1)"
# The installer must not touch a file the user owns.
check "the user's AGENTS.md is left exactly as it was" \
  bash -c "[ \"\$(cat '$T_AGENTS/AGENTS.md')\" = '# agents' ]"

# --- update detects, never selects (W-020) ---------------------------------
printf '\nupdate refreshes what is there and adds nothing (FR-HA-17)\n'
bash "$REPO/update.sh" "$T_DEFAULT" >/dev/null 2>&1
refute "update does not ADD opencode to a claude-only project" \
  test -d "$T_DEFAULT/.opencode"
bash "$REPO/update.sh" "$T_BOTH" >/dev/null 2>&1
check "update keeps the adapter in a project that has it" \
  test -f "$T_BOTH/.opencode/plugin/company-harness.js"

# --- background-subagents env wiring ----------------------------------------
# The flag is read from the process environment BEFORE opencode starts, and
# neither project config nor a plugin can enable it later (verified live
# 2026-08-24: the task tool schema is built without the background parameter).
# So an opencode install must wire the export into the user's shell profile.
printf '\nthe opencode install wires the background-subagents env\n'

HOME_SND="$WORK/home-snd"; mkdir -p "$HOME_SND"
env HOME="$HOME_SND" SHELL=/bin/zsh bash "$REPO/install.sh" --harness=opencode "$T_ONLY" >/dev/null 2>&1
check "an opencode install adds the export to the zshrc" \
  grep -q '^export OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true$' "$HOME_SND/.zshrc"
# The block is one guarded export line.
check "first install writes exactly one export line" \
  bash -c "test \"\$(grep -c OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS '$HOME_SND/.zshrc')\" -eq 1"
env HOME="$HOME_SND" SHELL=/bin/zsh bash "$REPO/install.sh" --harness=opencode "$T_ONLY" >/dev/null 2>&1
check "a second install does not duplicate the export (idempotent)" \
  bash -c "test \"\$(grep -c OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS '$HOME_SND/.zshrc')\" -eq 1"
# A comment mentioning the variable is not a wired export: the guard matches
# the exact active line only.
HOME_CMT="$WORK/home-cmt"; mkdir -p "$HOME_CMT"
printf '# OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS was here once\n' > "$HOME_CMT/.zshrc"
env HOME="$HOME_CMT" SHELL=/bin/zsh bash "$REPO/install.sh" --harness=opencode "$T_BOTH" >/dev/null 2>&1
check "a stale comment does not suppress the export" \
  grep -q '^export OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true$' "$HOME_CMT/.zshrc"

HOME_CLA="$WORK/home-cla"; mkdir -p "$HOME_CLA"
env HOME="$HOME_CLA" SHELL=/bin/zsh bash "$REPO/install.sh" "$T_DEFAULT" >/dev/null 2>&1
refute "a claude-only install touches no shell profile" \
  grep -qs OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS "$HOME_CLA/.zshrc"

HOME_OPT="$WORK/home-opt"; mkdir -p "$HOME_OPT"
env HOME="$HOME_OPT" SHELL=/bin/zsh bash "$REPO/install.sh" --harness=opencode --no-background-subagents-env "$T_BOTH" >/dev/null 2>&1
refute "--no-background-subagents-env writes nothing" \
  grep -qs OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS "$HOME_OPT/.zshrc"

# update brings the env wiring to an EXISTING opencode install too.
ENV_UPD="$WORK/env-upd"; mkdir -p "$ENV_UPD/.opencode/plugin" "$ENV_UPD/company/state"
cp "$REPO/.opencode/plugin/company-harness.js" "$ENV_UPD/.opencode/plugin/" 2>/dev/null
printf '{}' > "$ENV_UPD/company/state/install-manifest.json"
HOME_UPD="$WORK/home-upd"; mkdir -p "$HOME_UPD"
env HOME="$HOME_UPD" SHELL=/bin/bash bash "$REPO/update.sh" "$ENV_UPD" >/dev/null 2>&1
check "updating an existing opencode project wires the env (bash rc)" \
  grep -q '^export OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true$' "$HOME_UPD/.bashrc"
env HOME="$HOME_UPD" SHELL=/bin/bash bash "$REPO/update.sh" --check "$ENV_UPD" >/dev/null 2>&1
refute "--check never writes the env" \
  bash -c "test \"\$(grep -c claude-company '$HOME_UPD/.bashrc')\" -gt 1"

printf '\n================ SUMMARY ================\n'
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then printf 'ALL GREEN\n'; exit 0; else printf 'RED\n'; exit 1; fi
