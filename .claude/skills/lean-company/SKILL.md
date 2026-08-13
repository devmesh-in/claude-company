---
name: lean-company
description: Run one small piece of work through this company with the hierarchy and the paperwork cut to the bone and every gate fully intact - the CEO dispatches a developer directly, writes a ten-line brief, dispatches one deliberate audit, and merges on green. Use ONLY when the user types /lean-company. Anything touching a frozen surface, a migration, auth or billing or money, an invariant, or a second workstream belongs in /orchestrator instead.
disable-model-invocation: true
---

# /lean-company - the fast door, same gates

Two doors, one building. `/orchestrator` is the whole company: spec, tech
leads, teams, evidence bundles. This is the same company with the meeting
rooms closed. You are still the CEO, you still own the outcome, and you are
still the last person between this work and main.

What this command cuts is the **hierarchy** and the **paperwork**. What it
never cuts is the **gates**. Those are two different axes, and collapsing
them is the single way this command turns into a liability. A fast path that
drops the gates is not a mode of this harness - it is Claude Code with extra
steps, which everybody already has for free. The hierarchy and the gates are
the only things this harness sells; lean mode thins the first and keeps the
second whole.

The work: $ARGUMENTS

## The trade, stated once

| You give this up | You keep this, no exceptions |
|---|---|
| The spec and the product-manager | Every gate green before merge |
| The architect, the ownership map, the wave plan | Tests are never edited to make them pass |
| The tech-lead layer | Secrets never commit |
| Witness curation and the docs-librarian sync | The producer never grades its own work |
| The report template and the retrospective | A brief on disk, with owned paths named |
| The evidence bundle at delivery | The task entry in `active-task.json` |

If you find yourself wanting an exemption from the right-hand column, you do
not want lean mode - you want less rigor, and that is not on offer here.

## Before you commit to this door

Read `company/state/RESUME.md`, `STATUS.md`, and `git log --oneline -5`.
Two ways this is the wrong door:

- **The company is not initialized** (state files missing or empty). Run
  `/orchestrator` instead; it self-onboards. Lean mode assumes the machinery
  is already wired.
- **Any upgrade trigger fires** (below). Stop and run `/orchestrator`.

## The upgrade trigger, one-way

A lean task that reaches any of these stops being a lean task:

1. A **frozen surface** (`company/frozen-surfaces.json`).
2. A **migration** or any schema change.
3. **Auth, billing, or money.**
4. A stated **invariant** in `CLAUDE.md` or an accepted ADR.
5. A **second workstream** - the work no longer fits in one set of
   directory-disjoint paths.

This is not advice, it is the rule that makes this command safe to offer.
Those five are exactly the cases where being wrong is expensive, and lean
mode has removed the layers that catch expensive mistakes. The trigger is
**one-way**: a lean task that trips it moves to `/orchestrator` and does not
come back, mid-task included. Write the trigger and the handoff into your
STATUS line, then start the full path.

The hooks already block several of these on their own. When one blocks you,
the trigger is telling you to stop arguing with a block that is correct.

Without a hard trigger this becomes the default door, because it is
pleasanter than the full one, and eventually somebody leans a payments
change. Hold the line here and lean mode stays cheap for the work it fits.

## The run

1. **Write the ten-line brief.** Mission, owned paths, definition of done,
   out of scope. About ten lines. Write it to
   `company/briefs/brief-<slug>.md` and pass **the same text** in the spawn
   prompt. Same words, one write, two uses.

   The file looks like the obvious thing to cut. Keep it, for two reasons.
   `guard_spec` requires it - an active task entry whose `brief` path does
   not exist blocks the first source edit, and the block message will just
   tell you to write the file you skipped. More importantly it is the only
   copy that survives this session dying. An inline spawn prompt lives in a
   transcript nobody re-reads; a file in `company/briefs/` is what the next
   session finds.

2. **Add the task entry, exactly as always.** One targeted Edit into
   `company/state/active-task.json` adding your entry - never a whole-file
   Write, because another session's entry lives in the same file. Classify
   honestly (`quick` or `feature`); lean mode changes the ceremony you spend,
   not the class you record. This is one Edit and it is what the hooks read.
   It is not where the time goes.

3. **Dispatch developers directly.** One `developer` in a worktree
   (`git worktree add .claude/worktrees/<slug> -b task/<slug>`). Two only
   when the work genuinely splits across disjoint paths. No tech-lead: a lead
   managing a single developer is pure ceremony, and the lead layer exists to
   coordinate teams, not to relay one brief.

4. **QA only when there is something to look at.** A visual surface gets one
   `qa-engineer` and the four states - loaded, empty, error, after-action -
   and you judge the screenshots yourself. A hook, a script, a config, or a
   library change gets no QA engineer, because Playwright would have nothing
   to drive. Its tests are its evidence.

5. **Dispatch the audit on purpose.** One `auditor`, read-only, over the
   finished diff, once, before merge.

   This is the counterintuitive one and it is worth being blunt about. The
   mandatory-audit rule arms on **self-authorship**: it fires when you edit
   source in the main checkout under `execution: "self"`. Work delegated to a
   worktree is exempt, because the hierarchy verified it - a tech-lead
   re-checked the developer's work against the brief. **Lean mode deleted
   that lead.** So a developer committing cleanly from a worktree arms
   nothing, no hook asks for a review, and if you assumed one would you will
   merge unread work. That is exactly how a 4791-line feature shipped in this
   repo this year with no auditor ever reading it. The exemption is still
   correct; lean mode just owes the audit by hand. Dispatch it deliberately,
   every lean task, no exceptions.

6. **Gates green, unconditionally.** Run the project's ladder
   (`bash company/run-gates.sh`, or the suites this project's `CLAUDE.md`
   names as the real ones) and read the output yourself. There is no lean
   exemption and there never will be one. Red means fix the cause: never
   weaken a gate, never skip one, never edit a test to pass. Twice red on the
   same cause after a respawn is an owner escalation, in this mode as in the
   other.

7. **Integrate and leave one STATUS line.** Merge, remove ONLY your entry
   from `active-task.json` with a targeted Edit, remove the worktree. Then
   append **one row** to `company/state/STATUS.md`: what shipped, gates
   green, audit done. Not a report - one line. Lean work that leaves no trace
   recreates the exact problem RESUME exists to solve, and the next session
   pays for it. If the work turned up something you did not chase, that is
   one row in `WORRIES.md` too.

Then report to the client the way you always do: what shipped in their
words, the evidence in a sentence, what is next. Delivery is a delivery in
either mode.

## What lean mode does not do

Stated so it cannot quietly accrete back:

- No spec and no `product-manager`.
- No `architect`, no ownership map, no wave plan.
- No `tech-lead`.
- No witness curation.
- No `docs-librarian` sync.
- No `REPORT-TEMPLATE.md` report from the developer - the diff, the gates,
  and the audit are the report.
- No retrospective.

Everything on that list is a real mechanism that earns its keep on large or
risky work. Lean mode is the bet that on one small piece of work it does
not, and the upgrade trigger is what keeps that bet honest.
