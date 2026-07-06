---
name: autopilot
description: EXPERIMENTAL, opt-in only - one bounded tick of self-directed company operation (triage red gates, in-flight work, worries, CRs, then backlog; deliver; surface). Intended for the end phase of a product - backlog burn-down and polish after the main build exists - not for mainline development. Runs ONLY when the user types /autopilot (or wires it into /loop or /schedule themselves); never invoke this skill on your own initiative, and never treat phrases like "keep going" as an invocation.
disable-model-invocation: true
---

# /autopilot - one tick of the standing loop (EXPERIMENTAL)

This is an experimental, explicitly-invoked mode. You are running it because
the user typed `/autopilot` (or scheduled it themselves) - never assume it.
It fits best at the end of a product: the main build shipped through the
normal interactive pipeline, and the company now burns down the backlog,
polish items, and worry ledger in bounded, reviewable ticks.

You are the CEO running one bounded tick. `company/LOOPS.md` is the
doctrine; read it, then `ORCHESTRATOR.md` if this session has not loaded the
role yet. Optional argument focuses the tick: $ARGUMENTS

## Caps for this tick (declare before acting, honor absolutely)

- Engagements started or advanced: at most 2 (at most 1 if running
  unattended under a schedule).
- Attempts per failing cause: 2. The second identical failure stops the
  tick and surfaces - it is a design problem.
- Class ceiling: quick and feature only. Programs, hotfixes, and anything
  on the owner-escalation list are surfaced, never started, when nobody is
  watching.
- If you were invoked under /loop (dynamic pacing): after a productive tick
  schedule a short-interval wakeup; after an empty tick, a long one; after
  two empty ticks, stop scheduling and report idle.

## The tick, in order

1. **Read state** (RESUME first, then STATUS, WORRIES, DECISIONS,
   active-task.json, open CRs, `git worktree list`, `git log --oneline -10`).
   Create `company/state/BACKLOG.md` if it does not exist yet (owner wishes
   on top, company-discovered candidates below).
2. **Triage in fixed priority order** - the first hit wins:
   1. Gates red on main -> that is the engagement. Fix the cause through
      the pipeline.
   2. In-flight task stalled or finished-but-unintegrated -> unblock,
      verify, integrate it.
   3. WORRIES P0/P1 rows -> run the worry down (investigate; graduate it to
      a fix, a CR, or a STATUS risk).
   4. Open CRs awaiting arbitration -> decide them (owner-escalation CRs
      get surfaced instead).
   5. Top of `company/state/BACKLOG.md` -> classify it (ideation items get
      an options memo prepared for the owner rather than a build, when
      unattended) and run it through the normal pipeline.
3. **Execute through the normal machinery.** Nothing about the loop relaxes
   the method: specs for features, sealed briefs, tech-lead teams, QA
   evidence, gates, verify-never-trust. The hooks apply to you.
4. **Record.** Update RESUME (done / next), STATUS (red stays red), WORRIES
   (add what you noticed, graduate what you resolved), BACKLOG (pull what
   you took, append what triage discovered).
5. **Report the tick** in one screen: what this tick did, evidence summary,
   what the next tick should do first, decisions waiting on the owner, caps
   consumed. If nothing was actionable, say "idle tick" and why in one line.

## Stop-and-surface (end the tick early, always with a report)

Owner-escalation item hit; same cause failed twice; caps consumed; a hook
block you cannot self-serve; or nothing actionable for the second
consecutive tick. Surfacing beats pushing through - the loop's job is to
make the owner's next decision cheap, not to avoid needing one.
