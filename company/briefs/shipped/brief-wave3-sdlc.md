# BRIEF: wave3-sdlc

_Type: program-workstream. Spec: approved adoption plan (issues #23, #24,
#25). Lead: tech-lead. Date: 2026-07-09._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Ship the enterprise-SDLC surface of the program: release management
doctrine and the /release skill, the owner acceptance record, and the
hotfix postmortem. The owner's standing vision: claude-company models how
an actual enterprise runs its SDLC - a release is PREPARED by the company
and SHIPPED by the owner, never the reverse; sign-off and incident review
are recorded, not implied. Hard constraints: every file no_slop-clean;
the deploy boundary is absolute (nothing you write may run or script a
deploy, tag push, or npm publish - the skill ENDS at a proposal).

## Read first (in order)

1. `CLAUDE.md` (note: currently absent in this repo - issue #28; read
   `company/METHOD.md` as the canon and continue)
2. `company/METHOD.md` (you edit it - study voice first; note the new
   ADR/precedence sections from wave 2)
3. `ORCHESTRATOR.md` (you edit step 8; steps 6-7 were just extended by
   wave 2 - do not disturb them)
4. `company/GATES.md` (read-only for you: the G0 witnesses / G6 trace /
   G7 models / G8 audit ladder your release-readiness list cites)
5. `company/templates/REPORT-TEMPLATE.md` (you add the acceptance line;
   wave 2 added the Witness candidates section - keep it)
6. `company/state/DECISIONS.md`, `company/state/WORRIES.md` (shapes your
   doctrine references)
7. `.claude/skills/standup/SKILL.md` and `.claude/skills/gates/SKILL.md`
   (skill file idiom: frontmatter, structure, tone)
8. `.claude/agents/devops-engineer.md` (you add the release-prep duty)

## You own

- `company/RELEASE.md` (new)
- `company/templates/RELEASE-TEMPLATE.md`, `company/templates/POSTMORTEM-TEMPLATE.md` (new)
- `company/templates/REPORT-TEMPLATE.md` (acceptance line only)
- `company/METHOD.md` (hotfix postmortem rule + release pointer only)
- `ORCHESTRATOR.md` (step 8 acceptance record + release pointer only)
- `.claude/skills/release/` (new)
- `.claude/agents/devops-engineer.md` (release-prep duty only)

Nothing else. Hooks, tests, gates_detect, witnesses.json, GATES.md,
LOOPS.md, ADR files: read-only to you.

## Invariants in play (must not break)

- no_slop compliance everywhere (straight quotes, ' - ', three dots).
- Deploy boundary: merge integrates, deploy is a manual OWNER step. The
  /release skill prepares and proposes; it never tags, pushes a tag,
  publishes, or deploys - and never instructs an agent to.
- Existing canon structure: extend, never renumber or restructure.
- Both suites stay green (you change no code; prove it anyway).
- All spawned agents run opus.

## Frozen surfaces nearby (CR, never edit)

- `company/state/*` (your doctrine WRITES ABOUT DECISIONS.md; this task
  never writes state itself), `company/gates.config`, accepted ADRs under
  `company/adr/` (immutable - the guard blocks you), `.env*`, lockfiles.

## Scope (ordered)

1. **company/RELEASE.md** (#23) - the release doctrine, sibling in tone to
   GATES.md/GIT.md:
   - Principle: a release is PREPARED by the company, SHIPPED by the
     owner, never the reverse. Deploy/tag/publish are owner buttons.
   - Release readiness (ALL must hold, each mechanically checkable):
     full gate ladder green on integrated main (fresh stamp);
     `witness_check.py --check` green; audit gate (G8) green where wired;
     security-reviewer pass for releases touching auth/session/money;
     zero open P0/P1 rows in WORRIES.md; zero undecided CRs in
     company/change-requests/; STATUS shows no red task in the release
     scope.
   - Release preparation (what the devops-engineer produces, via
     /release): changelog derived from conventional commits and their
     `Task:` trailers since the last tag; semver bump proposal with the
     reasoning (breaking/feat/fix); release notes written as an evidence
     report (what shipped, gate ladder, known limits); the filled
     RELEASE-TEMPLATE checklist.
   - The handoff: the prepared release lands as a proposal entry in
     company/state/DECISIONS.md (written by the CEO, not the skill) -
     tag name, target commit, notes location. The owner tags and
     publishes. Include the exact git/gh commands the OWNER would run,
     clearly marked owner-only.
2. **company/templates/RELEASE-TEMPLATE.md** (#23): the checklist + notes
   shape - readiness table (each criterion, its command, its result),
   changelog section, semver proposal + reasoning, known limits, rollback
   note (how the owner reverts if the release is bad: previous tag,
   npm deprecate guidance - descriptive, owner-only).
3. **.claude/skills/release/SKILL.md** (#23): /release - owner/CEO
   invoked. Frontmatter like the existing skills
   (disable-model-invocation: true so it never self-triggers). Steps:
   verify readiness list mechanically (run the commands, paste outputs);
   if any criterion fails, STOP and report what is red - a release
   cannot be prepared from a red board; dispatch or act as
   devops-engineer to produce changelog/semver/notes per
   RELEASE-TEMPLATE; end at the DECISIONS.md proposal handoff. The skill
   text must state it never tags/publishes/deploys.
4. **Owner acceptance record** (#24): ORCHESTRATOR.md step 8 - the
   delivery report to the owner ends with an acceptance ask, and the CEO
   records the owner's response in company/state/DECISIONS.md as
   `accepted | accepted-with-notes | rejected` + date + one line; a
   rejected delivery reopens the task (STATUS back to red, worktree
   preserved or task respawned). REPORT-TEMPLATE.md: one final line -
   "Acceptance: pending owner" - so every report carries the field.
   METHOD.md: one sentence in the client-posture section (delivery is
   not done until acceptance is recorded; silence is not acceptance).
5. **Hotfix postmortem** (#25): company/templates/POSTMORTEM-TEMPLATE.md -
   timeline (detected/mitigated/resolved), root cause, blast radius, why
   the gates did not catch it, and THE PREVENTION LINE: which new gate /
   witness / frozen surface now prevents recurrence - it must name a real
   change (witness_check --add, a new gate in gates.config, a new frozen
   pattern) or state explicitly why none is possible. METHOD.md hotfix
   section: no hotfix task closes without a postmortem filed to
   company/specs/shipped/ (or the retro location the section already
   uses - follow the existing retroactive-spec wording); the prevention
   line is checked by the CEO at close.
6. **devops-engineer.md**: add the release-preparation duty (changelog,
   semver proposal, notes, checklist per RELEASE.md) with the existing
   "never deploys" line restated as the boundary.

## Integration seams

- Cite the wave-2 mechanisms by their exact names: `witness_check.py
  --check`, the G0/G6/G7/G8 ladder rows, risk bands. Do not redefine them.
- Wave-2 doctrine already owns ORCHESTRATOR steps 2/4/6/7 - your edits
  touch step 8 (and the release pointer) only.
- You guarantee: RELEASE-TEMPLATE readiness criteria are each one runnable
  command + expected result (mechanically checkable, no vibes).

## Definition of Done

Universal DoD plus:
- [ ] Both suites green, pasted: `python3 -m unittest discover -s
      tests/hooks -q` AND `npm test`
- [ ] Every owned file no_slop-clean
- [ ] No edits outside owned paths; zero frozen surfaces touched
- [ ] /release skill text ends at the DECISIONS.md proposal - grep it
      yourself for tag/publish/deploy commands presented as agent actions
      (owner-only sections clearly marked)
- [ ] Commits per company/GIT.md: conventional, `Task: wave3-sdlc`
      trailer, explicit paths; commit your brief file too
- [ ] Report per company/templates/REPORT-TEMPLATE.md (including the new
      acceptance line you added)

## Fallback assumptions

- OQ-W3-01: no previous tag exists (this repo has none) -> FALLBACK:
  changelog range is "since first commit" and the doctrine says the first
  release starts the tag history; note it in RELEASE.md.
- OQ-W3-02: where postmortems live -> FALLBACK: follow METHOD.md's
  existing retroactive-spec location for hotfixes; postmortem file sits
  next to the retroactive spec, named postmortem-<slug>.md.
- OQ-W3-03: DECISIONS.md entry shape -> FALLBACK: match the existing
  DECISIONS.md structure; one dated entry per decision, terse.
- OQ-W3-04: semver policy edge (pre-1.0 repo) -> FALLBACK: document both
  rules (pre-1.0: breaking bumps minor; post-1.0: standard semver) in
  RELEASE.md, one line each.

## Out of scope

- Any code, hook, or test change; GATES.md, LOOPS.md, ADR content
- Actually preparing or proposing a release for this repo (the machinery
  ships; the owner decides when to first use it)
- README/docs sync (docs-librarian pass after the program)
- Lessons loop, loop workers (deferred by owner decision)

## Report back

Facts: what changed (paths), suite outputs pasted, scope checklist,
ownership diff summary (`git diff --name-only task/wave2-doctrine..HEAD`),
CRs filed, deviations, worries, witness candidates (1-3, doc-anchor style:
which exact lines in RELEASE.md/templates are load-bearing contracts).
