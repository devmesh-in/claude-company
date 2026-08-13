# CLAUDE.md - project canon for claude-company

Read this first, every spawn. This repo IS the claude-company product: the
installer, hooks, skills, agents, and `company/` canon that ship into user
projects. When you work here you are building the machine other repos install,
not running a company against an app.

## The dual-nature rule (read before touching company/)

`company/` ships verbatim into every install, so it must stay generic. The
tracked `company/gates.config` keeps `CONFIGURE ME` placeholder gates on
purpose - they are what a fresh install inherits before onboarding wires real
commands. NEVER commit this repo's real gate commands into it. The suites that
actually gate THIS repo are run directly, not through `run-gates.sh`:

```bash
python3 -m unittest discover -s tests/hooks -q   # the hooks
npm test                                          # CLI ONLY - tests/cli/test_cli.sh
bash tests/install/run_tests.sh                   # installer + the run-gates.sh runner
bash tests/install/test_tui.sh                    # the install TUI
bash tests/install/test_update.sh                 # update/rollout, incl. legacy field installs
```

All five must be green before any commit, and CI runs all five plus the pack
manifest, the readme check and the no-slop scan.

**`npm test` is the CLI suite alone.** It does NOT run the installer, TUI or
update suites - only `prepublishOnly` chains those. This file previously said
two suites gate the repo and annotated `npm test` as covering install; both
claims were wrong, and on 2026-08-13 that error reached three sealed briefs and
cost a lane a full rebuild after CI caught a regression that two green local
suites had missed. If you change anything under `company/run-gates.sh`,
`install.sh`, `update.sh` or `lib/`, the installer suite is the one most likely
to catch you, and it is the one nobody runs by habit.

## Layout

| Path | What it is |
|---|---|
| `bin/`, `lib/`, `install`, `install.sh` | The CLI and installer that copy the payload into a project |
| `.claude/hooks/` | The enforcement hooks (Python) and their CLIs |
| `.claude/skills/` | Slash commands (`/orchestrator`, `/release`, `/standup`, ...) |
| `.claude/agents/` | The role definitions the CEO dispatches |
| `company/` | The canon, templates, and state that ship into installs |
| `tests/` | `tests/hooks/` (Python) and `tests/cli`, `tests/install` (bash) |
| `docs/` | Client-facing guides |

## Enforcement facts

- Hooks are Python 3.8 stdlib only and fail OPEN: an internal error lets the
  action through rather than jamming a session. The two integrity CLIs are the
  exception and fail LOUD - `witness_check.py` and `trace_check.py` on an
  orphan.
- `no_slop` applies to ALL writing: straight quotes, ' - ' not em dashes,
  three dots not the ellipsis character, no stock AI filler. A CI job scans
  every tracked text file for the same glyphs.
- The witness registry (`company/witnesses.json`) is checksum-sealed and
  mutated ONLY via `python3 .claude/hooks/witness_check.py --add/--remove` -
  never hand-edited.
- Accepted ADRs (`company/adr/`, `Status: accepted`) are immutable: a guard
  blocks edits, and a settled decision changes only through a superseding ADR.
- `CLAUDE.md` is NOT in the `package.json` pack list - it is repo-local canon
  and does not ship into installs. Keep it that way.

## Commits

Conventional subject scoped to the workstream, a `Task: <slug>` trailer, and
explicit staged paths - never `git add -A`. Work belongs on the task branch;
the commit guard blocks direct commits on `main` while a task is active.
