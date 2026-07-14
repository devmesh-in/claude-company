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

# --- update: top-level help lists it, subcommand help, usage/exit codes ----
echo "== update subcommand: help + usage + exit codes =="
node "$BIN" --help >"$WORK/h.out" 2>/dev/null
grep -qi '^  claude-company update' "$WORK/h.out" && pass "top-level help lists update" \
  || fail "top-level help lists update"

node "$BIN" update --help >"$WORK/uh.out" 2>/dev/null; RC=$?
[ "$RC" -eq 0 ] && pass "update --help exits 0" || fail "update --help exits 0 (rc=$RC)"
grep -qi 'never overwrites' "$WORK/uh.out" && pass "update --help states the preserve guarantee" \
  || fail "update --help states the preserve guarantee"
grep -q -- '--check' "$WORK/uh.out" && pass "update --help documents --check" || fail "update --help documents --check"

node "$BIN" update >"$WORK/nt.out" 2>&1; RC=$?
[ "$RC" -eq 1 ] && pass "update with no target exits 1 (usage)" || fail "update no target exits 1 (rc=$RC)"

node "$BIN" update "$WORK/does-not-exist" >"$WORK/ne.out" 2>&1; RC=$?
[ "$RC" -ne 0 ] && pass "update on missing target surfaces nonzero (rc=$RC)" \
  || fail "update on missing target surfaces nonzero"

# real install then update via the bin: pristine -> exit 0, no .new
UT="$WORK/proj"; mkdir -p "$UT"; git -C "$UT" init -q
"$INSTALL" --yes --target "$UT" --plain --no-detect-gates >/dev/null 2>&1
node "$BIN" update "$UT" --check >"$WORK/uc.out" 2>&1; RC=$?
[ "$RC" -eq 0 ] && pass "update --check via bin exits 0" || fail "update --check via bin exits 0 (rc=$RC)"
if find "$UT" -name '*.new' | grep -q .; then fail "update --check wrote no .new"; else pass "update --check wrote no .new"; fi

# native Windows: friendly unsupported message, exit 2
WIN_OUT="$(BIN="$BIN" node -e '
Object.defineProperty(process, "platform", { value: "win32" });
process.argv = [process.argv[0], "cli", "update", "."];
require(process.env.BIN);
' 2>&1)"; WIN_CODE=$?
if [ "$WIN_CODE" -eq 2 ] && printf '%s' "$WIN_OUT" | grep -q "Windows via WSL"; then
  pass "win32 update refused with WSL guidance (exit 2)"
else
  fail "win32 update refused with WSL guidance (exit $WIN_CODE)"
fi

# --- update self-update: currency check, handoff, fail-open, flags ---------
# All seams are env-injected (CC_LATEST_VERSION bypasses the network entirely);
# no assertion here ever touches the live registry. The re-exec vehicle is a
# stub `npx` on PATH so the handoff is observed without a real npm fetch.
echo "== update self-update (FR-SU-01..12) =="
STUB="$WORK/stub"; mkdir -p "$STUB"
cat > "$STUB/npx" <<'STUBEOF'
#!/usr/bin/env bash
printf 'STUB_NPX_ARGS=[%s]\n' "$*"
printf 'STUB_NPX_DONE=%s\n' "${CC_SELFUPDATE_DONE:-unset}"
exit 0
STUBEOF
chmod +x "$STUB/npx"

SU="$WORK/suproj"; mkdir -p "$SU"; git -C "$SU" init -q
"$INSTALL" --yes --target "$SU" --plain --no-detect-gates >/dev/null 2>&1

# forced-newer -> exactly one handoff line, npx invoked with the child marker
CC_LATEST_VERSION=99.0.0 PATH="$STUB:$PATH" node "$BIN" update "$SU" >"$WORK/su_h.out" 2>&1; RC=$?
grep -q 'self-update: handing off to claude-company@99.0.0 \.\.\.' "$WORK/su_h.out" \
  && pass "forced-newer prints the handoff line" || { fail "forced-newer prints the handoff line"; cat "$WORK/su_h.out"; }
