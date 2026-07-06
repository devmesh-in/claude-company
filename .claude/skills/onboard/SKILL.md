---
name: onboard
description: Adopt claude-company into an EXISTING codebase autonomously - audit the repo, recover architecture and tribal conventions, auto-wire the real test/lint/build commands as gates, apply opinionated frozen-surface defaults, and generate the canon from evidence. Zero owner interviews; the owner gets a findings memo with veto rights. Use when the user says /onboard or asks to set up claude-company in a repo that already has code. Note - /orchestrator self-initializes too; this skill is the explicit, thorough version.
---

# /onboard - adopt an existing codebase (autonomous)

The company adapts to the codebase, not the other way around - and it does the
adapting itself. Everything generated must come from evidence in the repo;
where you infer, mark confidence. Ask the owner nothing; report findings with
veto rights at the end.

## 0. Verify the drop-in

`company/METHOD.md` and `.claude/hooks/` must exist (installer ran).

## 1. Audit (Explore agents, parallel)

1. **Architecture recovery**: languages, frameworks, entry points, module
   map, data stores, external services, how pieces talk. One page, with paths.
2. **Conventions mining**: the unusual, opinionated, tribal things that
   prevent agent drift - naming quirks, error-handling patterns, forbidden
   practices visible in code. Skip the generic.
3. **Machinery discovery**: real test/lint/typecheck/build/dev/migrate/seed
   commands from scripts, Makefiles, CI configs - verified runnable.
4. **Load-bearing surfaces**: single writers, state machines, money/ledgers,
   auth seams, shipped migrations, generated code.

## 2. Wire it (you, from evidence, no approval gates)

- **Gates**: `python3 .claude/hooks/gates_detect.py --write`, then reconcile
  with the audit's findings (CI configs often know gates detection cannot
  see). Run `bash company/run-gates.sh` and record the honest result - gates
  that are red TODAY go into STATUS as the existing-debt baseline, not
  silently into the config as passing.
- **Frozen surfaces**: apply the opinionated defaults (shipped migrations,
  schema files, generated code, anything with exactly one writer) to
  `company/frozen-surfaces.json` with a why per entry. Freezing is
  reversible by the owner in one veto; do not block on pre-approval.
- **Canon**: create or extend `CLAUDE.md` (add sections, never clobber) with
  the architecture map, tribal conventions, and only the invariants the code
  actually enforces or clearly intends.
- **Spawn facts**: machinery commands, ports, seed behavior, quirks that
  would burn an agent - into `company/state/RESUME.md`.
- Seed `company/state/WORRIES.md` with the top risks the audit surfaced.

## 3. The findings memo (owner-facing, one screen)

What the company found, what it wired (gates and their current colors,
frozen surfaces and why), what it flagged (worries, debt baseline), and the
standing offer: "veto any of this by saying so; otherwise /orchestrator is
open for business." No questions, no tasks assigned to the owner.
