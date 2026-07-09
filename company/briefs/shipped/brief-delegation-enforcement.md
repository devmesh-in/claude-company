# BRIEF: delegation-enforcement

_Type: feature. Spec: owner-approved plan (content embedded below - this brief
is self-contained). Lead: tech-lead. Date: 2026-07-10._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Make the company hierarchy self-enforcing against context decay. Today the
CEO session forgets its team exists after a few turns and builds features
itself; nothing mechanical stops it. Ship five layers - a per-turn status pin,
a mid-flight drift nudge, an execution-decision gate at the first source edit,
doctrine that makes dispatch the default path, and a provenance backstop that
blocks committing or closing self-authored work without an independent audit.
Hard constraint: ZERO magic numbers and ZERO role bans - every blocking rule
derives from METHOD.md mechanism 5 (never let the producer grade itself) or
from consistency with the actor's own written record. Success is observable:
the smoke drill in the DoD passes end to end.

## Read first (in order)

1. `CLAUDE.md` (project canon)
2. `company/METHOD.md` (how the team works; mechanism 5 is the invariant you
   are mechanizing)
3. `.claude/hooks/_common.py` (helpers you MUST reuse: read_stdin_json,
   project_root, iso_now, adherence_log, block, log_bypass, read_json_file,
   active_task, rel_path, _git, work_hash, stamp_checksum, check_stamp)
4. `.claude/hooks/guard_models.py` (the manifest+hook precedent;
   SPAWN_TYPE_FIELDS lives here)
5. `.claude/hooks/guard_spec.py` (is_source and EXEMPT_DIRS - reuse, never
   redefine source-ness)
6. `.claude/hooks/guard_commit.py` (segments, git_subcmd, git_cwd - reuse for
   Bash parsing)
7. `.claude/hooks/stop_gate.py` and `.claude/hooks/session_start.py` (shapes
   to mirror / extend)
8. `tests/hooks/test_hooks.py` (test conventions: Base class, run_hook
   subprocess pattern, fixture roots) and `tests/hooks/run_tests.sh`
9. `.claude/settings.json` (current hook wiring - your additions go on top of
   exactly this)

## You own

- `.claude/hooks/` - new `guard_provenance.py`, new `context_pin.py`, small
  edits to `session_start.py` and `guard_frozen.py` (ALWAYS_DEFAULTS) only
- `tests/hooks/` - new test files (suggest `test_guard_provenance.py`,
  `test_context_pin.py`) plus a session_start case; never weaken existing tests
- `company/provenance.json` (new manifest)
- `company/frozen-surfaces.json` (add one `always` entry)
- `.claude/settings.json` (wiring additions only - do not reorder existing
  hooks)
- `ORCHESTRATOR.md`, `company/METHOD.md`,
  `.claude/skills/orchestrator/SKILL.md` (the doctrine passes specified below)

Nothing else. Anything not listed is read-only to you. If the fix you need
lives outside these paths, report it; do not make it.

## Invariants in play (must not break)

- METHOD.md mechanism 5: never let the producer grade itself. Your build
  mechanizes it; it must not weaken it anywhere else.
- Every hook fails OPEN on internal errors (except SystemExit re-raise) -
  match the house wrapper exactly. Enforcement is anti-accident, not
  anti-adversary.
- Hooks are role-blind: the ONLY actor discriminator is path/cwd under
  `.claude/worktrees/` vs the main checkout. Never attempt role detection.
- `_common.work_hash()` excludes `company/state/` - the ledger MUST live
  there so hook writes never stale the gates stamp.
- Python 3.8 stdlib only. No new dependencies.
- All writing hook-clean: straight quotes, ' - ' not em dashes, three dots
  not the ellipsis character - INCLUDING hook source, block messages, tests,
  and doctrine prose (no_slop blocks you otherwise).
- NO magic thresholds anywhere. If you find yourself writing a numeric limit
  into enforcement logic, stop and re-read the Mission.

