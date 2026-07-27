# BRIEF: multi-session-tasks

_Type: feature. Spec: `company/specs/spec-multi-session-tasks.md` (reference for
the CEO; you do NOT need it - this brief is sealed and self-contained).
Lead: tech-lead. Date: 2026-07-27._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

The owner runs several Claude Code sessions from the SAME checkout. Nothing
distinguishes them - identical `CLAUDE_PROJECT_DIR`, identical cwd, same tree,
same branch - and `company/state/active-task.json` is a singleton dict, so when
session B writes its task, session A silently inherits it. A's context pin
flips, A's brief lookup resolves to B's brief, A's `test_scope` grant flips, and
worst of all `guard_provenance.read_ledger` returns a FRESH ledger the moment
the on-disk slug stops matching, so A's recorded dispatches and audits are
erased and A is then spuriously blocked at commit, at Stop, and at its next
source edit - for work it already dispatched and already had audited. The
harness converts verified work into work the gates believe is unverified.

Make `active-task.json` hold N entries. Task facts become per-entry; working-tree
facts stay global and shared, because with every session in one checkout they
are honest shared facts.

**The one hard constraint that must survive contact with reality:** going from
one task to N must NEVER turn a gate's BLOCK into an ALLOW. Exactly three
weakenings are accepted, each named below, each logged, each with a test that
asserts it DOES bypass. If you find yourself widening a gate anywhere else to
make something pass, you have found a briefing error - report it, do not build
it.

## Read first (in order)

1. `CLAUDE.md` (project canon: the dual-nature rule, the two gate suites that
   actually gate this repo, commit discipline)
2. `company/METHOD.md` (how the team works)
3. `.claude/hooks/_common.py` - `active_task` at `:83` is what you are replacing
4. `.claude/hooks/guard_provenance.py` - the whole file; the wipe you are
   deleting is at `:302-303`
5. The nine call-site hooks: `guard_spec.py`, `guard_tests.py`,
   `guard_models.py`, `guard_commit.py`, `stop_gate.py`, `context_pin.py`,
   `session_start.py`, `cost_capture.py`, `risk_score.py`
6. `company/frozen-surfaces.json`
7. `tests/hooks/test_hooks.py` (study the `set_task` helper) and
   `tests/hooks/test_guard_provenance.py`

## You own

- `.claude/hooks/_common.py`
- `.claude/hooks/guard_provenance.py`
- `.claude/hooks/` call sites: `guard_spec.py`, `guard_tests.py`,
  `guard_models.py`, `guard_commit.py`, `stop_gate.py`, `context_pin.py`,
  `session_start.py`, `cost_capture.py`, `risk_score.py`
- Doctrine: `company/METHOD.md`, `company/GATES.md`, `company/RELEASE.md`,
  `ORCHESTRATOR.md`, `docs/glossary.md`
- Skills: `.claude/skills/{orchestrator,feature,standup,autopilot}/SKILL.md`
- State: `company/state/WORRIES.md`; `company/witnesses.json` ONLY via
  `python3 .claude/hooks/witness_check.py --add`
- Tests: `tests/hooks/test_active_task_schema.py` (new),
  `tests/hooks/test_hooks.py`, `test_guard_provenance.py`, `test_context_pin.py`,
  `test_session_start_digest.py`, `test_cost_capture.py`, `test_guard_secrets.py`,
  `test_risk_score.py`, `tests/install/test_update.sh`
- `.claude/agent-memory/{developer,tech-lead}/*.md` - repo-local, not shipped.
  Their "resolved from the main checkout" half stays true; their "single object"
  half does not. Fix the stale half or delete it.

Nothing else. Anything not listed is read-only to you. If the fix you need lives
outside these paths, report it; do not make it.

## Invariants in play (must not break)

- **Python 3.8 stdlib only** in every hook. Hooks fail OPEN on internal error
  (`except: sys.exit(0)`).
- **Fail-open is exactly why `active_task` is REMOVED rather than shimmed:** an
  `AttributeError` inside a hook's `try` lands in the silent-allow path. A shim
  returning `tasks[0]` would enforce against one arbitrary entry; a shim
  returning `None` at N>1 would disarm every gate at once. Remove it, migrate
  every call site in the same commit, and close it mechanically with a
  `not hasattr(_common, "active_task")` test plus a grep test failing on any
  residual `\bactive_task\s*\(` under `.claude/hooks/`.
- **The dual-nature rule (CLAUDE.md):** `company/` ships verbatim into user
  installs. All doctrine wording stays generic and must read correctly in an
  install where N is always 1 - "the list of tasks in flight in this working
  tree", not "the task in flight". `company/gates.config` keeps its
  `CONFIGURE ME` placeholders; NEVER commit this repo's real gate commands.
