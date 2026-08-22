#!/usr/bin/env python3
"""Delegation provenance enforcement for claude-company.

Nothing self-authored integrates on the authority of the context that produced
it: work built in the main checkout by the CEO/lead must earn one independent,
read-only auditor pass before it commits. Work delegated into the hierarchy (a
worktree task branch) is verified inside that hierarchy and needs no extra
audit. This hook records provenance and enforces that rule across four modes
keyed on (hook_event_name, tool_name):

  A) PostToolUse Edit|Write|MultiEdit - telemetry + a once-per-state drift
     nudge when a feature/program runs execution: "self" with an idle team.
     NEVER blocks.
  B-pre)  PreToolUse Task|Agent  - the FR-DE-15 tracking gate, then record a
     builder dispatch. Blocks ONLY an untracked feature/program task.
  B-post) PostToolUse Task|Agent - record a verifier (auditor) completion and
     its verdict against the current work_hash. NEVER blocks.
  C) PreToolUse Bash - the commit gate: a git commit carrying dirty
     self-authored source in the main checkout with no fresh audit BLOCKS.

Two further modes shipped and were deleted unfired. A Stop close gate that
never fired and could deadlock - Mode B-post returns early for a worktree cwd
and records no audit, while the close gate blocked demanding one, so the
auditor ran, its result was discarded and Stop blocked again. And a PreToolUse
Edit execution gate that never fired once in five weeks of adherence log. Both
events stay WIRED and are now inert; see the note above main()'s dispatch.

The manifest (company/provenance.json) is the rollout switch: missing or
unreadable, every mode silently allows. Everything fails OPEN - any internal
error lets the action through - with ONE deliberate exception, documented on
dirty_source_paths: Mode C fails CLOSED when git never answers. Python 3.8
stdlib only.

Every ledger MUTATION goes through update_ledger, which holds c.state_lock
across the whole read-modify-write. Several sessions share one checkout, so an
unlocked cycle loses updates, and a lost update drops a recorded audit - after
which Mode C blocks a commit whose audit really did happen, for a reason that
reads wrong.

active-task.json holds N entries at once (one owner, several Claude Code
sessions, one checkout), so every mode reads ALL of them. FR-MST-23 splits
the hotfix handling in two, and the split is the spine of this file:

  - Exemption TYPES are PER ENTRY. A gate that skips because the single
    entry's type is exempt still evaluates the NON-EXEMPT entries and blocks
    if any of them fails. The site that survives is the FR-DE-15 tracking gate
    in Mode B-pre: it filters to the feature/program entries and blocks when
    ANY of them is untracked, so a hotfix entry sitting beside an untracked
    feature entry does not let that feature's work start.
  - Waiver BYPASSES stay ANY, and only where blocking a declared production
    emergency behind an unrelated entry is the worse failure. In this file
    that is Mode C ONLY (RISK-MST-01, accepted). No other site has an
    ANY-hotfix bypass.

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
    "auditor). Neither shape is the favoured one. If this work has grown a "
    "second seam - paths that can be built without seeing each other - a lead "
    "is the cheaper shape from here, because the audit no longer covers the "
    "spread. If it is still one seam, self is the correct decision and this "
    "note is not an instruction to dispatch. This note fires once per state "
    "per entry; it will not repeat."
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

    NOT dead code, despite having no caller left in this module. Deleting the
    execution gate took away its in-module caller (the team-on-payroll line of
    that gate's block message), but session_start.py imports this module and
    calls gp.roster(root) twice to build the session digest's team line. It is
    part of this module's surface, not an internal of the deleted gate.

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

    Derived, not spelled. This used to answer by matching the literal string
    "/.claude/worktrees/" in the path while c.path_checkout answered the same
    question from the `.git` marker that DEFINES a working-tree root. Two
    implementations of one question is the class #107 fixed and #118 removed
    everywhere else, and each half was wrong in its own direction: `git
    worktree add` accepts any path, so a real worktree in /tmp/<slug> was not
    exempt here, while any directory named .claude/worktrees/<x> was.

    Both directions change, and the second one is a TIGHTENING: a
    `.claude/worktrees/<x>/` directory with NO `.git` marker is not a checkout
    and is no longer exempt. A fixture that fakes a worktree by making the
    directory must now write a real `.git` marker. A real worktree at ANY path
    is exempt.

    Relative paths resolve against root. Empty path -> False. Any exception ->
    False, unchanged: an exemption acts only on an affirmative yes, so an
    unanswerable question leaves the gate armed.
    """
    if not path:
        return False
    try:
        target = path
        if not os.path.isabs(target):
            target = os.path.join(root, target)
        # THE TRAP. path_checkout walks up from os.path.dirname(target), so a
        # DIRECTORY handed in bare resolves to its PARENT - and a worktree ROOT
        # (which is what payload["cwd"] is) would answer "main checkout", the
        # exact opposite of the truth. Appending a child component makes the
        # directory get probed as its own container.
        if os.path.isdir(target):
            target = os.path.join(target, "_")
        tree, outside = c.path_checkout(root, target)
        if outside:
            return True
        return os.path.abspath(tree) != os.path.abspath(root)
    except Exception:
        return False


