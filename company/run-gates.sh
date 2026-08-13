#!/usr/bin/env bash
# run-gates.sh - the claude-company gate runner.
# Reads company/gates.config, runs each gate command from the project root,
# prints a gate ladder, then stamps results via .claude/hooks/gate_stamp.py.
# Every gate is blocking: exits non-zero if any gate fails.
set -euo pipefail

# --- resolve project root -------------------------------------------------
# FR-HP-28: the work tree that contains the cwd wins over CLAUDE_PROJECT_DIR.
# The harness pins CLAUDE_PROJECT_DIR to the MAIN checkout even for an agent
# whose cwd is a worktree, so trusting it first gates and stamps a tree the
# caller never built - a green stamp for somebody else's code.
# OQ-HP-14 assumption: a ladder run inside a worktree deliberately does NOT
# satisfy the main checkout's stamp. That is intended; the alternative is the
# false green this order exists to kill.
if GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" && [ -n "$GIT_ROOT" ]; then
  PROJECT_ROOT="$GIT_ROOT"
elif [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  PROJECT_ROOT="$CLAUDE_PROJECT_DIR"
else
  PROJECT_ROOT="$(pwd)"
fi

# Suite clock starts before the config parse so total= covers the whole run.
SUITE_START=$(date +%s)

CONFIG="$PROJECT_ROOT/company/gates.config"
STAMPER="$PROJECT_ROOT/.claude/hooks/gate_stamp.py"
GATE_OUT_DIR="$PROJECT_ROOT/company/state/gate-output"

# --- colors ---------------------------------------------------------------
if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BOLD=''; C_RESET=''
fi

warn() { printf '%s\n' "${C_YELLOW}warning:${C_RESET} $*" >&2; }

# --- no config / empty config ---------------------------------------------
if [ ! -f "$CONFIG" ]; then
  echo "no gates configured - see company/GATES.md"
  exit 0
fi

# --- parse config into "name<TAB>base64(command)" lines -------------------
# base64-encode the command so arbitrary shell text survives the line format.
GATE_LINES="$(python3 - "$CONFIG" <<'PY'
import base64, json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception as e:
    sys.stderr.write("failed to parse gates.config: %s\n" % e)
    sys.exit(3)
gates = data.get("gates") or []
for g in gates:
    name = str(g.get("name", "")).strip()
    cmd = g.get("command", "")
    if not name or not cmd:
        continue
    enc = base64.b64encode(cmd.encode("utf-8")).decode("ascii")
    sys.stdout.write("%s\t%s\n" % (name, enc))
PY
)"

if [ -z "$GATE_LINES" ]; then
  echo "no gates configured - see company/GATES.md"
  exit 0
fi

# --- run each gate --------------------------------------------------------
echo "${C_BOLD}Running gates from ${PROJECT_ROOT}${C_RESET}"
echo

NAMES=""
OKS=""
DETAILS_FILE="$(mktemp -t rungates.XXXXXX)"
LADDER_FILE="$(mktemp -t rungates.XXXXXX)"
OUT_FILE=""
trap 'rm -f "$DETAILS_FILE" "$LADDER_FILE" "${OUT_FILE:-}"' EXIT

ANY_FAIL=0

# Read tab-separated lines without a subshell (so vars persist in bash 3.2).
while IFS=$'\t' read -r NAME ENC; do
  [ -n "$NAME" ] || continue
  CMD="$(printf '%s' "$ENC" | base64 --decode 2>/dev/null || printf '%s' "$ENC" | base64 -D)"

  echo "${C_BOLD}-> gate: ${NAME}${C_RESET}"
  START=$(date +%s)
  OUT_FILE="$(mktemp -t rungates.XXXXXX)"
  # Run from the project root. Do not let a failing gate abort the runner.
  set +e
  ( cd "$PROJECT_ROOT" && eval "$CMD" ) >"$OUT_FILE" 2>&1
  RC=$?
  set -e
  END=$(date +%s)
  DUR=$((END - START))

  # Detail for the stamp is computed first: it must not depend on where the
  # combined output ends up.
  LAST_LINE="$(awk 'NF{last=$0} END{print last}' "$OUT_FILE")"

  # FR-HP-20 / FR-HP-21: a green gate contributes its tail, not its whole log -
  # thousands of passing-test lines are transcript weight every later turn of
  # the calling session re-reads. A red gate still echoes everything; that is
  # when the detail is load-bearing. Either way the full combined stdout and
  # stderr is preserved under company/state/gate-output/.
  # OQ-HP-04 assumption: the tail is 3 non-empty lines plus one pointer line,
  # with no configuration knob.
  if [ "$RC" -eq 0 ]; then
    # awk 'NF' drops blank lines and exits 0 even when nothing matches, so this
    # pipeline cannot trip pipefail the way a grep -v pipeline would.
    awk 'NF' "$OUT_FILE" | tail -n 3
  else
    cat "$OUT_FILE"
  fi

  # A gate name is not a filename: fold anything outside [A-Za-z0-9._-] to _ so
  # a gate named with a slash cannot write outside the output directory.
  SAFE_NAME="$(printf '%s' "$NAME" | tr -c 'A-Za-z0-9._-' '_')"
  GATE_LOG=""
  # Preserving output is best-effort: a read-only company/state must not abort
  # the run or change the exit code, so both steps are guarded.
  if mkdir -p "$GATE_OUT_DIR" 2>/dev/null; then
    if mv -f "$OUT_FILE" "$GATE_OUT_DIR/$SAFE_NAME.log" 2>/dev/null; then
      GATE_LOG="company/state/gate-output/$SAFE_NAME.log"
    fi
  fi
  if [ -z "$GATE_LOG" ]; then
    rm -f "$OUT_FILE"
  elif [ "$RC" -eq 0 ]; then
    # Only point at a file that was actually written.
    echo "(full output: $GATE_LOG)"
  fi
  OUT_FILE=""

  if [ "$RC" -eq 0 ]; then
    STATUS="PASS"; OK="true"
  else
    STATUS="FAIL"; OK="false"; ANY_FAIL=1
  fi

  # Record for the ladder and for stamping (base64 the detail for safe transport).
  DENC="$(printf '%s' "$LAST_LINE" | base64 | tr -d '\n')"
  printf '%s\t%s\t%s\n' "$NAME" "$OK" "$DENC" >>"$DETAILS_FILE"
  printf '%s\t%s\t%ss\n' "$NAME" "$STATUS" "$DUR" >>"$LADDER_FILE"
  echo
