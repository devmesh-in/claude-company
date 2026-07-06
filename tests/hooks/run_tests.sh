#!/usr/bin/env bash
# Run the claude-company hook test suite.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/test_hooks.py" "$@"
