# BRIEF: affected-suites

_Type: feature. Lead: direct-developer. Date: 2026-08-13. Issue: #121._

## Mission

A 15-line hook fix currently costs about 15 minutes of verification, because
every lane runs all five suites and usually twice. `tests/install/test_update.sh`
alone is over 600 seconds of installer-rollout tests that no hook change can
reach. Build the thing that answers "which suites can MY change break", so a
lane stops paying for coverage it cannot affect.

This is the only change in the current backlog that attacks the clock rather
than the ceremony around it.

## Why this is a script and not a sentence

Two prose rules have already failed, in opposite directions. "The two suites
that actually gate THIS repo" was wrong, and a lane shipped a red branch because
of it. "All five suites, always" is correct and costs 15 minutes a run. A third
sentence saying "run the tests that matter" would push a judgment call onto every
agent on every change, and they will either be conservative (no gain) or guess
wrong (worse than today).

Which suites a change can break is a FACT about this repo. Facts belong in code.

## Scope

1. **A command** that takes changed paths (or derives them from git) and prints
   the suites that must run. Put it where the other repo tooling lives.
2. **Derive the suite list from `.github/workflows/ci.yml`**, not from a
   hand-kept copy. A second list of the suites is exactly the drift the canon
   gate exists to catch, and it would be ironic to add one here.
3. **The mapping.** `.claude/hooks/**` needs the hooks suite. `install.sh`,
   `update.sh`, `lib/`, `bin/` need the CLI, installer and update suites.
   `company/run-gates.sh` needs the INSTALLER suite - that is the pairing that
   would have caught this morning's red branch, so make sure it is there.
   Doctrine and canon files need the canon gate.
4. **Always include the hooks suite**, whatever changed. It is the cheapest one
   and it is the oracle for the rest.
5. **Wire it into `company/templates/BRIEF-TEMPLATE.md`** as ONE line in the
   DoD, replacing the current all-five instruction.

## Definition of Done

- [ ] A hooks-only change asks for hooks plus `npm test`, and NOT the update
      suite
- [ ] A change to `company/run-gates.sh` asks for the installer suite -
      demonstrate this one specifically, it is the regression that motivated it
- [ ] A change to `install.sh` asks for installer, update and CLI
- [ ] An unrecognised path asks for EVERYTHING. Unknown must fail safe: the
      cost of over-running is minutes, the cost of under-running is a red branch
- [ ] The suite list comes from `ci.yml`; adding a suite there without touching
      this tool must change its output. Prove it.
- [ ] BRIEF-TEMPLATE carries one line pointing at the command
- [ ] Suites for YOUR change: hooks, `npm test`, and the installer suite if you
      touch anything the installer copies

## Out of scope

- Test tiering (a smoke tier inside the suites). That is the other half of the
  clock problem and it is a separate, larger job.
- Changing what CI runs. CI keeps running everything across six platforms - it
  is the backstop, and scoping local verification is only safe because of it.
- Any hook. Three lanes are in flight under `.claude/hooks/`.

## Report back

What changed, the demonstrations above, what an unrecognised path does, and
1-3 witness candidates.
