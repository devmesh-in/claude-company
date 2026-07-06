#!/usr/bin/env bash
# tests/install/run_tests.sh - exercises install.sh and run-gates.sh.
#
# These tests are self-contained: they build a synthetic "source repo" that
# contains the real install.sh / run-gates.sh / gates.config / .mcp.json plus
# STUBS for the files owned by other agents (agents, hooks, skills, canon docs,
# settings.json). This keeps the suite deterministic and independent of whether
# those other files exist yet in the real repo.
set -uo pipefail

# --- locate the real repo (two levels up from this test file) -------------
TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TEST_DIR/../.." && pwd)"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
check() { # check <desc> <condition-cmd...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}

WORK="$(mktemp -d -t ccinstall.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# --- build a synthetic source repo ----------------------------------------
SRC="$WORK/src"
build_source() {
  rm -rf "$SRC"; mkdir -p "$SRC"
  cp "$REPO/install.sh" "$SRC/install.sh"
  mkdir -p "$SRC/.claude/agents" "$SRC/.claude/hooks" "$SRC/.claude/skills/orchestrator"
  mkdir -p "$SRC/company/templates" "$SRC/company/specs" "$SRC/company/briefs" "$SRC/company/change-requests"

  # stubs for other-agent-owned files
  printf 'stub agent\n' > "$SRC/.claude/agents/dev.md"
  printf '#!/usr/bin/env python3\nprint("no slop")\n' > "$SRC/.claude/hooks/no_slop.py"
  printf '#!/usr/bin/env python3\nimport sys\nprint("gate_stamp", sys.argv)\n' > "$SRC/.claude/hooks/gate_stamp.py"
  printf 'stub skill\n' > "$SRC/.claude/skills/orchestrator/SKILL.md"
  printf '# ORCHESTRATOR\n' > "$SRC/ORCHESTRATOR.md"
  printf '# METHOD\n' > "$SRC/company/METHOD.md"
  printf '# GATES\n' > "$SRC/company/GATES.md"
  printf '# EXTENDING\n' > "$SRC/company/EXTENDING.md"
  printf '{"frozen": []}\n' > "$SRC/company/frozen-surfaces.json"
  printf '# spec template\n' > "$SRC/company/templates/spec.md"

  # our real files
  cp "$REPO/company/run-gates.sh" "$SRC/company/run-gates.sh"
  cp "$REPO/company/gates.config" "$SRC/company/gates.config"
  cp "$REPO/.mcp.json" "$SRC/.mcp.json"

  # our settings.json fixture (stands in for the other agent's final file)
  cat > "$SRC/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": ".claude/hooks/no_slop.py"}]}
    ]
  },
  "permissions": {
    "deny": ["Read(./company/state/adherence.log)"]
  }
}
JSON
}

run_install() { bash "$SRC/install.sh" "$1" >"$WORK/install.out" 2>&1; }

# recursive checksum snapshot, excluding adherence.log (it is touched every run)
snapshot() {
  local dir="$1"
  ( cd "$dir" && find . -type f ! -name 'adherence.log' | LC_ALL=C sort | while IFS= read -r f; do
      printf '%s:' "$f"; cksum < "$f" | awk '{print $1, $2}'
    done )
}

json_valid() { python3 -m json.tool "$1" >/dev/null 2>&1; }
grep_count() { grep -c "$1" "$2" 2>/dev/null || echo 0; }

build_source

echo "== usage / guard tests =="
bash "$SRC/install.sh" >/dev/null 2>&1; [ $? -ne 0 ] && pass "no-arg errors" || fail "no-arg errors"
bash "$SRC/install.sh" "$WORK/does-not-exist" >/dev/null 2>&1; [ $? -ne 0 ] && pass "missing target errors" || fail "missing target errors"
bash "$SRC/install.sh" "$SRC" >/dev/null 2>&1; [ $? -ne 0 ] && pass "refuses to install into own repo" || fail "refuses to install into own repo"

