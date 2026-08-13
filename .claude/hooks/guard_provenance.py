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
unreadable, every mode silently allows. Everything fails OPEN: any internal
error lets the action through. Python 3.8 stdlib only.

active-task.json holds N entries at once (one owner, several Claude Code
sessions, one checkout), so every mode reads ALL of them. FR-MST-23 splits
the hotfix handling in two, and the split is the spine of this file:

  - Exemption TYPES are PER ENTRY. A gate that skips because the single
    entry's type is exempt now evaluates the NON-EXEMPT entries and blocks if
    any of them fails. That is Mode D (quick/hotfix) and the FR-DE-15 tracking
    gate in Mode B-pre and Mode E.
  - Waiver BYPASSES stay ANY, and only where blocking a declared production
    emergency behind an unrelated entry is the worse failure. In this file
    that is Mode C and Mode E ONLY (RISK-MST-01, accepted). No other site has
    an ANY-hotfix bypass.

BR-MST-02: with exactly one entry every mode produces byte-identical exit
code, stdout, stderr and adherence.log line to the single-task hook. That is
what c.qualify_reason exists for - it returns the reason unchanged at N <= 1
and names the responsible entries only at N > 1.
"""

import json
import os
import re
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

# FR-MST-25: every message below is in the ENTRY idiom - active-task.json
# holds N entries, so an escape hatch has to say WHICH entry to change and
# that the change is a targeted Edit, not a whole-file rewrite that would
# clobber another session's entry.
#
# FR-MST-30: <slugs> is the responsible-entry list (c.slug_list, cap 3). It is
# a single name at N == 1, so the rendered text is unchanged there. The cap is
# display truncation only and never reaches a decision.

# Fired once per state per entry from Mode A; <slug> is the only
# interpolation and it always names exactly ONE entry.
NUDGE_TEXT = (
    "[company] Reminder - entry '<slug>' in company/state/active-task.json "
    "runs with execution: \"self\" and zero dispatches of its own: the team "
    "is idle while you build. That is allowed and recorded, and the standing "
    "price applies - every self-authored commit needs a fresh read-only "
    "auditor pass before it integrates (one Task call, subagent_type: "
    "auditor). If this work is growing beyond glue, a tech-lead dispatch is "
    "cheaper: verification comes free through the hierarchy. This note fires "
    "once per state per entry; it will not repeat."
)

MODE_C_MSG = (
    "BLOCKED: git commit contains self-authored work with no independent "
    "verification.\n"
    "Task '<slugs>' has source changes produced in the main checkout, and no "
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
    "Production emergency: set \"type\": \"hotfix\" on YOUR entry in\n"
    "company/state/active-task.json - targeted Edit, never a whole-file "
    "rewrite\n"
    "(logged, never silent)."
)

MODE_E_MSG1 = (
    "BLOCKED: source edit on a feature/program task with no execution "
    "decision.\n"
    "Decide HOW task '<slugs>' executes and record it on YOUR entry in\n"
    "company/state/active-task.json - targeted Edit, never a whole-file "
    "rewrite\n"
    "(add both fields to that entry, then retry the edit):\n"
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
    "\"type\": \"hotfix\" on YOUR entry in active-task.json (logged, never "
    "silent)."
)

# The literal task/<slug> on the attribution line is documentation shown to
# the reader, which is why this message interpolates <slugs> and never
# <slug>.
MODE_E_MSG2 = (
    "BLOCKED: active-task.json records execution: \"delegated\" for task "
    "'<slugs>',\n"
    "but no dispatch has happened and this is a source edit in the main "
    "checkout.\n"
    "That contradicts your own written decision. Fix either side:\n"
    "1) Dispatch first (Task tool, subagent_type: tech-lead) - after a "
    "dispatch,\n"
    "   main-checkout glue edits flow freely.\n"
    "2) Or change the record: set \"execution\": \"self\" with a fresh\n"
    "   \"execution_why\" - self-built work then pays the mandatory audit at "
    "commit.\n"
    "With more than one entry active, the spawn prompt must name task/<slug> "
    "or\n"
    "the dispatch is not attributed to this entry.\n"
    "Production emergency: set \"type\": \"hotfix\" on YOUR entry (logged, "
    "never silent)."
)

# FR-DE-15 tracking gate. Interpolate only <slugs> and <type>; the '...' and
# '<n>' inside the body are literal text shown to the reader, not fields.
A3_MESSAGE = (
    "BLOCKED: task '<slugs>' is a <type> task in PR mode with no tracking "
    "issues\n"
    "recorded. All work ships through GitHub here (owner rule) - work that is "
    "not\n"
    "tracked does not start. Self-serve fix:\n"
    "1) Create one issue per deliverable: gh issue create --title ... --body "
    "...\n"
    "2) Record the numbers on YOUR entry in "
    "company/state/active-task.json:\n"
    "   \"issues\": [<n>, ...]\n"
    "3) Retry. The integration PR body will close them (Closes #<n> ...).\n"
    "No remote configured = this gate is off (local mode). Production "
    "emergency:\n"
    "set \"type\": \"hotfix\" on YOUR entry (logged, never silent)."
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
#
# FR-MST-14: the ledger is v2 and holds N entries at once:
#
#   {"version": 2,
#    "tasks": {"<slug>": {"dispatches": [...], "nudge_state": {...}|None}},
#    "unattributed_dispatches": [...],
#    "self_authored": [...],
#    "audits": [...],
#    "checksum": "..."}
#
# Dispatches and nudge state are PER-SLUG. Audits, self_authored and
# unattributed_dispatches are GLOBAL and are never keyed or pruned by slug:
# one auditor pass over the tree at work_hash H covers every entry's changes
# in that tree, so demanding N audits of one identical tree would be both
# wasteful and dishonest. nudge_state is per-slug (OQ-MST-08 assumption)
# because the nudge text names a slug, so a global fingerprint would suppress
# a true nudge for a second entry. self_authored stays global (OQ-MST-07
# assumption) - it is a property of the tree, not of an entry.

LEDGER_VERSION = 2


def ledger_key(entry):
    """The `tasks` key for one active-task entry.

    OQ-MST-03 assumption: a slugless entry keys under the EMPTY STRING, so it
    still gets its own record rather than colliding with a real slug.
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

    Per-slug lookup is the point: it is what stops one session's dispatch
    from vacuously satisfying another session's delegated decision. A
    regression to whole-ledger matching must fail a witness.
    """
    tasks = ledger.get("tasks")
    if not isinstance(tasks, dict):
        return []
    record = tasks.get(slug)
    if not isinstance(record, dict):
        return []
    dispatches = record.get("dispatches")
    return dispatches if isinstance(dispatches, list) else []


def credited_dispatches(ledger, entry, tasks):
    """The dispatches THIS entry may count, given who else is in flight.

    OQ-MST-03 assumption, fail-closed: with more than one entry active a
    dispatch is attributed by matching the entry slug in the spawn text, so a
    slugless entry can never be credited one. Its delegated decision therefore
    stays unsatisfied until the entry is given a slug.
    """
    if len(tasks or []) > 1 and not (entry or {}).get("task"):
        return []
    return dispatches_for(ledger, ledger_key(entry))


def migrate_v1(raw, keys):
    """FR-MST-16: a v1 ledger read as v2, IN MEMORY only.

    The v1 slug carries its dispatches and nudge state forward only while it
    is still in flight; self_authored and audits come with it. A v1 ledger
    written for a slug that has closed resets, exactly as it does today -
    carrying a closed task's audit forward would newly satisfy Mode C and be
    WEAKER than shipped behaviour.
    """
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
    """True when EVERY slug this ledger was written for has closed.

    FR-MST-15 removed the per-slug wipe: entries appearing and disappearing
    around a live entry never reset the ledger, which is the reported bug.
    A total turnover is a different thing - the ledger belongs to a finished
    generation of work, and keeping it would let a closed task's audit
    vacuously verify the next task's tree. That is a BLOCK today and no band
    may turn it into an ALLOW.

    An EMPTY recorded map counts as closed for the same reason. write_ledger
    prunes `tasks` to the active keys, so `tasks == {}` means the last write
    happened while nothing was active: it is a generation no ledger write ever
    claimed, while the global audits list still carries whatever the previous
    generation verified. Treating it as open let a closed task's audit be
    inherited by a task added afterwards at the same work_hash, which turns
    the Mode C and Mode D BLOCK of the single-task hook into an ALLOW. The
    ledger resets instead.
    """
    recorded = list(raw_tasks)
    if not recorded:
        return True
    return not any(k in keys for k in recorded)


def read_ledger(root):
    """The validated v2 ledger. NEVER writes; a migration is in-memory only.

    Fresh on an unusable file, on a tampered checksum, and on a closed
    generation. A tampered checksum resets audits and dispatches to empty so
    blocks stay honest (unverifiable history counts as no verification).
    Never raises.
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
    """FR-MST-17: `tasks` carries exactly the currently active ledger keys.

    A recorded slug with no entry in active-task.json is a closed task and its
    record goes. Every active key keeps a record even when empty, so the
    ledger always names the generation it was written for. The global lists
    (unattributed_dispatches, self_authored, audits) are never pruned by slug.
    """
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


