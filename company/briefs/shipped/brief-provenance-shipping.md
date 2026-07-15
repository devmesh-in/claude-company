# BRIEF: provenance-shipping

_Type: quick. Spec: none (quick - issue #64 is the source of truth).
Lead: direct-developer. Date: 2026-07-15._

> Anything in `company/frozen-surfaces.json` is FROZEN - CR, never a local
> edit.

## Mission

Ship the delegation enforcer's arming manifest. `guard_provenance.py` is
wired into every install's settings but `company/provenance.json` never
reaches field projects, so the enforcer is permanently dormant. Fresh
installs must arm it by default; `update` must NEVER silently arm an
existing project (an update must not switch a project's enforcement regime -
owner rule 2026-07-15) - it prints one notice line instead.

## Read first (in order)

1. CLAUDE.md, company/METHOD.md
2. install.sh (the copy_if_absent config block, section 4-ish, and how ok/skip
   lines print)
3. update.sh (the config_if_absent helper and its three call sites; the
   report block)
4. tests/install/run_tests.sh and tests/install/test_update.sh (where the
   new assertions go)

## You own

- `install.sh` (one copy_if_absent line for company/provenance.json)
- `update.sh` (the never-arm rule + notice line)
- `tests/install/run_tests.sh`, `tests/install/test_update.sh` (assertions)
- `docs/getting-started.md` or `docs/customizing.md` (one short note where
  enforcement/config files are listed, if they enumerate the config trio)

Nothing else. payload_paths.sh must NOT gain provenance.json (it is config,
not overwrite-set payload). lib/, bin/, hooks are read-only.

## Invariants in play (must not break)

- bash 3.2 compatible, zero deps; install stays fail-open.
- provenance.json is copy_if_absent class: PRESENT is never touched by
  either engine, no .new, no backup, not in the sha256 manifest.
- update NEVER creates company/provenance.json - when the target lacks it,
  update prints exactly one line, e.g.:
  "note: delegation enforcer installed but disarmed - create company/provenance.json to arm (see company/METHOD.md)"
  and counts nothing for it.
- Existing suites stay green; the bin-vs-bare parity test must stay green
  (provenance.json IS copied by install now - both paths must do it
  identically).
- Hook-clean writing: straight quotes, ' - ' not em dashes, '...' not the
  ellipsis glyph.

## Scope (ordered)

1. install.sh: add `copy_if_absent "$SRC/company/provenance.json" ...` next
   to the models.json line.
2. update.sh: where config_if_absent handles the trio, provenance.json gets
   the special rule: present -> unchanged (untouched, counted "unchanged");
   absent -> NOT restored, print the single notice line (stdout, once, in
   both --check and apply modes), count nothing.
3. Tests: (a) run_tests.sh - fresh install contains company/provenance.json
   with the packaged bytes; parity test still green. (b) test_update.sh -
   update on a target WITHOUT provenance.json does not create it and the
   output contains the notice line; update on a target WITH a (modified)
   provenance.json leaves it byte-identical, no .new, no backup, no notice.
4. Docs: one line if the config-file inventory in docs mentions the trio.

## Definition of Done

- [ ] Both suites green, run yourself: `python3 -m unittest discover -s
      tests/hooks -q` AND `npm test`; plus `bash tests/install/run_tests.sh`
      and `bash tests/install/test_update.sh`
- [ ] Fresh scratch install: company/provenance.json present, enforcer arms
      (hand-check: a synthetic guard_provenance Mode E probe on a feature
      task without execution decision BLOCKS in the scratch project)
- [ ] Scratch update on manifest-less project: file NOT created, notice
      printed once
- [ ] No edits outside owned paths
- [ ] Report: paths changed, suite outputs, transcripts of the two
      hand-checks, 1-2 proposed single-line verbatim witness markers
- [ ] DO NOT COMMIT - the CEO lands the commit

## Fallback assumptions

- Notice wording ambiguity -> use the exact line in Invariants; tag the site
  `# issue-64` in update.sh.
- Where the notice prints in the report -> immediately before the counts
  block, both modes.

## Out of scope

- Arming semantics, roles, or guard_provenance.py itself
- Retroactive arming of existing installs by any path
- payload_paths.sh / manifest changes

## Report back

Facts per REPORT-TEMPLATE.md. Tracking issue: #64.
