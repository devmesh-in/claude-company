# BRIEF: adr-hardening

_Type: quick. Spec: none (quick) - keyed to issue #31 (auditor finding).
Lead: direct developer. Date: 2026-07-10._

> Anything in `company/frozen-surfaces.json` is FROZEN - CR, never a local
> edit.

## Mission

Close the ADR lifecycle gap the auditor found (#31): a brand-new
`company/adr/*.md` written directly with `Status: accepted` currently
bypasses the propose-then-accept lifecycle, because the guard_frozen
accepted-ADR clause only inspects the file already on disk. After this
task, minting a pre-accepted ADR through the Edit/Write/MultiEdit tools is
blocked; creation must be `Status: proposed`.

## Read first (in order)

1. `company/METHOD.md` (mechanism 3 - the ADR rules you are enforcing)
2. `.claude/hooks/guard_frozen.py` (the existing accepted-ADR clause and
   the shipped-migrations precedent; study the fail direction)
3. `company/adr/README.md` (the lifecycle your block message must recite)
4. `tests/hooks/test_hooks.py` (the existing accepted/proposed ADR tests
   you extend)
5. `.claude/hooks/_common.py` (block(), fail-open idiom)

## You own

- `.claude/hooks/guard_frozen.py`
- `tests/hooks/`

Nothing else.

## Invariants in play

- Python 3.8 stdlib; the clause fails SAFE like the migrations/accepted
  clauses (on uncertainty about content, block - immutability checks are
  the one place we fail closed).
- Existing tests stay green and unedited (194 hook tests at your branch
  point across all modules - the suite count is 147; do not disturb).
- Witness W-006 lives in guard_commit.py, W-001/W-003 in
  guard_secrets.py - your file is guard_frozen.py; run
  `python3 .claude/hooks/witness_check.py` anyway and keep it 9/9.
- no_slop clean writing.

## Scope (ordered)

1. In the accepted-ADR section of guard_frozen.py: when the tool call
   targets a path matching `company/adr/*.md` that does NOT exist on disk
   (or is Write over a non-existent file), inspect the INCOMING content
   (tool_input new content for Write; for Edit/MultiEdit on a
   non-existent file the tool fails anyway - handle Write as the real
   vector, and Edit defensively). If the incoming content contains a line
   starting `Status: accepted` -> BLOCK: "a new ADR is born proposed,
   never accepted. Write it with Status: proposed; the CEO flips the
   status on acceptance (see company/adr/README.md)." Existing-file
   behavior is unchanged (accepted on disk = immutable; proposed on disk
   = editable, including a later flip of the status line by the CEO).
2. Tests in tests/hooks/ (extend the existing ADR test group): new Write
   with Status: accepted -> blocked exit 2; new Write with Status:
   proposed -> allowed; editing an existing proposed ADR to accepted
   (the CEO acceptance flip) -> allowed; existing accepted stays blocked;
   template file under company/templates/ never matches (path check).
3. Update the docstring's clause list.

## Definition of Done

- [ ] Both suites green, pasted: `python3 -m unittest discover -s
      tests/hooks -q` AND `npm test`
- [ ] `python3 .claude/hooks/witness_check.py` still 9/9, pasted
- [ ] Hand-exercise both directions with synthetic payloads (paste the
      block message)
- [ ] No edits outside owned paths; existing tests untouched
- [ ] Commits per company/GIT.md (`Task: adr-hardening` trailer, explicit
      paths); commit this brief too
- [ ] Report per company/templates/REPORT-TEMPLATE.md

## Fallback assumptions

- OQ-AH-01: MultiEdit on a new file with accepted status -> FALLBACK:
  same block as Write (inspect combined new content defensively).
- OQ-AH-02: status line matching -> FALLBACK: same literal-line semantics
  the existing clause uses (line starts with `Status: accepted`, tolerant
  of trailing whitespace); do not invent regex variants.

## Out of scope

- Bash-path enforcement (echo > file evades Edit/Write hooks; that is a
  known boundary of ALL PreToolUse file guards here, not this task)
- Doctrine/docs edits (parallel docs-sync task owns docs; company/adr/
  README already describes the lifecycle)
- Any other hook

## Report back

Facts: paths changed, suite + witness outputs, scope checklist, ownership
diff (`git diff --name-only main..HEAD`), hand-exercise transcript,
deviations, worries, 1 witness candidate for the new clause, acceptance
line.
