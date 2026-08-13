#!/usr/bin/env python3
"""Mechanical model-routing enforcement for claude-company.

The intended model per agent role lives in company/models.json - the single
deliberate place routing is decided. This guard blocks silent drift away from
it in three modes:

  a) PreToolUse (Task|Agent): a subagent spawn whose `model` override
     contradicts the manifest for that role -> BLOCK.
  b) PreToolUse (Edit|Write|MultiEdit) on .claude/agents/<role>.md: a
     frontmatter `model:` edit that contradicts the manifest -> BLOCK.
  c) --check CLI: compare every agent frontmatter `model:` against the
     manifest, and assert the shipped hook wiring in .claude/settings.json
     (EXPECTED_WIRING); exit 0 on full agreement, 1 on any mismatch or missing
     binding. For CI / gates.

Hotfix mode (ANY active-task entry with type=hotfix) bypasses the PreToolUse
modes with a logged BYPASS. Everything fails open: a missing/unreadable
manifest, an unknown role, or any internal error allows the action.
"""

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

HOOK = "guard_models"

MODEL_LINE = re.compile(r"^model:\s*(\S+)", re.MULTILINE)

SPAWN_TYPE_FIELDS = ("subagent_type", "agent_type", "type")

# FR-HP-25: the expected hook wiring, transcribed from the shipped
# .claude/settings.json. Rows are (event, tools, hook filename). `tools` is
# None for the events that carry no matcher; otherwise it is a tuple and EVERY
# tool named in it must be covered, so un-wiring a single alternative of a
# matcher (say dropping Write from "Edit|Write|MultiEdit") is still caught.
#
# WHY THIS GATE EXISTS: a fork of this codebase un-wired a hook while its own
# doctrine still cited that hook as a live integrity point. Nothing caught it,
# because no CODE had changed - so no test could fail. This table is the
# mechanical answer to that class of drift: enforcement cannot ship as code
# without teeth.
#
# OQ-HP-02 assumption: there is NO exemption knob for this assertion. A
# missing binding is a red gate and a change request, never a config opt-out.
EDIT_TOOLS = ("Edit", "Write", "MultiEdit")
SPAWN_TOOLS = ("Task", "Agent")

EXPECTED_WIRING = [
    ("PreToolUse", EDIT_TOOLS, "guard_frozen.py"),
    ("PreToolUse", EDIT_TOOLS, "guard_spec.py"),
    ("PreToolUse", EDIT_TOOLS, "guard_tests.py"),
    ("PreToolUse", EDIT_TOOLS, "no_slop.py"),
    ("PreToolUse", EDIT_TOOLS, "guard_models.py"),
    ("PreToolUse", EDIT_TOOLS, "guard_provenance.py"),
    ("PreToolUse", SPAWN_TOOLS, "guard_models.py"),
    ("PreToolUse", SPAWN_TOOLS, "guard_provenance.py"),
    ("PreToolUse", ("Bash",), "guard_commit.py"),
    ("PreToolUse", ("Bash",), "guard_secrets.py"),
    ("PreToolUse", ("Bash",), "guard_tests.py"),
    ("PreToolUse", ("Bash",), "guard_provenance.py"),
    ("PostToolUse", EDIT_TOOLS, "guard_provenance.py"),
    ("PostToolUse", SPAWN_TOOLS, "guard_provenance.py"),
    ("UserPromptSubmit", None, "context_pin.py"),
    ("Stop", None, "guard_provenance.py"),
    ("Stop", None, "cost_capture.py"),
    ("SubagentStop", None, "cost_capture.py"),
    ("SessionStart", None, "session_start.py"),
]

WIRING_FIXIT = (
    "re-run `claude-company update` to restore the shipped hook bindings in "
    ".claude/settings.json"
)


def load_manifest(root):
    """Return {role: model} from company/models.json, or None (fail-open)."""
    cfg = c.read_json_file(os.path.join(root, "company", "models.json"))
    if not isinstance(cfg, dict):
        return None
    roles = cfg.get("roles")
    if not isinstance(roles, dict):
        return None
    return roles


