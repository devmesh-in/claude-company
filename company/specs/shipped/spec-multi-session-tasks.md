# SPEC: multi-session tasks (N task entries in one active-task.json)

_Type: feature. Author: product-manager. Date: 2026-07-26._
_Status: SPEC-READY._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

Solution of record: `~/.claude/plans/flickering-painting-pony.md` (owner-approved
2026-07-26, core-only scope). This spec does not reopen the approved shape; it
makes it buildable and checkable.

Tracking issues: TBD at dispatch - one per commit band in the staging plan
(normalizer + call-site migration; ledger v2; multi-task semantics; doctrine and
tests). Recorded in `company/state/active-task.json` `"issues"` before the first
builder spawn - the FR-DE-15 tracking gate blocks the dispatch otherwise.

## Part 1 - Product requirements

### Problem

`company/state/active-task.json` is a singleton dict, read through
`_common.active_task(root)` at one fixed path under `project_root(payload)`.
Every enforcement hook derives its decision from that one object: `guard_spec`
(brief existence), `guard_tests` (`test_scope`), `guard_models` (hotfix),
`guard_commit` (protected-branch block, hotfix), `stop_gate` (close gate),
`guard_provenance` (all five modes), plus the read-only `context_pin`,
`session_start`, `cost_capture`, and `risk_score`.

The owner runs several Claude Code sessions from the SAME main checkout.
Nothing distinguishes them: identical `CLAUDE_PROJECT_DIR`, identical cwd, the
same working tree, the same branch. Only `cost_capture.py` ever reads
`session_id`, and it uses it for a log column, not for state.

So when session B writes its task into that file, session A silently inherits
B's task. A's context pin flips, A's brief lookup resolves to B's brief, A's
`test_scope` grant flips, and A's execution decision flips. The concrete costs
observed:

1. **Provenance loss.** `guard_provenance.read_ledger` (`:302-303`) returns a
   FRESH ledger whenever the on-disk `task` field stops matching the active
   slug, and the next write persists that empty ledger. A's recorded dispatches
   and audits are gone. A is then spuriously blocked at commit (Mode C: "no
   audit recorded"), at Stop (Mode D), and at its next source edit (Mode E:
   "delegated but no dispatch") - for work it already dispatched and already had
   audited.
2. **Wrong-brief enforcement.** `guard_spec` validates A's source edits against
   B's brief path. An edit that is in scope for A is judged against a document
   that never mentioned it.
3. **Silent grant flips.** `test_scope` and `execution` are read from whichever
   task wrote last. A session can gain or lose a grant it never requested.
4. **Lying telemetry.** `context_pin` injects B's slug, execution mode, and
   dispatch count into A's turns; `session_start` digests the wrong task;
   `cost_capture` books A's tokens to B's slug.

The cost today is that the harness actively fights the owner's normal working
pattern, and it fights it in the worst possible direction: it removes recorded
evidence of verification, which converts verified work into work the gates
believe is unverified. The workaround (one session at a time, or manual ledger
repair) is exactly the process-under-pressure failure this product exists to
make impossible.

### Goal and success metrics

`company/state/active-task.json` holds N task entries. Task facts become
per-entry; working-tree facts stay global and shared, because with every session
in one checkout they are honest shared facts. Adding a second entry never makes
any gate weaker, except in three named, logged, doctrine-covered places.

Binary success signals, all must hold:

- **SM-1**: Two-part parity. (a) Under the NEW code, a v1 single-object file and
  the equivalent v2 one-entry file produce byte-identical exit code, stdout,
  stderr, and `adherence.log` line for every hook. (b) Against TODAY's code, one
  entry produces the identical decision, exit code, and adherence action /
  target / reason, and identical message text except for the deliberate doctrine
  rewording of FR-MST-25, which applies uniformly at every N. Proven by a
  parameterized parity suite, not by inspection.
- **SM-2**: Two entries A and B active, A's dispatches recorded, B added later:
  A's dispatches are still counted, the ledger is not wiped, and A is not
  blocked at Mode C, Mode D, or Mode E.
- **SM-3**: Two entries A and B, both `"execution": "delegated"`, one dispatch
  whose spawn prompt names only B: a main-checkout source edit still BLOCKS on
  A (Mode E), naming A's slug.
- **SM-4**: For every gate (`guard_spec`, `guard_tests`, `guard_commit`,
  `stop_gate`, `guard_provenance` Modes C/D/E, `guard_models`), there is a test
  proving that adding a second entry does not turn a block into an allow -
  except the three accepted weakenings, which have tests asserting they DO
  bypass, each with a BYPASS or GRANT line naming the responsible entry.
- **SM-5**: `_common.active_task` no longer exists, and no file under
  `.claude/hooks/` references it (asserted by a `hasattr` test and a grep test).
- **SM-6**: A field install carrying a legacy single-object `active-task.json`
  and a v1 `provenance-ledger.json` survives `claude-company update`: one edit
  through `guard_spec` and one through Mode E, neither spuriously blocked; the
  existing `active-task.json` is never rewritten or deleted by update.
- **SM-7**: `python3 -m unittest discover -s tests/hooks -q`, `npm test`, and
  `bash tests/install/run_tests.sh` all green.

### Users and personas

- **The CEO session (primary).** Two or more main Claude sessions in the same
  checkout, each dispatching, editing glue, and committing on its own task
  branch. Full write access to `company/state/`. It adds and removes its own
  entry, and must never destroy another session's entry or provenance.
- **The dispatched tech lead / developer (indirect).** Works in a worktree.
  Never writes `active-task.json`; is read-gated by it (`test_scope` in
  particular - see the existing WORRIES row about worktree builders resolving
  `test_scope` from the main checkout). This spec does not change that posture.
- **The auditor (read-only).** Its completion writes a global audit record
  keyed by `work_hash`. One auditor pass over one tree covers every entry's
  changes in that tree.
- **The install/update operator.** Runs `claude-company update` on a field
  install that has a live single-object file. Gets N-entry support with no
  migration step and no data loss.
- **The owner (escalation only).** Owns the decision that concurrency is a
  supported working mode (already given, 2026-07-26). Not consulted mid-build.

No new privilege surface. No new file. No new CLI.

### User stories and acceptance criteria

- **US-MST-1**: As a CEO session, I can add my task to `active-task.json` while
  another session's task is already there, and neither session's enforcement
  flips to the other's task.
  - AC: given a file holding entry A (`type: feature`, `brief:
    company/briefs/brief-a.md`, `execution: delegated`), when a second session
    appends entry B (`type: feature`, `brief: company/briefs/brief-b.md`), then
    `context_pin` renders one line per entry plus one shared tree line;
    `guard_spec` validates against BOTH briefs; and no field of A is changed on
    disk.

- **US-MST-2**: As a CEO session, my recorded dispatches and audits survive
  another session adding or removing its task.
  - AC: given entry A with two recorded dispatches and a fresh audit at the
    current `work_hash`, when entry B is added and then removed, then
    `read_ledger` still reports two dispatches for A and the audit still
    satisfies Mode C; no ledger write empties A's record.

- **US-MST-3**: As the harness, a second task in flight never lets an
  unverified edit through a gate that would have blocked it alone.
  - AC: given entries A and B both `"execution": "delegated"`, when exactly one
    dispatch is recorded and its spawn prompt names only `task/b`, then a source
    edit in the main checkout exits 2 with a message naming A, and
    `adherence.log` carries a BLOCK line naming A.
  - AC: given entry A with a brief and entry B with no `brief` field, when a
    source edit is attempted, then `guard_spec` exits 2 naming B (ALL, not ANY).

- **US-MST-4**: As a CEO session declaring a production emergency, my hotfix
  entry bypasses the waiver gates, and the bypass is visible to anyone reading
  the log or the next turn.
  - AC: given entries `[feature-a, hotfix-b]`, when a commit is attempted on
    `main`, then it is allowed and `adherence.log` carries a BYPASS line naming
    `hotfix-b`; and `context_pin` renders a `HOTFIX:hotfix-b` marker on every
    turn while that entry exists.

