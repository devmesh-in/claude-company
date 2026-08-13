# CR-2: freeze-gate-run-artifacts

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
company/state/gates.log
company/state/gate-output/
```

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