def write_ledger(root, ledger):
    """Atomically write the ledger with a fresh checksum. Swallows all errors."""
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

# FR-HP-14: the verdict vocabulary, LONGEST token first. That order is load
# bearing twice - in the alternation and in the scrub below - so the SHIP
# inside DO-NOT-SHIP and inside SHIP-WITH-FIXES is never counted as a bare
# SHIP. HALT records the SAME stored value as DO-NOT-SHIP: the stored values
# cannot change, because old ledgers keep working and fresh_audit compares
# against the literal "do-not-ship".
_VERDICT_TOKENS = (
    ("DO-NOT-SHIP", "do-not-ship"),
    ("SHIP-WITH-FIXES", "ship-with-fixes"),
    ("HALT", "do-not-ship"),
    ("SHIP", "ship"),
)


def audit_verdict(text):
    """The verdict an auditor report states, as a stored ledger value.

    A LABELED verdict line ("Verdict: SHIP", "**Final verdict:** HALT") is
    authoritative; it is anchored at line start and never crosses a newline.
    Disagreeing labeled lines fail CLOSED to the most negative one. With no
    labeled line a token counts only when it is the SOLE verdict token in the
    whole text: an auditor that merely NAMES its vocabulary ("returns SHIP /
    SHIP-WITH-FIXES / DO-NOT-SHIP") must not be recorded as a rejection - the
    substring test this replaces recorded exactly that and cost four blocked
    commits against four PASSING audits.

    Returns "do-not-ship", "ship-with-fixes", "ship" or "unknown", and never
    raises on any input.
    """
    try:
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        alternation = "|".join(tok for tok, _v in _VERDICT_TOKENS)
        # The boundaries reject an adjacent letter or hyphen on either side,
        # so SHIPPING and RESHIP are not the SHIP token.
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
    # OQ-HP-09 assumption: an ambiguous audit is NOT a rejection. fresh_audit
    # already treats every verdict other than "do-not-ship" as passing, and
    # recording a guess as a rejection is how the deadlock happened.
    return "unknown"