- **US-MST-5**: As an install/update operator with a legacy file, nothing
  breaks and nothing is rewritten.
  - AC: given an install whose `active-task.json` is a single object
    `{"task": "x", "type": "feature", "brief": ..., "execution": "delegated",
    "execution_why": "..."}` and whose `provenance-ledger.json` is v1 with
    `"task": "x"` and one dispatch, when `claude-company update` runs and then a
    source edit is attempted, then the edit is ALLOWED (the v1 dispatch migrated
    in memory), `active-task.json` is byte-unchanged on disk, and no v2 file is
    written until the next hook write.

- **US-MST-6**: As a CEO session closing my task, removing my entry leaves the
  other session fully intact.
  - AC: given entries A and B with ledger records for both, when A's entry is
    removed with a targeted Edit, then B's entry, B's ledger dispatches, and the
    global audits are unchanged; and when B's entry is then removed, the file
    holds `{"version": 2, "tasks": []}` and every gate behaves exactly as it
    does with the file absent.

### Functional requirements

Stable IDs. Every FR is later implemented, tested, or explicitly deferred - the
traceability gate checks these IDs against the PR. Each consumer FR states its
rule AND the invariant that rule protects, so it can be checked against the
standing risk: going from 1 to N tasks must never silently disarm a gate.

#### Schema, normalizer, API surface

- **FR-MST-01**: `company/state/active-task.json` gains a v2 shape:
  `{"version": 2, "tasks": [ <entry>, ... ]}` where `<entry>` carries exactly
  today's single-object fields (`task`, `type`, `brief`, `test_scope`,
  `execution`, `execution_why`, `issues`, `reclassified_why`, and any
  project-added key). A LIST, not a slug-keyed object: insertion order is the
  stable render order for `context_pin` and `session_start`, and a list is what
  a targeted Edit appends to without touching a sibling.

- **FR-MST-02**: `_common.active_tasks(root) -> list` replaces
  `_common.active_task`. It normalizes in this exact order (BR-MST-01):
  non-container (None, str, int, ...) to `[]`; a dict carrying a `tasks` list to
  that list, keeping only dict members; any other dict to `[raw]` (the legacy
  field-install case, including `{}` to `[{}]`); a bare list to its dict
  members; anything else to `[]`. `{"tasks": []}` normalizes to `[]` and must be
  behaviorally identical to a missing file, so that removing the last entry
  lands back in the no-active-task state. Never raises.

- **FR-MST-03**: `_common.active_task` is REMOVED, not shimmed. A shim returning
  `tasks[0]` would enforce against one arbitrary entry; a shim returning `None`
  for N>1 would disarm every gate at once. Because an `AttributeError` inside a
  hook's `try` lands in `except: sys.exit(0)` (a silent allow), the removal is
  closed mechanically: all call sites migrate in one commit; a test asserts
  `not hasattr(_common, "active_task")`; and a grep test fails on any residual
  `\bactive_task\s*\(` under `.claude/hooks/`.

- **FR-MST-04**: `_common` gains shared helpers so the ANY/ALL logic lives in
  one place instead of being re-derived in nine hooks: `has_active_task(tasks)`,
  `hotfix_entry(tasks)` (the first entry with `type == "hotfix"`, else None),
  `entries_of_type(tasks, types)`, `slugs(tasks)` (truthy `task` values, order
  preserved), and `slug_list(tasks, cap=3)` (a display string, cap applied,
  overflow rendered as `and <n> more`). `guard_provenance.execution_decision`,
  `valid_issues`, and `tracking_untracked` stay where they are and keep their
  single-entry signatures - they are already per-entry predicates.

#### Per-consumer semantics (one FR per consumer hook)

