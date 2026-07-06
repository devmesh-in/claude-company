---
name: onboard
description: Adopt claude-company into an EXISTING codebase (brownfield) - audit the repo to recover its architecture and tribal conventions, discover the real test/lint/build commands, propose frozen surfaces from what is actually load-bearing, and generate the company canon from evidence rather than imposing greenfield docs. Use when the user says /onboard, or asks to "set up claude-company / the company system" in a repo that already has code. For an empty repo use company-init instead.
---

# /onboard - adopt an existing codebase

The company adapts to the codebase, not the other way around. Everything you
generate must come from evidence in the repo; where you infer, say so and mark
confidence. Do the steps in order.

## 1. Verify the drop-in

Confirm `company/METHOD.md` and `.claude/hooks/` exist (installer ran). If
not, stop and point the user at `install.sh`.

## 2. Audit the repo (dispatch Explore agents in parallel)

1. **Architecture recovery**: languages, frameworks, entry points, module map,
   data stores, external services, how the pieces talk. Output: a one-page
   architecture map with file paths.
2. **Conventions mining**: the unusual, opinionated, tribal things - naming
   quirks, error-handling patterns, forbidden practices visible in the code,
   comment conventions, directory meanings. The generic stuff (indentation)
   is noise; the tribal stuff prevents agent drift.
3. **Machinery discovery**: the REAL commands - test, lint, typecheck, build,
   dev-run, migrate, seed - from package scripts, Makefiles, CI configs.
   Verify each actually runs (or note why not).
4. **Load-bearing surfaces**: single-writer choke points, state machines,
   money/ledger code, auth seams, shipped migrations, generated code - the
   candidates for freezing.

## 3. Generate the canon (you, as CEO, from the audit)

- `CLAUDE.md`: create or extend (never clobber - add sections) with the
  architecture map, tribal conventions, and invariants you found stated as
  invariants only if the code actually enforces or clearly intends them.
- `company/gates.config`: the verified real commands, cheap-to-expensive. A
  command that does not currently pass goes in commented/annotated with its
  status - never wire a red gate in silently.
- `company/frozen-surfaces.json`: the load-bearing candidates, each with why.
  Present to the owner for approval BEFORE writing - freezing is a policy
  decision, not an inference.
- `company/state/RESUME.md` "facts every spawn prompt needs": the machinery
  commands, ports, seed behavior, quirks that would burn an agent.

## 4. Report and hand off

Present the owner: what you found, what you generated, the proposed frozen
surfaces (approve/edit), current gate status (which are green today - run
them), and the top 3 risks you would put in WORRIES.md. Apply their answers,
update STATUS/RESUME, and tell them `/orchestrator` is ready for its first
task.