def response_text(resp):
    """A Task tool_response flattened into real text.

    FR-HP-15: a response arrives as a list of content blocks, and str() on
    that container renders a newline as the two characters backslash and n,
    which destroys the line anchor audit_verdict depends on. Never raises.
    """
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


def role_of(tool_input):
    for field in guard_models.SPAWN_TYPE_FIELDS:
        val = (tool_input or {}).get(field)
        if val:
            return val
    return None


def attributed_entries(tasks, tool_input):
    """FR-MST-18: the entries one builder dispatch counts for.

    N == 1: the single entry, unconditionally - no prompt matching at all, so
    the shipped behaviour is untouched.

    N > 1: every entry whose slug appears in the spawn text. OQ-MST-04
    assumption: case-sensitive SUBSTRING match of the slug against the
    tool_input `prompt` and `description` fields, with no word boundary and no
    normalisation - doctrine already requires `task/<slug>` in the spawn
    prompt. The two fields are joined with a newline so a slug cannot match
    across the seam. A slugless entry is never matched (see
    credited_dispatches); returning [] means the dispatch was attributed to
    nobody.
    """
    tasks = tasks or []
    if len(tasks) <= 1:
        return list(tasks)
    ti = tool_input or {}
    text = "{}\n{}".format(ti.get("prompt") or "", ti.get("description") or "")
    return [e for e in tasks if e.get("task") and e.get("task") in text]


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
    """PostToolUse Edit|Write|MultiEdit: telemetry + drift nudge. No block.

    FR-MST-19: the nudge condition is evaluated PER ENTRY against that entry's
    own nudge_state, but at most ONE nudge fires per invocation (the first
    entry that both qualifies and is not already armed). The others fire on
    subsequent edits. self_authored stays GLOBAL - it is a property of the
    tree, not of an entry.
    """
    file_path = ti.get("file_path")
    if not file_path:
        sys.exit(0)
    tasks = c.active_tasks(root)
    if not tasks:
        sys.exit(0)
    # Today's early exit, generalised: no entry carries a slug, so there is
    # nothing to record a nudge against and nothing is written.
    if not c.slugs(tasks):
        sys.exit(0)
    if in_worktree_or_out_of_tree(file_path, root):
        sys.exit(0)
    rel = c.rel_path(root, file_path)
    if not guard_spec.is_source(rel, os.path.basename(rel)):
        sys.exit(0)

    ledger = read_ledger(root)
    # self_authored is a property of the tree, so it stays GLOBAL; the nudge
    # fingerprint names a slug, so it lives on that entry's record.
    seen = any(
        isinstance(e, dict) and e.get("path") == rel
        for e in ledger["self_authored"]
    )
    if not seen:
        ledger["self_authored"].append({"path": rel, "at": c.iso_now()})

    nudge_entry = None
    for task in tasks:
        key = ledger_key(task)
        record = task_record(ledger, key)
        qualifies = (
            bool(task.get("task"))
            and task.get("type") in ("feature", "program")
            and execution_decision(task) == "self"
            and len(credited_dispatches(ledger, task, tasks)) == 0
        )
        if not qualifies:
            if record.get("nudge_state"):
                record["nudge_state"] = None
            continue
        armed = (
            record.get("nudge_state") or {}
        ).get("fingerprint") == "self-idle"
        if armed or nudge_entry is not None:
            continue
        record["nudge_state"] = {"fingerprint": "self-idle", "at": c.iso_now()}
        nudge_entry = task

    if nudge_entry is not None:
        slug = nudge_entry.get("task")
        c.adherence_log(
            root, HOOK, "NUDGE", slug,
            c.qualify_reason("self-idle", tasks, nudge_entry),
        )
        write_ledger(root, ledger)
        emit_nudge(NUDGE_TEXT.replace("<slug>", slug))

    write_ledger(root, ledger)
    sys.exit(0)


