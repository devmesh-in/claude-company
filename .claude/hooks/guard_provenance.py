#!/usr/bin/env python3
"""Thin re-export shim. FR-ASR-22 / OQ-ASR-02 assumption.

Provenance enforcement (modes A/B/C) is deleted. settings.json does not
invoke this file. The frozen adapter test
(tests/harness/test_adapter.mjs, another session's working tree) still
does `import guard_provenance as g` and calls audit_verdict/response_text.
Those live in dispatch_feed; this module re-exports the two names.

No BLOCK path. Always fails open. Python 3.8 stdlib only.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dispatch_feed import audit_verdict, response_text  # noqa: E402

__all__ = ["audit_verdict", "response_text"]


def main():
    sys.exit(0)


if __name__ == "__main__":
    main()
