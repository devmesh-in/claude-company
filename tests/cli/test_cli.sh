#!/usr/bin/env bash
# tests/cli/test_cli.sh - coverage for the npm bin wrapper (bin/claude-company.js).
#
# The wrapper owns the subcommand parse and hands `install` to the Node
# installer in lib/. These tests prove: version/help/unknown-command behavior,
# that a real install through the bin matches a bare ./install, relative-target
# correctness, exit code passthrough, python3 preflight hard-fail, and the npm
# pack manifest (payload present, dev-only excluded, root install is a shim).
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TEST_DIR/../.." && pwd)"
BIN="$REPO/bin/claude-company.js"
INSTALL="$REPO/install"

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }

WORK="$(mktemp -d -t cccli.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

VERSION="$(node -e 'process.stdout.write(require("'"$REPO"'/package.json").version)')"

# --- 1. --version ----------------------------------------------------------
echo "== --version =="
OUT="$(node "$BIN" --version 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && pass "--version exits 0" || fail "--version exits 0 (rc=$RC)"
[ "$OUT" = "$VERSION" ] && pass "--version prints package.json version ($VERSION)" \
  || fail "--version prints package.json version (got '$OUT', want '$VERSION')"

# --- 2. --help -------------------------------------------------------------
echo "== --help =="
node "$BIN" --help >"$WORK/help.out" 2>/dev/null; RC=$?
[ "$RC" -eq 0 ] && pass "--help exits 0" || fail "--help exits 0 (rc=$RC)"
# help must go to stdout so it pipes (stderr was discarded above)
[ -s "$WORK/help.out" ] && pass "--help writes to stdout (pipeable)" \
  || fail "--help writes to stdout (pipeable)"
grep -qi 'install' "$WORK/help.out" && pass "--help mentions install" \
  || fail "--help mentions install"
grep -qi 'npx' "$WORK/help.out" && pass "--help mentions npx" \
  || fail "--help mentions npx"

# --- 3. unknown subcommand -------------------------------------------------
echo "== unknown subcommand =="
node "$BIN" frobnicate >"$WORK/unk.out" 2>&1; RC=$?
[ "$RC" -eq 1 ] && pass "unknown subcommand exits 1" || fail "unknown subcommand exits 1 (rc=$RC)"

# --- 4. install parity with bare ./install ---------------------------------
echo "== install via bin matches bare ./install =="
A="$WORK/viaBin"; B="$WORK/bare"; mkdir -p "$A" "$B"
git -C "$A" init -q; git -C "$B" init -q
node "$BIN" install "$A" --yes --plain --no-detect-gates >"$WORK/a.out" 2>&1
RC_A=$?
"$INSTALL" --yes --target "$B" --plain --no-detect-gates >"$WORK/b.out" 2>&1
RC_B=$?
[ "$RC_A" -eq 0 ] && pass "bin install exits 0" \
  || { fail "bin install exits 0 (rc=$RC_A)"; cat "$WORK/a.out"; }
[ "$RC_B" -eq 0 ] && pass "bare install exits 0" \
  || { fail "bare install exits 0 (rc=$RC_B)"; cat "$WORK/b.out"; }
DIFFOUT="$(diff -r "$A" "$B" 2>&1 | grep -v 'adherence.log')"
[ -z "$DIFFOUT" ] && pass "bin tree matches bare install tree" \
  || { fail "bin tree matches bare install tree"; printf '%s\n' "$DIFFOUT" | head; }

# --- 5. relative-target correctness ----------------------------------------
echo "== relative target resolves against user's cwd =="
PARENT="$WORK/relparent"; NAME="proj"; mkdir -p "$PARENT/$NAME"
git -C "$PARENT/$NAME" init -q
( cd "$PARENT" && node "$BIN" install "./$NAME" --yes --plain --no-detect-gates ) \
  >"$WORK/rel.out" 2>&1
RC=$?
[ "$RC" -eq 0 ] && pass "relative-target install exits 0" \
  || { fail "relative-target install exits 0 (rc=$RC)"; cat "$WORK/rel.out"; }
[ -f "$PARENT/$NAME/company/METHOD.md" ] \
  && pass "install landed in the relative target dir" \
  || fail "install landed in the relative target dir"
