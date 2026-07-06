# EXTENDING.md - The module contract

The invariant that keeps a system plug-and-play as it grows:

> **Adding a module never edits existing code.** It adds documentation, a
> contracts entry, schema additions, owned directories, and registrations.

If adding module N+1 would require editing the app shell, another module, or a
shared surface, the design is wrong or the change is a CR - stop.

## The narrow waist

Modules interact through a small, explicit set of shared surfaces and nothing
else. For most projects that means:

1. **The schema** - one source of truth for persistent shapes.
2. **The contracts** - enums, DTOs, and any state-machine tables encoded as
   data. Closed vocabularies come from contracts only; a string literal for a
   status or role fails review.
3. **The kernel** - the one service that owns cross-cutting mutations (state
   transitions, money movements, audit writes). A module that hand-rolls its
   own approve/return/transfer has failed review regardless of whether it works.

These surfaces are built first (Wave 0 of any program), then frozen: read-only
to module agents, changed only via CR, guarded by the `guard_frozen` hook and
listed in `company/frozen-surfaces.json`. Modules may REGISTER implementations
for extension points the kernel declares (guards, jobs, manifest entries); they
may not add transitions or edit the shell.

## The nine steps to add a module

1. **Specification first.** A module doc from `SPEC-TEMPLATE.md` with FR/BR/OQ
   IDs. No spec, no build.
2. **Agent brief.** Derived from the spec via `BRIEF-TEMPLATE.md`; sealed and
   self-contained.
3. **Canon deltas via CR.** Any needed schema/contracts/kernel change is filed
   and applied by the CEO in a dedicated gated PR before the module builds on it.
4. **Owned directories.** The module gets exactly its own directories (API side
   and UI side); the ownership map records them. Nothing else is writable.
5. **Registration, not modification.** The module plugs in via its manifest and
   self-registration. The shell discovers it.
6. **Non-negotiables apply.** Every mutation audited and authorized; server-side
   enforcement is the enforcement; locked data is read-only at the lowest layer
   you can enforce it.
7. **Seed the shared world.** All agents develop and test against one canonical
   seed. Seed changes are CEO-only PRs. No private fixtures for cross-module
   behavior.
8. **Gates.** The module's tests join the ladder; its slice extends the
   golden-path e2e via PR to the CEO.
9. **Documentation closure.** The module carries a one-page `MODULE.md`
   (`MODULE-TEMPLATE.md`) in each owned directory, created BEFORE coding and
   kept current. The docs-librarian syncs any canon the change touched.

## Wayfinding rule

An agent landing anywhere in the tree must be one file away from full context:
every owned directory carries its `MODULE.md` pointing at spec, brief,
contracts, owned routes, and seams.