def mode_b_pre(root, ti):
    """PreToolUse Task|Agent: record a builder dispatch, attributed per entry.

    FR-DE-15 runs first: an untracked feature/program entry does not start, and
    the gate is checked BEFORE any telemetry so a blocked spawn leaves no
    dispatch behind. FR-MST-23 makes that an ALL check over the non-exempt
    (feature/program) entries - the hotfix TYPE is an exemption, so a hotfix
    entry is simply not one of the entries this gate evaluates. It is NOT an
    ANY-hotfix waiver: a hotfix entry sitting beside an untracked feature entry
    must not start that feature's work. Verifier and other non-builder roles
    never reach here.
    """
    manifest = load_manifest(root)
    if manifest is None:
        sys.exit(0)
    role = role_of(ti)
    builders = manifest.get("builder_roles") or []
    tasks = c.active_tasks(root)
    if role in builders and tasks:
        gated = c.entries_of_type(tasks, ("feature", "program"))
        untracked = [e for e in gated if tracking_untracked(root, e)]
        hotfix = c.hotfix_entry(tasks)
        if untracked:
            c.block(
                root, HOOK, "spawn " + role,
                c.qualify_reason(
                    "untracked feature/program task", tasks, untracked
                ),
                A3_MESSAGE
                .replace("<slugs>", c.slug_list(untracked))
                .replace("<type>", untracked[0].get("type") or "feature"),
            )
        if hotfix is not None:
            c.log_bypass(
                root, HOOK, role,
                c.qualify_reason("hotfix mode", tasks, hotfix),
            )

        ledger = read_ledger(root)
        at = c.iso_now()
        attributed = attributed_entries(tasks, ti)
        if attributed:
            for entry in attributed:
                task_record(ledger, ledger_key(entry))["dispatches"].append(
                    {"role": role, "at": at}
                )
            c.adherence_log(
                root, HOOK, "DISPATCH", role,
                c.qualify_reason("builder spawn", tasks, attributed),
            )
        else:
            # FR-MST-18: a dispatch naming no active slug satisfies no entry's
            # delegated requirement. Record it globally and log it so the false
            # negative is diagnosable rather than invisible.
            ledger["unattributed_dispatches"].append({"role": role, "at": at})
            c.adherence_log(
                root, HOOK, "DISPATCH", role,
                c.qualify_reason(
                    "builder spawn attributed to no active task", tasks, tasks
                ),
            )
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
    tasks = c.active_tasks(root)
    if role in verifiers and tasks:
        try:
            resp = payload.get("tool_response")
            if resp is None:
                resp = payload.get("tool_result")  # OQ-DE-02 assumption
            verdict = audit_verdict(response_text(resp))
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
    """PreToolUse Bash: the commit gate.

    FR-MST-20. Order: git-commit segment, manifest, entries non-empty, ANY
    hotfix, worktree/merge exemptions, dirty source paths, fresh audit.

    RISK-MST-01, accepted: the hotfix waiver is ANY. One commit writes one
    tree, so blocking a declared production emergency behind an unrelated
    entry is the worse failure. Every bypass is logged and names the hotfix
    entry.

    Audits stay GLOBAL and are not demanded per entry: one auditor pass over
    the tree at work_hash H covers every entry's changes in that tree, so
    demanding N audits of one identical tree would be both wasteful and
    dishonest.
    """
    command = ti.get("command") or ""
    for seg in guard_commit.segments(command):
        sub, _ = guard_commit.git_subcmd(seg)
        if sub != "commit":
            continue
        if load_manifest(root) is None:
            continue
        tasks = c.active_tasks(root)
        if not tasks:
            continue
        hotfix = c.hotfix_entry(tasks)
        if hotfix is not None:
            c.log_bypass(
                root, HOOK, "git commit",
                c.qualify_reason("hotfix mode", tasks, hotfix),
            )
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
        # No hotfix reached here, so every entry in flight is non-exempt.
        slugs_str = c.slug_list(tasks)
        reason = staleness_reason(root, ledger)
        shown = dp[:5]
        paths_str = ", ".join(shown)
        if len(dp) > 5:
            paths_str += ", ... and {} more".format(len(dp) - 5)
        msg = (
            MODE_C_MSG.replace("<slugs>", slugs_str)
            .replace("<reason>", reason)
            .replace("<paths>", paths_str)
        )
        c.block(
            root, HOOK, "git commit",
            c.qualify_reason("self-authored, no fresh audit", tasks, tasks),
            msg,
        )
    sys.exit(0)


