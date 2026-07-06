---
name: gates
description: Run the project's full gate ladder (company/run-gates.sh) and stamp the result, or configure the gates themselves. Use when the user says /gates, "run the gates", "are we green", before any commit/merge in a claude-company project, or when a commit was hook-blocked for red/stale gates and you need current truth.
---

# /gates - run the ladder

1. Run `bash company/run-gates.sh` from the project root. It runs every gate
   in `company/gates.config`, prints the ladder, and stamps
   `company/state/gates.status` with the result and a work-tree hash.
2. Report the ladder verbatim, then one line of truth: fully green (stamp
   fresh, commits unblocked) or red (which gates, first failing output).
3. If red: do NOT weaken a gate, skip it, or edit tests to pass. Fix the
   cause, or route the failure: small defect -> fix it now; design-level ->
   back to the owning workstream with the failure output; failing twice on
   the same cause after a respawn -> stop and escalate to the owner.
4. If the stamp goes stale (any tracked edit outside company/state/ after
   stamping), the commit hook will block again - rerun this skill after
   changes; that is the intended loop.

## Configuring gates ($ARGUMENTS mentions adding/changing gates)

Edit `company/gates.config` (JSON: `{"gates": [{"name", "command",
"blocking": true}]}`) per the ladder contract in `company/GATES.md`:
cheap-to-expensive order, real commands that exit non-zero on failure, and
never a gate you intend to waive - every gate is blocking by definition.
Placeholder `CONFIGURE ME` gates fail deliberately so nobody ships on the
honor system; replace them with the project's real commands (during /onboard
these are the verified discovered commands).