def load_builtins(root):
    """Return {type: model} from company/models.json `builtins`, or None.

    Mirrors load_manifest and fails open (None) on a missing/malformed/
    unreadable file or section. Keys starting with '$' (e.g. "$comment") are
    dropped so they are never treated as a spawnable type, and only string
    model values are kept.
    """
    cfg = c.read_json_file(os.path.join(root, "company", "models.json"))
    if not isinstance(cfg, dict):
        return None
    builtins = cfg.get("builtins")
    if not isinstance(builtins, dict):
        return None
    return {
        k: v for k, v in builtins.items()
        if not k.startswith("$") and isinstance(v, str)
    }


def hotfix_bypass(root, target):
    """FR-MST-07: ANY entry of type hotfix bypasses the PreToolUse modes.

    Logs the BYPASS naming the responsible hotfix entry (the slug is appended
    only once a second entry exists, per BR-MST-02) and returns True. Returns
    False without logging when no entry is a hotfix.
    """
    tasks = c.active_tasks(root)
    hf = c.hotfix_entry(tasks)
    if hf is None:
        return False
    c.log_bypass(root, HOOK, target, c.qualify_reason("hotfix mode", tasks, hf))
    return True


def role_from_agent_path(rel):
    """Return the role for a .claude/agents/<role>.md path, else None."""
    norm = (rel or "").replace("\\", "/")
    if "/.claude/agents/" in ("/" + norm) and norm.endswith(".md"):
        return os.path.splitext(os.path.basename(norm))[0]
    return None


def new_text(tool_name, tool_input):
    if tool_name == "Write":
        return tool_input.get("content", "") or ""
    if tool_name == "Edit":
        return tool_input.get("new_string", "") or ""
    parts = []
    for edit in tool_input.get("edits", []) or []:
        parts.append(edit.get("new_string", "") or "")
    return "\n".join(parts)


def handle_spawn(root, tool_input, roles, builtins):
    role = None
    for field in SPAWN_TYPE_FIELDS:
        val = tool_input.get(field)
        if val:
            role = val
            break
    if role is None:
        return  # no spawn type -> allow
    if role in roles:
        # OQ-MRA-02 assumption: roles governs on any collision - a type present
        # in both `roles` and `builtins` is decided here, by the roles branch.
        handle_role_spawn(root, tool_input, roles, role)
        return
    # Not a manifest role. A built-in agent type has no .claude/agents
    # frontmatter to inherit from, so a bare spawn would silently take the
    # SESSION model - require an explicit matching override.
    if builtins is None:
        return  # no builtins section -> builtin enforcement inert (fail open)
    if role not in builtins:
        return  # unknown type -> allow
    pin = builtins[role]
    override = tool_input.get("model")
    if override == pin:
        return  # explicit matching override -> allow
    if hotfix_bypass(root, "spawn " + role):
        return
    if not override:
        c.block(
            root, HOOK, "spawn " + role,
            "builtin spawn no override (pin {})".format(pin),
            "BLOCKED: spawning built-in '{}' with no model override would "
            "inherit the session model - built-in agent types have no "
            "company/models.json frontmatter pin to fall back on.\n"
            "Fix: pass model: '{}'".format(role, pin),
        )
    c.block(
        root, HOOK, "spawn " + role,
        "builtin spawn override {} != pin {}".format(override, pin),
        "BLOCKED: spawning built-in '{}' with model '{}' contradicts "
        "company/models.json (built-in pin: '{}').\n"
        "Fix: pass model: '{}'".format(role, override, pin, pin),
    )


def handle_role_spawn(root, tool_input, roles, role):
    override = tool_input.get("model")
    if not override:
        return  # no override -> role inherits the manifest model, allow
    want = roles[role]
    if override == want:
        return  # matches the routing decision, allow
    if hotfix_bypass(root, "spawn " + role):
        return
    c.block(
        root, HOOK, "spawn " + role,
        "spawn override {} != manifest {}".format(override, want),
        "BLOCKED: spawning '{}' with model '{}' contradicts company/models.json "
        "(routing decision: '{}').\n"
        "Fix: drop the model override, or change company/models.json "
        "deliberately (that is the routing decision record).".format(
            role, override, want
        ),
    )


