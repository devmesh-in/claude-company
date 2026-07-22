# BRIEF: spawn-depth-shipping

_Type: quick. Spec: none (quick - fix already verified live in the field).
Lead: direct-developer. Date: 2026-07-22. Tracking: #79 (parent), #80-#82._

> Anything in `company/frozen-surfaces.json` is FROZEN - consume as shipped;
> changes via `company/change-requests/` only. This task touches no frozen
> surface.

## Mission

Claude Code 2.1.21 changed the default subagent spawn depth to 1, silently
flattening every claude-company org: tech-leads can no longer spawn their
developers/QA. The fix, verified live in a stamped project, is the env var
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2` in settings (it hot-applies).
Ship it in the framework so every fresh install AND every existing install on
its next update gets depth 2 automatically, and a regression test fails if the
template ever ships without it. Hard constraint: a user-set env value must
NEVER be overwritten (a project pinning depth 3 keeps 3).

## Read first (in order)

1. `CLAUDE.md` (project canon - dual-nature rule)
2. `company/METHOD.md`
3. `.claude/settings.json` (the shipped template you extend)
4. `install.sh` (section 5: the settings merge heredoc - hooks + permissions.deny today)
5. `update.sh` (the same heredoc between its finalize_merge scaffolding; issue-67 byte-identity rule)
6. `tests/cli/test_cli.sh` and `tests/install/test_update.sh` (find where settings-merge behavior is tested today; extend in kind)
7. `tests/hooks/test_hooks.py` (`test_repo_settings_wires_guard_models_under_task` - the template-shape test pattern to mirror)

## You own

- `.claude/settings.json` (add the env block only)
- `install.sh` (settings merge heredoc extension only)
- `update.sh` (settings merge heredoc extension only)
- `tests/hooks/test_hooks.py` (one template-shape test)
- `tests/cli/test_cli.sh` and/or `tests/install/test_update.sh` (merge behavior tests)

Nothing else. `.claude/settings.local.json` is the CEO's local file - do not
touch. If a fix you need lives outside these paths, report it; do not make it.

## Invariants in play (must not break)

- The settings merge python must remain BYTE-IDENTICAL between install.sh and
  update.sh (issue-67 precedent; there is a coupling worry in WORRIES - keep
  the two heredocs in lockstep).
- Merge semantics additive-only: `ours.env` keys absent from `theirs.env` are
  added; present keys are NEVER overwritten. Same spirit as permissions.deny
  union. A `theirs` whose `env` is not a dict is replaced-safe: treat as
  empty and set ours (do not crash - the merger must never brick an install).
- Deterministic installs: fresh install copies the template verbatim; a
  re-run of install/update over an already-env-carrying settings is a no-op.
- macOS bash 3.2 compatible; python stdlib only; no_slop on all writing.
- Existing tests stay green unmodified (extend, never edit-to-pass).
- Value is the STRING "2" (settings env values are strings), name exactly
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`.

## Scope (ordered)

1. (#80) `.claude/settings.json`: add top-level `"env": {"CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "2"}`.
2. (#81) Extend the settings merge python (both engines, byte-identical): merge
   `env` additively, user values win.
3. (#82a) `tests/hooks/test_hooks.py`: template-shape test asserting the shipped
   settings.json carries the env var at "2" (mirror the guard_models wiring
   regression test - this is the auto-update-era guard).
4. (#82b) Merge tests in the bash suites: existing settings WITHOUT env gains
   the key on update (and on install-over-existing if the cli suite covers that
   path today); a user-set value (e.g. "3") survives update; second run is a
   no-op/UNCHANGED; hooks + permissions.deny merge behavior unchanged.

## Definition of Done

- [ ] `python3 -m unittest discover -s tests/hooks -q` green
- [ ] `npm test` green
- [ ] `bash tests/install/test_update.sh` green
- [ ] Manual probe pasted in your report: run the extracted merge python over a
      settings.json lacking env -> key added; over one with depth "3" -> "3"
      kept; over the template itself -> byte-unchanged
- [ ] Byte-identity of the two heredocs proven (paste the diff/cmp output)
- [ ] No edits outside owned paths
- [ ] Commits per `company/GIT.md`: conventional subject, `Task:
      spawn-depth-shipping` trailer, explicit staged paths, brief included
- [ ] Report per `company/templates/REPORT-TEMPLATE.md` with 1-2 proposed
      witnesses

## Fallback assumptions

- Ambiguity: should other env keys ship too? -> FALLBACK: only
  CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH ships; the merge logic is generic over
  ours.env keys so future additions ride free.
- Ambiguity: theirs.env exists but is not a dict -> FALLBACK: replace with
  ours.env (fail-safe over fail-crash), note it in the report.

## Out of scope

- Changing hooks/permissions merge behavior.
- Any doctrine/docs beyond code comments (the CEO handles the docs pass if
  needed).
- `.claude/settings.local.json`, `~/.claude/settings.json` (user-machine
  scope - not the framework's).
- Depth values other than 2 or any depth-detection logic.

## Report back

Facts only: paths changed, all three suite outputs pasted, the manual merge
probes, byte-identity proof, ownership diff (`git diff --name-only main..HEAD`),
deviations, proposed witnesses, worries.
