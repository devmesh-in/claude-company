# ADR-0001: Adopt architecture decision records

Status: accepted
Date: 2026-07-09

## Context

claude-company decides where the walls go before parallel agents build, so the
system stays directory-disjoint and plug-and-play as it grows. Those structural
decisions - the narrow waist, single-writer surfaces, kernel extension points,
which paths are frozen - were carried in the architect's head and scattered
across specs and reports. Specs record what to build and expire when the feature
ships; they are the wrong home for a boundary decision that must bind every
future workstream. Without a durable record, a settled "how" gets relitigated
from memory, and a later brief can quietly contradict an earlier structural
choice with no mechanism to catch it.

## Decision

We adopt architecture decision records. Each load-bearing structural decision is
written as one ADR under `company/adr/`, using `company/templates/ADR-TEMPLATE.md`,
with a mechanical `Status` line (`proposed`, `accepted`, or
`superseded-by-ADR-NNN`). The architect proposes; the CEO accepts. An accepted
ADR is immutable and is changed only by superseding it with a new ADR; status
transitions are CEO-applied through the change-request protocol. ADRs are
append-only and never deleted. On architecture an accepted ADR wins; on scope
the spec wins; a brief that contradicts an accepted ADR is a briefing error and
a builder who notices files a CR rather than picking a winner.

## Consequences

- Structural decisions gain a durable, discoverable home, separate from the
  specs that expire and the reports that scroll away.
- Immutability is enforced, not asked for: a guard blocks Edit and Write on any
  ADR whose status line is the literal `Status: accepted`. Amending a settled
  decision is physically prevented; the only path forward is a superseding ADR.
- The precedence rule gives conflicts a single resolution - file a CR - so no
  builder resolves an architecture-versus-scope clash by judgment.
- The cost accepted: a small standing bureaucracy (propose, accept, supersede
  by CR, keep the index true) and the discipline never to write
  `Status: accepted` before a decision is truly final, because the file freezes
  the moment it is.

## Scope

- `company/adr/`

## Supersedes

none
