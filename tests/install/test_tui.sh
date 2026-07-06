#!/usr/bin/env bash
# tests/install/test_tui.sh - non-interactive coverage for the `install` TUI.
#
# The interactive TUI paths are exercised by humans. These tests cover the
# plain / non-TTY contract: help, plain install parity with bare install.sh,
# argument validation, gate detection, and NO_COLOR cleanliness.
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TEST_DIR/../.." && pwd)"
INSTALL="$REPO/install"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }

WORK="$(mktemp -d -t cctui.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# recursive checksum snapshot, excluding adherence.log (touched every run)
snapshot() {
  local dir="$1"
  ( cd "$dir" && find . -type f ! -name 'adherence.log' | LC_ALL=C sort |
    while IFS= read -r f; do
      printf '%s:' "$f"; cksum < "$f" | awk '{print $1, $2}'
    done )
}

echo "== python source compiles =="
if python3 -m py_compile "$INSTALL"; then pass "install compiles clean"
else fail "install compiles clean"; fi

echo "== --help =="
"$INSTALL" --help >"$WORK/help.out" 2>&1
if [ $? -eq 0 ]; then pass "--help exits 0"; else fail "--help exits 0"; fi
grep -qi 'usage' "$WORK/help.out" && pass "--help mentions usage" \
  || fail "--help mentions usage"

echo "== plain install parity with bare install.sh =="
A="$WORK/viaTUI"; B="$WORK/bare"; mkdir -p "$A" "$B"
git -C "$A" init -q; git -C "$B" init -q
"$INSTALL" --yes --target "$A" >"$WORK/a.out" 2>&1
RC_A=$?
bash "$REPO/install.sh" "$B" >"$WORK/b.out" 2>&1
RC_B=$?
[ "$RC_A" -eq 0 ] && pass "plain install exits 0" \
  || { fail "plain install exits 0 (rc=$RC_A)"; cat "$WORK/a.out"; }
if diff -r "$A" "$B" 2>/dev/null | grep -qv 'adherence.log'; then
  fail "plain tree matches bare install.sh"
  diff -r "$A" "$B" | grep -v adherence | head -20
else
  # confirm the only differences (if any) are adherence.log lines
  DIFFOUT="$(diff -r "$A" "$B" 2>&1 | grep -v 'adherence.log')"
  [ -z "$DIFFOUT" ] && pass "plain tree matches bare install.sh" \
    || { fail "plain tree matches bare install.sh"; printf '%s\n' "$DIFFOUT" | head; }
fi

echo "== missing target -> usage on stderr, exit 1 =="
"$INSTALL" --plain </dev/null >"$WORK/mt.out" 2>"$WORK/mt.err"
RC=$?
[ "$RC" -eq 1 ] && pass "missing target exits 1" || fail "missing target exits 1 (rc=$RC)"
grep -qi 'usage' "$WORK/mt.err" && pass "missing target prints usage to stderr" \
  || fail "missing target prints usage to stderr"

echo "== piped stdin (non-TTY) without target -> exit 1 =="
printf '\n' | "$INSTALL" >"$WORK/ps.out" 2>"$WORK/ps.err"
RC=$?
[ "$RC" -eq 1 ] && pass "piped stdin without target exits 1" \
  || fail "piped stdin without target exits 1 (rc=$RC)"

echo "== nonexistent dir -> nonzero + helpful message =="
"$INSTALL" --plain --target "$WORK/nope" </dev/null >"$WORK/ne.out" 2>"$WORK/ne.err"
RC=$?
[ "$RC" -ne 0 ] && pass "nonexistent dir nonzero" || fail "nonexistent dir nonzero"
grep -qi 'does not exist' "$WORK/ne.err" && pass "nonexistent dir helpful message" \
  || fail "nonexistent dir helpful message"

echo "== target = repo itself -> refused, nonzero =="
"$INSTALL" --plain --target "$REPO" </dev/null >"$WORK/rr.out" 2>"$WORK/rr.err"
RC=$?
[ "$RC" -ne 0 ] && pass "repo-itself refused nonzero" || fail "repo-itself refused nonzero"
grep -qi 'repo itself' "$WORK/rr.err" && pass "repo-itself helpful message" \
  || fail "repo-itself helpful message"

echo "== --yes --detect-gates writes real gates for a node project =="
G="$WORK/pkg"; mkdir -p "$G"; git -C "$G" init -q
cat > "$G/package.json" <<'JSON'
{"name":"demo","scripts":{"test":"echo hi","lint":"echo lint"}}
JSON
"$INSTALL" --yes --detect-gates --target "$G" >"$WORK/g.out" 2>&1
RC=$?
[ "$RC" -eq 0 ] && pass "detect-gates install exits 0" \
  || { fail "detect-gates install exits 0 (rc=$RC)"; cat "$WORK/g.out"; }
if grep -qi 'CONFIGURE ME' "$G/company/gates.config"; then
  fail "gates.config is non-placeholder after detect"
else
  grep -q 'npm test' "$G/company/gates.config" \
    && pass "gates.config is non-placeholder after detect" \
    || fail "gates.config is non-placeholder after detect"
fi

echo "== --no-detect-gates leaves placeholders =="
G2="$WORK/pkg2"; mkdir -p "$G2"; git -C "$G2" init -q
cat > "$G2/package.json" <<'JSON'
{"name":"demo","scripts":{"test":"echo hi"}}
JSON
"$INSTALL" --yes --no-detect-gates --target "$G2" >/dev/null 2>&1
grep -qi 'CONFIGURE ME' "$G2/company/gates.config" \
  && pass "no-detect-gates keeps placeholders" \
  || fail "no-detect-gates keeps placeholders"

echo "== NO_COLOR output contains no ESC bytes =="
N="$WORK/nc"; mkdir -p "$N"; git -C "$N" init -q
NO_COLOR=1 "$INSTALL" --yes --target "$N" >"$WORK/nc.out" 2>&1
ESC_COUNT=$(grep -c $'\x1b' "$WORK/nc.out")
[ "$ESC_COUNT" -eq 0 ] && pass "NO_COLOR emits no ESC bytes" \
  || fail "NO_COLOR emits no ESC bytes (count=$ESC_COUNT)"

echo "== --no-color flag also emits no ESC bytes =="
N2="$WORK/nc2"; mkdir -p "$N2"; git -C "$N2" init -q
"$INSTALL" --yes --no-color --target "$N2" >"$WORK/nc2.out" 2>&1
ESC2=$(grep -c $'\x1b' "$WORK/nc2.out")
[ "$ESC2" -eq 0 ] && pass "--no-color emits no ESC bytes" \
  || fail "--no-color emits no ESC bytes (count=$ESC2)"

echo "== idempotent re-run of plain install is a no-op =="
R="$WORK/rerun"; mkdir -p "$R"; git -C "$R" init -q
"$INSTALL" --yes --no-detect-gates --target "$R" >/dev/null 2>&1
SNAP_A="$(snapshot "$R")"
"$INSTALL" --yes --no-detect-gates --target "$R" >/dev/null 2>&1
SNAP_B="$(snapshot "$R")"
[ "$SNAP_A" = "$SNAP_B" ] && pass "second plain run is a no-op" \
  || { fail "second plain run is a no-op"; diff <(printf '%s\n' "$SNAP_A") \
       <(printf '%s\n' "$SNAP_B") | head; }

echo
echo "================ SUMMARY ================"
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && { echo "ALL GREEN"; exit 0; } || { echo "TESTS FAILED"; exit 1; }