def dirty_source_paths(root):
    """(answered, paths) - dirty project-relative source paths (excl. state).

    `answered` is whether git said anything at all, and it exists because this
    is the ONE place in this file that fails CLOSED. That INVERTS the file's
    usual fail-open posture and it is deliberate: "could not look" must never
    read as "nothing to see". Mode C, the only caller, arms on `not answered`.

    What this replaces: `out = c._git(...)` then `if not out: return []`.
    _common distinguishes three outcomes and _git collapses them to two, so a
    `git status` that timed out came back falsy and was indistinguishable from
    a clean tree - the commit gate silently disarmed under load with nothing in
    the log to say why. That is measured, not theoretical: on this machine a
    sibling lane's ladder run took another lane's hooks suite from 40 seconds
    to 217 on pure CPU contention, against a 5s default timeout.

    So the timeout is GIT_SLOW_TIMEOUT, not the default. This is a whole-tree
    question asked once per git-commit segment, and waiting 30 seconds for the
    right answer is strictly better than getting a wrong one in 5.

    GIT_REFUSED is a real NEGATIVE answer and does NOT arm the gate: git ran
    and answered - not a repository, bad pathspec - and an exemption is allowed
    to act on an affirmative negative. Only silence, where git never answered
    at all, is treated as "assume the worst".
    """
    status, out = c.git_result(
        root,
        ["status", "--porcelain", "--untracked-files=all",
         "--", ".", ":(exclude)company/state"],
        timeout=c.GIT_SLOW_TIMEOUT,
    )
    if status == c.GIT_SILENT:
        return False, []
    if status != c.GIT_ANSWERED:
        return True, []
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
    return True, paths


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


