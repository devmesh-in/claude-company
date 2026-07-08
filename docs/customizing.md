# Customizing

Everything the company runs on is a plain file in your repo. This guide covers the changes people make most: gates, protected files, process depth, and the team itself. Edit, commit, done; no rebuild step exists.

| I want to... | Edit | Section |
|---|---|---|
| Add or change a test gate | `company/gates.config` | [Gates](#add-or-change-gates) |
| Protect a file from agent edits | `company/frozen-surfaces.json` | [Protect a file](#protect-freeze-a-file) |
| Give a request more or less process | say it, or `company/METHOD.md` | [Tune process](#tune-how-much-process-a-request-gets) |
| Change a role's instructions or model | `.claude/agents/<role>.md` | [Change the team](#change-the-team) |
| Undo a founding default | `company/frozen-surfaces.json`, `CLAUDE.md` | [Founding defaults](#adjust-the-founding-defaults) |
| Change the enforcement itself | `.claude/hooks/` | [Enforcement](#change-the-enforcement-itself) |

## Add or change gates

Gates live in `company/gates.config`:

```json
{
  "gates": [
    { "name": "lint", "command": "npm run lint", "blocking": true },
    { "name": "tests", "command": "npm test", "blocking": true }
  ]
}
```

Rules that keep the ladder useful:

- Order cheap to expensive (lint before tests before build) so failures surface fast
- Every command must exit non-zero on failure, or the gate cannot block anything
- Add gates you intend to keep. There is no non-blocking mode, because a warnable gate becomes a skippable gate

To rebuild the config from your project automatically, run:

```bash
python3 .claude/hooks/gates_detect.py --write
```

It detects package scripts, pytest, Go, Cargo, and Makefiles, and only replaces placeholder entries; gates you wrote by hand are kept.

## Protect (freeze) a file

Add an entry to `company/frozen-surfaces.json`:

```json
{
  "surfaces": [
    { "pattern": "src/db/schema.*", "why": "single source of truth for data shapes", "change_via": "CR" }
  ]
}
```

Patterns match against the file path and its basename. From then on, every agent edit to a matching file is blocked, and the block message points the agent to the change-request process. Good candidates: schemas, shipped migrations, payment code, generated files, and anything with exactly one legitimate writer.

`.env` files, lockfiles, and the gate stamp are protected out of the box.

## Tune how much process a request gets

The CEO sizes each request automatically: `ideation`, `quick`, `feature`, `program`, or `hotfix`. The sizing rules live in `company/METHOD.md` under "Ceremony scales with the task". Two useful overrides:

- Say the class in your request ("treat this as a quick fix") and the CEO will honor it
- For a production fire, say hotfix. Hooks log instead of block, and the process catches up afterward

If features in your project keep getting more ceremony than they deserve, edit the class table in `METHOD.md`; it is canon, and the agents follow it.

## Change the team

Each role is one markdown file in `.claude/agents/`. The file's frontmatter sets the model and tool access; the body is the role's standing instructions.

- **Adjust a role**: edit its file. Keep instructions short and explain why a rule exists; agents follow reasons better than bare orders.
- **Add a role**: copy the closest existing file, rename it, and describe when it should be used in the `description` field. The CEO dispatches based on that description.
- **Change models**: routing is declared in `company/models.json`, one line per role, and enforced by a hook - a spawn that overrides a role's model, or an edit that changes an agent's `model:` frontmatter away from the manifest, gets blocked until you change the manifest first. That makes every routing change a deliberate, recorded decision instead of silent drift. Your main session (the CEO) is not in the manifest; it runs whatever model you launched Claude Code with.

  Two pieces of advice from how we run it: give the CEO the strongest model you have - it does the judgment work (verification, arbitration, judging evidence) - and keep workers on `opus`. On a tighter budget, downshift roles in the manifest to `sonnet`: developers tolerate it best, the auditor worst. Check agreement anytime with `python3 .claude/hooks/guard_models.py --check`.

Two roles are load-bearing; change them carefully. `tech-lead` is the only agent allowed to spawn other agents, and `developer` carries the working rules every builder inherits.

## Adjust the founding defaults

During self-onboarding the company freezes migration and schema files, wires detected gates, and records its choices for your veto. If it froze something you need fluid, remove the entry from `frozen-surfaces.json`. If it missed a convention your team cares about, add it to your project's `CLAUDE.md`; every agent reads that file first.

## Change the enforcement itself

The hooks are readable Python in `.claude/hooks/`, wired in `.claude/settings.json`, with tests in `tests/hooks/`. If you change a hook, run the suite:

```bash
bash tests/hooks/run_tests.sh
```

One caution: the hooks are the part of the system that keeps the rest honest. Weakening them quietly turns every other promise in this repo back into hope.
