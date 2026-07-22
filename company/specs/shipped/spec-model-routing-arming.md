# SPEC: model-routing arming (builtins enforcement + wiring gate)

_Type: feature. Author: product-manager. Date: 2026-07-22._
_Status: SPEC-READY._

The spec is rich and human-facing; it can be long. The builder agent NEVER
reads it - it reads the brief derived from it. Reference, do not embed.

Tracking issues: #74 (builtins enforcement), #75 (migration), #76 (wiring gate
+ doctrine).

## Part 1 - Product requirements

### Problem

`guard_models.py` is the company's model-routing enforcer: `company/models.json`
is the one deliberate place routing is decided, and the guard is supposed to
block any spawn or frontmatter edit that silently drifts off it. The owner rule
is all-opus, no tiering (DECISIONS #1). A live incident in the stamped project
company-brain, found 2026-07-22 via billing telemetry and fixed locally there,
proved three holes that let non-opus work run while the routing gate stayed
green. We are porting that proven fix into the framework so every install and
update inherits it.

Three concrete gaps:

1. **Code without wiring.** `guard_models` documents a PreToolUse `Task|Agent`
   mode that blocks spawns whose model override contradicts the manifest. In
   company-brain no `Task|Agent` matcher was registered in `.claude/settings.json`
   (a pre-0.2.1 settings merger deduped per-command and dropped whole repeated
   hook groups on update - fixed by PR #69), so the spawn check never ran. The
   models gate (`guard_models.py --check`) stayed green the whole time: it only
   diffs agent frontmatter against the manifest and is blind to whether the hook
   is actually wired. A gate that cannot see its own enforcement being
   disconnected is not a gate.

2. **Built-in agent types escape entirely.** The built-in types (`Explore`,
   `general-purpose`, `Plan`, `claude`) have no `.claude/agents/<role>.md`
   frontmatter pin and no `models.json` entry. `guard_models` treats every
   unknown role as allowed, and a bare spawn (no explicit `model`) silently
   inherits the SESSION model. When the session runs a non-opus model, an
   Opus-only project quietly runs built-in work off-policy - and the bill is
   the first place anyone notices.

3. **The Workflow tool is hook-invisible.** Its internal `agent()` spawns fire
   no PreToolUse events, so no hook can intercept them; they inherit the
   main-loop model. Worse, resuming a dead workflow re-runs INCOMPLETE
   early-stage agents live, so a pin on only the late stages is not enough -
   every `agent()` call needs an explicit model pin. There is no mechanical fix
   available (the tool is outside enforcement); only doctrine can close it.

The cost is concrete and already realized: real spend on the wrong model, in a
project whose whole routing policy is Opus-only, with the gate reporting green.

### Goal and success metrics

After this ships, on every install AND update with no enabling step:

- A spawn of a built-in type that is bare, or carries a model that contradicts
  `models.json`, is BLOCKED with a message naming the exact required model.
- The models gate (`guard_models.py --check`) goes RED when the `Task|Agent`
  spawn enforcement is not wired into `.claude/settings.json`, instead of
  reporting a false green.
- The Workflow tool is documented in canon (read by every agent) as forbidden
  by default, with the exact conditions under which it may be used.

Binary success signals (all must hold):

- `SM-1`: Spawn a builtins-listed type with a contradicting model -> hook exits
  2 (blocks), message names the manifest model.
- `SM-2`: Spawn a builtins-listed type bare (no override) -> hook exits 2, message
  names the required model to pass (the inherit-session case).
- `SM-3`: Spawn a builtins-listed type with the manifest model -> hook exits 0.
- `SM-4`: Spawn a manifest role bare -> hook exits 0 (frontmatter governs;
  unchanged behavior).
- `SM-5`: `guard_models.py --check` exits 0 with the `builtins` section present
  and the `Task|Agent` wiring in place; exits non-zero (red, with a fix-it line)
  when the `Task|Agent` wiring is missing.
- `SM-6`: A plain `claude-company update` of an existing install that lacks the
  `builtins` section injects it into `models.json` without altering any role,
  pricing, or version value; re-running update is a no-op for that file. A
  missing `models.json` is still restored by config-if-absent.
- `SM-7`: `python3 -m unittest discover -s tests/hooks -q` and `npm test` both
  stay green.

### Users and personas

- **The CEO / dispatcher (primary).** The main Claude session that spawns
  agents - including built-in `Explore` audits and any `general-purpose` /
  `Plan` helpers. It must be blocked from spawning a built-in off-policy, with a
  message it can act on immediately.
- **The install/update operator.** A developer who runs `claude-company install`
  or `update` in their project. They get the builtins enforcement and the wiring
  gate automatically, with existing `models.json` customizations preserved.
- **CI / the gate runner.** The non-interactive caller of
  `guard_models.py --check` (G7). It must fail loud (non-zero) when routing
  enforcement is disconnected, not silently pass.
- **The owner (escalation only).** Owns the routing policy (all-opus, DECISIONS
  #1) and any future authorization to use the Workflow tool. Not consulted
  mid-build; touched only by the doctrine this spec writes.

No new privilege surface is introduced.

### User stories and acceptance criteria

- **US-MRA-1**: As the dispatcher, when I spawn a built-in agent type off the
  routing policy, I am blocked and told exactly what to pass.
  - AC: given `models.json` pins builtin `Explore` to `opus`, when a `Task`
    spawn names `Explore` with `model: sonnet` (or with no `model` at all), then
    the hook exits 2 and the message names the required model (e.g. `pass
    model: 'opus'`). When the same spawn passes `model: opus`, the hook exits 0.

- **US-MRA-2**: As the dispatcher, my normal role spawns are unaffected.
  - AC: given `models.json` pins role `developer` to `opus`, when a `Task` spawn
    names `developer` with no `model` override, then the hook exits 0 (the
    frontmatter pin governs, exactly as today).

- **US-MRA-3**: As the gate runner, the models gate turns red when the spawn
  enforcement is not actually wired.
  - AC: given a `.claude/settings.json` with no PreToolUse matcher covering the
    `Task` spawn tool that registers `guard_models.py`, when I run
    `guard_models.py --check`, then it exits non-zero and prints a fix-it line
    naming the missing wiring. Given the shipped settings.json (which registers
    it), the same check exits 0.

- **US-MRA-4**: As an install/update operator, I get the builtins policy without
  re-configuring anything, and my `models.json` edits survive.
  - AC: given an existing install whose `models.json` has custom pricing and no
    `builtins` section, when I run `claude-company update`, then a `builtins`
    section pinning the four built-in types to `opus` is added, the `roles`,
    `pricing`, and `version` values are unchanged, and a second update writes
    nothing to `models.json`.

- **US-MRA-5**: As any agent reading canon, I learn the Workflow tool is
  off-limits by default and the exact conditions to use it.
  - AC: given `company/METHOD.md` and `ORCHESTRATOR.md`, when an agent reads
    them, then both state that the Workflow tool is outside hook enforcement,
    forbidden by default, permitted only with explicit owner authorization AND a
    model pin in every `agent()` call including all early stages (the resume
    trap). Both files are in the overwrite payload, so the doctrine ships on
    update.

### Functional requirements

Stable IDs. Every FR is later implemented, tested, or explicitly deferred - the
traceability gate checks these IDs against the PR.

- **FR-MRA-01**: `company/models.json` (the shipped template) gains a `builtins`
  object mapping the four built-in agent types - `Explore`, `general-purpose`,
  `Plan`, `claude` - each to `"opus"`, plus a `$comment` stating that the
  Workflow tool is hook-invisible and forbidden by default. `roles`, `pricing`,
  `version`, and the top-level `$comment` are unchanged.
- **FR-MRA-02**: `guard_models.py` gains a `load_builtins(root)` that returns the
  `builtins` map from `models.json`, or `None` when the section is absent,
  malformed, or the manifest is unreadable. A `None` result fails open (old
  manifests without a `builtins` section must not break enforcement or the
  guard).
- **FR-MRA-03**: In PreToolUse `Task|Agent` mode, when the spawn type is in
  `builtins`, `handle_spawn` BLOCKS unless an explicit `model` override exactly
  equals the builtins pin. A bare spawn (no `model`) BLOCKS. A wrong override
  BLOCKS. A matching override ALLOWS. The block message names the exact required
  model to pass.
- **FR-MRA-04**: The `roles`-section spawn behavior is unchanged: a frontmatter-
  pinned role may spawn bare (inherits the manifest, allowed); a contradicting
  override still blocks; an unknown type that is in neither `roles` nor
  `builtins` is still allowed (fail open).
- **FR-MRA-05**: A builtins block honors hotfix mode: when
  `company/state/active-task.json` has `type: hotfix`, the block is logged as a
  BYPASS via `c.log_bypass` and the spawn is allowed - matching the existing
  roles-mode hotfix behavior.
- **FR-MRA-06**: `run_check` (the `--check` gate) ignores `builtins` for the
  frontmatter diff: a built-in type is not treated as a role, is never expected
  to have a `.claude/agents/<type>.md` file, and its absence from the agents
  directory is not a mismatch.
- **FR-MRA-07**: `run_check` additionally verifies that `.claude/settings.json`
  registers a `guard_models.py` command under a PreToolUse matcher covering the
  `Task` spawn tool. Missing wiring turns the check RED (non-zero exit) with a
  fix-it message naming the missing matcher/command. This is a `--check` path,
  so it fails loud (never silently green) on a read/parse problem that leaves
  wiring unproven.
- **FR-MRA-08**: The shipped template `.claude/settings.json` registers
  `guard_models.py` (and `guard_provenance.py`) under a `Task|Agent` PreToolUse
  matcher. A regression test asserts this presence (position within the file is
  irrelevant), so a future edit that drops the group is caught. This is the
  regression gate for the exact live failure (code without wiring).
- **FR-MRA-09**: `install.sh` performs an idempotent, additive merge of the
  `builtins` section into `company/models.json`: if the section is absent it is
  injected (with its `$comment`); if present the file is left byte-unchanged. The
  merge never alters `roles`, `pricing`, `version`, or any user key values, and a
  re-run is a no-op.
- **FR-MRA-10**: `update.sh` performs the SAME merge as FR-MRA-09 via the
  existing `finalize_merge` infrastructure (FR-UPD-08 pattern): the merge python
  is byte-identical to install.sh's; the file is backed up before rewrite per
  update conventions; a re-run is a no-op (UNCHANGED). The existing
  `config_if_absent "company/models.json"` still restores a missing manifest
  before the merge runs.
- **FR-MRA-11**: `company/METHOD.md` gains a statement that the Workflow tool is
  outside hook enforcement, forbidden by default in company projects, and
  permitted only with explicit owner authorization AND a model pin in every
  `agent()` call including all early stages (the resume trap).
- **FR-MRA-12**: `ORCHESTRATOR.md` gains a line (at or near the dispatch section)
  stating the same Workflow-tool ban and the pin-every-stage rule, cross-
  referencing METHOD.md. Both files are in the overwrite payload
  (`lib/payload_paths.sh`), so the doctrine propagates on update.
- **FR-MRA-13**: `tests/hooks/test_hooks.py` gains regression coverage for the
  builtins spawn paths (bare -> block naming required model; wrong override ->
  block; matching override -> allow; hotfix -> logged bypass), for `run_check`
  staying green with `builtins` present, for `run_check` turning red when the
  `Task|Agent` wiring is missing, and for FR-MRA-08 (the shipped settings.json
  registers guard_models under a Task|Agent matcher).
- **FR-MRA-14**: `tests/install/test_update.sh` gains coverage that the
  `models.json` merge adds `builtins` to an existing manifest without touching
  user `roles`/`pricing`/`version`, is idempotent (second update is a no-op for
  the file), and that `config_if_absent` still restores a missing manifest.

### Business rules and validations

- **BR-MRA-01**: Builtins spawn decision matrix (server-side, in `handle_spawn`).
  Let `pin = builtins[type]`, `override = tool_input.model`:
  - `type not in builtins` -> defer to roles behavior (FR-MRA-04); builtins do
    not apply.
  - `type in builtins` and no `override` -> BLOCK (inherit-session case). Message
    names `pin`.
  - `type in builtins` and `override != pin` -> BLOCK. Message names `pin` and
    the offending override.
  - `type in builtins` and `override == pin` -> ALLOW.
- **BR-MRA-02**: Precedence when a type appears in BOTH `roles` and `builtins`:
  `roles` governs (frontmatter-pinned; bare spawn allowed). `builtins` is
  consulted only for a type absent from `roles`. The shipped four builtin names
  do not collide with the ten role names; this rule is defensive. (See
  OQ-MRA-02.)
- **BR-MRA-03**: Fail-open conditions for the PreToolUse modes: a missing or
  malformed `builtins` section, an unreadable manifest, an unknown type, or any
  internal error ALLOWS the spawn. Only `--check` fails loud. Old manifests
  without a `builtins` section behave exactly as today.
- **BR-MRA-04**: The wiring assertion (FR-MRA-07) inspects `.claude/settings.json`
  ONLY. `settings.local.json` (a user-local, additive file the installer does not
  manage) does NOT satisfy the check. A PreToolUse group whose `matcher` string
  matches the `Task` spawn tool (the shipped matcher is `"Task|Agent"`) and whose
  `hooks` include a command referencing `guard_models.py` counts as wired;
  otherwise the check is RED. (CEO recommendation, recorded as a rule.)
- **BR-MRA-05**: The `models.json` merge writes the file ONLY when `builtins` is
  absent (injection needed). When `builtins` is already present the merge emits
  the input bytes verbatim, so a fresh install (whose template already carries
  `builtins`) and every re-run are byte-for-byte no-ops. This keeps the
  bin-vs-bare install parity test green and makes the update path back up
  `models.json` at most once (on the single injecting run).
- **BR-MRA-06**: The `models.json` merge preserves the VALUES of `roles`,
  `pricing`, `version`, and any user-added keys. Under the OQ-MRA-01 fallback
  (canonical re-serialization on the one injecting run), whitespace/formatting of
  the existing content may normalize but no value changes; the pre-injection file
  is backed up on update.

### Scope

**In:**
- A `builtins` section in the shipped `company/models.json` pinning the four
  built-in types to `opus`, with the Workflow-tool `$comment`.
- `guard_models.py`: load builtins; block bare/contradicting builtin spawns
  naming the required model; hotfix bypass logged; roles behavior unchanged;
  fail open on manifest/builtins problems.
- `guard_models.py --check`: ignore builtins in the frontmatter diff, AND assert
  the `Task|Agent` guard_models wiring in `.claude/settings.json`, red-with-fix-it
  when absent.
- A regression test asserting the shipped settings.json registers guard_models
  under a `Task|Agent` PreToolUse matcher.
- An idempotent, additive `models.json` builtins merge in BOTH `install.sh` and
  `update.sh` (byte-identical merge python), backup per update conventions,
  config-if-absent still restoring a missing manifest.
- Workflow-tool doctrine in `company/METHOD.md` and `ORCHESTRATOR.md`.
- Regression tests in `tests/hooks/test_hooks.py` and
  `tests/install/test_update.sh`.

**Out:**
- **Intercepting the Workflow tool's `agent()` spawns.** They are hook-invisible;
  no hook can see or block them. Closed by doctrine only, never by a hook.
- **Auto-injecting a model pin into a bare spawn.** PreToolUse hooks block or
  allow; they do not rewrite tool input. A bare builtin spawn is blocked, not
  silently pinned.
- **Changing the routing policy or introducing model tiering.** All-opus stands
  (DECISIONS #1); the four builtins are pinned to `opus`.
- **Adding `.claude/agents/<type>.md` files for built-in types.** Builtins are not
  roles; the `--check` diff explicitly does not demand agent files for them.
- **A new standalone wiring hook or a new gate line in `gates.config`.** The
  wiring assertion is folded into the existing G7 `--check`; `company/gates.config`
  in THIS repo stays placeholder (dual-nature rule).
- **Byte-level preservation of existing `models.json` formatting on injection.**
  Values are preserved; formatting may normalize on the one injecting run
  (OQ-MRA-01).
- **Touching `provenance.json`, the delegation enforcer, or any other manifest /
  enforcement regime.**
- **A bespoke one-shot migration tool for already-stamped installs.** The
  additive merge on the next `install`/`update` is the migration path (issue #75).
- **Enumerating built-in types beyond the four named by the live defect.** Future
  built-in types not in the list inherit the session model and remain allowed
  (fail open) - a documented residual gap, closed by a one-line `models.json`
  edit shipped through the same additive merge (OQ-MRA-03).

### UX notes

- **Block microcopy (builtins bare / wrong).** Terse, low-token, action-first,
  naming the exact fix - matching the existing roles-mode block style. Example
  shape: `BLOCKED: spawning built-in 'Explore' inherits the session model, which
  may contradict company/models.json (routing decision: 'opus'). Fix: pass model:
  'opus'.` For a wrong override, name both the override and the pin.
- **Gate red microcopy (wiring missing).** One clear fix-it line the operator can
  act on: state that `guard_models` is not registered under a `Task|Agent`
  PreToolUse matcher in `.claude/settings.json`, and that re-running
  `claude-company install`/`update` (the fixed merger) re-adds it.
- **Update report.** The `models.json` builtins injection surfaces as a normal
  MERGED line in the update report on the one injecting run, and as UNCHANGED
  thereafter - no new report vocabulary.

## Part 2 - Build readiness (the bridge from PRD to buildable)

- **Owned directories / files:** `.claude/hooks/guard_models.py` (builtins load
  + spawn block + `--check` wiring assertion + builtins-ignore in the diff);
  `company/models.json` (add the `builtins` section + `$comment` to the template);
  `install.sh` (add the additive builtins merge after the `copy_if_absent
  company/models.json` line ~125); `update.sh` (add the same merge via
  `finalize_merge` after `config_if_absent "company/models.json"` line ~248);
  `company/METHOD.md` and `ORCHESTRATOR.md` (Workflow-tool doctrine);
  `tests/hooks/test_hooks.py` (extend `TestGuardModels`, ~lines 375-514);
  `tests/install/test_update.sh` (models.json merge coverage). Optionally a one-
  line note in `company/GATES.md` G7 that the gate now also asserts wiring - if
  touched, it is doc-only. One workstream, one tech lead. Disjoint from the only
  in-flight item (npm-release-0.2.1, a release task that touches no code dirs).

- **Invariants in play:**
  - Python 3.8 stdlib only in `guard_models.py`; hooks fail OPEN except `--check`
    which fails LOUD (guard_models is one of the two loud-check CLIs).
  - `models.json`, `guard_models.py`, and `.claude/settings.json` are NOT in
    `company/frozen-surfaces.json` (surfaces empty; the `always` list covers only
    machine-written state and lockfiles) - no frozen-surface hook blocks this
    build; no CR needed.
  - Dual-nature rule: `.claude/hooks/` and `company/run-gates.sh` ARE overwrite
    payload, so `guard_models.py` propagates to every install/update
    automatically; `company/models.json` and `company/gates.config` are config-
    if-absent (they do NOT propagate by overwrite - hence the additive merge for
    builtins). `gates.config` in THIS repo stays placeholder; no real gate
    command enters `company/`.
  - Byte-identical merge python between `install.sh` and `update.sh` (the
    settings.json heredoc-duplication precedent - WORRIES): the models.json merge
    heredoc must be copied verbatim between the two engines.
  - Determinism / bin-vs-bare parity: the merge must be deterministic and produce
    identical bytes across two installs. BR-MRA-05 (write only when injecting,
    verbatim otherwise) keeps the shipped-template case a no-op, preserving
    parity.
  - macOS bash 3.2 for any shell (no associative arrays, no `readarray`).
  - all-opus, no tiering (DECISIONS #1); principled enforcement, no magic numbers
    (the pin values derive from the manifest, never a hardcoded threshold);
    low-token injection (block messages stay ~1 terse recipe line); `no_slop` on
    all writing (straight quotes, ' - ', three dots).

- **Frozen surfaces touched:** None. `company/frozen-surfaces.json` `surfaces` is
  empty and its `always` list does not match any file this build edits. No CR is
  required. (`install-manifest.json` and `.update-backups/**` are frozen but this
  task does not write them.)

- **Data model impact:** One additive, forward-only JSON change:
  `company/models.json` gains a `builtins` object
  (`{ "Explore": "opus", "general-purpose": "opus", "Plan": "opus", "claude":
  "opus" }`) plus a `$comment`. Old manifests without the key stay valid (guard
  fails open on its absence; `--check` ignores it for the diff). No migration of
  existing user data beyond the additive merge; a missing manifest is still
  restored by config-if-absent.

- **Contracts impact:**
  - `models.json` schema: additive `builtins` map (role -> model string).
    Non-breaking; absence handled.
  - `guard_models.py --check` (G7) contract EXTENDED: a new RED condition -
    missing `Task|Agent` guard_models wiring in `.claude/settings.json`. Installs
    that are correctly wired stay green; an install with code-but-no-wiring flips
    from a false green to a true red. This flip is the intended surfacing, not a
    regression - note it in the PR and in the G7 wording.
  - `guard_models.py` PreToolUse `Task|Agent` behavior EXTENDED: builtin types
    now block when bare or contradicting. Roles behavior and the frontmatter mode
    are unchanged.
  - No CLI flags, no new files in the pack list (guard_models.py, models.json,
    install.sh, update.sh, METHOD.md, ORCHESTRATOR.md are all already packed).

- **Open questions and chosen fallbacks:**
  - **OQ-MRA-01**: Mechanism for the one-time `builtins` injection into an
    existing `models.json` - canonical `json.load`/`json.dump` re-serialization
    (may reformat whitespace once) vs byte-surgical insertion before the closing
    brace (preserves existing formatting). FALLBACK: **canonical re-serialization**
    - stdlib-only, deterministic, matches the settings.json merge precedent; it
    preserves all VALUES (roles/pricing/version/user keys), normalizes only
    formatting, runs at most once (BR-MRA-05: no rewrite when `builtins` already
    present), and the pre-injection file is backed up on update. Tag sites
    `# OQ-MRA-01 assumption`. Not an owner-escalation.
  - **OQ-MRA-02**: Precedence if a type ever appears in BOTH `roles` and
    `builtins`. FALLBACK: **roles governs** (frontmatter-pinned, bare allowed);
    builtins consulted only for types absent from roles (BR-MRA-02). The shipped
    names do not collide; the rule is defensive. Tag `# OQ-MRA-02 assumption`.
  - **OQ-MRA-03**: Built-in types beyond the four named by the live defect (a
    future Anthropic-added type). FALLBACK: **pin exactly the four**
    (`Explore`, `general-purpose`, `Plan`, `claude`); any other built-in type is
    unknown-to-manifest and remains ALLOWED bare (fail open) - a documented
    residual gap, closed by a one-line `models.json` edit shipped via the same
    additive merge. Not an owner-escalation.
  - **OQ-MRA-04**: Whether the `--check` wiring assertion should also require
    `guard_provenance.py` under `Task|Agent`. FALLBACK: **guard_models only** -
    the models gate asserts its OWN enforcement is wired; guard_provenance has its
    own enforcement and gates. Keeps G7 scoped to routing. Tag
    `# OQ-MRA-04 assumption`.
  - None of these are money, pricing, legal, or go-live questions, so none is an
    owner-escalation. The routing policy itself (all-opus) is already owner-
    decided (DECISIONS #1). Every fallback is safe to build on now; the owner may
    veto any later via `DECISIONS.md`.

- **Verification plan:**
  - FR-MRA-01 / SM-1..4: unit assertions on the shipped `models.json` shape
    (`builtins` present, four types -> `opus`, `$comment` present) plus the
    hook-behavior tests below.
  - FR-MRA-02 / BR-MRA-03: `test_hooks` - manifest with no `builtins` section and
    a garbage manifest both fail open on a builtin spawn (exit 0), proving old
    manifests do not break.
  - FR-MRA-03 / BR-MRA-01 / SM-1,2,3: `test_hooks` - builtin `Explore` spawn:
    bare -> exit 2 with the required model named; `model: sonnet` -> exit 2;
    `model: opus` -> exit 0.
  - FR-MRA-04 / SM-4: `test_hooks` - role `developer` bare spawn -> exit 0
    (unchanged); contradicting override still exit 2 (existing tests stay green).
  - FR-MRA-05: `test_hooks` - builtin spawn under `active-task type=hotfix` ->
    exit 0 and an adherence.log `BYPASS` line.
  - FR-MRA-06 / SM-5: `test_hooks` - `--check` with `builtins` present and matching
    role frontmatter + wiring -> exit 0; a builtin type having no agent file is
    not reported as a mismatch.
  - FR-MRA-07 / BR-MRA-04 / SM-5: `test_hooks` - `--check` against a settings.json
    with no `Task`-covering guard_models matcher -> non-zero + fix-it line;
    against one with the matcher -> that condition passes. settings.local.json
    with the matcher does NOT satisfy the check.
  - FR-MRA-08: `test_hooks` - the repo's shipped `.claude/settings.json` registers
    guard_models (and guard_provenance) under a `Task|Agent` PreToolUse matcher
    (presence assertion; position irrelevant).
  - FR-MRA-09 / FR-MRA-10 / BR-MRA-05,06 / SM-6: `tests/install/test_update.sh` -
    install, remove `builtins` from `models.json`, add a custom pricing key, run
    update; assert `builtins` added, `roles`/`pricing`/`version` values unchanged,
    the file backed up; run update again and assert `models.json` UNCHANGED (no
    write); delete `models.json` and assert config-if-absent restores it (which
    already carries `builtins`).
  - FR-MRA-11 / FR-MRA-12 / SM-7: a `no_slop`-clean read of the added METHOD.md
    and ORCHESTRATOR.md doctrine; `npm test` (which includes the pack manifest and
    install/update suites) and `python3 -m unittest discover -s tests/hooks -q`
    both green.

## Options considered

Divergence ran 14 candidate directions across five pattern categories
(assumption challenge, SCAMPER, inversion, analogical transfer, perspective
multiplication). Convergence criteria: client value, production risk, cost to
build, cost to operate, reversibility, zero-dependency fit, doctrine fit
(one deliberate routing record + owner veto visibility), and fail-open safety.
Survivors below.

| # | Option | Reasoning | Production risks | Trade-offs |
|---|---|---|---|---|
| 1 | **Builtins section in models.json + block bare/contradicting builtin spawns + fold the wiring assertion into G7 `--check` + additive models.json merge in install.sh/update.sh + Workflow doctrine** | Keeps `models.json` the ONE routing record the owner can see and veto; reuses the proven FR-UPD-08 merge pattern so it lands on install AND update with no new surface; folds the wiring check into the gate that already owns routing, so a disconnected enforcer can no longer read green. Minimal files, fail-open preserved, `--check` stays loud. | Canonical re-serialization reformats models.json once (mitigated: write-only-on-inject + backup); a future built-in type outside the four is still allowed (documented residual gap). | Modified installs get one backed-up rewrite of models.json; the builtin list is a manual enumeration. |
| 2 | Hardcode the builtin list inside `guard_models.py`; no `models.json` section, no migration | Zero migration; no models.json touch; simplest diff. | Hides the routing decision from the one record the owner reads and vetoes; no per-project tuning; the list is invisible in the manifest that documents routing. | Cheapest to build, worst doctrine fit. |
| 3 | A separate `guard_wiring.py` hook + a new gate line for the wiring assertion | Clean separation of "manifest agreement" from "enforcement is wired". | Adds a hook surface and needs a new gate command in `gates.config` - which ships placeholder in this repo (dual-nature); splits the "is routing enforced" story across two gates. | More modular, more surface, worse dual-nature fit. |

**Winner: Option 1.** It is the only survivor that keeps routing decisions in the
single owner-visible record, lands automatically on both install and update via a
pattern already proven in the codebase, and puts the wiring assertion inside the
exact gate whose false green caused the incident. Options 2 and 3 each trade the
core property away - 2 hides the decision, 3 fragments the gate and fights the
dual-nature rule.

**Strongest rejected option: Option 2 (hardcode the builtins in the hook).** It
wins on cost - no migration, no models.json touch, the smallest possible diff -
and the fail-open behavior would be identical. It lost on doctrine: `models.json`
is defined as the ONE deliberate place routing is decided and the place the owner
reads to veto (all-opus, DECISIONS #1); a hardcoded list is invisible there and
untunable per project. The migration cost Option 2 avoids is cheap - the additive
merge reuses the existing FR-UPD-08 `finalize_merge` path - so the saving is not
decisive against the doctrine loss. If the merge ever proves fragile in the field,
reopen this: a hardcoded default list with a models.json override is the right
compromise.

## Spec-ready checklist (the Phase 0 gate)

- [x] Every FR has a stable ID and at least one acceptance criterion (FR-MRA-01..14
  mapped to US-MRA-1..5 ACs, SM-1..7, and the verification plan).
- [x] Out-of-scope is explicit (Scope > Out: nine exclusions).
- [x] Every open question has a single decided fallback (OQ-MRA-01..04; BR-MRA-04
  records the settings.local.json decision).
- [x] Owned directories are named and disjoint from other in-flight work (only
  npm-release-0.2.1 is active - a release task touching no code dirs).
- [x] Frozen-surface needs are identified and CRs filed (none touched; guard_models.py,
  models.json, settings.json are not in the registry - no CR required).
- [x] Data/contract impact stated (additive `builtins` map; G7 `--check` gains a red
  wiring condition; guard_models Task|Agent behavior extended; no pack-list change).
- [x] Verification plan covers every FR (mapping listed under Verification plan).

## Part 3 - Brief handoff

Derive the brief with `company/templates/BRIEF-TEMPLATE.md`. The brief links this
spec; it does not embed it. Read-first for the builder: the project `CLAUDE.md`
(dual-nature rule), `company/METHOD.md`, `.claude/hooks/guard_models.py`,
`.claude/hooks/_common.py` (`block`, `log_bypass`, `active_task`, `read_json_file`,
`project_root`), `company/models.json`, `.claude/settings.json` (the `Task|Agent`
group), `install.sh` (section 5 settings heredoc + the `copy_if_absent
models.json` line), `update.sh` (`config_if_absent`, `finalize_merge`, the
settings heredoc), `lib/payload_paths.sh`, `tests/hooks/test_hooks.py`
(`TestGuardModels`), `tests/install/test_update.sh`. Gates for THIS repo:
`python3 -m unittest discover -s tests/hooks -q` and `npm test` - both green
before any commit. No CR is required (no frozen surface touched).
