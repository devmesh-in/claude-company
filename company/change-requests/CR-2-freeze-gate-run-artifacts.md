# CR-2: freeze-gate-run-artifacts and repair CR-UPD-1

_Requesting agent/task: tech-lead, task hp-runner (spec
company/specs/spec-harness-port.md, tracking issue #97). Date: 2026-08-13._
_Status: PROPOSED_

## Frozen surface affected

`company/frozen-surfaces.json` - the `always` list. New entries:

- `company/state/gates.log`
- `company/state/gate-output/**`

The same two patterns are also added to `guard_frozen.ALWAYS_DEFAULTS` and to
this repo's `.gitignore`. See "Exact proposed change" - all three landing spots
are part of this request, because the registry alone protects nobody who is
already installed.

This CR ALSO repairs CR-UPD-1, which landed only half of itself. Two further
patterns are added to `guard_frozen.ALWAYS_DEFAULTS`:

- `company/state/install-manifest.json`
- `company/state/.update-backups/**`

Both are already in the registry `always` list and neither was ever mirrored
into the hardcoded baseline, so both have been unprotected on every existing
install since CR-UPD-1 landed. Verified present in the registry and absent
from `ALWAYS_DEFAULTS` at base commit `55cf436`.

One more `.gitignore` line is added, needing no registry entry because it is
already on the always-list: `company/state/gates.status`. The stamp is
machine-written single-writer evidence for exactly the reasons above and is
committable today.

## Why (cite the requirement)

FR-HP-22 creates `company/state/gates.log`: one appended line per ladder run,
written ONLY by `company/run-gates.sh`. FR-HP-21 creates
`company/state/gate-output/<gate>.log`: the full combined stdout and stderr of
each gate, replaced every run, written ONLY by the runner. FR-HP-23 requires
both to be frozen and ignored.

These are machine-written run records. An agent that hand-edits either one
forges the evidence the company uses to answer "did the ladder actually run and
where did the time go". That is the same guarantee already given to
`company/state/gates.status`, `adherence.log`, `costs.log` and
`provenance-ledger.json`, and it is the same reasoning CR-UPD-1 used for the
install manifest: single-writer machine state is frozen so the record cannot be
edited into agreement with a claim.

`gate-output/<gate>.log` additionally carries the failing output a red gate is
judged on. A hand-edited gate log is a doctored failure report.

## Exact proposed change

1. In `company/frozen-surfaces.json`, append to the `always` array:

```json
"company/state/gates.log",
"company/state/gate-output/**"
```

2. In `.claude/hooks/guard_frozen.py`, append the same two patterns to
   `ALWAYS_DEFAULTS`:

```python
    "company/state/gates.log",
    "company/state/gate-output/**",
```

3. In `.gitignore`, add:

```gitignore
company/state/gates.status
company/state/gates.log
company/state/gate-output/
```

4. CR-UPD-1 repair - in `.claude/hooks/guard_frozen.py`, also append to
   `ALWAYS_DEFAULTS`:

```python
    "company/state/install-manifest.json",
    "company/state/.update-backups/**",
```

5. A test pinning the two copies of the baseline together, so this class of
   half-landing cannot recur:
   `tests/hooks/test_gate_runner.py::FrozenBaselineAgreement` asserts the
   registry `always` list and `guard_frozen.ALWAYS_DEFAULTS` are the same set,
   in both directions, with a failure message naming the drifted patterns.

All three are required. `install.sh` uses `copy_if_absent` and `update.sh`
restores `frozen-surfaces.json` only when it is absent, so the JSON `always`
list reaches FRESH installs only - the hardcoded `ALWAYS_DEFAULTS` is what
reaches an EXISTING install on update. The reference implementation this work
ports from did the registry entry and omitted the gitignore, and its run log is
committable today.

## Blast radius

`guard_frozen.py` reads the registry per edit, so entries 1 and 2 are
pattern-only: no call-site changes anywhere. The runner writes both paths
through the filesystem from bash, not through the Edit or Write tools, so
`guard_frozen` does not intercept its own writer - the same seam
`gate_stamp.py` already uses for `gates.status`.

Workstreams affected: none in flight touch `company/state/`. L3 (this lane)
owns all three files. L1 (hp-kernel) and L2 (hp-guards) are directory-disjoint
from every path above. L6 (wave 2) documents the behavior but changes no
registry entry.

Gates re-run: the two real suites for this repo,
`python3 -m unittest discover -s tests/hooks -q` and `npm test`. The pack
manifest test in `npm test` covers `company/frozen-surfaces.json` and
`.claude/hooks/*.py`, both already shipped, so the packaged file list does not
change.

## Owner sign-off needed?

No. Additive protection of two new machine-written state files. It weakens no
existing guarantee, changes no invariant, and matches the CR-UPD-1 precedent
directly. CEO approval is still a merge condition for this lane per FR-HP-27.

## Workaround if rejected

The lane ships FR-HP-21 and FR-HP-22 without the freeze. The runner still works
and still writes both files, but they become hand-editable by any agent and, if
the `.gitignore` entry is also rejected, committable - so a red run could be
edited to read green after the fact and then committed as history. There is no
partial version worth taking: the registry entry without the `ALWAYS_DEFAULTS`
entry protects zero existing installs, and either without the `.gitignore`
entry leaves the run log in `git status` and eventually in a commit.

---
_CEO decision and remarks:_

**APPROVED 2026-08-13.** Additive protection of two new single-writer machine
records, weakening no existing guarantee, on the CR-UPD-1 precedent. The
all-three-landing-spots argument is the right one and is the reason this CR
matters more than it looks: a registry entry alone protects nobody who is
already installed.

Two remarks recorded rather than actioned here:

1. **Application reconciled deliberately.** ORCHESTRATOR step 7 says the CEO
   applies approved CRs to frozen surfaces itself, in a dedicated PR. This lane
   applied it in-branch because ITS BRIEF granted it
   `company/frozen-surfaces.json` outright. That was my briefing choice and the
   lane followed the brief correctly, so the work stands as committed. The
   defect is mine: a brief should not hand a lane a frozen surface and then
   rely on doctrine to say the CEO owns changes to it. Folded to L6 as a
   doctrine reconciliation - either briefs stop granting frozen files, or the
   ORCHESTRATOR rule gains an explicit brief-grant exception. Do not treat this
   remark as precedent until L6 lands.

2. **CR-UPD-1 is half-landed and this CR proves it.** Verified at base commit
   55cf436: `company/state/install-manifest.json` and
   `company/state/.update-backups/**` are in the registry `always` list but
   ABSENT from `guard_frozen.ALWAYS_DEFAULTS`. By exactly the reasoning this CR
   rests on, both are unprotected on every existing install whose
   `frozen-surfaces.json` predates them. That is a live defect on main, one
   release old, and it is out of scope for this lane. Recorded as a P1 worry
   and owed its own CR.
