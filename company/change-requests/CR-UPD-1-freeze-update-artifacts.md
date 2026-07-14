# CR-UPD-1: freeze-update-artifacts

_Requesting agent/task: product-manager, task cli-update (spec company/specs/spec-cli-update.md). Date: 2026-07-15._
_Status: APPROVED_

## Frozen surface affected

`company/frozen-surfaces.json` - the `always` list. New entries:

- `company/state/install-manifest.json`
- `company/state/.update-backups/**`

## Why (cite the requirement)

FR-UPD-02 / FR-UPD-10: the install manifest is a machine-written provenance
baseline - only `install` and `update` may write it. FR-UPD-09: the backup tree
holds pre-update file content for rollback. An agent hand-editing either
corrupts provenance or destroys the rollback path. This matches how
`gates.status` and `provenance-ledger.json` are already frozen.

## Exact proposed change

In `company/frozen-surfaces.json`, append to the `always` array:

```json
"company/state/install-manifest.json",
"company/state/.update-backups/**"
```

## Blast radius

`guard_frozen.py` reads the registry per edit - no code change, pattern-only.
The cli-update workstream itself must not Edit/Write these paths from agent
tools (the engine writes them via bash, which guard_frozen does not intercept -
that is the intended seam). No other workstream is in flight. Gates re-run in
the build PR.

## Owner sign-off needed?

No - additive protection of new machine-written state files; weakens no
guarantee.

## Workaround if rejected

Ship without freezing; the manifest self-heals on the next update (rewritten
from packaged hashes), but hand edits between updates could silently flip a
modified file to "pristine" and let update clobber it. Freezing is the safe
default.

---
_CEO decision and remarks: APPROVED 2026-07-15 - additive, matches existing
precedent for machine-written state. CEO applies the registry edit in the build
PR per standing rule (frozen surfaces change only via CR, applied by the CEO).
Tracking issue #56._
