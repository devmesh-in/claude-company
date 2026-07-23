# BRIEF: release-0.2.3

_Type: quick. Spec: none (quick - release chore). Lead: CEO (self). Date: 2026-07-23._

## Mission

Prepare release v0.2.3 off current main: version bump 0.2.2 -> 0.2.3 so the
published package carries BOTH the model-routing arming (PR #77) and the
spawn-depth fix (PR #83). v0.2.2 was tagged pre-#83 and the owner directed the
jump to 0.2.3. Also archive the shipped spawn-depth brief and sync the boards.

## You own

- `package.json` (version line only)
- `company/state/*` boards, `company/briefs/` archival

## Definition of Done

- [ ] `python3 -m unittest discover -s tests/hooks -q` and `npm test` green
- [ ] Release PR merged; owner handed tag v0.2.3 + publish commands

## Out of scope

- Any code change; tag/publish (owner buttons).