- **The two suites that gate THIS repo are run directly, not through
  `run-gates.sh`:** `python3 -m unittest discover -s tests/hooks -q` and
  `npm test`. Both green before any commit. Plus
  `bash tests/install/run_tests.sh` for the rollout proof.
- **Witness registry is checksum-sealed** and mutated ONLY via
  `witness_check.py --add/--remove`. Never hand-edit `company/witnesses.json`.
- **Accepted ADRs are immutable.** None is edited here.
- **`no_slop` on all writing:** straight quotes, ' - ' not em dashes, three dots
  not the ellipsis character, no stock AI filler. A CI job scans every tracked
  text file.
- **Low-token per-turn injection:** `context_pin` stays terse, five lines
  maximum, ever.
- **Principled enforcement, no magic numbers:** no gate decision may derive from
  a count threshold. The cap of 3 appears ONLY in display truncation
  (`context_pin`, `session_start`, `cost_capture`, message rendering) and never
  in a block/allow decision.
- **Tests are the oracle.** Never edit a test to make code pass.

## Frozen surfaces nearby (CR, never edit)

`company/frozen-surfaces.json` has an EMPTY `surfaces` list, so no CR is
required for this task. Its `always` list covers
`company/state/provenance-ledger.json`, which `guard_frozen` blocks for the
`Edit` and `Write` TOOLS only - the hook writes that file through `os.replace`
and the tests write it through Python, so no path in this build is blocked.
`active-task.json` is deliberately NOT in the registry, and adding it is OUT OF
SCOPE.

## Scope (ordered)

Four commits, ascending blast radius, each independently reviewable. Do not
collapse them.

### Commit 1 - normalizer plus call-site migration, NO semantic change

Tracking issue #89. A pure refactor: every existing test passes UNTOUCHED. The
compatibility risk of the whole feature lives here.

1. **FR-MST-01** - v2 shape for `company/state/active-task.json`:
   `{"version": 2, "tasks": [ <entry>, ... ]}`. An entry carries exactly today's
   single-object fields (`task`, `type`, `brief`, `test_scope`, `execution`,
   `execution_why`, `issues`, `reclassified_why`, plus any project-added key). A
   LIST, not a slug-keyed object: insertion order is the stable render order,
   and a list is what a targeted Edit appends to without touching a sibling.
2. **FR-MST-02** - `_common.active_tasks(root) -> list` replaces
   `_common.active_task`. Normalize in EXACTLY this order, and never raise:

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

   This is BR-MST-01 and it is exhaustive. `{"version": 2, "tasks": []}`,
   `{"tasks": []}`, and a missing file must be INDISTINGUISHABLE to every hook
   (BR-MST-10) - that is what makes "remove your entry at close" safe as the
   last removal.
3. **FR-MST-03** - remove `_common.active_task`. Migrate all call sites in this
   same commit. Add the `hasattr` test and the grep test.
4. **FR-MST-04** - shared helpers in `_common`, so ANY/ALL logic lives in one
   place instead of being re-derived in nine hooks: `has_active_task(tasks)`,
   `hotfix_entry(tasks)` (the FIRST entry with `type == "hotfix"`, else None),
   `entries_of_type(tasks, types)`, `slugs(tasks)` (truthy `task` values, order
   preserved), `slug_list(tasks, cap=3)` (display string, overflow rendered as
   `and <n> more`). `guard_provenance.execution_decision`, `valid_issues`, and
   `tracking_untracked` stay where they are and keep their single-entry
   signatures - they are already per-entry predicates.
5. **BR-MST-02, the N==1 identity rule** - with exactly one entry, every hook
   produces byte-identical exit code, stdout, stderr, and `adherence.log` line
   for a v1 single-object file and the equivalent v2 one-entry file. Behavior
   changes ONLY when a second entry exists. Any FR whose DECISION differs at
   N==1 is a defect, not a design choice.

### Commit 2 - provenance ledger v2 (this commit alone fixes the reported bug)

Tracking issue #90. Must be verifiable on its own.

6. **FR-MST-14** - v2 ledger shape:
   `{"version": 2, "tasks": {"<slug>": {"dispatches": [...], "nudge_state": {...}}},
   "unattributed_dispatches": [...], "self_authored": [...], "audits": [...],
   "checksum": "..."}`. Dispatches and nudge state are PER-SLUG; audits,
   `self_authored`, and the `work_hash` they key on stay GLOBAL. One auditor
   pass over the tree at hash H covers every entry's changes in it, so demanding
   N audits of one identical tree would be both wasteful and dishonest.
