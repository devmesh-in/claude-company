#!/usr/bin/env python3
"""Read-side dispatch / ledger feed for claude-company.

FR-ASR-03: extracted from guard_provenance so context_pin and session_start
keep a compact status pin after provenance enforcement is deleted. This
module READS company/state/provenance-ledger.json and company/provenance.json.
It does not BLOCK. Python 3.8 stdlib only.

OQ-ASR-01 assumption: a dedicated module, not _common.py.
OQ-ASR-02 assumption: audit_verdict / response_text live here so the frozen
adapter test can still import them via the thin guard_provenance shim.
"""

import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

LEDGER_VERSION = 2

# FR-HP-15 / adapter F1: labeled verdict wins; HALT stores as do-not-ship.
_VERDICT_TOKENS = (
    ("DO-NOT-SHIP", "do-not-ship"),
    ("SHIP-WITH-FIXES", "ship-with-fixes"),
    ("HALT", "do-not-ship"),
    ("SHIP", "ship"),
)


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


def ledger_key(entry):
    """The `tasks` key for one active-task entry.

    OQ-MST-03 assumption: a slugless entry keys under the EMPTY STRING.
    """
    if not isinstance(entry, dict):
        return ""
    return entry.get("task") or ""


def active_keys(root):
    """The ledger key of every entry in flight, order preserved."""
    return [ledger_key(e) for e in c.active_tasks(root)]


def fresh_ledger():
    """An empty v2 ledger: no dispatches, no audits, nothing verified."""
    return {
        "version": LEDGER_VERSION,
        "tasks": {},
        "unattributed_dispatches": [],
        "self_authored": [],
        "audits": [],
    }


def task_record(ledger, slug):
    """The per-slug record, created empty if absent. Mutable in place."""
    tasks = ledger.get("tasks")
    if not isinstance(tasks, dict):
        tasks = {}
        ledger["tasks"] = tasks
    record = tasks.get(slug)
    if not isinstance(record, dict):
        record = {}
        tasks[slug] = record
    if not isinstance(record.get("dispatches"), list):
        record["dispatches"] = []
    if not record.get("nudge_state"):
        record["nudge_state"] = None
    return record


def dispatches_for(ledger, slug):
    """The dispatch list recorded against THIS slug. [] when absent.

    Per-slug lookup is the point: a regression to whole-ledger matching
    must fail witness W-033 (now pinned on this file).
    """
    tasks = ledger.get("tasks")
    if not isinstance(tasks, dict):
        return []
    record = tasks.get(slug)
    if not isinstance(record, dict):
        return []
    dispatches = record.get("dispatches")
    return dispatches if isinstance(dispatches, list) else []


def migrate_v1(raw, keys):
    """FR-MST-16: a v1 ledger read as v2, IN MEMORY only."""
    key = ledger_key(raw)
    if key not in keys:
        return fresh_ledger()
    ledger = fresh_ledger()
    nudge = raw.get("nudge_state")
    ledger["tasks"][key] = {
        "dispatches": raw.get("dispatches") or [],
        "nudge_state": nudge if nudge else None,
    }
    ledger["self_authored"] = raw.get("self_authored") or []
    ledger["audits"] = raw.get("audits") or []
    return ledger


def generation_closed(raw_tasks, keys):
    """True when EVERY slug this ledger was written for has closed."""
    recorded = list(raw_tasks)
    if not recorded:
        return True
    return not any(k in keys for k in recorded)