[ ! -e "$PARENT/company" ] \
  && pass "nothing installed into the parent by mistake" \
  || fail "nothing installed into the parent by mistake"

# --- 6. exit-code passthrough ----------------------------------------------
echo "== nonexistent target: installer's nonzero code surfaces =="
node "$BIN" install "$WORK/does-not-exist" --yes --plain >"$WORK/ne.out" 2>&1
RC=$?
[ "$RC" -ne 0 ] && pass "nonexistent target surfaces nonzero (rc=$RC)" \
  || fail "nonexistent target surfaces nonzero (rc=$RC)"

# --- 7. missing-python simulation ------------------------------------------
# The bin no longer needs Python to start; python3 is a hard preflight probe.
# With git and bash present but python3 absent, plain-mode preflight must
# hard-fail with exit 2 and name python3.
echo "== missing python -> preflight exit 2 naming python3 =="
PYENV="$WORK/nopy"; mkdir -p "$PYENV"
for t in node git bash; do
  b="$(command -v "$t")"; [ -n "$b" ] && ln -s "$b" "$PYENV/$t"
done
T7="$WORK/t7"; mkdir -p "$T7"; git -C "$T7" init -q
PATH="$PYENV" node "$BIN" install "$T7" --yes --plain >"$WORK/np.out" 2>"$WORK/np.err"
RC=$?
[ "$RC" -eq 2 ] && pass "missing python exits 2 (preflight)" || fail "missing python exits 2 (rc=$RC)"
grep -qi 'python3' "$WORK/np.err" && pass "missing python names python3 in message" \
  || { fail "missing python names python3 in message"; cat "$WORK/np.err"; }

# --- 8. npm pack manifest --------------------------------------------------
echo "== npm pack manifest contains payload, excludes dev-only =="
( cd "$REPO" && npm pack --dry-run --json 2>/dev/null ) \
  | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const j=JSON.parse(s);j[0].files.forEach(f=>console.log(f.path))})' \
  > "$WORK/pack.list"

want_present() {
  grep -qxF "$1" "$WORK/pack.list" && pass "pack contains $1" \
    || fail "pack MISSING $1"
}
want_absent() {
  if grep -qE "$1" "$WORK/pack.list"; then
    fail "pack should NOT contain $1"; grep -E "$1" "$WORK/pack.list" | head
  else
    pass "pack excludes $1"
  fi
}

want_present ".claude/agents/developer.md"
want_present ".claude/hooks/guard_commit.py"
want_present ".claude/settings.json"
want_present ".mcp.json"
want_present "company/METHOD.md"
want_present "install"
want_present "install.sh"
want_present "bin/claude-company.js"
want_present "lib/install-tui.js"
want_absent "^tests/"
want_absent "^\.assets/"
want_absent "__pycache__|\.pyc$"

# The root `install` is now a POSIX sh shim, not a Python file.
[ "$(head -1 "$INSTALL")" = "#!/bin/sh" ] && pass "packed install is a sh shim" \
  || fail "packed install is a sh shim (got '$(head -1 "$INSTALL")')"

# --- native Windows: friendly unsupported message, exit 2 ------------------
WIN_OUT="$(BIN="$BIN" node -e '
Object.defineProperty(process, "platform", { value: "win32" });
process.argv = [process.argv[0], "cli", "install", "."];
require(process.env.BIN);
' 2>&1)"; WIN_CODE=$?
if [ "$WIN_CODE" -eq 2 ] && printf '%s' "$WIN_OUT" | grep -q "Windows via WSL" \
  && printf '%s' "$WIN_OUT" | grep -q "wsl --install"; then
  pass "win32 install refused with WSL guidance (exit 2)"
else
  fail "win32 install refused with WSL guidance (exit $WIN_CODE)"
fi
# --version still works on win32
WIN_VER="$(BIN="$BIN" node -e '
Object.defineProperty(process, "platform", { value: "win32" });
process.argv = [process.argv[0], "cli", "--version"];
require(process.env.BIN);
' 2>&1)"
[ "$WIN_VER" = "$(node -p "require(\"$REPO/package.json\").version")" ] \
  && pass "win32 --version still works" || fail "win32 --version still works (got '$WIN_VER')"

echo
echo "================ SUMMARY ================"
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && { echo "ALL GREEN"; exit 0; } || { echo "TESTS FAILED"; exit 1; }
