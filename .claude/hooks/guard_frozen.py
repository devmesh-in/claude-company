#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): block edits to frozen surfaces.

Clauses, in order:
  1. always-frozen defaults + declared surfaces (company/frozen-surfaces.json;
     when that file is missing only the hardcoded `always` defaults apply).
  2. Accepted ADRs (company/adr/*.md) are immutable. An ADR already on disk with
     a `Status: accepted` line may only be superseded, never edited. A brand-new
     ADR is born proposed: creating one whose INCOMING content declares
     `Status: accepted` is blocked (the CEO flips the status on acceptance).
  3. git-TRACKED files under any migrations/ or alembic/versions/ directory (a
     new, untracked migration stays editable; on git uncertainty we treat the
     file as tracked and block).

Fails open on any internal error. The immutability checks (accepted ADRs,
shipped migrations) are the one place we fail SAFE - on uncertainty they block.
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
    "company/state/provenance-ledger.json",
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


def incoming_content(tool_name, tool_input):
    """Best-effort reconstruction of the text a create-tool would write.

    Write carries the whole file in `content` - the real vector for minting a
    pre-accepted ADR. MultiEdit/Edit carry new_string fragments; on a
    non-existent file an Edit fails anyway, so we inspect them only defensively.
    OQ-AH-01: MultiEdit inspects the combined new_strings.
    """
    if tool_name == "Write":
        return tool_input.get("content") or ""
    if tool_name == "MultiEdit":
        parts = []
        for e in tool_input.get("edits") or []:
            if isinstance(e, dict):
                parts.append(e.get("new_string") or "")
        return "\n".join(parts)
    if tool_name == "Edit":
        return tool_input.get("new_string") or ""
    return ""


def declares_accepted(text):
    # OQ-AH-02: same literal-line semantics as the on-disk accepted check - a
    # line that starts with `Status: accepted` (trailing whitespace tolerated,
    # since startswith ignores it). No regex variants.
    for line in (text or "").splitlines():
        if line.startswith("Status: accepted"):
            return True
    return False


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

        # Accepted ADRs are immutable (mirrors the shipped-migrations clause).
        # A decision that has been accepted may only be superseded by a NEW
        # ADR, never rewritten in place. Fail-safe direction on a read error:
        # block (same posture as migrations, which treat git uncertainty as
        # tracked). Only files directly under company/adr/ are governed - the
        # ADR-TEMPLATE.md under company/templates/ never matches this prefix.
        if rel.startswith("company/adr/") and rel.endswith(".md"):
            abs_path = file_path
            if not os.path.isabs(abs_path):
                abs_path = os.path.join(root, rel)
            if os.path.exists(abs_path):
                # On disk: accepted = immutable; proposed = editable (this is
                # also the CEO's acceptance flip, proposed -> accepted, which
                # reads the proposed on-disk status and is therefore allowed).
                accepted = False
                try:
                    with open(abs_path, "r", encoding="utf-8",
                              errors="replace") as f:
                        for line in f:
                            if line.startswith("Status: accepted"):
                                accepted = True
                                break
                except Exception:
                    accepted = True  # fail safe: unreadable existing ADR
                if accepted:
                    c.block(
                        root, HOOK, rel, "accepted ADR",
                        "BLOCKED: '{}' is an accepted ADR. Accepted ADRs are "
                        "immutable - write a new ADR that supersedes it "
                        "(Status: superseded-by-ADR-NNN is applied by the CEO "
                        "via CR), never edit the decision itself. {}".format(
                            rel, CR_NOTE
                        ),
                    )
            else:
                # Not yet on disk (#31): a brand-new ADR must be born proposed.
                # Inspect the INCOMING content so a pre-accepted ADR cannot be
                # minted straight through Write (the real vector). Proposed or
                # status-less new ADRs stay writable.
                if declares_accepted(incoming_content(
                        payload.get("tool_name"), tool_input)):
                    c.block(
                        root, HOOK, rel, "new ADR born accepted",
                        "BLOCKED: '{}' - a new ADR is born proposed, never "
                        "accepted. Write it with Status: proposed; the CEO "
                        "flips the status on acceptance (see "
                        "company/adr/README.md).".format(rel),
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
