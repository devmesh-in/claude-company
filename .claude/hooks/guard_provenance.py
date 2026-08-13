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
  C) PreToolUse Bash - the commit gate: a git commit BLOCKS while the tree it
     lands in carries armed dirty source with no fresh audit covering it.
  D) Stop - the close gate: finishing a task whose tree carries armed dirty
     source with no fresh audit emits a Stop block decision.
  E) PreToolUse Edit|Write|MultiEdit - the execution gate: a source edit on a
     feature/program task whose execution decision is missing (or delegated
     with no dispatch) BLOCKS.

FR-HP-44/45 and scope item 6: the audit demand in modes C and D is ARMED by
provenance, not by the shape of the tree. Three conditions arm it, any one of
them sufficient: a dirty path the ledger RECORDS as self-authored, a ledger
whose authorship history cannot be trusted (every dirty path arms it then -
fail closed), and a diff that risk_score.py bands high. A fresh audit at the
current work_hash satisfies it, exactly as before.

The one accepted hole: source written through Bash (a heredoc, sed, a
generator script) fires no PostToolUse Edit event, so it is never recorded
self-authored and never arms the demand on its own. OQ-HP-05, accepted - the
risk band still covers the high-risk subset, and the hole is characterized by
a test rather than left implicit.

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
import subprocess
import sys

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

# FR-HP-44. <why> names WHICH reset discarded the authorship history, from the
# in-memory _untrusted marker read_ledger sets; UNTRUSTED_WHY is the whole
# vocabulary.
MODE_C_UNTRUSTED_MSG = (
    "BLOCKED: git commit with no verifiable record of who authored this "
    "work.\n"
    "Task '<slugs>' has dirty source and the provenance ledger <why>, so "
    "the\n"
    "self-authorship history that would narrow this demand cannot be "
    "trusted.\n"
    "Every dirty source path arms the audit demand until it can be "
    "(<reason>).\n"
    "Dirty source: <paths>\n"
    "The ledger is written only by this hook and is never hand-edited; if it "
    "was\n"
    "edited, that is what reset it. Fix, in order:\n"
    "1) Run `bash company/run-gates.sh` until green.\n"
    "2) Dispatch the read-only auditor over your diff (Task tool,\n"
    "   subagent_type: auditor). Its completion is recorded automatically.\n"
    "3) Retry the commit WITHOUT editing source in between - any edit stales "
    "the\n"
    "   audit, which is correct.\n"
    "Production emergency: set \"type\": \"hotfix\" on YOUR entry in\n"
    "company/state/active-task.json - targeted Edit, never a whole-file "
    "rewrite\n"
    "(logged, never silent)."
)