def handle_frontmatter_edit(root, tool_name, tool_input, roles):
    file_path = tool_input.get("file_path") or ""
    rel = c.rel_path(root, file_path)
    role = role_from_agent_path(rel)
    if role is None or role not in roles:
        return  # not a manifest role -> allow
    text = new_text(tool_name, tool_input)
    m = MODEL_LINE.search(text)
    if not m:
        return  # edit does not touch a model line -> allow
    new_model = m.group(1)
    want = roles[role]
    if new_model == want:
        return
    if hotfix_bypass(root, rel):
        return
    c.block(
        root, HOOK, rel,
        "frontmatter model {} != manifest {}".format(new_model, want),
        "BLOCKED: setting '{}' model to '{}' contradicts company/models.json "
        "(routing decision: '{}').\n"
        "Fix: update company/models.json first (deliberate routing change), "
        "then this edit passes.".format(role, new_model, want),
    )


def check_spawn_wiring(root):
    """Assert .claude/settings.json wires guard_models on the Task spawn tool.

    Passes when some PreToolUse group has a matcher covering the Task tool -
    "Task" is one of its "|"-separated alternatives (the shipped matcher is
    "Task|Agent") - and one of that group's hooks runs a command referencing
    guard_models.py. Only the project settings.json counts; settings.local.json
    is ignored. Returns (ok, fixit_message).
    """
    fixit = (
        "spawn enforcement is not wired: .claude/settings.json has no "
        "PreToolUse matcher covering the Task spawn tool that runs "
        "guard_models.py - re-run `claude-company install` or `update` to "
        "re-add it."
    )
    settings = c.read_json_file(
        os.path.join(root, ".claude", "settings.json")
    )
    if not isinstance(settings, dict):
        return False, fixit
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False, fixit
    groups = hooks.get("PreToolUse")
    if not isinstance(groups, list):
        return False, fixit
    for group in groups:
        if not isinstance(group, dict):
            continue
        matcher = group.get("matcher") or ""
        if "Task" not in matcher.split("|"):
            continue
        for h in group.get("hooks") or []:
            if isinstance(h, dict) and "guard_models.py" in (
                h.get("command") or ""
            ):
                return True, ""
    return False, fixit


def group_covers(group, tool, filename):
    """True iff `group` runs `filename` for `tool` (None tool = no matcher).

    Same matcher semantics as check_spawn_wiring: a tool is covered when it is
    one of the "|"-separated alternatives of the group's matcher.
    """
    if not isinstance(group, dict):
        return False
    if tool is not None and tool not in (group.get("matcher") or "").split("|"):
        return False
    for h in group.get("hooks") or []:
        if isinstance(h, dict) and filename in (h.get("command") or ""):
            return True
    return False


def check_full_wiring(root):
    """Assert every EXPECTED_WIRING row is bound in .claude/settings.json.

    A SUBSET assertion, never an equality one: extra hooks and extra groups are
    allowed. A row is checked only when .claude/hooks/<filename> exists in this
    project, so an older install that simply does not have a newer hook is not
    failed for it. Only the project settings.json counts - settings.local.json
    is ignored. Returns (ok, [one line per missing binding]).

    A project whose settings.json is missing or unreadable IS un-wired: every
    row whose hook is on disk is then reported missing. That is deliberate -
    --check is a CLI gate, not a hook, so it fails loud rather than open.
    """
    settings = c.read_json_file(
        os.path.join(root, ".claude", "settings.json")
    )
    hooks_cfg = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks_cfg, dict):
        hooks_cfg = {}
    hooks_dir = os.path.join(root, ".claude", "hooks")
    missing = []
    for event, tools, filename in EXPECTED_WIRING:
        if not os.path.exists(os.path.join(hooks_dir, filename)):
            continue  # hook not installed here - nothing to wire
        groups = hooks_cfg.get(event)
        if not isinstance(groups, list):
            groups = []
        for tool in (tools if tools is not None else (None,)):
            if any(group_covers(g, tool, filename) for g in groups):
                continue
            missing.append(
                "{} ({}) does not run {}".format(
                    event, tool if tool else "no matcher", filename
                )
            )
    return not missing, missing