## Frozen surfaces nearby (CR, never edit)

- `company/state/gates.status`, `company/state/adherence.log`,
  `company/state/costs.log` - written only by existing machinery.
- You ADD `company/state/provenance-ledger.json` to the frozen `always` lists
  (registry + guard_frozen.ALWAYS_DEFAULTS); your hook writes it via plain
  file IO (hooks do not trigger hooks) - same pattern as gates.status.
- Lockfiles, `.env*` - untouchable as always.

## Scope (ordered)

1. **FR-DE-01 manifest.** New `company/provenance.json`:
   `{"$comment": ..., "version": 1, "verifier_roles": ["auditor", "security-reviewer"], "builder_roles": ["tech-lead", "developer", "qa-engineer"]}`.
   Missing file = every mode silently allows (fail-open rollout switch, same
   posture as company/models.json).
2. **FR-DE-02 ledger.** `company/state/provenance-ledger.json`, written ONLY
   by guard_provenance via tempfile-in-same-dir + os.replace:
   `{"version": 1, "task": <slug>, "self_authored": [{path, at}], "audits": [{role, at, work_hash, verdict}], "dispatches": [{role, at}], "nudge_state": {fingerprint, at}?, "checksum": <c.stamp_checksum of the rest>}`.
   Checksum-validated on read: tampered/corrupt = audits and dispatches read
   as EMPTY (blocks stay honest) while writes start from a fresh ledger.
   Reset the content whenever `task` != active slug. Add the path to
   `company/frozen-surfaces.json` `always` AND `guard_frozen.ALWAYS_DEFAULTS`.
