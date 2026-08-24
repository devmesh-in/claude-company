# RELEASE 0.3.3 - opencode nested dispatch and background subagents

_Prepared: 2026-08-24. Target: `task/harness-e2e` merge into `main`. Prepared by: CEO._
_Status: PROPOSED - awaiting owner. The company prepares; the owner ships._

## Contents

- The generated `.opencode/opencode.json` carries `subagent_depth: 2`: opencode's
  default of 1 strips the task tool from every lead session, so a tech-lead could
  describe its crew but never dispatch it. Verified live against real opencode
  1.18.21 - the depth-1 failure was reproduced, then a depth-2 nested spawn
  returned through lead to CEO.
- Background subagents (`task(background=true)`) made reachable at install time.
  The flag is read from the process environment before opencode starts and no
  config-file or plugin spelling enables it later (probed empirically), so
  `wire_background_subagents_env` in lib/payload_paths.sh - one shared
  implementation for install and update - wires it into the shell rc, macOS GUI
  (launchctl setenv), and the Windows user environment under WSL.
  `--no-background-subagents-env` is a full opt-out.

## Readiness

| # | Criterion | Result |
|---|---|---|
| R1 | gate ladder green, stamp fresh | **GREEN** - ladder below |
| R2 | `witness_check.py --check` | **GREEN** - exit 0, 35 witnesses, 0 failed |
| R3 | `trace_check.py` | **GREEN** - 23 requirements, 0 orphans |
| R4 | `guard_models.py --check` | **GREEN** - all 10 roles agree with the manifest |
| R5 | dependency audit (G8) | **NOT WIRED** - zero runtime/dev dependencies, as in 0.3.2 |
| R6 | security-reviewer verdict | **NOT REQUIRED** - installer env wiring reviewed by two auditor passes (one HALT on opt-out leakage + test-suite machine mutation; both fixed, re-audit SHIP) |
| R7 | no P0 or P1 worry | **RED, OWNER-ACCEPTED** - five follow-ups filed instead of fixed: #136 frozen-surfaces.json does not protect itself (both harnesses), #137 launchctl coverage lost at reboot, #138 Stop chain unobserved headless, #139 guard_commit false positive on out-of-tree repos, #140 migrate to an upstream config key when one exists |
| R8 | no undecided CR | **GREEN** - none filed against this work |
| R9 | no red task in release scope | **GREEN** - task harness-e2e complete |

### R1 ladder, pasted

```
Gate ladder
GATE                     RESULT TIME
------------------------ ------ ------
hooks                    PASS   (see company/state/gates.log)
tests                    PASS   (see company/state/gates.log)
```

Full six-suite run on the release tree: hooks OK (721), CLI 62/62, installer 97/97,
TUI 22/22, update 139/139, harness 165 checks ALL GREEN (43 core + 20 handlers +
21 renderer + 35 install/update + 46 real-binary).

## Claude side unchanged

A default (claude-only) install from this branch was diffed byte-for-byte against
a default install from the pre-release main: identical `.claude/` trees, identical
file lists, zero `$HOME` writes. `git diff main...branch -- .claude/` is empty.

## Semver

0.2.x -> 0.3.x patch-level per owner precedent (0.3.2); no breaking change: new
behavior activates only when the opencode harness is selected.
