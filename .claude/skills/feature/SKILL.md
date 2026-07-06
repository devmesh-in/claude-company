---
name: feature
description: Run ONE feature through the company's full SDLC - spec (product-manager), spec-ready gate, sealed brief, tech-lead build with developers and QA screenshots, evidence verification, integration. Use when the user says /feature <description>, or asks to build a specific feature "properly" / "through the process" in a claude-company project. For a batch of work or ongoing operation, use /orchestrator; for tiny fixes just classify quick there.
---

# /feature - one feature, full SDLC

You are the CEO for the duration of this feature. If you have not already
loaded the role this session, read `ORCHESTRATOR.md` first, then
`company/state/RESUME.md` and `STATUS.md`.

The feature request: $ARGUMENTS

Run the pipeline, gate by gate. Do not skip a step because the feature looks
easy - if it is genuinely `quick`-class (small bug/copy/config), say so and
route it as quick instead of forcing ceremony.

1. **Spec (Phase 0).** Dispatch **product-manager** with the request and any
   context from this session. Hold the result to the spec-ready checklist; if
   a line cannot be filled, send it back or get the owner's answer. Surface
   the OQ register to the owner now if any OQ is business-policy.
2. **Brief.** Derive the sealed brief from the spec
   (`company/templates/BRIEF-TEMPLATE.md`): owned dirs, invariants, frozen
   surfaces nearby, ordered scope, DoD, fallback per ambiguity, out-of-scope.
   Write it to `company/briefs/`, set `company/state/active-task.json`
   (`type: "feature"`, `brief: <path>`, `test_scope` as appropriate).
3. **Build.** Spawn one **tech-lead** in a worktree
   (`git worktree add .claude/worktrees/<slug> -b task/<slug>`) with the spawn
   skeleton from ORCHESTRATOR.md. The lead runs its own developers, fills
   gaps, and drives its qa-engineer for loaded/empty/error/after-action
   screenshots.
4. **Verify.** Never accept the report as done: re-run
   `bash company/run-gates.sh`, diff-check ownership against the brief,
   spot-read 2-3 FRs, hand-exercise one unhappy path, judge the screenshots
   against the acceptance criteria yourself. Findings under an hour: fix and
   note. Bigger: back to the lead with precise findings.
5. **Integrate.** Merge in dependency order, clear active-task.json, remove
   the worktree, archive spec + brief to `shipped/`, dispatch docs-librarian
   if docs are affected.
6. **Record and report.** Update STATUS/RESUME/WORRIES; report to the owner:
   what shipped, evidence summary, CRs decided, anything needing an owner
   decision.
