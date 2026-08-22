# BRIEF: hp-guards

_Type: program-workstream (L2 of the harness-port program).
Spec: `company/specs/spec-harness-port.md` - read ONLY the FR-HP-10 through
FR-HP-17 blocks and the OQ rows named below. The rest of the spec is not yours.
Lead: tech-lead. Date: 2026-08-13. Tracking issue: #99._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Four enforcement defects, all found by diffing a fork against this repo, none of
them in that fork's own changelog. Two are live enforcement ESCAPES: a git
command carrying a separated-argument global has its subcommand mis-parsed, so
`git -C sub commit` slips past the commit gate and `git -C sub push origin main`
slips past the owner-only protected-branch push check; and `is_source` exempts
any path with a `company/`, `docs/`, `.claude/` or `.github/` segment ANYWHERE in
it, so `app/company/billing.py` is ungated source today. One is a live
FALSE-BLOCK: the audit verdict is recorded by testing whether a string appears
anywhere in the payload, so an auditor that merely NAMES the verdict vocabulary
is recorded as a rejection - it has already cost four blocked commits against
four passing audits. The fourth is a block message that misleads.

Success is that all four are closed, each with a test that fails against today's
code. The hard constraint: **every one of these is a hook, and hooks fail OPEN.**
You are tightening what gets CAUGHT, which means you are also creating new ways
to BLOCK work that used to pass. Every new block must be correct, and FR-HP-11
exists because one of these fixes creates a false block if you land it alone.

## Read first (in order)

1. `CLAUDE.md` (project canon - Python 3.8 stdlib only, the two real gate suites)
2. `company/METHOD.md` (mechanism 5 and the client posture: a hook's block
   message is a RECIPE the blocked agent follows, not a scolding)
3. `.claude/hooks/guard_commit.py` (whole file - `git_subcmd`, the branch checks,
   the protected-branch rules)
4. `.claude/hooks/guard_secrets.py` (its duplicated copy of the same parser)
5. `.claude/hooks/guard_spec.py` (`is_source` and `EXEMPT_DIRS` only)
6. `.claude/hooks/guard_provenance.py` (the verdict recording site and the mode D
   block message only - the ledger locking and audit scope belong to L5 in wave 2)
7. `company/specs/spec-harness-port.md`, FR-HP-10 through FR-HP-17 only, plus
   OQ-HP-09 and OQ-HP-12. Those blocks carry acceptance criteria with concrete
   values; implement to them exactly.
8. `/Users/redomic/Documents/Projects/DevMesh/.claude/hooks/` - the working
   reference for all four fixes. Diff against it when ambiguous. It is a
   REFERENCE, not a specification: it is a polyrepo working copy, so ignore its
   `_SUBREPOS`, `seg_git_dir`, `commit_repo_root` and `repo_tree_hashes`.

## You own

- `.claude/hooks/guard_commit.py`
- `.claude/hooks/guard_secrets.py`
- `.claude/hooks/guard_spec.py` - **the `is_source` function only.** L4 owns the
  torn-read path in wave 2. Do not touch anything else in that file.
- `.claude/hooks/guard_provenance.py` - **the verdict parsing and the mode D
  reason string only.** L5 owns ledger locking and the audit scope in wave 2. Do
  not touch anything else in that file.
- `tests/hooks/test_guard_parsers.py` (new file, yours to create)

Nothing else. L1 is rewriting `_common.py` in parallel; L3 owns `run-gates.sh`,
`gate_stamp.py`, `guard_models.py` and `guard_frozen.py`. Report anything you
need there; do not make it.

## Invariants in play (must not break)

- **Hooks fail OPEN.** Any internal error lets the action through.
- **The secrets guard is the one gate that never yields.** It blocks even under
  a declared hotfix. Your dedup must not weaken that by one line.
- **Protected-branch rules stay exactly as strict.** FR-HP-10 makes them reach
  MORE commands, never fewer. A bare `git commit` on a protected branch with an
  active non-hotfix entry must still block, byte-identically.
- Block messages are self-service recipes. Every message you change must still
  tell the blocked agent exactly what to do next.
- `unknown` verdicts pass. This hook's posture is fail-open, and an ambiguous
  audit is not a rejection (OQ-HP-09).
- Python 3.8, stdlib only.

## Frozen surfaces nearby (CR, never edit)

- `company/state/provenance-ledger.json` is frozen and is written ONLY by
  `guard_provenance` itself. You change how a verdict is COMPUTED, never how the
  ledger is written, and the stored verdict values must not change - old ledgers
  have to keep working.
- `company/frozen-surfaces.json` belongs to L3 this wave.

## Scope (ordered)

Land each step with its tests. Steps 1 and 2 are one unit - do not merge 1
without 2.

1. **FR-HP-10 - `git_subcmd` consumes separated-argument globals** (`-C`, `-c`,
   `--git-dir`, `--work-tree`, `--namespace`, `--exec-path`). Attached forms
   (`-Cdir`, `--git-dir=x`) consume one token only. The trap to get right:
   `git commit -C HEAD~1` is `--reuse-message`, NOT a path, so only tokens
   BEFORE the subcommand are scanned.
