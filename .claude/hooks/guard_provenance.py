#!/usr/bin/env python3
"""Delegation provenance enforcement for claude-company.

Nothing self-authored integrates on the authority of the context that produced
it: work built in the main checkout by the CEO/lead must earn one independent,
read-only auditor pass before it commits or the task closes. Work delegated
into the hierarchy (a worktree task branch) is verified inside that hierarchy
and needs no extra audit. This hook records provenance and enforces that rule
across six modes keyed on (hook_event_name, tool_name):

  A) PostToolUse Edit|Write|MultiEdit - telemetry + a once-per-state drift
     nudge when a feature/program runs execution: "self" with an idle team.
     NEVER blocks.
  B-pre)  PreToolUse Task|Agent  - record a builder dispatch. NEVER blocks.
  B-post) PostToolUse Task|Agent - record a verifier (auditor) completion and
     its verdict against the current work_hash. NEVER blocks.
  C) PreToolUse Bash - the commit gate: a git commit carrying dirty
     self-authored source in the main checkout with no fresh audit BLOCKS.
  D) Stop - the close gate: finishing a task with dirty self-authored source
     and no fresh audit emits a Stop block decision.
  E) PreToolUse Edit|Write|MultiEdit - the execution gate: a source edit on a
     feature/program task whose execution decision is missing (or delegated
     with no dispatch) BLOCKS.

The manifest (company/provenance.json) is the rollout switch: missing or
unreadable, every mode silently allows. Hotfix tasks bypass with a logged
BYPASS. Everything fails OPEN: any internal error lets the action through.
Python 3.8 stdlib only.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402
import guard_commit  # noqa: E402
import guard_models  # noqa: E402
import guard_spec  # noqa: E402

HOOK = "guard_provenance"

LEDGER_REL = "company/state/provenance-ledger.json"
MANIFEST_REL = "company/provenance.json"

# Fired once per state from Mode A; <slug> is the only interpolation.
NUDGE_TEXT = (
    "[company] Reminder - task '<slug>' runs with execution: \"self\" and "
    "zero dispatches: the team is idle while you build. That is allowed and "
    "recorded, and the standing price applies - every self-authored commit "
    "needs a fresh read-only auditor pass before it integrates (one Task "
    "call, subagent_type: auditor). If this work is growing beyond glue, a "
    "tech-lead dispatch is cheaper: verification comes free through the "
    "hierarchy. This note fires once per state; it will not repeat."
)

MODE_C_MSG = (
    "BLOCKED: git commit contains self-authored work with no independent "
    "verification.\n"
    "Task '<slug>' has source changes produced in the main checkout, and no "
    "audit\n"
    "covers the current tree (<reason>).\n"
    "Self-authored paths: <paths>\n"
    "Nothing integrates on the authority of the context that produced it\n"
    "(company/METHOD.md, mechanism 5). Fix, in order:\n"
    "1) Run `bash company/run-gates.sh` until green.\n"
    "2) Dispatch the read-only auditor over your diff (Task tool,\n"
    "   subagent_type: auditor). Its completion is recorded automatically.\n"
    "3) Retry the commit WITHOUT editing source in between - any edit stales "
    "the\n"
    "   audit, which is correct.\n"
    "Cheaper alternative for anything beyond glue: move the work to a "
    "worktree\n"
    "task branch and give it to a developer - delegated work is verified "
    "inside\n"
    "the hierarchy and needs no extra audit.\n"
    "Production emergency: set \"type\": \"hotfix\" in "
    "company/state/active-task.json\n"
    "(logged, never silent)."
)

MODE_E_MSG1 = (
    "BLOCKED: source edit on a feature/program task with no execution "
    "decision.\n"
    "Decide HOW task '<slug>' executes and record it in "
    "company/state/active-task.json\n"
    "(add both fields, then retry the edit):\n"
    "  \"execution\": \"delegated\", \"execution_why\": \"<one line>\"\n"
    "      - the default: dispatch a tech-lead; developers build in "
    "worktrees and\n"
    "        verification comes free through the hierarchy.\n"
    "  \"execution\": \"self\", \"execution_why\": \"<one line>\"\n"
    "      - you build it; every self-authored commit then requires a fresh\n"
    "        read-only auditor pass before it integrates (enforced at commit "
    "and\n"
    "        at task close).\n"
    "Team on payroll: <roster>.\n"
    "Worktree edits are never gated by this. Production emergency: set\n"
    "\"type\": \"hotfix\" in active-task.json (logged, never silent)."
)

MODE_E_MSG2 = (
    "BLOCKED: active-task.json records execution: \"delegated\" for task "
    "'<slug>',\n"
    "but no dispatch has happened and this is a source edit in the main "
    "checkout.\n"
    "That contradicts your own written decision. Fix either side:\n"
    "1) Dispatch first (Task tool, subagent_type: tech-lead) - after a "
    "dispatch,\n"
    "   main-checkout glue edits flow freely.\n"
    "2) Or change the record: set \"execution\": \"self\" with a fresh\n"
    "   \"execution_why\" - self-built work then pays the mandatory audit at "
    "commit.\n"
    "Production emergency: set \"type\": \"hotfix\" (logged, never silent)."
)

# FR-DE-15 tracking gate. Interpolate only <slug> and <type>; the '...' and
# '<n>' inside the body are literal text shown to the reader, not fields.
A3_MESSAGE = (
    "BLOCKED: task '<slug>' is a <type> task in PR mode with no tracking "
    "issues\n"
    "recorded. All work ships through GitHub here (owner rule) - work that is "
    "not\n"
    "tracked does not start. Self-serve fix:\n"
    "1) Create one issue per deliverable: gh issue create --title ... --body "
    "...\n"
    "2) Record the numbers in company/state/active-task.json:\n"
    "   \"issues\": [<n>, ...]\n"
    "3) Retry. The integration PR body will close them (Closes #<n> ...).\n"
    "No remote configured = this gate is off (local mode). Production "
    "emergency:\n"
    "set \"type\": \"hotfix\" (logged, never silent)."
)


# --- paths and manifest ---------------------------------------------------

def ledger_path(root):
    return os.path.join(root, "company", "state", "provenance-ledger.json")


def manifest_path(root):
    return os.path.join(root, "company", "provenance.json")


def load_manifest(root):
    """Parsed company/provenance.json, or None (fail-open rollout switch)."""
    m = c.read_json_file(manifest_path(root))
    if not isinstance(m, dict):
        return None
    return m


def roster(root):
    """Sorted union of manifest verifier+builder roles and models.json roles.

    Never raises; returns [] on any trouble.
    """
    try:
        roles = set()
        manifest = load_manifest(root)
        if isinstance(manifest, dict):
            for key in ("verifier_roles", "builder_roles"):
                vals = manifest.get(key)
                if isinstance(vals, list):
                    for v in vals:
                        if v:
                            roles.add(v)
        models = c.read_json_file(
            os.path.join(root, "company", "models.json")
        )
        if isinstance(models, dict):
            mroles = models.get("roles")
            if isinstance(mroles, dict):
                for k in mroles:
                    if k:
                        roles.add(k)
        return sorted(roles)
    except Exception:
        return []


# --- location and git -----------------------------------------------------

def in_worktree_or_out_of_tree(path, root):
    """True if path is inside a worktree checkout OR outside the project root.

    Relative paths resolve against root. Empty path -> False.
    """
    if not path:
        return False
    try:
        p = path
        if not os.path.isabs(p):
            p = os.path.join(root, p)
        norm = os.path.normpath(p).replace(os.sep, "/")
        if "/.claude/worktrees/" in norm:
            return True
        root_norm = os.path.normpath(os.path.abspath(root)).replace(
            os.sep, "/"
        ).rstrip("/")
        if norm == root_norm:
            return False
        if norm.startswith(root_norm + "/"):
            return False
        return True
    except Exception:
        return False


def dirty_source_paths(root):
    """Project-relative source paths that are dirty in git (excl. state)."""
    out = c._git(
        root,
        ["status", "--porcelain", "--untracked-files=all",
         "--", ".", ":(exclude)company/state"],
    )
    if not out:
        return []
    paths = []
    for line in out.splitlines():
        if len(line) <= 3:
            continue
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip()
        if len(entry) >= 2 and entry.startswith('"') and entry.endswith('"'):
            entry = entry[1:-1]
        rel = entry.replace("\\", "/")
        if not rel:
            continue
        if guard_spec.is_source(rel, os.path.basename(rel)):
            paths.append(rel)
    return paths


# --- FR-DE-15 tracking gate -----------------------------------------------

def pr_mode(root):
    """True iff an 'origin' git remote exists (the PR-mode rollout switch).

    c._git returns None on any git failure, so no-remote / no-git -> False,
    which turns the tracking gate off (local mode, fail open).
    """
    out = c._git(root, ["remote", "get-url", "origin"])
    return bool(out and out.strip())


def valid_issues(task):
    """True iff task['issues'] is a non-empty list of real (non-bool) ints."""
    if not isinstance(task, dict):
        return False
    issues = task.get("issues")
    if not isinstance(issues, list) or not issues:
        return False
    return all(isinstance(x, int) and not isinstance(x, bool) for x in issues)


def tracking_untracked(root, task):
    """True iff a feature/program task starts untracked in PR mode.

    Untracked = no valid issues list recorded. No origin remote -> pr_mode
    False -> gate off.
    """
    return (
        isinstance(task, dict)
        and task.get("type") in ("feature", "program")
        and pr_mode(root)
        and not valid_issues(task)
    )


# --- ledger ---------------------------------------------------------------

def read_ledger(root):
    """Validated ledger for the ACTIVE task. Fresh on tamper/miss/slug-change.

    A tampered checksum resets audits and dispatches to empty so blocks stay
    honest (unverifiable history counts as no verification). Never raises.
    """
    task = c.active_task(root)
    slug = task.get("task") if isinstance(task, dict) else None
    fresh = {
        "version": 1,
        "task": slug,
        "self_authored": [],
        "audits": [],
        "dispatches": [],
        "nudge_state": None,
    }
    raw = c.read_json_file(ledger_path(root))
    if not isinstance(raw, dict):
        return fresh
    stored = raw.get("checksum")
    recomputed = c.stamp_checksum(
        {k: v for k, v in raw.items() if k != "checksum"}
    )
    if stored != recomputed:
        return fresh
    if raw.get("task") != slug:
        return fresh
    nudge = raw.get("nudge_state")
    return {
        "version": raw.get("version", 1),
        "task": slug,
        "self_authored": raw.get("self_authored") or [],
        "audits": raw.get("audits") or [],
        "dispatches": raw.get("dispatches") or [],
        "nudge_state": nudge if nudge else None,
    }


def write_ledger(root, ledger):
    """Atomically write the ledger with a fresh checksum. Swallows all errors."""
    try:
        path = ledger_path(root)
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        body = {k: v for k, v in ledger.items() if k != "checksum"}
        body["checksum"] = c.stamp_checksum(
            {k: v for k, v in body.items() if k != "checksum"}
        )
        fd, tmp = tempfile.mkstemp(dir=d)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(body, f)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception:
        pass


def fresh_audit(root, ledger):
    """True if some recorded audit covers the current tree and did not fail."""
    wh = c.work_hash(root)
    for a in ledger.get("audits") or []:
        if not isinstance(a, dict):
            continue
        if a.get("work_hash") == wh and a.get("verdict") != "do-not-ship":
            return True
    return False


def staleness_reason(root, ledger):
    """Why fresh_audit is False. Called only when it is False."""
    audits = ledger.get("audits") or []
    if not audits:
        return "no audit recorded"
    wh = c.work_hash(root)
    for a in audits:
        if isinstance(a, dict) and a.get("work_hash") == wh:
            # matches the tree but fresh_audit rejected it -> do-not-ship
            return "last audit verdict was DO-NOT-SHIP"
    return "audit is stale - the tree changed after the last audit"


# --- payload readers ------------------------------------------------------

def role_of(tool_input):
    for field in guard_models.SPAWN_TYPE_FIELDS:
        val = (tool_input or {}).get(field)
        if val:
            return val
    return None


def execution_decision(task):
    """'self' / 'delegated' only when both fields are present and meaningful."""
    if not isinstance(task, dict):
        return None
    ex = task.get("execution")
    if ex not in ("self", "delegated"):
        return None
    why = task.get("execution_why")
    if not isinstance(why, str) or not why.strip():
        return None
    return ex


def emit_nudge(text):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": text}}))
    sys.exit(0)


# --- modes ----------------------------------------------------------------

def mode_a(root, ti):
    """PostToolUse Edit|Write|MultiEdit: telemetry + drift nudge. No block."""
    file_path = ti.get("file_path")
    if not file_path:
        sys.exit(0)
    task = c.active_task(root)
    if not isinstance(task, dict):
        sys.exit(0)
    slug = task.get("task")
    if not slug:
        sys.exit(0)
    if in_worktree_or_out_of_tree(file_path, root):
        sys.exit(0)
    rel = c.rel_path(root, file_path)
    if not guard_spec.is_source(rel, os.path.basename(rel)):
        sys.exit(0)

    ledger = read_ledger(root)
    seen = any(
        isinstance(e, dict) and e.get("path") == rel
        for e in ledger["self_authored"]
    )
    if not seen:
        ledger["self_authored"].append({"path": rel, "at": c.iso_now()})

    condition = (
        task.get("type") in ("feature", "program")
        and execution_decision(task) == "self"
        and len(ledger["dispatches"]) == 0
    )
    if condition:
        if (ledger.get("nudge_state") or {}).get("fingerprint") != "self-idle":
            ledger["nudge_state"] = {
                "fingerprint": "self-idle", "at": c.iso_now()
            }
            c.adherence_log(root, HOOK, "NUDGE", slug, "self-idle")
            write_ledger(root, ledger)
            emit_nudge(NUDGE_TEXT.replace("<slug>", slug))
        write_ledger(root, ledger)
        sys.exit(0)

    if ledger.get("nudge_state"):
        ledger["nudge_state"] = None
    write_ledger(root, ledger)
    sys.exit(0)


def mode_b_pre(root, ti):
    """PreToolUse Task|Agent: record a builder dispatch. No block."""
    manifest = load_manifest(root)
    if manifest is None:
        sys.exit(0)
    role = role_of(ti)
    builders = manifest.get("builder_roles") or []
    task = c.active_task(root)
    if role in builders and isinstance(task, dict):
        # FR-DE-15: an untracked feature/program task does not start. Gate the
        # builder spawn BEFORE recording telemetry (a blocked spawn leaves no
        # dispatch). Hotfix is an explicit, logged bypass; verifier and other
        # non-builder roles never reach here.
        if task.get("type") == "hotfix":
            c.log_bypass(root, HOOK, role, "hotfix mode")
        elif tracking_untracked(root, task):
            slug = task.get("task") or "<task-slug>"
            ttype = task.get("type") or "feature"
            c.block(
                root, HOOK, "spawn " + role,
                "untracked feature/program task",
                A3_MESSAGE.replace("<slug>", slug).replace("<type>", ttype),
            )
        ledger = read_ledger(root)
        ledger["dispatches"].append({"role": role, "at": c.iso_now()})
        c.adherence_log(root, HOOK, "DISPATCH", role, "builder spawn")
        write_ledger(root, ledger)
    sys.exit(0)


def mode_b_post(root, ti, payload):
    """PostToolUse Task|Agent: record a verifier completion. No block."""
    if in_worktree_or_out_of_tree(payload.get("cwd"), root):
        sys.exit(0)
    manifest = load_manifest(root)
    if manifest is None:
        sys.exit(0)
    role = role_of(ti)
    verifiers = manifest.get("verifier_roles") or []
    task = c.active_task(root)
    if role in verifiers and isinstance(task, dict):
        try:
            resp = payload.get("tool_response")
            if resp is None:
                resp = payload.get("tool_result")  # OQ-DE-02 assumption
            verdict = "do-not-ship" if "DO-NOT-SHIP" in str(resp) else "unknown"
        except Exception:
            verdict = "unknown"
        ledger = read_ledger(root)
        ledger["audits"].append({
            "role": role,
            "at": c.iso_now(),
            "work_hash": c.work_hash(root),
            "verdict": verdict,
        })
        c.adherence_log(root, HOOK, "AUDIT", role, verdict)
        write_ledger(root, ledger)
    sys.exit(0)


def mode_c(root, ti, payload):
    """PreToolUse Bash: the commit gate."""
    command = ti.get("command") or ""
    for seg in guard_commit.segments(command):
        sub, _ = guard_commit.git_subcmd(seg)
        if sub != "commit":
            continue
        if load_manifest(root) is None:
            continue
        task = c.active_task(root)
        if not isinstance(task, dict):
            continue
        if task.get("type") == "hotfix":
            c.log_bypass(root, HOOK, "git commit", "hotfix mode")
            continue
        if in_worktree_or_out_of_tree(payload.get("cwd"), root):
            continue
        if os.path.isfile(os.path.join(root, ".git", "MERGE_HEAD")):
            c.log_bypass(root, HOOK, "git commit", "merge conclusion")
            continue
        dp = dirty_source_paths(root)
        if not dp:
            continue
        ledger = read_ledger(root)
        if fresh_audit(root, ledger):
            continue
        slug = task.get("task") or "<task-slug>"
        reason = staleness_reason(root, ledger)
        shown = dp[:5]
        paths_str = ", ".join(shown)
        if len(dp) > 5:
            paths_str += ", ... and {} more".format(len(dp) - 5)
        msg = (
            MODE_C_MSG.replace("<slug>", slug)
            .replace("<reason>", reason)
            .replace("<paths>", paths_str)
        )
        c.block(root, HOOK, "git commit", "self-authored, no fresh audit", msg)
    sys.exit(0)


def mode_d(root, payload):
    """Stop: the close gate. Mirrors stop_gate.py (prints a JSON decision)."""
    if payload.get("stop_hook_active"):
        sys.exit(0)
    task = c.active_task(root)
    if not isinstance(task, dict):
        sys.exit(0)
    if task.get("type") in ("quick", "hotfix"):
        sys.exit(0)
    if load_manifest(root) is None:
        sys.exit(0)
    dp = dirty_source_paths(root)
    ledger = read_ledger(root)
    if dp and not fresh_audit(root, ledger):
        slug = task.get("task", "(unknown)")
        c.adherence_log(
            root, HOOK, "BLOCK", slug, "self-authored, no fresh audit"
        )
        reason = (
            "Active task '{}' has self-authored source changes in the main "
            "checkout with no fresh independent audit. Dispatch the auditor "
            "(Task tool, subagent_type: auditor) and commit the audited work, "
            "or move it to a worktree task branch, before finishing."
        ).format(slug)
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def mode_e(root, ti):
    """PreToolUse Edit|Write|MultiEdit: the execution gate."""
    file_path = ti.get("file_path")
    if not file_path:
        sys.exit(0)
    if in_worktree_or_out_of_tree(file_path, root):
        sys.exit(0)
    rel = c.rel_path(root, file_path)
    if not guard_spec.is_source(rel, os.path.basename(rel)):
        sys.exit(0)
    if load_manifest(root) is None:
        sys.exit(0)
    task = c.active_task(root)
    if not isinstance(task, dict):
        sys.exit(0)
    ttype = task.get("type")
    if ttype not in ("feature", "program"):
        # OQ-DE-04 assumption: non-feature/program (quick, ideation, ...) are
        # ungated here; hotfix is an explicit, logged bypass.
        if ttype == "hotfix":
            c.log_bypass(root, HOOK, rel, "hotfix mode")
        sys.exit(0)

    slug = task.get("task") or "<task-slug>"
    # FR-DE-15: an untracked feature/program task in PR mode is blocked before
    # the execution-decision check, so a task missing BOTH is told to track
    # first. Step 6 already handled hotfix; only feature/program reach here.
    if tracking_untracked(root, task):
        c.block(
            root, HOOK, rel, "untracked feature/program task",
            A3_MESSAGE.replace("<slug>", slug).replace("<type>", ttype),
        )
    decision = execution_decision(task)
    if decision == "self":
        sys.exit(0)
    if decision == "delegated":
        ledger = read_ledger(root)
        if len(ledger["dispatches"]) >= 1:
            sys.exit(0)
        c.block(
            root, HOOK, rel, "delegated but no dispatch",
            MODE_E_MSG2.replace("<slug>", slug),
        )
    c.block(
        root, HOOK, rel, "no execution decision",
        MODE_E_MSG1.replace("<slug>", slug).replace(
            "<roster>", ", ".join(roster(root))
        ),
    )


def main():
    payload = c.read_stdin_json()
    if payload is None:
        sys.exit(0)
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    root = c.project_root(payload)
    ti = payload.get("tool_input") or {}

    try:
        if event == "PostToolUse" and tool in ("Edit", "Write", "MultiEdit"):
            mode_a(root, ti)
        elif event == "PreToolUse" and tool in ("Task", "Agent"):
            mode_b_pre(root, ti)
        elif event == "PostToolUse" and tool in ("Task", "Agent"):
            mode_b_post(root, ti, payload)
        elif event == "PreToolUse" and tool == "Bash":
            mode_c(root, ti, payload)
        elif event == "Stop":
            mode_d(root, payload)
        elif event == "PreToolUse" and tool in ("Edit", "Write", "MultiEdit"):
            mode_e(root, ti)
        else:
            sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
