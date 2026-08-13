# ADR-0003: The audit demand is scoped to recorded self-authorship

Status: proposed
Date: 2026-08-13

Written under FR-HP-47 (`company/specs/spec-harness-port.md`), for task
hp-provenance, issue #101. The status flip to `accepted` is requested by
CR-HP-2 - a new ADR is born proposed and only the CEO accepts it (ADR-0001).

## Context

METHOD mechanism 5 says: nothing SELF-AUTHORED integrates on the authority of
the context that produced it. `guard_provenance` is what makes that mechanical
rather than aspirational - Mode C blocks a commit and Mode D blocks task close
while the main checkout holds unaudited work.

The code has never asked that question. It asked a tree-shaped one instead:
`dirty_source_paths(root)` returns every dirty source path under the project
root, and any single one of them armed the demand. Authorship never entered the
decision. Two failures follow from that gap, and they point in opposite
directions, which is why one fix had to address both.

**It blocks work nobody in this company authored.** Measured against a real
polyrepo umbrella install on 2026-07-29: 71 paths blocked a clean, fully
delegated session from reaching Stop. Sixty-six were Playwright screenshots and
console logs, one was an `ORCHESTRATOR.md.new` that `claude-company update`
creates itself, the rest were a stray png, two fonts and an html file. The
company had authored eight files, all of them clean. The intersection of "dirty"
and "self-authored" was zero. The session's only routes out were to fake an
audit or to delete another session's files. Recorded as a P1 in
`company/state/WORRIES.md`; the fuller writeup is the PARK NOTE at the top of
`company/specs/spec-repo-scoped-enforcement.md`, whose own scoping premise was
refuted by the same measurement.

**It lets through work that badly needs a read.** The demand was triggered by
self-authorship and by nothing else, so risk had no vote. `multi-session-tasks`
was a 4,791-line feature touching every enforcement hook; because the lead
committed cleanly from its worktree, the ledger recorded `self_authored = 0`,
Mode C never armed, and no auditor ever read the diff. The dispatch plan had
pre-committed to an audit that then simply never happened, and nothing noticed.
Also a P1 row in `WORRIES.md`.

The same single question sits under both: the gate was measuring the tree when
the doctrine is about provenance and about risk.

## Decision

**The audit demand is armed by what this company is RECORDED as having
authored, or by the diff's risk band - never by the mere presence of dirty
files.** Concretely, at both Mode C (commit) and Mode D (task close), the demand
arms when any of three conditions holds, and it is satisfied, as before, by a
fresh audit at the current `work_hash`:

1. **Recorded self-authorship.** The dirty source paths INTERSECTED WITH the
   ledger's `self_authored` list is non-empty. `self_authored` is written only
   by Mode A, one entry per main-checkout source Edit or Write, and it is
   checksum-sealed inside `company/state/provenance-ledger.json`.
2. **An unverifiable ledger.** When `read_ledger` had to discard history - the
   file exists but does not parse, its checksum does not recompute, or its task
   generation closed - the authorship record is gone, and every dirty source
   path arms the demand again. This is the shipped behaviour, retained
   deliberately as the fail-closed direction. An ABSENT ledger is not this case:
   it means nothing was authored through the hooks, which is exactly what
   condition 1 is entitled to allow.
3. **A high risk band.** `risk_score.py` bands the diff `high`. Delegation does
   not waive it: the hierarchy verifies each piece and nothing checks that
   anyone read the whole. This is the DECISIONS #19 authorization, and it is
   what makes the demand scale with risk rather than only with authorship.

Two exemptions survive unchanged and one is added:

- Location (unchanged): work inside a nested checkout is verified inside the
  hierarchy and is exempt. That exemption is now DERIVED - the nearest ancestor
  directory holding a `.git` entry - instead of matched against the literal
  string `/.claude/worktrees/`, and at Mode C it is judged against the repo the
  commit actually lands in (`guard_commit.seg_git_dir`) rather than the session
  cwd.
- Emergency (unchanged): an ANY-entry hotfix waiver at Mode C, RISK-MST-01,
  accepted, always logged.
- Delegation, entry-shaped (added, FR-HP-45): every gated entry declares
  `execution: delegated`, each has at least one hook-recorded credited dispatch,
  and no dirty path is recorded self-authored. The declaration alone unlocks
  nothing - the two load-bearing conditions are both written by hooks and cannot
  be asserted by the agent being gated.

The evaluation order is load bearing and is part of this decision: dirty ->
fresh audit -> untrusted ledger -> recorded self-authorship -> risk band ->
delegated-with-dispatches. The risk band is evaluated BEFORE the delegation
exemption, so a delegated diff can never waive a high band. It is also computed
only at that point, so the ordinary paths pay nothing for it.

### The accepted hole: source written through Bash

`self_authored` is populated by the PostToolUse Edit/Write/MultiEdit event.
Source written through Bash - a heredoc, `sed`, a generator script - fires no
such event, is never recorded, and therefore no longer arms the demand.

