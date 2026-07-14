# WORRIES - the ledger of the un-acted-on

_Things observed but not yet run down: integration traps, flake sources, spec
ambiguities, anything that produced a surprise or a false-green. One row per
worry, brutally terse. Add a row the moment you notice it. Read this at the
start of every integration or audit step. A row graduates OUT when it becomes a
filed CR, a STATUS risk, or a verified fix - delete it then. P0 blocks a
wave/merge; P3 is polish._

| P | Worry | What (one line) | CEO logic (one line) |
|---|---|---|---|
| P2 | gates.config template-vs-local tension | On the product repo itself, tracked gates.config must stay placeholder (ships to installs) so stop_gate/guard_commit need uncommitted local wiring - a papercut every session | Consider gates.local.config override in run-gates.sh; candidate issue after wave 2 |
| P3 | costs.log accuracy limits | Multi-model stop intervals book tokens to the last model; sub-half-cent stops log est=$0.00 | Known limits from wave-1 report; revisit if spend reporting starts driving decisions |
| P2 | staging stales a provenance audit | work_hash includes diff --cached, so git add AFTER the auditor pass stales the audit even with identical content | Auditor worry #2: doc the order (stage, then audit, then commit) in ORCHESTRATOR step 7 wording next doctrine touch; operational for now |
| P3 | git -C evades guard_commit subcmd parse | guard_commit.git_subcmd treats -C <dir> as the subcommand token, so `git -C x commit` bypasses commit gates (pre-existing, Mode C inherits) | Anti-adversary, out of doctrine scope; candidate issue against guard_commit |
| P3 | Mode D lacks worktree-cwd exemption | Stop close-gate block message reads wrong if a worktree session ever gets an active-task.json (moot today - file is untracked) | Auditor worry #3; per-spec (mirrors stop_gate); revisit only if worktree sessions gain task state |
| P2 | session_start 60-line cap can hide digest | Saturated RESUME+STATUS could truncate the active-task + execution digest lines | Lead worry P2, inherited behavior; candidate tail-reservation tweak in session_start |
| P2 | update.sh duplicates install.sh merge heredocs | The three merges (settings/mcp/CLAUDE block) + CC_BLOCK are copied verbatim; a future install.sh merge change silently diverges update | cli-update lead worry; candidate fixture test asserting install and update produce identical merges; extraction forbidden this pass by additive-only brief |
| P3 | update spawns python3 per file (~3x/file) | ~180 spawns for 61 files - seconds today, slow at scale | Candidate manifest.py hashtree batch subcommand; not blocking |
| P3 | manifest emission fails open at install | lib/ or package.json missing -> no manifest, update runs bootstrap-safe forever (never clean "updated") | By design (safe); revisit only if field reports show chronic manifest-less installs |
| P3 | extensionless files count as source | guard_spec.is_source flags any extensionless file outside company/.claude/docs/.github (e.g. Makefile, a bare "report") - a non-code agent writing one hits the execution gate | Found in owner-requested gate probe 2026-07-15; md/json/state are proven exempt; candidate: extensionless allowlist if it ever bites |
| P3 | guard_tests gates md inside tests/ | Any write under a tests/ segment is blocked without test_scope regardless of extension, incl. tests/**/*.md (docs-librarian MODULE.md case) | Defensible (tests are the oracle) but extension-blind; candidate: exempt NON_SOURCE_EXT under tests/ if doc syncs start colliding |
