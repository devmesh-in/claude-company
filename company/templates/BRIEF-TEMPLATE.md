# BRIEF: <task-slug>

_Type: quick | feature | program-workstream. Spec: <link or "none (quick)">.
Lead: <tech-lead | direct-developer>. Date: YYYY-MM-DD._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

A vague brief is the main cause of a bad agent run. The agent reads this plus
the project's `CLAUDE.md`, nothing of the CEO's context. Make it sealed and
self-contained.

## Mission
One paragraph, in the user's terms, naming the observable outcome that means
success. Include the one hard constraint that must survive contact with reality.

## Read first (in order)
1. `CLAUDE.md` (project canon)
2. `company/METHOD.md` (how the team works)
3. <the specific module docs / source files to study - exact paths>

## You own
- `<dir>/` ...
- `<dir>/` ...

Nothing else. Anything not listed is read-only to you. If the fix you need
lives outside these paths, report it; do not make it.

## Invariants in play (must not break)
- <the specific project invariants this task brushes against>

## Frozen surfaces nearby (CR, never edit)
- <which frozen surfaces this task sits close to, and what to do instead>

## Scope (ordered)
1. <concrete step, citing FR-XX-NN>
2. ...

## Integration seams
- <adjacent module/workstream>: you guarantee <X>; you may assume <Y>.
- For full-stack work: land the API side first; the UI consumes the merged shape.

## Definition of Done
Universal DoD (every task) plus this task's specifics:
- [ ] Every FR in scope implemented, tested, or explicitly deferred with reason
- [ ] `bash company/run-gates.sh` green - run it yourself before reporting
- [ ] No edits outside owned directories; zero frozen surfaces patched locally
- [ ] UI work: screen driven live, four states captured (loaded/empty/error/after-action)
- [ ] Tests added for new behavior (tests are the oracle - never edited to pass)
- [ ] Commits follow `company/GIT.md`: conventional, `Task: <slug>` trailer,
      explicit paths staged
- [ ] `MODULE.md` created/updated in each owned directory
- [ ] Report follows `company/templates/REPORT-TEMPLATE.md`
- [ ] <task-specific DoD lines>

## Fallback assumptions
For every ambiguity, implement THIS stated assumption and tag the site - do not
guess, do not ask the user:
- OQ-XX-01: <question> -> FALLBACK: <decision>. Tag `// OQ-XX-01 assumption`.

## Out of scope
Explicitly, so nobody "helpfully" expands:
- <thing> (owned by <other workstream / later phase>)

## Report back
Your report must contain, as facts: what changed (paths), gate results (paste
the ladder), FR checklist, ownership diff summary, screenshots (UI), CRs filed,
deviations from this brief and why, worries for the CEO.
