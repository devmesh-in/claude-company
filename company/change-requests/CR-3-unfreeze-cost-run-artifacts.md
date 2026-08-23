# CR-3: unfreeze-cost-run-artifacts (supersedes part of CR-2)

_Requesting agent/task: CEO, task cost-ledger-removal (tracking issue #134).
Date: 2026-08-23._
_Status: APPLIED_

## Frozen surface affected

`company/frozen-surfaces.json` - the `always` list. Two entries REMOVED:

- `company/state/costs.log`
- `company/state/.cost-cursor.json`

The same two patterns are removed from `guard_frozen.ALWAYS_DEFAULTS`, because
`tests/hooks/test_gate_runner.py::FrozenBaselineAgreement` pins the registry
list and the hardcoded baseline set-equal in both directions. Removing one
without the other is a red gate by construction - which is the CR-2 mechanism
working as designed.

## Why (cite the requirement)

Owner decision 2026-08-23, tracked as #134: remove the cost ledger outright.

The freeze rationale in CR-2 was "single-writer machine state is frozen so the
record cannot be edited into agreement with a claim". That rationale is
conditional on a writer existing. `.claude/hooks/cost_capture.py` is the sole
writer of both paths and is deleted by this task. A frozen pattern protecting a
file that nothing produces protects nothing; it only leaves a live registry
entry citing a hook that is gone, which is precisely the dangling-reference
drift class that DECISIONS #20 and the `stop_gate` cleanup were about.

This is the narrow, load-bearing question for this CR: **does removing these
two patterns weaken any guarantee that still has a subject?** It does not. The
other five `company/state/` freezes - `gates.status`, `adherence.log`,
`provenance-ledger.json`, `install-manifest.json`, `.update-backups/**` - all
keep live single writers and are untouched.

## Exact proposed change

1. In `company/frozen-surfaces.json`, delete from the `always` array:

```json
"company/state/costs.log",
"company/state/.cost-cursor.json",
```

2. In `.claude/hooks/guard_frozen.py`, delete from `ALWAYS_DEFAULTS`:

```python
    "company/state/costs.log",
    "company/state/.cost-cursor.json",
```

3. In `.gitignore`, delete the two matching ignore lines. The files are local
   run artifacts of a hook that no longer exists; leaving ignore rules for
   paths nothing writes is dead configuration.

4. No change to `FrozenBaselineAgreement`. It is the gate that proves 1 and 2
   landed together, and it must stay green without modification. If that test
   needs editing to pass, this change is wrong.

## Blast radius

`guard_frozen.py` reads the registry per edit, so this is pattern-only: no call
sites change. After application, `company/state/costs.log` and
`company/state/.cost-cursor.json` become ordinary editable paths - acceptable,
because nothing writes them and the task deletes the existing local copies.

Workstreams affected: `arm-risk-band` is in flight and touches
`guard_provenance.py` and its tests. It is file-disjoint from `guard_frozen.py`,
`frozen-surfaces.json` and `.gitignore`. No rebase needed.

Gates re-run: all five suites. `tests/hooks` carries both
`FrozenBaselineAgreement` and the `EXPECTED_WIRING` assertion, and `npm test`
carries the pack manifest, which lists `company/` and `.claude/hooks/*.py` as
directories rather than files, so the packaged file list shrinks by one entry
without a manifest change.

## Owner sign-off needed?

No, beyond the direction already given. Removing the ledger is itself the
owner's decision (#134); this CR only unwinds the protection that existed to
serve it. It weakens no guarantee with a live subject and changes no invariant.

## Workaround if rejected

The task ships the hook deletion and leaves both patterns frozen. The result is
a registry entry and a hardcoded baseline entry protecting two paths that
nothing writes, and a `/standup` that no longer reads them - dead protection
plus a dangling reference. There is no partial version worth taking: removing
either copy alone turns `FrozenBaselineAgreement` red.

---
_CEO decision and remarks:_

**APPROVED and APPLIED 2026-08-23.** Both landing spots moved together, which
`FrozenBaselineAgreement` then confirmed rather than merely permitted: the
registry `always` list and `guard_frozen.ALWAYS_DEFAULTS` are set-equal at 15
patterns with zero drift in either direction. `.gitignore` no longer carries
the two lines. The test was not touched.

Verification run after application:

- `python3 -m unittest discover -s tests/hooks -q` - 721 tests OK (743 before;
  the 22 removed are the deleted `test_cost_capture.py` cases)
- `python3 .claude/hooks/guard_models.py --check` - exit 0, wiring assertion
  green with the two `cost_capture.py` rows gone
- `python3 .claude/hooks/witness_check.py --check` - exit 0, 35 witnesses,
  W-002 removed through the CLI

One remark recorded rather than actioned. This CR removes protection; every CR
before it added some. The asymmetry is worth naming because the reasoning that
makes removal safe here - "the sole writer is gone, so the pattern has no
subject" - is narrow and must not be generalized into "unused-looking freezes
can be pruned". A freeze whose writer still exists protects against a writer
that has not misbehaved YET. The test that this CR passes and a future pruning
CR would fail is: name the writer, and show it deleted in the same change.