2. **FR-HP-11 - `-C`-aware branch resolution.** Judge the branch and stamp
   checks for a segment carrying `-C <path>` against THAT directory. This is an
   addition beyond the original line item, and it is mandatory: without it,
   FR-HP-10 creates a NEW false-block class, because `git -C
   .claude/worktrees/<slug> commit` on a task branch would suddenly be judged
   against the main checkout's protected branch. Flag this addition prominently
   in your report so the CEO can veto it without unpicking FR-HP-10.
3. **FR-HP-12 - `guard_secrets` delegates** to `guard_commit.git_subcmd` and
   deletes its own copy. Prove delegation rather than duplication with a
   monkeypatch test, and prove a staged secret behind `git -C x commit` is now
   blocked.
4. **FR-HP-13 - `is_source` anchors the exempt-directory test to the FIRST path
   segment.** Do NOT port the fork's `_SUBREPOS` depth-two rule. Note carefully
   what this widens: `dirty_source_paths` filters through this same function, so
   newly-source paths also start counting toward the provenance audit demand.
   That is intended.
5. **FR-HP-14 and FR-HP-15 - labeled verdict parser.** A labeled verdict line
   wins; disagreeing labels fail CLOSED to the negative; without a label a token
   counts only when it is the SOLE verdict token in the text; anything ambiguous
   is `unknown` and passes. `SHIPPING` and `RESHIP` must not match `SHIP`. The
   stored ledger values do not change. Add `response_text` to flatten Task
   content blocks so newlines survive and the labeled anchor can match.
6. **FR-HP-16 - mode D block reason names the offending self-authored dirty
   paths** (first few plus a count), because that state can predate this session
   and the agent otherwise cannot tell what it is being blocked on.
7. **FR-HP-17 - block-message ergonomics.** `guard_commit`'s branch recipe warns
   that a compound `switch && commit` is judged against the CURRENT branch, so
   the switch has to run as its own command first.

## Integration seams

- **L1 (this wave)** is rewriting `_common.py`. You import from it; you do not
  change it. If you need a kernel primitive, report it.
- **L4 and L5 (wave 2)** take over `guard_spec.py` and `guard_provenance.py`
  respectively. Leave those files in a state a second lane can build on: no
  half-finished refactors, no renamed shared helpers.
- You guarantee that `guard_commit.git_subcmd` is the single parser in the
  codebase; L5 may assume it.

## Definition of Done

- [ ] Every FR in scope (FR-HP-10 through FR-HP-17) implemented, tested, or
      explicitly deferred with a reason
- [ ] **Gates: run the two real suites from YOUR worktree root**, per
      `CLAUDE.md`: `python3 -m unittest discover -s tests/hooks -q` and
      `npm test`. Both green, pasted in your report. Do NOT run
      `bash company/run-gates.sh` - from a worktree it resolves to the MAIN
      checkout and gates somebody else's tree. L3 is fixing that this wave.
- [ ] The full existing hook suite still passes - 393 was the baseline. A test
      you had to EDIT to pass is a finding, not a fix.
- [ ] Every one of the four defects has a test that FAILS against current code -
      demonstrate it, do not assert it. State the before and after in the report.
- [ ] FR-HP-11 called out explicitly in the report as a scope addition, with what
      breaks if the CEO vetoes it
- [ ] Subprocess end-to-end coverage for the protected-branch behavior, both the
      new `-C` path and the unchanged bare-commit path
- [ ] No edits outside owned files or outside the two named FUNCTIONS in the two
      shared files; zero frozen surfaces patched locally
- [ ] Commits follow `company/GIT.md`: conventional, `Task: hp-guards` trailer,
      explicit staged paths, never `git add -A`
- [ ] Report per `company/templates/REPORT-TEMPLATE.md`, with 1-3 witness
      candidates

## Fallback assumptions

- OQ-HP-09: an ambiguous verdict -> FALLBACK: record `unknown`, and `unknown`
  passes. Matches today's fail-open posture. Tag `# OQ-HP-09 assumption`.
- OQ-HP-12: `-C`-aware branch resolution -> FALLBACK: build it (step 2), and
  flag it in the report for CEO veto. Tag `# OQ-HP-12 assumption`.

## Out of scope

- Ledger locking, the audit scope narrowing, and `delegated_with_dispatches`.
  All L5, wave 2.
- The `guard_spec` torn-read fail-open path. L4, wave 2.
- `_SUBREPOS`, `seg_git_dir`, `commit_repo_root`, `repo_tree_hashes` from the
  reference implementation - polyrepo-specific, do not port.
- Anything about commit-versus-merge gate timing. Parked owner decision.
- `company/gates.config`, `package.json`, `install.sh`, `update.sh`,
  `.github/workflows/`.

## Report back

Facts only: what changed (paths), both suites' output pasted, the FR checklist,
the before-and-after for each of the four defects, ownership diff summary, CRs
filed, deviations and why, worries for the CEO, and your witness candidates.
