# BRIEF: wave1-enforcement

_Type: feature. Spec: approved adoption plan (issues #15, #16, #17).
Lead: tech-lead. Date: 2026-07-09._

> Schema, contracts, kernel, shared UI, and anything in
> `company/frozen-surfaces.json` are FROZEN - consume them exactly as shipped;
> any change goes through `company/change-requests/`, never a local edit.

## Mission

Ship wave 1 of the enforcement program: two new blocking/observing hooks
(guard_secrets, cost_capture), the Spend line in /standup, and a universal
"models" gate proposal in gates_detect. This is the claude-company product
repo itself - everything you build ships to every user install, so the
hooks must be Python 3.8 stdlib only, fail open, and follow the existing
idioms exactly. Hard constraint: the tracked `company/gates.config` keeps
its CONFIGURE-ME placeholders (it is a template copied into user installs);
never commit real gate commands into it.

## Read first (in order)

1. `CLAUDE.md` (project canon)
2. `company/METHOD.md` (how the team works)
3. `.claude/hooks/_common.py` - the shared helpers (block(), adherence_log(),
   read_json_file(), active_task(), stamp_checksum()); every hook imports it
4. `.claude/hooks/guard_commit.py` - the PreToolUse Bash idiom to copy
   (segments(), git_subcmd(), fail-open shape)
5. `.claude/hooks/guard_frozen.py` + `company/frozen-surfaces.json` - the
   frozen-surface mechanism you extend with costs.log
6. `.claude/hooks/gates_detect.py` - where the models gate proposal goes
7. `tests/hooks/test_hooks.py` - the test harness idiom (74 existing tests;
   yours join it)
8. `.claude/settings.json` - hook wiring shapes
9. Reference-only (port ideas, never code, from the ruflo research clone):
   `/private/tmp/claude-501/-Users-redomic-Documents-Projects-claude-company/b75f8fb8-9dd5-4e93-aa73-5b9c3af22d54/scratchpad/ruflo/plugins/ruflo-security-audit/`
   (secret pattern set) and `.../plugins/ruflo-cost-tracker/` (report shapes).

## You own

- `.claude/hooks/` (new: guard_secrets.py, cost_capture.py; edit:
  gates_detect.py, guard_frozen.py ALWAYS_DEFAULTS only if needed)
- `.claude/settings.json` (hook registration)
- `.claude/skills/standup/` (Spend line)
- `company/frozen-surfaces.json` (add costs.log to "always")
- `company/models.json` (add optional "pricing" map only; NEVER touch roles)
- `tests/hooks/` (new tests)
- `README.md` (one row in "The rules it enforces" table for the secrets
  guard; nothing else)
- `company/METHOD.md` (one row in the state-file table for costs.log;
  nothing else)

Nothing else. Anything not listed is read-only to you. If the fix you need
lives outside these paths, report it; do not make it.

## Invariants in play (must not break)

- Hooks fail OPEN on internal error (except immutability checks) - copy the
  `except Exception: sys.exit(0)` shape.
- Python 3.8 stdlib only; bash 3.2 compatible anything shell.
- Every block/bypass logs one line to company/state/adherence.log via
  _common helpers.
- All 74 existing hook tests stay green; `npm test` (31 CLI tests) stays
  green - your additions must not disturb the install pack (check
  package.json "files": settings.json and hooks/*.py DO ship).
- Writing style hook-clean: straight quotes, ' - ' not em dashes, three
  dots not the ellipsis character (no_slop blocks you otherwise).
- All agents you spawn run on opus (models.json routes; guard_models
  enforces - never override models in spawn calls).

## Frozen surfaces nearby (CR, never edit)

- `company/state/gates.status`, `company/state/adherence.log` (always-frozen;
  your hooks append to costs.log/adherence.log via direct open(), which is
  allowed - the freeze blocks Edit/Write tools).
- `.env*`, lockfiles.

## Scope (ordered)

1. **guard_secrets.py** (issue #15). New PreToolUse Bash hook. On
   `git commit` in the command: run `git diff --cached -U0` (5s timeout,
   copy the _git subprocess pattern), scan ADDED lines for:
   AWS access keys (`AKIA[0-9A-Z]{16}`), GitHub tokens
   (`ghp_[A-Za-z0-9]{36}`, `github_pat_[A-Za-z0-9_]{22,}`), Anthropic/OpenAI
   keys (`sk-ant-[A-Za-z0-9-]{20,}`, `sk-[A-Za-z0-9]{20,}`), Slack tokens
   (`xox[baprs]-[A-Za-z0-9-]{10,}`), private key headers
   (`-----BEGIN( RSA| EC| OPENSSH| PGP)? PRIVATE KEY-----`), JWTs
   (`eyJ[A-Za-z0-9_-]{20,}\.eyJ`), and a generic
   `(api[_-]?key|secret|token|passw(or)?d)\s*[:=]\s*['\"][A-Za-z0-9_/+=-]{16,}`.
   Skip files ending `.example`, `.sample`, `.template`, paths under any
   `tests/` or `fixtures/` directory, and lines containing `secret-ok:`.
   Block message: file, line number, pattern name, recipe (unstage the file,
   move the value to env, commit a placeholder). HOTFIX MODE DOES NOT BYPASS
   THIS HOOK - document that deviation in the module docstring. Also
   implement `--scan-branch <base>` CLI mode: same scan over
   `git diff <base>...HEAD`, table + `SECRETS_JSON: {...}` line, exit 0/1
   (wave 2 reuses it). Register in settings.json next to guard_commit.
2. **cost_capture.py** (issue #16). New hook on Stop AND SubagentStop
   (register both). Read the JSON payload from stdin; take
   `transcript_path` + `session_id`. Parse the transcript JSONL: for lines
   where `type == "assistant"`, read `message.model` and `message.usage`
   (input_tokens, output_tokens, cache_creation_input_tokens,
   cache_read_input_tokens). Dedup with a byte-offset cursor at
   `company/state/.cost-cursor.json` keyed by session_id; on transcript
   shrink (compaction) reset offset to 0 and use the stored cumulative
   totals to log only the delta - never double-count. Append one line per
   invocation to `company/state/costs.log`:
   `<iso-ts> | <session8> | <stop|subagent_stop> | <task-or-dash> | <model> | in=N out=N cache_r=N cache_w=N | est=$X.XX`
   Task slug from c.active_task(root). Cost estimate only if
   company/models.json has a "pricing" map (add one: opus in=15 out=75 per
   MTok, cache write 1.25x in, cache read 0.1x in, with a $comment marking
   them estimates); tokens-only line otherwise. Never blocks - always exit 0.
3. **frozen list**: add `company/state/costs.log` (and the cursor file) to
   the "always" list in company/frozen-surfaces.json (and
   guard_frozen.py ALWAYS_DEFAULTS if the pattern list lives there too).
4. **standup Spend line** (issue #16): /standup skill additionally tails
   company/state/costs.log and reports spend for today and for the active
   task (sum the est=$ column; tokens if no pricing).
5. **gates_detect models gate** (issue #17): in gates_detect.py add a
   stack-independent proposal
   `{"name": "models", "command": "python3 .claude/hooks/guard_models.py --check", "blocking": true}`
   emitted for every stack (it needs only python3, which the hooks already
   require). Order it before the test gates (cheap). Do NOT write it into
   the tracked template gates.config.
6. **Tests** (tests/hooks/test_hooks.py or a sibling module in tests/hooks/):
   guard_secrets - each pattern class blocks; .example/fixture/secret-ok
   skips pass; hotfix does NOT bypass; --scan-branch exit codes.
   cost_capture - parses a synthetic transcript, cursor dedup across two
   invocations, compaction reset without double-count, no pricing -> tokens
   only, malformed payload -> exit 0 silently.
   gates_detect - proposal list now contains the models gate for a bare
   package.json repo and for a no-stack repo.
7. **Docs**: README rules-table row for the secrets guard; METHOD.md
   state-table row for costs.log.

## Integration seams

- Wave 2 (not yours) consumes `guard_secrets.py --scan-branch` - keep its
  JSON shape stable: `SECRETS_JSON: {"hits": [{"file","line","pattern"}], "scanned": N}`.
- You guarantee: settings.json changes are additive (merge-safe with user
  settings per install.sh behavior); no existing hook entry is reordered.

## Definition of Done

Universal DoD plus:
- [ ] Every scope item implemented and tested
- [ ] Evidence ladder green - this repo's real suite, run directly:
      `python3 -m unittest discover -s tests/hooks -q` AND `npm test`
      (paste both outputs). The tracked gates.config stays placeholder;
      for local commit-gate integrity you may run
      `python3 .claude/hooks/gates_detect.py --write` INSIDE your worktree
      but MUST NOT stage/commit company/gates.config.
- [ ] No edits outside owned directories; zero frozen surfaces patched
- [ ] Tests added for new behavior (tests are the oracle - never edited to pass)
- [ ] Commits per company/GIT.md: conventional, `Task: wave1-enforcement`
      trailer, explicit paths staged (never git add -A)
- [ ] Report per company/templates/REPORT-TEMPLATE.md

## Fallback assumptions

- OQ-W1-01: exact pricing numbers -> FALLBACK: opus $15/MTok in, $75/MTok
  out, cache-write 1.25x in, cache-read 0.1x in, marked "estimate only" in a
  $comment. Tag `// OQ-W1-01` equivalent in the JSON $comment.
- OQ-W1-02: generic sk- pattern false-positives -> FALLBACK: require >= 20
  chars after the prefix; fixtures/secret-ok escape hatch covers the rest.
- OQ-W1-03: transcript missing, unreadable, or schema-drifted -> FALLBACK:
  fail open (exit 0, no log line). Never block a stop.
- OQ-W1-04: Stop payload field names differ across Claude Code versions ->
  FALLBACK: read defensively (`.get`), bail silently when absent.
- OQ-W1-05: costs.log line format details -> FALLBACK: exactly the format in
  scope item 2; keep it one-line greppable, pipe-separated.

## Out of scope

- risk_score.py, witness manifest, trace_check, CVE gate (wave 2)
- RELEASE/acceptance/postmortem doctrine (wave 3)
- Any change to company/gates.config template content, ORCHESTRATOR.md,
  GATES.md, agent definitions, models.json roles
- README/docs beyond the two rows named in scope

## Report back

Your report must contain, as facts: what changed (paths), both suite outputs
pasted, FR/scope checklist, ownership diff summary (`git diff --name-only
main..HEAD`), CRs filed, deviations from this brief and why, worries for the
CEO, and 1-3 proposed witness markers for wave 2 to record (which exact
guard lines are load-bearing).
