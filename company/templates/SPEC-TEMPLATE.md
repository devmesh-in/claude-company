# SPEC: <feature name>

_Type: feature | program-module. Author: product-manager. Date: YYYY-MM-DD._
_Status: DRAFT | SPEC-READY | SHIPPED (move to company/specs/shipped/ when shipped)._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

## Part 1 - Product requirements

### Problem
What hurts, for whom, and what it costs today. No solutions here.

### Goal and success metrics
The observable outcome that means this worked. Binary where possible.

### Users and personas
Who touches this, with their permissions posture.

### User stories and acceptance criteria
US-XX-1: As a <persona>, I can <action>, so that <value>.
  - AC: given/when/then, concrete enough to test.

### Functional requirements
Stable IDs. Every FR is later implemented, tested, or explicitly deferred - the
traceability gate checks these IDs against the PR.

- FR-XX-01: ...
- FR-XX-02: ...

### Business rules and validations
- BR-XX-01: ... (server-side; client mirrors are UX only)

### Scope
**In:** ...
**Out:** ... (be explicit - out-of-scope lines prevent helpful expansion)

### UX notes
Flows, states (loading/empty/error/ready), microcopy intent.

## Part 2 - Build readiness (the bridge from PRD to buildable)

If a line below cannot be filled, the spec is not ready. That is the point of
Phase 0: caught before any build tokens are spent.

- **Owned directories:** which dirs the build will create/modify, per workstream.
- **Invariants in play:** which project invariants this touches.
- **Frozen surfaces touched:** which, and the CR(s) needed before build.
- **Data model impact:** tables/columns/migrations, forward-only.
- **Contracts impact:** new enums/DTOs/transitions (additive? breaking?).
- **Open questions and chosen fallbacks:**
  - OQ-XX-01: <question>. FALLBACK: <the single decided default every agent
    implements, tagged `// OQ-XX-01 assumption` in code>. Owner answers later.
- **Verification plan:** how each FR will be proven (test, e2e slice, screenshot).

## Spec-ready checklist (the Phase 0 gate)

- [ ] Every FR has a stable ID and at least one acceptance criterion
- [ ] Out-of-scope is explicit
- [ ] Every open question has a single decided fallback
- [ ] Owned directories are named and disjoint from other in-flight work
- [ ] Frozen-surface needs are identified and CRs filed
- [ ] Data/contract impact stated (or "none")
- [ ] Verification plan covers every FR

## Part 3 - Brief handoff

Derive the brief(s) with `company/templates/BRIEF-TEMPLATE.md`. The brief links
this spec; it does not embed it.
