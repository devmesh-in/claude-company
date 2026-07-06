#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): block AI-slop tells in inserted text.

Ported from budget-manager's no-ai-slop.py. Scans only the text being written
(never the old text). Punctuation tells are near-zero false positive; phrase
tells are deliberately multi-word so they will not trip on identifiers. Files
under company/state/ (logs) and binary-ish extensions are skipped. Exit 2 on a
hit, exit 0 otherwise; fails open on malformed input.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "no_slop"

# --- 1. Punctuation tells (char, human-readable name, suggested fix) ---
PUNCT_TELLS = [
    ("—", "em dash", "use ' - ', ', ', or split the sentence"),
    ("–", "en dash", "use a hyphen '-' (or 'to' for ranges)"),
    ("―", "horizontal bar", "use '-' or rewrite"),
    ("“", "smart double quote (open)", "use a straight quote \""),
    ("”", "smart double quote (close)", "use a straight quote \""),
    ("‘", "smart single quote (open)", "use a straight quote '"),
    ("’", "smart single quote (close)", "use a straight apostrophe '"),
    ("…", "ellipsis char", "use three dots '...'"),
]

# --- 2. Phrase tells (regex, case-insensitive). Multi-word on purpose. ---
PHRASE_TELLS = [
    r"\bdelve(s|d|ing)?\b",
    r"\bit'?s worth noting\b",
    r"\bit'?s important to note\b",
    r"\b(a )?testament to\b",
    r"\bnavigat(e|ing) the (complexit|landscape|world)",
    r"\bin the (realm|world) of\b",
    r"\btapestry\b",
    r"\bat the end of the day\b",
    r"\bneedless to say\b",
    r"\bin today'?s (fast-paced|digital|ever-changing)\b",
    r"\bunlock(ing)? the (power|potential)\b",
    r"\bsupercharg(e|ed|ing)\b",
    r"\bseamless(ly)?\b",
    r"\bbustling\b",
    r"\bgame.?chang(er|ing)\b",
    r"\bparadigm shift\b",
    r"\bnot only\b[^.\n]{0,60}\bbut also\b",
    r"\bwhen it comes to\b",
    r"\belevate your\b",
    r"\bdive (deep|into)\b",
]
COMPILED_PHRASES = [re.compile(p, re.IGNORECASE) for p in PHRASE_TELLS]

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".gz", ".tar", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".mp3",
    ".wav", ".bin", ".so", ".dylib", ".o", ".class", ".lockb",
}


def text_under_edit(tool_name, tool_input):
    if tool_name == "Write":
        return tool_input.get("content", "") or ""
    if tool_name == "Edit":
        return tool_input.get("new_string", "") or ""
    parts = []
    for edit in tool_input.get("edits", []) or []:
        parts.append(edit.get("new_string", "") or "")
    return "\n".join(parts)


def scan(text):
    hits = []
    for ch, name, fix in PUNCT_TELLS:
        if ch in text:
            n = text.count(ch)
            hits.append("  - {} x{} -> {}".format(name, n, fix))
    for pat in COMPILED_PHRASES:
        m = pat.search(text)
        if m:
            hits.append(
                "  - slop phrase: \"{}\" -> rewrite plainly".format(m.group(0))
            )
    return hits


def skip_path(file_path):
    norm = (file_path or "").replace("\\", "/")
    if "company/state/" in norm:
        return True
    ext = os.path.splitext(norm)[1].lower()
    return ext in BINARY_EXT


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return 0
    tool_input = data.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    if skip_path(file_path):
        return 0
    text = text_under_edit(tool_name, tool_input)
    if not text:
        return 0
    hits = scan(text)
    if not hits:
        return 0
    try:
        root = c.project_root(data)
        c.adherence_log(
            root, HOOK, "BLOCK", c.rel_path(root, file_path),
            "slop tells: {}".format(len(hits)),
        )
    except Exception:
        pass
    print(
        "Blocked: AI-slop tells found in the text you are writing to "
        "{}.\n".format(file_path or "<file>") + "\n".join(hits) + "\n"
        "Rewrite the offending text and retry.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