def run_check(root):
    """Compare every agent frontmatter against the manifest. Exit 0/1.

    FR-MRA-06: this frontmatter/agent-file comparison is based ONLY on `roles`.
    Built-in types live in the separate `builtins` section and never demand a
    .claude/agents/<type>.md file, so their absence is never a mismatch here.
    """
    roles = load_manifest(root)
    if roles is None:
        print("company/models.json missing or unreadable")
        return 1
    agents_dir = os.path.join(root, ".claude", "agents")
    rows = []  # (role, frontmatter, manifest, ok)
    mismatches = []
    seen = set()
    for path in sorted(glob.glob(os.path.join(agents_dir, "*.md"))):
        role = os.path.splitext(os.path.basename(path))[0]
        seen.add(role)
        try:
            with open(path) as f:
                declared = MODEL_LINE.search(f.read())
        except Exception:
            declared = None
        fm = declared.group(1) if declared else "(none)"
        want = roles.get(role, "(not in manifest)")
        ok = role in roles and declared is not None and fm == roles[role]
        rows.append((role, fm, want, ok))
        if not ok:
            if role not in roles:
                mismatches.append(
                    "{}: has frontmatter model but no manifest entry".format(role)
                )
            elif declared is None:
                mismatches.append(
                    "{}: no frontmatter model declared "
                    "(manifest wants {})".format(role, roles[role])
                )
            else:
                mismatches.append(
                    "{}: frontmatter {} != manifest {}".format(
                        role, fm, roles[role]
                    )
                )
    for role in sorted(roles):
        if role not in seen:
            rows.append((role, "(no agent file)", roles[role], False))
            mismatches.append(
                "{}: in manifest but no .claude/agents/{}.md".format(role, role)
            )

    width = max([len(r[0]) for r in rows] + [4])
    print("{}  {:<8}  {}".format("role".ljust(width), "frontmat", "manifest"))
    for role, fm, want, ok in rows:
        mark = "ok" if ok else "XX"
        print("{}  {:<8}  {}  {}".format(role.ljust(width), fm, want, mark))
    if mismatches:
        print("\nmismatches:")
        for m in mismatches:
            print("  - " + m)

    # LOUD wiring assertion (FR-MRA-07), gated on builtins presence.
    # OQ-MRA-04 assumption: guard_models asserts only its OWN enforcement
    # wiring. Old manifests without a `builtins` section (load_builtins ->
    # None) skip this entirely and behave exactly as before.
    wiring_ok = True
    if load_builtins(root) is not None:
        wiring_ok, fixit = check_spawn_wiring(root)
        if not wiring_ok:
            print("\nspawn wiring:")
            print("  - " + fixit)

    # FR-HP-25: the full hook-wiring assertion. Additive to the spawn-wiring
    # one above and NOT gated on the builtins section - an install that has a
    # hook on disk but does not run it is un-wired regardless of its manifest.
    full_ok, missing_wiring = check_full_wiring(root)
    if not full_ok:
        print("\nhook wiring:")
        for line in missing_wiring:
            print("  - " + line)
        print("  fix: " + WIRING_FIXIT)

    if mismatches or not wiring_ok or not full_ok:
        return 1
    print("\nall agent models agree with company/models.json")
    return 0


def main():
    if "--check" in sys.argv[1:]:
        try:
            sys.exit(run_check(c.project_root(None)))
        except SystemExit:
            raise
        except Exception:
            # --check is a gate; a crash should not read as agreement.
            print("guard_models --check errored", file=sys.stderr)
            sys.exit(1)

    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    tool_name = payload.get("tool_name")
    root = c.project_root(payload)
    tool_input = payload.get("tool_input") or {}

    try:
        roles = load_manifest(root)
        if roles is None:
            sys.exit(0)  # no manifest -> fail open
        if tool_name in ("Task", "Agent"):
            handle_spawn(root, tool_input, roles, load_builtins(root))
        elif tool_name in ("Edit", "Write", "MultiEdit"):
            handle_frontmatter_edit(root, tool_name, tool_input, roles)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
