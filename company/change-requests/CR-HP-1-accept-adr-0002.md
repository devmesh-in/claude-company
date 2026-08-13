# CR-HP-1: accept-adr-0002

_Requesting agent/task: tech-lead, task hp-kernel (brief company/briefs/brief-hp-kernel.md, spec company/specs/spec-harness-port.md, issue #98). Date: 2026-08-13._
_Status: OPEN_

## Frozen surface affected

`company/adr/ADR-0002-content-based-freshness.md` - its `Status` line, plus the
index row and the next-free-number line in `company/adr/README.md`.

An ADR's status is CEO-applied by doctrine (ADR-0001, `company/adr/README.md`:
"Status flips are CEO-applied via CR"), and `guard_frozen` enforces the front
half of that rule mechanically: a new ADR written with `Status: accepted` is
blocked as "new ADR born accepted".

## Why (cite the requirement)

FR-HP-08 and the hp-kernel brief both instruct this lane to create ADR-0002 with
`Status: accepted`. That instruction contradicts accepted ADR-0001, whose scope
is `company/adr/` and which reserves the accept moment to the CEO. Per
`company/METHOD.md`, an accepted ADR wins on architecture and a brief that
contradicts one inside its scope is a briefing error - the builder files a CR
rather than picking a winner. So ADR-0002 ships `Status: proposed` and this CR
requests the flip.

Two notes for the decision, both facts rather than arguments:

1. The guard would NOT actually have fired here. It resolves the project root
   from `CLAUDE_PROJECT_DIR`, which the harness pins to the main checkout, so a
   worktree path does not match its `company/adr/` prefix test and the block is
   skipped. The rule was followed because it is the rule, not because it was
   enforced. The gap itself is reported as a worry, not fixed here - the file is
   not owned by this lane.
2. The decision content is final either way. Nothing in ADR-0002 is still being
   argued; only the status line is in question.

## Exact proposed change

1. In `company/adr/ADR-0002-content-based-freshness.md`, replace
   `Status: proposed` with `Status: accepted`, and delete the italic
   born-proposed note directly under it (it exists only to explain the proposed
   status and reads wrong once accepted).
2. In `company/adr/README.md`, bump `Next free number: ADR-0002` to
   `Next free number: ADR-0003` and append the index row:

```
| ADR-0002 | Freshness is content, not history position | accepted | `.claude/hooks/_common.py`, `company/state/gates.status` |
```

`company/adr/README.md` is outside this lane's owned paths, which is the second
reason this is a CR rather than a commit.

## Blast radius

Documentation and one status line. No code path reads either file. The
`tests/hooks/test_state_kernel.py` ADR test is written to pass in BOTH states:
it asserts the status line is exactly one of the mechanical forms and that,
while the ADR is `proposed`, this CR exists requesting acceptance. So the flip
does not turn any gate red, and neither does leaving it proposed.

## Owner sign-off needed?

No. It is a status transition on a decision the owner's own program already
directed (FR-HP-05, FR-HP-06), applied by the CEO under ADR-0001's lifecycle.

## Workaround if rejected

ADR-0002 stays `proposed`, which is honest: the freshness change ships, and its
architecture decision is on the record as argued but not yet adopted. The cost
is that `company/adr/` no longer reflects a settled decision that IS settled in
code, so the next lane touching `work_hash` has no binding record to read.

---
_CEO decision and remarks: pending._