echo "== fresh empty target =="
T1="$WORK/t1"; mkdir -p "$T1"
if run_install "$T1"; then pass "install succeeds on empty dir"; else fail "install succeeds on empty dir"; cat "$WORK/install.out"; fi
check "agents copied"            test -f "$T1/.claude/agents/dev.md"
check "hooks copied"             test -f "$T1/.claude/hooks/no_slop.py"
check "gate_stamp copied"        test -f "$T1/.claude/hooks/gate_stamp.py"
check "skills copied"            test -f "$T1/.claude/skills/orchestrator/SKILL.md"
check "ORCHESTRATOR.md copied"   test -f "$T1/ORCHESTRATOR.md"
check "METHOD.md copied"         test -f "$T1/company/METHOD.md"
check "GATES.md copied"          test -f "$T1/company/GATES.md"
check "EXTENDING.md copied"      test -f "$T1/company/EXTENDING.md"
check "templates copied"         test -f "$T1/company/templates/spec.md"
check "run-gates.sh copied"      test -f "$T1/company/run-gates.sh"
check "run-gates.sh executable"  test -x "$T1/company/run-gates.sh"
check "gates.config copied"      test -f "$T1/company/gates.config"
check "frozen-surfaces copied"   test -f "$T1/company/frozen-surfaces.json"
check ".mcp.json copied"         test -f "$T1/.mcp.json"
check "settings.json copied"     test -f "$T1/.claude/settings.json"
check "STATUS.md stub"           test -f "$T1/company/state/STATUS.md"
check "RESUME.md stub"           test -f "$T1/company/state/RESUME.md"
check "WORRIES.md stub"          test -f "$T1/company/state/WORRIES.md"
check "DECISIONS.md stub"        test -f "$T1/company/state/DECISIONS.md"
check "adherence.log touched"    test -f "$T1/company/state/adherence.log"
check "specs dir"                test -d "$T1/company/specs"
check "briefs dir"               test -d "$T1/company/briefs"
check "change-requests dir"      test -d "$T1/company/change-requests"
check "CLAUDE.md created"        test -f "$T1/CLAUDE.md"
check "CLAUDE.md has begin"      grep -q "claude-company:begin" "$T1/CLAUDE.md"
check "CLAUDE.md has end"        grep -q "claude-company:end" "$T1/CLAUDE.md"
check "settings.json valid"      json_valid "$T1/.claude/settings.json"
check ".mcp.json valid"          json_valid "$T1/.mcp.json"

echo "== existing CLAUDE.md + settings.json with user's own hook =="
T2="$WORK/t2"; mkdir -p "$T2/.claude"
cat > "$T2/CLAUDE.md" <<'MD'
# My Project

Some existing project notes the user wrote.
MD
cat > "$T2/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Write", "hooks": [{"type": "command", "command": "my-own-hook.sh"}]}
    ]
  },
  "permissions": {
    "deny": ["Read(./private/**)"]
  }
}
JSON
run_install "$T2" || { fail "install on existing config"; cat "$WORK/install.out"; }
check "settings.json still valid"        json_valid "$T2/.claude/settings.json"
check "user hook preserved"              grep -q "my-own-hook.sh" "$T2/.claude/settings.json"
check "our hook added"                   grep -q "no_slop.py" "$T2/.claude/settings.json"
check "user deny preserved"              grep -q "private/\*\*" "$T2/.claude/settings.json"
check "our deny added"                   grep -q "adherence.log" "$T2/.claude/settings.json"
check "user CLAUDE.md content preserved" grep -q "Some existing project notes" "$T2/CLAUDE.md"
check "company block appended"           grep -q "claude-company:begin" "$T2/CLAUDE.md"
# exactly one marker pair
[ "$(grep_count 'claude-company:begin' "$T2/CLAUDE.md")" -eq 1 ] && pass "single begin marker" || fail "single begin marker"

