# CR-HP-2: accept-adr-0003

_Requesting agent/task: tech-lead, task hp-provenance (brief `company/briefs/brief-hp-provenance.md`, spec `company/specs/spec-harness-port.md`, issue #101). Date: 2026-08-13._
_Status: PROPOSED_

## Frozen surface affected

`company/adr/ADR-0003-self-authored-audit-scope.md` - its `Status` line, plus
the index row and the next-free-number line in `company/adr/README.md`.

An ADR's status is CEO-applied by doctrine (ADR-0001, `company/adr/README.md`:
"Status flips are CEO-applied via CR"), and `guard_frozen` enforces the front
half of that rule mechanically: a new ADR written with `Status: accepted` is
blocked as "new ADR born accepted".

## Why (cite the requirement)

FR-HP-47 and the hp-provenance brief both instruct this lane to create ADR-0003
with `Status: accepted`. That instruction contradicts accepted ADR-0001, whose
scope is `company/adr/` and which reserves the accept moment to the CEO. Per
`company/METHOD.md`, an accepted ADR wins on architecture and a brief that
contradicts one inside that ADR's scope is a briefing error - the builder files
a CR rather than picking a winner. So ADR-0003 ships `Status: proposed` and this
CR requests the flip.

This is the same situation, and the same resolution, as CR-HP-1 on ADR-0002.

One difference from CR-HP-1 worth recording: CR-HP-1 noted that the guard would
not actually have fired, because `rel_path` did not resolve a worktree file
against its owning checkout and so a worktree path never matched the
`company/adr/` prefix test. That defect was the P0 fixed in #107. The guard now
DOES fire inside a worktree, so this CR is the only route.

## Exact proposed change

1. In `company/adr/ADR-0003-self-authored-audit-scope.md`, line 3:

   ```
   -Status: proposed
   +Status: accepted
   ```

2. In `company/adr/README.md`, the index table gains a row and the next-free
   number advances. Note the file is currently stale on both counts - it still
   reads `Next free number: ADR-0002` and lists only ADR-0001, so ADR-0002's own
   row is missing. The correct end state is:

   ```
   Next free number: ADR-0004.
   ```
   ```
   | ADR-0002 | Freshness is content, not history position | accepted | `_common.work_hash`, gate stamp, provenance ledger |
   | ADR-0003 | The audit demand is scoped to recorded self-authorship | accepted | `.claude/hooks/guard_provenance.py`, `company/state/provenance-ledger.json` |
   ```

   The ADR-0002 row is out of this lane's scope; it is named here only so the
   CEO can repair both in one edit rather than discovering the drift twice.

## Blast radius

None mechanical. `guard_frozen` reads the on-disk status line to decide
immutability, so after the flip ADR-0003 becomes immutable and can only be
superseded. No hook, gate or test reads ADR content. No workstream rebases.

## Owner sign-off needed?

no. ADR acceptance is a CEO action by ADR-0001; the decision this ADR records
(risk-scaled audit arming) was already owner-authorized as DECISIONS #19.

## Workaround if rejected

ADR-0003 stays `Status: proposed` and remains editable. The code, the tests and
the enforcement are unaffected - only the record's durability changes, and a
proposed ADR is a weaker citation for a decision that is already shipping.

---
_CEO decision and remarks:_