grep -q 'STUB_NPX_ARGS=\[-y claude-company@99.0.0 update' "$WORK/su_h.out" \
  && pass "handoff execs npx -y claude-company@<latest> update <args>" || fail "handoff execs the right npx line"
grep -q 'STUB_NPX_DONE=1' "$WORK/su_h.out" \
  && pass "handoff sets CC_SELFUPDATE_DONE=1 on the child" || fail "handoff sets CC_SELFUPDATE_DONE=1"
[ "$RC" -eq 0 ] && pass "handoff returns the child's exit code (0)" || fail "handoff returns child code (rc=$RC)"
grep -q 'update - preflight' "$WORK/su_h.out" && fail "handoff must not run the local update" || pass "handoff skips the local update"

# guarded child (CC_SELFUPDATE_DONE=1) -> no handoff, normal update proceeds
CC_LATEST_VERSION=99.0.0 CC_SELFUPDATE_DONE=1 PATH="$STUB:$PATH" node "$BIN" update "$SU" --check >"$WORK/su_g.out" 2>&1; RC=$?
grep -q 'handing off' "$WORK/su_g.out" && fail "guarded child does not re-hand-off" || pass "guarded child does not re-hand-off"
[ "$RC" -eq 0 ] && grep -q 'update - preflight' "$WORK/su_g.out" \
  && pass "guarded child runs the normal update" || fail "guarded child runs the normal update (rc=$RC)"

# equal version -> silent, normal update
CC_LATEST_VERSION="$VERSION" node "$BIN" update "$SU" --check >"$WORK/su_e.out" 2>&1; RC=$?
grep -q 'self-update:' "$WORK/su_e.out" && fail "equal version is silent" || pass "equal version is silent"
[ "$RC" -eq 0 ] && pass "equal-version update exits 0" || fail "equal-version update exits 0 (rc=$RC)"

# unreachable registry -> one WARN line, update still completes (fail open)
CC_REGISTRY_URL="https://127.0.0.1:9" CC_REGISTRY_TIMEOUT_MS=300 node "$BIN" update "$SU" --check >"$WORK/su_u.out" 2>&1; RC=$?
grep -q 'self-update: WARN' "$WORK/su_u.out" && pass "unreachable registry prints one WARN" || { fail "unreachable registry prints WARN"; cat "$WORK/su_u.out"; }
[ "$RC" -eq 0 ] && pass "unreachable-registry update still completes (0)" || fail "unreachable-registry update completes (rc=$RC)"

# --no-self-update with a newer version -> no handoff, no staleness, no network
CC_LATEST_VERSION=99.0.0 node "$BIN" update "$SU" --check --no-self-update >"$WORK/su_n.out" 2>&1; RC=$?
grep -q 'self-update:' "$WORK/su_n.out" && fail "--no-self-update skips the whole step" || pass "--no-self-update skips the whole step"
[ "$RC" -eq 0 ] && pass "--no-self-update update exits 0" || fail "--no-self-update update exits 0 (rc=$RC)"

# --check with a newer version -> staleness line, no re-exec, tree unchanged
CC_LATEST_VERSION=99.0.0 node "$BIN" update "$SU" --check >"$WORK/su_c.out" 2>&1; RC=$?
grep -q 'a newer claude-company is available' "$WORK/su_c.out" \
  && pass "--check reports staleness in the plan" || fail "--check reports staleness"
grep -q 'handing off' "$WORK/su_c.out" && fail "--check never re-execs" || pass "--check never re-execs"
if find "$SU" -name '*.new' | grep -q .; then fail "--check with newer wrote no .new"; else pass "--check with newer wrote no .new"; fi
[ "$RC" -eq 0 ] && pass "--check-with-newer exits 0" || fail "--check-with-newer exits 0 (rc=$RC)"

echo
echo "================ SUMMARY ================"
printf 'PASS: %d   FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && { echo "ALL GREEN"; exit 0; } || { echo "TESTS FAILED"; exit 1; }
