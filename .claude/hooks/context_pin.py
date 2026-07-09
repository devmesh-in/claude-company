#!/usr/bin/env python3
"""UserPromptSubmit hook: inject a one-line claude-company execution pin.

Every user turn gets a compact status line drawn from the active task and the
provenance ledger - for a feature/program task: execution mode, dispatch
count, self-authored count, and (in PR mode with no tracking issues) an iss=0
drift flag; for any other type: just the counts. A second line fires only when
a feature/program task has an idle team (no execution decision, or a decision
with zero dispatches), nudging a decision or a dispatch.

Pure read: never blocks, always exits 0, fails open on any internal error. The
roster and the doctrine already live in the system prompt, so this stays
deliberately under a tight token budget - nothing beyond the pin is injected.
Python 3.8 stdlib only.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402
import guard_provenance as gp  # noqa: E402

PREFIX = "[company]"
FEATURE_TYPES = ("feature", "program")
UNDECIDED = "undecided"
DRIFT_SEGMENT = " iss=0"
IDLE_LINE = "[company] team idle - decide execution / dispatch a tech-lead"


def emit(text):
    # OQ-DE-01 assumption: plain stdout + exit 0 is the documented injection
    # contract; a schema change is then a one-function edit.
    print(text)
    sys.exit(0)


def main():
    payload = c.read_stdin_json()
    try:
        root = c.project_root(payload)
        task = c.active_task(root)
        if not isinstance(task, dict):
            sys.exit(0)  # no active task -> nothing to pin

        slug = task.get("task")
        ttype = task.get("type")
        ledger = gp.read_ledger(root)
        disp = len(ledger["dispatches"])
        selfn = len(ledger["self_authored"])

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
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
