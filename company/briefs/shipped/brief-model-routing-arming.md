# BRIEF: model-routing-arming

_Type: feature. Spec: company/specs/spec-model-routing-arming.md (reference only - this brief is your sealed work order).
Lead: tech-lead. Date: 2026-07-22. Tracking issues: #74, #75, #76._

> Schema, contracts, kernel, and anything in `company/frozen-surfaces.json` are
> FROZEN - consume them exactly as shipped; any change goes through
> `company/change-requests/`, never a local edit. (This task touches no frozen
> surface - verified against the registry.)

## Mission

Arm the model-routing enforcement that shipped as code without teeth. A live
incident (stamped project company-brain, 2026-07-22, found via billing
telemetry) proved three holes: built-in agent types (Explore, general-purpose,
Plan, claude) have no manifest pin so a bare spawn silently inherits the
SESSION model against the project's Opus-only routing; the models gate
(`guard_models.py --check`) stays green even when the Task|Agent spawn hook is
not wired into settings.json (code-without-wiring was the exact live failure);
and the Workflow tool fires no hook events at all. Success is observable: a
bare or contradicting spawn of a built-in type BLOCKS with a message naming the
exact model to pass; the models gate goes RED when the spawn wiring is missing;
existing installs receive all of it automatically on the next
`claude-company update` with their models.json customizations preserved. Hard
constraint that must survive: hooks fail OPEN on any manifest problem (old
manifests without a builtins section behave exactly as today) - only `--check`
fails LOUD.

## Read first (in order)

1. `CLAUDE.md` (project canon - the dual-nature rule especially)
2. `company/METHOD.md` (how the team works)
3. `.claude/hooks/guard_models.py` (the enforcer you extend)
4. `.claude/hooks/_common.py` (`block`, `log_bypass`, `active_task`, `read_json_file`, `project_root`)
5. `company/models.json` (the routing manifest template)
6. `.claude/settings.json` (the shipped hook wiring - note the existing `Task|Agent` PreToolUse group)
7. `install.sh` (section 5: the settings.json merge heredoc; the models.json copy-if-absent line ~125)
8. `update.sh` (`config_if_absent "company/models.json"` ~line 248; `finalize_merge` FR-UPD-08 infrastructure; the settings merge heredoc)
9. `lib/payload_paths.sh` (what propagates by overwrite vs config-if-absent)
10. `tests/hooks/test_hooks.py` (`TestGuardModels`, ~lines 375-514)
11. `tests/install/test_update.sh` (the update suite you extend)
12. `ORCHESTRATOR.md` (dispatch section - doctrine target)

## You own

- `.claude/hooks/guard_models.py`
- `company/models.json`
- `install.sh` (the models.json merge addition only)
- `update.sh` (the models.json merge addition only)
- `company/METHOD.md` (Workflow-tool doctrine addition only)
- `ORCHESTRATOR.md` (Workflow-tool doctrine line only)
- `company/GATES.md` (optional one-line G7 note that the gate also asserts wiring - doc-only)
- `tests/hooks/test_hooks.py`
- `tests/install/test_update.sh`

Nothing else. Anything not listed is read-only to you. If the fix you need
lives outside these paths, report it; do not make it.

## Invariants in play (must not break)

- Python 3.8 stdlib only in hooks. Hooks fail OPEN (internal error lets the
  action through); `guard_models --check` is one of the loud exceptions and
  must fail RED, never silently green, when wiring is unproven.
- Dual-nature rule: `company/` ships verbatim into installs. `models.json`
  content must stay generic (pins are `"opus"`, the template default). NEVER
  put this repo's real gate commands into `company/gates.config`.
- `.claude/hooks/` and doctrine files (`company/METHOD.md`, `ORCHESTRATOR.md`)
  are overwrite payload - changes propagate on update automatically.
  `company/models.json` is config-if-absent - it does NOT propagate by
  overwrite; that is exactly why the additive merge exists.
- The models.json merge python must be byte-identical between `install.sh` and
  `update.sh` (same rule as the settings merge - see the issue-67 precedent).
- Deterministic installs / bin-vs-bare parity: when `builtins` is already
  present (every fresh install from the new template), the merge must leave the
  file byte-unchanged - write only when injecting.
- macOS bash 3.2 compatible shell (no associative arrays, no readarray).
- All-opus, no tiering (owner rule): the four builtins pin to `"opus"`.
- Principled enforcement: pin values come from the manifest, never hardcoded in
  the hook; block messages derive the model name from the manifest.
- no_slop on ALL writing including docs and test strings: straight quotes,
  ' - ' not em dashes, three dots not the ellipsis character, no stock filler.
- `company/witnesses.json` is checksum-sealed - do not touch it. Accepted ADRs
  are immutable - do not touch them.
