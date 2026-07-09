# BRIEF: wave2-doctrine

_Type: program-workstream. Spec: approved adoption plan (issue #20 doctrine
half + doctrine for #18, #19, #21, #22). Lead: tech-lead. Date: 2026-07-09._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Ship the doctrine half of wave 2: the ADR system's documents and duties,
and the canon updates that make the new enforcement tools (witnesses, risk
score, trace gate, audit gate, secrets guard) part of how the company
operates. A parallel workstream builds the tools themselves - you document
their contracts EXACTLY as specified in "Integration seams" below; do not
invent different names or shapes. Hard constraint: every file you write
must pass the no_slop hook (straight quotes, ' - ' never em dashes, three
dots never the ellipsis character) - you are writing the canon that
enforces this on everyone else.

## Read first (in order)

1. `CLAUDE.md`
2. `company/METHOD.md` (you edit it - study its voice and structure first)
3. `ORCHESTRATOR.md` (same)
4. `company/GATES.md` (same)
5. `company/templates/SPEC-TEMPLATE.md`, `BRIEF-TEMPLATE.md`,
   `REPORT-TEMPLATE.md`, `CR-TEMPLATE.md` (the template voice)
6. `.claude/agents/architect.md`, `.claude/agents/docs-librarian.md`
   (you add duties)
7. `company/frozen-surfaces.json` (context for the ADR immutability rule)

## You own

- `company/METHOD.md`, `company/GATES.md`, `ORCHESTRATOR.md`,
  `company/LOOPS.md`
- `company/adr/` (new directory: README.md index + ADR-0001)
- `company/templates/` (new: ADR-TEMPLATE.md; edit: REPORT-TEMPLATE.md)
- `.claude/agents/architect.md`, `.claude/agents/docs-librarian.md`

Nothing else. Anything not listed is read-only to you. The hooks, tests,
witnesses.json, gates_detect (parallel workstream) - do NOT touch, even to
"fix" something; report instead.

## Invariants in play (must not break)

- no_slop compliance in every file (it blocks your own writes otherwise).
- The canon's existing voice: terse, imperative, no marketing.
- Do not renumber or restructure existing sections; extend them.
- Existing tests must stay green - you touch no code, so any test that
  goes red means you broke a doc a test asserts on (README is out of
  scope for you; nothing else is test-pinned - verify anyway).
- All spawned agents run opus.

## Frozen surfaces nearby (CR, never edit)

- `company/state/*` (never write state as part of this task),
  `company/gates.config`, `.env*`, lockfiles.

## Scope (ordered)

1. **ADR template + directory** (#20): `company/templates/ADR-TEMPLATE.md`
   with fields: `# ADR-NNN: <title>`, `Status: proposed | accepted |
   superseded-by-ADR-NNN` (exact strings - a hook matches
   `Status: accepted` literally), Date, Context, Decision, Consequences,
   Scope (bulleted repo paths this decision binds), Supersedes (ADR-NNN or
   "none"). `company/adr/README.md`: purpose paragraph + index table
   (ID, title, status, scope) + lifecycle rules: architect proposes, CEO
   accepts, accepted ADRs are IMMUTABLE (a guard blocks edits) - supersede
   with a new ADR; status flips are CEO-applied via CR; ADRs are never
   deleted. Write `company/adr/ADR-0001-adr-system.md` as the founding
   example (Status: accepted): the decision to adopt ADRs, its scope
   (company/adr/), consequence (immutability enforcement).
2. **Precedence rule** (#20): in METHOD.md (with the other core
   mechanisms) and ORCHESTRATOR.md (briefing step): "ADR wins on
   architecture (how), SPEC wins on scope (what). A brief that contradicts
   an accepted ADR is a briefing error; a builder that notices the
   conflict files a CR - it never picks a winner." Add ADR proposal to the
   architect's Phase-0/program duties in ORCHESTRATOR.md step 2.
3. **GATES.md updates**: add ladder rows/sections for the new mechanical
   gates, using EXACTLY these contract points (built by the parallel
   workstream): gate `witnesses` - `python3
   .claude/hooks/witness_check.py` - FIRST rung (G0): every shipped
   fix/feature records 1-3 load-bearing witnesses (registry
   company/witnesses.json, mutations only via the CLI --add/--remove, IDs
   W-NNN); gate `trace` - `python3 .claude/hooks/trace_check.py` - makes
   G6 requirement traceability mechanical (orphan FR = red); gate `audit`
   - dependency/CVE scan - LAST rung (network-bound); gate `models` -
   `python3 .claude/hooks/guard_models.py --check` (wave 1). Plus a short
   "Secrets never commit" note: guard_secrets blocks at commit time and
   hotfix does NOT bypass it.
4. **ORCHESTRATOR.md verify step (step 6)**: add - run `python3
   .claude/hooks/risk_score.py --base <integration-base>` on every
   completed task branch; band `high` makes the auditor dispatch
   MANDATORY (not judgment), `medium` means extra spot-reads; the score
   only escalates verification, never waives it. **Step 7 (integrate)**:
   after merge + gates rerun, record witnesses for what shipped
   (`witness_check.py --add ...`, producer proposes markers in its
   report, CEO curates and records).
5. **LOOPS.md**: one addition to the /autopilot doctrine - an unattended
   tick treats a `high` risk band as stop-and-surface (aligns with the
   iron rules; do not otherwise expand LOOPS.md - the loop-workers
   upgrade is deferred by owner decision).
6. **REPORT-TEMPLATE.md**: add a "Witness candidates" line to the report
   shape (1-3 proposed load-bearing markers: file + exact substring +
   why) so producers propose and the CEO records.
7. **Agent duties**: architect.md - propose ADRs for boundary-shaping
   decisions in Phase 0/program planning; note accepted-ADR immutability
   and the precedence rule. docs-librarian.md - keep company/adr/README.md
   index true after merges; verify ADR Scope paths still exist; never
   change an ADR's Status.

## Integration seams

- The enforcement workstream (parallel) builds: witness_check.py,
  risk_score.py (bands low/medium/high, RISK_JSON), trace_check.py,
  gates_detect proposals named `witnesses`/`trace`/`audit`/`models`, and
  the guard_frozen accepted-ADR clause matching the literal line
  `Status: accepted`. Document these exactly; if you believe a contract
  is wrong, file a CR - do not improvise.
- ADR-0001 will be immutable the moment the enforcement branch lands -
  write it final.

## Definition of Done

Universal DoD plus:
- [ ] Both suites green (you changed no code; prove it anyway):
      `python3 -m unittest discover -s tests/hooks -q` AND `npm test`
- [ ] Every owned file no_slop-clean (your own writes going through means
      this held)
- [ ] No edits outside owned paths
- [ ] Commits per company/GIT.md: conventional, `Task: wave2-doctrine`
      trailer, explicit paths
- [ ] Report per company/templates/REPORT-TEMPLATE.md

## Fallback assumptions

- OQ-W2D-01: where the precedence rule sits in METHOD.md -> FALLBACK:
  with the frozen-surfaces/CR mechanism section, cross-referencing
  company/adr/README.md.
- OQ-W2D-02: ADR numbering -> FALLBACK: zero-padded ADR-0001 style;
  next-free noted in the index.
- OQ-W2D-03: how much GATES.md restructuring -> FALLBACK: none; append
  rows to the existing ladder table and add short sections; keep G-number
  scheme (witnesses = G0, trace fulfills existing G6, audit appended
  last).

## Out of scope

- ALL code: hooks, tests, gates_detect, witnesses.json (parallel
  workstream)
- README.md, docs/ (docs-librarian pass after the wave)
- BRIEF-TEMPLATE lessons line (deferred with the lessons loop)
- RELEASE.md, acceptance record, postmortem template (wave 3)
- SPEC-TEMPLATE changes

## Report back

Facts: what changed (paths), suite outputs pasted, scope checklist,
ownership diff summary (`git diff --name-only
task/wave1-enforcement..HEAD`), CRs filed, deviations, worries.