This is a real hole and it is accepted, not overlooked. It is the stated
fallback for OQ-HP-05, it is tagged at its site in
`.claude/hooks/guard_provenance.py`, and it is pinned by a characterization test
in `tests/hooks/test_guard_provenance.py` that ASSERTS the allow and names
OQ-HP-05, alongside a companion assertion that the identical fixture blocks the
moment the same path is recorded through a real Mode A event. If that test ever
fails, the hole closed and this ADR needs superseding.

It is narrow on purpose. Condition 2 covers a tampered or reset ledger, and
condition 3 covers a Bash-written change large or sensitive enough to band
`high`, so what remains is a small Bash-written change against an intact ledger
and a low band. Closing it properly means a PreToolUse Bash source-write
detector, which is a parser for arbitrary shell - a much larger and much less
reliable thing than the hole it would close.

### Why this is mechanism 5 implemented, not relaxed

Mechanism 5's sentence has two halves: nothing SELF-AUTHORED integrates
unaudited, and the producer never grades itself. The old code enforced neither
precisely - it enforced "nothing DIRTY integrates unaudited", which is a
different and strictly cruder proposition that was simultaneously too strict
(the 71 unrelated paths) and too lax (authorship was the only trigger, so a
4,791-line delegated change walked through).

Asking the recorded-authorship question narrows the demand to the sentence's
actual subject. Adding the risk band widens it past authorship to where the
sentence's PURPOSE lies. The producer still never grades itself: every
condition and every exemption is decided from hook-written state - the
`self_authored` list, the credited-dispatch list, the checksum, the audit
records - and the one field an agent writes for itself, `execution:
delegated`, unlocks nothing on its own.

## Consequences

### What becomes an ALLOW that used to BLOCK

Each of these has a decision-table row in `tests/hooks/test_guard_provenance.py`
and a one-line reason it is not a hole.

1. Dirty source that no Mode A event recorded, with an intact ledger and a
   non-high band, at commit and at Stop. Not a hole: it is the doctrine's own
   subject line, and the two escape routes from it - a reset ledger and a high
   band - are both still armed. This is the polyrepo case above.
2. The same case reached through the Bash hole specifically (OQ-HP-05). Not a
   hole in the sense that matters: it is a NAMED and TESTED limitation with a
   stated closing condition, which is the difference between an accepted
   limitation and a trap.
3. Every gated entry delegated with a credited dispatch and nothing self-authored
   dirty, at a non-high band. Not a hole: it is the exemption mechanism 5
   already grants delegated work, and its two load-bearing conditions are
   hook-written.
4. A commit whose target repo is a nested checkout reached via `git -C
   <worktree> commit` from the main checkout. Not a hole: the commit lands on
   the worktree's task branch, `seg_git_dir` accepts the path only when git
   itself answers `--is-inside-work-tree true` there, and it is the same
   location exemption the session-cwd route already granted.
5. A worktree created outside `.claude/worktrees/` now receives the delegated
   exemption at all six modes. Not a hole: it is the exemption a worktree was
   always entitled to, and withholding it was the bug - the kernel already
   resolved such a path correctly, and two answers to one question is the bug
   class #107 fixed.

### What becomes a BLOCK that used to ALLOW

6. A `high` risk band with dirty source and no fresh audit, at commit and at
   Stop, including when the work is fully delegated. This is the compensating
   control for item 1 and the direct answer to the `WORRIES.md` row.
7. A path under `.claude/worktrees/<name>/` where no checkout exists is now
   main-checkout work and is gated as such. Previously the path spelling alone
   bought the exemption.
8. A commit whose payload cwd is outside the project and is not a git work tree
   now resolves to the project root rather than being read as out-of-tree.

### The costs accepted

- The demand now depends on Mode A having fired, so anything that suppresses
  Mode A suppresses the arming. The Bash hole is the known instance; a hook
  that is unwired is the other, and that is what L3's hook-wiring gate covers.
- `risk_score.py` scores `base...HEAD`, so the band is blind to uncommitted
  work and the FIRST commit on a task branch is always scored against an empty
  diff. The risk arming is therefore effective from the second commit onward
  and at task close. Filed as CR-HP-4; not worked around locally, because a
  second risk model in `guard_provenance` would be exactly the numeric fence
  the owner has vetoed twice.
- Mode C and Mode D now spawn `risk_score.py` as a child process, bounded at 10
  seconds and fully fail-open, on the one path where the band can change the
  verdict. No answer never arms anything.
- `guard_provenance` depends on `_common._enclosing_checkout`, a private name.
  Calling it is deliberate - one derivation, not two - and CR-HP-3 asks L1 to
  expose it.

### Enforcement that now binds

- `.claude/hooks/guard_provenance.py` Modes C and D implement the order above;
  Modes A, B-pre and B-post wrap every ledger read-modify-write in
  `_common.state_lock`, so concurrent sessions stop losing dispatch credits.
- `tests/hooks/test_guard_provenance.py` carries the full decision table as one
  test per row for both modes, two-process race tests for all three ledger
  modes, and the OQ-HP-05 characterization test.

## Scope

- `.claude/hooks/guard_provenance.py`
- `company/state/provenance-ledger.json` (its `self_authored` list is the
  authorship record this decision reads)
- `tests/hooks/test_guard_provenance.py`

## Supersedes

none.