7. **FR-MST-15** - DELETE the slug-mismatch wipe at `guard_provenance.py:302-303`
   (`if raw.get("task") != slug: return fresh`). A v2 ledger is never reset
   because the set of active slugs changed. KEEP the checksum-tamper reset
   verbatim: unverifiable history still counts as no verification.
8. **FR-MST-16** - v1 ledger migration, IN MEMORY ONLY, inside `read_ledger`.
   When the parsed ledger is v1 (no `version: 2`), let `s = raw["task"]`. Invalid
   checksum -> fresh v2 ledger. Else if `s` is in the current active slugs ->
   v2 ledger with `tasks = {s: {"dispatches": raw["dispatches"], "nudge_state":
   raw["nudge_state"]}}`, `self_authored` and `audits` carried over. Else ->
   fresh v2 ledger, deliberately preserving today's wipe for that one case,
   because carrying a stale-slug audit forward would newly satisfy Mode C and be
   WEAKER than today. `read_ledger` NEVER writes; the migrated shape persists on
   the next `write_ledger`.
9. **FR-MST-17** - `write_ledger(root, ledger)` prunes `tasks` down to the
   currently active slugs before writing (a slug with no entry is a closed
   task), then writes atomically with a fresh checksum exactly as today.
   `unattributed_dispatches`, `self_authored`, and `audits` are NEVER pruned by
   slug. Read paths never write: `context_pin` and `session_start` both call
   `read_ledger` and must leave the file byte-identical and its mtime unchanged.

### Commit 3 - multi-task semantics, ascending blast radius

Tracking issue #91. Order within the commit: read-only hooks, then non-gates,
then the gates, then the provenance modes.

10. **FR-MST-13** (`context_pin.py:42-73`) - N==1 BYTE-IDENTICAL to today,
    including the standalone idle line. At N>1: one terse line per entry (cap 3,
    then `and <n> more`) carrying slug, type, `exec=`, `disp=` (per-slug), and
    the `iss=0` drift segment, with ` idle` appended to a drifty entry's OWN line
    instead of the standalone idle line; then ONE shared line prefixed `tree:`
    carrying the global `self=<n>`. Shape:
    `[company] feat-a feature exec=delegated disp=2 iss=0 idle`, then
    `[company] hotfix-b hotfix disp=0 HOTFIX`, then `[company] tree: self=4`.
    Never more than five lines. `self=` is a TREE fact and would be a lie on a
    per-entry line - hence the separate `tree:` line. While any entry is
    `hotfix`, render a `HOTFIX:<slug>` marker.
11. **FR-MST-12** (`session_start.py:50-66`) - one digest PAIR per entry (cap 3,
    then a single `and <n> more` line): the
    `active-task: <slug> (<type>) brief=<brief>` line and the
    `execution: ... | dispatches: ... | self-authored: ... | team: ...` line,
    where `dispatches` is that entry's per-slug count and `self-authored` is the
    global count. The existing `MAX_LINES` truncation is UNCHANGED. Render
    `HOTFIX:<slug>` while any entry is a hotfix.
12. **FR-MST-10** (`cost_capture.py:195-197`) - task column becomes
    `"+".join(sorted(slugs(tasks))[:3])`, with `+more` appended beyond three and
    `-` when empty. Exactly one slug renders exactly as today. Telemetry only, no
    invariant.
13. **FR-MST-11** (`risk_score.py:221-225`) - with no `--brief`: zero entries
    returns today's note; exactly one entry uses its `brief` (today); more than
    one returns a note naming the count and telling the caller to pass `--brief`.
    Exit code UNCHANGED - risk scoring is advisory, never a gate. Never guess a
    brief.
14. **FR-MST-06** (`guard_tests.py:52-54`) - **ANY.** `test_scope_open(root)` is
    true if ANY entry has `test_scope is True`. When `len(tasks) > 1` and the
    grant opens, write an `adherence.log` GRANT line naming the granting entry
    BEFORE allowing. This is accepted weakening RISK-MST-02.
15. **FR-MST-05** (`guard_spec.py:67-85`) - **ALL over non-hotfix entries**, in
    this EXACT order, and the order is the whole point: (a) NO entries -> BLOCK
    with `NO_BRIEF_MSG`, exactly as today when the file is absent; (b) filter out
    `hotfix` entries, and if none remain, `log_bypass` and allow (today's hotfix
    behavior at N==1); (c) BLOCK if ANY remaining entry lacks a `brief` or names
    a brief file that does not exist, message naming the offending slug(s).
    **The empty check MUST come first:** "ALL over non-hotfix entries" is
    vacuously TRUE on an empty list, which would silently flip this gate from
    BLOCK to ALLOW when no task is active. That is the single highest-value
    ordering constraint in this brief.
