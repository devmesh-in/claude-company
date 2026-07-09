# Architecture Decision Records

This directory holds the project's architecture decision records (ADRs): the
durable log of load-bearing structural choices and why each was made. An ADR
answers "how is this built and why", so a decision outlives the conversation
that produced it and no one relitigates a settled question from memory. Specs
say what to build; ADRs say how the structure holds together. Write one with
`company/templates/ADR-TEMPLATE.md`.

## Index

Next free number: ADR-0002. Numbers are zero-padded (ADR-0001) and never
reused, even after an ADR is superseded.

| ID | Title | Status | Scope |
|---|---|---|---|
| ADR-0001 | Adopt architecture decision records | accepted | `company/adr/` |

## Lifecycle

- **Propose.** The architect writes an ADR (`Status: proposed`) for any
  boundary-shaping decision during Phase 0 or program planning. Proposed ADRs
  are editable while the argument is live.
- **Accept.** The CEO adopts it by setting `Status: accepted`. That is the only
  moment the status line is allowed to become the literal `Status: accepted`.
- **Immutable once accepted.** A guard blocks Edit and Write on any ADR whose
  status is `accepted`. You do not amend an accepted ADR - you supersede it.
- **Supersede, never overwrite.** A changed decision gets a NEW ADR that names
  what it replaces in its `Supersedes` field; the superseded ADR's status flips
  to `superseded-by-ADR-NNN`.
- **Status flips are CEO-applied via CR.** Because accepted ADRs are frozen,
  changing a status (accept, or mark superseded) goes through
  `company/change-requests/`, applied by the CEO - never a local edit.
- **Never deleted.** ADRs are append-only history. A wrong decision is recorded,
  then superseded; it is not erased.

## Precedence

An accepted ADR wins on architecture (how); the spec wins on scope (what). A
brief that contradicts an accepted ADR inside that ADR's scope is a briefing
error. A builder who notices the conflict files a CR and does not pick a
winner. See `company/METHOD.md` (frozen surfaces and change requests) for where
this rule sits in the method.