# Scope item 6 / DECISIONS #19. The line count in the body is history, not a
# threshold: nothing in this file decides on a number of lines.
MODE_C_RISK_MSG = (
    "BLOCKED: git commit of a high-risk diff with no independent "
    "verification.\n"
    "Task '<slugs>' carries a diff that risk_score.py bands HIGH, and no "
    "audit\n"
    "covers the current tree (<reason>).\n"
    "Delegation does not waive this. The hierarchy verifies each piece and "
    "nothing\n"
    "checks that anyone read the whole: a 4,791-line fully delegated change\n"
    "integrated here once with no independent read at all, which is what this "
    "gate\n"
    "exists to stop.\n"
    "Fix, in order:\n"
    "1) Run `bash company/run-gates.sh` until green.\n"
    "2) Dispatch the read-only auditor over your diff (Task tool,\n"
    "   subagent_type: auditor). Its completion is recorded automatically.\n"
    "3) Retry the commit WITHOUT editing source in between - any edit stales "
    "the\n"
    "   audit, which is correct.\n"
    "See the band and the six signals that drove it:\n"
    "  python3 .claude/hooks/risk_score.py\n"
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
    """True if path belongs to a nested checkout under root, or sits outside root.

    Scope item 8. The checkout that owns a path is DERIVED - the nearest
    ancestor holding a `.git` entry - and never guessed from the literal
    string `/.claude/worktrees/`. `git worktree add` accepts any path, so a
    worktree at build/elsewhere/wt2 used to lose this exemption here while
    _common.rel_path resolved it correctly; two answers to one question is
    the bug class this program just fixed. This calls the kernel's own
    derivation rather than carrying a second copy of it. That name is private
    today - CR-HP-3 asks L1 to expose it - and the whole body is fail-open,
    so an unexpected shape degrades to "not a worktree" rather than raising.

    Relative paths resolve against root. Empty path -> False.
    """
    if not path:
        return False
    try:
        p = path
        if not os.path.isabs(p):
            p = os.path.join(root, p)
        norm = os.path.normpath(p).replace(os.sep, "/")
        root_norm = os.path.normpath(os.path.abspath(root)).replace(
            os.sep, "/"
        ).rstrip("/")
        if norm == root_norm:
            return False
        if not norm.startswith(root_norm + "/"):
            return True
        # _enclosing_checkout starts at the PARENT of its candidate, so a
        # directory candidate (a payload cwd, which may be the worktree root
        # itself) is probed one level down.
        probe = os.path.join(norm, "_") if os.path.isdir(norm) else norm
        return bool(c._enclosing_checkout(probe, root_norm))
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


def active_keys_known(root):
    """False while active-task.json EXISTS but does not parse.

    A torn read is a concurrent session mid-write and is transient, so
    c.active_tasks returns [] for it. Reading that [] as the active key set
    would make generation_closed() see EVERY recorded slug as closed, and the
    next write would then PERSIST that reset - destroying a real recorded
    audit and the self_authored list the FR-HP-44 narrowing reads. That path
    only became reachable with FR-HP-43, which gave a torn task file its own
    ledger write, and it turns a shipped BLOCK into an ALLOW: once the record
    of who authored the dirty paths is gone, the next Mode A event rewrites a
    valid ledger around a DIFFERENT path and the dirty work is no longer
    recorded as anyone's.

    c.active_tasks_unreadable exists precisely so a caller can tell "nothing
    in flight" from "cannot tell right now". This is the second one, and the
    answer to it is to touch nothing keyed on the slug set.
    """
    return not c.active_tasks_unreadable(root)


def fresh_ledger(untrusted=None):
    """An empty v2 ledger: no dispatches, no audits, nothing verified.

    `untrusted` names why the ledger's history was discarded, when it was.
    It is IN MEMORY ONLY - write_ledger strips every underscore-prefixed key
    - and it exists because a reset destroys the self_authored record along
    with everything else. FR-HP-44 narrows the audit demand to what this
    company is RECORDED as having authored, so a ledger that cannot account
    for authorship must fall back to arming on every dirty path, which is
    exactly the shipped behaviour. Without this, hand-editing the ledger
    would DISARM the gate instead of arming it.
    """
    ledger = {
        "version": LEDGER_VERSION,
        "tasks": {},
        "unattributed_dispatches": [],
        "self_authored": [],
        "audits": [],
    }
    if untrusted:
        ledger["_untrusted"] = untrusted
    return ledger


# The whole vocabulary of the _untrusted marker, rendered into the block
# messages. Keys are exactly the markers read_ledger sets.
UNTRUSTED_WHY = {
    "checksum": "does not verify its own checksum",
    "generation": "was reset when its task generation closed",
    "unreadable": "exists but does not parse",
}


def untrusted_why(marker):
    """The phrase naming what discarded the ledger's authorship history."""
    return UNTRUSTED_WHY.get(marker, "cannot account for authorship")


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


def migrate_v1(raw, keys, keys_known=True):
    """FR-MST-16: a v1 ledger read as v2, IN MEMORY only.

    The v1 slug carries its dispatches and nudge state forward only while it
    is still in flight; self_authored and audits come with it. A v1 ledger
    written for a slug that has closed resets, exactly as it does today -
    carrying a closed task's audit forward would newly satisfy Mode C and be
    WEAKER than shipped behaviour.

    `keys_known` False means active-task.json could not be read this instant
    (see active_keys_known), so "still in flight" is unanswerable and the
    record is carried forward rather than discarded on a torn read.
    """
    key = ledger_key(raw)
    if keys_known and key not in keys:
        return fresh_ledger("generation")
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

    FR-HP-44: every reset that DISCARDS an existing self_authored record
    carries the in-memory _untrusted marker, so the narrowed audit demand
    falls back to arming on every dirty path. An ABSENT file carries no
    marker: nothing was lost, this company has simply authored nothing
    through the hooks in this tree, which is the case the narrowing exists
    to allow.
    """
    keys = active_keys(root)
    keys_known = active_keys_known(root)
    raw = c.read_json_file(ledger_path(root))
    if not isinstance(raw, dict):
        if os.path.exists(ledger_path(root)):
            return fresh_ledger("unreadable")
        return fresh_ledger()
    stored = raw.get("checksum")
    recomputed = c.stamp_checksum(
        {k: v for k, v in raw.items() if k != "checksum"}
    )
    if stored != recomputed:
        return fresh_ledger("checksum")
    if raw.get("version") != LEDGER_VERSION:
        return migrate_v1(raw, keys, keys_known)
    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, dict):
        raw_tasks = {}
    if keys_known and generation_closed(raw_tasks, keys):
        return fresh_ledger("generation")
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
    if not active_keys_known(root):
        # A torn active-task.json makes the active key set unknowable, and
        # pruning against an unknowable set deletes every record. FR-HP-43
        # writes the ledger on exactly that path, so without this the torn
        # read is PERSISTED as a closed generation.
        return existing
    pruned = {}
    for key in active_keys(root):
        record = existing.get(key)
        if not isinstance(record, dict):
            record = {"dispatches": [], "nudge_state": None}
        pruned[key] = record
    return pruned


def write_ledger(root, ledger):
    """Atomically write the ledger with a fresh checksum. Swallows all errors.

    Underscore-prefixed keys are IN-MEMORY only (FR-HP-44's _untrusted
    marker), so they reach neither the file nor the checksum. Wrap the whole
    read-modify-write in c.state_lock at every call site - locking the write
    alone still loses the other session's update.
    """
    try:
        body = {
            k: v for k, v in ledger.items()
            if k != "checksum" and not k.startswith("_")
        }
        body["version"] = LEDGER_VERSION
        body["tasks"] = prune_tasks(root, body)
        for key in ("unattributed_dispatches", "self_authored", "audits"):
            if not isinstance(body.get(key), list):
                body[key] = []
        body["checksum"] = c.stamp_checksum(
            {k: v for k, v in body.items() if k != "checksum"}
        )
        c.write_json_atomic(ledger_path(root), body)
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


def paths_display(paths, cap=5):
    """The path list as one display string. Display only, never a decision."""
    shown = list(paths)[:cap]
    text = ", ".join(shown)
    if len(paths) > cap:
        text += ", ... and {} more".format(len(paths) - cap)
    return text


def self_authored_set(ledger):
    """The project-relative paths the ledger records as self-authored."""
    return {
        e.get("path") for e in (ledger.get("self_authored") or [])
        if isinstance(e, dict) and e.get("path")
    }


def armed_self_paths(ledger, dirty):
    """FR-HP-44: the dirty paths this company is RECORDED as having authored.

    METHOD mechanism 5 says nothing SELF-AUTHORED integrates unaudited. The
    gate has always asked a tree-shaped question instead - every dirty source
    path, including another session's and the owner's own - so a clean,
    fully-delegated session could not commit or reach Stop without deleting
    files it did not own. This asks the provenance-shaped question the
    doctrine actually states. Mode A is what populates self_authored, one
    entry per main-checkout source Edit/Write.
    """
    # OQ-HP-05 assumption: source written through Bash (heredoc, sed, a
    # generator script) fires no PostToolUse Edit event, so it never lands in
    # self_authored and never arms the demand here. Accepted: the risk band
    # still covers the high-risk subset of that hole.
    return sorted(self_authored_set(ledger).intersection(dirty or []))


def delegated_with_dispatches(ledger, tasks, gated, dirty):
    """FR-HP-45: an ENTRY-shaped route to the exemption mechanism 5 already
    grants delegated work - its verification happened inside the hierarchy.

    Requires ALL THREE, and only the first is a declaration:
      - every gated entry declares execution: delegated
      - each of them has at least one HOOK-RECORDED credited dispatch
      - no dirty path appears in the HOOK-RECORDED self_authored list
    The declaration alone unlocks nothing. Both load-bearing conditions are
    written by this hook and cannot be asserted by the agent being gated.

    Its allow set is a strict SUBSET of what armed_self_paths() already
    allows, since the third condition makes armed_self_paths() empty. It is
    kept because it is the entry-shaped statement of the doctrine and because
    it leaves a named, greppable BYPASS line in adherence.log where the
    path-shaped narrowing allows silently. It is deliberately evaluated AFTER
    the risk band, so it can never waive a high-band diff.
    """
    if not gated:
        return False
    if self_authored_set(ledger).intersection(dirty or []):
        return False
    return all(
        execution_decision(e) == "delegated"
        and len(credited_dispatches(ledger, e, tasks)) > 0
        for e in gated
    )


# Scope item 6 / DECISIONS #19. risk_score.py is READ-ONLY to this lane, so
# the band is taken through its documented machine contract (the single
# RISK_JSON line it prints last) rather than by importing and re-composing
# its scorers. Running it as a child process is deliberate on three counts:
# its own secret scan carries a 30s subprocess timeout that must never be
# inherited by a PreToolUse hook, the child ALWAYS exits 0 so its internal
# failures cannot leak into this gate, and the band is only ever computed on
# the narrow path where it can change the verdict.
# A latency bound, deliberately NOT a risk threshold: no verdict is derived
# from it, and exceeding it yields "no answer", which arms nothing. The bands
# remain the only fence, which is the DECISIONS #19 condition. (This carries
# no OQ tag on purpose - OQ-HP-05 is the Bash hole, not this.)
RISK_TIMEOUT_SECONDS = 10


def risk_band(root):
    """The band risk_score.py reports for this tree, or None. Never raises.

    None means "no answer", and no answer never arms anything - a broken or
    slow scorer must not start blocking commits.
    """
    # Known limitation, CR-HP-4: risk_score scores `base...HEAD`, which is
    # COMMITTED work on the branch. It cannot see uncommitted working-tree
    # changes, so the first commit on a fresh task branch is always scored
    # against an empty diff. The band therefore arms from the second commit
    # onward, and at task close.
    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "risk_score.py"
    )
    try:
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = root
        result = subprocess.run(
            [sys.executable, script, "--json"],
            capture_output=True, timeout=RISK_TIMEOUT_SECONDS, env=env,
        )
        out = result.stdout.decode("utf-8", "replace")
        for line in reversed(out.splitlines()):
            if line.startswith("RISK_JSON: "):
                data = json.loads(line[len("RISK_JSON: "):])
                band = data.get("band")
                return band if band in ("low", "medium", "high") else None
    except Exception:
        return None
    return None


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
    # There USED to be an early exit here for "no entry carries a slug", on
    # the grounds that there is nothing to record a nudge against. FR-HP-44
    # makes that exit unsafe: self_authored is now what ARMS Modes C and D,
    # and it is GLOBAL - a property of the tree, never keyed by slug - so
    # skipping the write let a slugless entry hold dirty source that nothing
    # was recorded as having authored, turning a shipped BLOCK into an ALLOW.
    # The nudge is unaffected: its own per-entry test already requires
    # bool(task.get("task")), so a slugless entry still never nudges, and the
    # empty-string key is the documented OQ-MST-03 shape.
    if in_worktree_or_out_of_tree(file_path, root):
        sys.exit(0)
    rel = c.rel_path(root, file_path)
    if not guard_spec.is_source(rel, os.path.basename(rel)):
        sys.exit(0)

    # FR-HP-40: the whole read-modify-write is one critical section. The nudge
    # is DECIDED here and EMITTED after the lock is released - emit_nudge
    # exits the process, and exiting from inside the manager would skip the
    # release path.
    nudge_slug = None
    with c.state_lock(root):
        ledger = read_ledger(root)
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

        if nudge_entry is not None:
            nudge_slug = nudge_entry.get("task")
            c.adherence_log(
                root, HOOK, "NUDGE", nudge_slug,
                c.qualify_reason("self-idle", tasks, nudge_entry),
            )
        write_ledger(root, ledger)

    if nudge_slug:
        emit_nudge(NUDGE_TEXT.replace("<slug>", nudge_slug))
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

    FR-HP-43: the early exits are flat, so a builder spawn is never silently
    dropped when the task file cannot be read.
    """
    manifest = load_manifest(root)
    if manifest is None:
        sys.exit(0)
    role = role_of(ti)
    builders = manifest.get("builder_roles") or []
    if role not in builders:
        sys.exit(0)
    tasks = c.active_tasks(root)
    if not tasks:
        # A builder spawn while active-task.json EXISTS but does not parse is a
        # concurrent session mid-write, not an absence of work. Dropping it
        # silently is what produces the false "delegated but no dispatch" block
        # later, so record it globally; a later repair can attribute it.
        if c.active_tasks_unreadable(root):
            with c.state_lock(root):
                ledger = read_ledger(root)
                ledger["unattributed_dispatches"].append(
                    {"role": role, "at": c.iso_now()}
                )
                write_ledger(root, ledger)
            c.adherence_log(
                root, HOOK, "DISPATCH", role,
                "builder spawn with no readable task entries "
                "(recorded unattributed)",
            )
        sys.exit(0)

    # The FR-DE-15 tracking gate and the hotfix bypass stay OUTSIDE and BEFORE
    # the lock, so a blocked spawn still leaves no dispatch behind.
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

    with c.state_lock(root):  # FR-HP-41
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
        with c.state_lock(root):  # FR-HP-42
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
    hotfix, worktree/merge exemptions, dirty source paths, fresh audit, then
    the three arming conditions in order - untrusted ledger, recorded
    self-authorship, high risk band - and finally the FR-HP-45 delegated
    bypass. Anything that reaches the end allows: dirty source nobody is
    recorded as having authored, in a band under high, arms nothing.

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
        # Scope item 7: the exemption belongs to the repo the commit LANDS in,
        # not to the session cwd. guard_commit.seg_git_dir is L2's resolver for
        # exactly that question (last -C wins, verified by git itself);
        # reusing it keeps one answer instead of two.
        target = guard_commit.seg_git_dir(seg, payload, root)
        if in_worktree_or_out_of_tree(target, root):
            continue
        if os.path.isfile(os.path.join(root, ".git", "MERGE_HEAD")):
            c.log_bypass(root, HOOK, "git commit", "merge conclusion")
            continue
        # Any nested checkout has been exempted above, so the only tree left
        # to judge is the project root.
        dp = dirty_source_paths(root)
        if not dp:
            continue
        ledger = read_ledger(root)
        if fresh_audit(root, ledger):
            continue
        # No hotfix reached here, so every entry in flight is non-exempt.
        slugs_str = c.slug_list(tasks)
        reason = staleness_reason(root, ledger)

        # FR-HP-44, arming condition 2: with no trustworthy authorship record
        # every dirty path arms the demand, which is the shipped behaviour.
        untrusted = ledger.get("_untrusted")
        if untrusted:
            c.block(
                root, HOOK, "git commit",
                c.qualify_reason(
                    "unverifiable provenance ledger, no fresh audit",
                    tasks, tasks,
                ),
                MODE_C_UNTRUSTED_MSG.replace("<slugs>", slugs_str)
                .replace("<why>", untrusted_why(untrusted))
                .replace("<reason>", reason)
                .replace("<paths>", paths_display(dp)),
            )

        # Arming condition 1. MODE_C_MSG's <paths> line is labelled
        # "Self-authored paths:" and until now rendered every dirty path;
        # feeding it `armed` makes that label true.
        armed = armed_self_paths(ledger, dp)
        if armed:
            c.block(
                root, HOOK, "git commit",
                c.qualify_reason(
                    "self-authored, no fresh audit", tasks, tasks
                ),
                MODE_C_MSG.replace("<slugs>", slugs_str)
                .replace("<reason>", reason)
                .replace("<paths>", paths_display(armed)),
            )

        # Arming condition 3, and the compensating control for the narrowing
        # below: the band is computed ONLY here, so the common paths (clean
        # tree, fresh audit, self-authored dirty) pay nothing for it.
        band = risk_band(root)
        if band == "high":
            c.block(
                root, HOOK, "git commit",
                c.qualify_reason(
                    "high-risk diff, no fresh audit", tasks, tasks
                ),
                MODE_C_RISK_MSG.replace("<slugs>", slugs_str)
                .replace("<reason>", reason),
            )

        # FR-HP-45: the entry-shaped statement of the same exemption, kept for
        # the named BYPASS line it leaves where the narrowing allows silently.
        if delegated_with_dispatches(ledger, tasks, tasks, dp):
            c.log_bypass(
                root, HOOK, "git commit",
                c.qualify_reason(
                    "delegated execution with recorded dispatches",
                    tasks, tasks,
                ),
            )
            continue
        # FR-HP-44 narrowing: dirty source nobody recorded as self-authored,
        # in a low or medium band, arms nothing.
        continue
    sys.exit(0)


def stop_block(root, tasks, gated, slug, short_reason, reason):
    """Log the BLOCK line and print one Stop block decision. Never returns.

    The three Mode D arming conditions differ only in their reason strings,
    so the evidence line and the decision shape are written once here.
    """
    c.adherence_log(
        root, HOOK, "BLOCK", slug,
        c.qualify_reason(short_reason, tasks, gated),
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def mode_d(root, payload):
    """Stop: the close gate. Mirrors stop_gate.py (prints a JSON decision).

    FR-MST-21, and this is NOT an ANY-hotfix site. quick and hotfix are
    exemption TYPES and FR-MST-23 makes exemptions PER ENTRY: the gate drops
    the exempt entries and evaluates the rest, so [quick, feature] still
    blocks. The exemption belongs to the quick entry, not to the tree.

    After those preconditions the arming order is Mode C's, condition for
    condition: untrusted ledger, recorded self-authorship, high risk band,
    then the FR-HP-45 delegated bypass. Reaching the end allows.
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
    if not dp:
        sys.exit(0)
    if fresh_audit(root, ledger):
        sys.exit(0)

    # N == 1 keeps the two-argument .get verbatim so a `{}` entry still
    # renders as (unknown). The slug is shared by all three block reasons.
    if len(tasks) <= 1:
        slug = tasks[0].get("task", "(unknown)")
    else:
        slug = c.slug_list(gated)

    # The same three arming conditions as Mode C, in the same order.
    untrusted = ledger.get("_untrusted")
    if untrusted:
        stop_block(
            root, tasks, gated, slug,
            "unverifiable provenance ledger, no fresh audit",
            (
                "Active task '{}' has dirty source and the provenance ledger "
                "{}, so there is no verifiable record of who authored this "
                "work. Every dirty source path arms the audit demand until "
                "there is. Dispatch the auditor (Task tool, subagent_type: "
                "auditor) and commit the audited work, or move it to a "
                "worktree task branch, before finishing."
            ).format(slug, untrusted_why(untrusted)),
        )

    # FR-HP-16: name the paths that armed the gate. self_authored is a
    # property of the TREE, so the offending work may predate this session,
    # and an unnamed block reads as an accusation the agent being blocked
    # cannot check. FR-HP-44 makes that same intersection the ARMING set.
    armed = armed_self_paths(ledger, dp)
    if armed:
        reason = (
            "Active task '{}' has self-authored source changes in the main "
            "checkout with no fresh independent audit. Dispatch the auditor "
            "(Task tool, subagent_type: auditor) and commit the audited work, "
            "or move it to a worktree task branch, before finishing."
        ).format(slug)
        shown = ", ".join(armed[:5])
        more = len(armed) - 5
        if more > 0:
            shown += " (+{} more)".format(more)
        reason += (
            " Self-authored dirty paths (possibly from an earlier "
            "session): {}.".format(shown)
        )
        stop_block(
            root, tasks, gated, slug,
            "self-authored, no fresh audit", reason,
        )

    band = risk_band(root)
    if band == "high":
        stop_block(
            root, tasks, gated, slug,
            "high-risk diff, no fresh audit",
            (
                "Active task '{}' has uncommitted source changes and "
                "risk_score.py bands this diff high, with no fresh "
                "independent audit. Delegation does not waive a high band - "
                "the hierarchy verifies each piece and nothing checks that "
                "anyone read the whole. Dispatch the auditor (Task tool, "
                "subagent_type: auditor) and commit the audited work before "
                "finishing. Run `python3 .claude/hooks/risk_score.py` to see "
                "what drove the band."
            ).format(slug),
        )

    if delegated_with_dispatches(ledger, tasks, gated, dp):
        c.log_bypass(
            root, HOOK, "stop",
            c.qualify_reason(
                "delegated execution with recorded dispatches", tasks, gated
            ),
        )
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
