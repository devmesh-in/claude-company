# RESUME / HANDOFF - read this first

_The restart point. Sessions die; work must not. The CEO updates this after
every spawn, merge, CR decision, and agent report. If a session died mid-flight,
check each worktree's git log before respawning - work may be complete on disk
without a report._

## 1. Program state at handoff

Adoption program SHIPPED 2026-07-10. Merged: #27 (wave 1), #33 (wave 2 enforce, ex-#29), #34 (wave 2 doctrine,
ex-#30), #32 (wave 3), #35 (close-out). Integrated main verified: 147 hook
tests + 31 CLI green, witness registry 9/9, gates_detect proposes
witnesses/models/tests/audit. Owner acceptance recorded (DECISIONS #3).

## 2. Next actions, in order

1. delegation-enforcement SHIPPED 2026-07-10 (PR #49, f9e5dae, closes
   #42-#47; acceptance DECISIONS #4). Close-out PR in flight if session
   died mid-close: witnesses W-011..W-013 recorded, brief archived to
   shipped/, active-task cleared - check chore/delegation-closeout branch
   state before redoing.
2. THE NEW GATES ARE LIVE ON MAIN. Every feature/program dispatch now
   requires, in active-task.json BEFORE work: "issues": [...] (GitHub,
   PR mode) and "execution": "delegated"|"self" + "execution_why". The
   context pin injects state every turn; self-built source needs an
   auditor pass at the current tree before commit/close. Do not fight
   the hooks - they are the product.
3. Candidate next: #36 (audit ENOLOCK), #37 (stamp-root mismatch +
   subagent worktree commits - CEO lands commits meanwhile), doc-sync of
   README/docs if they inventory hooks (guard_provenance + context_pin
   are new), or roadmap #1-#11.
2. After merge: docs-librarian sync if docs cover hooks; witnesses via
   witness_check.py --add from the lead's proposed markers.
3. Then: #36 (audit ENOLOCK), #37 (stamp-root mismatch), or roadmap #1-#11.
2. Deferred by owner (revisit on ask): lessons loop, loop workers, model
   tiering, gates.local.config override (WORRIES row).
3. Field lessons for spawn prompts: witness markers MUST be single-line
   verbatim substrings (W-010 incident, PR #41); dispatched subagents
   cannot commit in worktrees (#37) - plan for CEO landing; a stale MAIN
   stamp blocks worktree commits - restamp main first.

## 3. In flight

| Agent | Task | Worktree | Last known state |
|---|---|---|---|
| - | - | - | - |

## 4. Facts every spawn prompt needs

- Gate suite for THIS repo, run directly:
  `python3 -m unittest discover -s tests/hooks -q` AND `npm test`.
- The tracked company/gates.config keeps its CONFIGURE-ME placeholders (it
  ships to installs) - never commit real gate commands into it. The CEO
  keeps an uncommitted local wiring (hooks + tests gates) for honest
  stamps; rewire with gates_detect --write + hooks gate if lost.
- Writing must stay hook-clean: straight quotes, ' - ', three dots.
- All roles opus (owner veto on tiering). Never override models in spawns.
- PR mode: origin=github.com/devmesh-in/claude-company, gh authed as
  Redomic. Owner authorized CEO merges 2026-07-10 (recorded in DECISIONS).
  Branch protection: 9 CI checks + strict up-to-date (use
  `gh pr update-branch` when BEHIND).
- NEVER manually delete a remote branch that is a stacked PR's base - it
  CLOSES the child PRs (cost us #29/#30, recreated as #33/#34). Merge with
  `gh pr merge --delete-branch` or retarget children first.
- Hooks: Python 3.8 stdlib, fail open, import _common as c. guard_commit
  now resolves the branch from the payload cwd (worktree commits work).
- Witness registry: company/witnesses.json, mutate ONLY via
  `python3 .claude/hooks/witness_check.py --add/--remove`.
- Never `git add -A`; stage explicit paths; `Task: <slug>` trailer.

## 5. Done log (chronological, compressed)

- 2026-07-09: external framework deep research (3 explorers + design pass); plan
  approved; tiering vetoed; lessons/workers deferred; issues #15-#25.
- 2026-07-09: wave 1 built + verified (guard_secrets, cost_capture, models
  gate); PR #27. Dogfooding found #26 (guard_commit worktree bug).
- 2026-07-09: wave 2 built by two parallel leads + CEO verification +
  auditor SHIP on both; PRs #29/#30 (later #33/#34). Auditor found #31.
  Doctrine lead found #28.
- 2026-07-10: wave 3 built + verified (RELEASE doctrine, /release,
  acceptance record, postmortem); PR #32.
- 2026-07-10: owner authorized end-to-end merge; stack merged
  #27 -> #33 -> #34 -> #32 -> #35 (close-out: witnesses W-004..W-009,
  briefs archived). Integrated main verified green. Program closed;
  acceptance recorded.
- 2026-07-10: follow-up pair shipped. docs-sync (docs-librarian): README +
  docs/ synced with the program, new root CLAUDE.md - PR #39, closes #28.
  adr-hardening (developer): guard_frozen blocks minting pre-accepted
  ADRs - PR #38, closes #31. Close-outs #40/#41 (W-010; first marker was
  line-wrapped and the witness gate itself caught it - fixed verbatim).
  New bugs filed from integration: #36 (audit ENOLOCK), #37 (stamp-root
  mismatch + subagent worktree-commit blocker). Witnesses 10/10 on main.
- 2026-07-10: delegation-enforcement shipped (PR #49, issues #42-#47,
  DECISIONS #4-#5). 5 layers + FR-DE-15 tracking gate; one tech-lead +
  2 devs; CEO drill caught the porcelain dir-collapse dodge (-uall fix);
  auditor SHIP after 1 coverage fix; 213+31 green x3. Witnesses
  W-011..W-013. Field lessons: two-step cd-then-commit lets the CEO land
  worktree commits (#37 workaround); strict up-to-date protection
  silently defeats owner merge clicks when another PR lands first - use
  gh pr update-branch and re-ask; the classifier will NEVER let the CEO
  merge its own PR - plan the owner click into every delivery.
