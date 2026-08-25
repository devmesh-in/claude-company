# SPEC: AI-SDLC harness rework

_Type: program. Author: product-manager. Date: 2026-08-25._
_Status: SPEC-READY._
_Slug: `ai-sdlc-rework`. Prefix: ASR._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

## Context / rationale - four laws

This harness is an AI SDLC, not a human SDLC with agents in the seats. Human
process manages intent - approvals, sign-offs, accountability - because humans
have private context, misaligned incentives, and egos. Agents have none of
those. What agents have is confabulation: they sincerely report things that
never happened. So the harness manages evidence, not intent.

Four laws drive every mechanism:

1. **Attention is the scarce resource.** An agent with a narrow scope goes
   deep; a broad prompt goes shallow. Decomposition into sealed briefs IS the
   quality engine, and it applies to the coordinator too - a bloated CEO
   context makes shallow decisions.
2. **Self-report is not evidence.** Every "done" must be converted into proof
   the claimant cannot fabricate or reset: gates, tree-hash stamps, witnesses,
   trace checks. Blocks are reserved for the unrecoverable (secrets, the
   evidence record itself); everything recoverable is detected at merge, never
   permissioned mid-flight.
3. **Scripts sense, judges judge.** A script may only BLOCK on a context-free
   predicate - one that evaluates identically with zero knowledge of the
   session's intent (a path matches, a hash differs, a pattern fires, an ID
   lacks a test). Every situational question ("is this drift acceptable?",
   "was this reviewed enough?") is surfaced as a mechanical fact to an LLM
   judge who is NEVER the actor being judged. The seven-week log proves this
   dividing line: every hook that fought the work was a script guessing a
   situational fact (which tree, whose staleness, which session); every hook
   that never hurt anyone evaluates a context-free predicate. Rigid facts,
   flexible judgment.
4. **A rule is a mechanism or it is dead.** Prose is followed
   probabilistically; hooks are followed always. Doctrine that matters gets
   mechanized; doctrine not worth mechanizing gets deleted. Enforcement itself
   pays rent: a guard with no outcome-changing block on record is flagged for
   eviction (unrecoverable-class guards are rent-exempt).

The standing test stays DECISIONS #21: enforcement corrects behavior, it does
not exist for the sake of existing. Mechanisms are kept for depth/breadth,
never because we distrust the system the way companies distrust people.

**Evidence this spec cites (self-justifying):**

- `company/state/adherence.log` BLOCK counts (seven-week record):
  guard_commit 78, guard_frozen 24, guard_provenance 17, stop_gate 16,
  guard_models 14, guard_tests 12, guard_spec 6, no_slop 3, guard_secrets 3.
  `risk_score.py` has zero BLOCK lines and zero hook-event callers.
- DECISIONS #20 (2026-08-13): owner ruling on five weeks of log. KEEP
  `guard_secrets` (never fired because it read the wrong tree, not because
  there was nothing to find). DELETE hooks that fought the work because they
  were STATEFUL. The dividing line: stateless predicates stay.
- DECISIONS #21: a hook's fire count proves nothing; the question is whether
  the block ever changed an outcome. `guard_secrets` fired zero times and
  stays; `stop_gate` fired sixteen times and went because it corrected
  nothing.
- DECISIONS #22: YOU CANNOT BUILD A FAIL-CLOSED GATE ON STATE THE GATED PARTY
  CAN RESET. Six remediations of provenance audit-scope narrowing each created
  a new unlock. The 17 `guard_provenance` BLOCKs in the log are all
  `self-authored, no fresh audit` (Mode C) - a situational "does this work
  deserve an audit?" gated on an actor-resettable ledger.
- WORRIES P0: DECISIONS #19's risk band was never mechanized - `risk_score.py`
  has zero callers and is wired to no hook event. Audit-by-default replaces
  the band and closes this row's substance.
- WORRIES P2 "a clean delegated build gets NO independent audit": Mode C
  armed on self-authorship, not on risk, so a clean delegated merge skipped
  the auditor. Audit-by-default on every merge closes this.
