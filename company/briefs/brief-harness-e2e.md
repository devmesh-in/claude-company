# BRIEF: harness-e2e

_Type: feature. Spec: company/specs/spec-harness-agnostic.md (FR-HA ids) plus
live findings. Lead: direct-developer. Date: 2026-08-24._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Prove the opencode harness end to end against the REAL opencode binary
(1.18.21), fix what the run exposes, and ship the two capabilities the owner
called out: nested subagent dispatch (a tech-lead session must be able to
spawn its developer/qa-engineer crew - opencode defaults `subagent_depth` to
1, which silently strips the task tool from lead sessions) and background
subagents (`OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true` must be in the
process env before opencode starts; verified live that neither project config
nor a plugin can flip it after launch). Hard constraint: the Claude side does
not change behavior; verdicts stay identical across harnesses (BR-HA-03).

## Read first (in order)
1. `CLAUDE.md` (project canon)
2. `company/specs/spec-harness-agnostic.md` (the FR-HA contract)
3. `.opencode/MODULE.md`, `.opencode/plugin/company-harness.js`,
   `.opencode/lib/harness-core.js`, `lib/render-opencode.js`
4. `tests/harness/test_opencode.sh`, `tests/harness/test_install.sh`,
   `tests/harness/test_render.mjs`

## You own
- `lib/render-opencode.js` and the generated `.opencode/opencode.json`
- `install.sh` (opencode-harness block only), `update.sh` (detection parity)
- `tests/harness/*` (extend for new behavior)
- `docs/customizing.md` (opencode section)

## Invariants in play
- Default install (claude-only) must remain byte-identical in behavior: no
  .opencode output, no shell-profile writes.
- The adapter executes guards, never reimplements them (FR-HA-07).
- No-slop applies to every file touched.

## Scope (ordered)
1. Render `"subagent_depth": 2` into generated `.opencode/opencode.json`;
   re-render the repo tree so the drift gate stays green; pin it in
   tests/harness (renderer unit + real-binary assertion).
2. Install-time wiring of the background-subagents export into the user's
   shell rc when the opencode harness is selected: idempotent, marker-free
   (grep-guarded), opt-outable via `--no-background-subagents-env`, never
   fatal on failure. Update usage text.
3. Live E2E against real opencode in a scratch install: plugin loads, deny
   paths block, Task chains fire with parentID set, tech-lead spawns a
   developer (previously impossible), background task works with the flag,
   PostToolUse/Stop chains land.
4. Extend tests/harness for everything shipped; docs note both capabilities.

## Definition of Done
Universal DoD (every task) plus this task's specifics:
- [ ] All six suites green locally (hooks, CLI, installer, TUI, update, harness)
- [ ] A real opencode run shows a depth-1 session successfully spawning a
      company role (evidence in the task report)
- [ ] Fresh claude-only install unchanged; opencode install gains both fixes
