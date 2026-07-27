#!/usr/bin/env python3
"""SessionStart hook: print a compact claude-company state digest.

If company/state/RESUME.md or STATUS.md exist, emit a plain-text digest (<= 60
lines): the first 40 lines of RESUME.md, the first 20 of STATUS.md, and a
digest PAIR (identity line + execution line) per task entry in flight, display
truncated at three entries plus one overflow line.

With exactly ONE entry the two lines are what they have always been (BR-MST-02
identity). `dispatches` is that entry's PER-SLUG count; `self-authored` is the
GLOBAL count, a property of the tree rather than of an entry. Always exits 0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402
import guard_provenance as gp  # noqa: E402

MAX_LINES = 60

# Display truncation ONLY, and never a decision: this hook prints and exits 0.
DIGEST_CAP = 3

EXEC_LINE = (
    "execution: {} | dispatches: {} | self-authored: {} files | team: {}"
)


def head_lines(path, n):
    try:
        with open(path) as f:
            out = []
            for _ in range(n):
                line = f.readline()
                if not line:
                    break
                out.append(line.rstrip("\n"))
            return out
    except Exception:
        return []


def single_digest(root, tasks, out):
    """N == 1: the two lines shipped before multi-session tasks, unchanged."""
    task = tasks[0]
    out.append(
        "active-task: {} ({}) brief={}".format(
            task.get("task"), task.get("type"), task.get("brief")
        )
    )
    ledger = gp.read_ledger(root)
    out.append(
        EXEC_LINE.format(
            gp.execution_decision(task) or "undecided",
            len(gp.dispatches_for(ledger, gp.ledger_key(task))),
            len(ledger["self_authored"]),  # global, not per-slug
            ", ".join(gp.roster(root)),
        )
    )


def multi_digest(root, tasks, out):
    """N > 1: one digest PAIR per entry (capped), then one overflow line."""
    ledger = gp.read_ledger(root)
    team = ", ".join(gp.roster(root))
    selfn = len(ledger["self_authored"])  # global, not per-slug
    shown = tasks[:DIGEST_CAP]
    for entry in shown:
        line = "active-task: {} ({}) brief={}".format(
            entry.get("task"), entry.get("type"), entry.get("brief")
        )
        # The emergency marker names its own slug: at N > 1 the reader cannot
        # tell which entry is the hotfix otherwise.
        if entry.get("type") == "hotfix":
            line += " HOTFIX:{}".format(entry.get("task") or "<task-slug>")
        out.append(line)
        out.append(
            EXEC_LINE.format(
                gp.execution_decision(entry) or "undecided",
                len(gp.dispatches_for(ledger, gp.ledger_key(entry))),
                selfn,
                team,
            )
        )
    hidden = len(tasks) - len(shown)
    if hidden > 0:
        out.append("and {} more".format(hidden))


def main():
    payload = c.read_stdin_json() or {}
    try:
        root = c.project_root(payload)
        state = os.path.join(root, "company", "state")
        resume = os.path.join(state, "RESUME.md")
        status = os.path.join(state, "STATUS.md")
        if not (os.path.exists(resume) or os.path.exists(status)):
            sys.exit(0)

        out = ["claude-company state digest"]
        if os.path.exists(resume):
            out.append("-- RESUME.md --")
            out.extend(head_lines(resume, 40))
        if os.path.exists(status):
            out.append("-- STATUS.md --")
            out.extend(head_lines(status, 20))
        tasks = c.active_tasks(root)
        # BR-MST-02: the single-entry path is the shipped path, untouched.
        if len(tasks) == 1:
            single_digest(root, tasks, out)
        elif tasks:
            multi_digest(root, tasks, out)
        # MAX_LINES is deliberately unchanged: no reservation, no raise. A
        # saturated RESUME/STATUS hiding the digest is a known worry, not this
        # band's fix.
        print("\n".join(out[:MAX_LINES]))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
