#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): block edits to frozen surfaces.

Frozen surfaces are declared in company/frozen-surfaces.json. When that file is
missing only the hardcoded `always` defaults apply. Also blocks edits to
git-TRACKED files under any migrations/ or alembic/versions/ directory (a new,
untracked migration stays editable; on git uncertainty we treat the file as
tracked and block). Fails open on any internal error.
"""

import fnmatch
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_frozen"

ALWAYS_DEFAULTS = [
    ".env",
    ".env.*",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "company/state/gates.status",
    "company/state/adherence.log",
    "company/state/costs.log",
    "company/state/.cost-cursor.json",
]

ENV_ALLOW_SUFFIXES = (".example", ".sample", ".template")

CR_NOTE = (
    "Frozen surfaces change only through the change-request protocol "
    "(company/change-requests/), never a local edit. If this change is "
    "genuinely needed, file a CR: copy company/templates/CR-TEMPLATE.md to "
    "company/change-requests/CR-<n>-<slug>.md and surface it in your report. "
    "The CEO applies approved CRs."
)


def load_config(root):
    cfg = c.read_json_file(os.path.join(root, "company", "frozen-surfaces.json"))
    surfaces = []
    always = list(ALWAYS_DEFAULTS)
    if isinstance(cfg, dict):
        for s in cfg.get("surfaces", []) or []:
            if isinstance(s, dict) and s.get("pattern"):
                surfaces.append(s)
        extra = cfg.get("always")
        if isinstance(extra, list):
            for pat in extra:
                if pat not in always:
                    always.append(pat)
    return surfaces, always


def matches(pattern, rel, base):
    return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(base, pattern)


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    root = c.project_root(payload)
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        sys.exit(0)

    try:
        rel = c.rel_path(root, file_path)
        base = os.path.basename(rel) or os.path.basename(file_path)

        # Documented placeholder env files are always editable.
        if base.startswith(".env") and base.endswith(ENV_ALLOW_SUFFIXES):
            sys.exit(0)

        surfaces, always = load_config(root)

        for pat in always:
            if matches(pat, rel, base):
                c.block(
                    root, HOOK, rel, "always-frozen: " + pat,
                    "BLOCKED: '{}' is a frozen surface ({}). {}".format(
                        rel, pat, CR_NOTE
                    ),
                )

        for s in surfaces:
            pat = s.get("pattern")
            if matches(pat, rel, base):
                why = s.get("why", "declared frozen")
                via = s.get("change_via", "CR")
                c.block(
                    root, HOOK, rel, "frozen: " + pat,
                    "BLOCKED: '{}' is a frozen surface. WHY: {}. "
                    "Change via: {}. {}".format(rel, why, via, CR_NOTE),
                )

        # git-tracked migrations are immutable once shipped.
        segs = rel.split("/")
        in_migrations = "migrations" in segs[:-1]
        in_alembic_versions = False
        for i in range(len(segs) - 1):
            if segs[i] == "alembic" and i + 1 < len(segs) and segs[i + 1] == "versions":
                in_alembic_versions = True
                break
        if in_migrations or in_alembic_versions:
            abs_path = file_path
            if not os.path.isabs(abs_path):
                abs_path = os.path.join(root, rel)
            if c.is_git_tracked(abs_path):
                c.block(
                    root, HOOK, rel, "shipped migration",
                    "BLOCKED: '{}' is a shipped (git-tracked) migration. "
                    "Migrations are immutable once committed; create a NEW "
                    "revision instead. {}".format(rel, CR_NOTE),
                )
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
