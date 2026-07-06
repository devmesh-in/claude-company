---
name: company-init
description: Bootstrap claude-company in a NEW (greenfield) project - interview the owner about what they are building, dispatch the product-manager and architect to produce the founding spec, ownership map, frozen-surface registry, and gate ladder, and fill in the company state files. Use when the user says /company-init, asks to "set up the company" or "initialize claude-company" in a fresh or nearly-empty repo. For an existing codebase use the onboard skill instead.
---

# /company-init - found the company (greenfield)

You are founding this project's AI software company. The output is a project
where `/orchestrator` can immediately run real work. Do the steps in order.

## 1. Verify the drop-in

Confirm `company/METHOD.md`, `ORCHESTRATOR.md`, `.claude/agents/`, and
`.claude/hooks/` exist (the installer put them there). If not, stop and tell
the user to run `install.sh` from the claude-company repo first.

## 2. Interview the owner (AskUserQuestion, two rounds max)

Round 1 - the product: what are we building, for whom, what is the v1 that
would make them happy, what is explicitly NOT v1.
Round 2 - the ground rules: tech stack preference (or "architect decides"),
what counts as money/sensitive surfaces in this domain, deploy target, and
any hard constraints (compliance, offline, performance).

## 3. Phase 0 and structure (dispatch, in order)

1. **product-manager** agent: produce the founding spec in `company/specs/`
   from the interview - v1 scope with FR/BR IDs, OQ register with fallbacks,
   spec-ready checklist walked honestly.
2. **architect** agent: from that spec, produce the narrow waist design,
   ownership map, wave plan with hard exit criteria, proposed
   `company/frozen-surfaces.json` surfaces, and proposed `company/gates.config`
   gates (per `company/GATES.md`).
3. Review both yourself as CEO. Present the owner a one-screen summary and the
   decisions that are theirs (from the OQ register). Apply their answers to
   `company/state/DECISIONS.md`.

## 4. Wire the ground truth

- Write the architect's surfaces into `company/frozen-surfaces.json` and gates
  into `company/gates.config` (real commands; if the stack has no code yet,
  wire the commands the walking skeleton will satisfy, marked clearly).
- Fill `company/state/RESUME.md` section "Facts every spawn prompt needs":
  dev commands, ports, seed/reset behavior, conventions.
- Ensure the project `CLAUDE.md` exists with the claude-company block (the
  installer added it) plus the stack conventions the architect chose.
- Initialize git if needed; first commit: "found the company".

## 5. Hand off

Update `STATUS.md` (wave 0 pending) and `RESUME.md` (next actions: run wave 0
via /orchestrator). Tell the owner: the company is founded; `/orchestrator`
starts Wave 0 (narrow waist + walking skeleton) whenever they say go.
