# ADR-NNN: <title>

Status: proposed | accepted | superseded-by-ADR-NNN
Date: YYYY-MM-DD

An architecture decision record captures one load-bearing structural decision -
where a wall goes, which surface is the single writer, how modules find each
other - and the reasoning behind it, so the choice survives after the context
that produced it is gone. One decision per ADR. Keep it terse; link the spec or
CR that drove it rather than restating them.

The `Status` line is mechanical. Use exactly one of the three forms above:
`proposed` while the architect is still arguing it, `accepted` once the CEO
adopts it, or `superseded-by-ADR-NNN` when a later ADR replaces it. A guard
matches the literal line `Status: accepted` and freezes the file: an accepted
ADR is immutable, so do not write that status until the decision is final.

## Context

The forces in play: the constraint, the coupling, the failure mode being
avoided. What made this a decision worth recording rather than an obvious call.
No solutions here.

## Decision

The choice, stated plainly and in the active voice: "We put X behind Y",
"Module Z is the single writer of W". One decision. If you are tempted to write
"and also", that is a second ADR.

## Consequences

What this makes easy and what it makes hard, including the enforcement that now
binds because of it (which gate, which guard, which test). Name the cost you are
accepting, not just the benefit.

## Scope

The repo paths this decision binds - bulleted, exact. Anything under these paths
must honor this ADR; a brief that contradicts it inside this scope is a briefing
error, not a builder's choice.

- `<dir>/` ...

## Supersedes

ADR-NNN, or "none". When this ADR supersedes an earlier one, the earlier ADR's
status flips to `superseded-by-ADR-<this>` (a CEO-applied status change via CR);
the old record is never deleted.