echo "== .mcp.json merge preserves user server =="
T3="$WORK/t3"; mkdir -p "$T3"
cat > "$T3/.mcp.json" <<'JSON'
{"mcpServers": {"myserver": {"command": "foo", "args": ["bar"]}}}
JSON
run_install "$T3" || { fail "install on existing .mcp.json"; cat "$WORK/install.out"; }
check ".mcp.json valid"           json_valid "$T3/.mcp.json"
check "user mcp server preserved" grep -q "myserver" "$T3/.mcp.json"
check "playwright added"          grep -q "playwright" "$T3/.mcp.json"

echo "== state preservation =="
T4="$WORK/t4"; mkdir -p "$T4/company/state"
printf '# STATUS\n\nRED: the payments module has no tests yet.\n' > "$T4/company/state/STATUS.md"
printf 'user gates\n' > "$T4/company/gates.config.keep" # sentinel unrelated
cat > "$T4/company/gates.config" <<'JSON'
{"gates":[{"name":"mytest","command":"echo hi","blocking":true}]}
JSON
run_install "$T4" || { fail "install with pre-seeded state"; cat "$WORK/install.out"; }
check "STATUS.md content untouched"  grep -q "payments module has no tests" "$T4/company/state/STATUS.md"
check "STATUS.md not overwritten by stub" bash -c '! grep -q "maintained by the orchestrator" "'"$T4"'/company/state/STATUS.md"'
check "user gates.config preserved"  grep -q "mytest" "$T4/company/gates.config"

echo "== idempotency (second run changes nothing except adherence.log) =="
T5="$WORK/t5"; mkdir -p "$T5"
run_install "$T5" || fail "first install"
SNAP_A="$(snapshot "$T5")"
run_install "$T5" || fail "second install"
SNAP_B="$(snapshot "$T5")"
if [ "$SNAP_A" = "$SNAP_B" ]; then pass "second run is a no-op (checksums match)"; else
  fail "second run is a no-op (checksums match)"
  diff <(printf '%s\n' "$SNAP_A") <(printf '%s\n' "$SNAP_B") | head -20
fi
# marker not duplicated after re-run
[ "$(grep_count 'claude-company:begin' "$T5/CLAUDE.md")" -eq 1 ] && pass "marker not duplicated on re-run" || fail "marker not duplicated on re-run"

echo "== marker block replacement (not duplication) =="
T6="$WORK/t6"; mkdir -p "$T6"
cat > "$T6/CLAUDE.md" <<'MD'
# Project

<!-- claude-company:begin -->
OLD STALE BLOCK CONTENT
<!-- claude-company:end -->

Trailing user notes.
MD
run_install "$T6" || fail "install over stale marker block"
[ "$(grep_count 'claude-company:begin' "$T6/CLAUDE.md")" -eq 1 ] && pass "single begin after replace" || fail "single begin after replace"
[ "$(grep_count 'claude-company:end' "$T6/CLAUDE.md")" -eq 1 ] && pass "single end after replace" || fail "single end after replace"
check "stale block content removed"  bash -c '! grep -q "OLD STALE BLOCK CONTENT" "'"$T6"'/CLAUDE.md"'
check "new block content present"    grep -q "hierarchical SDLC system" "$T6/CLAUDE.md"
check "trailing user notes kept"     grep -q "Trailing user notes" "$T6/CLAUDE.md"

echo
echo "== run-gates.sh tests =="

make_gates_fixture() { # <dir> <stamper: real|missing>
  local d="$1" stamper="$2"
  rm -rf "$d"; mkdir -p "$d/company" "$d/.claude/hooks"
  cp "$REPO/company/run-gates.sh" "$d/company/run-gates.sh"
  if [ "$stamper" = "real" ]; then
    cat > "$d/.claude/hooks/gate_stamp.py" <<'PY'
#!/usr/bin/env python3
import sys, os
rec = os.path.join(os.path.dirname(__file__), "stamp_argv.txt")
with open(rec, "w") as f:
    f.write("\n".join(sys.argv))
print("stamped")
PY
  fi
}

