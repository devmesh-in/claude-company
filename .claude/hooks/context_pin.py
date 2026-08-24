#!/usr/bin/env python3
"""UserPromptSubmit hook: inject a compact claude-company execution pin.

Every user turn gets a compact status block drawn from the entries in flight
and the provenance ledger - for a feature/program entry: execution mode,
dispatch count, and (in PR mode with no tracking issues) an iss=0 drift flag;
for any other type: just the dispatch count.

With exactly ONE entry in flight the pin is what it has always been (BR-MST-02
identity): one status line carrying self=, plus a standalone team-idle line
when that entry has no execution decision or a decision with zero dispatches.

With MORE than one entry the pin renders one terse line per entry (display
truncated at three, then a single overflow line) and moves the two tree-wide
facts onto one shared trailing line: self= (a property of the tree, which
would be a lie on a per-entry line) and, when a hotfix entry falls outside the
displayed window, the emergency HOTFIX marker. The idle marker moves onto the
drifty entry's OWN line, because at N > 1 a standalone line cannot say WHICH
team is idle. At most five lines are ever emitted, at any N.

Pure read: never blocks, always exits 0, fails open on any internal error. The
roster and the doctrine already live in the system prompt, so this stays
deliberately under a tight token budget - nothing beyond the pin is injected.
Python 3.8 stdlib only.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402
import dispatch_feed as gp  # noqa: E402  # FR-ASR-03

PREFIX = "[company]"
FEATURE_TYPES = ("feature", "program")
UNDECIDED = "undecided"
DRIFT_SEGMENT = " iss=0"
IDLE_SEGMENT = " idle"
HOTFIX_SEGMENT = " HOTFIX"
IDLE_LINE = (
    "[company] team idle - no execution decision yet, or one with no "
    "dispatch behind it; decide self or delegated on the seam count"
)

# Display truncation ONLY. This number never reaches a block/allow decision -
# nothing here blocks, and no entry is dropped from any count because of it.
DISPLAY_CAP = 3


def emit(text):
    # OQ-DE-01 assumption: plain stdout + exit 0 is the documented injection
    # contract; a schema change is then a one-function edit.
    print(text)
    sys.exit(0)


def single_pin(root, tasks):
    """N == 1: byte-identical to the pin shipped before multi-session tasks."""
    task = tasks[0]

    slug = task.get("task")
    ttype = task.get("type")
    ledger = gp.read_ledger(root)
    disp = len(gp.dispatches_for(ledger, gp.ledger_key(task)))
    selfn = len(ledger["self_authored"])  # global: a property of the tree

    if ttype in FEATURE_TYPES:
        decision = gp.execution_decision(task)
        line1 = "{} {} {} exec={} disp={} self={}".format(
            PREFIX, slug, ttype, decision or UNDECIDED, disp, selfn
        )
        # FR-DE-15 drift signal: the tracking gate is armed and nothing is
        # recorded (PR mode, feature/program, no valid issues).
        if gp.tracking_untracked(root, task):
            line1 += DRIFT_SEGMENT
        drifty = decision is None or disp == 0
    else:
        # OQ-DE-04 assumption: ideation treated like quick - no exec, no
        # iss, no idle line.
        line1 = "{} {} {} disp={} self={}".format(
            PREFIX, slug, ttype, disp, selfn
        )
        drifty = False

    lines = [line1]
    if drifty:
        lines.append(IDLE_LINE)
    emit("\n".join(lines))


def entry_line(root, ledger, entry):
    """One terse line for one entry. No self= here: that is a TREE fact."""
    slug = entry.get("task") or "<task-slug>"
    ttype = entry.get("type")
    disp = len(gp.dispatches_for(ledger, gp.ledger_key(entry)))

    if ttype in FEATURE_TYPES:
        decision = gp.execution_decision(entry)
        line = "{} {} {} exec={} disp={}".format(
            PREFIX, slug, ttype, decision or UNDECIDED, disp
        )
        if gp.tracking_untracked(root, entry):
            line += DRIFT_SEGMENT
        # The idle marker rides THIS entry's line: at N > 1 a standalone line
        # cannot name the team that is idle.
        if decision is None or disp == 0:
            line += IDLE_SEGMENT
    else:
        line = "{} {} {} disp={}".format(PREFIX, slug, ttype, disp)

    if ttype == "hotfix":
        line += HOTFIX_SEGMENT
    return line


def multi_pin(root, tasks):
    """N > 1: one line per entry (capped), one overflow line, one tree line."""
    ledger = gp.read_ledger(root)
    shown = tasks[:DISPLAY_CAP]
    lines = [entry_line(root, ledger, entry) for entry in shown]

    hidden = len(tasks) - len(shown)
    if hidden > 0:
        lines.append("{} and {} more".format(PREFIX, hidden))

    tree = "{} tree: self={}".format(PREFIX, len(ledger["self_authored"]))
    # OQ-MST-01 assumption: display truncates at three entries, so a hotfix
    # past the window would lose its marker. Carry the slug on the tree line
    # instead. Truncation is cosmetic - there is no cap on entries and nothing
    # here blocks.
    hotfix = c.hotfix_entry(tasks)
    if hotfix is not None and c.hotfix_entry(shown) is None:
        tree += "{}:{}".format(
            HOTFIX_SEGMENT, hotfix.get("task") or "<task-slug>"
        )
    lines.append(tree)

    emit("\n".join(lines))


def main():
    payload = c.read_stdin_json()
    try:
        root = c.project_root(payload)
        tasks = c.active_tasks(root)
        if not tasks:
            sys.exit(0)  # no active task -> nothing to pin
        # BR-MST-02: the single-entry path is the shipped path, untouched.
        if len(tasks) == 1:
            single_pin(root, tasks)
        multi_pin(root, tasks)
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
