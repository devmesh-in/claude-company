# BRIEF: docs-sync

_Type: quick. Spec: none (quick) - keyed to issue #28 and the shipped
ruflo-adoption program (PRs #27, #33, #34, #32, #35). Lead:
docs-librarian (direct). Date: 2026-07-10._

> Anything in `company/frozen-surfaces.json` is FROZEN - CR, never a local
> edit.

## Mission

Sync the client-facing docs with what the program shipped, and give this
repo the project `CLAUDE.md` every dispatched agent is told to read
(closes #28). The merged code is the source of truth - read it, then make
the docs match. Never document aspiration; document what the code does.
Hard constraints: every file no_slop-clean; README structure survives the
CI "readme structure and links" guard and the npm pack tests (`npm test`
green is your proof).

## Read first (in order)

1. `company/METHOD.md`, `company/GATES.md`, `company/RELEASE.md`,
   `company/adr/README.md` (the canon you are summarizing for clients)
2. The shipped surface: `.claude/hooks/guard_secrets.py`,
   `cost_capture.py`, `witness_check.py`, `risk_score.py`,
   `trace_check.py`, `guard_frozen.py` (docstrings), `company/witnesses.json`,
   `.claude/skills/release/SKILL.md`, `.claude/skills/standup/SKILL.md`
3. `README.md`, `docs/how-it-works.md`, `docs/customizing.md`,
   `docs/getting-started.md` (current state + voice)
4. `company/state/RESUME.md` section 4 (the facts CLAUDE.md must carry)

## You own

- `README.md`, `docs/`
- `CLAUDE.md` (new, repo root)

Nothing else. No code, no hooks, no company/ canon edits, no templates.

## Invariants in play

- no_slop clean everywhere.
- README's existing structure/anchors survive (CI guards them); extend
  tables, do not restructure.
- `npm test` stays green (pack manifest tests run against the repo).
- CLAUDE.md is NOT in the npm pack files list - it is repo-local canon;
  keep it that way (do not add it to package.json).

## Scope (ordered)

1. **CLAUDE.md** (new, closes #28) - the project canon for THIS repo,
   read by every spawned agent. Terse, factual, about one page: what this
   repo is (the claude-company product: the installer, hooks, skills,
   agents, and company/ canon that ship into user projects); the
   dual-nature rule (tracked `company/gates.config` keeps CONFIGURE-ME
   placeholders because company/ ships to installs - never commit real
   gates into it; the two real suites are
   `python3 -m unittest discover -s tests/hooks -q` and `npm test`);
   layout map (bin/ lib/ install.sh .claude/hooks .claude/skills
   .claude/agents company/ tests/ docs/); enforcement facts (hooks are
   Python 3.8 stdlib, fail open, no_slop applies to all writing:
   straight quotes, ' - ', three dots); witness registry mutated only
   via witness_check.py --add/--remove; accepted ADRs immutable;
   conventional commits with Task: trailer, explicit staging.
2. **README.md**: "The rules it enforces" table - add rows for: shipped
   work stays shipped (witness manifest), accepted ADRs are immutable,
   requirements must trace to tests (orphan FR = red gate). Commands
   table - add `/release`. "How it works" list - one new numbered point
   or extension covering risk-scored verification (high risk = mandatory
   independent audit) and release/acceptance (a release is prepared by
   the company, shipped by you; delivery ends with your recorded
   acceptance). Keep it client-voice, no internal jargon.
3. **docs/how-it-works.md**: sync with the shipped method - the gate
   ladder now includes G0 witnesses / G6 trace / G7 models / G8 audit;
   the secrets guard (and that hotfix does not bypass it); cost
   accounting + /standup Spend; risk-scored verification driving auditor
   dispatch; the ADR system (precedence rule, immutability); release
   flow ending at an owner tag proposal; owner acceptance record; hotfix
   postmortems with the mandatory prevention line.
4. **docs/customizing.md**: how to see/edit the new surfaces -
   witnesses.json (via the CLI only), company/adr/ + ADR-TEMPLATE,
   RELEASE.md readiness list, pricing map in models.json for cost
   estimates.
5. **docs/getting-started.md**: touch only if something it says is now
   wrong; otherwise leave it.

## Definition of Done

- [ ] `npm test` green, pasted (README/pack guards pass)
- [ ] `python3 -m unittest discover -s tests/hooks -q` green, pasted
- [ ] Every claim in the docs traceable to shipped code/canon (no
      aspiration)
- [ ] No edits outside owned paths
- [ ] Commits per company/GIT.md (`Task: docs-sync` trailer, explicit
      paths); commit this brief too
- [ ] Report per company/templates/REPORT-TEMPLATE.md

## Fallback assumptions

- OQ-DS-01: how much README growth is too much -> FALLBACK: net +25 lines
  max; the README sells, docs/ explains.
- OQ-DS-02: CLAUDE.md length -> FALLBACK: under 60 lines; it is a fact
  sheet, not a manual.

## Out of scope

- Any code/hook/test/canon change; ORCHESTRATOR.md; templates
- Issue #31 (parallel task)
- Marketing rewrites of existing prose

## Report back

Facts: paths changed, both suite outputs, scope checklist, ownership diff
(`git diff --name-only main..HEAD`), deviations, worries, acceptance line.