done <<EOF
$GATE_LINES
EOF

# --- print the gate ladder ------------------------------------------------
echo "${C_BOLD}Gate ladder${C_RESET}"
printf '%-24s %-6s %s\n' "GATE" "RESULT" "TIME"
printf '%-24s %-6s %s\n' "------------------------" "------" "------"
while IFS=$'\t' read -r NAME STATUS DUR; do
  [ -n "$NAME" ] || continue
  if [ "$STATUS" = "PASS" ]; then COLOR="$C_GREEN"; else COLOR="$C_RED"; fi
  printf '%-24s %s%-6s%s %s\n' "$NAME" "$COLOR" "$STATUS" "$C_RESET" "$DUR"
done <"$LADDER_FILE"
echo

# --- stamp results --------------------------------------------------------
RESULTS_JSON="$(python3 - "$DETAILS_FILE" <<'PY'
import base64, json, sys
gates = []
with open(sys.argv[1]) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, ok, denc = parts[0], parts[1], parts[2]
        try:
            detail = base64.b64decode(denc.encode("ascii")).decode("utf-8", "replace")
        except Exception:
            detail = ""
        gates.append({"name": name, "ok": ok == "true", "detail": detail})
sys.stdout.write(json.dumps({"gates": gates}))
PY
)"

if [ -f "$STAMPER" ]; then
  # FR-HP-28: gate_stamp.py resolves its own root from CLAUDE_PROJECT_DIR
  # falling back to cwd. Hand it the root we actually gated, scoped to this
  # command, or the runner gates one tree and stamps another. Not exported:
  # the gate commands above must keep the environment they were given.
  if CLAUDE_PROJECT_DIR="$PROJECT_ROOT" python3 "$STAMPER" --results "$RESULTS_JSON"; then
    :
  else
    warn "gate_stamp.py exited non-zero; gate results were reported above but may not be stamped"
  fi
else
  warn "gate stamper not found at $STAMPER - skipping stamp (results reported above)"
fi

# --- append run history (FR-HP-22, one line per ladder run) ----------------
# company/state/gates.log answers "how many runs, what did each cost, which
# gate was red" without stdout scrollback. Written only by this runner, the
# same single-writer rule the stamp has. The per-gate fields are read back out
# of the ladder file so they are in ladder order and agree with the table.
# OQ-HP-06 assumption: no rotation in 0.2.7.
SUITE_END=$(date +%s)
GATES_LOG="$PROJECT_ROOT/company/state/gates.log"
SUMMARY=""
while IFS=$'\t' read -r NAME STATUS DUR; do
  [ -n "$NAME" ] || continue
  SUMMARY="$SUMMARY $NAME:$STATUS:$DUR"
done <"$LADDER_FILE"
if [ "$ANY_FAIL" -ne 0 ]; then RUN_STATUS="red"; else RUN_STATUS="green"; fi
# Telemetry is never load-bearing: a read-only company/state costs a log line,
# never the exit code.
# The append runs in a subshell so that a failing redirection is reported to
# the subshell's stderr, which the outer 2>/dev/null has already discarded.
mkdir -p "$PROJECT_ROOT/company/state" 2>/dev/null || true
( printf '%s | total=%ss | status=%s |%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$((SUITE_END - SUITE_START))" \
    "$RUN_STATUS" "$SUMMARY" >>"$GATES_LOG" ) 2>/dev/null || true

# --- final exit code ------------------------------------------------------
if [ "$ANY_FAIL" -ne 0 ]; then
  echo "${C_RED}${C_BOLD}gates FAILED${C_RESET}"
  exit 1
fi
echo "${C_GREEN}${C_BOLD}all gates passed${C_RESET}"
exit 0