- WORRIES P2 `guard_tests` resolves `test_scope` from the main checkout
  (worktree builders blocked). WORRIES P3 `guard_tests` gates md inside
  `tests/`.
- WORRIES P2 `pipefail` plus `printf | grep -q` is a latent FALSE-RED (9 sites
  in `tests/install/test_update.sh`, 3 in `tests/cli/test_cli.sh`).
- WORRIES P2 a suite run while another agent edits the same worktree is not
  evidence - informs per-gate isolation of output, not a second copy of the
  whole tree (see OQ-ASR-03).
- Owner vetoes respected: DECISIONS #1 (no model tiering; `guard_models`
  stays), #20/#21 (`guard_secrets` stays), accepted-ADR immutability stays.

## Part 1 - Product requirements

### Problem

The harness copied a human SDLC: permissioning mid-flight, rationing review by
predicted risk, and scripts that guessed situational facts (which tree, whose
staleness, whether this work "deserves" an audit). Seven weeks of
`adherence.log` show the cost: 17 provenance BLOCKs on an actor-resettable
ledger (DECISIONS #22), 24 frozen-surface BLOCKs of which lockfile and
`surfaces[]` mid-flight hits fought ordinary work, 14 model-routing BLOCKs of
which matching builtin overrides should have been ALLOW, and a P0 risk-band
that was never wired. Agents learned to route around the harness. That is the
failure mode DECISIONS #21 named.

### Goal and success metrics

Binary, checkable at integration:

- G1. `risk_score.py` is gone; no live caller, no settings wiring, no
  doctrine that tells the CEO to score a band before dispatching an auditor.
- G2. `guard_provenance.py` enforcement modes are gone; the dispatch-recording
  READ feed that `context_pin.py` and `session_start.py` consume still works.
- G3. Every BLOCK-to-ALLOW conversion listed in the BRs has an enumerated
  decision-table test; a mutation that re-BLOCKs the ALLOW cell fails that
  row.
- G4. `bash company/run-gates.sh` runs configured gates concurrently, preserves
  ladder order, per-gate logs, `gates.log`, and the stamp; a matching green
  stamp skips the run; any hash doubt runs.
- G5. The six CLAUDE.md suites are green. `trace_check.py` reports zero
  orphan ASR IDs.
- G6. Payload no longer ships ideation, standup, STATUS.md, or the two
  opt-in agents; those agents' doctrine lives in `company/EXTENDING.md`.

### Users and personas

| Persona | Posture | What changes for them |
|---|---|---|
| CEO session | Full tool access, hook-gated | Audit-by-default at merge; summaries not transcripts; no risk_score ritual |
| Dispatched lead / developer | Owns its directories | Worktree `test_scope`; lockfiles warn; frozen `surfaces[]` judged at commit |
| Auditor | Read-only | Brief is the negation of the builder's; dispatched on every merge |
| Field install | Inherits hooks verbatim | Smaller payload; parallel gates; stamp reuse |

### User stories and acceptance criteria

US-ASR-1: As a builder, I can edit a lockfile without a mid-flight BLOCK, so
that dependency work is not permissioned by a script.
  - AC: given a Write to `package-lock.json`, when the hook runs, then exit 0
    and an adherence.log WARN line exists; `.env` still exits 2.

US-ASR-2: As a worktree builder, I can edit tests my brief granted, so that
the grant in MY tree is the grant that counts.
  - AC: given worktree `test_scope: true` and main `test_scope: false`, when
    I edit a test file in the worktree, then ALLOW.

US-ASR-3: As a CEO, I can merge only after a falsification audit, so that a
clean delegated build cannot skip independent read.
  - AC: company and auditor doctrine dispatch the auditor on every merge;
    no risk-band or arming language remains in live runbooks.

### Functional requirements

- **FR-ASR-01:** `company/METHOD.md` opens with the four-law philosophy
  preamble (attention, evidence, scripts-sense-judges-judge, mechanism-or-dead)
  and the DECISIONS #21 standing test. Frozen-surface doctrine in the same
  file describes merge-time drift detection, not mid-flight `surfaces[]`
  blocking.
  - AC: the four laws are present as numbered prose; no sentence claims a
    script judges situational intent.
- **FR-ASR-02:** Delete `.claude/hooks/risk_score.py` and every live
  reference (COMPANY.md step 6, doctrine tests that pin the invocation,
  models/docs that treat the band as a dispatch trigger). Audit-by-default
  replaces the band (closes WORRIES P0 and the substance of DECISIONS #19).
  - AC: `rg risk_score` over hooks, settings, live skills, live agents, and
    `company/*.md` (not shipped historical specs/briefs) returns nothing
    load-bearing.
- **FR-ASR-03:** Extract the dispatch-recording READ feed that
  `context_pin.py` and `session_start.py` import from `guard_provenance`
  (`read_ledger`, `dispatches_for`, `ledger_key`, `execution_decision`,
  `tracking_untracked`, `roster`, and the helpers those need) into
  `.claude/hooks/dispatch_feed.py`. Rewire both callers. Then delete
  provenance enforcement modes A/B/C and unwire every `guard_provenance.py`
  settings binding (PreToolUse, PostToolUse, Stop).
  - AC: settings.json has zero `guard_provenance.py` commands;
    `EXPECTED_WIRING` matches; pin and digest still render dispatch counts
    from an existing ledger.
- **FR-ASR-04:** Sweep `.claude/hooks/_common.py` for helpers only the
  deleted hooks called; delete those helpers. Leave shared helpers.
  - AC: a comment at each deletion site names FR-ASR-04, or the sweep finds
    nothing unique and a test says so.
- **FR-ASR-05:** `guard_commit.py` judges the ACTING tree (the tree the
  commit happens in via `c.acting_tree`), never the main checkout, for
  branch, stamp, and gates.config. Adds commit-time frozen-surface drift:
  BLOCK only an UNDECLARED change to a path matching
  `company/frozen-surfaces.json` `surfaces[]` (path matches AND no file in
  `company/change-requests/` contains that path as a substring). The
  predicate is context-free.
  - AC: decision-table BR-ASR-03; a declared CR containing the path ALLOWs;
    an undeclared `surfaces[]` hit BLOCKs; `.env` is not this sensor (still
    `guard_frozen`).
- **FR-ASR-06:** `guard_tests.py` resolves `test_scope` from the target
  worktree's `active-task.json` (via `c.task_state_root`); exempts non-source
  extensions `.md`, `.json`, `.txt` under a `tests/` (or sibling test-dir)
  segment. Instrument protection for source test files stays.
  - AC: decision-table BR-ASR-04; `tests/foo.md` ALLOW without grant;
    `tests/foo.py` BLOCK without grant.
- **FR-ASR-07:** `guard_models.py` ALLOWs a builtin spawn whose `model`
  override exactly matches the pin; BLOCKs a mismatch and a missing
  override. DECISIONS #1 stands: no tiering, no "close enough" aliases.
  - AC: decision-table BR-ASR-05 covering match / mismatch / missing /
    hotfix / no-builtins-section / roles-over-builtins.
- **FR-ASR-08:** `guard_frozen.py` demotes lockfile patterns (`*.lock`,
  `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`,
  `Cargo.lock`) from BLOCK to WARN (adherence.log WARN line, stderr note,
  exit 0). `.env` / `.env.*` (except documented placeholders),
  `company/state` run artifacts, `witnesses.json`, and accepted ADRs stay
  hard BLOCK. `surfaces[]` mid-flight blocking is removed.
  - AC: decision-tables BR-ASR-01 and BR-ASR-02; FrozenBaselineAgreement
    still holds for the remaining always-BLOCK baseline (lockfiles leave
    both ALWAYS_DEFAULTS and the registry `always` list together).
- **FR-ASR-09:** `company/run-gates.sh` runs configured gates as background
  jobs then `wait`, bash 3.2 compatible (no `wait -n`, no GNU `readlink -f`).
  Ladder prints in config order after all jobs finish. Per-gate logs still
  land under `company/state/gate-output/`. `gates.log` still gets one line.
  Stamp still goes through `gate_stamp.py`.
  - AC: two gates in one config both run; ladder order matches config order
    even if the slower gate is listed first; a red gate still fails the
    runner.
- **FR-ASR-10:** Before running, if `gate_stamp.py --check` exits 0 (green,
  fresh, valid checksum, work_hash matches), the runner early-exits 0,
  reuses the existing stamp (does not rewrite it), prints a one-line reuse
  notice, and appends a `gates.log` line. Any doubt - missing stamper,
  missing stamp, red, stale, malformed, checksum fail, hash `no-git`,
  stamper non-zero - means RUN, never skip.
  - AC: decision-table BR-ASR-06.
- **FR-ASR-11:** Fix the pipefail/EPIPE false-red class: every
  `printf ... | grep -q` site in `tests/install/test_update.sh` (9) and
  `tests/cli/test_cli.sh` (3) becomes a herestring `grep -q ... <<< "$OUT"`
  (or `grep -c` without `-q`). Capture a command's exit code before any pipe
  through `tail`.
  - AC: those files contain zero `printf | grep -q` pipelines.
- **FR-ASR-12:** Stdlib-only CLI `.claude/hooks/rent_report.py` reads
  `company/state/adherence.log` and prints, per hook, BLOCK/WARN counts in a
  window versus the hook's declared falsifiable claim. Unrecoverable-class
  guards (`guard_secrets`, `guard_frozen` hard-BLOCK set, `witness_check`,
  `trace_check`) are marked rent-exempt. Wired into `company/RELEASE.md` as a
  readiness rung and mentioned in `.claude/skills/gates/SKILL.md`.
  - AC: `python3 .claude/hooks/rent_report.py` exits 0 on this repo's log
    and names `guard_commit`.
- **FR-ASR-13:** Seam review: `.claude/skills/company/SKILL.md` gains a
  pre-spawn step (fresh-context read of the decomposition: lanes disjoint,
  briefs cover the requirement graph). Mechanical disjointness of brief
  "You own" globs is `.claude/hooks/seam_check.py` (stdlib). Overlap exits 1.
  - AC: two briefs whose You-own globs share a path fail; disjoint globs
    pass; missing briefs dir exits 0 (nothing to check).
- **FR-ASR-14:** Rewrite `.claude/agents/auditor.md`: the brief is the
  NEGATION of the builder's ("prove this broken"), with an attempt budget
  (OQ-ASR-08). Dispatched by default on every merge. Remove arming /
  risk-band / "large or risky" language from live runbooks (COMPANY.md,
  company skill, METHOD.md provenance paragraph, RELEASE.md R6 still
  names an opt-in security pass via EXTENDING.md, not a missing agent file).
  - AC: auditor.md does not mention risk band, provenance ledger recording,
    or `DO-NOT-SHIP` as a token the reader must avoid for a deleted parser.
- **FR-ASR-15:** Company skill and `tech-lead.md` carry the three-part
  subtask test: (1) self-contained in two sentences, (2) names its
  mechanical oracle, (3) fits one context window with room. Single-agent-first
  escalation only on named failure modes (context pressure, genuine parallel
  seams). CEO context budget: leads return summaries not transcripts;
  routine restart at the threshold in OQ-ASR-07.
- **FR-ASR-16:** `company/templates/REPORT-TEMPLATE.md` hard summary budget
  (~1-2k tokens: facts, pasted ladder, FR checklist). Bulky evidence lives
  under `company/evidence/<slug>/` and is referenced by path.
- **FR-ASR-17:** `company/templates/BRIEF-TEMPLATE.md`: each ordered Scope
  step names the mechanical oracle that proves it done. Frozen-surface note
  describes the merge-time drift model (undeclared `surfaces[]` change
  blocks at commit), not mid-flight CR-or-stop.
- **FR-ASR-18:** Dedup sweep across `.claude/agents/*.md` and the
  company skill: remove lines that restate what hooks enforce, and all
  live references to STATUS.md, ideation, standup, risk_score,
  guard_provenance, stop_gate.
- **FR-ASR-19:** Payload cuts: delete `company/IDEATION.md`,
  `.claude/agents/ideation-strategist.md`, `.claude/skills/brainstorm/`,
  `.claude/skills/standup/`. Move devops-engineer and security-reviewer
  content into a `company/EXTENDING.md` opt-in section; delete those two
  agent files. Fold load-bearing STATUS.md facts into RESUME.md; delete
  `company/state/STATUS.md`; stop scaffolding STATUS.md on install.
  `session_start.py` digests RESUME only. Update `package.json` pack lists
  and payload path lists (`lib/payload_paths.sh`, `install.sh`, `update.sh`)
  for every deleted or added shipped file. `qa-engineer` stays.
  `company/models.json` drops the deleted roles.
- **FR-ASR-20:** Tests: update `tests/hooks` for every hook change; add the
  BR decision-table rows; DELETE tests of deleted behavior (risk_score,
  provenance enforcement modes). Update install/update/CLI tests for payload
  and settings-fanout changes. Regenerate `.opencode/` via
  `node lib/render-opencode.js` after agent/skill changes.
- **FR-ASR-21:** `guard_models.py --check` EXPECTED_WIRING matches the
  post-cut settings.json (no provenance rows; Stop/PostToolUse groups that
  become empty are omitted).
- **FR-ASR-22:** `dispatch_feed.py` also carries `audit_verdict` and
  `response_text` (the parser `tests/harness/test_adapter.mjs` imports). A
  thin `.claude/hooks/guard_provenance.py` re-exports those two names so the
  frozen adapter test (do-not-touch from another session) keeps importing
  `guard_provenance`. The shim has no settings wiring and no BLOCK path.
  - AC: `import guard_provenance as g; g.audit_verdict("Verdict: HALT.")`
    still returns `do-not-ship`; settings.json does not invoke the shim as a
    hook.

### Business rules and validations

- **BR-ASR-01:** Lockfile BLOCK-to-WARN (FR-ASR-08) does not ship without an
  enumerated decision-table test covering every combination of inputs that
  reach the decision, with its expected verdict. Rows at minimum: each
  lockfile pattern WARNs (exit 0 + WARN log); `.env` BLOCKs; `.env.example`
  ALLOWs; `company/state/adherence.log` BLOCKs; accepted ADR BLOCKs; ordinary
  source ALLOWs. Pattern: the enumerated BLOCK-to-ALLOW table in
  `company/specs/spec-harness-port.md` (around line 772).
- **BR-ASR-02:** `surfaces[]` mid-flight BLOCK-to-ALLOW (FR-ASR-08) does not
  ship without a decision-table row: a path matching `surfaces[]` and not
  always-frozen ALLOWs at Edit/Write; the same undeclared path BLOCKs at
  `git commit` (FR-ASR-05); a CR whose body contains the path ALLOWs the
  commit.
- **BR-ASR-03:** Acting-tree stamp/branch judgment (FR-ASR-05) does not ship
  without a decision-table: commit in a worktree with a green acting-tree
  stamp ALLOWs even when main's stamp is stale; commit in a worktree with a
  stale acting-tree stamp BLOCKs even when main is green; unresolved `-C`
  falls through and does not invent a skip.
- **BR-ASR-04:** Worktree `test_scope` plus non-source exemption (FR-ASR-06)
  does not ship without a decision-table: worktree grant / main deny ->
  ALLOW; worktree deny / main grant -> BLOCK; no worktree file -> fallback
  to main; `.md`/`.json`/`.txt` under `tests/` ALLOW without grant; `.py`
  under `tests/` BLOCK without grant.
- **BR-ASR-05:** Builtin-spawn override ALLOW (FR-ASR-07) does not ship
  without a decision-table: override == pin ALLOW; override != pin BLOCK;
  missing override BLOCK; hotfix BYPASS; no `builtins` section ALLOW
  (fail-open); role also in `roles` uses the roles branch.
- **BR-ASR-06:** Stamp early-exit (FR-ASR-10) does not ship without a
  decision-table: green+matching hash -> skip (exit 0, stamp bytes
  unchanged); missing / red / stale / malformed / checksum-invalid /
  stamper-absent / `work_hash` failure -> RUN.
- **BR-ASR-07:** Dual-nature rule: `company/` stays generic; tracked
  `company/gates.config` keeps `CONFIGURE ME` placeholders. This program
  does not commit this repo's real gate commands.
- **BR-ASR-08:** Fail-open posture preserved. New paths exit 0 or allow on
  internal error. `witness_check.py` and `trace_check.py` (on an orphan)
  stay fail-loud. `seam_check.py` and `rent_report.py` are CLIs: overlap
  is loud for seam_check; rent_report fails open on a missing log.
- **BR-ASR-09:** Hooks stay Python 3.8 stdlib only. No new runtime state
  file in the packed payload (`package.json` already negates
  `company/state/**`).
- **BR-ASR-10:** Every FR/BR ID in this spec appears verbatim in an
  implementing code comment or a test name, so `trace_check.py` can see it.
- **BR-ASR-11:** Tests of deleted behavior are deleted, not skipped. A
  skip-green for a missing subject is the class CLAUDE.md forbids.
- **BR-ASR-12:** Owner-settled keeps: DECISIONS #1 (no model tiering),
  #20/#21 (`guard_secrets` stays), accepted-ADR immutability. Unrecoverable
  guards are rent-exempt.

### Scope

**In:**

- Spec, hook deletions and fixes, gate runner parallel + early-exit,
  pipefail test harness fix, rent report, seam check, auditor rewrite,
  prompt alignment, payload cuts, tests, opencode regen, witness updates
  via `witness_check.py` only.

**Out:**

- Committing or branching (working tree left for independent audit).
- Touching pre-existing uncommitted files from another session:
  `company/gates.config`, `company/specs/spec-harness-agnostic.md`,
  `tests/harness/test_adapter.mjs`, `company/state/.state.lock`.
- Model tiering (DECISIONS #1).
- Deleting `qa-engineer`.
- Porting polyrepo `HASH_EXCLUDES` of `*.md`/`*.txt`.
- Rebuilding a fail-closed provenance ledger (DECISIONS #22).
- Per-gate full-tree copies in the runner (OQ-ASR-03).

### UX notes

Hook BLOCKs still print a recipe to stderr and exit 2. Lockfile WARNs print a
one-line note to stderr, log WARN, and allow. Gate runner skip is one line
naming the reused hash, not a fake ladder. Rent report is a table a human
(or `/release`) can read.

## Part 2 - Build readiness

- **Owned directories:** `.claude/hooks/`, `.claude/agents/`,
  `.claude/skills/`, `company/` (canon, templates, EXTENDING.md, METHOD.md,
  RELEASE.md, run-gates.sh, frozen-surfaces.json, models.json, specs,
  state/RESUME.md), `lib/payload_paths.sh`, `install.sh`, `update.sh`,
  `tests/hooks/`, `tests/install/`, `tests/cli/`, `tests/harness/` except
  `tests/harness/test_adapter.mjs`. `.opencode/` is generated only via
  `node lib/render-opencode.js`.
- **Invariants in play:** dual-nature `company/`; fail-open hooks;
  checksum-sealed witnesses; accepted ADR immutability; content-based
  freshness (ADR-0002); CLAUDE.md six suites; no_slop.
- **Frozen surfaces touched:** none in `surfaces[]` for this repo (empty).
  Hook code that *implements* frozen-surface policy is not itself a frozen
  path. `company/witnesses.json` mutations only via `witness_check.py`.
- **Data model impact:** none (no schema). Ledger remains a file other
  hooks may read; nothing new writes Mode C audits.
- **Contracts impact:** settings.json hook wiring (additive deletion of
  provenance bindings); models.json roles map loses three keys;
  EXPECTED_WIRING table shrinks; STOP/PostToolUse events omitted if empty.
- **Open questions and chosen fallbacks:**
  - OQ-ASR-01: Where does the dispatch feed live? FALLBACK: new module
    `.claude/hooks/dispatch_feed.py`, not `_common.py` (keeps `_common`
    from absorbing a ledger). Tag `// OQ-ASR-01 assumption`.
  - OQ-ASR-02: Does deleting provenance break `test_adapter.mjs` (frozen)?
    FALLBACK: thin `guard_provenance.py` re-exports `audit_verdict` and
    `response_text` from `dispatch_feed`; no hook wiring. Tag
    `// OQ-ASR-02 assumption`.
  - OQ-ASR-03: Per-gate tree copies for parallel runs? FALLBACK: no copies;
    isolate stdout/stderr/logs only; same `PROJECT_ROOT`. Copying would
    fingerprint a different tree than the stamp. Tag `// OQ-ASR-03 assumption`.
  - OQ-ASR-04: How does a CR "name" a path? FALLBACK: any file under
    `company/change-requests/` whose contents contain the project-relative
    path as a substring. No YAML frontmatter required. Tag
    `// OQ-ASR-04 assumption`.
  - OQ-ASR-05: Early-exit still rewrite the stamp? FALLBACK: no; reuse
    bytes. Append `gates.log` with `status=green reused=1`. Tag
    `// OQ-ASR-05 assumption`.
  - OQ-ASR-06: Rent-report window default? FALLBACK: whole log; optional
    `--days N`. Tag `// OQ-ASR-06 assumption`.
  - OQ-ASR-07: CEO restart threshold? FALLBACK: after three lead reports
    in one session, or when the session says it is losing the plot,
    restart and re-read RESUME/DECISIONS/WORRIES. Tag
    `// OQ-ASR-07 assumption`.
  - OQ-ASR-08: Auditor attempt budget? FALLBACK: three falsification
    attempts, then report with what remains un-broken. Tag
    `// OQ-ASR-08 assumption`.
  - OQ-ASR-09: Empty Stop/PostToolUse after provenance cut? FALLBACK:
    omit the empty event groups from settings.json. Tag
    `// OQ-ASR-09 assumption`.
  - OQ-ASR-10: User STATUS.md already on disk in a field install?
    FALLBACK: leave it; do not scaffold a new one; session_start ignores
    it. Tag `// OQ-ASR-10 assumption`.
- **Verification plan:**
  - Each FR: implementing comment or test name (BR-ASR-10) plus the six
    suites in CLAUDE.md:
    `python3 -m unittest discover -s tests/hooks -q`
    `npm test`
    `bash tests/install/run_tests.sh`
    `bash tests/install/test_tui.sh`
    `bash tests/install/test_update.sh`
    `bash tests/harness/run_tests.sh`
  - BR-ASR-01..06: named decision-table test methods.
  - `python3 .claude/hooks/trace_check.py --spec company/specs/spec-ai-sdlc-rework.md`
    zero orphans.
  - `python3 .claude/hooks/witness_check.py --check` after registry updates
    via `--remove`/`--add` only.

## Spec-ready checklist (the Phase 0 gate)

- [x] Every FR has a stable ID and at least one acceptance criterion
- [x] Out-of-scope is explicit
- [x] Every open question has a single decided fallback
- [x] Owned directories are named and disjoint from other in-flight work
- [x] Frozen-surface needs are identified (none in surfaces[]; witnesses via CLI)
- [x] Data/contract impact stated
- [x] Verification plan covers every FR (six CLAUDE.md suites)

## Part 3 - Brief handoff

This program is executed in-session against this spec; no separate brief
file is required for the builder that already holds this document.
Derive any follow-up brief with `company/templates/BRIEF-TEMPLATE.md`.