- **FR-MST-05** (`guard_spec.py:67-85`) - **ALL over non-hotfix entries.**
  Order: (a) no entries -> BLOCK with `NO_BRIEF_MSG`, exactly as today when the
  file is absent; (b) filter out entries whose `type` is `hotfix`; if none
  remain, `log_bypass` and allow (today's hotfix behavior at N==1); (c) BLOCK if
  ANY remaining entry lacks a `brief` or names a brief file that does not exist,
  message naming the offending slug(s).
  _Invariant protected:_ no source edit happens without a written brief covering
  it. The edited path is not attributable to an entry, so "some entry has a
  brief" would be an unrelated-edit hole. ALL is strictly stronger than today
  and reduces to today at N==1.

- **FR-MST-06** (`guard_tests.py:52-54`) - **ANY.** `test_scope_open(root)` is
  true if ANY entry has `test_scope is True`. When `len(tasks) > 1` and the
  grant opens, write an `adherence.log` GRANT line naming the granting entry
  before allowing.
  _Invariant protected:_ tests are the oracle and are edited only under an
  explicit brief-granted scope. This is accepted weakening #2 (RISK-MST-02):
  entry B's blanket grant unlocks test edits for entry A. Made auditable rather
  than closed, because glob-scoped grants are out of scope.

- **FR-MST-07** (`guard_models.py:66-68`) - **ANY hotfix.** `is_hotfix(root)` is
  true if ANY entry has `type == "hotfix"`; the logged bypass names that entry's
  slug.
  _Invariant protected:_ all-opus routing (DECISIONS #1). Routing is cost and
  quality, not a safety invariant, and blocking a declared production emergency
  behind an unrelated entry is the worse failure. This is part of accepted
  weakening #1 (RISK-MST-01).

- **FR-MST-08** (`guard_commit.py:122-160`) - **presence + ANY hotfix.** The
  protected-branch commit block arms iff the entry list is non-empty (an empty
  list keeps today's founding-commit exemption); it is bypassed, with a BYPASS
  line naming the slug, if ANY entry is `hotfix`. The whole-gate hotfix bypass
  below it is likewise ANY. The gate-stamp logic at `:161-189` is untouched and
  stays a tree fact.
  _Invariant protected:_ work belongs on a task branch, and nothing commits over
  red or stale gates. The branch is one branch for all sessions in this
  checkout, so the stamp and the branch are honest shared facts; only the
  message rendering is per-entry (FR-MST-30).

- **FR-MST-09** (`stop_gate.py:29-46`) - **per-entry exempt types, ANY
  blocker.** Filter to entries whose `type` is outside `{quick, hotfix}`; if
  none remain, exit 0 (today's behavior at N==1); otherwise run the existing
  stamp check and emit the block decision if it is red or stale, naming the
  remaining slugs (`slug_list`, cap 3).
  _Invariant protected:_ a session does not finish with the tree red or stale
  under a task that owes gates. `[quick, feature]` therefore blocks - correct,
  because the tree is red with a feature in flight; the exemption belongs to the
  quick entry, not to the tree.

- **FR-MST-10** (`cost_capture.py:195-197`) - **joined slugs.** The task column
  becomes `"+".join(sorted(slugs(tasks))[:3])`, with `+more` appended when more
  than three exist, and `-` when the list is empty. Exactly one slug renders
  exactly as today.
  _Invariant protected:_ none (telemetry only). Per-message attribution needs
  session-keyed state, which is out of scope; this records what was in flight,
  which is true.

- **FR-MST-11** (`risk_score.py:221-225`) - **sole entry only.** With no
  `--brief`: zero entries returns today's note; exactly one entry uses its
  `brief` (today); more than one returns a note naming the count and telling the
  caller to pass `--brief`. Exit code unchanged (the brief is one input among
  several).
  _Invariant protected:_ risk scoring is advisory, never a gate. Guessing which
  brief applies would silently score the wrong document.

- **FR-MST-12** (`session_start.py:50-66`) - **one digest pair per entry.** For
  each entry (cap 3, then a single `and <n> more` line): the
  `active-task: <slug> (<type>) brief=<brief>` line and the
  `execution: ... | dispatches: ... | self-authored: ... | team: ...` line,
  where `dispatches` is that entry's per-slug count and `self-authored` is the
  global count. The existing `MAX_LINES` truncation is unchanged.
  _Invariant protected:_ none (read-only digest). Named here because a wrong
  digest is how a session starts believing it owns another session's task.

- **FR-MST-13** (`context_pin.py:42-73`) - **N==1 byte-identical; N>1 per-entry
  plus one tree line.** With exactly one entry, emit today's exact line(s),
  including the standalone idle line. With more than one entry, emit one terse
  line per entry (cap 3, then `and <n> more`) carrying slug, type, `exec=`,
  `disp=` (per-slug), and the `iss=0` drift segment, with ` idle` appended to a
  drifty entry's own line instead of the standalone idle line; then ONE shared
  line prefixed `tree:` carrying the global `self=<n>`. While any entry is
  `hotfix`, render a `HOTFIX:<slug>` marker (RISK-MST-01 mitigation).
  _Invariant protected:_ the per-turn injection stays about one terse line per
  fact and never lies. `self=` is a tree fact and would be a lie on a per-entry
  line; hence the separate `tree:` line.

#### Provenance ledger v2

- **FR-MST-14**: `company/state/provenance-ledger.json` gains a v2 shape:
  `{"version": 2, "tasks": {"<slug>": {"dispatches": [...], "nudge_state":
  {...}}}, "unattributed_dispatches": [...], "self_authored": [...], "audits":
  [...], "checksum": "..."}`. Dispatches and nudge state are per-slug; audits,
  `self_authored`, and the `work_hash` they are keyed on stay global. An auditor
  pass over the tree at hash H covers every entry's changes in it, so demanding
  N audits of one identical tree would be both wasteful and dishonest.

- **FR-MST-15**: The slug-mismatch wipe at `guard_provenance.py:302-303`
  (`if raw.get("task") != slug: return fresh`) is DELETED. A v2 ledger is never
  reset because the set of active slugs changed. The checksum-tamper reset is
  KEPT verbatim: unverifiable history still counts as no verification.

- **FR-MST-16**: v1 ledger migration, IN MEMORY ONLY, inside `read_ledger`:
  when the parsed ledger is v1 (no `version: 2`), let `s = raw["task"]`. If the
  checksum is invalid, return a fresh v2 ledger. Else if `s` is in the current
  active slugs, return a v2 ledger with `tasks = {s: {"dispatches":
  raw["dispatches"], "nudge_state": raw["nudge_state"]}}` and `self_authored`
  and `audits` carried over. Else return a fresh v2 ledger - deliberately
  preserving today's wipe for that one case, because carrying a stale-slug audit
  forward would newly satisfy Mode C and be WEAKER than today. `read_ledger`
  never writes; the migrated shape persists on the next `write_ledger`.

- **FR-MST-17**: `write_ledger(root, ledger)` prunes `tasks` down to the
  currently active slugs before writing (a slug with no entry is a closed task),
  then writes atomically with a fresh checksum exactly as today.
  `unattributed_dispatches`, `self_authored`, and `audits` are never pruned by
  slug. Read paths never write: `context_pin` and `session_start` both call
  `read_ledger` and must leave the file untouched.

- **FR-MST-18** (Mode B-pre, `guard_provenance.py:442-469`) - **dispatch
  attribution.** With exactly one entry, the dispatch is attributed to it
  unconditionally (byte-identical to today). With more than one, it is
  attributed to EVERY entry whose slug appears in the spawn prompt or
  description; doctrine already requires the spawn prompt to name `task/<slug>`,
  so this costs nothing new. A dispatch matching no entry is appended to
  `unattributed_dispatches`, which satisfies NO entry's delegated requirement,
  and writes an adherence line so the false negative is diagnosable. The
  FR-DE-15 tracking gate still runs BEFORE the dispatch is recorded, now as
  ANY-hotfix bypass then ALL-tracking over feature/program entries.

- **FR-MST-19** (Mode A, `:395-439`) - **per-entry nudge, global telemetry.**
  `self_authored` stays a global list appended once per distinct path. The
  self-idle nudge condition is evaluated per entry (`type` in
  `{feature, program}`, `execution_decision == "self"`, per-slug dispatch count
  zero) against that entry's own `nudge_state`. At most one nudge is emitted per
  invocation - the first qualifying entry in list order; the others fire on
  subsequent edits. Mode A never blocks.

- **FR-MST-20** (Mode C, `:502-540`) - **ANY hotfix, global audit, per-entry
  message.** Order: git-commit segment detection, manifest present, entries
  non-empty (empty exits as today), ANY-hotfix bypass logging the hotfix slug,
  worktree/merge exemptions, `dirty_source_paths` (global), `fresh_audit`
  (global). On block, the message names the non-exempt slugs (`slug_list`, cap
  3) in place of `<slug>`.
  _Invariant protected:_ nothing self-authored integrates on the authority of
  the context that produced it. Dirty paths and audits are tree facts; only the
  hotfix waiver and the message are per-entry.

- **FR-MST-21** (Mode D, `:543-568`) - **per-entry exempt types, ANY blocker.**
  Filter to entries whose `type` is outside `{quick, hotfix}`; if none remain,
  exit 0. Otherwise the existing global dirty-path and `fresh_audit` logic is
  verbatim, and the block reason names the remaining slugs.

- **FR-MST-22** (Mode E, `:571-619`) - **ordered, ALL where it gates.** Exact
  order: (1) path and manifest checks, unchanged; (2) no entries -> allow
  (today); (3) ANY-hotfix -> `log_bypass` naming the hotfix slug, allow;
  (4) filter to `feature`/`program` entries, none -> allow; (5) ALL-tracking -
  BLOCK with `A3_MESSAGE` if ANY of those entries is `tracking_untracked`;
  (6) ALL-execution-decision - BLOCK with `MODE_E_MSG1` if ANY lacks a valid
  decision; (7) per-entry dispatch - BLOCK with `MODE_E_MSG2` for any entry
  whose decision is `delegated` and whose PER-SLUG dispatch count is zero.
  Steps 5-7 are ALL, so a second feature entry can only make Mode E block more.
  Per-slug `dispatches_for(slug)` is what stops session B's dispatch from
  vacuously satisfying session A's `delegated` decision - this is SM-3.

- **FR-MST-23** - **the hotfix split, stated once and applied everywhere.**
  Exemption TYPES are per-entry: a gate that today skips because the single
  task's type is exempt now evaluates the non-exempt entries and blocks if any
  of them fails (`guard_spec`, `stop_gate`, Mode D). Waiver BYPASSES stay ANY
  and exist only where blocking a declared production emergency behind an
  unrelated entry is the worse failure: `guard_models`, `guard_commit`, Mode C,
  Mode E. No other hook gains an ANY bypass. `guard_secrets` continues to ignore
  `active-task.json` entirely and never honors hotfix (GATES.md).

#### Write safety, doctrine, rollout

- **FR-MST-24** - **the write-safety doctrine rule.** Wherever
  `active-task.json` is described, canon states: **add your task's entry with a
  targeted Edit; remove ONLY your entry; never rewrite the whole file.** The
  reasoning is stated once (an `Edit` replaces against current disk content, so
  two sessions editing at different anchors both survive; a whole-file `Write`
  drops the other session's entry). Files: `company/METHOD.md:122,146`,
  `company/GATES.md:80`, `COMPANY.md:69-71,92-108,146-150`,
  `docs/glossary.md:143,339,340`, and the skills `company/SKILL.md:41,82`,
  `feature/SKILL.md:25,37`, `standup/SKILL.md:13,26,39`,
  `autopilot/SKILL.md:35`. Wording stays generic and must read correctly in an
  install where N is always 1: "the list of tasks in flight in this working
  tree", not "the task in flight". NO CLI and NO freeze are added - both were
  scoped out by the owner. The residual risk that nothing mechanically enforces
  Edit-over-Write is recorded as RISK-MST-04.

- **FR-MST-25** - **hook messages carrying doctrine change with it.**
  `guard_spec.NO_BRIEF_MSG`, `guard_tests.OUT_OF_SCOPE`,
  `guard_provenance.MODE_C_MSG`, `MODE_E_MSG1`, `MODE_E_MSG2`, `A3_MESSAGE`,
  `NUDGE_TEXT`, and the `stop_gate` reason string are updated to the entry
  idiom (add/remove YOUR entry). `MODE_E_MSG2` additionally gains one line:
  when more than one entry is active, the spawn prompt must name `task/<slug>`
  or the dispatch is not attributed to this entry. Messages stay terse and
  action-first; each still reads correctly at N==1.

- **FR-MST-26** - **witness on the load-bearing sentence.** The replacement for
  `.claude/skills/company/SKILL.md:82` ("Set active-task.json on dispatch;
  clear it on integration") gets a witness added via
  `python3 .claude/hooks/witness_check.py --add` (never by hand-editing
  `company/witnesses.json`). A second witness covers the deleted wipe: a
  `must_contain` on `.claude/hooks/guard_provenance.py` for the per-slug
  dispatch lookup, so a regression to slug-matching is caught.

- **FR-MST-27** - **WORRIES rows.** `company/state/WORRIES.md` gains one row per
  accepted weakening (RISK-MST-01, -02, -03) and one for the Edit-over-Write
  residual (RISK-MST-04), each terse, with its mitigation and its escalation
  path in the CEO-logic column.

- **FR-MST-28** - **tests.** `tests/hooks/run_tests.sh` already discovers every
  `test_*.py` (landed in 3b17591), so new test files run in CI - the
  prerequisite is satisfied and must be re-verified, not re-done. Add
  `tests/hooks/test_active_task_schema.py` (normalizer table, `active_task`
  absence, grep guard, helper behavior); add a `set_tasks(*objs)` helper beside
  each existing `set_task(obj)` in `tests/hooks/test_hooks.py`,
  `test_guard_secrets.py`, and `test_cost_capture.py`; extend
  `test_guard_provenance.py`, `test_context_pin.py`,
  `test_session_start_digest.py`, and `test_risk_score.py` per the verification
  plan. The roughly 45 existing `set_task(obj)` call sites are NOT rewritten -
  they are the v1-compat regression proof.

- **FR-MST-29** - **field rollout proof.** `tests/install/test_update.sh` gains
  a case that updates an install carrying a legacy single-object
  `active-task.json` and a v1 `provenance-ledger.json`, then drives one edit
  through `guard_spec` and one through Mode E and asserts neither spuriously
  blocks, and asserts `update` never rewrites or deletes an existing
  `active-task.json`. `active-task.json` stays untracked and unscaffolded - an
  empty scaffold is behaviorally identical to absence (BR-MST-11).
  `company/RELEASE.md` gains one line: update should not run mid-task, because
  `guard_provenance` imports `guard_spec`, `guard_models`, and `guard_commit`,
  and `context_pin`/`session_start` import `guard_provenance`, so a mid-turn
  tree swap can mix versions for sub-second windows.

- **FR-MST-30** - **block-message rendering at N>1.** Every block or bypass
  message and every `adherence.log` line names the responsible entry (or
  entries, `slug_list`, cap 3). Specifically: the `guard_commit`
  protected-branch message renders today's exact text at N==1, and at N>1
  renders one `git switch -c task/<slug>` line per non-exempt entry (cap 3).
  _Invariant protected:_ when a hook blocks, its message is a recipe the blocked
  agent can follow (METHOD.md, "hooks teach the machine"). A message that does
  not say WHICH task caused the block is not a recipe.

- **FR-MST-31** - **standup attribution.** `.claude/skills/standup/SKILL.md:26`
  currently matches `costs.log` lines whose task column equals the active slug.
  It becomes: a line matches an entry when the task column CONTAINS that entry's
  slug (the column may now be `a+b`). Costs are reported per entry by
  containment and are explicitly approximate when more than one entry was in
  flight (OQ-MST-05).

### Business rules and validations

- **BR-MST-01** - **normalization table.** `active_tasks(root)` maps on-disk
  content to a list, exhaustively:

  | On disk | Result | Note |
  |---|---|---|
  | file missing / unreadable / invalid JSON | `[]` | today's fail-open |
  | `null`, `"x"`, `3`, `true` | `[]` | non-container |
  | `{"version": 2, "tasks": [A, B]}` | `[A, B]` | v2, non-dict members dropped |
  | `{"version": 2, "tasks": []}` | `[]` | identical to file missing |
  | `{"tasks": []}` (no version) | `[]` | `tasks` list wins over legacy-dict |
  | `{"task": "x", ...}` | `[{"task": "x", ...}]` | v1 field install |
  | `{}` | `[{}]` | "a task exists" - preserves today's guard_commit/stop_gate behavior |
  | `[A, B]` | `[A, B]` | bare list tolerated |
  | `{"tasks": {...}}` (dict, not list) | `[{"tasks": {...}}]` | falls through to the legacy-dict rule |

- **BR-MST-02** - **the N==1 identity rule.** With exactly one entry, every hook
  produces byte-identical exit code, stdout, stderr, and `adherence.log` line
  for the v1 single-object file and the equivalent v2 one-entry file. Against
  today's behavior, one entry produces the identical decision, exit code, and
  adherence action / target / reason; the only permitted text difference is the
  doctrine rewording of FR-MST-25, which is applied at every N and never changes
  a decision. Behavior changes only when a second entry exists. Any FR whose
  DECISION differs at N==1 is a defect, not a design choice.

- **BR-MST-03** - **the fact-classification rule.** GLOBAL (tree facts, computed
  once, shared by every session in this checkout): `work_hash`, the
  `gates.status` stamp and its staleness, `dirty_source_paths`, the
  `guard_secrets` staged-index scan, the current branch, ledger `audits`,
  ledger `self_authored`. PER-ENTRY (task facts): `brief`, `type`, `test_scope`,
  `execution`, `execution_why`, `issues`, `reclassified_why`, ledger
  `dispatches`, ledger `nudge_state`. Adding a per-entry field never changes a
  tree fact, and no new state file, lease, lock, or session-keyed record is
  introduced.

- **BR-MST-04** - **the monotonicity rule (the central check).** For every gate,
  adding an entry may only leave the decision unchanged or turn an ALLOW into a
  BLOCK. The only permitted exceptions are RISK-MST-01, -02, and -03, each of
  which must log a BYPASS or GRANT line naming the responsible entry. A reviewer
  checks each consumer FR against this rule; a PR that adds an ANY bypass not
  listed in FR-MST-23 fails review.

- **BR-MST-05** - **hotfix split.** Exemption types are per-entry; waiver
  bypasses are ANY and exist ONLY in `guard_models`, `guard_commit`, Mode C, and
  Mode E (FR-MST-23). `guard_secrets` honors no bypass at all.

- **BR-MST-06** - **dispatch attribution.** N==1: unconditional. N>1: an entry
  is credited when its slug appears as a substring of the spawn prompt or the
  description (case-sensitive, no word-boundary requirement - OQ-MST-04). Zero
  matches -> `unattributed_dispatches` plus an adherence line; it satisfies no
  entry. One dispatch may credit several entries when several slugs appear.

- **BR-MST-07** - **naming rule.** Every BLOCK, BYPASS, GRANT, DISPATCH, NUDGE,
  and AUDIT line in `adherence.log`, and every block message, names the entry
  slug(s) it concerns. `<task-slug>` remains the placeholder for an entry with
  no `task` value.

- **BR-MST-08** - **ledger write rule.** Only `write_ledger` mutates the file;
  it prunes per-slug records for slugs with no entry, and it is the only place a
  prune happens. Read paths never write. The atomic tempfile + `os.replace`
  write and the salted checksum are unchanged.

- **BR-MST-09** - **ledger migration rule.** v1 with a live slug migrates in
  memory (dispatches preserved); v1 with a dead slug returns fresh (today's
  behavior preserved on purpose); any checksum mismatch returns fresh. A v2
  ledger is never reset for a slug reason.

- **BR-MST-10** - **empty-list equivalence.** `{"version": 2, "tasks": []}`,
  `{"tasks": []}`, and a missing file are indistinguishable to every hook. This
  is what makes "remove your entry at close" safe as the last removal.

- **BR-MST-11** - **no scaffolding.** Neither `install` nor `update` creates,
  rewrites, or deletes `active-task.json`. It stays untracked and absent until a
  session writes it. An empty scaffold is behaviorally identical to absence and
  would only add a file to keep in sync.

### Scope

**In:**

- v2 schema for `active-task.json` and the `active_tasks` normalizer with full
  v1 compatibility; removal of `active_task()` with a mechanical residual check.
- Shared ANY/ALL helpers in `_common`.
- Migration of all nine consumer hooks plus `guard_provenance`'s seven call
  sites, each to the rule named in FR-MST-05 through FR-MST-13 and FR-MST-18
  through FR-MST-22.
- Provenance ledger v2: per-slug dispatches and nudge state, global audits and
  `self_authored`, deletion of the slug-mismatch wipe, in-memory v1 migration,
  prune-at-write, unattributed-dispatch bucket.
- The Edit-over-Write doctrine rule in canon, skills, docs, and hook messages;
  two witnesses; four WORRIES rows.
- Tests: schema/normalizer suite, N==1 parity suite, one "a second task must not
  disarm gate X" test per gate, the reported bug as a test, deliberate assertion
  of the three weakenings, and the field-install rollout proof.
- One `company/RELEASE.md` line on not updating mid-task.

**Out (explicit - each of these prevents a helpful expansion):**

- **`test_scope` glob lists.** The planned fix for RISK-MST-02; dropped by owner
  decision. `test_scope` stays a boolean, and the ANY grant is logged, not
  narrowed.
- **The ledger incarnation check.** The planned fix for RISK-MST-03 (a per-entry
  incarnation id so a removed-then-readded slug cannot inherit old dispatches);
  dropped by owner decision.
- **The `session_start` line-reservation fix.** The existing `MAX_LINES`
  truncation can still hide the task digest behind a saturated RESUME/STATUS;
  that is a pre-existing WORRIES row and stays one.
- **An `ALWAYS_RECIPES` message map.** Block messages are edited in place; no
  new message-registry abstraction.
- **A `risk_score --task` flag.** With N>1 and no `--brief`, `risk_score`
  returns a note (FR-MST-11). No new flag.
- **Per-branch or per-worktree gate stamps.** One checkout means one working
  tree and one branch; `gates.status` staleness is an honest shared fact.
  Scoping it would remove real enforcement, not friction.
- **Scoped `work_hash`.** Same reason: the hash fingerprints the tree, and the
  tree is shared.
- **Session leases, locks, or any advisory-lock mechanism.**
- **Session-id-keyed state, per-session `company/state`, or any use of
  `session_id` beyond today's `cost_capture` log column.**
- **A hotfix TTL.**
- **An `active_task.py` CLI** to add and remove entries. Doctrine plus targeted
  Edit is the mechanism; the residual risk is accepted and recorded.
- **Freezing `active-task.json`** (a `guard_frozen` rule blocking `Write` while
  allowing `Edit`). Named as the escalation path for RISK-MST-04 if it bites in
  the field, roughly eight lines - but not built now.
- **Fixing the two pre-existing WORRIES rows this change brushes against**:
  dispatched worktree agents cannot commit (`guard_commit.git_cwd`), and
  `guard_tests` resolving `test_scope` from the main checkout. Both are real,
  both are out of this brief, both stay WORRIES rows.
- **Scaffolding `active-task.json` at install or update** (BR-MST-11).
- **Any change to `guard_secrets`, `guard_frozen`, `no_slop`, `trace_check`,
  `witness_check`, `gate_stamp`, or `gates_detect`.**
- **Real gate commands in `company/gates.config`.** The dual-nature rule stands;
  the tracked config keeps its `CONFIGURE ME` placeholders.

### UX notes

The only surfaces a human sees are hook messages, the per-turn pin, and the
session digest.

- **Per-turn pin (`context_pin`).** N==1 is unchanged. N>1 stays inside the
  low-token budget: one short line per entry, cap 3, plus one `tree:` line.
  Shape: `[company] feat-a feature exec=delegated disp=2 iss=0 idle`, then
  `[company] hotfix-b hotfix disp=0 HOTFIX`, then `[company] tree: self=4`.
  Never more than five lines.
- **Session digest (`session_start`).** Two lines per entry, cap 3, then
  `and <n> more`. Unchanged at N==1.
- **Block messages.** Action-first, naming the offending slug(s) and the exact
  field to fix. At N>1 the fix instruction is repeated per offending entry (cap
  3) rather than collapsed, because the fix genuinely differs per entry.
- **Bypass visibility.** A hotfix entry is loud: `HOTFIX:<slug>` in the pin and
  the digest for as long as it exists, plus a named BYPASS line at every waiver
  site. METHOD.md makes removing the hotfix entry part of the already-mandatory
  postmortem.
- **Empty state.** Removing the last entry leaves `{"version": 2, "tasks": []}`,
  which every hook treats as no active task - no pin, no digest task lines, no
  gate arming beyond the tree-level ones.

## Part 2 - Build readiness (the bridge from PRD to buildable)

- **Owned directories / files (one workstream, one tech lead):**
  - `.claude/hooks/_common.py` (normalizer, helpers, `active_task` removed)
  - `.claude/hooks/guard_provenance.py` (ledger v2 plus five modes)
  - `.claude/hooks/` call-site migration: `guard_spec.py`, `guard_tests.py`,
    `guard_models.py`, `guard_commit.py`, `stop_gate.py`, `context_pin.py`,
    `session_start.py`, `cost_capture.py`, `risk_score.py`
  - Doctrine: `company/METHOD.md`, `company/GATES.md`, `company/RELEASE.md`,
    `COMPANY.md`, `docs/glossary.md`
  - Skills: `.claude/skills/{company,feature,standup,autopilot}/SKILL.md`
  - State: `company/state/WORRIES.md`; `company/witnesses.json` ONLY via
    `witness_check.py --add`
  - Tests: `tests/hooks/test_active_task_schema.py` (new),
    `tests/hooks/test_hooks.py`, `test_guard_provenance.py`,
    `test_context_pin.py`, `test_session_start_digest.py`,
    `test_cost_capture.py`, `test_guard_secrets.py`, `test_risk_score.py`,
    `tests/install/test_update.sh`
  - Stale after this change, repo-local, not shipped:
    `.claude/agent-memory/{developer,tech-lead}/*.md` - their "resolved from
    main" half stays true, their "single object" half does not. Update or delete
    the stale half.

  Disjointness: the only other in-flight item is `test-infra-fixes` (a quick
  task on `tests/hooks/run_tests.sh` and `tests/cli/test_cli.sh`), which must be
  merged before this branches; and `release-0.2.3`, which touches no source.
  This spec's own file (`company/specs/`) is excluded from the pack list.

- **Invariants in play:**
  - Python 3.8 stdlib only in every hook; hooks fail OPEN on internal error
    (`except: sys.exit(0)`); the two loud CLIs (`witness_check.py`,
    `trace_check.py`) are untouched.
  - Fail-open is exactly why `active_task` is removed rather than shimmed: a
    missing attribute inside a hook's `try` becomes a silent allow (FR-MST-03).
  - Dual-nature rule (CLAUDE.md): `company/` ships verbatim into installs, so
    all doctrine wording stays generic and reads correctly where N is always 1;
    `company/gates.config` keeps its `CONFIGURE ME` placeholders; the two suites
    that gate this repo are run directly (`python3 -m unittest discover -s
    tests/hooks -q` and `npm test`).
  - Witness registry is checksum-sealed and mutated only via
    `witness_check.py --add/--remove`.
  - Accepted ADRs are immutable; none is edited here.
  - `no_slop` on all writing: straight quotes, ' - ', three dots, no filler.
  - Low-token per-turn injection: `context_pin` stays terse (five lines max).
  - Principled enforcement, no magic numbers: no gate decision derives from a
    count threshold. The cap of 3 appears ONLY in display truncation
    (`context_pin`, `session_start`, `cost_capture`, message rendering) and
    never in a block/allow decision.
  - Commit discipline: conventional subject, `Task: multi-session-tasks`
    trailer, explicit staged paths, work on the task branch.

- **Frozen surfaces touched:** None, and no CR is required.
  `company/frozen-surfaces.json` has an empty `surfaces` list; its `always` list
  covers `company/state/provenance-ledger.json` (and other machine-written
  state), which `guard_frozen` blocks for the `Edit`/`Write` TOOLS only - the
  hook writes it through `os.replace` and the tests write it through Python, so
  no path in this build is blocked. `active-task.json` is deliberately NOT in
  the registry, and adding it is out of scope (see Scope > Out).

- **Data model impact:** two forward-only JSON schema changes, both handled by
  in-memory normalizers, neither migrating a file on disk.
  1. `active-task.json`: v1 single object -> v2 `{"version": 2, "tasks": [...]}`.
     Old files keep working forever (BR-MST-01); nothing rewrites an existing
     file; entry fields are exactly today's fields.
  2. `provenance-ledger.json`: v1 flat -> v2 with a per-slug `tasks` map plus
     `unattributed_dispatches`. Migration is in memory on read and persists on
     the next write (BR-MST-09). The file is machine-written only.
  No database, no columns, no external migration.

- **Contracts impact:**
  - `_common` module API: `active_task` REMOVED (breaking for any consumer);
    `active_tasks` and five helpers ADDED. The only consumers are this repo's
    hooks and its test suite, both migrated in the same commit.
  - `guard_provenance.read_ledger` return shape changes (per-slug `tasks` map
    instead of a flat `dispatches` list). Consumers: `context_pin`,
    `session_start`, and `guard_provenance` itself - all in scope. `roster`,
    `execution_decision`, `valid_issues`, `tracking_untracked`, `fresh_audit`,
    and `staleness_reason` keep their signatures.
  - `costs.log` task column may now be `a+b` (append-only file; historical lines
    unaffected). The only consumer is the standup skill (FR-MST-31).
  - Hook message strings change (FR-MST-25). Any test asserting exact message
    text must be updated; witnesses on those strings are re-added via the CLI.
  - No CLI flags, no new shipped files, no pack-list change: every touched
    shipped path is already covered by `package.json` `files`
    (`.claude/hooks/*.py`, `.claude/skills/`, `company/`, `docs/`,
    `COMPANY.md`); `tests/` is not packed and `company/specs/**` is
    excluded.

- **Named risks (the three accepted weakenings plus two residuals):**

  - **RISK-MST-01 - ANY-hotfix bypass.** With entries `[feature-a, hotfix-b]`,
    `guard_models`, `guard_commit`, Mode C, and Mode E are bypassed where
    `[feature-a]` alone would arm them. Unrelated feature work rides the
    emergency waiver.
    _Why accepted:_ blocking a declared production emergency behind an unrelated
    entry is the worse failure.
    _Mitigation:_ every bypass line names the hotfix slug in `adherence.log`
    (BR-MST-07); `context_pin` and `session_start` render a loud
    `HOTFIX:<slug>` for as long as the entry exists (FR-MST-13, FR-MST-12);
    METHOD.md makes removing the hotfix entry part of the already-mandatory
    postmortem (FR-MST-24). Asserted deliberately by a test (FR-MST-28) so a
    future change is a conscious edit, not silent drift.

  - **RISK-MST-02 - ANY `test_scope`.** A blanket `"test_scope": true` on entry
    B unlocks test-file edits for entry A.
    _Why accepted:_ glob-scoped grants were the planned fix and were scoped out.
    _Mitigation:_ when `len(tasks) > 1` and the grant opens, an adherence GRANT
    line names the granting entry, so the ambiguous case is auditable after the
    fact (FR-MST-06). Escalation path if it bites: per-entry glob lists.

  - **RISK-MST-03 - ledger resurrection.** Remove entry A and re-add it before
    the next `write_ledger` prunes its record, and the new incarnation inherits
    the old dispatches - so Mode E is satisfied by a dispatch that belonged to
    the previous incarnation of that slug.
    _Why accepted:_ narrow window (prune happens on the very next ledger write,
    which is any dispatch, audit, or source edit); the incarnation check was
    scoped out.
    _Mitigation:_ documented in WORRIES with its escalation path (a per-entry
    incarnation id compared at read).

  - **RISK-MST-04 - nothing enforces Edit-over-Write.** An agent can still
    `Write` the whole file and drop a sibling entry. Doctrine is the only
    control.
    _Why accepted:_ the owner scoped out both the CLI and the freeze.
    _Mitigation:_ the rule is stated at every doctrine site where the file is
    mentioned (FR-MST-24) plus in the hook messages that instruct a write
    (FR-MST-25); WORRIES row names the fix if it bites (a `guard_frozen` rule
    blocking `Write` while allowing `Edit`, roughly eight lines).

  - **RISK-MST-05 (friction, not weakness) - ALL-tracking blocks unrelated
    dispatch.** With `[tracked-a, untracked-b]`, Mode B-pre blocks A's builder
    spawn until B records its issues. Fail-closed and consistent with
    BR-MST-04; the fix is one field, and the message names B. Recorded so a
    field report is diagnosed as intended behavior rather than a bug.

- **Open questions and chosen fallbacks:** every OQ below has ONE decided
  fallback that every agent implements and tags `// OQ-MST-NN assumption` (or
  `# OQ-MST-NN assumption` in Python). None blocks the build.

  - **OQ-MST-01**: Is there a maximum number of entries? FALLBACK: **no hard
    cap and no block**. Display truncates at 3 with `and <n> more`
    (`context_pin`, `session_start`, `cost_capture`, block messages). A cap
    would be a magic number in a gate, which the invariants forbid.
  - **OQ-MST-02**: Duplicate slugs in the list. FALLBACK: **tolerate, do not
    dedupe, do not block**. Every entry is evaluated independently; ledger
    records for the duplicate slugs merge under the one key, so both entries see
    the same dispatch count. Doctrine states slugs are unique per working tree.
    Escalate to a block only if it is observed in the field.
  - **OQ-MST-03**: An entry with a missing or empty `task` slug. FALLBACK:
    **the entry still counts** for existence and type rules (preserving today's
    `{}` behavior at `guard_commit` and `stop_gate`); it renders as
    `<task-slug>`; it is keyed in the ledger under the empty string and can
    never be credited an attributed dispatch at N>1 (no slug to match), so a
    slugless `delegated` entry blocks Mode E until it is given a slug. That is
    fail-closed and correct.
  - **OQ-MST-04**: Dispatch-attribution matching at N>1. FALLBACK:
    **case-sensitive substring match** of the entry slug against the
    concatenation of the spawn `prompt` and `description` fields; no word
    boundary, no normalization. Doctrine already requires `task/<slug>` in the
    spawn prompt, so a plain substring is sufficient and cheap; a false positive
    requires one slug to be a substring of another, which duplicate-free
    slugging already discourages.
  - **OQ-MST-05**: How `standup` reports cost when the `costs.log` task column
    is `a+b`. FALLBACK: **containment match, summed, flagged approximate** - a
    line counts toward every entry whose slug it contains, and the standup
    output states that multi-task lines are attributed to all of them. No
    splitting, no per-session apportionment (that needs session state, which is
    out of scope).
  - **OQ-MST-06**: `risk_score` behavior with N>1 and no `--brief`. FALLBACK:
    **exit code unchanged, brief-derived signals omitted, one note** naming the
    active entry count and telling the caller to pass `--brief`. Never guess a
    brief.
  - **OQ-MST-07**: Should ledger `self_authored` become per-slug? FALLBACK:
    **global**. It is derived from edited paths in the shared tree with no
    reliable attribution to an entry; making it per-entry would require
    guessing. It is a tree fact (BR-MST-03).
  - **OQ-MST-08**: Should `nudge_state` be global or per-slug? FALLBACK:
    **per-slug**, inside `tasks[<slug>]`. The nudge text names a slug, so a
    global fingerprint would suppress a true nudge for a second entry.
  - **OQ-MST-09**: Behavior when `active-task.json` is read mid-write by another
    session (a partial or invalid JSON read). FALLBACK: **today's behavior,
    unchanged** - `read_json_file` returns None, `active_tasks` returns `[]`,
    and gates that require an entry fall open for that one invocation. No retry
    loop, no lock, no backoff. Recorded here because at N>1 the window is real
    but still sub-millisecond, and a retry loop in a fail-open hook adds more
    risk than it removes.
  - **OQ-MST-10** (owner-facing, business-policy flavored): is multi-session
    concurrency a SUPPORTED, documented capability of claude-company for
    clients, or an internal tolerance the product does not advertise? This
    touches what the product promises and therefore what it must keep working.
    FALLBACK: **documented as supported in `docs/glossary.md` and the METHOD
    wording, with no marketing claim and no version-bump treatment beyond the
    normal minor release**. Recorded for `company/state/DECISIONS.md` as an
    owner item to confirm or veto at delivery; the build does not wait on it,
    and a veto costs only a wording edit.

- **Verification plan:** each FR is proven by a named, executable check. Gate
  ladder first, both green before any commit per CLAUDE.md:
  `python3 -m unittest discover -s tests/hooks -q`, `npm test`, and
  `bash tests/install/run_tests.sh`.

  - **FR-MST-01, FR-MST-02, BR-MST-01, BR-MST-10**:
    `tests/hooks/test_active_task_schema.py` drives every row of the BR-MST-01
    table through `active_tasks` and asserts the exact list; plus
    `{"version": 2, "tasks": []}` vs a missing file compared across
    `guard_commit` and `stop_gate` (identical exit codes and log lines).
  - **FR-MST-03, SM-5**: a test asserting
    `not hasattr(_common, "active_task")`, and a grep test over
    `.claude/hooks/*.py` failing on `\bactive_task\s*\(`.
  - **FR-MST-04**: unit tests per helper, including `slug_list` truncation and
    `hotfix_entry` returning the FIRST hotfix entry.
  - **BR-MST-02, SM-1**: a parameterized parity suite. For each of the ten
    consumer hooks and each of the six `guard_provenance` events, run the hook
    against (a) a v1 single-object file and (b) the equivalent v2 one-entry
    file, and assert identical exit code, stdout, stderr, and the appended
    `adherence.log` line. Plus: the roughly 45 existing `set_task(obj)` call
    sites pass UNCHANGED except where an assertion pins message text that
    FR-MST-25 deliberately rewords - that is the v1-compat regression proof, so
    they are not otherwise rewritten, and every text-only edit to an existing
    assertion is called out in the PR body so a decision change cannot hide
    inside one.
  - **FR-MST-05**: entry A with a brief + entry B with no `brief` -> source edit
    exits 2 naming B. A with a brief + B with a `brief` pointing at a missing
    file -> exits 2 naming B. Zero entries -> exits 2 (today). All-hotfix
    entries -> exit 0 with a BYPASS line.
  - **FR-MST-06, RISK-MST-02**: `[A(test_scope false), B(test_scope true)]` ->
    a `tests/` edit is ALLOWED and `adherence.log` carries a GRANT line naming
    B. `[A(false)]` alone -> blocked (unchanged).
  - **FR-MST-07, RISK-MST-01**: `[feature-a, hotfix-b]` -> a contradicting
    builtin spawn is allowed with a BYPASS line naming `hotfix-b`;
    `[feature-a]` alone -> blocked.
  - **FR-MST-08, FR-MST-30**: zero entries on `main` -> commit allowed
    (founding-commit exemption). One entry on `main` -> blocked with today's
    exact message. Two entries on `main` -> blocked with one `git switch` line
    per entry. `[feature-a, hotfix-b]` on `main` -> allowed with a BYPASS naming
    `hotfix-b`. Stamp-check behavior identical in all four.
  - **FR-MST-09**: `[quick]` with a red stamp -> no block (today).
    `[quick, feature]` with a red stamp -> block naming the feature entry.
    `[quick, hotfix]` -> no block.
  - **FR-MST-10, FR-MST-31**: one entry -> today's exact task column; two
    entries -> `a+b` sorted; four entries -> three joined plus `+more`; zero ->
    `-`.
  - **FR-MST-11, OQ-MST-06**: zero/one/two entries with no `--brief` -> today's
    note / the sole brief / the count note, exit code unchanged.
  - **FR-MST-12, FR-MST-13**: golden-output tests. One entry -> byte-identical
    to today's pin and digest. Two entries -> two entry lines plus one `tree:`
    line, five lines maximum, `self=` present exactly once. A hotfix entry ->
    `HOTFIX:<slug>` present in both.
  - **FR-MST-14, FR-MST-17, BR-MST-08**: write a ledger with a record for a slug
    that has no entry, call `write_ledger`, assert the record is pruned and
    `audits`/`self_authored`/`unattributed_dispatches` survive. Call
    `read_ledger` from `context_pin` and `session_start` and assert the file
    mtime and bytes are unchanged.
  - **FR-MST-15, SM-2 (the reported bug, as a test)**: entries A and B active,
    A's two dispatches and one audit recorded; add B; assert `read_ledger` still
    reports A's dispatches and the audit, and that Mode C, Mode D, and Mode E
    all allow for A. Then remove B and assert the same.
  - **FR-MST-16, BR-MST-09, SM-6**: v1 ledger with a live slug -> dispatches
    migrated, Mode E allows. v1 ledger with a dead slug -> fresh, Mode C blocks
    (today's behavior preserved). v1 ledger with a broken checksum -> fresh.
  - **FR-MST-18, SM-3 (the highest-value case)**: entries A and B, both
    `"execution": "delegated"`, one recorded dispatch whose spawn prompt names
    only `task/b`; assert a main-checkout source edit exits 2 with a message
    naming A and a BLOCK line naming A. Then record a dispatch naming `task/a`
    and assert the edit is allowed. Also: a dispatch naming neither lands in
    `unattributed_dispatches`, writes an adherence line, and satisfies neither
    entry.
  - **FR-MST-19**: `[self-idle-a, self-idle-b]` -> exactly one nudge emitted per
    edit, naming the first entry; a second edit nudges the second entry; neither
    repeats.
  - **FR-MST-20, FR-MST-21**: two non-exempt entries with dirty source and no
    fresh audit -> Mode C and Mode D block naming both. One fresh global audit
    covers both entries (no second audit demanded). `[quick, hotfix]` -> Mode D
    exits 0.
  - **FR-MST-22, BR-MST-04**: Mode E ordering table driven case by case -
    untracked-B blocks even when A is tracked; undecided-B blocks even when A is
    decided; delegated-A with zero own dispatches blocks even when B has two.
  - **FR-MST-23, BR-MST-05**: an inventory test asserting the ANY-bypass sites
    are exactly `guard_models`, `guard_commit`, Mode C, Mode E - and that
    `guard_spec`, `guard_tests`, `stop_gate`, and Mode D use per-entry exemption
    instead.
  - **FR-MST-24, FR-MST-25**: `no_slop`-clean read of every doctrine and message
    edit; a test asserting the entry idiom string is present in the shipped
    doctrine files; existing message-assertion tests updated.
  - **FR-MST-26**: `python3 .claude/hooks/witness_check.py` green on the two new
    witnesses; registry checksum valid.
  - **FR-MST-27**: WORRIES rows present, one per named risk.
  - **FR-MST-28**: `tests/hooks/run_tests.sh` re-verified to discover every
    `test_*.py` (the prerequisite landed in 3b17591); the new suite appears in
    the CI test count.
  - **FR-MST-29, SM-6**: `tests/install/test_update.sh` - install, plant a
    legacy single-object `active-task.json` and a v1 ledger, run update, drive
    one `guard_spec` edit and one Mode E edit, assert neither blocks, assert
    `active-task.json` byte-unchanged and still present.
  - **SM-4**: the per-gate "a second task must not disarm gate X" tests
    enumerated above (`guard_spec`, `guard_tests`, `guard_commit`, `stop_gate`,
    Modes C/D/E, `guard_models`), plus the three weakenings asserted
    deliberately.
  - **SM-7**: the full gate ladder green, before any commit.
  - **Live end-to-end check on this repo before the delivery report** (evidence
    for the report, not a substitute for tests): add two entries; confirm
    `context_pin` renders both and `session_start` digests both; remove one and
    confirm the other and its ledger record survive; remove the last and confirm
    the founding-commit exemption returns.

## Options considered

Divergence ran 15 candidate directions across five pattern categories:
assumption challenge (the mandatory one), inversion, SCAMPER, constraint
variation, perspective multiplication, and analogical transfer. The top-level
shape (one file, N entries) was owner-decided on 2026-07-26 and is not reopened;
the divergence was run to test whether the decided shape survives contact with
the alternatives and to surface the requirements the alternatives imply. It
produced four things this spec would not otherwise contain: the monotonicity
rule (BR-MST-04, from inversion), the naming rule (BR-MST-07, from the support
engineer perspective), the hotfix-amplification weakening (RISK-MST-01, from the
attacker perspective), and the fact-classification rule (BR-MST-03, from the
assumption challenge on "gates are per-task").

Notable non-survivors, briefly: derive the active task from the branch name
(collapses to one task - same checkout, one branch); delete `active-task.json`
and glob `company/briefs/*.md` (loses type, execution decision, and issues, and
briefs linger after close); keep the single object and add a `siblings` array
(two ways to say one thing, and the primary object still races); make a second
session a hard error (blocks the owner's actual working pattern); pure doctrine
with no code change (the ledger wipe is a code bug and doctrine cannot fix it).

| # | Option | Reasoning | Production risks | Trade-offs |
|---|---|---|---|---|
| 1 | **One file, `tasks` LIST of entries; tree facts global, task facts per-entry; ledger v2 with per-slug dispatches** | Entry fields are exactly today's fields, so the v1 file is one normalizer branch away and N==1 is provably unchanged. Insertion order gives a stable render order for the pin. A list is what a targeted Edit appends to without touching a sibling. Everything shared stays shared, which is correct rather than merely cheap - one checkout is one tree and one branch. | The write race is closed by doctrine only (RISK-MST-04). Nine hooks change at once, and a missed call site becomes a silent allow through fail-open (closed by FR-MST-03's grep and hasattr tests). | Ten files touched in one branch; the compat risk concentrates in the normalizer, which is independently reviewable as a pure refactor commit. |
| 2 | One file, `tasks` as a slug-keyed OBJECT | An Edit anchors naturally on a unique key, and per-slug ledger lookup becomes a direct join. Duplicate slugs are impossible by construction (kills OQ-MST-02). | JSON object ordering is an implementation detail, so pin and digest ordering is not doctrine-stable; the slug then lives both as the key and inside the value, or the entry shape stops matching today's single object - which breaks the cheap v1 normalizer. | Slightly better write ergonomics, materially worse v1 compatibility and render determinism. |
| 3 | A DIRECTORY of per-task files: `company/state/tasks/<slug>.json` | Removes the write race entirely and mechanically - each session owns its own file, so no Edit discipline is needed and RISK-MST-04 disappears. Removal is a file delete. Naturally per-entry. | Every hook read becomes a directory listing with murkier fail-open semantics (unreadable dir vs empty dir); a stale file from a crashed session lingers with nothing to prune it; the install/update/pack surface gains a state directory to scaffold and keep in sync. | Trades one accepted doctrine risk for a new lifecycle problem, and touches the shipped payload surface instead of just the hooks. |

**Winner: Option 1.** It is the only survivor where N==1 is provably unchanged
for every field install (entry fields are literally today's fields), where the
migration is an in-memory normalizer rather than a file operation, and where the
shipped payload surface does not grow. It also fixes the reported bug in a
single reviewable commit (ledger v2), independent of the multi-task semantics.

**Strongest rejected option: Option 3 (a directory of per-task files).** It wins
on the one thing Option 1 accepts as residual risk: it makes the write race
structurally impossible rather than doctrinally discouraged, which matters
because RISK-MST-04 has no mechanical control at all. It lost on lifecycle and
surface: a per-session file has no owner once the session dies, so a crashed
session leaves a phantom task arming gates forever with nothing to prune it
(the single file at least gets rewritten by the next session), and it adds a
state directory to the installer, the update engine, and the pack list for a
problem that a one-line doctrine rule addresses. If RISK-MST-04 bites in the
field, reopen this - but reopen it in the cheaper order: first the
`guard_frozen` rule blocking `Write` while allowing `Edit` (roughly eight
lines), and only then the directory.

## Spec-ready checklist (the Phase 0 gate)

- [x] **Every FR has a stable ID and at least one acceptance criterion.**
  FR-MST-01 through FR-MST-31, each mapped in the Verification plan; US-MST-1
  through US-MST-6 and SM-1 through SM-7 carry the given/when/then form.
- [x] **Out-of-scope is explicit.** Fourteen exclusions in Scope > Out,
  including all five owner-dropped items and every rejected mechanism
  (per-branch stamps, scoped `work_hash`, leases, locks, session-keyed state,
  the CLI, the freeze).
- [x] **Every open question has a single decided fallback.** OQ-MST-01 through
  OQ-MST-10, each with one fallback tagged in code. OQ-MST-10 is the only
  owner-facing one and is recorded for `DECISIONS.md`; its fallback lets the
  build proceed and a veto costs only a wording edit.
- [x] **Owned directories are named and disjoint from other in-flight work.**
  Named in Part 2. `test-infra-fixes` (tests/hooks/run_tests.sh,
  tests/cli/test_cli.sh) must merge first; `release-0.2.3` touches no source.
- [x] **Frozen-surface needs are identified and CRs filed.** None touched, no CR
  required: `surfaces` is empty, and the `always` entries this build writes
  (`provenance-ledger.json`) are written by Python, not by the `Edit`/`Write`
  tools that `guard_frozen` intercepts.
- [x] **Data/contract impact stated.** Two forward-only JSON schema versions
  with in-memory normalizers; `_common.active_task` removed;
  `read_ledger` return shape changed; `costs.log` task column may join slugs;
  no pack-list change.
- [x] **Verification plan covers every FR.** One named executable check per FR
  plus the seven SM signals and the live end-to-end check.

Prerequisite confirmed satisfied: the CI test-discovery fix
(`tests/hooks/run_tests.sh` discovering every `test_*.py`) landed in commit
3b17591. It must be on `main` before this task branches, otherwise the new test
files never run in CI and every claim in the Verification plan is unproven.

## Part 3 - Brief handoff

Derive one brief with `company/templates/BRIEF-TEMPLATE.md`; the brief links
this spec and does not embed it. One workstream, one tech lead.

Read-first for the builder: the project `CLAUDE.md` (dual-nature rule, the two
gate suites, commit discipline), `company/METHOD.md`,
`.claude/hooks/_common.py`, `.claude/hooks/guard_provenance.py`, then the nine
call-site hooks, `company/frozen-surfaces.json`, `tests/hooks/test_hooks.py`
(the `set_task` helper), and `tests/hooks/test_guard_provenance.py`.

Commit order in the brief (ascending blast radius, each independently
reviewable):

1. Normalizer plus all call sites migrated with NO semantic change - a pure
   refactor where every existing test passes untouched. The compatibility risk
   lives here.
2. Ledger v2: schema, in-memory v1 migration, wipe removal, per-slug
   dispatches, prune-at-write. **This commit alone fixes the reported bug** and
   should be verifiable on its own.
3. Multi-task semantics, ascending blast radius: read-only hooks
   (`context_pin`, `session_start`), then non-gates (`cost_capture`,
   `risk_score`), then `guard_tests`, `guard_spec`, `guard_commit`,
   `stop_gate`, `guard_models`, then the `guard_provenance` modes.
4. Doctrine, skills, docs, witnesses, WORRIES rows, RELEASE.md line.

Gates for this repo: `python3 -m unittest discover -s tests/hooks -q` and
`npm test`, both green before any commit, plus
`bash tests/install/run_tests.sh` for the rollout proof. No CR is required.
