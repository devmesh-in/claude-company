# BRIEF: wave2-enforce

_Type: program-workstream. Spec: approved adoption plan (issues #18, #19,
#21, #22, #26 + the enforcement half of #20). Lead: tech-lead.
Date: 2026-07-09._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Ship the verification-hardening machinery of wave 2: witness manifest,
diff risk scoring, requirement traceability gate, CVE audit gate proposal,
the guard_frozen clause for accepted ADRs, and the guard_commit worktree
bug fix. Everything ships to user installs: Python 3.8 stdlib only, fail
open, existing idioms exactly. Hard constraint: the tracked
`company/gates.config` keeps its CONFIGURE-ME placeholders - new gates are
gates_detect PROPOSALS, never template edits.

## Read first (in order)

1. `CLAUDE.md`
2. `company/METHOD.md`
3. `.claude/hooks/_common.py` (block(), adherence_log(), read_json_file(),
   stamp_checksum(), current_branch(), _git())
4. `.claude/hooks/gate_stamp.py` - the salted-checksum integrity idiom the
   witness registry copies
5. `.claude/hooks/gates_detect.py` - you extend its proposal set (wave 1
   already added a "models" proposal; follow that shape and its tests)
6. `.claude/hooks/guard_secrets.py` - your risk scorer consumes its
   `--scan-branch` `SECRETS_JSON` output (shape is FROZEN, documented in
   its docstring)
7. `.claude/hooks/guard_frozen.py` - the shipped-migrations special case is
   the exact precedent for the accepted-ADR clause
8. `.claude/hooks/guard_commit.py` - you fix its branch check (#26)
9. `tests/hooks/` - test idioms (test_hooks.py, test_guard_secrets.py)
10. `company/templates/BRIEF-TEMPLATE.md` - risk_score parses the
    "## You own" section of briefs in this format

## You own

- `.claude/hooks/` (new: witness_check.py, risk_score.py, trace_check.py;
  edit: gates_detect.py, guard_frozen.py, guard_commit.py)
- `tests/hooks/`
- `company/witnesses.json` (new - you create and seed it)

Nothing else. Anything not listed is read-only to you. Doctrine docs
(GATES.md, ORCHESTRATOR.md, METHOD.md, templates, agents) belong to a
parallel workstream - do NOT touch them even to "help".

## Invariants in play (must not break)

- Hooks fail OPEN except immutability checks; Python 3.8 stdlib; bash 3.2.
- Every block/bypass logs to adherence.log via _common.
- All existing tests stay green (106 hook tests + 31 CLI tests at your
  branch point); never edit an existing test to make it pass.
- Writing hook-clean: straight quotes, ' - ', three dots.
- All spawned agents run opus; never override models.
- `SECRETS_JSON` shape is frozen - consume, never change.

## Frozen surfaces nearby (CR, never edit)

- `company/state/gates.status`, `adherence.log`, `costs.log`, `.env*`,
  lockfiles. Your hooks append via open() where the design says so.

## Scope (ordered)

1. **witness_check.py + company/witnesses.json** (#18).
   Registry shape:
   `{"$comment": ..., "version": 1, "witnesses": [{"id": "W-001", "task":
   "<slug>", "file": "<repo-rel>", "must_contain": "<literal substring>",
   "regex": false, "why": "<one line>", "added_at": "<iso>"}], "checksum":
   "<c.stamp_checksum over the canonical JSON of everything except
   checksum>"}`.
   CLI modes: default/`--check` (validate checksum FIRST - a mismatch means
   hand-edit, FAIL loudly; then each witness: file exists AND contains
   marker; human table + final `WITNESS_JSON: {"ok": bool, "failed":
   [ids], "count": N}`; exit 0/1), `--add --file F --contains S --task T
   --why W [--regex]` (assign next W-NNN, recompute checksum, adherence
   INFO line), `--remove W-NNN --why W` (same, removal never silent).
   Registry mutations ONLY through the CLI. Seed the registry with three
   witnesses from wave 1 (pick the exact load-bearing substrings from the
   real files): (a) guard_secrets.py anthropic-before-openai pattern
   ordering, (b) cost_capture.py compaction clamp
   (`max(0, file_total` line), (c) guard_secrets.py `SECRETS_JSON:` emit.
   gates_detect: propose `{"name": "witnesses", "command": "python3
   .claude/hooks/witness_check.py", "blocking": true}` FIRST in proposal
   order, only when company/witnesses.json exists with >= 1 witness.
2. **risk_score.py** (#19). CLI, advisory, ALWAYS exit 0:
   `python3 .claude/hooks/risk_score.py [--base <ref>] [--brief <path>] [--json]`.
   Defaults: base = merge-base of main and HEAD; brief from
   active-task.json "brief". Signals over `git diff --numstat` /
   `--name-only base...HEAD`: size 0-15 (thresholds 200/800 changed
   lines), out-of-ownership 10/path (parse the brief's "## You own"
   bullet list of dirs; a path outside all of them scores), frozen
   proximity 15 direct match of frozen-surfaces.json patterns (always +
   surfaces) / 5 for a sibling (same directory as a frozen match),
   test-ratio 0-15 (source lines changed vs test lines changed; >400 src
   with <10% test lines = 15), sensitive paths 10 (any of: migrations
   dirs, .claude/hooks/, company/gates.config, .claude/settings.json),
   secrets 25 (run guard_secrets.py --scan-branch <base>, parse
   SECRETS_JSON hits). Bands: <25 low, 25-49 medium, >=50 high. Output:
   human signal table + `RISK_JSON: {"score": N, "band": "...",
   "signals": {...}, "recommendation": "..."}` + one adherence INFO line
   (hook name risk_score). Missing brief -> skip ownership signal, note
   it in output (still exit 0).
3. **trace_check.py** (#22). CLI:
   `python3 .claude/hooks/trace_check.py [--spec <path>]`.
   Default spec: newest .md in company/specs/ containing FR- IDs; none ->
   print "no spec with FR IDs" and exit 0. Extract IDs matching
   `\b(FR|BR)-[A-Z0-9]+-\d+\b` (also accept `FR-\d+`). For each ID:
   traceable = appears in >= 1 test file (tests/ dirs, test_*/. spec./
   _test. names) AND >= 1 non-test tracked source file (git ls-files for
   the file set; search file contents). Human matrix + `TRACE_JSON:
   {"total": N, "orphans": [ids], "ok": bool}`; exit 1 if orphans.
   gates_detect: propose `{"name": "trace", "command": "python3
   .claude/hooks/trace_check.py", "blocking": true}` only when a spec
   with FR IDs exists in company/specs/; order after tests, before audit.
4. **gates_detect audit gate** (#21): per stack - node: `npm audit
   --omit=dev --audit-level=high` (pnpm: `pnpm audit --prod
   --audit-level=high`; yarn: `yarn npm audit --severity high`); python:
   `pip-audit` (only when pip-audit is on PATH - follow the existing
   split_invocable skip idiom). ALWAYS LAST in proposal order.
5. **guard_frozen.py accepted-ADR clause** (#20 enforcement half): in the
   Edit/Write/MultiEdit path, if the target's repo-relative path matches
   `company/adr/*.md` AND the ON-DISK file contains a line starting
   `Status: accepted` -> block: "accepted ADRs are immutable - write a new
   ADR that supersedes it (Status: superseded-by-ADR-NNN is applied by the
   CEO via CR), never edit the decision itself." Proposed/absent files
   stay editable. Follow the shipped-migrations clause exactly (fail-safe
   direction on error, same as migrations).
6. **guard_commit branch-check fix** (#26): current_branch must reflect
   the tree the git command runs in. Use the payload's "cwd" field when
   present and a git repo (git -C <cwd>); fall back to root. Regression
   test: temp repo + `git worktree add` fixture, payload cwd = worktree on
   a task branch, active task set, commit command -> ALLOWED; same
   payload with cwd = main checkout -> BLOCKED.
7. **Tests** for every item above in tests/hooks/ (new module(s) fine):
   witness checksum tamper / missing marker / regex mode / empty registry
   exit 0 / add-remove recompute; risk bands + ownership parse + missing
   brief; trace orphan / traceable / no-spec exit 0; gates_detect
   proposal-order (witnesses first, audit last, trace conditional);
   guard_frozen accepted vs proposed ADR; guard_commit worktree fixture.

## Integration seams

- The doctrine workstream (parallel, not yours) documents your tools in
  GATES.md/ORCHESTRATOR.md using these EXACT contract points: gate names
  `witnesses`, `trace`, `audit`, `models`; CLI paths as above; RISK_JSON
  bands low/medium/high; witness IDs W-NNN. Keep them stable.
- You guarantee: witness_check --check output ends with the WITNESS_JSON
  line; risk_score always exits 0; trace_check exits 1 only on orphans.

## Definition of Done

Universal DoD plus:
- [ ] Both suites green, run directly and pasted:
      `python3 -m unittest discover -s tests/hooks -q` AND `npm test`.
      Template gates.config untouched.
- [ ] `python3 .claude/hooks/witness_check.py` green on the seeded registry
      (paste it)
- [ ] `python3 .claude/hooks/risk_score.py --base main` runs clean on your
      own branch (paste it)
- [ ] No edits outside owned paths
- [ ] Commits per company/GIT.md: conventional, `Task: wave2-enforce`
      trailer, explicit paths (never git add -A; never stage
      company/state files or gates.config)
- [ ] Report per company/templates/REPORT-TEMPLATE.md

## Fallback assumptions

- OQ-W2-01: numstat binary files show "-" -> FALLBACK: count as 0 lines.
- OQ-W2-02: brief "You own" parse ambiguity -> FALLBACK: take every
  backticked path in list items under the "## You own" heading until the
  next "##"; treat trailing "/" as directory prefix match.
- OQ-W2-03: witness added_at -> FALLBACK: current UTC ISO minute from
  `date -u`; determinism not required.
- OQ-W2-04: sibling definition for frozen proximity -> FALLBACK: changed
  file whose dirname equals the dirname of any file matching a frozen
  pattern in the repo at HEAD.
- OQ-W2-05: risk recommendation strings -> FALLBACK: low = "standard
  verification", medium = "extra spot-reads", high = "auditor dispatch
  mandatory".

## Out of scope

- ALL doctrine/docs: GATES.md, METHOD.md, ORCHESTRATOR.md, LOOPS.md,
  templates, agent definitions, company/adr/ content (parallel workstream)
- README rows (docs-librarian pass after the wave)
- RELEASE/acceptance/postmortem (wave 3); lessons loop; loop workers
- Any change to company/gates.config template content or models.json

## Report back

Facts: what changed (paths), both suite outputs + witness_check +
risk_score outputs pasted, scope checklist, ownership diff summary
(`git diff --name-only task/wave1-enforcement..HEAD`), CRs filed,
deviations, worries, and 1-3 proposed witness markers for what YOU
shipped (the CEO records them post-merge).
