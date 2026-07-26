#!/usr/bin/env bash
# Run the claude-company hook test suite.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Discover every test_*.py here, not just test_hooks.py: CI calls this script,
# so anything it misses never runs in CI. Top-level dir is pinned to HERE so the
# suite imports exactly as it does under a bare
# `python3 -m unittest discover -s tests/hooks`.
# -v keeps the per-test names in the CI log: test_hooks.py ran unittest.main
# with verbosity=2, and discover would otherwise collapse 224 tests to dots.
exec python3 -m unittest discover -s "$HERE" -t "$HERE" -v "$@"