16. **FR-MST-08** (`guard_commit.py:122-160`) - **presence plus ANY hotfix.**
    The protected-branch commit block arms iff the entry list is non-empty (an
    empty list keeps today's founding-commit exemption); it is bypassed, with a
    BYPASS line naming the slug, if ANY entry is `hotfix`. The whole-gate hotfix
    bypass below it is likewise ANY. The gate-stamp logic at `:161-189` is
    UNTOUCHED and stays a tree fact.
17. **FR-MST-09** (`stop_gate.py:29-46`) - **per-entry exempt types, ANY
    blocker.** Filter to entries whose `type` is outside `{quick, hotfix}`; if
    none remain, exit 0 (today's behavior at N==1); otherwise run the existing
    stamp check and emit the block decision if red or stale, naming the
    remaining slugs (`slug_list`, cap 3). `[quick, feature]` therefore BLOCKS -
    correct, because the tree is red with a feature in flight; the exemption
    belongs to the quick entry, not to the tree.
18. **FR-MST-07** (`guard_models.py:66-68`) - **ANY hotfix.** `is_hotfix(root)`
    is true if ANY entry has `type == "hotfix"`; the logged bypass names that
    entry's slug.
19. **FR-MST-18** (Mode B-pre, `guard_provenance.py:442-469`) - **dispatch
    attribution.** N==1: attributed unconditionally, byte-identical to today.
    N>1: attributed to EVERY entry whose slug appears in the spawn prompt or
    description. A dispatch matching NO entry is appended to
    `unattributed_dispatches`, satisfies NO entry's delegated requirement, and
    writes an adherence line so the false negative is diagnosable. The FR-DE-15
    tracking gate still runs BEFORE the dispatch is recorded, now as ANY-hotfix
    bypass then ALL-tracking over feature/program entries.
20. **FR-MST-19** (Mode A, `:395-439`) - **per-entry nudge, global telemetry.**
    `self_authored` stays a GLOBAL list appended once per distinct path. The
    self-idle nudge condition is evaluated PER ENTRY (`type` in
    `{feature, program}`, `execution_decision == "self"`, per-slug dispatch count
    zero) against that entry's OWN `nudge_state`. At most one nudge per
    invocation - the first qualifying entry in list order; the others fire on
    subsequent edits. Mode A never blocks.
21. **FR-MST-20** (Mode C, `:502-540`) - **ANY hotfix, global audit, per-entry
    message.** Order: git-commit segment detection, manifest present, entries
    non-empty (empty exits as today), ANY-hotfix bypass logging the hotfix slug,
    worktree/merge exemptions, `dirty_source_paths` (global), `fresh_audit`
    (global). On block, the message names the non-exempt slugs (cap 3) in place
    of `<slug>`.
22. **FR-MST-21** (Mode D, `:543-568`) - **per-entry exempt types, ANY blocker.**
    Filter to entries whose `type` is outside `{quick, hotfix}`; none remain ->
    exit 0. Otherwise the existing global dirty-path and `fresh_audit` logic is
    verbatim, and the block reason names the remaining slugs.
23. **FR-MST-22** (Mode E, `:571-619`) - **ordered, ALL where it gates.** EXACT
    order: (1) path and manifest checks, unchanged; (2) no entries -> allow
    (today); (3) ANY-hotfix -> `log_bypass` naming the hotfix slug, allow;
    (4) filter to `feature`/`program` entries, none -> allow; (5) ALL-tracking -
    BLOCK with `A3_MESSAGE` if ANY of those entries is `tracking_untracked`;
    (6) ALL-execution-decision - BLOCK with `MODE_E_MSG1` if ANY lacks a valid
    decision; (7) per-entry dispatch - BLOCK with `MODE_E_MSG2` for any entry
    whose decision is `delegated` and whose PER-SLUG dispatch count is zero.
    Steps 5-7 are ALL, so a second feature entry can only make Mode E block
    MORE. Per-slug `dispatches_for(slug)` is what stops session B's dispatch
    from vacuously satisfying session A's `delegated` decision.
24. **FR-MST-23** - **the hotfix split, applied everywhere and nowhere else.**
    Exemption TYPES are per-entry: a gate that today skips because the single
    task's type is exempt now evaluates the non-exempt entries and blocks if any
    fails (`guard_spec`, `stop_gate`, Mode D). Waiver BYPASSES stay ANY and
    exist ONLY where blocking a declared production emergency behind an
    unrelated entry is the worse failure: `guard_models`, `guard_commit`,
    Mode C, Mode E. No other hook gains an ANY bypass. `guard_secrets` continues
    to ignore `active-task.json` entirely and never honors hotfix.
25. **FR-MST-30** - **block-message rendering at N>1.** Every block or bypass
    message and every `adherence.log` line names the responsible entry or
    entries (`slug_list`, cap 3). Specifically the `guard_commit`
    protected-branch message renders today's EXACT text at N==1, and at N>1
    renders one `git switch -c task/<slug>` line per non-exempt entry (cap 3).
    A message that does not say WHICH task caused the block is not a recipe, and
    hook messages are recipes.

### Commit 4 - doctrine, skills, docs, witnesses, worries, rollout

Tracking issue #92.

26. **FR-MST-24** - the write-safety doctrine rule. Wherever `active-task.json`
    is described, canon states: **add your task's entry with a targeted Edit;
    remove ONLY your entry; never rewrite the whole file.** State the reasoning
    ONCE: an `Edit` replaces against current disk content, so two sessions
    editing at different anchors both survive; a whole-file `Write` drops the
    other session's entry. Sites: `company/METHOD.md:122,146`,
    `company/GATES.md:80`, `ORCHESTRATOR.md:69-71,92-108,146-150`,
    `docs/glossary.md:143,339,340`, and the skills
    `orchestrator/SKILL.md:41,82`, `feature/SKILL.md:25,37`,
    `standup/SKILL.md:13,26,39`, `autopilot/SKILL.md:35`. Line numbers are a
    starting map, not a guarantee - grep for the real sites. NO CLI and NO
    freeze: both were scoped out by the owner.
27. **FR-MST-25** - hook messages carry the doctrine change with them.
    `guard_spec.NO_BRIEF_MSG`, `guard_tests.OUT_OF_SCOPE`,
    `guard_provenance.MODE_C_MSG`, `MODE_E_MSG1`, `MODE_E_MSG2`, `A3_MESSAGE`,
    `NUDGE_TEXT`, and the `stop_gate` reason string move to the entry idiom (add
    or remove YOUR entry). `MODE_E_MSG2` gains ONE line: when more than one
    entry is active, the spawn prompt must name `task/<slug>` or the dispatch is
    not attributed to this entry. Terse, action-first, each still correct at
    N==1. This is the ONLY permitted text difference at N==1, it applies
    uniformly at every N, and it never changes a decision.
28. **FR-MST-26** - two witnesses, added ONLY via
    `python3 .claude/hooks/witness_check.py --add`. One on the replacement for
    `.claude/skills/orchestrator/SKILL.md:82` ("Set active-task.json on dispatch;
    clear it on integration"). One `must_contain` on
    `.claude/hooks/guard_provenance.py` for the per-slug dispatch lookup, so a
    regression to slug-matching is caught.
29. **FR-MST-27** - `company/state/WORRIES.md` gains one row per accepted
    weakening (RISK-MST-01, -02, -03) and one for the Edit-over-Write residual
    (RISK-MST-04), each terse, with its mitigation and escalation path in the
    CEO-logic column.
30. **FR-MST-31** - `.claude/skills/standup/SKILL.md:26` currently matches
    `costs.log` lines whose task column EQUALS the active slug. It becomes: a
    line matches an entry when the task column CONTAINS that entry's slug (the
    column may now be `a+b`). Costs are reported per entry by containment and
    are explicitly flagged approximate when more than one entry was in flight.
31. **FR-MST-29** - field rollout proof. `tests/install/test_update.sh` gains a
    case that updates an install carrying a legacy single-object
    `active-task.json` and a v1 `provenance-ledger.json`, then drives one edit
    through `guard_spec` and one through Mode E and asserts neither spuriously
    blocks, and asserts `update` never rewrites or deletes an existing
    `active-task.json`. `active-task.json` stays untracked and unscaffolded -
    neither `install` nor `update` creates, rewrites, or deletes it (BR-MST-11).
    `company/RELEASE.md` gains ONE line: update should not run mid-task, because
    `guard_provenance` imports `guard_spec`, `guard_models`, and `guard_commit`,
    and `context_pin`/`session_start` import `guard_provenance`, so a mid-turn
    tree swap can mix versions for sub-second windows.

## The three accepted weakenings (assert them, do not close them)

These are the ONLY places where adding an entry may turn a BLOCK into an ALLOW.
Each needs a test that asserts it DOES bypass, plus a BYPASS or GRANT line
naming the responsible entry. A future change then has to be a conscious edit
rather than silent drift.

- **RISK-MST-01 - ANY-hotfix bypass.** With `[feature-a, hotfix-b]`,
  `guard_models`, `guard_commit`, Mode C, and Mode E are bypassed where
  `[feature-a]` alone would arm them. Unrelated feature work rides the emergency
  waiver. Accepted because blocking a declared production emergency behind an
  unrelated entry is the worse failure. Mitigated by the named BYPASS lines, the
  loud `HOTFIX:<slug>` in pin and digest, and METHOD.md making removal of the
  hotfix entry part of the already-mandatory postmortem.
- **RISK-MST-02 - ANY `test_scope`.** A blanket `"test_scope": true` on entry B
  unlocks test-file edits for entry A. Accepted because glob-scoped grants were
  scoped out. Mitigated by the GRANT line naming the granting entry when
  `len(tasks) > 1`.
- **RISK-MST-03 - ledger resurrection.** Remove entry A and re-add it before the
  next `write_ledger` prunes its record, and the new incarnation inherits the
  old dispatches. Accepted: narrow window, and the incarnation check was scoped
  out. Mitigated by a WORRIES row naming the fix.

Plus one residual that is not a weakening but has no mechanical control:
**RISK-MST-04** - nothing enforces Edit-over-Write. An agent can still `Write`
the whole file and drop a sibling entry. Doctrine is the only control, which is
why the FR-MST-24 wording carries real load.

## Known environment hazards (read this before you fight a hook)

These are recorded facts about this repo and this harness, confirmed on prior
workstreams. None is a defect in your work. Do NOT try to fix them, and do NOT
work around any hook.

1. **You will not be able to `git commit` from the worktree.** The harness runs
   every tool call with cwd and `CLAUDE_PROJECT_DIR` pinned to the MAIN
   checkout, so `guard_commit.git_cwd` resolves the branch as `main`, sees a
   protected branch, and blocks - even though the worktree really is on
   `task/multi-session-tasks`. `cd` does not persist between Bash calls and
   `git -C` does not help (the hook never reads the command args). This is a
   known P1 WORRIES row. **Do the work, verify it, `git add` your explicit paths
   (staging is NOT blocked), then hand me the exact commit message per band in
   your report.** I commit from the main checkout on your branch. Do NOT flip
   `active-task.json` to `type: hotfix` to earn a bypass, and do not reformulate
   the command to sneak past.
2. **File edits work fine.** Use the Edit/Write tools with ABSOLUTE worktree
   paths and they land correctly. Verification (`unittest`, `npm test`) runs
   fine from the worktree.
3. **`test_scope` is already open for you.** `guard_tests` reads it from the
   MAIN checkout, which a worktree copy cannot override. I have set
   `"test_scope": true` in main's `active-task.json` before dispatching you, so
   your test edits will pass. If you get blocked on a test path anyway, that is
   news - report it, do not route around it.
4. **`bash company/run-gates.sh` is RED BY DESIGN in this repo** and is NOT your
   gate. The tracked `company/gates.config` ships `CONFIGURE ME` placeholders on
   purpose (the dual-nature rule). Your gate ladder is the three commands named
   in the DoD. Do not "fix" `gates.config`.
5. **Your baseline, measured on main at `c83bf3c` immediately before this
   dispatch:** `python3 -m unittest discover -s tests/hooks -q` = **224 tests,
   OK**. `npm test` = **PASS 62, FAIL 0, ALL GREEN**. Any deviation from those
   numbers is yours to explain. (An older agent-memory note claims `npm test`
   has 10 pre-existing `pack MISSING` failures - that was fixed in PR #85 and is
   now stale. 62/0 is the truth.)
6. **`tests/install/test_tui.sh` can never be green in a wired checkout** - the
   installer copies the working-tree `gates.config` while the test asserts the
   tracked `CONFIGURE ME` placeholders. Known P2 WORRIES row. It is not in your
   gate ladder; do not chase it.

## Integration seams

- Single workstream, no parallel workstream to coordinate with. Nothing else is
  in flight: `test-infra-fixes` and `pack-state-leak` are merged, and the
  prerequisite (`tests/hooks/run_tests.sh` discovering every `test_*.py`) landed
  on main in `3b17591` - re-verify it, do not re-do it.
- You branch from `main` at `c83bf3c` or later.
- Contract changes and their only consumers, all inside your owned paths:
  `_common.active_task` REMOVED and `active_tasks` plus five helpers ADDED
  (consumers: this repo's hooks and test suite); `guard_provenance.read_ledger`
  return shape changes to a per-slug `tasks` map (consumers: `context_pin`,
  `session_start`, `guard_provenance` itself); `costs.log` task column may become
  `a+b` (consumer: the standup skill). `roster`, `execution_decision`,
  `valid_issues`, `tracking_untracked`, `fresh_audit`, and `staleness_reason`
  KEEP their signatures.
- No pack-list change: every touched shipped path is already covered by
  `package.json` `files`. `tests/` is not packed and `company/specs/**` is
  excluded. Do not touch `package.json`.

## Definition of Done

Universal DoD plus this task's specifics:

- [ ] Every FR in scope implemented, tested, or explicitly deferred with reason
- [ ] `python3 -m unittest discover -s tests/hooks -q` green - run it yourself
- [ ] `npm test` green - run it yourself
- [ ] `bash tests/install/run_tests.sh` green (the rollout proof)
- [ ] No edits outside owned directories; zero frozen surfaces patched locally
- [ ] Tests added for new behavior; tests are the oracle and are never edited to
      pass
- [ ] **The parity suite exists and passes:** for each of the ten consumer hooks
      and each of the six `guard_provenance` events, run the hook against (a) a
      v1 single-object file and (b) the equivalent v2 one-entry file, and assert
      identical exit code, stdout, stderr, and appended `adherence.log` line
- [ ] **The roughly 45 existing `set_task(obj)` call sites pass UNCHANGED**,
      except where an assertion pins message text that FR-MST-25 deliberately
      rewords. They are the v1-compat regression proof, so they are not
      otherwise rewritten - and EVERY text-only edit to an existing assertion is
      called out explicitly in your report, so a decision change cannot hide
      inside one. Add a `set_tasks(*objs)` helper BESIDE the existing
      `set_task(obj)`; do not replace it.
- [ ] **One "a second task must not disarm gate X" test per gate:**
      `guard_spec`, `guard_tests`, `guard_commit`, `stop_gate`, Modes C/D/E,
      `guard_models`
- [ ] **The reported bug as a test:** entries A and B active, A's two dispatches
      and one audit recorded, B added; assert `read_ledger` still reports A's
      dispatches and the audit, and that Mode C, Mode D, and Mode E all allow
      for A. Then remove B and assert the same.
- [ ] **The highest-value case as a test:** entries A and B both
      `"execution": "delegated"`, one recorded dispatch whose spawn prompt names
      only `task/b`; a main-checkout source edit exits 2 with a message naming A
      and a BLOCK line naming A. Then record a dispatch naming `task/a` and
      assert the edit is allowed.
- [ ] **An inventory test** asserting the ANY-bypass sites are EXACTLY
      `guard_models`, `guard_commit`, Mode C, Mode E - and that `guard_spec`,
      `guard_tests`, `stop_gate`, and Mode D use per-entry exemption instead
- [ ] The three weakenings each asserted deliberately by a test
- [ ] `python3 .claude/hooks/witness_check.py` green; registry checksum valid
- [ ] Live end-to-end check on this repo before you report: add two entries,
      confirm `context_pin` renders both and `session_start` digests both;
      remove one and confirm the other and its ledger record survive; remove the
      last and confirm the founding-commit exemption returns. Paste the output.
- [ ] `MODULE.md` created/updated in each owned directory that has one
- [ ] Commits follow `company/GIT.md`: conventional subject,
      `Task: multi-session-tasks` trailer, explicit staged paths, never
      `git add -A`
- [ ] Report follows `company/templates/REPORT-TEMPLATE.md`

There is no UI in this task, so there are no screenshots. Your evidence is the
gate ladder, the parity suite, and the live end-to-end check.

## Fallback assumptions

For every ambiguity, implement THIS stated assumption and tag the site
`# OQ-MST-NN assumption`. Do not guess, do not ask the user.

- **OQ-MST-01**: Maximum number of entries? FALLBACK: **no hard cap, no block**.
  Display truncates at 3 with `and <n> more`. A cap would be a magic number in a
  gate, which the invariants forbid.
- **OQ-MST-02**: Duplicate slugs in the list? FALLBACK: **tolerate, do not
  dedupe, do not block**. Each entry evaluates independently; ledger records for
  duplicate slugs merge under the one key. Doctrine states slugs are unique per
  working tree.
- **OQ-MST-03**: An entry with a missing or empty `task` slug? FALLBACK: **the
  entry still counts** for existence and type rules (preserving today's `{}`
  behavior at `guard_commit` and `stop_gate`); it renders as `<task-slug>`; it
  keys in the ledger under the empty string and can never be credited an
  attributed dispatch at N>1, so a slugless `delegated` entry blocks Mode E
  until it is given a slug. Fail-closed and correct.
- **OQ-MST-04**: Dispatch attribution matching at N>1? FALLBACK:
  **case-sensitive substring match** of the entry slug against the concatenation
  of the spawn `prompt` and `description` fields. No word boundary, no
  normalization. Doctrine already requires `task/<slug>` in the spawn prompt.
- **OQ-MST-05**: How does `standup` report cost when the task column is `a+b`?
  FALLBACK: **containment match, summed, flagged approximate**. A line counts
  toward every entry whose slug it contains, and the output states that
  multi-task lines are attributed to all of them. No splitting.
- **OQ-MST-06**: `risk_score` with N>1 and no `--brief`? FALLBACK: **exit code
  unchanged, brief-derived signals omitted, one note** naming the active entry
  count and telling the caller to pass `--brief`.
- **OQ-MST-07**: Should ledger `self_authored` become per-slug? FALLBACK:
  **global**. It derives from edited paths in the shared tree with no reliable
  attribution to an entry. It is a tree fact.
- **OQ-MST-08**: Should `nudge_state` be global or per-slug? FALLBACK:
  **per-slug**, inside `tasks[<slug>]`. The nudge text names a slug, so a global
  fingerprint would suppress a true nudge for a second entry.
- **OQ-MST-09**: `active-task.json` read mid-write by another session (partial
  or invalid JSON)? FALLBACK: **today's behavior, unchanged** -
  `read_json_file` returns None, `active_tasks` returns `[]`, and gates
  requiring an entry fall open for that one invocation. No retry loop, no lock,
  no backoff: a retry loop in a fail-open hook adds more risk than it removes.
- **OQ-MST-10**: Is multi-session concurrency a SUPPORTED, documented capability
  for clients, or an internal tolerance? FALLBACK: **documented as supported in
  `docs/glossary.md` and the METHOD wording, with no marketing claim**. This one
  is an owner decision recorded for `DECISIONS.md`; the build does not wait on
  it and a veto costs only a wording edit.

## Out of scope

Explicitly, so nobody helpfully expands. Each of these was considered and
dropped, most by owner decision.

- **`test_scope` glob lists** - the planned fix for RISK-MST-02. Dropped by the
  owner. `test_scope` stays a boolean and the ANY grant is logged, not narrowed.
- **The ledger incarnation check** - the planned fix for RISK-MST-03. Dropped by
  the owner.
- **The `session_start` line-reservation fix** - `MAX_LINES` can still hide the
  task digest behind a saturated RESUME/STATUS. Pre-existing WORRIES row, stays
  one.
- **An `ALWAYS_RECIPES` message map** - edit block messages in place; no new
  message-registry abstraction.
- **A `risk_score --task` flag.**
- **Per-branch or per-worktree gate stamps** - one checkout is one working tree
  and one branch; `gates.status` staleness is an honest shared fact, and scoping
  it would remove real enforcement, not friction.
- **Scoped `work_hash`** - same reason; the hash fingerprints the tree.
- **Session leases, locks, or any advisory-lock mechanism.**
- **Session-id-keyed state, per-session `company/state`, or any use of
  `session_id` beyond today's `cost_capture` log column.**
- **A hotfix TTL.**
- **An `active_task.py` CLI** to add and remove entries. Doctrine plus targeted
  Edit is the mechanism; the residual is accepted and recorded as RISK-MST-04.
- **Freezing `active-task.json`** (a `guard_frozen` rule blocking `Write` while
  allowing `Edit`). Named as the escalation path for RISK-MST-04, roughly eight
  lines, but NOT built now.
- **Fixing the two pre-existing WORRIES rows this change brushes against**:
  dispatched worktree agents cannot commit (`guard_commit.git_cwd`), and
  `guard_tests` resolving `test_scope` from the main checkout. Both real, both
  out of this brief, both stay WORRIES rows.
- **Scaffolding `active-task.json` at install or update.**
- **Any change to `guard_secrets`, `guard_frozen`, `no_slop`, `trace_check`,
  `witness_check`, `gate_stamp`, or `gates_detect`.**
- **Real gate commands in `company/gates.config`** - the dual-nature rule
  stands; the tracked config keeps its `CONFIGURE ME` placeholders.
- **Adding `active-task.json` to `company/frozen-surfaces.json`.**
- **Any `package.json` change.**

## Report back

Your report must contain, as facts: what changed (paths), the full gate ladder
output pasted (`python3 -m unittest discover -s tests/hooks -q`, `npm test`,
`bash tests/install/run_tests.sh`), the FR checklist FR-MST-01 through
FR-MST-31, the ownership diff summary, the live end-to-end check output, every
text-only edit you made to an existing test assertion and why, CRs filed,
deviations from this brief and why, and worries for the CEO. Do not ask the user
questions - file a CR or surface it in your report.