3. **FR-DE-03..08 `guard_provenance.py`** - one script, standard fail-open
   wrapper, dispatch on (hook_event_name, tool_name). Import _common as c,
   guard_commit, guard_spec (they guard main() under __name__). Helpers:
   load_manifest; in_worktree_or_out_of_tree (normalized abs path contains
   `/.claude/worktrees/` or is not under root); dirty_source_paths(root) -
   parse `git status --porcelain -- . ':(exclude)company/state'` via c._git,
   rename `a -> b` takes b, filter guard_spec.is_source;
   read_ledger/write_ledger; fresh_audit (any audit with work_hash ==
   c.work_hash(root) and verdict != "do-not-ship"); role_of (iterate
   guard_models.SPAWN_TYPE_FIELDS); execution_decision(task) -> "self" |
   "delegated" | None (None unless execution is valid AND execution_why is a
   non-empty string); roster(root) (sorted union of manifest roles +
   company/models.json roles when readable); emit_nudge(text) (prints
   json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
   "additionalContext": text}}), exit 0 - keep emission isolated in this one
   function).
   - **FR-DE-03 Mode A** (PostToolUse Edit|Write|MultiEdit; telemetry +
     nudge; never blocks): main-checkout source edit during an active task ->
     append {path, at} to self_authored (dedupe by path). Same
     read-modify-write cycle, evaluate the ONE nudge condition: type in
     ("feature", "program") AND execution_decision == "self" AND
     len(dispatches) == 0. Condition true and nudge_state.fingerprint !=
     "self-idle": set nudge_state, adherence_log NUDGE, emit_nudge with
     exactly: `[company] Reminder - task '<slug>' runs with execution:
     "self" and zero dispatches: the team is idle while you build. That is
     allowed and recorded, and the standing price applies - every
     self-authored commit needs a fresh read-only auditor pass before it
     integrates (one Task call, subagent_type: auditor). If this work is
     growing beyond glue, a tech-lead dispatch is cheaper: verification
     comes free through the hierarchy. This note fires once per state; it
     will not repeat.` Condition false and nudge_state set: clear it
     silently. No counters, no timers - state-change dedup only.
   - **FR-DE-04 Mode B-pre** (PreToolUse Task|Agent; telemetry; never
     blocks): role in builder_roles and active task exists -> append
     {role, at} to dispatches; adherence_log DISPATCH.
   - **FR-DE-05 Mode B-post** (PostToolUse Task|Agent; the audit record):
     role in verifier_roles and active task exists -> append {role, at,
     work_hash: c.work_hash(root), verdict} to audits; adherence_log AUDIT.
     Recorded at COMPLETION deliberately (the auditor runs gates, which can
     create untracked artifacts that change work_hash; recording after
     mirrors gate_stamp). verdict: scan str(tool_response) for the literal
     token `DO-NOT-SHIP` -> "do-not-ship" (recorded but does NOT unblock);
     else "unknown" (unblocks); any parse trouble -> "unknown". Skip when
     payload cwd is in a worktree (a lead's internal reviewer is not the
     integrator's audit).
   - **FR-DE-06 Mode C** (PreToolUse Bash; the layer-5 commit gate): for
     each guard_commit.segments() segment whose git_subcmd is "commit":
     manifest missing -> allow; active task not a dict -> allow (founding);
     type hotfix -> log_bypass, allow; payload cwd in worktree/out-of-tree
     -> allow; os.path.isfile(<root>/.git/MERGE_HEAD) -> log_bypass "merge
     conclusion", allow; dirty_source_paths empty -> allow; fresh_audit ->
     allow; else c.block with the exact recipe message in the appendix
     (interpolate slug, staleness reason, up to 5 paths then "... and N
     more"). `git merge` segments: untouched (guard_commit's stamp check
     covers integration of hierarchy-verified work).
   - **FR-DE-07 Mode D** (Stop; the layer-5 close gate): mirror
     stop_gate.py exactly - stop_hook_active first, no task or type in
     ("quick", "hotfix") -> exit 0, manifest missing -> exit 0; then
     dirty_source_paths non-empty and no fresh_audit -> adherence_log BLOCK
     + print {"decision": "block", "reason": "Active task '<slug>' has
     self-authored source changes in the main checkout with no fresh
     independent audit. Dispatch the auditor (Task tool, subagent_type:
     auditor) and commit the audited work, or move it to a worktree task
     branch, before finishing."}; exit 0.
   - **FR-DE-08 Mode E** (PreToolUse Edit|Write|MultiEdit; the layer-3
     execution gate): check order, each miss = silent allow: file_path
     present; rel/cwd not under .claude/worktrees/ and in-tree;
     guard_spec.is_source; manifest present; active task is a dict; type in
     ("feature", "program") - quick exempt by definition, hotfix ->
     log_bypass, allow. Then on execution_decision(task): "self" -> allow;
     "delegated" -> dispatches >= 1 allow (glue lane), == 0 block with
     appendix message 2 (contradiction); None -> block with appendix
     message 1 (undecided, roster interpolated).
4. **FR-DE-09 `context_pin.py`** (UserPromptSubmit; layer 1): pure read
   (import _common as c, import guard_provenance as gp). No active task ->
   silent exit 0. Else print to stdout and exit 0 (stdout is injected as
   context; keep emission in one emit(text) helper). TOKEN BUDGET IS THE
   DESIGN CONSTRAINT: one terse line always -
   `[company] <slug> <type> exec=<self|delegated|undecided> disp=<n> self=<n>`
   - plus a second line ONLY when drifty (feature/program with exec
   undecided or dispatches == 0):
   `[company] team idle - decide execution / dispatch a tech-lead`.
   quick/hotfix/ideation: line 1 only, without `exec=`. NEVER inject the
   roster (it is already in the system prompt) or doctrine prose. Total
   output under 160 characters in every case; never blocks; fails open.
5. **FR-DE-10 wiring** (`.claude/settings.json`, additions only): append
   guard_provenance.py to PreToolUse `Edit|Write|MultiEdit` (after
   guard_models - mode E runs last), PreToolUse `Task|Agent` (after
   guard_models), PreToolUse `Bash` (after guard_tests), and `Stop` (after
   stop_gate, before cost_capture). NEW top-level `PostToolUse` array:
   matcher `Edit|Write|MultiEdit` -> guard_provenance.py; matcher
   `Task|Agent` -> guard_provenance.py. NEW top-level `UserPromptSubmit`
   (no matcher key, like Stop) -> context_pin.py. Preserve every existing
   entry and order.
6. **FR-DE-11 session_start digest line**: inside the existing active-task
   block (session_start.py line ~49), append one line via gp helpers, counts
   0 when ledger missing/tampered:
   `execution: <self|delegated|undecided> | dispatches: <n> | self-authored: <n> files | team: <roster comma-joined>`.
7. **FR-DE-12 active-task schema**: no code - the optional fields
   `execution`, `execution_why`, `reclassified_why` are documented in the
   doctrine pass (METHOD.md state table row).
8. **FR-DE-13 doctrine pass** (exact replacement prose in the appendix):
   ORCHESTRATOR.md "Your role" first bullet swap + new operating-loop step
   between Brief and Dispatch + "Quality bar" extension + step-6/7 audit
   order note; SKILL.md classify-sentence rewrite; METHOD.md mechanism 5
   enforcement paragraph + provenance-ledger.json state-table row +
   active-task.json row note.
9. **FR-DE-15 tracking gate (ADDENDUM, owner-directed 2026-07-10)**: in PR
   mode, feature/program work cannot START untracked. Details:
   - `pr_mode(root)` helper in guard_provenance: True when
     `git remote get-url origin` succeeds (via c._git). False/error -> the
     whole gate is silently off (local mode, fail open).
   - active-task.json optional field `"issues": [<int>, ...]` - the
     tracking record. Valid = non-empty list of ints.
   - **Mode B-pre extension**: BEFORE recording dispatch telemetry, if
     role is in builder_roles AND active task type in ("feature",
     "program") AND pr_mode AND issues invalid -> c.block with the message
     in Appendix A3 (this is the ONE place Mode B-pre may block; telemetry
     append still never blocks). Hotfix -> log_bypass, allow. Verifier and
     non-builder spawns never blocked.
   - **Mode E extension**: same condition checked immediately before the
     execution-decision check (undecided message comes after; a task
     missing both gets the tracking block first) -> Appendix A3 message.
   - **Context pin**: when pr_mode and feature/program and issues invalid,
     line 1 gains ` iss=0` (drift signal; otherwise no iss segment - keep
     tokens flat).
   - No `gh` calls and no network inside hooks - presence of the list is
     the record; visibility guards honesty.
   - Tests: builder spawn blocked without issues (stderr has "gh issue
     create"); allowed with issues=[42]; verifier spawn never blocked;
     quick task never blocked; no-origin fixture -> gate off (use the
     bare init_git fixture without a remote, and add a remote via
     `git remote add origin <dummy>` for the PR-mode cases); Mode E
     tracking block fires before the undecided block; hotfix BYPASS
     logged; context pin shows iss=0 only in the drift case.
10. **FR-DE-14 tests**: new classes/files per conventions (subprocess
   run_hook, throwaway fixture roots, init_git where needed). Matrix:
   - Execution gate: no decision -> exit 2 stderr has "execution" + roster;
     self+why -> allow; self without why -> block; delegated + 0 dispatches
     -> exit 2 "contradicts"; seed dispatch via real Mode B-pre payload then
     delegated edit -> allow; worktree file path -> allow; worktree cwd ->
     allow; quick -> allow; hotfix -> allow + BYPASS logged; .md target ->
     allow; missing manifest -> allow; no task -> allow; garbage stdin ->
     allow.
   - Provenance commit gate: dirty source + no audit -> exit 2 naming
     auditor + path; fresh audit -> allow; edit-after-audit stale -> block;
     clean tree -> allow; dirty non-source -> allow; missing manifest ->
     allow; no task -> allow; hotfix BYPASS logged; worktree cwd -> allow
     despite dirty main; MERGE_HEAD -> allow; DO-NOT-SHIP verdict does not
     unblock; tampered ledger = no audit; ledger resets on slug change.
   - Stop gate: block (reason names slug + auditor) / audited allow / quick
     silent / stop_hook_active silent.
   - Drift nudge: first offending edit -> stdout JSON
     hookSpecificOutput.additionalContext contains "auditor" + ledger
     nudge_state set; second identical -> empty stdout; dispatch then edit
     -> silent + nudge_state cleared; new slug re-arms; worktree silent;
     delegated silent; quick silent.
   - Context pin: no task -> empty stdout; feature undecided -> exactly two
     lines with exec=undecided and "team idle"; feature delegated + 1
     dispatch -> exactly one line disp=1; quick -> one line, no exec=;
     disp/self counts reflect seeded ledger; output < 160 chars in every
     case; garbage stdin -> exit 0.
   - session_start: feature task + ledger -> digest contains "execution:".
   - Full existing suite stays green.

## Integration seams

- guard_commit/stop_gate/gate_stamp/_common: READ-ONLY seams - import their
  functions; zero edits to those files. If a needed seam is missing, report
  it, do not patch it.
- Existing hooks continue to fire before yours; do not change their order.
- The auditor agent definition (.claude/agents/auditor.md) is read-only
  context; its report template's DO-NOT-SHIP token is the verdict seam.

## Definition of Done

Universal DoD plus this task's specifics:
- [ ] Every FR-DE above implemented and tested, or explicitly deferred with
      reason in the report
- [ ] `bash company/run-gates.sh` green in the worktree - run it yourself
      before reporting (npm install in the worktree first if node_modules is
      absent; never `git add -A`)
- [ ] No edits outside owned paths; zero frozen surfaces patched locally
- [ ] Smoke drill executed by piping payloads into the hooks (no UI - this
      replaces Playwright QA) and the transcript pasted in the report:
      (a) feature task, no decision, source-edit payload -> Mode E block
      with roster; (b) execution delegated + why, edit -> contradiction
      block; (c) simulated tech-lead PreToolUse spawn payload, edit ->
      allow; (d) execution self, edit -> allow + exactly one nudge JSON,
      second edit silent; (e) commit payload with dirty source -> Mode C
      block; simulated auditor PostToolUse payload -> allow; edit again ->
      stale block; (f) UserPromptSubmit payload -> pin line(s) correct and
      under 160 chars; (g) session_start output carries the execution line.
- [ ] Tests added for all new behavior (tests are the oracle - never edited
      to pass); existing suites untouched and green
- [ ] DO NOT COMMIT - known issue #37 blocks subagent worktree commits. Leave
      the work uncommitted in the worktree, stage NOTHING, and report; the
      CEO lands the commit. This supersedes the GIT.md commit DoD line.
- [ ] MODULE.md: create/refresh `.claude/hooks/MODULE.md` if present pattern
      exists; otherwise cover the change inventory in the report
- [ ] Report follows `company/templates/REPORT-TEMPLATE.md` and proposes 1-3
      single-line verbatim witness markers (they must exist verbatim on ONE
      line in the shipped files - see W-010 lesson)

## Fallback assumptions

- OQ-DE-01: exact JSON schema for UserPromptSubmit injection differs from
  stdout-print? -> FALLBACK: plain stdout + exit 0 (documented behavior);
  keep emission isolated in emit() so a schema swap is a one-function
  change. Tag `# OQ-DE-01 assumption`.
- OQ-DE-02: PostToolUse payload field name for the subagent result
  (tool_response vs tool_result)? -> FALLBACK: read
  payload.get("tool_response") and fall back to payload.get("tool_result"),
  stringify defensively. Tag `# OQ-DE-02 assumption`.
- OQ-DE-03: tests directory layout for new suites? -> FALLBACK: new files
  test_guard_provenance.py and test_context_pin.py importing the Base
  helper from test_hooks.py if importable, else replicating the minimal
  pattern locally.
- OQ-DE-04: `ideation` task type in Mode E/context pin? -> FALLBACK: treat
  like quick (line 1 only, no gate) - ideation never edits source by
  doctrine.
- OQ-DE-05: MultiEdit payload shape for new text extraction in telemetry?
  -> FALLBACK: mirror guard_models.new_text (content / new_string /
  edits[].new_string joined).

## Out of scope

- Bash-escape telemetry (redirect writes into source paths) - enforcement
  already derives from git; telemetry gap is accepted v1 (future issue).
- Any change to guard_commit.py, stop_gate.py, gate_stamp.py, _common.py,
  guard_secrets.py, cost_capture.py, risk_score.py, witness_check.py,
  trace_check.py.
- Issues #36 and #37 (separate tasks).
- Budgets, quotas, line counts, role bans of any kind - explicitly rejected
  by the owner.
- Deploy/release anything - never.

## Report back

Your report must contain, as facts: what changed (paths), gate results (paste
the ladder), FR-DE checklist, ownership diff summary (`git diff --stat` and
`git status --porcelain` since you will not commit), the smoke-drill
transcript, CRs filed, deviations from this brief and why, proposed witness
markers, worries for the CEO.

---

## Appendix A - exact block messages (hook-clean; interpolations in <>)

Mode E message 1 (undecided):
```
BLOCKED: source edit on a feature/program task with no execution decision.
Decide HOW task '<slug>' executes and record it in company/state/active-task.json
(add both fields, then retry the edit):
  "execution": "delegated", "execution_why": "<one line>"
      - the default: dispatch a tech-lead; developers build in worktrees and
        verification comes free through the hierarchy.
  "execution": "self", "execution_why": "<one line>"
      - you build it; every self-authored commit then requires a fresh
        read-only auditor pass before it integrates (enforced at commit and
        at task close).
Team on payroll: <roster, comma-joined>.
Worktree edits are never gated by this. Production emergency: set
"type": "hotfix" in active-task.json (logged, never silent).
```

Mode E message 2 (delegated contradiction):
```
BLOCKED: active-task.json records execution: "delegated" for task '<slug>',
but no dispatch has happened and this is a source edit in the main checkout.
That contradicts your own written decision. Fix either side:
1) Dispatch first (Task tool, subagent_type: tech-lead) - after a dispatch,
   main-checkout glue edits flow freely.
2) Or change the record: set "execution": "self" with a fresh
   "execution_why" - self-built work then pays the mandatory audit at commit.
Production emergency: set "type": "hotfix" (logged, never silent).
```

Mode C message (commit gate):
```
BLOCKED: git commit contains self-authored work with no independent verification.
Task '<slug>' has source changes produced in the main checkout, and no audit
covers the current tree (<no audit recorded | audit is stale - the tree
changed after the last audit | last audit verdict was DO-NOT-SHIP>).
Self-authored paths: <up to 5 paths, then '... and N more'>
Nothing integrates on the authority of the context that produced it
(company/METHOD.md, mechanism 5). Fix, in order:
1) Run `bash company/run-gates.sh` until green.
2) Dispatch the read-only auditor over your diff (Task tool,
   subagent_type: auditor). Its completion is recorded automatically.
3) Retry the commit WITHOUT editing source in between - any edit stales the
   audit, which is correct.
Cheaper alternative for anything beyond glue: move the work to a worktree
task branch and give it to a developer - delegated work is verified inside
the hierarchy and needs no extra audit.
Production emergency: set "type": "hotfix" in company/state/active-task.json
(logged, never silent).
```

Appendix A3 - tracking gate message (Mode B-pre builder spawn / Mode E):
```
BLOCKED: task '<slug>' is a <type> task in PR mode with no tracking issues
recorded. All work ships through GitHub here (owner rule) - work that is not
tracked does not start. Self-serve fix:
1) Create one issue per deliverable: gh issue create --title ... --body ...
2) Record the numbers in company/state/active-task.json:
   "issues": [<n>, ...]
3) Retry. The integration PR body will close them (Closes #<n> ...).
No remote configured = this gate is off (local mode). Production emergency:
set "type": "hotfix" (logged, never silent).
```

## Appendix B - exact doctrine prose

ORCHESTRATOR.md - replace the first "Your role" bullet (the one beginning
"**You code, with judgment about what is yours vs. theirs.**") with:

```
- **You code whenever coding is the fastest correct path - but nothing you
  write integrates on your own authority.** There is no line budget and no
  time budget. The economics are enforced instead: any source change produced
  in the main checkout is self-authored, and the provenance hook blocks its
  commit (and the task's close) until the read-only auditor has passed over
  the exact tree you are committing. Delegated work already pays that cost
  inside the hierarchy - developers report, the lead verifies, you judge the
  lead's diff - so a worktree merge needs no extra audit. Price it before you
  start: self-build = build + a mandatory audit dispatch + no self-merge on
  the remote; delegate = verification comes free through the hierarchy. Glue
  and small fixes are cheap to audit - that is just 'PRs need review'.
  Anything beyond glue is cheaper to delegate, not because a rule says so but
  because the arithmetic says so. Record either way in STATUS and the
  module's MODULE.md changelog.
```

ORCHESTRATOR.md - insert a new operating-loop step between step 4 (Brief) and
step 5 (Dispatch), renumbering the rest or labeling it 4b:

```
4b. **Decide execution, in writing.** For feature and program tasks, before
    the first source edit in the main checkout, record the decision in
    company/state/active-task.json: "execution": "delegated" (the default -
    one tech-lead per workstream) or "execution": "self" (the exception),
    each with a one-line "execution_why". A hook blocks main-checkout source
    edits until the decision exists, and blocks them under delegated until at
    least one dispatch has actually happened - a written decision the
    behavior contradicts is a briefing error, not a suggestion. Decide while
    context is fresh; the status line pinned to every turn shows the
    decision, the dispatch count, and the idle flag.
```

ORCHESTRATOR.md "Quality bar": extend the line "auditor double-checks the big
ones" to "auditor double-checks the big ones, and every self-authored
commit - the provenance hook enforces that last one mechanically." In step 7
(Integrate), add one sentence: "Order for self-authored work: gates green
first, then the auditor pass, then ONE commit of the audited work - a commit
moves HEAD, which stales both the stamp and the audit, so splitting means
rerunning both, which is correct."

.claude/skills/orchestrator/SKILL.md - in "The engagement", extend the
"Work given" bullet's classify sentence so the default path is explicit:

```
For feature and program work the path is: spec, sealed brief, record
"execution": "delegated" in active-task.json, dispatch tech-leads. Building
it yourself is the exception: it requires the written "execution": "self"
decision (a hook enforces this at the first source edit) and every
self-authored commit pays a mandatory read-only audit before it integrates.
```

company/METHOD.md - append to mechanism 5:

```
This applies to the CEO mechanically, not just as prose: the provenance hook
(.claude/hooks/guard_provenance.py, manifest company/provenance.json) blocks
commit and task close while the main checkout holds source changes no
independent verifier context has audited at the current tree state. Delegated
worktree work is exempt - its verification already happened inside the
hierarchy.
```

company/METHOD.md state table: add row
`provenance-ledger.json | Audit and dispatch records for the task in flight (written only by the provenance hook).`
and extend the active-task.json row's description with: "carries the task's
written execution decision (execution / execution_why) for feature/program
work, plus reclassified_why on downgrades".