def read_ledger(root):
    """The validated v2 ledger. NEVER writes; a migration is in-memory only.

    Fresh on an unusable file, on a tampered checksum, and on a closed
    generation. Never raises.
    """
    keys = active_keys(root)
    raw = c.read_json_file(ledger_path(root))
    if not isinstance(raw, dict):
        return fresh_ledger()
    stored = raw.get("checksum")
    recomputed = c.stamp_checksum(
        {k: v for k, v in raw.items() if k != "checksum"}
    )
    if stored != recomputed:
        return fresh_ledger()
    if raw.get("version") != LEDGER_VERSION:
        return migrate_v1(raw, keys)
    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, dict):
        raw_tasks = {}
    if generation_closed(raw_tasks, keys):
        return fresh_ledger()
    ledger = fresh_ledger()
    for key, record in raw_tasks.items():
        if not isinstance(record, dict):
            continue
        nudge = record.get("nudge_state")
        ledger["tasks"][key] = {
            "dispatches": record.get("dispatches") or [],
            "nudge_state": nudge if nudge else None,
        }
    ledger["unattributed_dispatches"] = (
        raw.get("unattributed_dispatches") or []
    )
    ledger["self_authored"] = raw.get("self_authored") or []
    ledger["audits"] = raw.get("audits") or []
    return ledger


def prune_tasks(root, ledger):
    existing = ledger.get("tasks")
    if not isinstance(existing, dict):
        existing = {}
    pruned = {}
    for key in active_keys(root):
        record = existing.get(key)
        if not isinstance(record, dict):
            record = {"dispatches": [], "nudge_state": None}
        pruned[key] = record
    return pruned


def write_sealed_ledger(root, ledger):
    """Atomically write a checksum-sealed ledger. Swallows all errors.

    Not a hook. Tests seed pin/digest fixtures with this instead of driving
    deleted provenance modes.
    """
    try:
        path = ledger_path(root)
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        body = {k: v for k, v in ledger.items() if k != "checksum"}
        body["version"] = LEDGER_VERSION
        body["tasks"] = prune_tasks(root, body)
        for key in ("unattributed_dispatches", "self_authored", "audits"):
            if not isinstance(body.get(key), list):
                body[key] = []
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


def pr_mode(root):
    """True iff an 'origin' git remote exists (the PR-mode rollout switch)."""
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
    """True iff a feature/program task starts untracked in PR mode."""
    return (
        isinstance(task, dict)
        and task.get("type") in ("feature", "program")
        and pr_mode(root)
        and not valid_issues(task)
    )


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


def audit_verdict(text):
    """The verdict an auditor report states, as a stored ledger value.

    A LABELED verdict line is authoritative. HALT stores as do-not-ship.
    Returns "do-not-ship", "ship-with-fixes", "ship" or "unknown".
    """
    try:
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        alternation = "|".join(tok for tok, _v in _VERDICT_TOKENS)
        labeled = re.findall(
            r"(?im)^\W*(?:final\s+)?verdict\b[^\n]*?"
            r"(?<![A-Z-])(" + alternation + r")(?![A-Z-])",
            text,
        )
        if labeled:
            found = set()
            for hit in labeled:
                for tok, value in _VERDICT_TOKENS:
                    if hit.upper() == tok:
                        found.add(value)
            for value in ("do-not-ship", "ship-with-fixes", "ship"):
                if value in found:
                    return value
        present = []
        scrub = text
        for tok, value in _VERDICT_TOKENS:
            pattern = r"(?<![A-Z-])" + re.escape(tok) + r"(?![A-Z-])"
            if re.search(pattern, scrub):
                present.append(value)
                scrub = re.sub(pattern, " ", scrub)
        if len(present) == 1:
            return present[0]
    except Exception:
        return "unknown"
    return "unknown"


def response_text(resp):
    """A Task tool_response flattened into real text. Never raises."""
    try:
        if isinstance(resp, str):
            return resp
        if isinstance(resp, dict):
            keys = [
                k for k in ("text", "content", "result", "output") if k in resp
            ]
            if not keys:
                return str(resp)
            return "\n".join(
                p for p in (response_text(resp[k]) for k in keys) if p
            )
        if isinstance(resp, (list, tuple)):
            return "\n".join(p for p in (response_text(x) for x in resp) if p)
        return "" if resp is None else str(resp)
    except Exception:
        return ""