- Existing `TestGuardModels` tests must stay green unmodified (tests are the
  oracle - never edited to pass; extending the class with new tests is fine).

## Frozen surfaces nearby (CR, never edit)

- `company/state/install-manifest.json` and
  `company/state/.update-backups/**` are frozen (machine-written). Your update
  tests exercise them via the update engine only - never write them directly.
- No file you edit is in the frozen registry (verified). If you believe you
  need one, file a CR and report; do not edit.

## Scope (ordered)

1. **FR-MRA-01** `company/models.json`: add a `builtins` object mapping
   `Explore`, `general-purpose`, `Plan`, `claude` each to `"opus"`, plus a
   `$comment` inside it stating: built-in agent types have no frontmatter pin,
   so a bare spawn inherits the session model - guard_models therefore requires
   an explicit matching `model` override for these; and the Workflow tool is
   hook-invisible (its agent() spawns fire no PreToolUse events) and forbidden
   by default - see METHOD.md. Leave `roles`, `pricing`, `version`, and the
   top-level `$comment` unchanged.
2. **FR-MRA-02** `guard_models.py`: add `load_builtins(root)` returning the
   `builtins` map or `None` when absent/malformed/unreadable. `None` fails
   open everywhere (old manifests must not break).
3. **FR-MRA-03/04/05, BR-MRA-01/02/03** `handle_spawn`: when the spawn type is
   absent from `roles` but present in `builtins`: no `model` override -> BLOCK;
   override != pin -> BLOCK; override == pin -> ALLOW. Block messages must name
   the exact required model (shape: `Fix: pass model: 'opus'` - derive the
   value from the manifest; for a wrong override name both the override and the
   pin; for a bare spawn state that it would inherit the session model).
   Precedence: `roles` governs on any collision; builtins consulted only for
   non-role types. Hotfix mode (`active-task type=hotfix`) bypasses with
   `c.log_bypass`, matching roles-mode behavior. Roles behavior is UNCHANGED:
   frontmatter-pinned roles spawn bare -> allow; unknown types in neither
   section -> allow.
4. **FR-MRA-06** `run_check`: the frontmatter diff ignores `builtins` entirely
   - a builtin type never demands a `.claude/agents/<type>.md` file and its
   absence is not a mismatch.
5. **FR-MRA-07, BR-MRA-04** `run_check`: additionally verify that
   `.claude/settings.json` (project-relative; that file ONLY -
   settings.local.json does not count) contains a PreToolUse group whose
   `matcher` covers the `Task` spawn tool (the shipped matcher is
   `"Task|Agent"`; treat the matcher as covering Task if the string `Task`
   appears as one of its `|`-separated alternatives) and whose hooks include a
   command referencing `guard_models.py`. Missing/unparseable settings or
   missing wiring -> RED (non-zero) with one fix-it line naming the missing
   matcher/command and stating that re-running `claude-company install` or
   `update` re-adds it. This is a --check path: fail loud.
6. **FR-MRA-09/10, BR-MRA-05/06** the migration merge: an idempotent, additive
   `models.json` merge in BOTH `install.sh` (after its models.json
   copy-if-absent) and `update.sh` (via `finalize_merge`, after
   `config_if_absent "company/models.json"`). Byte-identical merge python
   between the two engines. Behavior: `builtins` absent -> inject the section
   (with its `$comment`) preserving the VALUES of `roles`/`pricing`/`version`/
   any user keys (canonical json re-serialization per OQ-MRA-01 - formatting
   may normalize on the one injecting run); `builtins` present -> emit input
   bytes verbatim (no write, no backup). update backs up per its existing
   convention on the one injecting run; re-run is UNCHANGED/no-op.
   config-if-absent still restores a missing manifest first (the restored
   template already carries builtins, so the merge then no-ops).
7. **FR-MRA-11/12** doctrine: `company/METHOD.md` gains a short subsection
   stating the Workflow tool is outside hook enforcement (its internal agent()
   spawns fire no PreToolUse events and inherit the main-loop model), is
   FORBIDDEN by default in company projects, and is permitted only with
   explicit owner authorization AND a `model` pin in EVERY `agent()` call
   including all early stages - resuming a dead workflow re-runs incomplete
   early-stage agents live, so partial pinning does not hold. `ORCHESTRATOR.md`
   gains a matching line at the dispatch section cross-referencing METHOD.md.
   Keep both terse and hook-clean.
8. **FR-MRA-08/13** `tests/hooks/test_hooks.py` (extend `TestGuardModels` or
   add a sibling class): builtin spawn bare -> exit 2 naming the required
   model; wrong override -> exit 2; matching override -> exit 0; hotfix ->
   exit 0 + BYPASS line in adherence.log; manifest without builtins section ->
   builtin spawn allowed (fail open); `--check` green with builtins present,
   wiring present, and roles matching (and no mismatch reported for builtin
   types); `--check` RED with fix-it line when the settings.json lacks a
   Task-covering guard_models matcher; the REPO'S OWN shipped
   `.claude/settings.json` registers `guard_models.py` under a `Task|Agent`
   PreToolUse matcher (presence, not position - this is the regression gate
   for code-without-wiring).
