#!/usr/bin/env bash
# tests/harness/run_tests.sh - the harness suite, sixth gate of the ladder.
#
# CI and the local ladder both call THIS, never the individual files. W-030
# recorded what happens otherwise: CI once exec'd one test file directly and
# silently dropped from 224 hook tests to 103, with no other symptom.
#
# Five layers, all blocking, none substituting for another:
#
#   test_core.mjs     the adapter's decisions, no opencode needed
#   test_adapter.mjs  the handlers themselves, driven against recording
#                     guards - this is where the payload contract lives
#   test_render.mjs   the .claude -> .opencode renderer and the drift gate
#   test_install.sh   harness selection in install and update
#   test_opencode.sh  the REAL binary: does opencode still call us the way we
#                     think it does
set -uo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
RC=0

run() { # run <label> <cmd...>
  printf '\n\033[1m-> %s\033[0m\n' "$1"
  shift
  if "$@"; then :; else RC=1; fi
}

run "adapter logic"     node "$TEST_DIR/test_core.mjs"
run "adapter handlers"  node "$TEST_DIR/test_adapter.mjs"
run "renderer + drift"  node "$TEST_DIR/test_render.mjs"
run "install + update"  bash "$TEST_DIR/test_install.sh"
run "real opencode"     bash "$TEST_DIR/test_opencode.sh"

printf '\n================ HARNESS SUITE ================\n'
if [ "$RC" -eq 0 ]; then printf 'ALL GREEN\n'; else printf 'RED\n'; fi
exit "$RC"
