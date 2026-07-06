---
name: cr
description: File or decide a change request against a frozen surface (schema, contracts, kernel, migrations, anything in company/frozen-surfaces.json). Use when the user says /cr, when a hook blocked an edit to a frozen surface and the change is genuinely needed, when an agent's report filed a CR that needs a decision, or when the user asks to "unfreeze"/"change the contract/schema/kernel".
---

# /cr - the change-request protocol

$ARGUMENTS tells you which mode you are in; if ambiguous, look at
`company/change-requests/` and infer (a named PROPOSED CR means decide mode).

## Mode A - file a CR

1. Copy `company/templates/CR-TEMPLATE.md` to
   `company/change-requests/CR-<n>-<slug>.md` (next free number is tracked in
   `company/state/STATUS.md`; bump it).
2. Fill every section honestly. The two that decide the CR's fate:
   - **Why (cite the requirement):** a CR without a concrete FR/BR/invariant
     citation is rejected by default.
   - **Exact proposed change:** the precise diff. No "something like".
3. Update STATUS.md's CR table. If the surface is on the owner-escalation
   list (money, invariants, prod schema, versioning), flag it for the owner
   in the report - the CEO cannot approve those alone.

## Mode B - decide a CR (CEO only)

Arbitrate by the standing criteria:

- **Approve when:** the cited requirement genuinely needs it; additive over
  breaking; blast radius stated and acceptable; no workstream-specific logic
  leaking into a shared surface.
- **Reject when:** convenience-driven; duplicates an existing surface;
  vocabulary invention; the workstream can meet its spec without it.

Write the decision and reasoning into the CR's footer, set Status, update
STATUS.md.

**If approved, apply it yourself** in a dedicated branch/PR that runs the full
gates - approved CRs to frozen surfaces are CEO-applied, never agent-applied.
Note: the `guard_frozen` hook blocks you too; the sanctioned path is to edit
`company/frozen-surfaces.json` ONLY as part of applying an approved CR (state
this in the commit message), make the change, run
`bash company/run-gates.sh`, then re-freeze. Set Status to APPLIED with the
commit hash, and tell affected agents (via their briefs' next update) to
rebase.
