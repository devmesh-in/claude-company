#!/usr/bin/env bash
# run-gates.sh - the claude-company gate runner.
# Reads company/gates.config, runs each gate command from the project root,
# prints a gate ladder, then stamps results via .claude/hooks/gate_stamp.py.
# Every gate is blocking: exits non-zero if any gate fails.
set -euo pipefail

# --- resolve project root -------------------------------------------------
# FR-HP-28: the root is resolved from the RUNNER'S OWN LOCATION. This script
# always ships at <root>/company/run-gates.sh, so the root is the parent of the
# directory holding it - and gates.config, .claude/hooks and company/state are
# all its siblings. The runner is part of the project it gates.
#
# NOT resolved from CLAUDE_PROJECT_DIR first: the harness pins that to the MAIN
# checkout even for an agent whose cwd is a worktree, so a lead running the
# ladder in its worktree would gate and stamp a tree it never built and receive
# a green stamp for somebody else's code.
#
# NOT resolved from the cwd's git work tree either: the cwd is incidental. An
# explicit `bash /path/to/project/company/run-gates.sh` issued from anywhere
# must gate THAT project, and a cwd that merely happens to sit inside some
# other git repository must not redirect the run. Every in-repo invocation is
# relative (`bash company/run-gates.sh` from the project root), so a worktree
# run still executes the worktree's copy and still resolves to the worktree.
#
# OQ-HP-14 assumption: a ladder run inside a worktree deliberately does NOT
# satisfy the main checkout's stamp. That is intended; the alternative is the
# false green this rule exists to kill.
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
# Follow symlinks by hand: `readlink -f` is GNU-only and macOS does not have it.
LINK_HOPS=0
while [ -L "$SCRIPT_PATH" ] && [ "$LINK_HOPS" -lt 16 ]; do
  LINK_TARGET="$(readlink "$SCRIPT_PATH")"
  case "$LINK_TARGET" in
    /*) SCRIPT_PATH="$LINK_TARGET" ;;
    *)  SCRIPT_PATH="$(dirname "$SCRIPT_PATH")/$LINK_TARGET" ;;
  esac
  LINK_HOPS=$((LINK_HOPS + 1))
done
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" 2>/dev/null && pwd -P || true)"

# The "company" check is what keeps the fallbacks reachable: piped stdin and
# `bash -c` leave $0 as "bash", and a confidently wrong root is worse than an
# honest fallback.
if [ -n "$SCRIPT_DIR" ] && [ "$(basename "$SCRIPT_DIR")" = "company" ]; then
  PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
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

# FR-ASR-10 / BR-ASR-06 / OQ-ASR-05 assumption: reuse a green matching
# stamp. Missing stamper, non-zero --check, hash trouble -> RUN, never skip.
if [ -f "$STAMPER" ]; then
  set +e
  CLAUDE_PROJECT_DIR="$PROJECT_ROOT" python3 "$STAMPER" --check >/dev/null 2>&1
  CHECK_RC=$?
  set -e
  if [ "$CHECK_RC" -eq 0 ]; then
    # FR-ASR-10: a matching no-git hash is not evidence of freshness - RUN.
    WH="$(CLAUDE_PROJECT_DIR="$PROJECT_ROOT" python3 -c '
import os, sys
root = os.environ["CLAUDE_PROJECT_DIR"]
sys.path.insert(0, os.path.join(root, ".claude", "hooks"))
import _common as c
print(c.work_hash(root))
' 2>/dev/null || true)"
    case "$WH" in
      ""|"no-git") CHECK_RC=2 ;;
    esac
  fi
  if [ "$CHECK_RC" -eq 0 ]; then
    echo "gates already green for this tree; reusing stamp"
    SUITE_END=$(date +%s)
    GATES_LOG="$PROJECT_ROOT/company/state/gates.log"
    mkdir -p "$PROJECT_ROOT/company/state" 2>/dev/null || true
    ( printf '%s | total=%ss | status=%s | reused=1\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$((SUITE_END - SUITE_START))" \
        "green" >>"$GATES_LOG" ) 2>/dev/null || true
    echo "${C_GREEN}${C_BOLD}all gates passed${C_RESET}"
    exit 0
  fi
fi

# --- run gates in parallel (FR-ASR-09). OQ-ASR-03 assumption: same tree,
# isolated stdout/stderr/logs, no per-gate copies. bash 3.2: no wait -n.
echo "${C_BOLD}Running gates from ${PROJECT_ROOT}${C_RESET}"
echo

DETAILS_FILE="$(mktemp -t rungates.XXXXXX)"
LADDER_FILE="$(mktemp -t rungates.XXXXXX)"
JOB_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rungates.XXXXXX")"
trap 'rm -rf "$JOB_DIR" "$DETAILS_FILE" "$LADDER_FILE"' EXIT

run_one_gate() {
  _idx="$1"
  _name="$2"
  _cmd="$3"
  _safe="$4"
  START=$(date +%s)
  OUT_FILE="$JOB_DIR/${_idx}.out"
  set +e
  ( cd "$PROJECT_ROOT" && eval "$_cmd" ) >"$OUT_FILE" 2>&1
  RC=$?
  set -e
  END=$(date +%s)
  DUR=$((END - START))
  LAST_LINE="$(awk 'NF{last=$0} END{print last}' "$OUT_FILE")"
  printf '%s\n' "$RC" >"$JOB_DIR/${_idx}.rc"
  printf '%s\n' "$DUR" >"$JOB_DIR/${_idx}.dur"
  printf '%s\n' "$_name" >"$JOB_DIR/${_idx}.name"
  printf '%s\n' "$_safe" >"$JOB_DIR/${_idx}.safe"
  printf '%s\n' "$LAST_LINE" >"$JOB_DIR/${_idx}.last"
}

INDEX=0
while IFS=$'\t' read -r NAME ENC; do
  [ -n "$NAME" ] || continue
  INDEX=$((INDEX + 1))
  CMD="$(printf '%s' "$ENC" | base64 --decode 2>/dev/null || printf '%s' "$ENC" | base64 -D)"
  SAFE_NAME="$(printf '%s' "$NAME" | tr -c 'A-Za-z0-9._-' '_')"
  run_one_gate "$INDEX" "$NAME" "$CMD" "$SAFE_NAME" &
done <<EOF
$GATE_LINES
EOF

set +e
wait
set -e

ANY_FAIL=0
i=1
while [ "$i" -le "$INDEX" ]; do
  NAME="$(cat "$JOB_DIR/$i.name")"
  SAFE_NAME="$(cat "$JOB_DIR/$i.safe")"
  RC="$(cat "$JOB_DIR/$i.rc")"
  DUR="$(cat "$JOB_DIR/$i.dur")"
  LAST_LINE="$(cat "$JOB_DIR/$i.last")"
  OUT_FILE="$JOB_DIR/$i.out"

  echo "${C_BOLD}-> gate: ${NAME}${C_RESET}"
  if [ "$RC" -eq 0 ]; then
    awk 'NF' "$OUT_FILE" | tail -n 3
  else
    cat "$OUT_FILE"
  fi

  GATE_LOG=""
  if mkdir -p "$GATE_OUT_DIR" 2>/dev/null; then
    if mv -f "$OUT_FILE" "$GATE_OUT_DIR/$SAFE_NAME.log" 2>/dev/null; then
      GATE_LOG="company/state/gate-output/$SAFE_NAME.log"
    fi
  fi
  if [ -z "$GATE_LOG" ]; then
    rm -f "$OUT_FILE"
  elif [ "$RC" -eq 0 ]; then
    echo "(full output: $GATE_LOG)"
  fi

  if [ "$RC" -eq 0 ]; then
    STATUS="PASS"; OK="true"
  else
    STATUS="FAIL"; OK="false"; ANY_FAIL=1
  fi

  DENC="$(printf '%s' "$LAST_LINE" | base64 | tr -d '\n')"
  printf '%s\t%s\t%s\n' "$NAME" "$OK" "$DENC" >>"$DETAILS_FILE"
  printf '%s\t%s\t%ss\n' "$NAME" "$STATUS" "$DUR" >>"$LADDER_FILE"
  echo
  i=$((i + 1))
done

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
