# BRIEF: lean-company

_Type: feature. Spec: lite (one repo, nothing frozen, no money, no invariant -
the Phase 0 spec-lite rung, DECISIONS #19). Lead: direct-developer.
Date: 2026-08-13. Tracking issue: #109._

## Mission

Build `/lean-company`: a second entry point to this harness for quick
iteration. It is a SEPARATE command, deliberately, not a mode flag on
`/company` - a flag would branch the main path and multiply the test
matrix, while a separate door costs neither.

The line it walks: it cuts the HIERARCHY and the PAPERWORK, and it never cuts
the GATES. Those are different axes and conflating them is the whole failure
mode here. Success is a CEO able to take a small piece of work from request to
merged in a handful of minutes, with the same guarantees about correctness and
a much smaller pile of artifacts.

The hard constraint that must survive contact with reality: **a fast path that
drops the gates is not a mode of this harness, it is Claude Code with extra
steps.** People already have that for free. What only this harness gives is the
hierarchy and the gates; lean mode thins the first and keeps the second whole.

## Read first (in order)

1. `CLAUDE.md` (project canon - and note it names all FIVE gate suites)
2. `company/METHOD.md` - the five mechanisms, and the ceremony table. Read
   mechanism 5 carefully; lean mode must still satisfy it.
3. `.claude/skills/company/SKILL.md` - the full-ceremony command you are
   writing the lean sibling of. Match its voice and structure; a reader should
   feel these are two doors into one building.
4. `.claude/skills/feature/SKILL.md` and `.claude/skills/gates/SKILL.md` - the
   house style for a skill file.
5. `COMPANY.md` - READ ONLY, do not edit. It is owned by another lane
   in flight.

## You own

- `.claude/skills/lean-company/SKILL.md` (new - this is the deliverable)
- `README.md` and `docs/getting-started.md` - one mention each, no rewrites
- `install.sh` - the advertised command list in the epilogue near line 422
  ONLY. One line. Touch nothing else in that file.
- `tests/install/run_tests.sh` - one assertion, see DoD

Nothing else. THREE OTHER LANES ARE BUILDING RIGHT NOW and you must not
collide: `COMPANY.md`, `company/METHOD.md`, `company/GATES.md`,
`company/templates/BRIEF-TEMPLATE.md`, `.claude/agents/**` and
`.github/workflows/ci.yml` belong to the doctrine lane; every file under
`.claude/hooks/` belongs to two others. If lean mode needs a doctrine change or
a hook change, WRITE IT DOWN in your report - do not make it.

## What the skill must specify

1. **The shape.** CEO dispatches one or two `developer` agents directly. No
   tech-lead: a lead managing a single developer is ceremony. Two developers
   only when the work genuinely splits across disjoint paths.
2. **QA only when there is something to look at.** A visual surface gets one
   `qa-engineer` and the four states. A hook, a script or a config change gets
   none, because Playwright would have nothing to drive.
3. **ONE audit, dispatched ON PURPOSE.** This is the subtle part and it must be
   stated plainly in the skill: the mandatory-audit rule is triggered by
   SELF-AUTHORSHIP, so a developer committing cleanly from a worktree never
   arms it. A CEO who assumes the hook will demand a review will not get one.
   In lean mode the CEO dispatches the `auditor` deliberately, once, on the
   finished diff.
4. **Gates green, unconditionally.** The suites named in `CLAUDE.md` must pass
   before merge, exactly as in full mode. No lean exemption exists.
5. **A ten-line brief that doubles as the spawn prompt.** The CEO writes about
   ten lines - mission, owned paths, definition of done, out of scope - drops
   them at `company/briefs/brief-<slug>.md`, and passes the same text in the
   spawn prompt. Same words, one write. Explain WHY the file still exists at
   all, because it looks like the obvious thing to cut: `guard_spec` requires
   it, and more importantly it is the only copy that survives a session death,
   since an inline prompt lives in a transcript nobody re-reads.
6. **One STATUS line.** Not a report. One row, so the next session can see what
   happened. Lean work that leaves no trace recreates the problem RESUME exists
   to solve.
7. **Task state is unchanged.** The entry in `company/state/active-task.json`
   is written exactly as always - targeted Edit, never a whole-file Write - and
   classification rules do not change. That discipline is one Edit and it is
   what the hooks read; it is not where the time goes.
8. **The hard upgrade trigger, one-way.** A lean task that reaches a FROZEN
   SURFACE, a MIGRATION, AUTH or BILLING or MONEY, an INVARIANT, or a SECOND
   WORKSTREAM stops and moves to `/company`. Not as advice - as the rule
   that keeps this command safe to offer, because those are exactly the cases
   where being wrong is expensive. Note that the hooks will block several of
   them anyway, so the trigger mostly tells the CEO to stop arguing with a
   block that is correct.
9. **What lean mode does NOT do**, stated explicitly so it cannot accrete: no
   spec and no product-manager, no architect, no tech-lead, no wave plan, no
   witness curation, no docs-librarian sync, no report template, no
   retrospective.

## Definition of Done

- [ ] `.claude/skills/lean-company/SKILL.md` exists and covers all nine points
      above, in the house voice
- [ ] One mention each in `README.md` and `docs/getting-started.md`, and one
      line in the `install.sh` epilogue list
- [ ] `tests/install/run_tests.sh` gains ONE assertion that the lean skill is
      copied by an install, matching the existing `skills copied` idiom. Note
      that suite builds a STUB source tree, so add the stub file alongside the
      existing `skills/company` stub or your assertion will fail for the
      wrong reason.
- [ ] Gates: run all five suites named in `CLAUDE.md` from your worktree root
      and paste them. Do NOT run `bash company/run-gates.sh`.
- [ ] Ownership diff touches only the files listed above
- [ ] No em dashes, straight quotes, three dots - the writing gate scans every
      tracked text file and it will catch you
- [ ] Conventional commit, `Task: lean-company` trailer, explicit staged paths
- [ ] Report: what changed, five suites pasted, ownership diff, anything lean
      mode needs from doctrine or hooks that you did NOT make, and 1-3 witness
      candidates

## Fallback assumptions

- The command name is `lean-company`, so the directory is
  `.claude/skills/lean-company/`. Do not rename it or add an alias; a second
  entry point to a second entry point is how this gets confusing.
- If you cannot tell whether something belongs in the skill or in doctrine,
  put it in the skill and flag it in the report. Doctrine is owned by a lane in
  flight and a conflict costs more than a slightly long skill file.

## Out of scope

- Any change to `/company` or to any doctrine file.
- Any hook change, including making `quick` entries cheaper. Another lane owns
  that.
- Renaming `/company` to `/company`, which is a separate open question.
- Building a profile or mode system. This is one command, nothing more.

## Report back

Facts: what changed, the five suites pasted, ownership diff, the list of things
lean mode wants from doctrine or hooks that you deliberately did not make,
deviations, worries, witness candidates.
