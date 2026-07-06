#!/usr/bin/env bash
# run-gates.sh - the claude-company gate runner.
# Reads company/gates.config, runs each gate command from the project root,
# prints a gate ladder, then stamps results via .claude/hooks/gate_stamp.py.
# Every gate is blocking: exits non-zero if any gate fails.
set -euo pipefail

# --- resolve project root -------------------------------------------------
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  PROJECT_ROOT="$CLAUDE_PROJECT_DIR"
elif PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  PROJECT_ROOT="$(pwd)"
fi

CONFIG="$PROJECT_ROOT/company/gates.config"
STAMPER="$PROJECT_ROOT/.claude/hooks/gate_stamp.py"

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
trap 'rm -f "$DETAILS_FILE" "$LADDER_FILE"' EXIT

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

  # Echo the gate output so the user sees it, then keep the last line as detail.
  cat "$OUT_FILE"
  LAST_LINE="$(awk 'NF{last=$0} END{print last}' "$OUT_FILE")"
  rm -f "$OUT_FILE"

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
  if python3 "$STAMPER" --results "$RESULTS_JSON"; then
    :
  else
    warn "gate_stamp.py exited non-zero; gate results were reported above but may not be stamped"
  fi
else
  warn "gate stamper not found at $STAMPER - skipping stamp (results reported above)"
fi

# --- final exit code ------------------------------------------------------
if [ "$ANY_FAIL" -ne 0 ]; then
  echo "${C_RED}${C_BOLD}gates FAILED${C_RESET}"
  exit 1
fi
echo "${C_GREEN}${C_BOLD}all gates passed${C_RESET}"
exit 0
