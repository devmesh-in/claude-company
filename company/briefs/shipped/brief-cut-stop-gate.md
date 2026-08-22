# BRIEF: cut-stop-gate

_Type: feature. Lean path. Spec: none - this brief is the spec.
Lead: direct-developer. Date: 2026-08-13. Tracking issue: #116.
Owner ruling: DECISIONS #20._

## Mission

Delete `stop_gate` outright and propagate every mention. Sixteen blocks in five
weeks, zero catches, ever - and everything it guards is uncommitted work that
cannot reach main, because `guard_commit` gates the merge and CI gates the PR.
It is hygiene wearing an enforcement badge, and it cost one working session
roughly two hours in false blocks.

Move the check it was doing to where it informs instead of blocks.

## STEP ONE, and do not skip it - the trap in this task

`tests/hooks/test_stop_gate_scope.py` does NOT only test `stop_gate`. It also
holds `CeremonyDoctrineMatchesTheGuard` and roughly twenty doctrine-clause
assertions, which are this repo's mechanism for making canon-versus-code
disagreement a red gate. One of them caught the METHOD ceremony clause drifting
from `guard_spec` today, hours after it was written, with nobody remembering to
look.

Deleting a file whose name says "stop_gate" is the obvious move and it would
silently destroy them.

**MOVE those assertions to a surviving file FIRST**, prove they still pass, and
commit that move as its own commit BEFORE any deletion. `CeremonyDoctrineMatchesTheGuard`
must still fail if `guard_spec` and METHOD's ceremony table disagree - verify
that by temporarily breaking one of them, watching it go red, and restoring.

## Then delete

1. `.claude/hooks/stop_gate.py`
2. Its wiring in `.claude/settings.json` (the `Stop` hook array)
3. Its row in `guard_models.EXPECTED_WIRING` - the wiring gate asserts every
   expected binding exists, so leaving the row makes `--check` red, and leaving
   the FILE while deleting the row makes it red the other way. Both must go.
4. The remaining `stop_gate` tests, once the doctrine assertions are safely out
5. Every mention in doctrine: `ORCHESTRATOR.md`, `company/METHOD.md`,
   `company/GATES.md`, `.claude/agents/*.md`, `docs/**`, `README.md`. Grep for
   `stop_gate` and for prose describing a Stop-time gate; some references
   describe it without naming the file.
6. Any hotfix-bypass or bypass-inventory test that enumerates it

## Then move the check where it belongs

`session_start.py` already runs once per session and prints a digest. Add ONE
line: when the gate stamp is missing, red or stale AND a non-quick, non-hotfix
entry is active, say so.

That is the same fact `stop_gate` was blocking on, delivered to the person who
can act on it at the moment they can act, instead of to the person trying to
stop. It must never block - `session_start` has no block path and must not
grow one.

## What this costs, stated so it is not discovered later

Three paths lose their only coverage: a session that edits source and never
commits, one that commits green then edits more, and an entry closed while
gates are red. All three end in uncommitted work that cannot reach main, which
is why the owner ruled to cut. The byte-identity oracle proving the gate was
scoped rather than weakened goes too. Record this in your report; do not argue
it.

## Definition of Done

- [ ] The doctrine assertions live in a surviving file and are PROVEN still
      load-bearing (break one side, watch red, restore) - in its own commit,
      before any deletion
- [ ] `grep -rn stop_gate` across tracked files returns nothing but historical
      references in `company/state/` (which is a record and stays)
- [ ] `python3 .claude/hooks/guard_models.py --check` exits 0
- [ ] `session_start` prints the stale-stamp line when it should and stays
      silent otherwise, with a test for both
- [ ] Suites: hooks, `npm test`, and `bash tests/install/run_tests.sh`. That
      last one matters because `.claude/settings.json` is copied by the
      installer. SKIP `test_update.sh` - it cannot reach this change and costs
      600 seconds.
- [ ] Conventional commits, `Task: cut-stop-gate` trailer, explicit paths

## Out of scope

Every other hook. `guard_provenance` and `_common` are owned by lanes in
flight - do not touch them.

## Report back

What changed, where the doctrine assertions went and the proof they still bite,
the grep result, the three suites, and 1-3 witness candidates.