echo "-- passing + failing gate --"
GF="$WORK/gates_mixed"; make_gates_fixture "$GF" real
cat > "$GF/company/gates.config" <<'JSON'
{"gates":[{"name":"tests","command":"echo good","blocking":true},{"name":"lint","command":"echo bad && exit 1","blocking":true}]}
JSON
CLAUDE_PROJECT_DIR="$GF" bash "$GF/company/run-gates.sh" >"$WORK/gates.out" 2>&1
RC=$?
[ "$RC" -ne 0 ] && pass "mixed gates exit non-zero (rc=$RC)" || fail "mixed gates exit non-zero (rc=$RC)"
check "stamping attempted"          test -f "$GF/.claude/hooks/stamp_argv.txt"
check "stamp argv has --results"    grep -q -- "--results" "$GF/.claude/hooks/stamp_argv.txt"
check "stamp json has tests gate"   grep -q '"name": "tests"' "$GF/.claude/hooks/stamp_argv.txt"
check "stamp json marks tests ok"   grep -q '"name": "tests", "ok": true' "$GF/.claude/hooks/stamp_argv.txt"
check "stamp json marks lint fail"  grep -q '"name": "lint", "ok": false' "$GF/.claude/hooks/stamp_argv.txt"
check "ladder printed"              grep -q "Gate ladder" "$WORK/gates.out"

echo "-- all passing gates --"
GP="$WORK/gates_pass"; make_gates_fixture "$GP" real
cat > "$GP/company/gates.config" <<'JSON'
{"gates":[{"name":"tests","command":"echo good","blocking":true}]}
JSON
CLAUDE_PROJECT_DIR="$GP" bash "$GP/company/run-gates.sh" >/dev/null 2>&1
RC=$?
[ "$RC" -eq 0 ] && pass "all-pass gates exit zero" || fail "all-pass gates exit zero (rc=$RC)"
check "all-pass stamped"            test -f "$GP/.claude/hooks/stamp_argv.txt"

echo "-- missing stamper tolerated --"
GM="$WORK/gates_nostamp"; make_gates_fixture "$GM" missing
cat > "$GM/company/gates.config" <<'JSON'
{"gates":[{"name":"tests","command":"echo good","blocking":true}]}
JSON
CLAUDE_PROJECT_DIR="$GM" bash "$GM/company/run-gates.sh" >"$WORK/gates_nostamp.out" 2>&1
RC=$?
[ "$RC" -eq 0 ] && pass "missing stamper still exits per gate result" || fail "missing stamper still exits per gate result (rc=$RC)"
check "warns about missing stamper" grep -q "gate stamper not found" "$WORK/gates_nostamp.out"

echo "-- no gates configured --"
GN="$WORK/gates_none"; make_gates_fixture "$GN" real
cat > "$GN/company/gates.config" <<'JSON'
{"gates":[]}
JSON
CLAUDE_PROJECT_DIR="$GN" bash "$GN/company/run-gates.sh" >"$WORK/gates_none.out" 2>&1
RC=$?
[ "$RC" -eq 0 ] && pass "empty gates exit zero" || fail "empty gates exit zero (rc=$RC)"
check "prints no-gates message"     grep -q "no gates configured" "$WORK/gates_none.out"
check "no stamp when no gates"      bash -c '! test -f "'"$GN"'/.claude/hooks/stamp_argv.txt"'

echo "-- missing config --"
GC="$WORK/gates_noconfig"; make_gates_fixture "$GC" real
rm -f "$GC/company/gates.config"
CLAUDE_PROJECT_DIR="$GC" bash "$GC/company/run-gates.sh" >"$WORK/gates_noconfig.out" 2>&1
RC=$?
[ "$RC" -eq 0 ] && pass "missing config exits zero" || fail "missing config exits zero (rc=$RC)"
check "prints no-gates message"     grep -q "no gates configured" "$WORK/gates_noconfig.out"

echo
echo "================ SUMMARY ================"
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && { echo "ALL GREEN"; exit 0; } || { echo "TESTS FAILED"; exit 1; }
