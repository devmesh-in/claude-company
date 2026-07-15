# BRIEF: settings-merger-fix

_Type: quick. Spec: none (issue #67 + this brief are the source of truth).
Lead: direct-developer. Date: 2026-07-15._

## Mission

Fix the settings merger in install.sh so no hook group is ever dropped.
Root cause (CEO-pinned, issue #67): the merge dedups hook entries by
COMMAND STRING per event - `have = commands_in_event(existing_groups)` is
shared across ALL groups of an event, so a command that legitimately
appears under multiple matchers (guard_provenance under
Edit|Write|MultiEdit AND Task|Agent AND Bash; guard_tests under
Edit|Write|MultiEdit AND Bash; guard_models under Edit|Write|MultiEdit AND
Task|Agent) survives only in the first group; later groups lose those
entries and, when emptied, vanish entirely. Field impact: fresh installs
lost the whole PreToolUse Task|Agent group and the Bash group's
guard_tests + guard_provenance - dispatch telemetry, spawn gates, the
commit gate, and the test-oracle Bash gate all silently unwired.

## Read first (in order)

1. CLAUDE.md, company/METHOD.md
2. install.sh section 5 ("settings.json (copy or deep-merge)") - the PY
   heredoc with the merge logic
3. tests/install/run_tests.sh (style + where settings assertions live)
4. .claude/settings.json (the payload being merged - the multi-matcher
   ground truth)

## You own

- install.sh (ONLY the settings-merge PY heredoc)
- tests/install/run_tests.sh (new assertions)
- update.sh IF its settings merge duplicates the same buggy logic (it
  re-runs "the same idempotent merges install uses" - check; the brief for
  cli-update mandated byte-identical merge blocks, so the bug is likely
  cloned there. Fix both, keep them byte-identical, per the existing
  COUPLING comments.)

Nothing else.

## Invariants in play (must not break)

- Dedup key becomes (matcher, command): a command may appear once PER
  MATCHER GROUP, and dedup applies only against existing entries of the
  SAME matcher (so re-running install/update on an already-correct file
  stays a no-op - idempotency is asserted by existing tests).
- Fresh copy must be group-for-group faithful to the payload.
- A user's own custom groups/entries are never removed or reordered.
- python3 3.8 stdlib only; bash 3.2; zero deps.
- Both suites green: `python3 -m unittest discover -s tests/hooks -q` AND
  `npm test`; plus `bash tests/install/run_tests.sh` and
  `bash tests/install/test_update.sh` (update.sh merge must stay green).
- The bin-vs-bare parity test must stay green.
- Hook-clean writing: straight quotes, ' - ' never em dashes, '...' never
  the ellipsis glyph.

## Scope (ordered)

1. Fix the merge in install.sh: track existing commands PER MATCHER
   (e.g. dict matcher -> set of commands; groups with no matcher key use a
   sentinel). Tag the fix site `# issue-67`.
2. Mirror the exact same fix into update.sh's settings-merge heredoc if it
   carries the same logic (keep byte-identical per the COUPLING comments).
3. Tests in run_tests.sh:
   a. Fresh install into an empty dir -> installed settings.json hook
      groups == payload's, group-for-group and entry-for-entry (parity
      assertion driven from the payload file, not hardcoded names).
   b. Merge case: pre-seed a settings.json with a user hook group (custom
      matcher + custom command) -> after install, user group intact AND
      every payload group complete.
   c. Idempotency: run install twice -> byte-identical settings.json.
4. If update.sh was fixed, add/extend the test_update.sh merge assertion
   so a pristine update leaves a correct settings.json correct (no
   MERGED churn), and a dropped-group settings.json gets HEALED by update
   (this is how existing 0.2.0 installs in the field get fixed).

## Out of scope

- Any other install.sh/update.sh section
- Permissions-deny merge logic (correct today)
- Reworking the merger into a shared file (the byte-identical COUPLING
  convention stands this pass)

## Report back

Facts per REPORT-TEMPLATE.md: paths, all four suite outputs pasted, the
parity/merge/heal test evidence, deviations, 1-2 proposed single-line
verbatim witness markers, worries. Tracking issue: #67.
DO NOT COMMIT - the CEO lands the commit.