def mode_d(root, payload):
    """Stop: the close gate. Mirrors stop_gate.py (prints a JSON decision).

    FR-MST-21, and this is NOT an ANY-hotfix site. quick and hotfix are
    exemption TYPES and FR-MST-23 makes exemptions PER ENTRY: the gate drops
    the exempt entries and evaluates the rest, so [quick, feature] still
    blocks. The exemption belongs to the quick entry, not to the tree.
    """
    if payload.get("stop_hook_active"):
        sys.exit(0)
    tasks = c.active_tasks(root)
    if not tasks:
        sys.exit(0)
    gated = [
        e for e in tasks if e.get("type") not in ("quick", "hotfix")
    ]
    if not gated:
        sys.exit(0)
    if load_manifest(root) is None:
        sys.exit(0)
    dp = dirty_source_paths(root)
    ledger = read_ledger(root)
    if dp and not fresh_audit(root, ledger):
        # N == 1 keeps the two-argument .get verbatim so a `{}` entry still
        # renders as (unknown).
        if len(tasks) <= 1:
            slug = tasks[0].get("task", "(unknown)")
        else:
            slug = c.slug_list(gated)
        c.adherence_log(
            root, HOOK, "BLOCK", slug,
            c.qualify_reason("self-authored, no fresh audit", tasks, gated),
        )
        reason = (
            "Active task '{}' has self-authored source changes in the main "
            "checkout with no fresh independent audit. Dispatch the auditor "
            "(Task tool, subagent_type: auditor) and commit the audited work, "
            "or move it to a worktree task branch, before finishing."
        ).format(slug)
        # FR-HP-16: name the paths that armed the gate. self_authored is a
        # property of the TREE, so the offending work may predate this
        # session, and an unnamed block reads as an accusation the agent
        # being blocked cannot check. Display only - it reaches no decision.
        self_dirty = sorted(
            {
                e.get("path")
                for e in (ledger.get("self_authored") or [])
                if isinstance(e, dict)
            }.intersection(dp)
        )
        if self_dirty:
            shown = ", ".join(self_dirty[:5])
            more = len(self_dirty) - 5
            if more > 0:
                shown += " (+{} more)".format(more)
            reason += (
                " Self-authored dirty paths (possibly from an earlier "
                "session): {}.".format(shown)
            )
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def mode_e(root, ti):
    """PreToolUse Edit|Write|MultiEdit: the execution gate.

    FR-MST-22, and the ORDER is the point:
      1. path and manifest checks
      2. no entries -> allow
      3. ANY hotfix -> logged bypass, allow (RISK-MST-01, accepted: one edit
         touches one tree, and blocking a declared production emergency behind
         an unrelated entry is the worse failure)
      4. filter to the feature/program entries; none -> allow
      5. ALL tracking      - block if ANY of them is untracked
      6. ALL execution     - block if ANY of them lacks a decision
      7. per-entry dispatch - block for any delegated entry with zero
         dispatches OF ITS OWN
    Steps 5-7 are ALL checks, so a second feature entry can only make this
    gate block MORE. Step 7 goes through credited_dispatches (per-slug); a
    whole-ledger dispatch count would let session B's dispatch vacuously
    satisfy session A's delegated decision.
    """
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
    tasks = c.active_tasks(root)
    if not tasks:
        sys.exit(0)

    hotfix = c.hotfix_entry(tasks)
    if hotfix is not None:
        c.log_bypass(
            root, HOOK, rel, c.qualify_reason("hotfix mode", tasks, hotfix)
        )
        sys.exit(0)

    # OQ-DE-04 assumption: non-feature/program entries (quick, ideation, ...)
    # are ungated here.
    gated = c.entries_of_type(tasks, ("feature", "program"))
    if not gated:
        sys.exit(0)

    # FR-DE-15: untracked entries are blocked before the execution-decision
    # check, so an entry missing BOTH is told to track first.
    untracked = [e for e in gated if tracking_untracked(root, e)]
    if untracked:
        c.block(
            root, HOOK, rel,
            c.qualify_reason(
                "untracked feature/program task", tasks, untracked
            ),
            A3_MESSAGE
            .replace("<slugs>", c.slug_list(untracked))
            .replace("<type>", untracked[0].get("type") or "feature"),
        )

    undecided = [e for e in gated if execution_decision(e) is None]
    if undecided:
        c.block(
            root, HOOK, rel,
            c.qualify_reason("no execution decision", tasks, undecided),
            MODE_E_MSG1
            .replace("<slugs>", c.slug_list(undecided))
            .replace("<roster>", ", ".join(roster(root))),
        )

    delegated = [e for e in gated if execution_decision(e) == "delegated"]
    if delegated:
        ledger = read_ledger(root)
        starving = [
            e for e in delegated
            if len(credited_dispatches(ledger, e, tasks)) == 0
        ]
        if starving:
            c.block(
                root, HOOK, rel,
                c.qualify_reason(
                    "delegated but no dispatch", tasks, starving
                ),
                MODE_E_MSG2.replace("<slugs>", c.slug_list(starving)),
            )
    sys.exit(0)


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
