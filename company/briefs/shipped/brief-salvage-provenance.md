# BRIEF: salvage-provenance

_Type: feature. Lead: tech-lead. Date: 2026-08-13. Issue: #120._

## Mission

`guard_provenance.py` is 1,135 lines - a fifth of the whole hook layer -
delivering ONE working gate. Take the four fixes worth keeping from a lane that
was closed unmerged, cut the two modes that have never fired, and leave the file
smaller and honest.

Hard constraint: **you are NOT reinstating the audit-scope narrowing.** PR #112
was closed after two independent HALT verdicts, DECISIONS #22. The narrowing made
the audit demand depend on a ledger the gated party can delete; every patch to
survive that created a new unlock, and the last one turned a DO-NOT-SHIP verdict
into an unlock. Mode C keeps arming on dirty source exactly as it does today.

## Salvage - four fixes, all cleared by the first audit

1. **`state_lock` on every ledger read-modify-write** (modes A, B-pre, B-post).
   It has ZERO call sites on main today: the concurrency layer written for
   multi-session tasks is dead code while the ledger it was written for is
   read-modify-written unlocked from every session. Prove it with a real
   two-process race whose UNLOCKED arm is asserted to lose a row - a race test
   that only shows the locked case passing proves nothing.
2. **Unattributed dispatches.** A builder spawn whose task file is unreadable
   must record an UNATTRIBUTED dispatch rather than silently nothing. A vanished
   dispatch produces a false "delegated but no dispatch" block later, and the
   agent has no way to know that is what happened.
3. **The hardcoded worktree test at :233.** `in_worktree_or_out_of_tree` matches
   the literal `/.claude/worktrees/` while `_common` now derives the answer.
   Use the derived primitive. Two answers to one question is the exact class
   #107 fixed and #118 removed everywhere else.
4. **`dirty_source_paths` reads a falsy `_git` result as a clean tree.** #118
   added `git_result` returning GIT_ANSWERED / GIT_REFUSED / GIT_SILENT; this
   caller still collapses them. Under CPU contention a slow `git status`
   silently disarms every arming condition - measured, not theoretical.
   **Fail CLOSED here**: an unanswered tree is dirty, not clean. Say in your
   report that you did, and why, since it inverts the file's usual posture.

## Cut modes D and E

Mode E has NEVER fired - zero "no execution decision" and zero "delegated but no
dispatch" lines in five weeks of `company/state/adherence.log`. Mode D has never
fired and can deadlock: `mode_b_post` returns early for a worktree cwd and
records no audit, while `mode_d` blocks demanding one, so the auditor runs, the
result is discarded, and Stop blocks again.

Keep mode C. It fired six times and it is the working gate.

**Prove the cut is safe rather than asserting it.** Any test that passes only
because D or E existed must be shown failing for the right reason before you
delete it. A test deleted with its behavior is correct; a test deleted because
it was in the way is not.

## Three dangling references, now false in shipped code

`guard_commit.py:16` claims gates "still block task completion via stop_gate" -
that hook is deleted. `guard_provenance.py:952` says "Mirrors stop_gate.py".
`gate_stamp.py:71` points at it in past tense. Three comment edits.

## You own

`.claude/hooks/guard_provenance.py`, `.claude/hooks/guard_commit.py` (the
docstring only), `.claude/hooks/gate_stamp.py` (the comment only),
`tests/hooks/test_guard_provenance.py`, and any test file that only tests D or E.

NOT `_common.py`, NOT `risk_score.py` - other lanes are in flight there.

## Definition of Done

- [ ] Two-process race tests with the unlocked arm asserted to LOSE
- [ ] The GIT_SILENT path fails closed, with a test that drives it
- [ ] Modes D and E gone, with the safety of each deletion demonstrated
- [ ] `grep -rn stop_gate .claude/hooks/` returns nothing
- [ ] Line count before and after in your report - this file's size is the point
- [ ] Suites: hooks, `npm test`. SKIP the installer, TUI and update suites -
      nothing here can reach them, and the update suite alone is 600 seconds.
- [ ] Conventional commits, `Task: salvage-provenance` trailer, explicit paths

## Report back

What changed, the line count delta, the race evidence, the deletion-safety
evidence, what you deliberately did NOT reinstate, and 1-3 witness candidates.