def update_ledger(root, mutate):
    """Read-modify-write the ledger under c.state_lock. Returns mutate's value.

    THE ONLY ledger mutation path. Multi-session task entries shipped in
    v0.2.6, so several Claude Code sessions against one working tree is the
    normal operating mode here, and every one of them was doing an unlocked
    read-modify-write on this file. A lost update is not cosmetic: it drops a
    recorded audit, and Mode C then blocks a commit whose audit really did
    happen, citing "no audit recorded" - a block that is both wrong and
    unactionable, since the thing it asks for was already done.

    The lock spans the READ as well as the write. Wrapping only the write
    leaves the whole race intact.

    `mutate(ledger)` gets the ledger to edit in place and MUST NOT exit - a
    sys.exit inside the lock leaves the mutation half-applied and, in mode_a's
    case, skips the write entirely. Anything the caller wants to do after the
    ledger lands (log, emit, exit) is returned from mutate and done out here,
    once the lock is released.

    c.state_lock is itself fail-open in every direction - no fcntl, no state
    dir, an exception, a 2s timeout all proceed UNLOCKED - so this degrades to
    exactly the previous unlocked behavior and can never brick a session.
    """
    with c.state_lock(root):
        ledger = read_ledger(root)
        result = mutate(ledger)
        write_ledger(root, ledger)
    return result


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

    def mutate(ledger):
        # self_authored is a property of the tree, so it stays GLOBAL; the
        # nudge fingerprint names a slug, so it lives on that entry's record.
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
            record["nudge_state"] = {
                "fingerprint": "self-idle", "at": c.iso_now()
            }
            nudge_entry = task
        return nudge_entry

    # The nudge entry comes back OUT of the lock rather than being acted on
    # inside it: emit_nudge calls sys.exit, and exiting inside update_ledger
    # would skip the write that arms the once-per-state fingerprint - so the
    # same nudge would fire on every subsequent edit forever. This is still
    # exactly ONE ledger write per invocation, as before.
    nudge_entry = update_ledger(root, mutate)
    if nudge_entry is not None:
        slug = nudge_entry.get("task")
        c.adherence_log(
            root, HOOK, "NUDGE", slug,
            c.qualify_reason("self-idle", tasks, nudge_entry),
        )
        emit_nudge(NUDGE_TEXT.replace("<slug>", slug))
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
    if role in builders and not tasks:
        # c.active_tasks returns [] for BOTH "no task in flight" and "the file
        # exists but does not parse" - almost always a concurrent session
        # mid-write, since a whole-file write is not atomic. Those are opposite
        # facts. Treating the second as the first made the dispatch vanish
        # entirely, and a vanished dispatch is what later produces a false
        # "delegated but no dispatch" block with nothing anywhere for the
        # blocked agent to read that would explain it. Record it unattributed.
        if c.active_tasks_unreadable(root):
            at = c.iso_now()

            def mutate(ledger):
                ledger["unattributed_dispatches"].append({
                    "role": role, "at": at, "reason": "unreadable task state",
                })

            update_ledger(root, mutate)
            c.adherence_log(
                root, HOOK, "DISPATCH", role,
                "builder spawn, unreadable task state",
            )
        # File absent is genuinely "no task in flight" - record nothing.
        sys.exit(0)
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

        at = c.iso_now()
        attributed = attributed_entries(tasks, ti)

        def mutate(ledger):
            if attributed:
                for entry in attributed:
                    task_record(
                        ledger, ledger_key(entry)
                    )["dispatches"].append({"role": role, "at": at})
            else:
                # FR-MST-18: a dispatch naming no active slug satisfies no
                # entry's delegated requirement. Record it globally so the
                # false negative is diagnosable rather than invisible.
                ledger["unattributed_dispatches"].append(
                    {"role": role, "at": at}
                )

        update_ledger(root, mutate)
        if attributed:
            c.adherence_log(
                root, HOOK, "DISPATCH", role,
                c.qualify_reason("builder spawn", tasks, attributed),
            )
        else:
            c.adherence_log(
                root, HOOK, "DISPATCH", role,
                c.qualify_reason(
                    "builder spawn attributed to no active task", tasks, tasks
                ),
            )
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
        audit = {
            "role": role,
            "at": c.iso_now(),
            "work_hash": c.work_hash(root),
            "verdict": verdict,
        }

        def mutate(ledger):
            ledger["audits"].append(audit)

        update_ledger(root, mutate)
        c.adherence_log(root, HOOK, "AUDIT", role, verdict)
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
        # FAIL CLOSED on silence, and only on silence. An affirmative clean
        # tree allows; a tree git never reported on is treated as dirty,
        # because a gate that stops gating under load - quietly - is worse
        # than one that never gated. See dirty_source_paths.
        answered, dp = dirty_source_paths(root)
        if answered and not dp:
            continue
        # Read-only: no state_lock. write_ledger replaces the file in one
        # os.replace, so a read is never torn, and taking a 2s-timeout lock in
        # front of every Bash command would be a real cost for no correctness
        # gain.
        ledger = read_ledger(root)
        if fresh_audit(root, ledger):
            continue
        # No hotfix reached here, so every entry in flight is non-exempt.
        slugs_str = c.slug_list(tasks)
        reason = staleness_reason(root, ledger)
        if not answered:
            paths_str = (
                "unknown - git did not answer; treating the tree as dirty"
            )
        else:
            shown = dp[:5]
            paths_str = ", ".join(shown)
            if len(dp) > 5:
                paths_str += ", ... and {} more".format(len(dp) - 5)
        msg = (
            MODE_C_MSG.replace("<slugs>", slugs_str)
            .replace("<reason>", reason)
            .replace("<paths>", paths_str)
        )
        short = "self-authored, no fresh audit"
        if not answered:
            short += " (git silent)"
        c.block(
            root, HOOK, "git commit",
            c.qualify_reason(short, tasks, tasks),
            msg,
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

    # Stop and PreToolUse Edit|Write|MultiEdit are still WIRED to this hook in
    # .claude/settings.json, and guard_models pins that wiring inventory, so
    # the wiring is deliberate and stays. Both now fall through to the `else`
    # and exit 0: the close gate (Stop) and the execution gate (PreToolUse
    # Edit) were deleted unfired. The hole is not an oversight and is not an
    # invitation - do NOT hang a new mode off either event to fill it. If one
    # of those gates is ever wanted back, it comes back through a spec, not
    # through the empty slot.
    try:
        if event == "PostToolUse" and tool in ("Edit", "Write", "MultiEdit"):
            mode_a(root, ti)
        elif event == "PreToolUse" and tool in ("Task", "Agent"):
            mode_b_pre(root, ti)
        elif event == "PostToolUse" and tool in ("Task", "Agent"):
            mode_b_post(root, ti, payload)
        elif event == "PreToolUse" and tool == "Bash":
            mode_c(root, ti, payload)
        else:
            sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