9. **FR-MRA-14** `tests/install/test_update.sh`: existing install with
   `builtins` stripped from models.json plus a custom user key -> update
   injects `builtins`, preserves `roles`/`pricing`/`version`/custom values,
   backs the file up; second update leaves models.json unwritten (UNCHANGED);
   deleted models.json -> config-if-absent restores it and the merge no-ops.
10. If you touch `company/GATES.md`, one line only: G7 also asserts the
    Task|Agent wiring.

## Integration seams

- The npm-release-0.2.1 task is in flight but touches no code paths - no
  contention. You guarantee: no changes outside your owned paths; the
  settings.json template and its merge logic are UNTOUCHED (the Task|Agent
  group already exists at HEAD and the merger heal is already proven - your
  wiring work is the gate assertion and tests, not the wiring itself).
- `lib/manifest.py` / pack list: all files you touch are already packed -
  verify with `npm test` (it includes the pack manifest suite); report if the
  manifest test flags anything, do not edit the pack list.

## Definition of Done

Universal DoD plus this task's specifics:
- [ ] Every FR in scope (FR-MRA-01..14) implemented and tested, or explicitly
      deferred with reason
- [ ] THIS repo's gates green, run yourself before reporting (dual-nature: not
      run-gates.sh here): `python3 -m unittest discover -s tests/hooks -q` AND
      `npm test`
- [ ] `python3 .claude/hooks/guard_models.py --check` run from the worktree
      root: green (proves the new wiring assertion passes on the shipped tree)
- [ ] Live acceptance replay from the worktree, piped payloads (paste output in
      the report): builtin + contradicting model -> block naming manifest
      model; builtin bare -> block; builtin + manifest model -> allow;
      manifest role bare -> allow
- [ ] No edits outside owned paths; zero frozen surfaces touched
- [ ] Tests added for new behavior; existing tests unmodified and green
- [ ] Commits follow `company/GIT.md`: conventional subject, `Task:
      model-routing-arming` trailer, explicit paths staged (never `git add -A`)
- [ ] `MODULE.md` updated where owned dirs have one (`.claude/hooks/MODULE.md`
      if present; `lib/MODULE.md` is NOT yours - do not touch)
- [ ] Report follows `company/templates/REPORT-TEMPLATE.md` and proposes 1-3
      witness candidates (load-bearing markers) for the CEO to curate

## Fallback assumptions

For every ambiguity, implement THIS stated assumption and tag the site - do
not guess, do not ask the user:
- OQ-MRA-01: builtins injection mechanism -> FALLBACK: canonical
  `json.load`/`json.dump` re-serialization on the one injecting run (values
  preserved, formatting may normalize once, file backed up on update; no write
  when builtins already present). Tag `# OQ-MRA-01 assumption`.
- OQ-MRA-02: type in BOTH roles and builtins -> FALLBACK: roles governs;
  builtins only for non-role types. Tag `# OQ-MRA-02 assumption`.
- OQ-MRA-03: built-in types beyond the four -> FALLBACK: pin exactly the four;
  any other type in neither section stays allowed (documented residual gap).
- OQ-MRA-04: wiring assertion scope -> FALLBACK: guard_models only (the models
  gate asserts its OWN enforcement); guard_provenance wiring is out of scope.
  Tag `# OQ-MRA-04 assumption`.

## Out of scope

Explicitly, so nobody "helpfully" expands:
- Intercepting Workflow-tool agent() spawns mechanically (impossible - hooks
  never see them; doctrine only).
- Auto-injecting a model pin into a bare spawn (PreToolUse blocks or allows,
  never rewrites input).
- Any change to the routing policy or model tiering (all-opus stands).
- `.claude/agents/<type>.md` files for built-in types.
- A new standalone wiring hook or new gates.config line (wiring assertion
  lives inside `--check`; gates.config stays placeholder in this repo).
- Byte-exact formatting preservation of a user models.json on the one
  injecting run (values only - OQ-MRA-01).
- provenance.json / delegation enforcer / any other enforcement regime.
- The settings.json template or its merge heredocs (already correct; issue-67
  fix proven).
- A bespoke one-shot migration tool (the additive merge on next
  install/update IS the migration).

## Report back

Your report must contain, as facts: what changed (paths), gate results (paste
both suite outputs AND the --check output AND the live acceptance replay),
FR checklist (FR-MRA-01..14), ownership diff summary
(`git diff --name-only main..HEAD`), CRs filed (expect none), deviations from
this brief and why, 1-3 proposed witnesses, worries for the CEO.
