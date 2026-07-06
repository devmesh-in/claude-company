# How it works

This page explains the method behind claude-company: why it is shaped like a company, what the gates check, and how the pieces keep each other honest. Read it when you want to understand the system well enough to explain it to someone else.

## The core idea

AI agents are capable builders and unreliable narrators. Left alone, an agent under pressure will report failing work as done, widen its own scope, and edit tests until they pass. Process documents help, but an instruction is something the model can skip.

claude-company treats that as an engineering problem, not a prompting problem. The rules that matter are enforced by hooks: scripts that run before every file edit and shell command, and block the ones that break the rules. The prose explains the why; the hook supplies the no.

## Why a company

The structure copies what makes real engineering organizations work at scale: separated roles with separated incentives.

- **Thinkers and builders are different agents.** The product manager and architect explore options and write plans. Developers build. A builder never quietly redefines the plan, because it never owns the plan.
- **Producers never grade their own work.** Developers report with evidence. Tech leads verify their developers. QA captures screenshots but does not judge them. The CEO judges, and an independent auditor rechecks the big merges. Each layer catches what the layer below was too close to see.
- **Everyone owns their own directories.** Work orders name the exact directories an agent may touch. Two agents never share one directory, so parallel work cannot collide.

The hierarchy stays shallow on purpose: the CEO, then tech leads, then their developers and QA. Deeper pyramids add token cost and lose information at every handoff.

## The paperwork, and who reads what

The company runs on a few typed documents rather than long conversations:

- **Spec**: what to build and how you will know it works. Written by the product manager, with numbered requirements (FR-01, FR-02) that thread through everything downstream. Records the options that were considered and rejected.
- **Brief**: a sealed work order derived from the spec. Names the mission, the owned directories, the definition of done, and a decided fallback for every ambiguity. The builder reads the brief, never the spec, so its context stays small and its instructions stay exact.
- **Report**: what an agent hands back. Facts only: the diff, the gate output, the screenshots, the deviations.
- **Options memo**: the output of brainstorming. Numbered ideas with reasoning, risks, and trade-offs, a scored recommendation, and the strongest rejected option.

Ambiguity is handled once, in writing. Every open question in a spec gets one decided fallback, so ten parallel agents make the same assumption instead of ten different ones. Questions only a human should answer wait for you in `company/state/DECISIONS.md` while the build proceeds on the fallback.

## The gates

A gate is a command that must exit successfully: your test suite, your linter, your build. Gates live in `company/gates.config`, and `company/run-gates.sh` runs the ladder and stamps the result with a fingerprint of your working tree.

The stamp is what gives gates teeth. The commit hook checks three things: the stamp exists, every gate passed, and the fingerprint still matches your files. Change one file after the gates ran and the stamp goes stale, so "it passed earlier" stops counting. Nobody, including the CEO, can commit past a red or stale stamp.

Two habits keep gates meaningful:

- **Test the negative space.** Where a table lists allowed actions, generate the complement and assert every non-listed action is rejected. Positive-only tests pass while a system silently allows everything.
- **Never trust a worktree's numbers.** Agents build in isolated git worktrees, where stale artifacts can mask integration failures. Verification reruns gates on the integrated result.

## Protected files

Some files hold the whole system up: database migrations that already shipped, the schema, lockfiles, anything with exactly one legitimate writer. These are listed in `company/frozen-surfaces.json`, and the hook blocks every edit to them.

When an agent genuinely needs a protected file changed, it files a change request instead: what, why, the exact proposed change, and the blast radius. The CEO decides, applies approved changes in a dedicated gated commit, and the requesting agent rebases. The paperwork is the point: every change to a shared surface becomes visible and reviewed instead of silent.

## What the owner keeps

The escalation list is short and absolute. No agent decides production deploys, production schema changes, anything involving money, the weakening of any protection, scope beyond a brief, or business policy. One more rule catches design problems early: a gate that fails twice on the same cause stops the work and surfaces to you, because repeated failure means the plan is wrong, not the agent.

## Watching it enforce

Every hook block and every hotfix bypass appends one line to `company/state/adherence.log`. The log is the difference between a system that claims discipline and one that demonstrates it. Repeated blocks on the same agent or file are a signal worth reading: the work order was vague, or the design is fighting the rules.
